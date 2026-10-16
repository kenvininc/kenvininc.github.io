import uuid
from unittest import mock

from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.catalog.models import Product, StockMovement
from apps.catalog.services import set_price
from apps.orders.models import Order, OrderEvent
from apps.orders.services import (
    OrderError,
    cancel_unpaid_bank_orders,
    change_payment,
    change_status,
    place_order,
    restock_returned,
)
from apps.promotions.models import Coupon

from .helpers import configure_site, customer, make_product


class PlaceOrderTests(TestCase):
    def setUp(self):
        configure_site()
        self.p, (self.v,) = make_product(price=150_000, compare=180_000, stock=5)

    def test_snapshot_totals_and_stock(self):
        Coupon.objects.create(code="G20", discount_type="fixed", value=20_000)
        order, created = place_order({self.v.pk: 2}, customer(), "cod", "G20", uuid.uuid4())
        self.assertTrue(created)
        self.assertEqual((order.subtotal, order.discount_total, order.shipping_fee, order.total), (300_000, 20_000, 30_000, 310_000))
        item = order.items.get()
        self.assertEqual((item.product_name, item.sku, item.unit_price, item.compare_at_price, item.quantity, item.line_total),
                         (self.p.name, self.v.sku, 150_000, 180_000, 2, 300_000))
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 3)
        self.assertEqual(StockMovement.objects.filter(order_item=item, kind="order").get().delta, -2)
        self.assertEqual(Coupon.objects.get(code="G20").used_count, 1)
        self.assertEqual(order.phone, "0912345678")

    def test_price_change_does_not_alter_existing_order(self):
        order, _ = place_order({self.v.pk: 1}, customer(), "cod", "", uuid.uuid4())
        set_price(self.v, 99_000, None, None, "manual")
        Product.objects.filter(pk=self.p.pk).update(name="Tên mới")
        order.refresh_from_db()
        item = order.items.get()
        self.assertEqual((item.unit_price, item.product_name, order.total), (150_000, self.p.name, 180_000))

    def test_idempotent_resubmit(self):
        key = uuid.uuid4()
        o1, c1 = place_order({self.v.pk: 1}, customer(), "cod", "", key)
        o2, c2 = place_order({self.v.pk: 1}, customer(), "cod", "", key)
        self.assertEqual(o1.pk, o2.pk)
        self.assertEqual((c1, c2), (True, False))
        self.assertEqual(Order.objects.count(), 1)
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 4)

    def test_cannot_oversell(self):
        with self.assertRaises(OrderError):
            place_order({self.v.pk: 6}, customer(), "cod", "", uuid.uuid4())
        self.v.refresh_from_db()
        self.assertEqual(self.v.stock, 5)
        self.assertEqual(Order.objects.count(), 0)
        place_order({self.v.pk: 5}, customer(), "cod", "", uuid.uuid4())
        with self.assertRaises(OrderError):
            place_order({self.v.pk: 1}, customer(), "cod", "", uuid.uuid4())

    def test_database_rejects_negative_stock(self):
        from apps.catalog.models import Variant

        with self.assertRaises(IntegrityError), transaction.atomic():
            Variant.objects.filter(pk=self.v.pk).update(stock=-1)

    def test_unpublished_or_disabled_cannot_be_ordered(self):
        Product.objects.filter(pk=self.p.pk).update(status=Product.Status.HIDDEN)
        with self.assertRaises(OrderError):
            place_order({self.v.pk: 1}, customer(), "cod", "", uuid.uuid4())

    def test_payment_method_must_be_enabled(self):
        with self.assertRaises(OrderError):
            place_order({self.v.pk: 1}, customer(), "bank_transfer", "", uuid.uuid4())

    @override_settings(EMAIL_HOST="smtp.invalid")
    def test_email_failure_keeps_order(self):
        with mock.patch("apps.orders.services.send_mail", side_effect=OSError("down")):
            with self.captureOnCommitCallbacks(execute=True):
                order, _ = place_order({self.v.pk: 1}, {**customer(), "email": "a@b.vn"}, "cod", "", uuid.uuid4())
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())
        self.assertTrue(OrderEvent.objects.filter(order=order, kind="email", note__icontains="thất bại").exists())


class OrderProcessingTests(TestCase):
    def setUp(self):
        configure_site()
        self.p, (self.v,) = make_product(price=100_000, stock=10)
        Coupon.objects.create(code="C1", discount_type="fixed", value=10_000, usage_limit=1)
        self.order, _ = place_order({self.v.pk: 3}, customer(), "cod", "C1", uuid.uuid4())

    def stock(self):
        self.v.refresh_from_db()
        return self.v.stock

    def test_cancel_restocks_exactly_once_and_releases_coupon(self):
        self.assertEqual(self.stock(), 7)
        self.assertEqual(Coupon.objects.get(code="C1").used_count, 1)
        change_status(self.order.pk, "cancelled", None, note="Khách hủy")
        self.assertEqual(self.stock(), 10)
        self.assertEqual(Coupon.objects.get(code="C1").used_count, 0)
        with self.assertRaises(OrderError):
            change_status(self.order.pk, "cancelled", None)
        self.assertEqual(self.stock(), 10)

    def test_invalid_transitions(self):
        with self.assertRaises(OrderError):
            change_status(self.order.pk, "completed", None)
        for s in ("confirmed", "packing", "shipping"):
            change_status(self.order.pk, s, None)
        with self.assertRaises(OrderError):
            change_status(self.order.pk, "cancelled", None)  # đang giao thì không hủy, chỉ hoàn/trả

    def test_return_restock_once(self):
        for s in ("confirmed", "packing", "shipping", "completed"):
            change_status(self.order.pk, s, None)
        change_status(self.order.pk, "returned", None, restock_return=False)
        self.assertEqual(self.stock(), 7)
        restock_returned(self.order.pk, None)
        self.assertEqual(self.stock(), 10)
        with self.assertRaises(OrderError):
            restock_returned(self.order.pk, None)
        self.assertEqual(self.stock(), 10)
        self.assertEqual(StockMovement.objects.filter(kind="order_return").count(), 1)

    def test_restock_unique_constraint(self):
        item = self.order.items.get()
        StockMovement.objects.create(variant=self.v, kind="order_cancel", delta=3, stock_after=10, order_item=item)
        with self.assertRaises(IntegrityError), transaction.atomic():
            StockMovement.objects.create(variant=self.v, kind="order_return", delta=3, stock_after=13, order_item=item)

    def test_payment_status(self):
        change_payment(self.order.pk, "paid", None)
        with self.assertRaisesMessage(OrderError, "lý do"):
            change_payment(self.order.pk, "refunded", None, note="")
        change_payment(self.order.pk, "refunded", None, note="Trả lại tiền")
        o = Order.objects.get(pk=self.order.pk)
        self.assertEqual(o.payment_status, "refunded")
        self.assertEqual(o.status, "new")  # trạng thái xử lý độc lập với thanh toán

    def test_auto_cancel_unpaid_bank_transfer(self):
        configure_site(bank_transfer_enabled=True, bank_name="NH", bank_account_number="1", bank_account_name="A")
        bank, _ = place_order({self.v.pk: 2}, customer(), "bank_transfer", "", uuid.uuid4())
        Order.objects.filter(pk=bank.pk).update(created_at=bank.created_at - __import__("datetime").timedelta(hours=25))
        self.assertEqual(cancel_unpaid_bank_orders(24), 1)
        self.assertEqual(Order.objects.get(pk=bank.pk).status, "cancelled")
        self.assertEqual(Order.objects.get(pk=self.order.pk).status, "new")  # COD không bị hủy
        self.assertEqual(self.stock(), 7)
