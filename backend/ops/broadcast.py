"""Fan-out of dashboard snapshots to connected WebSocket clients.

Broadcasts are triggered from the ingestion write path (after commit) and
debounced: a burst of transactions across 40 venues collapses into one
recompute+broadcast per BROADCAST_MIN_INTERVAL_SECONDS, so query cost scales
with time, not with transaction volume or connected-client count. Because
every incoming transaction re-triggers this after the debounce window, the
dashboard is never more than ~BROADCAST_MIN_INTERVAL_SECONDS stale during
active trading - well within the "seconds, not minutes" requirement.
"""
import threading
import time

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

GROUP_NAME = "dashboard"

_lock = threading.Lock()
_last_sent_at = 0.0


def broadcast_snapshot_update():
    global _last_sent_at
    with _lock:
        now = time.monotonic()
        if (now - _last_sent_at) < settings.BROADCAST_MIN_INTERVAL_SECONDS:
            return
        _last_sent_at = now

    channel_layer = get_channel_layer()
    if channel_layer is None:
        return

    from .aggregation import build_dashboard_snapshot

    snapshot = build_dashboard_snapshot()
    async_to_sync(channel_layer.group_send)(
        GROUP_NAME, {"type": "dashboard.update", "snapshot": snapshot}
    )
