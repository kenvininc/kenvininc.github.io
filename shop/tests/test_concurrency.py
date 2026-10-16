"""Kiểm tra đặt hàng đồng thời trên PostgreSQL thật (khóa dòng select_for_update)."""

import threading
import unittest
import uuid

from django.db import connection, connections
from django.test import TransactionTestCase

from apps.orders.models import Order
from apps.orders.services import OrderError, place_order

from .helpers import configure_site, customer, make_product


@unittest.skipUnless(connection.vendor == "postgresql", "Cần PostgreSQL")
class ConcurrentOrderTests(TransactionTestCase):
    def _run(self, n, fn):
        barrier = threading.Barrier(n)
        results = []

        def worker(i):
            try:
                barrier.wait()
                results.append(("ok", fn(i)))
            except OrderError as e:
                results.append(("err", str(e)))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return results

    def test_last_items_sold_once(self):
        configure_site()
        _p, (v,) = make_product(stock=3)
        results = self._run(8, lambda i: place_order({v.pk: 1}, customer(), "cod", "", uuid.uuid4()))
        v.refresh_from_db()
        self.assertEqual(sum(1 for r in results if r[0] == "ok"), 3)
        self.assertEqual(v.stock, 0)
        self.assertEqual(Order.objects.count(), 3)

    def test_same_request_sent_concurrently_creates_one_order(self):
        configure_site()
        _p, (v,) = make_product(stock=10)
        key = uuid.uuid4()
        results = self._run(5, lambda i: place_order({v.pk: 2}, customer(), "cod", "", key)[0].pk)
        ids = {r[1] for r in results if r[0] == "ok"}
        self.assertEqual(len(ids), 1)
        self.assertEqual(Order.objects.count(), 1)
        v.refresh_from_db()
        self.assertEqual(v.stock, 8)
