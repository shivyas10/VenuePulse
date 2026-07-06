from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from ops.anomaly import evaluate_venue_anomalies
from ops.models import Transaction
from ops.tests.factories import make_transaction, make_venue


@override_settings(
    ANOMALY_SALES_DROP_WINDOW_MINUTES=60,
    ANOMALY_SALES_DROP_THRESHOLD=0.4,
    ANOMALY_SALES_DROP_MIN_BASELINE=50,
    ANOMALY_VOID_REFUND_WINDOW_MINUTES=60,
    ANOMALY_VOID_REFUND_RATIO_THRESHOLD=0.2,
    ANOMALY_VOID_REFUND_MIN_COUNT=5,
)
class SalesDropTests(TestCase):
    def setUp(self):
        self.now = timezone.localtime()
        self.venue = make_venue()

    def test_flags_a_sharp_drop_against_the_prior_hour(self):
        two_hours_ago = self.now - timedelta(minutes=90)
        make_transaction(self.venue, two_hours_ago, total="200.00")
        # last hour: nothing -> 100% drop vs a healthy baseline

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertTrue(result[self.venue.id]["sales_drop"])

    def test_does_not_flag_when_prior_window_is_below_min_baseline(self):
        two_hours_ago = self.now - timedelta(minutes=90)
        make_transaction(self.venue, two_hours_ago, total="10.00")  # below $50 baseline

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertFalse(result[self.venue.id]["sales_drop"])

    def test_does_not_flag_steady_trade(self):
        two_hours_ago = self.now - timedelta(minutes=90)
        thirty_min_ago = self.now - timedelta(minutes=30)
        make_transaction(self.venue, two_hours_ago, total="100.00")
        make_transaction(self.venue, thirty_min_ago, total="95.00")

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertFalse(result[self.venue.id]["sales_drop"])


@override_settings(
    ANOMALY_VOID_REFUND_WINDOW_MINUTES=60,
    ANOMALY_VOID_REFUND_RATIO_THRESHOLD=0.2,
    ANOMALY_VOID_REFUND_MIN_COUNT=5,
)
class VoidRefundSpikeTests(TestCase):
    def setUp(self):
        self.now = timezone.localtime()
        self.venue = make_venue()

    def test_flags_high_void_refund_ratio(self):
        for _ in range(4):
            make_transaction(self.venue, self.now, tx_type=Transaction.Type.SALE, total="20.00")
        for _ in range(3):
            make_transaction(self.venue, self.now, tx_type=Transaction.Type.VOID, total="20.00")

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertTrue(result[self.venue.id]["void_refund_spike"])

    def test_does_not_flag_below_min_sample_size(self):
        make_transaction(self.venue, self.now, tx_type=Transaction.Type.VOID, total="20.00")
        make_transaction(self.venue, self.now, tx_type=Transaction.Type.SALE, total="20.00")
        # total count = 2, below ANOMALY_VOID_REFUND_MIN_COUNT=5

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertFalse(result[self.venue.id]["void_refund_spike"])

    def test_does_not_flag_healthy_ratio(self):
        for _ in range(9):
            make_transaction(self.venue, self.now, tx_type=Transaction.Type.SALE, total="20.00")
        make_transaction(self.venue, self.now, tx_type=Transaction.Type.VOID, total="20.00")

        result = evaluate_venue_anomalies([self.venue.id], now=self.now)

        self.assertFalse(result[self.venue.id]["void_refund_spike"])
