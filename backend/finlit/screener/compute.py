"""One flat dict of screener metrics per company, worked out from the stored snapshot sections (no provider calls).

Everything here is plain arithmetic on figures the company page already shows, so the screener and the page always agree.
A metric that cannot be worked out is simply left out (None), never guessed.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence

Num = Optional[float]
MULTIPLES = ("pe", "pb", "ps", "pfcf", "ev_ebitda", "ev_sales", "peg", "price_to_tangible")


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


def _flag(cond: Optional[bool]) -> Num:
    return None if cond is None else (1.0 if cond else 0.0)


def _pct_diff(now: Num, avg: Num) -> Num:
    return None if now is None or avg is None or avg <= 0 else (now - avg) / avg * 100


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
    hist = (ratios.get("history") or {}).get("rows") or {}
    yearly = fin.get("yearly") or {}
    pl, bs, cf, qpl = yearly.get("pl") or {}, yearly.get("bs") or {}, yearly.get("cf") or {}, (fin.get("quarterly") or {}).get("pl") or {}

    def hrow(key: str) -> List[Num]:
        return [_n(v) for v in hist.get(key) or []]

    # ---------------- statements, latest year
    rev, np_, op, ebt, fcost, dep = (_row(pl, k) for k in ("revenue", "net_profit", "operating_profit", "profit_before_tax", "finance_costs", "depreciation"))
    eps_row = _row(pl, "eps")
    equity, borrow, cash, cur_a, cur_l, assets, inv, recv, fixed, invest = (_row(bs, k) for k in ("total_equity", "borrowings", "cash", "current_assets", "current_liabilities", "total_assets", "inventories", "receivables", "fixed_assets", "investments"))
    cfo_r, capex_r, fcf_r = _row(cf, "operating"), _row(cf, "capex"), _row(cf, "free_cash_flow")
    rev0, np0, op0 = _last(rev), _last(np_), _last(op)
    eq0, debt0, cash0, assets0 = _last(equity), _last(borrow), _last(cash), _last(assets)
    cfo0, fcf0 = _last(cfo_r), _last(fcf_r)
    capex0 = _n(abs(_last(capex_r))) if _last(capex_r) is not None else None
    market_cap = _n(quote.get("marketCapCr")) or _n(profile.get("marketCapCr")) or latest.get("market_cap")
    price = _n(quote.get("price"))

    out["market_cap"], out["price"] = market_cap, price
    out["revenue"], out["net_profit"], out["total_assets"] = rev0, np0, assets0
    out["eps"] = _last(eps_row)
    shares = _div(np0, _last(eps_row))  # crore shares implied by profit / EPS
    out["book_value_ps"] = _div(eq0, shares)
    net_debt = _sub(debt0, _add(cash0 or 0.0, _last(invest) or 0.0)) if debt0 is not None else None
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
    out["ev_sales"] = _div(out["enterprise_value"], rev0)
    out["earnings_yield"] = _div(1.0, pe, 100) if pe and pe > 0 else None
    out["fcf_yield"] = _div(fcf0, market_cap, 100)
    pcagr = latest.get("profit_cagr_5y") or latest.get("profit_cagr")
    out["peg"] = _div(pe, pcagr) if pe and pe > 0 and pcagr and pcagr > 0 else None
    vh = (ratios.get("valuationHistory") or {}).get("rows") or {}
    out["pe_vs_avg"] = _pct_diff(pe, _mean([_n(x) for x in vh.get("pe") or [] if _n(x) and _n(x) > 0]))
    out["pb_vs_avg"] = _pct_diff(pb, _mean([_n(x) for x in vh.get("pb") or [] if _n(x) and _n(x) > 0]))
    out["price_to_tangible"] = _div(market_cap, assets0)

    for k in MULTIPLES:  # a loss-maker's P/E or a negative-equity P/B is not a "cheap" number, it is no number
        if out.get(k) is not None and out[k] <= 0:
            out[k] = None

    # ---------------- profitability
    for k, src in (("roe", "roe"), ("roce", "roce"), ("roa", "roa"), ("rota", "rota"), ("gross_margin", "gross_margin"), ("ebitda_margin", "ebitda_margin"),
                   ("ebit_margin", "ebit_margin"), ("pretax_margin", "pretax_margin"), ("tax_rate", "effective_tax_rate")):
        out[k] = latest.get(src)
    out["operating_margin"] = latest.get("operating_margin") if latest.get("operating_margin") is not None else latest.get("opm")
    out["net_margin"] = latest.get("net_margin") if latest.get("net_margin") is not None else latest.get("npm")
    opm_series = [_div(o, r, 100) for o, r in zip(op, rev)]
    out["roe_3y"], out["roce_3y"] = _mean(hrow("roe")[-3:]), _mean(hrow("roce")[-3:])
    out["opm_3y"] = _mean(opm_series[-3:])
    out["opm_change"] = _sub(_last(opm_series), _last(opm_series, 1))

    # ---------------- growth
    out["sales_growth"] = latest.get("sales_growth_latest") if latest.get("sales_growth_latest") is not None else _growth(rev0, _last(rev, 1))
    out["profit_growth"] = latest.get("profit_growth_latest") if latest.get("profit_growth_latest") is not None else _growth(np0, _last(np_, 1))
    out["sales_cagr_3y"] = latest.get("revenue_cagr_3y") if latest.get("revenue_cagr_3y") is not None else _cagr(rev0, _last(rev, 3), 3)
    out["sales_cagr_5y"] = latest.get("revenue_cagr_5y") if latest.get("revenue_cagr_5y") is not None else (latest.get("sales_cagr") if latest.get("sales_cagr") is not None else _cagr(rev0, _last(rev, 5), 5))
    out["profit_cagr_3y"] = latest.get("profit_cagr_3y") if latest.get("profit_cagr_3y") is not None else _cagr(np0, _last(np_, 3), 3)
    out["profit_cagr_5y"] = latest.get("profit_cagr_5y") if latest.get("profit_cagr_5y") is not None else (latest.get("profit_cagr") if latest.get("profit_cagr") is not None else _cagr(np0, _last(np_, 5), 5))
    out["ebitda_cagr_5y"], out["eps_cagr_5y"], out["cfo_cagr_3y"] = latest.get("ebitda_cagr_5y"), latest.get("eps_cagr_5y"), latest.get("cfo_cagr_3y")
    out["bv_cagr_5y"] = latest.get("book_value_cagr_5y")
    dps = [_n(x) for x in ((events.get("dividendsByFY") or {}).get("dps") or [])]
    first_d = next((x for x in dps if x and x > 0), None)
    out["dps_cagr"] = _cagr(_last(dps), first_d, max(0, len(dps) - 1 - dps.index(first_d))) if first_d is not None and dps else None
    last5 = np_[-6:]
    out["years_profit_up"] = float(sum(1 for a, b in zip(last5[1:], last5[:-1]) if a is not None and b is not None and a > b)) if len([x for x in last5 if x is not None]) >= 4 else None

    # ---------------- quarterly results
    qrev, qnp, qop, qeps, qfin = (_row(qpl, k) for k in ("revenue", "net_profit", "operating_profit", "eps", "finance_costs"))
    out["q_revenue"], out["q_net_profit"], out["q_operating_profit"], out["q_eps"] = _last(qrev), _last(qnp), _last(qop), _last(qeps)
    out["q_sales_yoy"], out["q_profit_yoy"] = _growth(_last(qrev), _last(qrev, 4)), _growth(_last(qnp), _last(qnp, 4))
    out["q_sales_qoq"], out["q_profit_qoq"] = _growth(_last(qrev), _last(qrev, 1)), _growth(_last(qnp), _last(qnp, 1))
    out["q_opm"], out["q_npm"] = _div(_last(qop), _last(qrev), 100), _div(_last(qnp), _last(qrev), 100)
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
    out["net_debt_to_equity"] = _div(net_debt, eq0)
    ebitda0 = _add(op0, _last(dep)) if op0 is not None and _last(dep) is not None else op0
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
    out["cfo_to_pat"] = latest.get("cfo_to_pat") if latest.get("cfo_to_pat") is not None else _div(cfo0, np0, 100)
    out["fcf_to_pat"] = latest.get("fcf_to_pat") if latest.get("fcf_to_pat") is not None else _div(fcf0, np0, 100)
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
    out["div_years"] = float(sum(1 for x in dps[-6:] if x and x > 0)) if dps else None
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
    out["avg_volume_20d"] = sum(v20) / len(v20) if len(v20) >= 10 else None
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

    # ---------------- FinLit model
    score = summary.get("score") or {}
    out["overall"] = _n(score.get("overall"))
    pill = {p.get("key"): _n(p.get("score")) for p in score.get("pillars") or [] if isinstance(p, dict)}
    for k in ("quality", "growth", "profitability", "balance", "technical"):
        out[f"pillar_{k}"] = pill.get(k)
    four = [pill.get(k) for k in ("quality", "growth", "profitability", "balance") if pill.get(k) is not None]
    out["fundamental_score"] = round(sum(four) / len(four)) if len(four) >= 3 else None
    out["strengths_count"], out["watchouts_count"] = float(len(summary.get("strengths") or [])), float(len(summary.get("watchouts") or []))
    out["score_change"] = None  # filled in from score history when the screener data is loaded

    return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in out.items() if v is not None}
