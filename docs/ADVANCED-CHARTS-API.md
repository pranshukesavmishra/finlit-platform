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
  "coverageNote": "Only companies with a stored full report are charted: mostly the largest listed companies, not all listed companies."
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
  "highlight": ["TCS", "INFY"]                          // <= plan company limit
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

## 3. GET /api/advanced/history (Silver+; Gold for some metrics)

`?symbols=TCS,INFY&x=g_rev&y=g_np` (or `&pair=3.2`). One point per FY per company; statistics per company (never pooled).

```jsonc
{
  "pair": "3.2",
  "x": {"id": "g_rev", "label": "Revenue growth (%)", "unit": "%", "basis": "fy", "scale": "lin"},
  "y": {"id": "g_np", "label": "Net profit growth (%)", "unit": "%", "basis": "fy", "scale": "lin"},
  "companies": [
    {"s": "TCS", "name": "Tata Consultancy Services", "status": "ok",     // "ok" | "no_report" | "unknown" | "lender_excluded"
     "points": [{"fy": "FY22", "x": 16.8, "y": 14.1}],
     "missing": [{"fy": "FY19", "axis": "x", "code": "no_prev", "text": "No earlier year to measure growth from."}],
     "n": 7,
     "stats": { /* section 6; decision is "few" when n < 10, which is the usual case */ }}
  ],
  "notes": ["Series that trend over time can correlate even when unrelated.", "..."],
  "caveats": ["Correlation is not causation.", "Information only, not advice."]
}
```

## 4. GET /api/advanced/tech (Gold)

`?symbol=RELIANCE&kind=rsi|macd|p52h|volg|beta&h=5|20|60` (h ignored for volg and beta).

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
`kind=macd`: x = MACD histogram (EMA12 - EMA26 - EMA9 of that) as % of the close.

## 5. POST /api/advanced/export (Silver+)

Body: `{"mode": "cross", ...the /cross body}` or `{"mode": "history", "symbols": [...], "x": "...", "y": "...", "pair": "..."}` or
`{"mode": "tech", "symbol": "...", "kind": "...", "h": 20}`. Plan checks are the same as the matching chart route.

Response: `text/csv; charset=utf-8` (UTF-8 BOM), `Content-Disposition: attachment; filename="finlit-advanced-<pair or x-y>.csv"`.
Layout: a header block of `# key,value` lines (title, as-of, n, universeTotal, r, rho, slope, intercept, p, decision, method, caveats),
one blank line, then the table:
`symbol,name,sector,fy,x,y,included,reason,highlighted` (cross; one row per company in the universe, `included` = yes/no, `reason` = code);
history: `symbol,name,fy,x,y,included,reason`; tech: `date,x,y,included,reason`.
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
  "influence": {"max": {"s": "XYZ", "name": "XYZ Ltd", "cook": 0.21, "leverage": 0.04},
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
| start_gap | No close within 7 days of the start of the window. |
| jump | A split, bonus or a one-day price move of more than 80% inside the window: the return is not computed. |
| basis | The stored daily closes are not on the provider's split/bonus-adjusted basis for this window. |
| not_complete | The 12 months after the signal date have not passed yet. |
| no_market | No NIFTY 50 history for these weeks. |
| warmup | The indicator needs more earlier prices at this date. |
| log_le0 | Zero or negative: cannot be placed on a log scale. |
| fy_mismatch | Results year differs from the majority ("Same FY only" is on). |
| trimmed | Left out by "leave out the most extreme 1%". |
| no_value | No value (not reported by the provider). |

## 8. Plan risk 1 (split/bonus adjustment of stored closes): conclusion

(Filled in after investigation; see the section below.)

## Deviations from the plan

(Filled in as the build proceeds.)

## Changelog
* v1 (22 Oct 2026): first version, written before the backend code.
