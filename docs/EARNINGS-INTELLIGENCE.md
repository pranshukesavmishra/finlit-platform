# Earnings Quality Intelligence

Level 1 "Quick insights" card at the top of the Profit Reality Check (stock page, Ratios section). Code: `frontend/src/lib/earningsIntel.ts` (rules), `frontend/src/stock/EarningsIntel.tsx` (card), `frontend/src/styles/earningsintel.css`.

Everything is plain arithmetic on the numbers the section already loaded (yearly P&L, balance sheet, cash flow from the same `financials` call, so plan limits are unchanged). No model, no network, nothing estimated. Level 2 (deep analysis) is the existing data part, unchanged. Level 3 is the "Investor interpretation" disclosure in the card. The card describes earnings quality; it never labels a company fraudulent or manipulating, never scores it down for negative cash flow alone, and gives no advice.

Caveat shown in the card: "Some businesses have seasonal or project-based cash cycles."

## Rules

"Last three years" means the three latest years shown. A single weak year alone is never the top level. Missing inputs give "Not enough data".

| Module | Badges | Rule |
|---|---|---|
| Profit vs Cash Flow | Red flag / Watch / Steady | A year is weak when profit is positive and operating cash flow is negative or below 80% of profit (80% is the existing Profit Reality Check threshold). Red flag: latest year weak AND (weak in 2 of the last 3 profitable years OR five-year cash/profit below 80%). Watch: latest year weak, or 2 of the last 3 weak. Else Steady. Needs latest profit and cash flow. |
| Receivables Quality | Investigate / OK | Receivables growth minus revenue growth. Investigate when the latest gap is 10 or more points, or the three-year average gap is. Needs two consecutive years. |
| Inventory Efficiency | Investigate / OK | Same rule with inventory. Companies not reporting inventory get "Not enough data". |
| Normalized Earnings | Relatively stable / Unstable | Gap between reported and normalized profit as a share of reported profit. Unstable at 30% or more in the latest year, or 15% or more in 2 of the last 3. Needs positive latest profit. |
| Free Cash Flow | Weak / Adequate / Strong | Sum of FCF over sum of profit, last three years (at least two years, positive profit total). Strong 60% or more, Adequate 20% to 60%, Weak below 20% or negative. |
| Earnings Sustainability | Review / OK | One-off items at 15% or more of profit, or other income above 20% of pre-tax profit, in 2 of the last 3 years. |

Header pill (from Profit vs Cash Flow): Red flag gives "Weak cash backing", Watch gives "Cash backing to watch", Steady gives "Cash backing steady", missing gives "Not enough data". Each pill has a shape (flag, !, tick, dash) plus text.

Thresholds are in `INTEL_THRESHOLDS`. Why these values: 80% and 15%/30% reuse the Profit Reality Check's own thresholds so both parts agree; 10 points and 20% likewise; FCF 20%/60% and the "2 of 3" repeat rule are the owner-reviewable choices of this module.

## Sector handling

- Lenders (the page's `isBank`, or sector/industry text matching bank, NBFC, insurance, housing finance, microfinance, lending, credit): no cash-conversion, FCF, receivables or inventory modules and no cash-based pill. The card says "Cash-flow analysis is not comparable for lenders" and shows Normalized Earnings and Earnings Sustainability only.
- Project-based, seasonal or cyclical industries (sector/industry text matching construction, infrastructure, engineering, capital goods, real estate, shipbuilding, defence, sugar, fertiliser, cement, steel, metals, mining, power, airlines, hotels, agri, auto): Profit vs Cash Flow Red flag is softened to Watch and an extra caveat is shown.
- Peer comparison: the peers data on the page has no cash-conversion fields, so the card says "Peer comparison: not available". No new data feed.

## Sign fix in the data part

Operating cash flow / profit used `nf()`, which drops the sign (it uses the absolute value), so negative cash flow showed as a positive percentage. The row now uses the signed formatter. Ratios are kept at four decimals (not two) before display to avoid double rounding. The five-year tile and bullet, and the "normalized" bullet, now carry the minus sign (U+2212).

## Not built (needs the owner's methodology decision)

Earnings Quality Score 0-100 (no score is invented), Cash Conversion Trend as its own module, Core vs Non-core Profit as its own module, Accrual Quality, Dividend Sustainability, Debt Repayment Capacity, Earnings Red Flags aggregate, Peer Benchmarking (no data feed).
