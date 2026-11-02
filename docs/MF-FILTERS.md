# Mutual Fund Screener: filters (page `/funds/screener`)

Code: `backend/finlit/mfscreen/` (spec = filter registry and parser, facets = counts/histograms in one call, calc = pure figures, job = nightly fill, api = stock search),
migration `081_mf_screen.sql`, `frontend/src/pages/MfScreener.tsx`, `frontend/src/mf/screen/*`, `frontend/src/lib/mfScreen*.ts`. Spec: "FinLit MF Screener Filter Specification v1.1".
Descriptive only: no buy / sell / hold / avoid / target / "best". Free plan.

## API
* `GET /api/mf` keeps every old parameter. New: `subs cap style struct mat amcs house plans options inst status family fresh aumbasis aumrank launch_from launch_to rng=field:min:max nd=field rk chk chk_each exit tick tags sector sector_min holds pfdate cflow cstreak csize extra`. All values are checked against fixed lists (unknown = HTTP 400) and travel as bound parameters. `extra=true` adds each row's screener figures (`x`).
* `GET /api/mf/filters?screen=true&<same filters>` returns in ONE call: count beside every option (each group counted with the other groups' filters applied), a histogram and "N of M funds have this figure" for every numeric field, the return-vs-risk points, the category flow bars, and what the nightly job built. Without `screen` the answer is unchanged. Cached by data version and filter state; ETag/304.
* `GET /api/mf/screen/stocks?q=` finds NSE symbols held by funds (for "holds this stock").
* Nightly job `refresh-mf-screen` (registry job `mf-screen`, group funds, after facts, industry, portfolios; docs/JOBS.md) fills `mf_screen`, `mf_screen_hold`, `mf_cat_flow` in one transaction; idempotent; no network. Run by hand: `python -m finlit.worker refresh-mf-screen`.

## Status of every filter
Built = works on stored data today. Partial = works, with a stated coverage gap shown in the panel as "N of M funds have this figure". Not built = shown disabled under "Needs a data source".

| Spec section / filter | Status | Note and free route (spec F-codes) |
|---|---|---|
| 2 Type, sub-category, cap chips, investment style, scheme structure | Built | Counts per value. Cap chips and style are lookups on the sub-category. |
| 2 Debt maturity band | Built (category band) | Labelled "category band", not measured duration. |
| 3 Fund house with counts, house size | Built | House size = sum of the house's families' size (understated where a scheme has no size). |
| 3 Geography | Not built | Needs scheme-name keywords + holdings ISIN check (F-F, F-B). |
| 3 House parentage | Not built | Needs the 45-row hand table (F-F). Owner action. |
| 3 House has full data | Partial | Tick "Has a portfolio" and the portfolio group's no-data count say it per fund. |
| 4 Plan, option, instrument, status, family view, freshness | Built | Defaults: Direct, Growth, still publishing, funds + ETFs. Instrument: ETF list or AMFI ETF categories. |
| 5 Size (AUM), basis, rank by size, share of category, net-assets change, age, launch date | Built / Partial | Size and TER coverage depends on the AMFI fetch (see owner actions). Net-assets change uses the 3 stored month-ends only (F-G for longer). |
| 6 Returns 1Y/3Y/5Y, SIP 3Y/5Y, excess over category, rank/quartile, 1 day, 1M, 6M | Built / Partial | 1M and 6M exist for the ~100 largest funds only (F-H to fill all). Calendar-year returns (the three full years before the run's year, December to December month-end NAV) and the biggest monthly gain of the last 36: Built (`x_cy1..3`, `x_up_month`, migration 086). |
| 6 Consistency | Built | Share of last 36 months ahead of the peer median. |
| 7 TER, vs category, Direct-Regular gap, fee share | Built / Partial | Partial where AMFI TER is missing (F-A, F-B). |
| 7 Exit load, exit percentage | Partial | Read from the fund house wording already stored (about 74%). Bands are exclusive. |
| 8 Volatility 1Y/3Y, biggest fall, worst month, worst 12 months, share of negative months, time below high, downside capture, Sharpe (6%), quick ticks | Built | From month-end NAVs. Downside deviation (root mean square of the falling months x sqrt 12) and volatility against the category median (3-year volatility / median of the same sub-category and plan, needs 3 peers): Built (`x_down_dev`, `x_vol_rel`, migration 086). |
| 8 Risk-o-meter (scheme, benchmark) | Not built | Needs AMFI file from an unblocked host (F-A), then fund-house pages (F-B, F-C). |
| 9 Asset split, equity share, holdings count, top-10, largest holding, sector exposure, holds a stock, portfolio date, net assets | Built / Partial | Only houses with a parsed portfolio file; others show in the "no data" count, never as zero. |
| 9 Recent moves in a stock, large/mid/small cap share, portfolio P/E, quality, health | Not built | Need 2 stored months (F-G), the AMFI cap list (F-D) and a join to stock ratios (F-E). |
| 10 Sector/theme, technology and AI, global themes, factor, index tracked | Built (name tags) | Our own editable table `mf_tags` (keywords + optional portfolio-sector rule, review date). Accuracy depends on names; the panel shows how many funds are tagged. Staff edit rows in SQL; there is no admin screen yet. |
| 10 Commodities (gold/silver) | Built | Via sub-category "Gold ETFs", "Silver ETFs". |
| 10 Benchmark, index tracked from benchmark text | Not built | F-A, F-D, F-E. |
| 11 Checklist passed / each check | Built | Existing checklist. "Score movement" Not built (needs score history). |
| 11 Health score, labels, pillar scores, confidence, rank in group | Not built here | Gold feature: use /fund-score-screener. The preset "Health score 65+ at low cost" is shown disabled. |
| 12 Debt / Hybrid / ELSS / index / ETF panels | Partial | Debt: maturity band, worst month, fee share, top-10, exit load. Credit rating: Not built (F-B, F-C). ETF-only panel (traded value, premium) and tracking error: Not built. |
| 13 Category net flow, streak, size, AUM and folio growth | Built | From AMFI's monthly category report via `mf_cat_flow`. Overseas fund-of-funds underlying market: Not built. |
| 13 Hot funds, most opened | Built | |
| 14 Data-quality ticks (TER, exit load, portfolio, 5-year history) | Built | Risk-o-meter, benchmark, managers, confidence 80%: Not built (refused by the API). |
| 14 Fund manager search | Not built | F-B, F-C. |
| 14 Presets (11) | 10 built, 1 disabled | Each is a plain set of filters, editable. "Small caps that fell less" uses "fell less than the category median" (not the best-quartile rule). |
| 14 Sort options | Built | Size, 1Y/3Y/5Y, SIP, expense, biggest fall, rank in category, age, name; health score for Gold. |

## Owner actions
1. Enable the nightly job: it runs with `FUND_LOADS_ENABLED=1` (job `mf-screen`). Run `python -m finlit.worker refresh-mf-screen` once after deploy; until then risk/rank/portfolio/category filters show "no data" honestly.
2. Run the AMFI expense-ratio and AUM fetch from a host AMFI accepts (F-A); without it TER and size are partial and the checklist's second check is unknown for many funds.
3. Fund-house portfolio files for HDFC, Kotak, Edelweiss, Navi, Union and PDF-only houses (F-B, F-C) to remove their "no data".
4. Review `mf_tags` keywords and set `reviewed_on`; check how many passive funds got an index tag (shown in the panel) before promising "Index tracked".
5. Fund-house parentage table (F-F) and the AMFI half-yearly cap list (F-D) if those filters are wanted.
