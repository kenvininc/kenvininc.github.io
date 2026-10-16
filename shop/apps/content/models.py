from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone


def validate_link(value):
    if not value:
        return
    if value.startswith("/") and not value.startswith("//") and "\\" not in value:
        return
    if value.startswith("https://") or value.startswith("http://"):
        return
    raise ValidationError("Liên kết phải bắt đầu bằng / (trang trong shop) hoặc https://")


def upload_banner(instance, filename):
    return f"banners/{filename}"


class BannerQuerySet(models.QuerySet):
    def live(self, now=None):
        now = now or timezone.now()
        return (
            self.filter(is_active=True)
            .filter(models.Q(starts_at__isnull=True) | models.Q(starts_at__lte=now))
            .filter(models.Q(ends_at__isnull=True) | models.Q(ends_at__gt=now))
        )


class Banner(models.Model):
    class Placement(models.TextChoices):
        HERO = "hero", "Banner chính (trượt)"
        SIDE = "side", "Banner phụ bên phải"
        STRIP = "strip", "Banner ngang giữa trang"

    title = models.CharField("Tiêu đề (mô tả ảnh)", max_length=150)
    image = models.ImageField("Ảnh desktop", upload_to=upload_banner)
    image_mobile = models.ImageField("Ảnh điện thoại (tùy chọn)", upload_to=upload_banner, blank=True)
    link_url = models.CharField("Liên kết", max_length=300, blank=True, validators=[validate_link])
    placement = models.CharField("Vị trí", max_length=10, choices=Placement.choices, default=Placement.HERO)
    sort_order = models.IntegerField("Thứ tự", default=0)
    is_active = models.BooleanField("Đang bật", default=True)
    starts_at = models.DateTimeField("Hiện từ", null=True, blank=True)
    ends_at = models.DateTimeField("Hiện đến", null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = BannerQuerySet.as_manager()

    class Meta:
        ordering = ["placement", "sort_order", "id"]

    def __str__(self):
        return self.title


class Page(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        PUBLISHED = "published", "Đã xuất bản"

    title = models.CharField("Tiêu đề", max_length=150)
    slug = models.SlugField("Đường dẫn", max_length=120, unique=True)
    body = models.TextField("Nội dung", blank=True)
    status = models.CharField("Trạng thái", max_length=10, choices=Status.choices, default=Status.DRAFT)
    show_in_footer = models.BooleanField("Hiện ở chân trang", default=True)
    sort_order = models.IntegerField("Thứ tự", default=0)
    seo_title = models.CharField("Tiêu đề SEO", max_length=70, blank=True)
    seo_description = models.CharField("Mô tả SEO", max_length=170, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("store:page", args=[self.slug])
