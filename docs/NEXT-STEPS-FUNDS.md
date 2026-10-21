# ETFs and Mutual funds: where things stand and what to do next

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
