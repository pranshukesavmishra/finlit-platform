# Accounts, plans and personalisation

How sign-in, plans and the member's own settings work in the real site. Everything below is built and covered by tests
(`backend/tests/test_auth*.py`, `frontend/e2e/accounts.mjs`).

## Sign-in design (stage 1: our own FastAPI accounts, swappable later)
- Email + password. Passwords are hashed with argon2id (at most 4 hashes run at once so a flood of logins cannot exhaust the server).
- A session is a random token in an `HttpOnly`, `SameSite=Lax`, `Secure` cookie (`__Host-fl_session` in production). Only its SHA-256 hash is stored.
- State-changing requests need the session's CSRF token (`X-CSRF-Token`) **and** an allowed `Origin`.
- Wrong email and wrong password give the same answer and take the same time. 8 wrong passwords lock the account for 15 minutes. Per-IP and per-email rate limits apply to sign-up, sign-in, reset and resend.
- Email confirmation and password reset use single-use hashed links (24 h / 1 h). Resetting or changing a password signs out every other device.
- Two-step sign-in (authenticator app, RFC 6238). The secret is encrypted at rest (`SECRET_KEY`). **Administrators must use it**; admin tools stay closed until the session has passed the code.
- Members can see and end their sessions, change password, switch two-step on/off, and delete the account.
- A managed provider (the earlier "managed login" decision) can replace this later: the website only talks to `/api/auth/*`, `/api/me/*`.

## Plans are enforced on the server
The middle plan was called Bronze until migration `007_plan_silver.sql`; existing Bronze members became Silver. (The "Copper" palette keeps its stored id `bronze`.)
Promised but not built yet, shown as "Soon" / "Later" on the plans page: IPO data and portfolio import (Silver), advanced model score (Gold), equity research report (Gold, later).
| What | Basic / visitor | Bronze | Gold |
|---|---|---|---|
| FinLit score, pillar scores, thesis, strengths, watch-outs | removed | yes | yes |
| Ratio history | 5 key ratios | 5 key ratios | all, plus valuation history |
| Detailed ratio groups, segments, EMA200/RSI, price statistics | removed | statistics yes | all |
| Watchlist | none | 3 lists, 30 stocks | 50 lists, 1,000 stocks |
| Saved screens | 3 | 20 | 100 |
| Companies to compare | 2 | 2 | 4 |

`SHOWCASE_SYMBOLS` (default `RELIANCE`) are shown in full to everyone as the free example. Plan-dependent responses are `Cache-Control: private, no-cache`
with `Vary: Cookie` and a plan-specific ETag, so a shared cache can never hand a Gold response to someone else and a new plan shows at once.
Prices are "Soon": there are no payments yet. A member asks for a plan on `/account/plan`; an administrator grants it in `/console` (1 year, any length by API).

## Create the first administrator
```bash
cd backend && FINLIT_ADMIN_PASSWORD='a long passphrase' python -m finlit.auth.cli create-admin --email you@company.com
# lost authenticator:  python -m finlit.auth.cli reset-mfa --email you@company.com
```
First sign-in sends the administrator to *Account → Security* to add the authenticator app. Then `/console` (members, plan requests, audit log) opens.

## Production settings (checked at start-up; the API refuses to run if unsafe)
`SECRET_KEY` (32+ random chars), `MAIL_MODE=resend` + `RESEND_API_KEY` + `MAIL_FROM`, `PUBLIC_SITE_URL=https://finlitventures.com`, `CORS_ORIGINS`, `ALLOWED_HOSTS`.
Domainless staging (pages.dev + sslip.io are different sites) needs `COOKIE_SAMESITE=none`; remove it once the real domain is connected.
The API's database role (`finlit_api`) has only the grants the accounts tables need (verified in tests).

## Personalisation
Six palettes (Ivory & Gold default, Champagne, Copper, Graphite, Midnight, Emerald) × light/dark, density, and a dashboard whose widgets can be switched on/off,
resized and reordered. Choices live in the browser and, when signed in, in the account (`user_state.prefs`), so they follow the member to a new device.
Palettes are defined in `frontend/src/lib/palettes.ts`; add one there and add its id to `PALETTES` in `backend/finlit/auth/routes.py`.

## Running everything locally
```bash
SITE_PY=/path/to/python-with-old-site-deps SITE_BACKEND=/path/to/Financial-Portfolio/backend SHOWCASE_SYMBOLS=NONE dev/run_stack.sh
cd frontend && node e2e/accounts.mjs http://127.0.0.1:4173      # 60+ browser checks of the real flows
dev/run_stack.sh stop
```
With real data instead of fixtures (the key is read from `FINEDGE_API_KEY`, never stored): `python -m finlit.worker ingest-all --limit 200` once, then
`LIVE_DATA=1 dev/run_stack.sh` (no `SITE_BACKEND` needed; only the market ticker, served by the older site API, is then empty) and `node e2e/live_data.mjs http://127.0.0.1:4173`.
Mail in development goes to the `outbox` table. `scripts/seed_dev_universe.py` adds fictional `SMP-` companies so the screener has a universe; never run it in production.

## Known gaps (need input or later work)
- Data: only RELIANCE is ingested locally; the full universe needs the FinEdge key and `python -m finlit.worker ingest ...` (polite concurrency).
- "vs market expectations" in the results dashboard needs consensus-estimate data; "score change vs previous quarter" needs a score-history table.
- Payments (Razorpay), Google sign-in/passkeys, legal review of the Terms/Privacy text, and connecting the domain are still to do.

## Added since: score history, data health, alerts, installable app
- **Score history:** every ingest writes one `score_history` row per day; the report shows "▲ +3 points since …" once there is a reading about a quarter old (`/api/stocks/{symbol}/score-history`, Bronze+).
- **Data health** (admin console): companies in the universe / loaded / scored / queued, last load, last-24-hour results and recent failures.
- **Target-price alerts:** `python -m finlit.worker check-alerts` (cron every 10 min in market hours). One email when a watchlist stock *crosses* the target the member set, at most once a day per stock; members can switch it off in Account → Appearance.
- **Installable app:** web manifest, icons, and a small service worker (offline shell; never caches `/api`). Also `robots.txt` and `sitemap.xml`.
