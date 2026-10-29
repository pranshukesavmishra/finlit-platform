# Parity: our two engines against finlit_technicals v1.1

Both engines were run on **identical bars** and the answers compared. Nothing here is estimated: the scripts are
`docs/technicals/parity_check.py` (technical scores) and `docs/technicals/parity_leadership.py` (leader / in line / laggard).
They need numpy and pandas (the package does), so they are not part of the test suite or the Docker image. The regression
tests that keep the result true are `site-api/backend/tests/test_technical_parity.py` and `backend/tests/test_leadership.py`
(`test_weekly_runs_equal_the_package_week_by_week`); their expected values were produced by the package.

## 1. Technical scores (ST/LT v14.3, "ST/LT Score Breakdown & Peers v1.2")

Ours = `site-api/backend/premium_technical.py` on the provider rows (the production path). Package = `finlit_technicals.stlt.compute`.
Scores are the full-precision values (−100 to +100). "Components" is the number of the 29 component signals that differ.
The run is after the two changes made in this delivery (Pine's EMA seeding; all-zero provider rows).

| Scenario (daily bars) | Short-term ours | pkg | Long-term ours | pkg | Stage ours/pkg | Components that differ |
|---|---|---|---|---|---|---|
| strong uptrend (900) | +36.98 | +36.98 | +66.85 | +66.85 | 2 / 2 | 0 |
| downtrend (900) | −26.04 | −26.04 | −38.04 | −38.04 | 4 / 4 | 0 |
| sideways (900) | +23.18 | +23.18 | −52.17 | −52.17 | 4 / 4 | 0 |
| volatile (900) | −33.33 | −33.33 | −75.00 | −75.00 | 4 / 4 | 0 |
| gap up on the last bar | +26.56 | +26.56 | +34.78 | +34.78 | 2 / 2 | 0 |
| gap down on the last bar | −10.94 | −10.94 | −42.93 | −42.93 | 4 / 4 | 0 |
| small cap (benchmark Smallcap 100) | −8.59 | −8.59 | −28.26 | −28.26 | 4 / 4 | 0 |
| mid cap (Midcap 100) | −17.71 | −17.71 | −66.85 | −66.85 | 4 / 4 | 0 |
| large cap (Nifty 50) | +46.88 | +46.88 | +59.78 | +59.78 | 2 / 2 | 0 |
| **real recorded bars**: TCS (1,679) | +33.85 | +33.85 | −3.80 | −3.80 | 4 / 4 | 0 |
| HDFCBANK | −23.96 | −23.96 | −51.09 | −51.09 | 4 / 4 | 0 |
| SKIPPER | −33.33 | −33.33 | −11.96 | −11.96 | 3 / 3 | 0 |
| BAJFINANCE | −32.55 | −32.55 | −35.87 | −35.87 | 3 / 3 | 0 |
| HDFCLIFE | −5.21 | −5.21 | −51.09 | −51.09 | 4 / 4 | 0 |
| short history, 400 bars | −41.15 | −41.15 | withheld | +1.63 | 3 / 3 | 1 (RS rating, long) |
| short history, 260 bars | +65.62 | +65.62 | withheld | +39.13 | 2 / 2 | 1 |
| short history, 230 bars | −25.00 | −25.00 | withheld | +38.04 | 2 / 2 | 3 |
| short history, 150 bars | withheld | +13.02 | withheld | −3.80 | none / 2 | 17 |
| new listing, 60 bars | withheld | +22.40 | withheld | −39.67 | none / 1 | 18 |
| new listing, 30 bars | withheld | +20.83 | withheld | −39.67 | none / 1 | 26 |

The real bars are the daily quotes recorded in `site-api/backend/tests/fixtures/premium_replay` (five stocks, 2020 to 26 Oct 2026). No index bars are
recorded, so the index for those five is the equal-weighted mean of the five closes (the same for both engines).

**Wider sweep.** 240 more seeded series (900 to 1,500 bars; drifts from −0.2% to +0.2% a day; volatility 0.6% to 3.5%; one to three gaps of ±3 to
5% near the end; every third series with flat zero-range bars and no-volume bars; all four market-cap classes): **identical in every one**, in the two
scores and in all 29 component signals. Before the EMA change 2 of the first 90 differed.

**Result for full histories (about 500 bars or more): the two engines give the same numbers** (differences of 0e+00 in every case above). So the live
ratings are not churned, and the package adds what we lack: the component readings and points, the trend alignment and the peer lists.

### Rule differences found, and what was decided

| # | Difference | Decision |
|---|---|---|
| T1 | **EMA seeding.** Ours seeded every EMA at the first observation (the older model note said so). Pine's `ta.ema` (and the package) gives nothing until `length` observations exist and seeds with their average. For histories under about 1,000 sessions this flipped a close EMA 100 vs EMA 200 or OBV EMA 50 vs 150 comparison in 2 of 90 series (the long-term rows `ema50_200`, `ema100_200`, `obv_trend`). | **Ours changed to Pine's.** Pinned by `test_ema_is_pines_ta_ema` and the parity tests. Uncertain only in that the earlier model note (`docs/prism/premium-st-lt-model.md`) described the old behaviour; the package states it follows Pine, and the sweep proves the two agree. A stored report keeps its old numbers until recalculated. |
| T2 | **All-zero provider rows.** FinEdge pads holidays with `open = high = low = close = volume = 0`. Ours treated each as a missing candle and used only the bars after the last one. On the recorded quotes the row of 3 Sep 2026 left 34 usable bars, so **both scores were withheld for all five stocks**. The package drops non-positive closes. The financial-health inputs already treated such a row as "not a session" (`premium_data.py`). | **Ours changed** (`normalise_bars`): a row whose five fields are all exactly zero is not a bar. A zero beside real prices, or a row with missing (not zero) values, is still a gap. Test: `test_all_zero_provider_rows_are_not_sessions`. |
| T3 | **One bar with close above its high.** The recorded TCS row for 1 Feb 2026 (a Sunday budget-day session) has open 3,141, high 3,141, low 3,092, close 3,178.2. Ours marks open/high/low missing when the candle is inconsistent and so uses only the 180 bars after it (both scores withheld for TCS, HDFCBANK, SKIPPER, HDFCLIFE on the raw rows; BAJFINANCE has no such bar and matches exactly). The package accepts the bar. | **Kept ours** (accuracy first: nothing is repaired or invented). The production candle path (Dhan first, which rejects a series that has such a row and falls back to FinEdge/Upstox) is unchanged. Founder follow-up: see README, "Needs the founder". |
| T4 | **Young stocks.** The package computes a score from whatever exists and treats `na` as in Pine (a missing RS rating counts as −1, a missing 52-week structure as 0, EMA 200 as "not above"). With under about 500 bars the long-term score therefore leans negative because of missing history, not because of the chart. Ours withholds the score and says which signals are missing (new listing, 30 bars: 26 of 29 signals unavailable). | **Kept ours.** A number built on missing inputs would break "never invent; every blank shows its reason". The package README says the same about `percentrank` on short histories. |
| T5 | **Words.** Package: Very strong / Strong / Neutral / Weak / Very weak. Site: Strongly positive / Positive / Neutral / Negative / Strongly negative (already on the cards, in the PDF and in the search palette). Same bands (+50, +20, −20, −50). | **Kept the site's words** (one wording file, three copies kept identical by tests). The model's own verdict words (STRONG BUY ...) were already never shown; the nine verdict cells are the nine trend alignment cells of the package, with the same tone, so the descriptive alignment label now stands where "Trend: positive / mixed / negative" stood. |
| T6 | **`capped`.** Package: `capped` is true whenever the stage is 3 or 4 (the cap applies). Ours: `stageCapped` is true only when the cap lowered the score. | Both kept; the screen says which: "the limit changed nothing" or "+24.3 became +19". |
| T7 | Benchmark names: "Midcap 100" (package) against "Nifty Midcap 100" (ours). | Ours kept; same index. |

Identical (checked): the 15 + 14 component rules and weights (96 and 92 in use with sector RS off and value-area migration on), the ADX trend factor
(×1 above 25, ×0.5 below 20, else ×0.75), the Weinstein stage and the +19 cap, RSI regimes, the swing-failure state machine, the volume profile and
value-area migration, the squeeze, gaps, candle priority, the 9 EMA consolidation scan, the beta-adjusted RS percentile (126 and 252 sessions, the
`percentrank` convention), weekly RSI / MACD of the last completed week, market-cap benchmark selection per bar (Rs 1,07,000 / 32,800 crore, Nifty 500 when
unknown), and the rating and band boundaries.

## 2. Leader / In line / Laggard ("Leader & Laggard vs Peers v1.0")

Our pure functions (`leadership.label_group`, `settle`, `ret`) on the same weekly closes as `peers.compute`, for every weekly run of the last 60 weeks.
The package is given five flat daily bars per week (same last close, same weekly volume), so both read the same weekly figures.

| World | Comparable runs | Differences |
|---|---|---|
| 24 peers, sector index; one thin, one under a year, one stale | 59 | none |
| same, no sector index (peer average) | 59 | none |
| 9 peers | 60 | none |
| 13 peers, one stops trading on the Wednesday of the last week | 60 | none |
| 7 peers of which 3 are too new to rank until week 53 | 17 of 60 (the rest: too few) | none |

Compared per run: ranked count, k (leader slots), the stock's rank, the 12-month, 6-month and 3-month relative return, the 12-month figure against the
market index, this week's label, the published label (the two-run stability rule) and the direction. The pinned values are in
`backend/tests/fixtures/leadership_parity.json`.

### Rule differences found, and what was decided

| # | Package (README, tests, Pine behaviour) | Ours before | Decision |
|---|---|---|---|
| L1 | k = ceil(30% of ranked); Leader = rank ≤ k and 12-month figure > 0; Laggard = rank > n − k and < 0 | same (`END_SHARE_TENTHS = 3`, integer arithmetic) | same, no change |
| L2 | Rank key: 12-month figure vs the sector benchmark; ties: 6-month, then market cap | same | same |
| L3 | Direction: 13-week figure ≥ +5 / ≤ −5 points | same | same |
| L4 | 6 or more ranked (the stock counts); 52 weeks of prices; Rs 1 crore median daily traded value over the last 13 weeks | same constants | same |
| L5 | Liquidity is judged **as of each week** | judged once, on the latest 13 weeks, for every week of the history | **Ours changed**: when the stored series has volumes, `Prices.thin_on(t)` judges as of `t`. Only the stored history rows could differ; the current label was the same. |
| L6 | A peer with no bar in the last completed week (it stopped, or its prices lag the stock's) is stale | stale only when its last close was more than 7 days old | **Ours changed**: within a group, a peer whose latest close lies in an earlier week than the group's latest is stale, even if under 7 days old. When every price lags the same way (a late refresh) nobody is. The 7-day guard stays. |
| L7 | Runs on the **first bar of the next week** and ranks the week before. A peer that last traded in the ranked week but not in the new week is stale | Runs after Friday's close and ranks that week | **Ours kept** (the week is complete and the label is current a few days earlier). It is the only reason the two differ in one week of the stale-peer world; that week is not compared. |
| L8 | Stability: a new label needs the same this-week answer in two weekly runs in a row; the first label shows at once | same (`settle`) | same |
| L9 | When the stock cannot be ranked (state 2, 3 or 4: young, thin, too few peers) the published label is **withdrawn** and the next ranked run publishes at once | the last label is kept and flagged stale after 2 missed runs | **Ours kept.** A data gap on one peer for a week should not make every page flip to "no label" and back. Note for the founder. |
| L10 | Sector benchmark: the NSE sector index named for the group, else the equal-weighted average of the ranked peers (the stock included), with a note | same (`peer_average` and the note) | same |
| L11 | **Market index by size**: Rs 1,07,000 crore or more Nifty 50; Rs 32,800 crore or more Midcap 150; else Smallcap 250; unknown Nifty 500 | by rank of the market cap among the stocks in `listing_quotes` (1 to 100, 101 to 250, then small); unknown counted as small | **Ours changed** to the rupee cut-offs, so a company has one size class everywhere (the Prism technical view already used them), and to Nifty 500 for an unknown cap (migration 071 adds the `unknown` row to `leadership_market`). `test_market_cap_cut_offs_are_the_prism_technical_views` keeps the two files' constants equal. |
| L12 | **Peer groups**: the five researched groups (IT 14, pharma 16, private banks 13, PSU banks 12, auto 20), else the TradingView industry list (35 largest liquid names), else the sector list | the data provider's industry, widened to the sector when it had fewer than 6 rankable stocks | **Adopted** (see README, "Peer groups"); our grouping is kept for stocks on none of the lists and for lists too thin to rank with the prices stored here. |
| L13 | The peer list for the peer row of "ST/LT v1.2" is capped at 30; "Leader & Laggard v1.0" uses 37. The two scripts therefore rank 31 and 35 names for a 35-name list | n/a | One answer only: the whole list (the v1.0 rule). Every list is 35 names or fewer, so 37 never truncates. |
| L14 | Reliability: the spec's own backtest sentences for IT, pharma, banks and auto | our own quarterly backtest on the stored weekly history (needs 10 years of checks) | Both: the spec's numbers are shown for its five researched groups until our backtest has a tier of its own, then ours replaces them (never both). Labelled on the card. |
| — | The package has no fundamentals check, corporate-action hold or "fundamental below peers" note | we have all three (`fund`, `find_breaks`) | Kept; they add information and never change a rank or a label. |

Conflict with the earlier "developer spec" constants at the top of `leadership.py` (reported, as asked): L5, L6, L11 above are where the earlier file and
the package disagreed. The earlier constants (52 / 13 / 26 weeks, 30% ends, ±5 points, 6 peers, 52 weeks of history, Rs 1 crore, 2-run stability) are
the same as the package's. `STALE_DAYS = 7` is the one the package's rule refines (L6). Nothing else conflicts.

## 3. Strings scanned for advice wording (compliance)

Every string the package can emit was scanned with the site's forbidden-word expression (`buy`, `sell`, `hold`, `reduc…`, `avoid…`, `target…`,
`accumulat…`, `entry`, `exit`, `stop…`): `stlt.RATINGS`, `ALIGNMENT`, `BAND_NAMES`, `tips()` (the "how" text of every row), the readings of four
full runs, `peers.LABELS`, the curated group names, `rel_text`, `ST_METHOD`, `LT_METHOD` and the two disclaimers (175 strings).

Hits, and what was done:

* `tips["rs_leadership"]` (short and long): "**holding** up vs a weak index" — reworded to "staying firm against a weak index".
* `rs_lead_txt` readings: "**Holding** up vs index" and "Leader: **holding** while index fell …" — not used (our own readings are used).
* `PeerResult.pending()`: "(shows if it **holds** next week)" — replaced by "This week the ranking says Laggard. It becomes the label if the next weekly run says the same."
* The package's docstring "no trade calls, entries or stops" is a comment, not output.

`test_trend_alignment_labels_and_how_texts_have_no_advice_word`, the front-end scans and `test_this_week_line_names_the_rule_without_advice_words`
keep every new string clean.
