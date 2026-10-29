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
| i | Stock page for LUMAXTECH disagreed with the company's older site: market cap Rs 13,931 Cr in the ratio strip but Rs 12,409 Cr in the Company overview card; P/E 37.17, P/B 9.91 against FinEdge's 34.72, 9.49 (company site) | `backend/tests/test_valuation_rule.py` (`test_one_market_cap_on_the_whole_page`, `test_finedge_pe_and_pb_are_shown_as_sent`, `test_pe_and_pb_fall_back_to_ours_with_a_note_when_finedge_sends_none`); audit tool `backend/tests/test_provider_compare.py` | passes (reports rebuild on SNAPSHOT_VERSION 5) |

Live safety nets (not tests of one case): the nightly integrity audit (`backend/finlit/integrity.py`, worker `audit-integrity`, Console > Data health > Data integrity),
the coverage audit (`audit-coverage`), `scripts/preflight.sh` before every push, `scripts/smoke.sh` after every deploy.

## Valuation figures: FinEdge wins, one market cap (fault i)

**What was wrong.** Two separate rules made one page disagree with itself and with the company's older site (`site-api/backend/server.py`, which is the verified reference: it shows FinEdge's figures).

1. Two market caps. The ratio strip read `live.marketCapCr or profile.marketCapCr` (FinEdge `/quote` `market_cap`); the overview card read `summary.profile.marketCapCr` (FinEdge `/company-profile` `market_cap`). The recorded Reliance payloads show why they differ: the quote's cap is price x shares (Rs 1,184 x 13.53 bn shares = Rs 16,02,252 Cr, "Today"); the profile's (Rs 16,79,117 Cr) is an older daily file. The company's site also overwrites the profile cap with the quote's (`server.py` ~3691 and ~3809).
2. Our own figure overrode FinEdge's. `DERIVED_WINS` let our computed P/E, P/B, P/S, P/FCF (FinEdge's daily value re-priced by live price / close price), EV/EBITDA, dividend yield and market cap replace FinEdge's. The company's site shows FinEdge's `daily-price-ratios` P/E and P/B as sent.

**The rule now.**

| Figure | Shown from | When FinEdge sends none | Period label |
|---|---|---|---|
| Market cap (strip, overview card, quote, score inputs, screener `market_cap`) | ONE number: FinEdge `/quote` `market_cap`, else `/company-profile` `market_cap` (`summary.profile.marketCapSource` says which) | blank, with a reason in `ratios.blanks` | "Today" (quote) or "Company profile" |
| P/E, P/B, P/S, P/FCF | FinEdge `/daily-price-ratios` latest row, as sent, never re-priced (also in the screener metrics) | ours: market cap / TTM profit, / equity, / TTM sales, / free cash flow, with a plain-words note; a loss or negative equity gives no number and a reason | "As of 28 Sep 2026" (FinEdge's row date); fallback: "TTM" or the year |
| EV/EBITDA, dividend yield | FinEdge sends neither at stock level in any recorded payload, so ours is the labelled fallback (rule `fallback`, note says so). If a FinEdge field appears, `compare-provider --discover` lists it and flags a MISMATCH until the rule reads it | n/a | "TTM" |
| ROE, ROCE, D/E, margins, growth | FinEdge ratio rows (unchanged) | n/a | unchanged |

Still ours (a different measure or basis from anything FinEdge sends, rule `override`, labelled): cash conversion (CFO and FCF over profit), liabilities over assets, dividend payout (declared dividend for the year over EPS, FinEdge's is paid), sales CAGR on the statements table shown, and P/E on continuing-operations profit when a demerger gain is material (Tata Motors case). Every shown ratio carries `rule` (`finedge` / `fallback` / `override`) and, for fallback and override, a `note`.

**Audit tool.** `python -m finlit.worker compare-provider --symbols LUMAXTECH` (or `--sample 5`) reads the raw FinEdge endpoints for each company (9 provider calls, paced) and prints, for market cap (profile, quote, screener), price, P/E, P/B, EV/EBITDA, dividend yield, ROE, ROCE, D/E, sales and profit (year and TTM), EPS, book value and shares: the endpoint and field, FinEdge's value, our stored value and section, the percent difference, the verdict (match within 0.5% / explained / MISMATCH) and the rule. Exit code 1 on any MISMATCH. The result is stored in `mf_meta` key `provider-compare:last`. Run it after a deploy for a few companies; reports built before this fix read as MISMATCH for P/E and P/B until they are rebuilt (SNAPSHOT_VERSION 5 queues the rebuild).
