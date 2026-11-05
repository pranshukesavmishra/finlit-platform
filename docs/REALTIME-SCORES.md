# Real-time scores

Request (low priority): "model scoring to be made real time". Written honestly: some scores are real time, some are minutes behind, some stay nightly because their inputs only exist nightly.

## 1. How each score is produced and what moves it

| Score | Stored in | Inputs and when they change | Old refresh | New refresh |
|---|---|---|---|---|
| FinLit IQ, fundamental pillars (Quality, Growth, Profitability, Balance) | `scores`, `snapshots.summary` | (a) filings: a new quarter or year. Not price, not candles, not NAV | results job rebuilds the company when it declares (already event-driven); otherwise `ingest-all` nightly | unchanged: **event-driven**, stored in the same write as the rebuild. On opening a company, a declared result the report does not hold queues a rebuild (`report_behind_filing`) instead of waiting for the 24 h rule |
| FinLit IQ, Technical pillar and overall | same | (b) live price and (c) daily closes: price against its 50 and 200 day averages, RSI | frozen at the last full build; the price header moved every minute but the score did not | **near real time**: the quote job (every minute while a visitor is on the site, market hours) recomputes it with `snapshot.iq_view`, the build's own function, and writes summary and `scores` row together |
| FinLit IQ of companies without a stored report (slim score) | `scores` | filings only; no price history is kept for them | `score-all` | unchanged (nightly): there are no candles to recompute from |
| FinLit Prism rating (Fundamental, Valuation, Quality, Risk) | `prism_reports` (+ `card` for the screener) | (a) filings; Valuation also uses the price at calculation time | nightly pre-calculation, rating up to 7 days old | **event-driven, minutes**: results stored -> queued -> `scores-live` job recalculates (one at a time). On opening: behind a newer quarter, or calculated before the latest completed session -> background recalculation, stored one shown with its date |
| Prism technical views (short / long term) | `prism_reports` | (c) completed daily candles | `refresh-technicals` after the close | unchanged: **daily after the close**, because the model reads completed bars; an intraday number would not be what the model defines |
| Mutual Fund Health Score | `mf_scores` | (d) NAV (AMFI publishes nightly) and portfolios | `score-mf` nightly | unchanged: **nightly**, there is nothing newer to react to |

Where today's staleness came from: the quote job patched only `summary.quote` and the screener metrics, never the score; Prism was recalculated only by the nightly batch (7 day age rule), so a result declared at 3 pm showed the old Prism rating until the next night or week.

## 2. Design

* **Single source of truth.** The live IQ is written into the stored summary (stock page) and the `scores` row (screener, alerts, lists) in the same tick; `scores.live_at` / `scored_at` and `summary.score.asOf` say when. Prism writes `prism_reports` (report and card) in one statement as before.
* **Equality.** `scorelive.rescore` uses `snapshot.iq_view` and the exact non-price inputs the build stored in `summary.iqInputs`, the stored daily closes, and the same live-bar rule. `tests/test_scorelive.py` builds a report, moves the price and compares score, thesis, strengths and watch-outs with a full build at that price (four price/date cases). An integrity check (the four non-price pillars must reproduce the stored ones) makes it return nothing rather than guess. Reports built before `iqInputs` existed are left to the nightly build, which adds it.
* **Prism events.** `refresh-results` queues each rebuilt company (`rt:prism:q`, max 500, de-duplicated). The light job `scores-live` (probe: queue not empty, at least 3 minutes apart, plus MORNING) recalculates up to `RT_PRISM_PER_RUN` (20) companies, one at a time, through `prism.calculate_and_store`, the function the nightly job uses; it yields to members, checks first that the company still needs it (idempotent), tries a company at most once per 90 min, and stops after three provider failures in a row.
* **On open.** `/api/prism/reports/latest` answers at once with the stored rating and a `freshness` block (`calculatedAt`, `stale`, `kind`, `reason`, `refreshing`). A stale rating starts one background recalculation (one at a time in the web process, 30 min cool-down per company, `RT_SWR_PER_HOUR` default 40 an hour). Plan gating is unchanged: the server checks it before any of this.
* **Guard rails.** No switch turns the scheduled work off. Knobs only size it: `RT_SCORE_COHORT` (6000), `RT_PRISM_PER_RUN` (20), `RT_SWR_PER_HOUR` (40). Nothing raises into a request or a job. The nightly batch stays as the safety net.
* **Status.** `/api/jobs/status` data table has `score_lag`: Prism ratings behind a quarter the IQ already holds (late after 6 h, stale after 30 h), queue length, and the newest live recompute while the market is open with visitors. `scores-live` runs are in `job_runs`.

## 3. What is NOT real time

* The live IQ recompute runs when the quote job runs: every minute with a visitor on the site in market hours, every 15 minutes if only alerts need quotes. It is minutes-fresh, not tick-fresh, and does nothing after the close (the last value is what the nightly build gives for the closing price).
* Prism's Valuation part is re-priced only when Prism is recalculated (a filing, or the first open after a completed session). Prism is not recomputed on every price change: it takes 5 to 15 seconds and provider calls.
* If the model's own data provider lacks a new quarter, the rating is recalculated once, not repeated tonight; the nightly job (7 day age rule) is the net. A dedicated stale-quarter rule in the nightly selection is NOT added.
* Prism technical views stay daily; MF Health Score stays nightly; slim-score companies stay nightly.
* The score history keeps one point a day; today's point is overwritten by the live value.

## 4. Not verified offline
Real provider quotes, the Dhan trade-time format on live ticks, the live Prism site backend, and load on the 2 GB server (the extra work per tick is one Redis read and a few moving-average passes per company). Check after deploy: `/api/jobs/status` -> `score_lag`, and a stock page score "as of".
