"""Tạo sẵn các trang nội dung cơ bản ở trạng thái Nháp, nội dung trống.

Chủ shop tự nhập nội dung chính sách rồi xuất bản. Không tự viết chính sách thay shop.
"""

from django.db import migrations

PAGES = [
    ("gioi-thieu", "Giới thiệu", 10),
    ("lien-he", "Liên hệ", 20),
    ("chinh-sach-giao-hang", "Chính sách giao hàng", 30),
    ("chinh-sach-doi-tra", "Chính sách đổi trả", 40),
    ("chinh-sach-bao-mat", "Chính sách bảo mật", 50),
]


def seed(apps, schema_editor):
    Page = apps.get_model("content", "Page")
    for slug, title, order in PAGES:
        Page.objects.get_or_create(slug=slug, defaults={"title": title, "sort_order": order})


class Migration(migrations.Migration):
    dependencies = [("content", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
