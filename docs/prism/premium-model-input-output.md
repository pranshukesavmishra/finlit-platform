# Premium model input/output contract

This reference describes the implementation, not a provider's entire API schema. The adapter is the boundary between provider-specific data and the pure scoring engine. See [implementation and formulas](premium-model-implementation.md) and [report lifecycle](premium-report-lifecycle.md).

## 1. Public application requests

All report generation and signed-PDF requests require a CMS administrator bearer token. They return `Cache-Control: no-store`. Company selection uses the same admin Stock Fundamentals search/discovery endpoints as the dashboard.

### Generate the current report

```http
POST /api/premium-reports
Authorization: Bearer <administrator token>
Content-Type: application/json
```

```json
{
  "query": "HDFCBANK",
  "statement_type": "consolidated",
  "delivery": "inline"
}
```

| Request field | Accepted value / behavior |
| --- | --- |
| `query` | 2-80 characters: selected symbol, company name, ISIN or supported search alias. Exact identity is resolved before fetching data. Ambiguous matches require selecting a symbol. Unknown ticker-like text is not fabricated into an instrument. |
| `statement_type` | `consolidated` or `standalone`; default consolidated. The response reports the dashboard's effective basis and requested-basis metadata separately. |
| `delivery` | `inline` for the current frontend: HTTP 200 with a ready signed snapshot. Default `background` exists for compatibility: HTTP 202 with a process-local pending job. |

Relevant failures: 401 expired/missing admin session; 404 unknown company; 422 invalid/ambiguous request; 502 generation/provider failure. A successful response can still have missing model inputs; inspect its rating, review and completeness fields. Compatibility jobs can also return 429 when generation capacity is exhausted.

### Download the exact current calculation

```http
POST /api/premium-reports/pdf
Authorization: Bearer <administrator token>
Content-Type: application/json
```

The body is `{ "report": snapshotWithoutReceipt, "receipt": snapshotReceipt }`. Preserve the whole report, including `snapshotExpiresAt`; remove only `snapshotReceipt` from the nested report. The response is `application/pdf` with an attachment filename. Expiry, tampering, wrong subject or wrong-purpose receipt returns HTTP 400. The server verifies the snapshot and renders it without fetching providers or recalculating the rating.

The current snapshot expires after 1,800 seconds. The frontend keeps only the current report in tab session storage and module memory. It does not save report history. A new browser tab/deep link cannot be assumed to have another tab's signed snapshot.

## 2. Raw provider capture -> adapter

Production uses `_premium_dashboard_inputs(symbol, requested_basis, now)` and returns `(raw, sources, effective_basis, sourcing)`. The adapter is `adapt_inputs(raw, symbol, as_of_date, effective_basis)`, returning `(inputs, group, profile, input_meta, warnings, trends)`.

| Raw section | Meaning |
| --- | --- |
| `profile` | Resolved company classification and description used for group selection. |
| `quarterly`, `annual` | Resolved selected-basis P&L rows with end dates, optional start/publication dates and provider amount fields. |
| `balance`, `balance_recent` | Annual and recent balance-sheet observations; exact dates determine latest and year-earlier comparisons. |
| `cashflow` | Annual operating cash-flow rows; quarterly dashboard cash flow is not treated as annual. |
| `quote` | Symbol-keyed price/market-cap/share-count observation; quote market cap is already in crore. |
| `prices` | Dated close/volume history from one selected daily series. |
| `summary`, `distribution`, `declaration` | Dated share counts, promoter holdings, pledged amounts and explicit no-pledge declarations. |
| `asset_quality`, `asset_quality_basis` | Dashboard-selected NPA disclosure rows and their explicitly reported basis. |
| `ratios` | Dated historical valuation multiples used for own-history medians. |
| `peers` | Industry peer symbols for fallback benchmark calculations. |
| `benchmarkObservations` | Reported provider comparisons with metric, provider, scope, retrieval time and available basis/date information. |

Financial statement raw amounts use rupees internally. Normalized engine monetary values use crore. Read `financial_fields.py` and the adapter's ordered aliases before adding mappings. Neither a generic category name nor a successful HTTP request proves that the needed observation exists.

## 3. Pure engine input

`score_company(inputs: dict, group: str) -> rating: dict`. Unsupported groups raise `ValueError`. It performs no network/database/clock access and does not mutate its input.

### Units and chronology

- All arrays run **oldest -> newest**, sharing the adapter's calendar slots for their frequency. An interior missing period remains `null`; arrays are not independently compacted.
- Keep at most 14 quarterly observations and six annual observations. More input history is sliced to the engine's configured windows.
- Monetary values are **INR crore**; EPS and price are **INR/share**; `shares` is **crore shares**. Therefore `price * shares` produces market cap in crore.
- Percentage inputs are percentage points: `2.5` means 2.5%, not 0.025. Ratios such as debt/equity and valuation multiples are plain multiples.
- Unknowns are `null`/`None` or absent keys. Observed zero is meaningful. Non-finite/boolean/non-numeric values are rejected by numeric normalization. The engine is not a substitute for identity, date, unit or basis validation in the adapter.

### Financial history fields

| Key | Type / unit | Consumed by |
| --- | --- | --- |
| `sales_q`, `sales_y` | `list[number|null]`, crore | Income streak/growth/CAGR; non-financial margins; loss severity. "Sales" means operating revenue, lender NII or insurer net premium according to group. |
| `net_profit_q`, `net_profit_y` | Same | Profit streak/growth/CAGR, latest annual profitability, cash conversion, PEG and loss rules. |
| `operating_profit_q` | Same, operating EBITDA | Non-financial margin change and trailing EV/EBITDA. Generic operating profit is not interchangeable. |
| `eps_q` | `list[number|null]`, INR/share | Four-quarter EPS denominator for calculated P/E. |
| `operating_cash_flow_y` | `list[number|null]`, crore | Three-year cash conversion, matched to annual profit slots. |
| `net_worth_y` | `list[number|null]`, crore | Internal annual financial-history display; not the ROE denominator. |

### Latest scalar fields

| Key | Unit / required definition | Consumed by |
| --- | --- | --- |
| `price` | Positive INR/share, with date recorded in metadata | P/E, P/B, enterprise value. |
| `shares` | Positive crore shares with identity/market-cap reconciliation | P/B and enterprise value. |
| `eps_fy` | Latest annual INR/share | P/E fallback only when fewer than four quarterly EPS slots exist and trailing EPS is unavailable. |
| `eps_ttm` | Optional explicit trailing INR/share accepted by the pure engine | Preferred fallback over annual EPS when fewer than four quarterly slots exist. The ordinary adapter calculates P/E primarily from quarterly EPS. |
| `net_worth` | Latest **total equity**, crore | D/E, ROE, P/B, net-worth growth and loss/negative-equity valuation rules. |
| `total_assets` | Latest total assets, crore | BANK/NBFC ROA. |
| `total_debt` | Latest total borrowings, crore; liabilities are not borrowings | D/E and enterprise value. |
| `cash` | Latest cash and bank balances, crore | Enterprise value. Investments are not automatically cash. |
| `profit_before_tax`, `interest_cost` | Latest annual matching-period PBT and P&L interest expense, crore | Interest cover. Expense zero requires an explicit observation; missing expense stays unavailable. |
| `loans_now`, `loans_1y_ago` | Latest and exact year-earlier loan book, crore | BANK/NBFC loan growth. |
| `net_worth_1y_ago` | Equity on the exact year-earlier date, crore | INSURANCE net-worth growth. |
| `gross_npa_pct`, `net_npa_pct` | Reported percentages after fraction conversion and placeholder checks | BANK/NBFC Quality. |
| `industry_median_pe`, `industry_median_pb`, `industry_median_ev_ebitda` | Positive compatible comparison multiples | Applicable industry/sector valuation slots. Legacy key names can hold a disclosed sector benchmark; inspect `benchmark_details`. |
| `own_5y_median_pe`, `own_5y_median_pb` | Positive median from eligible historical buckets | Own-history valuation slots and permitted substitutions. |
| `volatility_pct`, `biggest_fall_pct` | Percentages calculated from validated daily history | Risk. |
| `trading_value_cr` | Average daily trading value, crore | Risk step score. |
| `promoter_pledged_pct` | Percentage of promoter holdings pledged, 0-100 | Risk. Unknown values are excluded from scoring but reduce coverage. |

Additional diagnostics are retained without automatically becoming active scoring factors: `annual_net_worth`, `annual_total_assets`, `capital_adequacy_pct`, `solvency_ratio`, `risk_calculation`, `valuation_unverified` and `benchmark_details`. Capital adequacy/solvency are not active Quality inputs in the current version.

`rating_blockers: list[str]` prevents an overall rating. `rating_cautions: list[str]` sets a separate review-required data-integrity flag without changing documented metric points.

### Offline example

Run from the repository root; this uses a synthetic fixture and makes no provider requests:

```python
import json
from pathlib import Path
from backend.premium_engine import score_company

inputs = json.loads(Path("backend/tests/premium_example.json").read_text())
rating = score_company(inputs, "MFG")
print(rating["final"], rating["label"], rating["confidence"])
for factor in rating["metrics"]:
    print(factor["metric"], factor["value"], factor["points"], factor["status"])
```

## 4. Rating output

| Key | Meaning |
| --- | --- |
| `modelVersion`, `baselineVersion`, `fillVersion` | Engine implementation, owner baseline and fixed estimation snapshot. |
| `group` | Resolved one of eight groups. |
| `final` | Unrounded score out of 100, or `null` when NOT RATED. |
| `label` | STRONG / HEALTHY / AVERAGE / WEAK / POOR, or NOT RATED. A provisional STRONG is labelled HEALTHY. |
| `status` | RATED / PROVISIONAL / NOT RATED; distinct from the HTTP report's lifecycle `state`. |
| `parts`, `partWeights` | Four category scores after caps, and final aggregation weights. Category values can remain internal when the final rating is withheld; reader views hide them for NOT RATED. |
| `coverage`, `confidence` | Per-category completeness and weighted overall completeness, each 0-1. They are not probabilities. |
| `judgedQuarters` | Minimum year-on-year comparison count across income and profit streaks, not the number of good growth quarters. |
| `dataIntegrityStatus` | PASS or REVIEW REQUIRED based on cautions/blockers, independent of RATED/PROVISIONAL. |
| `metrics` | Factor rows described below. |
| `loss`, `lossCapped`, `valuationCapped`, `adjustments`, `capPointsLost` | Loss profile, applied ceilings and their reconciled effect on the final score. |
| `strengths`, `weaknesses`, `flags`, `alerts`, `headline` | Internal ranked findings and explanations; presentation supplies separate reader-friendly wording. |

Each metric row includes `part`, `metric`, `label`, raw `value`, `unit`, `points`, `status`, `statusLabel`, configured `weight`, normalized active `share`, `details`, optional `fallbackFor`, `worst`/`best` bounds, color boundaries, `severity`, and final-score `pointsEarned`/`pointsLost`. `details` holds the actual comparison periods/values, CAGR years, streak comparison counts/credits, selected growth and special-rule explanation where applicable.

| Factor status | Score treatment | Coverage treatment |
| --- | --- | --- |
| `A` Actual | Calculated/reported usable input, including meaningful zero | Full credit, except the explicit partial credit for short streak histories |
| `Z` Negative / loss rule | Documented special score; often zero | Rule-based available input; short-history blending still follows the model's streak credit rule |
| `S` Substituted | Approved industry/sector substitution for unavailable own-history benchmark | Available replacement; original history limitation is disclosed |
| `F` Filled | Supplied group point estimate remains in the score denominator | Missing input, zero credit |
| `N` Not applicable | Excluded from category score | Excluded from required coverage denominator |
| `L` Not supplied | Unknown pledge is excluded from score | Still in required coverage denominator, zero credit |

`A` does not mean a direct provider scalar: an accurately calculated ratio can be `A`. Use provenance/source metadata to distinguish reported and derived inputs.

## 5. Ready report and signed snapshot output

The service combines the rating with:

| Key | Meaning |
| --- | --- |
| `id`, `state`, `createdAt`, `completedAt` | Calculation ID, `ready`, and UTC ISO timestamps. IDs are not durable saved-report identifiers. |
| `statementType`, `company` | Effective statement basis; symbol, name and available classification/description. |
| `inputs`, `inputHash` | Exact normalized inputs used by the run, and their canonical sorted-JSON SHA-256 identity. The hash is diagnostic, not the PDF authentication token. |
| `inputMeta` | Data dates, chronology, provenance, valuation checks, requested/effective basis and dashboard source/recovery metadata. |
| `sources`, `warnings`, `benchmark` | Source availability metadata, safe limitations and benchmark policy/scope/coverage. A successful source request can still have missing fields. No provider credentials are included. |
| `trends` | Annual `{period, revenue, profit, eps}` rows used by the business-performance view. |
| `calculationTrace` | Internal quarterly/annual tables, latest inputs, per-factor equations and score aggregation/cap reconciliation. |
| `review` | Reader-facing category pros/cons, mixed/unavailable factors, notes and completeness details. |
| `snapshotExpiresAt`, `snapshotReceipt` | Added at HTTP delivery. Expiry and signed receipt bind the complete snapshot to the authenticated administrator. Do not modify the snapshot before PDF download. |

### Completeness output

`review.completeness` contains:

```typescript
{
  complete: boolean;
  missingFactorCount: number;
  limitedHistoryCount: number;
  items: Array<{
    metric: string;
    category: string;
    label: string;
    kind: "missing" | "limitedHistory";
    missingInputs: string[];
    reason: string;
    treatment: string;
  }>;
}
```

This checks the scored factor list, not all optional raw provider fields. `reason` names missing dependencies and reporting periods where known; `treatment` identifies an estimate, exclusion or short-history blend. Unknown pledge remains visible even when excluded from score. Valid zero/loss rules, true inapplicability and usable substitutions are not incorrectly listed as missing. The website and PDF consume this same presentation logic; older snapshots prompt recalculation for newer disclosure fields.

## 6. Changes and reproducibility

For a numerical investigation, preserve the effective group, `inputs`, chronology, versions, source/benchmark definitions and the unrounded rating. Run the pure engine on those exact inputs; a final reference score alone is insufficient to attribute a difference. Provider timing, statement basis, share-count definitions and benchmark scope can change results without a formula error.

Store small deterministic inputs in `backend/tests/fixtures` with meaningful regression assertions. Keep bulk provider captures, temporary audit databases, workbook diagnostics and PDF previews out of source control. Update these contracts whenever an input's meaning, fallback, unit or output interpretation changes.
