"""Rule-based anomaly flags for the dashboard's visual cues.

Two simple, fixed-threshold rules rather than per-venue historical
baselines (e.g. "vs. this venue's trailing 7-day average for this time of
day"). A baseline model is the better long-term answer and is called out
in the README as the first thing to build next - it needs several days of
history to be meaningful, which a fresh take-home dataset doesn't have.
Fixed thresholds are transparent, tunable (see settings.py), and enough to
demonstrate the mechanism end-to-end.
"""
from datetime import timedelta

from django.conf import settings
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Transaction

ZERO = Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))


def _sales_total(venue_ids, start, end):
    # (start, end] - exclusive start / inclusive end - so adjacent windows
    # tile the timeline with no gap and no double-count at the shared edge.
    rows = (
        Transaction.objects.filter(
            venue_id__in=venue_ids, type=Transaction.Type.SALE, timestamp__gt=start, timestamp__lte=end
        )
        .values("venue_id")
        .annotate(total=Coalesce(Sum("total"), ZERO))
    )
    return {row["venue_id"]: row["total"] for row in rows}


def _sale_void_refund_counts(venue_ids, start, end):
    rows = (
        Transaction.objects.filter(venue_id__in=venue_ids, timestamp__gt=start, timestamp__lte=end)
        .values("venue_id")
        .annotate(
            sale_count=Count("id", filter=Q(type=Transaction.Type.SALE)),
            void_count=Count("id", filter=Q(type=Transaction.Type.VOID)),
            refund_count=Count("id", filter=Q(type=Transaction.Type.REFUND)),
        )
    )
    return {row["venue_id"]: row for row in rows}


def evaluate_venue_anomalies(venue_ids, now=None):
    """Returns {venue_id: {"sales_drop": bool, "void_refund_spike": bool}}."""
    if not venue_ids:
        return {}
    now = now or timezone.localtime()

    drop_window = timedelta(minutes=settings.ANOMALY_SALES_DROP_WINDOW_MINUTES)
    current_start = now - drop_window
    previous_start = now - (drop_window * 2)

    current_sales = _sales_total(venue_ids, current_start, now)
    previous_sales = _sales_total(venue_ids, previous_start, current_start)

    vr_window = timedelta(minutes=settings.ANOMALY_VOID_REFUND_WINDOW_MINUTES)
    vr_counts = _sale_void_refund_counts(venue_ids, now - vr_window, now)

    result = {}
    for venue_id in venue_ids:
        prev = previous_sales.get(venue_id, 0)
        curr = current_sales.get(venue_id, 0)
        sales_drop = False
        if prev >= settings.ANOMALY_SALES_DROP_MIN_BASELINE:
            drop_ratio = (prev - curr) / prev if prev else 0
            sales_drop = drop_ratio >= settings.ANOMALY_SALES_DROP_THRESHOLD

        counts = vr_counts.get(venue_id, {"sale_count": 0, "void_count": 0, "refund_count": 0})
        total_count = counts["sale_count"] + counts["void_count"] + counts["refund_count"]
        void_refund_spike = False
        if total_count >= settings.ANOMALY_VOID_REFUND_MIN_COUNT:
            ratio = (counts["void_count"] + counts["refund_count"]) / total_count
            void_refund_spike = ratio >= settings.ANOMALY_VOID_REFUND_RATIO_THRESHOLD

        result[venue_id] = {"sales_drop": sales_drop, "void_refund_spike": void_refund_spike}

    return result
