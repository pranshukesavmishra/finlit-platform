# Preflight (before a push) and smoke (after a deploy)

## `scripts/preflight.sh`: run before ANY push to main
Runs, in order: backend pytest (needs `bash dev/services.sh` once for Postgres and Redis), frontend `tsc --noEmit`, `vitest run`, `npm run build`, bandit, gitleaks (if installed;
set `GITLEAKS=/path/to/gitleaks`), `bash -n` on `deploy/*.sh deploy/aws/*.sh scripts/*.sh dev/*.sh`, and a grep for secret patterns in tracked files.
It keeps going after a failure, prints one PASS/FAIL line per step and a summary, and exits non-zero if anything failed.
`SKIP_BACKEND=1` / `SKIP_FRONTEND=1` skip a half. The only filtered error is src/three TypeScript errors when the `three` package is not installed (sandbox). The
site-api tests run too when their dependencies are installed (CI always runs them).
Environment for tests: `TEST_DATABASE_URL`, `TEST_REDIS_URL` (defaults match `dev/services.sh`).

## `scripts/smoke.sh <base-url>`: run after every deploy
Checks health, home page, screener catalog (total > 5000), a summary with price and score for RELIANCE and one small-cap, the latest declared day's
"being updated" share (at most `MAX_UPDATING_PCT`, default 40), /etfs, /funds, forum threads, glossary (> 300 terms). Prints PASS/FAIL lines; exit 1 on any FAIL.
The repository-root `.github/workflows/platform-smoke.yml` runs on demand against the entered AWS site URL. Scheduled runs require the repository variable `FINLIT_SITE_URL`. It only reports check results; it does not deploy or open issues.
`SMALLCAP` (default `SBFC`) can be changed.

## Nightly integrity audit
`python -m finlit.worker audit-integrity` (03:40 IST, light; skipped while the loads switch is off). Samples 40 companies, one provider call each; result in the admin Console > Data health tab.
