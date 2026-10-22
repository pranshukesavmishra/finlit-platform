# Advanced charts: correlation spec (from the founder's document "next_changes", 22-10-2026)

Founder's request (chat, 22 Oct 2026): put these 10 sections of correlation graphs under Graph Studio, as a child item "Advanced charts" in the sidebar/menu.
In all these correlations check whether a regression line can be made, and make a correct one. Users must be able to compare multiple companies on these graphs
by adding company names. The "What it helps analyse" text goes into the (?) help of each chart. Everything must be precise: never a wrong or invented figure.

Document instruction: "In all these correlations check if regression lines can be made".

## 1. Valuation ratio correlations
These help assess how the market values companies relative to their financial performance.

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| P/E ratio | Revenue growth (%) | Valuation relative to sales growth |
| P/E ratio | EPS growth (%) | Valuation relative to earnings growth |
| P/E ratio | ROE (%) | Valuation relative to shareholder profitability |
| P/E ratio | ROCE (%) | Valuation relative to capital efficiency |
| P/E ratio | Operating margin (%) | Valuation relative to operating profitability |
| P/E ratio | Net profit margin (%) | Valuation relative to net profitability |
| P/E ratio | Free cash flow growth (%) | Valuation relative to free cash flow growth |
| P/E ratio | Dividend yield (%) | Earnings valuation versus income yield |
| P/B ratio | ROE (%) | Book valuation relative to shareholder returns |
| P/B ratio | ROA (%) | Book valuation relative to asset profitability |
| P/B ratio | EPS growth (%) | Book valuation relative to earnings growth |
| P/B ratio | Net worth growth (%) | Valuation relative to book-value growth |
| EV/EBITDA | EBITDA growth (%) | Enterprise valuation relative to operating growth |
| EV/EBITDA | EBITDA margin (%) | Valuation relative to operating profitability |
| EV/EBITDA | ROCE (%) | Enterprise valuation relative to capital efficiency |
| EV/EBITDA | Free cash flow yield (%) | Valuation relative to cash generation |
| EV/Sales | Revenue growth (%) | Sales valuation relative to growth |
| EV/Sales | Operating margin (%) | Sales valuation relative to operating profitability |
| EV/CFO | CFO growth (%) | Enterprise value relative to operating cash-flow growth |
| EV/CFO | CFO/PAT | Cash-flow quality relative to valuation |
| PEG ratio | EPS growth (%) | P/E valuation adjusted for earnings growth |
| Market cap | Revenue | Company size relative to business scale |
| Market cap | Net profit | Market valuation relative to earnings |
| Market cap | Operating cash flow | Market valuation relative to cash generation |

Priority checks: P/E vs EPS growth, P/B vs ROE, EV/EBITDA vs EBITDA growth, EV/CFO vs operating cash flow growth, and EV/Sales vs revenue growth.

## 2. Profitability correlations
These identify which factors are associated with stronger profitability and returns.

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| ROE (%) | P/B ratio | Profitability versus book valuation |
| ROE (%) | P/E ratio | Shareholder returns versus earnings valuation |
| ROE (%) | ROA (%) | Returns to shareholders versus returns on assets |
| ROE (%) | ROCE (%) | Equity returns versus capital efficiency |
| ROCE (%) | ROA (%) | Capital efficiency versus asset efficiency |
| ROCE (%) | Operating margin (%) | Capital returns versus operating profitability |
| ROA (%) | Net profit margin (%) | Asset returns versus net profitability |
| Operating margin (%) | Net profit margin (%) | Operating versus bottom-line profitability |
| Gross margin (%) | Operating margin (%) | Gross profitability versus operating cost efficiency |
| EBITDA margin (%) | Operating margin (%) | Operating earnings versus operating profit |
| EBITDA margin (%) | Net profit margin (%) | Operating earnings versus final profitability |
| Revenue growth (%) | Operating margin (%) | Growth versus operating profitability |
| Revenue growth (%) | ROCE (%) | Growth versus capital efficiency |
| Asset turnover | ROA (%) | Asset utilisation versus asset returns |
| Inventory turnover | ROCE (%) | Inventory efficiency versus capital returns |
| Interest coverage ratio | ROE (%) | Ability to cover interest versus shareholder returns |
| Cost-to-income ratio (%) | ROA (%) | Operating cost efficiency versus asset profitability |

## 3. Growth correlations
Use these to assess whether growth in sales, earnings, assets and cash flow moves together.

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Revenue growth (%) | EPS growth (%) | Whether sales growth translates into per-share earnings growth |
| Revenue growth (%) | Net profit growth (%) | Whether sales growth translates into profit growth |
| Revenue growth (%) | EBITDA growth (%) | Sales growth versus operating earnings growth |
| Revenue growth (%) | Operating cash flow growth (%) | Sales growth versus cash generation |
| EBITDA growth (%) | Net profit growth (%) | Operating earnings growth versus net profit growth |
| EBITDA growth (%) | Operating cash flow growth (%) | Earnings growth versus cash generation |
| Net profit growth (%) | EPS growth (%) | Profit growth versus per-share earnings growth |
| EPS growth (%) | Share price return (%) | Earnings growth versus stock performance |
| Revenue growth (%) | Total shareholder return (%) | Sales growth versus shareholder returns |
| Asset growth (%) | Revenue growth (%) | Asset expansion versus sales generation |
| Capital expenditure growth (%) | Revenue growth (%) | Investment expansion versus sales growth |
| Working capital growth (%) | Revenue growth (%) | Working capital requirements relative to sales expansion |
| Order book growth (%) | Revenue growth (%) | Future business pipeline versus realised revenue |
| Book value growth (%) | EPS growth (%) | Balance-sheet growth versus earnings growth |
| R&D expenditure growth (%) | Revenue growth (%) | Research investment versus sales expansion |

## 4. Leverage and debt correlations
Useful for financial risk warnings and identifying companies whose profits may be sensitive to debt.

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Debt-to-equity | ROE (%) | Leverage versus shareholder returns |
| Debt-to-equity | ROCE (%) | Leverage versus capital efficiency |
| Debt-to-equity | Interest coverage ratio | Debt burden versus interest-paying capacity |
| Debt-to-equity | Net profit margin (%) | Leverage versus bottom-line profitability |
| Debt-to-equity | EPS growth (%) | Leverage versus earnings growth |
| Debt-to-equity | Share price volatility | Leverage versus market risk |
| Debt-to-equity | Credit rating or credit-risk score | Leverage versus creditworthiness |
| Debt-to-assets | ROA (%) | Debt funding versus asset returns |
| Net debt/EBITDA | EV/EBITDA | Debt burden versus enterprise valuation |
| Net debt/EBITDA | Free cash flow | Debt burden versus cash available |
| Interest coverage ratio | Debt-to-equity | Interest capacity versus leverage |
| Interest expense growth (%) | EBIT growth (%) | Growth in interest costs versus operating earnings |
| Interest expense growth (%) | Net profit growth (%) | Whether financing costs are eroding profit growth |
| CFO/Total debt | Debt-to-equity | Cash-backed debt repayment capacity |
| Current liabilities/Total liabilities | Current ratio | Short-term versus overall liability structure |

Sector adjustment: Debt-to-equity is less directly comparable across banks and non-financial companies. For banks, prefer capital adequacy, gross NPAs, net NPAs, loan growth and net interest margin.

## 5. Cash flow and earnings quality correlations
Accounting profits do not always translate into cash.

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Net profit | Operating cash flow (CFO) | Whether reported profits are supported by cash |
| CFO | Free cash flow (FCF) | Cash generation after capital expenditure |
| Net profit growth (%) | CFO growth (%) | Profit growth versus cash-flow growth |
| Revenue growth (%) | CFO growth (%) | Sales growth versus cash collection |
| CFO/PAT | Net profit margin (%) | Cash conversion relative to reported profitability |
| CFO/PAT | EPS growth (%) | Cash backing for earnings growth |
| CFO/Total debt | Net debt/EBITDA | Debt repayment capacity versus leverage |
| FCF yield (%) | P/E ratio | Free cash flow yield versus earnings valuation |
| FCF yield (%) | EV/EBITDA | Cash generation versus enterprise valuation |
| Capital expenditure | Revenue growth (%) | Investment spending versus expansion |
| Capital expenditure | CFO | Operating cash generation versus reinvestment |
| Receivables growth (%) | Revenue growth (%) | Whether receivables are growing faster than sales |
| Inventory growth (%) | Revenue growth (%) | Whether inventory is accumulating faster than sales |
| Payables growth (%) | Revenue growth (%) | Supplier financing relative to business expansion |
| Depreciation growth (%) | Capital expenditure growth (%) | Depreciation trends versus asset investment |
| CFO | EBITDA | Cash generation versus operating earnings |
| Accruals ratio | CFO/PAT | Accrual dependence versus cash conversion |

High-priority warning: if revenue and net profit are increasing but CFO is declining, investigate receivables, inventory, working capital and accounting accruals before drawing conclusions.

## 6. Liquidity and working capital correlations

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Current ratio | Quick ratio | Overall liquidity versus liquid-asset coverage |
| Current ratio | Debt-to-equity | Short-term liquidity versus leverage |
| Quick ratio | Interest coverage ratio | Liquid resources versus interest-paying capacity |
| Cash ratio | Current liabilities | Cash available relative to short-term obligations |
| Receivables turnover | Operating margin (%) | Collection efficiency versus profitability |
| Receivables days | Revenue growth (%) | Collection delays versus sales growth |
| Inventory turnover | Gross margin (%) | Inventory efficiency versus gross profitability |
| Inventory days | Revenue growth (%) | Inventory accumulation relative to sales growth |
| Payables days | CFO | Supplier payment timing versus cash generation |
| Cash conversion cycle | CFO | Working capital cycle versus cash generation |
| Cash conversion cycle | ROCE (%) | Working capital efficiency versus capital returns |
| Working capital/Revenue | Operating margin (%) | Working capital intensity versus profitability |
| Current assets/Total assets | ROA (%) | Asset composition versus asset returns |

## 7. Dividend and shareholder-return correlations

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Dividend yield (%) | P/E ratio | Dividend income versus earnings valuation |
| Dividend yield (%) | P/B ratio | Dividend income versus book valuation |
| Dividend payout ratio (%) | EPS growth (%) | Distribution of earnings versus earnings growth |
| Dividend payout ratio (%) | Retained earnings growth (%) | Dividends versus internal capital accumulation |
| Dividend payout ratio (%) | ROE (%) | Earnings distribution versus shareholder profitability |
| Dividend yield (%) | CFO/Share | Dividend income versus cash generation per share |
| Dividend cover | Dividend yield (%) | Dividend sustainability versus yield |
| Dividend growth (%) | EPS growth (%) | Dividend increases versus earnings increases |
| Dividend growth (%) | CFO growth (%) | Dividend increases versus cash-flow growth |
| Share buyback yield (%) | EPS growth (%) | Buybacks versus per-share earnings growth |
| Total shareholder return (%) | EPS growth (%) | Investor returns versus earnings growth |
| Total shareholder return (%) | ROE (%) | Investor returns versus profitability |
| Book value per share growth (%) | Share price return (%) | Growth in underlying book value versus market returns |

## 8. Market price and technical indicator correlations

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| P/E ratio | Share price return (%) | Valuation multiple versus price performance |
| P/B ratio | Share price return (%) | Book valuation versus price performance |
| EPS growth (%) | Share price return (%) | Earnings growth versus stock returns |
| Revenue growth (%) | Share price return (%) | Business growth versus stock returns |
| Relative strength index (RSI) | Next-period return (%) | Momentum indicator versus subsequent returns |
| MACD | Next-period return (%) | Momentum signals versus subsequent returns |
| Trading volume growth (%) | Absolute price return (%) | Trading activity versus price movement |
| Beta | Market return (%) | Market sensitivity and co-movement |
| Historical volatility | Maximum drawdown | Price variability versus downside risk |
| Price-to-52-week-high (%) | Next-period return (%) | Price position versus subsequent performance |
| Delivery volume percentage | Next-period return (%) | Delivery activity versus subsequent performance |
| Institutional ownership change (%) | Share price return (%) | Institutional positioning versus price performance |

For technical indicators, use time-aligned observations and test future returns over defined horizons, such as 5, 20 or 60 trading days. Same-day correlations can be misleading.

## 9. Financial statement warning correlations

| X-axis | Y-axis | What it helps analyse |
|---|---|---|
| Revenue growth (%) | Net profit growth (%) | Whether profit growth substantially exceeds sales growth |
| Revenue growth (%) | EBITDA growth (%) | Whether operating earnings outpace sales |
| EBITDA growth (%) | CFO growth (%) | Whether operating earnings are supported by cash |
| EPS growth (%) | Net profit growth (%) | Whether per-share growth differs from overall profit growth |
| Receivables growth (%) | Revenue growth (%) | Possible collection or revenue-recognition concerns |
| Inventory growth (%) | Revenue growth (%) | Possible inventory accumulation |
| Other income/Net profit (%) | Net profit growth (%) | Dependence on non-core income |
| Exceptional items/Net profit (%) | Net profit growth (%) | Whether reported growth relies on unusual items |
| Interest expense growth (%) | Revenue growth (%) | Whether financing costs outpace business growth |
| Tax expense growth (%) | Profit before tax growth (%) | Unusual changes in the effective tax burden |
| CFO growth (%) | Net profit growth (%) | Divergence between cash and accounting earnings |
| Debt growth (%) | EBITDA growth (%) | Whether debt is rising faster than operating earnings |
| Promoter pledge (%) | Debt-to-equity | Promoter-share pledging versus leverage risk |
| Auditor qualifications or modified opinion | CFO/PAT | Audit concerns alongside weak cash conversion |
| Contingent liabilities/Net worth (%) | Debt-to-equity | Off-balance-sheet exposures versus reported leverage |

Important: the existing rule "profit growth exceeding three times revenue growth" is best implemented as a separate warning rule, not as a correlation test. Growth rates near zero or negative can make that comparison unstable.

## 10. Sector-specific correlations

| Sector | X-axis | Y-axis | What it helps analyse |
|---|---|---|---|
| Banking | Net interest margin (NIM) | ROA (%) | Lending profitability versus asset returns |
| Banking | GNPA (%) | P/B ratio | Asset quality versus book valuation |
| Banking | CASA ratio (%) | NIM (%) | Deposit mix versus lending profitability |
| Banking | Credit growth (%) | Net profit growth (%) | Lending expansion versus profit growth |
| Banking | Capital adequacy ratio (%) | ROE (%) | Capital strength versus shareholder returns |
| Insurance | Embedded value growth (%) | Share price return (%) | Value creation versus stock performance |
| Insurance | Combined ratio (%) | Underwriting profit | Underwriting efficiency versus profit |
| IT services | Revenue growth (%) | EBIT margin (%) | Growth versus operating profitability |
| IT services | Employee growth (%) | Revenue growth (%) | Workforce expansion versus sales growth |
| IT services | Revenue per employee | Operating margin (%) | Workforce productivity versus profitability |
| FMCG | Volume growth (%) | Revenue growth (%) | Underlying demand versus reported sales growth |
| FMCG | Advertising expenditure/Revenue (%) | Revenue growth (%) | Marketing investment versus sales growth |
| Manufacturing | Capacity utilisation (%) | Operating margin (%) | Plant utilisation versus profitability |
| Manufacturing | Raw material cost/Revenue (%) | Operating margin (%) | Input-cost pressure versus margins |
| Automobile | Vehicle sales growth (%) | Revenue growth (%) | Unit sales versus revenue expansion |
| Real estate | Pre-sales growth (%) | Revenue growth (%) | Bookings versus recognised revenue |
| Real estate | Net debt/EBITDA | Interest coverage ratio | Leverage versus debt-servicing capacity |
| Telecom | ARPU growth (%) | Revenue growth (%) | Average customer revenue versus sales growth |
| Pharma | R&D/Revenue (%) | Revenue growth (%) | Research investment versus sales growth |
| Commodities | Commodity price change (%) | Operating margin (%) | Commodity price sensitivity |
| Retail | Same-store sales growth (%) | Operating margin (%) | Existing-store growth versus profitability |
