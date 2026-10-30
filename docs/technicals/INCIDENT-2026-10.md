# Incident 2026-10: "the technical score is wrong, not accurate, or late compared with other platforms"

Status: fixed in code (commit on branch `batch-dd`), **not yet deployed**; the live data could not be reached from where this was investigated (no
server, Dhan, FinEdge or internet), so every claim about live numbers is marked and has a browser check (section 8).

## 0. Summary

| | Finding | Verdict |
|---|---|---|
| **H1 staleness** | The technical view is stored inside the Prism report and was only recalculated when the whole report was. | **PROVED. This is the main cause.** Fixed: a daily `refresh-technicals` job plus a refresh on page open. |
| H2 input data | The number of bars, the Indian-date / 16:00 rule, the weekly rule, the benchmark choice and alignment, the sector switch and the divisor are correct. Two real weaknesses found: a candle whose close is a rounding step above its high rejected a whole Dhan series (and a bonus issue under 40% is not caught). | Mostly **refuted**; two small fixes and one open item (section 3). |
| H3 calculation | Every indicator equals an independent textbook implementation to 1e-11 on 5 real series and 3 synthetic ones. | **Refuted as a cause of wrong numbers.** The remaining differences from TradingView are known, and measured (section 4). |
| H4 display | The card showed the report's calculation date, never the day the technical scores describe. | **PROVED, fixed** everywhere the scores are shown. The basic (silver) Technical pillar is a separate, nightly number (section 5). |

## 1. H1: staleness (proved)

Where the technical view lives and how it was refreshed (line numbers are in `backend/finlit/prism.py` before this change):

* `technicalAssessment` is built **inside** the report calculation (site backend `premium_service.generate_report`) and stored in `prism_reports.report`;
  `card` (screener) is copied from it (`card_of`, line 287). `GET /api/prism/reports/latest` (line 435) returns the stored row as it is: it never recalculates.
* The only things that recalculate it: a member's Recalculate; a member opening a company with no report or one older than 6 hours (`REUSE_SECONDS`,
  line 65, `_fresh`); and the nightly `precompute-prism`.
* The nightly selection (`_pending`, line 986) lists a company only when it has **no report or `generated_at` older than `--days` (default 7**,
  `worker.py` line 518), and the widened companies (no full report; `widen_candidates`, line 944) only when older than `WIDEN_REFRESH_DAYS = 30` and within a
  budget of 30 companies a night (`WIDEN_DEFAULT`). So a stored technical view is up to **7 days** old for the companies with a full report, and, because the
  widening budget is 30 a night, **a month or more** for the rest: the "Calculated 28 Oct" on a report seen days later is exactly this.
* Proof as a test: `backend/tests/test_prism_technical.py::test_precompute_never_refreshes_a_young_report_so_its_technical_view_ages` (a report from 2 days
  ago with a view a week behind is not selected by `precompute` but is by the new selection), and `test_selection_is_by_bar_date_not_by_report_age`.
* Other platforms show the last close. A view that is 1 to 7+ days old differs by days of price movement: the short-term score moves by 4 to 14 points
  from one session to the next on the recorded stocks (CROSSCHECK.md, "previous session": TCS +33.85 vs +20.31, HDFCLIFE -5.21 vs -1.04).

### The fix

1. `finlit/prism_technical.py`, worker command **`refresh-technicals`**: for every company with a stored report whose technical bar date is older than the
   newest completed session, fetch the same Dhan candles a report would, call the new site backend route **`POST /api/premium-reports/technical`**, and
   replace only `report.technicalAssessment` (+ `technicalCalculatedAt`) and the card's `st` / `lt` / `technicalBarDate` / `technicalAt`. The rating,
   `generated_at`, the id (PDF links) and every other field are untouched (`test_the_refresh_replaces_only_the_technical_view_and_its_dates`).
2. **Same numbers as the full report**: the route runs `prices_with_supplied` -> `benchmarks_with_supplied` -> `build_technical_assessment`, exactly the
   functions the report runs (`site-api/backend/technical_refresh.py`). `test_technical_only_equals_the_full_report_path_bar_for_bar` proves equality of the
   whole assessment dictionary for four share-count cases (all four benchmarks); the endpoint test proves the route returns that same dictionary.
3. **When it runs** (`deploy/scheduler.sh`, `deploy/crontab`): weekdays **18:30 IST** (the exchange closes 15:30; both the report path and Prism's candle rule treat
   a day as complete from 16:00), a late retry at **21:10** (evening window) / 21:15 (cron), and a catch-up in the **06:45** morning window. Each run is
   resumable (what is at the newest session is done), so a retry only does what is left; it stops at 45 minutes (`--max-minutes`) and after five failures in a row.
4. **Which session is "the newest"**: the Nifty 50's last candle Dhan holds (`prism_candles.reference_session`), not a weekday guess. On a market holiday, or
   before Dhan has posted the day, that is the earlier date, so nothing is fetched twice, and a company Dhan holds nothing newer for is remembered for the day
   (`test_a_holiday_or_a_late_dhan_...`, `test_a_company_dhan_holds_nothing_newer_for_...`).
5. **Cost** (measured here, `crosscheck.py`): one assessment is **0.57 to 0.67 s of one core** for ~1,680 bars. For about 1,300 stored reports that is about
   13 to 15 minutes of CPU plus Dhan's one call per company at 3 a second (about 7 minutes of pacing, which overlaps). Run as one process under `nice` and the
   `run light technicals` lock, one at a time: it is not a parallel job on the 2 vCPU box. It checks for a waiting member before each company and waits
   (`paused_for_members`), and the site backend turns it away (429) while a member's report is being calculated. The `loads` admin switch pauses it.
6. **On page open** (`prism.latest` -> `prism_technical.refresh_on_open`): opening a company whose stored technical view is behind the newest session starts a
   refresh of just that company in the background (one per company per 30 minutes, 2 at a time, never when Dhan was found down); the stored view is shown at
   once with its own date and the page asks again every 20 seconds while "refreshing" (at most about 2.5 minutes).
7. Coverage: companies **with a stored Prism report** (the header dots, the card, the screener's Prism columns and the report all read it). A company with no
   report has no technical view to refresh; it gets one when `precompute-prism` / widening rates it, and from then on is refreshed daily.

## 2. The migration

**None.** The new marker lives inside the existing jsonb (`card.technicalBarDate`, `card.technicalAt`, `report.technicalCalculatedAt`), selected with
`COALESCE(card->>'technicalBarDate', report #>> '{technicalAssessment,asOf}')`, which also covers reports stored before this change. (If the team ever wants an
index: the table has about 1,300 rows; none is needed.) Migrations 074 and 075 are left free for the other work.

## 3. H2: input data (checked in code; live behaviour cannot be seen)

| Question | Answer and evidence |
|---|---|
| How many bars are requested? | Dhan: `HISTORY_DAYS = 365*6+20` (prism_candles.py) = about 1,500 sessions, `STOCK_MIN 252`, `INDEX_MIN 505`, `MAX_ROWS 2000`. FinEdge fallback: `from year-6` (server.py line 683). The long-term score needs about 505 bars (252 for the rank and 252 of look-back): `crosscheck.py` shows the long-term score is withheld with the last 260 or 400 bars and complete from 600. So the requests are long enough; **not truncated**. |
| Is the history long enough for the indicators to converge to TradingView's? | EMA 200 from the last 500 bars differs from the full-history value by up to 6.2 (price units), from 750 bars by 0.05, from 1,000 by 0.005, from 1,500 by 0.0001; RSI, MACD and ADX converge by 500 bars (1e-14). With about 1,500 bars the numbers are TradingView's to 4 decimals. |
| Today's unfinished bar? | Never used: `expected_session` (prism_candles.py) and `_technical_candle_date` (server.py) both cut at 16:00 IST; rows after that date are dropped in both places (`clean_reason`, `check_series`). TradingView includes the live bar during the day, so intraday numbers **will** differ; the model's rule ("latest completed daily session") is deliberate (CROSSCHECK.md, effect b). |
| Off by one: IST against UTC against the container? | The Indian date is used everywhere (`ZoneInfo("Asia/Kolkata")`; the containers set `TZ=Asia/Kolkata` too). One inconsistency found: `generate_report` passed the UTC date (`now.date()`) as `as_of` to the technical build while the candles were cut at the Indian date. It changed nothing (the two dates coincide whenever it matters) but is now the one shared function `premium_technical.last_completed_session`. Tests pin the boundary (15:59 and 16:00 IST, 02:00 IST on a Monday = Sunday UTC, Friday midnight). **Refuted as a cause.** |
| The evening after the close: the new session or the previous one? | From 16:00 IST the day's bar is included (`test_the_new_session_replaces_the_old_one_the_evening_after_the_close`). The problem was not this but that nothing re-ran the calculation (H1). |
| Holidays, weekends | No weekday/holiday calendar is guessed: the newest bar the provider holds up to that date is the session. The refresh finds the real last session from the Nifty 50's own candles. |
| "Preceding week" on a Friday and a Monday? | `weekly_closes` excludes the whole calendar week of the last bar. On Friday evening the current week (Mon to Fri) is excluded and the previous Friday's close is the last weekly close; on Monday the week that just ended is the last (Pine's `request.security(W)[1]` behaviour). A holiday-shortened week closes on its last session. Pinned by 2 tests. **Correct.** |
| NSE or BSE, symbol mapping, series? | `dhan.security_map`: the NSE row by trading symbol, preferring series EQ, BE, BZ, SM, ST, SZ (EQ first), else the BSE row by scrip code. NSE volume and prices. The stock's last close must be within 15% of the quote price, otherwise the Dhan series is refused (a wrong instrument shows up). Not testable without the live instrument file. |
| Duplicates, all-zero rows | Dhan duplicates collapse (`collapse_repeats`); all-zero provider rows are not sessions (T2). |
| **Close above high (T3)** | The recorded FinEdge rows have it on **2 of 8,406 bars** (TCS and HDFCLIFE, both 1 Feb 2026, the Sunday budget session: TCS close 3178.2 against a high of 3141, +1.2%; HDFCLIFE close 714.65 against a low of 720.65, -0.8%; none for HDFCBANK, SKIPPER, BAJFINANCE). Not rounding: a real data error in the special session. On the FinEdge path such a bar leaves only the later bars usable, so **both scores of that stock stay withheld until it is 252 sessions old (short term) and about 505 (long term)**; a Dhan series with the same bar is refused and falls back to FinEdge. Whether Dhan has the same error cannot be seen offline. Before this fix, **one** such bar made both the FinEdge path (history cut to the 180 bars after it: both scores withheld) and the Dhan path (the whole series refused, silent fallback to FinEdge) throw the whole history away. Decision: a tolerance of **0.05% of the price** (`RANGE_TOLERANCE`, mirrored in the research API) is rounding noise and the open/close is taken as the high/low it touches; anything bigger (like the two recorded cases) stays a bad candle and is withheld exactly as before. Pinned: `test_fit_range_tolerates_rounding_only`, `test_a_rounding_sized_violation_keeps_the_history_and_a_real_one_still_withholds`. How often real **Dhan** data trips even this tolerance cannot be known offline; the refresh job counts such series under `unusable_candles` in its run record. |
| Benchmark by company size | Cut-offs 1,07,000 and 32,800 crore (also in `leadership.py`; a test keeps the two equal); chosen **per bar** with the shares times the bar's close, Nifty 500 when the shares are unknown. The refresh passes the shares the full report used (stored in the view as `sharesCr` from now on), otherwise listing market value / price. |
| Is the index aligned with the stock's dates? | Required: the index must hold **every one** of the stock's last 505 session dates (`supplied_benchmarks`, `load_benchmark_history`), else that index is replaced by FinEdge/Upstox, else the relative-strength rows (and with them the long-term score) are unavailable. Seen in the harness: an index that lacks 3 of the stock's dates withheld the long-term score of all five stocks. With Dhan's stock and index on one exchange calendar this holds; **a Dhan index with a gap would silently drop to FinEdge/Upstox**. |
| RS windows | Beta over 126 returns clamped to 0.3 to 3.0; excess returns over 21/63/126/189/252 sessions; percentile over 126 and 252: identical to the team's package (PARITY.md). |
| Sector comparison "switched off" | By the model's own default (`options.sectorRS = false`; the model note: "Sector comparison defaults off ... denominator 96 / 92. There is no sector-index selection UI"). Their weights (4 and 8) leave the divisor: Score = 100 x sum(weight x signal) / weights in use, as in the indicator with the sector option off (PARITY.md, identical). A signal that is **missing** (young stock) never leaves the divisor: the score is withheld instead (T4, deliberate). **Not a bug.** |
| An unadjusted corporate action | The plausibility check refuses a series with a close-to-close move over 40%. A 1:2 bonus (-33%) **passes** it. If a provider ever sent such a series unadjusted, the scores would be wrong by 4 to 15 points (short term) and 12 to 51 points (long term) (CROSSCHECK.md, "an unadjusted bonus issue"). Dhan adjusts, per its documentation, but this has "not been independently verified against FinEdge adjusted closes" (the model's own note). **Open item**: cross-check the last 250 sessions against the stored corporate actions (needs live data to calibrate); not changed here. |

## 4. H3: calculation against other platforms (refuted as a cause; effects measured)

`docs/technicals/crosscheck.py` (reproducible, see CROSSCHECK.md): EMA 9/20/50/100/200, RSI 14 (Wilder), MACD 12/26/9, ATR 14, ADX/DMI 14 (Wilder), OBV and
Bollinger 20/2 written from the textbook, compared with `technical_series.py` on 5 real series (about 1,680 sessions each) and 3 synthetic ones of 1,500 bars:
**maximum difference 2e-11 for every indicator, 0 presence mismatches**. Reasons a number may still differ from TradingView and their size are in
CROSSCHECK.md; in short: the live bar (up to about 5 points on the short-term score of one stock in the test, 0 on others), history shorter than about 600 bars
(long-term score withheld; EMA 200 not converged), adjusted against unadjusted prices (4 to 15 points short term, 12 to 51 long term), a day's staleness (4 to 14 points per session on the short-term score).

## 5. H4: display and caches

* The stock-page card and the report hero showed `createdAt` (when the **report** was calculated). They now also show **"Technical view as of 29 Oct 2026"**
  (the last bar), in: the stock-page Technical analysis card, the full report's footer line, the six header dots' tooltips (technical dots), the screener's
  short/long-term cells (tooltip) and the screener CSV header. The full report's "Prices as of" line and the PDF's "Daily close:" line already carried the bar
  date. The portfolio tiles show the basic pillar (below), not Prism's.
* Cache: `/api/prism/reports/latest` is `no-store` (Cache-Control) and the stock page's query has `staleTime` 60 s, refetching every 20 s while a refresh runs;
  `/api/prism/scores` is private for 60 s; the screener universe (including the card's technical columns) is built from the database and kept in Redis for **3 minutes** (`build_universe`, api.py), and now also reports `tech_as_of`, the newest bar date it holds. No cache longer than 3 minutes was found.
* **The basic FinLit score's Technical pillar** (price against the 50 and 200 day averages, RSI) is computed in `snapshot.build` from the stored daily history
  (`indicators.technical_snapshot`) when a company's snapshot is built: nightly by `ingest-all` (about 01:00 IST, skipped for a company loaded in the last 20 hours),
  adding the live quote as a provisional bar at that moment. `refresh-quotes` patches the price into the summary during market hours but does **not** recompute
  the pillar. So the pillar is **as of the last nightly build** (up to about a day old) while the header price is live: the two can disagree during the session
  and until the next night. Not changed (a rebuild per quote would defeat the nightly design); stated here and in the README.

## 6. What changed (files)

`site-api/backend/`: `technical_series.py` (`fit_range`), `premium_technical.py` (tolerance, `last_completed_session`, `sharesCr` in the view),
`premium_supplied_candles.py` (tolerance), `technical_refresh.py` (new), `server.py` (route), `premium_service.py`. `backend/finlit/`: `prism_technical.py` (new),
`prism_candles.py` (tolerance, `reference_session`), `prism.py` (card markers, `technical` stamp in the answers, scores, on-open refresh), `prism_screen.py`,
`auth/entitlements.py`, `worker.py`, `api.py`. `deploy/scheduler.sh`, `deploy/crontab`. Frontend: card, report footer, dots, screener, types. Tests:
`site-api/backend/tests/test_technical_refresh.py` (24), `backend/tests/test_prism_technical.py` (17), `frontend/src/stock/techAsOf.test.tsx`.

## 7. Server commands, once, after deploy

```
cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T -d app sh -c 'python -m finlit.worker refresh-technicals > /tmp/technicals.log 2>&1'
```

It refreshes every stored report that is behind (about 15 to 25 minutes for 1,300; it stops at 45 minutes and the 18:30 / 21:10 / 06:45 runs finish the rest).
Add `--force` to recalculate even the current ones, `--symbols TCS INFY` for a few. Follow it: `docker compose ... exec -T app tail -f /tmp/technicals.log`
(it prints one JSON line at the end), or in a browser, section 8.

## 8. How the founder verifies from a browser (no server access)

Open **`https://<site>/api/technicals/status`** (public, read-only, no symbols or scores, cached 60 s):

* `expectedSession`: the last weekday whose session should be complete (16:00 IST rule). `newestSessionFound`: the newest session Dhan actually has (differs on a
  holiday or when Dhan is late).
* `newestBarDate`, `oldestBarDate`, `medianAgeDays`, `maxAgeDays`: the bar dates the stored technical views hold. **Healthy: after about 19:30 IST on a trading day
  `newestBarDate` = `newestSessionFound`, `behindNewestSession` is small, `medianAgeDays` is 0 or 1 (2 or 3 over a weekend).** `barDates` is the count per date.
* `lastRun`: `at`, `status` (`ok`, `partial`, `failed`, `skipped`), `updated`, `skipped`, `failed`, `withheld`, and `reasons` (`no_new_bar`, `no_candles`, `unusable_candles`,
  `gap_in_candles`, `short_history`, `stale_candles`, `incomplete_signals`, `site_backend_<code>`), `paused_for_members`, `targetSession`, `seconds`.
  `lastSkipped` says why the scheduler skipped a run (memory, the heavy-loads switch). `status: skipped, reason: dhan_unavailable` means Dhan's index candles
  could not be read: check the Dhan token.
* On a company page (Gold), the card and the dots say "Technical view as of <date>". Compare that date with the last candle on TradingView's daily chart, and
  the score with the figures in CROSSCHECK.md's list of known differences.

## 9. Could not be verified, and uncertain

* Real Dhan candles: how often a close is above the high, whether the history is adjusted, whether the Nifty indices have every stock session, the actual
  Dhan timestamps. All are guarded (the refresh counts and names each failure) but can only be seen live.
* The site backend's route needs the same environment as the full report (FinEdge for a missing index series). The first run after deploy will show it in `reasons`.
* Whether Dhan's call allowance (shared with the quote jobs) copes with 1,300 candle calls in the evening: the job paces itself (3 a second) and stops after five failures.
* The 7-day / 30-day precompute cadence is unchanged on purpose: the fundamental model does not need to be recalculated daily.
