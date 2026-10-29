"""How a company's revenue mix has changed: per-segment trends, a trend tag and descriptive sentences.

Pure functions, no I/O.  Input is the stored `segments` table (`periods` + {name: {revenue[], ebit[]}} in ₹ crore, one value per
period, None where the segment is not reported).  Everything is computed from the unrounded numbers; rounding happens only on the
final output.  Nothing here ever adjusts a number: when a segment's definition looks as if it changed, the row is only flagged.

Rules (also written up in docs/SEGMENTS.md):
  comparable window   longest run of consecutive fiscal years, ending at the latest year, in which the segment's revenue is positive
  CAGR                (end / start) ** (1 / (years - 1)) - 1 over the window; needs >= MIN_YEARS (3) comparable years
  share               segment revenue / sum of all segment revenues in that year (inter-segment eliminations make the sum differ
                      from reported revenue)
  trend tag           Discontinued / merged  not reported (positive) in the latest year
                      New                    first reported in one of the last NEW_WITHIN_YEARS (2) years, and not in the data's first year
                      Not enough history     fewer than 3 comparable years
                      Growing                CAGR >= +5 % a year AND share not down by more than 2 pp
                      Declining              CAGR <= -2 % a year
                      Steady                 anything else
  definition changed  (a) a segment stops being reported in the very year another segment is first reported, or
                      (b) a segment's revenue moves by >= JUMP_FACTOR (3x up, or down to 1/3) in one year, the move is >= 1 % of that
                          year's total, and another segment moves the opposite way by 0.5x to 2x of the same amount in that year.
                      Flag only.  Rows whose window contains such a break are left out of the headline sentences.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

MIN_YEARS = 3                # comparable years needed for a growth rate and for any sentence
GROW_CAGR = 5.0              # % a year at or above which a segment is Growing ...
GROW_MAX_SHARE_LOSS = 2.0    # ... unless its share fell by more than this many percentage points
DECLINE_CAGR = -2.0          # % a year at or below which a segment is Declining
NEW_WITHIN_YEARS = 2         # first reported this recently (and not in the first year of data) -> New
JUMP_FACTOR = 3.0
JUMP_MIN_TOTAL_PCT = 1.0     # a jump smaller than this % of the year's total is noise
OFFSET_LOW, OFFSET_HIGH = 0.5, 2.0
RANK_MIN_SHARE = 1.0         # % of revenue a segment needs (at the end of its window) to be named fastest / gainer / loser
MIN_SHARE_MOVE = 0.5         # pp: smaller moves are not called a gain or a loss
MAX_SENTENCES = 5

TAGS = {
    "growing": "Growing", "declining": "Declining", "steady": "Steady", "new": "New",
    "discontinued": "Discontinued / merged", "short": "Not enough history",
}
BASIS = ("Shares are of the sum of the segment revenues. Inter-segment sales are removed from reported revenue, "
         "so that sum can differ from the company's reported revenue.")
THRESHOLDS = {
    "minYears": MIN_YEARS, "growingCagrPct": GROW_CAGR, "growingMaxShareLossPp": GROW_MAX_SHARE_LOSS,
    "decliningCagrPct": DECLINE_CAGR, "newWithinYears": NEW_WITHIN_YEARS, "jumpFactor": JUMP_FACTOR,
}


def fy_number(label: Any) -> Optional[int]:
    """'FY26' -> 26 (the two-digit year); anything else -> None."""
    text = str(label or "")
    if len(text) >= 4 and text[:2] == "FY" and text[2:].isdigit():
        return int(text[2:])
    return None


def _num(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return None if value != value else float(value)  # NaN -> None


def _r(value: Optional[float], digits: int = 2) -> Optional[float]:
    return None if value is None else round(value, digits)


def cagr_pct(start: float, end: float, years: int) -> Optional[float]:
    """Compound annual growth in %, `years` = number of comparable years (so years - 1 growth steps)."""
    if years < 2 or start is None or end is None or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1.0 / (years - 1)) - 1.0) * 100.0


def comparable_window(revenue: List[Optional[float]], years: List[Optional[int]]) -> Tuple[Optional[int], Optional[int]]:
    """(start index, end index) of the longest run of consecutive fiscal years with positive revenue that ends at the last
    period; (None, None) when the segment has no positive revenue in the last period.  A gap in the periods themselves
    (a missing fiscal year) also ends the run."""
    n = len(revenue)
    if not n or revenue[-1] is None or revenue[-1] <= 0 or years[-1] is None:
        return None, None
    start = n - 1
    while start > 0:
        prev = start - 1
        v = revenue[prev]
        if v is None or v <= 0 or years[prev] is None or years[prev] != years[start] - 1:
            break
        start = prev
    return start, n - 1


def _last_positive(revenue: List[Optional[float]]) -> Optional[int]:
    for i in range(len(revenue) - 1, -1, -1):
        v = revenue[i]
        if v is not None and v > 0:
            return i
    return None


def _first_positive(revenue: List[Optional[float]]) -> Optional[int]:
    for i, v in enumerate(revenue):
        if v is not None and v > 0:
            return i
    return None


def _totals(table: Dict[str, dict], n: int) -> List[float]:
    out = []
    for i in range(n):
        out.append(sum(v for v in ((t["revenue"][i] if i < len(t["revenue"]) else None) for t in table.values()) if v is not None))
    return out


def _clean(periods: List[str], table: Dict[str, dict]) -> Dict[str, dict]:
    """Same table with numbers coerced (junk -> None) and every series exactly as long as `periods`."""
    n = len(periods)
    out = {}
    for name, series in (table or {}).items():
        if not isinstance(series, dict):
            continue
        rev = [_num(v) for v in (series.get("revenue") or [])][:n]
        ebit = [_num(v) for v in (series.get("ebit") or [])][:n]
        out[name] = {"revenue": rev + [None] * (n - len(rev)), "ebit": ebit + [None] * (n - len(ebit))}
    return out


def detect_definition_changes(periods: List[str], table: Dict[str, dict]) -> Dict[str, dict]:
    """{segment: {"year": "FY24", "note": "..."}} for segments whose definition looks as if it changed. Flags only."""
    n = len(periods)
    years = [fy_number(p) for p in periods]
    totals = _totals(table, n)
    flags: Dict[str, dict] = {}

    def flag(name: str, year: str, note: str, kind: str) -> None:
        if name not in flags:  # the first (oldest) reason is kept
            flags[name] = {"year": year, "note": note, "kind": kind}

    firsts = {name: _first_positive(t["revenue"]) for name, t in table.items()}
    lasts = {name: _last_positive(t["revenue"]) for name, t in table.items()}
    # (a) one segment stops in the year another starts.
    for gone, last in lasts.items():
        if last is None or last >= n - 1:
            continue
        stop = last + 1  # first period without it
        for new, first in firsts.items():
            if new != gone and first == stop and stop > 0:
                year = periods[stop]
                flag(gone, year, f"{gone} stopped being reported in {year}, the year {new} started; the two may be a reorganisation of the same business.", "stopped")
                flag(new, year, f"{new} started in {year}, the year {gone} stopped being reported; the two may be a reorganisation of the same business.", "started")
    # (b) a big one-year jump matched by another segment moving the other way.
    for i in range(1, n):
        if years[i] is None or years[i - 1] is None or years[i] != years[i - 1] + 1 or totals[i] <= 0:
            continue
        moves = {}
        for name, t in table.items():
            a, b = t["revenue"][i - 1], t["revenue"][i]
            if a is not None and b is not None and a > 0 and b > 0:
                moves[name] = (a, b, b - a)
        for name, (a, b, d) in moves.items():
            big_up, big_down = b >= JUMP_FACTOR * a, b <= a / JUMP_FACTOR
            if not (big_up or big_down) or abs(d) < totals[i] * JUMP_MIN_TOTAL_PCT / 100.0:
                continue
            for other, (_, _, od) in moves.items():
                if other == name or od * d >= 0:
                    continue
                if OFFSET_LOW * abs(d) <= abs(od) <= OFFSET_HIGH * abs(d):
                    year = periods[i]
                    word = "jumped" if big_up else "dropped"
                    flag(name, year, f"{name} revenue {word} by more than {JUMP_FACTOR:g}x in {year} while {other} moved the other way by a similar amount; the split between them may have been redrawn.", "jump")
                    flag(other, year, f"{other} revenue moved sharply in {year} while {name} moved the other way by a similar amount; the split between them may have been redrawn.", "jump")
    return flags


def _big_jumps(periods: List[str], table: Dict[str, dict]) -> List[Tuple[str, str]]:
    """(segment, year) pairs where revenue changed by >= JUMP_FACTOR in one year (more than 1% of the total): a caution, not a flag."""
    n, years, totals = len(periods), [fy_number(p) for p in periods], _totals(table, len(periods))
    out = []
    for name, t in table.items():
        for i in range(1, n):
            a, b = t["revenue"][i - 1], t["revenue"][i]
            if years[i] is None or years[i - 1] is None or years[i] != years[i - 1] + 1 or a is None or b is None or a <= 0 or b <= 0 or totals[i] <= 0:
                continue
            if (b >= JUMP_FACTOR * a or b <= a / JUMP_FACTOR) and abs(b - a) >= totals[i] * JUMP_MIN_TOTAL_PCT / 100.0:
                out.append((name, periods[i]))
    return out


def _join(names: List[str]) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def segment_rows(periods: List[str], table: Dict[str, dict], flags: Dict[str, dict]) -> List[dict]:
    n = len(periods)
    years = [fy_number(p) for p in periods]
    totals = _totals(table, n)
    latest = periods[-1]
    first_year_data = 0
    rows = []
    for name, t in table.items():
        rev, ebit = t["revenue"], t["ebit"]
        first, last = _first_positive(rev), _last_positive(rev)
        row: Dict[str, Any] = {
            "name": name, "trend": "short", "trendLabel": TAGS["short"], "firstReported": periods[first] if first is not None else None,
            "lastReported": periods[last] if last is not None else None, "window": None, "years": 0, "revenue": None, "sharePct": None,
            "shareStartPct": None, "shareChangePp": None, "cagrPct": None, "yoyPct": None, "marginPct": None, "marginChangePp": None,
            "definitionChanged": name in flags, "definitionYear": flags.get(name, {}).get("year"), "definitionNote": flags.get(name, {}).get("note"),
            "definitionKind": flags.get(name, {}).get("kind"),
            "windowAffected": False, "note": None,
        }
        if last is None:
            rows.append(row)
            continue
        start, end = comparable_window(rev, years)
        if start is None:  # not reported in the latest year
            row.update(trend="discontinued", trendLabel=TAGS["discontinued"], note=f"Not reported in {latest}; last reported in {periods[last]}.",
                       lastRevenue=_r(rev[last]), lastSharePct=_r(rev[last] / totals[last] * 100.0) if totals[last] > 0 else None)
            rows.append(row)
            continue
        count = end - start + 1
        share = lambda i: rev[i] / totals[i] * 100.0 if totals[i] > 0 else None  # noqa: E731
        s0, s1 = share(start), share(end)
        row.update(window=[periods[start], periods[end]], years=count, revenue=_r(rev[end]), sharePct=_r(s1),
                   shareStartPct=_r(s0), shareChangePp=_r(s1 - s0) if s0 is not None and s1 is not None else None)
        if end >= 1 and rev[end - 1] is not None and rev[end - 1] > 0 and years[end - 1] == years[end] - 1:
            row["yoyPct"] = _r((rev[end] / rev[end - 1] - 1.0) * 100.0)
        if ebit[end] is not None:
            row["marginPct"] = _r(ebit[end] / rev[end] * 100.0)
            if ebit[start] is not None and count >= 2:
                row["marginChangePp"] = _r(ebit[end] / rev[end] * 100.0 - ebit[start] / rev[start] * 100.0)
        growth = cagr_pct(rev[start], rev[end], count) if count >= MIN_YEARS else None
        row["cagrPct"] = _r(growth)
        pp = (s1 - s0) if s0 is not None and s1 is not None else 0.0
        row["_cagr"], row["_pp"], row["_s1"] = growth, pp, s1
        row["gap"] = first is not None and start > first  # reported earlier, but not in an unbroken run to the latest year  # unrounded, for the sentences; dropped before output
        if flags.get(name) and flags[name]["year"] in periods[start + 1:end + 1]:
            row["windowAffected"] = True
        recent = first is not None and first > first_year_data and first >= n - NEW_WITHIN_YEARS and first == start
        if recent:
            tag = "new"
        elif growth is None:
            tag = "short"
        elif growth <= DECLINE_CAGR:
            tag = "declining"
        elif growth >= GROW_CAGR and pp >= -GROW_MAX_SHARE_LOSS:
            tag = "growing"
        else:
            tag = "steady"
        row["trend"], row["trendLabel"] = tag, TAGS[tag]
        if tag == "new":
            row["note"] = f"First reported in {periods[first]}."
        elif tag == "short":
            row["note"] = "Not enough years to work out a growth rate."
        rows.append(row)
    return rows


def _one(x: float) -> str:
    return f"{x:.1f}"


def _cr(x: float) -> str:
    return f"{x:,.0f}"


def sentences(periods: List[str], table: Dict[str, dict], rows: List[dict]) -> List[str]:
    """At most MAX_SENTENCES descriptive sentences, each with the numbers and the period it rests on."""
    latest = periods[-1]
    usable = [r for r in rows if r["years"] >= MIN_YEARS and r["trend"] != "discontinued" and not r["windowAffected"]]
    if not usable:
        return []
    # "Others" is a catch-all of whatever the company does not break out, so it is never named fastest, gainer or loser.
    ranked = [r for r in usable if (r["_s1"] or 0) >= RANK_MIN_SHARE and r["name"].strip().lower() != "others"]
    jumps = {}
    for nm, yr in _big_jumps(periods, table):
        jumps.setdefault(nm, []).append(yr)
    span = lambda r: f"{r['window'][0]} to {r['window'][1]}"  # noqa: E731
    out: List[str] = []
    grow = [r for r in ranked if r["_cagr"] is not None and r["_cagr"] > 0]
    if grow:
        r = max(grow, key=lambda x: x["_cagr"])
        t = table[r["name"]]["revenue"]
        i0 = periods.index(r["window"][0])
        out.append(f"{r['name']} had the fastest revenue growth among the segments, {_one(r['_cagr'])}% a year from {span(r)} (₹{_cr(t[i0])} Cr to ₹{_cr(r['revenue'])} Cr)"
                   + (f", including a single-year change of more than three times in {_join(jumps[r['name']])}." if r["name"] in jumps else "."))
    gain = [r for r in ranked if r["_pp"] >= MIN_SHARE_MOVE]
    lose = [r for r in ranked if r["_pp"] <= -MIN_SHARE_MOVE]
    if gain:
        r = max(gain, key=lambda x: x["_pp"])
        out.append(f"{r['name']} gained the most share of segment revenue: from {_one(r['shareStartPct'])}% to {_one(r['sharePct'])}% ({_one(r['_pp'])} percentage points up) over {span(r)}.")
    if lose:
        r = min(lose, key=lambda x: x["_pp"])
        out.append(f"{r['name']} lost the most share of segment revenue: from {_one(r['shareStartPct'])}% to {_one(r['sharePct'])}% ({_one(abs(r['_pp']))} percentage points down) over {span(r)}.")
    shrink = [r for r in ranked if r["trend"] == "declining" and r["_cagr"] is not None]
    if shrink:
        r = min(shrink, key=lambda x: x["_cagr"])
        out.append(f"{r['name']} revenue fell {_one(abs(r['_cagr']))}% a year from {span(r)}.")
    stopped = [r for r in rows if r["trend"] == "discontinued"]
    if stopped:
        names = _join([f"{r['name']} (last reported {r['lastReported']})" for r in stopped[:3]])
        one = len(stopped[:3]) == 1
        out.append(f"{names} {'is' if one else 'are'} not reported in {latest}; the company may have merged {'it' if one else 'them'} into another segment or stopped reporting.")
    # concentration: the largest segment's share, over the run of consecutive years ending at the latest year
    years = [fy_number(p) for p in periods]
    start = len(periods) - 1
    while start > 0 and years[start] is not None and years[start - 1] == years[start] - 1:
        start -= 1
    totals = _totals(table, len(periods))
    if len(periods) - start >= MIN_YEARS:
        def top(i: int) -> Optional[Tuple[str, float]]:
            vals = [(nm, t["revenue"][i]) for nm, t in table.items() if t["revenue"][i] is not None and t["revenue"][i] > 0]
            return (max(vals, key=lambda x: x[1])[0], max(v for _, v in vals) / totals[i] * 100.0) if vals and totals[i] > 0 else None
        a, b = top(start), top(len(periods) - 1)
        if a and b:
            d = b[1] - a[1]
            who = f"{b[0]}" if a[0] == b[0] else f"{a[0]} in {periods[start]}, {b[0]} in {latest}"
            if abs(d) >= 1.0:
                out.append(f"The largest segment ({who}) went from {_one(a[1])}% to {_one(b[1])}% of segment revenue between {periods[start]} and {latest}, so revenue became {'more' if d > 0 else 'less'} concentrated.")
            else:
                out.append(f"The largest segment ({who}) stayed at about {_one(b[1])}% of segment revenue between {periods[start]} and {latest}.")
    return out[:MAX_SENTENCES]


def cautions(periods: List[str], table: Dict[str, dict], rows: List[dict], flags: Dict[str, dict]) -> List[str]:
    out: List[str] = []
    latest = periods[-1]
    by_year: Dict[str, List[str]] = {}
    for name, f in flags.items():
        by_year.setdefault(f["year"], []).append(name)
    for year in sorted(by_year, key=lambda y: fy_number(y) or 0):
        before = [n for n in by_year[year] if flags[n]["kind"] != "started"]
        began = [n for n in by_year[year] if flags[n]["kind"] == "started"]
        tail = f" ({_join(began)} first reported in {year})" if began else ""
        out.append(f"Segment definitions can change when a company reorganises; years before {year} may not be comparable for {_join(before)}{tail}.")
    jumps = [(n, y) for n, y in _big_jumps(periods, table) if flags.get(n, {}).get("year") != y]
    if jumps:
        out.append("Revenue changed by more than three times in a single year for " + _join([f"{n} ({y})" for n, y in jumps[:4]]) + "; read those growth rates with care.")
    gaps = [r["name"] for r in rows if r.get("gap")][:4]
    if gaps:
        out.append(f"{_join(gaps)} {'has' if len(gaps) == 1 else 'have'} gaps in the reported years, so the comparison starts after the last gap.")
    return out


def build_insights(periods: List[str], table: Dict[str, dict]) -> dict:
    """The `insights` block stored with the report's segments section. Never raises on odd input."""
    periods = [p for p in (periods or []) if isinstance(p, str)]
    clean = _clean(periods, table or {})
    # a segment that never reports anything (all missing or zero) tells us nothing
    clean = {k: v for k, v in clean.items() if any(x not in (None, 0) for x in v["revenue"])}
    base = {"basis": BASIS, "thresholds": THRESHOLDS, "latestPeriod": periods[-1] if periods else None, "rows": [], "sentences": [], "cautions": []}
    if not periods or not clean:
        return {**base, "status": "none", "statusText": "Segment history is not available for this company."}
    if len(clean) == 1:
        return {**base, "status": "single", "statusText": "This company reports a single business segment."}
    flags = detect_definition_changes(periods, clean)
    rows = segment_rows(periods, clean, flags)
    short = len(periods) < MIN_YEARS or not any(r["years"] >= MIN_YEARS for r in rows)
    status = "short" if short else "ok"
    text = (f"Only {len(periods)} year{'s' if len(periods) != 1 else ''} of segment data {'is' if len(periods) == 1 else 'are'} available, so no trends are drawn yet (at least {MIN_YEARS} comparable years are needed)."
            if short else "")
    sents = [] if short else sentences(periods, clean, rows)
    notes = cautions(periods, clean, rows, flags)
    for r in rows:
        for k in ("_cagr", "_pp", "_s1"):
            r.pop(k, None)
        r.setdefault("gap", False)
    order = {"discontinued": 1}
    rows.sort(key=lambda r: (order.get(r["trend"], 0), -((r["revenue"] if r["revenue"] is not None else r.get("lastRevenue")) or 0)))
    return {**base, "status": status, "statusText": text, "rows": rows, "sentences": sents, "cautions": notes}
