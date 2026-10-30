"""Every metric of spec Section 6: meaning, formula, no-data rule. One function per metric, all returning a Res.

States: A actual, Z negative (0 points), S substituted (wider peer set, or a longer window stands in), F filled with the group value later by the engine
(this module only says F and why), N not applicable. The zero rules of Appendix Z are applied here: a real zero is scored, a zero divisor is floored, a
zero that stands for 'not reported' (Kind C) is a gap. Test for a gap with is_missing, never `if not x`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Tuple

from . import exitload
from .groups import risk_level
from .model import Res
from .peers import Calc, Space, sharpe_of
from .sheets import (DD_FLOOR_DEFAULT, DOWN_FLOOR, K_FAMILY, PILLARS, SHEETS, TER_FLOOR, Metric, vol_floor)
from .toolkit import is_missing, safe_ratio, scale

DEBT_FIRST = ("r3y", "r1y")        # RET_ABS for debt: 3-year return, else 1-year (S)
OTHER_FIRST = ("r5y", "r3y")       # everything else: 5-year, else 3-year (S)
ETF_LIQUIDITY_STEPS = ((25.0, 100.0), (5.0, 80.0), (1.0, 60.0), (0.25, 30.0))


@dataclass
class Ctx:
    c: Calc
    space: Space
    pillar: str
    m: Metric
    lim: Optional[Tuple[float, float]]       # resolved limits (worst, best); None for step metrics
    V: float = 1.0                           # tracking-family volatility scale (passive / other sheets)


def _res(x: Ctx, state: str, **kw) -> Res:
    return Res(id=x.m.id, pillar=x.pillar, state=state, wt=x.m.wt, limits=x.lim, **kw)


def _gap(x: Ctx, why: str, rule: Optional[str] = None, **kw) -> Res:
    return _res(x, "F", why=why, rule=rule, **kw)


def _na(x: Ctx, why: str) -> Res:
    return _res(x, "N", why=why)


def _pts(x: Ctx, value: float) -> Optional[float]:
    return scale(value, x.lim[0], x.lim[1]) if x.lim else None


def _rel(x: Ctx, own: Optional[float], peer_name: str, form: str, floor: float = 0.0, gap_why: str = "no_value", frozen_zero: bool = False) -> Res:
    """Fund figure against the median of its peers, in one of the three forms of spec Section 4: excess (own - median, pp), ratio (own / max(median, floor)),
    difference (own - median). The peer median never contains the fund itself; a median of 0 is used as it is (Kind A) or floored (Kind B)."""
    if is_missing(own):
        return _gap(x, gap_why)
    if frozen_zero and own == 0 and x.c.h.frozen:
        return _gap(x, "frozen_nav", rule="frozen_nav")
    med, n, scope = x.space.peer_median(x.c, peer_name)
    if med is None:
        return _gap(x, "no_peers", own=own, peer_n=n)
    if form == "ratio":
        value = safe_ratio(own, med, floor)
        rule = "kindB_peer_median_zero" if med == 0 else None   # Kind B: a zero divisor is floored, never divided by
        if rule:
            x.c.hit(rule)
    else:
        value, rule = own - med, None
    return _res(x, "S" if scope == "grp" else "A", value=value, own=own, peer=med, peer_n=n, scope=scope, points=_pts(x, value), rule=rule)


# ------------------------------------------------------------------------------------------------------------------ 6.1 performance

def _ret_rel(attr: str) -> Callable[[Ctx], Res]:
    def fn(x: Ctx) -> Res:
        return _rel(x, getattr(x.c.f, attr), attr, "excess", gap_why="history_short", frozen_zero=True)
    return fn


def ret_abs(x: Ctx) -> Res:
    f = x.c.f
    if f.group == "OT-PASSIVE":
        return _na(x, "passive")
    first, second = DEBT_FIRST if f.group.startswith("DB-") else OTHER_FIRST
    for i, attr in enumerate((first, second)):
        v = getattr(f, attr)
        if not is_missing(v):
            if v == 0 and x.c.h.frozen:
                return _gap(x, "frozen_nav", rule="frozen_nav")
            return _res(x, "S" if i else "A", value=v, own=v, points=_pts(x, v), why=attr if i else None)
    return _gap(x, "history_short")


def sip_rel(x: Ctx) -> Res:
    f = x.c.f
    for i, attr in enumerate(("sip5y", "sip3y")):
        own = getattr(f, attr)
        if is_missing(own) or (own == 0 and x.c.h.frozen):
            continue
        med, n, scope = x.space.peer_median(x.c, attr)
        if med is None:
            continue
        return _res(x, "S" if (i or scope == "grp") else "A", value=own - med, own=own, peer=med, peer_n=n, scope=scope, points=_pts(x, own - med), why=attr if i else None)
    return _gap(x, "history_short" if is_missing(f.sip3y) else "no_peers")


def _window_ok(x: Ctx) -> Optional[Res]:
    """A gap result when the month-end window cannot be used (None when it can)."""
    h = x.c.h
    if h.frozen:
        return _gap(x, "frozen_nav", rule="frozen_nav")
    if not h.window_ok:
        return _gap(x, "window_broken")
    return None


def hit_rate(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    got = x.space.paired(x.c)
    if got is None:
        return _gap(x, "under_12_months_compared")
    scope, n, pairs = got
    value = 100.0 * sum(1 for r, m in pairs if r >= m) / len(pairs)
    return _res(x, "S" if scope == "grp" else "A", value=value, own=value, peer_n=n, scope=scope, points=_pts(x, value), why=f"{len(pairs)} months compared")


# ------------------------------------------------------------------------------------------------------------------ 6.2 risk

def vol_ratio(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    return _rel(x, x.c.vol, "vol", "ratio", floor=vol_floor(x.c.f.group), gap_why="window_broken")


def _fall(x: Ctx) -> Optional[Res]:
    c = x.c
    if c.h.frozen:
        return _gap(x, "frozen_nav", rule="frozen_nav")
    if c.fall is None:
        if c.fall_why:
            c.hit("fall_zero")
            return _gap(x, c.fall_why, rule="kindC_fall_zero")
        return _gap(x, "fall_unavailable")
    return None


def dd_ratio(x: Ctx) -> Res:
    bad = _fall(x)
    if bad:
        return bad
    return _rel(x, abs(x.c.fall), "absfall", "ratio", floor=DD_FLOOR_DEFAULT)


def mdd_abs(x: Ctx) -> Res:
    bad = _fall(x)
    if bad:
        return bad
    v = abs(x.c.fall)
    return _res(x, "A", value=v, own=v, points=_pts(x, v))


def down_capture(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    got = x.space.paired(x.c)
    if got is None:
        return _gap(x, "under_12_months_compared")
    scope, n, pairs = got
    down = [(r, m) for r, m in pairs if m < 0]
    if len(down) < 6:
        return _na(x, "fewer_than_6_down_months")
    avg_r = sum(r for r, _ in down) / len(down)
    avg_m = sum(m for _, m in down) / len(down)
    den = min(avg_m, DOWN_FLOOR)
    if avg_m > DOWN_FLOOR:
        x.c.hit("kindB_down_capture_floor")
    value = 100.0 * avg_r / den
    return _res(x, "S" if scope == "grp" else "A", value=value, own=avg_r, peer=avg_m, peer_n=n, scope=scope, points=_pts(x, value),
                why=f"{len(down)} down months", rule="kindB_down_capture_floor" if avg_m > DOWN_FLOOR else None)


def sharpe_rel(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    s = sharpe_of(x.c.f.r3y, x.c.vol, x.c.f.group)
    return _rel(x, s, "sharpe", "diff", gap_why="history_short")


def sharpe_abs(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    s = sharpe_of(x.c.f.r3y, x.c.vol, x.c.f.group)
    if s is None:
        return _gap(x, "history_short")
    return _res(x, "A", value=s, own=s, points=_pts(x, s))


def worst12_rel(x: Ctx) -> Res:
    bad = _window_ok(x)
    if bad:
        return bad
    return _rel(x, x.c.h.worst12, "worst12", "excess", gap_why="under_12_months")


def _window_abs(attr: str) -> Callable[[Ctx], Res]:
    def fn(x: Ctx) -> Res:
        bad = _window_ok(x)
        if bad:
            return bad
        v = getattr(x.c.h, attr)
        return _gap(x, "window_broken") if v is None else _res(x, "A", value=v, own=v, points=_pts(x, v))
    return fn


def calmar(x: Ctx) -> Res:
    f, c = x.c.f, x.c
    if is_missing(f.r3y):
        return _gap(x, "history_short")
    if f.r3y <= 0:
        return _res(x, "Z", value=0.0, own=f.r3y, points=0.0, why="loss_3y")
    bad = _fall(x)
    if bad:
        return bad
    v = f.r3y / max(abs(c.fall), 1.0)
    return _res(x, "A", value=v, own=f.r3y, points=_pts(x, v))


# ------------------------------------------------------------------------------------------------------------------ 6.3 cost

def ter_vs_peer(x: Ctx) -> Res:
    c = x.c
    if not c.ter_ok:
        return _gap(x, c.ter_why or "ter_missing", rule="kindC_" + (c.ter_why or "ter_missing"))
    return _rel(x, c.f.ter, "ter", "ratio", floor=TER_FLOOR)


def ter_abs(x: Ctx) -> Res:
    c = x.c
    if not c.ter_ok:
        return _gap(x, c.ter_why or "ter_missing", rule="kindC_" + (c.ter_why or "ter_missing"))
    return _res(x, "A", value=c.f.ter, own=c.f.ter, points=_pts(x, c.f.ter))


def fee_share(x: Ctx) -> Res:
    c, f = x.c, x.c.f
    if is_missing(f.r3y):
        return _gap(x, "history_short")
    if f.r3y <= 0:
        return _res(x, "Z", value=None, own=f.r3y, points=0.0, why="loss_3y")
    if not c.ter_ok:
        return _gap(x, c.ter_why or "ter_missing", rule="kindC_" + (c.ter_why or "ter_missing"))
    v = 100.0 * f.ter / (f.r3y + f.ter)
    return _res(x, "A", value=v, own=f.ter, peer=f.r3y, points=_pts(x, v))


def exit_load(x: Ctx) -> Res:
    p = exitload.parse(x.c.f.exit_text)
    if p.points is None:
        return _gap(x, "exit_load_unreadable" if (x.c.f.exit_text or "").strip() else "exit_load_missing", rule="exit_load_unreadable" if (x.c.f.exit_text or "").strip() else None)
    return _res(x, "A", value=p.load, own=p.load, points=float(p.points), why=p.rule, peer=float(p.days) if p.days is not None else None)


# ------------------------------------------------------------------------------------------------------------------ 6.4 quality

def age(x: Ctx) -> Res:
    f = x.c.f
    nav_date = f.nav_date or x.c.run_date
    months = x.c.h.months
    years = None
    if f.launch is not None and f.launch <= nav_date and (nav_date - f.launch).days > 0:
        years = (nav_date - f.launch).days / 365.25
    if years is None:
        why = "launch_date_missing" if f.launch is None else "launch_date_impossible"
        if f.launch is not None:
            x.c.hit("age_impossible")
        v = months / 12.0
        return _res(x, "S", value=v, own=v, points=_pts(x, v), why=why)
    return _res(x, "A", value=years, own=years, points=_pts(x, years))


def size_fit(x: Ctx) -> Res:
    f = x.c.f
    if is_missing(f.aum_lakh):
        return _gap(x, "aum_missing")
    if f.aum_lakh == 0:
        return _gap(x, "aum_zero", rule="kindC_aum_zero")
    cr = f.aum_lakh / 100.0
    _, floor, best, cap = x.m.lim
    p = scale(cr, floor, best)
    if cap:
        p = min(p, scale(cr, 2 * cap, cap))
    return _res(x, "A", value=cr, own=cr, points=p)


def equity_invested(x: Ctx) -> Res:
    f = x.c.f
    if not f.has_portfolio or is_missing(f.equity_pct):
        return _gap(x, "portfolio_missing")
    if f.equity_pct == 0:
        return _gap(x, "equity_zero", rule="kindC_equity_zero")
    return _res(x, "A", value=f.equity_pct, own=f.equity_pct, points=_pts(x, f.equity_pct))


def top10_conc(x: Ctx) -> Res:
    f = x.c.f
    if not f.has_portfolio or is_missing(f.top10):
        return _gap(x, "portfolio_missing")
    if f.top10 == 0:
        return _gap(x, "top10_zero", rule="kindC_top10_zero")
    return _rel(x, f.top10, "top10", "excess")


def sector_conc(x: Ctx) -> Res:
    f = x.c.f
    if not f.has_portfolio or is_missing(f.sector_top):
        return _gap(x, "portfolio_missing")
    if f.sector_top == 0:
        return _gap(x, "sector_zero", rule="kindC_sector_zero")
    return _rel(x, f.sector_top, "sector", "excess")


def asset_fit_debt(x: Ctx) -> Res:
    f = x.c.f
    if not f.has_portfolio or is_missing(f.equity_pct) or is_missing(f.split_sum):
        return _gap(x, "portfolio_missing")
    if f.split_sum < 50:
        return _gap(x, "split_unparsed", rule="kindC_split_unparsed")   # an empty or partial split is a failed parse, not a pure debt fund
    v = f.equity_pct + (f.other_pct or 0.0)
    return _res(x, "A", value=v, own=v, points=_pts(x, v))


def alloc_fit(x: Ctx) -> Res:
    f = x.c.f
    if not f.has_portfolio or is_missing(f.equity_pct) or is_missing(f.split_sum) or f.split_sum < 50:
        return _gap(x, "portfolio_missing")
    if f.equity_pct == 0 and f.group == "HY-AGGR":
        return _gap(x, "equity_zero", rule="kindC_equity_zero")
    med, n, scope = x.space.peer_median(x.c, "equity")
    if med is None:
        return _gap(x, "no_peers", own=f.equity_pct, peer_n=n)
    v = abs(f.equity_pct - med)
    return _res(x, "S" if scope == "grp" else "A", value=v, own=f.equity_pct, peer=med, peer_n=n, scope=scope, points=_pts(x, v))


def riskometer_rel(x: Ctx) -> Res:
    lvl = risk_level(x.c.f.risk_text)
    if lvl is None:
        return _gap(x, "risk_missing" if not (x.c.f.risk_text or "").strip() else "risk_unreadable")
    return _rel(x, float(lvl), "risk", "diff")


def etf_liquidity(x: Ctx) -> Res:
    f = x.c.f
    if not x.c.is_etf:
        return _na(x, "not_etf")
    if is_missing(f.turnover_cr):
        return _gap(x, "turnover_missing")
    pts = next((p for lo, p in ETF_LIQUIDITY_STEPS if f.turnover_cr >= lo), 0.0)
    return _res(x, "A", value=f.turnover_cr, own=f.turnover_cr, points=pts)


def etf_premium(x: Ctx) -> Res:
    f = x.c.f
    if not x.c.is_etf:
        return _na(x, "not_etf")
    if is_missing(f.premium):
        return _gap(x, "no_trade_on_nav_date")
    if f.premium == 0 and not f.traded_on_nav_date:
        return _gap(x, "no_trade_on_nav_date", rule="kindC_etf_premium_no_trade")   # feeds write 0 for no trade
    v = abs(f.premium)
    return _res(x, "A", value=v, own=f.premium, points=_pts(x, v))


FUNCS: Dict[str, Callable[[Ctx], Res]] = {
    "RET_1Y_REL": _ret_rel("r1y"), "RET_3Y_REL": _ret_rel("r3y"), "RET_5Y_REL": _ret_rel("r5y"), "RET_ABS": ret_abs, "SIP_REL": sip_rel, "HIT_RATE": hit_rate,
    "VOL_RATIO": vol_ratio, "DD_RATIO": dd_ratio, "DOWN_CAPTURE": down_capture, "SHARPE_REL": sharpe_rel, "SHARPE_ABS": sharpe_abs, "WORST12_REL": worst12_rel,
    "WORST_MONTH": _window_abs("worst_month"), "MDD_ABS": mdd_abs, "NEG_MONTHS": _window_abs("neg_months"), "UNDERWATER": _window_abs("underwater"), "CALMAR": calmar,
    "TER_VS_PEER": ter_vs_peer, "TER_ABS": ter_abs, "FEE_SHARE": fee_share, "EXIT_LOAD": exit_load,
    "AGE": age, "SIZE_FIT": size_fit, "EQUITY_INVESTED": equity_invested, "TOP10_CONC_REL": top10_conc, "SECTOR_CONC_REL": sector_conc,
    "ASSET_FIT_DEBT": asset_fit_debt, "ALLOC_FIT": alloc_fit, "RISKOMETER_REL": riskometer_rel, "ETF_LIQUIDITY": etf_liquidity, "ETF_PREMIUM": etf_premium,
}


def resolve_limits(m: Metric, group: str, plan: str, V: float) -> Optional[Tuple[float, float]]:
    """The (worst, best) pair of a metric for this fund, or None for a step metric / a metric with no limits."""
    lim = m.lim
    if lim is None or lim == "step":
        return None
    if isinstance(lim, dict):
        return lim["Direct" if plan in ("Direct", "ETF") else "Regular"]
    if lim and lim[0] == "sym":
        k = K_FAMILY[group][lim[1]] * V
        return (-k, k)
    if lim and lim[0] == "abs_v":
        return (6.0, 6.0 + V)
    if lim and lim[0] == "size":
        return (lim[1], lim[2])
    return lim


def family_v(c: Calc, space: Space) -> float:
    """V = max(median of the family's VOL_M, 1.0): the scale of the limits of the passive and other sheets (spec 7.5)."""
    med, _, _ = space.peer_median(c, "vol")
    return max(med if med is not None else 0.0, 1.0)


def compute_metric(c: Calc, space: Space, pillar: str, m: Metric, V: float) -> Res:
    lim = resolve_limits(m, c.f.group, c.f.plan, V)
    x = Ctx(c=c, space=space, pillar=pillar, m=m, lim=lim, V=V)
    if m.lim is None:
        return _na(x, "lock_in" if m.id == "EXIT_LOAD" else "not_in_sheet")
    return FUNCS[m.id](x)
