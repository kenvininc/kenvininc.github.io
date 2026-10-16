from datetime import datetime, time, timedelta

from django.db.models import Count, Q, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.catalog.models import Product, Variant
from apps.content.models import Page
from apps.core.models import SiteSettings
from apps.core.roles import has_perm, require_perm
from apps.orders.models import Order

RANGES = [
    ("today", "Hôm nay"),
    ("7d", "7 ngày qua"),
    ("30d", "30 ngày qua"),
    ("month", "Tháng này"),
    ("custom", "Tùy chọn"),
]


def _range(request):
    tz = timezone.get_current_timezone()
    today = timezone.localdate()
    key = request.GET.get("khoang", "month")
    start_date, end_date = today.replace(day=1), today
    if key == "today":
        start_date = today
    elif key == "7d":
        start_date = today - timedelta(days=6)
    elif key == "30d":
        start_date = today - timedelta(days=29)
    elif key == "custom":
        try:
            start_date = datetime.strptime(request.GET.get("tu", ""), "%Y-%m-%d").date()
            end_date = datetime.strptime(request.GET.get("den", ""), "%Y-%m-%d").date()
        except ValueError:
            key, start_date = "month", today.replace(day=1)
        if end_date < start_date:
            start_date, end_date = end_date, start_date
    else:
        key = "month"
    start = datetime.combine(start_date, time.min, tzinfo=tz)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    return key, start_date, end_date, start, end


@require_perm("view_dashboard")
def dashboard(request):
    user = request.user
    site = SiteSettings.load()
    key, start_date, end_date, start, end = _range(request)
    S = Order.Status
    ctx = {"ranges": RANGES, "range_key": key, "start_date": start_date, "end_date": end_date}

    if has_perm(user, "view_orders") or has_perm(user, "view_reports"):
        counts = Order.objects.aggregate(
            new=Count("id", filter=Q(status=S.NEW)),
            processing=Count("id", filter=Q(status__in=[S.CONFIRMED, S.PACKING])),
            shipping=Count("id", filter=Q(status=S.SHIPPING)),
            unpaid_bank=Count("id", filter=Q(payment_method="bank_transfer", payment_status="unpaid", status=S.NEW)),
        )
        in_range = Order.objects.aggregate(
            created=Count("id", filter=Q(created_at__gte=start, created_at__lt=end)),
            completed=Count("id", filter=Q(status=S.COMPLETED, completed_at__gte=start, completed_at__lt=end)),
            cancelled=Count("id", filter=Q(status=S.CANCELLED, cancelled_at__gte=start, cancelled_at__lt=end)),
        )
        ctx.update(counts=counts, in_range=in_range, show_orders=True)
        ctx["recent_orders"] = Order.objects.all()[:8]

    if has_perm(user, "view_reports"):
        done = Order.objects.filter(status=S.COMPLETED, completed_at__gte=start, completed_at__lt=end)
        agg = done.aggregate(total=Sum("total"), shipping=Sum("shipping_fee"), discount=Sum("discount_total"), subtotal=Sum("subtotal"), n=Count("id"))
        ctx["revenue"] = {k: (v or 0) for k, v in agg.items()}
        ctx["revenue"]["goods"] = ctx["revenue"]["subtotal"] - ctx["revenue"]["discount"]

    if has_perm(user, "manage_products") or has_perm(user, "manage_stock"):
        low = (
            Variant.objects.filter(is_active=True, stock__lte=site.low_stock_threshold)
            .exclude(product__status=Product.Status.HIDDEN)
            .select_related("product")
            .order_by("stock", "product__name")
        )
        ctx["show_stock"] = True
        ctx["low_stock"] = low[:12]
        ctx["low_stock_count"] = low.count()
        ctx["product_counts"] = Product.objects.aggregate(
            published=Count("id", filter=Q(status="published")), draft=Count("id", filter=Q(status="draft"))
        )

    if has_perm(user, "manage_settings"):
        todo = []
        if not site.is_configured:
            todo.append(("Kiểm tra và lưu cấu hình cửa hàng (liên hệ, phí giao hàng, thanh toán).", "panel:settings"))
        if not Page.objects.filter(status="published").exists():
            todo.append(("Nhập nội dung và xuất bản các trang chính sách (giao hàng, đổi trả, bảo mật).", "panel:pages"))
        if not Product.objects.filter(status="published").exists():
            todo.append(("Thêm sản phẩm và chuyển sang trạng thái Đang bán.", "panel:product_add"))
        ctx["todo"] = todo
    return render(request, "panel/dashboard.html", ctx)
