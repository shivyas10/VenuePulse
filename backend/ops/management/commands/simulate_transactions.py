"""Simulates 40 POS terminals streaming transactions into the system.

Why an HTTP-posting simulator rather than seeding the DB directly: it
exercises the real write path (validation -> idempotent create -> commit ->
broadcast) exactly the way an actual POS integration would, which is the
thing worth demonstrating in this exercise. Two phases:

1. Backfill - posts today's trade-so-far (midnight -> now) at a realistic
   per-venue pace, so the dashboard isn't empty and the hourly trade chart
   has real shape the moment you open it. Two venues are deliberately
   scripted into the last hour of that backfill (one quiet, one
   void/refund-heavy) so both anomaly flags are visible immediately rather
   than depending on random luck.
2. Live - keeps streaming new transactions in real time afterwards, so the
   "updates within seconds, no refresh" requirement is actually observable.
"""
import random
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

MENU = {
    "pub": [
        ("beer-pint", "Pint of Lager", 8.5),
        ("beer-craft", "Craft Beer", 11.0),
        ("wine-glass", "House Wine", 9.5),
        ("burger", "Pub Burger", 19.0),
        ("fries", "Basket of Fries", 7.5),
        ("wings", "Chicken Wings", 14.0),
        ("parma", "Chicken Parma", 22.0),
    ],
    "restaurant": [
        ("wine-bottle", "Bottle of Wine", 45.0),
        ("wine-glass", "Glass of Wine", 12.0),
        ("steak", "Grilled Steak", 38.0),
        ("pasta", "Pasta of the Day", 26.0),
        ("salad", "Seasonal Salad", 18.0),
        ("dessert", "Dessert", 14.0),
        ("coffee", "Coffee", 5.0),
    ],
    "function_space": [
        ("canape", "Canape Selection", 6.0),
        ("beverage-pkg", "Beverage Package (per head)", 55.0),
        ("venue-hire", "Venue Hire Fee", 800.0),
        ("catering-pkg", "Catering Package (per head)", 65.0),
    ],
}


def _build_items(kind, n_lines):
    catalogue = MENU[kind]
    lines = []
    for _ in range(n_lines):
        item_id, name, price = random.choice(catalogue)
        qty = random.randint(1, 3)
        lines.append({"item_id": item_id, "name": name, "qty": qty, "price": price})
    return lines


def _make_transaction(venue, tx_type, ts):
    n_lines = random.randint(1, 4)
    items = _build_items(venue["kind"], n_lines)
    total = round(sum(item["price"] * item["qty"] for item in items), 2)
    return {
        "venue_id": venue["id"],
        "transaction_id": str(uuid.uuid4()),
        "timestamp": ts.isoformat(),
        "type": tx_type,
        "items": items,
        "total": total,
        "staff_id": f"staff-{random.randint(1, 12)}",
    }


class Command(BaseCommand):
    help = "Simulates POS terminals across all venues posting transactions to the ingest API."

    def add_arguments(self, parser):
        parser.add_argument("--base-url", default="http://localhost:8000")
        parser.add_argument("--token", default=settings.POS_INGEST_TOKEN)
        parser.add_argument("--tick-seconds", type=float, default=2.0)
        parser.add_argument("--no-backfill", action="store_true")
        parser.add_argument("--no-live", action="store_true", help="Backfill only, then exit.")
        parser.add_argument(
            "--backfill-hours",
            type=float,
            default=3.0,
            help="How far back (from now, capped at today's midnight) to backfill history for.",
        )
        parser.add_argument(
            "--concurrency",
            type=int,
            default=8,
            help="Concurrent backfill posting workers. SQLite serializes writes, so keep this "
            "modest for local/native runs; Postgres (docker-compose) handles more.",
        )

    def handle(self, *args, **options):
        from ops.models import Venue

        venues = list(Venue.objects.all().values("id", "name", "kind"))
        if not venues:
            self.stderr.write("No venues found - run `manage.py loaddata venues` first.")
            return

        self.base_url = options["base_url"].rstrip("/")
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {options['token']}"
        self._wait_for_backend()

        if not options["no_backfill"]:
            self._backfill(venues, options["backfill_hours"], options["concurrency"])

        if not options["no_live"]:
            self._run_live(venues, options["tick_seconds"])

    def _wait_for_backend(self, retries=30, delay=2.0):
        """The simulator and backend start concurrently under
        docker-compose; poll the health endpoint rather than racing it."""
        for attempt in range(retries):
            try:
                resp = requests.get(f"{self.base_url}/api/health/", timeout=3)
                if resp.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(delay)
        self.stderr.write("Backend never became healthy - continuing anyway.")

    # -- backfill --------------------------------------------------------
    def _backfill(self, venues, backfill_hours, concurrency):
        now = timezone.localtime()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = max(midnight, now - timedelta(hours=backfill_hours))
        if now <= start:
            return

        drop_venue, spike_venue = (venues[0], venues[1]) if len(venues) > 1 else (venues[0], None)
        self.stdout.write(
            f"Backfilling {start.strftime('%H:%M')} -> {now.strftime('%H:%M')} for {len(venues)} venues..."
        )
        self.stdout.write(
            f"  Scripted sales-drop venue: {drop_venue['name']} (id={drop_venue['id']})"
        )
        if spike_venue:
            self.stdout.write(
                f"  Scripted void/refund-spike venue: {spike_venue['name']} (id={spike_venue['id']})"
            )

        payloads = []
        for venue in venues:
            payloads.extend(self._build_venue_backfill(venue, start, now, drop_venue, spike_venue))

        self.stdout.write(f"Posting {len(payloads)} backfilled transactions...")
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            list(pool.map(self._post, payloads))
        self.stdout.write(self.style.SUCCESS(f"Backfill complete: {len(payloads)} transactions posted."))

    def _build_venue_backfill(self, venue, start, now, drop_venue, spike_venue):
        """Pure generation of this venue's backfilled transactions (no I/O),
        so posting can be parallelized separately from data shaping."""
        payloads = []
        t = start
        last_hour_start = now - timedelta(minutes=60)
        is_drop_venue = venue["id"] == drop_venue["id"]
        is_spike_venue = spike_venue is not None and venue["id"] == spike_venue["id"]

        while t < now:
            in_last_hour = t >= last_hour_start

            # Scripted sales-drop venue: healthy trade rate until the final
            # hour, then goes almost quiet.
            if is_drop_venue and in_last_hour:
                gap_minutes = random.uniform(20, 30)
            else:
                gap_minutes = random.uniform(3, 9)
            t = t + timedelta(minutes=gap_minutes)
            if t >= now:
                break

            payloads.append(_make_transaction(venue, "sale", t))

            # Scripted void/refund-spike venue: elevated void/refund rate
            # in the final hour only.
            if is_spike_venue and in_last_hour and random.random() < 0.45:
                vr_type = random.choice(["void", "refund"])
                payloads.append(_make_transaction(venue, vr_type, t))
            elif random.random() < 0.04:
                vr_type = random.choice(["void", "refund"])
                payloads.append(_make_transaction(venue, vr_type, t))

        return payloads

    def _post(self, payload):
        try:
            resp = self.session.post(f"{self.base_url}/api/transactions/", json=payload, timeout=10)
            if resp.status_code not in (200, 201):
                self.stderr.write(f"Unexpected status {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as exc:
            self.stderr.write(f"Request failed: {exc}")

    # -- live streaming ----------------------------------------------------
    def _run_live(self, venues, tick_seconds):
        self.stdout.write(self.style.SUCCESS("Streaming live transactions - Ctrl+C to stop."))
        try:
            while True:
                now = timezone.localtime()
                for venue in venues:
                    if random.random() < 0.15:
                        self._post(_make_transaction(venue, "sale", now))
                    elif random.random() < 0.01:
                        vr_type = random.choice(["void", "refund"])
                        self._post(_make_transaction(venue, vr_type, now))
                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            self.stdout.write("\nStopped.")
