import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

HEX_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate_hex_color(value):
    if value and not HEX_COLOR.match(value):
        raise ValidationError("Mã màu phải có dạng #RRGGBB, ví dụ #B23A62.")


def upload_branding(instance, filename):
    return f"branding/{filename}"


class SiteSettings(models.Model):
    """Cấu hình cửa hàng (chỉ có 1 bản ghi, pk=1). Sửa trong /admin/cai-dat/."""

    shop_name = models.CharField("Tên shop", max_length=120, default="Kenvin Shop")
    tagline = models.CharField("Khẩu hiệu ngắn", max_length=200, blank=True)
    logo = models.ImageField("Logo", upload_to=upload_branding, blank=True)
    primary_color = models.CharField(
        "Màu chủ đạo", max_length=7, default="#B23A62", validators=[validate_hex_color]
    )
    hotline = models.CharField("Hotline", max_length=30, blank=True)
    email = models.EmailField("Email liên hệ", blank=True)
    address = models.CharField("Địa chỉ", max_length=255, blank=True)
    opening_hours = models.CharField("Giờ hoạt động", max_length=200, blank=True)
    zalo = models.CharField("Zalo (số điện thoại hoặc link)", max_length=200, blank=True)
    facebook_url = models.URLField("Facebook", blank=True)
    instagram_url = models.URLField("Instagram", blank=True)
    tiktok_url = models.URLField("TikTok", blank=True)
    youtube_url = models.URLField("YouTube", blank=True)

    # Vận chuyển
    shipping_flat_fee = models.PositiveBigIntegerField("Phí giao hàng đồng giá (đ)", default=0)
    free_shipping_threshold = models.PositiveBigIntegerField(
        "Miễn phí giao hàng cho đơn từ (đ)",
        null=True,
        blank=True,
        help_text="Để trống nếu không áp dụng. Tính trên tiền hàng sau khi trừ mã giảm giá.",
    )
    shipping_note = models.CharField(
        "Ghi chú giao hàng hiển thị lúc đặt hàng", max_length=255, blank=True
    )

    # Thanh toán
    cod_enabled = models.BooleanField("Cho phép thanh toán khi nhận hàng (COD)", default=True)
    bank_transfer_enabled = models.BooleanField("Cho phép chuyển khoản ngân hàng", default=False)
    bank_name = models.CharField("Ngân hàng", max_length=120, blank=True)
    bank_account_number = models.CharField("Số tài khoản", max_length=40, blank=True)
    bank_account_name = models.CharField("Chủ tài khoản", max_length=120, blank=True)
    bank_transfer_hold_hours = models.PositiveIntegerField(
        "Tự hủy đơn chuyển khoản chưa thanh toán sau (giờ)",
        default=0,
        help_text="0 = không tự hủy. Cần cài lịch chạy lệnh cancel_unpaid_orders (xem hướng dẫn).",
    )

    # Kho
    low_stock_threshold = models.PositiveIntegerField("Cảnh báo sắp hết hàng khi tồn ≤", default=5)
    max_qty_per_item = models.PositiveIntegerField("Số lượng tối đa mỗi sản phẩm trong 1 đơn", default=20)

    # Hiển thị ở trang sản phẩm
    shipping_policy_summary = models.TextField("Tóm tắt chính sách giao hàng", blank=True)
    return_policy_summary = models.TextField("Tóm tắt chính sách đổi trả", blank=True)

    # SEO mặc định
    seo_title = models.CharField("Tiêu đề SEO trang chủ", max_length=70, blank=True)
    seo_description = models.CharField("Mô tả SEO trang chủ", max_length=170, blank=True)

    is_configured = models.BooleanField(default=False, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cấu hình cửa hàng"

    def __str__(self):
        return self.shop_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def bank_transfer_ready(self):
        return bool(
            self.bank_transfer_enabled
            and self.bank_name
            and self.bank_account_number
            and self.bank_account_name
        )

    def payment_methods(self):
        methods = []
        if self.cod_enabled:
            methods.append(("cod", "Thanh toán khi nhận hàng (COD)"))
        if self.bank_transfer_ready:
            methods.append(("bank_transfer", "Chuyển khoản ngân hàng"))
        return methods


class AuditLog(models.Model):
    """Nhật ký thao tác quan trọng của người quản trị. Không ghi mật khẩu/token."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=60)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=60, blank=True)
    summary = models.CharField(max_length=500, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.username} {self.action}"


class Permission(models.Model):
    """Model không tạo bảng, chỉ dùng để khai báo quyền của control panel."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("view_dashboard", "Xem tổng quan"),
            ("view_reports", "Xem doanh thu"),
            ("manage_products", "Quản lý sản phẩm, danh mục, thương hiệu"),
            ("manage_prices", "Sửa giá, cập nhật giá hàng loạt"),
            ("manage_stock", "Điều chỉnh tồn kho"),
            ("import_export", "Nhập/xuất Excel sản phẩm"),
            ("view_orders", "Xem đơn hàng"),
            ("manage_orders", "Xử lý đơn hàng"),
            ("manage_payments", "Cập nhật trạng thái thanh toán"),
            ("manage_promotions", "Quản lý mã giảm giá"),
            ("manage_content", "Quản lý banner, trang nội dung, trang chủ"),
            ("manage_settings", "Cấu hình cửa hàng"),
            ("manage_users", "Quản lý tài khoản quản trị"),
            ("view_audit", "Xem nhật ký thao tác"),
        ]
