from django.utils import timezone

from apps.core.text import format_vnd

from .models import Coupon


class CouponError(Exception):
    pass


def compute_discount(coupon, subtotal):
    """Số tiền giảm (đồng, số nguyên). Không bao giờ vượt tiền hàng."""
    if coupon.discount_type == Coupon.Type.PERCENT:
        amount = subtotal * coupon.value // 100
        if coupon.max_discount is not None:
            amount = min(amount, coupon.max_discount)
    else:
        amount = coupon.value
    return max(0, min(amount, subtotal))


def check_coupon(coupon, subtotal, phone=None, now=None):
    """Kiểm tra điều kiện, báo lỗi bằng CouponError với thông điệp cho khách."""
    now = now or timezone.now()
    if not coupon.is_active:
        raise CouponError("Mã giảm giá không hợp lệ.")
    if coupon.starts_at and now < coupon.starts_at:
        raise CouponError("Mã giảm giá chưa đến thời gian áp dụng.")
    if coupon.ends_at and now >= coupon.ends_at:
        raise CouponError("Mã giảm giá đã hết hạn.")
    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise CouponError("Mã giảm giá đã hết lượt sử dụng.")
    if subtotal < coupon.min_order_value:
        raise CouponError(f"Mã chỉ áp dụng cho đơn từ {format_vnd(coupon.min_order_value)} (tiền hàng).")
    if phone and coupon.usage_limit_per_phone is not None:
        from apps.orders.models import Order

        used = (
            Order.objects.filter(coupon=coupon, phone=phone)
            .exclude(status__in=[Order.Status.CANCELLED])
            .count()
        )
        if used >= coupon.usage_limit_per_phone:
            raise CouponError("Số điện thoại này đã dùng hết lượt của mã giảm giá.")
    return compute_discount(coupon, subtotal)


def find_coupon(code, for_update=False):
    code = (code or "").strip().upper()
    if not code:
        return None
    qs = Coupon.objects.all()
    if for_update:
        qs = qs.select_for_update()
    coupon = qs.filter(code=code).first()
    if coupon is None:
        raise CouponError("Mã giảm giá không tồn tại.")
    return coupon
