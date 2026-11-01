# Revenue-to-Cash Intelligence

Gold card on every stock page (`id="revenue-cash"`, right after Profit Reality Check inside the Ratios section; nav pill "Cash conversion").
Code: `frontend/src/lib/revenueCash.ts` (rules), `frontend/src/stock/RevenueCash.tsx` (card), `frontend/src/styles/revenue-cash.css` (prefix `rcx-`).

## Data (all from the stock page's `financials` section, yearly tables only)
| Input | Source row |
|---|---|
| Revenue | `yearly.pl.revenue` |
| Net profit | `yearly.pl.net_profit` |
| Operating cash flow (OCF) | `yearly.cf.operating` |
| Capex (negative number) / free cash flow | `yearly.cf.capex`, `yearly.cf.free_cash_flow` (falls back to OCF + capex) |
| Receivables, inventory | `yearly.bs.receivables`, `yearly.bs.inventories` |
| Fixed assets + CWIP | `yearly.bs.fixed_assets`, `yearly.bs.cwip` |
| Industry group | `profile.sector`, `industry`, `subIndustry` |
| Lender | `dataQuality.isBank`, plus bank / NBFC / insurance in the sector labels |

Annual is compared with annual only; quarterly tables are never read (so TTM and annual cannot mix). Periods are matched by label across tables; a missing value is `null` (gap), never zero. OCF margin = OCF / revenue (same OCF definition as the Profit Reality Check, which uses OCF / profit). Negative values show U+2212 and are rounded before the sign is chosen (nothing displays as "-0.0%").
Rules compare the figures as displayed (one decimal), so "exceeds 20 points" never sits beside "20.0".

## Plan
`financials` is served to every plan (it feeds the Basic Financials section), so no Gold-only number exists in it. The card is nevertheless Gold only: when the plan lacks Gold the component does not request or compute anything and renders only the header and the Gate lock over an empty outline (no figures in the DOM). Free example companies (OpenAccess) are open. No backend change was needed.

## Rules
| # | Condition (latest year unless stated) | Text | Severity |
|---|---|---|---|
| 1 | OCF margin < 0% | Revenue is not generating positive operating cash | Critical |
| 2 | OCF margin < 5% in each of the last 3 years | Weak cash conversion consistency | High |
| 3 | revenue growth > 0 and OCF margin < 0 | Sales growth is not translating into cash | Critical |
| 4 | receivables growth - revenue growth > 20 pp | Customer collection risk | High |
| 5 | inventory growth - revenue growth > 20 pp | Inventory accumulation risk | High |
| 6 | debtor days up by more than 20% (relative) | Collection efficiency deteriorating | High |
| 7 | free cash flow < 0 in each of the last 3 years | Expansion may require external funding | High |
| 8 | 5-year sum of OCF < 5-year sum of net profit (needs 5 years of both and positive profit) | Earnings have weak cash backing | High |
| 9 | OCF margin higher in each of 3 consecutive years (4 margins) | Cash conversion improving | Positive |

Boundaries are strict: exactly 0%, 5.0%, 20.0 pp, +20% do not trigger. Receivables, inventory and debtor days use average balances when three year-ends exist, otherwise year-end for both years compared; the card says which in a tooltip. Debtor days = receivables / revenue x 365.
Persistence tag per warning: "This year only", "n of the last m years", or "Based on only m years of data" (under 3 judgeable years). Rules 2, 7, 9 need 3 years, rule 8 five.
Status pill: negative -> Needs attention; 0 to <5% -> Watch (Improving if rule 9 holds); >=5% -> Healthy.

## Expansion downgrade (rule 7 only)
If capex >= 10% of revenue, fixed assets + CWIP up >= 10% and revenue growing, severity drops one level (High to Moderate) and the card says why. Capex is outside OCF, so rules 1 to 3 are never downgraded for it.

## Industry groups (keyword match on sector/industry; first match in the order project, trading, seasonal, capital)
| Group | Adjustment | Caveat shown |
|---|---|---|
| Capital-intensive | rule 7 one level lower | yes |
| Project and EPC | weak margin 3%, gap 30 pp, debtor days 30%; rules 2,4,5,6 one level lower | yes |
| Seasonal | gap 30 pp, debtor days 30%; rules 4,5,6 one level lower | yes |
| Trading and distribution | weak margin 2%, inventory gap 30 pp; rules 2,5 one level lower | yes |
No industry or peer median of OCF margin, receivables or inventory growth exists in the loaded data, so the card states "Industry benchmark not available".

## Lenders
`isBank` (or bank, NBFC, insurance in the labels) shows "Not comparable for lenders" instead of any figure.

## Wording
Descriptive only: no advice words, never fraud or manipulation. The block is "Automated warnings"; the paragraph is "Reading the numbers" ("Investor" could read as advice). Tests scan all generated text.

## Not built
Per-company industry medians; TTM view; server-side computation (not needed, see Plan); the standalone Fundamentals page does not show the card.
