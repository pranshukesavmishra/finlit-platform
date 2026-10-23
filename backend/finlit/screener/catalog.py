"""Every filter the screener offers: one list, used by the computation, the query API, the plan gate and the website.

Tiers: "basic" (free), "silver" (the full catalogue), "gold" (FinLit's own model filters).
unit: "x" times, "%" percent, "Cr" rupees crore, "Rs" rupees, "d" days, "n" count, "pts" score points, "flag" yes/no (stored 1 or 0).
better: "higher" / "lower" / "none" (used for the plain-words hint and sorting defaults).
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple, Optional


class Metric(NamedTuple):
    key: str
    label: str
    group: str
    unit: str
    better: str = "none"
    tier: str = "silver"
    say: str = ""
    digits: int = 1


GROUPS = [
    ("size", "Size & Price"), ("returns", "Returns"), ("valuation", "Valuation"), ("profitability", "Profitability"), ("growth", "Growth"),
    ("quarterly", "Quarterly Results"), ("health", "Financial Health"), ("liquidity", "Liquidity"), ("solvency", "Solvency"), ("efficiency", "Efficiency"),
    ("ownership", "Ownership"), ("events", "Company Events"), ("flags", "Red Flags"), ("banks", "Banks & Lenders"), ("trading", "Volume, Range & Trend"),
    ("model", "FinLit Model"),
]
GROUP_LABEL = dict(GROUPS)
GROUP_TIER = {"model": "gold"}

M = Metric
_B = "basic"
CATALOG: List[Metric] = [
    # ---- Size & Price
    M("market_cap", "Market cap", "size", "Cr", "none", _B, "What the whole company is worth on the stock market.", 0),
    M("price", "Share price", "size", "Rs", "none", _B, "Latest traded price of one share.", 2),
    M("enterprise_value", "Enterprise value", "size", "Cr", "none", "silver", "Market value plus debt, less cash: the price of buying the whole business.", 0),
    M("revenue", "Sales (latest year)", "size", "Cr", "higher", "silver", "Total sales in the latest financial year.", 0),
    M("net_profit", "Net profit (latest year)", "size", "Cr", "higher", "silver", "Profit after all costs and tax in the latest year.", 0),
    M("total_assets", "Total assets", "size", "Cr", "none", "silver", "Everything the company owns, as per the balance sheet.", 0),
    M("book_value_ps", "Book value per share", "size", "Rs", "higher", "silver", "Owners' money in the business, per share.", 2),
    M("eps", "Earnings per share", "size", "Rs", "higher", "silver", "Profit that belongs to each share, latest year.", 2),
    # ---- Returns
    M("ret_1d", "1-day change", "returns", "%", "higher", _B, "How the price moved today.", 1),
    M("ret_1m", "1-month return", "returns", "%", "higher", _B, "Price change over the last month.", 1),
    M("ret_3m", "3-month return", "returns", "%", "higher", "silver", "Price change over three months.", 1),
    M("ret_6m", "6-month return", "returns", "%", "higher", "silver", "Price change over six months.", 1),
    M("ret_1y", "1-year return", "returns", "%", "higher", _B, "Price change over the last year.", 1),
    M("ret_3y", "3-year return", "returns", "%", "higher", "silver", "Price change over three years.", 1),
    M("ret_5y", "5-year return", "returns", "%", "higher", "silver", "Price change over five years.", 1),
    M("ret_1y_total", "1-year total return", "returns", "%", "higher", "silver", "Price change plus dividends received over a year.", 1),
    # ---- Valuation
    M("pe", "P/E Ratio", "valuation", "x", "lower", _B, "Rupees you pay for each rupee of yearly profit.", 1),
    M("pb", "P/B Ratio", "valuation", "x", "lower", "silver", "Price compared with what the books say the company owns.", 2),
    M("ev_ebitda", "EV / EBITDA", "valuation", "x", "lower", "silver", "Enterprise value for each rupee of operating earnings.", 1),
    M("dividend_yield", "Dividend Yield", "valuation", "%", "higher", _B, "Yearly cash dividend for every ₹100 invested.", 2),
    M("peg", "PEG Ratio", "valuation", "x", "lower", "silver", "P/E divided by yearly profit growth. Under 1 can mean growth is cheap.", 2),
    M("earnings_yield", "Earnings Yield", "valuation", "%", "higher", "silver", "Yearly profit for every ₹100 of market value (the inverse of P/E).", 1),
    M("graham_value", "Graham Fair Value", "valuation", "Rs", "none", "silver", "Benjamin Graham's rule of thumb: the square root of 22.5 × earnings per share × book value per share.", 0),
    M("graham_upside", "Upside to Graham Value", "valuation", "%", "higher", "silver", "How far the share price is below (+) or above (−) the Graham fair value.", 0),
    M("ev_cfo", "EV / CFO", "valuation", "x", "lower", "silver", "Enterprise value for each rupee of operating cash flow.", 1),
    M("ev_sales", "EV / Sales", "valuation", "x", "lower", "silver", "Enterprise value for each rupee of sales.", 2),
    M("ps", "Price / Sales", "valuation", "x", "lower", "silver", "Rupees you pay for each rupee of yearly sales.", 2),
    M("price_cfo", "Price / CFO", "valuation", "x", "lower", "silver", "Market value for each rupee of operating cash flow.", 1),
    M("dividend_payout", "Dividend Payout", "valuation", "%", "none", "silver", "Share of profit paid out as dividend.", 0),
    M("pfcf", "Price / FCF", "valuation", "x", "lower", "silver", "Market value for each rupee of free cash flow.", 1),
    M("fcf_yield", "FCF Yield", "valuation", "%", "higher", "silver", "Spare cash generated for every ₹100 of market value.", 1),
    M("sales_ps", "Sales / Share", "valuation", "Rs", "higher", "silver", "Yearly sales for each share.", 1),
    M("cash_ps", "Cash / Share", "valuation", "Rs", "higher", "silver", "Cash on the balance sheet for each share.", 1),
    M("net_cash_ps", "Net Cash / Share", "valuation", "Rs", "higher", "silver", "Cash and investments less debt, for each share. Negative means net debt.", 1),
    M("fcf_ps", "FCF / Share", "valuation", "Rs", "higher", "silver", "Free cash flow for each share.", 1),
    M("pe_vs_median_5y", "P/E vs own 5Y median", "valuation", "%", "lower", "silver", "How far today's P/E is above (+) or below (−) its own median of the last five years.", 0),
    M("pe_median_5y", "Median P/E (5Y)", "valuation", "x", "none", "silver", "The middle P/E of the last five yearly readings.", 1),
    M("pb_vs_median_5y", "P/B vs own 5Y median", "valuation", "%", "lower", "silver", "How far today's P/B is above (+) or below (−) its own median of the last five years.", 0),
    M("pe_vs_sector", "P/E vs sector median", "valuation", "%", "lower", "silver", "How far the P/E is above (+) or below (−) the median of its sector.", 0),
    M("pb_vs_sector", "P/B vs sector median", "valuation", "%", "lower", "silver", "How far the P/B is above (+) or below (−) the median of its sector.", 0),
    M("price_to_tangible", "Market cap to total assets", "valuation", "x", "lower", "silver", "Market value for each rupee of assets owned.", 2),
    # averages over the last 3 / 5 / 7 yearly readings: reached from the Now / 3Y / 5Y / 7Y tabs of their base filter, not listed on their own
    M("pe_avg_3y", "P/E Ratio, 3Y average", "valuation", "x", "lower", "silver", "Average of the last three yearly P/E readings.", 1),
    M("pe_avg_5y", "P/E Ratio, 5Y average", "valuation", "x", "lower", "silver", "Average of the last five yearly P/E readings.", 1),
    M("pe_avg_7y", "P/E Ratio, 7Y average", "valuation", "x", "lower", "silver", "Average of the last seven yearly P/E readings.", 1),
    M("pb_avg_3y", "P/B Ratio, 3Y average", "valuation", "x", "lower", "silver", "Average of the last three yearly P/B readings.", 2),
    M("pb_avg_5y", "P/B Ratio, 5Y average", "valuation", "x", "lower", "silver", "Average of the last five yearly P/B readings.", 2),
    M("pb_avg_7y", "P/B Ratio, 7Y average", "valuation", "x", "lower", "silver", "Average of the last seven yearly P/B readings.", 2),
    M("ps_avg_3y", "Price / Sales, 3Y average", "valuation", "x", "lower", "silver", "Average of the last three yearly P/S readings.", 2),
    M("ps_avg_5y", "Price / Sales, 5Y average", "valuation", "x", "lower", "silver", "Average of the last five yearly P/S readings.", 2),
    M("ps_avg_7y", "Price / Sales, 7Y average", "valuation", "x", "lower", "silver", "Average of the last seven yearly P/S readings.", 2),
    # ---- Profitability
    M("roe", "Return on equity", "profitability", "%", "higher", _B, "Profit earned on shareholders' money.", 1),
    M("roce", "Return on capital employed", "profitability", "%", "higher", _B, "Profit earned on all the money used in the business.", 1),
    M("roa", "Return on assets", "profitability", "%", "higher", "silver", "Profit earned on everything the company owns.", 1),
    M("rota", "Return on tangible assets", "profitability", "%", "higher", "silver", "Profit earned on physical assets.", 1),
    M("operating_margin", "Operating margin, annual (latest year)", "profitability", "%", "higher", _B, "Annual: operating profit from the core business out of every ₹100 of sales, latest financial year.", 1),
    M("op_profit", "Operating profit, annual (latest year)", "profitability", "Cr", "higher", "silver", "Annual: profit from the core business in the latest financial year, before depreciation and interest.", 0),
    M("net_margin", "Net margin", "profitability", "%", "higher", "silver", "Final profit out of every ₹100 of sales.", 1),
    M("gross_margin", "Gross margin", "profitability", "%", "higher", "silver", "Sales left after the direct cost of goods.", 1),
    M("ebitda_margin", "EBITDA margin", "profitability", "%", "higher", "silver", "Operating earnings before depreciation, out of every ₹100 of sales.", 1),
    M("ebit_margin", "EBIT margin", "profitability", "%", "higher", "silver", "Operating earnings after depreciation, out of every ₹100 of sales.", 1),
    M("pretax_margin", "Pre-tax margin", "profitability", "%", "higher", "silver", "Profit before tax out of every ₹100 of sales.", 1),
    M("tax_rate", "Effective tax rate", "profitability", "%", "none", "silver", "Share of pre-tax profit paid as tax.", 1),
    M("roe_3y", "ROE, 3-year average", "profitability", "%", "higher", "silver", "Average return on equity over the last three years.", 1),
    M("roce_3y", "ROCE, 3-year average", "profitability", "%", "higher", "silver", "Average return on capital over the last three years.", 1),
    M("opm_3y", "Operating margin, annual, 3-year average", "profitability", "%", "higher", "silver", "Average operating margin over the last three years.", 1),
    M("opm_change", "Operating margin change, annual (1 year)", "profitability", "pts", "higher", "silver", "Annual: percentage points the operating margin moved in the latest financial year.", 1),
    # ---- Growth
    M("sales_growth", "Sales growth (latest year)", "growth", "%", "higher", "silver", "How much sales grew in the latest year.", 1),
    M("profit_growth", "Profit growth (latest year)", "growth", "%", "higher", "silver", "How much profit grew in the latest year.", 1),
    M("op_profit_growth", "Operating profit growth, annual (year on year)", "growth", "%", "higher", "silver", "Annual: how much operating profit grew in the latest financial year against the year before. Blank when last year was a loss.", 1),
    M("op_profit_cagr_3y", "Operating profit growth, annual, 3 years a year (CAGR)", "growth", "%", "higher", "silver", "Annual: yearly operating profit growth over three financial years. Blank unless both ends are profits.", 1),
    M("op_profit_cagr_5y", "Operating profit growth, annual, 5 years a year (CAGR)", "growth", "%", "higher", "silver", "Annual: yearly operating profit growth over five financial years. Blank unless both ends are profits.", 1),
    M("sales_cagr_3y", "Sales growth, 3 years a year", "growth", "%", "higher", "silver", "Yearly sales growth over three years.", 1),
    M("sales_cagr_5y", "Sales growth, 5 years a year", "growth", "%", "higher", _B, "Yearly sales growth over five years.", 1),
    M("profit_cagr_3y", "Profit growth, 3 years a year", "growth", "%", "higher", "silver", "Yearly profit growth over three years.", 1),
    M("profit_cagr_5y", "Profit growth, 5 years a year", "growth", "%", "higher", _B, "Yearly profit growth over five years.", 1),
    M("ebitda_cagr_5y", "EBITDA growth, 5 years a year", "growth", "%", "higher", "silver", "Yearly growth in operating earnings over five years.", 1),
    M("eps_cagr_5y", "EPS growth, 5 years a year", "growth", "%", "higher", "silver", "Yearly growth in earnings per share over five years.", 1),
    M("cfo_cagr_3y", "Operating cash flow growth, 3 years a year", "growth", "%", "higher", "silver", "Yearly growth in cash from operations over three years.", 1),
    M("bv_cagr_5y", "Book value growth, 5 years a year", "growth", "%", "higher", "silver", "Yearly growth in owners' money over five years.", 1),
    M("dps_cagr", "Dividend growth (yearly)", "growth", "%", "higher", "silver", "Yearly growth in dividend per share over the years reported.", 1),
    M("years_profit_up", "Years of rising profit (last 5)", "growth", "n", "higher", "silver", "In how many of the last five years profit was higher than the year before.", 0),
    # ---- Quarterly Results
    M("q_revenue", "Latest quarter sales", "quarterly", "Cr", "higher", "silver", "Sales in the most recent quarter.", 0),
    M("q_net_profit", "Latest quarter profit", "quarterly", "Cr", "higher", "silver", "Net profit in the most recent quarter.", 0),
    M("q_operating_profit", "Operating profit, quarterly (latest quarter)", "quarterly", "Cr", "higher", "silver", "Quarterly: operating profit in the most recent quarter.", 0),
    M("q_eps", "Latest quarter EPS", "quarterly", "Rs", "higher", "silver", "Earnings per share in the most recent quarter.", 2),
    M("q_sales_yoy", "Sales growth vs same quarter last year", "quarterly", "%", "higher", "silver", "Latest quarter's sales against the same quarter a year ago.", 1),
    M("q_profit_yoy", "Profit growth vs same quarter last year", "quarterly", "%", "higher", "silver", "Latest quarter's profit against the same quarter a year ago.", 1),
    M("q_sales_qoq", "Sales growth vs previous quarter", "quarterly", "%", "higher", "silver", "Latest quarter's sales against the quarter before.", 1),
    M("q_profit_qoq", "Profit growth vs previous quarter", "quarterly", "%", "higher", "silver", "Latest quarter's profit against the quarter before.", 1),
    M("q_opm", "Operating margin, quarterly (latest quarter)", "quarterly", "%", "higher", "silver", "Operating margin in the most recent quarter.", 1),
    M("q_npm", "Latest quarter net margin", "quarterly", "%", "higher", "silver", "Net margin in the most recent quarter.", 1),
    M("ttm_revenue", "Sales, last 12 months", "quarterly", "Cr", "higher", "silver", "Sum of the last four quarters' sales.", 0),
    M("ttm_net_profit", "Profit, last 12 months", "quarterly", "Cr", "higher", "silver", "Sum of the last four quarters' profit.", 0),
    M("ttm_eps", "EPS, last 12 months", "quarterly", "Rs", "higher", "silver", "Sum of the last four quarters' earnings per share.", 2),
    M("q_sales_up", "Quarters of rising sales (last 4, year on year)", "quarterly", "n", "higher", "silver", "In how many of the last four quarters sales beat the same quarter a year ago.", 0),
    M("q_profit_up", "Quarters of rising profit (last 4, year on year)", "quarterly", "n", "higher", "silver", "In how many of the last four quarters profit beat the same quarter a year ago.", 0),
    # ---- Financial Health
    M("debt_to_equity", "Debt to equity", "health", "x", "lower", _B, "Rupees owed for every rupee of owners' money.", 2),
    M("lt_debt_to_equity", "Long-term debt to equity", "health", "x", "lower", "silver", "Long-term borrowings for every rupee of owners' money.", 2),
    M("net_debt", "Net debt", "health", "Cr", "lower", "silver", "Borrowings less cash and investments. Negative means net cash.", 0),
    M("net_debt_to_equity", "Net debt to equity", "health", "x", "lower", "silver", "Net debt for every rupee of owners' money.", 2),
    M("net_debt_to_ebitda", "Net debt to EBITDA", "health", "x", "lower", "silver", "Years of operating earnings needed to repay net debt.", 1),
    M("borrowings", "Total borrowings", "health", "Cr", "lower", "silver", "All loans and debt on the balance sheet.", 0),
    M("cash", "Cash and equivalents", "health", "Cr", "higher", "silver", "Cash on the balance sheet.", 0),
    M("cash_to_debt", "Cash to debt", "health", "x", "higher", "silver", "Cash held for each rupee of borrowings.", 2),
    M("debt_to_fcf", "Debt to free cash flow", "health", "x", "lower", "silver", "Years of spare cash needed to repay all debt.", 1),
    M("interest_coverage", "Interest cover", "health", "x", "higher", _B, "How many times operating profit covers the interest bill.", 1),
    M("fcf", "Free cash flow (latest year)", "health", "Cr", "higher", "silver", "Cash from operations less capital spending.", 0),
    M("cfo", "Operating cash flow (latest year)", "health", "Cr", "higher", "silver", "Cash generated by the business itself.", 0),
    # ---- Liquidity
    M("current_ratio", "Current ratio", "liquidity", "x", "higher", "silver", "Short-term assets for each rupee of short-term bills.", 2),
    M("quick_ratio", "Quick ratio", "liquidity", "x", "higher", "silver", "Current ratio without unsold stock.", 2),
    M("cash_to_current_liab", "Cash to current liabilities", "liquidity", "x", "higher", "silver", "Cash held for each rupee of short-term bills.", 2),
    M("working_capital", "Working capital", "liquidity", "Cr", "higher", "silver", "Short-term assets less short-term liabilities.", 0),
    M("working_capital_to_sales", "Working capital to sales", "liquidity", "%", "lower", "silver", "Money tied up in day-to-day running, as a share of sales.", 1),
    # ---- Solvency
    M("debt_to_assets", "Debt to assets", "solvency", "x", "lower", "silver", "Borrowings for each rupee of assets.", 2),
    M("liabilities_to_assets", "Liabilities to assets", "solvency", "x", "lower", "silver", "Everything owed for each rupee of assets.", 2),
    M("financial_leverage", "Financial leverage", "solvency", "x", "lower", "silver", "Assets for each rupee of owners' money.", 2),
    M("equity_ratio", "Equity ratio", "solvency", "%", "higher", "silver", "Share of assets funded by owners' money.", 0),
    M("equity", "Owners' equity", "solvency", "Cr", "higher", "silver", "Shareholders' money in the business.", 0),
    # ---- Efficiency
    M("asset_turnover", "Asset turnover", "efficiency", "x", "higher", "silver", "Sales made for each rupee of assets.", 2),
    M("fixed_asset_turnover", "Fixed asset turnover", "efficiency", "x", "higher", "silver", "Sales made for each rupee of factories and equipment.", 2),
    M("inventory_days", "Inventory days", "efficiency", "d", "lower", "silver", "Days of sales sitting unsold as stock.", 0),
    M("debtor_days", "Debtor days", "efficiency", "d", "lower", "silver", "Days it takes customers to pay.", 0),
    M("payable_days", "Payable days", "efficiency", "d", "none", "silver", "Days the company takes to pay suppliers.", 0),
    M("cash_cycle", "Cash conversion cycle", "efficiency", "d", "lower", "silver", "Days between paying for stock and getting paid.", 0),
    M("cfo_to_pat", "Cash profit conversion", "efficiency", "%", "higher", "silver", "Operating cash flow as a share of reported profit.", 0),
    M("fcf_to_pat", "Free cash flow to profit", "efficiency", "%", "higher", "silver", "Free cash flow as a share of reported profit.", 0),
    M("capex_to_sales", "Capital spending to sales", "efficiency", "%", "none", "silver", "Share of sales reinvested in equipment and capacity.", 1),
    M("capex_to_cfo", "Capital spending to operating cash", "efficiency", "%", "none", "silver", "Share of operating cash flow reinvested.", 0),
    M("sales_per_employee", "Sales per employee", "efficiency", "Cr", "higher", "silver", "Yearly sales divided by headcount, in crore rupees.", 2),
    M("profit_per_employee", "Profit per employee", "efficiency", "Cr", "higher", "silver", "Yearly profit divided by headcount, in crore rupees.", 3),
    M("employees", "Employees", "efficiency", "n", "none", "silver", "Headcount reported by the company.", 0),
    M("retention_ratio", "Profit retained", "efficiency", "%", "none", "silver", "Share of profit kept in the business.", 0),
    # ---- Ownership
    M("own_promoters", "Promoter holding", "ownership", "%", "none", "silver", "Share of the company held by its founders and their group.", 1),
    M("own_fii", "Foreign institutions", "ownership", "%", "none", "silver", "Share held by foreign funds.", 1),
    M("own_dii", "Domestic institutions", "ownership", "%", "none", "silver", "Share held by Indian funds, insurers and banks.", 1),
    M("own_public", "Public holding", "ownership", "%", "none", "silver", "Share held by everyday investors and others.", 1),
    M("own_government", "Government holding", "ownership", "%", "none", "silver", "Share held by government bodies.", 1),
    M("own_institutions", "All institutions", "ownership", "%", "none", "silver", "Foreign plus domestic institutions.", 1),
    M("own_promoters_chg_1y", "Promoter holding change (1 year)", "ownership", "pts", "higher", "silver", "Percentage points promoters bought (+) or sold (−) in a year.", 2),
    M("own_fii_chg_1y", "Foreign institutions change (1 year)", "ownership", "pts", "higher", "silver", "Percentage points foreign funds bought (+) or sold (−) in a year.", 2),
    M("own_dii_chg_1y", "Domestic institutions change (1 year)", "ownership", "pts", "higher", "silver", "Percentage points Indian institutions bought (+) or sold (−) in a year.", 2),
    M("own_public_chg_1y", "Public holding change (1 year)", "ownership", "pts", "none", "silver", "Percentage points everyday investors added (+) or cut (−) in a year.", 2),
    M("own_promoters_chg_1q", "Promoter holding change (last quarter)", "ownership", "pts", "higher", "silver", "Percentage points promoters bought (+) or sold (−) last quarter.", 2),
    M("own_fii_chg_1q", "Foreign institutions change (last quarter)", "ownership", "pts", "higher", "silver", "Percentage points foreign funds bought (+) or sold (−) last quarter.", 2),
    M("own_dii_chg_1q", "Domestic institutions change (last quarter)", "ownership", "pts", "higher", "silver", "Percentage points Indian institutions bought (+) or sold (−) last quarter.", 2),
    M("own_inst_chg_1y", "Institutions change (1 year)", "ownership", "pts", "higher", "silver", "Percentage points all institutions added (+) or cut (−) in a year.", 2),
    # ---- Company Events
    M("div_ttm", "Dividend per share (last 12 months)", "events", "Rs", "higher", "silver", "Dividends declared over the last twelve months.", 2),
    M("div_last_days", "Days since last dividend", "events", "d", "lower", "silver", "How long since the last dividend went ex.", 0),
    M("div_years", "Years of dividends (last 6)", "events", "n", "higher", "silver", "In how many of the last six years a dividend was declared.", 0),
    M("div_paying", "Pays a dividend", "events", "flag", "higher", "silver", "Yes if a dividend was declared in the last 12 months.", 0),
    M("bonus_3y", "Bonus issue in last 3 years", "events", "flag", "none", "silver", "Yes if bonus shares were issued in the last three years.", 0),
    M("split_3y", "Stock split in last 3 years", "events", "flag", "none", "silver", "Yes if shares were split in the last three years.", 0),
    M("buyback_3y", "Buyback in last 3 years", "events", "flag", "none", "silver", "Yes if the company bought back shares in the last three years.", 0),
    M("actions_1y", "Corporate actions in the last year", "events", "n", "none", "silver", "Count of dividends, bonus, splits and similar events in a year.", 0),
    # ---- Red Flags (1 = the warning applies)
    M("flag_loss", "Loss-making", "flags", "flag", "lower", "silver", "Yes if the latest year's net profit is negative.", 0),
    M("flag_cfo_negative", "Negative operating cash flow", "flags", "flag", "lower", "silver", "Yes if the business burned cash from operations last year.", 0),
    M("flag_cash_gap", "Profit not backed by cash", "flags", "flag", "lower", "silver", "Yes if cash profit is under half of reported profit.", 0),
    M("flag_high_debt", "High debt", "flags", "flag", "lower", "silver", "Yes if debt to equity is above 2.", 0),
    M("flag_weak_cover", "Weak interest cover", "flags", "flag", "lower", "silver", "Yes if operating profit covers interest less than 1.5 times.", 0),
    M("flag_profit_fall", "Profit fell sharply", "flags", "flag", "lower", "silver", "Yes if profit fell more than 20% in the latest year.", 0),
    M("flag_promoter_selling", "Promoters selling", "flags", "flag", "lower", "silver", "Yes if promoters cut their holding by more than 2 points in a year.", 0),
    M("flag_below_trend", "Far below long-term trend", "flags", "flag", "lower", "silver", "Yes if the price is over 20% below its 200-day average.", 0),
    M("flag_count", "Number of red flags", "flags", "n", "lower", "silver", "How many of the eight warnings apply.", 0),
    # ---- Banks & lenders
    M("is_bank", "Bank or lender", "banks", "flag", "none", "silver", "Yes for banks and lending companies, whose accounts follow different rules.", 0),
    M("interest_to_revenue", "Interest cost to income", "banks", "%", "lower", "silver", "Interest paid out of every ₹100 of income.", 0),
    # ---- Volume, range and trend
    M("volume", "Volume (latest day)", "trading", "n", "none", "silver", "Shares traded on the latest day.", 0),
    M("avg_volume_20d", "Average volume (20 days)", "trading", "n", "none", "silver", "Average shares traded per day over 20 days.", 0),
    M("volume_vs_avg", "Volume against 20-day average", "trading", "x", "none", "silver", "Today's volume as a multiple of the 20-day average.", 1),
    M("turnover_cr", "Traded value (latest day)", "trading", "Cr", "none", "silver", "Rupees changing hands on the latest day.", 1),
    M("high_52w", "52-week high", "trading", "Rs", "none", "silver", "Highest price in the last year.", 2),
    M("low_52w", "52-week low", "trading", "Rs", "none", "silver", "Lowest price in the last year.", 2),
    M("pct_from_high", "Below 52-week high", "trading", "%", "none", "silver", "How far the price is under its 52-week high.", 1),
    M("pct_from_low", "Above 52-week low", "trading", "%", "none", "silver", "How far the price is over its 52-week low.", 1),
    M("range_pos", "Position in 52-week range", "trading", "%", "none", "silver", "0 means at the 52-week low, 100 means at the high.", 0),
    M("near_high", "Near 52-week high", "trading", "flag", "none", "silver", "Yes if within 3% of the 52-week high.", 0),
    M("near_low", "Near 52-week low", "trading", "flag", "none", "silver", "Yes if within 3% of the 52-week low.", 0),
    M("vs_ema50", "Price against 50-day average", "trading", "%", "none", "silver", "How far the price is above (+) or below (−) its 50-day average.", 1),
    M("vs_ema200", "Price against 200-day average", "trading", "%", "none", "silver", "How far the price is above (+) or below (−) its 200-day average.", 1),
    M("rsi14", "RSI (14 days)", "trading", "pts", "none", "silver", "Momentum from 0 to 100. Under 30 is oversold, over 70 overbought.", 0),
    M("volatility", "Volatility (yearly)", "trading", "%", "lower", "silver", "How much the price swings in a year.", 0),
    M("max_drawdown", "Worst fall (since data starts)", "trading", "%", "higher", "silver", "Biggest drop from a peak to a low.", 0),
    # ---- FinLit model (Gold)
    M("overall", "FinLit score", "model", "pts", "higher", "gold", "Average of the five FinLit pillars, out of 100.", 0),
    M("pillar_quality", "Quality pillar", "model", "pts", "higher", "gold", "Return on money and how well profit turns into cash.", 0),
    M("pillar_growth", "Growth pillar", "model", "pts", "higher", "gold", "Sales and profit growth over the years.", 0),
    M("pillar_profitability", "Profitability pillar", "model", "pts", "higher", "gold", "Margins and returns on money.", 0),
    M("pillar_balance", "Balance sheet pillar", "model", "pts", "higher", "gold", "Debt, liquidity and interest cover.", 0),
    M("pillar_technical", "Technical pillar", "model", "pts", "higher", "gold", "Price trend and momentum.", 0),
    M("fundamental_score", "Fundamental score", "model", "pts", "higher", "gold", "Average of the four business pillars (no price trend).", 0),
    M("score_change", "Score change since last quarter", "model", "pts", "higher", "gold", "Points the FinLit score moved since the last quarter.", 0),
    M("strengths_count", "Strengths found", "model", "n", "higher", "gold", "How many strengths the FinLit model lists for the company.", 0),
    M("watchouts_count", "Watch-outs found", "model", "n", "lower", "gold", "How many watch-outs the FinLit model lists for the company.", 0),
]
BY_KEY: Dict[str, Metric] = {m.key: m for m in CATALOG}
# "Now / 3Y avg / 5Y avg / 7Y avg" tabs: base filter -> the filter behind each tab
VARIANTS: Dict[str, Dict[str, str]] = {b: {"now": b, "3y": f"{b}_avg_3y", "5y": f"{b}_avg_5y", "7y": f"{b}_avg_7y"} for b in ("pe", "pb", "ps")}
# Stored beside the filters in `scores.metrics` but not a filter: which quarter q_revenue and the other q_* figures are for (yyyymmdd).
INTERNAL_KEYS = {"q_period_end", "m_ver"}
HIDDEN = {v for tabs in VARIANTS.values() for k, v in tabs.items() if k != "now"}   # shown only through their tabs
RANK = {"basic": 0, "silver": 1, "gold": 2}

# Non-numeric filters
INDEX_LISTS = {  # code -> (label, niftyindices file)
    "NIFTY50": ("NIFTY 50", "ind_nifty50list"), "NIFTYNEXT50": ("NIFTY Next 50", "ind_niftynext50list"), "NIFTY100": ("NIFTY 100", "ind_nifty100list"),
    "NIFTY200": ("NIFTY 200", "ind_nifty200list"), "NIFTY500": ("NIFTY 500", "ind_nifty500list"), "NIFTYMIDCAP150": ("NIFTY Midcap 150", "ind_niftymidcap150list"),
    "NIFTYMIDCAP100": ("NIFTY Midcap 100", "ind_niftymidcap100list"), "NIFTYSMALLCAP250": ("NIFTY Smallcap 250", "ind_niftysmallcap250list"),
    "NIFTYSMALLCAP100": ("NIFTY Smallcap 100", "ind_niftysmallcap100list"), "NIFTYMIDSMALL400": ("NIFTY MidSmallcap 400", "ind_niftymidsmallcap400list"),
    "NIFTYLARGEMID250": ("NIFTY LargeMidcap 250", "ind_niftylargemidcap250list"), "NIFTYBANK": ("NIFTY Bank", "ind_niftybanklist"),
    "NIFTYIT": ("NIFTY IT", "ind_niftyitlist"), "NIFTYFMCG": ("NIFTY FMCG", "ind_niftyfmcglist"), "NIFTYPHARMA": ("NIFTY Pharma", "ind_niftypharmalist"),
    "NIFTYAUTO": ("NIFTY Auto", "ind_niftyautolist"),
    # sector indices for the dashboard's sectoral activity (a list the exchange does not publish under this name is skipped by the nightly job)
    "NIFTYFINSERVICE": ("NIFTY Financial Services", "ind_niftyfinancelist"), "NIFTYPVTBANK": ("NIFTY Private Bank", "ind_nifty_privatebanklist"),
    "NIFTYPSUBANK": ("NIFTY PSU Bank", "ind_niftypsubanklist"), "NIFTYENERGY": ("NIFTY Energy", "ind_niftyenergylist"), "NIFTYOILGAS": ("NIFTY Oil & Gas", "ind_niftyoilgaslist"),
    "NIFTYCONSUMERDURABLES": ("NIFTY Consumer Durables", "ind_niftyconsumerdurableslist"), "NIFTYHEALTHCARE": ("NIFTY Healthcare", "ind_niftyhealthcarelist"),
    "NIFTYINFRA": ("NIFTY Infrastructure", "ind_niftyinfralist"), "NIFTYMANUFACTURING": ("NIFTY India Manufacturing", "ind_niftyindiamanufacturinglist"),
    "NIFTYREALTY": ("NIFTY Realty", "ind_niftyrealtylist"), "NIFTYMEDIA": ("NIFTY Media", "ind_niftymedialist"), "NIFTYMETAL": ("NIFTY Metal", "ind_niftymetallist"),
    "NIFTYCOMMODITIES": ("NIFTY Commodities", "ind_niftycommoditieslist"),
}
CAPS = ("Large", "Mid", "Small")


def tier_of(key: str) -> str:
    return BY_KEY[key].tier


def allowed(plan: str, tier: str) -> bool:
    return RANK.get(plan, 0) >= RANK[tier]
