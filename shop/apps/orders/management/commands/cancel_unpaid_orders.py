"""Hủy đơn chuyển khoản chưa thanh toán quá số giờ cấu hình (Cấu hình cửa hàng).

Chạy định kỳ (ví dụ mỗi 30 phút) bằng Task Scheduler của Synology:
    docker exec kenvinshop-web python manage.py cancel_unpaid_orders
"""

from django.core.management.base import BaseCommand

from apps.core.models import SiteSettings
from apps.orders.services import cancel_unpaid_bank_orders


class Command(BaseCommand):
    help = "Hủy đơn chuyển khoản quá hạn chưa thanh toán và hoàn tồn kho."

    def handle(self, *args, **opts):
        hours = SiteSettings.load().bank_transfer_hold_hours
        if not hours:
            self.stdout.write("Chưa bật tự hủy (số giờ = 0). Không làm gì.")
            return
        n = cancel_unpaid_bank_orders(hours)
        self.stdout.write(f"Đã hủy {n} đơn.")
