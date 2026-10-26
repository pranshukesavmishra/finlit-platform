# FinLit platform

**Website** (`frontend/`, React + TypeScript, navy and gold design) · **Research service** (`backend/`, fast stock reports)
· The company **site backend** (from Financial-Portfolio) lives in `site-api/`. Free launch steps: [`docs/LAUNCH-GUIDE.md`](docs/LAUNCH-GUIDE.md) (PDF: `docs/FinLit-Launch-Guide.pdf`); paid alternative: [`docs/LAUNCH-RUNBOOK.md`](docs/LAUNCH-RUNBOOK.md).

```bash
# develop the website against both backends
cd frontend && npm ci && npm run dev            # http://localhost:5173, proxies /api (see vite.config.ts)
python dev/site_api_dev.py --backend ../financial-portfolio/backend --port 8001   # site backend, in-memory Mongo (dev only)
# research service: see "Run locally" below, then:  node e2e/smoke.mjs http://127.0.0.1:5173
```

The rebuild of finlitventures.com. This first slice is the **data layer and speed**: stock research pages
that load in milliseconds instead of seconds, with the data bugs from the current site fixed at the source.

## Why the current stock page is slow, and what changed

| Current site (Financial-Portfolio) | This repo |
|---|---|
| Every page view resolves the symbol and Upstox key **before** checking the cache | API reads one Redis key; no lookups |
| 20–40 FinEdge calls **in sequence** on the request path, 18 s timeout each | Worker fetches all 21 endpoints **in parallel**, off the request path |
| In-memory cache per process, lost on restart | Postgres is the source of truth, Redis is the hot cache |
| One huge JSON; indicators recomputed in the browser | Small precomputed sections; summary is ~2 KB gzipped |
| 2,139 ms even on a cache hit | **~2.5 ms** p50 for the summary; all sections ~21 ms (local HTTP, see below) |

Benchmark (`scripts/bench.py`, local uvicorn with 2 workers, 300 requests per endpoint):

```
endpoint                              bytes(gz)   p50 ms   p95 ms   server ms
/api/stocks/RELIANCE                       2371     2.47     3.21     0.41
/api/stocks/RELIANCE/financials            2121     2.47     2.97     0.38
/api/stocks/RELIANCE/ratios                6076     2.87     3.90     0.42
/api/stocks/RELIANCE/price?range=1Y        4374     2.75     3.33     0.41
/api/stocks/RELIANCE/ownership              537     2.42     3.09     0.40
/api/stocks/RELIANCE/events                1104     2.34     3.45     0.37
/api/stocks/search-index                  89271     4.49     6.77     1.00
page data: summary 2.4 ms, all sections 20.6 ms
```

On the real VPS, add network round-trip time: about 20–40 ms from Indian cities to Bangalore or Mumbai.
Responses carry `ETag` and `Cache-Control: public, max-age=60, stale-while-revalidate=600`, so Cloudflare
and the browser serve repeat views without reaching the server.

## Data fixes (verified against real FinEdge payloads in `backend/tests/fixtures`)

- **Dividend return showed 89.14% at every horizon.** `DD-Mon-YYYY` dates were not parsed, and dividends were
  double counted. Now dates are parsed, duplicates removed, and split/bonus-adjusted amounts are used,
  inside the window only.
- **Dividend payout showed 81.42%.** It was computed as yield ÷ P/E. Now FinEdge's payout is used directly.
- **1Y return disagreed between panels** (−15.41% vs −16.2%). There is now one `trailing_returns` calculation.
- **Price chart dropped to ₹0.** Zero closes and isolated outliers more than 35% from their neighbours are
  removed, and each removal is listed in `dataQuality.removedBadTicks`.
- **Period dates such as `20260331` were read as Unix time** (FY71). They are now parsed as `YYYYMMDD`.
- **Segment names were duplicated** ("Oil & Gas" and "Oil and Gas"). They are now merged.
- **Score moved to the server** (model `v1`, identical thresholds and bands to the current site), so every
  user sees the same number. The score is versioned, so a Gold "advanced" model can ship beside it.

## Security and data quality

- **Plan and research:** [`docs/platform-plan.md`](docs/platform-plan.md) covers security layers,
  data quality, UI, scaling and the login design, with sources.
- **Server hardening steps:** [`deploy/README.md`](deploy/README.md).
- **In the code today:**
  - strict security headers;
  - per-client rate limits;
  - trusted hosts;
  - a production safety switch;
  - a read-only database role for the API;
  - hardened containers;
  - pip-audit, bandit and gitleaks in CI;
  - a 23-check data quality gate that refuses to publish broken numbers.

## Layout

```
backend/
  finlit/
    normalize/   FinEdge payload -> clean tables (₹ crore, %, ISO dates), glossary of every metric
    analytics/   indicators (EMA, RSI), returns, derived metrics, score v1, plain-English notes
    quality.py   23 publish-time checks (accounting identities, units, freshness, ranges)
    security.py  response headers, client IP resolution, Redis rate limiter
    snapshot.py  raw bundle -> sections: summary, financials, ratios, price ranges, ownership, events, segments, peers
    finedge.py   async client: parallel fetch, retries on 429/5xx, consolidated -> standalone fallback, fixture mode
    store.py     Postgres (snapshots, scores, price_daily, companies, runs, queue) + Redis section cache
    worker.py    CLI: migrate | refresh-universe | ingest | refresh-stale | refresh-quotes | drain-queue
    api.py       read-only FastAPI app
  tests/         unit tests + end-to-end tests (worker -> Postgres/Redis -> API)
  scripts/bench.py
design/          tokens.json (IBM Carbon based) -> dist/tokens.css (web) + dist/tokens.ts (React Native app)
deploy/          crontab (IST) and server hardening guide
```

## API

| Route | Notes |
|---|---|
| `GET /api/stocks/{symbol}` | Summary: profile, quote, 52-week range, sparkline, score, thesis, strengths and watch-outs, key metrics, returns, data quality |
| `GET /api/stocks/{symbol}/{section}` | `financials`, `ratios`, `ownership`, `events`, `segments`, `peers` |
| `GET /api/stocks/{symbol}/price?range=1M\|6M\|1Y\|3Y\|5Y\|MAX` | Daily OHLCV up to 1Y; weekly closes for longer ranges |
| `GET /api/stocks/search-index` | Every listed stock, for instant search in the browser (pre-gzipped, ~89 KB) |
| `GET /api/screener/top?limit=50` | Highest-scored stocks |
| `GET /api/health` | Postgres and Redis status |

All stock routes take `?statement=consolidated|standalone` (default `consolidated`). A known stock with no
snapshot yet returns `202 {"status":"queued"}` with `Retry-After: 3`; the worker builds it within a few seconds (FinEdge latency decides; the build itself takes ~10 ms).

## Run locally

```bash
cp .env.example .env            # add FINEDGE_API_KEY, or set FINEDGE_MODE=fixtures to work offline
docker compose up -d --build
docker compose run --rm worker refresh-universe
docker compose run --rm worker ingest RELIANCE TCS HDFCBANK
curl localhost:8000/api/stocks/RELIANCE
```

Without Docker:

```bash
cd backend
python -m venv .venv && . .venv/bin/activate && pip install -r requirements-dev.txt
export FINEDGE_MODE=fixtures DATABASE_URL=postgresql://finlit:finlit@localhost:5432/finlit REDIS_URL=redis://localhost:6379/0
python -m finlit.worker migrate && python -m finlit.worker refresh-universe && python -m finlit.worker ingest RELIANCE
uvicorn finlit.api:create_app --factory --port 8000
python -m pytest -q             # integration tests use finlit_test DB and Redis db 15; skipped if unreachable
```

## Deploying (Stage 1)

- **VPS:** one server (DigitalOcean Bangalore 4 GB, or Oracle Always Free in Mumbai/Hyderabad) runs
  `docker compose up -d`, with Caddy or Nginx in front for TLS.
- **Cloudflare:** proxy `api.finlitventures.com` through Cloudflare, with a cache rule for
  `/api/stocks/*` that respects origin headers.
- **Cron:** install `deploy/crontab` in `/etc/cron.d/finlit`:
  - live quotes every minute in market hours;
  - fundamentals nightly;
  - the stock list weekly.
- **Frontend:** Cloudflare Pages. **Files:** Cloudflare R2.

### Render (one free container) and FinLit Prism

`render.yaml` + `Dockerfile` run the website, the research API, the site backend (`site-api/backend`, own venv `/opt/site-venv`, 127.0.0.1:8001)
and the jobs in one 512 MB service; `deploy/render-start.sh` is the entrypoint. FinLit Prism (the Gold plan's financial-health rating) lives in the
site backend. Full guide, with the checklist to switch it on: [`docs/prism/DEPLOY.md`](docs/prism/DEPLOY.md).

| Variable | Needed for Prism | If missing |
| --- | --- | --- |
| `FINEDGE_API_KEY` | yes | reports fail with 503 "FinEdge API is not configured" |
| `CMS_JWT_SECRET` (32+ chars, same in the research API and the site backend; generated by `render.yaml`) | yes | Prism reports "not connected"; the site backend refuses its tokens |
| `DATABASE_URL`, `REDIS_URL` | yes (already required) | stored reports / PDF snapshots unavailable |
| `MONGO_URL`, `DB_NAME` | no | the site backend starts anyway when `FINEDGE_API_KEY` + `CMS_JWT_SECRET` are set; blog/CMS, uploads and forms answer 503 |
| `UPSTOX_ACCESS_TOKEN` | optional | no second-source recovery of missing statement years |
| `PREMIUM_GENERATION_SLOTS` (1 on the free plan, default 2), `STOCK_FUNDAMENTALS_CACHE_ENTRIES` (32) | tuning | defaults |
| `SITE_API_START` (`auto`, `never`, `always`) | tuning | `auto` |

Measured (recorded data, no network wait): site backend about 87 MB idle, about 100 MB peak with four reports and PDFs at once.
Locally, `dev/run_stack.sh` runs Prism on recorded FinEdge answers for eight companies without any provider key.

## Next phases

1. `/stocks/:symbol` page (React, the approved stock.html design) wired to these sections, with the
   summary painted first, prefetch on search hover, and instant client-side search.
2. Accounts and plans: email OTP plus Google sign-in, Razorpay, Basic/Silver/Gold gating enforced on
   the server.
3. Gold features: advanced model, quarterly ratios, technical score, buckets, segments, triggers.
4. Tools: screener, watchlist, PDF/CSV export, alerts.
5. The rest of the site, and moving blog and contacts from MongoDB to Postgres.
