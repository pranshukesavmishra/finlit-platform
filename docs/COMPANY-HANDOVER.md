# FinLit platform: handover to the company repository

This folder is a snapshot of `pranshukesavmishra/finlit-platform`. It was built on top of the company's `Financial-Portfolio` code and is
delivered inside one folder (`finlit-platform/`) so that nothing in the company repository is overwritten. The company decides what to merge
and what to change. Nothing here contains secrets: configuration is read from the environment, and `.env.example` lists the names only.

## 1. What is in it

| Folder | What it is | Relation to `Financial-Portfolio` |
|---|---|---|
| `frontend/` | The website (React + TypeScript, Vite, react-query). Stock reports, screener, compare, Graph Studio, Prism, calculators, portfolio checker, quarter results, forum, funds and ETFs, admin console. | New; replaces the company's `frontend/` for the public site. |
| `backend/` (`finlit/`) | The research API (FastAPI, Postgres, Redis): stock reports precomputed by a worker, screener, results, alerts, accounts and plans (Basic, Silver, Gold), Prism front door, funds and ETFs, data-quality checks. | New. Name clash with the company's `backend/`: that is why this delivery lives in a folder. |
| `site-api/backend/` | The company's site backend (blog/CMS, portfolio, forms, chat, premium reports). | **Derived from the company's `backend/`.** Differences are listed in section 3. |
| `deploy/`, `Dockerfile`, `render.yaml` | One container (website + research API + site backend + scheduler) for a free Render service; Caddy files for a VPS. | New. |
| `docs/` | Plans, runbooks, `docs/prism/` (the Prism contract, coverage ledger and the company's model documents), `KNOWN-ISSUES.md`. | New, plus copies of the company's Prism documents. |
| `scripts/` | `preflight.sh` (all checks before a push), `smoke.sh` (live-site check), `export-to-company.sh` (this delivery). | New. |

## 2. How to run it

```bash
bash dev/services.sh                        # Postgres and Redis for development (Docker or local services)
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
PYTHONPATH=. .venv/bin/python -m finlit.worker migrate        # applies backend/finlit/migrations (001 to 065)
cd ../frontend && npm ci && npm run dev                       # http://localhost:5173 (VITE_DEMO=1 runs it without any backend)
```

Tests: `scripts/preflight.sh` runs everything (research API pytest, site backend pytest, vitest, type check, build, bandit, gitleaks,
`bash -n` on the deploy scripts, a secret-pattern scan). Single areas:

```bash
cd backend  && TEST_DATABASE_URL=postgresql://USER:PASS@localhost:5432/finlit_test TEST_REDIS_URL=redis://localhost:6379/1 PYTHONPATH=. .venv/bin/python -m pytest -q
cd site-api && FINEDGE_API_KEY= PYTHONPATH=.:backend python -m pytest -q -c backend/pytest.ini backend
cd frontend && npx tsc --noEmit && npx vitest run
```

Configuration names (values are never in the repository): `FINEDGE_API_KEY`, `DATABASE_URL` (Postgres), `MONGO_URL` and `DB_NAME` (site backend),
`REDIS_URL`, `CMS_JWT_SECRET`, `SECRET_KEY`, `UPSTOX_ACCESS_TOKEN`, `DHAN_*` (optional), `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_REQUIRE_MFA`,
`ALLOWED_HOSTS`, and switches such as `FUND_LOADS_ENABLED` and `BOOT_LOAD_ENABLED`. See `.env.example`, `render.yaml` and `docs/LAUNCH-GUIDE.md`.

## 3. How `site-api/backend` differs from the company's `backend`

Compared with `Financial-Portfolio` at commit `6ed9d2a` (merge of PR #40, the version this work was synchronised with):

- **Changed files:** `server.py`, `premium_benchmarks.py`, `premium_completeness.py`, `premium_data.py`, `premium_presentation.py`,
  `premium_provider.py`, `premium_service.py`, `requirements.txt`, and four test files (`test_api.py`, `test_chat.py`,
  `test_portfolio_report.py`, `test_service_enquiry.py`).
- **New files:** `premium_cache.py`, `premium_supplied_candles.py`, `technical_wording.py` and `technical_wording.json`, `premium_replay/`, and
  the matching tests (`test_premium_input_assembly.py`, `test_premium_kept_technical.py`, `test_premium_price_window.py`,
  `test_premium_supplied_candles.py`, `test_regression_risk_inputs.py`, `test_start_without_mongo.py`, `test_technical_wording.py`).
- **What the changes do:** (a) the Prism calculation is much faster (shared provider calls, kept inputs and peer rows, 16 parallel peer
  lookups) with identical numbers: `test_premium_input_assembly.py` replays five companies through the old and the new assembly and demands exact
  equality; (b) price series can be supplied by the caller (Dhan candles first, then Upstox and FinEdge) with sanity checks;
  (c) all-zero holiday rows from the provider are dropped from the price window; (d) the PDF relabels the model's technical-assessment words
  on a copy of the report (the company's `premium_pdf.py` is unchanged); (e) the site backend starts without MongoDB.
- The model itself (`premium_engine.py`, `premium_model_config.py`, scoring, weights and thresholds) is the company's, unchanged. The coverage
  ledger is `docs/prism/COVERAGE.md`.
- `Financial-Portfolio/backend` also holds two broker PDFs (`realizedPnL_*.pdf`) that are not in this delivery.

## 4. What the company needs to decide or change before merging

1. **Layout:** the research API is called `backend/` here and so is the company's. Decide the final names (for example `research-api/` and
   `site-api/`) and update `Dockerfile`, `render.yaml`, `deploy/*`, `.github/workflows` and the import paths in tests accordingly.
2. **Hosting and quotas:** the delivery is tuned for free tiers (512 MB container, Neon free Postgres, Atlas free Mongo). The scheduler groups
   database work into short windows so the database can sleep (`deploy/scheduler.sh`, `backend/finlit/wake.py`). A paid plan removes most of
   this work.
3. **Data licences:** FinEdge is the primary provider. Upstox (analytics token), Dhan, AMFI and NSE files are used as secondary sources. Check each
   provider's terms for public display and caching before launch; Dhan's written permission to show its data publicly is still open.
4. **Accounts and plans:** Basic, Silver and Gold are enforced on the server (`backend/finlit/auth/entitlements.py`). Payments are not connected: plan changes are requested by members and approved in the admin console.
5. **Compliance wording:** nothing shown to readers uses buy, sell, hold, reduce, avoid, accumulate or target language. Tests scan the PDF text and
   the API responses for it. Keep the line "Describes the company's financial health from its filings and prices; not a recommendation."
6. **Admin sign-in:** `ADMIN_REQUIRE_MFA` is set to `0` in `render.yaml` for the testing period. Set it to `1` before a public launch.
7. **Known limits** are in `docs/KNOWN-ISSUES.md` and `docs/LAUNCH-STATUS.md`. ETF and fund data loads are paused by default
   (`FUND_LOADS_ENABLED`), and holdings, expense ratios and exit loads for funds are not loaded yet (`docs/NEXT-STEPS-FUNDS.md`).

## 5. Where to start reading

`README.md` (overview and speed design), `docs/TECHNICAL-DOCUMENT.md`, `docs/platform-plan.md`, `docs/prism/CONTRACT.md`,
`docs/ops/MEMORY-AND-503.md` (why the free container needs care), `docs/PREFLIGHT-AND-SMOKE.md`.
