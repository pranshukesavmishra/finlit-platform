# Advanced charts: implementation plan (approved for build; the verifier checks against it)

Spec: docs/ADVANCED-CHARTS-SPEC.md (10 sections, 162 pairs, help text verbatim).

## 0. Findings from the code (read before building)
- Coverage: full metrics exist only for companies with a stored report (store.prune keeps top INGEST_LIMIT, default 500, plus followed/recently opened). ~5,000 "light" rows (data.with_listing) only have price, market cap, day change, 52w range, volume. Universe ~500-1,200, mostly large caps. Every chart must say so.
- No numpy/scipy in backend/requirements.txt: all statistics in pure Python; reference values in fixtures.
- Screener mixes periods: roe/roce/roa/de from provider ratios.latest (prefers TTM over latest FY, normalize/ratios.py build_ratios); operating_margin/net_margin are FinLit opm/npm for latest FY (analytics/derived.py); ev_ebitda uses provider TTM EBITDA while net_debt_to_ebitda uses FY operating profit; sales_growth can silently fall back to latest quarter vs a year ago (growth_basis="quarter").
- FinLit "Operating margin" IS the EBITDA margin: operating_profit = revenue - (expenses - interest - depreciation), i.e. before D&A and other income (normalize/statements.py header). Spec pair 2.10 (EBITDA margin vs Operating margin) is identical by definition here.
- Not stored: payables line (not in BS_FIELDS); R&D, advertising, raw material (not in PL_FIELDS); bank advances/NIM inputs/GNPA/CASA/CAR; employee history (only latest headcount from profile text); pledge, contingent liabilities, auditor opinion, delivery %.
- Price history: ~6-7 years of daily closes in snapshot section `price` (Postgres only, never Redis: store._cache); FinEdge daily_quotes from Jan (year-6); price_daily pruned to 500 days. NOT established whether closes are split/bonus adjusted (fixture does not span RELIANCE Oct 2024 bonus).
- screener/jobs.py rebuild_metrics(only_missing=True) does NOT compare m_ver (only checks presence): bumping METRICS_VERSION alone will not trigger a rebuild. Fix it.
- The 3x rule already exists: plflags.py case 1 (RATIO=3, MIN_PROFIT_JUMP=10), TS twin frontend/src/lib/plFlags.ts with shared fixtures.
- AppShell "Graph Studio" NavLink has end:false; it would light up on /graphs/advanced; needs end:true.
- Graph Studio uses hard-coded --gx-* hex colours (styles/graphs.css). Advanced charts must use var(--k1..k8) directly.
- Graph Studio tiers (graphviews.GRAPH_LIMITS): scatter is a Silver chart type; companies per view Basic 2, Silver 3, Gold 6; full ratio history and valuationHistory (yearly P/E, P/B) are Gold (auth/entitlements.redact_section); every plan gets history of gross_margin, operating_margin, net_margin, roe, roce.

## 1. Data map
### 1.1 Definitions (one code path: advanced/derive.py)
- FY basis: fundamentals for ONE year per company = its latest FY = last column of financials.yearly.pl (label stored as ax_fy). Provider ratios read from ratios.history.rows[key] at that SAME FY label, NOT ratios.latest (TTM). Missing for that FY -> missing with reason `no_fy` (`non_march` when ratios._fy drops non-March headers).
- "Today" basis: price-based multiples = screener values as shown on stock page/screener: pe, pb, ev_ebitda, ev_sales, ev_cfo, peg, market_cap, dividend_yield, fcf_yield.
- Same-FY rule in a pair: both FY metrics must carry the same FY label (dividend metrics can lag); "today" metrics exempt. Response carries FY breakdown (e.g. "FY26: 790, FY25: 22") and a "Same FY only" toggle drops the minority FY.
- Growth, one definition, YoY: g = (V_t / V_{t-1} - 1) x 100, defined only when both present, V_{t-1} > 0 (compute._growth convention: a swing from a loss is not growth) and the two period ends are 330-400 days apart (else reason `gap`). Why YoY not 3y CAGR: history mode needs one value per year; same FY as FY ratios; section 9 is about the latest year's divergence; CAGR loses more companies and only <=10 years are stored. Screener sales_growth/profit_growth are NOT used (can be quarter-based).
- Net profit = continuing net profit where present (statements.calc_view / net_profit_continuing), as in compute.py.
- Per-share guard: EPS growth, BVPS growth and CFO/share growth excluded with reason `share_change` when a bonus/split action (events.actions type contains bonus/split) falls between the two FY ends, or diluted shares change by >+-25% together with such an action.
- Price-window guards (all returns, volatility, technicals): window excluded (reason `jump`) if a split/bonus action falls inside it or any day has |ln(C_j/C_{j-1})| > ln(1.8). Start close must be within 7 days of its target (same rule as returns.trailing_returns).
- Lenders (is_bank): same drops as compute.py / snapshot.NOT_FOR_LENDERS plus new: cash_ratio, nd_ebitda, cfo_debt, cl_tl, wc_rev, ca_ta, cfo_pat, accruals, inv_turnover, recv_turnover, ebit_margin, gross_margin, every CFO/FCF/capex metric and its growth, g_int, g_debt, g_wc, g_inv, g_recv, EV multiples. Reason `lender`. Chart shows "N banks/NBFCs left out: these ratios do not apply to lenders". Pairs whose metrics are all lender-safe (P/E, P/B, ROE, ROA, NPM, revenue/NP/EPS growth, market cap, DY, payout, returns) include lenders by default; any lender-sensitive metric forces "Exclude banks and lenders" on.
- Negative equity: existing drops (pb, roe, de via NOT_FOR_NEGATIVE_EQUITY), reason `neg_equity`.

### 1.2 Metric dictionary ("Screener" = catalogue key in screener/catalog.py; "Hist" = ratios.history at ax_fy, provider, FinLit-filled per snapshot._fill_profitability; "New" = computed in derive.py, stored as ax_<id> in scores.metrics)
| id | Label | Source / formula |
|---|---|---|
| pe | P/E | Screener pe (provider TTM re-priced to quote; <=0 -> `loss`) |
| pb | P/B | Screener pb |
| ev_ebitda | EV/EBITDA | Screener (EV = mcap + borrowings - cash; provider TTM EBITDA) |
| ev_sales | EV/Sales | Screener (EV / latest-FY revenue) |
| ev_cfo | EV/CFO | Screener (CFO <= 0 -> `cfo_le0`) |
| peg | PEG | Screener (P/E / 5-y profit CAGR, not EPS growth: disclosed) |
| mcap | Market cap Rs Cr | Screener market_cap |
| dy | Dividend yield | Screener (TTM; 0 is a real 0 for non-payers) |
| fcf_yield | FCF yield | Screener (FY FCF / mcap x 100) |
| cfo_yield | CFO yield (alt for 7.6) | New: FY CFO / mcap x 100 |
| revenue, net_profit, ebitda (=operating_profit), cfo, fcf, capex (=abs capex), cur_liab | Amounts Rs Cr | New: FY values from pl/bs/cf |
| opm | Operating margin (before depreciation = EBITDA margin) | op / revenue x 100 (lenders / total_income), = screener operating_margin |
| npm | Net margin | NP / revenue x 100 (lenders / total income), = screener net_margin |
| ebit_margin | EBIT margin (after depreciation) | New: (PBT + finance_costs) / revenue x 100 |
| gross_margin | Gross margin | Hist (provider only, no COGS stored) |
| roe, roce, roa | Return ratios | Hist |
| de, debt_assets, icr, current_ratio, quick_ratio, asset_turnover, inv_days, debtor_days, payable_days, ccc | Provider ratios | Hist |
| cash_ratio | Cash ratio | New: cash / current_liabilities |
| nd_ebitda | Net debt/EBITDA | New: (borrowings - cash) / op, only when op > 0 (negative = net cash, kept) |
| cfo_debt | CFO/Total debt | New: CFO / borrowings, only when borrowings > 0 (else `no_debt`) |
| cl_tl | Current liabilities / Total liabilities | New: CL / total_liabilities x 100 |
| wc_rev | Working capital / Revenue | New: (CA - CL) / revenue x 100 |
| ca_ta | Current assets / Total assets | New: CA / TA x 100 |
| inv_turnover | Inventory turnover | New: 365 / inv_days ("from the provider's inventory days") |
| recv_turnover | Receivables turnover | New: 365 / debtor_days (days > 0) |
| cfo_pat | CFO/PAT | New: CFO / NP x 100, only when NP > 0 |
| accruals | Accruals ratio | New: (NP_t - CFO_t) / ((TA_t + TA_{t-1})/2) x 100 |
| oi_np | Other income / NP | New: other_income / NP x 100 (NP > 0) |
| exc_np | Exceptional items / NP | New: exceptional / NP x 100 (NP > 0); with no exceptional row the value is 0 ONLY if op + OI - fin - dep reconciles to PBT within max(2%, Rs 0.02 Cr); else `no_data` |
| payout | Dividend payout | = screener dividend_payout (DPS_FY / EPS_FY) |
| div_cover | Dividend cover | New: EPS_FY / DPS_FY (DPS > 0) |
| cfo_ps | CFO per share Rs | New: CFO / diluted_shares_cr |
| eps, bvps | Per share | EPS as in compute; BVPS = equity / shares |
| g_rev, g_np, g_eps, g_ebitda, g_ebit (PBT+fin), g_pbt, g_tax, g_cfo, g_fcf, g_capex, g_assets, g_bv (equity), g_bvps, g_wc, g_recv, g_inv, g_dep, g_int (finance_costs), g_debt | YoY growth | New, per 1.1 |
| g_dps | Dividend growth | New: events.dividendsByFY.dps (already split-adjusted); FY must not be in `partial` and must equal ax_fy, else `partial` |
| ret_fy / tsr_fy | Share price return / TSR, same FY | New: close at FY end / close at previous FY end - 1; TSR adds dividends with ex-date in (start, end] / start close |
| vol3y / mdd3y | Volatility / max drawdown 3y | New: stdev daily log returns over last 756 sessions x sqrt(252) x 100 (needs >= 700 sessions); peak-to-trough % same window |
| inst_chg_1y + ret_inst | Institutional holding change + return same window | Screener own_inst_chg_1y; new: price return between the two shareholding quarter-ends |
| pe_sig, pb_sig, fwd12 | Forward variant (8.1-8.4) | Signal date = FY end + 75 days (past SEBI 60-day deadline), last close on/before it; pe_sig = close / EPS_FY; pb_sig = close / BVPS_FY; fwd12 = return over next 12 calendar months; cross-section uses the latest FY whose window is complete. No look-ahead. |
| rsi, macd_pct, p52h, volg, beta | Technicals | advanced/tech.py, company mode (section 2c) |

### 1.3 Pair-by-pair (162 pairs). Codes: A both stored; C computable (new ax_); N not available; M mechanical link (banner "a strong correlation is expected by construction because X is computed from Y"); L lenders excluded.
Section 1 (24, all ship): 1.1 P/E-g_rev C; 1.2 P/E-g_eps C; 1.3 P/E-ROE A; 1.4 P/E-ROCE A; 1.5 P/E-opm A; 1.6 P/E-npm A; 1.7 P/E-g_fcf C,L (many excluded base<=0); 1.8 P/E-DY A,M (price in both); 1.9 P/B-ROE A,M (P/B ~ P/E x ROE); 1.10 P/B-ROA A; 1.11 P/B-g_eps C; 1.12 P/B-g_bv C; 1.13 EV/EBITDA-g_ebitda C,L (TTM provider EBITDA on X, FY FinLit on Y: note); 1.14 EV/EBITDA-EBITDA margin(=opm) A,L; 1.15 EV/EBITDA-ROCE A,L; 1.16 EV/EBITDA-FCF yield A,L; 1.17 EV/Sales-g_rev C,L; 1.18 EV/Sales-opm A,L,M; 1.19 EV/CFO-g_cfo C,L; 1.20 EV/CFO-cfo_pat A,L; 1.21 PEG-g_eps C,M; 1.22 mcap-revenue A log-log; 1.23 mcap-NP A log-log (NP<=0 left out of log view); 1.24 mcap-CFO A,L log-log.
Section 2 (16 ship, 1 N): 2.1 ROE-P/B A,M; 2.2 ROE-P/E A; 2.3 ROE-ROA A,M (ROE = ROA x leverage); 2.4 ROE-ROCE A; 2.5 ROCE-ROA A; 2.6 ROCE-opm A; 2.7 ROA-npm A,M (ROA = NPM x asset turnover); 2.8 opm-npm A,M; 2.9 gross_margin-opm A,L; 2.10 ADAPTED (identical by FinLit definitions): shipped as "EBITDA margin (opm) vs EBIT margin" with explanation C,L; 2.11 EBITDA margin-npm A = same chart as 2.8 (note); 2.12 g_rev-opm C; 2.13 g_rev-ROCE C; 2.14 asset_turnover-ROA A,L,M; 2.15 inv_turnover-ROCE C,L; 2.16 ICR-ROE A,L (log toggle; debt-free companies give huge/no cover); 2.17 cost-to-income vs ROA N (bank op costs and provisions not split in stored P&L; not standard for non-banks).
Section 3 (13 ship, 2 N): 3.1 g_rev-g_eps C; 3.2 g_rev-g_np C; 3.3 g_rev-g_ebitda C; 3.4 g_rev-g_cfo C,L; 3.5 g_ebitda-g_np C; 3.6 g_ebitda-g_cfo C,L; 3.7 g_np-g_eps C,M (identical unless share count changes); 3.8 g_eps-ret_fy C; 3.9 g_rev-tsr_fy C; 3.10 g_assets-g_rev C; 3.11 g_capex-g_rev C,L; 3.12 g_wc-g_rev C,L (negative WC bases excluded, counted); 3.13 order book N (only in company presentations); 3.14 g_bv-g_eps C; 3.15 R&D N (not a separate stored P&L line).
Section 4 (14 ship, 1 N; all L per the doc's sector note): 4.1 D/E-ROE A; 4.2 D/E-ROCE A; 4.3 D/E-ICR A; 4.4 D/E-npm A; 4.5 D/E-g_eps C; 4.6 D/E-vol3y C; 4.7 credit rating N (not stored; agency licence terms unchecked); 4.8 debt_assets-ROA A; 4.9 nd_ebitda-EV/EBITDA A (different EBITDA periods, disclosed); 4.10 nd_ebitda-FCF Rs Cr A (amount: size note + one-click switch to FCF yield); 4.11 ICR-D/E A (axes swapped from 4.3; Y-on-X line differs); 4.12 g_int-g_ebit C; 4.13 g_int-g_np C; 4.14 cfo_debt-D/E C; 4.15 cl_tl-current_ratio C.
Section 5 (16 ship, 1 N; all L): 5.1 NP-CFO A (amounts; linear axes + Theil-Sen + Spearman; log view keeps >0 only); 5.2 CFO-FCF A,M; 5.3 g_np-g_cfo C; 5.4 g_rev-g_cfo C = same chart as 3.4; 5.5 cfo_pat-npm A; 5.6 cfo_pat-g_eps C; 5.7 cfo_debt-nd_ebitda C; 5.8 FCF yield-P/E A; 5.9 FCF yield-EV/EBITDA A; 5.10 capex Rs Cr-g_rev C (size note); 5.11 capex-CFO A log-log; 5.12 g_recv-g_rev C; 5.13 g_inv-g_rev C; 5.14 payables growth N (no payables line mapped; later via tradePayables* in BS_FIELDS + full reload); 5.15 g_dep-g_capex C; 5.16 CFO-EBITDA A; 5.17 accruals-cfo_pat C,M.
Section 6 (13 ship, all L): 6.1 current-quick A,M; 6.2 current-D/E A; 6.3 quick-ICR A; 6.4 cash_ratio-cur_liab C,M (CL is denominator; log X); 6.5 recv_turnover-opm C; 6.6 debtor_days-g_rev C; 6.7 inv_turnover-gross_margin C; 6.8 inv_days-g_rev C; 6.9 payable_days-CFO A; 6.10 ccc-CFO A; 6.11 ccc-ROCE A; 6.12 wc_rev-opm A; 6.13 ca_ta-ROA C.
Section 7 (11 ship, 2 N): 7.1 DY-P/E A,M; 7.2 DY-P/B A; 7.3 payout-g_eps C; 7.4 retained earnings growth N (no retained-earnings line; reserves include securities premium; no substitute); 7.5 payout-ROE A; 7.6 DY-cfo_ps C (warning: rupees per share not comparable across companies; one-click alternative DY-cfo_yield; meaningful in history mode); 7.7 div_cover-DY C (payers only); 7.8 g_dps-g_eps C; 7.9 g_dps-g_cfo C,L; 7.10 buyback yield N (amounts not stored, only 3-year flag); 7.11 tsr_fy-g_eps C; 7.12 tsr_fy-ROE C; 7.13 g_bvps-ret_fy C.
Section 8 (11 ship, 1 N): 8.1 P/E-return C two variants (a) same FY (M: price in both) (b) forward pe_sig vs fwd12; 8.2 P/B-return C same two variants; 8.3 g_eps-return C (= 3.8 plus forward variant); 8.4 g_rev-return C; 8.5 RSI-next return C company mode h=5/20/60; 8.6 MACD-next return C company mode; 8.7 volume growth-|return| C company mode; 8.8 ADAPTED "Beta vs Market return": weekly stock return vs weekly NIFTY 50 return, regression slope = beta, company mode, NIFTY 50 levels from existing /api/indices/NIF50/history (no new source); in cross-section market return is the same for every company so that view is not offered (say so); 8.9 vol3y-mdd3y C cross-section; 8.10 p52h-next return C company mode; 8.11 delivery % N (NSE bhavcopy not ingested); 8.12 inst_chg_1y-ret_inst C.
Section 9 (12 ship, 3 N): 9.1 g_rev-g_np C; 9.2 g_rev-g_ebitda C; 9.3 g_ebitda-g_cfo C,L; 9.4 g_eps-g_np C,M; 9.5 g_recv-g_rev C,L; 9.6 g_inv-g_rev C,L; 9.7 oi_np-g_np C; 9.8 exc_np-g_np C; 9.9 g_int-g_rev C,L; 9.10 g_tax-g_pbt C (tax credits make base <=0: excluded); 9.11 g_cfo-g_np C,L; 9.12 g_debt-g_ebitda C,L; 9.13 promoter pledge N; 9.14 auditor opinion N; 9.15 contingent liabilities/net worth N. The 3x rule is NOT a correlation: reuse plflags.py case 1 (server) / plFlags.ts (client), show as a separate flag list for the selected companies. The doc's high-priority warning (revenue up and NP up but CFO down) is a separate flag list too.
Section 10 (3 ship, 18 N): Banking 5 all N (NIM needs interest-earning assets; advances, GNPA, CASA, CAR not stored) -> offer instead, labelled "available for lenders": P/B-ROE and P/B-ROA filtered to is_bank. Insurance 2 N (embedded value, combined ratio not stored). IT: 10.8 g_rev-EBIT margin C (filter NIFTY IT membership or industry); 10.9 employee growth N (only latest headcount); 10.10 sales_per_employee-opm A (disclose headcount date unknown). FMCG volume, FMCG advertising, manufacturing capacity, manufacturing raw material, auto vehicle sales, real-estate pre-sales, telecom ARPU, pharma R&D, commodities price, retail same-store sales: all N (not stored lines; no commodity price series). Real estate 10.17 nd_ebitda-ICR A (realty firms are not lenders).
TOTALS: 162 pairs = 54 A + 79 C + 29 N; 133 ship now (82%) incl. 2 adapted (2.10, 8.8). 8.5, 8.6, 8.7, 8.8, 8.10 run in company mode.

## 2. Modes
(a) Cross-section (each point = one company). Universe filters reuse the facets of /api/screener/catalog (no new facet endpoint): sector and industry (Table.sector/industry); SEBI size band (Table.cap Large/Mid/Small) + optional min/max market cap; index membership (Table.members, INDEX_LISTS: NIFTY 50/100/200/500, sector indices); "Exclude lenders"; "Same FY only"; "Leave out the most extreme 1%" (off by default). Section 10 presets apply a sector filter; build the industry/sector mapping from SELECT DISTINCT macro_sector, sector, industry FROM scores, never guessed; NIFTY IT can use index membership. Added companies: labelled, distinct marker shapes in --k1..k6; outside the universe filter -> hollow + "not part of the statistics"; no stored report -> "open its page to load it"; a missing value -> chip shows the reason.
(b) Company history (each point = one FY per selected company); one colour per company; statistics per company, no pooling. Sections 2, 3, 4 (not 4.6/4.9), 5 (not 5.8/5.9), 6, 7 (not DY pairs), 9, 10.8, 10.17. Up to 9 YoY points so lines usually withheld (n < 10). Ratio history outside BASIC_HISTORY_KEYS needs Gold. Section 1 P/E and P/B pairs only via provider valuationHistory (Gold); verify its definition first (FY-end vs average price), fallback our own close-at-FY-end / EPS. EV, market cap, DY, FCF-yield history not offered ("no stored year-end enterprise value or price-based yield"). Level-vs-level history shows "trending series correlate even when unrelated".
(c) Section 8 technical: company time series from stored daily closes. Indicators at day k use closes up to k only: RSI14 Wilder via analytics/indicators.rsi; MACD histogram % of price = (EMA12 - EMA26 - EMA9 of that) / close x 100 via indicators.ema; p52h = C_k / max(C_{k-251..k}) x 100. Forward return R = C_{k+h}/C_k - 1, h in {5,20,60} trading days. NON-OVERLAPPING grid: k = N-1-h, N-1-2h, ... back to first defined index (n ~ 340/85/28). No same-day correlations for 8.5, 8.6, 8.10. Volume growth (8.7): non-overlapping 20-day windows, sum vol / sum vol of previous window - 1, vs |return| of the same window. Beta (8.8): ISO-week last closes (market.weekly), last 156 weeks, aligned by week key, needs >= 104 weeks; slope = beta. Phase 2 (NOT now, needs founder OK: +8 MB): universe IC version.

## 3. Statistics (backend advanced/stats.py, pure Python, math.fsum, two-pass)
Inputs: pairs (x_i, y_i), i=1..n after exclusions, sorted by symbol.
- xbar, ybar; Sxx = sum (x-xbar)^2; Syy; Sxy.
- Pearson r = Sxy / sqrt(Sxx Syy), clamped to [-1, 1].
- OLS b = Sxy/Sxx, a = ybar - b xbar, R^2 = r^2. SSE = sum (y_i - a - b x_i)^2, s = sqrt(SSE/(n-2)), SE(b) = s/sqrt(Sxx). t = b/SE(b) = r sqrt((n-2)/(1-r^2)); |r| = 1 -> p = 0, zero-width band.
- p (two-sided) = I_{v/(v+t^2)}(v/2, 1/2), v = n-2: regularised incomplete beta by Lentz continued fraction + math.lgamma. t* = inverse t at 0.975 by bisection on that CDF to 1e-12. Slope 95% CI = b +- t* SE(b).
- 95% confidence band for the mean line at x0: yhat +- t* s sqrt(1/n + (x0-xbar)^2/Sxx); 60 x0 points over [min x, max x]; label "band for the fitted line, not a range for individual companies".
- Fisher CI for r (n >= 10): tanh(atanh r +- 1.959964/sqrt(n-3)).
- Spearman rho = Pearson on average ranks (ties averaged); its p by the same t formula, shown only for n >= 10.
- Theil-Sen = exact median of pairwise slopes with x_j != x_i; intercept = median(y - b x). O(n^2), fine for n <= 1,500, deterministic.
- Influence: h_ii = 1/n + (x_i-xbar)^2/Sxx; Cook's D_i = e_i^2/(2 s^2) * h_ii/(1-h_ii)^2; refit without the max-D point (leave-one-out).
- Curvature: centred x, fit y = c0 + c1 x + c2 x^2 by normal equations; t-test on c2 with n-3 df; dR^2 = R^2_quad - R^2_lin.
DECISION (first failing rule wins; numbers ALWAYS shown):
1. n < 10 -> no line: "too few points (n)".
2. Sxx = 0 or Syy = 0 -> no line: "no spread".
3. p_Pearson >= 0.05 -> no line: "no reliable linear relationship".
4. |r| < 0.30 -> no line: "statistically detectable but too weak to be useful (explains under 9%)".
5. leave-one-out flips sign, or p >= 0.05, or |r| < 0.3; or Theil-Sen sign != OLS sign -> no line: "the line depends on one company: {name}".
6. c2 p < 0.01 and dR^2 >= 0.10 -> no straight line: "the relationship is curved".
7. |b_TS - b_OLS| > 0.25 |b_OLS| -> draw OLS + band AND the Theil-Sen line: "extreme values pull the straight line".
else -> draw OLS + 95% band.
Anscombe expected: I OLS drawn; II curved, no line; III OLS + Theil-Sen (b_TS 0.345556 vs OLS 0.499727); IV depends on one company (without x=19, Sxx = 0).
Scales/outliers: each metric has scale in {lin, log_ok}; strictly positive size amounts default to log; multiples and ICR offer a log toggle. Statistics computed in the displayed (transformed) space; both variants returned; values <=0 left out of the log view and counted. Spearman identical across scales (say so). NO winsorising. Instead: raw statistics with the checks; Spearman and Theil-Sen companions; view domain defaults to the 1st-99th percentile with "k points outside the view" edge markers and a "show all" toggle (statistics always use all included points); optional "leave out the most extreme 1% at each end" toggle (type-7 quantiles on X and Y) applied as an exclusion with names listed. Validity filters (P/E > 0, growth base > 0, NP > 0 for /NP ratios) are exclusions with reason codes, never substitutions.
Caveats always shown: correlation is not causation; information only, not advice; p-values assume independent companies and sector clustering breaks that; ~133 charts means ~5% look significant by chance. Rounding: r and rho 2 decimals; p 3 significant figures or "< 0.001"; slope 3 significant figures as "Y per 1 X".
Reproducibility: every response carries n, excluded {reason: count} (each company counted once, fixed order: no_report -> lender -> x reason -> y reason -> log -> fy_mismatch -> trimmed), universeTotal (invariant universeTotal = n + sum excluded), fyBreakdown, tableBuiltAt, method, the full point list. CSV export reproduces every point used. JSON outputs 6 significant figures.

## 4. API, caching, gating, routes
Router advanced/api.py, prefix /api/advanced (registered in api.py):
- GET /catalog: sections, 162 pairs (id, x, y, verbatim help, status A/C/N, reason, flags M/L, modes, tier), metric definitions (label, unit, formula text, scale, lender rule). Plan-independent; Cache-Control public, max-age=300; ~15 KB gzip.
- POST /cross: body {x, y, universe{sector[], industry[], index[], cap[], mcapMin, mcapMax, lenders, sameFy}, scale{x,y}, trim, highlight[<= plan companies]}. x/y whitelisted against the catalogue (custom pairs too). Data from the in-memory screener Table + new ax columns. Stats cached in a process LRU (256) keyed by (table.loaded, normalised body minus highlights). Payload <= ~1,200 points.
- GET /history?symbols=A,B&x=&y=: per-company FY series by derive.history() from store.get_section (financials, ratios, events, summary), cached adv:h:{sym}:{statement}:{etag} 1 h.
- GET /tech?symbol=&kind=rsi|macd|p52h|volg|beta&h=: reads the Postgres price section once, cached adv:t:{sym}:{etag} 6 h.
- POST /export: CSV with header block (statistics, method, as-of) and rows symbol, name, sector, FY, x, y, included/reason, highlighted; formula-injection guard on text cells.
Storage: no new table. derive.latest() merged into screener/compute.compute(); ax_* floats, ax_fy, ax_div_fy and an ax_miss reason-code map stored in scores.metrics (~1.5-2 KB per company, ~2 MB total). screener/data.Table keeps ax columns.
Gating (server-enforced; private, no-store, Vary: Cookie as screener; fail(403, "plan_required"); company limits from graphviews.GRAPH_LIMITS):
- Basic / visitor: page, catalogue, help, unavailable list; charts LOCKED (matches "scatter = Silver"). [Founder may later choose a taster: P/B-ROE on NIFTY 50, no highlights.]
- Silver: all cross-section charts, history mode for statement-derived metrics and the five basic ratio-history keys, highlight 3 companies, CSV export.
- Gold: plus full ratio history and valuationHistory in history mode, section 8 forward and technical charts, 6 companies.
Routes: /graphs/advanced (redirect to /graphs/advanced/valuation) and /graphs/advanced/:section; slugs valuation, profitability, growth, leverage, cash-flow, liquidity, dividends, market, warnings, sector. Query ?pair=1.9&mode=cross|history&c=SYM1,SYM2&u=<encoded universe>&sx=log (shareable).

## 5. UI (pages/AdvancedCharts.tsx, components/AdvScatter.tsx)
- Section tabs: role="tablist", 10 tabs, arrow keys + Home/End, URL is source of truth; under 600 px a labelled <select> replaces the strip (no sideways scroll).
- Pair picker: the doc rows as "X vs Y" with status chip (Ready / Adapted / Not available) and (?) help reusing the ChartHelp popover behaviour, text = doc's "What it helps analyse" + axis definitions and formulas. "Custom X/Y": two typo-tolerant metric searches (metricSearch.rankMetrics) over the whitelisted metric list.
- Chart: SVG with CSS variables only: points var(--muted) ~35% opacity; highlights var(--k1..k6) with distinct shapes; line var(--text); band var(--gold) ~15% opacity; grid var(--border). Log axes 1-2-5 ticks. Edge markers for off-view points. Highlight labels (legend on phones). Hover/focus tooltip: company, x, y with units (fmtValue). Arrow keys move through highlighted companies then nearest points. aria-label one-line summary. "Show as table" toggle = accessible data view. No looping animation.
- Add-company chips: lib/companySearch.ts ranks the search index (useSearchIndex) with metricSearch.score/distance: exact symbol > symbol prefix > name tokens > fuzzy; "relaince" must find RELIANCE. Shows used/limit ("2/3"), upgrade at the limit, Enter/Escape.
- Stats panel in plain words via pure advSentence(stats), e.g. "Across 812 companies, higher ROE tends to go with higher P/B (Pearson r = 0.46, moderate; Spearman rho = 0.52; p < 0.001). The line explains 21% of the variation; on average +1 point of ROE goes with +0.09x P/B. 61 left out: 38 loss-making (no P/E), 23 no FY26 ROE. Prices as stored at <time>; results FY26 (790) / FY25 (22). Correlation is not causation. Information only, not advice." When no line is drawn, the panel states the rule's reason.
- Also: mechanical-link banner (M); lender note (L); coverage line "N companies with a stored report out of 5,7xx listed, mostly the largest"; "Not available (k)" list per section in <details> with reasons + page-level "What we cannot chart and why"; section 9 P&L flags (plFlags.ts) for selected companies; export CSV (Silver+); link back to Graph Studio and an "Advanced charts" link in the Graph Studio header.
- Phone (390 px): stacked: selects, mode toggle, chart full width (height 300, width from useWidth), stats card, chips, filters in <details>; long labels wrap; never hide bugs with overflow-x hidden.

## 6. Files
Backend new: advanced/__init__.py, catalog.py (metric dictionary, 162 pairs, verbatim help, statuses, reasons, flags, modes, tiers), derive.py (pure: history(sections), latest(sections), reason codes, guards), stats.py, tech.py, table.py (universe filter, exclusion accounting, LRU), api.py.
Backend shared edits (minimal): screener/compute.py merge derive.latest(sections) before final rounding, METRICS_VERSION = 3.0; screener/data.py Table.__init__ collects ax_* keys plus ax_fy, ax_div_fy, ax_miss; screener/jobs.py only_missing also selects COALESCE((metrics->>'m_ver')::float, 0) < METRICS_VERSION; api.py include_router. After deploy run `worker rebuild-metrics` once.
Frontend new: pages/AdvancedCharts.tsx, components/AdvScatter.tsx, lib/advanced.ts (types, react-query calls, URL encode/decode, advSentence, CSV via graphData.csvRow, log ticks, band path), lib/companySearch.ts, styles/advcharts.css.
Frontend shared edits: App.tsx two lazy routes under AppShell; AppShell.tsx Graph Studio end:true + child item {to: "/graphs/advanced", label: "Advanced charts", sub: true} + one .side-i.sub indent rule (styles/account.css); Layout.tsx MENUS Research group right after Graph Studio: ["/graphs/advanced", "Advanced charts", "Correlations with tested regression lines", "spark"]; GraphStudio.tsx header link; e2e/mobile.mjs add the page.

## 7. Tests
- test_advanced_stats.py + tests/fixtures/advanced/stats_reference.json (values verified by two independent pure-Python computations, matching published Anscombe and t-table values):
  Anscombe I: r = 0.816421, b = 0.500091, a = 3.000091, R^2 = 0.666542, t = 4.241455, p = 0.0021696 (df 9), rho = 0.818182, Theil-Sen (0.501667, 2.936667).
  Anscombe II: r = 0.816237, rho = 0.690909, decision = curved.
  Anscombe III: r = 0.816287, b = 0.499727, rho = 0.990909, TS = (0.345556, 4.004444), decision = OLS + Theil-Sen.
  Anscombe IV: r = 0.816521, rho = 0.5 (ties), decision = one company.
  t* (0.975): df 9 = 2.262157, df 30 = 2.042272, df 1000 = 1.962339. Two-sided p: t=2, df=10 -> 0.073388; t=1, df=5 -> 0.363217.
  Edge cases: y = 2x+1 (r = 1, p = 0, zero-width band); constant y; n = 2; heavy ties.
- test_advanced_derive.py (reliance_sections fixture): each g_* and ratio recomputed independently from the raw FinEdge fixture JSON (e.g. revenueFromOperations/1e7 FY26 vs FY25); latest() == last point of history(); lender drops; negative equity; base <= 0; gap; share_change; jump; partial dividend FY; exc_np reconciliation rule.
- test_advanced_catalog.py: parse docs/ADVANCED-CHARTS-SPEC.md tables, assert every pair exists with VERBATIM help text; counts 162 / 133 / 29; every N has a reason; every metric id resolves; no "buy"/"sell" wording.
- test_advanced_api.py (fake store/table as test_screener.py): gating per route and tier; highlight limits = GRAPH_LIMITS; invariant universeTotal = n + sum excluded; lenders absent from D/E charts; light rows counted as no_report; CSV guard.
- test_advanced_tech.py: no look-ahead (indicator at k unchanged when future closes are appended); non-overlapping grid; beta on synthetic y = 1.5 m gives 1.5; split-jump exclusion.
- Integration (@pytest.mark.integration): 5 real companies, recompute their ax values from /api/stocks/{sym}/financials, /ratios, /events JSON, match to 1e-6.
- vitest: companySearch.test.ts (typos, symbol vs name); advanced.test.ts (URL round-trip; advSentence for every decision reason incl. "no reliable linear relationship"; log ticks; band path; CSV injection guard).

## 8. Risks to verify
1. Split/bonus adjustment of stored daily closes (most important): check a known split/bonus in the last 6 years (e.g. RELIANCE 1:1 bonus Oct 2024). Adjusted -> events.adjustedAmount right for TSR; unadjusted -> use unadjusted amount for in-window dividends and rely on the jump/action exclusion.
2. Provider valuationHistory P/E definition (FY-end vs average price): compare with average_price and FY-end close; if unclear use our own close / EPS.
3. Universe bias: only stored reports, ~500-1,200 large companies; disclose on every chart; never say "all listed companies".
4. Definition mismatches labelled in tooltips: EV/EBITDA uses TTM provider EBITDA while EBITDA growth is FY FinLit; FY ROE may differ from the stock page headline (TTM); "Operating margin" means before depreciation; PEG uses profit CAGR.
5. Mechanical pairs (M) and duplicates (2.11 = 2.8, 5.4 = 3.4, 8.3 = 3.8) show their banners.
6. rebuild_metrics(only_missing) version bug: fix it or run a full rebuild; until then ax_* missing for old rows: chart says "being prepared", never zeros.
7. Section 10 sector mapping from real distinct values with tested counts; insurers are not is_bank but D/E and margins are odd for them: flag insurers by industry.
8. Performance: Theil-Sen O(n^2) at n ~ 1,200 ~ 0.7 M slopes: cache per table refresh; derive runs inside refresh_metrics_for on every live price patch: profile it; /tech reads ~150 KB from Postgres per company: cached.
9. Statistical honesty: cross-sectional dependence; multiple comparisons; small n in history mode (lines rarely drawn, correct); overlapping windows avoided by design.
Verifier checklist: (a) export a chart's CSV and recompute r, rho, b, a, p and the band in an independent tool, match to 4 significant figures; (b) hand-check 5 companies' ax_* values against raw stored sections; (c) Anscombe outcomes; (d) exclusion-sum invariant; (e) lenders absent from L charts; (f) gating with Basic, Silver, Gold sessions; (g) help text verbatim; (h) 390 px no sideways scroll, light and dark, keyboard-only, screen reader (tabs, chart summary, table toggle); (i) no invented values, every "—" has a reason; (j) disclaimer and "correlation is not causation" on every chart.
