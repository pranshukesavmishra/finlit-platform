# Revenue and profit estimate: method

Source: the team's "Revenue & Profit Prediction Model" (proposed methodology). Implemented in `backend/finlit/outlook/model.py`.

1. **Horizon.** Short-term 1 year (FY+1), mid-term 3 years (FY+1 to FY+3), long-term 5 years (FY+1 to FY+5). The horizon selects the weight column.
2. **Weighted growth rate** `g = sum(w_i * x_i)`, each column totals 100. Revenue: company growth 1Y, CAGR 3Y, CAGR 5Y; sector the same three. Profit: the same six for net profit, plus the net profit margin trend. Weights (short/mid/long): revenue 50/10/5, 10/40/15, 5/10/40, sector 25/20/20, 5/10/5, 5/10/15; profit 35/10/5, 10/25/15, 5/10/30, sector 25/20/20, 5/10/5, 5/10/15, margin trend 15/15/10.
3. **Iterative estimate** `V(t+1) = V(t) * (1 + g)`, from the latest reported financial year. No year-specific inputs are stored, so the same rate is held for each year (the spec allows this). Example: 1,000 Cr at 12% gives 1,120.00 / 1,254.40 / 1,404.93. Profit is estimated directly from its own rate, never as revenue times margin.
4. **Data rules.** 1Y = year on year; 3Y and 5Y = CAGR `(end/begin)^(1/years) - 1`. Sector = median of peers (never the average), taken from the screener table: the company's industry when at least 5 peers have the figure, otherwise its sector; blank (with the reason) below 5. A missing input drops out and its weight is shared across the available inputs of the same horizon in proportion (re-normalised to 100); the page lists what was unavailable. Each input is limited to -50% .. +50% a year (`INPUT_CAP`), and the table shows "limited from" when that applied. Margin trend = relative change `m1/m0 - 1`, not percentage points.
5. **Loss or near-zero profit.** A CAGR or year-on-year ratio needs a positive start and end, and a start above 0.5% of that year's revenue. Otherwise the change is measured against the average size of profit across the window, per year, and the row says so. If the latest year's profit is not positive no estimate is drawn (a growth rate cannot be applied to a loss); the inputs are still shown.
6. **One-off items.** Historical profit is net profit, with profit from discontinued operations taken out where stored (`net_profit_continuing`), and material exceptional items (10% or more of profit) taken out after tax at the year's own tax rate (0-35%, 25% when unknown). Adjusted years are named on the page.

## Adapted from the spec, and why
- Sector medians use the screener's per-company growth figures as stored (latest year, 3 and 5 year), which are not adjusted for one-off items.
- Banks and lenders: total income is used as revenue when stored.
- The estimate is annual (financial years). The previous four-quarter range and the outlook score were replaced.
- The chart shows no range band: the model produces one rate.
- Weights are validated to total 100; the sliders keep that automatically, the API can also scale (`normalise`).
- Not shown on the site: accuracy figures. See BACKTEST.md before trusting the weights.
