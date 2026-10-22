"""Advanced charts catalogue: the metric dictionary, the founder's 162 pairs (labels and help text verbatim from
docs/ADVANCED-CHARTS-SPEC.md, checked by tests/test_advanced_catalog.py), what ships, and why the rest cannot.

Metric `col`: where the cross-section value lives in the screener Table: a screener column ("pe") or an advanced column ("ax_g_rev").
`basis`: "today" (price-based, as on the stock page), "fy" (the company's latest financial year), "window" (a price window), "tech".
`lenders`: "ok" (lender-safe: banks and NBFCs included by default) or "excluded" (not meaningful for lenders: always left out).
`history`: plan tier for the per-company history mode ("silver" / "gold"), or None when no yearly history is offered.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional, Tuple

from ..auth.entitlements import BASIC_HISTORY_KEYS
from .stats import DECISION_TEXT


class Metric(NamedTuple):
    id: str
    label: str
    short: str
    unit: str
    basis: str
    formula: str
    col: str
    log_ok: bool = False
    lenders: str = "ok"
    history: Optional[str] = "silver"
    digits: int = 1


_G = "YoY growth, latest financial year against the one before: (this year / last year - 1) x 100. Defined only when both years are reported, last year is above zero and the two period ends are 330-400 days apart."
_HIST_NOTE = "Provider's yearly ratio for the company's latest financial year (not the trailing-12-month headline)."


def _m(id_, label, short, unit, basis, formula, col=None, log_ok=False, lenders="ok", history="silver", digits=1) -> Metric:
    return Metric(id_, label, short, unit, basis, formula, col or f"ax_{id_}", log_ok, lenders, history, digits)


_X = "excluded"
METRIC_LIST: List[Metric] = [
    # ---- today (price-based, as on the stock page and the screener)
    _m("pe", "P/E ratio", "P/E", "x", "today", "Share price / earnings per share over the last 12 months (provider, re-priced to the latest quote). Loss-makers have no P/E.", "pe", True, history="gold"),
    _m("pb", "P/B ratio", "P/B", "x", "today", "Share price / book value per share (provider, re-priced to the latest quote). Zero or negative equity: no P/B.", "pb", True, history="gold", digits=2),
    _m("ev_ebitda", "EV/EBITDA", "EV/EBITDA", "x", "today", "Enterprise value (market cap + borrowings - cash) / EBITDA of the last 12 months (provider EBITDA).", "ev_ebitda", True, _X, None),
    _m("ev_sales", "EV/Sales", "EV/Sales", "x", "today", "Enterprise value / sales of the latest financial year.", "ev_sales", True, _X, None, 2),
    _m("ev_cfo", "EV/CFO", "EV/CFO", "x", "today", "Enterprise value / operating cash flow of the latest financial year (the same year as the other FY figures). CFO zero or negative: not meaningful.", None, True, _X, None),
    _m("peg", "PEG ratio", "PEG", "x", "today", "P/E / 5-year yearly profit growth (%). Uses profit growth, not EPS growth. Defined only when both are above zero.", "peg", True, history=None, digits=2),
    _m("mcap", "Market cap", "Market cap", "Cr", "today", "Share price x shares outstanding, Rs crore.", "market_cap", True, history=None, digits=0),
    _m("dy", "Dividend yield (%)", "Dividend yield", "%", "today", "Dividends with ex-date in the last 12 months / share price x 100 (split and bonus adjusted). 0 for a company that paid nothing.", "dividend_yield", history=None, digits=2),
    _m("fcf_yield", "Free cash flow yield (%)", "FCF yield", "%", "today", "Free cash flow (CFO - capital expenditure) of the latest financial year / today's market cap x 100.", None, False, _X, None),
    _m("cfo_yield", "CFO yield (%)", "CFO yield", "%", "today", "Operating cash flow of the latest financial year / today's market cap x 100.", None, False, _X, None),
    # ---- latest financial year: amounts (Rs crore)
    _m("revenue", "Revenue", "Revenue", "Cr", "fy", "Revenue from operations of the latest financial year, Rs crore (a lender: interest earned plus fees).", log_ok=True, digits=0),
    _m("np", "Net profit", "Net profit", "Cr", "fy", "Net profit attributable to shareholders, continuing operations where a material discontinued profit exists, Rs crore.", log_ok=True, digits=0),
    _m("ebitda", "EBITDA", "EBITDA", "Cr", "fy", "Operating profit before depreciation, interest and other income (FinLit operating profit), Rs crore.", log_ok=True, digits=0),
    _m("cfo", "Operating cash flow (CFO)", "CFO", "Cr", "fy", "Cash from operating activities, Rs crore.", log_ok=True, lenders=_X, digits=0),
    _m("fcf", "Free cash flow (FCF)", "FCF", "Cr", "fy", "Operating cash flow - capital expenditure, Rs crore.", log_ok=True, lenders=_X, digits=0),
    _m("capex", "Capital expenditure", "Capex", "Cr", "fy", "Purchase of property, plant, equipment and intangibles (as a positive amount), Rs crore.", log_ok=True, lenders=_X, digits=0),
    _m("cur_liab", "Current liabilities", "Current liabilities", "Cr", "fy", "Current liabilities from the balance sheet, Rs crore.", log_ok=True, lenders=_X, digits=0),
    # ---- latest financial year: margins and returns
    _m("opm", "Operating margin (%)", "Operating margin", "%", "fy", "FinLit operating profit (before depreciation, interest and other income: this is the EBITDA margin) / revenue x 100 (a lender: / total income)."),
    _m("npm", "Net profit margin (%)", "Net margin", "%", "fy", "Net profit / revenue x 100 (a lender: / total income)."),
    _m("ebit_margin", "EBIT margin (%)", "EBIT margin", "%", "fy", "(Profit before tax + finance costs) / revenue x 100: operating earnings after depreciation.", lenders=_X),
    _m("gross_margin", "Gross margin (%)", "Gross margin", "%", "fy", "Provider's gross margin for the latest financial year (no cost-of-goods line is stored).", lenders=_X),
    _m("roe", "ROE (%)", "ROE", "%", "fy", "Net profit / shareholders' equity x 100. " + _HIST_NOTE),
    _m("roce", "ROCE (%)", "ROCE", "%", "fy", "Return on capital employed. " + _HIST_NOTE),
    _m("roa", "ROA (%)", "ROA", "%", "fy", "Net profit / total assets x 100. " + _HIST_NOTE, history="gold"),
    # ---- leverage, liquidity, efficiency (provider yearly ratios at the latest FY)
    _m("de", "Debt-to-equity", "D/E", "x", "fy", "Total debt / shareholders' equity. " + _HIST_NOTE, log_ok=True, lenders=_X, history="gold", digits=2),
    _m("debt_assets", "Debt-to-assets", "Debt/assets", "x", "fy", "Total debt / total assets. " + _HIST_NOTE, lenders=_X, history="gold", digits=2),
    _m("icr", "Interest coverage ratio", "Interest cover", "x", "fy", "Operating earnings / interest cost. " + _HIST_NOTE, log_ok=True, lenders=_X, history="gold"),
    _m("current_ratio", "Current ratio", "Current ratio", "ratio", "fy", "Current assets / current liabilities. " + _HIST_NOTE, log_ok=True, lenders=_X, history="gold", digits=2),
    _m("quick_ratio", "Quick ratio", "Quick ratio", "ratio", "fy", "Current assets less inventories / current liabilities. " + _HIST_NOTE, log_ok=True, lenders=_X, history="gold", digits=2),
    _m("asset_turnover", "Asset turnover", "Asset turnover", "x", "fy", "Revenue / total assets. " + _HIST_NOTE, lenders=_X, history="gold", digits=2),
    _m("inv_days", "Inventory days", "Inventory days", "d", "fy", "Days of sales held as inventory. " + _HIST_NOTE, lenders=_X, history="gold", digits=0),
    _m("debtor_days", "Receivables days", "Receivables days", "d", "fy", "Days customers take to pay. " + _HIST_NOTE, lenders=_X, history="gold", digits=0),
    _m("payable_days", "Payables days", "Payables days", "d", "fy", "Days taken to pay suppliers. " + _HIST_NOTE, lenders=_X, history="gold", digits=0),
    _m("ccc", "Cash conversion cycle", "Cash cycle", "d", "fy", "Inventory days + receivables days - payables days. " + _HIST_NOTE, lenders=_X, history="gold", digits=0),
    _m("inv_turnover", "Inventory turnover", "Inventory turnover", "x", "fy", "365 / the provider's inventory days (inventory days above zero).", log_ok=True, lenders=_X, history="gold"),
    _m("recv_turnover", "Receivables turnover", "Receivables turnover", "x", "fy", "365 / the provider's receivables days (receivables days above zero).", log_ok=True, lenders=_X, history="gold"),
    _m("cash_ratio", "Cash ratio", "Cash ratio", "ratio", "fy", "Cash and cash equivalents / current liabilities.", log_ok=True, lenders=_X, digits=2),
    _m("nd_ebitda", "Net debt/EBITDA", "Net debt/EBITDA", "x", "fy", "(Borrowings - cash) / EBITDA, only when EBITDA is above zero. Negative means more cash than debt.", lenders=_X, digits=2),
    _m("cfo_debt", "CFO/Total debt", "CFO/debt", "x", "fy", "Operating cash flow / borrowings, only when there are borrowings.", lenders=_X, digits=2),
    _m("cl_tl", "Current liabilities/Total liabilities", "CL/TL", "%", "fy", "Current liabilities / total liabilities x 100.", lenders=_X),
    _m("wc_rev", "Working capital/Revenue", "WC/Revenue", "%", "fy", "(Current assets - current liabilities) / revenue x 100.", lenders=_X),
    _m("ca_ta", "Current assets/Total assets", "CA/TA", "%", "fy", "Current assets / total assets x 100.", lenders=_X),
    _m("cfo_pat", "CFO/PAT", "CFO/PAT", "%", "fy", "Operating cash flow / net profit x 100, only when net profit is above zero.", lenders=_X, digits=0),
    _m("accruals", "Accruals ratio", "Accruals", "%", "fy", "(Net profit - operating cash flow) / average total assets of this and last year x 100.", lenders=_X),
    _m("oi_np", "Other income/Net profit (%)", "Other income/NP", "%", "fy", "Other income / net profit x 100, only when net profit is above zero."),
    _m("exc_np", "Exceptional items/Net profit (%)", "Exceptional/NP", "%", "fy", "Exceptional items / net profit x 100, only when net profit is above zero. With no exceptional line the value is 0 only if the P&L reconciles to profit before tax without one."),
    _m("payout", "Dividend payout ratio (%)", "Payout", "%", "fy", "Dividend per share declared for the year / EPS of the same year x 100 (split and bonus adjusted)."),
    _m("div_cover", "Dividend cover", "Dividend cover", "x", "fy", "EPS / dividend per share for the same year (payers only).", log_ok=True, digits=2),
    _m("cfo_ps", "CFO/Share", "CFO/share", "Rs", "fy", "Operating cash flow / diluted shares, rupees per share.", lenders=_X, digits=2),
    _m("eps", "EPS", "EPS", "Rs", "fy", "Earnings per share (continuing operations where relevant).", digits=2),
    _m("bvps", "Book value per share", "BVPS", "Rs", "fy", "Shareholders' equity / diluted shares, rupees per share.", digits=2),
    # ---- growth (YoY, latest FY)
    _m("g_rev", "Revenue growth (%)", "Revenue growth", "%", "fy", _G),
    _m("g_np", "Net profit growth (%)", "Profit growth", "%", "fy", _G + " Net profit on continuing operations where relevant."),
    _m("g_eps", "EPS growth (%)", "EPS growth", "%", "fy", _G + " Left out when the share count changed by more than 25% (or by more than 5% with a bonus or split)."),
    _m("g_ebitda", "EBITDA growth (%)", "EBITDA growth", "%", "fy", _G + " EBITDA = FinLit operating profit."),
    _m("g_ebit", "EBIT growth (%)", "EBIT growth", "%", "fy", _G + " EBIT = profit before tax + finance costs.", lenders=_X),
    _m("g_pbt", "Profit before tax growth (%)", "PBT growth", "%", "fy", _G),
    _m("g_tax", "Tax expense growth (%)", "Tax growth", "%", "fy", _G + " A tax credit in the earlier year means no growth figure."),
    _m("g_cfo", "CFO growth (%)", "CFO growth", "%", "fy", _G, lenders=_X),
    _m("g_fcf", "Free cash flow growth (%)", "FCF growth", "%", "fy", _G, lenders=_X),
    _m("g_capex", "Capital expenditure growth (%)", "Capex growth", "%", "fy", _G, lenders=_X),
    _m("g_assets", "Asset growth (%)", "Asset growth", "%", "fy", _G + " Total assets."),
    _m("g_bv", "Book value growth (%)", "Book value growth", "%", "fy", _G + " Shareholders' equity (net worth)."),
    _m("g_bvps", "Book value per share growth (%)", "BVPS growth", "%", "fy", _G + " Left out when the share count changed by more than 25% (or by more than 5% with a bonus or split)."),
    _m("g_wc", "Working capital growth (%)", "WC growth", "%", "fy", _G + " Working capital = current assets - current liabilities.", lenders=_X),
    _m("g_recv", "Receivables growth (%)", "Receivables growth", "%", "fy", _G + " Trade receivables.", lenders=_X),
    _m("g_inv", "Inventory growth (%)", "Inventory growth", "%", "fy", _G, lenders=_X),
    _m("g_dep", "Depreciation growth (%)", "Depreciation growth", "%", "fy", _G, lenders=_X),
    _m("g_int", "Interest expense growth (%)", "Interest growth", "%", "fy", _G + " Finance costs.", lenders=_X),
    _m("g_debt", "Debt growth (%)", "Debt growth", "%", "fy", _G + " Borrowings.", lenders=_X),
    _m("g_dps", "Dividend growth (%)", "Dividend growth", "%", "fy", "Dividend per share declared for the latest financial year against the year before (split and bonus adjusted). Both years must be complete."),
    # ---- price windows
    _m("ret_fy", "Share price return (%)", "Price return", "%", "window", "Close on the financial-year end / close on the previous financial-year end - 1, x 100 (last close on or before each date, within 7 days). Same year as the results."),
    _m("tsr_fy", "Total shareholder return (%)", "TSR", "%", "window", "Price return over the financial year plus dividends with ex-date inside it, as a % of the starting close."),
    _m("pe_fy", "P/E ratio (at the financial-year end)", "P/E (FY end)", "x", "window", "Close on the financial-year end / EPS of that year (EPS above zero).", log_ok=True, history=None),
    _m("pb_fy", "P/B ratio (at the financial-year end)", "P/B (FY end)", "x", "window", "Close on the financial-year end / book value per share of that year (equity above zero).", log_ok=True, history=None, digits=2),
    _m("vol3y", "Share price volatility", "Volatility", "%", "window", "Standard deviation of daily log returns over the last 756 sessions x sqrt(252) x 100 (needs at least 700 sessions).", history=None),
    _m("mdd3y", "Maximum drawdown", "Max drawdown", "%", "window", "Largest fall from a peak to a later low of the daily close over the last 756 sessions, in % (negative).", history=None),
    _m("inst_chg", "Institutional ownership change (%)", "Institutional change", "pts", "window", "Change in foreign + domestic institutional holding over the last year, in percentage points (latest shareholding quarter against the same quarter a year earlier).", "ax_inst_chg", history=None, digits=2),
    _m("ret_inst", "Share price return (%)", "Price return", "%", "window", "Price return between the same two shareholding quarter-ends.", history=None),
    _m("pe_sig", "P/E ratio (75 days after the year end)", "P/E (signal)", "x", "window", "Close 75 days after the financial-year end (past the 60-day results deadline) / EPS of that year. Latest year whose next 12 months are complete.", log_ok=True, history=None),
    _m("pb_sig", "P/B ratio (75 days after the year end)", "P/B (signal)", "x", "window", "Close 75 days after the financial-year end / book value per share of that year.", log_ok=True, history=None, digits=2),
    _m("g_eps_sig", "EPS growth (%) (signal year)", "EPS growth", "%", "window", "EPS growth of the financial year used for the signal.", history=None),
    _m("g_rev_sig", "Revenue growth (%) (signal year)", "Revenue growth", "%", "window", "Revenue growth of the financial year used for the signal.", history=None),
    _m("fwd12", "Share price return over the next 12 months (%)", "Next-12-month return", "%", "window", "Close 12 calendar months after the signal date / close on the signal date - 1, x 100. No look-ahead: the signal uses only results published by then.", history=None),
    _m("sales_per_employee", "Revenue per employee", "Revenue/employee", "Cr", "fy", "Latest-year revenue / headcount from the company profile (the headcount date is not known), Rs crore.", "sales_per_employee", True, history=None, digits=2),
    # ---- technical (company mode, /tech)
    _m("rsi", "RSI (14 days, Wilder)", "RSI", "pts", "tech", "Wilder's 14-day relative strength index on daily closes up to the signal day.", "", history=None, digits=0),
    _m("macd_pct", "MACD histogram (% of price)", "MACD", "%", "tech", "(EMA12 - EMA26 - EMA9 of that difference) / close x 100, on closes up to the signal day.", "", history=None, digits=2),
    _m("p52h", "Price-to-52-week-high (%)", "Price/52w high", "%", "tech", "Close / highest close of the last 252 sessions x 100.", "", history=None),
    _m("volg", "Trading volume growth (%)", "Volume growth", "%", "tech", "Total volume of a 20-session window / total volume of the previous 20 sessions - 1, x 100.", "", history=None),
    _m("abs_ret", "Absolute price return (%)", "Absolute return", "%", "tech", "Absolute price change over the same 20-session window, in %.", "", history=None),
    _m("fwd_ret", "Next-period return (%)", "Next-period return", "%", "tech", "Close h trading days after the signal day / close on the signal day - 1, x 100 (h = 5, 20 or 60).", "", history=None),
    _m("mkt_ret", "Market return (%)", "NIFTY 50 weekly return", "%", "tech", "NIFTY 50 weekly return (last close of each ISO week).", "", history=None),
    _m("stock_ret", "Stock weekly return (%)", "Stock weekly return", "%", "tech", "The company's weekly return (last close of each ISO week).", "", history=None),
]
METRICS: Dict[str, Metric] = {m.id: m for m in METRIC_LIST}
TECH_IDS = {m.id for m in METRIC_LIST if m.basis == "tech"}
# Provider yearly ratios read at the company's latest FY from ratios.history (metric id -> history row key)
HIST_KEYS = {"gross_margin": "gross_margin", "roe": "roe", "roce": "roce", "roa": "roa", "de": "debt_to_equity", "debt_assets": "debt_to_assets",
             "icr": "interest_coverage", "current_ratio": "current_ratio", "quick_ratio": "quick_ratio", "asset_turnover": "asset_turnover",
             "inv_days": "inventory_days", "debtor_days": "debtor_days", "payable_days": "payable_days", "ccc": "cash_conversion_cycle"}
assert all((METRICS[k].history == "silver") == (v in BASIC_HISTORY_KEYS) for k, v in HIST_KEYS.items())
FY_IDS = [m.id for m in METRIC_LIST if m.basis == "fy" and m.col.startswith("ax_")]
WINDOW_IDS = [m.id for m in METRIC_LIST if m.basis == "window"]
LENDER_DROP = {m.id for m in METRIC_LIST if m.lenders == _X}

SECTIONS: List[dict] = [
    {"id": 1, "slug": "valuation", "title": "Valuation ratio correlations",
     "intro": "These help assess how the market values companies relative to their financial performance.",
     "note": "Priority checks: P/E vs EPS growth, P/B vs ROE, EV/EBITDA vs EBITDA growth, EV/CFO vs operating cash flow growth, and EV/Sales vs revenue growth."},
    {"id": 2, "slug": "profitability", "title": "Profitability correlations",
     "intro": "These identify which factors are associated with stronger profitability and returns.", "note": None},
    {"id": 3, "slug": "growth", "title": "Growth correlations",
     "intro": "Use these to assess whether growth in sales, earnings, assets and cash flow moves together.", "note": None},
    {"id": 4, "slug": "leverage", "title": "Leverage and debt correlations",
     "intro": "Useful for financial risk warnings and identifying companies whose profits may be sensitive to debt.",
     "note": "Sector adjustment: Debt-to-equity is less directly comparable across banks and non-financial companies. For banks, prefer capital adequacy, gross NPAs, net NPAs, loan growth and net interest margin."},
    {"id": 5, "slug": "cash-flow", "title": "Cash flow and earnings quality correlations",
     "intro": "Accounting profits do not always translate into cash.",
     "note": "High-priority warning: if revenue and net profit are increasing but CFO is declining, investigate receivables, inventory, working capital and accounting accruals before drawing conclusions."},
    {"id": 6, "slug": "liquidity", "title": "Liquidity and working capital correlations", "intro": None, "note": None},
    {"id": 7, "slug": "dividends", "title": "Dividend and shareholder-return correlations", "intro": None, "note": None},
    {"id": 8, "slug": "market", "title": "Market price and technical indicator correlations", "intro": None,
     "note": "For technical indicators, use time-aligned observations and test future returns over defined horizons, such as 5, 20 or 60 trading days. Same-day correlations can be misleading."},
    {"id": 9, "slug": "warnings", "title": "Financial statement warning correlations", "intro": None,
     "note": "Important: the existing rule \"profit growth exceeding three times revenue growth\" is best implemented as a separate warning rule, not as a correlation test. Growth rates near zero or negative can make that comparison unstable."},
    {"id": 10, "slug": "sector", "title": "Sector-specific correlations", "intro": None, "note": None},
]

# (id, xLabel, yLabel, help) verbatim; section 10 rows carry the sector first.
ROWS: List[Tuple[str, ...]] = [
    ('1.1', 'P/E ratio', 'Revenue growth (%)', 'Valuation relative to sales growth'),
    ('1.2', 'P/E ratio', 'EPS growth (%)', 'Valuation relative to earnings growth'),
    ('1.3', 'P/E ratio', 'ROE (%)', 'Valuation relative to shareholder profitability'),
    ('1.4', 'P/E ratio', 'ROCE (%)', 'Valuation relative to capital efficiency'),
    ('1.5', 'P/E ratio', 'Operating margin (%)', 'Valuation relative to operating profitability'),
    ('1.6', 'P/E ratio', 'Net profit margin (%)', 'Valuation relative to net profitability'),
    ('1.7', 'P/E ratio', 'Free cash flow growth (%)', 'Valuation relative to free cash flow growth'),
    ('1.8', 'P/E ratio', 'Dividend yield (%)', 'Earnings valuation versus income yield'),
    ('1.9', 'P/B ratio', 'ROE (%)', 'Book valuation relative to shareholder returns'),
    ('1.10', 'P/B ratio', 'ROA (%)', 'Book valuation relative to asset profitability'),
    ('1.11', 'P/B ratio', 'EPS growth (%)', 'Book valuation relative to earnings growth'),
    ('1.12', 'P/B ratio', 'Net worth growth (%)', 'Valuation relative to book-value growth'),
    ('1.13', 'EV/EBITDA', 'EBITDA growth (%)', 'Enterprise valuation relative to operating growth'),
    ('1.14', 'EV/EBITDA', 'EBITDA margin (%)', 'Valuation relative to operating profitability'),
    ('1.15', 'EV/EBITDA', 'ROCE (%)', 'Enterprise valuation relative to capital efficiency'),
    ('1.16', 'EV/EBITDA', 'Free cash flow yield (%)', 'Valuation relative to cash generation'),
    ('1.17', 'EV/Sales', 'Revenue growth (%)', 'Sales valuation relative to growth'),
    ('1.18', 'EV/Sales', 'Operating margin (%)', 'Sales valuation relative to operating profitability'),
    ('1.19', 'EV/CFO', 'CFO growth (%)', 'Enterprise value relative to operating cash-flow growth'),
    ('1.20', 'EV/CFO', 'CFO/PAT', 'Cash-flow quality relative to valuation'),
    ('1.21', 'PEG ratio', 'EPS growth (%)', 'P/E valuation adjusted for earnings growth'),
    ('1.22', 'Market cap', 'Revenue', 'Company size relative to business scale'),
    ('1.23', 'Market cap', 'Net profit', 'Market valuation relative to earnings'),
    ('1.24', 'Market cap', 'Operating cash flow', 'Market valuation relative to cash generation'),
    ('2.1', 'ROE (%)', 'P/B ratio', 'Profitability versus book valuation'),
    ('2.2', 'ROE (%)', 'P/E ratio', 'Shareholder returns versus earnings valuation'),
    ('2.3', 'ROE (%)', 'ROA (%)', 'Returns to shareholders versus returns on assets'),
    ('2.4', 'ROE (%)', 'ROCE (%)', 'Equity returns versus capital efficiency'),
    ('2.5', 'ROCE (%)', 'ROA (%)', 'Capital efficiency versus asset efficiency'),
    ('2.6', 'ROCE (%)', 'Operating margin (%)', 'Capital returns versus operating profitability'),
    ('2.7', 'ROA (%)', 'Net profit margin (%)', 'Asset returns versus net profitability'),
    ('2.8', 'Operating margin (%)', 'Net profit margin (%)', 'Operating versus bottom-line profitability'),
    ('2.9', 'Gross margin (%)', 'Operating margin (%)', 'Gross profitability versus operating cost efficiency'),
    ('2.10', 'EBITDA margin (%)', 'Operating margin (%)', 'Operating earnings versus operating profit'),
    ('2.11', 'EBITDA margin (%)', 'Net profit margin (%)', 'Operating earnings versus final profitability'),
    ('2.12', 'Revenue growth (%)', 'Operating margin (%)', 'Growth versus operating profitability'),
    ('2.13', 'Revenue growth (%)', 'ROCE (%)', 'Growth versus capital efficiency'),
    ('2.14', 'Asset turnover', 'ROA (%)', 'Asset utilisation versus asset returns'),
    ('2.15', 'Inventory turnover', 'ROCE (%)', 'Inventory efficiency versus capital returns'),
    ('2.16', 'Interest coverage ratio', 'ROE (%)', 'Ability to cover interest versus shareholder returns'),
    ('2.17', 'Cost-to-income ratio (%)', 'ROA (%)', 'Operating cost efficiency versus asset profitability'),
    ('3.1', 'Revenue growth (%)', 'EPS growth (%)', 'Whether sales growth translates into per-share earnings growth'),
    ('3.2', 'Revenue growth (%)', 'Net profit growth (%)', 'Whether sales growth translates into profit growth'),
    ('3.3', 'Revenue growth (%)', 'EBITDA growth (%)', 'Sales growth versus operating earnings growth'),
    ('3.4', 'Revenue growth (%)', 'Operating cash flow growth (%)', 'Sales growth versus cash generation'),
    ('3.5', 'EBITDA growth (%)', 'Net profit growth (%)', 'Operating earnings growth versus net profit growth'),
    ('3.6', 'EBITDA growth (%)', 'Operating cash flow growth (%)', 'Earnings growth versus cash generation'),
    ('3.7', 'Net profit growth (%)', 'EPS growth (%)', 'Profit growth versus per-share earnings growth'),
    ('3.8', 'EPS growth (%)', 'Share price return (%)', 'Earnings growth versus stock performance'),
    ('3.9', 'Revenue growth (%)', 'Total shareholder return (%)', 'Sales growth versus shareholder returns'),
    ('3.10', 'Asset growth (%)', 'Revenue growth (%)', 'Asset expansion versus sales generation'),
    ('3.11', 'Capital expenditure growth (%)', 'Revenue growth (%)', 'Investment expansion versus sales growth'),
    ('3.12', 'Working capital growth (%)', 'Revenue growth (%)', 'Working capital requirements relative to sales expansion'),
    ('3.13', 'Order book growth (%)', 'Revenue growth (%)', 'Future business pipeline versus realised revenue'),
    ('3.14', 'Book value growth (%)', 'EPS growth (%)', 'Balance-sheet growth versus earnings growth'),
    ('3.15', 'R&D expenditure growth (%)', 'Revenue growth (%)', 'Research investment versus sales expansion'),
    ('4.1', 'Debt-to-equity', 'ROE (%)', 'Leverage versus shareholder returns'),
    ('4.2', 'Debt-to-equity', 'ROCE (%)', 'Leverage versus capital efficiency'),
    ('4.3', 'Debt-to-equity', 'Interest coverage ratio', 'Debt burden versus interest-paying capacity'),
    ('4.4', 'Debt-to-equity', 'Net profit margin (%)', 'Leverage versus bottom-line profitability'),
    ('4.5', 'Debt-to-equity', 'EPS growth (%)', 'Leverage versus earnings growth'),
    ('4.6', 'Debt-to-equity', 'Share price volatility', 'Leverage versus market risk'),
    ('4.7', 'Debt-to-equity', 'Credit rating or credit-risk score', 'Leverage versus creditworthiness'),
    ('4.8', 'Debt-to-assets', 'ROA (%)', 'Debt funding versus asset returns'),
    ('4.9', 'Net debt/EBITDA', 'EV/EBITDA', 'Debt burden versus enterprise valuation'),
    ('4.10', 'Net debt/EBITDA', 'Free cash flow', 'Debt burden versus cash available'),
    ('4.11', 'Interest coverage ratio', 'Debt-to-equity', 'Interest capacity versus leverage'),
    ('4.12', 'Interest expense growth (%)', 'EBIT growth (%)', 'Growth in interest costs versus operating earnings'),
    ('4.13', 'Interest expense growth (%)', 'Net profit growth (%)', 'Whether financing costs are eroding profit growth'),
    ('4.14', 'CFO/Total debt', 'Debt-to-equity', 'Cash-backed debt repayment capacity'),
    ('4.15', 'Current liabilities/Total liabilities', 'Current ratio', 'Short-term versus overall liability structure'),
    ('5.1', 'Net profit', 'Operating cash flow (CFO)', 'Whether reported profits are supported by cash'),
    ('5.2', 'CFO', 'Free cash flow (FCF)', 'Cash generation after capital expenditure'),
    ('5.3', 'Net profit growth (%)', 'CFO growth (%)', 'Profit growth versus cash-flow growth'),
    ('5.4', 'Revenue growth (%)', 'CFO growth (%)', 'Sales growth versus cash collection'),
    ('5.5', 'CFO/PAT', 'Net profit margin (%)', 'Cash conversion relative to reported profitability'),
    ('5.6', 'CFO/PAT', 'EPS growth (%)', 'Cash backing for earnings growth'),
    ('5.7', 'CFO/Total debt', 'Net debt/EBITDA', 'Debt repayment capacity versus leverage'),
    ('5.8', 'FCF yield (%)', 'P/E ratio', 'Free cash flow yield versus earnings valuation'),
    ('5.9', 'FCF yield (%)', 'EV/EBITDA', 'Cash generation versus enterprise valuation'),
    ('5.10', 'Capital expenditure', 'Revenue growth (%)', 'Investment spending versus expansion'),
    ('5.11', 'Capital expenditure', 'CFO', 'Operating cash generation versus reinvestment'),
    ('5.12', 'Receivables growth (%)', 'Revenue growth (%)', 'Whether receivables are growing faster than sales'),
    ('5.13', 'Inventory growth (%)', 'Revenue growth (%)', 'Whether inventory is accumulating faster than sales'),
    ('5.14', 'Payables growth (%)', 'Revenue growth (%)', 'Supplier financing relative to business expansion'),
    ('5.15', 'Depreciation growth (%)', 'Capital expenditure growth (%)', 'Depreciation trends versus asset investment'),
    ('5.16', 'CFO', 'EBITDA', 'Cash generation versus operating earnings'),
    ('5.17', 'Accruals ratio', 'CFO/PAT', 'Accrual dependence versus cash conversion'),
    ('6.1', 'Current ratio', 'Quick ratio', 'Overall liquidity versus liquid-asset coverage'),
    ('6.2', 'Current ratio', 'Debt-to-equity', 'Short-term liquidity versus leverage'),
    ('6.3', 'Quick ratio', 'Interest coverage ratio', 'Liquid resources versus interest-paying capacity'),
    ('6.4', 'Cash ratio', 'Current liabilities', 'Cash available relative to short-term obligations'),
    ('6.5', 'Receivables turnover', 'Operating margin (%)', 'Collection efficiency versus profitability'),
    ('6.6', 'Receivables days', 'Revenue growth (%)', 'Collection delays versus sales growth'),
    ('6.7', 'Inventory turnover', 'Gross margin (%)', 'Inventory efficiency versus gross profitability'),
    ('6.8', 'Inventory days', 'Revenue growth (%)', 'Inventory accumulation relative to sales growth'),
    ('6.9', 'Payables days', 'CFO', 'Supplier payment timing versus cash generation'),
    ('6.10', 'Cash conversion cycle', 'CFO', 'Working capital cycle versus cash generation'),
    ('6.11', 'Cash conversion cycle', 'ROCE (%)', 'Working capital efficiency versus capital returns'),
    ('6.12', 'Working capital/Revenue', 'Operating margin (%)', 'Working capital intensity versus profitability'),
    ('6.13', 'Current assets/Total assets', 'ROA (%)', 'Asset composition versus asset returns'),
    ('7.1', 'Dividend yield (%)', 'P/E ratio', 'Dividend income versus earnings valuation'),
    ('7.2', 'Dividend yield (%)', 'P/B ratio', 'Dividend income versus book valuation'),
    ('7.3', 'Dividend payout ratio (%)', 'EPS growth (%)', 'Distribution of earnings versus earnings growth'),
    ('7.4', 'Dividend payout ratio (%)', 'Retained earnings growth (%)', 'Dividends versus internal capital accumulation'),
    ('7.5', 'Dividend payout ratio (%)', 'ROE (%)', 'Earnings distribution versus shareholder profitability'),
    ('7.6', 'Dividend yield (%)', 'CFO/Share', 'Dividend income versus cash generation per share'),
    ('7.7', 'Dividend cover', 'Dividend yield (%)', 'Dividend sustainability versus yield'),
    ('7.8', 'Dividend growth (%)', 'EPS growth (%)', 'Dividend increases versus earnings increases'),
    ('7.9', 'Dividend growth (%)', 'CFO growth (%)', 'Dividend increases versus cash-flow growth'),
    ('7.10', 'Share buyback yield (%)', 'EPS growth (%)', 'Buybacks versus per-share earnings growth'),
    ('7.11', 'Total shareholder return (%)', 'EPS growth (%)', 'Investor returns versus earnings growth'),
    ('7.12', 'Total shareholder return (%)', 'ROE (%)', 'Investor returns versus profitability'),
    ('7.13', 'Book value per share growth (%)', 'Share price return (%)', 'Growth in underlying book value versus market returns'),
    ('8.1', 'P/E ratio', 'Share price return (%)', 'Valuation multiple versus price performance'),
    ('8.2', 'P/B ratio', 'Share price return (%)', 'Book valuation versus price performance'),
    ('8.3', 'EPS growth (%)', 'Share price return (%)', 'Earnings growth versus stock returns'),
    ('8.4', 'Revenue growth (%)', 'Share price return (%)', 'Business growth versus stock returns'),
    ('8.5', 'Relative strength index (RSI)', 'Next-period return (%)', 'Momentum indicator versus subsequent returns'),
    ('8.6', 'MACD', 'Next-period return (%)', 'Momentum signals versus subsequent returns'),
    ('8.7', 'Trading volume growth (%)', 'Absolute price return (%)', 'Trading activity versus price movement'),
    ('8.8', 'Beta', 'Market return (%)', 'Market sensitivity and co-movement'),
    ('8.9', 'Historical volatility', 'Maximum drawdown', 'Price variability versus downside risk'),
    ('8.10', 'Price-to-52-week-high (%)', 'Next-period return (%)', 'Price position versus subsequent performance'),
    ('8.11', 'Delivery volume percentage', 'Next-period return (%)', 'Delivery activity versus subsequent performance'),
    ('8.12', 'Institutional ownership change (%)', 'Share price return (%)', 'Institutional positioning versus price performance'),
    ('9.1', 'Revenue growth (%)', 'Net profit growth (%)', 'Whether profit growth substantially exceeds sales growth'),
    ('9.2', 'Revenue growth (%)', 'EBITDA growth (%)', 'Whether operating earnings outpace sales'),
    ('9.3', 'EBITDA growth (%)', 'CFO growth (%)', 'Whether operating earnings are supported by cash'),
    ('9.4', 'EPS growth (%)', 'Net profit growth (%)', 'Whether per-share growth differs from overall profit growth'),
    ('9.5', 'Receivables growth (%)', 'Revenue growth (%)', 'Possible collection or revenue-recognition concerns'),
    ('9.6', 'Inventory growth (%)', 'Revenue growth (%)', 'Possible inventory accumulation'),
    ('9.7', 'Other income/Net profit (%)', 'Net profit growth (%)', 'Dependence on non-core income'),
    ('9.8', 'Exceptional items/Net profit (%)', 'Net profit growth (%)', 'Whether reported growth relies on unusual items'),
    ('9.9', 'Interest expense growth (%)', 'Revenue growth (%)', 'Whether financing costs outpace business growth'),
    ('9.10', 'Tax expense growth (%)', 'Profit before tax growth (%)', 'Unusual changes in the effective tax burden'),
    ('9.11', 'CFO growth (%)', 'Net profit growth (%)', 'Divergence between cash and accounting earnings'),
    ('9.12', 'Debt growth (%)', 'EBITDA growth (%)', 'Whether debt is rising faster than operating earnings'),
    ('9.13', 'Promoter pledge (%)', 'Debt-to-equity', 'Promoter-share pledging versus leverage risk'),
    ('9.14', 'Auditor qualifications or modified opinion', 'CFO/PAT', 'Audit concerns alongside weak cash conversion'),
    ('9.15', 'Contingent liabilities/Net worth (%)', 'Debt-to-equity', 'Off-balance-sheet exposures versus reported leverage'),
    ('10.1', 'Banking', 'Net interest margin (NIM)', 'ROA (%)', 'Lending profitability versus asset returns'),
    ('10.2', 'Banking', 'GNPA (%)', 'P/B ratio', 'Asset quality versus book valuation'),
    ('10.3', 'Banking', 'CASA ratio (%)', 'NIM (%)', 'Deposit mix versus lending profitability'),
    ('10.4', 'Banking', 'Credit growth (%)', 'Net profit growth (%)', 'Lending expansion versus profit growth'),
    ('10.5', 'Banking', 'Capital adequacy ratio (%)', 'ROE (%)', 'Capital strength versus shareholder returns'),
    ('10.6', 'Insurance', 'Embedded value growth (%)', 'Share price return (%)', 'Value creation versus stock performance'),
    ('10.7', 'Insurance', 'Combined ratio (%)', 'Underwriting profit', 'Underwriting efficiency versus profit'),
    ('10.8', 'IT services', 'Revenue growth (%)', 'EBIT margin (%)', 'Growth versus operating profitability'),
    ('10.9', 'IT services', 'Employee growth (%)', 'Revenue growth (%)', 'Workforce expansion versus sales growth'),
    ('10.10', 'IT services', 'Revenue per employee', 'Operating margin (%)', 'Workforce productivity versus profitability'),
    ('10.11', 'FMCG', 'Volume growth (%)', 'Revenue growth (%)', 'Underlying demand versus reported sales growth'),
    ('10.12', 'FMCG', 'Advertising expenditure/Revenue (%)', 'Revenue growth (%)', 'Marketing investment versus sales growth'),
    ('10.13', 'Manufacturing', 'Capacity utilisation (%)', 'Operating margin (%)', 'Plant utilisation versus profitability'),
    ('10.14', 'Manufacturing', 'Raw material cost/Revenue (%)', 'Operating margin (%)', 'Input-cost pressure versus margins'),
    ('10.15', 'Automobile', 'Vehicle sales growth (%)', 'Revenue growth (%)', 'Unit sales versus revenue expansion'),
    ('10.16', 'Real estate', 'Pre-sales growth (%)', 'Revenue growth (%)', 'Bookings versus recognised revenue'),
    ('10.17', 'Real estate', 'Net debt/EBITDA', 'Interest coverage ratio', 'Leverage versus debt-servicing capacity'),
    ('10.18', 'Telecom', 'ARPU growth (%)', 'Revenue growth (%)', 'Average customer revenue versus sales growth'),
    ('10.19', 'Pharma', 'R&D/Revenue (%)', 'Revenue growth (%)', 'Research investment versus sales growth'),
    ('10.20', 'Commodities', 'Commodity price change (%)', 'Operating margin (%)', 'Commodity price sensitivity'),
    ('10.21', 'Retail', 'Same-store sales growth (%)', 'Operating margin (%)', 'Existing-store growth versus profitability'),
]

_MECH = "A strong correlation is expected by construction because "
_NA = "Not available: "
_IT = {"kind": "index", "value": "NIFTYIT", "match": ["information technology", "it - software", "it services", "software"]}
_REALTY = {"kind": "match", "value": None, "match": ["realty", "real estate"]}

# id -> (x, y, source, flags, extras). Unavailable pairs: (None, None, "N", "", {"reason": ...}).
SPEC: Dict[str, tuple] = {
    "1.1": ("pe", "g_rev", "C", "", {}),
    "1.2": ("pe", "g_eps", "C", "", {}),
    "1.3": ("pe", "roe", "A", "", {}),
    "1.4": ("pe", "roce", "A", "", {}),
    "1.5": ("pe", "opm", "A", "", {}),
    "1.6": ("pe", "npm", "A", "", {}),
    "1.7": ("pe", "g_fcf", "C", "L", {"notes": ["Many companies are left out because free cash flow was zero or negative in the earlier year (growth from a negative base is not defined)."]}),
    "1.8": ("pe", "dy", "A", "M", {"mechanical": _MECH + "both P/E and dividend yield contain the share price (one divides by it, the other multiplies)."}),
    "1.9": ("pb", "roe", "A", "M", {"mechanical": _MECH + "P/B is roughly P/E multiplied by ROE."}),
    "1.10": ("pb", "roa", "A", "", {}),
    "1.11": ("pb", "g_eps", "C", "", {}),
    "1.12": ("pb", "g_bv", "C", "", {}),
    "1.13": ("ev_ebitda", "g_ebitda", "C", "L", {"notes": ["EV/EBITDA uses the provider's trailing-12-month EBITDA; EBITDA growth is FinLit's latest financial year against the year before."]}),
    "1.14": ("ev_ebitda", "opm", "A", "L", {"notes": ["FinLit's operating margin is measured before depreciation, so it is the EBITDA margin."]}),
    "1.15": ("ev_ebitda", "roce", "A", "L", {}),
    "1.16": ("ev_ebitda", "fcf_yield", "A", "L", {}),
    "1.17": ("ev_sales", "g_rev", "C", "L", {}),
    "1.18": ("ev_sales", "opm", "A", "LM", {"mechanical": _MECH + "EV/Sales equals EV/EBITDA multiplied by the EBITDA (operating) margin."}),
    "1.19": ("ev_cfo", "g_cfo", "C", "L", {}),
    "1.20": ("ev_cfo", "cfo_pat", "A", "L", {}),
    "1.21": ("peg", "g_eps", "C", "M", {"mechanical": _MECH + "PEG is P/E divided by a growth rate.", "notes": ["PEG here divides P/E by the 5-year profit growth rate, not by EPS growth."]}),
    "1.22": ("mcap", "revenue", "A", "", {"scale": ("log", "log")}),
    "1.23": ("mcap", "np", "A", "", {"scale": ("log", "log"), "notes": ["On the log scale, loss-making companies (net profit zero or below) are left out and counted."]}),
    "1.24": ("mcap", "cfo", "A", "L", {"scale": ("log", "log")}),
    "2.1": ("roe", "pb", "A", "M", {"mechanical": _MECH + "P/B is roughly P/E multiplied by ROE."}),
    "2.2": ("roe", "pe", "A", "", {}),
    "2.3": ("roe", "roa", "A", "M", {"mechanical": _MECH + "ROE equals ROA multiplied by financial leverage (assets / equity)."}),
    "2.4": ("roe", "roce", "A", "", {}),
    "2.5": ("roce", "roa", "A", "", {}),
    "2.6": ("roce", "opm", "A", "", {}),
    "2.7": ("roa", "npm", "A", "M", {"mechanical": _MECH + "ROA equals net margin multiplied by asset turnover."}),
    "2.8": ("opm", "npm", "A", "M", {"mechanical": _MECH + "net profit is operating profit after depreciation, interest, other income and tax."}),
    "2.9": ("gross_margin", "opm", "A", "L", {}),
    "2.10": ("opm", "ebit_margin", "C", "L", {"adapted": True, "reason": "Adapted: FinLit's operating margin is measured before depreciation, so it IS the EBITDA margin and the chart as written would compare a figure with itself. Shown instead: EBITDA margin (= FinLit operating margin) against EBIT margin (after depreciation)."}),
    "2.11": ("opm", "npm", "A", "M", {"mechanical": _MECH + "net profit is operating profit after depreciation, interest, other income and tax.", "notes": ["EBITDA margin is FinLit's operating margin, so this is the same chart as 2.8."]}),
    "2.12": ("g_rev", "opm", "C", "", {}),
    "2.13": ("g_rev", "roce", "C", "", {}),
    "2.14": ("asset_turnover", "roa", "A", "LM", {"mechanical": _MECH + "ROA equals net margin multiplied by asset turnover."}),
    "2.15": ("inv_turnover", "roce", "C", "L", {}),
    "2.16": ("icr", "roe", "A", "L", {"notes": ["Companies with little or no debt have very large or no interest cover: try the log scale."]}),
    "2.17": (None, None, "N", "", {"reason": _NA + "a bank's operating costs and loan-loss provisions are not split out in the stored profit and loss, and cost-to-income is not a standard ratio for other companies."}),
    "3.1": ("g_rev", "g_eps", "C", "", {}),
    "3.2": ("g_rev", "g_np", "C", "", {}),
    "3.3": ("g_rev", "g_ebitda", "C", "", {}),
    "3.4": ("g_rev", "g_cfo", "C", "L", {}),
    "3.5": ("g_ebitda", "g_np", "C", "", {}),
    "3.6": ("g_ebitda", "g_cfo", "C", "L", {}),
    "3.7": ("g_np", "g_eps", "C", "M", {"mechanical": _MECH + "EPS growth equals net profit growth unless the number of shares changes."}),
    "3.8": ("g_eps", "ret_fy", "C", "", {}),
    "3.9": ("g_rev", "tsr_fy", "C", "", {}),
    "3.10": ("g_assets", "g_rev", "C", "", {}),
    "3.11": ("g_capex", "g_rev", "C", "L", {}),
    "3.12": ("g_wc", "g_rev", "C", "L", {"notes": ["Companies whose working capital was zero or negative in the earlier year are left out and counted (growth from a negative base is not defined)."]}),
    "3.13": (None, None, "N", "", {"reason": _NA + "order books are disclosed only in company presentations, not in the financial data we store."}),
    "3.14": ("g_bv", "g_eps", "C", "", {}),
    "3.15": (None, None, "N", "", {"reason": _NA + "R&D spending is not a separate line in the stored profit and loss."}),
    "4.1": ("de", "roe", "A", "L", {}),
    "4.2": ("de", "roce", "A", "L", {}),
    "4.3": ("de", "icr", "A", "L", {}),
    "4.4": ("de", "npm", "A", "L", {}),
    "4.5": ("de", "g_eps", "C", "L", {}),
    "4.6": ("de", "vol3y", "C", "L", {}),
    "4.7": (None, None, "N", "", {"reason": _NA + "credit ratings are not stored, and the rating agencies' terms for reusing them have not been checked."}),
    "4.8": ("debt_assets", "roa", "A", "L", {}),
    "4.9": ("nd_ebitda", "ev_ebitda", "A", "L", {"notes": ["Net debt/EBITDA uses the latest financial year's EBITDA; EV/EBITDA uses the provider's trailing-12-month EBITDA."]}),
    "4.10": ("nd_ebitda", "fcf", "A", "L", {"notes": ["Free cash flow is an amount in rupees crore: large companies sit far out simply because they are large. Switch to FCF yield to compare on a size-free basis."],
                                          "alt": {"x": "nd_ebitda", "y": "fcf_yield", "label": "Net debt/EBITDA vs FCF yield (%)"}}),
    "4.11": ("icr", "de", "A", "L", {"notes": ["Axes swapped from 4.3: the line of Y on X is a different line, not the same one flipped."]}),
    "4.12": ("g_int", "g_ebit", "C", "L", {}),
    "4.13": ("g_int", "g_np", "C", "L", {}),
    "4.14": ("cfo_debt", "de", "C", "L", {}),
    "4.15": ("cl_tl", "current_ratio", "C", "L", {}),
    "5.1": ("np", "cfo", "A", "L", {"notes": ["Amounts in rupees crore: size dominates. The robust (Theil-Sen) line and Spearman's rank correlation are less affected by the largest companies; the log view keeps only positive values."]}),
    "5.2": ("cfo", "fcf", "A", "LM", {"mechanical": _MECH + "free cash flow is CFO minus capital expenditure."}),
    "5.3": ("g_np", "g_cfo", "C", "L", {}),
    "5.4": ("g_rev", "g_cfo", "C", "L", {}),
    "5.5": ("cfo_pat", "npm", "A", "L", {}),
    "5.6": ("cfo_pat", "g_eps", "C", "L", {}),
    "5.7": ("cfo_debt", "nd_ebitda", "C", "L", {}),
    "5.8": ("fcf_yield", "pe", "A", "L", {}),
    "5.9": ("fcf_yield", "ev_ebitda", "A", "L", {}),
    "5.10": ("capex", "g_rev", "C", "L", {"notes": ["Capital expenditure is an amount in rupees crore: large companies sit far out simply because they are large."]}),
    "5.11": ("capex", "cfo", "A", "L", {"scale": ("log", "log")}),
    "5.12": ("g_recv", "g_rev", "C", "L", {}),
    "5.13": ("g_inv", "g_rev", "C", "L", {}),
    "5.14": (None, None, "N", "", {"reason": _NA + "trade payables are not read from the balance sheet yet (adding them needs a full reload of every company)."}),
    "5.15": ("g_dep", "g_capex", "C", "L", {}),
    "5.16": ("cfo", "ebitda", "A", "L", {}),
    "5.17": ("accruals", "cfo_pat", "C", "LM", {"mechanical": _MECH + "both are built from the gap between net profit and operating cash flow."}),
    "6.1": ("current_ratio", "quick_ratio", "A", "LM", {"mechanical": _MECH + "the quick ratio is the current ratio without inventories."}),
    "6.2": ("current_ratio", "de", "A", "L", {}),
    "6.3": ("quick_ratio", "icr", "A", "L", {}),
    "6.4": ("cash_ratio", "cur_liab", "C", "LM", {"mechanical": _MECH + "current liabilities are the denominator of the cash ratio.", "scale": ("log", "log")}),
    "6.5": ("recv_turnover", "opm", "C", "L", {}),
    "6.6": ("debtor_days", "g_rev", "C", "L", {}),
    "6.7": ("inv_turnover", "gross_margin", "C", "L", {}),
    "6.8": ("inv_days", "g_rev", "C", "L", {}),
    "6.9": ("payable_days", "cfo", "A", "L", {}),
    "6.10": ("ccc", "cfo", "A", "L", {}),
    "6.11": ("ccc", "roce", "A", "L", {}),
    "6.12": ("wc_rev", "opm", "A", "L", {}),
    "6.13": ("ca_ta", "roa", "C", "L", {}),
    "7.1": ("dy", "pe", "A", "M", {"mechanical": _MECH + "dividend yield and P/E both contain the share price."}),
    "7.2": ("dy", "pb", "A", "", {}),
    "7.3": ("payout", "g_eps", "C", "", {}),
    "7.4": (None, None, "N", "", {"reason": _NA + "there is no retained-earnings line; reserves also include the securities premium, so there is no honest substitute."}),
    "7.5": ("payout", "roe", "A", "", {}),
    "7.6": ("dy", "cfo_ps", "C", "", {"notes": ["CFO per share is in rupees per share, which depends on how many shares a company has issued: it cannot be compared across companies. Use the CFO yield alternative, or the history mode for one company."],
                                      "alt": {"x": "dy", "y": "cfo_yield", "label": "Dividend yield (%) vs CFO yield (%)"}}),
    "7.7": ("div_cover", "dy", "C", "", {"notes": ["Dividend payers only."]}),
    "7.8": ("g_dps", "g_eps", "C", "", {}),
    "7.9": ("g_dps", "g_cfo", "C", "L", {}),
    "7.10": (None, None, "N", "", {"reason": _NA + "buyback amounts are not stored (only whether a buyback happened in the last three years)."}),
    "7.11": ("tsr_fy", "g_eps", "C", "", {}),
    "7.12": ("tsr_fy", "roe", "C", "", {}),
    "7.13": ("g_bvps", "ret_fy", "C", "", {}),
    "8.1": ("pe_fy", "ret_fy", "C", "M", {"mechanical": _MECH + "the share price is in both the multiple and the return.",
                                         "variants": [{"id": "forward", "label": "Forward: P/E 75 days after the year end vs the next 12 months' return", "x": "pe_sig", "y": "fwd12", "tier": "gold"}]}),
    "8.2": ("pb_fy", "ret_fy", "C", "M", {"mechanical": _MECH + "the share price is in both the multiple and the return.",
                                         "variants": [{"id": "forward", "label": "Forward: P/B 75 days after the year end vs the next 12 months' return", "x": "pb_sig", "y": "fwd12", "tier": "gold"}]}),
    "8.3": ("g_eps", "ret_fy", "C", "", {"variants": [{"id": "forward", "label": "Forward: EPS growth vs the next 12 months' return (from 75 days after the year end)", "x": "g_eps_sig", "y": "fwd12", "tier": "gold"}]}),
    "8.4": ("g_rev", "ret_fy", "C", "", {"variants": [{"id": "forward", "label": "Forward: revenue growth vs the next 12 months' return (from 75 days after the year end)", "x": "g_rev_sig", "y": "fwd12", "tier": "gold"}]}),
    "8.5": ("rsi", "fwd_ret", "C", "", {"tech": {"kind": "rsi", "h": [5, 20, 60]}}),
    "8.6": ("macd_pct", "fwd_ret", "C", "", {"tech": {"kind": "macd", "h": [5, 20, 60]}}),
    "8.7": ("volg", "abs_ret", "C", "", {"tech": {"kind": "volg", "h": [20]}}),
    "8.8": ("mkt_ret", "stock_ret", "C", "", {"tech": {"kind": "beta", "h": [5]}, "adapted": True,
                                              "reason": "Adapted: beta is the slope of a company's weekly returns on the market's weekly returns. Shown per company: weekly stock return against weekly NIFTY 50 return over the last 3 years; the regression slope is the beta. Across companies the market return is the same number for everyone, so that view is not offered."}),
    "8.9": ("vol3y", "mdd3y", "C", "", {}),
    "8.10": ("p52h", "fwd_ret", "C", "", {"tech": {"kind": "p52h", "h": [5, 20, 60]}}),
    "8.11": (None, None, "N", "", {"reason": _NA + "delivery volumes (the NSE daily bhavcopy) are not collected."}),
    "8.12": ("inst_chg", "ret_inst", "C", "", {}),
    "9.1": ("g_rev", "g_np", "C", "", {}),
    "9.2": ("g_rev", "g_ebitda", "C", "", {}),
    "9.3": ("g_ebitda", "g_cfo", "C", "L", {}),
    "9.4": ("g_eps", "g_np", "C", "M", {"mechanical": _MECH + "EPS growth equals net profit growth unless the number of shares changes."}),
    "9.5": ("g_recv", "g_rev", "C", "L", {}),
    "9.6": ("g_inv", "g_rev", "C", "L", {}),
    "9.7": ("oi_np", "g_np", "C", "", {}),
    "9.8": ("exc_np", "g_np", "C", "", {}),
    "9.9": ("g_int", "g_rev", "C", "L", {}),
    "9.10": ("g_tax", "g_pbt", "C", "", {}),
    "9.11": ("g_cfo", "g_np", "C", "L", {}),
    "9.12": ("g_debt", "g_ebitda", "C", "L", {}),
    "9.13": (None, None, "N", "", {"reason": _NA + "promoter pledge data is not collected."}),
    "9.14": (None, None, "N", "", {"reason": _NA + "auditor opinions are not collected."}),
    "9.15": (None, None, "N", "", {"reason": _NA + "contingent liabilities are not collected."}),
    "10.1": (None, None, "N", "", {"reason": _NA + "net interest margin needs interest-earning assets, which are not stored. See \"Available for lenders\" below."}),
    "10.2": (None, None, "N", "", {"reason": _NA + "gross NPA is not stored. See \"Available for lenders\" below."}),
    "10.3": (None, None, "N", "", {"reason": _NA + "CASA ratio and net interest margin are not stored."}),
    "10.4": (None, None, "N", "", {"reason": _NA + "bank advances (loan book) are not stored, so credit growth cannot be measured."}),
    "10.5": (None, None, "N", "", {"reason": _NA + "capital adequacy ratio is not stored."}),
    "10.6": (None, None, "N", "", {"reason": _NA + "embedded value is not stored."}),
    "10.7": (None, None, "N", "", {"reason": _NA + "combined ratio and underwriting profit are not stored."}),
    "10.8": ("g_rev", "ebit_margin", "C", "L", {"preset": _IT}),
    "10.9": (None, None, "N", "", {"reason": _NA + "only the latest headcount is known (from the company profile), so employee growth cannot be measured."}),
    "10.10": ("sales_per_employee", "opm", "A", "", {"preset": _IT, "notes": ["Headcount comes from the company profile; the date it refers to is not known."]}),
    "10.11": (None, None, "N", "", {"reason": _NA + "sales volumes are not stored."}),
    "10.12": (None, None, "N", "", {"reason": _NA + "advertising spending is not a separate line in the stored profit and loss."}),
    "10.13": (None, None, "N", "", {"reason": _NA + "capacity utilisation is not stored."}),
    "10.14": (None, None, "N", "", {"reason": _NA + "raw material cost is not a separate line in the stored profit and loss."}),
    "10.15": (None, None, "N", "", {"reason": _NA + "vehicle unit sales are not stored."}),
    "10.16": (None, None, "N", "", {"reason": _NA + "pre-sales (bookings) are not stored."}),
    "10.17": ("nd_ebitda", "icr", "A", "L", {"preset": _REALTY}),
    "10.18": (None, None, "N", "", {"reason": _NA + "ARPU is not stored."}),
    "10.19": (None, None, "N", "", {"reason": _NA + "R&D spending is not a separate line in the stored profit and loss."}),
    "10.20": (None, None, "N", "", {"reason": _NA + "no commodity price series is stored."}),
    "10.21": (None, None, "N", "", {"reason": _NA + "same-store sales are not stored."}),
}

# Section 10: offered instead of the banking rows (not counted among the 162 pairs)
ALTERNATIVES = [
    {"id": "10.B1", "section": 10, "xLabel": "P/B ratio", "yLabel": "ROE (%)", "x": "pb", "y": "roe", "lenders": "only", "label": "Available for lenders",
     "help": "Book valuation relative to shareholder returns, banks and lenders only."},
    {"id": "10.B2", "section": 10, "xLabel": "P/B ratio", "yLabel": "ROA (%)", "x": "pb", "y": "roa", "lenders": "only", "label": "Available for lenders",
     "help": "Book valuation relative to asset profitability, banks and lenders only."},
]

REASONS: Dict[str, str] = {
    "no_report": "No stored full report for this company yet: open its page to load it.",
    "preparing": "This company's figures for these charts are being prepared (refresh pending).",
    "unknown": "Not in our list of listed companies.",
    "outside": "Outside the chosen filters: shown for reference, not part of the statistics.",
    "lender": "Banks and lenders left out: this ratio does not apply to lenders.",
    "neg_equity": "Negative or zero equity: the ratio would mislead.",
    "no_fy": "No figure for the company's latest financial year.",
    "non_march": "The company's financial year does not end in March, so the provider's yearly ratio is not available.",
    "no_data": "Not reported in the company's stored statements.",
    "loss": "Loss-making: a price multiple or a ratio on profit is not meaningful.",
    "np_le0": "Net profit is zero or negative: a ratio on profit is not meaningful.",
    "cfo_le0": "Operating cash flow is zero or negative: EV/CFO is not meaningful.",
    "op_le0": "Operating profit (EBITDA) is zero or negative: the ratio is not meaningful.",
    "no_debt": "No borrowings: the ratio is not defined.",
    "den_zero": "The denominator is zero.",
    "no_prev": "No earlier year to measure growth from.",
    "base_le0": "Growth not defined: the earlier year was zero or negative (a swing from a loss is not growth).",
    "gap": "The two years are not consecutive (period ends not 330-400 days apart).",
    "share_change": "The share count changed by more than 25% (or by more than 5% with a bonus or split): per-share growth is not comparable.",
    "partial": "The dividend year is not complete, or is not the same year as the results.",
    "no_dividend": "No dividend for the year.",
    "no_growth": "No positive 5-year profit growth to divide by.",
    "short_history": "Not enough daily price history.",
    "start_gap": "No close within 7 days of the start or end of the window.",
    "jump": "A split, bonus or a one-day price move of more than 80% inside the window: the return is not computed.",
    "basis": "The stored daily closes could not be confirmed to be on the provider's split/bonus-adjusted basis for this window.",
    "not_complete": "The 12 months after the signal date have not passed yet.",
    "no_market": "No NIFTY 50 history for these weeks.",
    "warmup": "The indicator needs more earlier prices at this date.",
    "log_le0": "Zero or negative: cannot be placed on a log scale.",
    "fy_mismatch": "Results year differs from the majority (\"Same FY only\" is on).",
    "trimmed": "Left out by \"leave out the most extreme 1%\".",
    "no_value": "No value (not reported by the provider, or not meaningful).",
}

CAVEATS = [
    "Correlation is not causation.",
    "Information only, not advice.",
    "p-values assume the companies are independent; companies in one sector move together, so the p-values overstate certainty.",
    "With about 130 charts, roughly 1 in 20 will look statistically significant by chance alone.",
]
COVERAGE_NOTE = "Only companies with a stored full report are charted: mostly the largest listed companies, not all listed companies."


def _sec(pid: str) -> int:
    return int(pid.split(".")[0])


def history_tier(x: str, y: str) -> Optional[str]:
    hx, hy = METRICS[x].history, METRICS[y].history
    if hx is None or hy is None:
        return None
    return "gold" if "gold" in (hx, hy) else "silver"


def _build_pairs() -> List[dict]:
    pairs: List[dict] = []
    seen: Dict[Tuple[str, str], str] = {}
    for row in ROWS:
        pid = row[0]
        sector = row[1] if len(row) == 5 else None
        xl, yl, hp = row[-3], row[-2], row[-1]
        x, y, src, flags, ex = SPEC[pid]
        sec = _sec(pid)
        p: dict = {"id": pid, "section": sec, "row": int(pid.split(".")[1]), "xLabel": xl, "yLabel": yl, "help": hp, "source": src,
                   "x": x, "y": y, "flags": sorted(set(flags)), "mechanical": ex.get("mechanical"), "notes": list(ex.get("notes", [])),
                   "reason": ex.get("reason"), "sector": sector, "preset": ex.get("preset"), "alt": ex.get("alt"), "tech": ex.get("tech"),
                   "variants": list(ex.get("variants", [])), "sameAs": None}
        if src == "N":
            p.update(status="unavailable", modes=[], tier={}, lenders=None, scale=None, logOk=None)
            pairs.append(p)
            continue
        p["status"] = "adapted" if ex.get("adapted") else "ready"
        mx, my = METRICS[x], METRICS[y]
        if ex.get("tech"):
            p.update(modes=["tech"], tier={"tech": "gold"}, lenders="auto")
        else:
            modes, tier = ["cross"], {"cross": "silver"}
            ht = history_tier(x, y)
            if ht and sec != 8:
                modes.append("history")
                tier["history"] = ht
            p.update(modes=modes, tier=tier)
            forced = "L" in flags or mx.lenders == "excluded" or my.lenders == "excluded"
            if forced and "L" not in p["flags"]:
                p["flags"] = sorted(set(p["flags"]) | {"L"})
            p["lenders"] = "excluded" if forced else "auto"
            key = (x, y)
            if key in seen:
                p["sameAs"] = seen[key]
            else:
                seen[key] = pid
        sc = ex.get("scale", ("lin", "lin"))
        p["scale"] = {"x": sc[0], "y": sc[1]}
        p["logOk"] = {"x": mx.log_ok, "y": my.log_ok}
        pairs.append(p)
    return pairs


PAIRS: List[dict] = _build_pairs()
BY_ID: Dict[str, dict] = {p["id"]: p for p in PAIRS}
for _a in ALTERNATIVES:
    BY_ID[_a["id"]] = {**_a, "row": 0, "source": "A", "flags": [], "mechanical": None, "notes": [], "reason": None, "sector": "Banking",
                       "preset": None, "alt": None, "tech": None, "variants": [], "sameAs": None, "status": "ready", "modes": ["cross"],
                       "tier": {"cross": "silver"}, "scale": {"x": "lin", "y": "lin"}, "logOk": {"x": True, "y": False}}


def metric_json(m: Metric) -> dict:
    return {"label": m.label, "short": m.short, "unit": m.unit, "basis": m.basis, "digits": m.digits, "formula": m.formula,
            "logOk": m.log_ok, "lenders": m.lenders, "history": m.history}


def catalog_json() -> dict:
    counts = {"pairs": len(PAIRS), "ready": sum(p["status"] == "ready" for p in PAIRS), "adapted": sum(p["status"] == "adapted" for p in PAIRS),
              "unavailable": sum(p["status"] == "unavailable" for p in PAIRS)}
    for s in ("A", "C", "N"):
        counts[s] = sum(p["source"] == s for p in PAIRS)
    sections = []
    for s in SECTIONS:
        sections.append({**s, "pairs": [p["id"] for p in PAIRS if p["section"] == s["id"]],
                         "alternatives": [a for a in ALTERNATIVES if a["section"] == s["id"]]})
    return {"version": 1, "counts": counts, "sections": sections, "pairs": PAIRS,
            "metrics": {m.id: metric_json(m) for m in METRIC_LIST}, "reasons": REASONS,
            "decisions": dict(DECISION_TEXT),
            "caveats": CAVEATS, "coverageNote": COVERAGE_NOTE}
