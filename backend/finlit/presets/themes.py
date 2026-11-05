"""Sector themes in play (redesign pdf, p12): sector breadth and the nightly state machine.

Breadth is now the share of a sector's stocks within 15% of their 52-week high (fields the score tabs may use); the moving-average breadth of the first version is gone.
It is stored in the `b50` column (`b200` stays empty), and history written by the old definition is ignored, so Emerging and Fading start again from a clean 20 sessions.

Universe: stocks with a market cap of Rs 1,000 Cr or more, grouped by the Sector LABEL (the merged `sector` label of the company, never its Industry and never the broad macro sector). Generic labels are left out of theme status; groups with fewer than
8 companies are "small groups" (shown only behind the small-groups chip: spec p11 lists four of them with the label "Small group").
Per sector label and for the whole universe, per night:
    B    breadth: share of members within 15 % of the 52-week high (stored in the `b50` column)
    R3   median 3-month return (even count: the mean of the two middle values)
    RS3  industry R3 minus market R3, in percentage points
States, all relative to the market (B, RS3 in percent / points):
    In play    B >= max(40, market B + 15) AND RS3 >= +5
    Emerging   B up 20 points or more over 20 sessions, now >= market B + 10, AND RS3 >= 0
    Fading     in play at some point in the last 20 sessions, now RS3 < 0 OR B < market B + 5
    None       everything else
Emerging and Fading need history (the 20th session back); until 20 sessions are stored an industry can only be In play or None. This is not guessed.
Never empty: with fewer than 3 industries in play, the 3 with the highest RS3 among those whose B50 is above the market's are listed as "closest".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

from .industry import is_generic

FLOOR = 1000.0          # Rs crore
MIN_MEMBERS = 8
MIN_SMALL = 5           # smaller than this is not shown at all (a group of three is a coincidence, not a theme)
LOOKBACK = 20           # sessions
KEEP_SESSIONS = 60
NEAR_HIGH = 15.0        # within 15 % of the 52-week high
MARKET = "*"
KEY_PREFIX = "sector:"      # stored rows are keyed "sector:<label>": rows written when themes were grouped by Industry carry no prefix and are ignored, so no history of another grouping is mixed in
NEVER_EMPTY = 3

IN_PLAY_FLOOR = 40.0
IN_PLAY_B50_MARGIN = 15.0
IN_PLAY_RS3 = 5.0
EMERGING_RISE = 20.0
EMERGING_MARGIN = 10.0
FADING_MARGIN = 5.0


@dataclass
class Breadth:
    members: int
    b50: Optional[float] = None
    b200: Optional[float] = None
    r3: Optional[float] = None
    nh: Optional[float] = None


def _share(vals: Sequence[Optional[float]], test: Callable[[float], bool]) -> Optional[float]:
    known = [v for v in vals if v is not None and v == v]
    return None if not known else round(100.0 * sum(1 for v in known if test(v)) / len(known), 4)


def median(vals: Sequence[float]) -> Optional[float]:
    xs = sorted(v for v in vals if v is not None and v == v)
    if not xs:
        return None
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2.0


def breadth_of(table, idx: Sequence[int]) -> Breadth:
    c = table.cols
    pick = lambda k: [c[k][i] for i in idx]   # noqa: E731
    r3 = median([v for v in pick("ret_3m") if v == v])
    nh = _share(pick("pct_from_high"), lambda v: v <= NEAR_HIGH)
    return Breadth(len(idx), nh, None, None if r3 is None else round(r3, 4), nh)


def in_play(b50: Optional[float], b200: Optional[float], rs3: Optional[float], m_b50: Optional[float], m_b200: Optional[float] = None) -> bool:
    """`b50` is the breadth (share within 15% of the 52-week high); `b200` and `m_b200` are kept only so older callers still fit and are ignored."""
    if None in (b50, rs3, m_b50):
        return False
    return b50 >= max(IN_PLAY_FLOOR, m_b50 + IN_PLAY_B50_MARGIN) and rs3 >= IN_PLAY_RS3


def classify(b50, b200, rs3, m_b50, m_b200, history: Sequence[dict]) -> str:
    """'in_play' | 'emerging' | 'fading' | 'none'. `history`: the earlier stored sessions of this industry, oldest first, each {'b50', 'in_play'}
    (today is not in it)."""
    if in_play(b50, b200, rs3, m_b50, m_b200):
        return "in_play"
    if b50 is None or rs3 is None or m_b50 is None:
        return "none"
    if len(history) >= LOOKBACK:
        before = history[-LOOKBACK].get("b50")
        if before is not None and b50 - before >= EMERGING_RISE and b50 >= m_b50 + EMERGING_MARGIN and rs3 >= 0:
            return "emerging"
    if any(h.get("in_play") for h in history[-LOOKBACK:]) and (rs3 < 0 or b50 < m_b50 + FADING_MARGIN):
        return "fading"
    return "none"


@dataclass
class ThemeEval:
    market: Breadth
    industries: Dict[str, dict] = field(default_factory=dict)   # industry -> {members,b50,b200,r3,nh,rs3,in_play,state,small,idx}
    in_play: List[str] = field(default_factory=list)
    closest: List[str] = field(default_factory=list)


def by_sector_label(table) -> Callable[[int], Optional[str]]:
    """The grouping the theme screens use: the company's Sector label (merged spellings). Not its Industry, not the broad macro sector."""
    return lambda i: table.sector_label[i]


def evaluate(table, industry_of: Callable[[int], Optional[str]], history: Sequence[dict], floor: float = FLOOR) -> ThemeEval:
    """`history`: earlier sessions, oldest first; each {industry: {'b50','in_play',...}} with MARKET ('*') for the market."""
    mc = table.cols["market_cap"]
    members = [i for i in range(table.n) if mc[i] == mc[i] and mc[i] >= floor]
    market = breadth_of(table, members)
    by: Dict[str, List[int]] = {}
    for i in members:
        ind = industry_of(i)
        if ind and not is_generic(ind):
            by.setdefault(ind, []).append(i)
    ev = ThemeEval(market)
    for ind, idx in sorted(by.items()):
        if len(idx) < MIN_SMALL:
            continue
        b = breadth_of(table, idx)
        rs3 = None if b.r3 is None or market.r3 is None else round(b.r3 - market.r3, 4)
        hist = [h[ind] for h in history if ind in h]
        state = classify(b.b50, b.b200, rs3, market.b50, market.b200, hist)
        ev.industries[ind] = {"members": b.members, "b50": b.b50, "b200": b.b200, "r3": b.r3, "nh": b.nh, "rs3": rs3, "in_play": state == "in_play",
                              "state": state, "small": b.members < MIN_MEMBERS, "idx": idx}
    regular = {k: v for k, v in ev.industries.items() if not v["small"]}
    ev.in_play = sorted([k for k, v in regular.items() if v["state"] == "in_play"], key=lambda k: -(regular[k]["rs3"] or 0))
    if len(ev.in_play) < NEVER_EMPTY and market.b50 is not None:
        cand = [k for k, v in regular.items() if v["state"] != "in_play" and v["b50"] is not None and v["b50"] > market.b50 and v["rs3"] is not None]
        ev.closest = sorted(cand, key=lambda k: (-regular[k]["rs3"], k))[:NEVER_EMPTY]
    return ev


def why_not(row: dict, market: Breadth) -> str:
    """Plain words for the first in-play condition a closest industry misses."""
    need = max(IN_PLAY_FLOOR, (market.b50 or 0) + IN_PLAY_B50_MARGIN)
    if row["b50"] is None or row["b50"] < need:
        return f"Fewer than {need:.0f}% of its stocks are near their 52-week high"
    short = None if row["rs3"] is None else IN_PLAY_RS3 - row["rs3"]
    return "Its median 3-month return is " + ("not yet " if short is None else f"{max(short, 0):.1f} points short of the +{IN_PLAY_RS3:.0f} points needed ") + "above the market's"


def stored_rows(as_of, ev: ThemeEval) -> List[tuple]:
    """Rows for industry_breadth_daily: the market first, then every industry (small groups too, so their history builds up)."""
    m = ev.market
    rows = [(as_of, MARKET, m.members, m.b50, None, m.r3, m.nh, None, False, None)]
    for ind, v in ev.industries.items():
        rows.append((as_of, KEY_PREFIX + ind, v["members"], v["b50"], None, v["r3"], v["nh"], v["rs3"], v["in_play"], v["state"]))
    return rows


def history_from_rows(rows: Sequence[dict]) -> List[dict]:
    """industry_breadth_daily rows (any order) -> [{industry: {...}}] oldest session first."""
    by_day: Dict[object, dict] = {}
    for r in rows:
        if r.get("b200") is not None:
            continue          # written by the first version (moving-average breadth): a different measure, never mixed in
        name = r["industry"]
        if name != MARKET:
            if not str(name).startswith(KEY_PREFIX):
                continue          # written when themes were grouped by Industry: a different grouping, never mixed in
            name = name[len(KEY_PREFIX):]
        by_day.setdefault(r["as_of"], {})[name] = {"b50": r["b50"], "b200": r["b200"], "rs3": r["rs3"], "in_play": bool(r["in_play"])}
    return [by_day[d] for d in sorted(by_day)]


