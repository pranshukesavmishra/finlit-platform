# finlit_technicals

Three TradingView indicators in Python, for the FinLit website:

| Function | TradingView indicator | What it returns |
|---|---|---|
| `score(symbol, source)` | ST/LT Score Breakdown & Peers v1.2 | Short-term and long-term technical scores (−100 to +100), every component of the calculation (reading, signal, weight, points), the trend alignment (short-term band × long-term band) and the peer row |
| `peer_label(symbol, source)` | Leader & Laggard vs Peers v1.0 | Leader / In line / Laggard vs industry peers, rank, relative returns vs the sector and market index, the peers table and the weekly history |
| `SectorEngine(source)` | Sector & Leaders v2.0, on NSE's industries | `.board()`: every NSE industry's state (Washout, Thrust C / CAP, Confirmed, Fading, Neutral), breadth, the market context and live leader flags. `.industry(name)`: one industry page with a year of breadth history, its counted stocks and why the others are not counted. `.stock(symbol)`: the stock inside its industry (6-month quarter, leader flag, bottom timing) |

The data can come from NSE itself: `python -m finlit_technicals fetch-nse --dir nse` keeps a folder of NSE's daily
files (every stock since 2016, delisted ones included, and every index), and `NseHistory("nse")` reads it as a price
source for all three indicators.

The rules, weights and default settings are the indicators' own. The code follows Pine Script's rules for how
indicators start (EMA seeding, `na` handling), weekly bars (the last completed week) and benchmark series, so
the same daily bars give the same numbers as the chart. It needs **numpy**, **pandas** and **openpyxl** (to read
AMFI's market-cap lists). It has no broker or web framework in it.

Every label describes the chart's condition (Very strong … Very weak, "Strong on both timeframes",
"Short-term pullback within a long-term uptrend" …). The package has no buy / sell wording, trade calls, entries
or stops. The TradingView indicators' verdict ("STRONG BUY", "ACCUMULATE ON DIPS" …) is replaced by the trend
alignment below; the numbers and the band rules are unchanged. Not investment advice.

## 1. Install

```
pip install ./finlit_technicals            # or: pip install "./finlit_technicals[web]" for the Flask example
python finlit_technicals/tests/run_tests.py
```
Python 3.10 or newer, numpy 1.22+, pandas 2.0+, openpyxl 3.0+ (tested on Python 3.13 with pandas 3.0; the
calculations also on Python 3.10 with pandas 2.3).

## 2. Data it needs

### NSE's own files (recommended)

```
python -m finlit_technicals fetch-nse --dir /srv/finlit/nse      # first run about 40 minutes, then a minute a day
```
Run it every evening after 7 pm IST, before the batch. It skips what it already has, so an interrupted run is
simply run again. What it keeps (about 250 MB):

| Files | What |
|---|---|
| `bhav_<year>.csv.gz` | NSE's bhavcopy: every security traded each day since 2016 (prices as traded, volume, traded value, trades, series, ISIN) |
| `idx_<year>.csv.gz` | the close of every NSE index each day |
| `ref/EQUITY_L.csv`, `ref/symbolchange.csv` | listed stocks with names; NSE's symbol changes |
| `ref/corporate_actions.txt` | splits, bonuses, rights and demergers newer than the bundled list (from NSE's website) |
| `ref/industries_extra.json` | NSE industry of new listings missing from the bundled list (from NSE's website) |
| `amfi/<yyyy>H<n>.xlsx` | AMFI's half-yearly average market caps of all listed companies (2017 H2 onwards) |

`NseHistory(folder)` turns them into a price source:
- **Adjusted prices.** Corporate actions for 2016 to Oct 2026 are bundled (`data/nse_corporate_actions.txt`, 1,230
  lines from NSE's corporate-action records); newer ones come from `fetch-nse`. Splits, bonuses and consolidations
  use the stated ratio, rights issues the theoretical ex-rights price, demergers the opening gap. A move that no NSE
  price band allows (below 35% or above 2.8x of the last close) with nothing on file is treated as an unrecorded
  action.
- **One history per company.** Stocks are followed through NSE's symbol changes (ZOMATO → ETERNAL), and renames
  missing from that file are linked by ISIN (PHILIPCARB → PCBL). Old symbols resolve to the current one.
- **Delisted stocks stay.** Their history remains, so the sector study and the universe rules see the market as it
  was, not only today's survivors.
- **Holiday copies are dropped.** On many holidays since 2020 NSE serves the previous day's file; those days are
  removed (81 of them), and the trading days then match Dhan's calendar exactly.
- **Indices.** `index("NSE:NIFTY")` and every code in the table below come from the index files.
- **Speed.** The first build takes about 30 seconds and is cached in `<folder>/.finlit_cache/` (rebuilt when a file
  changes).

`fetch-nse` reads corporate actions and new listings' industries from NSE's website API, which sometimes refuses
scripts. When it does, the run says so and everything else still works: new listings stay unclassified, and splits
are caught only when the move is too large for any price band.

### Any other data

**Daily bars** for each stock and index: a pandas DataFrame indexed by date, columns `open, high, low, close,
volume`, oldest first. Prices must be adjusted for splits and bonuses, as any charting feed is. Give as much
history as you have; since 2017 is plenty (more only matters for stocks listed before that, and only in the
far decimals). For new listings, give everything since the listing day.

**Indices** are named by the codes below. Map them to your vendor's names. Each one is only needed in the
situations listed.

| Code | Index | NSE name | Needed for |
|---|---|---|---|
| `NSE:CNX500` | Nifty 500 | NIFTY 500 | RS benchmark when the market cap is unknown; market index for the peer label when the cap is unknown |
| `NSE:NIFTY` | Nifty 50 | NIFTY 50 | RS benchmark and market index, large caps |
| `NSE:CNXMIDCAP` | Nifty Midcap 100 | NIFTY MIDCAP 100 | RS benchmark, mid caps |
| `NSE:CNXSMALLCAP` | Nifty Smallcap 100 | NIFTY SMALLCAP 100 | RS benchmark, small caps |
| `NSE:NIFTYMIDCAP150` | Nifty Midcap 150 | NIFTY MIDCAP 150 | market index for the peer label, mid caps |
| `NSE:NIFTYSMLCAP250` | Nifty Smallcap 250 | NIFTY SMALLCAP 250 | market index for the peer label, small caps |
| `NSE:CNXIT`, `NSE:CNXPHARMA`, `NSE:NIFTYPVTBANK`, `NSE:CNXPSUBANK`, `NSE:CNXAUTO`, `NSE:CNXENERGY`, `NSE:CNXMETAL`, `NSE:CNXREALTY`, `NSE:CNXFMCG`, `NSE:CNXFINANCE`, `NSE:CNXMEDIA`, `NSE:CNXINFRA` | Nifty sector indices | see `sources.INDICES` | the peer label's sector benchmark (groups without one use the equal-weighted peer average) |

A missing index is treated as the chart treats a missing symbol. For the sector index the peer average is used
instead, and a note says so. For the RS benchmark the RS rows read as `None`.

**Market cap** (Rs crore) of the stock: `market_cap_cr=`. This decides the RS benchmark and the market index:
- Rs 1,07,000 crore or more: large cap (Nifty 50).
- Rs 32,800 crore or more: mid cap (Midcap 100 / Midcap 150).
- Otherwise: small cap (Smallcap 100 / Smallcap 250).

These are the AMFI cut-offs for the list in force from Aug 2026; change them in `StltParams` when AMFI revises
them. Alternatively pass `cap="large" | "mid" | "small"`. Without either, both use Nifty 500, as TradingView
does for a stock with no share count. Peers' market caps (`peer_caps=`) only break exact ties.

**Industries for the sector engine** are NSE's (`data/nse_industries.json`, 2,838 stocks including delisted ones,
collected from NSE's quote pages on 29 Oct 2026). See section 5, Sector views.

**Peer groups** for the peer label are bundled in `finlit_technicals/data/peer_groups.json`. These are the indicators' own lists:
TradingView industries and sectors, the 35 largest liquid NSE stocks in each, as of 27 Oct 2026. The spec's five
curated groups (IT, pharma, private banks, PSU banks, auto) are in `peers.py`. For a stock outside every list,
pass `industry="Steel"` (its TradingView industry) or your own `peer_list="A,B,C"`. Pass `groups_file=` to use
a refreshed list.

**When to run**: after the day's close, once the day's bar is in your database. The peer label uses only
completed weeks (Monday to Friday), so it changes once a week.

## 3. Use it

```python
from finlit_technicals import score, peer_label, NseHistory, SectorEngine, CsvFolder, MemorySource

src = NseHistory("nse")        # NSE's files (fetch-nse); or CsvFolder("prices") with stocks/SAMBHV.csv, indices/CNX500.csv ...
d = score("SAMBHV", src, market_cap_cr=4500)              # dict, ready for json.dumps
p = peer_label("SAMBHV", src, market_cap_cr=4500, table="all", history_weeks=52)
eng = SectorEngine(src)        # builds once, then answers from memory
eng.board(); eng.industry("Ferrous Metals"); eng.stock("SAMBHV")
```

To read from your own database, write a class with two methods and pass it as `source`:

```python
class MyDb:
    def daily(self, symbol):  ...   # -> DataFrame (open, high, low, close, volume) or None
    def index(self, code):    ...   # code is "NSE:CNX500" etc. -> DataFrame or None
```

`MemorySource({"SAMBHV": df}, {"NSE:CNX500": idx_df})` wraps frames you already hold. `Cached(source)` loads
each symbol once.

Options shared by both functions: `market_cap_cr`, `cap`, `industry`, `sector`, `peer_list`,
`group` (`auto | it | pharma | pvtbank | psubank | autosector | industry | sector | custom`), `peer_caps`,
`groups_file`.

Options for `score` only: `bench` (`auto | nifty500 | nifty50 | midcap100 | smallcap100`), `peers=False` to
skip the peer row, and `params=StltParams(...)` for any indicator setting (all defaults are the indicator's).

Options for `peer_label` only: `max_peers` (37 as in Leader & Laggard v1.0; the v1.2 peer row uses 30),
`table` (`"top10" | "all" | None`) and `history_weeks`.

Errors:
- `LookupError` when the source has no prices for the stock.
- `ValueError` for a bad option.

Missing peers or indices never raise. They show up in `notes`.

## 4. Nightly batch and serving

```
python -m finlit_technicals fetch-nse --dir nse
python -m finlit_technicals batch --nse nse --out site_data
```
- Writes `site_data/<SYMBOL>.json` (`{"score": ..., "peers": ..., "sector": ...}`) for every classified stock that
  traded on the last day (about 2,400 with `--nse`; with `--data`, every stock in the peer lists). Use
  `--symbols A,B,C` for your own list. With `--nse`, market caps and large / mid / small come from AMFI's latest
  list; `--caps` overrides them.
- Also writes `site_data/_summary.json`, one line per stock with the scores, bands, trend alignment, stage, peer
  label and rank, and its industry's state, 6-month quarter and leader flag, for lists and screener filters.
- And the sector pages: `site_data/sectors/_board.json` (Sector Pulse) and `site_data/sectors/<slug>.json` for each
  NSE industry or sector group (`ferrous-metals.json`, `pharmaceuticals-biotechnology.json`,
  `oil-gas-consumable-fuels.json` ...), with each stock's peer label joined in. `--no-sectors` skips them.
- `market_caps.csv` has the columns `symbol,mcap_cr` (Rs crore) and optionally `cap` (large / mid / small).
- Each stock takes about half a second for both indicators on one core, so 2,400 stocks take about 20 minutes.
  Split the list across processes to go faster. One bad stock is logged in the summary and does not stop the run.

`examples/flask_app.py` serves the batch output and computes live when there is no file or when the request
carries `?cap=` / `?mcap=`:

```
GET /api/technicals/SAMBHV/score
GET /api/technicals/SAMBHV/peers?table=all&weeks=12
GET /api/technicals/SAMBHV/sector
GET /api/technicals/summary
GET /api/sectors
GET /api/sectors/ferrous-metals
```
Start it with `FINLIT_NSE=nse FINLIT_OUT=site_data flask --app examples/flask_app.py run`.

The same takes a few lines in Django or FastAPI: call `score()` / `peer_label()` / the `SectorEngine` views and
return the dict.

Command line, for checking numbers by hand:
```
python -m finlit_technicals score SAMBHV --nse nse --mcap 4500         (add --json for the website's JSON)
python -m finlit_technicals peers SAMBHV --nse nse --mcap 4500 --all
python -m finlit_technicals sectors --nse nse
python -m finlit_technicals industry "Ferrous Metals" --nse nse
python -m finlit_technicals stock-sector SAMBHV --nse nse
```
`--data prices` works in place of `--nse` for a CsvFolder.

## 5. What comes back

Every value is a plain str / int / float / bool / None / list / dict. Dates are `YYYY-MM-DD`. Missing numbers
are `None`, never NaN, so `json.dumps(..., allow_nan=False)` works.

**`score()`**

| Field | Meaning |
|---|---|
| `date`, `close`, `bars`, `benchmark` | last bar used, its close, daily bars available, RS benchmark name |
| `short_term.score` / `long_term.score` | the scores (−100 to +100), 2 decimals; `display` is the rounded figure the chart shows |
| `.rating`, `.rating_code` | Very strong (+2, score ≥ +50), Strong (+1, ≥ +20), Neutral (0), Weak (−1, ≤ −20), Very weak (−2, ≤ −50) |
| `.band`, `.band_code` | Positive (1, ≥ +20), Neutral (0), Negative (−1, ≤ −20): the band that feeds the trend alignment |
| `.raw`, `.divisor` | Σ weight × signal, and the weights in use (96 and 92 with the default settings) |
| `.components[]` | `key` (stable id), `name`, `reading` (what the chart shows now), `signal` (−1 to +1), `weight`, `points`, `on`, `how` (how the reading becomes a signal) |
| `short_term.trend_factor` | ADX and the multiplier applied to the first three components |
| `long_term.stage`, `.capped`, `.uncapped` | Weinstein stage 1–4; in Stage 3 / 4 the score is capped at +19 |
| `trend_alignment.label`, `.code` | how the two trends line up (table below); `code` is a fixed id such as `st_positive_lt_negative` |
| `trend_alignment.how`, `.rule` | the sentence ("Short-term +39.3 (Positive) × long-term +35.3 (Positive) = Strong on both timeframes") and the band rule |
| `trend_alignment.cells[]` | all 9 cells of the 3 × 3 trend map (`st_band`, `lt_band`, `code`, `label`, `current`) for drawing the grid |
| `peers` | the peer row: the same fields as `peer_label()` without the table and history |
| `notes` | data gaps worth showing (missing index, short history ...) |

Trend alignment (short-term band down, long-term band across):

| Short-term ↓ / Long-term → | Positive | Neutral | Negative |
|---|---|---|---|
| **Positive** | Strong on both timeframes | Short-term strength, no long-term trend | Short-term bounce within a long-term downtrend |
| **Neutral** | Long-term uptrend, short-term pause | No clear trend | Long-term downtrend, short-term flat |
| **Negative** | Short-term pullback within a long-term uptrend | Short-term weakness, no long-term trend | Weak on both timeframes |

The labels are in `stlt.RATINGS` and `stlt.ALIGNMENT`; change the wording there and every output follows.

**`peer_label()`**

| Field | Meaning |
|---|---|
| `label`, `label_code` | Leader (1), In line (0), Laggard (−1) or No label (null): the published label |
| `this_week`, `pending` | this week's rank-based label; `pending` explains it when it differs (it shows if it holds next week) |
| `since`, `changed_last_run` | when the label started; whether the last weekly run changed it |
| `status` | one line: "3rd of 29 Steel peers · +29.9 pts vs Nifty Metal · +45.7 pts vs Nifty Smallcap 250 (12 months) · gaining over 3 months" |
| `state` | 0 ranked · 1 no peer group · 2 not enough history · 3 thin trading · 4 too few peers · 5 waiting for a completed week |
| `rank`, `ranked`, `leader_slots` | rank by 12-month points vs the sector benchmark, peers ranked, k = ceil(30% × ranked) |
| `relative_return_pts` | stock minus index return in % points: vs sector 3 / 6 / 12 months, vs market 12 months |
| `direction` | gaining / weakening (13-week figure ≥ +5 / ≤ −5 pts) / steady |
| `benchmarks` | sector index name (or "peer average") and market index name |
| `group` | peer group name, kind (spec group / industry / sector / custom), peers listed |
| `table[]`, `table_more`, `not_ranked[]` | the peers table (rank, symbol, status, this week, pts vs sector 12M / 3M, vs market 12M) and the excluded peers with the reason |
| `history[]` | the weekly runs: week ranked, label, rank, pts vs sector 12M and 3M, vs market 12M. These are the indicator's lines |
| `reliability` | the spec's research on whether leadership has held in this group (IT, pharma, banks, auto) |
| `runs_last_52` | counts of Leader / In line / Laggard over the last 52 weekly runs |

**Sector views** (`SectorEngine`; every percentage is a share of the group's counted stocks, 0–100)

*Which industries.* NSE classifies every company on four levels: Macro-economic Sector > Sector > Industry > Basic
Industry (Commodities > Metals & Mining > Ferrous Metals > Iron & Steel). The engine uses the **Industry** level. An
industry with fewer than 10 counted stocks today is read together with the other small industries of its NSE
Sector, as one group named after the sector (Oil + Gas + Consumable Fuels = "Oil Gas & Consumable Fuels"). A group
needs 8 counted stocks with prices on a day to have a reading; groups below that are listed in `too_few_stocks`.
On Oct 29, 2026: 46 groups, 37 with a reading (31 NSE industries), 1,198 stocks counted.

*Which stocks count* (`universe.py`). Rebuilt on the first trading day of each month from data up to the day
before, so history uses only what was known then:

| Rule | Setting | Why (noise test on 175,000 stock-months, 2017–2026) |
|---|---|---|
| Series | NSE main board, EQ series (not trade-for-trade BE / BZ, not SME); leaves at once on a move to BE / BZ | trade-for-trade stocks are mostly under surveillance and jump |
| Liquidity | median daily traded value over 65 sessions ≥ Rs 2 crore to join; stays until under Rs 1 crore | correlation with the industry rose and 10% one-day jumps fell steadily up to about Rs 2–5 crore, then levelled off |
| Regular trading | traded on 62 of the last 65 sessions; leaves after 5 sessions without a trade | a day without trades repeats the last close |
| Not locked | at most 1 of the last 65 sessions with high = low | a single locked session already doubled the return autocorrelation |
| Price | Rs 20 or more | below Rs 20 closes were unchanged 3–10 times as often |
| Size | AMFI average market cap ≥ Rs 1,000 crore to join; stays until under Rs 800 crore | correlation with the industry flattened above Rs 1,000 crore |
| Seasoning | 126 sessions traded since listing | early IPO swings; a new listing's "52-week high" is only its high since listing |

The rupee floors are in today's money; earlier years use them scaled by NSE's turnover (liquidity) and AMFI's total
market cap (size) at the time. The thresholds were set on these noise measures before any return was looked at.
With a source other than `NseHistory`, the same rules run on close × volume, and the size rule needs `amfi_dir=`.

| Field | Meaning |
|---|---|
| `name`, `slug`, `kind`, `sector`, `industries` | the group; `kind` is `industry` or `sector` (a group of small industries, listed in `industries`) |
| `state`, `state_code`, `meaning` | Neutral, Washout, Thrust C, Thrust CAP, Confirmed, Fading (`washout`, `thrust_c` ...) and a one-line meaning |
| `breadth.above_9 / above_20 / above_50` | share of counted stocks above their 9, 20 and 50-day EMA today |
| `breadth.lowest_50_last_30` | lowest 50-day reading in the last 30 sessions: under 40 is what makes a Washout |
| `index_vs_52w_high` | the equal-weighted group index vs its 52-week high, % |
| `last_60d_low` | when that index made its most recent 60-day low (`sessions_ago`, `date`) |
| `higher_low_share` | at that low, the share of stocks still above their own earlier lows; under 20 = capitulation |
| `last_thrust` | `type` (C / CAP), `date`, `sessions_ago`; `today` flags a thrust, Fading or Confirmed event on the last day |
| `stocks_counted`, `stocks_listed`, `stocks_traded_today`, `leader_flags` | counted stocks, the group's stocks trading today, counted stocks with a price today, live leader flags |
| board `counts`, `market`, `market_note` | groups per state; the Nifty 50 vs its 200-day average with a one-line note on what the study found in such markets; a note when more than half the groups are Fading |
| board `universe` | the "which stocks are counted" block: classified stocks that traded on the last day, how many meet the rules, how many are counted in groups with a reading, and `reasons[]` (each reason with its number of stocks; most stocks miss several, so these add up to more than `not_counted`) |
| board `leader_flags[]`, `too_few_stocks[]` | every live flag (symbol, group, tier 15%+ or 10–15%, `sessions_ago`, `new_today`, 6-month quarter); groups without a reading |
| board `universe_rules`, `study` | the rules in one paragraph; the study's market and rally findings, limits, and every figure (`study.figures`, the same as `data/sector_study.json`) |
| industry `summary`, `rule`, `since` | one plain-English paragraph, the state's rule, the day the state began |
| industry `history` | `dates`, `above_9/20/50`, `state_code`, `index_vs_52w_high`, `stocks_counted` for each session (default 260) |
| industry `bands[]`, `events[]` | runs of one state (`from`, `to`) for the chart's shading; thrust, Fading and Confirmed days for its markers |
| industry `stocks[]` | each counted stock ranked by 6-month return: `name`, `industry`, `quarter`, `bottom`, `leader_flag`, `amfi_category`, `peer_label` |
| industry `not_counted[]` | the group's other stocks trading today, each with `not_counted_because` (plain-English reasons) |
| industry `study`, `leader_flag_note` | what the study found for this state, the market context, rallies, each stock column and the limits |
| stock view | the stock's `industry`, `sector`, `amfi_category`, the group's row and summary, then `rank_6m` of `ranked_6m`, `quarter_name`, `bottom`, `leader_flag`, `leader_flag_text`; or `in_group: false` with `not_counted_because` and a `note` |

The wording describes the group; it never says what to do. The rules are those of Sector & Leaders v2.0 (the same
code as the dhan_alerts nightly scan).

**The study behind the wording** (Nov 2026; NSE data from Jan 2016, cases Jan 2017 to Oct 2026, 46 groups, the
universe rebuilt monthly and delisted companies included). Measured on the group's equal-weighted index: "rose 15%
first" means it closed 15% above the event day before it closed 8% below; points are the next 60 sessions against
the same group's average 60 sessions.

| | Cases | Rose 15% first | Points vs usual | Notes |
|---|---|---|---|---|
| Thrust C | 476 | 48% | +1.1 | about zero when averaged week by week (132 weeks) |
| Thrust CAP | 214 | 47% | +4.2 | −0.6 without 2020 |
| Thrusts, Nifty 50 below its 200-day average | 256 | 67% | +9.4 | 44 separate weeks; +6.5 without 2020 (215 cases, 36 weeks) |
| Thrusts, Nifty 50 above its 200-day average | 434 | 36% | −2.2 | 123 separate weeks |
| Confirmed | 857 | 50% | +0.9 | a median 30 sessions after the low |
| Fading | 1,517 | 44% | +0.2 | |
| Leader flag, 15%+ tier (vs industry, 120 sessions) | 644 | – | +6.0% (median +2.8%, 55% beat) | average member on the same days −0.2% (43%); 2020 −3.9% |
| Leader flag, 10–15% tier | 837 | – | +0.8% (median −1.5%, 47%) | |

Big rallies (25%+ within 120 sessions of a 60-session low): 285; a C or CAP thrust came within 20 sessions of the
low in 145 (51%), typically 5 sessions after it. Quarter by 6-month return at a C thrust: top +0.8, bottom −1.6
points over 60 sessions; no order after a CAP. Bottom timing: no meaningful difference. Limits: cases overlap in
time; the market split was examined after seeing results; NSE's labels are today's; costs are ignored. The
earlier figures (58% / +3.0 points for C, 67% / +10.0 for CAP) came from the 35 largest stocks per TradingView
industry as listed today, which left out companies that later failed.

## 6. Matching TradingView

- Same bars, same settings → same numbers. Differences come from data:
  - a stock with more history on one side;
  - a different volume figure (this affects the peers' Rs 1 crore a day liquidity floor);
  - today's bar, which TradingView shows live while a database has it after the close.
- Assumptions about TradingView internals that only matter at the edges:
  - `ta.percentrank` divides by the full length even when part of the window has no data. This affects the
    long-term RS rating of stocks with less than about two years of history.
  - Of two equal swing highs, the first is the pivot.
  - `ta.highest` / `ta.lowest` give no value until the window is full.
- Tests: `tests/test_core.py` checks the Pine built-ins against slow reference versions and Wilder's textbook RSI
  example, the scores, the labels, the swing-failure pattern, the volume profile, the peer ranking and the two-week label
  rule. `tests/test_api.py` checks the JSON, the data sources, the batch, the command line and the Flask example.
  `tests/test_sectors.py` builds a small NSE folder with the awkward cases (a split, a rename, a rename missing from
  NSE's file, a delisting, an IPO, a move to trade-for-trade, a holiday copy, thin, locked, cheap and small stocks)
  and checks the data layer, the universe rules and reasons, the breadth engine (washout, thrust, leader flag), the
  three sector views, the downloader's parsers, and the batch, command-line and Flask sector paths.

## 7. Files

```
finlit_technicals/pine.py      TradingView built-ins (ema, rma, rsi, atr, dmi, macd, percentrank, pivots ...)
finlit_technicals/stlt.py      ST / LT scores, components, ratings, trend alignment
finlit_technicals/peers.py     leader / laggard: peer groups, weekly runs, ranking, stability rule
finlit_technicals/api.py       score(), peer_label() and their JSON
finlit_technicals/sectors.py   sector breadth engine and the board / industry / stock views
finlit_technicals/universe.py  which stocks count, month by month (the rules above), AMFI market caps
finlit_technicals/industries.py NSE industries and the groups the engine reads
finlit_technicals/nse.py       NseHistory: NSE's files as a price source (adjustments, renames, delistings, indices)
finlit_technicals/fetch.py     fetch-nse: downloads and updates NSE's files
finlit_technicals/sources.py   data source interface, CsvFolder, MemorySource, Cached, index codes
finlit_technicals/batch.py     nightly run -> one JSON per stock + _summary.json + sectors/
finlit_technicals/data/peer_groups.json          the indicators' peer lists (27 Oct 2026)
finlit_technicals/data/nse_industries.json       NSE industry and sector of 2,838 stocks (29 Oct 2026)
finlit_technicals/data/nse_corporate_actions.txt NSE's splits, bonuses, rights, demergers 2016 - Oct 2026
finlit_technicals/data/sector_study.json         the study's figures
examples/flask_app.py          example web API
```
