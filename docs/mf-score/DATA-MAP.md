# Mutual Fund Health Score: data map

Our source for every spec input, its coverage and gaps. Coverage figures are the ones in `docs/MUTUAL-FUND-DATA-REPORT.md` / `docs/NEXT-STEPS-FUNDS.md` (dated, not re-counted here);
the first real `score-mf` run reports exact counts in `/api/mf/status` (`states`, `zeroRules`). The spec's "Mutual Fund Data Report" names map to ours as below.

| Spec input | Our source | Coverage and gaps |
|---|---|---|
| nav, nav_date, active | `mf_schemes.nav, nav_date, active` (AMFI NAVAll) | every scheme |
| Month-end NAVs (mf_monthly) | `mf_monthly.days, navs` (about 63 points, latest NAV last) | active Growth schemes; gap: a scheme with fewer than 12 months is NOT RATED |
| r1y r3y r5y | `mf_schemes.r1y, r3y, r5y` (percent, 3Y and 5Y a year) | schemes old enough; empty when no NAV near the start date |
| sip3y, sip5y | `mf_schemes.sip3y, sip5y` | needs every instalment month; young funds have none (3Y substitutes for 5Y) |
| mdd3y_m | `mf_schemes.mdd3y_m` (0 or negative) | schemes with 36 months; for 12-35 months our own working over the available months |
| aum_lakh | `mf_schemes.aum_lakh` (family total; AMFI quarter, else portfolio net assets) | most schemes; AMFI 0 is stored as 0 (Kind C, filled and counted) |
| ter, terRegular/Direct | `mf_schemes.ter, ter_date` from `mf_ter` | AMFI feed (8,235 of 8,250 in the sandbox; the AWS box could not reach it, five houses fill in); 0 stored as 0 (Kind C); older than 45 days is F |
| launch_date | `mf_facts.launch_date` (AMFI scheme master) | about all; missing or impossible gives AGE from NAV months (S) |
| exit load text | `disclosure_facts` kind `exitload` (AMFI scheme details) | about 74% of schemes; unreadable or missing is F |
| benchmark | `disclosure_facts` kind `benchmark`, else `disclosure_portfolios.benchmark` | 1,047 of 2,043 families; used only for passive tracking families |
| risk-o-meter | `disclosure_facts` kind `risk` (scheme level) | 626 of 2,043 families; unreadable or missing is F, Low is a real level 0 |
| asset split, top-10, sector | latest `disclosure_portfolios` per family (holdings jsonb), summed in `loader.portfolio_summary` | fund houses with a parsed file (1,690 families in the live run); no file is F; zero values are Kind C |
| ETF traded value, premium | `etf_funds.avg_turnover` (rupees, divided by 1e7 for crore), `nav_premium`; volumes of `etf_history` for "traded on the NAV date" | 355 ETFs; premium is null when the ETF did not trade on the NAV date (F) |
| ETF month-end prices | `etf_history.dates, closes` cut at `etf_funds.break_date` | price returns without dividends; ETF returns `ret_1y, cagr_3y, cagr_5y` |
| ETF TER, size, launch, risk, exit load | the AMFI scheme found by ISIN, then its family facts | a gap where the ISIN is not matched |

Not available (never faked): tracking error, index total return, portfolio P/E and P/B, credit ratings, yield and duration, turnover, manager tenure. Not scored in v1 (shown elsewhere only):
1 and 6 month returns, daily volatility, exit load of solution funds, managers, the 5-point checklist.

Zero-value ingest (Appendix Z, Kind C): TER and AUM arrive as 0 where AMFI shows 0; the portfolio summary gives 0 for an empty split. Ingest is unchanged; the model treats these as missing at read time,
counts every hit (`zeroRules`, `fund:<rule>`) and names the cause in the page ("expense ratio reported as 0, treated as missing").

## Upgrade tables (migration 073)

| Table | Written by | Read by | Notes |
|---|---|---|---|
| `mf_score_history` (key, week) | `score-mf` (same transaction as `mf_scores`) | history, compare, calibration, alerts | one row per scheme per ISO week; final, four parts, label, status, rank, percentile; pruned after 3 years |
| `mf_score_alerts` | API (Gold members) | `score-mf` | `band` or `move`; `last_week` keeps it to one message per weekly row |

Screener columns beyond `mf_scores`: AUM (`mf_schemes.aum_lakh` / 100), expense ratio (`mf_schemes.ter`), 1Y/3Y/5Y returns (`mf_schemes.r1y/r3y/r5y`, ETFs: `etf_funds.ret_1y/cagr_3y/cagr_5y`), age (`mf_facts.launch_date`, else months of NAV history).
