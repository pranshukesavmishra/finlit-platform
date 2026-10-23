"""One flat dict of screener metrics per company, worked out from the stored snapshot sections (no provider calls).

Everything here is plain arithmetic on figures the company page already shows, so the screener and the page always agree.
A metric that cannot be worked out is simply left out (None), never guessed.
"""

from __future__ import annotations

import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..advanced.derive import latest as ax_latest

Num = Optional[float]
METRICS_VERSION = 3.0   # 3: advanced-chart figures (ax_*); 2: annual operating profit metrics
MULTIPLES = ("pe", "pb", "ps", "pfcf", "ev_ebitda", "ev_sales", "ev_cfo", "price_cfo", "peg", "price_to_tangible")


def _n(v: Any) -> Num:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _div(a: Num, b: Num, scale: float = 1.0) -> Num:
    return None if a is None or b is None or b == 0 else a / b * scale


def _sub(a: Num, b: Num) -> Num:
    return None if a is None or b is None else a - b


def _add(*xs: Num) -> Num:
    return None if any(x is None for x in xs) else sum(xs)  # type: ignore[arg-type]


def _growth(a: Num, b: Num) -> Num:
    """Percent change from b to a; undefined when the base is zero or negative (a swing from a loss is not 'growth')."""
    return None if a is None or b is None or b <= 0 else (a - b) / b * 100


def _cagr(a: Num, b: Num, years: int) -> Num:
    if a is None or b is None or a <= 0 or b <= 0 or years <= 0:
        return None
    return ((a / b) ** (1.0 / years) - 1) * 100


def _row(table: Dict[str, Any], key: str) -> List[Num]:
    return [_n(v) for v in ((table or {}).get("rows") or {}).get(key) or []]


def _last(xs: Sequence[Num], back: int = 0) -> Num:
    return xs[-1 - back] if len(xs) > back else None


def _mean(xs: Sequence[Num]) -> Num:
    v = [x for x in xs if x is not None]
    return sum(v) / len(v) if v else None


def _median(xs: Sequence[float]) -> Num:
    v = sorted(xs)
    n = len(v)
    return None if not n else (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2)


def _flag(cond: Optional[bool]) -> Num:
    return None if cond is None else (1.0 if cond else 0.0)


def _pct_diff(now: Num, avg: Num) -> Num:
    return None if now is None or avg is None or avg <= 0 else (now - avg) / avg * 100


QUARTER_KEYS = ("q_revenue", "q_net_profit", "q_operating_profit", "q_eps", "q_sales_yoy", "q_profit_yoy", "q_sales_qoq", "q_profit_qoq", "q_opm", "q_npm", "q_period_end")


def _ymd(v: Any) -> Num:
    """'2026-09-30' -> 20260930.0 (a number, so it sits in the metrics beside the rest and compares with < and >)."""
    try:
        d = datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return float(d.year * 10000 + d.month * 100 + d.day)


def quarter_block(qpl: Dict[str, Any], at: Optional[date] = None, tolerance_days: int = 10) -> Dict[str, Num]:
    """The quarterly-results figures (revenue, profit, margins, growth against last year and last quarter) for ONE quarter of a company's
    quarterly profit & loss table: the newest one, or the one ending on `at` (within `tolerance_days`). `q_period_end` says which quarter
    these numbers are for (yyyymmdd), so a reader can tell last quarter's figures from this quarter's. Empty when `at` is not in the table."""
    ends = [str(e)[:10] if e else None for e in (qpl or {}).get("periodEnds") or []]
    qrev, qnp, qop, qeps = (_row(qpl, k) for k in ("revenue", "net_profit", "operating_profit", "eps"))
    if at is None:
        i = (len(ends) or len(qrev)) - 1
    else:
        best: Optional[Tuple[int, int]] = None
        for j, e in enumerate(ends):
            try:
                gap = abs((datetime.strptime(e, "%Y-%m-%d").date() - at).days) if e else None
            except ValueError:
                gap = None
            if gap is not None and gap <= tolerance_days and (best is None or gap < best[0]):
                best = (gap, j)
        if best is None:
            return {}
        i = best[1]

    def at_(xs: Sequence[Num], back: int = 0) -> Num:
        j = i - back
        return xs[j] if 0 <= j < len(xs) else None

    return {
        "q_revenue": at_(qrev), "q_net_profit": at_(qnp), "q_operating_profit": at_(qop), "q_eps": at_(qeps),
        "q_sales_yoy": _growth(at_(qrev), at_(qrev, 4)), "q_profit_yoy": _growth(at_(qnp), at_(qnp, 4)),
        "q_sales_qoq": _growth(at_(qrev), at_(qrev, 1)), "q_profit_qoq": _growth(at_(qnp), at_(qnp, 1)),
        "q_opm": _div(at_(qop), at_(qrev), 100), "q_npm": _div(at_(qnp), at_(qrev), 100),
        "q_period_end": _ymd(ends[i]) if 0 <= i < len(ends) else None,
    }


def compute(sections: Dict[str, dict], today: Optional[date] = None) -> Dict[str, Num]:
    today = today or date.today()
    out: Dict[str, Num] = {}
    summary = sections.get("summary") or {}
    fin = sections.get("financials") or {}
    ratios = sections.get("ratios") or {}
    own = sections.get("ownership") or {}
    events = sections.get("events") or {}
    price_sec = sections.get("price") or {}
    stats = sections.get("stats") or {}
    profile, quote = summary.get("profile") or {}, summary.get("quote") or {}
    latest = {k: _n(v.get("value")) for k, v in (ratios.get("latest") or {}).items() if isinstance(v, dict)}
    spans = {k: v.get("period") for k, v in (ratios.get("latest") or {}).items() if isinstance(v, dict)}   # e.g. "4Y": how many years a growth rate really covers
    hist = (ratios.get("history") or {}).get("rows") or {}
    yearly = fin.get("yearly") or {}
    pl, bs, cf, qpl = yearly.get("pl") or {}, yearly.get("bs") or {}, yearly.get("cf") or {}, (fin.get("quarterly") or {}).get("pl") or {}

    def hrow(key: str) -> List[Num]:
        return [_n(v) for v in hist.get(key) or []]

    # ---------------- statements, latest year
    rev, np_, op, ebt, fcost, dep = (_row(pl, k) for k in ("revenue", "net_profit", "operating_profit", "profit_before_tax", "finance_costs", "depreciation"))
    if _row(pl, "net_profit_continuing"):   # profit that will not repeat (a demerger gain) is not what the business earns: judge it on continuing profit
        np_ = _row(pl, "net_profit_continuing")
    eps_row = _row(pl, "eps")
    equity, borrow, cash, cur_a, cur_l, assets, inv, recv, fixed, invest = (_row(bs, k) for k in ("total_equity", "borrowings", "cash", "current_assets", "current_liabilities", "total_assets", "inventories", "receivables", "fixed_assets", "investments"))
    cfo_r, capex_r, fcf_r = _row(cf, "operating"), _row(cf, "capex"), _row(cf, "free_cash_flow")
    rev0, np0, op0 = _last(rev), _last(np_), _last(op)
    eq0, debt0, cash0, assets0 = _last(equity), _last(borrow), _last(cash), _last(assets)
    if debt0 is None and eq0 is not None:
        debt0 = 0.0   # a balance sheet that lists no borrowings is a company with none (the provider sends nothing, not zero)
    cfo0, fcf0 = _last(cfo_r), _last(fcf_r)
    capex0 = _n(abs(_last(capex_r))) if _last(capex_r) is not None else None
    market_cap = _n(quote.get("marketCapCr")) or _n(profile.get("marketCapCr")) or latest.get("market_cap")
    price = _n(quote.get("price"))

    out["market_cap"], out["price"] = market_cap, price
    out["revenue"], out["net_profit"], out["total_assets"] = rev0, np0, assets0
    np_rep0 = _last(_row(pl, "net_profit"))
    out["eps"] = _last(eps_row)
    if _row(pl, "net_profit_continuing") and np_rep0 and _last(eps_row) is not None:
        out["eps"] = round(_last(eps_row) * np0 / np_rep0, 2) if np0 is not None else None   # EPS on continuing profit, the same share count
    shares_row = _row(pl, "diluted_shares_cr")
    shares = _last(shares_row) if _last(shares_row) else _div(np_rep0, _last(eps_row))   # crore shares: reported, else profit / EPS
    out["book_value_ps"] = _div(eq0, shares)
    net_debt = _sub(debt0, cash0 or 0.0) if debt0 is not None else None   # borrowings less cash: the same definition the report's EV/EBITDA uses
    out["net_debt"] = net_debt
    out["enterprise_value"] = _add(market_cap, net_debt) if market_cap is not None and net_debt is not None else None
    out["borrowings"], out["cash"], out["equity"], out["fcf"], out["cfo"] = debt0, cash0, eq0, fcf0, cfo0

    # ---------------- returns
    rets = {r.get("period"): r for r in summary.get("returns") or [] if isinstance(r, dict)}
    out["ret_1d"] = _n(quote.get("changePct"))
    for key, per in (("ret_1m", "1M"), ("ret_3m", "3M"), ("ret_6m", "6M"), ("ret_1y", "1Y"), ("ret_3y", "3Y"), ("ret_5y", "5Y")):
        out[key] = _n((rets.get(per) or {}).get("price"))
    out["ret_1y_total"] = _n((rets.get("1Y") or {}).get("total"))

    # ---------------- valuation
    pe, pb, ps = latest.get("pe"), latest.get("pb"), latest.get("ps")
    out.update(pe=pe, pb=pb, ps=ps, pfcf=latest.get("pfcf"), ev_ebitda=latest.get("ev_ebitda"), dividend_yield=latest.get("dividend_yield"),
               dividend_payout=latest.get("dividend_payout"))
    # The provider's ratios are as of the last full load; between loads the price moves. Scale the price-based ones by how far it moved.
    ref = _n(quote.get("refPrice"))
    f = price / ref if price and ref and ref > 0 else None
    if f and abs(f - 1) > 1e-9:
        for k in ("pe", "pb", "ps", "pfcf"):
            out[k] = out[k] * f if out.get(k) is not None else None
        out["dividend_yield"] = out["dividend_yield"] / f if out.get("dividend_yield") is not None else None
        if out.get("ev_ebitda") is not None and market_cap and net_debt is not None and market_cap / f + net_debt > 0:
            out["ev_ebitda"] *= (market_cap + net_debt) / (market_cap / f + net_debt)
        pe = out["pe"]; pb = out["pb"]
    out["ev_sales"] = _div(out["enterprise_value"], rev0)
    out["ev_cfo"] = _div(out["enterprise_value"], cfo0) if cfo0 and cfo0 > 0 else None
    out["price_cfo"] = _div(market_cap, cfo0) if cfo0 and cfo0 > 0 else None
    out["sales_ps"] = _div(rev0, shares)
    out["fcf_ps"] = _div(fcf0, shares)
    out["cash_ps"] = _div(cash0, shares)
    out["net_cash_ps"] = _div(-net_debt, shares) if net_debt is not None else None
    eps0, bvps = out["eps"], out["book_value_ps"]
    graham = (22.5 * eps0 * bvps) ** 0.5 if eps0 and bvps and eps0 > 0 and bvps > 0 else None   # Benjamin Graham: sqrt(22.5 x EPS x book value per share)
    out["graham_value"] = graham
    out["graham_upside"] = _div(_sub(graham, price), price, 100) if graham and price else None
    out["earnings_yield"] = _div(1.0, pe, 100) if pe and pe > 0 else None
    out["fcf_yield"] = _div(fcf0, market_cap, 100)
    pcagr = latest.get("profit_cagr_5y") or latest.get("profit_cagr")
    out["peg"] = _div(pe, pcagr) if pe and pe > 0 and pcagr and pcagr > 0 else None
    vh = (ratios.get("valuationHistory") or {}).get("rows") or {}
    # yearly readings of P/E, P/B and P/S (newest last): averages over the last 3, 5 and 7 years, and the 5-year median
    medians: Dict[str, Num] = {}
    for key in ("pe", "pb", "ps"):
        series = [x for x in (_n(v) for v in vh.get(key) or []) if x is not None and x > 0]
        for years in (3, 5, 7):
            if len(series) >= min(years, 3):
                out[f"{key}_avg_{years}y"] = _mean(series[-years:])
        if len(series) >= 3:
            medians[key] = _median(series[-5:])
    out["pe_median_5y"] = medians.get("pe")
    out["pe_vs_median_5y"] = _pct_diff(pe, medians.get("pe"))
    out["pb_vs_median_5y"] = _pct_diff(pb, medians.get("pb"))
    out["price_to_tangible"] = _div(market_cap, assets0)

    for k in MULTIPLES:  # a loss-maker's P/E or a negative-equity P/B is not a "cheap" number, it is no number
        if out.get(k) is not None and out[k] <= 0:
            out[k] = None

    # ---------------- profitability
    for k, src in (("roe", "roe"), ("roce", "roce"), ("roa", "roa"), ("rota", "rota"), ("gross_margin", "gross_margin"), ("ebitda_margin", "ebitda_margin"),
                   ("ebit_margin", "ebit_margin"), ("pretax_margin", "pretax_margin"), ("tax_rate", "effective_tax_rate")):
        out[k] = latest.get(src)
    # the margins the FinLit score uses (operating profit before depreciation and interest, and profit attributable to shareholders, over sales),
    # so the screener, the report and the score all show the same number
    out["operating_margin"] = latest.get("opm") if latest.get("opm") is not None else latest.get("operating_margin")
    out["net_margin"] = latest.get("npm") if latest.get("npm") is not None else latest.get("net_margin")
    opm_series = [_div(o, r, 100) for o, r in zip(op, rev)]
    out["roe_3y"], out["roce_3y"] = _mean(hrow("roe")[-3:]), _mean(hrow("roce")[-3:])
    out["opm_3y"] = _mean(opm_series[-3:])
    out["opm_change"] = _sub(_last(opm_series), _last(opm_series, 1))

    # ---------------- growth
    out["sales_growth"] = latest.get("sales_growth_latest") if latest.get("sales_growth_latest") is not None else _growth(rev0, _last(rev, 1))
    out["profit_growth"] = latest.get("profit_growth_latest") if latest.get("profit_growth_latest") is not None else _growth(np0, _last(np_, 1))
    out["sales_cagr_3y"] = latest.get("revenue_cagr_3y") if latest.get("revenue_cagr_3y") is not None else _cagr(rev0, _last(rev, 3), 3)
    out["sales_cagr_5y"] = latest.get("revenue_cagr_5y") if latest.get("revenue_cagr_5y") is not None else (latest.get("sales_cagr") if latest.get("sales_cagr") is not None and spans.get("sales_cagr") in (None, "5Y") else _cagr(rev0, _last(rev, 5), 5))
    out["profit_cagr_3y"] = latest.get("profit_cagr_3y") if latest.get("profit_cagr_3y") is not None else _cagr(np0, _last(np_, 3), 3)
    out["profit_cagr_5y"] = latest.get("profit_cagr_5y") if latest.get("profit_cagr_5y") is not None else (latest.get("profit_cagr") if latest.get("profit_cagr") is not None and spans.get("profit_cagr") in (None, "5Y") else _cagr(np0, _last(np_, 5), 5))
    # operating profit, ANNUAL (the quarterly one is q_operating_profit): straight from the yearly P&L, so it agrees with the report
    out["op_profit"] = op0
    out["op_profit_growth"] = _growth(op0, _last(op, 1))
    out["op_profit_cagr_3y"] = _cagr(op0, _last(op, 3), 3)
    out["op_profit_cagr_5y"] = _cagr(op0, _last(op, 5), 5)
    out["ebitda_cagr_5y"], out["eps_cagr_5y"], out["cfo_cagr_3y"] = latest.get("ebitda_cagr_5y"), latest.get("eps_cagr_5y"), latest.get("cfo_cagr_3y")
    out["bv_cagr_5y"] = latest.get("book_value_cagr_5y")
    dv = events.get("dividendsByFY") or {}
    by_fy = {int(p[2:]): _n(x) for p, x in zip(dv.get("periods") or [], dv.get("dps") or []) if p not in (dv.get("partial") or []) and str(p)[2:].isdigit()}
    last_fy = int(str(dv.get("endedFY") or "FY0")[2:] or 0)
    if last_fy and not by_fy.get(last_fy) and today.month <= 8:
        last_fy -= 1   # the final dividend for the year just ended is usually declared in May to July
    dps = [by_fy.get(y) or 0.0 for y in range(last_fy - 5, last_fy + 1)] if by_fy and last_fy else []
    first_y = next((y for y in range(last_fy - 5, last_fy + 1) if (by_fy.get(y) or 0) > 0), None) if dps else None
    out["dps_cagr"] = _cagr(by_fy.get(last_fy), by_fy.get(first_y), last_fy - first_y) if first_y is not None and last_fy > first_y and (by_fy.get(last_fy) or 0) > 0 else None
    last5 = np_[-6:]
    out["years_profit_up"] = float(sum(1 for a, b in zip(last5[1:], last5[:-1]) if a is not None and b is not None and a > b)) if len([x for x in last5 if x is not None]) >= 4 else None

    # ---------------- quarterly results
    qrev, qnp, qop, qeps = (_row(qpl, k) for k in ("revenue", "net_profit", "operating_profit", "eps"))
    out.update(quarter_block(qpl))
    out["ttm_revenue"] = sum(qrev[-4:]) if len(qrev) >= 4 and None not in qrev[-4:] else None  # type: ignore[arg-type]
    out["ttm_net_profit"] = sum(qnp[-4:]) if len(qnp) >= 4 and None not in qnp[-4:] else None  # type: ignore[arg-type]
    out["ttm_eps"] = sum(qeps[-4:]) if len(qeps) >= 4 and None not in qeps[-4:] else None  # type: ignore[arg-type]
    if len(qrev) >= 8:
        out["q_sales_up"] = float(sum(1 for i in range(1, 5) if qrev[-i] is not None and qrev[-i - 4] is not None and qrev[-i] > qrev[-i - 4]))
    if len(qnp) >= 8:
        out["q_profit_up"] = float(sum(1 for i in range(1, 5) if qnp[-i] is not None and qnp[-i - 4] is not None and qnp[-i] > qnp[-i - 4]))

    # ---------------- health, liquidity, solvency
    out["debt_to_equity"], out["lt_debt_to_equity"] = latest.get("debt_to_equity"), latest.get("lt_debt_to_equity")
    out["interest_coverage"] = latest.get("interest_coverage")
    out["debt_to_fcf"] = latest.get("debt_to_fcf")
    out["net_debt_to_equity"] = _div(net_debt, eq0) if eq0 is not None and eq0 > 0 else None
    ebitda0 = op0   # operating profit here is already before depreciation and interest, so it is the EBITDA
    out["net_debt_to_ebitda"] = _div(net_debt, ebitda0) if net_debt is not None and ebitda0 and ebitda0 > 0 else None
    out["cash_to_debt"] = _div(cash0, debt0)
    out["current_ratio"], out["quick_ratio"] = latest.get("current_ratio"), latest.get("quick_ratio")
    out["cash_to_current_liab"] = _div(cash0, _last(cur_l))
    out["working_capital"] = _sub(_last(cur_a), _last(cur_l))
    out["working_capital_to_sales"] = _div(out["working_capital"], rev0, 100)
    out["debt_to_assets"], out["liabilities_to_assets"], out["financial_leverage"] = latest.get("debt_to_assets"), latest.get("liabilities_to_assets"), latest.get("financial_leverage")
    out["equity_ratio"] = _div(eq0, assets0, 100)

    # ---------------- efficiency
    out["asset_turnover"] = latest.get("asset_turnover") if latest.get("asset_turnover") is not None else _div(rev0, assets0)
    out["fixed_asset_turnover"] = _div(rev0, _last(fixed))
    out["inventory_days"], out["debtor_days"], out["payable_days"] = latest.get("inventory_days"), latest.get("debtor_days"), latest.get("payable_days")
    out["cash_cycle"], out["retention_ratio"] = latest.get("cash_conversion_cycle"), latest.get("retention_ratio")
    out["cfo_to_pat"] = latest.get("cfo_to_pat") if latest.get("cfo_to_pat") is not None else (_div(cfo0, np0, 100) if np0 and np0 > 0 else None)
    out["fcf_to_pat"] = latest.get("fcf_to_pat") if latest.get("fcf_to_pat") is not None else (_div(fcf0, np0, 100) if np0 and np0 > 0 else None)
    out["capex_to_sales"], out["capex_to_cfo"] = _div(capex0, rev0, 100), _div(capex0, cfo0, 100)
    emp = _n(profile.get("employees"))
    out["employees"] = emp
    out["sales_per_employee"] = _div(rev0, emp) if emp and emp > 0 else None
    out["profit_per_employee"] = _div(np0, emp) if emp and emp > 0 else None

    # ---------------- ownership
    series = own.get("series") or {}
    latest_own = {x.get("key"): x for x in own.get("latest") or [] if isinstance(x, dict)}
    for k in ("promoters", "fii", "dii", "public", "government"):
        out[f"own_{k}"] = _n((latest_own.get(k) or {}).get("value"))
    for k in ("promoters", "fii", "dii", "public"):
        out[f"own_{k}_chg_1y"] = _n((latest_own.get(k) or {}).get("change1yPts"))
        s = [_n(x) for x in series.get(k) or []]
        out[f"own_{k}_chg_1q"] = _sub(_last(s), _last(s, 1)) if k != "public" else None
    out["own_institutions"] = _add(out["own_fii"], out["own_dii"]) if out["own_fii"] is not None and out["own_dii"] is not None else None
    out["own_inst_chg_1y"] = _add(out["own_fii_chg_1y"], out["own_dii_chg_1y"]) if out["own_fii_chg_1y"] is not None and out["own_dii_chg_1y"] is not None else None

    # ---------------- events
    actions = [a for a in events.get("actions") or [] if isinstance(a, dict) and a.get("date")]

    def days_ago(a: dict) -> Optional[int]:
        try:
            return (today - datetime.strptime(str(a["date"])[:10], "%Y-%m-%d").date()).days
        except ValueError:
            return None

    divs = [(a, days_ago(a)) for a in actions if "dividend" in str(a.get("type", ""))]
    past_divs = [(a, d) for a, d in divs if d is not None and d >= 0]
    ttm = [a for a, d in past_divs if d <= 365]
    out["div_ttm"] = sum(_n(a.get("adjustedAmount") or a.get("amount")) or 0.0 for a in ttm) if past_divs else None
    out["div_last_days"] = float(min(d for _, d in past_divs)) if past_divs else None
    out["div_years"] = float(sum(1 for x in dps if x and x > 0)) if dps else None
    out["div_paying"] = _flag(bool(ttm)) if actions or dps else None
    has_data = bool(actions)
    out["bonus_3y"] = _flag(any("bonus" in str(a.get("type", "")) and 0 <= (days_ago(a) or -1) <= 1095 for a in actions)) if has_data else None
    out["split_3y"] = _flag(any("split" in str(a.get("type", "")) and 0 <= (days_ago(a) or -1) <= 1095 for a in actions)) if has_data else None
    out["buyback_3y"] = _flag(any("buyback" in str(a.get("type", "")) and 0 <= (days_ago(a) or -1) <= 1095 for a in actions)) if has_data else None
    out["actions_1y"] = float(sum(1 for a in actions if 0 <= (days_ago(a) or -1) <= 365)) if has_data else None

    # ---------------- trading, range, trend
    daily = price_sec.get("daily") or {}
    closes, vols = [_n(x) for x in daily.get("c") or []], [_n(x) for x in daily.get("v") or []]
    tech = price_sec.get("technical") or {}
    out["volume"] = _n(quote.get("volume")) or _last(vols)
    v20 = [x for x in vols[-21:-1] if x is not None]
    out["avg_volume_20d"] = sorted(v20)[len(v20) // 2] if len(v20) >= 10 else None   # the median day: one huge block-deal day must not set the "usual" volume
    out["volume_vs_avg"] = _div(out["volume"], out["avg_volume_20d"])
    out["turnover_cr"] = _div(_n(price) * out["volume"], 1e7) if price is not None and out["volume"] is not None else None
    hi, lo = _n(quote.get("high52")) or _n((summary.get("range52") or {}).get("high")), _n(quote.get("low52")) or _n((summary.get("range52") or {}).get("low"))
    out["high_52w"], out["low_52w"] = hi, lo
    out["pct_from_high"] = _div(_sub(hi, price), hi, 100) if hi and price is not None else None
    out["pct_from_low"] = _div(_sub(price, lo), lo, 100) if lo and price is not None else None
    out["range_pos"] = _div(_sub(price, lo), _sub(hi, lo), 100) if hi is not None and lo is not None and hi > lo and price is not None else None
    out["near_high"] = _flag(out["pct_from_high"] <= 3) if out["pct_from_high"] is not None else None
    out["near_low"] = _flag(out["pct_from_low"] <= 3) if out["pct_from_low"] is not None else None
    out["vs_ema50"], out["vs_ema200"], out["rsi14"] = _n(tech.get("vsEma50Pct")), _n(tech.get("vsEma200Pct")), _n(tech.get("rsi14"))
    out["volatility"] = _n((stats.get("volatility") or {}).get("current"))
    out["max_drawdown"] = _n((stats.get("drawdown") or {}).get("max"))

    # ---------------- banks
    is_bank = bool((summary.get("dataQuality") or {}).get("isBank"))
    out["is_bank"] = _flag(is_bank)
    out["interest_to_revenue"] = _div(_last(fcost), _n(_last(_row(pl, "total_income"))) or rev0, 100)

    # ---------------- red flags
    out["flag_loss"] = _flag(np0 < 0) if np0 is not None else None
    out["flag_cfo_negative"] = _flag(cfo0 < 0) if cfo0 is not None else None
    out["flag_cash_gap"] = _flag(out["cfo_to_pat"] < 50) if out["cfo_to_pat"] is not None and np0 and np0 > 0 else None
    out["flag_high_debt"] = _flag(out["debt_to_equity"] > 2) if out["debt_to_equity"] is not None and not is_bank else None
    out["flag_weak_cover"] = _flag(out["interest_coverage"] < 1.5) if out["interest_coverage"] is not None and not is_bank else None
    pg = _growth(np0, _last(np_, 1)) if _last(np_, 1) and _last(np_, 1) > 0 and np0 is not None else None
    out["flag_profit_fall"] = _flag(pg < -20) if pg is not None else None
    out["flag_promoter_selling"] = _flag(out["own_promoters_chg_1y"] < -2) if out["own_promoters_chg_1y"] is not None else None
    out["flag_below_trend"] = _flag(out["vs_ema200"] < -20) if out["vs_ema200"] is not None else None
    fl = [out[k] for k in ("flag_loss", "flag_cfo_negative", "flag_cash_gap", "flag_high_debt", "flag_weak_cover", "flag_profit_fall", "flag_promoter_selling", "flag_below_trend")]
    out["flag_count"] = float(sum(1 for x in fl if x)) if sum(1 for x in fl if x is not None) >= 4 else None
    if is_bank:   # see snapshot.NOT_FOR_LENDERS: a lender's debt, working capital and cash flow are not read like a factory's
        for k in ("flag_cfo_negative", "flag_cash_gap", "flag_high_debt", "flag_weak_cover", "debt_to_equity", "lt_debt_to_equity", "net_debt", "net_debt_to_equity", "net_debt_to_ebitda",
                  "enterprise_value", "ev_sales", "ev_cfo", "ev_ebitda", "pfcf", "price_cfo", "fcf_yield", "debt_to_assets", "debt_to_fcf", "interest_coverage", "current_ratio", "quick_ratio",
                  "cash_to_debt", "cash_to_current_liab", "working_capital", "working_capital_to_sales", "asset_turnover", "fixed_asset_turnover", "gross_margin", "ebitda_margin", "ebit_margin",
                  "inventory_days", "debtor_days", "payable_days", "cash_cycle", "cfo_to_pat", "fcf_to_pat", "fcf", "cfo", "fcf_ps", "capex_to_sales", "capex_to_cfo", "net_cash_ps", "cash_ps"):
            out.pop(k, None)
        out["flag_count"] = None

    # ---------------- FinLit model
    score = summary.get("score") or {}
    out["overall"] = _n(score.get("overall"))
    pill = {p.get("key"): _n(p.get("score")) for p in score.get("pillars") or [] if isinstance(p, dict)}
    for k in ("quality", "growth", "profitability", "balance", "technical"):
        out[f"pillar_{k}"] = pill.get(k)
    four = [pill.get(k) for k in ("quality", "growth", "profitability", "balance") if pill.get(k) is not None]
    out["fundamental_score"] = int(sum(four) / len(four) + 0.5) if len(four) >= 3 else None   # half up, like the website
    out["strengths_count"], out["watchouts_count"] = float(len(summary.get("strengths") or [])), float(len(summary.get("watchouts") or []))
    out["score_change"] = None  # filled in from score history when the screener data is loaded

    # the advanced-chart figures (advanced/derive.py): ax_<id> values, ax_fy, ax_sig_fy / ax_sig_date and ax_miss (why each missing one is missing)
    try:
        out.update(ax_latest(sections, out, today))
    except Exception:   # never let one company's odd data stop the screener: its charts show "being prepared" instead (no ax_miss stored)
        logging.getLogger("finlit.advanced").exception("advanced-chart figures not computed")
    out["m_ver"] = METRICS_VERSION   # which version of this file worked the figures out: a rebuild is due when it is older
    return {k: _round(k, v) for k, v in out.items() if v is not None}


def _round(key: str, v: Any) -> Any:
    if not isinstance(v, float):
        return v
    # advanced-chart figures keep 10 significant figures so they can be checked against the raw statements; the rest keep 4 decimals as before
    return float(f"{v:.10g}") if key.startswith("ax_") else round(v, 4)
