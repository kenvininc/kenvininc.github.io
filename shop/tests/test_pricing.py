from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.core.models import SiteSettings
from apps.core.text import format_vnd, render_rich_text
from apps.orders.services import build_quote, place_order, shipping_fee_for
from apps.promotions.models import Coupon
from apps.promotions.services import CouponError, check_coupon, compute_discount

from .helpers import configure_site, customer, make_product


class MoneyFormatTests(SimpleTestCase):
    def test_vnd(self):
        self.assertEqual(format_vnd(1234567), "1.234.567 ₫")
        self.assertEqual(format_vnd(0), "0 ₫")
        self.assertEqual(format_vnd(None), "")


class RichTextTests(SimpleTestCase):
    def test_html_is_escaped(self):
        out = render_rich_text('<script>alert(1)</script> **đậm**')
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn("<strong>đậm</strong>", out)

    def test_only_safe_links(self):
        self.assertIn('href="/trang/a/"', render_rich_text("[a](/trang/a/)"))
        self.assertIn('href="https://x.vn"', render_rich_text("[a](https://x.vn)"))
        for bad in ("[a](javascript:alert(1))", "[a](//evil.com)", "[a](/\\evil.com)", '[a](https://x" onclick="y)'):
            out = render_rich_text(bad)
            self.assertNotIn("javascript:", out.split("href=")[-1] if "href=" in out else "")
            self.assertNotIn('href="//', out)
            self.assertNotIn("onclick=\"", out)

    def test_lists_and_headings(self):
        out = render_rich_text("## Tiêu đề\n- một\n- hai\n\nĐoạn")
        self.assertIn("<h3>Tiêu đề</h3>", out)
        self.assertIn("<ul><li>một</li><li>hai</li></ul>", out)
        self.assertIn("<p>Đoạn</p>", out)


class CouponMathTests(SimpleTestCase):
    def test_fixed_never_exceeds_subtotal(self):
        c = Coupon(discount_type="fixed", value=50_000)
        self.assertEqual(compute_discount(c, 200_000), 50_000)
        self.assertEqual(compute_discount(c, 30_000), 30_000)

    def test_percent_floor_and_cap(self):
        c = Coupon(discount_type="percent", value=15)
        self.assertEqual(compute_discount(c, 99_999), 14_999)  # làm tròn xuống, số nguyên đồng
        c.max_discount = 10_000
        self.assertEqual(compute_discount(c, 200_000), 10_000)

    def test_shipping_threshold_uses_amount_after_discount(self):
        s = SiteSettings(shipping_flat_fee=30_000, free_shipping_threshold=500_000)
        self.assertEqual(shipping_fee_for(499_999, s), 30_000)
        self.assertEqual(shipping_fee_for(500_000, s), 0)
        s.free_shipping_threshold = None
        self.assertEqual(shipping_fee_for(10_000_000, s), 30_000)


class CouponRuleTests(TestCase):
    def test_conditions(self):
        now = timezone.now()
        c = Coupon.objects.create(code="A", discount_type="fixed", value=10_000, min_order_value=100_000)
        with self.assertRaisesMessage(CouponError, "đơn từ"):
            check_coupon(c, 99_000)
        self.assertEqual(check_coupon(c, 100_000), 10_000)
        c.is_active = False
        with self.assertRaises(CouponError):
            check_coupon(c, 200_000)
        c.is_active, c.starts_at = True, now + timedelta(hours=1)
        with self.assertRaisesMessage(CouponError, "chưa đến"):
            check_coupon(c, 200_000)
        c.starts_at, c.ends_at = None, now - timedelta(seconds=1)
        with self.assertRaisesMessage(CouponError, "hết hạn"):
            check_coupon(c, 200_000)
        c.ends_at, c.usage_limit, c.used_count = None, 1, 1
        with self.assertRaisesMessage(CouponError, "hết lượt"):
            check_coupon(c, 200_000)

    def test_quote_is_computed_from_database(self):
        configure_site()
        _p, (v,) = make_product(price=120_000, stock=5)
        Coupon.objects.create(code="GIAM10", discount_type="percent", value=10)
        q = build_quote({v.pk: 2}, "giam10")
        self.assertEqual(q.subtotal, 240_000)
        self.assertEqual(q.discount, 24_000)
        self.assertEqual(q.shipping_fee, 30_000)
        self.assertEqual(q.total, 246_000)

    def test_per_phone_limit(self):
        configure_site()
        _p, (v,) = make_product(stock=10)
        Coupon.objects.create(code="MOT", discount_type="fixed", value=5_000, usage_limit_per_phone=1)
        import uuid

        place_order({v.pk: 1}, customer("0911111111"), "cod", "MOT", uuid.uuid4())
        from apps.orders.services import OrderError

        with self.assertRaisesMessage(OrderError, "hết lượt"):
            place_order({v.pk: 1}, customer("0911111111"), "cod", "MOT", uuid.uuid4())
        place_order({v.pk: 1}, customer("0922222222"), "cod", "MOT", uuid.uuid4())
