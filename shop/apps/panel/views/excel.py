from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.catalog.excel import apply_import, build_template, export_products, parse_import
from apps.catalog.models import ImportJob, Product
from apps.catalog.services import ConcurrentChange
from apps.core.roles import require_perm
from apps.core.utils import audit

from ..forms import ImportForm
from .common import xlsx_response


@require_perm("import_export")
def import_page(request):
    form = ImportForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        f = form.cleaned_data["file"]
        if f.size > settings.MAX_EXCEL_UPLOAD_MB * 1024 * 1024:
            form.add_error("file", f"File vượt quá {settings.MAX_EXCEL_UPLOAD_MB} MB.")
        elif not f.name.lower().endswith(".xlsx"):
            form.add_error("file", "Chỉ nhận file .xlsx.")
        else:
            plan, summary, errors = parse_import(f, auto_create=form.cleaned_data["auto_create"])
            job = ImportJob.objects.create(
                user=request.user, filename=f.name[:255], plan=plan or {}, summary=summary or {}, errors=errors
            )
            return redirect("panel:import_preview", pk=job.pk)
    return render(request, "panel/excel/import.html", {"form": form})


@require_perm("import_export")
def import_preview(request, pk):
    job = get_object_or_404(ImportJob, pk=pk, user=request.user)
    if request.method == "POST":
        if job.applied_at:
            messages.info(request, "File này đã được nhập trước đó.")
        elif job.errors:
            messages.error(request, "File còn lỗi, không thể nhập.")
        elif timezone.now() - job.created_at > timezone.timedelta(hours=2):
            messages.error(request, "Bản xem trước đã quá 2 giờ, vui lòng tải file lên lại.")
        else:
            try:
                job.applied_at = apply_import(job.plan, request.user)
            except ConcurrentChange as e:
                messages.error(request, f"{e} Không có dữ liệu nào được ghi. Vui lòng tải file lên lại.")
                return redirect("panel:import")
            job.save(update_fields=["applied_at"])
            audit(request, "excel_import", job, f"{job.filename}: {job.summary}")
            messages.success(request, "Đã nhập dữ liệu từ Excel.")
            return redirect("panel:products")
    preview_rows = []
    for p in (job.plan or {}).get("products", [])[:200]:
        for r in p["rows"]:
            preview_rows.append({"code": p["code"], "name": p["fields"].get("name", ""), "new": not p["product_id"], **r})
    return render(request, "panel/excel/preview.html", {"job": job, "rows": preview_rows})


@require_perm("import_export")
def import_template(request):
    return xlsx_response(build_template(), "mau-nhap-san-pham.xlsx")


@require_perm("import_export")
def export(request):
    audit(request, "excel_export_products")
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    return xlsx_response(export_products(Product.objects.order_by("code")), f"san-pham-{stamp}.xlsx")
