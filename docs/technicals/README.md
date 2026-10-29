# Technical scores and Leader / In line / Laggard: the finlit_technicals v1.1 delivery

The team delivered a Python package, `finlit_technicals` v1.1, with ports of two TradingView indicators:
"ST/LT Score Breakdown & Peers v1.2" (short-term and long-term scores, every component, trend alignment) and
"Leader & Laggard vs Peers v1.0" (label, ranks, peers table, weekly history). This note says what was done with it, why,
and what is left for the founder. The evidence is in [PARITY.md](PARITY.md); read that first if you doubt a decision.

## 1. The result in one paragraph

On the same bars the package and our two engines give **the same numbers** (technical: 260 series, every one identical in the two scores and in
all 29 component signals; leader / laggard: five synthetic worlds and 60 weekly runs each, identical ranks, labels and figures). So no live rating
was churned. What the package has and we lacked was added: the component breakdown, the trend alignment, the "this week" label, the peer lists
and the not-ranked list. The few real rule differences were settled one by one (PARITY.md, tables T1 to T7 and L1 to L14) and are pinned by tests
whose expected values came from running the package.

## 2. What changed on each screen

### Prism card, technical block (stock page) and the full Prism report

* **Trend alignment** under the two scales on the card: a shape and one of nine descriptive labels ("Strong on both timeframes", "Short-term pullback
  within a long-term uptrend", …). It is the short-term band (+20 or more Positive, −20 or less Negative) times the long-term band. It is worked
  out from the two scores, so **reports stored before this existed show it too** (no recalculation).
* **Full report**, technical section: the alignment chip with the working ("Short-term +47 (Positive) × long-term +19 (Neutral) = …"), the 3 × 3
  **trend map** with the current cell highlighted, and **"How these scores are built"**: one expandable table per timeframe with every row (reading now,
  signal −1 to +1, weight, points), the total (the points add up to the score), the weights in use (96 and 92), the ADX trend factor (short term) and
  the Weinstein stage with the +19 limit and what it did (long term), and a "How it is read" text for every row. The data date is in the text.
* A report stored before the breakdown existed has no weights or points; its table says so and offers "Recalculate to add the breakdown" (same
  recalculate action as before). Nothing is invented for it.
* Words: the descriptive site words (Strongly positive … Strongly negative) are kept. The model's own words and verdict labels are never shown; the
  alignment label replaces "Trend: positive / mixed / negative" (the same nine cells and tone).

How it reaches the screen: `site-api/backend` calculates (unchanged scores; new `observations.adx`, `observations.trendMultiplier`, `longTerm.uncappedScore`);
the research API's `technical_view` (backend/finlit/prism.py) passes each row's `weight`, adds `points` and `divisor`, and `relabel_technical` adds
`trendAlignment`; the page reads them (`frontend/src/lib/prismTechnical.ts`, `components/prism/pzr/TechBreakdown.tsx`). **Every new field is optional** on
the page; an old stored report renders as before. `inputHash` and `sourceCodeSha256` are still never sent (tests).

### "How it ranks among N peers" (stock page)

* A status block above the table: the status sentence (same format as the package: "6th of 11 IT peers · +14.0 pts vs Nifty IT · −6.8 pts vs Nifty 50
  (12 months) · gaining over 3 months"), **this week's own answer when it differs from the published label** ("This week the ranking says In line. It
  becomes the label if the next weekly run says the same."), what the figures are measured against (the sector index, or the average of the ranked peers
  with the note that there is no index), how many of the group can be Leaders and Laggards, **how long the label has stood**, the **Leader / In line /
  Laggard counts of the last 52 weeks**, and the peer group (the indicator's list, its date, and how many of its names are ranked).
* Columns as before (#, company, status chip with the gaining / weakening arrow, vs sector 12M, vs sector 3M, vs market 12M); a small "This week: …"
  under a chip whose own answer differs (every peer, not just this company); "Show all N companies"; a **"Not ranked this week (N)"** list with a
  reason for each ("Too thinly traded", "Under a year of prices", "No price history stored here yet", "Not covered here").
* The reliability card shows the spec's own backtest for its five researched groups until this site's backtest has ten years of checks (labelled).
* Older API answers (before migration 071) still render: the new fields are optional.

## 3. Decisions

| Question | Decision | Evidence |
|---|---|---|
| Vendor the package? | **No.** Its two pieces we needed (the rules and the data) are small: the rules were already in our modules and identical; the data (peer lists) is a JSON file. | The Docker image has **no numpy or pandas** (two Python environments, neither lists them; the package imports both). Adding them would be a heavy dependency (and a rebuild of both environments) for code that duplicates what we have. No requirements file changed. |
| Which engine for the technical scores? | **Keep ours**, align it where it differed (EMA seeding, all-zero provider rows). | PARITY.md section 1. |
| Which peer groups? | **The indicator's lists first** (the spec's five researched groups, then the TradingView industry, then its sector), with the earlier grouping by the data provider's industry for stocks on no list, for a list with fewer than 6 stocks this site can rank, and as the widening rule. A stock is ranked in exactly one group, and the page says which. | section 5 below. |
| Where is the breakdown computed? | Points, divisor and alignment are derived where the report is built for the browser, from the weights and signals, so they always agree with the score. | `test_breakdown_points_add_up_to_the_stored_score_and_the_alignment_is_derived` uses the real stored snapshot. |
| Show weights? | **Yes**, per the brief; the indicator publishes them. The earlier model note said they are not shown to readers. | One line to undo: remove `"weight"` from `TECH_FACTOR` in prism.py; the table then loses the weight and points columns and says "recalculate". |
| Rating words | Kept the site's words. | PARITY.md T5. |

## 4. Data and API

* Migration `071_leadership_lists.sql` (the next free number): `leadership.group_source`, `group_listed`, `list_as_of`; `leadership_history.raw_label`,
  `rel13`; table `leadership_unranked`; the `unknown` row of `leadership_market` (Nifty 500). All additive and idempotent.
* `GET /api/stocks/{symbol}/leadership` adds `peerGroup.source / listed / listAsOf / leaderSlots`, `display.pending`, `peers[].rawLabel`, `notRanked`,
  `runs52`, `sectorReliability.source`. `leadership-history` rows add `rawLabel` and `rel13`. Rows stored before the migration have nulls and show as
  "ranked among the data provider's industry peers".
* Worker commands are unchanged in name (`refresh-leadership`, `backfill-history`, `backtest-leadership`). `refresh-leadership` now prints, per
  peer list, how many names it lists, how many have stored prices, how many are ranked and how many stocks it is home to (`lists` in its result).
* Market cap for the size classes comes from `listing_quotes.market_cap` (Rs crore); the cut-offs (1,07,000 and 32,800 crore, the AMFI list in force
  from Aug 2026) are `MARKET_CAP_CUTS` in `backend/finlit/leadership.py` and the same two numbers in `site-api/backend/technical_series.py`. **Change both
  when AMFI revises them**; a test fails if they differ.

## 5. Peer groups: the decision and the numbers

The package ships 71 TradingView industry lists and 19 sector lists (the 35 largest liquid NSE stocks each, "as of 27 Oct 2026") and the spec's five
researched groups: **95 lists, 1,347 different symbols** (stored in `backend/finlit/data/leadership_groups.json`, generated by
`backend/scripts/make_leadership_groups.py`).

Coverage against what this site can supply:

* **Symbols**: 1,338 of the 1,347 are in the provider's symbol list (the fixture of 5,745 listings). The researched groups are complete: IT 14 of 14,
  pharma 16 of 16, private banks 13 of 13, PSU banks 12 of 12, auto 20 of 20. Missing: ANANTAM, ANZEN, CAPINVIT, CUBEINVIT, ICICILIFE, INDIGRID, NHIT,
  SHREMINVIT, VERTIS (mostly InvITs). The list "Investment Trusts/Mutual Funds" has 1 of 7 names, so it can never be ranked and its stocks use the
  earlier grouping.
* **Sector indices**: all 12 NSE indices the lists name exist in our index table (IT, Pharma, Private Bank, PSU Bank, Auto, Energy, Metal, Realty, FMCG,
  Financial Services, Media, Infrastructure). 43 of the 95 lists name one; the other 52 use the **equal-weighted average of the ranked peers**, exactly
  as the package does, with the same note on the page.
* **Prices**: a stock is ranked only if its weekly closes are stored (the price section of its stored report). How many of a list's names have them
  depends on which companies the database keeps in full (`INGEST_LIMIT`), which I cannot see from here. The weekly job tells you: the `lists` part of
  its printed result gives `listed / withPrices / ranked / homes` per list. A list needs 6 ranked names; otherwise its stocks fall back to their
  industry group (and the page says so).
* **Visible change**: the pharma group the founder saw ("29 pharma peers") is the provider's industry (29 names with stored reports). The
  researched pharma list has 16 names, so it will read "N pharma peers" with N at most 16; pharma stocks outside those 16 are ranked in the
  TradingView lists ("Pharmaceuticals: Major", "Pharmaceuticals: Other") or, if on none, as before. This is the spec's definition (its reliability
  research was done on these lists).

**How to refresh the lists** (the package says "as of 27 Oct 2026"): get a newer `peer_groups.json` from the team (they regenerate it from
TradingView's screener), run `python backend/scripts/make_leadership_groups.py <path>/peer_groups.json`, update `AS_OF` in the script, run
`pytest backend/tests/test_leadership.py`, commit the data file. The spec's five researched groups and their research numbers are in the script's
`CURATED` and `SPEC_RELIABILITY`; they change only if the team re-runs the study. A new list needs no code.

## 6. Dependencies and the Docker image

No change. `numpy` and `pandas` are **not** added; nothing imported at run time needs them. The files added to the image are the data file
(`backend/finlit/data/leadership_groups.json`, inside the `backend/finlit` folder the Dockerfile already copies) and the refresh script (inside
`backend/scripts`, also copied). The package itself is not in the repository; the scripts under `docs/technicals/` use it from a path you give them
(see "Reproduce").

**Licence:** the zip carries no licence file (only `pyproject.toml`). Nothing of the package's code was copied; what was taken is the peer list
data, the five researched groups, the nine alignment labels and the rules (all described in its README). Please confirm with the team that they
may be used on the site.

## 7. Load

* **Technical scores** are calculated by the existing Prism calculation, one company at a time: about 0.4 s of one core for 700 daily bars and 0.6 s for
  1,500 (pure Python; measured here). The package says about 0.5 s per stock for both indicators with numpy. Nothing was added to that path except a
  few extra numbers, so the nightly `precompute-prism` job (which already yields to members) is unchanged. If you ever want scores for every listed
  company every night (about 1,300 on the package's lists), that is 8 to 13 minutes of one core: batch it the way `precompute-prism` is batched, never
  as a new parallel job on the 2 vCPU server.
* **Leader / Laggard**: the weekly job did one ranking per industry; it now does one per peer list (95 lists of at most 35 names). Ranking all
  95 lists on one date takes about 0.05 s; a ten-year backfill (every 4th Friday, 131 dates) about 4 s. The job is dominated by its database reads and
  by the index levels (12 more index series than before, each cached for 6 hours in Redis, one provider call when cold). It also writes one more
  small table (`leadership_unranked`, a few thousand rows, replaced each week). The quarterly `backtest-leadership` now also covers the 95 lists
  (about 8 s of CPU and 12 more long index series, cached 8 days). **No new job and no new schedule**: it all runs inside the existing weekly and
  quarterly commands.

## 8. Needs the founder

1. **Confirm the licence** of the package (section 6).
2. **Read the first weekly run's `lists` output** and tell the team which of the five researched groups rank fewer than 6 names (PSU banks need 6 of
   12 with stored prices); those stocks use the industry grouping until the prices are stored.
3. **Run `backfill-history` and `backtest-leadership`** if not already done, so the reliability card has this site's own numbers; until then it shows
   the spec's (labelled). Delete the `method = 'spec'` rows of `sector_reliability` if you would rather show "Not enough history".
4. **The EMA change** (T1): the earlier model note described first-observation seeding. If the owner's Pine script seeds that way, say so and it is a one-line
   revert in `site-api/backend/technical_series.py` (the pinned tests then change with it). I believe Pine's `ta.ema` is correct and the package agrees.
5. **A candle with close above its high** (T3) makes our strict rule use only the bars after it (TCS's budget-day row of 1 Feb 2026 in the recorded quotes
   withholds both scores for months). Decide whether to keep the strict rule (nothing invented) or to accept such a bar when open, close and volume are
   valid. The production path prefers Dhan, which rejects the whole series on such a row and falls back to FinEdge, then Upstox.
6. **Young stocks** (T4): scores are withheld under about 500 bars, with the reason. The chart shows a number built on missing history; we do not.
7. **Weights on screen**: confirm that showing weights is acceptable (section 3).
8. **The nine symbols** not in the provider's list (above); "ICICILIFE" may be an old name (ICICI Prudential Life is ICICIPRULI).
9. **Twice a year**, when AMFI revises the cut-offs: update `MARKET_CAP_CUTS` and `technical_series.py`.
10. Frontend only: the older "Combined trend" wording in any marketing copy or PDF template outside this repository should now read "Trend alignment".

## 9. Reproduce

```
python3 docs/technicals/parity_check.py     /path/to/finlit_technicals_repo_root          # technical scores, both engines
python3 docs/technicals/parity_leadership.py /path/to/finlit_technicals_repo_root          # leader / laggard, both engines
python3 docs/technicals/parity_check.py     /path/to/finlit_technicals_repo_root --pins site-api/backend/tests/fixtures/technical_parity_pins.json
python3 docs/technicals/parity_leadership.py /path/to/finlit_technicals_repo_root --pins backend/tests/fixtures/leadership_parity.json
PYTHONPATH=backend:site-api python docs/technicals/make_view_fixture.py                    # the front-end fixture of the new technical view
python3 docs/technicals/make_leadership_fixture.py /path/to/finlit_technicals_repo_root     # the front-end fixture of a list-based ranking
```
(needs numpy and pandas on the machine that runs the first four; the tests need neither.)
