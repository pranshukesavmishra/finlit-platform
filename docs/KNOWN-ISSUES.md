# Known issues ledger

Every fault the founder reported, one line each, with the test that stops it coming back silently. A fault gets a line and a test BEFORE it is closed.
Run all of them with `scripts/preflight.sh`. "xfail" = the test is written against the intended behaviour and is waiting for a fix that is still landing; remove the marker when it lands.

| # | Fault reported | Regression test | Status |
|---|---|---|---|
| a | A company with no data from the provider (BSE 540084) showed a blank price or "Not enough data" with no reason | `backend/tests/test_coverage.py::test_a_company_the_provider_sent_nothing_for_is_empty_and_explained_not_a_fault` | passes |
| b | Consolidated statements stale vs standalone (SBFC: consolidated stops Mar 2025, standalone runs to Sep 2026): the fresher basis must be used | `backend/tests/test_regressions.py::test_b_stale_consolidated_is_replaced_by_the_fresher_standalone_basis`, also `test_finedge.py::test_stale_consolidated_switches_every_statement_to_standalone_and_says_so` | xfail(strict=False) until the fix lands; nightly audit check "Latest quarter" watches it live |
| c | EPS sign lost in the P&L table (Cineline: a loss shown as positive EPS) | `backend/tests/test_pl_crosscheck.py::test_cineline_the_company_in_the_founders_screenshots` and `::test_eps_sign_is_taken_from_profit_when_the_provider_contradicts_it` | passes |
| d | A single-slice donut chart (100% holder) drew nothing | `frontend/src/charts/Atlas.test.tsx` | passes |
| e | Results declared but "report being updated" for more than 3 days | `backend/tests/test_regressions.py::test_e_*`, `backend/tests/test_integrity.py::test_declared_*`; nightly audit check "Declared results" | passes |
| f | X-axis labels thinned although every period label fits | `frontend/src/lib/chartAxis.regression.test.ts` (and `chartAxis.test.ts`) | passes |
| g | Input completeness card said "unavailable" for a figure the Risk card shows | `site-api/backend/tests/test_regression_risk_inputs.py` | xfail(strict=False) until the fix lands |
| h | 503 after deploys / out of memory | rules in `docs/ops/MEMORY-AND-503.md`; `scripts/smoke.sh` and `.github/workflows/smoke.yml` catch it; `backend/tests/test_sysctl.py::test_scheduler_syntax_and_checks` | documented + monitored |

Live safety nets (not tests of one case): the nightly integrity audit (`backend/finlit/integrity.py`, worker `audit-integrity`, Console > Data health > Data integrity),
the coverage audit (`audit-coverage`), `scripts/preflight.sh` before every push, `scripts/smoke.sh` after every deploy.
