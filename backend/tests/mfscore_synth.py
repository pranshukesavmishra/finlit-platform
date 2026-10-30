"""Synthetic funds for the Mutual Fund Health Score tests and the speed measurement: month-end NAV series with a chosen drift and volatility, and the
other inputs filled with plausible values. Nothing here is real data."""

import calendar
import random
from datetime import date
from typing import List, Optional

from finlit.mfscore.groups import group_of
from finlit.mfscore.model import FundIn

END = date(2026, 10, 29)


def month_ends(months: int, end: date = END) -> List[int]:
    """Ordinals of `months` consecutive month-end dates, the last being `end` itself (the latest NAV)."""
    out = []
    y, m = end.year, end.month
    for i in range(months):
        yy, mm = y, m - (months - 1 - i)
        while mm < 1:
            yy, mm = yy - 1, mm + 12
        last = end.day if (yy, mm) == (end.year, end.month) else calendar.monthrange(yy, mm)[1]
        out.append(date(yy, mm, last).toordinal())
    return out


def series(months: int, drift: float, vol: float, seed: int, start: float = 100.0, rets: Optional[List[float]] = None) -> List[float]:
    """NAVs: month returns are `rets` when given, else drift (% a month) plus a seeded random swing of size `vol` (% a month)."""
    rnd = random.Random(seed)
    navs = [start]
    for i in range(months - 1):
        r = rets[i] if rets is not None else drift + rnd.gauss(0, vol)
        navs.append(navs[-1] * (1 + r / 100))
    return navs


TAB_OF_PREFIX = {"EQ": "equity", "DB": "debt", "HY": "hybrid", "SOL": "solution", "OT": "other"}


def fund(key: str, group: str, sub: str, plan: str = "Direct", months: int = 61, drift: float = 1.0, vol: float = 4.0, seed: int = 1, **kw) -> FundIn:
    navs = series(months, drift, vol, seed)
    days = month_ends(months)
    f = FundIn(key=key, kind=kw.pop("kind", "mf"), name=kw.pop("name", key), plan=plan, group=group, sub=sub, sub_label=sub, category=sub, mdays=days, mnavs=navs,
               nav_date=END)
    n = months
    f.r1y = (navs[-1] / navs[-13] - 1) * 100 if n >= 13 else None
    f.r3y = ((navs[-1] / navs[-37]) ** (1 / 3) - 1) * 100 if n >= 37 else None
    f.r5y = ((navs[-1] / navs[-61]) ** (1 / 5) - 1) * 100 if n >= 61 else None
    f.sip3y = f.r3y * 0.9 if f.r3y is not None else None
    f.sip5y = f.r5y * 0.9 if f.r5y is not None else None
    peak, worst = navs[max(0, n - 37)], 0.0
    for v in navs[max(0, n - 37):]:
        peak = max(peak, v)
        worst = min(worst, (v / peak - 1) * 100)
    f.mdd = worst if n >= 37 else None
    f.aum_lakh = 500_000.0
    f.ter = 0.8 if plan == "Direct" else 1.6
    f.ter_date = date(2026, 10, 20)
    f.launch = date(2018, 1, 1)
    f.exit_text = "Nil"
    f.risk_text = "Very High" if group.startswith("EQ") else "Moderate"
    f.has_portfolio, f.equity_pct, f.other_pct, f.split_sum, f.top10, f.sector_top = True, 95.0, 0.0, 100.0, 40.0, 25.0
    for k, v in kw.items():
        setattr(f, k, v)
    return f


def universe(n_per_scope: int = 12, groups=None, seed: int = 7) -> List[FundIn]:
    """A small universe: every group, both plans, n_per_scope funds in one sub-category each."""
    from finlit.mf import classify  # noqa: F401  (kept so a rename of the category rules breaks this helper loudly)
    sub_of = {"EQ-LARGE": "large-cap", "EQ-BROAD": "flexi-cap", "EQ-MID": "mid-cap", "EQ-SMALL": "small-cap", "EQ-THEME": "sectoral-thematic", "DB-CASH": "liquid",
              "DB-ACCRUAL": "short-duration", "DB-DURATION": "long-duration", "DB-CREDIT": "credit-risk", "HY-ARB": "arbitrage", "HY-CONS": "conservative-hybrid",
              "HY-AGGR": "aggressive-hybrid", "HY-DYN": "balanced-advantage", "SOL": "retirement", "OT-PASSIVE": "index-funds", "OT-OTHER": "fof-domestic"}
    rnd = random.Random(seed)
    out: List[FundIn] = []
    for g in groups or list(sub_of):
        debt = g.startswith("DB-") or g == "HY-ARB"
        for plan in ("Direct", "Regular"):
            for i in range(n_per_scope):
                drift = (0.45 if debt else 1.0) + rnd.gauss(0, 0.05 if debt else 0.25)
                vol = (0.12 if g == "DB-CASH" else 0.5 if debt else 3.5) + rnd.random() * (0.1 if debt else 1.5)
                kw = {}
                if g == "OT-PASSIVE":
                    kw["family_key"] = "nifty50"
                out.append(fund(f"mf:{g}:{plan}:{i}", g, sub_of[g], plan=plan, drift=drift, vol=vol, seed=rnd.randint(1, 10 ** 9),
                                ter=(0.2 if g == "OT-PASSIVE" else 0.6 + rnd.random() * 0.5) + (0.8 if plan == "Regular" else 0), **kw))
    return out
