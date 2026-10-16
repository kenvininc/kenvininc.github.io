"""Nghiệp vụ giá và tồn kho. Mọi thay đổi đều ghi lịch sử."""

from django.db import transaction
from django.db.models import F

from .models import PriceHistory, StockMovement, Variant


class ConcurrentChange(Exception):
    """Dữ liệu đã bị thay đổi bởi thao tác khác sau khi người dùng mở form."""


def set_price(variant, price, compare_at_price, user, source, reason="", expected=None):
    """Đổi giá 1 biến thể (phải gọi trong transaction, variant đã select_for_update).

    expected=(price, compare) là giá người dùng thấy lúc mở form; khác giá hiện tại
    thì báo lỗi thay vì ghi đè.
    """
    if expected is not None and (variant.price, variant.compare_at_price) != tuple(expected):
        raise ConcurrentChange(f"Giá của SKU {variant.sku} vừa được người khác thay đổi.")
    if variant.price == price and variant.compare_at_price == compare_at_price:
        return False
    PriceHistory.objects.create(
        variant=variant,
        old_price=variant.price,
        new_price=price,
        old_compare_at_price=variant.compare_at_price,
        new_compare_at_price=compare_at_price,
        source=source,
        reason=reason[:255],
        changed_by=user,
    )
    Variant.objects.filter(pk=variant.pk).update(price=price, compare_at_price=compare_at_price)
    variant.price, variant.compare_at_price = price, compare_at_price
    return True


def adjust_stock(variant_id, delta, kind, user=None, reason="", order_item=None, expected=None):
    """Cộng/trừ tồn kho có khóa dòng. Trả về tồn kho mới.

    expected: tồn kho người dùng thấy lúc mở form (để phát hiện có đơn mới chen vào).
    """
    with transaction.atomic():
        v = Variant.objects.select_for_update().get(pk=variant_id)
        if expected is not None and v.stock != expected:
            raise ConcurrentChange(
                f"Tồn kho SKU {v.sku} đã thay đổi từ {expected} thành {v.stock} (có thể do đơn hàng mới). "
                "Vui lòng kiểm tra lại."
            )
        if delta == 0:
            return v.stock
        new_stock = v.stock + delta
        if new_stock < 0:
            raise ValueError(f"Tồn kho SKU {v.sku} không đủ (còn {v.stock}).")
        Variant.objects.filter(pk=v.pk).update(stock=F("stock") + delta)
        StockMovement.objects.create(
            variant=v,
            kind=kind,
            delta=delta,
            stock_after=new_stock,
            reason=reason[:255],
            order_item=order_item,
            user=user,
        )
        return new_stock
