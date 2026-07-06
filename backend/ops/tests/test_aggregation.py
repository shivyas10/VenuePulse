from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from ops.aggregation import hourly_trade, top_items, venue_sales_ranking
from ops.models import Transaction
from ops.tests.factories import make_transaction, make_venue


class VenueSalesRankingTests(TestCase):
    def setUp(self):
        self.now = timezone.localtime()
        self.venue_a = make_venue("Venue A")
        self.venue_b = make_venue("Venue B")

    def test_ranks_highest_total_first(self):
        make_transaction(self.venue_a, self.now, total="50.00")
        make_transaction(self.venue_b, self.now, total="200.00")

        ranking = venue_sales_ranking(now=self.now)

        self.assertEqual([row["venue_id"] for row in ranking], [self.venue_b.id, self.venue_a.id])
        self.assertEqual(ranking[0]["total_sales"], Decimal("200.00"))

    def test_only_counts_sale_type_not_void_or_refund(self):
        make_transaction(self.venue_a, self.now, tx_type=Transaction.Type.SALE, total="100.00")
        make_transaction(self.venue_a, self.now, tx_type=Transaction.Type.VOID, total="30.00")
        make_transaction(self.venue_a, self.now, tx_type=Transaction.Type.REFUND, total="20.00")

        ranking = venue_sales_ranking(now=self.now)

        self.assertEqual(ranking[0]["total_sales"], Decimal("100.00"))
        self.assertEqual(ranking[0]["sale_count"], 1)

    def test_excludes_transactions_from_before_today(self):
        yesterday = self.now - timedelta(days=1)
        make_transaction(self.venue_a, yesterday, total="500.00")

        ranking = venue_sales_ranking(now=self.now)

        self.assertEqual(ranking, [])


class TopItemsTests(TestCase):
    def setUp(self):
        self.now = timezone.localtime()
        self.venue = make_venue()

    def test_ranks_by_quantity_sold(self):
        make_transaction(
            self.venue,
            self.now,
            items=[{"item_id": "beer", "name": "Beer", "qty": 5, "price": "8.00"}],
        )
        make_transaction(
            self.venue,
            self.now,
            items=[{"item_id": "wine", "name": "Wine", "qty": 2, "price": "12.00"}],
        )

        items = top_items(now=self.now)

        self.assertEqual(items[0]["item_id"], "beer")
        self.assertEqual(items[0]["qty_sold"], 5)

    def test_scoped_to_single_venue(self):
        other_venue = make_venue("Other Venue")
        make_transaction(
            self.venue, self.now, items=[{"item_id": "beer", "name": "Beer", "qty": 3, "price": "8.00"}]
        )
        make_transaction(
            other_venue, self.now, items=[{"item_id": "wine", "name": "Wine", "qty": 9, "price": "12.00"}]
        )

        items = top_items(venue_id=self.venue.id, now=self.now)

        self.assertEqual([i["item_id"] for i in items], ["beer"])


class HourlyTradeTests(TestCase):
    def test_buckets_by_hour(self):
        now = timezone.localtime().replace(minute=30, second=0, microsecond=0)
        venue = make_venue()
        hour_ago = now - timedelta(hours=1)

        make_transaction(venue, hour_ago, total="40.00")
        make_transaction(venue, now, total="60.00")

        buckets = hourly_trade(venue.id, now=now)

        self.assertEqual(len(buckets), 2)
        self.assertEqual(Decimal(buckets[-1]["total_sales"]), Decimal("60.00"))
