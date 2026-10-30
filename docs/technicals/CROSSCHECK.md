# Cross-check: our technical engine against independent indicator code, and why a number can differ from TradingView

Reproduce: `PYTHONPATH=site-api/backend python docs/technicals/crosscheck.py [--json out.json]` (pure Python; numpy and pandas are not in the project's
environments and are **not** added). The reference code in the script is written from the textbook definitions, loop by loop, and shares nothing with
`site-api/backend/technical_series.py`. Data: the five real recorded series in `site-api/backend/tests/fixtures/premium_replay` (TCS, HDFCBANK, SKIPPER,
BAJFINANCE, HDFCLIFE, 1 Jan 2020 to 26 Oct 2026, about 1,680 sessions each) and seeded synthetic walks. No index bars are recorded, so the index is the
equal-weighted mean of the five stocks, the same in every variant: each difference below isolates its factor. The two recorded candles with a close/open outside
their range (TCS and HDFCLIFE, 1 Feb 2026) are clamped in this script only; production withholds such a candle (INCIDENT-2026-10.md, section 3).

## 1. Indicators: maximum absolute difference, ours against the textbook (5 real series; 3 synthetic series of 1,500 bars gave at most 7e-12)

| Indicator | Max difference | Presence mismatches |
|---|---|---|
| EMA 9 / 20 / 50 / 100 / 200 (SMA-seeded, Pine's `ta.ema`) | 2.7e-12 / 1.8e-12 / 5.5e-12 / 5.9e-12 / 2.0e-11 | 0 |
| RSI 14 (Wilder) | 3.6e-14 | 0 |
| MACD 12/26/9: line / signal / histogram | 2.7e-12 / 2.6e-12 / 1.2e-12 | 0 |
| ATR 14 (Wilder; first true range = high - low, as Pine) | 7.1e-14 | 0 |
| ADX / DMI 14 (Wilder) | 5.0e-14 | 0 |
| OBV | 0 | 0 |
| Bollinger 20, 2 (population standard deviation, as `ta.stdev`) | 9.1e-13 | n/a |

Conclusion: the indicator functions are **not** a source of error. (The model's other rules, the 15 + 14 components, equal the team's `finlit_technicals`
package on identical bars: PARITY.md.)

## 2. Warm-up: how many bars the recursive indicators need (max over the 5 stocks; difference at the last bar against the value from all ~1,680 bars)

| Indicator | last 250 bars | 500 | 750 | 1,000 | 1,500 |
|---|---|---|---|---|---|
| EMA 200 (price units) | 42.8 | 6.15 | 0.048 | 0.0053 | 0.0001 |
| RSI 14 | 2e-7 | 1e-14 | 0 | 0 | 0 |
| MACD line | 6e-7 | 0 | 0 | 0 | 0 |
| ADX 14 | 1e-6 | 7e-14 | 0 | 0 | 0 |

The research API requests six years from Dhan (about 1,500 sessions): the values are TradingView's to four decimals (TradingView itself starts from the first
bar the chart holds, so it equals the full-history value). The FinEdge fallback requests `year - 6` to `year`.

## 3. Effect on the final scores (short-term ST / long-term LT), per stock

Full history (clamped T3): TCS ST +33.85 LT -3.80; HDFCBANK -23.96 / -51.09; SKIPPER -33.33 / -11.96; BAJFINANCE -32.55 / -35.87; HDFCLIFE -5.21 / -51.09.

| Factor | Effect |
|---|---|
| **Number of bars fed** | Last 600, 1,000 or 1,500 bars: **identical** to the full history (difference 0.0, ST and LT). Last 400 or 260 bars: **LT withheld** (the long-term relative-strength rank needs about 505 aligned sessions); ST unchanged except BAJFINANCE with 260 bars (-36.72 against -32.55: 4.2 points, the EMA 200 / ADX warm-up). **Rule: at least about 600 bars.** |
| **Live (unfinished) bar** (simulated: halfway to the close, 45% of the volume) | ST: TCS 0.0, SKIPPER 0.0, BAJFINANCE 0.0, HDFCLIFE 0.0, **HDFCBANK +5.2** (-23.96 completed, -18.75 live); LT unchanged for all five. TradingView draws the live bar during the session, so an intraday difference of this kind is expected; **after the close both use the same bar**. The model deliberately uses the last completed session. |
| **One session of staleness** (the previous session's score against the latest) | ST moves 4 to 14 points in one session: TCS +33.85 vs +20.31 (13.5), HDFCBANK -23.96 vs -18.75, SKIPPER -33.33 vs -37.50, BAJFINANCE -32.55 vs -28.39, HDFCLIFE -5.21 vs -1.04; LT up to 8 (BAJFINANCE -35.87 vs -27.72). A view a week old (what H1 produced) is worse. This is the dominant, measured cause of "our number differs from other platforms". |
| **EMA seed** (first-value against SMA seed, T1) on the full history | **0.0** for all five. On the last 250 bars BAJFINANCE ST -36.72 (first-value) against -32.55 (SMA): 4.2. Only a short history shows the seed; the engine is on Pine's seed. |
| **An unadjusted bonus issue** (1:2, 60 sessions back; the one-day drop is 30 to 34%, **below the 40% plausibility check**) | ST: TCS -8.3, HDFCBANK -4.2, SKIPPER -8.3, BAJFINANCE -6.3, HDFCLIFE -14.6; LT: TCS -51, HDFCBANK -17, SKIPPER -46, BAJFINANCE -28, HDFCLIFE -12 points. This is the one factor that could make a score **seriously wrong** and not be caught; it needs the provider to deliver an unadjusted series (Dhan says it adjusts). Open item: INCIDENT-2026-10.md, section 3. |
| **A close a rounding step above the high** (T3) | Before: one such bar cut the history to the bars after it and withheld both scores (4 of 5 recorded stocks, raw FinEdge rows). Now: within 0.05% it is taken as the high/low; beyond that (the two recorded cases are 1.2% and 0.8%) the candle is still withheld. |
| **Provider's all-zero holiday rows** (T2) | Fixed earlier; without the fix all five stocks lost both scores. |
| **Index missing some of the stock's sessions** | The long-term score (and the ST RS rank) is withheld for all five stocks with an index that lacks 3 of their dates; the harness fills the gaps. |

## 4. Cost

One full assessment: **0.57 s (TCS, 1,682 bars) and 0.60 to 0.67 s (BAJFINANCE, 1,679 bars)** of one core, pure Python (this machine).

## 5. What to tell the team when a number differs from TradingView

1. Is the date the same? Our card says "Technical view as of <date>"; TradingView's daily chart must end on the same completed day (turn the live bar off / compare after the close).
2. Same prices? Adjusted for splits and bonuses, NSE series. A split/bonus in the last year is the one case that can change a score by tens of points.
3. Same history length? Our engine uses about six years; TradingView's value is the same to four decimals once 750+ bars are loaded.
4. Same rules? The scores are the 15 + 14 components of the ST/LT indicator with sector comparison off (weights 96 and 92), the ADX trend factor and the Weinstein stage limit; a TradingView user with the sector option on will see a different total.
