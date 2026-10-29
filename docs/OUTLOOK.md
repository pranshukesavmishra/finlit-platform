# Profit and revenue outlook (Gold)

`POST /api/outlook/{symbol}` with `{kind: "profit"|"revenue", weights?: {group letter: percent}, statement?}`. Code: `backend/finlit/outlook/`.
Information only, not investment advice. It describes a scenario from the company's own reported history. It is not a forecast and never a price or recommendation.

## Contract
- Gold (and administrators) only; other plans get 403 `plan_required`, no data. Responses are `private, no-store`; cached 10 minutes in Redis by symbol, statement, kind, weights hash and the stored report version (etags of the summary, financials, ratios and segments sections).
- `weights`: omitted = "Use our model" (default weights). Otherwise every group of the tab, each 0-100, total 100 within 0.01 (else 422 `invalid_weights`). Parameters inside a group keep their default proportions.
- Response: `score {value|null, band, reason}`, `coverage {measured, total, weightPct}`, `groups[] {letter, name, weightPct, effectiveWeightPct, score, band, coverage, status, reason}`, `range`, `asOf`, `disclaimer`. Never parameter names, thresholds or formulas.

## Score
Each measurable parameter is mapped to 0-100 by a linear range fixed in `scorers.py` (generic, not sector-specific). A group score is the weighted mean of its measurable parameters (weights renormalised inside the group). The overall score is the mean of the live group scores weighted by the chosen group percentages (a group with no measurable parameter drops out, so the others are renormalised to 100). If under 50% of the chosen weight can be measured there is no score, with the reason. Bands: green >= 70, orange 50-69, red < 50 (words: Supportive, Mixed, Subdued).

## What is measurable (see `registry.py`)
Measured from the stored sections (yearly and quarterly P&L, balance sheet, cash flow, ratio history, segments). Not in our data, so excluded: employee and other operating expenses; geographic and recurring revenue; order book, order inflow, book-to-bill, customer/unit growth; capacity utilisation; sales volume, price, mix; unbilled revenue; industry growth (peers are a symbol list) and market share. Revenue groups C, E and G are therefore always "Not available", and the revenue segment group needs two or more reported segments, so a company with one reported segment may fall under the 50% rule for revenue.
Lenders (`summary.dataQuality.isBank`): EBITDA, EBIT and gross margin, operating-cost, leverage, working-capital, cash-flow and capex measures are excluded; net margin, ROA and profit growth/volatility stay. Group E and D then show "Not meaningful for banks and lenders" and the Profit tab usually shows no score.

## Indicative growth range (`rangecalc.py`)
Next four quarters in total (net profit or revenue) versus the same four quarters a year earlier, i.e. the latest four reported quarters (T), against the four before (T0):
1. Needs eight consecutive reported quarters, T > 0 and T0 > 0; otherwise "Not enough history for a range" / "not positive" with the reason.
2. Baseline g0 = average of trailing-four-quarter growth (T/T0 - 1) and the 3-year CAGR of the yearly figure (when both ends are positive); each limited to -40%..+60% first.
3. Spread: s = standard deviation of the company's quarterly year-on-year growth (at least four of the latest eight); half-width w = s/2 (a four-quarter total smooths quarter noise), kept between 3 and 25 points.
4. Tilt: mid = g0 + (score - 50)/50 * w/2 (no score: no tilt). low = mid - w, high = mid + w; each limited to -40%..+60%, and `capped` names the limited ends.
Limits: it extrapolates reported growth and its own variation; it knows nothing about the future, the sector or events. Lumpy profits give wide ranges.
