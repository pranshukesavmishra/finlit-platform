"""P&L divergence flags: eight situations where revenue and profit tell different stories, worked out from a company's own reported
yearly and quarterly profit-and-loss tables (₹ crore). Pure functions, no I/O. This is the Python twin of frontend/src/lib/plFlags.ts;
both run the shared cases in frontend/src/lib/fixtures/plFlags.cases.json (see backend/tests/test_plflags.py), so they cannot drift apart.

A flag is information ("worth a closer look"), never advice. Missing data never makes a flag. Revenue growth needs a positive earlier
revenue; per-cent profit growth needs a positive earlier profit (on a zero or negative base only the direction is used, and the size
tests of cases 1 and 5 are skipped, apart from a swing from a loss to a profit in case 5). Comparisons are against the same period a year
earlier, matched on period end dates; quarter on quarter is used for case 1 only. Moves under DEAD_BAND per cent count as flat.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, List, Optional

DEAD_BAND = 0.5       # per cent: smaller moves count as flat
RATIO = 3             # case 1: profit growth more than 3x revenue growth
MIN_PROFIT_JUMP = 10  # case 1: ...and profit up at least this much
REVENUE_SHARP = 20    # case 4
NEAR_ZERO = 2         # case 4: profit growth at or below this is "barely grows"
PROFIT_SHARP = 30     # case 5
FLAT_BAND = 5         # case 5: revenue growth within -5..+5
RUN_QUARTERS = 2      # case 8

CASES: Dict[int, Dict[str, str]] = {
    1: dict(id="profit_outgrows_revenue", title="Profit is growing much faster than revenue", severity="watch", why="Profit can be lifted by one-off items or unusual cost savings."),
    2: dict(id="revenue_down_profit_up", title="Revenue fell while profit rose", severity="watch", why="Worth checking for one-off gains, cost cuts or a change in margins."),
    3: dict(id="revenue_up_profit_down", title="Revenue rose while profit fell", severity="caution", why="Costs may be rising faster than sales, or profitability may be weakening."),
    4: dict(id="revenue_up_profit_flat", title="Revenue rose sharply but profit did not follow", severity="caution", why="Growth that does not reach profit may be of lower quality."),
    5: dict(id="profit_up_revenue_flat", title="Profit rose sharply on flat revenue", severity="watch", why="Earnings may be leaning on non-operating gains or exceptional savings."),
    6: dict(id="both_down", title="Revenue and profit both fell", severity="caution", why="This can be a sign of a business slowdown."),
    7: dict(id="net_up_operating_down", title="Net profit rose while operating profit fell", severity="watch", why="Non-operating income or tax effects may be driving the earnings."),
    8: dict(id="persistent_divergence", title="Revenue and profit have moved in opposite directions for several quarters", severity="caution", why="A repeating gap can point to a structural change or unusual earnings."),
}

Table = Dict[str, Any]


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def _at(t: Optional[Table], key: str, i: int) -> Optional[float]:
    rows = (t or {}).get("rows") or {}
    col = rows.get(key)
    return _num(col[i]) if isinstance(col, list) and 0 <= i < len(col) else None


def _day(s: Any) -> Optional[int]:
    try:
        return date.fromisoformat(str(s)[:10]).toordinal() if isinstance(s, str) else None
    except ValueError:
        return None


_RANGE = {"year": (335, 395, 365), "quarter": (75, 105, 91)}


def prior_index(t: Optional[Table], i: int, back: str) -> Optional[int]:
    """Index of the period that ended about one year (or quarter) before period i, matched on period end dates."""
    ends = (t or {}).get("periodEnds") or []
    cur = _day(ends[i]) if i < len(ends) else None
    if cur is None:
        return _annual_fallback(t, i, back)
    lo, hi, target = _RANGE[back]
    best, best_d = None, float("inf")
    for j in range(i):
        e = _day(ends[j]) if j < len(ends) else None
        if e is None:
            continue
        d = cur - e
        if lo <= d <= hi and abs(d - target) < best_d:
            best, best_d = j, abs(d - target)
    return best


def _annual_fallback(t: Optional[Table], i: int, back: str) -> Optional[int]:
    import re
    if back != "year" or i < 1:
        return None
    per = (t or {}).get("periods") or []
    a = re.fullmatch(r"FY(\d{2})", per[i]) if i < len(per) and isinstance(per[i], str) else None
    b = re.fullmatch(r"FY(\d{2})", per[i - 1]) if i - 1 < len(per) and isinstance(per[i - 1], str) else None
    return i - 1 if a and b and (int(a.group(1)) - int(b.group(1)) + 100) % 100 == 1 else None


class Move:
    __slots__ = ("cur", "prev", "pct", "dir")

    def __init__(self, cur: float, prev: float, pct: Optional[float], d: int):
        self.cur, self.prev, self.pct, self.dir = cur, prev, pct, d


def move(cur: Optional[float], prev: Optional[float]) -> Optional[Move]:
    if cur is None or prev is None:
        return None
    if prev == 0:
        return Move(cur, prev, None, 1 if cur > 0 else -1 if cur < 0 else 0)
    pct = (cur - prev) / abs(prev) * 100
    return Move(cur, prev, pct, 0 if abs(pct) < DEAD_BAND else (1 if cur > prev else -1))


def _rev_move(cur: Optional[float], prev: Optional[float]) -> Optional[Move]:
    return move(cur, prev) if prev is not None and prev > 0 else None


def _pct_pos(m: Optional[Move]) -> Optional[float]:
    return m.pct if m is not None and m.prev > 0 else None


def _r1(v: float) -> float:
    return math.floor(v * 10 + 0.5) / 10


def _pc(v: float) -> str:
    return f"{_r1(abs(v)):.1f}%"


def _crore(v: float) -> str:
    n = str(math.floor(abs(v) + 0.5))
    if len(n) > 3:   # Indian grouping, as the front end writes it: 1,23,456
        n = _lakh(n)
    return "₹" + n + " crore"


def _lakh(n: str) -> str:
    head, tail = n[:-3], n[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def _verb(m: Move) -> str:
    return "rose" if m.dir > 0 else "fell" if m.dir < 0 else "was flat"


def _money(v: float) -> str:
    return ("a loss of " if v < 0 else "a profit of ") + _crore(v)


def _profit_words(m: Move) -> str:
    if m.prev <= 0 or m.cur <= 0:
        if (m.prev < 0 < m.cur) or (m.prev > 0 > m.cur):
            return f"net profit turned from {_money(m.prev)} to {_money(m.cur)}"
        return f"net result moved from {'zero' if m.prev == 0 else _money(m.prev)} to {'zero' if m.cur == 0 else _money(m.cur)}"
    return f"net profit {_verb(m)} {'' if m.pct is None else _pc(m.pct)}".strip()


def _pair(t: Table, i: int, j: int) -> Dict[str, Optional[Move]]:
    return {"rev": _rev_move(_at(t, "revenue", i), _at(t, "revenue", j)),
            "np": move(_at(t, "net_profit", i), _at(t, "net_profit", j)),
            "op": move(_at(t, "operating_profit", i), _at(t, "operating_profit", j))}


def _evaluate(p: Dict[str, Optional[Move]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    rev, np_, op = p["rev"], p["np"], p["op"]
    if rev and np_:
        rg, pg = rev.pct, _pct_pos(np_)
        flat_rev = rg is not None and -FLAT_BAND <= rg <= FLAT_BAND
        five = flat_rev and ((pg is not None and pg > PROFIT_SHARP) or (np_.prev < 0 < np_.cur))
        if five:
            out.append({"no": 5, "text": f"Revenue was nearly flat ({'+' if rg >= 0 else '-'}{_pc(rg)}) while {_profit_words(np_)}."})
        if not five and rg is not None and rg > FLAT_BAND and pg is not None and pg >= MIN_PROFIT_JUMP and pg > RATIO * rg:
            out.append({"no": 1, "text": f"Revenue grew {_pc(rg)} but net profit grew {_pc(pg)}, more than {RATIO} times as fast."})
        if not five and rev.dir < 0 and np_.dir > 0:
            out.append({"no": 2, "text": f"Revenue {_verb(rev)} {_pc(rev.pct)} while {_profit_words(np_)}."})
        barely = np_.pct <= NEAR_ZERO if np_.pct is not None else np_.cur <= 0
        four = rg is not None and rg > REVENUE_SHARP and barely
        if four:
            out.append({"no": 4, "text": f"Revenue grew {_pc(rg)} but {_profit_words(np_)}."})
        if not four and rev.dir > 0 and np_.dir < 0:
            out.append({"no": 3, "text": f"Revenue grew {_pc(rev.pct)} while {_profit_words(np_)}."})
        if rev.dir < 0 and np_.dir < 0:
            out.append({"no": 6, "text": f"Revenue fell {_pc(rev.pct)} and {_profit_words(np_)}."})
    if np_ and op and np_.dir > 0 and op.dir < 0:
        w = _profit_words(np_)
        out.append({"no": 7, "text": f"{w[0].upper() + w[1:]}, while operating profit fell{' ' + _pc(op.pct) if op.pct is not None and op.prev > 0 else ''}."})
    return out


def _build(no: int, scope: str, basis: str, t: Table, i: int, j: int, text: str, p: Optional[Dict[str, Optional[Move]]], extra: Optional[List[str]] = None) -> Dict[str, Any]:
    c = CASES[no]
    period, against = t["periods"][i], t["periods"][j]
    rows = ["net_profit", "operating_profit"] if no == 7 else ["revenue", "net_profit"]
    periods: List[str] = []
    for x in [period, against, *(extra or [])]:
        if x and x not in periods:
            periods.append(x)

    def g(m: Optional[Move], pos: bool = False) -> Optional[float]:
        v = _pct_pos(m) if pos else (m.pct if m else None)
        return None if v is None else _r1(v)
    return {"case": no, "id": c["id"], "severity": c["severity"], "scope": scope, "basis": basis, "period": period, "against": against,
            "title": c["title"], "text": f"{text} Compared with {against}.", "why": c["why"],
            "revenueGrowth": g(p["rev"]) if p else None, "profitGrowth": g(p["np"], True) if p else None, "operatingGrowth": g(p["op"], True) if p else None,
            "rows": [k for k in rows if (t.get("rows") or {}).get(k)], "periods": periods, "key": f"{no}:{scope}:{period}"}


def divergence_run(q: Table) -> List[Dict[str, Any]]:
    """Latest quarters (newest first) where revenue and net profit moved in opposite directions against the same quarter a year earlier."""
    steps: List[Dict[str, Any]] = []
    i: Optional[int] = len(q.get("periods") or []) - 1
    while i is not None and i >= 0:
        j = prior_index(q, i, "year")
        if j is None:
            break
        p = _pair(q, i, j)
        if not p["rev"] or not p["np"] or p["rev"].dir == 0 or p["np"].dir == 0 or p["rev"].dir == p["np"].dir:
            break
        steps.append({"i": i, "j": j, "rev": p["rev"].dir})
        i = prior_index(q, i, "quarter")
    return steps


def prepare(t: Optional[Table], lender: bool) -> Optional[Table]:
    """For a lender (bank or NBFC) revenue is the same Revenue line the statements and the results table show; total income is used only when a company has no Revenue line. Operating profit is not a meaningful line for a lender, so it is dropped."""
    if not t or not lender:
        return t
    rows = dict(t.get("rows") or {})
    has = lambda xs: isinstance(xs, list) and any(_num(v) is not None for v in xs)
    if not has(rows.get("revenue")) and has(rows.get("total_income")):
        rows["revenue"] = rows["total_income"]
    rows.pop("operating_profit", None)
    return {**t, "rows": rows}


def _growth(p: Dict[str, Optional[Move]]) -> Dict[str, Optional[float]]:
    return {"revenue": None if not p["rev"] or p["rev"].pct is None else _r1(p["rev"].pct),
            "profit": None if _pct_pos(p["np"]) is None else _r1(_pct_pos(p["np"])),
            "operating": None if _pct_pos(p["op"]) is None else _r1(_pct_pos(p["op"]))}


def period_views(annual: Optional[Table], quarterly: Optional[Table], lender: bool = False) -> Dict[str, Optional[Dict[str, Any]]]:
    """Growth against the same period a year earlier for the latest quarter and the latest year, whether or not a flag fired: the numbers
    shown beside a flag so that both views are always named (period, comparison period, period end)."""
    out: Dict[str, Optional[Dict[str, Any]]] = {"annual": None, "quarterly": None}
    for scope, t in (("annual", prepare(annual, lender)), ("quarterly", prepare(quarterly, lender))):
        if not t or not t.get("periods"):
            continue
        i = len(t["periods"]) - 1
        j = prior_index(t, i, "year")
        if j is None:
            continue
        ends = t.get("periodEnds") or []
        out[scope] = {"scope": scope, "label": "latest quarter" if scope == "quarterly" else "latest year", "period": t["periods"][i], "against": t["periods"][j],
                      "periodEnd": ends[i] if i < len(ends) else None, "growth": _growth(_pair(t, i, j))}
    return out


def pl_flags(annual: Optional[Table], quarterly: Optional[Table], lender: bool = False) -> List[Dict[str, Any]]:
    """All flags for the latest annual and latest quarterly period; [] when the data supports none."""
    out: List[Dict[str, Any]] = []
    a, q = prepare(annual, lender), prepare(quarterly, lender)
    if a and a.get("periods"):
        i = len(a["periods"]) - 1
        j = prior_index(a, i, "year")
        if j is not None:
            p = _pair(a, i, j)
            out += [_build(h["no"], "annual", "yoy", a, i, j, h["text"], p) for h in _evaluate(p)]
    if q and q.get("periods"):
        i = len(q["periods"]) - 1
        y, s = prior_index(q, i, "year"), prior_index(q, i, "quarter")
        if y is not None:
            p = _pair(q, i, y)
            out += [_build(h["no"], "quarterly", "yoy", q, i, y, h["text"], p) for h in _evaluate(p)]
        if s is not None:
            p = _pair(q, i, s)
            h1 = next((h for h in _evaluate(p) if h["no"] == 1), None)
            if h1:
                out.append(_build(1, "quarterly", "qoq", q, i, s, h1["text"], p))
        run = divergence_run(q)
        if len(run) >= RUN_QUARTERS:
            last, first = run[0], run[-1]
            names = [q["periods"][r["i"]] for r in reversed(run)]
            yago = [q["periods"][r["j"]] for r in run]
            words = ("Revenue rose while profit fell" if all(r["rev"] > 0 for r in run) else
                     "Revenue fell while profit rose" if all(r["rev"] < 0 for r in run) else "Revenue and profit moved in opposite directions")
            out.append(_build(8, "quarterly", "run", q, last["i"], last["j"],
                              f"{words} (each against the same quarter a year earlier) in {len(run)} quarters in a row, from {q['periods'][first['i']]} to {q['periods'][last['i']]}.",
                              _pair(q, last["i"], last["j"]), names + yago))
    return _dedupe(out)


def _dedupe(flags: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen, has_run, out = set(), any(f["case"] == 8 for f in flags), []
    for f in flags:
        if has_run and f["scope"] == "quarterly" and f["case"] in (2, 3) and f["basis"] == "yoy":
            continue
        if f["key"] in seen:
            continue
        seen.add(f["key"])
        out.append(f)
    return sorted(out, key=lambda f: f["case"])
