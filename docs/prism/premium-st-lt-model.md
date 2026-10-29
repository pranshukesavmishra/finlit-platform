# Premium ST/LT score and verdict

## Scope and source

The owner's `st_lt_score_v14_3.pine` defines this additive market assessment.
Source SHA-256: `8fd234be9c7c76f750eb315530f525e9a8b8359ee90efbb183e524f8e618e078`.
The earlier six-page PDF explains the model; executable v14.3 resolves the exact
rules and boundaries. In particular, exactly -50 is **Sell**, as in `f_rate`.

Only short-term score, long-term score, combined verdict and the factors behind
them are implemented. Entry/exit plans, stop-losses, targets, position sizing,
confluence trade gates, simulated transactions and backtests are excluded.
Scoring dependencies remain even if their Pine settings appeared in a trade-plan
input group: the 5/15-bar pivots and 60-bar, 24-bin profile are examples.

The output appears only in Premium Reports and their PDF downloads. It is
independent of the existing financial-health score and does not change the
financial statements, source policy, industry classification or health model.
TradingView supplies **no runtime data**; the Pine file is the algorithm reference.

## Modules

| Module | Responsibility |
| --- | --- |
| `premium_technical.py` | Validate candle data, choose one stock series, aggregate signals, map ratings/verdict, assemble the report contract. |
| `technical_series.py` | EMA/Wilder smoothing, RSI, MACD, ATR/ADX, OBV, weekly closes, regression, percentile rank, beta and benchmark series. |
| `technical_patterns.py` | Confirmed pivots, untouched-level sweeps, SFP confirmation/invalidation/age, range-distributed volume profiles and value migration. |
| `technical_scoring.py` | Scoring-only translation of the owner's daily/weekly indicators and ST/LT rules. No provider calls. |
| `premium_technical_sources.py` | FinEdge index history, complete Upstox fallback, session-date checks and bounded 15-minute cache. |
| `premium_service.py` | Attach the assessment after financial-health scoring. |
| `PremiumTechnicalAssessment.jsx` | ST/LT score cards on a -100 to +100 scale, verdict, supporting/adverse/neutral signals and missing inputs. |
| `premium_pdf.py` | Export the exact signed assessment without provider calls or rescoring. |

## Data resolution

Use reported FinEdge values first, legitimate calculations second, then Upstox;
otherwise expose the missing dependency. Stock data starts with the shared
Stock Fundamentals dashboard's **untouched** resolved provider history. Its
price-chart normalisation substitutes close for absent open/high/low, so a
separate `technicalPrices` capture precedes those display defaults. These defaults
must never become candle observations.

FinEdge `/daily-quotes/{symbol}` supplies adjusted closes and volume, but the
observed response does not supply full historical OHLC. OHLC cannot be recovered
from close alone. A complete series from the existing Upstox daily-candle
connector therefore supplies the technical model when needed. Do not combine
FinEdge closes with unadjusted OHLC or splice exchanges. The health model keeps
its original dashboard inputs. Price-series provenance and corporate-action
adjustment limitations are disclosed in the assessment.

Daily sessions are excluded until 16:00 IST. Weekly values follow Pine's
`request.security(..., W, indicator[1], lookahead_on)`: use the week preceding the
latest evaluated daily bar, including when that bar is a Friday. No current-week
lookahead is introduced. Market holidays and special sessions follow actual
provider dates; there is no fabricated weekday-only calendar.

### Benchmarks

| Market-cap class | Threshold, INR crore | FinEdge symbol | Upstox instrument |
| --- | --- | --- | --- |
| Large | >=107000 | NIF50 | NSE_INDEX\|Nifty 50 |
| Mid | >=32800 and <107000 | NIFMID100 | NSE_INDEX\|NIFTY MIDCAP 100 |
| Small | <32800 | NIFSMA100 | NSE_INDEX\|NIFTY SMLCAP 100 |
| No usable shares / fallback | Source rule | NIF500 | NSE_INDEX\|Nifty 500 |

These are the **supplied model defaults**, not automatically refreshed AMFI
thresholds. Market cap is resolved crore shares multiplied by that bar's close.
The benchmark may therefore change through the history. Each index's returns,
log returns and rolling highs are calculated on its own series before selection,
matching Pine's `f_bpack`/`f_pick`; no return is taken across two different indices.

FinEdge `/index/market-price/historical` is the primary source, using six years
of history. A series must have the required matching stock-session dates as well
as enough recent observations. Live checks found FinEdge omissions including
24 September 2026; a long record count alone is insufficient. When needed, one
complete Upstox index series replaces the incomplete index series. Do not fill
missing index closes with zero, yesterday's close or another provider's day.
All four indices are available to preserve historical cap-group changes and the
source's Nifty 500 fallback. Provider identifiers were checked against FinEdge's
index master and Upstox's official NSE instrument list.

## Numerical rules

- ST: 15 source components, weights total 100. Sector comparison defaults off,
  so 14 signals remain and the denominator is **96**. Value migration stays on.
  Explicitly switching it off as well would make the denominator **90**.
- LT: 14 source components, weights total 100. Sector off leaves 13 signals and
  denominator **92**. There is no sector-index selection UI in this implementation.
- Score = `100 * sum(weight * signal) / enabled_weight`, each signal in [-1,+1].
  Missing signals never reduce the denominator or become neutral values.
- ST applies the source ADX multiplier only to EMA stack, price/EMA20 and MACD.
  RSI regimes, consolidation, squeeze release, gaps, candle priority, SFPs,
  leadership and value migration follow the v14.3 conditions.
- Profiles distribute each bar's volume uniformly over its high-low range,
  across 24 bins. First maximum-volume bin wins a POC tie; adjacent-bin ties
  expand upwards. Value area contains 70% of volume. This is the **source's
  specified approximation**, not a claim to reconstruct actual volume at price.
- SFPs scan existing untouched pivots before inserting newly confirmed pivots.
  Swept levels are consumed whether they fail or break. Confirmation, death,
  inclusive 5/15-session age limits and bearish priority on equal timestamps
  follow the source.
- Beta uses 126 daily log-return pairs, clamped to 0.3–3.0; undefined beta uses
  the source's default 1.0. Excess returns use ordinary 21/63/126/189/252-session
  percentage returns. ST/LT weighted excess returns are ranked against their
  previous 126/252 observations, counting ties as less-than-or-equal.
- EMA recursion follows Pine's `ta.ema`: no value until `length` consecutive
  observations, then their simple average, then recursive (changed with the
  finlit_technicals v1.1 delivery; before, it was seeded at the first observed
  value, which differs from the chart for histories under about 1,000 sessions
  and flipped a close EMA 100 / EMA 200 comparison in 2 of 90 test series).
  ATR/RSI/ADX use Wilder smoothing with an initial arithmetic mean; ATR's first
  TR uses high-low.
  BB standard deviation and beta variance are population calculations.
- Stage uses 150-day SMA, its 50-session slope and slope 50 sessions earlier,
  plus the exact breakout-volume rules. Fresh Stage 2 lasts <=60 sessions after
  Stage 1. Stage 3/4 caps LT at +19 before rating/verdict. `freshOnly` is off.
- Rating: >=50 Strong Buy; >=20 Buy; >-20 Hold; >-50 Reduce; otherwise Sell.
  Verdict bands: >=20 bullish, <=-20 bearish, otherwise neutral. All nine
  combinations use the source matrix and its green/amber/red mapping.
- Scores retain full precision for ratings/verdict. Rounding is display-only.
  Implementation hashes are not shown to report readers. Each row's weight is shown
  (the indicator publishes them; see docs/technicals/README.md): the report shows
  weight and points per row, the divisor, the ADX trend factor and the stage
  limit. The model's own verdict words are never shown; the nine verdict cells
  are shown as the descriptive trend alignment (short-term band x long-term band).

## Missing data and availability

For a fully rated assessment all enabled signals must be available. ST can be
ready before LT; a combined verdict requires both scores. The long RS history
requires 505 aligned observations with the previous-252-observation percentile
convention. Weekly MACD requires enough preceding weekly closes. Current trend
components also require their documented daily comparison history.

An invalid candle is retained as a gap during parsing. The engine uses only the
complete consecutive suffix after the last invalid OHLCV observation; it never
compresses returns across missing candles. Volume zero is valid. An absent value
is not zero. Undefined flat-series RSI or zero-ATR extension is explicitly
unavailable. Data more than 10 calendar days old is withheld as a current score.
These are data-integrity safeguards; they do not change the source weights.

No prior swing profile and no active SFP are **neutral under explicit source
rules**, rather than missing-data fills. Missing share count triggers the source's
Nifty 500 benchmark fallback and is disclosed.

## Report contract and lifecycle

`technicalAssessment` contains `modelVersion`, `sourceCodeSha256`, `inputHash`,
`status` (ready/incomplete), `asOf`, `provider`, `dailyBars`, `usableDailyBars`,
`fresh`, `shortTerm`, `longTerm`, `verdict`, `notes`, `observations`,
`benchmarkSources` and `options`.

Each horizon contains nullable `score`, `rating`, `status`, `horizon`,
`availableCount`, `requiredCount`, `stageCapped`, and `factors`. Factors contain
`key`, `label`, `weight`, nullable `signal`, `status`
(available/unavailable/disabled), and a reader-facing observation or missing reason.
`observations` exposes stage, freshness of Stage 2, SMA slope, selected benchmark,
benchmarks used over the comparison window, beta and ST/LT RS percentiles.
`benchmarkSources` gives provider, last date and observation count for each index.
The technical hash covers stock candles, benchmark inputs, shares and source hash.

This field is included in the existing signed snapshot. PDF export does not
fetch or recalculate anything. There is no new persistence or public endpoint.
Older snapshots without the field remain viewable; recalculate to get ST/LT.

## Validation and practical limits

Tests cover source weight totals, option denominators, all verdict combinations,
exact rating boundaries, stage caps, weighted reconstruction, percentile ties,
benchmark-class crossings, SFP transitions, profile allocation, missing histories,
provider precedence, session-date recovery, cache behaviour, snapshot integrity,
PDF output and frontend rendering. Existing health-model tests remain in place.

Real provider runs verify end-to-end data availability across large/mid/small
stocks. Exact screen-for-screen TradingView parity has **not** been independently
established: a dated reference export using the same adjusted candles, history
start and settings is required for that comparison. Data-provider adjustment and
exchange differences may change indicators near signal thresholds. The report
states its actual source and as-of date rather than implying identical feeds.
