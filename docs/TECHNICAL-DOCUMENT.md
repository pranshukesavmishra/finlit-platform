# FinLit: Technical Document

Status: October 2026, pre-launch (staging). Live at https://finlit-arug.onrender.com

## 1. What it is
FinLit is an Indian retail-investor research platform: stock research reports with a FinLit score, screener (160+ filters), query builder, compare, charts, ETF and mutual-fund pages, watchlists, portfolio tracker, alerts, results and IPO calendars, FII/DII flows, market heatmap and sector view, commodities, option chain and DCF calculator, under three plans (Basic, Silver, Gold). Information only, not investment advice.

## 2. Architecture
One Docker container on Render (free plan, Singapore) runs everything:

| Part | Technology | Role |
|---|---|---|
| Research API | Python, FastAPI, uvicorn | Serves all `/api/*` endpoints and the built website |
| Website | React, TypeScript, Vite, TanStack Query | Single-page app, served by the API |
| Site backend | Python, FastAPI, MongoDB (Atlas M0) | Blog/CMS, forms, chat, portfolio uploads (`site-api/`) |
| Background jobs | Python worker CLI (`python -m finlit.worker`), shell scheduler (`deploy/scheduler.sh`) | Data loading, refreshes, alerts |
| Database | PostgreSQL on Neon (free) | Reports, scores, quotes, users, flows, funds |
| Cache | Redis (Render Key Value, free, ~25 MB) | Section cache, quotes, rate limits, queues |

Request flow: browser, API, Redis (hit) or Postgres (miss), JSON, gzip, ETag (304 on repeat visits).

## 3. Data sources
| Data | Source |
|---|---|
| Financials, ratios, peers, shareholding, company profile | FinEdge (licensed API) |
| Live prices, day change, charts (daily and intraday), option chain, index levels, MCX commodity prices, F&O lot sizes, surveillance flags, circuit limits, MTF | Dhan (DhanHQ v2) |
| FII/DII cash-market flows | NSE daily FII/DII report; NSDL FPI Monitor (history, FPI debt and hybrid) |
| Index constituents | NSE published index lists |
| Mutual fund NAV, expense ratio, fund size | AMFI |
| Macro | MoSPI, RBI |
| International commodity prices | Not live (needs a paid metals.dev or MetalpriceAPI key) |

Dhan has no fundamentals; those come only from FinEdge. Every source step is isolated: a failing source keeps the last good data and says so on the page.

## 4. Backend (`backend/finlit`)
- `api.py` app factory, middleware (security headers, CORS, rate limit, gzip), stock sections with ETag and plan gating.
- `worker.py` job CLI: `ingest`, `ingest-all`, `score-all`, `refresh-listing`, `refresh-indices`, `refresh-flows`, `refresh-etf`, `refresh-mf`, `refresh-instruments`, `rebuild-metrics`, `drain-queue`, and more.
- `finedge.py`, `dhan.py` provider clients (retries, pacing, token renewal by TOTP).
- `snapshot.py` + `normalize/` turn raw statements into the report sections and run data-quality checks (a report that fails critical checks is rejected and the last good one is kept).
- `screener/` metrics, the in-memory screener table (cached, loaded incrementally), the query language (`ql.py`, `qeval.py`, `qapi.py`) and baskets.
- `flows.py`, `etf.py`, `mf.py`, `indices.py`, `options.py`, `commodities.py`, `intraday.py`, `alertengine.py`, `dcf.py`, `premium.py`, `auth/` (sign-up, sign-in, MFA, plans).
- Migrations: `migrations/NNN_*.sql` (58 so far), run at start by `Store.migrate()`.

## 5. Frontend (`frontend/src`)
React pages under `pages/` (about 49), the company report under `stock/`, shared hooks in `lib/` (`api.ts`, `basis.ts`, `markets.ts`). The company page has a Consolidated / Standalone switch; all sections follow it. Unit tests with Vitest.

## 6. Data pipeline
1. First start: load calendars, company universe, price list for every listed company (about 5,800), index lists, the top companies in full (`INGEST_LIMIT`, 500), then scores for every other company (`score-all`, resumable, 1,500 a night).
2. Companies without a stored report are built on demand when first opened (queued, a few seconds).
3. Recurring: prices every minute for stored reports; listing prices after the close (15:50 IST) and nightly; flows after 18:00 IST; fund and macro data nightly.
4. Bulk jobs run at low CPU priority so visitors are served first.

## 7. Security
HTTPS with security headers, Argon2-style password hashing, MFA required for administrators, rate limits per client IP, plan checks on the server, CI scans (gitleaks secrets, bandit, pip-audit, npm audit). No secrets in the repository; they live in the Render environment.

## 8. Testing and delivery
Backend: pytest (about 1,100 tests, with Postgres and Redis). Frontend: type check and Vitest. GitHub Actions run all checks on every pull request; merging to `main` auto-deploys on Render.

## 9. Known limits (free tier)
- Small shared CPU: response times vary while data jobs run (about 0.4 s from a distance; the app itself answers in milliseconds).
- Neon free plan caps data transfer at 5 GB a month; the app caches heavily and reads only changed rows to stay inside it (`docs/NEON-EGRESS.md`).
- Redis is small (25 MB); the app tolerates it being emptied.
- Some companies have short statement history at the provider (for example LIC: 2 years).
- Showing MCX prices publicly needs written permission from Dhan/MCX; redistribution terms for FinEdge and Dhan data are still to be settled.

## 10. Environment
Key settings (set in Render, never in code): `DATABASE_URL`, `MONGO_URL`, `FINEDGE_API_KEY`, `DHAN_CLIENT_ID` with `DHAN_PIN` and `DHAN_TOTP_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `INGEST_LIMIT`, `SCORE_ALL_PER_RUN`. Optional: `RESEND_API_KEY` (email), `GEMINI_API_KEY` (AI chat), `METALS_DEV_API_KEY`.

More detail: `docs/` (launch guide, runbook, Dhan setup, flows, Neon egress).
