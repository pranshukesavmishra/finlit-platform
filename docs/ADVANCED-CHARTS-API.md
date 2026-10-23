# Advanced charts: API contract (backend -> frontend)

Status: v1, written before the backend code so the frontend can build against it. Every change after this point is listed in the
changelog at the bottom. Source of truth for behaviour: docs/ADVANCED-CHARTS-PLAN.md; deviations are listed in their own section.

All endpoints live under `/api/advanced`. All numbers are JSON numbers (never strings). `null` always means "no value" and is always
accompanied by a reason code somewhere in the same object (`reason`, `missing[]` or `excluded[]`). No endpoint ever returns buy/sell
wording; every chart response carries `caveats[]` which includes "Correlation is not causation." and "Information only, not advice."

## 0. Conventions

* Units (`unit` field of a metric): `"x"` times (a multiple), `"%"` percent (already x100: 12.5 means 12.5%), `"Cr"` rupees crore,
  `"Rs"` rupees (per share), `"d"` days, `"pts"` index points (RSI 0-100), `"ratio"` a plain ratio that is not a multiple (e.g. current ratio
  0.99), `"n"` a count.
* Metric `basis`: `"today"` (price-based, as on the stock page today: P/E, P/B, EV multiples, market cap, dividend yield, FCF yield),
  `"fy"` (one financial year per company: its latest FY = last column of its yearly P&L; label in `fy`), `"window"` (a price window tied to
  an FY or a fixed lookback), `"tech"` (company time series, section 8 company mode).
* Values: point values (`x`, `y`) are sent exactly as stored (at most 4 decimals), so a CSV export recomputes the same statistics.
  Statistics are sent with 6 significant figures.
* Errors use the house shape (FastAPI HTTPException):
  `{"detail": {"status": "<code>", "detail": "<plain English>", ...extra}}` with HTTP status:
  * 400 `bad_request` (unknown metric, bad symbol, bad kind/h), 404 `unknown_pair`,
  * 403 `plan_required` + `"plan": "silver"|"gold"` (feature above the caller's plan),
  * 403 `plan_limit` + `"plan"` + `"limit": n` (more companies than the plan allows),
  * 422 = pydantic validation (malformed body).
* Caching headers: `/catalog` is `public, max-age=300`. Every other route is `private, no-store` + `Vary: Cookie` (plan-dependent).

### Plans and gating (server-enforced)
| Feature | Basic / visitor | Silver | Gold |
|---|---|---|---|
| GET /catalog (page, help, unavailable list) | yes | yes | yes |
| POST /cross (cross-section scatter) | 403 plan_required silver | yes | yes |
| cross-section forward variants (pairs 8.1-8.4 `variant: "forward"`) | 403 | 403 plan_required gold | yes |
| GET /history, statement-derived metrics + gross margin, ROE, ROCE, margins | 403 | yes | yes |
| GET /history, other provider ratio history (ROA, D/E, debt/assets, interest cover, current/quick ratio, asset turnover, inventory/debtor/payable days, cash cycle, inventory/receivables turnover) and P/E, P/B history | 403 | 403 plan_required gold | yes |
| GET /tech (section 8 company mode) | 403 | 403 plan_required gold | yes |
| POST /export (CSV) | 403 | yes (what the plan can chart) | yes |
| companies per chart (`highlight` in /cross, `symbols` in /history) | - | 3 | 6 |

The company limits are graphviews.GRAPH_LIMITS[plan]["companies"] (Basic 2, Silver 3, Gold 6); exceeding them returns
403 `plan_limit` with `limit`.

## 1. GET /api/advanced/catalog

Plan-independent; the frontend uses it for tabs, pair picker, (?) help, metric search and the "not available" lists.

```jsonc
{
  "version": 1,
  "counts": {"pairs": 162, "ready": 131, "adapted": 2, "unavailable": 29, "A": 54, "C": 79, "N": 29},
  "sections": [
    {"id": 1, "slug": "valuation", "title": "Valuation ratio correlations",
     "intro": "These help assess how the market values companies relative to their financial performance.",
     "note": "Priority checks: P/E vs EPS growth, P/B vs ROE, ...",           // verbatim doc note or null
     "pairs": ["1.1", "1.2", "..."],
     "alternatives": []}                                                         // section 10 only, see below
  ],
  "pairs": [
    {"id": "1.9", "section": 1, "row": 9,
     "xLabel": "P/B ratio", "yLabel": "ROE (%)",                               // verbatim from the founder's table
     "help": "Book valuation relative to shareholder returns",                 // verbatim "What it helps analyse"
     "status": "ready",                                                         // "ready" | "adapted" | "unavailable"
     "source": "A",                                                             // "A" both stored, "C" computed, "N" not available
     "x": "pb", "y": "roe",                                                     // metric ids (null for unavailable pairs)
     "flags": ["M"],                                                            // "M" mechanical link, "L" lenders always excluded
     "mechanical": "A strong correlation is expected by construction because P/B is roughly P/E x ROE.",   // null unless "M"
     "notes": ["..."],                                                          // definition notes shown under the chart
     "reason": null,                                                            // plain English, for unavailable/adapted pairs
     "modes": ["cross", "history"],                                             // any of "cross", "history", "tech"
     "tier": {"cross": "silver", "history": "gold"},                            // plan needed per mode
     "lenders": "auto",                                                         // "auto" (lender-safe: included), "excluded", "only"
     "scale": {"x": "lin", "y": "lin"},                                         // default axis scale: "lin" | "log"
     "logOk": {"x": true, "y": false},                                          // whether a log toggle is offered per axis
     "sameAs": null,                                                            // e.g. "2.8" when this is the identical chart
     "variants": [],                                                            // e.g. [{"id":"forward","label":"Forward (12 months after results)","tier":"gold"}]
     "alt": null,                                                               // one-click alternative pair, e.g. {"x":"dy","y":"cfo_yield","label":"..."}
     "sector": null,                                                            // section 10: "Banking", "IT services", ...
     "preset": null,                                                            // section 10 universe preset: {"kind":"index","value":"NIFTYIT"} | {"kind":"match","value":"realty"}
     "tech": null}                                                              // company-mode pairs: {"kind":"rsi","h":[5,20,60]}
  ],
  "metrics": {
    "roe": {"label": "ROE (%)", "short": "ROE", "unit": "%", "basis": "fy", "digits": 1,
            "formula": "Net profit / closing shareholders' equity x 100, for the company's latest financial year (provider's yearly figure; FinLit fills a missing year from the statements on the same definition).",
            "source": "Provider yearly ratio at the same FY",
            "logOk": false, "lenders": "ok",                                   // "ok" | "excluded"
            "history": "silver"}                                               // plan for history mode, or null (no history offered)
  },
  "reasons": {"loss": "Loss-making: a price multiple is not meaningful.", "...": "..."},
  "decisions": {"few": "Too few points for a reliable line ({n}).", "...": "..."},
  "caveats": ["Correlation is not causation.", "Information only, not advice.", "..."],
  "coverageNote": "Only companies with a stored full report are charted: mostly the largest listed companies, not all listed companies.",
  "indices": [{"code": "NIFTY50", "label": "NIFTY 50"}, "..."],          // index reference points allowed in POST /cross `indices`
  "benchmarks": [{"code": "NIF50", "label": "NIFTY 50"}, "..."]         // market series for beta (/tech `market`) and yearly returns (/history `index`)
}
```

Section 10 `alternatives`: `[{"id": "10.B1", "xLabel": "P/B ratio", "yLabel": "ROE (%)", "x": "pb", "y": "roe", "lenders": "only",
"label": "Available for lenders", "help": "..."}, {"id": "10.B2", ... "y": "roa"}]` (not counted among the 162 pairs).

## 2. POST /api/advanced/cross (Silver+)

Cross-section: one point per company.

Request:
```jsonc
{
  "pair": "1.9",                 // optional; when given, x/y default to the pair's and pair rules apply (lenders, notes, variants)
  "x": "pb", "y": "roe",         // metric ids (required when no pair; must be whitelisted metric ids)
  "variant": null,               // "forward" for 8.1-8.4 (Gold)
  "universe": {
    "sector": [], "industry": [], "index": [],          // same facet values as /api/screener/catalog (sectors, industries, index codes)
    "cap": [],                                          // "Large" | "Mid" | "Small"
    "mcapMin": null, "mcapMax": null,                   // Rs Cr
    "lenders": "auto",                                  // "auto" | "exclude" | "include" | "only"   (lender-sensitive pairs force exclude)
    "sameFy": false                                     // drop companies whose FY differs from the majority FY (FY metrics only)
  },
  "scale": {"x": "lin", "y": "lin"},                    // "log" only where the metric allows it
  "trim": false,                                        // leave out the most extreme 1% at each end of X and of Y (type-7 quantiles)
  "highlight": ["TCS", "INFY"],                         // <= plan company limit
  "indices": ["NIFTY50", "NIFTYIT"]                     // optional, <= 3, codes from catalog.indices (screener INDEX_LISTS); unknown code -> 422
}
```

Response:
```jsonc
{
  "pair": "1.9", "variant": null,
  "x": {"id": "pb", "label": "P/B ratio", "unit": "x", "basis": "today", "scale": "lin"},
  "y": {"id": "roe", "label": "ROE (%)", "unit": "%", "basis": "fy", "scale": "lin"},
  "n": 812,                                  // points used in the statistics
  "universeTotal": 1180,                     // companies matching the universe filters (incl. those without a stored report)
  "excluded": [                              // each company counted once, first failing check wins, in this fixed order:
                                             // no_report -> preparing -> lender -> x -> y -> log -> fy_mismatch -> trimmed
    {"stage": "no_report", "code": "no_report", "axis": null, "count": 300, "text": "No stored full report yet."},
    {"stage": "x", "code": "neg_equity", "axis": "x", "count": 4, "text": "Negative or zero equity: the ratio would mislead."},
    {"stage": "y", "code": "no_fy", "axis": "y", "count": 23, "text": "No figure for the company's latest financial year."}
  ],                                         // invariant: universeTotal == n + sum(count)
  "points": [                                // every point used, sorted by symbol
    {"s": "ABB", "name": "ABB India", "sector": "Capital Goods", "x": 15.2, "y": 22.4, "fy": "FY26"}
  ],
  "highlights": [
    {"s": "TCS", "name": "Tata Consultancy Services", "x": 13.1, "y": 52.4, "fy": "FY26",
     "status": "included",                   // "included" | "excluded" | "outside" (filtered out of the universe; drawn hollow, not in stats)
                                             // | "no_report" (open its page to load it) | "unknown" (not a listed symbol)
     "reason": null, "reasonText": null}     // for "excluded": the code/text of the first failing check
  ],
  "stats": { /* see section 6, null when n == 0 */ },
  "fyBreakdown": [{"fy": "FY26", "n": 790}, {"fy": "FY25", "n": 22}],
  "indices": [                                // index REFERENCE points: never part of n or of the statistics (inStats is always false)
    {"code": "NIFTY50", "label": "NIFTY 50",
     "x": 3.91, "y": 15.2,                    // null when not computable; then `reason` / `reasonText` say why
     "method": {"x": "ratio_of_sums", "y": "ratio_of_sums"},   // or "median"
     "formula": {"x": "Sum of market caps / sum of latest-FY shareholders' equity (negative equity included).", "y": "..."},
     "membersTotal": 50,                      // index members found in our company list
     "membersEligible": 50,                   // with a market cap, and passing the chart's lender rule (lenders excluded -> banks not eligible)
     "membersUsed": 47,                       // eligible, with a stored report and the inputs for BOTH axes
     "mcapCoveragePct": 96.4,                 // market cap of used / eligible members, %
     "fyBreakdown": [{"fy": "FY26", "n": 46}, {"fy": "FY25", "n": 1}],
     "lossMembers": 2,                        // only for P/E: used members with zero/negative net profit (they ARE included, as NSE does)
     "lenders": "included",                   // "included" | "excluded" | "only" (same rule as the company points)
     "reason": null, "reasonText": null,      // "low_coverage" | "den_le0" | "no_members" | "log_le0" | "no_list"
     "inStats": false}
  ],
  "view": {"x": [0.8, 42.1], "y": [-12.0, 61.5], "outside": 17},   // default view = 1st-99th percentile; `outside` points drawn as edge markers
  "lenders": {"mode": "excluded", "forced": true, "count": 61},     // count = lenders left out (also inside excluded[])
  "preset": null,                             // section 10: {"label":"IT services","matched":{"index":["NIFTYIT"]}}
  "notes": ["A strong correlation is expected by construction because ...", "..."],
  "caveats": ["Correlation is not causation.", "Information only, not advice.",
              "p-values assume independent companies; companies in one sector move together, so they overstate certainty.",
              "With about 130 charts, roughly 1 in 20 will look significant by chance alone."],
  "coverage": {"withReport": 1180, "listed": 5712},
  "tableBuiltAt": "2026-10-22T10:15:00Z",
  "method": "Pearson and OLS on the points shown (log10 of values on a log axis), Spearman on ranks (ties averaged), Theil-Sen median slope; ..."
}
```

### 2a. Index reference points (`indices` in /cross)
Computed ONLY from stored figures of the index's member companies (membership: NSE Indices' public constituent lists, table
`index_members`); nothing is fetched from an index provider or estimated.
* `ratio_of_sums` (market-cap aggregate) where a sound one exists: P/E = sum of market caps / sum of latest-FY net profits over ALL used
  members, loss-makers included (NSE's convention; their count is in `lossMembers`); P/B = sum mcap / sum equity; EV/EBITDA, EV/Sales,
  EV/CFO = sum EV / sum of the FY figure; dividend yield = sum (yield x mcap) / sum mcap; FCF/CFO yield = sum FY amount / sum mcap; margins
  = sum numerator / sum revenue (lenders: total income); ROE, ROA = sum net profit / sum equity (assets); ROCE = sum EBIT / sum (assets -
  current liabilities); D/E, debt/assets, net debt/EBITDA, CFO/debt, CL/TL, WC/revenue, CA/TA, cash ratio, CFO/PAT, other income/NP,
  exceptional/NP likewise; every YoY growth = sum of this year's values / sum of last year's values - 1 over members that report both years
  (period ends 330-400 days apart). These use the same latest FY per company as the company points.
* `median` of the members' own values for everything else (current/quick ratio, days and cycles, interest cover, turnover ratios,
  gross margin, per-share items and their growth, dividend payout/cover/growth, PEG, amounts, returns, volatility, multiples at a past date).
* Value only when `mcapCoveragePct >= 80`; otherwise `x`/`y` null, `reason: "low_coverage"`, `reasonText: "Only 62% of the index (by market
  cap) has stored figures for this chart; at least 80% is needed."`. Sum of denominators <= 0 -> `den_le0`.
* The company-point P/E and EV/EBITDA are trailing-12-month (provider); the index aggregates use the latest financial year, because
  that is what is stored for every member. The `formula` strings say so.

## 3. GET /api/advanced/history (Silver+; Gold for some metrics)

`?symbols=TCS,INFY&x=g_rev&y=g_np` (or `&pair=3.2`). One point per FY per company; statistics per company (never pooled).

```jsonc
{
  "pair": "3.2",
  "x": {"id": "g_rev", "label": "Revenue growth (%)", "unit": "%", "basis": "fy", "scale": "lin"},
  "y": {"id": "g_np", "label": "Net profit growth (%)", "unit": "%", "basis": "fy", "scale": "lin"},
  "companies": [
    {"s": "TCS", "name": "Tata Consultancy Services", "status": "ok", "isBank": false,    // "ok" | "no_report" (a lender's lender-only ratios come back in missing[] with code "lender")
     "points": [{"fy": "FY22", "x": 16.8, "y": 14.1}],
     "missing": [{"fy": "FY19", "axis": "x", "code": "no_prev", "text": "No earlier year to measure growth from."}],
     "n": 7,
     "stats": { /* section 6; decision is "few" when n < 10, which is the usual case */ }}
  ],
  "notes": ["Series that trend over time can correlate even when unrelated.", "..."],
  "caveats": ["Correlation is not causation.", "Information only, not advice."],
  "benchmarks": [                               // only with &index=NIF50 (catalog.benchmarks) and a pair with share price return / TSR on an axis
    {"code": "NIF50", "label": "NIFTY 50", "metric": "ret_fy",
     "note": "Index price return over each company's financial year (dividends not included: no total-return index is stored).",
     "companies": [{"s": "TCS", "years": [{"fy": "FY26", "value": -3.1, "reason": null}, {"fy": "FY21", "value": null, "reason": "short_history"}]}]}
  ]
}
```
Yearly P/E and P/B in history mode are the provider's yearly figures: average share price over the financial year / that year's EPS
(book value per share). Verified exactly on all 8 stored RELIANCE years. Index level history covers 5 years (`short_history` before).

## 4. GET /api/advanced/tech (Gold)

`?symbol=RELIANCE&kind=rsi|macd|p52h|volg|beta&h=5|20|60&market=NIF50` (h ignored for volg and beta; `market` only for beta, one of
catalog.benchmarks; the levels are the site's stored index history, `/api/indices/{code}/history`; unknown code -> 400).

```jsonc
{
  "symbol": "RELIANCE", "name": "Reliance Industries", "kind": "rsi", "h": 20, "pair": "8.5",
  "x": {"id": "rsi", "label": "RSI (14 days, Wilder)", "unit": "pts"},
  "y": {"id": "fwd_ret", "label": "Return over the next 20 trading days (%)", "unit": "%"},
  "points": [{"d": "2026-08-28", "x": 41.27, "y": -3.12}],   // d = signal day k (x uses closes up to k only; y = C[k+h]/C[k]-1)
  "excluded": [{"code": "jump", "count": 1, "text": "..."}, {"code": "warmup", "count": 0, "text": "..."}],
  "n": 21,
  "stats": { /* section 6 */ },
  "grid": "non-overlapping: k = last-h, last-2h, ... (each forward window used once)",
  "asOf": "2026-09-29", "notes": ["..."], "caveats": ["..."]
}
```
`kind=beta`: points are ISO weeks `{"d": "2026-09-25", "x": <NIFTY 50 weekly return %>, "y": <stock weekly return %>}`, last 156
weeks, needs >= 104; `stats.ols.slope` is the beta. `kind=volg`: non-overlapping 20-session windows; x = volume growth % against the previous
window, y = absolute price return % of the same window. `kind=p52h`: x = close / highest close of the last 252 sessions x 100.
`kind=macd`: x = MACD histogram (EMA12 - EMA26 - EMA9 of that) as % of the close. Extra fields: `"beta"` (the OLS slope, only when
>= 104 weeks; else null with a note), `"market": {"code","label"}` for beta.
Windows are left out (`jump`) when a split/bonus or a one-day move beyond ln(1.8) lies inside the forward window or inside the indicator's
look-back (RSI 42 sessions, MACD 78, 52-week high 251).

## 4a. GET /api/advanced/flags (Silver+) - section 9 warning lists (not correlations)
`?symbols=TCS,INFY` (<= plan company limit).
```jsonc
{"rule": "Profit growth more than 3 times revenue growth with profit up at least 10% (same rule as the stock page's P&L flags).",
 "companies": [{"s": "TCS", "status": "ok",                          // or "no_report"
                "threeX": [ /* plflags case-1 flag objects, exactly as the stock page's P&L flags (frontend plFlags.ts twin) */ ],
                "cfo": [{"fy": "FY26", "id": "cfo_divergence", "title": "Revenue and net profit rose but operating cash flow fell",
                         "why": "Investigate receivables, inventory, working capital and accounting accruals before drawing conclusions.",
                         "revenueGrowth": 8.1, "profitGrowth": 12.0, "cfoGrowth": -6.5}]}],
 "caveats": ["..."]}
```

## 5. POST /api/advanced/export (Silver+)

Body: `{"mode": "cross", ...the /cross body}` or `{"mode": "history", "symbols": [...], "x": "...", "y": "...", "pair": "..."}` or
`{"mode": "tech", "symbol": "...", "kind": "...", "h": 20}`. Plan checks are the same as the matching chart route.

Response: `text/csv; charset=utf-8` (UTF-8 BOM), `Content-Disposition: attachment; filename="finlit-advanced-<pair or x-y>.csv"`.
Layout: a header block of `# key,value` lines (title, as-of, n, universeTotal, r, rho, slope, intercept, p, decision, method, caveats),
one blank line, then the table:
`symbol,name,sector,fy,x,y,included,reason,highlighted` (cross; one row per company in the universe, `included` = yes/no, `reason` = code);
history: `symbol,name,fy,x,y,included,reason` (missing years as `included=no`, reason `x:code` / `y:code`; each company's statistics follow as rows whose name cell is `# key`); tech: `date,x,y,included,reason`.
Any text cell starting with `=`, `+`, `-`, `@`, tab or carriage return is prefixed with `'` (formula-injection guard); numbers are written raw.

## 6. The `stats` object (same in /cross, /history, /tech)

```jsonc
{
  "n": 812,
  "space": {"x": "lin", "y": "log"},          // statistics are computed on log10(value) for a log axis
  "mean": {"x": 4.1, "y": 1.21}, "sxx": 1234.5, "syy": 99.1, "sxy": 210.2,   // in the computation space
  "pearson": {"r": 0.4612, "r2": 0.2127, "t": 14.68, "df": 810, "p": 1.2e-43, "ci": [0.405, 0.514]},   // ci null when n < 10
  "spearman": {"rho": 0.5201, "p": 3.3e-58},  // p null when n < 10
  "ols": {"slope": 0.0912, "intercept": 0.84, "se": 0.0062, "ci": [0.079, 0.103], "s": 0.31, "tCrit": 1.9628},
  "theilSen": {"slope": 0.0871, "intercept": 0.86},
  "influence": {"max": {"s": "XYZ", "name": "XYZ Ltd", "cook": 0.21, "leverage": 0.04},   // history: s = FY label; tech: s = date; cook null = leverage 1 (infinite)
                "without": {"n": 811, "r": 0.4544, "p": 4.0e-42, "slope": 0.0899}},
  "curvature": {"c2": -0.0012, "p": 0.31, "dR2": 0.001},
  "decision": {"line": "ols",                 // "ols" (draw OLS + band), "ols_ts" (OLS + band AND Theil-Sen), "none"
               "rule": "ok",                  // ok | few | no_spread | not_significant | weak | one_company | curved | pulled
               "text": "A straight line fits: higher P/B tends to go with higher ROE."},
  "line": {"x0": 0.8, "y0": 1.2, "x1": 42.1, "y1": 5.0},   // OLS line in DATA units over [min x, max x]; null when line == "none"
  "tsLine": {"x0": ..., "y0": ..., "x1": ..., "y1": ...},  // only when line == "ols_ts"
  "band": [{"x": 0.8, "lo": 0.9, "y": 1.2, "hi": 1.5}],     // 60 points, DATA units, 95% band for the fitted line (not for companies); null when no line
  "rounded": {"r": "0.46", "rho": "0.52", "p": "< 0.001", "slope": "0.0912", "r2pct": "21%"}   // display strings per the plan's rounding
}
```
Any field that cannot be computed is `null` (e.g. `pearson.r` when Sxx or Syy is 0; `spearman.p`, `pearson.ci` when n < 10; `theilSen`
when every x is equal; `influence` and `curvature` when n < 4). On a log axis, `line`, `tsLine` and `band` are transformed back to data
units (10^y), so they are curves on a linear axis and straight on the log axis the frontend draws.

Decision rules (first failing rule wins; numbers always shown):
| rule | condition | text |
|---|---|---|
| few | n < 10 | Too few points for a reliable line (n = {n}). |
| no_spread | Sxx = 0 or Syy = 0 | No line: the values do not vary. |
| not_significant | Pearson p >= 0.05 | No reliable linear relationship (p = {p}). |
| weak | abs(r) < 0.30 | Statistically detectable but too weak to be useful (explains under 9%). |
| one_company | leave-one-out (max Cook's D) flips the slope sign, or makes p >= 0.05, or abs(r) < 0.30; or Theil-Sen slope sign differs from OLS | No line: the line depends on one company ({name}). |
| curved | quadratic term p < 0.01 and R2 gain >= 0.10 | No straight line: the relationship is curved. |
| pulled | abs(b_TS - b_OLS) > 0.25 abs(b_OLS) | Extreme values pull the straight line: both the straight line and a robust (Theil-Sen) line are drawn. |
| ok | otherwise | A straight line is drawn with its 95% band. |

## 7. Reason codes (plain English)

`reasons` in /catalog carries this table; responses carry the text too.

| code | text |
|---|---|
| no_report | No stored full report for this company yet: open its page to load it. |
| preparing | This company's figures for these charts are being prepared (refresh pending). |
| unknown | Not in our list of listed companies. |
| outside | Outside the chosen filters: shown for reference, not part of the statistics. |
| lender | Banks and lenders left out: this ratio does not apply to lenders. |
| neg_equity | Negative or zero equity: the ratio would mislead. |
| no_fy | No figure for the company's latest financial year. |
| non_march | The company's financial year does not end in March, so the provider's yearly ratio is not available. |
| no_data | Not reported in the company's stored statements. |
| loss | Loss-making: a price multiple or a ratio on profit is not meaningful. |
| np_le0 | Net profit is zero or negative: a ratio on profit is not meaningful. |
| cfo_le0 | Operating cash flow is zero or negative: EV/CFO is not meaningful. |
| op_le0 | Operating profit (EBITDA) is zero or negative: the ratio is not meaningful. |
| no_debt | No borrowings: the ratio is not defined. |
| den_zero | The denominator is zero. |
| no_prev | No earlier year to measure growth from. |
| base_le0 | Growth not defined: the earlier year was zero or negative (a swing from a loss is not growth). |
| gap | The two years are not consecutive (period ends not 330-400 days apart). |
| share_change | The share count changed by more than 25% (or by more than 5% with a bonus or split): per-share growth is not comparable. |
| partial | The dividend year is not complete, or is not the same year as the results. |
| no_dividend | No dividend for the year. |
| short_history | Not enough daily price history. |
| start_gap | No close within 7 days of the start or end of the window. |
| jump | A split, bonus or a one-day price move of more than 80% inside the window: the return is not computed. |
| basis | The stored daily closes could not be confirmed to be on the provider's split/bonus-adjusted basis for this window. |
| not_complete | The 12 months after the signal date have not passed yet. |
| no_market | No NIFTY 50 history for these weeks. |
| warmup | The indicator needs more earlier prices at this date. |
| log_le0 | Zero or negative: cannot be placed on a log scale. |
| fy_mismatch | Results year differs from the majority ("Same FY only" is on). |
| trimmed | Left out by "leave out the most extreme 1%". |
| no_value | No value (not reported by the provider, or not meaningful). |
| no_growth | No positive 5-year profit growth to divide by. |
| not_lender | Not a bank or lender (this chart shows lenders only). |
| no_volume | Trading volume missing for some days in the window. |
| no_list | The member list of this index is not stored. |
| low_coverage (index) | Only {pct}% of the index (by market cap) has stored figures for this chart; at least 80% is needed. |
| den_le0 (index) | The members' combined denominator is zero or negative, so the aggregate is not meaningful. |
| no_members (index) | No member of this index has the figures for this chart. |

## 8. Plan risks 1 and 2: conclusions from the code and the recorded fixtures

**Risk 1 (split/bonus adjustment of stored closes).** What the RELIANCE fixtures prove (1:1 bonus, ex-date 28 Oct 2024):
* Dividend `adj_amount` is adjusted for later bonuses/rights (Aug 2024 Rs 10 -> 5; Aug 2019 Rs 6.5 -> 3.0469, which also carries the 2020
  rights factor). events.adjustedAmount is therefore on today's share basis.
* The provider's yearly `average_price` is adjusted (FY24 Rs 1,275.01, half the pre-bonus level), and its yearly P/E and P/B equal
  average_price / EPS and average_price / (equity / diluted shares) exactly on all 8 years (test_provider_yearly_pe_pb_definition).
* EPS and diluted share counts are RESTATED in every year (about 1,353 crore shares FY19-FY26 although balance-sheet share capital
  doubled from Rs 6,766 Cr to Rs 13,532 Cr in FY25). Per-share growth across a bonus is therefore comparable in the stored data.
* The daily-close fixture starts on 1 Jan 2025, AFTER the ex-date, and the corporate-actions fixture is empty. So whether the provider
  back-adjusts DAILY closes is NOT established by the fixtures. Check available here: the mean of our FY26 daily closes (Rs 1,424.90 on
  246 sessions) is within 0.45% of the provider's adjusted FY26 average (Rs 1,431.28), i.e. the post-bonus closes are on the adjusted basis.
Consequences built in (correct under either answer): (a) any window with a split/bonus action or a one-day move beyond ln(1.8) is
excluded (`jump`); (b) a TSR whose in-window dividends were later re-based, and every price/EPS figure at a past date (P/E and P/B at the
FY end, the forward P/E and P/B), require the "basis check": the mean of our daily closes in that FY must be within 3% of the provider's
adjusted average price (falls back to "no later split/bonus and no later re-based dividend"), else `basis`.
Open: a small bonus (e.g. 1:10, a 9% step) in an unadjusted series is not caught by the jump rule; it is caught by the basis check
only for TSR and price-at-date figures, not for plain price returns. Needs one live check on a company with a split in the last 6 years
(requires the FinEdge key, not available to this build).

**Risk 2 (provider yearly P/E definition).** Average price over the financial year / that year's EPS (exact on 8 of 8 years). History
mode labels it "(yearly, average price)".

## Deviations from the plan (each increases precision or honesty)
1. Per-share guard (`share_change`): excludes when the share count changes by more than 25%, or by more than 5% with a bonus/split
   between the two year ends. The plan excluded on any bonus/split; the stored EPS and share counts are restated (risk 1), so that would
   have thrown away correct figures, while a non-restated bonus shows as a share-count jump either way.
2. Dividends per FY are summed from all stored dividends (same forFY rule as events.dividends_by_fiscal_year, without its six-year cut).
   A year with no dividend stored counts as 0 only after the declaration season (FY end + 183 days) and only when the company has stored
   dividends from before that year; otherwise `partial` / `no_data`.
3. EV/CFO, FCF yield and CFO yield use the cash flow of the SAME latest FY as the other figures (the screener uses the last cash-flow
   column, which can be a different year).
4. Net debt/EBITDA and cash ratio: an absent cash line is `no_data` (the screener treats it as 0). An absent borrowings line is 0, as in
   the screener.
5. The plan's exceptional-items reconciliation rule is applied to every absent P&L line used: other income (other income/NP), finance
   costs (EBIT, EBIT margin, EBIT growth) and exceptional items are taken as 0 only when operating profit + other income - finance costs -
   depreciation + exceptional items reconciles to profit before tax within max(2%, Rs 0.02 Cr).
6. Price basis check (risk 1) for TSR with re-based dividends and every price-at-date multiple.
7. `sameAs` is set for every chart with exactly the same axes (2.11=2.8, 5.4=3.4, 8.3=3.8 as planned, plus 9.1=3.2, 9.2=3.3, 9.3=3.6,
   9.5=5.12, 9.6=5.13).
8. 8.1 / 8.2 "same FY" use P/E and P/B at the financial-year-end close (pe_fy, pb_fy) against that year's return, not today's multiple.
9. Statistics are returned for the requested scale only (the plan said both); a scale toggle re-requests and is served from the LRU.
10. No `ax_div_fy`: every FY figure, dividends included, is on `ax_fy` by construction; forward figures carry `ax_sig_fy` / `ax_sig_date`.
11. `ax_*` values are stored with 10 significant figures (the rest of scores.metrics keeps 4 decimals) so they can be checked against the
    raw statements; per-share figures inherit the statements' 0.01-crore rounding of the share count (relative error <= 4e-6).
12. Technical windows are also excluded when the jump lies in the indicator's look-back, not only in the forward window.
13. Decision rule 5: a Theil-Sen slope of exactly 0 against a non-zero OLS slope counts as a sign difference; a point with leverage 1
    (Anscombe IV) has infinite Cook's distance (`cook: null`) and an undefined refit, which fails the rule.
14. Lender-only alternatives for section 10 banking (10.B1 P/B-ROE, 10.B2 P/B-ROA) are separate entries, not among the 162.
15. Added (founder, 22-23 Oct): index reference points, benchmark choice for beta and yearly returns, and GET /flags for section 9's
    warning lists.
16. The plan's "Silver: history for statement-derived metrics" also covers price-window yearly figures (share price return, TSR) and
    dividends, which come from stored prices and corporate actions.

## Changelog
* v1 (22 Oct 2026): first version, written before the backend code.
* v2 (23 Oct 2026): `indices` in POST /cross (request + `indices[]` in the response, section 2a); catalog `indices` and `benchmarks`;
  /history `index` param + `benchmarks[]`; /tech `market` param + `beta`/`market` fields; new GET /flags (section 4a); reason codes
  no_growth, not_lender, no_volume, no_list and the index reasons; `influence.max.s` meaning per mode; risk conclusions and deviations
  filled in. Nothing removed or renamed from v1.
