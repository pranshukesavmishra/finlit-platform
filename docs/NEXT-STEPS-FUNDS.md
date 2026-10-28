# ETFs and Mutual funds: where things stand and what to do next

## Fund holdings and exit loads (`finlit/portfolios.py`, worker `refresh-portfolios`)
- Runs at boot (after the stock loads, in turn with the other fund jobs, skipped if it ran in the last 20 hours) and daily at 04:40 IST; result at
  `/api/mf/status` (`run:refresh-portfolios`). AMFI's TER / AUM / launch dates stay with `refresh-facts` (`finlit/disclosure.py`), whose `get_facts`
  merges these in: exit load (AMFI scheme details, about 74 % of schemes), benchmark (portfolio files, or AMFI's fund-performance list when it answers),
  risk-o-meter and fund managers (when a source is loaded), a second launch date, and month-end net assets when no quarterly AUM is listed.
- Holdings, sector split, month-end AUM and benchmark from the fund houses' own monthly portfolio files, 38 houses (`finlit/disclosure_parsers/amcs.py`,
  `houses_a.py` to `houses_d.py`; `page_lister` covers any house that links its files). Live run Sep 2026 on a local copy: 1,690 scheme families.
  Peak memory of one house's run: at most 82 MB (HSBC, a 4.5 MB page).
- Risk-o-meter, fund managers and benchmark (`disclosure_parsers/managers_risk.py`, step `managers`): AMFI tracking error (index funds and ETFs) plus the
  houses' own pages for DSP, SBI, Axis, Nippon, Tata, Motilal, Groww, Mirae, WhiteOak, The Wealth Company, Shriram, LIC, Canara Robeco: risk 626,
  managers 601, benchmark 1,047 of 2,043 active families. These are page scrapes: a redesign gives 0 rows (the status shows seen/matched counts).
- **Left out on purpose (owner's decisions, October 2026):** HDFC (its service answers only requests carrying hdfcfund.com as Origin) and Kotak (captcha
  and bot check). Edelweiss and Navi are behind bot protection; Union's site is unreachable from the sandbox; Carnelian publishes no portfolio file yet.
  No adapter spoofs a header or goes around a challenge; keep it that way.
- **Expense ratio (TER) from the fund houses' own pages (step `ter` of `refresh-portfolios`, `finlit/disclosure_parsers/ter.py`, Oct 2026):** AMFI's TER feed
  (`refresh-facts` step_ter, `mf_ter`) is empty because AMFI does not answer our AWS (Sydney) address range. SEBI makes every fund house publish scheme-wise,
  plan-wise TER daily, so the nightly job reads those pages and stores one family-keyed fact `ter` = `{regular, direct}` (percent a year, total TER) with the
  house's date, source name and page URL (`disclosure_facts`). `disclosure.get_facts` shows AMFI's figure when `mf_ter` has the scheme, else the fund
  house's (with a note). A house already stored today is not asked again (`disclosure_runs` source `ter:<house>`); `--only ter` re-runs it. One or two
  requests per house, one second apart. Refused, never stored: TER outside 0 to 3.5, Direct above Regular, a row older than 45 days, a sheet without the
  SEBI header; an ETF filed as Regular 0.00 beside a real Direct figure is read as Direct only. Checked Oct 28 2026 against the dev copy of `mf_schemes`:
  Growth plans with a TER, Regular 312 of 1,686 and Direct 301 of 1,665 (SBI 97 of 97 Direct, Nippon 81 of 108 families, Tata 61, Sundaram 35, Canara 27).
  Sources (all plain GETs, no login or token):
  - SBI: `https://www.sbimf.com/docs/default-source/ter_allschemes/current-year-ter.xlsx` (linked from `/total-expense-ratio`), one row per scheme and day.
  - Nippon India: `https://mf.nipponindiaim.com/TotalExpenseRatio/TotalExpenseRatio<FY>.xlsx` (FY like `2026-2027`; percent signs in text cells; listed on
    `/investor-services/downloads/total-expense-ratio-of-mutual-fund-schemes`).
  - Tata: the `.xls` link for the current year on `https://www.tatamutualfund.com/expense-ratio/total-expense-ratio` (file name changes each upload, so the
    page is read first; old OLE2 format, read with `disclosure_parsers/xls.py`; its last day can lag by about two weeks, inside the 45-day limit).
  - Sundaram: `https://www.sundarammutual.com/ter` loads its table with one AjaxPro POST (`/ajax/Views_TER_V2,App_Web_bvj3k5zr.ashx?_method=DailyTER&_session=no`,
    empty body); the method id in the URL may change when they redeploy (then the step reports an error for `sundaram` and the others still run).
  - Canara Robeco: `https://www.canararobeco.com/wp-json/ter/v1/records?from_date=&to_date=` (the JSON their `/expense-ratio` page reads; last 7 days asked).
  Not read, and why: UTI (the page's own API `prod-api-investor.utimf.com/api/v1/scheduler/getTerData` answers 401 without a session token: not touched);
  ICICI Prudential (F5 bot-defence script on the page); Axis (Next.js app calling a gateway, no public file found); DSP (`/ter-historical` shows a static table
  dated 31 Mar 2026 only: too old, the 45-day rule would drop it; revisit if they refresh it); Mirae (page loads its list through a WCF `AjaxService`, not
  tried); Quant (`/Total-Expense-Ratio` is an ASP.NET pager of 2020-era rows); PPFAS (only the 2018 notice PDF and change notices); Franklin, Bandhan, Invesco,
  Motilal, WhiteOak, JioBlackRock (pages are script shells, no file or API found without a browser); ABSL and HSBC (connection from the sandbox timed out);
  HDFC and Kotak (excluded by the owner); Edelweiss (403). Next: Mirae's AjaxService, DSP when refreshed, and the houses above from Render's address.
- Still open: risk-o-meter and managers for ICICI, Kotak, HDFC, ABSL, UTI, Bandhan, Invesco, HSBC, Franklin, Mahindra, Bajaj, JM (no machine-readable
  source that follows the rules was found; PPFAS and Old Bridge publish PDFs only). AMFI's fund-performance feed (benchmark + risk) is 403 from the
  sandbox: check `parts.performance` in the `refresh-portfolios` status on Render.

## Mutual Fund Insights (`finlit/mf_insights.py`, worker `refresh-industry`, page `/funds/insights`)
- Source: AMFI's monthly category report, one workbook a month (portal.amfiindia.com/spages/am<mon><yyyy>repo.xls, found through the listing at amfiindia.com/research-information/amfi-monthly; a corrected `...reporevised.xls` wins). Per scheme category: schemes, folios, funds mobilised, redemptions, net inflow, month-end and average AUM (rupees crore). Read from April 2019, the first category-wise report; the older reports use another layout and are not read.
- Checks: the file must name the expected month, have every column, and its categories must add up to AMFI's own sub-totals and Grand Total; a file that fails is recorded as `refused` and nothing is stored (a stored month keeps its figures). Verified on all 90 reports April 2019 - September 2026 (one real run: 90 stored, 0 refused, about 3.5 minutes at 1.5 s between files; tables about 4,500 rows, 1.3 MB).
- Schedule: `refresh-industry` daily at 18:25 IST under the fund lock, and in the boot chain after `refresh-facts` (`--max-age-hours 20`). Each day it reads the listing page and asks for the newest stored month with its ETag (a 304 when unchanged; about 5 seconds in all); a new month is loaded when AMFI publishes it (around the 8th-10th). `--since YYYY-MM` reloads from a month on. The result is at `/api/mf/status` (`run:refresh-industry`).
- API `GET /api/mf/insights` (registered before `/api/mf/{code}`), cached in Redis per data version (`mfi:ver`, bumped when a month lands). Says `status: empty` with a reason until the first load.
- AMFI's portal sometimes drops a TLS connection mid-download (seen on about 1 in 10 requests from the sandbox); `mf._retry` retries, and a month that still fails is simply asked again on the next run.

## Live state (22 October 2026, read this first)
- **How to see what the boot/nightly steps did:** open `https://finlit-arug.onrender.com/api/mf/status` (no login). It shows, for `refresh-etf`, `refresh-mf`, `backfill-mf` and `refresh-facts`, when they last ran, their status and counts. Render's logs are not reachable from outside.
- **Funds are loaded:** 8,247 active schemes after the exclusions; Growth plans are the default view; best-known fund houses first (`MF_FEATURED_AMCS` in `config.py`). IDCW pages link to the Growth option of the same fund.
- **ETFs are loaded:** the 22 Oct refresh ended `ok`. All 355 ETFs have a price; 274 have a 1-year and 95 a 5-year return. Every blank has its reason: listed less than 1 / 5 years (75 / 252), liquid ETFs whose price does not move (6), or a price break in the provider's history (9 ETFs; see below).
- **ETF price breaks are NOT splits:** checked against Upstox's raw candles: LIQUID1 x32, ABSLLIQUID x260, GOLDETF x4.5, MOLOWVOL x7, MIDSELIETF two instruments interleaved under one ISIN, and MOM30IETF's "x10" predates its own August 2022 launch. The older history under those ISINs is another security, so withholding the figures is correct. Do not add split adjustment without a corporate-action source.
- **Fund facts (new):** `refresh-facts` (nightly 21:40 IST and at boot, `finlit/disclosure.py`) loads from AMFI: fund size (the latest quarter's average AUM, all plans of a scheme together), expense ratio (TER) of the Regular and Direct plan (ETFs: their one plan), and launch date. Checked live: 8,250 active schemes, TER for 8,235, AUM for 8,049, launch date for 8,234; peak memory 131 MB; about a minute. The top-100 ready list is now ranked by that AUM. Figures were checked by hand (Parag Parikh Flexi Cap 0.69% Direct, ₹1,47,064 crore; NIFTYBEES 0.05%), and the TER workbook against AMFI's JSON API.

## Done and verified
- **Live on main:** /etfs, /etfs/:symbol, /etfs/compare, /funds, /funds/:id, /funds/compare, menus, Home cards, proxy paths, nightly jobs (ETF 20:40 IST weekdays, funds 21:10 IST).
- **Why lists were empty:** nothing loaded data into the live database. The first-boot load in `deploy/scheduler.sh` now runs, after the web server answers: `refresh-etf`, then `refresh-mf`, then `backfill-mf`, each only if the previous worked, one log line each. Resumable (fund houses already done are skipped). Peak memory measured: fund refresh 133 MB, SBI backfill 117 MB, ETF refresh 174 MB.
- **Live counts after the first load:** 355 ETFs; 14,401 fund schemes (8,665 active), 3,214 with 1-year returns, 1,768 with 5-year returns (before the exclusions below).
- **Returns:** only 1 day, 1 year, 5 year in list, detail and compare (sortable). ETF 5Y is total price change (about X% a year shown beneath); fund 5Y is per year (CAGR). Other periods, volatility and drawdown sit in the detail Risk area. "—" shows its reason as visible text.
- **Excluded fund houses:** one list, `MF_EXCLUDED_AMCS` in `backend/finlit/config.py` (ASK, Abakkus, ITI, Lakshya, NJ, PGIM India, Samco, Taurus, Trust, Unifi, Zerodha). Matching was tested against all 56 AMFI house names: exactly those 11 match. They are skipped in refresh/backfill and pruned (510 rows locally). Footnote on every fund page.
- **Fast path:** top 100 ETFs (by 20-session average traded value) and top 100 funds in hot tables (`etf_hot`, `mf_hot`, migrations 037/038) plus Redis, served in about 1 ms locally. Everything else is searchable (typo-tolerant) and computed on demand then cached (funds: 3 days, ETF charts: 14 days). Fund storage went from 57.7 MB to 7.3 MB locally. Fund ranking is by fund size (AMFI quarterly average AUM) once `refresh-facts` has run; until then the fallback order and its own wording apply.
- **Admin:** the data-health panel (Console) shows ETF and fund counts and last refresh.
- **Checks at hand-off:** backend 587 tests, frontend 393 tests, tsc, build, bandit and gitleaks clean. Returns recomputed independently from raw data for 17 ETFs and 5 cold funds: all match.

## Not done / not verified
- **Benchmark and risk-o-meter:** AMFI publishes them on its fund performance page (`/polling/amfi/fund-performance`, an iframe app), but AMFI's firewall answers 403 to the sandbox even from a real browser. Test it FROM RENDER (the server's address may be allowed); if it answers, the parked code in `docs/wip-disclosure` (`step_performance`) shows the calls.
- **Minimum investment is stored, not shown:** AMFI's scheme master lists it, but it is out of date for some schemes (every SBI Liquid Fund plan, retail included, at a ₹5 crore institutional minimum; 95 codes at a bare ₹5 or ₹10). Pages say so. Show it only with a second source to check it against.
- **Exit load, fund managers, tracking error, holdings, sector split:** no free machine-readable official source found (factsheets and portfolio files are per fund house, PDF or Excel). The parked parsers are the starting point for the monthly portfolio files.
- ETF re-fetch is still one Upstox call per ETF per night.

## Ready-made pieces
- `frontend/src/holdings/` (HoldingsSection): donut with keyboard-focusable slices and tooltips, positions under 1% grouped into "Other holdings", a table of every small holding with its exact percent, top-10 concentration, sector list, asset split, month-over-month changes, links to /stocks/<symbol>. Tested with demo data only.
- Routes `GET /api/mf/{code}/facts|portfolio` and `GET /api/etf/{symbol}/facts|portfolio` import `finlit.disclosure` lazily and return "unavailable" with a reason when it is absent. Contract: `get_portfolio(pool, key)` returns `{asOf, previousAsOf, source, sourceUrl, holdings:[{name, isin, sector, assetClass, pct, qty, valueLakh, stockSymbol, prevPct, change}], exited, summary:{count, top10Pct, assetSplit, sectors}}`; `get_facts` returns each field as `{value, asOf, source}` or `{unavailable: reason}`. Fund page also expects `finlit.disclosure.top_by_aum(pool, n)` for the hot ranking.
- Unfinished data-source work is parked in `docs/wip-disclosure/` (a partial `disclosure.py`, parsers, migration 036, fixtures). It is NOT shipped: it had 4 bandit B314 findings (xml parsing; use defusedxml) and no verified sources. Move it back into `backend/finlit/` only after fixing and testing.

## Next steps, in order
1. After the first night with this code on Render, read `/api/mf/status`: `run:refresh-facts` should be `ok` with about 2,100 TER schemes and 8,000+ AUM codes. Open a few fund pages (Fund facts card) and the Funds home list (ranked by fund size).
2. From Render, test AMFI's fund performance page (benchmark, risk-o-meter); record a small real fixture if it answers.
3. Fund houses' monthly portfolio disclosures (holdings, sector split), starting with SBI, HDFC, ICICI Prudential, Nippon India, Kotak, Aditya Birla Sun Life, Axis, UTI, Mirae: one parser per format, every file validated (holdings near 100%, valid ISIN check digits, sensible dates), only the latest 3 months kept. `finlit.disclosure.get_portfolio(pool, key)` is the contract the pages already call.

## Score every listed company (Score Screener)
- `score-all` (nightly 02:40 IST and at the end of boot-load) scores companies that have no recent score, biggest first, keeping only the ~5 KB score row (no report, no prices). Cap per run: `SCORE_ALL_PER_RUN` (default 1500, 90 min budget); failed or rejected companies are not retried for 7 days.
- `/api/screener/universe` lists every listed company; rows without a score carry `scored: false` and the page says how many are still waiting. Sector appears once a company is scored. Opening a company builds its full report as before.
- `prune` now keeps score rows for every listed company and drops only reports and prices outside the kept set.
