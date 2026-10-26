# FinLit Prism: deployment and configuration

How FinLit Prism (the Gold plan's financial-health rating, see [CONTRACT.md](CONTRACT.md)) runs in production, what it needs, and how
the owner switches it on. For the report flow itself read [premium-report-lifecycle.md](premium-report-lifecycle.md).

**Still to come in this document:** the model's technical part (how the score is built, inputs, versioning rules) will be added later.
For now the engineering references are [premium-model-implementation.md](premium-model-implementation.md) and
[premium-model-input-output.md](premium-model-input-output.md).

**Model version.** Every report carries the version of the model that calculated it in `rating.modelVersion` (and `baselineVersion`,
`fillVersion`); the research API also keeps it in the `model_version` column of `prism_reports` and shows it in `GET /api/prism/status`.
A stored report from an older version is recognised by comparing its `modelVersion` with the current one, and is recalculated
rather than edited (a signed snapshot is never upgraded in place).

## What runs where (production = one Render free container, 512 MB)

```
Render web service "finlit"  (deploy/render-start.sh)
 |- research API + website        :8000   python 3.13, /usr/local            ~ memory of its own
 |- site backend (uvicorn)        :8001   python 3.13, /opt/site-venv        ~ 90 MB idle, ~100 MB while generating
 |- scheduler / background jobs
```

The research API calls the site backend at `SITE_API_URL` (`http://127.0.0.1:8001`, set by `render-start.sh`) with a 5-minute
token signed by `CMS_JWT_SECRET`. The site backend loads company data from FinEdge (and Upstox for gaps), calculates the rating, and signs
a 30-minute snapshot that the PDF needs.

`render-start.sh` starts the site backend when **any** of these holds (and `SITE_API_URL` is not already set to an outside host):

| Condition | Result |
| --- | --- |
| `MONGO_URL` is set | Starts; blog/CMS, portfolio uploads, forms, chat and Prism all work. |
| no `MONGO_URL`, but `FINEDGE_API_KEY` set and `CMS_JWT_SECRET` has 32+ characters | Starts without MongoDB: **Prism and Gold market data work**; the blog index stays empty, the portfolio page shows the report shipped with the code, forms and CMS admin answer `503 "...its content database is not connected"` at once (no waiting). |
| otherwise | Not started (Prism says "not connected"). The log line `[site-api] not started: ...` says why. |
| `SITE_API_START=never` | Never started (saves ~90 MB). `SITE_API_START=always` starts it regardless. |

## Environment variables

Set in the Render dashboard (Environment tab) unless marked `render.yaml`. `sync: false` means typed by hand; nothing secret is in the repository.

| Variable | Used by | Needed for Prism? | When missing or wrong |
| --- | --- | --- | --- |
| `FINEDGE_API_KEY` | site backend (and research API) | **Yes** | Every report fails with 503 "FinEdge API is not configured". With no `MONGO_URL` either, the site backend is not started at all. |
| `CMS_JWT_SECRET` | research API **and** site backend (same value; `render.yaml` generates it) | **Yes**, 32+ bytes | Shorter than 32 bytes or empty: the site backend refuses every Prism call (503 "CMS authentication is not securely configured") and `GET /api/prism/status` reports Prism as not connected. It also signs the PDF snapshot, so changing it invalidates snapshots made before the change (users just recalculate). |
| `DATABASE_URL` (Neon Postgres) | research API | **Yes** | Stored reports (`prism_reports`, migration `063_prism_reports.sql`) need it; it is already required by the whole site. |
| `REDIS_URL` | research API | **Yes** | Snapshots for the PDF (30 min) and limits live there (`render.yaml` links the free Redis). |
| `SITE_API_URL` | research API | Set automatically | Leave blank on Render. Set only for a site backend hosted elsewhere (then also set the variables above on that host). |
| `UPSTOX_ACCESS_TOKEN` (`sync: false`) | site backend | Optional | Without it there is no second-source recovery of missing statement years and no ticker strip; reports still calculate from FinEdge and say what was missing. The token expires daily; Upstox needs it renewed. |
| `MONGO_URL`, `DB_NAME` | site backend | No | Blog/CMS/forms off, see above. `DB_NAME` defaults to `finlit`. |
| `PREMIUM_GENERATION_SLOTS` (`render.yaml`: 1) | site backend | Tuning | Reports calculated at once in the site backend, 1 to 4, default 2 when unset. `render.yaml` sets 1 for the 512 MB plan. |
| `STOCK_FUNDAMENTALS_CACHE_ENTRIES` (`render.yaml`: 32) | site backend | Tuning | How many resolved provider answers (each report uses 2 to 4, ~40 KB each, 15 minutes) are kept; oldest dropped first. Default 32, range 4 to 2000. |
| `SITE_API_START` (`render.yaml`: auto) | `deploy/render-start.sh` | Tuning | `auto`, `never`, `always` as in the table above. |
| `CMS_ADMIN_EMAIL`, `CMS_ADMIN_PASSWORD_HASH` or `CMS_PASSWORD_LOGIN` | site backend | No | Only the site's own CMS password login; administrators use `POST /api/me/cms-token`. |
| `ALLOWED_HOSTS`, `CORS_ORIGINS` | site backend | No | Defaults accept `localhost` and `127.0.0.1`, which is all the research API needs inside the container. |

The research API's own limits (20 reports a member a day, 2 generations at once) are in the research API; this page covers the site backend.

## How to turn Prism on (owner checklist)

1. **Render dashboard, service `finlit`, Environment.** Check `FINEDGE_API_KEY` is set (it already is for the stock pages) and that
   `CMS_JWT_SECRET` exists (generated by the blueprint; it must be 32+ characters, which generated values are).
2. Optional: add `UPSTOX_ACCESS_TOKEN` (fresh each day) for the second data source.
3. Keep `PREMIUM_GENERATION_SLOTS=1` on the free plan. Raise it only on a plan with more memory.
4. Leave `MONGO_URL` out if you do not use the blog/CMS yet; Prism runs without it. Set it later and restart to switch those pages on.
5. **Redeploy** (the service must be running; it is currently suspended and must be resumed first). In the log look for
   `[site-api] starting ...` (and `Application startup complete`), then the research API starting.
6. Check `https://<your-site>/api/prism/status`: `"available": true` and a `modelVersion`.
7. Sign in as the Gold demo (`demo-gold@finlit-demo.com`) or the administrator, open `/prism`, generate a report for a large company
   (for example RELIANCE or TCS), download the PDF.
8. If `available` is false, the `reason` and the `[site-api]` log lines tell which of the above is missing.

## Memory and time (measured)

On the recorded FinEdge answers (`site-api/backend/tests/fixtures/premium_stock_audit_2026_10_18.json`, 8 companies), Python 3.13,
`MALLOC_ARENA_MAX=2`, the real uvicorn process of the site backend, no MongoDB:

| | Measured |
| --- | --- |
| Resident memory right after start (idle) | 86 to 88 MB |
| After 8 different reports and their PDFs | 98.7 MB |
| 4 reports and PDFs at the same time, 16 in a row | 101 MB peak |
| Cost of one report beyond idle | about 1 to 2 MB (the PDF renderer does not spike; PDFs are 13 to 15 KB) |
| Scoring + trace + review (pure engine) | about 1 ms |
| Dashboard loader + model on recorded data | 170 to 310 ms |
| PDF render | 30 to 90 ms (first call about 190 ms) |
| Snapshot (kept 30 minutes, never in the browser) | 45 to 62 KB |

In production the time is dominated by FinEdge/Upstox calls (the research API plans for 60 to 120 seconds per report), not by CPU or memory. Memory is
therefore bounded by the process base (about 90 MB) plus the provider-data cache (`STOCK_FUNDAMENTALS_CACHE_ENTRIES`, at most ~1.5 MB at 32)
plus the number of simultaneous reports; a second slot costs only a few MB, so the limit of 1 is a safety margin for the shared 512 MB,
not a measured need. These numbers use recorded data without network waiting; a live check on the deployed service is still to be done once it is resumed.

## Image and dependencies

`Dockerfile` builds `/opt/site-venv` from `site-api/backend/requirements.txt` (reportlab, PyJWT, pypdf, motor, fastapi, ...). Nothing extra
is installed for Prism. `pip-audit --strict -r site-api/backend/requirements.txt` (the `Security` workflow) reports no known
vulnerabilities for the current pins.

## Local development

`dev/run_stack.sh` starts the site backend with the recorded FinEdge answers (no provider keys) when `FINEDGE_API_KEY` is empty or `dev`:

```bash
dev/run_stack.sh                      # fixtures: Prism works for RELIANCE, TCS, MARUTI, NTPC, DLF, HDFCBANK, BAJFINANCE, HDFCLIFE
SITE_PY=/path/to/site-venv/bin/python dev/run_stack.sh
# only the site backend, without MongoDB, as production runs it when MONGO_URL is unset:
site-venv/bin/python dev/site_api_dev.py --backend site-api/backend --port 8001 --no-mongo
```

Limits of the fixtures: only those eight companies resolve (anything else is "not found"); standalone answers with the consolidated
figures; no industry peers (valuation medians come from the recorded ratios or group fills); no Upstox. The model, loader, review and PDF
themselves run unchanged. For real data set `FINEDGE_API_KEY` and use `--no-prism-fixtures` (or `LIVE_DATA=1 dev/run_stack.sh`).

## Tests

```bash
cd site-api && PYTHONPATH=.:backend python -m pytest -q -c backend/pytest.ini backend/tests
```

CI (`.github/workflows/ci.yml`, job `site-api`) runs exactly this on Python 3.13. The tests need no provider key and no network; they include
`test_start_without_mongo.py` (starts the server without `MONGO_URL`, generates a report and its PDF, checks database routes answer 503 at once).
