"""Tạo DỮ LIỆU DEMO để xem giao diện khi phát triển.

Chỉ chạy khi DEBUG=1. Mọi tên đều có tiền tố [DEMO], ảnh là ảnh tự vẽ, không phải sản phẩm thật.
Xóa dữ liệu demo: python manage.py seed_demo --clear
"""

import io
import random

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from PIL import Image, ImageDraw, ImageFont

from apps.catalog.models import Attribute, Brand, Category, PriceHistory, Product, ProductImage, StockMovement, Variant, unique_slug
from apps.catalog.services import adjust_stock
from apps.content.models import Banner
from apps.orders.models import OrderItem
from apps.promotions.models import Coupon

TAG = "[DEMO]"
PALETTE = [(244, 214, 222), (231, 222, 246), (214, 236, 228), (250, 232, 210), (220, 232, 246), (246, 220, 214)]

CATS = {
    "Trang điểm": ["Son môi", "Kem nền", "Phấn má"],
    "Chăm sóc da": ["Sữa rửa mặt", "Toner", "Kem dưỡng", "Kem chống nắng"],
    "Chăm sóc tóc": ["Dầu gội", "Dầu xả"],
    "Chăm sóc cơ thể": ["Sữa tắm", "Dưỡng thể"],
}
BRANDS = ["Demo Rose", "Demo Lab", "Demo Botanic", "Demo Pure"]


def _font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _image(text, size=(900, 900), color=None):
    color = color or random.choice(PALETTE)
    img = Image.new("RGB", size, color)
    d = ImageDraw.Draw(img)
    w, h = size
    # Hình chai/lọ đơn giản
    if w == h:
        d.rounded_rectangle([w * 0.38, h * 0.22, w * 0.62, h * 0.8], radius=40, fill=(255, 255, 255))
        d.rectangle([w * 0.44, h * 0.14, w * 0.56, h * 0.23], fill=(90, 80, 95))
    else:
        d.ellipse([w * 0.6, -h * 0.4, w * 1.1, h * 1.2], fill=tuple(min(255, c + 12) for c in color))
    d.text((w * 0.06, h * 0.86 if w == h else h * 0.38), text, fill=(70, 60, 75), font=_font(int(h * (0.05 if w == h else 0.12))))
    d.text((w * 0.06, h * 0.05), "DEMO", fill=(178, 58, 98), font=_font(int(h * 0.07)))
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=80)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Tạo dữ liệu demo (chỉ dùng khi phát triển)."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Xóa dữ liệu demo")

    def handle(self, *args, **opts):
        if not settings.DEBUG:
            raise CommandError("Chỉ chạy được khi DEBUG=1. Không tạo dữ liệu demo trên production.")
        if opts["clear"]:
            return self.clear()
        random.seed(7)
        with transaction.atomic():
            self.seed()
        self.stdout.write(self.style.SUCCESS("Đã tạo dữ liệu demo. Xóa bằng: python manage.py seed_demo --clear"))

    def clear(self):
        demo = Product.objects.filter(name__startswith=TAG)
        if OrderItem.objects.filter(variant__product__in=demo).exists():
            raise CommandError("Có đơn hàng chứa sản phẩm demo. Hãy xóa database dev thay vì xóa từng phần.")
        for img in ProductImage.objects.filter(product__in=demo):
            img.image.delete(save=False)
            img.thumb.delete(save=False)
        demo.delete()
        Brand.objects.filter(name__startswith="Demo ").delete()
        for b in Banner.objects.filter(title__startswith=TAG):
            b.image.delete(save=False)
            b.delete()
        Coupon.objects.filter(code="DEMO10").delete()
        Category.objects.filter(products__isnull=True, parent__isnull=False, description=TAG).delete()
        Category.objects.filter(products__isnull=True, children__isnull=True, description=TAG).delete()
        self.stdout.write("Đã xóa dữ liệu demo.")

    def seed(self):
        cats = []
        for i, (root, children) in enumerate(CATS.items()):
            parent, _ = Category.objects.get_or_create(
                name=root, parent=None, defaults={"slug": unique_slug(Category, root), "sort_order": i, "description": TAG, "show_on_home": True}
            )
            for j, child in enumerate(children):
                c, _ = Category.objects.get_or_create(
                    name=child, parent=parent, defaults={"slug": unique_slug(Category, child), "sort_order": j, "description": TAG}
                )
                cats.append(c)
        brands = [
            Brand.objects.get_or_create(name=b, defaults={"slug": unique_slug(Brand, b)})[0] for b in BRANDS
        ]
        vol, _ = Attribute.objects.get_or_create(name="Dung tích")
        color, _ = Attribute.objects.get_or_create(name="Màu sắc", defaults={"is_color": True})

        n = 0
        for c in cats:
            for k in range(3):
                n += 1
                is_lip = c.name == "Son môi"
                name = f"{TAG} {c.name} mẫu số {n}"
                p = Product.objects.create(
                    name=name, slug=unique_slug(Product, name), code=f"DEMO{n:03d}", brand=random.choice(brands), category=c,
                    variant_attribute=color if is_lip else (vol if k != 2 else None), status=Product.Status.PUBLISHED,
                    short_description="Sản phẩm demo để xem giao diện. Không phải sản phẩm thật.",
                    description="Nội dung mô tả demo.\n\nThay bằng thông tin do nhà sản xuất hoặc nhà phân phối cung cấp.",
                    usage="- Hướng dẫn sử dụng demo.\n- Thay bằng hướng dẫn của nhà sản xuất.",
                    is_featured=n % 4 == 0, is_new=n % 3 == 0, is_on_sale_section=n % 5 == 0,
                )
                for idx in range(2):
                    data = _image(f"Mẫu {n}" + (" - mặt sau" if idx else ""))
                    img = ProductImage(product=p, sort_order=idx, is_main=idx == 0, alt=name)
                    img.image.save(f"demo{n}_{idx}.webp", ContentFile(data), save=False)
                    img.thumb.save(f"demo{n}_{idx}_t.webp", ContentFile(data), save=False)
                    img.save()
                if is_lip:
                    options = [("01 Đỏ", "#B3263E"), ("02 Hồng đất", "#B5656B"), ("03 Cam", "#D9603B")]
                elif p.variant_attribute_id:
                    options = [("30ml", ""), ("50ml", "")]
                else:
                    options = [("", "")]
                base = random.choice([129000, 159000, 189000, 245000, 320000, 450000])
                for vi, (value, hexc) in enumerate(options):
                    price = base + vi * 40000
                    compare = price + random.choice([0, 0, 30000, 60000]) or None
                    if compare == price:
                        compare = None
                    v = Variant.objects.create(
                        product=p, sku=f"DEMO{n:03d}-{vi + 1}", value=value, color_hex=hexc, price=price,
                        compare_at_price=compare, sort_order=vi,
                    )
                    PriceHistory.objects.create(variant=v, new_price=price, new_compare_at_price=compare, source="create", reason="Demo")
                    stock = random.choice([0, 3, 12, 25, 40]) if n % 7 else 0
                    if stock:
                        adjust_stock(v.pk, stock, StockMovement.Kind.INITIAL, reason="Demo")
                p.refresh_search_text()

        sale = cats[0]
        for i, (title, place, size) in enumerate(
            [("Ưu đãi tháng này", "hero", (1600, 700)), ("Hàng mới về", "hero", (1600, 700)),
             ("Chăm sóc da", "side", (800, 400)), ("Trang điểm", "side", (800, 400)), ("Thương hiệu", "strip", (1600, 300))]
        ):
            b = Banner(title=f"{TAG} {title}", placement=place, sort_order=i, link_url="/khuyen-mai/" if i == 0 else sale.get_absolute_url())
            b.image.save(f"demo_banner_{i}.webp", ContentFile(_image(f"{TAG} {title}", size)), save=False)
            b.save()
        Coupon.objects.get_or_create(code="DEMO10", defaults={"description": "Mã demo giảm 10%", "discount_type": "percent", "value": 10, "max_discount": 50000})
