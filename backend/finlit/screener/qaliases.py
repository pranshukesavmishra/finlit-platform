"""Names a member may type for a metric in the query builder (finlit/screener/ql.py).

Built from the real catalogue, never typed by hand ratio by ratio: every metric answers to its key, its catalogue label, its glossary label and a curated
list of everyday names ("mcap", "P/E", "debt to equity", "sales growth 3 years"...). Matching ignores case, spacing and punctuation (`norm`), so
"P/E", "p e" and "PE" are one name. One name points at exactly one metric: a curated name that clashes with another is a programming error and stops
the import (and the tests), while a name made automatically (a label without its bracket, a glossary label) that clashes is dropped.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .catalog import BY_KEY, CATALOG, HIDDEN

_GLOSSARY = json.loads((Path(__file__).resolve().parent.parent / "normalize" / "glossary_data.json").read_text(encoding="utf-8"))
GLOSS: Dict[str, dict] = _GLOSSARY["metrics"]
TERMS: Dict[str, dict] = {t["id"]: t for t in _GLOSSARY["terms"]}


def norm(s: str) -> str:
    """Lower case letters and digits only: 'P/E Ratio' -> 'peratio'."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _period(bases: List[str], n: int, extra: List[str] = ()) -> List[str]:
    out = list(extra)
    for b in bases:
        out += [f"{b} {n} years", f"{b} {n} year", f"{b} {n}y", f"{n} year {b}", f"{n}y {b}", f"{b} {n} yr", f"{b} cagr {n} years", f"{b} cagr {n}y"]
    return out


SALES = ["sales growth", "revenue growth", "sales cagr", "revenue cagr"]
PROFIT = ["profit growth", "net profit growth", "pat growth", "profit cagr", "net profit cagr"]

CURATED: Dict[str, List[str]] = {
    "market_cap": ["market capitalization", "market capitalisation", "mcap", "mkt cap", "mktcap", "m cap"],
    "price": ["price", "current price", "cmp", "ltp", "stock price", "last traded price", "share price"],
    "enterprise_value": ["ev", "enterprise val"],
    "revenue": ["sales", "revenue", "annual sales", "annual revenue", "turnover sales", "sales latest year", "revenue latest year"],
    "net_profit": ["profit", "net profit", "pat", "profit after tax", "annual profit", "annual net profit", "net income"],
    "total_assets": ["assets", "total asset"],
    "book_value_ps": ["book value", "bvps", "bv per share", "book value ps", "bv"],
    "eps": ["eps", "earning per share", "earnings per share", "annual eps"],
    "ret_1d": ["1 day change", "day change", "change today", "daily change", "1d change", "1 day return", "1d return", "todays change", "price change today"],
    "ret_1m": ["1 month return", "1m return", "1 month change", "1m change", "return 1 month", "monthly return", "1 month price change"],
    "ret_3m": ["3 month return", "3m return", "3 month change", "return 3 months", "quarterly return"],
    "ret_6m": ["6 month return", "6m return", "6 month change", "return 6 months", "half yearly return"],
    "ret_1y": ["1 year return", "1y return", "1 year change", "1y change", "yearly return", "annual return", "return 1 year", "1 year price change"],
    "ret_3y": ["3 year return", "3y return", "3 year change", "return 3 years", "3y change"],
    "ret_5y": ["5 year return", "5y return", "5 year change", "return 5 years", "5y change"],
    "ret_1y_total": ["1 year total return", "1y total return", "total return 1 year", "total return 1y", "total return"],
    "pe": ["pe", "p/e", "p e", "pe ratio", "p/e ratio", "price to earning", "price to earnings", "price earnings", "price earning ratio", "price to earnings ratio",
           "price to earning ratio", "earnings multiple", "pe ttm", "p/e ttm"],
    "pb": ["pb", "p/b", "pb ratio", "p/b ratio", "price to book", "price to book value", "price book", "pbv", "p/bv", "price to book ratio", "price book value"],
    "ev_ebitda": ["ev/ebitda", "ev to ebitda", "ev by ebitda", "enterprise value to ebitda", "ev ebitda ratio"],
    "dividend_yield": ["div yield", "dividend yield %", "yield", "dividend yield ratio"],
    "peg": ["peg", "peg ratio", "price earnings growth"],
    "earnings_yield": ["earnings yield", "earning yield"],
    "graham_value": ["graham value", "graham number", "graham fair value", "graham"],
    "graham_upside": ["upside to graham value", "graham upside", "upside to graham", "upside graham"],
    "ev_cfo": ["ev/cfo", "ev to cfo", "ev to operating cash flow"],
    "ev_sales": ["ev/sales", "ev to sales", "ev sales ratio"],
    "ps": ["ps", "p/s", "ps ratio", "p/s ratio", "price to sales", "price/sales", "price sales", "price to sales ratio", "price sales ratio"],
    "price_cfo": ["price to cash flow", "p/cf", "price/cfo", "price to cfo", "price cash flow", "p/cfo"],
    "dividend_payout": ["dividend payout", "payout ratio", "payout", "dividend payout ratio"],
    "pfcf": ["p/fcf", "price to fcf", "price to free cash flow", "price/fcf", "pfcf ratio"],
    "fcf_yield": ["fcf yield", "free cash flow yield"],
    "sales_ps": ["sales per share", "revenue per share", "sales/share"],
    "cash_ps": ["cash per share", "cash/share"],
    "net_cash_ps": ["net cash per share", "net cash/share"],
    "fcf_ps": ["fcf per share", "free cash flow per share", "fcf/share"],
    "pe_vs_median_5y": ["pe vs 5y median", "pe vs own 5 year median", "pe vs median pe 5y", "pe against 5y median", "pe vs own median", "pe vs history"],
    "pe_median_5y": ["median pe", "median pe 5y", "median pe 5 years", "5y median pe", "5 year median pe"],
    "pb_vs_median_5y": ["pb vs 5y median", "pb vs own 5 year median", "pb vs own median", "pb vs history"],
    "pe_vs_sector": ["pe vs sector", "pe vs industry", "pe against sector", "pe vs sector pe", "pe relative to sector"],
    "pb_vs_sector": ["pb vs sector", "pb vs industry", "pb against sector", "pb relative to sector"],
    "price_to_tangible": ["market cap to assets", "mcap to assets", "market cap to total assets", "price to assets"],
    "roe": ["roe", "return on equity", "return on net worth", "ronw", "return on shareholders funds"],
    "roce": ["roce", "return on capital employed", "return on capital", "roic"],
    "roa": ["roa", "return on assets", "return on total assets"],
    "rota": ["rota", "return on tangible assets", "return on tangible asset"],
    "operating_margin": ["opm", "operating margin", "operating profit margin", "opm annual", "operating margin annual", "operating margin latest year", "ebit operating margin"],
    "op_profit": ["operating profit", "operating profit annual", "op profit", "annual operating profit"],
    "net_margin": ["npm", "net margin", "net profit margin", "profit margin", "pat margin"],
    "gross_margin": ["gross margin", "gross profit margin", "gpm"],
    "ebitda_margin": ["ebitda margin"],
    "ebit_margin": ["ebit margin"],
    "pretax_margin": ["pre tax margin", "pretax margin", "pbt margin", "profit before tax margin"],
    "tax_rate": ["tax rate", "effective tax rate", "tax"],
    "roe_3y": ["roe 3 year", "roe 3y", "3 year roe", "3y roe", "roe 3 year average", "roe 3y average", "roe 3y avg", "average roe 3 years", "3 year average roe", "3y avg roe",
               "roe avg 3y", "roe average 3 years"],
    "roce_3y": ["roce 3 year", "roce 3y", "3 year roce", "3y roce", "roce 3 year average", "roce 3y average", "roce 3y avg", "average roce 3 years", "3 year average roce",
                "3y avg roce", "roce avg 3y", "roce average 3 years"],
    "opm_3y": ["opm 3y", "opm 3 year", "3 year opm", "opm 3y average", "opm 3 year average", "operating margin 3 year average", "operating margin 3y average",
               "operating margin 3y", "3 year average operating margin", "3y avg opm"],
    "opm_change": ["opm change", "operating margin change", "change in opm", "change in operating margin", "opm change 1 year", "operating margin change 1 year"],
    "sales_growth": ["sales growth", "revenue growth", "sales growth latest year", "annual sales growth", "yearly sales growth", "sales growth yoy annual", "sales growth 1 year",
                     "sales growth 1y"],
    "profit_growth": ["profit growth", "net profit growth", "profit growth latest year", "annual profit growth", "yearly profit growth", "pat growth", "profit growth 1 year",
                      "profit growth 1y"],
    "op_profit_growth": ["operating profit growth", "op profit growth", "operating profit growth annual", "ebit growth"],
    "op_profit_cagr_3y": _period(["operating profit growth", "operating profit cagr", "op profit growth", "op profit cagr"], 3),
    "op_profit_cagr_5y": _period(["operating profit growth", "operating profit cagr", "op profit growth", "op profit cagr"], 5),
    "sales_cagr_3y": _period(SALES, 3),
    "sales_cagr_5y": _period(SALES, 5),
    "profit_cagr_3y": _period(PROFIT, 3),
    "profit_cagr_5y": _period(PROFIT, 5),
    "ebitda_cagr_5y": _period(["ebitda growth", "ebitda cagr"], 5),
    "eps_cagr_5y": _period(["eps growth", "eps cagr", "earnings growth"], 5),
    "cfo_cagr_3y": _period(["operating cash flow growth", "cfo growth", "cfo cagr", "operating cash flow cagr"], 3),
    "bv_cagr_5y": _period(["book value growth", "bv growth", "book value cagr", "bv cagr"], 5),
    "dps_cagr": ["dividend growth", "dps growth", "dps cagr", "dividend cagr", "yearly dividend growth"],
    "years_profit_up": ["years of profit growth", "years of rising profit", "years profit up", "profit growth years", "years of rising profits", "profit rising years"],
    "q_revenue": ["quarterly sales", "quarter sales", "latest quarter sales", "quarterly revenue", "latest quarter revenue", "q sales", "q revenue"],
    "q_net_profit": ["quarterly profit", "quarter profit", "latest quarter profit", "quarterly net profit", "latest quarter net profit", "q profit", "q net profit", "quarterly pat"],
    "q_operating_profit": ["quarterly operating profit", "latest quarter operating profit", "quarter operating profit", "q operating profit"],
    "q_eps": ["quarterly eps", "latest quarter eps", "quarter eps", "q eps"],
    "q_sales_yoy": ["quarterly sales growth", "quarterly sales growth yoy", "yoy sales growth", "yoy quarterly sales growth", "sales growth yoy", "sales growth yoy quarterly",
                    "quarter sales growth yoy", "qoq sales growth yoy"],
    "q_profit_yoy": ["quarterly profit growth", "quarterly profit growth yoy", "yoy profit growth", "yoy quarterly profit growth", "profit growth yoy", "profit growth yoy quarterly",
                     "quarter profit growth yoy"],
    "q_sales_qoq": ["qoq sales growth", "sales growth qoq", "quarter on quarter sales growth", "sequential sales growth", "quarterly sales growth qoq"],
    "q_profit_qoq": ["qoq profit growth", "profit growth qoq", "quarter on quarter profit growth", "sequential profit growth", "quarterly profit growth qoq"],
    "q_opm": ["quarterly opm", "latest quarter opm", "opm quarterly", "quarterly operating margin", "latest quarter operating margin", "q opm", "opm latest quarter"],
    "q_npm": ["quarterly npm", "latest quarter npm", "quarterly net margin", "latest quarter net margin", "q npm", "quarterly net profit margin"],
    "ttm_revenue": ["ttm sales", "ttm revenue", "sales ttm", "revenue ttm", "sales last 12 months", "sales last twelve months", "trailing sales"],
    "ttm_net_profit": ["ttm profit", "ttm net profit", "profit ttm", "net profit ttm", "profit last 12 months", "profit last twelve months", "ttm pat"],
    "ttm_eps": ["ttm eps", "eps ttm", "eps last 12 months", "trailing eps"],
    "q_sales_up": ["quarters of rising sales", "quarters sales up", "quarters of sales growth"],
    "q_profit_up": ["quarters of rising profit", "quarters profit up", "quarters of profit growth"],
    "debt_to_equity": ["debt to equity", "d/e", "de ratio", "d e", "debt/equity", "debt equity", "debt to equity ratio", "debt equity ratio", "dte", "gearing", "debt/equity ratio",
                       "total debt to equity"],
    "lt_debt_to_equity": ["long term debt to equity", "lt debt to equity", "long term debt/equity", "lt d/e", "long term d/e"],
    "net_debt_to_equity": ["net debt to equity", "net d/e", "net debt/equity", "net debt equity", "net gearing"],
    "net_debt_to_ebitda": ["net debt to ebitda", "net debt/ebitda", "net debt ebitda", "net debt by ebitda", "leverage ratio"],
    "net_debt": ["net debt", "net borrowings"],
    "borrowings": ["debt", "total debt", "borrowings", "total borrowing", "borrowing", "loans"],
    "cash": ["cash", "cash and equivalents", "cash and bank", "cash balance"],
    "cash_to_debt": ["cash to debt", "cash/debt", "cash debt ratio", "cash to borrowings"],
    "debt_to_fcf": ["debt to fcf", "debt/fcf", "debt to free cash flow", "debt fcf", "debt/free cash flow"],
    "interest_coverage": ["interest coverage", "interest cover", "icr", "interest coverage ratio", "interest cover ratio", "times interest earned", "tie"],
    "fcf": ["fcf", "free cash flow", "free cash flow latest year", "annual fcf", "annual free cash flow"],
    "cfo": ["cfo", "operating cash flow", "cash from operations", "cash flow from operations", "operating cash flow latest year", "annual cfo"],
    "current_ratio": ["current ratio"],
    "quick_ratio": ["quick ratio", "acid test ratio", "acid test"],
    "cash_to_current_liab": ["cash to current liabilities", "cash/current liabilities", "cash ratio"],
    "working_capital": ["working capital", "net working capital", "wc"],
    "working_capital_to_sales": ["working capital to sales", "working capital/sales", "wc to sales"],
    "debt_to_assets": ["debt to assets", "debt/assets", "debt assets", "debt to asset"],
    "liabilities_to_assets": ["liabilities to assets", "liabilities/assets", "liabilities assets"],
    "financial_leverage": ["financial leverage", "equity multiplier", "leverage"],
    "equity_ratio": ["equity ratio"],
    "equity": ["equity", "shareholders equity", "shareholders funds", "owners equity", "net worth", "networth", "total equity"],
    "asset_turnover": ["asset turnover", "asset turnover ratio", "assets turnover"],
    "fixed_asset_turnover": ["fixed asset turnover", "fixed assets turnover", "fat"],
    "inventory_days": ["inventory days", "inventory holding days", "days inventory", "dio"],
    "debtor_days": ["debtor days", "receivable days", "receivables days", "days sales outstanding", "dso", "debtors days"],
    "payable_days": ["payable days", "payables days", "creditor days", "creditors days", "dpo"],
    "cash_cycle": ["cash conversion cycle", "ccc", "cash cycle", "cash conversion cycle days"],
    "cfo_to_pat": ["cash conversion", "cfo to pat", "cfo/pat", "cash profit conversion", "cash conversion cfo pat", "cfo pat", "cfo to profit"],
    "fcf_to_pat": ["fcf to pat", "fcf/pat", "free cash flow to profit", "fcf to profit", "free cash flow to pat"],
    "capex_to_sales": ["capex to sales", "capex/sales", "capex sales", "capital spending to sales", "capex intensity"],
    "capex_to_cfo": ["capex to cfo", "capex/cfo", "capex to operating cash", "capital spending to operating cash"],
    "sales_per_employee": ["sales per employee", "revenue per employee", "sales/employee"],
    "profit_per_employee": ["profit per employee", "profit/employee"],
    "employees": ["employees", "employee count", "number of employees", "headcount"],
    "retention_ratio": ["retention ratio", "profit retained", "retention", "earnings retention"],
    "own_promoters": ["promoter holding", "promoters holding", "promoter stake", "promoter shareholding", "promoter", "promoters", "promoter ownership", "promoter holding %"],
    "own_fii": ["fii holding", "fii", "fpi holding", "fpi", "fii/fpi holding", "fii fpi holding", "foreign institutions", "foreign institutional holding", "foreign holding",
                "foreign investors holding", "fii stake"],
    "own_dii": ["dii holding", "dii", "domestic institutions", "domestic institutional holding", "dii stake", "domestic holding"],
    "own_public": ["public holding", "public shareholding", "retail holding", "public", "public stake", "retail and public holding"],
    "own_government": ["government holding", "govt holding", "government stake", "govt stake", "government shareholding"],
    "own_institutions": ["institutional holding", "all institutions", "institutions holding", "institutions", "total institutional holding", "fii and dii holding"],
    "own_promoters_chg_1y": ["promoter holding change", "promoter holding change 1 year", "change in promoter holding", "promoter holding change 1y", "promoter holding change yearly",
                             "promoter stake change", "promoter holding chg"],
    "own_fii_chg_1y": ["fii holding change", "fii holding change 1 year", "change in fii holding", "fii change", "fii holding change 1y", "fii stake change", "fii holding chg"],
    "own_dii_chg_1y": ["dii holding change", "dii holding change 1 year", "change in dii holding", "dii change", "dii holding change 1y", "dii stake change", "dii holding chg"],
    "own_public_chg_1y": ["public holding change", "public holding change 1 year", "change in public holding", "public change", "public holding change 1y"],
    "own_promoters_chg_1q": ["promoter holding change quarter", "promoter holding change last quarter", "promoter holding change 1q", "promoter holding change qoq",
                             "change in promoter holding last quarter"],
    "own_fii_chg_1q": ["fii holding change quarter", "fii holding change last quarter", "fii holding change 1q", "fii holding change qoq"],
    "own_dii_chg_1q": ["dii holding change quarter", "dii holding change last quarter", "dii holding change 1q", "dii holding change qoq"],
    "own_inst_chg_1y": ["institutions change", "institutional holding change", "institutions holding change", "institutional holding change 1 year", "change in institutional holding"],
    "div_ttm": ["dividend per share", "dps", "dividend ttm", "dividend last 12 months", "dividend per share ttm", "dividend rs"],
    "div_last_days": ["days since last dividend", "days since dividend", "last dividend days", "days from last dividend"],
    "div_years": ["years of dividends", "years of dividend", "dividend years", "dividend paying years", "years paying dividend", "dividend streak"],
    "div_paying": ["pays a dividend", "pays dividend", "dividend paying", "dividend payer", "pays dividends", "dividend paid", "has dividend"],
    "bonus_3y": ["bonus issue", "bonus in last 3 years", "bonus 3y", "bonus issue 3y", "recent bonus"],
    "split_3y": ["stock split", "split in last 3 years", "split 3y", "stock split 3y", "recent split"],
    "buyback_3y": ["buyback", "buy back", "buyback in last 3 years", "buyback 3y", "share buyback", "recent buyback"],
    "actions_1y": ["corporate actions", "corporate actions last year", "corporate actions 1 year", "corporate actions in last year", "actions 1y"],
    "flag_loss": ["loss making", "loss-making", "makes a loss", "is loss making", "loss"],
    "flag_cfo_negative": ["negative operating cash flow", "negative cfo", "cfo negative", "operating cash flow negative"],
    "flag_cash_gap": ["profit not backed by cash", "cash gap", "profit cash gap", "profit without cash"],
    "flag_high_debt": ["high debt", "high debt flag"],
    "flag_weak_cover": ["weak interest cover", "weak interest coverage", "weak cover"],
    "flag_profit_fall": ["profit fell sharply", "profit fall", "sharp profit fall", "profit fell"],
    "flag_promoter_selling": ["promoters selling", "promoter selling", "promoter sells"],
    "flag_below_trend": ["far below long term trend", "far below trend", "below long term trend", "below trend"],
    "flag_count": ["number of red flags", "red flags", "red flag count", "flags", "count of red flags", "red flag"],
    "is_bank": ["bank or lender", "is bank", "bank", "lender", "is a bank", "bank or nbfc", "is lender"],
    "interest_to_revenue": ["interest cost to income", "interest to income", "interest to revenue", "interest cost to revenue"],
    "volume": ["volume", "volume latest day", "trading volume", "shares traded", "volume today"],
    "avg_volume_20d": ["average volume", "avg volume", "average volume 20 days", "avg volume 20d", "20 day average volume", "20d average volume", "average volume 20d", "avg vol"],
    "volume_vs_avg": ["volume vs average", "volume against average", "volume spike", "volume vs avg", "volume against 20 day average", "relative volume"],
    "turnover_cr": ["traded value", "traded value latest day", "daily turnover", "turnover", "value traded", "traded turnover"],
    "high_52w": ["52 week high", "52w high", "52wk high", "52 weeks high", "yearly high", "year high", "52 week high price"],
    "low_52w": ["52 week low", "52w low", "52wk low", "52 weeks low", "yearly low", "year low", "52 week low price"],
    "pct_from_high": ["below 52 week high", "below 52w high", "% below 52 week high", "pct from high", "distance from 52 week high", "fall from 52 week high", "percent below high",
                      "below high", "down from 52 week high", "from 52 week high"],
    "pct_from_low": ["above 52 week low", "above 52w low", "% above 52 week low", "pct from low", "distance from 52 week low", "rise from 52 week low", "percent above low",
                     "above low", "up from 52 week low", "from 52 week low"],
    "range_pos": ["position in 52 week range", "52 week range position", "range position", "52w range position", "position in range"],
    "near_high": ["near 52 week high", "near 52w high", "near high", "close to 52 week high"],
    "near_low": ["near 52 week low", "near 52w low", "near low", "close to 52 week low"],
    "fno": ["fno", "f&o", "futures and options", "has f&o", "in f&o", "derivatives", "has futures and options", "f and o", "fo stock"],
    "vs_ema50": ["price vs 50 day average", "price vs 50 dma", "price vs 50 ema", "price against 50 dma", "vs 50 dma", "vs 50 day average", "price vs 50dma", "50 dma gap",
                 "price vs ema50", "price vs 50 day ema", "price above 50 dma", "distance from 50 dma"],
    "vs_ema200": ["price vs 200 day average", "price vs 200 dma", "price vs 200 ema", "price against 200 dma", "vs 200 dma", "vs 200 day average", "price vs 200dma", "200 dma gap",
                  "price vs ema200", "price vs 200 day ema", "price above 200 dma", "distance from 200 dma"],
    "rsi14": ["rsi", "rsi 14", "rsi14", "rsi 14 days", "relative strength index", "rsi 14 day"],
    "volatility": ["volatility", "yearly volatility", "annual volatility", "volatility yearly", "price volatility"],
    "max_drawdown": ["max drawdown", "maximum drawdown", "drawdown", "worst fall", "mdd"],
    "overall": ["finlit score", "overall score", "finlit overall", "overall", "score", "finlit rating score"],
    "pillar_quality": ["quality pillar", "quality score", "quality pillar score", "quality"],
    "pillar_growth": ["growth pillar", "growth score", "growth pillar score"],
    "pillar_profitability": ["profitability pillar", "profitability score", "profitability pillar score"],
    "pillar_balance": ["balance sheet pillar", "balance sheet score", "balance pillar", "balance pillar score"],
    "pillar_technical": ["technical pillar", "technical score", "technical pillar score"],
    "fundamental_score": ["fundamental score", "fundamentals score", "fundamental"],
    "score_change": ["score change", "score change since last quarter", "finlit score change", "change in score", "change in finlit score"],
    "strengths_count": ["strengths found", "strengths count", "number of strengths", "strengths"],
    "watchouts_count": ["watch outs found", "watchouts found", "watch outs count", "number of watch outs", "watchouts", "watch outs", "watch-outs"],
}
# The P/E, P/B and P/S "average" tabs the screener hides behind "Now / 3Y / 5Y / 7Y": here they are ordinary names.
for _base, _words in (("pe", ["pe", "p/e", "price to earnings"]), ("pb", ["pb", "p/b", "price to book"]), ("ps", ["ps", "p/s", "price to sales"])):
    for _n in (3, 5, 7):
        CURATED[f"{_base}_avg_{_n}y"] = [f"{w} {_n} year average" for w in _words] + [f"{w} {_n}y average" for w in _words] + [f"{w} {_n}y avg" for w in _words] + \
            [f"{_n} year average {w}" for w in _words] + [f"{_n}y avg {w}" for w in _words] + [f"average {w} {_n} years" for w in _words] + [f"{w} avg {_n}y" for w in _words]

# Words that are units after a number, never part of a ratio name.
UNIT_WORDS = {"cr": "Cr", "crore": "Cr", "crores": "Cr", "lakh": "lakh", "lakhs": "lakh", "lac": "lakh", "lacs": "lakh", "x": "x", "times": "x", "days": "d", "day": "d"}


def _variants(m) -> List[str]:
    """Names made from the catalogue itself (priority order): the key, the label, the label without its bracket, the glossary label."""
    key = m.key.replace("_", " ")
    out = [key, m.label]
    nob = re.sub(r"\s*\([^)]*\)", "", m.label).strip()
    if nob and nob != m.label:
        out.append(nob)
    g = GLOSS.get(m.key, {}).get("label")
    if g:
        out.append(g)
        out.append(re.sub(r"\s*\([^)]*\)", "", g).strip())
    return out


def _build() -> Tuple[Dict[str, str], Dict[str, str], List[str], List[Tuple[str, str, str]]]:
    alias: Dict[str, str] = {}
    text: Dict[str, str] = {}
    problems: List[str] = []
    dropped: List[Tuple[str, str, str]] = []

    def put(name: str, key: str, strict: bool) -> None:
        n = norm(name)
        if not n:
            return
        have = alias.get(n)
        if have is None:
            alias[n] = key
            text[n] = name
        elif have != key:
            if strict:
                problems.append(f"{name!r} -> {key} clashes with {have}")
            else:
                dropped.append((name, key, have))

    # 1. the key and the catalogue label are the contract: they may never clash
    for m in CATALOG:
        put(m.key.replace("_", " "), m.key, True)
        put(m.label, m.key, True)
    # 2. curated names: must not clash with anything
    for m in CATALOG:
        for a in CURATED.get(m.key, []):
            put(a, m.key, True)
    # 3. automatic names: dropped quietly if they would be ambiguous
    for m in CATALOG:
        for a in _variants(m):
            put(a, m.key, False)
    return alias, text, problems, dropped


ALIAS, ALIAS_TEXT, PROBLEMS, DROPPED = _build()
if PROBLEMS:   # an ambiguous name is a bug in this file, never something a member should meet
    raise RuntimeError("ambiguous metric names: " + "; ".join(PROBLEMS))
assert set(CURATED) <= set(BY_KEY), set(CURATED) - set(BY_KEY)
# Every prefix of every name: lets the parser walk a typed phrase one word at a time and stop at the first word that cannot continue any name.
PREFIXES: Set[str] = {n[:i] for n in ALIAS for i in range(1, len(n) + 1)}
BY_KEY_ALIASES: Dict[str, List[str]] = {}
for _n, _k in ALIAS.items():
    BY_KEY_ALIASES.setdefault(_k, []).append(_n)


def display_names(key: str, limit: int = 8) -> List[str]:
    """Names to show a member for a metric: the label first, then the everyday short names (spelling as written above)."""
    m = BY_KEY[key]
    seen = {norm(m.label)}
    out = [m.label]
    g = GLOSS.get(key, {}).get("label")
    cands = ([g] if g else []) + CURATED.get(key, [])
    for a in cands:
        n = norm(a)
        if n and n not in seen and ALIAS.get(n) == key:
            seen.add(n)
            out.append(a)
    return out[:limit]


def definition(key: str) -> str:
    """One line from the glossary (what the figure is), else the catalogue's plain-words hint."""
    g = GLOSS.get(key, {})
    return (g.get("what") or BY_KEY[key].say or "").strip()


HIDDEN_KEYS = HIDDEN
