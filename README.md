# Ops Dashboard

A real-time dashboard for a 40-venue hospitality group's operations team: total sales by venue, top-selling items, drop/spike anomaly flags, and a per-venue drill-down — updating within seconds as POS transactions stream in, no page refresh.

Built with Django (DRF + Channels) and React (TypeScript + Vite).

## Contents

- [Running it](#running-it)
- [Architecture](#architecture)
- [Key decisions & trade-offs](#key-decisions--trade-offs)
- [Assumptions](#assumptions)
- [Anomaly detection](#anomaly-detection)
- [What I'd do differently / improve with more time](#what-id-do-differently--improve-with-more-time)

## Running it

### Option A: Docker Compose (recommended, one command)

**Setup + start:**
```bash
docker compose up --build -d
```
This builds and starts Postgres, Redis, the Django/Channels backend (migrates, seeds 40 venues, creates a default login), a transaction simulator, and the React dev server. `-d` runs it detached; drop it to watch logs stream instead.

**Check status / logs:**
```bash
docker compose ps
docker compose logs -f            # all services
docker compose logs -f backend    # just one (backend/frontend/db/redis/simulator)
```

**Stop:**
```bash
docker compose down
```
Containers are removed but the Postgres data volume persists across restarts. Add `-v` (`docker compose down -v`) to also wipe the database for a clean slate next time.

**Once running:**
- Dashboard: http://localhost:5173
- Django admin: http://localhost:8000/admin/
- API: http://localhost:8000
- Login (both): `ops_admin` / `ops-admin-pass123` (override via `OPS_ADMIN_USERNAME` / `OPS_ADMIN_PASSWORD`)

### Option B: Native (no Docker)

The app also runs with zero external services — SQLite by default, and Django Channels' in-memory layer instead of Redis. This is how it was actually developed in this environment before Docker was available, and it's still a fine way to run it without installing Docker at all.

**One-time setup:**
```bash
cd backend
python -m venv venv
./venv/Scripts/activate        # Windows; `source venv/bin/activate` on macOS/Linux
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py loaddata venues
python manage.py ensure_admin   # creates ops_admin / ops-admin-pass123
```

**Start (3 separate terminals, each from the repo root):**
```bash
# Terminal 1 - backend
cd backend && ./venv/Scripts/activate
python -m daphne -b 127.0.0.1 -p 8000 config.asgi:application

# Terminal 2 - simulator (backfills history, then streams live transactions)
cd backend && ./venv/Scripts/activate
python manage.py simulate_transactions

# Terminal 3 - frontend
cd frontend
npm install     # first time only
npm run dev
```

**Stop:** `Ctrl+C` in each terminal.

**Once running:**
- Dashboard: http://localhost:5173
- Django admin: http://localhost:8000/admin/
- Login (both): `ops_admin` / `ops-admin-pass123`

**Reset local data** (wipe and reseed SQLite):
```bash
cd backend
rm db.sqlite3
python manage.py migrate
python manage.py loaddata venues
python manage.py ensure_admin
```

### Running tests

```bash
cd backend
python manage.py test ops
```

## Architecture

```
POS terminals --HTTP POST--> Django (DRF)  --on commit--> debounced broadcast
                                  |                              |
                            Postgres/SQLite               Channels group_send
                                  |                              |
                        REST read endpoints              WebSocket consumer
                         (initial page load)               (all open dashboards)
                                  \                              /
                                   \                            /
                                    ---> React dashboard (single view) <---
```

- **Write path**: POS terminals `POST /api/transactions/` with a shared bearer token. The view validates, writes `Transaction` + `TransactionItem` rows in one atomic block, and on commit triggers a debounced broadcast.
- **Read path (initial load)**: `GET /api/dashboard/` and `GET /api/venues/<id>/detail/` — plain aggregate SQL (`SUM`/`GROUP BY`), computed fresh per request. At 40 venues and realistic volume this is milliseconds; see [below](#why-no-rollup-table) for when that stops being true.
- **Read path (live updates)**: one WebSocket per dashboard session (`/ws/dashboard/`). A single recompute is broadcast to every connected session — the query cost doesn't scale with the number of ops users watching.
- **Venue drill-down**: fetched via REST when the modal opens (fast, no separate socket). While the modal stays open, it's invalidated and refetched on the same tick as the main dashboard broadcast, reusing the existing "something changed" signal instead of opening a second channel per open modal.

## Key decisions & trade-offs

**Django Channels (WebSockets) over SSE or polling.** The brief requires updates "within seconds, no refresh" for sessions open "for hours." Channels is the idiomatic Django answer and keeps the connection two-way if the dashboard ever needs to push commands back (e.g. "acknowledge this alert"). SSE would have been simpler to wire up (no channel layer), and I considered it — but Channels is the better long-term fit and isn't meaningfully harder given DRF is already in play.

**Postgres in Docker, SQLite natively.** The DB is chosen entirely by `DATABASE_URL` (via `dj-database-url`) — same code, no branching. Postgres is the intended target: proper concurrent-write handling, real `GROUP BY`/`SUM` performance at scale, and it's what the docker-compose stack runs. SQLite was the pragmatic fallback for iterating in an environment where Docker/WSL2 couldn't be installed non-interactively — it's genuinely fine for this dataset size, but its single-writer lock is visible under concurrent load (see the simulator's `--concurrency` flag, which defaults conservatively for exactly this reason).

**In-memory channel layer locally, Redis via `REDIS_URL`.** Same pattern as the DB: `channels.layers.InMemoryChannelLayer` works correctly for a single `daphne` process (which is what "runs locally" means here), but doesn't fan out across multiple worker processes — that's what `REDIS_URL` is for, and docker-compose sets it.

**Debounced broadcast, not per-transaction.** Every ingested transaction calls `broadcast_snapshot_update()`, but it's rate-limited to at most once per `BROADCAST_MIN_INTERVAL_SECONDS` (default 1s). A burst across 40 venues collapses into one recompute+broadcast, and because trading is continuous, the next transaction re-triggers it anyway — so the dashboard is never more than ~1s stale during active trading, and query cost doesn't scale with transaction volume.

**Separate auth for POS ingestion vs. the dashboard.** POS terminals aren't logged-in users, so `POST /api/transactions/` uses a shared bearer token (`POS_INGEST_TOKEN`), while the dashboard uses Django session auth with CSRF. Mixing these (e.g. making POS terminals log in) would be the wrong shape of trust boundary.

**Idempotent ingestion.** `(venue, transaction_id)` has a DB unique constraint. A POS retrying a delivery after a dropped response re-sends the same payload, and that must not double-count a sale — the view treats a duplicate as a 200, not an error, and relies on the DB constraint (not a check-then-insert) to be race-safe under concurrent writes.

**No pre-aggregated rollup tables.** <a id="why-no-rollup-table"></a> Aggregates are computed on demand from the raw `Transaction`/`TransactionItem` tables, with indexes on `(venue, timestamp)` and `(timestamp, type)`. At 40 venues this is trivially fast and always correct — a rollup table would add write-path complexity (keeping it in sync) that isn't justified yet. The threshold where that flips is roughly: once a single dashboard recompute takes long enough to threaten the "seconds" freshness budget (hundreds of venues, or years of retained history), that's when I'd introduce an incrementally-maintained rollup table and change the read path to hit it instead.

**Normalized items, not JSON.** `TransactionItem` is its own table rather than a JSON blob on `Transaction`, specifically so "top selling items" is a real `GROUP BY`/`SUM` rather than app-level aggregation across deserialized blobs.

**Simulator posts over HTTP, not direct DB writes.** It exercises the exact write path a real POS integration would hit (validation, idempotency, auth, broadcast) rather than seeding data behind the system's back. It runs in two phases: a **backfill** (last 3 hours by default, capped at midnight) so the dashboard and hourly chart aren't empty on first load, followed by **live streaming** so the "real-time, no refresh" behavior is actually observable. Two venues are deliberately scripted during backfill — one into a quiet spell, one into a void/refund-heavy spell — so both anomaly flags are visible immediately rather than depending on random luck.

## Assumptions

- **Single group-wide timezone.** All 40 venues are treated as one timezone (`DJANGO_TIME_ZONE`, default UTC) for "today" and "last hour." A real multi-region rollout would store each venue's own timezone and compute "today" per-venue.
- **"Total sales" = gross `sale`-type transactions.** Voids and refunds are tracked and surfaced (for the anomaly flag and the drill-down), but not netted against the sales total — the brief's wording ("total sales... a ranked list") reads as gross revenue, with voids/refunds treated as their own signal rather than folded into the same number.
- **"Top selling" ranks by units sold**, not revenue — matches how "top selling items" is usually meant in hospitality ops conversation, though revenue is easy to add as a second sort if that's what's actually wanted.
- **POS venues are pre-provisioned**, not self-registering — 40 venues are seeded via fixture, matching "operates 40 venues" as a fixed, known set rather than something that grows at runtime.

## Anomaly detection

Two fixed-threshold rules (tunable via Django settings / env vars), not per-venue historical baselines:

- **Sales drop**: last 60 minutes vs. the preceding 60 minutes, flagged if down ≥40%, and only if the prior window had at least $50 of trade (so a venue going from $2 to $0 doesn't falsely read as a crisis).
- **Void/refund spike**: (voids + refunds) / total transactions in the last 60 minutes ≥20%, and only once there are at least 5 transactions in the window (so one void out of one transaction doesn't trip it).

This is a deliberate simplification. A fresh dataset has no multi-day history, so a proper baseline ("this venue's trailing 7-day average for this time of day") isn't buildable yet — and it's genuinely the better long-term answer, since fixed thresholds will both miss slow-building issues and occasionally false-positive on small-sample venues (visible in the demo data — a few venues flag `sales_drop` just from random variance in a 3-hour backfill window). I'd rather ship the honest, simple version and say so than fake a baseline against data that can't support one.

## What I'd do differently / improve with more time

- **Per-venue historical baselines** for anomaly detection instead of fixed thresholds, once there's enough retained history to compute them.
- **Rollup/materialized aggregate tables** if venue count or retention grew enough that on-demand aggregation stopped being "milliseconds" — see the trade-off note above.
- **Per-venue timezones** instead of one group-wide clock.
- **Reconnect/backfill gap handling** on the frontend socket: right now a reconnect gets a fresh snapshot (correct), but a dropped connection during the gap isn't visually distinguished from "no news is good news" — a small "reconnecting..." indicator would close that gap.
- **More frontend tests** — the backend has unit coverage on the aggregation/anomaly/ingestion logic (the parts with real branching), but the frontend was verified manually (see below) rather than with component tests, given the take-home's explicit steer toward "some tests on important logic, not coverage for its own sake."
- **Structured logging / metrics** on the ingestion and broadcast paths — useful in production, not needed to demonstrate the mechanism here.

## Verification performed

- Backend: 22 unit tests covering aggregation queries, both anomaly rules (including the boundary/threshold edge cases), ingestion validation, idempotency, and auth enforcement (`python manage.py test ops`).
- Manual end-to-end: ran the full native stack (Daphne + simulator + Vite dev server) and drove it with a scripted Playwright browser session — logged in, confirmed all 40 venues render ranked with correct anomaly badges, opened the drill-down modal and confirmed the hourly chart and per-venue item list render, and confirmed a posted transaction arrives on an already-open dashboard via the WebSocket without a refresh.
- Docker Compose path verified end-to-end: `docker compose up --build` brings up Postgres, Redis, backend, frontend, and the simulator; confirmed login, all 40 ranked venues, correct anomaly flags, and the Django admin's static assets all work against the containerized stack.
