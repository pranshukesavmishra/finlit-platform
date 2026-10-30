"""FinLit Mutual Fund Health Score (model specification v1.1 draft, 30 October 2026).

A descriptive health check of a fund against funds of the same kind, built from month-end NAVs, costs and holdings that the site already holds.
It is not a forecast and not a recommendation. Information only, not investment advice.

Package layout (pure scoring code first, database code last):
  toolkit    is_missing, scale, safe_ratio, pillar, MedianBook (the spec's Section 4 and the zero rules of Appendix Z)
  groups     AMFI category -> type -> group (Section 5), the tracking-family key of index funds and ETFs (Section 7.5)
  sheets     one configuration per group: weights, metrics, limits (Section 7), as data
  history    month-end NAVs -> monthly returns, volatility, falls, frozen / broken NAV tests (Sections 3 and 6)
  exitload   exit-load text -> step-table points (Section 6.3)
  metrics    every metric of Section 6 (one function each)
  engine     peer sets, states, group values, pillars, final score, labels, confidence, reasons for a whole universe of funds
  reasons    plain-language text for every metric (data file reasons.json)
  loader     database rows -> FundIn (the only place that knows our tables)
  job        the `score-mf` worker command
  api        GET /api/mf/{code}/score and GET /api/mf/scores
"""

MODEL_VERSION = "mf-health-1.1-draft"
