import io
import uuid

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.catalog.models import Brand, Category, Product, StockMovement, Variant
from apps.catalog.services import adjust_stock
from apps.core.models import SiteSettings
from apps.core.roles import sync_roles

PASSWORD = "Test-Password-2026!"


def make_user(username, *roles, active=True):
    sync_roles()
    u = User.objects.create_user(username, password=PASSWORD, is_staff=True, is_active=active)
    u.groups.set(Group.objects.filter(name__in=roles))
    return u


def make_product(name="Son thử", price=100_000, stock=10, compare=None, status=Product.Status.PUBLISHED, variants=None):
    brand, _ = Brand.objects.get_or_create(name="Hãng A", defaults={"slug": "hang-a"})
    cat, _ = Category.objects.get_or_create(name="Son môi", defaults={"slug": "son-moi"})
    p = Product.objects.create(name=name, slug=f"p-{uuid.uuid4().hex[:8]}", brand=brand, category=cat, status=status)
    variants = variants or [("", price, compare, stock)]
    out = []
    for i, (value, vprice, vcompare, vstock) in enumerate(variants):
        v = Variant.objects.create(product=p, sku=f"SKU-{uuid.uuid4().hex[:8]}", value=value, price=vprice, compare_at_price=vcompare)
        if vstock:
            adjust_stock(v.pk, vstock, StockMovement.Kind.INITIAL)
        v.refresh_from_db()
        out.append(v)
    p.refresh_search_text()
    return p, out


def configure_site(**kw):
    s = SiteSettings.load()
    defaults = {"shipping_flat_fee": 30_000, "free_shipping_threshold": 500_000, "cod_enabled": True}
    defaults.update(kw)
    for k, v in defaults.items():
        setattr(s, k, v)
    s.save()
    return s


def customer(phone="0912345678"):
    return {"customer_name": "Nguyễn Văn A", "phone": phone, "email": "", "address": "12 Đường Thử, Quận 1", "customer_note": ""}


def png_upload(name="a.png", size=(60, 60)):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 100, 120)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")
