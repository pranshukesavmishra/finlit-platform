# Mutual fund data report

Prepared for the founder from the code on branch `claude/brave-mayer-fkr9oj` (read on 29 October 2026, after pulling the latest commits). Nothing here is from memory: every source claim cites `file:line`. Where the code or the docs do not say something, this report says "not loaded" or "not stated". No key, token or password value is printed; only the names of the settings that hold them.

How to read it: Section 1 is the summary. Section 2 lists every outside source. Section 3 lists every figure (one row each). Section 4 lists the web addresses FinLit serves. Section 5 separates what is loaded and checked from what is partial or missing. Section 6 says how a person can check a number. Section 7 lists open questions for you.

Paths below are relative to the repository root. `backend/finlit/` is shortened to `bf/`.

---

## 1. Summary

**What fund data FinLit holds.** Mutual fund data is built around the official AMFI (Association of Mutual Funds in India) files. In plain terms:

- Every scheme AMFI lists, with its code, name, ISIN, fund house, category, Direct/Regular plan, Growth/IDCW option, latest NAV and NAV date (AMFI NAV file).
- Returns, volatility, largest fall and SIP returns that FinLit calculates itself from NAV history (AMFI history files). Nothing is bought from a paid data vendor for mutual funds.
- Fund size (average AUM), expense ratio (TER) and launch date from other AMFI files. Where AMFI's expense-ratio file cannot be reached, five fund houses' own pages fill in (see 5.2).
- Holdings, sector split, asset split, month-end net assets and benchmark from the fund houses' own monthly portfolio files (39 houses in the code).
- Exit load text and a second launch date from AMFI scheme details.
- Risk-o-meter, fund managers and benchmark, scraped from a limited set of fund houses' web pages.
- Industry totals by category (schemes, folios, money raised, redemptions, net inflow, AUM) from AMFI's monthly category report, April 2019 onward.
- ETFs (exchange-traded funds) use NSE prices from Upstox or Dhan plus AMFI NAV and fund facts (Section 2, rows S15 and S16).

**How much (only figures stated in the docs; they are dated and were not re-counted for this report).**

| Item | Figure | Where stated |
|---|---|---|
| Active schemes after exclusions | 8,247 (22 Oct 2026) | `docs/NEXT-STEPS-FUNDS.md:53` |
| All schemes stored including stopped ones | 14,401 before exclusions, of which 8,665 active (first load) | `docs/NEXT-STEPS-FUNDS.md:61` |
| ETFs | 355; all have a price; 274 have a 1-year and 95 a 5-year return | `docs/NEXT-STEPS-FUNDS.md:54` |
| Scheme families with a portfolio file (live run, Sep 2026, on a local copy) | 1,690 | `docs/NEXT-STEPS-FUNDS.md:9` |
| Risk-o-meter / managers / benchmark rows | 626 / 601 / 1,047 of 2,043 active families | `docs/NEXT-STEPS-FUNDS.md:12` |
| AMFI TER checked live (sandbox, not production) | 8,235 of 8,250 active schemes; AUM 8,049; launch date 8,234 | `docs/NEXT-STEPS-FUNDS.md:56` |
| Industry reports stored | 90 months, April 2019 to September 2026, 0 refused | `docs/NEXT-STEPS-FUNDS.md:46` |
| Backend tests at hand-off | 587 (frontend 393) | `docs/NEXT-STEPS-FUNDS.md:66`. Not re-run for this report. |

Note: the 8,235 TER figure was measured where AMFI answered. On the live (AWS) server AMFI's TER feed does not answer (`docs/NEXT-STEPS-FUNDS.md:18`). See 5.2.

**Refresh schedule (times are IST; `deploy/scheduler.sh:18` sets `TZ=Asia/Kolkata`).**

| What | Worker command | When | Where |
|---|---|---|---|
| NAVs, returns, SIP, hot pages | `refresh-mf` | daily 21:10 and again 23:30 | `deploy/scheduler.sh:272`, `:279` |
| Fund size, TER, launch date (AMFI) | `refresh-facts` | daily 21:10 window | `deploy/scheduler.sh:273` |
| ETF prices and history | `refresh-etf` | weekdays 21:10, retries in the 21:10 and 23:30 windows | `deploy/scheduler.sh:275`, `:280` |
| Industry category report | `refresh-industry` | daily 19:10 | `deploy/scheduler.sh:261` |
| 5-year NAV history by fund house | `backfill-mf` | daily 01:00 window | `deploy/scheduler.sh:235` |
| Holdings, exit load, benchmark, risk, managers, fund-house TER | `refresh-portfolios` | daily, inside the 01:00 window after the stock loads | `deploy/scheduler.sh:238` |
| Dhan instrument file (ETF list) | `refresh-instruments` | daily 06:45 | `deploy/scheduler.sh:246` |
| First start | all of the above in order | on boot | `deploy/scheduler.sh:135-162` |

All fund jobs run only if `FUND_LOADS_ENABLED=1` (`deploy/scheduler.sh:78`) and the admin "heavy data loads" switch is on (`deploy/scheduler.sh:77`). They take turns on one lock (`deploy/scheduler.sh:66`).

---

## 2. Sources

"Auth" shows whether a key is needed and the setting name only. "Fetched" gives the worker command and its schedule. Every AMFI download identifies itself with the User-Agent `FinLitVentures-MF/1.0 (+https://finlitventures.com; ...)` (`bf/mf.py:57`).

| ID | Source | Exact address as in the code | Method | Auth | Format | Fetched (command, schedule) | Limits, retries, caching | What can go wrong |
|---|---|---|---|---|---|---|---|---|
| S1 | AMFI NAV file (every scheme, latest NAV) | `https://portal.amfiindia.com/spages/NAVAll.txt` (`bf/mf.py:54`) | GET | No | Text, `;` separated, 8 fields per line (`bf/mf.py:278-332`) | `refresh-mf`, 21:10 and 23:30 daily, plus boot | Timeout 300 s; 3 tries with waits of 3 s, 6 s on timeouts, resets and 5xx (`bf/mf.py:720-731`). The file is refused, with nothing changed, if it lacks AMFI's header, has under 80% of the stored schemes, is older than what is stored, or more than 2% of lines are unreadable (`bf/mf.py:804-826`). A NAV dated after tomorrow is dropped (`bf/mf.py:265-272`). | AMFI down or late (23:30 retry exists because of AMFI's 11 pm deadline, `deploy/scheduler.sh:277`). A layout change makes the refusal rule trigger and the old data stay. |
| S2 | AMFI NAV history download | `https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx` with `frmdt`, `todt` and optional `mf=<fund-house id>` (`bf/mf.py:55`, `:742-785`) | GET, streamed | No | Text, same layout as S1 | `backfill-mf` (01:00 window, boot); inside `refresh-mf`: gap repair (20-day pieces, at most 120 days), return start-date windows (1, 3, 5 years, `ANCHOR_DAYS`=14), the last 7 days for the previous NAV, and month-end NAVs (stops after 1,200 s or 3 failures in a row) (`bf/mf.py:1093-1170`, `:1177`) | Can only be asked for a whole fund house; about 13 MB and 9 s a year for a house of 400 schemes (`bf/mf.py:5-8`). Fund-house ids are hard-coded (`bf/mf.py:80-98`). | AMFI drops the connection on about 1 in 10 requests from the test machine (`docs/NEXT-STEPS-FUNDS.md:49`); a failed month or house is asked again on the next run. A fund house missing from the id list has no AMFI history and falls back to S3. |
| S3 | api.mfapi.in (third-party mirror of AMFI data) | `https://api.mfapi.in/mf/<scheme code>` (`bf/mf.py:56`, `:1674-1700`) | GET | No | JSON | On demand when someone opens a Growth scheme with no stored AMFI series; nightly for hot schemes missing a series (`bf/mf.py:1470-1490`); 10-year history for the head-to-head page (`bf/mf_compare.py:387-415`) | Used only if its newest NAV equals AMFI's NAV for the same day, otherwise nothing is shown (`bf/mf.py:1696-1700`). Timeout 15 s (`bf/mf.py:1719`). Cached in Redis 3 days (`COLD_TTL`), a failure for 10 minutes (`bf/mf.py:1710`); 10-year copy 2 days (`bf/mf_compare.py:60`). The page says "third-party mirror" when used (`frontend/src/pages/Funds.tsx`, "About the data" card). | A third party with no stated terms in the code. Can lag AMFI. The code does not mention a licence. |
| S4 | AMFI scheme master | `https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0` (`bf/disclosure.py:37`) | GET | No | CSV, columns checked by name (`bf/disclosure.py:125-150`) | `refresh-facts`, 21:10 daily | Refused if under 8,000 rows (`bf/disclosure.py:47`, `:291-296`). 3 tries (`mf._retry`). | Stored minimum amounts are out of date for some schemes, so minimum investment is not shown (5.2). |
| S5 | AMFI expense ratio (TER) | Month list `https://www.amfiindia.com/api/populate-ter-month?year=<FY>`, then `https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID=All&Month=<m>&strCat=-1&strType=-1&excel=true` (`bf/disclosure.py:38-39`, `:253-271`) | GET (workbook streamed to a temp file) | No | JSON then Excel (about 3 MB) | `refresh-facts`, 21:10 daily | Refused if under 1,500 schemes; a TER of 0 is read as "no such plan" and a cell above 5.0 is ignored (`bf/disclosure.py:48`, `:50`, `:157-165`, `:306-315`). | **AMFI does not answer the live server's address range, so this feed is empty there** (`docs/NEXT-STEPS-FUNDS.md:18`). Fund-house pages (S14) then fill in for five houses. |
| S6 | AMFI average AUM, scheme-wise | `https://www.amfiindia.com/api/average-aum-schemewise?strType=Typewise&fyId=<n>&periodId=<n>` (`bf/disclosure.py:40`, `:278-288`) | GET | No | JSON | `refresh-facts`, 21:10 daily | Newest quarter first, then older ones; up to 6 asks per quarter with waits of 15 s growing (`bf/disclosure.py:51`, `:274-275`). Refused under 3,000 scheme codes (`bf/disclosure.py:49`). A quarter replaces the previous one whole (`bf/disclosure.py:318-337`). | AMFI sometimes answers an empty quarter for minutes (`bf/disclosure.py:274`). A scheme launched after the quarter has no figure. |
| S7 | AMFI monthly category report | Listing page `https://www.amfiindia.com/research-information/amfi-monthly`; files `https://portal.amfiindia.com/spages/am<mon><yyyy>repo.xls` (a `...reporevised.xls` wins) (`bf/mf_insights.py:45-46`, `:95-120`) | GET with `If-None-Match` | No | Excel (.xls, or .xlsx under an .xls name) | `refresh-industry`, 19:10 daily, plus boot | 1.5 s between downloads (`bf/mf_insights.py:49`); a file over 5 MB is refused; stored only if the right month, all columns, 25 or more categories and category totals matching AMFI's own Grand Total (`bf/mf_insights.py:48-52`, `:264`). Unchanged file costs a 304. | AMFI changes the layout (already happened in 2020 and Aug 2026, `bf/mf_insights.py:15-17`); a failing month is recorded "refused" and not stored. Months before April 2019 are not read. |
| S8 | AMFI scheme details | `https://www.amfiindia.com/api/populate-mf`, `.../api/populate-scheme?MF_ID=`, `.../api/scheme-details?MF_ID=&scheme_id=` (`bf/portfolios.py:52-54`) | GET | No | JSON | `refresh-portfolios` step `loads` | One list call per fund house, then one call per scheme; 3 at a time, 0.1 s pause between houses; a scheme's load text is asked again after 25 days (`bf/portfolios.py:55`, `:492-540`). | Per docs about 74% of schemes have an exit load text (`docs/NEXT-STEPS-FUNDS.md:5-7`). Text is stored as AMFI wrote it, cut at 600 characters (`bf/portfolios.py:473-486`). |
| S9 | AMFI fund performance list | POST `https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance` and `.../getsubcategory` (`bf/portfolios.py:56-57`, `:434-470`) | POST (JSON) | No | JSON | `refresh-portfolios` step `performance` | About 50 calls, 0.15 s apart; refused under 1,000 schemes (`bf/portfolios.py:445-452`). | **Docs say AMFI's firewall answers 403 to the test machine** (`docs/NEXT-STEPS-FUNDS.md:41-42`, `:69`). Whether it answers from the live server is not stated; the status page `/api/mf/status` (key `run:refresh-portfolios`, `parts.performance`) is where to look. Gives benchmark, risk-o-meter and AUM in crore; the AUM here is stored but not read by any page (`bf/portfolios.py:468`; no other use found). |
| S10 | AMFI tracking-error disclosure | `https://www.amfiindia.com/api/populate-mf`, `https://www.amfiindia.com/api/tracking-error-data?MF_ID=&strdt=` (`bf/disclosure_parsers/managers_risk.py:254-255`, `:259-282`) | GET | No | JSON | `refresh-portfolios` step `managers` | Newest of the last 12 days per house; 4 pages in flight (`managers_risk.py:58`). | Only the **benchmark name** of index funds and ETFs is read. The tracking-error value is **not** read or stored. |
| S11 | NSE share list (for linking holdings to stock pages) | `https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv` (`bf/portfolios.py:58`) | GET, browser-style User-Agent | No | CSV | `refresh-portfolios` step `isin` | Refused under 1,500 rows (`bf/portfolios.py:416-420`). | Only the ISIN to symbol link; not fund data. |
| S12 | Fund houses' monthly portfolio files (SEBI-mandated) | 39 adapters; each lists files with its own address pattern (full list below this table) (`bf/disclosure_parsers/amcs.py:238-251`, `houses_a.py`-`houses_d.py`) | GET, a few POST/AJAX calls | No | Excel (.xls/.xlsx, some zipped) | `refresh-portfolios`, daily; last 3 month-ends asked (`bf/portfolios.py:46`) | Max 2 connections (`bf/portfolios.py:366-368`); 3 tries; file size capped at 60 MB (`amcs.py:24`); 0.3 s between files (`bf/portfolios.py:690`); a bundle already read is skipped (`disclosure_runs`). Each file is parsed and checked (see 5.4); a failing file is reported, never stored. | A house redesigns its site: the adapter returns 0 files. Names that match two AMFI schemes are refused, not guessed (`bf/portfolios.py:121-146`). |
| S13 | Fund houses' own web pages for risk-o-meter, managers, benchmark | 13 sources: DSP, SBI, Axis, Nippon India, Tata, Motilal Oswal, Groww, Mirae, WhiteOak, The Wealth Company, Shriram, LIC, Canara Robeco, plus S10 (`managers_risk.py:6-35`, `:356`) | GET (SBI also POST with a visitor token its site issues) | No | HTML, embedded JSON, Excel | `refresh-portfolios` step `managers` | 3 tries; 429/502/503/504 retried, 403/404 not (`managers_risk.py:218-232`); 4 at a time. A fund house's own statement beats AMFI's benchmark (`managers_risk.py:865-872`). | The code says plainly: these are page scrapes, a redesign gives 0 rows (`docs/NEXT-STEPS-FUNDS.md:12-13`). Nippon and Motilal risk levels are read from the file name of the risk-o-meter picture (`managers_risk.py:7-9`). |
| S14 | Fund houses' own expense ratio pages | SBI `https://www.sbimf.com/docs/default-source/ter_allschemes/current-year-ter.xlsx`; Nippon `https://mf.nipponindiaim.com/TotalExpenseRatio/TotalExpenseRatio<FY>.xlsx`; Tata (page `https://www.tatamutualfund.com/expense-ratio/total-expense-ratio`, file link read from it); Sundaram `https://www.sundarammutual.com/ajax/Views_TER_V2,App_Web_bvj3k5zr.ashx?_method=DailyTER&_session=no`; Canara Robeco `https://www.canararobeco.com/wp-json/ter/v1/records` (`bf/disclosure_parsers/ter.py:49-56`) | GET (Sundaram POST) | No | Excel, JSON | `refresh-portfolios` step `ter` | 1 s between houses (`ter.py:41`); a house already stored today is skipped; refused: TER outside 0 to 3.5, Direct above Regular, row older than 45 days, wrong header (`ter.py:5`, `:38-39`). | Used only where AMFI's file has no figure (`bf/disclosure.py` `_house_ter_fact`, in `get_facts`). The Sundaram address contains a generated method id that may change when the site is redeployed (`docs/NEXT-STEPS-FUNDS.md:34-35`). |
| S15 | Upstox (ETF prices) | Instrument list `https://assets.upstox.com/market-quote/instruments/exchange/complete.json.gz` (`bf/etf.py:52`); quotes `/v2/market-quote/quotes` (200 keys a call) and daily candles `/v3/historical-candle/<key>/days/1/...` on `UPSTOX_BASE_URL` default `https://api.upstox.com` (`bf/etf.py:511-550`, `bf/config.py:30-31`) | GET | Yes for quotes and candles: `UPSTOX_ACCESS_TOKEN`. The instrument list file is public. | JSON | `refresh-etf`, weekdays 21:10 (+ resume runs) | Paced to `ETF_CALLS_PER_MINUTE` (default 50) after a burst of 50 (`bf/config.py:51`, `bf/etf.py:69`); Upstox quota is about 2,000 calls per 30 minutes shared by every job on the token (`bf/etf.py` `Pacer` docstring). Whole 10 years re-fetched about weekly, other nights only the last weeks (`bf/etf.py:61`, seven days). | Token expiry leaves stored rows untouched (`bf/etf.py:20-22`). One call per ETF per night (`docs/NEXT-STEPS-FUNDS.md:72`). |
| S16 | Dhan (ETF list and prices) | Public instrument file `https://images.dhan.co/api-data/api-scrip-master-detailed.csv` (`bf/dhan.py:34`); prices `/marketfeed/ltp`, `/marketfeed/quote`, candles `/charts/historical` on `DHAN_BASE_URL` default `https://api.dhan.co/v2` (`bf/dhan.py:347-369`, `bf/config.py:39`) | GET (file), POST (prices) | Instrument file: no. Prices: yes, `DHAN_CLIENT_ID` with either (`DHAN_PIN` and `DHAN_TOTP_SECRET`) or `DHAN_ACCESS_TOKEN` (`bf/config.py:33-38`) | CSV, JSON | `refresh-instruments` daily 06:45; prices inside `refresh-etf` | Dhan is chosen when set up and its file holds at least 100 NSE ETFs; `ETF_SOURCE=upstox` or `dhan` forces one (`bf/etf.py:595-609`). At least 1.05 s between price calls; 1,000 quotes a call (`bf/dhan.py:347`, `:360`; `bf/etf.py:552-593`). | **Dhan's written permission to show its data publicly is still open** (`docs/COMPANY-HANDOVER.md:66-67`, `docs/DHAN-SETUP.md:27`). Which of S15 or S16 is the live ETF price source is decided at run time and is not recorded in the code. |
| S17 | FinEdge | Not used for funds. `bf/finedge.py` and `bf/upstox.py` fundamentals calls are for companies (`bf/upstox.py:167-176`). | | | | | | |

**Fund-house portfolio file adapters (S12), 39 in the code.** Counted by loading the module: sbi, ppfas, barodabnp, groww, helios, mirae, invesco, dsp, absl, nippon, uti, axis, tata, bandhan, hsbc, motilal, franklin, sundaram, lic, quant, canara, mahindra, boi, bajaj, whiteoak, jm, oneamc, quantum, shriram, jio, wealthco, angelone, capitalmind, oldbridge, choice, alphagrep, carnelian, monarch, icici (`amcs.py:238-251`, `houses_a.py:185-189`, `houses_b.py:205-210`, `houses_c.py:451-467`, `houses_d.py:43`). `docs/NEXT-STEPS-FUNDS.md:8` says 38 houses; the code has 39. HDFC and Kotak have no adapter (owner's decision, 5.2). Carnelian is listed but publishes no file yet (`docs/NEXT-STEPS-FUNDS.md:15`).

**Two points on how some adapters reach their source.** (a) Several adapters send a browser-style User-Agent string ending in "FinLitVentures/1.0" (`amcs.py:21`, `managers_risk.py:56`). (b) The Mahindra Manulife adapter reads a JSON answer that the site encrypts with a key and initial value that the site's own public JavaScript contains; the code holds a copy of that key and re-reads the site's script if the key changes (`houses_c.py:59-96`). The code comment calls it "transport obfuscation only: no login, cookie or captcha". The JM Financial and Jio BlackRock adapters also read tokens or action ids out of the site's scripts (`houses_c.py:223-245`, `:289-310`). Whether these methods fit each site's terms of use is not recorded anywhere in the code or docs (see Section 7).

**What the code does not use for funds.** No FinEdge call for funds. No paid mutual-fund data vendor. The word "factsheet" appears in messages only; no PDF is parsed.

---

## 3. Fields: every stored or served parameter

Legend. **Table** means the database table and the migration that creates it (`bf/migrations/`). **Route** is the FinLit web address (Section 4). **Shown** is where a visitor sees it (`frontend/src/...`). **Plan gating:** no Basic/Silver/Gold check was found in any fund route (`bf/mf.py`, `bf/mf_insights.py`, `bf/mf_compare.py`, `bf/etf.py` carry no login or plan test) or fund page (`frontend/src/pages/Funds.tsx`, `FundInsights.tsx`, `FundHeadToHead.tsx`, `Etfs.tsx`); the only plan check found in the backend is the Gold gate in `bf/premium.py:39`, which is not a fund route. So "none found" applies to every row below.

### 3.1 Identity

| Parameter (as shown) | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| AMFI scheme code | `code` | whole number | S1 | `mf_schemes.code` (035) | all `/api/mf*` | Scheme page header | Primary key. |
| Scheme name | `name` | text | S1 | `mf_schemes.name` | list, detail | Table, page title | Whitespace tidied (`mf.py:307`). |
| ISIN | `isin` | text, 12 characters | S1 | `mf_schemes.isin` | detail | "ISIN ..." line under name | Only kept if it matches the ISIN pattern (`mf.py:138`, `:322-323`). |
| Reinvestment ISIN | `isin_reinvest` | text | S1 | `mf_schemes.isin_reinvest` | detail | same line | |
| Fund house (AMC) | `amc` | text | S1: the fund-house line above a block of schemes | `mf_schemes.amc` | list, detail, filters | Table, chip | 11 houses are removed (5.2). Display shortens "Mutual Fund". |
| Scheme type | `scheme_type` | Open Ended / Close Ended / Interval | S1 section header | `mf_schemes.scheme_type` | detail | Chip | |
| Category | `category` | text, AMFI's header | S1 | `mf_schemes.category` | list, detail, filters | Table, chips | Two spellings of AMFI names exist and are merged by `classify` (`mf.py:1322`). |
| Tab and sub-category | derived | Equity / Hybrid / Debt / Solution Oriented / Others; sub-category | Calculated from category text with a rule table | not stored (derived on the fly) | `/api/mf?group=`, `/filters` | Category tabs and tick-boxes on /funds | Table at `mf.py:1270-1336`; mirrored in `frontend/src/lib/mfCategories.ts` ("keep the two in step"). Unrecognised names land in Others. |
| Plan | `plan` | Direct / Regular / Unspecified | S1: AMFI's plan column, else the name | `mf_schemes.plan` | list, detail | Table, chip | `clean_plan`, `mf.py:213-224`. |
| Option | `option_class`, `option_label` | Growth / IDCW / Other; AMFI's wording | S1 | `mf_schemes` | list, detail | Table, chip | IDCW covers dividend, payout, reinvestment (`mf.py:210`, `:227-243`). "Other" means AMFI states none. |
| Family (groups plans of one scheme) | `family` | text key: `amc | category | name without plan and option words` | Calculated | `mf_schemes.family` | detail ("Other plans and options of this fund") | Card on scheme page | Holdings, TER and facts are stored per family, not per code (`043_portfolios.sql`). |
| Still publishing | `active` | yes/no | Calculated | `mf_schemes.active` | list | "Stopped publishing" label; hidden unless `stopped=true` | True if last NAV is within 7 days of the newest NAV in the file (`mf.py:60`). |

### 3.2 NAV, NAV history, returns, risk

| Parameter | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes and formula |
|---|---|---|---|---|---|---|---|
| NAV | `nav`, `nav_date` | number, rupees per unit; date | S1 | `mf_schemes` (035) | list, detail, compare | Table, page header | A missing or "N.A." NAV never overwrites a stored one (`mf.py:914` doc). |
| Previous NAV | `prev_nav`, `prev_date` | number; date | S1 history, S2 | `mf_schemes` | list, detail | Under the 1 day figure | The date is named because slow schemes skip days. |
| 1 day change | `change` | percent | Calculated | not stored | list, detail | Table column "1 day"; first return tile | `(nav / prev_nav - 1) x 100`, 2 decimals (`mf.py:1745-1749`, `:2033-2036`). |
| NAV history | `mf_history.blob` | daily series, packed | S2 (or S3) | `mf_history` (035, kept for the 100 hot schemes only since 037) | detail, compare | NAV chart | About 5 years: `KEEP_DAYS` = 5 x 366 + 20 days (`mf.py:59`). Other schemes: fetched when opened and cached 3 days. |
| Month-end NAVs | `mf_monthly` | about 60 NAVs per Growth scheme | S2 | `mf_monthly` (047) | not served | Feeds SIP and month-end fall | Last NAV of each calendar month (`mf.py:475-505`). |
| Returns 1 month, 6 months | `r1m`, `r6m` | percent, total change | Calculated | `mf_schemes` | detail | "Other periods" in Risk card | Hot schemes only. Formula below. |
| Return 1 year | `r1y` | percent, total change | Calculated | `mf_schemes` | list, detail, compare | Table column, return tile | `(end NAV / start NAV - 1) x 100`. Start NAV = the latest NAV on or before the date one year earlier, at most 7 days before it (`mf.py:393-417`, `MAX_STALE` line 62). |
| Return 3 years | `r3y` | percent per year (CAGR) | Calculated | `mf_schemes` | list, detail | Table column "3 yrs p.a."; Other periods | `(end / start) ^ (365 / days between the two NAV dates) - 1`. |
| Return 5 years | `r5y` | percent per year (CAGR) | Calculated | `mf_schemes` | list, detail | Table column "5 yrs p.a."; return tile | Same CAGR formula (`mf.py:410-415`). |
| Volatility, 1 and 3 years | `vol1y`, `vol3y` | percent per year | Calculated | `mf_schemes` | detail | Risk card | Sample standard deviation of daily NAV changes over the window, weekends left out, times the square root of 252; no figure if fewer than 80% of the expected days (`mf.py:420-436`). Hot schemes only. |
| Largest fall (daily) | `mdd` | percent, 0 or negative | Calculated | `mf_schemes` | detail | Risk card "Largest fall" | Biggest drop from a NAV high to a later low over the stored history (about 5 years), at least 30 NAVs (`mf.py:439-450`). |
| Largest fall (month-end, 3 years) | `mdd3y_m` (API `fall3y`) | percent, 0 or negative | Calculated | `mf_schemes` (047) | list | Not a table column; used by the checklist | Same idea over month-end NAVs of the last 36 months; needs the first month and at most 3 missing months (`mf.py:587-600`). |
| SIP return 3 / 5 years | `sip3y`, `sip5y` | percent per year (XIRR) | Calculated | `mf_schemes` (047) | list | Table group "SIP returns (XIRR)" | Equal monthly amounts on the month-end NAV of each of the 36 (60) months before the latest month, valued at the latest NAV; the yearly rate that makes the flows sum to zero, `sum(flow / (1+r)^(days/365))`; no figure if any month is missing (`mf.py:508-584`). |
| Which returns the page shows | | | | | | Scheme page: 1 day, 1 year, 5 year as large tiles; 1M, 6M, 3Y under Risk | The docs line "only 1 day, 1 year, 5 year in list, detail and compare" (`docs/NEXT-STEPS-FUNDS.md:62`) is out of date: the table also has 3 years and SIP columns (`frontend/src/lib/mf.ts:143-158`). |

IDCW and "Other" options get no returns (a payout lowers the NAV, `mf.py:2008-2017`); the page says why.

### 3.3 Fund facts

| Parameter | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| Fund size (AUM) | `aum_lakh` (list shows crore) | number, rupees lakh stored; crore shown | S6 (average over the latest quarter, all plans of the scheme added together); fallback: month-end net assets from a fund house's portfolio file (S12) | `mf_facts.aum_lakh` (041); `mf_schemes.aum_lakh`, `aum_kind` q or m (047); `disclosure_portfolios.net_assets_lakh` (043) | list (`aum`, `aumAsOf`, `aumKind`), `/{code}/facts` | Table "Fund size"; Fund facts card | Family total = sum over the family's codes for the latest quarter (`mf.py:1349-1355`; `disclosure.py:382-392`). The monthly fallback is labelled in the tooltip and note. |
| Expense ratio Regular / Direct | `ter`; facts `terRegular`, `terDirect` | percent per year | S5 (AMFI); fallback S14 (five fund houses) on the Fund facts card | `mf_ter` (041); `disclosure_facts` kind `ter` (043); `mf_schemes.ter`, `ter_date` (047) | list `ter`, `/{code}/facts` | Table "Expense ratio"; Fund facts card | **The table column reads only AMFI's `mf_ter`** (`mf.py:1349-1369`); the Fund facts card also falls back to the fund house's own figure (`disclosure.py` `get_facts`). So on a server where AMFI's feed is empty, the table column can be blank where the scheme page has a figure. |
| Launch date | `launch_date`; second `launch_details` | date | S4; second source S8 (used only when S4 has none) | `mf_facts.launch_date` (041); `disclosure_facts` kind `launch_details` (043) | `/{code}/facts` | Fund facts card | |
| Minimum investment | `min_text` | text | S4 | `mf_facts.min_text` (041) | `/{code}/facts` always says "unavailable" | Fund facts card shows "—" with the reason | **Stored, not shown**: AMFI's value is out of date for some schemes; a bare 5 or 10 is dropped (`disclosure.py:97-117`, `:427-429`). |
| Exit load | `exitload` | text, as AMFI wrote it | S8 | `disclosure_facts` kind `exitload` (043) | `/{code}/facts` | Fund facts card | Docs: about 74% of schemes (`docs/NEXT-STEPS-FUNDS.md:5-7`). |
| Benchmark | `benchmark` | text | S13 or S10 or S12 file or S9 | `disclosure_facts` kind `benchmark`; else `disclosure_portfolios.benchmark` (043) | `/{code}/facts` | Fund facts card | Priority: a fund house's own statement, then AMFI, then the portfolio file (`managers_risk.py:865-872`, `portfolios.py:344-348`). Docs: 1,047 of 2,043 active families. |
| Risk-o-meter | `risk` {scheme, benchmark} | one of Low, Low to Moderate, Moderate, Moderately High, High, Very High | S13, S9 | `disclosure_facts` kind `risk` | `/{code}/facts` | Fund facts card | Only a whole match to one of the six SEBI levels is accepted (`managers_risk.py:62`, `:85-98`). Docs: 626 families. |
| Fund managers | `managers` {names} | list of names | S13 | `disclosure_facts` kind `managers` | `/{code}/facts` | Fund facts card | Honorifics and "since ..." removed (`managers_risk.py:100-107`). Docs: 601 families. |
| Category and fund house on facts card | `category`, `amc` | text | S1 | `mf_schemes` | `/{code}/facts` | Fund facts card | Dated by the NAV date. |
| Tracking error | not stored | | S10 supplies only the benchmark name | none | none | not on mutual fund pages; the ETF facts card shows "Tracking error" as unavailable | **Not loaded** (`disclosure.py:58`, `:476`). |

### 3.4 Portfolio

| Parameter | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| Holdings (name, ISIN, sector, asset class, % of net assets, quantity, value) | `holdings` | rows; percent; quantity; rupees lakh | S12 | `disclosure_portfolios.holdings` (043), one packed row per family and month-end; only the latest 3 month-ends kept (`portfolios.py:46`, `:172-193`) | `/api/mf/{code}/portfolio` | "What it invests in" section (`frontend/src/holdings/HoldingsSection.tsx`) | Quantity and value are shown only if the file has them. A holding links to a stock page if its ISIN is in the NSE list (S11) and the company is loaded. |
| Month-end date of the portfolio | `asOf` | date | file's own "as on" date | `disclosure_portfolios.as_of` | portfolio | same | |
| Net assets (month end) | `netAssetsLakh` | rupees lakh | file's Grand Total | `disclosure_portfolios.net_assets_lakh` | portfolio, and the AUM fallback | same | |
| Sector split | `summary.sectors` | percent of net assets by industry, equity rows only | Calculated from the file's industry column | not stored (derived) | portfolio | same | Rows without an industry fall under "Not classified" (`portfolios.py:246-290`). |
| Asset split | `summary.assetSplit` | percent: equity, debt, cash, other | Calculated | not stored | portfolio | same | |
| Top-10 concentration | `summary.top10Pct` | percent | Calculated: the ten largest non-cash holdings added | not stored | portfolio | same | |
| Change since last month, exited holdings | `change`, `prevPct`, `exited` | new / increased / decreased / unchanged (within 0.005 point) | Calculated against the previous stored month | not stored | portfolio | same | Needs two months stored. |

### 3.5 Industry insights (AMFI monthly category report)

| Parameter | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| Schemes | `schemes` | count | S7 | `mf_industry`, `mf_industry_months` (046) | `/api/mf/insights` | /funds/insights, "By scheme category" and totals | One row per month and category; about 60 categories a month. |
| Folios | `folios` | count (accounts) | S7 | same | same | Industry trend, category table | |
| Funds mobilised | `mobilized` | rupees crore | S7 | same | same | Net flows card | |
| Redemptions | `redemption` | rupees crore | S7 | same | same | Net flows card | |
| Net inflow | `net_flow` (API `netFlow`) | rupees crore, plus or minus | S7 | same | same | Net flows card, trend | Mobilised minus redemptions as AMFI prints it. |
| AUM at month end | `aum` | rupees crore | S7 | same | same | "Where the money sits", trend | |
| Average AUM | `aaum` | rupees crore | S7 | same | same | Category table | |
| Share of total | `share` | percent | Calculated: group AUM / total AUM (`mf_insights.py:630`) | not stored | same | "Where the money sits" | |
| Month-on-month change | `change`, `changePct` | rupees crore; percent | Calculated against the previous month, only if it is the adjacent month (`mf_insights.py:575-583`, `:616`) | not stored | same | KPI cards | |
| Group split | `grp` | Equity / Debt / Hybrid / Solution oriented / Other / domestic fund of funds | Our grouping of AMFI's headings | `mf_industry.grp` | same | "Where the money sits" | Domestic fund of funds are shown apart because AMFI leaves them out of its totals. |

Page sections: Industry trend, Where the money sits, Net flows, By scheme category (`frontend/src/pages/FundInsights.tsx:146`, `:272`, `:304`, `:329`).

### 3.6 Checklist, category comparison, search

| Parameter | Internal name | Type | Source | Table | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| Checklist (5 checks) | `chk_pass`, `chk_known`, `chk_bits`, `chk_mask` | "3/5" style; each check pass, fail or unknown | Calculated by SQL (`mf.py:1371-1403`) | `mf_schemes` (047) | list (`checklist`, `peers`) | Table column "Checklist" with hover | Each active Growth scheme is compared with its own sub-category and plan. Checks: (1) 5-year return above the peer median (3-year if no 5-year); (2) expense ratio below the peer median; (3) smaller largest month-end fall than the peer median; (4) fund size at least 50,000 lakh (Rs 500 crore); (5) at least 5 years since launch. Checks 1 to 3 count only if the scheme and at least 3 peers have the figure; checks 4 and 5 need only the scheme's own figure (`mf.py:1338-1346`, `:1371-1403`). The medians are stored in `mf_meta` key `dashboard`. These are descriptive pass/fail tests, not a rating. |
| Return and cost bands | derived in browser | Negative / 0-8% / 8-15% / Above 15% etc.; Low / Moderate / High | Calculated in `frontend/src/lib/mf.ts` | not stored | n/a | Small word under returns and expense ratio | Explained on the page (`frontend/src/pages/Funds.tsx:58`). |
| Category average | `mf_cat_avg` | index starting at 100 | Calculated: equal-weighted index of active Growth funds of the category and plan, one per fund, at most 60, at least 3 (`mf_compare.py:53-54`) | `mf_cat_avg` (048) | `/api/mf-compare` | Head-to-head page | Funds that closed or merged are missing, so it can flatter the category; the page says so (`mf_compare.py:695`). |
| Head-to-head measures | | | Calculated from NAV history | not stored | `/api/mf-compare?a=&b=&period=` | /funds/compare with two funds: "Compare what matters" (`FundHeadToHead.tsx:367`) | Periods 1Y, 3Y, 5Y, 10Y (10Y from the third-party mirror only). Return, rolling returns (window 3, 12, 12, 36 months), volatility (sample standard deviation of weekday NAV changes x sqrt 252), downside deviation, largest fall with peak, trough and recovery date, worst and best month, calendar years, "beats category average" tallies, excess return against the category average. **Sharpe ratio = (return per year - 6) / volatility, with 6% a year as an assumed risk-free rate, not a measured figure** (`mf_compare.py:50-52`, `:254-272`). No alpha against the benchmark index (`mf_compare.py:23-27`). |
| Multi-fund compare | | | Calculated | not stored | `/api/mf/compare?ids=` | /funds/compare?ids=... (2 to 4 funds) | Facts, returns, risk and NAV series rebased to 100 on the first day all have a NAV. |
| Search | | | Our own in-memory index of names and fund houses (about 14,000 strings) | not stored | `/api/mf?q=` | Funds list box; global search overlay; SIP calculator's "use a real fund's return" box | Tolerant of spaces and up to a few spelling errors (`mf.py:626-700`). Result ranking is by match quality. |

### 3.7 ETFs (same site, separate pages /etfs)

| Parameter | Internal name | Type, unit | Source | Table (migration) | Route | Shown | Notes |
|---|---|---|---|---|---|---|---|
| Symbol, ISIN, names | `symbol`, `isin`, `exchange_name`, `short_name`, `scheme_name`, `display_name` | text | S15 or S16 list; AMFI names matched by ISIN (S1) | `etf_funds` (034) | `/api/etf*` | List, detail | |
| Fund house | `fund_house` | text | S1, matched by ISIN | `etf_funds` | same | Key facts | |
| Category and asset class | `category`, `asset_class` | key from `CATEGORIES` | Calculated from keywords in the names (`etf.py:130-153`) | `etf_funds` | same | Chip; unclear names show "Category not clear from the name" | |
| Price, previous close, day change, price date, volume | `price`, `prev_close`, `change_pct`, `price_date`, `volume` | rupees; percent; date; units | S15/S16 | `etf_funds` | same | List, detail | |
| Average traded value | `avg_turnover` | rupees per day | Calculated: average of close x volume over the last 20 sessions (needs 10) (`etf.py:372-376`) | `etf_funds` | same | Default sort; "hot" ranking | |
| Returns 1M, 6M, 1Y, 3Y, 5Y; CAGR 3Y, 5Y | `ret_*`, `cagr_*` | percent, **price return, dividends not included** | Calculated from price closes | `etf_funds` | same | Table, detail | Total change; 3Y and 5Y also per year `(end/start)^(1/years) - 1` with years from days / 365.25 (`etf.py:331-337`). Look-back price must exist within 10 days. |
| Volatility 1Y; largest fall 1Y, 3Y, 5Y; 52-week high and low | `vol_1y`, `mdd_*`, `high52`, `low52` | percent; rupees | Calculated | `etf_funds` | same | Detail "Risk, in plain words" | Volatility needs at least 150 trading days (`etf.py:58`). |
| Price break date | `break_date` | date | Calculated: a one-day move beyond 40% marks suspected split or bad price; earlier prices are withheld (`etf.py:261`, `BREAK_MOVE`) | `etf_funds` | same | Notice on detail | Docs verified nine ETFs against Upstox raw candles (`docs/NEXT-STEPS-FUNDS.md:55`). |
| NAV and premium or discount | `nav`, `nav_date`, `nav_premium` | rupees; percent | AMFI NAV (S1) matched by ISIN; calculated `(close on NAV date / NAV - 1) x 100`, only if the ETF traded on that day, and not shown beyond 100% (`etf.py:378-389`) | `etf_funds` | same | "NAV and premium" card | |
| ETF facts (AUM, expense ratio, launch date, benchmark, managers, risk-o-meter, holdings) | as in 3.3 and 3.4, found by ISIN | | same as mutual funds | same tables | `/api/etf/{symbol}/facts`, `/portfolio` | Fund facts, "What it invests in" | Minimum investment shows "1 unit, bought on the stock exchange" and exit load "None when sold on the stock exchange", both labelled "NSE trading rules" (`disclosure.py:477-478`). Tracking error: unavailable. |
| Top-100 "hot" list | `hot`, `turnover_rank` | | Calculated | `etf_funds`, `etf_hot` (038) | `/api/etf` | Default list | Ranked by average traded value. |
| Candle history | `etf_history` | packed arrays | S15/S16 | `etf_history` (034) | `/api/etf/{symbol}` | Price chart | Hot ETFs keep 10 years; others are fetched when opened and cached 14 days (`etf.py:66`). |

`UNAVAILABLE` in `bf/etf.py:74` and `NOT_AVAILABLE` in `bf/mf.py:74` list items as "not loaded" and are still sent in the payload (`notAvailable`), but the fund page does not display them (no use found in `frontend/src` outside types and demo code). The module notes at the top of `mf.py:22-23` and `etf.py:5-6` are out of date for the same reason.

---

## 4. API routes served by FinLit for funds

All are GET, need no login, and carry the caching shown. Responses carry an ETag and answer 304 to `If-None-Match`. Fund data is cached in Redis under a data version that changes after each refresh (`mf.py:1783-1812`).

| Path | Parameters | Response fields | Cache |
|---|---|---|---|
| `/api/mf` (`mf.py:1834`) | `q` search (80 chars), `category`, `categories` (repeat), `group` (equity, hybrid, debt, solution, other), `amc`, `plan` (Direct, Regular, Unspecified), `option` (Growth default; Growth, IDCW, Other, All), `stopped`, `min1y`/`max1y`/`min5y`/`max5y`, `sort` (name, amc, category, nav, navDate, r1y, r3y, r5y, change, sip3y, sip5y, aum, ter, checklist), `dir`, `page`, `size` (max 100) | `total`, `page`, `pages`, `items[]` with `code, name, amc, category, plan, option, optionClass, nav, navDate, change, changeSince, active, r1y, r3y, r5y, retDate, noReturns, sip3y, sip5y, fall3y, aum (crore), aumAsOf, aumKind, ter, terDate, checklist{pass, of, bits, mask, peer}`; `peers`; `checklist.checks`; `dataDate`, `updatedAt`, `source`, `disclaimer`, `excludedAmcs` | Redis 900 s; browser 300 s then stale-while-revalidate 3,600 s (`mf.py:70`, `:1791`) |
| `/api/mf/filters` (`mf.py:1923`) | none | categories with counts, tabs, fund houses with counts, plan and option counts, totals | same |
| `/api/mf/hot` (`mf.py:2108`) | none | `basis` text, `items[]` (the list rows plus `rank`) | Redis 36 h; rebuilt nightly |
| `/api/mf/compare` (`mf.py:2056`) | `ids` (2 to 4 codes, comma separated), `range` (1M, 6M, 1Y, 3Y, 5Y, MAX) | per fund: identity, NAV, change, `returns{1m..5y}`, `risk`, `history`; `chart` rebased to 100 or `chartNote` | same |
| `/api/mf/insights` (`mf_insights.py:663`) | none | `status` ("empty" with a reason before the first load), `month`, `asOf`, `kpis{aum, netFlow, folios, equityAum}`, `series`, `groups[]` with `items[]`, `fofDomestic`, `gaps`, `source`, `sourceUrl` | Redis 6 h per data version; browser 600 s. Registered before `/api/mf/{code}` (`api.py:565-566`) |
| `/api/mf/status` (`mf.py:2099`) | none | for each worker step, when it last ran, its status and counts; no secrets | `no-store` |
| `/api/mf/{code}/facts` (`mf.py:2149`) | scheme code | `facts` with keys `aum, terRegular, terDirect, exitLoad, benchmark, managers, riskometer, launchDate, minInvestment, category, amc`, each `{value, asOf, source, note}` or `{unavailable: reason}` | Redis 900 s |
| `/api/mf/{code}/portfolio` (`mf.py:2170`) | scheme code | `asOf, previousAsOf, source, sourceUrl, holdings[], exited[], summary{count, top10Pct, assetSplit, sectors}, netAssetsLakh, notes` or `{unavailable}` | same |
| `/api/mf/{code}` (`mf.py:2183`) | scheme code | `code, name, isin, isinReinvest, amc, category, categoryGroup, schemeType, plan, optionClass, option, active, nav, navDate, prevNav, prevDate, change, returns{1m,6m,1y,3y,5y: value, kind, from, why}, risk{vol1y, vol3y, maxDrawdown{value, peak, trough, since}}, retDate, series (chart ranges), history{source, from, to, points, complete, note}, family[], dataDate, source, disclaimer, excludedAmcs` | Hot schemes: Redis 36 h (header `X-MF-Path: hot`); others: Redis 900 s. Each open also counts toward a "most opened" tally used by the fallback hot ranking (`mf.py:2188-2191`). |
| `/api/mf-compare/categories` (`mf_compare.py:753`) | none | open-ended categories with fund counts per plan | Redis 6 h (`_cached`, `mf_compare.py:722`) |
| `/api/mf-compare/funds` (`mf_compare.py:777`) | `category`, `plan` | funds with `code, name, amc, launch, r1y, r5y` | Redis 6 h |
| `/api/mf-compare` (`mf_compare.py:794`) | `a`, `b` (codes), `period` (1Y, 3Y, 5Y, 10Y) | `funds`, `category`, `returns`, `risk`, `consistency`, `costs`, `pending` | Redis 6 h (`COMPARE_TTL`, `mf_compare.py:63`); an answer still waiting for its category average is not kept (`no-store`); the page asks again every 4 seconds (`frontend/src/lib/mfCompare.ts:236`) |
| `/api/etf` (`etf.py:1221`) | `q`, `category`, `asset`, `sort`, `order`, `limit` (max 100), `offset`, and min/max filters on figures | `items[]` (fields in 3.7), `total`, `universe`, `categories`, `groups`, `asOf`, `source` | 120 s (`etf.py:1018`) |
| `/api/etf/compare` (`etf.py:1367`) | `symbols`, `range` | rebased series and notes | same |
| `/api/etf/{symbol}` (`etf.py:1411`) | `range` | headline, returns, risk, NAV, facts, series, notes | same |
| `/api/etf/{symbol}/facts`, `/portfolio` (`etf.py:1479-1502`) | symbol | same shape as the mutual fund ones | 300 s; 60 s on "unavailable" |

Pages: `/funds`, `/funds/:id`, `/funds/compare`, `/funds/insights`, `/etfs`, `/etfs/:symbol`, `/etfs/compare` (`frontend/src/App.tsx:95-102`).

---

## 5. Data gaps and limits

### 5.1 Loaded and verified (by the code's own checks and the docs' hand checks)

| Item | What was checked | Evidence |
|---|---|---|
| NAV, category, plan, option | File refused if header, row count, date or readability tests fail | `mf.py:804-826`; `backend/tests/test_mf.py` (40 tests) |
| Returns for funds | Recomputed independently from raw data for 17 ETFs and 5 cold funds; all matched | `docs/NEXT-STEPS-FUNDS.md:66` |
| Fund size and TER (AMFI) | Parag Parikh Flexi Cap 0.69% Direct and Rs 1,47,064 crore, NIFTYBEES 0.05%, and the TER workbook against AMFI's JSON | `docs/NEXT-STEPS-FUNDS.md:56` (checked where AMFI answered) |
| Industry report | All 90 reports April 2019 to September 2026 stored, 0 refused; totals must add up to AMFI's Grand Total | `docs/NEXT-STEPS-FUNDS.md:46`; `backend/tests/test_mf_insights.py` (18 tests) |
| Holdings | Per file: valid date; percent not negative (except short derivative lines) and not above 110; rows add up to the file's own total within 0.1 + 0.002 x rows points, or to 100 within 1 + 0.002 x rows if there is no total; the file's total within 0.5 of 100; invalid ISIN check digits dropped, and the file refused if over 5% fail | `disclosure_parsers/model.py:19-23`, `:114-160`; `backend/tests/test_portfolios.py` (17 tests) |
| ETF prices | One-day move beyond 40% marks a break and withholds earlier prices; checked against Upstox raw candles | `docs/NEXT-STEPS-FUNDS.md:55` |

Test counts above are the number of test functions in each file; they were not run for this report.

### 5.2 Loaded but partial

| Item | What is missing and why | Evidence |
|---|---|---|
| Fund houses not loaded (owner's exclusions) | **11 fund houses are removed from everything**: ASK, Abakkus, ITI, Lakshya, NJ, PGIM India, Samco, Taurus, Trust, Unifi, Zerodha. Their schemes are not stored and a footnote lists them on every fund page. | `bf/config.py:15`; `bf/mf.py:100-125`, `:1078`; `frontend/src/mf/Bits.tsx:34` |
| HDFC and Kotak: no portfolio, risk-o-meter, managers | Left out on purpose by the owner: HDFC's service answers only requests that carry hdfcfund.com as Origin; Kotak has a captcha and bot check. "No adapter spoofs a header or goes around a challenge." Their NAVs, returns and AMFI-based figures are still loaded (both are in the featured list, `config.py:13`). | `docs/NEXT-STEPS-FUNDS.md:14-16` |
| Other houses without portfolio files | Edelweiss and Navi (bot protection); Union (site unreachable from the test machine); Carnelian (no file yet). Not in the adapter list: Edelweiss, Navi, Union, HDFC, Kotak. | `docs/NEXT-STEPS-FUNDS.md:14-16`; `amcs.py:238-251` |
| PDF-only houses | PPFAS and Old Bridge publish PDFs only; PDFs are not parsed. Both have adapters in the code; what they return is not stated in the docs. | `docs/NEXT-STEPS-FUNDS.md:40-41` |
| Expense ratio on the live server | AMFI's TER feed does not answer the live server; five fund houses' own pages fill in (SBI, Nippon, Tata, Sundaram, Canara Robeco), measured on a dev copy at Regular 312 of 1,686 and Direct 301 of 1,665 Growth plans. Not read: UTI (needs a session token, not touched), ICICI Prudential, Axis, DSP (table dated 31 Mar 2026), Mirae, Quant, PPFAS, Franklin, Bandhan, Invesco, Motilal, WhiteOak, Jio BlackRock, ABSL, HSBC, HDFC, Kotak, Edelweiss. Because the table column reads only AMFI's file, it may be blank on the live server where the scheme page shows a figure (see 3.3). | `docs/NEXT-STEPS-FUNDS.md:17-40`; `bf/mf.py:1349-1369` |
| Risk-o-meter, managers, benchmark | Only the scraped houses. Still open for ICICI, Kotak, HDFC, ABSL, UTI, Bandhan, Invesco, HSBC, Franklin, Mahindra, Bajaj, JM. Docs: risk 626, managers 601, benchmark 1,047 of 2,043 active families. A redesign of a scraped page gives 0 rows; the status page shows seen and matched counts. | `docs/NEXT-STEPS-FUNDS.md:11-13`, `:40-42` |
| Exit load | About 74% of schemes (AMFI scheme details). | `docs/NEXT-STEPS-FUNDS.md:5-7` |
| Returns 1M, 6M, volatility, daily largest fall | Held for the 100 "hot" schemes only (ranked by AMFI fund size); other Growth schemes keep only 1Y, 3Y, 5Y, SIP and month-end fall. These are fetched and shown when a person opens the scheme (via the mirror S3), and cached 3 days. If the mirror does not agree with AMFI, nothing is shown. | `bf/mf.py:1470-1500`, `:1674-1700`, `:1952-1968` |
| IDCW and unspecified options | No returns, by design. | `bf/mf.py:2008-2017` |
| Schemes under 1, 3 or 5 years old | "No figure" with the reason, never a guess. | `bf/mf.py:393-417` |
| Longer history | AMFI history is stored for about 5 years only; the 10-year view in head-to-head comes from the third-party mirror and is labelled so. | `bf/mf_compare.py:5-9` |
| Category average | Excludes funds that closed or merged; at most 60 funds per category. | `bf/mf_compare.py:52-54`, `:695` |
| Industry report | April 2019 onward only; earlier layout not read. | `bf/mf_insights.py:48`, `:609` |
| Portfolio history | Only the latest 3 month-ends per scheme are kept. | `bf/portfolios.py:46` |

### 5.3 Not loaded

| Item | Reason given in code or docs |
|---|---|
| Tracking error value (index funds and ETFs) | No machine-readable source found; the benchmark name is read, the value is not (`disclosure.py:58`). |
| Minimum investment | Stored, deliberately not shown: out of date for some schemes (every SBI Liquid Fund plan at a Rs 5 crore institutional minimum; 95 codes at a bare Rs 5 or Rs 10), no second source to check against (`docs/NEXT-STEPS-FUNDS.md:70`, `disclosure.py:97`, `:427`). |
| Portfolio holdings, risk-o-meter and managers for the houses listed in 5.2 | See 5.2. |
| Alpha against the benchmark index | Index data available to FinLit is price-only without dividends and goes back five years (`mf_compare.py:23-27`). |
| Direct/Regular "other" disclosures: NAV for IDCW returns | By design. |
| Fund house factsheet PDFs | Not parsed anywhere. |
| Anything for the 11 excluded houses | See 5.2. |
| AUM from AMFI's fund-performance list | Fetched when AMFI answers, stored as `aum_daily`, but no page reads it (`portfolios.py:468`). |

### 5.4 Accuracy checks that exist, and known risks

Checks in code: refusal of a bad AMFI file (S1, S4, S5, S6, S7) so that stored data stays as it was; day-count checks on returns (start NAV at most 7 days before the date); mirror NAV must equal AMFI's NAV for the same day; holdings validation (5.1); ISIN check digit (`disclosure_parsers/model.py:26-40`); ETF price-break rule; names that match two schemes are refused rather than guessed (`portfolios.py:121-146`); every stored fact carries a date and a source; every missing figure shows a reason on the page. A nightly integrity audit and a coverage audit exist for the whole site, not specifically for funds (`docs/KNOWN-ISSUES.md`, last paragraph before the valuation section). `docs/KNOWN-ISSUES.md` lists no mutual-fund fault.

Known risks:

- **Page scrapes break silently.** Risk-o-meter, managers and benchmark come from fund-house web pages; a redesign gives zero rows (`docs/NEXT-STEPS-FUNDS.md:12-13`).
- **AMFI blocking.** AMFI's TER feed does not answer from the live server's address range; its fund-performance feed answered 403 from the test machine.
- **Times differ between docs and scheduler.** The docs say `refresh-facts` runs at 21:40 (`docs/NEXT-STEPS-FUNDS.md:56`), `refresh-portfolios` at 04:40 (`:4`) and `refresh-industry` at 18:25 (`:47`); the scheduler runs facts in the 21:10 window (`deploy/scheduler.sh:273`), industry in the 19:10 window (`:261`) and portfolios inside the 01:00 night chain (`:238`). The migration header for portfolios says "between the 8th and the 20th" (`043_portfolios.sql:1-2`); the code runs daily. The scheduler is the code that runs.
- **Hot set is not a quality ranking.** It is the 100 largest funds by AMFI average AUM when AUM is loaded; otherwise the fallback is the most-opened schemes plus a spread across categories, and the basis text on the page says so (`mf.py:1425-1427`, `:1429-1466`).
- **Checklist medians** depend on fewer than the full set of funds when TER is missing on a server (checks need at least 3 peers).
- **Rounding.** Returns shown to 2 decimals; stored as floating-point numbers.

---

## 6. How a person can check a number on a fund page

| Number on the page | Compare against | How |
|---|---|---|
| NAV and NAV date | AMFI NAV file `https://portal.amfiindia.com/spages/NAVAll.txt` or amfiindia.com NAV page | Find the scheme code; fields are `Scheme Code; ISIN; ISIN reinvest; Scheme Name; Plan; Option; NAV; Date`. |
| 1 day change | Same file, previous day's NAV (AMFI NAV history report, `DownloadNAVHistoryReport_Po.aspx`) | `(NAV / previous NAV - 1) x 100`. The previous NAV date is printed on the page. |
| 1 year return | AMFI NAV history report for the fund house, the NAV on the start date shown beside the figure | `(latest NAV / start NAV - 1) x 100`. |
| 3 and 5 year per year | Same | `(latest / start)^(365 / days between the two NAV dates) - 1`. The start NAV date is shown on the page for hot schemes. |
| Volatility, largest fall | AMFI NAV history, spreadsheet | Standard deviation of daily changes x sqrt 252; deepest peak-to-trough fall. Only for the NAV window named on the page. |
| SIP return | Spreadsheet XIRR on month-end NAVs | Equal amounts on the last NAV day of each of the 36 or 60 months before the latest month, final value at the latest NAV. |
| Fund size | AMFI "Average AUM, scheme-wise" page, quarter named on the page | Added across plans of the scheme. If the tooltip says month-end net assets, compare with the fund house's monthly portfolio file (Grand Total). |
| Expense ratio | AMFI "TER of mutual fund schemes" page, or the fund house's daily TER page | The date is on the page. |
| Launch date | AMFI scheme master file or AMFI scheme details | |
| Exit load, benchmark | AMFI scheme details (exit load); fund house's scheme page or the scheme information document | |
| Risk-o-meter, managers | Fund house's scheme page or factsheet | The source and date are printed beside each. |
| Holdings, sector split, asset split | The fund house's monthly portfolio Excel file; the page names the source and gives its address | Percent of net assets; the sector split is the sum of equity rows by industry. |
| Industry totals | AMFI "Monthly Report" workbook for the month (listing page `amfiindia.com/research-information/amfi-monthly`) | Figures in rupees crore as AMFI prints them. |
| ETF price, return | NSE closing price history | Price return, dividends excluded. |
| ETF NAV and premium | AMFI NAV file, by ISIN | `(close on the NAV's date / NAV - 1) x 100`. |

---

## 7. Open questions for the owner

1. **Dhan:** written permission to show Dhan's data publicly is still open (`docs/COMPANY-HANDOVER.md:66-67`; `docs/DHAN-SETUP.md:27`). It matters for ETF prices if Dhan is the live ETF price source (S16). Which source the live server uses for ETFs is not recorded in the code (decided at run time, `bf/etf.py:595-609`).
2. **Upstox:** the docs ask that every provider's terms for public display and caching be checked (`docs/COMPANY-HANDOVER.md:66`). No answer is recorded for Upstox.
3. **AMFI files (S1 to S10):** the code treats them as public files and sets a User-Agent naming FinLit. No licence or terms-of-use note for redistribution of AMFI data is recorded in the code or docs. This is open.
4. **api.mfapi.in (S3):** a third-party mirror used for on-demand history and the 10-year view. No terms or licence are recorded; the code comment calls it a mirror of AMFI data.
5. **Fund houses' own sites (S12 to S14):** no per-house permission or terms note is recorded. The code and docs state a rule of not going around blocks (`docs/NEXT-STEPS-FUNDS.md:15-16`; `ter.py:6-9`). Two practices are worth your decision: browser-style User-Agent strings on many adapters (`amcs.py:21`; `managers_risk.py:56`), and the Mahindra Manulife adapter using the key in the site's public script to read an encrypted answer (`houses_c.py:59-96`).
6. **Exclusions:** keep, widen or reverse the 11-house exclusion (`config.py:15`) and the HDFC / Kotak decision; each affects what visitors see.
7. **Expense ratio on the live server:** AMFI's TER feed is empty there. Decide whether to extend fund-house TER pages to the fund list column (today only the scheme page falls back) and which further houses to add.
8. **Doc corrections:** `docs/NEXT-STEPS-FUNDS.md` still says 38 fund houses (code: 39), `refresh-facts` at 21:40 (scheduler: 21:10 window), `refresh-portfolios` at 04:40 (scheduler: night chain), `refresh-industry` at 18:25 (scheduler: 19:10 window), and "only 1 day, 1 year, 5 year" (page also shows 3 years and SIP). The stale module notes in `bf/mf.py:22-23` and `bf/etf.py:5-6` also say fund size and expense ratio are not loaded.
9. **Could not be determined from the code:** the live counts today (only the dated figures in Section 1); whether AMFI's fund-performance feed (S9) answers from the live server; which fund-house adapters returned files on the last live run; the live ETF price source.
