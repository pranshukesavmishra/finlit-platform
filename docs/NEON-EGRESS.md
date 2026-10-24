# Neon network transfer (egress)

Neon's free plan allows **5 GB a month of public network transfer**: every byte the database sends to the app, counted per project. At 100% Neon
refuses queries, so sign-in, accounts, baskets and the rest stop. Writes into the database are free; only what Postgres **returns** counts. Redis
(Render's private network) and the FinEdge/Dhan calls are not counted.

So the rule for this codebase is: **never read a table on a timer; probe, then fetch only what changed, and keep the rest in Redis.**

## What reads what, and how often

Sizes are estimates from the code (nothing could be measured from the repository): a stored score row with its `metrics` is about 5 KB (about 5,800
companies, so the whole table is about 30 MB); about 600 companies hold a full report (about 100 KB across its sections, price history included) and
get a live quote every minute in market hours. Check the real numbers with `/api/admin/db-usage` (below).

| Reader | When | Per run before | Per run after | How |
|---|---|---|---|---|
| Screener table (`screener/data.py`; screener, query builder, compare, results, advanced charts) | any request after the gap | ~30 MB every 10 min | probe ~200 B; changed rows only (~3 MB in market hours, 5 KB per changed company) | rows cached compressed in Redis; see below |
| Quote job `refresh_metrics_for` (every minute, 09:00-15:59 IST) | 420 runs a day | every touched company's sections from Postgres: 5-60 MB | 0 in steady state | inputs kept in Redis (`mi:*`), summary from Redis |
| `security_map` (same job) | every minute | join over `companies` x `dhan_instruments`, ~20 KB | 0 | Redis `dhan:secmap`, dropped by `dhan:instruments:ver` |
| `snapshot_symbols` (same job) | every minute | ~15 KB | 0 (once per 30 min) | Redis `quotes:symbols` |
| Results page (`results.py`) | while the page is used | feed 3 MB every 2 min plus a quarter ~1 MB every 3 min | feed read only when it changed; a quarter at most every 30 min in market hours, and not at all outside them unless a probe says something moved | Redis `results:decl`, probe |
| `refresh-results` (hourly, worker) | 16 a day | the same 3 MB feed read | Redis copy | shares `results:decl` |
| Search box prices (`search.py`) | while used, every 2 min | 0.5 MB per level | changed companies only (~40 KB) | Redis `search-quotes:raw` |
| Name list (`store.search_index`) | every hour, and after every chunk of a bulk load | ~350 KB | every 6 hours, and once at the end of a bulk load | longer TTL, one drop per load |
| Saved-screen emails (`screens.py`, 07:30 weekdays) | daily | the whole score table, ~30 MB | only the figures the members' screens use, ~1.5 MB | cut inside the query |
| Alerts, statement figures (`alertengine.py`, 19:30) | daily | whole `financials`/`ownership` reports, ~40 KB a watched company | ~1 KB a company | `jsonb` cut inside the query |
| Profit-and-loss flags (`plalerts.py`, 19:30) | daily | whole `financials` reports | the two P&L tables | same |
| Alerts, live (`check-alerts --kind live`, every 10 min) | 42 a day | scores of alerted symbols, bytes | unchanged | already small |
| Technical alerts (`price_daily`, 420 days per alerted symbol) | daily | ~17 KB a symbol | unchanged | once a day, only for symbols with such an alert |
| MF and ETF nightly jobs, `store.prune`, `drain_queue` | nightly / 6-hourly | small; ETF reads are Redis-first, the queue is gated by a Redis flag | unchanged | not measured: watch them in `db-usage` |
| Every worker command start (`Store.connect(migrate=True)`) | each job, including each minute's quote job | ~1 KB (`schema_migrations`) | unchanged | negligible (about 8 MB a month) |

### The screener table in detail

* `scores.changed_at` (migration 057) is stamped by every writer (report scoring, `refresh_metrics_for`, `rebuild_metrics`). `updated_at` is **not**
  moved by the live-quote job and is what the nightly rescoring reads as "how old is this score", so it could not be used.
* **Probe**: `count(*)` and `max(changed_at)` of `scores` (model v1), and `count(*)`/`max(updated_at)` of `listing_quotes`. Nothing changed: no rows move.
* **Delta**: symbols whose `changed_at` is newer than the last probe (minus 2 minutes of overlap) are picked first, then `DISTINCT ON (symbol)` is run
  again for **all** the rows of those symbols, so a changed standalone row never beats an unchanged consolidated one.
* **Reconcile** (every 6 hours, or at once when the row count fell and nothing was written, which is a prune): the list of symbols (pruned
  companies go, new ones are read), the unscored companies, listing figures, index members and score history.
* **Full read** (every 7 days, or when Redis has nothing, or the database looks like another one): everything from Postgres, about 30 MB.
* The compressed rows (about 5-8 MB) live in Redis under `screener:rows:<db tag>` and in the web process; a restart reads them from Redis. If Redis is
  missing or evicts the key, the next check reads Postgres (one full read). The key carries a tag of the database host, so a new Neon project never
  reuses the old project's rows.
* The Table is built from the rows exactly as before (`Table.__init__` is untouched).

### Cadence and freshness, as chosen

| | Market hours (weekdays 09:00-15:59 IST) | Otherwise |
|---|---|---|
| Screener / compare / advanced charts: how old a price can be | **up to 30 minutes** (`MARKET_GAP`) | a probe every 10 minutes (`OFF_GAP`); fetches only if a nightly job changed something |
| Results page: how old a quarter's rows can be | up to 30 minutes (`MARKET_TTL`) | unchanged until a probe says otherwise |
| Search box prices | 2 minutes (as before) | as before |
| Live quote job | every minute (as before) | not running |

Everything else users see is the same data. The one visible trade-off is the 30-minute age of prices on the screener, compare, results and advanced
charts (the stock page itself and the search box still update every minute / 2 minutes). Edit `MARKET_GAP` in `screener/data.py` (and `MARKET_TTL` in
`results.py`) to move it; 60 minutes halves the largest remaining item.

## Reading `pg_stat_statements`

Migration 056 runs `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` and never fails if it cannot. As an administrator (with the authenticator code),
open `GET /api/admin/db-usage`. It returns the 15 statements that returned the most rows since the statistics were last reset, each with the query
text (trimmed), `calls`, total `rows` and `rowsPerCall`, or `{"enabled": false, "message": ...}` if the extension is not there (then run
`CREATE EXTENSION pg_stat_statements;` once in Neon's SQL editor).

How to read it: Postgres does not count bytes per statement, so multiply rows by the rough row size (a screener row is ~5 KB, most others
under 200 bytes). A statement with a large `rows` total is where the bytes are. Statistics may reset when the Neon compute restarts (it suspends
after 5 idle minutes; the always-on keep-alive normally prevents that), so look at it daily and compare.

## Budget alarm (do this weekly, it takes a minute)

Neon console > the project > the **Usage** (or **Billing**) page, **Public network transfer** (the labels move now and then): the month so far against 5 GB. Rule of thumb for the
month, day by day: 15% by day 5, 50% by day 15, 80% by day 24. If it is ahead of that, open `/api/admin/db-usage`, find the statement with the
largest `rows`, and fix that first. At 80% before the month's last week: raise `MARKET_GAP` to 3600.

## Switching to a fresh free project

1. Neon console: create a new project (same region as Render, Singapore), copy its **direct** connection string (not the `-pooler` host).
2. Render > the `finlit` service > Environment: set `DATABASE_URL` to the new string, save. The service redeploys.
3. On start `deploy/render-start.sh` runs `python -m finlit.worker migrate` (all migrations, including 056 and 057), then the boot load fills the
   empty database again (universe, listing, index lists, the biggest companies, scores, funds). The first hours are slow and the screener shows
   only listing figures until reports are loaded; users and saved data of the old project are **not** copied (export them from the old project
   with `scripts/backup.sh` before it is deleted, if they matter).
4. Redis can stay as it is: its cached rows are keyed by the old database's host and are ignored.
5. Open `/api/admin/db-usage` after a day to confirm the new project's pattern.
