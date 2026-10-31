# DII history on the FII/DII page (owner item 26)

Question: FII is filled for the whole last year, DII is hatched/empty from Oct 2025 to early June 2026. Is the DII data available, and why is it not coming?

## Root cause

Certain (from the code, `backend/finlit/flows_sources.py`, `flows.py`, `docs/FLOWS.md`):

* **FII/FPI** comes from NSDL's FPI Monitor daily-trends tables. NSDL's own date form (`Reports/Archive.aspx`, "To Date") returns every reporting day of a month, so the job loaded history month by month back to Jan 2010 (`step_fpi`, `FIRST = 2010-01-01`).
* **DII** comes from a different NSDL page, `Users/DIIGenerateReport.aspx` (`Rep=L` latest, `Rep=A` one day via the "Enter Date" form). The code records that NSDL began publishing this report on **1 June 2026** (`DII_START`). `step_dii` only asks for days from `DII_START` on. There is therefore no DII row before that date in our database, by design. It is not a join, rounding, cut-off or upsert bug that hides DII rows that exist.
* The exchanges' own FII/DII cash report (`nseindia.com/api/fiidiiTradeReact`, job `flows-nse`) serves only the latest session, so even when it answers it adds one day at a time. NSE and BSE sit behind bot protection that the project does not bypass.

Bugs found and fixed while reading the pipeline (they could hide or corrupt rows that do exist):

1. `DII_SQL` and `FII_SQL`: when a day's source was `nse`, the nightly NSDL job kept NSE's buy/sell but overwrote the net with NSDL's. Buy, sell and net then came from different sources and did not add up.
2. `checked()` dropped the whole day (FII too) when one side failed the buy - sell = net check. It now blanks only the bad side.
3. UI: the DII total, "Overall" and the "1Y DII" figure summed a partial year as if it were a year (already partly fixed on the base branch; completed here: every line, total and tooltip now names its own window).

Inferred (cannot be checked from here, no production access): the exact first DII date in your table, and the row counts. The screenshot's "DII missing for 1,104 sessions" is an older build's count of every empty day across the 5-year history, not only the last year. The base branch text now counts only the days since NSDL's DII report exists and calls the earlier days "not published".

## Confirm it on the server (read-only)

```
SELECT to_char(d,'YYYY-MM') AS month, count(*) AS sessions,
       count(fii_net) AS fii_days, count(dii_net) AS dii_days,
       min(d) FILTER (WHERE dii_net IS NOT NULL) AS first_dii, array_agg(DISTINCT dii_source) AS dii_src
FROM flows_daily WHERE d >= '2025-04-01' GROUP BY 1 ORDER BY 1;
```
Expected: `dii_days = 0` for every month before 2026-06 and a full count after. Also `https://<site>/api/flows` (look at `coverage.diiFrom`, `diiSessions`, `diiPublishedFrom`) and `/api/jobs/status` for the `flows` and `backfill-dii` jobs.

## Sources evaluated

The sandbox could not reach the publishers (www.nseindia.com, www.fpi.nsdl.co.in and the news sites do not resolve here), so none was probed live. Statements below come from the project's earlier probes (`docs/FLOWS.md`) and a web search.

| Source | History | Terms / access | Verdict |
|---|---|---|---|
| NSDL DII report (`DIIGenerateReport.aspx`, date form) | begins 1 Jun 2026 per the project notes; a web search result hints an NSDL page dated 25 May 2026, unverified | public, no key, honest User-Agent, no robots rule against it | already used. `backfill-dii` probes it for earlier days and stops where it has nothing |
| NSE "FII / DII trading activity" report and `fiidiiTradeReact` | the site shows the latest day; history is only through paid/bulk products | bot protection; automated scraping is not something we do | not used. Do not scrape |
| NSDL FPI Monitor | FPI only, no DII | public | FII only |
| SEBI / AMFI mutual fund statistics | monthly or one day; mutual funds are only a part of DII | public | cannot form a daily DII series |
| Third-party sites (news, "tapetide"-type trackers) | daily history | their own terms, redistribution not granted | not used |

Conclusion: there is no free, legitimately redistributable daily DII history for Oct 2025 to May 2026 that we can confirm. The page says so instead of showing a number. If NSDL's date form turns out to serve earlier days, `backfill-dii` loads them. If you want the full history, the legitimate route is a licensed data feed from NSE or a vendor.

## What was built

* `worker backfill-dii [--from 2025-04-01] [--to DATE] [--max-requests 150]` (`flows.backfill_dii`), registered in `jobs/registry.py` as the weekly bulk job `backfill-dii`.
  * walks weekdays newest to oldest through NSDL's date form;
  * strict: the report must be dated the day asked, be a weekday, have buy - sell = net, and the investor types must add up to the total (`parse_dii`);
  * insert-only: `DII_FILL_SQL` fills a day only when its `dii_net` is empty, so manual and exchange figures are never overwritten;
  * records `dii_source='nsdl'` and `updated_at` (fetch time) on each row;
  * resumable: filled days and known-empty days (meta `dii_empty`) are not asked again; after 25 empty weekdays in a row it records the floor (meta `dii_backfill`) and later runs skip that range;
  * `coverage.diiPublishedFrom` moves back to the earliest NSDL-sourced DII day, so the page wording follows the data.
* Page: calendar header "DII daily figures start on <date>; before that no daily DII series is available from our sources" (derived from the data); hatched/outlined squares read "No DII figure for this day: our daily DII feed starts on <date>"; "DII since <date>" instead of "1Y DII"; the chart legend lists each line's own window ("FII: a to b, n sessions", "DII: ...", "Overall: only sessions with both"); the tooltips on a day without DII say so; the daily-bars DII view shows its window; the dashboard panel states where DII starts; the plain-language summary adds the same sentence; Net combined is a dash on days without DII (table, calendar detail, CSV blank).
* Why the footer numbers did not add up (FII -4.17L, DII +3.25L, Overall +2.00L): FII was summed over the whole year, DII and Overall only from the first DII day. The page now shows both FII totals, whole range and "where DII exists", with dates.

## Owner checklist (one at a time, on the server)

1. Run the SQL above and confirm the zero months.
2. `$W backfill-dii --from 2025-04-01` (where `$W` is the worker wrapper used in `deploy/crontab`). Read the printed `saved`, `oldest`, `floorFound`.
3. If `saved` is 0 and `floorFound` is true, NSDL has nothing earlier; nothing more can be done from free sources.
4. `$W refresh-flows --only dii` then reload `/fii-dii`.
