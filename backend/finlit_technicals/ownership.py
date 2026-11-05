"""Ownership insights: plain-language readings of a company's shareholding pattern, from rules that apply to every
listed stock.

    from finlit_technicals import ownership as O
    pack = O.pack_from_site(ownership_json, premium_json)   # /api/stocks/SYM/ownership + premium/fundamentals
    view = O.analyse(pack)                                   # -> dict for the page: table, sparklines, facts, signals
    view["headline"]                                         # the three sentences shown at the top

Every rule is in RULES below (id, when it fires, tone). The rules look at quarterly shareholding filings, the share
count, promoter pledges, lock-ins, the number of shareholders and named holders of 1% or more. Stake changes are
checked against the share count first, so a new share issue is never read as promoter selling. The wording describes
what holders did; it never says what an investor should do.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

RULES_VERSION = "ownership-1.1"
DISCLAIMER = "Read from quarterly shareholding filings. A description of who owns the company, not investment advice."

GROUPS: List[Tuple[str, str, str]] = [
    ("promoters", "Promoters", "Founders and their group"),
    ("dii", "Domestic institutions", "Indian mutual funds, insurers, banks and pension funds"),
    ("fii", "Foreign institutions", "Foreign funds"),
    ("public", "Retail & others", "Individuals, companies and others"),
    ("government", "Government", "Central and state governments, outside the promoter group"),
]
LABEL = {k: n for k, n, _ in GROUPS}
LOWER = {"promoters": "promoters", "dii": "domestic institutions", "fii": "foreign institutions",
         "public": "retail and other investors", "government": "the government"}
POSS = {"promoters": "promoters'", "dii": "domestic institutions'", "fii": "foreign institutions'",
        "public": "retail and other investors'", "government": "the government's"}
SHORT = {"promoters": "Promoters", "dii": "Indian funds", "fii": "Foreign funds", "public": "Retail",
         "government": "Government"}                      # names for the short card titles

# thresholds, in percentage points (pts) of the company unless stated
T = {
    "noise": 0.05,                 # quarterly changes smaller than this count as no change
    "promoter_move": 0.25,         # promoter stake change that counts (promoters rarely move)
    "held_move_pct": 1.0,          # % change in the NUMBER of shares a holder owns that counts as buying or selling
    "share_count_pct": 0.5,        # share-count change above which stakes are judged by shares held, not %
    "inst_move": 1.0,              # institutional stake change over a year that counts
    "inst_move_small": 0.5,        # ... or this much, if it is also 20% or more of what they held
    "inst_move_rel": 0.20,
    "big_quarter": 2.0,            # a single-quarter change this large is worth a line of its own
    "big_quarter_small": 1.0,      # ... or this, if it is 25% or more of the holding
    "big_quarter_rel": 0.25,
    "rotation": 1.0,               # one institution group up and the other down by this much over a year
    "rotation_5y": 3.0,
    "retail_shift_1y": 2.0,        # retail up and institutions down by this much (1 year)
    "retail_shift_3y": 4.0,        # ... or by this much over three years
    "inst_total": 2.0,             # institutions together up or down by this much over a year
    "low_inst": 5.0,               # institutions together own less than this
    "pledge_high": 10.0,           # % of promoter shares pledged
    "pledge_rise": 3.0,            # rise in that % over a year
    "pledge_gone_from": 5.0,       # pledge at or above this within a year and now under 1%
    "lock_in": 5.0,                # % of shares locked in worth a mention
    "lock_in_end": 10.0,           # fall in locked-in % in the latest quarter (a lock-in ended)
    "float_min": 25.0,             # SEBI minimum public shareholding
    "holders_pct": 10.0,           # change in the number of shareholders over a year
    "named_move": 0.3,             # named holder (1% or more) change over a year
    "extreme_range": 1.0,          # a high/low needs at least this much range in the window
}

RULES = [
    ("P1", "Promoters bought", "Promoter stake up 0.25 pts or more (1 year, else 3 years), or promoters own 1%+ more shares "
                               "when the share count changed", "supportive"),
    ("P2", "Promoters sold", "Promoter stake down 0.25 pts or more with fewer shares held (1 year, else 3 years)", "watch"),
    ("P3", "Stake diluted, not sold", "Promoter stake down because the share count grew; shares held about the same",
     "neutral"),
    ("P4", "Promoters steady", "Promoter stake within 0.25 pts for three years", "neutral"),
    ("P5", "Just over half", "Promoters hold 50% to 51%", "neutral"),
    ("P6", "Public float below 25%", "Promoters hold more than 75%", "neutral"),
    ("P7", "Promoter shares pledged", "10% or more of promoter shares pledged, or pledge up 3 pts in a year", "watch"),
    ("P8", "Pledge released", "Pledge was 5% or more within a year, now under 1%", "supportive"),
    ("P9", "Lock-in", "5% or more of shares locked in, or a lock-in on 10%+ of shares ended last quarter", "neutral"),
    ("I1", "Foreign institutions' trend", "Foreign stake moved 1 pt (or 0.5 pt and 20%) in a year, same direction in 3 "
                                         "of the last 4 quarters", "supportive if buying, watch if selling"),
    ("I2", "Domestic institutions' trend", "Same test for domestic institutions", "supportive if buying, watch if selling"),
    ("I3", "Rotation", "One institution group up 1 pt and the other down 1 pt over a year, roughly offsetting", "neutral"),
    ("I4", "Multi-year high or low", "A group at its highest or lowest in up to five years (range 1 pt or more)",
     "neutral"),
    ("I5", "Big quarter", "A group moved 2 pts (or 1 pt and 25%) in the latest quarter", "neutral"),
    ("I6", "Institutions together", "Foreign plus domestic institutions up or down 2 pts in a year",
     "supportive if up, watch if down"),
    ("I7", "Few institutions", "Foreign plus domestic institutions own under 5%", "neutral"),
    ("R1", "From institutions to individuals", "Retail up and institutions down by 2 pts in a year (or 4 pts in three)",
     "watch"),
    ("R2", "Number of shareholders", "Up or down 10% or more in a year", "neutral"),
    ("S1", "New shares issued", "Share count up 0.5% or more in a year (when no promoter rule already says so)", "neutral"),
    ("S2", "Buyback", "Share count down 0.5% or more in a year", "neutral"),
    ("H1", "Named holders", "A holder of 1% or more moved 0.3 pts in a year, or crossed 1%", "neutral"),
]


# --------------------------------------------------------------------------------------------- formatting
def _r1(x: float) -> float:
    return round(x + (1e-9 if x >= 0 else -1e-9), 1)          # 18.65 -> 18.7, as people round


def pct(x: Optional[float]) -> str:
    return "—" if x is None else f"{_r1(x):.1f}%"


def pts(d: float, sign: bool = True) -> str:
    s = f"{abs(d):.2f}" if abs(d) < 0.1 else f"{_r1(abs(d)):.1f}"
    return (("+" if d > 0 else "−" if d < 0 else "") if sign else "") + s + " pts"


def count_in(n: float) -> str:
    """Indian style: 50.7 lakh, 1.2 crore, 76,317."""
    if n >= 1e7:
        return f"{n / 1e7:.2f} crore"
    if n >= 1e5:
        return f"{n / 1e5:.1f} lakh"
    return f"{int(round(n)):,}"


def _f(x) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


# --------------------------------------------------------------------------------------------- input
def pack_from_site(ownership: dict, premium: Optional[dict] = None, symbol: Optional[str] = None) -> dict:
    """/api/stocks/SYM/ownership (periods + series, oldest first) and, optionally, the premium/fundamentals response
    (ownershipStructure: share count, pledges, lock-in, shareholders; shareholdingDetails: named holders)."""
    pack = {"symbol": symbol or (ownership.get("meta") or {}).get("symbol"), "periods": list(ownership["periods"]),
            "series": {k: list(v) for k, v in ownership["series"].items()}}
    if premium:
        st: Dict[str, Any] = {}
        for item in premium.get("ownershipStructure") or []:
            hist = item.get("history") or []
            st.setdefault("periods", [h["period"] for h in hist])
            st[item.get("category")] = [_f(h.get("value")) for h in hist]
        pack["structure"] = st
        holders = []
        group_of = {"institutions domestic": "dii", "institutions foreign": "fii", "non-institutions": "public",
                    "government": "government"}
        for g in premium.get("shareholdingDetails") or []:
            grp = group_of.get(str(g.get("label", "")).lower())
            if not grp:
                continue
            for k in g.get("children") or []:
                h = k.get("history") or []
                now = _f(h[0]["value"]) if h else None
                ago = _f(h[4]["value"]) if len(h) > 4 else None
                if (now or 0) >= 1 or (ago or 0) >= 1:
                    holders.append([k.get("label"), grp, now, ago])
        pack["holders"] = holders
    return pack


def _structure_by_period(pack: dict) -> Dict[str, Dict[str, Optional[float]]]:
    st = pack.get("structure") or {}
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for i, p in enumerate(st.get("periods") or []):
        out[p] = {k: (_f(v[i]) if i < len(v) else None) for k, v in st.items() if k != "periods" and isinstance(v, list)}
    return out


# --------------------------------------------------------------------------------------------- the analysis
def _changes(xs: Sequence[Optional[float]]) -> List[Optional[float]]:
    return [None if a is None or b is None else b - a for a, b in zip(xs, xs[1:])]


def _streak(ch: Sequence[Optional[float]]) -> int:
    """Consecutive latest quarters moving the same way (signed: +3 = three rises in a row)."""
    s = 0
    for c in reversed(ch):
        if c is None or abs(c) < T["noise"]:
            break
        if s == 0 or (c > 0) == (s > 0):
            s += 1 if c > 0 else -1
        else:
            break
    return s


def _ago(xs: Sequence[Optional[float]], q: int) -> Optional[float]:
    return xs[-1 - q] if len(xs) > q else None


def _material(d: float, base: Optional[float]) -> bool:
    if abs(d) >= T["inst_move"]:
        return True
    return abs(d) >= T["inst_move_small"] and base is not None and base > 0 and abs(d) / base >= T["inst_move_rel"]


def _span(n_values: int, first_period: str) -> str:
    if n_values >= 21:
        return "in five years"
    if n_values >= 13:
        return "in three years"
    return f"since {first_period}"


class _Ctx:
    def __init__(self, pack: dict):
        self.pack = pack
        self.periods: List[str] = list(pack["periods"])
        self.series = {k: [_f(x) for x in v] for k, v in pack["series"].items()}
        self.n = len(self.periods)
        st = _structure_by_period(pack)
        self.shares = [st.get(p, {}).get("total_shares") for p in self.periods]
        self.pledge = [st.get(p, {}).get("promoter_pledged_percent") for p in self.periods]
        self.locked = [st.get(p, {}).get("locked_in_percent") for p in self.periods]
        self.holders_n = [st.get(p, {}).get("total_shareholders") for p in self.periods]
        self.signals: List[dict] = []

    def s(self, key: str) -> List[Optional[float]]:
        return self.series.get(key) or [None] * self.n

    def now(self, key: str) -> Optional[float]:
        return self.s(key)[-1] if self.n else None

    def add(self, rid: str, group: Optional[str], tone: str, priority: int, text: str, covers: Sequence[str] = (),
            title: str = "", stat: str = "", **facts):
        """text: the full sentence. title: the same point in a few words, for the card. stat: the number behind it."""
        self.signals.append({"id": rid, "group": group, "tone": tone, "priority": priority, "title": title or text,
                             "stat": stat, "text": text, "covers": list(covers), "facts": facts})


def _held(pct_val: Optional[float], shares: Optional[float]) -> Optional[float]:
    return None if pct_val is None or shares is None else pct_val * shares / 100.0


def _promoter_rules(c: _Ctx) -> Optional[str]:
    p = c.s("promoters")
    for q, when in ((4, "over the year"), (12, "over three years")):
        then, now = _ago(p, q), p[-1] if p else None
        if then is None or now is None:
            continue
        d = now - then
        sh_then, sh_now = _ago(c.shares, q), c.shares[-1] if c.shares else None
        if sh_then and sh_now and abs(sh_now / sh_then - 1) * 100 >= T["share_count_pct"]:
            g = (sh_now / sh_then - 1) * 100
            held = (_held(now, sh_now) / _held(then, sh_then) - 1) * 100
            if held >= T["held_move_pct"]:
                c.add("P1", "promoters", "supportive", 90 if held >= 2 else 72,
                      f"Promoters took up new shares: they own {held:.1f}% more shares than {_when_ago(q)}. "
                      f"Their stake is {pct(now)} (from {pct(then)}) because the share count grew {g:.1f}%.",
                      window=q, held_change_pct=round(held, 2), share_count_change_pct=round(g, 2),
                      title="Promoters took up new shares", stat=f"{held:+.1f}% more shares; stake {pct(now)}")
                return "P1"
            if held <= -T["held_move_pct"]:
                c.add("P2", "promoters", "watch", 95 if held <= -2 else 74,
                      f"Promoters sold: they own {abs(held):.1f}% fewer shares than {_when_ago(q)}, and their stake "
                      f"is {pct(now)} (from {pct(then)}).", window=q, held_change_pct=round(held, 2),
                      title="Promoters sold shares", stat=f"{abs(held):.1f}% fewer shares; stake {pct(now)}")
                return "P2"
            if d <= -T["promoter_move"]:
                c.add("P3", "promoters", "neutral", 84,
                      f"Promoters' stake fell to {pct(now)} from {pct(then)} {when} because the company issued new "
                      f"shares (share count +{g:.1f}%). Promoters did not sell.", window=q,
                      share_count_change_pct=round(g, 2), covers=["S1"],
                      title="Stake diluted by new shares, not sold", stat=f"{pct(then)} → {pct(now)}; shares +{g:.1f}%")
                return "P3"
            continue
        if d >= T["promoter_move"]:
            c.add("P1", "promoters", "supportive", 90 if d >= 1 else 72,
                  f"Promoters raised their stake to {pct(now)} from {pct(then)} {when} ({pts(d)}).", window=q,
                  change_pts=round(d, 2), title="Promoters raised their stake", stat=f"{pct(then)} → {pct(now)} {_short_when(q)}")
            return "P1"
        if d <= -T["promoter_move"]:
            big = " That is a large sale." if d <= -2 else ""
            c.add("P2", "promoters", "watch", 95 if d <= -1 else 74,
                  f"Promoters sold: their stake fell to {pct(now)} from {pct(then)} {when} ({pts(d)}).{big}",
                  window=q, change_pts=round(d, 2), title="Promoters sold shares",
                  stat=f"{pct(then)} → {pct(now)} {_short_when(q)}")
            return "P2"
    return None


def _short_when(q: int) -> str:
    return "in a year" if q == 4 else "in 3 years" if q == 12 else f"in {q} quarters"


def _when_ago(q: int) -> str:
    return "a year ago" if q == 4 else "three years ago" if q == 12 else f"{q} quarters ago"


def analyse(pack: dict) -> Dict[str, Any]:
    c = _Ctx(pack)
    if c.n < 2:
        raise ValueError("need at least two quarterly filings")
    groups = [g for g in GROUPS if any(v is not None and v > 0 for v in c.s(g[0]))]

    # ---- the table
    table = []
    for key, label, desc in groups:
        xs = c.s(key)
        ch = _changes(xs)
        row = {"key": key, "label": label, "description": desc, "now": xs[-1],
               "change_1q": None if _ago(xs, 1) is None else round(xs[-1] - _ago(xs, 1), 2),
               "change_1y": None if _ago(xs, 4) is None else round(xs[-1] - _ago(xs, 4), 2),
               "change_3y": None if _ago(xs, 12) is None else round(xs[-1] - _ago(xs, 12), 2),
               "change_5y": None if _ago(xs, 20) is None else round(xs[-1] - _ago(xs, 20), 2),
               "streak": _streak(ch), "spark": xs[-21:], "spark_periods": c.periods[-21:]}
        table.append(row)

    # ---- promoters
    fired = _promoter_rules(c)
    pr = c.now("promoters")
    if pr is not None:
        p = c.s("promoters")
        if not fired and _ago(p, 12) is not None and max(p[-13:]) - min(p[-13:]) < T["promoter_move"]:
            c.add("P4", "promoters", "neutral", 30, f"Promoters have held about {pct(pr)} for three years.",
                  title="Promoters steady for three years", stat=f"about {pct(pr)}")
        if 50.0 <= pr < 51.0:
            c.add("P5", "promoters", "neutral", 40, f"Promoters hold {pct(pr)}, just over half of the company.",
                  title="Promoters hold just over half", stat=pct(pr))
        if pr > 100 - T["float_min"]:
            c.add("P6", "promoters", "neutral", 80,
                  f"Promoters hold {pct(pr)}, so only {pct(100 - pr)} is with the public. Listed companies must have "
                  f"at least 25% public shareholding, so promoters are required to bring their stake down to 75% "
                  f"over time.", title="Public holding below the 25% minimum", stat=f"public {pct(100 - pr)}")
    pl = c.pledge[-1] if c.pledge else None
    if pl is not None:
        pl_ago = _ago(c.pledge, 4)
        recent = [x for x in c.pledge[-5:-1] if x is not None]
        if pl >= T["pledge_high"] or (pl_ago is not None and pl - pl_ago >= T["pledge_rise"]):
            tail = f", from {pl_ago:.1f}% a year ago" if pl_ago is not None else ""
            c.add("P7", "promoters", "watch", 86,
                  f"{pl:.1f}% of promoters' shares are pledged as loan collateral{tail}.", pledged=pl,
                  title="Promoter shares pledged",
                  stat=f"{pl:.1f}%" + (f", was {pl_ago:.1f}%" if pl_ago is not None else ""))
        elif pl < 1 and recent and max(recent) >= T["pledge_gone_from"]:
            c.add("P8", "promoters", "supportive", 85,
                  f"Promoters released their pledged shares: {max(recent):.1f}% were pledged within the last year, "
                  f"{pl:.1f}% now.", title="Promoters released pledged shares", stat=f"{max(recent):.1f}% → {pl:.1f}%")
    lk, lk_prev = (c.locked[-1] if c.locked else None), _ago(c.locked, 1)
    if lk is not None and lk_prev is not None and lk_prev - lk >= T["lock_in_end"]:
        c.add("P9", None, "neutral", 88,
              f"The lock-in on {lk_prev - lk:.1f}% of the company's shares ended last quarter, so those shares can "
              f"now be sold. {lk:.1f}% remain locked in.", ended=round(lk_prev - lk, 2), locked=lk,
              title=f"Lock-in ended on {lk_prev - lk:.0f}% of shares", stat=f"{lk:.1f}% still locked in")
    elif lk is not None and lk >= T["lock_in"]:
        c.add("P9", None, "neutral", 48,
              f"{lk:.1f}% of the company's shares are locked in (from a share issue or listing) and cannot be sold "
              f"until the lock-in ends.", locked=lk, title="Shares under lock-in", stat=f"{lk:.1f}% of shares")

    # ---- institutions
    for key, rid in (("fii", "I1"), ("dii", "I2")):
        xs = c.s(key)
        then, now = _ago(xs, 4), xs[-1]
        if then is None or now is None:
            continue
        d = now - then
        last4 = [x for x in _changes(xs)[-4:] if x is not None]
        ups = sum(1 for x in last4 if x >= T["noise"])
        downs = sum(1 for x in last4 if x <= -T["noise"])
        if not _material(d, then):
            continue
        st = _streak(_changes(xs))
        if d < 0 and downs >= 3:
            how = f"for {abs(st)} quarters in a row" if st <= -3 else f"in {downs} of the last 4 quarters"
            c.add(rid, key, "watch", 70,
                  f"{LABEL[key]} have cut their stake {how}: {pct(now)} now against {pct(then)} a year ago.",
                  change_pts=round(d, 2), title=f"{SHORT[key]} selling",
                  stat=f"{pct(then)} → {pct(now)}; " + (f"{abs(st)} quarters in a row" if st <= -3 else f"{downs} of 4 quarters"))
        elif d > 0 and ups >= 3:
            how = f"for {st} quarters in a row" if st >= 3 else f"in {ups} of the last 4 quarters"
            c.add(rid, key, "supportive", 70,
                  f"{LABEL[key]} have added to their stake {how}: {pct(now)} now against {pct(then)} a year ago.",
                  change_pts=round(d, 2), title=f"{SHORT[key]} buying",
                  stat=f"{pct(then)} → {pct(now)}; " + (f"{st} quarters in a row" if st >= 3 else f"{ups} of 4 quarters"))
    f, d_ = c.s("fii"), c.s("dii")
    if _ago(f, 4) is not None and _ago(d_, 4) is not None:
        df, dd = f[-1] - _ago(f, 4), d_[-1] - _ago(d_, 4)
        long = ""
        if _ago(f, 20) is not None and _ago(d_, 20) is not None:
            df5, dd5 = f[-1] - _ago(f, 20), d_[-1] - _ago(d_, 20)
            if df5 * dd5 < 0 and abs(df5) >= T["rotation_5y"] and abs(dd5) >= T["rotation_5y"]:
                long = (f" Over five years foreign institutions went from {pct(_ago(f, 20))} to {pct(f[-1])} and "
                        f"domestic institutions from {pct(_ago(d_, 20))} to {pct(d_[-1])}.")
        offset = df * dd < 0 and 0.5 <= abs(dd) / max(abs(df), 1e-9) <= 2.0
        if offset and df <= -T["rotation"] and dd >= T["rotation"]:
            c.add("I3", None, "neutral", 78,
                  f"Indian institutions are taking up what foreign funds sell: over the year domestic institutions "
                  f"rose to {pct(d_[-1])} ({pts(dd)}) while foreign institutions fell to {pct(f[-1])} ({pts(df)})."
                  + long, covers=["I1", "I2"], title="Indian funds buying what foreign funds sell",
                  stat=f"Indian {pts(dd)}, foreign {pts(df)} in a year")
        elif offset and df >= T["rotation"] and dd <= -T["rotation"]:
            c.add("I3", None, "neutral", 78,
                  f"Foreign funds are taking up what Indian institutions sell: over the year foreign institutions "
                  f"rose to {pct(f[-1])} ({pts(df)}) while domestic institutions fell to {pct(d_[-1])} ({pts(dd)})."
                  + long, covers=["I1", "I2"], title="Foreign funds buying what Indian funds sell",
                  stat=f"Foreign {pts(df)}, Indian {pts(dd)} in a year")
        inst_now, inst_then = f[-1] + d_[-1], _ago(f, 4) + _ago(d_, 4)
        di = inst_now - inst_then
        if abs(di) >= T["inst_total"]:
            c.add("I6", None, "supportive" if di > 0 else "watch", 65,
                  f"Institutions together own {pct(inst_now)}, {'up' if di > 0 else 'down'} from {pct(inst_then)} a "
                  f"year ago.", title=f"Institutions {'adding' if di > 0 else 'reducing'} together",
                  stat=f"{pct(inst_then)} → {pct(inst_now)}")
    if f and d_ and f[-1] is not None and d_[-1] is not None and f[-1] + d_[-1] < T["low_inst"]:
        c.add("I7", None, "neutral", 35, f"Institutions own only {pct(f[-1] + d_[-1])} of the company.",
              title="Few institutional owners", stat=f"institutions {pct(f[-1] + d_[-1])}")

    # multi-year highs and lows, one sentence for all groups
    hi, lo = [], []
    for key, label, _ in groups:
        xs = [x for x in c.s(key)[-21:] if x is not None]
        if len(xs) < 9 or max(xs) - min(xs) < T["extreme_range"]:
            continue
        if xs[-1] >= max(xs) - 0.005:
            hi.append(key)
        elif xs[-1] <= min(xs) + 0.005:
            lo.append(key)
    if hi or lo:
        n_vals = min(21, c.n)
        span = _span(n_vals, c.periods[-n_vals])

        def owners(keys):
            names = [POSS[k] for k in keys]
            joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
            return joined + (" holding is" if len(names) == 1 else " holdings are")
        parts = []
        if lo:
            parts.append(owners(lo) + " the lowest")
        if hi:
            parts.append(owners(hi) + " the highest")
        text = ", while ".join(parts) + f" {span}."
        yrs = re.search(r"(\w+) years?", span)
        n_txt = {"two": "2", "three": "3", "four": "4", "five": "5"}.get(yrs.group(1), yrs.group(1)) if yrs else ""
        tag = f"{n_txt}-year" if n_txt else "record"
        def names(keys, first):
            xs = [SHORT[k] if (first and i == 0) or k == "dii" else SHORT[k].lower() for i, k in enumerate(keys)]
            return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]
        bits = []
        if lo:
            bits.append(f"{names(lo, True)} at {tag} low{'s' if len(lo) > 1 else ''}")
        if hi:
            bits.append(f"{names(hi, not lo)} at {'' if lo else tag + ' '}high{'s' if len(hi) > 1 else ''}")
        title = ", ".join(bits)
        c.add("I4", None, "neutral", 55, text[0].upper() + text[1:], highs=hi, lows=lo, title=title,
              stat=" · ".join(f"{SHORT[k]} {pct(c.now(k))}" for k in lo + hi))

    # big single-quarter moves (promoter moves are covered by the promoter rules)
    for key, label, _ in groups:
        if key == "promoters":
            continue
        xs = c.s(key)
        if _ago(xs, 1) is None or xs[-1] is None:
            continue
        d = xs[-1] - _ago(xs, 1)
        base = _ago(xs, 1)
        if abs(d) >= T["big_quarter"] or (abs(d) >= T["big_quarter_small"] and base and abs(d) / base >= T["big_quarter_rel"]):
            c.add("I5", key, "neutral", 62,
                  f"{label} {'rose' if d > 0 else 'fell'} {pts(d, sign=False)} in the latest quarter alone, to "
                  f"{pct(xs[-1])}.", change_pts=round(d, 2), title=f"Big quarter for {SHORT[key].lower()}",
                  stat=f"{pts(d)} to {pct(xs[-1])}")

    # ---- retail
    pub = c.s("public")
    for q, thr, when in ((4, T["retail_shift_1y"], "Over the year"), (12, T["retail_shift_3y"], "Over three years")):
        if _ago(pub, q) is None or _ago(f, q) is None or _ago(d_, q) is None:
            continue
        dp = pub[-1] - _ago(pub, q)
        di = (f[-1] + d_[-1]) - (_ago(f, q) + _ago(d_, q))
        if dp >= thr and di <= -thr:
            c.add("R1", "public", "watch", 76,
                  f"{when} shares have moved from institutions to individual investors: retail and others hold "
                  f"{pct(pub[-1])} (from {pct(_ago(pub, q))}), institutions {pct(f[-1] + d_[-1])} "
                  f"(from {pct(_ago(f, q) + _ago(d_, q))}).", title="Shares moving to individual investors",
                  stat=f"retail {pct(_ago(pub, q))} → {pct(pub[-1])} {_short_when(q)}")
            break
    hn, hn_ago = (c.holders_n[-1] if c.holders_n else None), _ago(c.holders_n, 4)
    if hn and hn_ago:
        g = (hn / hn_ago - 1) * 100
        if abs(g) >= T["holders_pct"]:
            c.add("R2", None, "neutral", 50,
                  f"The number of shareholders {'rose' if g > 0 else 'fell'} {abs(g):.0f}% in a year, to "
                  f"{count_in(hn)}.", change_pct=round(g, 1), holders=hn,
                  title=f"Shareholders {'up' if g > 0 else 'down'} {abs(g):.0f}% in a year", stat=count_in(hn))

    # ---- share count
    sh, sh_ago = (c.shares[-1] if c.shares else None), _ago(c.shares, 4)
    if sh and sh_ago:
        g = (sh / sh_ago - 1) * 100
        if g >= T["share_count_pct"] and not any(s["id"] in ("P1", "P3") and s["facts"].get("share_count_change_pct")
                                                 for s in c.signals):
            c.add("S1", None, "neutral", 52,
                  f"The company issued new shares: the share count grew {g:.1f}% in the year, so every holder who did "
                  f"not take part now owns a smaller percentage.", title="New shares issued",
                  stat=f"share count +{g:.1f}% in a year")
        elif g <= -T["share_count_pct"]:
            c.add("S2", None, "neutral", 52,
                  f"The share count fell {abs(g):.1f}% in the year (a buyback), so remaining holders own a larger "
                  f"percentage without buying.", title="Buyback reduced the share count",
                  stat=f"share count −{abs(g):.1f}%")

    # ---- named holders
    for name, grp, now, ago in pack.get("holders") or []:
        now, ago = _f(now), _f(ago)
        nm = _title(name)
        if now is not None and ago is not None and abs(now - ago) >= T["named_move"]:
            c.add("H1", grp, "neutral", 45,
                  f"{nm} {'raised' if now > ago else 'cut'} its stake to {now:.2f}% from {ago:.2f}%.",
                  title=f"{nm} {'raised' if now > ago else 'cut'} its stake", stat=f"{ago:.2f}% → {now:.2f}%")
        elif now is not None and now >= 1 and (ago is None or ago < 1):
            c.add("H1", grp, "neutral", 45, f"{nm} now holds {now:.2f}% (under 1% a year ago).",
                  title=f"{nm} now holds over 1%", stat=f"{now:.2f}%")
        elif ago is not None and ago >= 1 and (now is None or now < 1):
            c.add("H1", grp, "neutral", 45, f"{nm} held {ago:.2f}% a year ago and now holds under 1%.",
                  title=f"{nm} now under 1%", stat=f"was {ago:.2f}%")

    signals = sorted(c.signals, key=lambda s: -s["priority"])
    headline, top, covered = [], [], set()
    for s in signals:
        if s["id"] in covered:
            continue
        headline.append(s["text"])
        top.append(s)
        covered.update(s["covers"])
        if len(headline) == 3:
            break
    card = lambda s: {"id": s["id"], "tone": s["tone"], "title": s["title"], "stat": s["stat"], "text": s["text"]}
    cards = [card(s) for s in top]
    more = [card(s) for s in signals if s not in top]
    facts = {
        "as_of": c.periods[-1],
        "compared_with": c.periods[-5] if c.n >= 5 else c.periods[0],
        "share_count_cr": sh, "share_count_change_1y_pct": None if not (sh and sh_ago) else round((sh / sh_ago - 1) * 100, 2),
        "promoter_pledged_pct": pl, "locked_in_pct": lk, "shareholders": hn,
        "shareholders_change_1y_pct": None if not (hn and hn_ago) else round((hn / hn_ago - 1) * 100, 1),
        "share_count_by_period": {p: v for p, v in zip(c.periods, c.shares) if v is not None},
        "top_holders": sorted([{"name": _title(h[0]), "group": h[1], "now": _f(h[2]), "year_ago": _f(h[3])}
                               for h in pack.get("holders") or [] if _f(h[2])], key=lambda x: -x["now"])[:6],
    }
    return {"symbol": pack.get("symbol"), "as_of": c.periods[-1], "table": table, "facts": facts,
            "signals": signals, "headline": headline, "cards": cards, "more": more,
            "quiet_text": None if headline else QUIET,
            "rules_version": RULES_VERSION, "disclaimer": DISCLAIMER}


def _title(name: Any) -> str:
    s = str(name or "").strip()
    if s.isupper():
        s = s.title()
    return re.sub(r"\bOf\b", "of", s)


QUIET = "No notable change in who owns the company in this filing."


def as_text(view: Dict[str, Any]) -> str:
    """The card as plain text (command line, alerts, checking by eye)."""
    L = [f"{view.get('symbol') or ''} ownership, {view['as_of']}"]
    for r in view["table"]:
        ch = "" if r["change_1y"] is None else f"  1y {pts(r['change_1y'])}"
        L.append(f"  {r['label']:<24}{pct(r['now']):>7}{ch}")
    L.append("")
    L += [f"* {h}" for h in view["headline"]] or [view["quiet_text"]]
    rest = [s for s in view["signals"] if s["text"] not in view["headline"]]
    if rest:
        L.append("Also in this filing:")
        L += [f"  - {s['text']}" for s in rest]
    L.append(view["disclaimer"])
    return "\n".join(L)


def cli(argv: Sequence[str]) -> int:
    """python -m finlit_technicals ownership PACK.json [--json]
       python -m finlit_technicals ownership-batch --packs DIR --out DIR      (one <SYMBOL>.json per pack)
       python -m finlit_technicals ownership-rules"""
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(prog="finlit_technicals ownership")
    ap.add_argument("command", choices=["ownership", "ownership-batch", "ownership-rules"])
    ap.add_argument("pack", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--packs")
    ap.add_argument("--out")
    a = ap.parse_args(list(argv))
    if a.command == "ownership-rules":
        print(json.dumps({"rules_version": RULES_VERSION, "rules": rules_table()}, ensure_ascii=False, indent=1))
        return 0
    if a.command == "ownership-batch":
        if not (a.packs and a.out):
            ap.error("ownership-batch needs --packs and --out")
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        n = bad = 0
        for f in sorted(Path(a.packs).glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                pack = json.loads(f.read_text(encoding="utf-8"))
                pack.setdefault("symbol", f.stem.upper())
                (out / f"{f.stem.upper()}.json").write_text(json.dumps(analyse(pack), ensure_ascii=False), encoding="utf-8")
                n += 1
            except Exception as e:  # one bad pack must not stop the night's run
                bad += 1
                print(f"{f.name}: {e}")
        print(f"ownership: {n} written, {bad} failed")
        return 0 if n or not bad else 1
    if not a.pack:
        ap.error("give a pack file")
    pack = json.loads(Path(a.pack).read_text(encoding="utf-8"))
    pack.setdefault("symbol", Path(a.pack).stem.upper())
    v = analyse(pack)
    print(json.dumps(v, ensure_ascii=False, indent=1) if a.json else as_text(v))
    return 0


def rules_table() -> List[Dict[str, str]]:
    return [{"id": r[0], "name": r[1], "when": r[2], "tone": r[3]} for r in RULES]
