from django.conf import settings
from django.db import models
from django.db.models import Q


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Mới"
        CONFIRMED = "confirmed", "Đã xác nhận"
        PACKING = "packing", "Đang đóng gói"
        SHIPPING = "shipping", "Đang giao"
        COMPLETED = "completed", "Hoàn tất"
        CANCELLED = "cancelled", "Đã hủy"
        RETURNED = "returned", "Hoàn/trả hàng"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Chưa thanh toán"
        PAID = "paid", "Đã thanh toán"
        REFUNDED = "refunded", "Đã hoàn tiền"

    class PaymentMethod(models.TextChoices):
        COD = "cod", "Thanh toán khi nhận hàng (COD)"
        BANK_TRANSFER = "bank_transfer", "Chuyển khoản ngân hàng"

    code = models.CharField("Mã đơn", max_length=20, unique=True)
    idempotency_key = models.UUIDField(unique=True)

    customer_name = models.CharField("Họ tên", max_length=120)
    phone = models.CharField("Điện thoại", max_length=20, db_index=True)
    email = models.EmailField("Email", blank=True)
    address = models.TextField("Địa chỉ giao hàng")
    customer_note = models.TextField("Ghi chú của khách", blank=True)

    status = models.CharField("Trạng thái xử lý", max_length=12, choices=Status.choices, default=Status.NEW)
    payment_method = models.CharField("Phương thức thanh toán", max_length=20, choices=PaymentMethod.choices)
    payment_status = models.CharField(
        "Thanh toán", max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )

    subtotal = models.PositiveBigIntegerField("Tiền hàng")
    discount_total = models.PositiveBigIntegerField("Giảm giá", default=0)
    shipping_fee = models.PositiveBigIntegerField("Phí giao hàng", default=0)
    total = models.PositiveBigIntegerField("Tổng thanh toán")

    coupon = models.ForeignKey(
        "promotions.Coupon", null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    coupon_code = models.CharField("Mã giảm giá", max_length=40, blank=True)
    coupon_released = models.BooleanField(default=False)
    stock_restored = models.BooleanField(default=False)

    carrier = models.CharField("Đơn vị vận chuyển", max_length=80, blank=True)
    tracking_code = models.CharField("Mã vận đơn", max_length=80, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Đơn hàng"
        constraints = [
            models.CheckConstraint(
                condition=Q(total=models.F("subtotal") - models.F("discount_total") + models.F("shipping_fee")),
                name="order_total_consistent",
            )
        ]

    def __str__(self):
        return self.code

    @property
    def item_count(self):
        return sum(i.quantity for i in self.items.all())


class OrderItem(models.Model):
    """Bản chụp sản phẩm tại thời điểm đặt hàng. Sửa sản phẩm sau đó không ảnh hưởng."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey("catalog.Variant", on_delete=models.PROTECT, related_name="order_items")
    product_name = models.CharField(max_length=255)
    variant_label = models.CharField(max_length=160, blank=True)
    sku = models.CharField(max_length=64)
    image_url = models.CharField(max_length=300, blank=True)
    unit_price = models.PositiveBigIntegerField()
    compare_at_price = models.PositiveBigIntegerField(null=True, blank=True)
    quantity = models.PositiveIntegerField()
    line_total = models.PositiveBigIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="orderitem_qty_positive"),
        ]

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"


class OrderEvent(models.Model):
    """Lịch sử đơn: đổi trạng thái, thanh toán, vận đơn, ghi chú nội bộ, kho."""

    class Kind(models.TextChoices):
        CREATED = "created", "Tạo đơn"
        STATUS = "status", "Trạng thái xử lý"
        PAYMENT = "payment", "Thanh toán"
        SHIPPING = "shipping", "Vận chuyển"
        NOTE = "note", "Ghi chú nội bộ"
        STOCK = "stock", "Tồn kho"
        EMAIL = "email", "Email"

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    from_value = models.CharField(max_length=40, blank=True)
    to_value = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
