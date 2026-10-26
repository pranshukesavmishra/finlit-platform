# Upstream coverage ledger: Yusra-Khan532/financial-portfolio -> FinLit

Every file tracked in the upstream repository (`git ls-files` at upstream HEAD **6ed9d2a**, 276 files) and where it is in FinLit. Upstream `backend/` = FinLit `site-api/backend/`; merge base for the first three-way merge = upstream **67aab4f** (commit 1346489 here); the second (26 Oct) merged b112ba1..6ed9d2a with base b112ba1. Generated and checked on 2026-10-26 (first merge 2026-10-25).

## Totals

| Status | Files | Meaning |
| --- | ---: | --- |
| `merged-identical` | 73 | a byte-identical copy exists in FinLit (checked with `cmp`) |
| `merged-3way` | 6 | merged with FinLit's own changes; every upstream and every FinLit line proven present (section 2) |
| `ported` | 17 | rewritten for the FinLit TypeScript site; being written now (planned path given) |
| `equivalent-exists` | 67 | FinLit has its own implementation; the note says what (if anything) the upstream version has that FinLit lacks |
| `not-merged` | 113 | deliberately not merged, with the reason |
| **total** | **276** | |

Per directory:

| Directory | `merged-identical` | `merged-3way` | `ported` | `equivalent-exists` | `not-merged` | total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `(repository root)` |  |  |  | 2 | 5 | 7 |
| `.emergent` |  |  |  |  | 2 | 2 |
| `.emergent/cron` |  |  |  |  | 5 | 5 |
| `.emergent/markers` |  |  |  |  | 2 | 2 |
| `.github/workflows` |  |  |  | 1 |  | 1 |
| `assets/team` |  |  |  | 1 | 2 | 3 |
| `backend` | 28 | 2 |  |  |  | 30 |
| `backend/content_uploads` | 8 |  |  |  |  | 8 |
| `backend/portfolio_data` | 1 |  |  |  |  | 1 |
| `backend/portfolio_data/sources` |  |  |  |  | 2 | 2 |
| `backend/tests` | 25 | 4 |  |  |  | 29 |
| `backend/tests/fixtures` | 4 |  |  |  |  | 4 |
| `docs` | 5 |  |  |  |  | 5 |
| `frontend` |  |  |  | 4 | 6 | 10 |
| `frontend/plugins/health-check` |  |  |  |  | 2 | 2 |
| `frontend/public` |  |  |  | 2 |  | 2 |
| `frontend/public/reports` |  |  |  |  | 2 | 2 |
| `frontend/src` |  |  |  | 5 |  | 5 |
| `frontend/src/assets/brand` | 1 |  |  |  |  | 1 |
| `frontend/src/assets/team` |  |  |  | 1 | 2 | 3 |
| `frontend/src/components` |  |  | 6 | 17 |  | 23 |
| `frontend/src/components/FinLitAssistant` |  |  |  | 5 |  | 5 |
| `frontend/src/components/blog` |  |  |  | 1 |  | 1 |
| `frontend/src/components/cms` |  |  |  | 5 |  | 5 |
| `frontend/src/components/ui` |  |  |  |  | 46 | 46 |
| `frontend/src/constants/testIds` |  |  |  |  | 3 | 3 |
| `frontend/src/data` | 1 |  |  | 3 | 1 | 5 |
| `frontend/src/hooks` |  |  | 2 | 2 |  | 4 |
| `frontend/src/lib` |  |  | 8 | 3 | 1 | 12 |
| `frontend/src/pages` |  |  | 1 | 15 | 1 | 17 |
| `memory` |  |  |  |  | 2 | 2 |
| `test_reports` |  |  |  |  | 4 | 4 |
| `test_reports/pytest` |  |  |  |  | 2 | 2 |
| `tests` |  |  |  |  | 1 | 1 |
| `tmp/pdfs` |  |  |  |  | 22 | 22 |

## Features in upstream that FinLit does not have (excluding the premium model)

For the user to decide. None of these is needed by FinLit Prism.

| Feature | Upstream file(s) | What it does / FinLit state |
| --- | --- | --- |
| CMS: edit an existing post | BlogAdminEditPage, ContentEditor | FinLit's Admin can only create a draft, publish/unpublish and delete; the site backend already supports `PUT /api/content/admin/items/{id}` with every field. |
| CMS: PDF / spreadsheet / image posts | ContentEditor | Upload a resource file (`POST /api/content/admin/upload`, 15 MB) as a Report, Data or Visual post. FinLit's blog can display such posts but its Admin cannot create them. |
| CMS: cover images | ContentEditor, blog/CoverImage | Upload a cover or give an https URL. FinLit shows covers but cannot set one. |
| CMS: rich-text editor | RichTextEditor (tiptap) | Bold, italic, underline, lists, quotes, https links and inline images. FinLit uses a plain textarea. |
| CMS: draft preview | BlogAdminPreviewPage | See a draft as readers will before publishing. |
| CMS: search and filter the content list | BlogAdminPage | Filter by status/type and search titles. |
| Portfolio statement upload | BlogAdminPage | Administrator uploads a new broker statement PDF (`POST /api/portfolio/admin/upload`) to refresh the public /portfolio report. FinLit's site backend supports it (and keeps it in MongoDB) but there is no button. |
| Bank asset quality | StockFundamentalsAdminPage | GNPA %, NNPA % and CET1 % for banks (site backend already returns `bankAssetQuality`). |
| Data quality flags | StockFundamentalsAdminPage | Shows where FinEdge and a fallback provider disagree (`dataQuality` in the fundamentals payload). |
| Dev metrics | StockFundamentalsAdminPage | Fetch timing and payload mix of the fundamentals request (administrator diagnostics). |
| Sector / industry company browser | CompanyBrowser, companyClassifications.json | Browse FinEdge companies by sector or industry. The research API already proxies `/api/premium/fundamentals/browse`; no FinLit page uses it. |
| P&L "Growth %" view (YoY / QoQ) | IncomeGrowthView, fundamentalGrowth | Toggle on the fundamentals P&L chart showing revenue, net profit and EPS growth, with the reason when a value cannot be computed. Added upstream since 67aab4f; not part of the model. |
| Key-factor panels | StockFundamentalsAdminPage | Stock DNA, Valuation / Quality / Technicals key factors and Financial Snapshot panels built from FinEdge highlights (FinLit has its own score pillars and valuation sections instead). |
| Home page sections | Home, Performance, Process, Philosophy, Testimonial | Portfolio performance, the 7-step process, philosophy and the client testimonial on the home page. The copy is already in `frontend/src/content/site.ts` but is not rendered. |
| Markets / Commodities dashboards: parity check | MarketsPage, CommodityExplorer | Checked in code: FinLit Markets.tsx has all seven tabs, date and symbol filters, in-table search, paging and CSV export, and its Commodities tab has both catalogues (monthly indices, eight core industries), search, history and month change. Nothing found missing. Only differences: upstream pages the commodity catalogue (FinLit scrolls it) and is administrator-only (FinLit: Gold). |
| Named shareholders (DetailedShareholding): parity check | DetailedShareholding | FinLit Fundamentals.tsx has the named-shareholder Tree from `shareholdingDetails`. Nothing missing. |
| Contact form "investment size" | Contact | Optional field the site backend accepts (`investment_size`). |
| Published service prices | data/services.js, finlitAssistantData | Rs 99 first session to Rs 2,499 a year. FinLit deliberately withholds prices ("announced soon"); listed only for completeness. |
| "Financial Product - Coming soon" page | FinancialProductPage | Placeholder at `/financial-product`. |
| Bundled portfolio fallback | data/portfolio.js, usePortfolioData | Upstream shows the bundled report when the API is down; FinLit shows an error state. |

### Port risk found while checking (premium model)

* `PremiumFinancialHistory.jsx` reads `report.calculationTrace` (quarterly and annual sales, owner profit, EBITDA, EPS, operating cash flow, book equity, latest ratios). CONTRACT.md removes `calculationTrace` from `PrismReport` and adds only `trends` (revenue, profit, EPS). Unless the research API passes these rows on (for example as `financialHistory`), the port loses that section.

## 1. File ledger

### `(repository root)`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `.gitconfig` | `not-merged` | - | Git identity of the Emergent agent (`emergent-agent-e1`); repository-local tooling. |
| `.gitignore` | `equivalent-exists` | `.gitignore` | FinLit has its own. Upstream additions since 67aab4f (`/output/`, `/outputs/`, `/tmp/`, `*.sqlite*`, `*.xlsx.inspect.ndjson` for audit workspaces) are not in FinLit's file; only matters if someone runs upstream audit scripts from the repo root. |
| `README.md` | `equivalent-exists` | docs/prism/CONTRACT.md + docs/prism/*.md | Upstream README only links the three model docs, which are in docs/prism/. |
| `design_guidelines.json` | `not-merged` | - | Emergent design brief for the CRA/Tailwind site; FinLit has its own design system (frontend/src/styles, design/). |
| `finedge_output.txt` | `not-merged` | - | Output of a one-off FinEdge API access probe (UTF-16 text, key hidden). Generated artefact. |
| `test_finedge_api.py` | `not-merged` | - | One-off FinEdge endpoint probe script at the repo root (no key inside). FinLit's FinEdge use is covered by site-api tests and backend/finlit provider tests. |
| `test_result.md` | `not-merged` | - | Emergent testing-protocol log. Not product code. |

### `.emergent`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `.emergent/emergent.yml` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |
| `.emergent/system_deps.txt` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |

### `.emergent/cron`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `.emergent/cron/applied.hash` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. Empty file. |
| `.emergent/cron/dispatch_webhook.sh` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |
| `.emergent/cron/watch_crons.sh` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |
| `.emergent/cron/webhook-crons` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |
| `.emergent/cron/webhook_crond.sh` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. |

### `.emergent/markers`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `.emergent/markers/.bootstrap-complete` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. Empty file. |
| `.emergent/markers/.restore-complete` | `not-merged` | - | Emergent platform scaffolding (agent cron/markers/config); not part of the product. Empty file. |

### `.github/workflows`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `.github/workflows/webpack.yml` | `equivalent-exists` | .github/workflows/frontend.yml, ci.yml | Upstream builds the CRA app on Node 18/20/22. FinLit CI builds/tests the Vite site (`frontend.yml`) and runs the site backend tests (`ci.yml` job `site-api`). Nothing upstream-only. |

### `assets/team`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `assets/team/nishant.png` | `equivalent-exists` | `frontend/public/team/nishant.webp` | Duplicate of frontend/src/assets/team/nishant.png; FinLit ships the same portrait as WebP (About page). |
| `assets/team/umam.png` | `not-merged` | - | Team portrait not referenced by any upstream code (only nishant.png is imported). Personal photo; add only if a team section is wanted. |
| `assets/team/yusra.png` | `not-merged` | - | Team portrait not referenced by any upstream code. Personal photo; add only if a team section is wanted. |

### `backend`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/benchmark_resolution.py` | `merged-identical` | `site-api/backend/benchmark_resolution.py` | Premium model: valuation benchmark (P/E, P/B) resolution for the model. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/email_service.py` | `merged-identical` | `site-api/backend/email_service.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/financial_fields.py` | `merged-identical` | `site-api/backend/financial_fields.py` | Premium model: shared financial field names. New upstream since 67aab4f, added verbatim. |
| `backend/financial_records.py` | `merged-identical` | `site-api/backend/financial_records.py` | Premium model: provider-neutral numeric/date parsing, row selection and the rupee-to-crore constant (split out of premium_data.py). New upstream since b112ba1, added verbatim. |
| `backend/fundamental_resolution.py` | `merged-identical` | `site-api/backend/fundamental_resolution.py` | Premium model: source resolution / fallbacks between FinEdge and Upstox. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/generate_portfolio_data.py` | `merged-identical` | `site-api/backend/generate_portfolio_data.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/market_data.py` | `merged-identical` | `site-api/backend/market_data.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/portfolio_report.py` | `merged-identical` | `site-api/backend/portfolio_report.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/premium_benchmarks.py` | `merged-identical` | `site-api/backend/premium_benchmarks.py` | Premium model: peer observation collection/cache and reported-first report benchmarks (split out of premium_data.py). New upstream since b112ba1, added verbatim. |
| `backend/premium_classification.py` | `merged-identical` | `site-api/backend/premium_classification.py` | Premium model: profile extraction and deterministic model-group classification (split out of premium_data.py). New upstream since b112ba1, added verbatim. |
| `backend/premium_completeness.py` | `merged-identical` | `site-api/backend/premium_completeness.py` | Premium model: input completeness and history checks. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_data.py` | `merged-identical` | `site-api/backend/premium_data.py` | Premium model: model input loader (same loader as Stock Fundamentals). New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_engine.py` | `merged-identical` | `site-api/backend/premium_engine.py` | Premium model: deterministic scoring engine (3.6.9). New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_model_config.py` | `merged-identical` | `site-api/backend/premium_model_config.py` | Premium model: weights, bands and thresholds. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_pdf.py` | `merged-identical` | `site-api/backend/premium_pdf.py` | Premium model: ReportLab PDF renderer. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_presentation.py` | `merged-identical` | `site-api/backend/premium_presentation.py` | Premium model: reader-facing review (pros/cons, notes). New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_provider.py` | `merged-identical` | `site-api/backend/premium_provider.py` | Premium model: shared bounded provider/retry budget and the standalone FinEdge input loader (split out of premium_data.py). New upstream since b112ba1, added verbatim. |
| `backend/premium_service.py` | `merged-identical` | `site-api/backend/premium_service.py` | Premium model: report generation service (background / inline delivery). New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/premium_snapshot.py` | `merged-identical` | `site-api/backend/premium_snapshot.py` | Premium model: signed snapshot receipt (HS256, 30 min). New upstream since 67aab4f, added verbatim. |
| `backend/premium_technical.py` | `merged-identical` | `site-api/backend/premium_technical.py` | ST/LT technical assessment: candle validation, series choice, signal aggregation, ratings/verdict, report contract. New upstream since b112ba1, added verbatim. |
| `backend/premium_technical_sources.py` | `merged-identical` | `site-api/backend/premium_technical_sources.py` | ST/LT technical assessment: FinEdge index history, Upstox fallback, session-date checks, 15-minute cache. New upstream since b112ba1, added verbatim. |
| `backend/premium_trace.py` | `merged-identical` | `site-api/backend/premium_trace.py` | Premium model: calculation trace. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/pytest.ini` | `merged-identical` | `site-api/backend/pytest.ini` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/requirements.txt` | `merged-3way` | `site-api/backend/requirements.txt` | Upstream adds `reportlab>=4.0,<5`; FinLit keeps its framework upgrades (fastapi 0.143.2, uvicorn 0.54.0, pymongo>=4.11, motor>=3.7, pyjwt, pytest-xdist). 1/1 upstream and 5/5 FinLit lines present. |
| `backend/server.py` | `merged-3way` | `site-api/backend/server.py` | Both sides changed since 67aab4f. Upstream adds the premium-report API (`/api/premium-reports*`, `/api/premium-report-downloads/{token}`, PDF, signed snapshot) and FinEdge/Upstox data recovery; FinLit keeps its hardening (MongoDB copies of uploads and of the portfolio report, `CMS_PASSWORD_LOGIN` gate, plain-password hash fallback, `GEMINI_MODEL`, plain-text chat rules, no "Never quote a price" regression, enquiry list for admins, no `*.vercel.app` CORS). Line proof: 357/357 upstream lines and 75/75 FinLit lines present, 0 deviations (section 2). 26 Oct: merged again, upstream b112ba1..6ed9d2a (+26 lines: technical candles/benchmarks capture, leverage inputs, `ZoneInfo` import); one conflict (the cache store line: FinLit's bounded `_remember_stock_fundamentals` kept, upstream's three `model_inputs` lines added before it). Proof in section 2b. 26 Oct (Dhan candles, FinLit delta, upstream lines unchanged): `PremiumReportRequest` gains optional `suppliedCandles`; `_premium_dashboard_inputs` gains an optional 4th argument `supplied_candles` and its two technical calls (`resolve_technical_prices`, `load_benchmark_history`) are wrapped in `lambda`s passed to `prices_with_supplied` / `benchmarks_with_supplied` (new FinLit file `premium_supplied_candles.py`; with no supplied candles the original calls run with the same arguments); `_generate_premium_report` and the two `generate_report(...)` call sites pass the 4th argument through lambdas. `premium_technical.py` and `premium_technical_sources.py` stay `merged-identical`. New FinLit tests (not upstream): `tests/test_premium_supplied_candles.py`. |
| `backend/stock_dashboard_audit.py` | `merged-identical` | `site-api/backend/stock_dashboard_audit.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/technical_patterns.py` | `merged-identical` | `site-api/backend/technical_patterns.py` | ST/LT technical assessment: pivots, sweeps, SFPs and range-distributed volume profiles. New upstream since b112ba1, added verbatim. |
| `backend/technical_scoring.py` | `merged-identical` | `site-api/backend/technical_scoring.py` | ST/LT technical assessment: scoring-only translation of the owner's daily/weekly indicators and ST/LT rules. New upstream since b112ba1, added verbatim. |
| `backend/technical_series.py` | `merged-identical` | `site-api/backend/technical_series.py` | ST/LT technical assessment: EMA/Wilder smoothing, RSI, MACD, ATR/ADX, OBV, regression, percentile rank, beta, benchmark series. New upstream since b112ba1, added verbatim. |
| `backend/vercel.json` | `merged-identical` | `site-api/backend/vercel.json` | Upstream Vercel serverless setting (`maxDuration` 300 s). Inert on FinLit (Render/Docker), kept for parity. |

### `backend/content_uploads`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/content_uploads/05aba463-c278-429c-9d35-74b5c402d0ff.png` | `merged-identical` | `site-api/backend/content_uploads/05aba463-c278-429c-9d35-74b5c402d0ff.png` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/0ea1ecb5-2c2a-4a57-823e-cc18c7693381.pdf` | `merged-identical` | `site-api/backend/content_uploads/0ea1ecb5-2c2a-4a57-823e-cc18c7693381.pdf` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/36403c97-4374-40ed-8f29-f50aa74c6f65.pdf` | `merged-identical` | `site-api/backend/content_uploads/36403c97-4374-40ed-8f29-f50aa74c6f65.pdf` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/8aa9754b-be3c-4aa5-894c-2f1ac9138157.pdf` | `merged-identical` | `site-api/backend/content_uploads/8aa9754b-be3c-4aa5-894c-2f1ac9138157.pdf` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/bce3ac2f-d9d2-4442-af10-977bb972d6fd.png` | `merged-identical` | `site-api/backend/content_uploads/bce3ac2f-d9d2-4442-af10-977bb972d6fd.png` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/ca7a96fc-6d8c-473f-8f50-c0d238305fbb.png` | `merged-identical` | `site-api/backend/content_uploads/ca7a96fc-6d8c-473f-8f50-c0d238305fbb.png` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/dcfbc8a8-935b-4d2a-b164-84766a8e5745.xlsx` | `merged-identical` | `site-api/backend/content_uploads/dcfbc8a8-935b-4d2a-b164-84766a8e5745.xlsx` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |
| `backend/content_uploads/f4d11a2a-07bd-40e4-b265-7862cf7e102c.png` | `merged-identical` | `site-api/backend/content_uploads/f4d11a2a-07bd-40e4-b265-7862cf7e102c.png` | CMS upload shipped with the code (fallback for MongoDB `content_blobs`). Unchanged on both sides since 67aab4f. |

### `backend/portfolio_data`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/portfolio_data/current.json` | `merged-identical` | `site-api/backend/portfolio_data/current.json` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |

### `backend/portfolio_data/sources`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/portfolio_data/sources/realizedPnL_EQ_2026-04-01_To_2026-09-10_BR2287.pdf` | `not-merged` | - | Personal brokerage statement (realised P&L, client code BR2287). Deliberately not added; FinLit keeps `site-api/backend/portfolio_data/sources/.gitkeep` and serves the already-generated `portfolio_data/current.json` (identical to upstream) plus admin uploads stored in MongoDB. |
| `backend/portfolio_data/sources/realizedPnL_EQ_2026-04-01_To_2026-09-26_BR2287.pdf` | `not-merged` | - | Personal brokerage statement (realised P&L, client code BR2287). Deliberately not added; FinLit keeps `site-api/backend/portfolio_data/sources/.gitkeep` and serves the already-generated `portfolio_data/current.json` (identical to upstream) plus admin uploads stored in MongoDB. |

### `backend/tests`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/tests/conftest.py` | `merged-identical` | `site-api/backend/tests/conftest.py` | Taken through `git merge-file`; FinLit had no local change, so the result equals upstream HEAD (adds the premium fixtures/env). |
| `backend/tests/premium_example.json` | `merged-identical` | `site-api/backend/tests/premium_example.json` | Premium model regression fixture. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_api.py` | `merged-3way` | `site-api/backend/tests/test_api.py` | Upstream unchanged since 67aab4f; FinLit adds `test_password_only_cms_sign_in_is_off_unless_enabled` (8 lines). Every upstream line present (FinLit removed none). |
| `backend/tests/test_assessment_data_recovery.py` | `merged-identical` | `site-api/backend/tests/test_assessment_data_recovery.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_chat.py` | `merged-3way` | `site-api/backend/tests/test_chat.py` | Upstream unchanged since 67aab4f; FinLit adds `test_plain_chat_text_strips_markdown` (5 lines). Every upstream line present. |
| `backend/tests/test_email_service.py` | `merged-identical` | `site-api/backend/tests/test_email_service.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/tests/test_flagged_company_lookup.py` | `merged-identical` | `site-api/backend/tests/test_flagged_company_lookup.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_fourth_quarter_recovery.py` | `merged-identical` | `site-api/backend/tests/test_fourth_quarter_recovery.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_market_data.py` | `merged-identical` | `site-api/backend/tests/test_market_data.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/tests/test_portfolio_report.py` | `merged-3way` | `site-api/backend/tests/test_portfolio_report.py` | Upstream unchanged since 67aab4f; FinLit adds a skip when the (deliberately absent) broker PDF is missing (3 lines). Every upstream line present. |
| `backend/tests/test_premium_accuracy.py` | `merged-identical` | `site-api/backend/tests/test_premium_accuracy.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_bank_fallbacks.py` | `merged-identical` | `site-api/backend/tests/test_premium_bank_fallbacks.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_cagr_windows.py` | `merged-identical` | `site-api/backend/tests/test_premium_cagr_windows.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_completeness.py` | `merged-identical` | `site-api/backend/tests/test_premium_completeness.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_insurance_leverage.py` | `merged-identical` | `site-api/backend/tests/test_premium_insurance_leverage.py` | Insurance financial-leverage regression test (engine 3.6.10). New upstream since b112ba1, added verbatim. |
| `backend/tests/test_premium_loss_rules.py` | `merged-identical` | `site-api/backend/tests/test_premium_loss_rules.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_presentation.py` | `merged-identical` | `site-api/backend/tests/test_premium_presentation.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_premium_recovery.py` | `merged-identical` | `site-api/backend/tests/test_premium_recovery.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_premium_reports.py` | `merged-identical` | `site-api/backend/tests/test_premium_reports.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_serverless.py` | `merged-identical` | `site-api/backend/tests/test_premium_serverless.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_premium_shared_sources.py` | `merged-identical` | `site-api/backend/tests/test_premium_shared_sources.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_premium_technical.py` | `merged-identical` | `site-api/backend/tests/test_premium_technical.py` | ST/LT technical assessment: weights, denominators, verdict matrix, rating boundaries, stage cap, percentile ties, SFPs, profiles, PDF. New upstream since b112ba1, added verbatim. |
| `backend/tests/test_premium_technical_sources.py` | `merged-identical` | `site-api/backend/tests/test_premium_technical_sources.py` | ST/LT technical assessment: benchmark source precedence, session-date recovery and cache. New upstream since b112ba1, added verbatim. |
| `backend/tests/test_premium_trace.py` | `merged-identical` | `site-api/backend/tests/test_premium_trace.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |
| `backend/tests/test_required_input_recovery.py` | `merged-identical` | `site-api/backend/tests/test_required_input_recovery.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. |
| `backend/tests/test_service_enquiry.py` | `merged-3way` | `site-api/backend/tests/test_service_enquiry.py` | Upstream unchanged since 67aab4f; FinLit adds `test_enquiries_are_listed_for_the_administrator_only` (6 lines). Every upstream line present. |
| `backend/tests/test_stock_classification_search.py` | `merged-identical` | `site-api/backend/tests/test_stock_classification_search.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/tests/test_stock_fundamental_normalization.py` | `merged-identical` | `site-api/backend/tests/test_stock_fundamental_normalization.py` | Unchanged on both sides since 67aab4f (FinLit copy already identical). |
| `backend/tests/test_valuation_benchmarks.py` | `merged-identical` | `site-api/backend/tests/test_valuation_benchmarks.py` | Premium model regression test. New upstream since 67aab4f, added verbatim. Updated 26 Oct to upstream 6ed9d2a (engine 3.6.10 / ST-LT); still byte-identical (`cmp`). |

### `backend/tests/fixtures`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `backend/tests/fixtures/premium_owner_parity.json` | `merged-identical` | `site-api/backend/tests/fixtures/premium_owner_parity.json` | Premium model regression fixture. New upstream since 67aab4f, added verbatim. |
| `backend/tests/fixtures/premium_reconciliation_2026_10_18.json` | `merged-identical` | `site-api/backend/tests/fixtures/premium_reconciliation_2026_10_18.json` | Premium model regression fixture. New upstream since 67aab4f, added verbatim. |
| `backend/tests/fixtures/premium_reliance_screenshot.json` | `merged-identical` | `site-api/backend/tests/fixtures/premium_reliance_screenshot.json` | Premium model regression fixture. New upstream since 67aab4f, added verbatim. |
| `backend/tests/fixtures/premium_stock_audit_2026_10_18.json` | `merged-identical` | `site-api/backend/tests/fixtures/premium_stock_audit_2026_10_18.json` | Premium model regression fixture. New upstream since 67aab4f, added verbatim. |

### `docs`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `docs/portfolio-updates-summary.md` | `merged-identical` | `docs/prism/portfolio-updates-summary.md` | Upstream model documentation, copied verbatim. Paths inside refer to upstream `backend/` = FinLit `site-api/backend/`. |
| `docs/premium-model-implementation.md` | `merged-identical` | `docs/prism/premium-model-implementation.md` | Upstream model documentation, copied verbatim. Paths inside refer to upstream `backend/` = FinLit `site-api/backend/`. Updated 26 Oct to upstream 6ed9d2a. |
| `docs/premium-model-input-output.md` | `merged-identical` | `docs/prism/premium-model-input-output.md` | Upstream model documentation, copied verbatim. Paths inside refer to upstream `backend/` = FinLit `site-api/backend/`. Updated 26 Oct to upstream 6ed9d2a. |
| `docs/premium-report-lifecycle.md` | `merged-identical` | `docs/prism/premium-report-lifecycle.md` | Upstream model documentation, copied verbatim. Paths inside refer to upstream `backend/` = FinLit `site-api/backend/`. Updated 26 Oct to upstream 6ed9d2a. |
| `docs/premium-st-lt-model.md` | `merged-identical` | `docs/prism/premium-st-lt-model.md` | Upstream ST/LT model documentation (new since b112ba1), copied verbatim. Paths inside refer to upstream `backend/` = FinLit `site-api/backend/`. |

### `frontend`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/.gitignore` | `equivalent-exists` | `.gitignore` | CRA ignores; FinLit ignores `frontend/node_modules/` and `frontend/dist/` at the root. |
| `frontend/README.md` | `not-merged` | - | Stock Create React App README. |
| `frontend/components.json` | `not-merged` | - | shadcn/ui generator config; FinLit does not use shadcn. |
| `frontend/craco.config.js` | `not-merged` | - | CRA/craco build config (the only change since 67aab4f is a Jest `@/` alias for the premium tests). FinLit builds with Vite (frontend/vite config, vitest). |
| `frontend/jsconfig.json` | `not-merged` | - | CRA `@/` path alias; FinLit uses TypeScript with relative imports. |
| `frontend/package-lock.json` | `equivalent-exists` | `frontend/package-lock.json` | Different toolchain (CRA vs Vite); FinLit has its own lock file. |
| `frontend/package.json` | `equivalent-exists` | `frontend/package.json` | Different toolchain (CRA + shadcn + recharts + tiptap + lenis vs Vite + TS). The premium port needs no new package (FinLit draws charts in SVG). |
| `frontend/postcss.config.js` | `not-merged` | - | Tailwind/PostCSS config; FinLit does not use Tailwind. |
| `frontend/tailwind.config.js` | `not-merged` | - | Tailwind theme; FinLit uses CSS custom properties (frontend/src/styles/theme.css). |
| `frontend/vercel.json` | `equivalent-exists` | `frontend/public/_redirects` | SPA rewrite to index.html; FinLit has `_redirects` and the research API serves the SPA in the single-image deploy. |

### `frontend/plugins/health-check`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/plugins/health-check/health-endpoints.js` | `not-merged` | - | Emergent dev-server health-check plugin for webpack. |
| `frontend/plugins/health-check/webpack-health-plugin.js` | `not-merged` | - | Emergent dev-server health-check plugin for webpack. |

### `frontend/public`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/public/favicon.svg` | `equivalent-exists` | `frontend/public/favicon.svg` | FinLit has its own favicon (and PWA icons). |
| `frontend/public/index.html` | `equivalent-exists` | `frontend/index.html` | CRA HTML shell; FinLit has the Vite shell. |

### `frontend/public/reports`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/public/reports/realizedPnL_EQ_2026-04-01_To_2026-09-10_BR2287.pdf` | `not-merged` | - | Personal brokerage statement published as a download upstream. Deliberately not added. |
| `frontend/public/reports/realizedPnL_EQ_2026-04-01_To_2026-09-26_BR2287.pdf` | `not-merged` | - | Personal brokerage statement published as a download upstream. Deliberately not added. |

### `frontend/src`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/App.css` | `equivalent-exists` | `frontend/src/styles/*.css` | App styles for the CRA site; FinLit has its own style sheets. |
| `frontend/src/App.js` | `equivalent-exists` | `frontend/src/App.tsx` | Router. Every upstream route has a FinLit page except `/financial-product` (a "Coming soon" placeholder) and the admin sub-routes noted below. The two routes added since 67aab4f (`/blog/admin/premium-reports[/:reportId]`) become `/prism` and `/prism/:symbol` (to be ported: App.tsx routes). |
| `frontend/src/config.js` | `equivalent-exists` | frontend/src/content/site.ts (COMPANY) | Contact e-mail and LinkedIn URL. |
| `frontend/src/index.css` | `equivalent-exists` | frontend/src/styles/theme.css, site.css | Global CSS/theme tokens. |
| `frontend/src/index.js` | `equivalent-exists` | `frontend/src/main.tsx` | App entry. |

### `frontend/src/assets/brand`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/assets/brand/finlit-logo-transparent.png` | `merged-identical` | `frontend/public/brand/finlit-logo.png` | Byte-identical (cmp) under another name. |

### `frontend/src/assets/team`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/assets/team/nishant.png` | `equivalent-exists` | `frontend/public/team/nishant.webp` | Same portrait converted to WebP; used by About (content/site.ts FOUNDER.photo). |
| `frontend/src/assets/team/umam.png` | `not-merged` | - | Not imported anywhere upstream. Personal photo. |
| `frontend/src/assets/team/yusra.png` | `not-merged` | - | Not imported anywhere upstream. Personal photo. |

### `frontend/src/components`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/components/CommodityExplorer.jsx` | `equivalent-exists` | frontend/src/pages/Markets.tsx (Commodities tab) | Same FinEdge monthly-index / core-infra catalogue and history via `/api/premium/commodities*` (research API proxy). FinLit also has a public commodities page (pages/Commodities.tsx). Nothing upstream-only. |
| `frontend/src/components/CompanyBrowser.jsx` | `equivalent-exists` | frontend/src/components/search/SearchOverlay.tsx, pages/Screener.tsx | FinLit finds companies by search/screener. Upstream-only: browsing by FinEdge sector/industry list (uses `/api/stocks/admin/fundamentals/browse` + companyClassifications.json). The research API already proxies it (`GET /api/premium/fundamentals/browse`) but no FinLit page calls it. Its "Select" mode is used by the premium page (to be ported: frontend/src/pages/Prism.tsx company picker). |
| `frontend/src/components/Contact.jsx` | `equivalent-exists` | frontend/src/pages/Contact.tsx, pages/Home.tsx (closing call to action) | Contact form posting to `/api/contact`. Upstream-only: the optional "investment size" field (`investment_size`, accepted by the site backend) and the form on the home page itself. |
| `frontend/src/components/DetailedShareholding.jsx` | `equivalent-exists` | frontend/src/pages/Fundamentals.tsx (Shareholders tab, "Named shareholders" Tree) | Named shareholder tree from `shareholdingDetails`. |
| `frontend/src/components/Footer.jsx` | `equivalent-exists` | frontend/src/components/Layout.tsx (footer) | Footer with contact e-mail/LinkedIn. |
| `frontend/src/components/Hero.jsx` | `equivalent-exists` | frontend/src/pages/Home.tsx, components/HeroCanvas.tsx | Home hero. |
| `frontend/src/components/IncomeGrowthView.jsx` | `equivalent-exists` | frontend/src/stock/Sections*.tsx ("Year-on-year growth by line item"), stock/Sections4.tsx (quarter vs previous quarter) | Added upstream since 67aab4f (not part of the model): a "Growth %" view of revenue, net profit and EPS on the fundamentals P&L chart, YoY or QoQ, with the reason a value is missing. FinLit shows YoY growth by line on the stock page and QoQ on the latest-quarter section, but not this toggle on the Gold fundamentals dashboard. |
| `frontend/src/components/MarketTicker.jsx` | `equivalent-exists` | `frontend/src/components/Tape.tsx` | Index strip; FinLit reads `/api/indices` (research API) instead of the site backend `/api/market-ticker` (still exposed as `getTicker` in lib/siteApi.ts). |
| `frontend/src/components/Navbar.jsx` | `equivalent-exists` | frontend/src/components/Layout.tsx, lib/nav.ts | Navigation. |
| `frontend/src/components/Performance.jsx` | `equivalent-exists` | `frontend/src/pages/Portfolio.tsx` | Portfolio KPIs and charts. Upstream also shows them as a section of the home page; FinLit shows them on /portfolio only. |
| `frontend/src/components/Philosophy.jsx` | `equivalent-exists` | frontend/src/content/site.ts (PHILOSOPHY), pages/About.tsx (principles) | The philosophy chips are in content/site.ts but not rendered on FinLit's home page (FinLit home was redesigned). |
| `frontend/src/components/PremiumFinancialHistory.jsx` | `ported` | to be ported: frontend/src/pages/Prism*.tsx (financial history section) | Premium report: quarterly/annual results and key ratios from `report.calculationTrace`. NOTE: CONTRACT.md strips `calculationTrace` from `PrismReport` and only adds `trends` (revenue, profit, eps), so the port must carry these rows another way (e.g. a `financialHistory` field) or this section is lost. Changed again upstream in 6ed9d2a (page split into hook + detail component). |
| `frontend/src/components/PremiumInputCompleteness.jsx` | `ported` | to be ported: frontend/src/pages/Prism*.tsx (input completeness panel) | Premium report: missing factors / limited histories from `review.completeness` (premium_completeness.py). |
| `frontend/src/components/PremiumReportDetail.jsx` | `ported` | to be ported: frontend/src/pages/PrismReport.tsx | New upstream (6ed9d2a): the completed-report rendering extracted from PremiumReportPage.jsx. |
| `frontend/src/components/PremiumTechnicalAssessment.jsx` | `ported` | to be ported: frontend/src/pages/PrismReport.tsx (technicalAssessment section) | New upstream (6ed9d2a): ST/LT score cards, verdict, signals and missing inputs from `technicalAssessment` (see CONTRACT.md, section technicalAssessment; the research API strips weights and hashes; labels are relabelled by the display layer). |
| `frontend/src/components/PremiumTechnicalAssessment.test.jsx` | `ported` | to be ported: frontend/src/pages/Prism*.test.tsx | New upstream (6ed9d2a): test of the technical assessment card. |
| `frontend/src/components/Process.jsx` | `equivalent-exists` | frontend/src/content/site.ts (PROCESS) | The 7-step investment process is in content/site.ts but not rendered anywhere in FinLit. |
| `frontend/src/components/Reveal.jsx` | `equivalent-exists` | `frontend/src/components/Reveal.tsx` | Scroll reveal. |
| `frontend/src/components/Services.jsx` | `equivalent-exists` | frontend/src/pages/Home.tsx, pages/Services.tsx, content/site.ts (SERVICES) | Services summary. |
| `frontend/src/components/Testimonial.jsx` | `equivalent-exists` | frontend/src/content/site.ts (TESTIMONIAL) | The testimonial is in content/site.ts but not rendered anywhere in FinLit. |
| `frontend/src/components/ThemeProvider.jsx` | `equivalent-exists` | frontend/src/lib/ui.tsx (theme), public/theme-init.js | Light/dark theme. |
| `frontend/src/components/ThemeToggle.jsx` | `equivalent-exists` | frontend/src/components/Layout.tsx (theme button) | Theme toggle. |

### `frontend/src/components/FinLitAssistant`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/components/FinLitAssistant/AssistantMarkdown.jsx` | `equivalent-exists` | site-api/backend/server.py `plain_chat_text`, frontend/src/components/Assistant.tsx | Upstream renders the model's markdown in the bubble; FinLit asks for plain text and strips markdown server-side, so no renderer is needed. |
| `frontend/src/components/FinLitAssistant/AssistantMarkdown.test.jsx` | `equivalent-exists` | `site-api/backend/tests/test_chat.py::test_plain_chat_text_strips_markdown` | Test of the markdown renderer; FinLit tests the server-side stripping instead. |
| `frontend/src/components/FinLitAssistant/FinLitAssistant.css` | `equivalent-exists` | frontend/src/styles/site.css (assistant styles) | Assistant styles. |
| `frontend/src/components/FinLitAssistant/FinLitAssistant.jsx` | `equivalent-exists` | `frontend/src/components/Assistant.tsx` | Guided menu + free-text chat to `/api/chat`, same flow. |
| `frontend/src/components/FinLitAssistant/finlitAssistantData.js` | `equivalent-exists` | frontend/src/content/site.ts (ASSISTANT) | Assistant decision tree. FinLit's version omits the price list on purpose (prices are not published). |

### `frontend/src/components/blog`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/components/blog/CoverImage.jsx` | `equivalent-exists` | frontend/src/pages/Blog.tsx (cover), components/PageArt.tsx (CoverArt fallback) | Post cover image with fallback art. |

### `frontend/src/components/cms`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/components/cms/AdminRoute.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx (hasSession / AdminLogin) | Admin guard. FinLit exchanges the member session (with MFA) for the CMS token. |
| `frontend/src/components/cms/AdminShell.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx, pages/Console.tsx | Admin chrome. |
| `frontend/src/components/cms/ArticleContent.jsx` | `equivalent-exists` | frontend/src/pages/Blog.tsx (BlogPost, sanitised HTML) | Article renderer. |
| `frontend/src/components/cms/ContentEditor.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx (New article form) | PARTIAL. FinLit can create a text article draft, publish/unpublish and delete. Upstream-only: editing an existing item; PDF / spreadsheet / image resources (upload via `/api/content/admin/upload`); cover image upload or URL; author, slug, status on create; inline images. |
| `frontend/src/components/cms/RichTextEditor.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx (plain textarea) | PARTIAL. Upstream tiptap editor (bold, italic, underline, lists, quote, https links, inline image upload). FinLit: plain textarea, blank line = paragraph. |

### `frontend/src/components/ui`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/components/ui/accordion.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/alert-dialog.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/alert.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/aspect-ratio.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/avatar.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/badge.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/breadcrumb.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/button.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/calendar.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/card.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/carousel.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/checkbox.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/collapsible.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/command.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/context-menu.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/dialog.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/drawer.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/dropdown-menu.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/form.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/hover-card.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/input-otp.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/input.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/label.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/menubar.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/navigation-menu.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/pagination.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/popover.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/progress.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/radio-group.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/resizable.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/scroll-area.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/select.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/separator.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/sheet.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/skeleton.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/slider.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/sonner.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/switch.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/table.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/tabs.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/textarea.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/toast.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/toaster.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/toggle-group.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/toggle.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |
| `frontend/src/components/ui/tooltip.jsx` | `not-merged` | - | shadcn/ui (Radix) primitive for the CRA/Tailwind site. FinLit's React 19/TS site uses no shadcn/Radix/Tailwind; its own components and CSS (frontend/src/components, styles/) cover the same needs. |

### `frontend/src/constants/testIds`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/constants/testIds/auth.js` | `not-merged` | - | Emergent test-id constants; not imported by any upstream component. |
| `frontend/src/constants/testIds/home.js` | `not-merged` | - | Emergent test-id constants; not imported by any upstream component. |
| `frontend/src/constants/testIds/index.js` | `not-merged` | - | Emergent test-id constants; not imported by any upstream component. |

### `frontend/src/data`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/data/about.js` | `equivalent-exists` | frontend/src/content/site.ts (FOUNDER, PILLARS, PRINCIPLES) | About page content (FinLit rewrote the wording). |
| `frontend/src/data/companyClassifications.json` | `not-merged` | - | Sector/industry list used only by CompanyBrowser (see "features absent"). |
| `frontend/src/data/portfolio.generated.json` | `merged-identical` | `site-api/backend/portfolio_data/current.json` | Byte-identical (cmp). Upstream bundles it as the offline fallback; FinLit serves it from `/api/portfolio/report`. |
| `frontend/src/data/portfolio.js` | `equivalent-exists` | frontend/src/lib/siteApi.ts (PortfolioReport), content/site.ts (PROCESS, PILLARS) | Static portfolio fallback + home copy. FinLit has no bundled fallback (shows an error state if the site backend is down). |
| `frontend/src/data/services.js` | `equivalent-exists` | frontend/src/content/site.ts (SERVICES, PRICING with PRICE_TBA) | Services. Upstream publishes prices (First Session Rs 99 ... 1 Year Rs 2,499); FinLit deliberately does not. |

### `frontend/src/hooks`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/hooks/use-toast.js` | `equivalent-exists` | frontend/src/lib/ui.tsx (toast) | shadcn toast hook; FinLit has its own toast. |
| `frontend/src/hooks/usePortfolioData.js` | `equivalent-exists` | frontend/src/pages/Portfolio.tsx (useQuery getPortfolio) | Portfolio fetch. Upstream merges with the bundled fallback; FinLit does not. |
| `frontend/src/hooks/usePremiumReport.js` | `ported` | to be ported: frontend/src/lib/prism.ts | New upstream (6ed9d2a): the report workflow hook extracted from the page (generation, restore, download). |
| `frontend/src/hooks/usePremiumReport.test.jsx` | `ported` | to be ported: frontend/src/lib/prism.test.ts | New upstream (6ed9d2a): tests of that hook. |

### `frontend/src/lib`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/lib/cms.js` | `equivalent-exists` | frontend/src/pages/Admin.tsx (adminFetch), lib/siteApi.ts | CMS token + requests. The change since 67aab4f (`responseType: "blob"` for the premium PDF) is replaced by the research API PDF route (to be ported: frontend/src/lib/prism.ts). |
| `frontend/src/lib/currentPremiumReport.js` | `ported` | to be ported: frontend/src/lib/prism.ts | Keeps the signed snapshot of the current report in sessionStorage for the PDF. By CONTRACT.md the snapshot stays server-side (Redis `prism:snap:{id}`, 30 min) and the browser only gets `pdfAvailableUntil`; the expiry logic moves there. |
| `frontend/src/lib/currentPremiumReport.test.js` | `ported` | to be ported: frontend/src/lib/prism.test.ts | Tests snapshot expiry / reuse; to be re-expressed against `pdfAvailableUntil` and the 410 "expired" answer. |
| `frontend/src/lib/fundamentalGrowth.js` | `equivalent-exists` | frontend/src/stock/Sections*.tsx (YoY growth by line) | Growth maths for IncomeGrowthView (YoY/QoQ with missing-value reasons). See IncomeGrowthView. |
| `frontend/src/lib/fundamentalGrowth.test.js` | `equivalent-exists` | `frontend/src/lib/qresults.test.ts` | Tests of the growth maths; FinLit tests its own quarter maths. |
| `frontend/src/lib/premiumReportDownload.js` | `ported` | to be ported: frontend/src/lib/prism.ts | New upstream (6ed9d2a): signed-snapshot PDF download request; FinLit downloads through `/api/prism/reports/{id}/pdf`. |
| `frontend/src/lib/premiumReportDownload.test.js` | `ported` | to be ported: frontend/src/lib/prism.test.ts | New upstream (6ed9d2a): tests of that download helper. |
| `frontend/src/lib/premiumReportPolling.js` | `ported` | to be ported: frontend/src/lib/prism.ts / backend/finlit/prism.py | Polls `state: generating` with back-off on 408/429/5xx. CONTRACT.md uses inline delivery (the research API waits), so the retry/back-off behaviour moves to the research API call and the page's 429/502/503 handling. |
| `frontend/src/lib/premiumReportPolling.test.js` | `ported` | to be ported: frontend/src/lib/prism.test.ts | Tests of the polling/back-off; to be re-expressed for the inline flow. |
| `frontend/src/lib/premiumReportReview.js` | `ported` | to be ported: frontend/src/lib/prism.ts | Builds pros/cons from metrics for older reports without `review`. Server always returns `review` (premium_presentation.build_report_review); keep the fallback for stored rows. |
| `frontend/src/lib/premiumReportReview.test.js` | `ported` | to be ported: frontend/src/lib/prism.test.ts | Test of the review fallback. |
| `frontend/src/lib/utils.js` | `not-merged` | - | shadcn `cn()` class-name helper (clsx + tailwind-merge). |

### `frontend/src/pages`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `frontend/src/pages/AboutPage.jsx` | `equivalent-exists` | `frontend/src/pages/About.tsx` | About. |
| `frontend/src/pages/BlogAdminEditPage.jsx` | `equivalent-exists` | `frontend/src/pages/Admin.tsx` | PARTIAL: FinLit cannot edit an existing item (only publish/unpublish/delete). See features absent. |
| `frontend/src/pages/BlogAdminLoginPage.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx (AdminLogin), pages/Login.tsx | FinLit: member sign-in with MFA, then CMS token; password-only CMS login is off unless `CMS_PASSWORD_LOGIN=1`. |
| `frontend/src/pages/BlogAdminNewPage.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx (New article) | PARTIAL: text articles only (see ContentEditor). |
| `frontend/src/pages/BlogAdminPage.jsx` | `equivalent-exists` | frontend/src/pages/Admin.tsx, pages/Console.tsx, pages/Premium.tsx | PARTIAL. FinLit lists content, contact messages and enquiries and links the Gold dashboards. Upstream-only: content search and status/type filter; the portfolio statement upload (`/api/portfolio/admin/upload`, `/api/portfolio/admin/report`) that refreshes /portfolio. The "Premium Report" link added since 67aab4f becomes the Prism entry (to be ported: nav.ts / Premium.tsx). |
| `frontend/src/pages/BlogAdminPreviewPage.jsx` | `equivalent-exists` | frontend/src/pages/Blog.tsx (BlogPost, published items only) | PARTIAL: no admin preview of a draft in FinLit. |
| `frontend/src/pages/BlogDetailPage.jsx` | `equivalent-exists` | frontend/src/pages/Blog.tsx (BlogPost) | Article / PDF / image / download. |
| `frontend/src/pages/BlogPage.jsx` | `equivalent-exists` | frontend/src/pages/Blog.tsx (Blog) | List with type filter and search. |
| `frontend/src/pages/ContactPage.jsx` | `equivalent-exists` | `frontend/src/pages/Contact.tsx` | Contact page (see Contact.jsx for the investment-size field). |
| `frontend/src/pages/FinancialProductPage.jsx` | `not-merged` | - | "Financial Product - Coming soon" placeholder page at `/financial-product`; no content. |
| `frontend/src/pages/Home.jsx` | `equivalent-exists` | `frontend/src/pages/Home.tsx` | Home. FinLit's redesigned home does not include upstream's Performance, Process, Philosophy and Testimonial sections (content kept in content/site.ts). |
| `frontend/src/pages/MarketsPage.jsx` | `equivalent-exists` | `frontend/src/pages/Markets.tsx` | Market Events & Index Dashboard (IPO, results, announcements, transcripts, commodities, indices, index valuation) through `/api/premium/markets/*`; Gold instead of admin-only. |
| `frontend/src/pages/PortfolioPage.jsx` | `equivalent-exists` | `frontend/src/pages/Portfolio.tsx` | Realised P&L report. |
| `frontend/src/pages/PremiumReportPage.jsx` | `ported` | to be ported: frontend/src/pages/Prism.tsx + PrismReport.tsx (routes /prism, /prism/:symbol) | The premium report page (generate, statement choice, score parts, completeness, data freshness, business performance, pros/cons, review notes, financial history, PDF). Not the same as FinLit's existing `pages/PremiumReport.tsx` (FinLit-score printable report). Changed again upstream in 6ed9d2a (page split into hook + detail component). |
| `frontend/src/components/PremiumReportDetail.test.jsx` | `ported` | to be ported: frontend/src/pages/Prism*.test.tsx | Renamed upstream from `pages/PremiumReportPage.test.jsx` (6ed9d2a): rendering, NOT RATED and PDF tests now target the extracted detail component. |
| `frontend/src/pages/ServicesPage.jsx` | `equivalent-exists` | frontend/src/pages/Services.tsx, components/Enquiry.tsx | Services + enquiry to `/api/service-enquiry`. Prices intentionally not shown in FinLit. |
| `frontend/src/pages/StockFundamentalsAdminPage.jsx` | `equivalent-exists` | frontend/src/pages/Fundamentals.tsx (+ stock/StockPage.tsx) | PARTIAL. FinLit's Gold "Stock Fundamental Data Dashboard" has snapshot, P&L, balance sheet, cash flow, ratios, profitability ratios, revenue segments, shareholding (pattern, structure, pledge, named holders), peers and corporate actions via `/api/premium/fundamentals`; price chart, returns, insights and data quality come from the research API on the stock page. Upstream-only: Bank Asset Quality (GNPA, NNPA, CET1), Data Quality Flags (FinEdge vs fallback provider disagreements), Dev Metrics (fetch timing), sector/industry company browser, the P&L "Growth %" YoY/QoQ view (added since 67aab4f), and the Stock DNA / Valuation / Quality / Technicals key-factor panels built from FinEdge highlights. |
| `frontend/src/pages/WhatWeDoPage.jsx` | `equivalent-exists` | frontend/src/pages/Why.tsx, content/site.ts (WHY) | Why we exist. |

### `memory`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `memory/.gitkeep` | `not-merged` | - | Emergent agent memory folder placeholder (empty). |
| `memory/PRD.md` | `not-merged` | - | Emergent agent product brief for the original PMS site. Not product code. |

### `test_reports`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `test_reports/.gitkeep` | `not-merged` | - | Upstream test report folder placeholder (empty). |
| `test_reports/iteration_1.json` | `not-merged` | - | Upstream Emergent test report (generated). |
| `test_reports/iteration_2.json` | `not-merged` | - | Upstream Emergent test report (generated). |
| `test_reports/iteration_3.json` | `not-merged` | - | Upstream Emergent test report (generated). |

### `test_reports/pytest`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `test_reports/pytest/.gitkeep` | `not-merged` | - | Upstream test report folder placeholder (empty). |
| `test_reports/pytest/pytest_results.xml` | `not-merged` | - | Upstream pytest JUnit output (generated). |

### `tests`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `tests/__init__.py` | `not-merged` | - | Empty root `tests` package; upstream has no root tests in it. |

### `tmp/pdfs`

| Upstream path | Status | FinLit location | Note |
| --- | --- | --- | --- |
| `tmp/pdfs/realized_pnl-01.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-02.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-03.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-04.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-05.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-06.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-07.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-08.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-09.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-10.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-11.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-12.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-13.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-14.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-15.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-16.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-17.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-18.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-19.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-20.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-21.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |
| `tmp/pdfs/realized_pnl-22.png` | `not-merged` | - | Generated page render of the personal broker statement (realised P&L). Upstream itself now ignores `/tmp/`. |

## 2. Line-level proof for the three-way merged files

Method: for each file, the non-blank, whitespace-normalised `+`/`-` lines of `git diff 67aab4f HEAD -- backend/<file>` (upstream) and of upstream 67aab4f -> FinLit `1346489^:site-api/backend/<file>` (FinLit-local) were checked against the merged `site-api/backend/<file>`: every added line must be present (as many times as the change requires), no removed line may come back, and for every line the merged count must equal FinLit + upstream - base. Independently, a fresh `git merge-file -p` of (FinLit pre-merge, 67aab4f, upstream HEAD) was compared byte-for-byte with the merged file.

Which files really had both sides changed (all `site-api/backend` files classified base / FinLit / upstream / merged):

* both changed: `server.py`, `requirements.txt` -> merged-3way
* only upstream changed: `tests/conftest.py` -> result equals upstream HEAD (byte-identical)
* only FinLit changed: `tests/test_api.py`, `tests/test_chat.py`, `tests/test_portfolio_report.py`, `tests/test_service_enquiry.py` -> result equals FinLit pre-merge (upstream HEAD content all present)
* every other upstream backend file: unchanged on both sides or new upstream, byte-identical (section 3)
* FinLit-only: `portfolio_data/sources/.gitkeep` (kept); upstream-only: the two broker PDFs (not merged)

Result: **no missing line, nothing to fix.**

```
=== server.py
  upstream 67aab4f..HEAD: +357 / -43 non-blank lines;  FinLit-local: +75 / -13
  upstream added lines present in merged: 357/357
  FinLit-local added lines present in merged: 75/75
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== requirements.txt
  upstream 67aab4f..HEAD: +1 / -0 non-blank lines;  FinLit-local: +5 / -4
  upstream added lines present in merged: 1/1
  FinLit-local added lines present in merged: 5/5
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== tests/conftest.py
  upstream 67aab4f..HEAD: +6 / -2 non-blank lines;  FinLit-local: +0 / -0
  upstream added lines present in merged: 6/6
  FinLit-local added lines present in merged: 0/0
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== tests/test_api.py
  upstream 67aab4f..HEAD: +0 / -0 non-blank lines;  FinLit-local: +8 / -0
  upstream added lines present in merged: 0/0
  FinLit-local added lines present in merged: 8/8
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== tests/test_chat.py
  upstream 67aab4f..HEAD: +0 / -0 non-blank lines;  FinLit-local: +5 / -0
  upstream added lines present in merged: 0/0
  FinLit-local added lines present in merged: 5/5
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== tests/test_portfolio_report.py
  upstream 67aab4f..HEAD: +0 / -0 non-blank lines;  FinLit-local: +3 / -0
  upstream added lines present in merged: 0/0
  FinLit-local added lines present in merged: 3/3
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
=== tests/test_service_enquiry.py
  upstream 67aab4f..HEAD: +0 / -0 non-blank lines;  FinLit-local: +6 / -0
  upstream added lines present in merged: 0/0
  FinLit-local added lines present in merged: 6/6
  upstream-removed lines resurrected: 0;  local-removed lines resurrected: 0
  multiset deviations (M != L+T-B): 0
  fresh git merge-file: conflicts=0 byte-identical-to-merged=True
TOTAL {'up_added': 364, 'up_present': 364, 'loc_added': 102, 'loc_present': 102, 'up_removed': 45, 'loc_removed': 17, 'deviations': 0}
```

Semantic check: none of the 357 upstream lines added to `server.py` calls a function FinLit replaced (`read_current_portfolio_report`, `stored_asset_path`, chat/CMS login code); the new routes are all under `require_admin`.

### 2b. Second merge, 26 October: upstream b112ba1..6ed9d2a (48 files: 34 backend, 4 model docs, 10 frontend)

Classification (`site-api/backend/<f>` against upstream `b112ba1:backend/<f>` with `cmp`): of the 34 changed or new upstream backend files, **33 were never modified by FinLit** (21 changed upstream, 12 new) and
were replaced by upstream 6ed9d2a (byte-identical, section 3b); only `server.py` was changed on both sides and went through
`git merge-file` (base = `b112ba1:backend/server.py`, ours = FinLit main, theirs = `6ed9d2a:backend/server.py`). Upstream changed no `requirements.txt` in this range, so none was merged, and no fixture file changed.
The one conflict was resolved keeping both intents: FinLit's `_remember_stock_fundamentals(cache_key, ...)` (bounded cache, replaces upstream's direct
dictionary store) stays, and upstream's three added `model_inputs[...]` lines (`technicalPrices`, `leverage`, `secondaryLeverage`) are placed before it.

Proof (non-blank, whitespace-normalised lines; `M != L+T-B` compares the merged file with the multiset ours + theirs - base):

```
upstream 6ed9d2a vs b112ba1: +26 / -0 non-blank lines
FinLit-local vs b112ba1:     +148 / -18
upstream added lines present in merged: 26/26
FinLit-local added lines present in merged: 148/148
upstream-removed lines still in merged beyond FinLit's own copies: 0
multiset deviations (M != L+T-B): 0
lines only in merged: []  only in expected: []
```

Semantic check: the 26 upstream lines only add the technical-candle and benchmark capture, two model inputs and the `ZoneInfo` import; none calls a function FinLit replaced.
`premium_service.py` and `premium_pdf.py` (the signed snapshot now carries `technicalAssessment`; the PDF renders it without provider calls) are byte-identical to upstream.

## 3. Byte identity

`cmp` of every `merged-identical` pair (60 files):

```
OK   backend/benchmark_resolution.py == site-api/backend/benchmark_resolution.py
OK   backend/content_uploads/05aba463-c278-429c-9d35-74b5c402d0ff.png == site-api/backend/content_uploads/05aba463-c278-429c-9d35-74b5c402d0ff.png
OK   backend/content_uploads/0ea1ecb5-2c2a-4a57-823e-cc18c7693381.pdf == site-api/backend/content_uploads/0ea1ecb5-2c2a-4a57-823e-cc18c7693381.pdf
OK   backend/content_uploads/36403c97-4374-40ed-8f29-f50aa74c6f65.pdf == site-api/backend/content_uploads/36403c97-4374-40ed-8f29-f50aa74c6f65.pdf
OK   backend/content_uploads/8aa9754b-be3c-4aa5-894c-2f1ac9138157.pdf == site-api/backend/content_uploads/8aa9754b-be3c-4aa5-894c-2f1ac9138157.pdf
OK   backend/content_uploads/bce3ac2f-d9d2-4442-af10-977bb972d6fd.png == site-api/backend/content_uploads/bce3ac2f-d9d2-4442-af10-977bb972d6fd.png
OK   backend/content_uploads/ca7a96fc-6d8c-473f-8f50-c0d238305fbb.png == site-api/backend/content_uploads/ca7a96fc-6d8c-473f-8f50-c0d238305fbb.png
OK   backend/content_uploads/dcfbc8a8-935b-4d2a-b164-84766a8e5745.xlsx == site-api/backend/content_uploads/dcfbc8a8-935b-4d2a-b164-84766a8e5745.xlsx
OK   backend/content_uploads/f4d11a2a-07bd-40e4-b265-7862cf7e102c.png == site-api/backend/content_uploads/f4d11a2a-07bd-40e4-b265-7862cf7e102c.png
OK   backend/email_service.py == site-api/backend/email_service.py
OK   backend/financial_fields.py == site-api/backend/financial_fields.py
OK   backend/fundamental_resolution.py == site-api/backend/fundamental_resolution.py
OK   backend/generate_portfolio_data.py == site-api/backend/generate_portfolio_data.py
OK   backend/market_data.py == site-api/backend/market_data.py
OK   backend/portfolio_data/current.json == site-api/backend/portfolio_data/current.json
OK   backend/portfolio_report.py == site-api/backend/portfolio_report.py
OK   backend/premium_completeness.py == site-api/backend/premium_completeness.py
OK   backend/premium_data.py == site-api/backend/premium_data.py
OK   backend/premium_engine.py == site-api/backend/premium_engine.py
OK   backend/premium_model_config.py == site-api/backend/premium_model_config.py
OK   backend/premium_pdf.py == site-api/backend/premium_pdf.py
OK   backend/premium_presentation.py == site-api/backend/premium_presentation.py
OK   backend/premium_service.py == site-api/backend/premium_service.py
OK   backend/premium_snapshot.py == site-api/backend/premium_snapshot.py
OK   backend/premium_trace.py == site-api/backend/premium_trace.py
OK   backend/pytest.ini == site-api/backend/pytest.ini
OK   backend/stock_dashboard_audit.py == site-api/backend/stock_dashboard_audit.py
OK   backend/tests/conftest.py == site-api/backend/tests/conftest.py
OK   backend/tests/fixtures/premium_owner_parity.json == site-api/backend/tests/fixtures/premium_owner_parity.json
OK   backend/tests/fixtures/premium_reconciliation_2026_10_18.json == site-api/backend/tests/fixtures/premium_reconciliation_2026_10_18.json
OK   backend/tests/fixtures/premium_reliance_screenshot.json == site-api/backend/tests/fixtures/premium_reliance_screenshot.json
OK   backend/tests/fixtures/premium_stock_audit_2026_10_18.json == site-api/backend/tests/fixtures/premium_stock_audit_2026_10_18.json
OK   backend/tests/premium_example.json == site-api/backend/tests/premium_example.json
OK   backend/tests/test_assessment_data_recovery.py == site-api/backend/tests/test_assessment_data_recovery.py
OK   backend/tests/test_email_service.py == site-api/backend/tests/test_email_service.py
OK   backend/tests/test_flagged_company_lookup.py == site-api/backend/tests/test_flagged_company_lookup.py
OK   backend/tests/test_fourth_quarter_recovery.py == site-api/backend/tests/test_fourth_quarter_recovery.py
OK   backend/tests/test_market_data.py == site-api/backend/tests/test_market_data.py
OK   backend/tests/test_premium_accuracy.py == site-api/backend/tests/test_premium_accuracy.py
OK   backend/tests/test_premium_bank_fallbacks.py == site-api/backend/tests/test_premium_bank_fallbacks.py
OK   backend/tests/test_premium_cagr_windows.py == site-api/backend/tests/test_premium_cagr_windows.py
OK   backend/tests/test_premium_completeness.py == site-api/backend/tests/test_premium_completeness.py
OK   backend/tests/test_premium_loss_rules.py == site-api/backend/tests/test_premium_loss_rules.py
OK   backend/tests/test_premium_presentation.py == site-api/backend/tests/test_premium_presentation.py
OK   backend/tests/test_premium_recovery.py == site-api/backend/tests/test_premium_recovery.py
OK   backend/tests/test_premium_reports.py == site-api/backend/tests/test_premium_reports.py
OK   backend/tests/test_premium_serverless.py == site-api/backend/tests/test_premium_serverless.py
OK   backend/tests/test_premium_shared_sources.py == site-api/backend/tests/test_premium_shared_sources.py
OK   backend/tests/test_premium_trace.py == site-api/backend/tests/test_premium_trace.py
OK   backend/tests/test_required_input_recovery.py == site-api/backend/tests/test_required_input_recovery.py
OK   backend/tests/test_stock_classification_search.py == site-api/backend/tests/test_stock_classification_search.py
OK   backend/tests/test_stock_fundamental_normalization.py == site-api/backend/tests/test_stock_fundamental_normalization.py
OK   backend/tests/test_valuation_benchmarks.py == site-api/backend/tests/test_valuation_benchmarks.py
OK   backend/vercel.json == site-api/backend/vercel.json
OK   docs/portfolio-updates-summary.md == docs/prism/portfolio-updates-summary.md
OK   docs/premium-model-implementation.md == docs/prism/premium-model-implementation.md
OK   docs/premium-model-input-output.md == docs/prism/premium-model-input-output.md
OK   docs/premium-report-lifecycle.md == docs/prism/premium-report-lifecycle.md
OK   frontend/src/assets/brand/finlit-logo-transparent.png == frontend/public/brand/finlit-logo.png
OK   frontend/src/data/portfolio.generated.json == site-api/backend/portfolio_data/current.json
cmp identical: 60  differing: 0
```

### 3b. Byte identity after the 26 October merge

`cmp` of the 33 backend files replaced or added and the 4 model docs against upstream 6ed9d2a:

```
OK   backend/benchmark_resolution.py == site-api/backend/benchmark_resolution.py
OK   backend/financial_records.py == site-api/backend/financial_records.py
OK   backend/fundamental_resolution.py == site-api/backend/fundamental_resolution.py
OK   backend/premium_benchmarks.py == site-api/backend/premium_benchmarks.py
OK   backend/premium_classification.py == site-api/backend/premium_classification.py
OK   backend/premium_completeness.py == site-api/backend/premium_completeness.py
OK   backend/premium_data.py == site-api/backend/premium_data.py
OK   backend/premium_engine.py == site-api/backend/premium_engine.py
OK   backend/premium_model_config.py == site-api/backend/premium_model_config.py
OK   backend/premium_pdf.py == site-api/backend/premium_pdf.py
OK   backend/premium_presentation.py == site-api/backend/premium_presentation.py
OK   backend/premium_provider.py == site-api/backend/premium_provider.py
OK   backend/premium_service.py == site-api/backend/premium_service.py
OK   backend/premium_technical.py == site-api/backend/premium_technical.py
OK   backend/premium_technical_sources.py == site-api/backend/premium_technical_sources.py
OK   backend/premium_trace.py == site-api/backend/premium_trace.py
OK   backend/technical_patterns.py == site-api/backend/technical_patterns.py
OK   backend/technical_scoring.py == site-api/backend/technical_scoring.py
OK   backend/technical_series.py == site-api/backend/technical_series.py
OK   backend/tests/test_assessment_data_recovery.py == site-api/backend/tests/test_assessment_data_recovery.py
OK   backend/tests/test_flagged_company_lookup.py == site-api/backend/tests/test_flagged_company_lookup.py
OK   backend/tests/test_premium_accuracy.py == site-api/backend/tests/test_premium_accuracy.py
OK   backend/tests/test_premium_bank_fallbacks.py == site-api/backend/tests/test_premium_bank_fallbacks.py
OK   backend/tests/test_premium_cagr_windows.py == site-api/backend/tests/test_premium_cagr_windows.py
OK   backend/tests/test_premium_completeness.py == site-api/backend/tests/test_premium_completeness.py
OK   backend/tests/test_premium_insurance_leverage.py == site-api/backend/tests/test_premium_insurance_leverage.py
OK   backend/tests/test_premium_loss_rules.py == site-api/backend/tests/test_premium_loss_rules.py
OK   backend/tests/test_premium_reports.py == site-api/backend/tests/test_premium_reports.py
OK   backend/tests/test_premium_shared_sources.py == site-api/backend/tests/test_premium_shared_sources.py
OK   backend/tests/test_premium_technical.py == site-api/backend/tests/test_premium_technical.py
OK   backend/tests/test_premium_technical_sources.py == site-api/backend/tests/test_premium_technical_sources.py
OK   backend/tests/test_premium_trace.py == site-api/backend/tests/test_premium_trace.py
OK   backend/tests/test_valuation_benchmarks.py == site-api/backend/tests/test_valuation_benchmarks.py
OK   docs/premium-model-implementation.md == docs/prism/premium-model-implementation.md
OK   docs/premium-model-input-output.md == docs/prism/premium-model-input-output.md
OK   docs/premium-report-lifecycle.md == docs/prism/premium-report-lifecycle.md
OK   docs/premium-st-lt-model.md == docs/prism/premium-st-lt-model.md
cmp identical: 37  differing: 0
```

## 4. Tests

Site backend, full suite after the 26 October merge (`cd site-api && PYTHONPATH=.:backend <site-venv>/bin/python -m pytest -q -n 4 -c backend/pytest.ini backend/tests`):

```
499 passed, 1 skipped, 36 warnings
SKIPPED [1] backend/tests/test_portfolio_report.py:11: source statement not present   (the broker PDF that was deliberately not added)
```

Upstream's documented model regression list (docs/prism/premium-model-implementation.md, "Run the relevant regression suites"), run against the FinLit copy: `457 passed`.
(The first merge, at b112ba1, recorded 446 passed, 1 skipped for the whole suite and 408 for this list.) New upstream tests this time: `test_premium_technical.py`,
`test_premium_technical_sources.py`, `test_premium_insurance_leverage.py`; 11 upstream test files were updated for the module split and 3.6.10.

Research API (`backend/tests/test_prism.py`, real Postgres and Redis): 42 passed (5 new tests for `technicalAssessment`, and the two 3.6.9 version asserts became 3.6.10).

The frontend half of that list is tested by the frontend task (vitest); the upstream CRA tests it mirrors are listed in section 1 as `ported`.

## 5. Dependencies in production

Third-party imports of `site-api/backend` (all modules and tests): fastapi, starlette, pydantic, motor, pymongo, bcrypt, jwt (PyJWT), dotenv, requests, pypdf, nh3, resend, google-genai, **reportlab** (new, premium_pdf.py), pytest; `zoneinfo` needs tzdata. All are in `site-api/backend/requirements.txt` (reportlab pulls Pillow and charset-normalizer). Installed in the test venv: reportlab 4.5.1, PyJWT 2.15.1, pypdf 6.21.2, Pillow 13.0.0.

Every production path installs that file, so reportlab reaches production with no deploy change:

* `Dockerfile` (Render single image, render.yaml): `/opt/site-venv/bin/pip install -r site-api/backend/requirements.txt` (Python 3.13), copies all of `site-api/backend`.
* `deploy/site-api/Dockerfile` (docker-compose.prod/staging): `pip install -r requirements.txt` from `site-api/backend` (Python 3.12), `COPY . .`.
* `.github/workflows/ci.yml` job `site-api`: `pip install -r site-api/backend/requirements.txt mongomock-motor` and runs the whole suite (Python 3.12), so the new model tests run in CI.
* `.github/workflows/security.yml`: `pip-audit --strict -r site-api/backend/requirements.txt` now also audits reportlab (and Pillow). pip-audit is not installed here, so this was not run locally.

The research API (`backend/requirements.txt`) needs nothing new for the Prism hop: it already signs the HS256 CMS token without PyJWT (`backend/finlit/auth/routes.py`, `backend/finlit/premium.py`). The new model modules read no new environment variable (the snapshot is signed with the existing `CMS_JWT_SECRET`; data uses the existing `FINEDGE_API_KEY` / `UPSTOX_ACCESS_TOKEN`). The 26 October merge adds no dependency and no variable either (`requirements.txt` unchanged upstream); in practice the ST/LT technical assessment needs `UPSTOX_ACCESS_TOKEN` for complete candles, see `DEPLOY.md`.

Gaps: **none blocking.** Notes for the deploy owner: (a) `deploy/render-start.sh` can start the site backend through `dev/site_api_dev.py`, which imports `mongomock_motor`, but that package is not in `site-api/backend/requirements.txt` (only CI installs it), so that fallback path would fail in the image; this predates the merge. (b) `site-api/backend/vercel.json` is inert outside Vercel. (c) The premium PDF uses ReportLab's built-in fonts only, so no system font package is needed in the slim images.
