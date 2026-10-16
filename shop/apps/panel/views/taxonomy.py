from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.models import Attribute, Brand, Category
from apps.core.images import process_upload
from apps.core.roles import require_perm
from apps.core.utils import audit

from ..forms import AttributeForm, BrandForm, CategoryForm


def _store_image(form, instance, upload_field, model_field, remove_field):
    f = form.cleaned_data.get(upload_field)
    current = getattr(instance, model_field)
    if form.cleaned_data.get(remove_field) and current:
        current.delete(save=False)
        setattr(instance, model_field, "")
    if f:
        main, _ = process_upload(f, max_side=800, thumb_side=0)
        if current:
            current.delete(save=False)
        getattr(instance, model_field).save(main.name, main, save=False)


def _crud_form(request, model, form_class, instance, template_title, list_url, upload=None):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        try:
            if upload:
                _store_image(form, obj, *upload)
        except ValidationError as e:
            form.add_error(upload[0], e)
        else:
            obj.save()
            audit(request, f"{model.__name__.lower()}_{'update' if instance else 'create'}", obj, str(obj))
            messages.success(request, f"Đã lưu “{obj}”.")
            return redirect(list_url)
    return render(
        request, "panel/form_page.html",
        {"form": form, "title": template_title, "back": list_url, "object": instance, "multipart": bool(upload),
         "delete_url": request.path + "xoa/" if instance else None},
    )


def _delete(request, obj, list_url, blocked_msg):
    name = str(obj)
    try:
        obj.delete()
    except ProtectedError:
        messages.error(request, blocked_msg)
        return redirect(list_url)
    audit(request, f"{obj.__class__.__name__.lower()}_delete", summary=name)
    messages.success(request, f"Đã xóa “{name}”.")
    return redirect(list_url)


# ---------------------------------------------------------------- Danh mục


@require_perm("manage_products")
def category_list(request):
    roots = Category.objects.filter(parent__isnull=True).annotate(n=Count("products")).prefetch_related("children")
    counts = dict(Category.objects.annotate(n=Count("products")).values_list("pk", "n"))
    return render(request, "panel/taxonomy/categories.html", {"roots": roots, "counts": counts})


@require_perm("manage_products")
def category_form(request, pk=None):
    obj = get_object_or_404(Category, pk=pk) if pk else None
    return _crud_form(request, Category, CategoryForm, obj, "Sửa danh mục" if obj else "Thêm danh mục",
                      "/admin/danh-muc/", ("image_upload", "image", "remove_image"))


@require_POST
@require_perm("manage_products")
def category_delete(request, pk):
    return _delete(request, get_object_or_404(Category, pk=pk), "/admin/danh-muc/",
                   "Danh mục đang có sản phẩm hoặc danh mục con nên không xóa được. Hãy chuyển sản phẩm sang danh mục khác hoặc tắt “Hiển thị”.")


# ---------------------------------------------------------------- Thương hiệu


@require_perm("manage_products")
def brand_list(request):
    return render(request, "panel/taxonomy/brands.html", {"brands": Brand.objects.annotate(n=Count("products"))})


@require_perm("manage_products")
def brand_form(request, pk=None):
    obj = get_object_or_404(Brand, pk=pk) if pk else None
    return _crud_form(request, Brand, BrandForm, obj, "Sửa thương hiệu" if obj else "Thêm thương hiệu",
                      "/admin/thuong-hieu/", ("logo_upload", "logo", "remove_logo"))


@require_POST
@require_perm("manage_products")
def brand_delete(request, pk):
    return _delete(request, get_object_or_404(Brand, pk=pk), "/admin/thuong-hieu/",
                   "Thương hiệu đang có sản phẩm nên không xóa được. Hãy tắt “Hiển thị”.")


# ---------------------------------------------------------------- Thuộc tính


@require_perm("manage_products")
def attribute_list(request):
    return render(request, "panel/taxonomy/attributes.html", {"attributes": Attribute.objects.annotate(n=Count("product"))})


@require_perm("manage_products")
def attribute_form(request, pk=None):
    obj = get_object_or_404(Attribute, pk=pk) if pk else None
    return _crud_form(request, Attribute, AttributeForm, obj, "Sửa thuộc tính" if obj else "Thêm thuộc tính", "/admin/thuoc-tinh/")


@require_POST
@require_perm("manage_products")
def attribute_delete(request, pk):
    return _delete(request, get_object_or_404(Attribute, pk=pk), "/admin/thuoc-tinh/",
                   "Thuộc tính đang được sản phẩm sử dụng nên không xóa được.")
