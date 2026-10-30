# FinLit Mutual Fund Health Score

Code: `backend/finlit/mfscore/` (pure scoring engine, loader, job, API), migration `072_mf_scores.sql`, worker command `score-mf`, page `/methodology/mf-score`,
card on `/funds/:id`, a Health score column on `/funds`, score rows on both fund comparisons. Specification: "Mutual Fund Health Score, Model Specification v1.1
(draft), 30 October 2026" (formulas, limits, weights and the Appendix Z zero rules are implemented as written; the sheets are data in `mfscore/sheets.py`, one table per
group exactly as spec Section 7). The score describes; it never advises. No accuracy claim is made anywhere. Every limit is a designer starting value that is not yet calibrated.

Compliance line shown with every score: "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice."

## Run it

Server (the one line):

    cd /opt/finlit && docker compose --env-file .env.aws -f src/finlit-platform/deploy/aws/docker-compose.aws.yml exec -T -d app sh -c 'python -m finlit.worker score-mf > /tmp/score-mf.log 2>&1'

It also runs once a day in the night chain right after `refresh-portfolios` (`deploy/scheduler.sh`, `run_funds score-mf score-mf`: same lock, memory wait and pause switches as the other
fund jobs) and once at the end of the boot load (`--max-age-hours 20`). Options: `--symbols 120465 NIFTYBEES` scores the whole universe (peer medians need it) and writes only those
funds; `--limit N` is for testing only (partial peer sets, removes nothing). One transaction, idempotent. Verify: `/api/mf/status` shows `run:score-mf` with counts, status counts,
metric-state counts and the Appendix Z.3 zero-rule counters (`zeroRules`: rule name -> hits, `fund:<rule>` -> funds hit). API: `GET /api/mf/{code}/score`, `GET /api/mf/etf/{symbol}/score`,
`GET /api/mf/scores?codes=&group=&category=&plan=&status=&sort=&limit=`, `GET /api/mf?sort=score` (Silver).
Measured on synthetic data: 5,120 funds (16 groups, both plans) score in 2.3 s of CPU, peak 219 MB including the synthetic inputs; one process, no threads fighting the web server.

## Plan gating

Silver and Gold (and admin) see the score. Basic and visitors get a locked answer: no value, no pillar, no breakdown, no rank, no list order (`/api/mf/scores` lists return nothing,
`?codes=` returns null fields, `/api/mf?sort=score` answers 403). Responses are `private, no-store`. Optional open schemes: env `MF_SCORE_SHOWCASE=120465,...` (the site has no fund showcase list, default none).

## Decisions where the draft is silent (all "designer decision pending confirmation")

1. Labels by score: Strong 80+, Healthy 65-79, Average 50-64, Weak 35-49, Poor under 35 (the Prism / FinLit words and edges); colour green 70+, orange 50-69, red under 50.
2. Weak-fund cap (design rule 6): Risk or Quality pillar under 35 caps FINAL at 64; under 50 caps it at 79. The uncapped figure is stored (`raw_final`) and shown.
3. Status: history rows exactly as spec Section 3. In addition data confidence under 30% = NOT RATED, under 60% = PROVISIONAL. PROVISIONAL caps the label (not the number) at Healthy.
4. Months of history = calendar span of month-end NAVs (60+ all; 36-59; 12-35; under 12). The series ends with the latest NAV (a part month), as the site's other month-end figures do.
5. Window W: last 36 returns, 33 valid needed; a young fund's window is its returns minus 3 missing allowed (at least 11 valid). Invalid month = NAV 0/negative/missing in it or the month before.
6. Group value uses the points of funds in states A, S and Z; fewer than 8 funds = 50; median above 50 is cut to 50; a median of 0 stays 0.
7. Peer scope per metric: sub-category + plan first (8), then group + plan (S), else F. Monthly series (hit rate, down-capture) pick the first scope with 12 compared months; a month needs 8 peers (3 for a family).
8. Kind C zeros also exclude the peer from medians: TER under 0.01 (spec), top-10 / largest sector of 0, equity 0 in AGGR, equity-fund 36-month fall of exactly 0.
9. Frozen NAV (VOL_M under 0.01 pp) sets every window measure to F (hit rate, volatility, falls, Sharpe, worst month, ...) and exactly-0 returns to F, and raises NAV_BREAK. A peer with NAV_BREAK is not a peer.
10. Data confidence = share of the final weight carried by A/Z/S metrics (window metrics of a young fund count n/36); an all-N pillar counts as missing.
11. Rank and percentile: inside sub-category and plan (the tracking family for index funds and ETFs with at least 3 members), needs 3 scored funds; percentile = share of the others with a lower score.
12. "Funds in this category are near-identical" shown for Overnight, Liquid and Arbitrage (spec names CASH/overnight/liquid and ARB).
13. Debt "Fixed term and interval" and any unrecognised debt category go to ACCRUAL, hybrid default to AGGR, equity default to BROAD (spec defaults).
14. ETFs: scored from `etf_funds` / `etf_history` (exchange month-end closes, price returns without dividends, break_date respected), always OT-PASSIVE, own plan "ETF" (Direct limits). Exit-load text of an ETF is missing so that measure is F, not invented.
    An AMFI ETF-category scheme in mf_schemes inherits its ETF's score (by ISIN). IDCW / other options inherit the Growth plan of the same fund and are labelled inherited.
15. Tracking family key: benchmark text (or the index words of the scheme name) lower-cased with TRI / Total Return Index / Index removed. It groups funds on the same index; it is not tracking error.
16. Storage: one current row per fund (`mf_scores`), no daily history (a daily history of about 14 MB of breakdown per day would not fit the small database). Open question below.
17. Ingest: the feeds keep a placeholder 0 for TER and AUM (the TER comment says NULL, the code stores what AMFI sends). Ingest is not changed (risk); Kind C rules run at read time and are counted.
18. Spec Section 7.5 lists RET_3Y_REL 25 and RET_5Y_REL 20 for Others (the reverse of equity); implemented as written.

## Calibration checklist (spec Section 12 and Z.3) as team tasks

- Back-test every limit and weight on real data before anything is published; check the group value and score distributions per group.
- Z.3-1: read `zeroRules` counters after the first real run; a high TER / AUM / top-10 / equity count is a feed problem.
- Z.3-2: check the TER floor 0.05, down-capture floor 0.05 pp and frozen-NAV cut-off 0.01 pp against the real distributions.
- Z.3-3: confirm the 50% minimum for a valid asset split against parsed portfolio files.
- Z.3-4: every zero-handling event carries its rule name in the breakdown (`rule`) and the reasons say "expense ratio not reported".
- Z.3-5: change ingest to store NULL, not 0, where possible and count the fields where it cannot be done.
- Count index funds and ETFs whose tracking family has fewer than 3 members; check the name parser on real scheme names.
- Capacity caps of SIZE_FIT (60,000 / 30,000 / 20,000 / 12,000 crore) are guesses; replace them with an observed size-return relation.
- Check how many funds are NOT RATED / PROVISIONAL because of the 30% / 60% confidence thresholds.

## Open questions for the designer

1. Confirm labels, the weak-fund cap (64 / 79), and the confidence thresholds (30% / 60%) above; Sections 8 to 12 of the draft were not in the PDF.
2. Should a part-month latest NAV count as a month return? Should a stale (older than 45 days) TER be F when the TER feed is not refreshed on the server?
3. Is a daily score history wanted (storage)? Should a big one-month NAV jump (split, bonus) raise the NAV break flag? The spec only names invalid months and frozen NAVs.
4. Near-identical note: also for money market and ultra short?
5. Exit load for ETFs: F (unknown) or 100 (no exit load by construction)?
6. Fixed-term and interval funds: ACCRUAL is a default only.
7. Should peers include funds of other houses only, or all houses (now: all)?
