"""Per-fund working figures and the peer sets (spec Section 3, "Peer set rules").

A peer is an active Growth scheme of the same sub-category and the same plan (Direct with Direct, Regular with Regular), with at least 12 months of
history and no suspected NAV break; the fund itself is never in its own median. Too few peers with an actual value for a metric (8; 3 for a tracking
family): widen to every fund of the same group and plan (state S), else the metric is filled with the group value (state F). Passive funds are compared with
funds tracking the same index (same instrument kind: ETF with ETF, mutual fund with mutual fund, same plan), never widened. A peer whose TER is below 0.01 is
left out of the TER median only (a placeholder zero, Kind C)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Hashable, List, Optional, Tuple

from . import history
from .groups import risk_level
from .model import FundIn
from .sheets import (DD_FLOOR_DEFAULT, MIN_PEERS, MIN_PEERS_FAMILY, RISK_FREE, TER_MAX_AGE_DAYS, TER_MIN_REAL, vol_floor)
from .toolkit import MedianBook, is_missing


@dataclass
class Calc:
    """One fund with the figures derived from its inputs. Built once per run."""
    f: FundIn
    h: history.Hist
    run_date: date
    row: str = "none"                       # history row: all | three_year | window | none
    vol: Optional[float] = None             # VOL_M, None when the window is unusable or the NAV is frozen
    fall: Optional[float] = None            # month-end fall used (stored mdd3y_m, else our own working over the available months)
    fall_why: Optional[str] = None
    zero_fall_ok: bool = False              # a fall of exactly 0 is a real value (Debt and arbitrage), else Kind C
    ter_ok: bool = False
    ter_why: Optional[str] = None
    peer_ok: bool = False
    pv: Dict[str, Optional[float]] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return self.f.key

    def hit(self, rule: str) -> None:
        self.counters[rule] = self.counters.get(rule, 0) + 1

    @property
    def is_etf(self) -> bool:
        return self.f.kind == "etf"


def sharpe_of(r3y: Optional[float], vol: Optional[float], group: str) -> Optional[float]:
    """SHARPE_M = (r3y - 6) / max(VOL_M, floor). None without a 3-year return or a usable volatility (a frozen NAV has none)."""
    if is_missing(r3y) or vol is None:
        return None
    return (r3y - RISK_FREE) / max(vol, vol_floor(group))


def ter_state(f: FundIn, run_date: date) -> Tuple[bool, Optional[str]]:
    """(usable, cause). A TER is missing, a placeholder zero (below 0.01: Kind C) or older than 45 days (stale)."""
    if is_missing(f.ter):
        return False, "ter_missing"
    if f.ter < TER_MIN_REAL:
        return False, "ter_zero"
    if f.ter_date is not None and (run_date - f.ter_date).days > TER_MAX_AGE_DAYS:
        return False, "ter_stale"
    return True, None


def build_calc(f: FundIn, run_date: date) -> Calc:
    h = history.compute(f.mdays, f.mnavs)
    c = Calc(f=f, h=h, run_date=run_date, row=history.status_row(h.months))
    c.zero_fall_ok = f.group.startswith("DB-") or f.group == "HY-ARB"
    if c.row == "none":
        return c
    c.vol = h.vol_m if (h.window_ok and not h.frozen) else None
    if h.frozen:
        c.hit("frozen_nav")
    if h.invalid:
        c.hit("nav_invalid_month")
    fall = f.mdd if not is_missing(f.mdd) else h.fall
    if fall is not None and fall == 0 and not c.zero_fall_ok:
        c.fall, c.fall_why = None, "fall_zero"     # Kind C: a 36-month fall of exactly 0 is not credible outside Debt and arbitrage
    else:
        c.fall = fall
    c.ter_ok, c.ter_why = ter_state(f, run_date)
    if c.ter_why in ("ter_zero", "ter_stale"):
        c.hit(c.ter_why)
    if not is_missing(f.aum_lakh) and f.aum_lakh == 0:
        c.hit("aum_zero")
    if f.has_portfolio:
        if f.top10 == 0:
            c.hit("top10_zero")
        if f.equity_pct == 0 and f.group.startswith(("EQ-", "HY-AGGR")):
            c.hit("equity_zero")
        if f.split_sum is not None and f.split_sum < 50:
            c.hit("split_unparsed")
    c.peer_ok = c.row != "none" and not h.break_flag and h.window_ok
    # peers' values (the same figures a fund is measured by, so a peer is treated as the fund itself would be)
    split_ok = f.has_portfolio and f.split_sum is not None and f.split_sum >= 50
    c.pv = {
        "r1y": f.r1y, "r3y": f.r3y, "r5y": f.r5y, "sip3y": f.sip3y, "sip5y": f.sip5y,
        "vol": c.vol, "sharpe": sharpe_of(f.r3y, c.vol, f.group),
        "absfall": abs(c.fall) if c.fall is not None else None,
        "worst12": h.worst12,
        "ter": f.ter if (not is_missing(f.ter) and f.ter >= TER_MIN_REAL) else None,
        "top10": f.top10 if (f.has_portfolio and f.top10 and f.top10 > 0) else None,
        "sector": f.sector_top if (f.has_portfolio and f.sector_top and f.sector_top > 0) else None,
        "equity": f.equity_pct if (split_ok and not is_missing(f.equity_pct) and not (f.equity_pct == 0 and f.group == "HY-AGGR")) else None,
        "risk": risk_level(f.risk_text),
    }
    return c


class Space:
    """The peer scopes of a whole universe and the medians over them (built lazily, kept for the run)."""

    def __init__(self, calcs: List[Calc]):
        self.scopes: Dict[str, List[Calc]] = {}
        self._books: Dict[Tuple[str, str], MedianBook] = {}
        self._months: Dict[str, Dict[int, MedianBook]] = {}
        for c in calcs:
            if not c.peer_ok:
                continue
            for k in self.keys_of(c.f):
                self.scopes.setdefault(k, []).append(c)

    @staticmethod
    def keys_of(f: FundIn) -> List[str]:
        if f.group == "OT-PASSIVE":
            return [f"fam:{f.family_key}|{f.kind}|{f.plan}"] if f.family_key else []
        return [f"sub:{f.sub}|{f.plan}|{f.kind}", f"grp:{f.group}|{f.plan}|{f.kind}"]

    @staticmethod
    def order(f: FundIn) -> List[Tuple[str, str, int]]:
        """Scopes a fund is measured against, narrowest first: (kind, key, minimum peers)."""
        if f.group == "OT-PASSIVE":
            return [("fam", f"fam:{f.family_key}|{f.kind}|{f.plan}", MIN_PEERS_FAMILY)] if f.family_key else []
        return [("sub", f"sub:{f.sub}|{f.plan}|{f.kind}", MIN_PEERS), ("grp", f"grp:{f.group}|{f.plan}|{f.kind}", MIN_PEERS)]

    def book(self, scope: str, name: str) -> MedianBook:
        k = (scope, name)
        b = self._books.get(k)
        if b is None:
            b = self._books[k] = MedianBook((c.key, c.pv.get(name)) for c in self.scopes.get(scope, ()))
        return b

    def months(self, scope: str) -> Dict[int, MedianBook]:
        m = self._months.get(scope)
        if m is None:
            by: Dict[int, List[Tuple[Hashable, float]]] = {}
            for c in self.scopes.get(scope, ()):
                for mk, r in c.h.rets.items():
                    by.setdefault(mk, []).append((c.key, r))
            m = self._months[scope] = {mk: MedianBook(items) for mk, items in by.items()}
        return m

    def peer_median(self, c: Calc, name: str) -> Tuple[Optional[float], int, Optional[str]]:
        """(median of the others, how many, scope kind) from the narrowest scope with enough peers having an actual value; (None, n, None) when none has."""
        best_n = 0
        for kind, key, need in self.order(c.f):
            med, n = self.book(key, name).median(exclude=c.key)
            best_n = max(best_n, n)
            if med is not None and n >= need:
                return med, n, kind
        return None, best_n, None

    def paired(self, c: Calc) -> Optional[Tuple[str, int, List[Tuple[float, float]]]]:
        """(scope kind, peers, [(r_t, m_t)]) for the months of W where the peer median m_t exists (at least 8 peers that month, 3 for a family).
        The first scope giving 12 compared months wins; None when no scope does."""
        for kind, key, need in self.order(c.f):
            books = self.months(key)
            pairs: List[Tuple[float, float]] = []
            peers = 0
            for mk, r in c.h.rets.items():
                b = books.get(mk)
                if b is None:
                    continue
                med, n = b.median(exclude=c.key)
                if med is not None and n >= need:
                    pairs.append((r, med))
                    peers = max(peers, n)
            if len(pairs) >= 12:
                return kind, peers, pairs
        return None
