from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Exists, F, Min, OuterRef, Prefetch, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.catalog.models import Brand, Category, Product, ProductImage, Variant
from apps.content.models import Banner, Page
from apps.core.models import SiteSettings
from apps.core.roles import has_perm
from apps.core.text import normalize_search
from apps.core.utils import RateLimit, client_ip
from apps.orders.models import Order
from apps.orders.services import (
    OrderError,
    build_quote,
    get_cart,
    place_order,
    save_cart,
)

from .forms import CheckoutForm, LookupForm

PAGE_SIZE = 24
SORTS = {
    "moi-nhat": ("Mới nhất", ["-published_at", "-id"]),
    "gia-tang": ("Giá tăng dần", ["min_price", "-id"]),
    "gia-giam": ("Giá giảm dần", ["-min_price", "-id"]),
    "ten": ("Tên A–Z", ["name"]),
}
MY_ORDERS = "my_orders"


def card_queryset(qs=None):
    """Sản phẩm hiển thị cho khách, kèm giá thấp nhất và trạng thái còn hàng."""
    qs = qs if qs is not None else Product.objects.all()
    active = Variant.objects.filter(is_active=True)
    return (
        qs.published()
        .filter(Exists(active.filter(product=OuterRef("pk"))))
        .annotate(
            min_price=Min("variants__price", filter=Q(variants__is_active=True)),
            has_stock=Exists(active.filter(product=OuterRef("pk"), stock__gt=0)),
        )
        .select_related("brand")
        .prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_main", "sort_order", "id")),
            Prefetch("variants", queryset=Variant.objects.filter(is_active=True)),
        )
    )


def _int(value):
    try:
        v = int(str(value).replace(".", "").replace(",", "").strip())
        return v if v >= 0 else None
    except (TypeError, ValueError):
        return None


def listing(request, qs, template_ctx, show_category_filter=True, show_brand_filter=True):
    """Lọc, sắp xếp, phân trang dùng chung cho danh mục, thương hiệu, tìm kiếm."""
    qs = card_queryset(qs)
    base_ids = qs.values("pk")
    facet_brands = Brand.objects.filter(is_active=True, products__in=base_ids).distinct()
    facet_cats = Category.objects.filter(is_active=True, products__in=base_ids).distinct()

    selected_brands = [s for s in request.GET.getlist("thuong-hieu") if s]
    selected_cats = [s for s in request.GET.getlist("danh-muc") if s]
    price_min = _int(request.GET.get("gia-tu"))
    price_max = _int(request.GET.get("gia-den"))
    in_stock = request.GET.get("con-hang") == "1"
    sort = request.GET.get("sap-xep", "moi-nhat")
    if sort not in SORTS:
        sort = "moi-nhat"

    if selected_brands:
        qs = qs.filter(brand__slug__in=selected_brands)
    if selected_cats:
        qs = qs.filter(Q(category__slug__in=selected_cats) | Q(category__parent__slug__in=selected_cats))
    if price_min is not None:
        qs = qs.filter(min_price__gte=price_min)
    if price_max is not None:
        qs = qs.filter(min_price__lte=price_max)
    if in_stock:
        qs = qs.filter(has_stock=True)
    qs = qs.order_by(*SORTS[sort][1])

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("trang"))
    active_filters = bool(selected_brands or selected_cats or price_min is not None or price_max is not None or in_stock)
    ctx = {
        "page_obj": page,
        "products": page.object_list,
        "sorts": [(k, v[0]) for k, v in SORTS.items()],
        "sort": sort,
        "facet_brands": facet_brands if show_brand_filter else [],
        "facet_cats": facet_cats if show_category_filter else [],
        "selected_brands": selected_brands,
        "selected_cats": selected_cats,
        "price_min": price_min,
        "price_max": price_max,
        "in_stock": in_stock,
        "active_filters": active_filters,
    }
    ctx.update(template_ctx)
    return render(request, "store/listing.html", ctx)


@require_GET
def home(request):
    banners = list(Banner.objects.live())
    cards = card_queryset()
    ctx = {
        "hero_banners": [b for b in banners if b.placement == Banner.Placement.HERO],
        "side_banners": [b for b in banners if b.placement == Banner.Placement.SIDE][:2],
        "strip_banners": [b for b in banners if b.placement == Banner.Placement.STRIP],
        "home_categories": Category.objects.filter(is_active=True, show_on_home=True),
        "featured": cards.filter(is_featured=True)[:10],
        "new_products": cards.filter(is_new=True)[:10],
        "sale_products": cards.filter(is_on_sale_section=True)[:10],
        "brands": Brand.objects.filter(is_active=True).exclude(logo="")[:12],
    }
    return render(request, "store/home.html", ctx)


@require_GET
def category(request, slug):
    cat = get_object_or_404(Category.objects.select_related("parent"), slug=slug, is_active=True)
    if cat.parent_id and not cat.parent.is_active:
        raise Http404
    qs = Product.objects.filter(category_id__in=cat.descendant_ids())
    children = cat.children.filter(is_active=True)
    return listing(
        request,
        qs,
        {"title": cat.name, "category": cat, "children": children, "seo_obj": cat},
        show_category_filter=False,
    )


@require_GET
def brand_list(request):
    brands = Brand.objects.filter(is_active=True)
    return render(request, "store/brands.html", {"brands": brands})


@require_GET
def brand(request, slug):
    b = get_object_or_404(Brand, slug=slug, is_active=True)
    return listing(
        request, Product.objects.filter(brand=b), {"title": b.name, "brand": b, "seo_obj": b}, show_brand_filter=False
    )


@require_GET
def sale(request):
    discounted = Variant.objects.filter(
        product=OuterRef("pk"), is_active=True, compare_at_price__isnull=False
    ).filter(compare_at_price__gt=F("price"))
    return listing(request, Product.objects.filter(Exists(discounted)), {"title": "Đang giảm giá"})


@require_GET
def new_arrivals(request):
    return listing(request, Product.objects.all(), {"title": "Hàng mới về"})


@require_GET
def search(request):
    q = (request.GET.get("q") or "").strip()[:100]
    terms = normalize_search(q).split()
    qs = Product.objects.all()
    if terms:
        for t in terms:
            qs = qs.filter(search_text__icontains=t)
    else:
        qs = qs.none()
    return listing(request, qs, {"title": f"Kết quả tìm kiếm: “{q}”" if q else "Tìm kiếm", "query": q, "is_search": True})


@require_GET
def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("brand", "category", "category__parent", "variant_attribute").prefetch_related(
            Prefetch("images", queryset=ProductImage.objects.order_by("-is_main", "sort_order", "id")),
            Prefetch("variants", queryset=Variant.objects.filter(is_active=True).select_related("image")),
        ),
        slug=slug,
    )
    is_preview = False
    if product.status != Product.Status.PUBLISHED:
        if has_perm(request.user, "manage_products") or has_perm(request.user, "manage_content"):
            is_preview = True
        else:
            raise Http404
    variants = list(product.variants.all())
    if not variants and not is_preview:
        raise Http404
    selected = None
    want = request.GET.get("bien-the")
    if want:
        selected = next((v for v in variants if str(v.pk) == want), None)
    selected = selected or product.display_variant
    related = []
    if product.category_id:
        related = card_queryset(Product.objects.filter(category_id=product.category_id).exclude(pk=product.pk))[:8]
    return render(
        request,
        "store/product.html",
        {
            "product": product,
            "variants": variants,
            "selected": selected,
            "images": list(product.images.all()),
            "related": related,
            "is_preview": is_preview,
            "seo_obj": product,
            "policy_links": set(
                Page.objects.filter(
                    status=Page.Status.PUBLISHED, slug__in=["chinh-sach-giao-hang", "chinh-sach-doi-tra"]
                ).values_list("slug", flat=True)
            ),
        },
    )


@require_GET
def page(request, slug):
    p = get_object_or_404(Page, slug=slug)
    is_preview = False
    if p.status != Page.Status.PUBLISHED:
        if has_perm(request.user, "manage_content"):
            is_preview = True
        else:
            raise Http404
    return render(request, "store/page.html", {"page": p, "is_preview": is_preview, "seo_obj": p})


# ---------------------------------------------------------------- Giỏ hàng


def _wants_json(request):
    return request.headers.get("X-Requested-With") == "fetch"


def _cart_response(request, ok, message, status=200):
    if _wants_json(request):
        return JsonResponse(
            {"ok": ok, "message": message, "cart_count": sum(get_cart(request.session).values())}, status=status
        )
    (messages.success if ok else messages.error)(request, message)
    nxt = request.POST.get("next") or ""
    if nxt.startswith("/") and not nxt.startswith("//") and "\\" not in nxt:
        return redirect(nxt)
    return redirect("store:cart")


@require_POST
def cart_add(request):
    site = SiteSettings.load()
    try:
        variant_id = int(request.POST.get("variant_id", ""))
        qty = int(request.POST.get("quantity", "1"))
    except ValueError:
        return _cart_response(request, False, "Vui lòng chọn phân loại sản phẩm.", 400)
    if qty < 1:
        return _cart_response(request, False, "Số lượng không hợp lệ.", 400)
    v = Variant.objects.select_related("product").filter(pk=variant_id).first()
    if not v or not v.is_active or v.product.status != Product.Status.PUBLISHED:
        return _cart_response(request, False, "Sản phẩm này hiện không còn bán.", 400)
    cart = get_cart(request.session)
    new_qty = cart.get(v.pk, 0) + qty
    limit = min(v.stock, site.max_qty_per_item)
    if v.stock <= 0:
        return _cart_response(request, False, "Sản phẩm đã hết hàng.", 409)
    if new_qty > limit:
        msg = (
            f"Chỉ còn {v.stock} sản phẩm."
            if limit == v.stock
            else f"Mỗi đơn tối đa {site.max_qty_per_item} sản phẩm cùng loại."
        )
        if cart.get(v.pk):
            msg += f" Giỏ hàng đã có {cart[v.pk]}."
        return _cart_response(request, False, msg, 409)
    cart[v.pk] = new_qty
    save_cart(request.session, cart)
    return _cart_response(request, True, f"Đã thêm “{v}” vào giỏ hàng.")


@require_POST
def cart_update(request):
    cart = get_cart(request.session)
    for key, value in request.POST.items():
        if not key.startswith("qty_"):
            continue
        try:
            vid, qty = int(key[4:]), int(value)
        except ValueError:
            continue
        if vid in cart:
            if qty <= 0:
                cart.pop(vid)
            else:
                cart[vid] = min(qty, 999)
    save_cart(request.session, cart)
    messages.success(request, "Đã cập nhật giỏ hàng.")
    return redirect("store:cart")


@require_POST
def cart_remove(request):
    cart = get_cart(request.session)
    try:
        cart.pop(int(request.POST.get("variant_id", "")), None)
    except ValueError:
        pass
    save_cart(request.session, cart)
    messages.success(request, "Đã xóa sản phẩm khỏi giỏ hàng.")
    return redirect("store:cart")


@require_POST
def cart_coupon(request):
    if request.POST.get("action") == "remove":
        request.session.pop("coupon_code", None)
        messages.success(request, "Đã bỏ mã giảm giá.")
        return redirect("store:checkout" if request.POST.get("back") == "checkout" else "store:cart")
    code = (request.POST.get("coupon_code") or "").strip().upper()[:40]
    back = "store:checkout" if request.POST.get("back") == "checkout" else "store:cart"
    if not code:
        messages.error(request, "Vui lòng nhập mã giảm giá.")
        return redirect(back)
    limiter = RateLimit("coupon", 20, 600)
    ip = client_ip(request) or "unknown"
    if limiter.hit(ip) > 20:
        messages.error(request, "Bạn thử quá nhiều lần, vui lòng thử lại sau ít phút.")
        return redirect(back)
    quote = build_quote(get_cart(request.session), code)
    if quote.coupon_error:
        messages.error(request, quote.coupon_error)
    else:
        request.session["coupon_code"] = code
        messages.success(request, f"Đã áp dụng mã {code}.")
    return redirect(back)


def cart(request):
    cart_data = get_cart(request.session)
    quote = build_quote(cart_data, request.session.get("coupon_code", ""))
    if quote.removed:
        for vid in quote.removed:
            cart_data.pop(vid, None)
        save_cart(request.session, cart_data)
    if request.session.get("coupon_code") and quote.coupon_error:
        messages.warning(request, f"Mã {request.session['coupon_code']}: {quote.coupon_error}")
    return render(request, "store/cart.html", {"quote": quote})


def checkout(request):
    site = SiteSettings.load()
    cart_data = get_cart(request.session)
    coupon_code = request.session.get("coupon_code", "")
    methods = site.payment_methods()
    form = CheckoutForm(request.POST or None, payment_methods=methods)
    phone = None
    if request.method == "POST" and form.is_valid():
        phone = form.cleaned_data["phone"]
    quote = build_quote(cart_data, coupon_code, phone=phone)
    if not quote.lines:
        messages.info(request, "Giỏ hàng đang trống.")
        return redirect("store:cart")
    if quote.has_problems:
        messages.error(request, "Giỏ hàng có sản phẩm không đủ hàng hoặc ngừng bán, vui lòng điều chỉnh trước khi đặt.")
        return redirect("store:cart")

    error = ""
    if request.method == "POST" and form.is_valid():
        cd = form.cleaned_data
        customer = {k: cd[k] for k in ("customer_name", "phone", "email", "address", "customer_note")}
        try:
            order, _created = place_order(
                cart_data, customer, cd["payment_method"], coupon_code, cd["idempotency_key"]
            )
        except OrderError as e:
            error = str(e)
        else:
            save_cart(request.session, {})
            request.session.pop("coupon_code", None)
            _remember_order(request, order.code)
            return redirect("store:order_success", code=order.code)
    return render(
        request,
        "store/checkout.html",
        {"form": form, "quote": quote, "error": error, "no_methods": not methods},
    )


def _remember_order(request, code):
    codes = [c for c in request.session.get(MY_ORDERS, []) if c != code]
    request.session[MY_ORDERS] = (codes + [code])[-20:]


def _order_for_session(request, code):
    if code not in request.session.get(MY_ORDERS, []):
        raise Http404
    return get_object_or_404(Order.objects.prefetch_related("items"), code=code)


def order_success(request, code):
    order = _order_for_session(request, code)
    return render(request, "store/order_success.html", {"order": order})


def order_view(request, code):
    order = _order_for_session(request, code)
    return render(request, "store/order_view.html", {"order": order})


def order_lookup(request):
    form = LookupForm(request.POST or None)
    error = ""
    if request.method == "POST":
        limiter = RateLimit("lookup", 10, 900)
        ip = client_ip(request) or "unknown"
        if limiter.is_blocked(ip):
            error = "Bạn tra cứu quá nhiều lần. Vui lòng thử lại sau 15 phút."
        elif form.is_valid():
            order = Order.objects.filter(code=form.cleaned_data["code"], phone=form.cleaned_data["phone"]).first()
            if order:
                _remember_order(request, order.code)
                return redirect("store:order_view", code=order.code)
            limiter.hit(ip)
            error = "Không tìm thấy đơn hàng với mã và số điện thoại này."
    return render(request, "store/order_lookup.html", {"form": form, "error": error})


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /admin/",
        "Disallow: /gio-hang/",
        "Disallow: /thanh-toan/",
        "Disallow: /don-hang/",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")
