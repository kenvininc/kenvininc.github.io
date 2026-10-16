import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.models import validate_hex_color
from apps.core.text import normalize_search, vn_slugify


def upload_product_image(instance, filename):
    now = timezone.now()
    return f"products/{now:%Y/%m}/{filename}"


def upload_catalog_image(instance, filename):
    return f"catalog/{filename}"


class SeoFields(models.Model):
    seo_title = models.CharField("Tiêu đề SEO", max_length=70, blank=True)
    seo_description = models.CharField("Mô tả SEO", max_length=170, blank=True)

    class Meta:
        abstract = True


class Category(SeoFields):
    name = models.CharField("Tên danh mục", max_length=120)
    slug = models.SlugField("Đường dẫn", max_length=140, unique=True)
    parent = models.ForeignKey(
        "self",
        verbose_name="Danh mục cha",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    description = models.TextField("Mô tả", blank=True)
    image = models.ImageField("Ảnh/icon", upload_to=upload_catalog_image, blank=True)
    sort_order = models.IntegerField("Thứ tự", default=0)
    is_active = models.BooleanField("Hiển thị", default=True)
    show_on_home = models.BooleanField("Hiện trên trang chủ", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Danh mục"

    def __str__(self):
        return f"{self.parent.name} › {self.name}" if self.parent_id else self.name

    def get_absolute_url(self):
        return reverse("store:category", args=[self.slug])

    def descendant_ids(self):
        ids = [self.pk]
        ids += list(self.children.values_list("pk", flat=True))
        return ids


class Brand(SeoFields):
    name = models.CharField("Tên thương hiệu", max_length=120, unique=True)
    slug = models.SlugField("Đường dẫn", max_length=140, unique=True)
    logo = models.ImageField("Logo", upload_to=upload_catalog_image, blank=True)
    description = models.TextField("Giới thiệu", blank=True)
    sort_order = models.IntegerField("Thứ tự", default=0)
    is_active = models.BooleanField("Hiển thị", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Thương hiệu"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("store:brand", args=[self.slug])


class Attribute(models.Model):
    """Loại biến thể: Dung tích, Màu sắc, Quy cách..."""

    name = models.CharField("Tên thuộc tính", max_length=60, unique=True)
    is_color = models.BooleanField(
        "Là màu sắc", default=False, help_text="Hiển thị ô màu khi khách chọn biến thể."
    )
    sort_order = models.IntegerField("Thứ tự", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "Thuộc tính"

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Product.Status.PUBLISHED)

    def visible(self):
        """Sản phẩm đăng bán, có ít nhất 1 biến thể đang bật."""
        return self.published().filter(variants__is_active=True).distinct()


class Product(SeoFields):
    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        PUBLISHED = "published", "Đang bán"
        HIDDEN = "hidden", "Ẩn"

    code = models.CharField(
        "Mã sản phẩm",
        max_length=60,
        unique=True,
        help_text="Mã nội bộ, dùng để nhập/xuất Excel. Để trống sẽ tự tạo.",
    )
    name = models.CharField("Tên sản phẩm", max_length=255)
    slug = models.SlugField("Đường dẫn", max_length=200, unique=True)
    brand = models.ForeignKey(
        Brand, verbose_name="Thương hiệu", null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    category = models.ForeignKey(
        Category, verbose_name="Danh mục", null=True, blank=True, on_delete=models.PROTECT, related_name="products"
    )
    variant_attribute = models.ForeignKey(
        Attribute,
        verbose_name="Loại biến thể",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        help_text="Ví dụ: Dung tích, Màu sắc. Để trống nếu sản phẩm chỉ có 1 loại.",
    )
    short_description = models.CharField("Mô tả ngắn", max_length=300, blank=True)
    description = models.TextField("Mô tả", blank=True)
    ingredients = models.TextField("Thành phần", blank=True)
    benefits = models.TextField("Công dụng", blank=True)
    usage = models.TextField("Hướng dẫn sử dụng", blank=True)
    status = models.CharField("Trạng thái", max_length=12, choices=Status.choices, default=Status.DRAFT)
    is_featured = models.BooleanField("Nổi bật (trang chủ)", default=False)
    is_new = models.BooleanField("Sản phẩm mới (trang chủ)", default=False)
    is_on_sale_section = models.BooleanField("Khu đang giảm giá (trang chủ)", default=False)
    search_text = models.TextField(blank=True, editable=False)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "Sản phẩm"
        indexes = [models.Index(fields=["status", "published_at"])]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("store:product", args=[self.slug])

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = "SP" + uuid.uuid4().hex[:8].upper()
        if self.status == self.Status.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        self.refresh_search_text(save=False)
        super().save(*args, **kwargs)

    def refresh_search_text(self, save=True):
        parts = [self.name, self.code]
        if self.brand_id:
            parts.append(self.brand.name)
        if self.pk:
            parts += list(self.variants.values_list("sku", flat=True))
            parts += list(self.variants.values_list("value", flat=True))
        self.search_text = normalize_search(" ".join(p for p in parts if p))
        if save and self.pk:
            Product.objects.filter(pk=self.pk).update(search_text=self.search_text)

    @property
    def main_image(self):
        images = list(self.images.all())
        for img in images:
            if img.is_main:
                return img
        return images[0] if images else None

    def active_variants(self):
        return [v for v in self.variants.all() if v.is_active]

    @property
    def display_variant(self):
        """Biến thể có giá thấp nhất trong số còn hàng (hoặc thấp nhất nếu hết hàng)."""
        variants = self.active_variants()
        if not variants:
            return None
        in_stock = [v for v in variants if v.stock > 0]
        return min(in_stock or variants, key=lambda v: v.price)

    @property
    def in_stock(self):
        return any(v.stock > 0 for v in self.active_variants())

    @property
    def has_price_range(self):
        prices = {v.price for v in self.active_variants()}
        return len(prices) > 1


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to=upload_product_image)
    thumb = models.ImageField(upload_to=upload_product_image, blank=True)
    alt = models.CharField("Mô tả ảnh", max_length=200, blank=True)
    sort_order = models.IntegerField(default=0)
    is_main = models.BooleanField("Ảnh đại diện", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.alt or f"Ảnh {self.pk}"

    @property
    def thumb_url(self):
        return (self.thumb or self.image).url


class Variant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField("SKU", max_length=64, unique=True)
    value = models.CharField(
        "Giá trị biến thể", max_length=80, blank=True, help_text="Ví dụ: 50ml, 01 Đỏ Cam. Để trống nếu chỉ có 1 loại."
    )
    color_hex = models.CharField("Mã màu", max_length=7, blank=True, validators=[validate_hex_color])
    price = models.PositiveBigIntegerField("Giá bán (đ)")
    compare_at_price = models.PositiveBigIntegerField("Giá gốc (đ)", null=True, blank=True)
    stock = models.IntegerField("Tồn kho", default=0)
    image = models.ForeignKey(
        ProductImage, verbose_name="Ảnh riêng", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    is_active = models.BooleanField("Đang bán", default=True)
    sort_order = models.IntegerField("Thứ tự", default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            # Chốt chặn cuối ở database: tồn kho không bao giờ âm.
            models.CheckConstraint(condition=Q(stock__gte=0), name="variant_stock_non_negative"),
        ]

    def __str__(self):
        return f"{self.product.name} - {self.value}" if self.value else self.product.name

    @property
    def label(self):
        return self.value or "Mặc định"

    @property
    def is_discounted(self):
        return bool(self.compare_at_price and self.compare_at_price > self.price)


class PriceHistory(models.Model):
    class Source(models.TextChoices):
        MANUAL = "manual", "Sửa tay"
        BULK = "bulk", "Cập nhật hàng loạt"
        IMPORT = "import", "Nhập Excel"
        CREATE = "create", "Tạo mới"

    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="price_history")
    old_price = models.PositiveBigIntegerField(null=True)
    new_price = models.PositiveBigIntegerField()
    old_compare_at_price = models.PositiveBigIntegerField(null=True)
    new_compare_at_price = models.PositiveBigIntegerField(null=True)
    source = models.CharField(max_length=10, choices=Source.choices)
    reason = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    changed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-changed_at", "-id"]


class StockMovement(models.Model):
    class Kind(models.TextChoices):
        INITIAL = "initial", "Tồn ban đầu"
        ADJUST = "adjust", "Điều chỉnh"
        IMPORT = "import", "Nhập Excel"
        ORDER = "order", "Trừ cho đơn hàng"
        ORDER_CANCEL = "order_cancel", "Hoàn do hủy đơn"
        ORDER_RETURN = "order_return", "Hoàn do trả hàng"

    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="stock_movements")
    kind = models.CharField(max_length=15, choices=Kind.choices)
    delta = models.IntegerField()
    stock_after = models.IntegerField()
    reason = models.CharField(max_length=255, blank=True)
    order_item = models.ForeignKey(
        "orders.OrderItem", null=True, blank=True, on_delete=models.PROTECT, related_name="stock_movements"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            # Mỗi dòng đơn chỉ được trừ kho 1 lần và hoàn kho 1 lần.
            models.UniqueConstraint(
                fields=["order_item", "kind"],
                condition=Q(order_item__isnull=False),
                name="stock_once_per_order_item_kind",
            ),
            models.UniqueConstraint(
                fields=["order_item"],
                condition=Q(kind__in=["order_cancel", "order_return"]),
                name="stock_restock_once_per_order_item",
            ),
        ]


def unique_slug(model, base, instance_pk=None, max_length=180):
    base = vn_slugify(base, max_length) or "muc"
    slug, i = base, 2
    qs = model.objects.all()
    if instance_pk:
        qs = qs.exclude(pk=instance_pk)
    while qs.filter(slug=slug).exists():
        slug = f"{base}-{i}"
        i += 1
    return slug


class ImportJob(models.Model):
    """Kết quả kiểm tra file Excel, chờ người dùng xác nhận mới ghi vào database."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    filename = models.CharField(max_length=255)
    plan = models.JSONField(default=dict)
    summary = models.JSONField(default=dict)
    errors = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
