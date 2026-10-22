# ETFs and Mutual funds: where things stand and what to do next

## Fund facts and holdings (October 2026): `finlit/disclosure.py`, worker `refresh-disclosures`
- Runs at boot (after the stock loads, skipped if it ran in the last 20 hours) and daily at 04:40 IST; result at `/api/mf/status` (`run:refresh-disclosures`).
- From AMFI, for (almost) every active scheme: expense ratio regular/direct (TER), AUM (quarterly average; month-end net assets where a portfolio file is read),
  launch date, minimum investment, exit load (AMFI scheme details, about 74 %). Measured locally: TER 8 226 / 8 250, AUM 8 209, minimum 8 072, exit load 6 104.
- Holdings, sector split, month-end AUM and benchmark from the fund houses' own monthly files: SBI, Nippon India, Aditya Birla Sun Life, Mirae, DSP, Invesco,
  Baroda BNP Paribas, Groww, PPFAS, Helios (2 666 of 8 250 schemes). Adapters: `finlit/disclosure_parsers/amcs.py` (`page_lister` covers any house that links its files).
- Not yet: risk-o-meter (AMFI's fund-performance feed answers 403 to the sandbox; it may work from Render: check `parts.performance` in the status),
  fund managers (factsheet PDFs only), holdings for ICICI Prudential (host blocked from the sandbox), HDFC and Edelweiss (403), Kotak (hCaptcha),
  Bandhan (obfuscated app), UTI, Axis, Tata, HSBC, LIC, Motilal, Franklin, Sundaram, Union, quant and the smaller houses (no direct links found yet).

## Live state at hand-off (read this first)
- **How to see what the boot/nightly steps did:** open `https://finlit-arug.onrender.com/api/mf/status` (no login). It shows, for `refresh-etf`, `refresh-mf` and `backfill-mf`, when they last ran, their status and counts. Render's logs are not reachable from outside.
- **Funds are loaded:** 8,249 schemes listed after the exclusions; Growth plans are the default view (3,386 schemes); 3,050 have a 1-year and 1,688 a 5-year return; top 100 ready list served; best-known fund houses first (list `MF_FEATURED_AMCS` in `config.py`). IDCW pages link to the Growth option of the same fund.
- **ETFs are NOT fully loaded:** the last live ETF refresh ended `partial` (103 instruments kept their old rows, 71 had no history), and only 92 of 355 ETFs show a 1-year and 44 a 5-year return. Suspected cause: Upstox's request quota (about 2,000 historical-candle calls per 30 minutes) was used up by several redeploys that each repeated the full ETF load. The boot chain now skips a load that ran in the last 12 hours (15 minutes if it was partial). **Since then:** the ETF job is paced (50 candle calls a minute after a burst of 50, `ETF_CALLS_PER_MINUTE`), stops asking when Upstox still answers 429 after retries, and records why instruments failed (`failed`: symbol and HTTP code, `reason`: counts) at `/api/mf/status`. `refresh-etf --resume` fetches only the ETFs not fetched since the last close (column `etf_funds.fetched_at`, migration 039); the boot chain uses it, and the scheduler retries at 22:10 and 23:40 IST on weekdays (no provider calls when nothing is missing). **First job for the next session:** read `/api/mf/status` after a night's run and the retries; if ETFs still fail, the recorded codes say why.
- ETF figures that round to 0.00% (liquid ETFs that pay out earnings) are now stored empty and shown as "—" with the reason.

## Done and verified
- **Live on main:** /etfs, /etfs/:symbol, /etfs/compare, /funds, /funds/:id, /funds/compare, menus, Home cards, proxy paths, nightly jobs (ETF 20:40 IST weekdays, funds 21:10 IST).
- **Why lists were empty:** nothing loaded data into the live database. The first-boot load in `deploy/scheduler.sh` now runs, after the web server answers: `refresh-etf`, then `refresh-mf`, then `backfill-mf`, each only if the previous worked, one log line each. Resumable (fund houses already done are skipped). Peak memory measured: fund refresh 133 MB, SBI backfill 117 MB, ETF refresh 174 MB.
- **Live counts after the first load:** 355 ETFs; 14,401 fund schemes (8,665 active), 3,214 with 1-year returns, 1,768 with 5-year returns (before the exclusions below).
- **Returns:** only 1 day, 1 year, 5 year in list, detail and compare (sortable). ETF 5Y is total price change (about X% a year shown beneath); fund 5Y is per year (CAGR). Other periods, volatility and drawdown sit in the detail Risk area. "—" shows its reason as visible text.
- **Excluded fund houses:** one list, `MF_EXCLUDED_AMCS` in `backend/finlit/config.py` (ASK, Abakkus, ITI, Lakshya, NJ, PGIM India, Samco, Taurus, Trust, Unifi, Zerodha). Matching was tested against all 56 AMFI house names: exactly those 11 match. They are skipped in refresh/backfill and pruned (510 rows locally). Footnote on every fund page.
- **Fast path:** top 100 ETFs (by 20-session average traded value) and top 100 funds in hot tables (`etf_hot`, `mf_hot`, migrations 037/038) plus Redis, served in about 1 ms locally. Everything else is searchable (typo-tolerant) and computed on demand then cached (funds: 3 days, ETF charts: 14 days). Fund storage went from 57.7 MB to 7.3 MB locally. Fund ranking is NOT by AUM (no verified AUM source yet); the page says so.
- **Admin:** the data-health panel (Console) shows ETF and fund counts and last refresh.
- **Checks at hand-off:** backend 587 tests, frontend 393 tests, tsc, build, bandit and gitleaks clean. Returns recomputed independently from raw data for 17 ETFs and 5 cold funds: all match.

## Not done / not verified
- The phone (390px) ETF list table still scrolls sideways inside its own box and clips the 5-year column. Fix this first.
- No live Upstox check of the new ETF code on Render; hot-list size and latency measured only on small fixtures (ETF) and the local fund DB.
- Funds ranking by AUM; ETF re-fetch is still one Upstox call per ETF per night.
- **Not built (no verified free source yet):** AUM, expense ratio (TER, regular and direct), exit load, benchmark, fund manager(s), riskometer, launch date, minimum investment, holdings, sector split. Upstox has none of these for ETFs or funds (checked: fundamentals empty, no mutual fund endpoints). Pages show "—" with a reason.

## Ready-made pieces
- `frontend/src/holdings/` (HoldingsSection): donut with keyboard-focusable slices and tooltips, positions under 1% grouped into "Other holdings", a table of every small holding with its exact percent, top-10 concentration, sector list, asset split, month-over-month changes, links to /stocks/<symbol>. Tested with demo data only.
- Routes `GET /api/mf/{code}/facts|portfolio` and `GET /api/etf/{symbol}/facts|portfolio` import `finlit.disclosure` lazily and return "unavailable" with a reason when it is absent. Contract: `get_portfolio(pool, key)` returns `{asOf, previousAsOf, source, sourceUrl, holdings:[{name, isin, sector, assetClass, pct, qty, valueLakh, stockSymbol, prevPct, change}], exited, summary:{count, top10Pct, assetSplit, sectors}}`; `get_facts` returns each field as `{value, asOf, source}` or `{unavailable: reason}`. Fund page also expects `finlit.disclosure.top_by_aum(pool, n)` for the hot ranking.
- Unfinished data-source work is parked in `docs/wip-disclosure/` (a partial `disclosure.py`, parsers, migration 036, fixtures). It is NOT shipped: it had 4 bandit B314 findings (xml parsing; use defusedxml) and no verified sources. Move it back into `backend/finlit/` only after fixing and testing.

## Next steps, in order
1. Fix the phone ETF list clipping.
2. Research and test from the sandbox AND from Render (record small real fixtures in `backend/tests/fixtures/disclosure/`): AMFI monthly scheme-wise AUM (the site's JSON `api/average-aum-schemewise` looked like fund-house level; find the scheme-wise report), AMFI TER disclosure (not a static file; inspect the site's network calls), scheme master data, and each fund house's monthly portfolio disclosure (Excel) and factsheet. Start with SBI, HDFC, ICICI Prudential, Nippon India, Kotak, Aditya Birla Sun Life, Axis, UTI, Mirae. ETF holdings come from the same files (match by ISIN).
3. One parser per format into one common shape; validate every file (holding percents about 100, valid ISIN check digits, sensible dates) and refuse bad files. Keep only the latest 3 monthly disclosures per scheme; report the size. Match holdings to stock pages by ISIN.
4. Add `finlit.disclosure`, migration, a worker command and a scheduler line (run daily between the 8th and 20th of each month, IST), then check the facts and holdings sections on the live pages.
5. Rank the top-100 funds by verified AUM once available.
