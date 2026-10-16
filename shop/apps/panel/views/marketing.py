"""Khuyến mãi, banner, trang nội dung, trang chủ và cấu hình cửa hàng."""

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Product
from apps.content.models import Banner, Page
from apps.core.images import process_upload
from apps.core.models import SiteSettings
from apps.core.roles import require_perm
from apps.core.text import normalize_search
from apps.core.utils import audit
from apps.promotions.models import Coupon

from ..forms import BannerForm, CouponForm, PageForm, SettingsForm
from .common import paginate

# ---------------------------------------------------------------- Mã giảm giá


@require_perm("manage_promotions")
def coupon_list(request):
    return render(request, "panel/marketing/coupons.html", {"page_obj": paginate(request, Coupon.objects.all())})


@require_perm("manage_promotions")
def coupon_form(request, pk=None):
    obj = get_object_or_404(Coupon, pk=pk) if pk else None
    form = CouponForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        c = form.save()
        audit(request, "coupon_update" if obj else "coupon_create", c, c.code)
        messages.success(request, f"Đã lưu mã {c.code}.")
        return redirect("panel:coupons")
    return render(request, "panel/form_page.html", {
        "form": form, "title": f"Sửa mã {obj.code}" if obj else "Thêm mã giảm giá", "back": "/admin/khuyen-mai/",
        "object": obj, "delete_url": request.path + "xoa/" if obj and not obj.used_count else None,
        "intro": "Quy tắc: mỗi đơn dùng tối đa 1 mã; mã tính trên tiền hàng (đã là giá bán sau giảm giá sản phẩm), "
                 "không giảm phí giao hàng; số tiền giảm không vượt quá tiền hàng. Đơn bị hủy sẽ trả lại lượt dùng.",
    })


@require_POST
@require_perm("manage_promotions")
def coupon_delete(request, pk):
    c = get_object_or_404(Coupon, pk=pk)
    if c.used_count or c.orders.exists():
        messages.error(request, "Mã đã được dùng trong đơn hàng nên không xóa được. Hãy tắt “Đang bật”.")
        return redirect("panel:coupon_edit", pk=pk)
    code = c.code
    c.delete()
    audit(request, "coupon_delete", summary=code)
    messages.success(request, f"Đã xóa mã {code}.")
    return redirect("panel:coupons")


# ---------------------------------------------------------------- Banner


@require_perm("manage_content")
def banner_list(request):
    return render(request, "panel/marketing/banners.html", {"banners": Banner.objects.all()})


@require_perm("manage_content")
def banner_form(request, pk=None):
    obj = get_object_or_404(Banner, pk=pk) if pk else None
    form = BannerForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        b = form.save(commit=False)
        try:
            if form.cleaned_data.get("image_upload"):
                main, _ = process_upload(form.cleaned_data["image_upload"], max_side=2000, thumb_side=0)
                if b.image:
                    b.image.delete(save=False)
                b.image.save(main.name, main, save=False)
            if form.cleaned_data.get("remove_mobile") and b.image_mobile:
                b.image_mobile.delete(save=False)
                b.image_mobile = ""
            if form.cleaned_data.get("image_mobile_upload"):
                main, _ = process_upload(form.cleaned_data["image_mobile_upload"], max_side=1200, thumb_side=0)
                if b.image_mobile:
                    b.image_mobile.delete(save=False)
                b.image_mobile.save(main.name, main, save=False)
        except ValidationError as e:
            form.add_error(None, e)
        else:
            b.save()
            audit(request, "banner_update" if obj else "banner_create", b, b.title)
            messages.success(request, "Đã lưu banner.")
            return redirect("panel:banners")
    return render(request, "panel/form_page.html", {
        "form": form, "title": "Sửa banner" if obj else "Thêm banner", "back": "/admin/banner/", "object": obj,
        "multipart": True, "delete_url": request.path + "xoa/" if obj else None, "image_preview": obj.image.url if obj and obj.image else None,
    })


@require_POST
@require_perm("manage_content")
def banner_delete(request, pk):
    b = get_object_or_404(Banner, pk=pk)
    for f in (b.image, b.image_mobile):
        if f:
            f.delete(save=False)
    title = b.title
    b.delete()
    audit(request, "banner_delete", summary=title)
    messages.success(request, "Đã xóa banner.")
    return redirect("panel:banners")


@require_POST
@require_perm("manage_content")
def banner_toggle(request, pk):
    b = get_object_or_404(Banner, pk=pk)
    b.is_active = not b.is_active
    b.save(update_fields=["is_active", "updated_at"])
    audit(request, "banner_toggle", b, f"{b.title}: {'bật' if b.is_active else 'tắt'}")
    return redirect("panel:banners")


# ---------------------------------------------------------------- Trang nội dung


@require_perm("manage_content")
def page_list(request):
    return render(request, "panel/marketing/pages.html", {"pages": Page.objects.all()})


@require_perm("manage_content")
def page_form(request, pk=None):
    obj = get_object_or_404(Page, pk=pk) if pk else None
    form = PageForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        p = form.save()
        audit(request, "page_update" if obj else "page_create", p, p.title)
        messages.success(request, f"Đã lưu trang “{p.title}”.")
        if request.POST.get("then") == "preview":
            return redirect(p.get_absolute_url())
        return redirect("panel:page_edit", pk=p.pk)
    return render(request, "panel/marketing/page_form.html", {"form": form, "object": obj})


@require_POST
@require_perm("manage_content")
def page_delete(request, pk):
    p = get_object_or_404(Page, pk=pk)
    if p.slug in ("gioi-thieu", "lien-he", "chinh-sach-giao-hang", "chinh-sach-doi-tra", "chinh-sach-bao-mat"):
        messages.error(request, "Đây là trang hệ thống, không xóa được. Có thể chuyển về Nháp để ẩn.")
        return redirect("panel:page_edit", pk=pk)
    title = p.title
    p.delete()
    audit(request, "page_delete", summary=title)
    messages.success(request, f"Đã xóa trang “{title}”.")
    return redirect("panel:pages")


# ---------------------------------------------------------------- Trang chủ


@require_perm("manage_content")
def home_config(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "categories":
            ids = [int(i) for i in request.POST.getlist("home_categories") if i.isdigit()]
            Category.objects.update(show_on_home=False)
            Category.objects.filter(pk__in=ids).update(show_on_home=True)
            audit(request, "home_categories", summary=f"{len(ids)} danh mục")
            messages.success(request, "Đã lưu danh mục hiển thị trên trang chủ.")
        elif action in ("add", "remove"):
            flag = request.POST.get("flag")
            pid = request.POST.get("product_id", "")
            if flag in ("is_featured", "is_new", "is_on_sale_section") and pid.isdigit():
                p = get_object_or_404(Product, pk=pid)
                setattr(p, flag, action == "add")
                p.save(update_fields=[flag, "updated_at"])
                audit(request, "home_product", p, f"{flag}={action == 'add'}")
                messages.success(request, f"Đã cập nhật “{p.name}”.")
        return redirect(request.get_full_path())
    q = (request.GET.get("q") or "").strip()
    results = []
    if q:
        qs = Product.objects.all()
        for t in normalize_search(q).split():
            qs = qs.filter(search_text__icontains=t)
        results = qs[:20]
    sections = [
        ("is_featured", "Sản phẩm nổi bật", Product.objects.filter(is_featured=True)),
        ("is_on_sale_section", "Đang giảm giá", Product.objects.filter(is_on_sale_section=True)),
        ("is_new", "Hàng mới về", Product.objects.filter(is_new=True)),
    ]
    return render(request, "panel/marketing/home.html", {
        "categories": Category.objects.filter(Q(parent__isnull=True) | Q(show_on_home=True)).select_related("parent"),
        "all_categories": Category.objects.select_related("parent"),
        "sections": sections, "q": q, "results": results,
    })


# ---------------------------------------------------------------- Cấu hình


@require_perm("manage_settings")
def settings_view(request):
    obj = SiteSettings.load()
    form = SettingsForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        s = form.save(commit=False)
        try:
            if form.cleaned_data.get("remove_logo") and s.logo:
                s.logo.delete(save=False)
                s.logo = ""
            if form.cleaned_data.get("logo_upload"):
                main, _ = process_upload(form.cleaned_data["logo_upload"], max_side=600, thumb_side=0)
                if s.logo:
                    s.logo.delete(save=False)
                s.logo.save(main.name, main, save=False)
        except ValidationError as e:
            form.add_error("logo_upload", e)
        else:
            s.is_configured = True
            s.save()
            audit(request, "settings_update", s, ", ".join(form.changed_data)[:400])
            messages.success(request, "Đã lưu cấu hình cửa hàng.")
            return redirect("panel:settings")
    return render(request, "panel/marketing/settings.html", {"form": form, "obj": obj})
