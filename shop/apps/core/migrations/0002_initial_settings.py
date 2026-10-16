"""Thông tin shop đã được chủ shop xác nhận: tên Kenvin Shop, hotline 0946404793.

Các cấu hình kinh doanh khác (phí ship, thanh toán, chính sách) để trống,
chủ shop nhập trong /admin/cai-dat/.
"""

from django.db import migrations


def seed(apps, schema_editor):
    SiteSettings = apps.get_model("core", "SiteSettings")
    obj, created = SiteSettings.objects.get_or_create(pk=1, defaults={"shop_name": "Kenvin Shop", "hotline": "0946404793"})
    if not created and not obj.hotline:
        obj.hotline = "0946404793"
        obj.save(update_fields=["hotline"])


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
