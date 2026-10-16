from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Coupon(models.Model):
    """Mã giảm giá.

    Quy tắc áp dụng (kiểm tra ở backend, xem apps/promotions/services.py):
    - Mỗi đơn dùng tối đa 1 mã.
    - Mã tính trên tiền hàng (đã là giá bán sau giảm giá sản phẩm), không giảm phí giao hàng.
    - Số tiền giảm không vượt quá tiền hàng.
    """

    class Type(models.TextChoices):
        FIXED = "fixed", "Giảm số tiền"
        PERCENT = "percent", "Giảm theo %"

    code = models.CharField("Mã", max_length=40, unique=True)
    description = models.CharField("Mô tả hiển thị cho khách", max_length=200, blank=True)
    discount_type = models.CharField("Loại giảm", max_length=10, choices=Type.choices, default=Type.FIXED)
    value = models.PositiveBigIntegerField("Giá trị", help_text="Số tiền (đ) hoặc số % (1–100).")
    max_discount = models.PositiveBigIntegerField(
        "Giảm tối đa (đ)", null=True, blank=True, help_text="Chỉ dùng cho loại %. Để trống = không giới hạn."
    )
    min_order_value = models.PositiveBigIntegerField("Giá trị đơn tối thiểu (đ)", default=0)
    starts_at = models.DateTimeField("Bắt đầu", null=True, blank=True)
    ends_at = models.DateTimeField("Kết thúc", null=True, blank=True)
    usage_limit = models.PositiveIntegerField("Tổng số lượt dùng tối đa", null=True, blank=True)
    usage_limit_per_phone = models.PositiveIntegerField(
        "Số lượt tối đa mỗi số điện thoại", null=True, blank=True
    )
    used_count = models.PositiveIntegerField("Đã dùng", default=0, editable=False)
    is_active = models.BooleanField("Đang bật", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Mã giảm giá"
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_type="fixed") | Q(value__gte=1, value__lte=100),
                name="coupon_percent_range",
            )
        ]

    def __str__(self):
        return self.code

    def clean(self):
        self.code = (self.code or "").strip().upper()
        if self.discount_type == self.Type.PERCENT and not (1 <= (self.value or 0) <= 100):
            raise ValidationError({"value": "Phần trăm phải từ 1 đến 100."})
        if self.discount_type == self.Type.FIXED and not self.value:
            raise ValidationError({"value": "Số tiền giảm phải lớn hơn 0."})
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "Thời gian kết thúc phải sau thời gian bắt đầu."})

    @property
    def status_label(self):
        now = timezone.now()
        if not self.is_active:
            return "Đang tắt"
        if self.starts_at and now < self.starts_at:
            return "Chưa bắt đầu"
        if self.ends_at and now >= self.ends_at:
            return "Hết hạn"
        if self.usage_limit is not None and self.used_count >= self.usage_limit:
            return "Hết lượt"
        return "Đang áp dụng"
