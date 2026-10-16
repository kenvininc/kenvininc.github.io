"""Nghiệp vụ giỏ hàng, tính tiền, đặt hàng và xử lý đơn.

Chính sách tồn kho (xem README):
- Trừ tồn NGAY khi đơn được tạo, trong cùng transaction, có khóa dòng biến thể.
  Không đủ hàng thì không tạo đơn → không bán vượt tồn.
- Hủy đơn (trước khi giao) → hoàn tồn 1 lần.
- Hoàn/trả hàng → chỉ hoàn tồn khi admin xác nhận đã nhận lại hàng, 1 lần.
- Database có ràng buộc stock >= 0 và mỗi dòng đơn chỉ trừ/hoàn 1 lần.
"""

import logging
import secrets
from dataclasses import dataclass, field

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import F
from django.template.loader import render_to_string
from django.utils import timezone

from apps.catalog.models import Product, StockMovement, Variant
from apps.catalog.services import adjust_stock
from apps.core.models import SiteSettings
from apps.promotions.models import Coupon
from apps.promotions.services import CouponError, check_coupon, find_coupon

from .models import Order, OrderEvent, OrderItem

log = logging.getLogger("shop.orders")

S = Order.Status
TRANSITIONS = {
    S.NEW: [S.CONFIRMED, S.CANCELLED],
    S.CONFIRMED: [S.PACKING, S.CANCELLED],
    S.PACKING: [S.SHIPPING, S.CANCELLED],
    S.SHIPPING: [S.COMPLETED, S.RETURNED],
    S.COMPLETED: [S.RETURNED],
    S.CANCELLED: [],
    S.RETURNED: [],
}

P = Order.PaymentStatus
PAYMENT_TRANSITIONS = {
    P.UNPAID: [P.PAID],
    P.PAID: [P.UNPAID, P.REFUNDED],
    P.REFUNDED: [],
}


class OrderError(Exception):
    pass


# ---------------------------------------------------------------- Giỏ hàng (session)

CART_KEY = "cart"


def get_cart(session):
    raw = session.get(CART_KEY) or {}
    cart = {}
    for k, v in raw.items():
        try:
            vid, qty = int(k), int(v)
        except (TypeError, ValueError):
            continue
        if qty > 0:
            cart[vid] = qty
    return cart


def save_cart(session, cart):
    session[CART_KEY] = {str(k): int(v) for k, v in cart.items() if v > 0}
    session.modified = True


def cart_count(session):
    return sum(get_cart(session).values())


# ---------------------------------------------------------------- Tính tiền


@dataclass
class Line:
    variant: Variant
    quantity: int
    unit_price: int
    line_total: int
    problem: str = ""


@dataclass
class Quote:
    lines: list = field(default_factory=list)
    subtotal: int = 0
    discount: int = 0
    shipping_fee: int = 0
    total: int = 0
    coupon: Coupon = None
    coupon_error: str = ""
    removed: list = field(default_factory=list)

    @property
    def has_problems(self):
        return any(l.problem for l in self.lines)


def shipping_fee_for(amount_after_discount, site):
    """Phí giao hàng đồng giá; miễn phí nếu tiền hàng sau giảm giá ≥ ngưỡng."""
    if site.free_shipping_threshold and amount_after_discount >= site.free_shipping_threshold:
        return 0
    return site.shipping_flat_fee


def build_quote(cart, coupon_code="", phone=None, lock=False, site=None):
    """Tính tiền hoàn toàn từ database. Không dùng giá trị nào do trình duyệt gửi lên."""
    site = site or SiteSettings.load()
    quote = Quote()
    ids = sorted(cart.keys())
    qs = Variant.objects.select_related("product", "image").prefetch_related("product__images")
    if lock:
        # Khóa theo thứ tự id để tránh deadlock khi nhiều đơn cùng lúc.
        qs = qs.select_for_update(of=("self",)).order_by("id")
    variants = {v.id: v for v in qs.filter(id__in=ids)}
    for vid in ids:
        v = variants.get(vid)
        qty = cart[vid]
        if v is None:
            quote.removed.append(vid)
            continue
        problem = ""
        if not v.is_active or v.product.status != Product.Status.PUBLISHED:
            problem = "Sản phẩm này hiện không còn bán."
        elif v.stock <= 0:
            problem = "Hết hàng."
        elif qty > v.stock:
            problem = f"Chỉ còn {v.stock} sản phẩm."
        elif qty > site.max_qty_per_item:
            problem = f"Mỗi đơn tối đa {site.max_qty_per_item} sản phẩm cùng loại."
        quote.lines.append(Line(v, qty, v.price, v.price * qty, problem))
    quote.subtotal = sum(l.line_total for l in quote.lines if not l.problem)

    if coupon_code:
        try:
            coupon = find_coupon(coupon_code, for_update=lock)
            quote.discount = check_coupon(coupon, quote.subtotal, phone=phone)
            quote.coupon = coupon
        except CouponError as e:
            quote.coupon_error = str(e)
    quote.shipping_fee = shipping_fee_for(quote.subtotal - quote.discount, site) if quote.subtotal else 0
    quote.total = quote.subtotal - quote.discount + quote.shipping_fee
    return quote


# ---------------------------------------------------------------- Đặt hàng

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _new_code():
    date = timezone.localdate().strftime("%y%m%d")
    return "KS" + date + "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))


def place_order(cart, customer, payment_method, coupon_code, idempotency_key):
    """Tạo đơn. Gửi lặp cùng idempotency_key trả về đúng đơn đã tạo, không trừ kho lần hai.

    customer: dict(customer_name, phone, email, address, customer_note)
    Raise OrderError với thông điệp hiển thị cho khách.
    """
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    if not cart:
        raise OrderError("Giỏ hàng đang trống.")
    site = SiteSettings.load()
    allowed = dict(site.payment_methods())
    if payment_method not in allowed:
        raise OrderError("Phương thức thanh toán không hợp lệ.")

    for attempt in range(3):
        try:
            with transaction.atomic():
                quote = build_quote(cart, coupon_code, phone=customer["phone"], lock=True, site=site)
                if quote.removed or not quote.lines:
                    raise OrderError("Giỏ hàng có sản phẩm không còn tồn tại. Vui lòng kiểm tra lại giỏ hàng.")
                if quote.has_problems:
                    raise OrderError("Một số sản phẩm trong giỏ không đủ hàng hoặc ngừng bán. Vui lòng kiểm tra lại giỏ hàng.")
                if coupon_code and quote.coupon_error:
                    raise OrderError(quote.coupon_error)

                order = Order.objects.create(
                    code=_new_code(),
                    idempotency_key=idempotency_key,
                    payment_method=payment_method,
                    subtotal=quote.subtotal,
                    discount_total=quote.discount,
                    shipping_fee=quote.shipping_fee,
                    total=quote.total,
                    coupon=quote.coupon,
                    coupon_code=quote.coupon.code if quote.coupon else "",
                    **customer,
                )
                for line in quote.lines:
                    v = line.variant
                    img = v.image or v.product.main_image
                    attr = v.product.variant_attribute.name if v.product.variant_attribute_id else ""
                    item = OrderItem.objects.create(
                        order=order,
                        variant=v,
                        product_name=v.product.name,
                        variant_label=f"{attr}: {v.value}" if (attr and v.value) else v.value,
                        sku=v.sku,
                        image_url=img.thumb_url if img else "",
                        unit_price=line.unit_price,
                        compare_at_price=v.compare_at_price if v.is_discounted else None,
                        quantity=line.quantity,
                        line_total=line.line_total,
                    )
                    adjust_stock(
                        v.id, -line.quantity, StockMovement.Kind.ORDER, reason=f"Đơn {order.code}", order_item=item
                    )
                if quote.coupon:
                    Coupon.objects.filter(pk=quote.coupon.pk).update(used_count=F("used_count") + 1)
                OrderEvent.objects.create(order=order, kind=OrderEvent.Kind.CREATED, to_value=order.status)
                transaction.on_commit(lambda oid=order.id: send_order_emails(oid))
                return order, True
        except IntegrityError:
            existing = Order.objects.filter(idempotency_key=idempotency_key).first()
            if existing:
                return existing, False
            if attempt == 2:
                raise
    raise OrderError("Không tạo được đơn hàng, vui lòng thử lại.")


def send_order_emails(order_id):
    """Gửi email sau khi đơn đã lưu. Lỗi gửi email chỉ ghi log, không ảnh hưởng đơn."""
    if not settings.EMAIL_HOST:
        return
    try:
        order = Order.objects.prefetch_related("items").get(pk=order_id)
        site = SiteSettings.load()
        ctx = {"order": order, "site": site, "site_url": settings.SITE_URL}
        subject = f"[{site.shop_name}] Đơn hàng {order.code}"
        body = render_to_string("emails/order_created.txt", ctx)
        if order.email:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [order.email])
        if settings.ORDER_NOTIFY_EMAILS:
            send_mail("Đơn mới " + order.code, body, settings.DEFAULT_FROM_EMAIL, settings.ORDER_NOTIFY_EMAILS)
        OrderEvent.objects.create(order=order, kind=OrderEvent.Kind.EMAIL, note="Đã gửi email xác nhận.")
    except Exception as e:  # noqa: BLE001 - không để lỗi email làm hỏng request
        log.warning("Gửi email đơn id=%s lỗi: %s", order_id, e.__class__.__name__)
        try:
            OrderEvent.objects.create(order_id=order_id, kind=OrderEvent.Kind.EMAIL, note="Gửi email thất bại.")
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- Xử lý đơn (admin)


def _restock(order, kind, user, reason):
    """Hoàn tồn toàn bộ dòng đơn, đúng 1 lần (cờ stock_restored + unique constraint)."""
    if order.stock_restored:
        return False
    for item in order.items.all():
        adjust_stock(item.variant_id, item.quantity, kind, user=user, reason=reason, order_item=item)
    order.stock_restored = True
    OrderEvent.objects.create(order=order, kind=OrderEvent.Kind.STOCK, note=reason, user=user)
    return True


def _release_coupon(order):
    if order.coupon_id and not order.coupon_released:
        coupon = Coupon.objects.select_for_update().get(pk=order.coupon_id)
        if coupon.used_count > 0:
            Coupon.objects.filter(pk=coupon.pk).update(used_count=coupon.used_count - 1)
        order.coupon_released = True


def change_status(order_id, new_status, user, note="", restock_return=False):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        old = order.status
        if new_status == old:
            raise OrderError("Đơn đã ở trạng thái này.")
        if new_status not in TRANSITIONS[old]:
            raise OrderError(
                f"Không thể chuyển từ “{Order.Status(old).label}” sang “{Order.Status(new_status).label}”."
            )
        now = timezone.now()
        order.status = new_status
        if new_status == S.CONFIRMED:
            order.confirmed_at = now
        elif new_status == S.COMPLETED:
            order.completed_at = now
        elif new_status == S.CANCELLED:
            order.cancelled_at = now
            _restock(order, StockMovement.Kind.ORDER_CANCEL, user, f"Hủy đơn {order.code}")
            _release_coupon(order)
        elif new_status == S.RETURNED and restock_return:
            _restock(order, StockMovement.Kind.ORDER_RETURN, user, f"Nhận lại hàng hoàn đơn {order.code}")
        order.save()
        OrderEvent.objects.create(
            order=order, kind=OrderEvent.Kind.STATUS, from_value=old, to_value=new_status, note=note, user=user
        )
        return order


def restock_returned(order_id, user):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status != S.RETURNED:
            raise OrderError("Chỉ nhập lại kho cho đơn ở trạng thái Hoàn/trả hàng.")
        if not _restock(order, StockMovement.Kind.ORDER_RETURN, user, f"Nhận lại hàng hoàn đơn {order.code}"):
            raise OrderError("Đơn này đã được hoàn tồn trước đó.")
        order.save()
        return order


def change_payment(order_id, new_status, user, note=""):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        old = order.payment_status
        if new_status not in PAYMENT_TRANSITIONS[old]:
            raise OrderError("Không thể đổi trạng thái thanh toán như vậy.")
        if new_status in (P.UNPAID, P.REFUNDED) and not note.strip():
            raise OrderError("Vui lòng ghi lý do.")
        order.payment_status = new_status
        order.paid_at = timezone.now() if new_status == P.PAID else order.paid_at
        order.save()
        OrderEvent.objects.create(
            order=order, kind=OrderEvent.Kind.PAYMENT, from_value=old, to_value=new_status, note=note, user=user
        )
        return order


def update_shipping(order_id, carrier, tracking_code, user):
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if (order.carrier, order.tracking_code) == (carrier, tracking_code):
            return order
        old = f"{order.carrier} {order.tracking_code}".strip()
        order.carrier, order.tracking_code = carrier, tracking_code
        order.save()
        OrderEvent.objects.create(
            order=order,
            kind=OrderEvent.Kind.SHIPPING,
            from_value=old[:40],
            to_value=f"{carrier} {tracking_code}".strip()[:40],
            user=user,
        )
        return order


def add_note(order_id, note, user):
    if not note.strip():
        raise OrderError("Ghi chú trống.")
    OrderEvent.objects.create(order_id=order_id, kind=OrderEvent.Kind.NOTE, note=note.strip(), user=user)


def cancel_unpaid_bank_orders(hours, now=None):
    """Hủy đơn chuyển khoản chưa thanh toán quá `hours` giờ, trạng thái còn Mới."""
    now = now or timezone.now()
    cutoff = now - timezone.timedelta(hours=hours)
    ids = list(
        Order.objects.filter(
            payment_method=Order.PaymentMethod.BANK_TRANSFER,
            payment_status=P.UNPAID,
            status=S.NEW,
            created_at__lt=cutoff,
        ).values_list("id", flat=True)
    )
    done = 0
    for oid in ids:
        try:
            change_status(oid, S.CANCELLED, None, note=f"Tự hủy: chưa thanh toán sau {hours} giờ.")
            done += 1
        except OrderError:
            continue
    return done
