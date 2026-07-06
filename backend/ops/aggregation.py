"""Read-side aggregation queries backing the dashboard.

Kept as plain ORM aggregate queries (SUM/COUNT with GROUP BY) rather than
pre-computed rollup tables. At 40 venues and realistic POS volume, these
queries are cheap and always-correct; a rollup table would add write-path
complexity that isn't justified at this scale. See README for the scale
threshold where that trade-off flips.
"""
from decimal import Decimal

from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncHour
from django.utils import timezone

from .anomaly import evaluate_venue_anomalies
from .models import Transaction, Venue

ZERO = Value(Decimal("0"), output_field=DecimalField(max_digits=10, decimal_places=2))


def _today_range(now=None):
    now = now or timezone.localtime()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, now


def venue_sales_ranking(now=None):
    """Total 'sale'-type revenue per venue today, ranked highest to lowest."""
    start, now = _today_range(now)
    rows = (
        Transaction.objects.filter(timestamp__gte=start, timestamp__lte=now, type=Transaction.Type.SALE)
        .values("venue_id", "venue__name")
        .annotate(total_sales=Coalesce(Sum("total"), ZERO), sale_count=Count("id"))
        .order_by("-total_sales")
    )
    return [
        {
            "venue_id": row["venue_id"],
            "venue_name": row["venue__name"],
            "total_sales": row["total_sales"],
            "sale_count": row["sale_count"],
        }
        for row in rows
    ]


def top_items(venue_id=None, limit=10, now=None):
    """Top selling items by quantity, optionally scoped to one venue."""
    start, now = _today_range(now)
    qs = Transaction.objects.filter(
        timestamp__gte=start, timestamp__lte=now, type=Transaction.Type.SALE
    )
    if venue_id is not None:
        qs = qs.filter(venue_id=venue_id)

    rows = (
        qs.values("items__item_id", "items__name")
        .annotate(qty_sold=Coalesce(Sum("items__qty"), Value(0)))
        .exclude(items__item_id__isnull=True)
        .order_by("-qty_sold")[:limit]
    )
    return [
        {
            "item_id": row["items__item_id"],
            "name": row["items__name"],
            "qty_sold": row["qty_sold"],
        }
        for row in rows
    ]


def hourly_trade(venue_id, now=None):
    """Hourly sales buckets for today, for the venue drill-down view."""
    start, now = _today_range(now)
    rows = (
        Transaction.objects.filter(
            venue_id=venue_id, timestamp__gte=start, timestamp__lte=now, type=Transaction.Type.SALE
        )
        .annotate(hour=TruncHour("timestamp"))
        .values("hour")
        .annotate(total_sales=Coalesce(Sum("total"), ZERO), sale_count=Count("id"))
        .order_by("hour")
    )
    return [
        {
            "hour": row["hour"].isoformat(),
            "total_sales": row["total_sales"],
            "sale_count": row["sale_count"],
        }
        for row in rows
    ]


def venue_void_refund_summary(venue_id, now=None):
    start, now = _today_range(now)
    rows = Transaction.objects.filter(
        venue_id=venue_id, timestamp__gte=start, timestamp__lte=now
    ).aggregate(
        void_count=Count("id", filter=Q(type=Transaction.Type.VOID)),
        refund_count=Count("id", filter=Q(type=Transaction.Type.REFUND)),
        refund_total=Coalesce(Sum("total", filter=Q(type=Transaction.Type.REFUND)), ZERO),
    )
    return rows


def build_dashboard_snapshot(now=None):
    """The single payload sent to every connected dashboard client.

    Computed once per broadcast tick and fanned out to N connected
    sessions via the channel layer group, rather than each client
    triggering its own query load.
    """
    now = now or timezone.localtime()
    ranking = venue_sales_ranking(now=now)
    venue_ids = [row["venue_id"] for row in ranking]
    anomalies = evaluate_venue_anomalies(venue_ids, now=now)

    for row in ranking:
        row["anomalies"] = anomalies.get(row["venue_id"], {"sales_drop": False, "void_refund_spike": False})
        # Decimal isn't JSON-serializable by default; normalize at the edge.
        row["total_sales"] = str(row["total_sales"])

    group_top_items = top_items(now=now)

    return {
        "generated_at": now.isoformat(),
        "venues": ranking,
        "top_items": group_top_items,
    }


def build_venue_detail(venue_id, now=None):
    now = now or timezone.localtime()
    venue = Venue.objects.get(pk=venue_id)
    hourly = hourly_trade(venue_id, now=now)
    for bucket in hourly:
        bucket["total_sales"] = str(bucket["total_sales"])
    items = top_items(venue_id=venue_id, now=now)
    void_refund = venue_void_refund_summary(venue_id, now=now)
    anomalies = evaluate_venue_anomalies([venue_id], now=now).get(
        venue_id, {"sales_drop": False, "void_refund_spike": False}
    )
    return {
        "venue_id": venue_id,
        "venue_name": venue.name,
        "hourly_trade": hourly,
        "top_items": items,
        "void_count": void_refund["void_count"],
        "refund_count": void_refund["refund_count"],
        "refund_total": str(void_refund["refund_total"]),
        "anomalies": anomalies,
    }
