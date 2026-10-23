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
- Still open: risk-o-meter and managers for ICICI, Kotak, HDFC, ABSL, UTI, Bandhan, Invesco, HSBC, Franklin, Mahindra, Bajaj, JM (no machine-readable
  source that follows the rules was found; PPFAS and Old Bridge publish PDFs only). AMFI's fund-performance feed (benchmark + risk) is 403 from the
  sandbox: check `parts.performance` in the `refresh-portfolios` status on Render.

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
