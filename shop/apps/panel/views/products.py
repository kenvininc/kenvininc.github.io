from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Min, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Brand, Category, PriceHistory, Product, ProductImage, StockMovement, Variant, unique_slug
from apps.catalog.services import ConcurrentChange, adjust_stock, set_price
from apps.core.images import process_upload
from apps.core.models import SiteSettings
from apps.core.roles import has_perm, require_perm
from apps.core.text import normalize_search
from apps.core.utils import audit
from apps.orders.models import OrderItem

from ..forms import ProductForm, VariantFormSet
from .common import paginate

BULK_ACTIONS = {
    "publish": ("Chuyển sang Đang bán", {"status": Product.Status.PUBLISHED}),
    "hide": ("Ẩn", {"status": Product.Status.HIDDEN}),
    "draft": ("Chuyển về Nháp", {"status": Product.Status.DRAFT}),
    "featured_on": ("Đánh dấu Nổi bật", {"is_featured": True}),
    "featured_off": ("Bỏ Nổi bật", {"is_featured": False}),
    "new_on": ("Đánh dấu Sản phẩm mới", {"is_new": True}),
    "new_off": ("Bỏ Sản phẩm mới", {"is_new": False}),
    "sale_on": ("Đưa vào khu Đang giảm giá", {"is_on_sale_section": True}),
    "sale_off": ("Bỏ khỏi khu Đang giảm giá", {"is_on_sale_section": False}),
}


@require_perm("manage_products", "manage_content")
def product_list(request):
    site = SiteSettings.load()
    qs = Product.objects.select_related("brand", "category").prefetch_related("images").annotate(
        min_price=Min("variants__price"), max_price=Max("variants__price"), total_stock=Sum("variants__stock"),
        min_stock=Min("variants__stock"),
    )
    q = (request.GET.get("q") or "").strip()
    if q:
        for t in normalize_search(q).split():
            qs = qs.filter(search_text__icontains=t)
    status = request.GET.get("status", "")
    if status in Product.Status.values:
        qs = qs.filter(status=status)
    cat = request.GET.get("category", "")
    if cat.isdigit():
        qs = qs.filter(Q(category_id=cat) | Q(category__parent_id=cat))
    brand = request.GET.get("brand", "")
    if brand.isdigit():
        qs = qs.filter(brand_id=brand)
    stock = request.GET.get("stock", "")
    if stock == "out":
        qs = qs.filter(min_stock__lte=0)
    elif stock == "low":
        qs = qs.filter(min_stock__lte=site.low_stock_threshold)
    home = request.GET.get("home", "")
    if home in ("is_featured", "is_new", "is_on_sale_section"):
        qs = qs.filter(**{home: True})
    page = paginate(request, qs.order_by("-updated_at"))
    return render(
        request,
        "panel/products/list.html",
        {
            "page_obj": page,
            "statuses": Product.Status.choices,
            "categories": Category.objects.select_related("parent"),
            "brands": Brand.objects.all(),
            "bulk_actions": [(k, v[0]) for k, v in BULK_ACTIONS.items()],
            "low_threshold": site.low_stock_threshold,
        },
    )


@require_POST
@require_perm("manage_products", "manage_content")
def product_bulk(request):
    action = request.POST.get("action")
    ids = [int(i) for i in request.POST.getlist("ids") if i.isdigit()]
    if action not in BULK_ACTIONS or not ids:
        messages.error(request, "Chọn sản phẩm và thao tác.")
        return redirect(request.POST.get("back") or "panel:products")
    label, changes = BULK_ACTIONS[action]
    if "status" in changes and not has_perm(request.user, "manage_products"):
        messages.error(request, "Bạn không có quyền đổi trạng thái sản phẩm.")
        return redirect("panel:products")
    count = 0
    for p in Product.objects.filter(pk__in=ids):
        for k, v in changes.items():
            setattr(p, k, v)
        p.save()
        count += 1
    audit(request, "product_bulk", summary=f"{label}: {count} sản phẩm (id {','.join(map(str, ids[:30]))})")
    messages.success(request, f"{label}: đã cập nhật {count} sản phẩm.")
    back = request.POST.get("back", "")
    return redirect(back if back.startswith("/admin/") else "panel:products")


def _save_images(request, product, files):
    errors = []
    start = (product.images.aggregate(m=Max("sort_order"))["m"] or -1) + 1
    has_main = product.images.filter(is_main=True).exists()
    for i, f in enumerate(files):
        try:
            main, thumb = process_upload(f)
        except ValidationError as e:
            errors.append(f"{f.name}: {e.messages[0]}")
            continue
        img = ProductImage(product=product, sort_order=start + i, alt=product.name[:200], is_main=not has_main)
        img.image.save(main.name, main, save=False)
        img.thumb.save(thumb.name, thumb, save=False)
        img.save()
        has_main = True
    return errors


def _product_form(request, product=None):
    is_new = product is None
    product = product or Product()
    can_price = has_perm(request.user, "manage_prices")
    can_stock = has_perm(request.user, "manage_stock")
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    formset = VariantFormSet(request.POST or None, instance=product, prefix="v")
    error = ""
    if request.method == "POST":
        stock_reason = (request.POST.get("stock_reason") or "").strip()[:255]
        price_reason = (request.POST.get("price_reason") or "").strip()[:255]
        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    p = form.save(commit=False)
                    if not p.slug:
                        p.slug = unique_slug(Product, p.name)
                    if is_new:
                        p.created_by = request.user
                    p.save()
                    _save_variants(request, p, formset, can_price, can_stock, stock_reason, price_reason)
                    p.refresh_search_text()
            except ConcurrentChange as e:
                error = str(e) + " Trang đã được tải lại với dữ liệu mới nhất, vui lòng nhập lại thay đổi."
                messages.error(request, error)
                return redirect("panel:product_edit", pk=product.pk) if product.pk else redirect("panel:product_add")
            except _FormProblem as e:
                error = str(e)
                # Transaction đã rollback: tạo lại form từ dữ liệu gửi lên để không giữ pk ảo trong bộ nhớ.
                product = Product() if is_new else Product.objects.get(pk=product.pk)
                form = ProductForm(request.POST, instance=product)
                formset = VariantFormSet(request.POST, instance=product, prefix="v")
                form.is_valid()
                formset.is_valid()
            else:
                img_errors = _save_images(request, p, form.cleaned_data.get("new_images") or [])
                for e in img_errors:
                    messages.error(request, "Ảnh không hợp lệ — " + e)
                audit(request, "product_create" if is_new else "product_update", p, f"{p.code} {p.name}")
                messages.success(request, f"Đã lưu sản phẩm “{p.name}”.")
                if request.POST.get("then") == "view" and p.status == Product.Status.PUBLISHED:
                    return redirect(p.get_absolute_url())
                return redirect("panel:product_edit", pk=p.pk)
        else:
            error = "Vui lòng kiểm tra lại các ô được đánh dấu."
    images = list(product.images.all()) if product.pk else []
    in_orders = (
        set(OrderItem.objects.filter(variant__product=product).values_list("variant_id", flat=True)) if product.pk else set()
    )
    return render(
        request,
        "panel/products/form.html",
        {
            "form": form,
            "formset": formset,
            "product": product if product.pk else None,
            "images": images,
            "error": error,
            "can_price": can_price,
            "can_stock": can_stock,
            "in_orders": in_orders,
        },
    )


class _FormProblem(Exception):
    pass


def _save_variants(request, product, formset, can_price, can_stock, stock_reason, price_reason):
    user = request.user
    for f in formset.forms:
        if not f.cleaned_data:
            continue
        cd = f.cleaned_data
        v = f.instance
        if cd.get("DELETE"):
            if v.pk:
                if OrderItem.objects.filter(variant=v).exists():
                    raise _FormProblem(f"SKU {v.sku} đã có trong đơn hàng nên không xóa được. Hãy bỏ chọn “Đang bán”.")
                v.delete()
            continue
        if not v.pk:
            if not can_price:
                raise _FormProblem("Bạn không có quyền đặt giá cho biến thể mới.")
            new = f.save(commit=False)
            new.product = product
            new.stock = 0
            new.save()
            PriceHistory.objects.create(
                variant=new, old_price=None, new_price=new.price, new_compare_at_price=new.compare_at_price,
                source=PriceHistory.Source.CREATE, reason="Tạo biến thể", changed_by=user,
            )
            if cd.get("stock"):
                if not can_stock:
                    raise _FormProblem("Bạn không có quyền nhập tồn kho.")
                adjust_stock(new.pk, cd["stock"], StockMovement.Kind.INITIAL, user=user, reason="Tồn ban đầu")
            continue

        locked = Variant.objects.select_for_update().get(pk=v.pk)
        new_price, new_compare = cd["price"], cd.get("compare_at_price")
        orig = (cd.get("orig_price"), cd.get("orig_compare"))
        if (new_price, new_compare) != orig:
            if not can_price:
                raise _FormProblem("Bạn không có quyền sửa giá.")
            set_price(locked, new_price, new_compare, user, PriceHistory.Source.MANUAL, price_reason, expected=orig)
        # Lưu các trường khác (không đụng giá/tồn kho đã xử lý ở trên).
        for field in ("value", "sku", "color_hex", "image", "is_active", "sort_order"):
            setattr(locked, field, cd.get(field) if field != "value" else (cd.get("value") or "").strip())
        locked.save(update_fields=["value", "sku", "color_hex", "image", "is_active", "sort_order", "updated_at"])
        if cd.get("stock") is not None and cd.get("orig_stock") is not None and cd["stock"] != cd["orig_stock"]:
            if not can_stock:
                raise _FormProblem("Bạn không có quyền sửa tồn kho.")
            if not stock_reason:
                raise _FormProblem("Có thay đổi tồn kho: vui lòng nhập “Lý do điều chỉnh tồn kho”.")
            adjust_stock(
                locked.pk, cd["stock"] - cd["orig_stock"], StockMovement.Kind.ADJUST, user=user,
                reason=stock_reason, expected=cd["orig_stock"],
            )


@require_perm("manage_products")
def product_add(request):
    return _product_form(request)


@require_perm("manage_products")
def product_edit(request, pk):
    return _product_form(request, get_object_or_404(Product, pk=pk))


@require_POST
@require_perm("manage_products")
def product_delete(request, pk):
    p = get_object_or_404(Product, pk=pk)
    if OrderItem.objects.filter(variant__product=p).exists():
        messages.error(request, "Sản phẩm đã có trong đơn hàng nên không thể xóa. Hãy chuyển sang trạng thái Ẩn.")
        return redirect("panel:product_edit", pk=p.pk)
    files = [(i.image, i.thumb) for i in p.images.all()]
    name = p.name
    with transaction.atomic():
        p.delete()
    for image, thumb in files:
        image.delete(save=False)
        if thumb:
            thumb.delete(save=False)
    audit(request, "product_delete", summary=f"{pk} {name}")
    messages.success(request, f"Đã xóa sản phẩm “{name}”.")
    return redirect("panel:products")


@require_POST
@require_perm("manage_products")
def product_images(request, pk):
    """Upload thêm ảnh, đổi thứ tự, chọn ảnh đại diện, sửa mô tả, xóa ảnh."""
    product = get_object_or_404(Product, pk=pk)
    action = request.POST.get("action")
    if action == "upload":
        files = request.FILES.getlist("images")
        if not files:
            messages.error(request, "Chưa chọn ảnh.")
        else:
            errors = _save_images(request, product, files)
            ok = len(files) - len(errors)
            for e in errors:
                messages.error(request, "Ảnh không hợp lệ — " + e)
            if ok:
                messages.success(request, f"Đã tải lên {ok} ảnh.")
        return redirect(f"/admin/san-pham/{pk}/#anh")
    img = get_object_or_404(ProductImage, pk=request.POST.get("image_id"), product=product)
    images = list(product.images.order_by("sort_order", "id"))
    if action in ("up", "down"):
        i = images.index(img)
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(images):
            images[i], images[j] = images[j], images[i]
            for n, im in enumerate(images):
                if im.sort_order != n:
                    ProductImage.objects.filter(pk=im.pk).update(sort_order=n)
    elif action == "main":
        with transaction.atomic():
            product.images.update(is_main=False)
            ProductImage.objects.filter(pk=img.pk).update(is_main=True)
        messages.success(request, "Đã chọn ảnh đại diện.")
    elif action == "alt":
        img.alt = (request.POST.get("alt") or "").strip()[:200]
        img.save(update_fields=["alt"])
        messages.success(request, "Đã lưu mô tả ảnh.")
    elif action == "delete":
        was_main = img.is_main
        Variant.objects.filter(image=img).update(image=None)
        img.image.delete(save=False)
        if img.thumb:
            img.thumb.delete(save=False)
        img.delete()
        if was_main:
            first = product.images.order_by("sort_order", "id").first()
            if first:
                ProductImage.objects.filter(pk=first.pk).update(is_main=True)
        messages.success(request, "Đã xóa ảnh.")
    audit(request, f"product_image_{action}", product, product.name)
    return redirect(f"/admin/san-pham/{pk}/#anh")
