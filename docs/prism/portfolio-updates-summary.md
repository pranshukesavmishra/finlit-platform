# Stakeholder update — Financial Portfolio

Branch: `codex/portfolio-updates`
Prepared: 18 October 2026 (IST)
Scope: all feature changes on this branch relative to its starting commit, `b463db6` (branch created 17 October 2026). Earlier chart, ratio-bucketing and theme changes already present at that commit are excluded.

## Delivered changes

1. **Bank asset-quality table below P&L**
   - Added Gross NPA %, Net NPA % and CET1 ratio % below the P&L / quarterly results table for banks only; excluded NBFCs, insurers and asset managers from this new table.
   - Matched displayed periods to the financial statements and converted provider fractions into percentages.
   - Ignored all-zero provider placeholder disclosures and used available standalone bank disclosures when consolidated disclosures are unavailable, with the statement basis labelled.

2. **Revenue breakdown within P&L**
   - Made Revenue expandable to show business segments returned by the FinEdge segment-revenue API, for annual and quarterly views and the effective statement basis.
   - Added “Less: inter-segment revenue” and “Other revenue adjustments” to reconcile segment figures to the displayed P&L revenue; the adjustment row explains the difference.
   - Combined punctuation variants such as “Oil & Gas” and “Oil and Gas”. Segment names remain provider-driven rather than a fixed company-specific list.
   - Suppressed breakdowns for periods where the provider’s component figures contradict its own segment total and surfaced a data-quality warning.

3. **Structure Summary and promoter pledge disclosures**
   - Added a table for the latest 12 quarterly filings: total shares (crores), locked-in shares %, pledged shares %, promoter pledged shares %, and total shareholders. Added a Structure navigation shortcut.
   - Used total company shares as the denominator for company pledge %, and promoter-group shares for promoter pledge %.
   - Integrated FinEdge summary, distribution and declaration responses. Explicit “no shares” declarations fill otherwise missing locked-in and promoter-pledge values with zero; unknown values remain N/A.
   - Preserved very small positive percentages instead of rounding them to a displayed zero, and added explanations for declaration-based zeroes and missing data.

4. **Detailed shareholding pattern**
   - Added a separate quarterly table retaining reported ownership categories and expandable named shareholder rows.
   - Included holder/category search, expand/collapse controls, and older/newer quarter navigation in 12-quarter windows.
   - Preserved parent totals separately from child holdings to avoid double-counting. Missing disclosures remain N/A.

5. **Company discovery by sector or industry**
   - Added Discover companies above Direct search, expanded by default.
   - Supported sector/industry selection, starter suggestions, exact classification entry, result counts, filtering, pagination, and opening a company’s fundamentals.
   - Added shortcuts to browse the current company’s sector or industry.
   - Used FinEdge’s documented classification-search parameters, resolved returned BSE codes through the stock directory, and removed duplicates.
   - Changed name/symbol/ISIN search to use the stock directory. Removed the default Reliance selection and automatic initial company load; empty search now shows a prompt and disables loading/refreshing until appropriate.

6. **Admin Market Events & Index Dashboard**
   - Added a dedicated admin dashboard with IPO calendar, results calendar, corporate announcements, investor call transcripts, index prices and index valuation history.
   - Included date filters where supported, optional company symbols for disclosures, index selection for valuation history, search within results, pagination, refresh/retry handling, and source/fetch timestamps.
   - Linked announcements/transcripts to provider documents after validating their URLs. Added request date-range limits and five-minute backend caching.
   - Placed the “Market Events & Index Dashboard” button directly below “Stock Fundamental Data Dashboard” in the CMS.
   - Required admin access for the dashboard and its new data endpoints. The `/markets` route also requires admin access and redirects to the admin dashboard. No public Markets navigation entry is present.
   - Added an explicit “Back to CMS” button across all Markets sections, including Index prices and Index valuation.

7. **Commodity prices and trends**
   - Added a Commodity prices tab within the admin Markets dashboard.
   - Included searchable commodity lookup, monthly commodity indices and eight-core-industry indices, selected-series monthly history, provider percentage changes, pagination and refresh/retry handling.
   - Labelled values as monthly index levels rather than rupee spot prices, and displayed the latest reported month.
   - Allowed history to remain available if the percentage-change feed fails. Protected the new commodity endpoints with admin authentication.

## Validation and current limitations

- Production frontend build passed.
- All 31 targeted backend tests passed across financial normalization, classification search, market feeds, commodity handling, access control and validation.
- Local in-app browser checks covered the new workflows, including live commodity data, Reliance’s detailed shareholding/Structure Summary, and the Markets Back to CMS navigation.
- Reliance’s promoter pledge now displays 0% where its declarations explicitly confirm none. Total-company pledged shares remain N/A where FinEdge supplies neither a number nor a declaration establishing none; promoter-only declarations cannot establish the total-company figure.
- Data availability and freshness depend on FinEdge. Index prices are reported end-of-day values; commodity series are monthly indices. Classification suggestions are a starter list, with exact custom classifications supported.
- The financial model/calculation engine is not implemented in this change. Pledge disclosures are available in the dashboard for future use.
- These changes have been validated locally; this update does not constitute a production deployment.
