"""Fund Compare: two mutual funds of one category head to head over 1, 3, 5 or 10 years, on four questions (returns, risk, consistency,
costs), each fund also measured against its category's average. Built on the same AMFI NAV data as finlit/mf.py; this is information only,
never advice.

Where the numbers come from
  NAV series        1Y / 3Y / 5Y: mf.load_series (AMFI's own stored history for the hot schemes, else the checked mirror; about five years).
                    10Y: the full history of the third-party mirror of AMFI data (api.mfapi.in), used only when its NAV for AMFI's latest (or the
                    previous) NAV date agrees with AMFI's NAVAll. AMFI's own history is stored for five years only, so 10Y always says so.
  Category average  an equal-weighted index of the category's active Growth options on the same plan (Direct by default), one per fund, at most
                    CAT_MAX of them (the largest by AUM when there are more): each weekday the index moves by the average of the members' NAV changes
                    that day. A fund joins on its first NAV day. Funds that closed or merged are not in AMFI's current list, so they are missing from
                    the average (it can flatter the category a little); the page says so. Worked out once per category, plan and NAV date and kept
                    in mf_cat_avg (migration 047), because it needs up to CAT_MAX NAV histories.
  Facts             finlit.disclosure.get_facts: expense ratio (TER), AUM, exit load, benchmark name, managers, risk-o-meter, each with its own date
                    and source, or the reason it is missing.

Not here, on purpose: alpha against the benchmark index. The index levels this site can load (finlit/indices.py, a paid provider) are price
indices without dividends and go back five years only, while a fund's NAV keeps its dividends; the comparison would flatter every fund. The
excess return shown is against the category average, and is labelled that way.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import logging
import math
import re
import statistics
import unicodedata
from bisect import bisect_right
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

import httpx
from fastapi import APIRouter, Query, Request, Response

from . import mf
from .auth.routes import fail
from .background import etag_matches, spawn
from .store import dumps, etag_for

log = logging.getLogger("finlit.mf_compare")
router = APIRouter(prefix="/api/mf-compare")

PERIODS: Dict[str, int] = {"1Y": 12, "3Y": 36, "5Y": 60, "10Y": 120}
ROLLING: Dict[str, int] = {"1Y": 3, "3Y": 12, "5Y": 12, "10Y": 36}   # rolling window length in months for each period
PLANS = ("Direct", "Regular")
RISK_FREE = 6.0
RISK_FREE_NOTE = ("Sharpe ratio = (return per year − 6%) ÷ volatility. The 6% a year stands in for a risk-free return (roughly where India's 91-day Treasury bill "
                  "yield has been over the last decade). It is an assumption, not a measured figure: a different one changes the ratio.")
CAT_MAX = 60               # funds in a category average at most (a few categories have hundreds of index funds)
CAT_MIN = 3                # fewer funds with history than this: no average is shown
CAT_SPAN = 10 * 366 + 40   # days of category index kept: ten years and a little more, so the 10Y start day is inside
CAT_WAIT = 12.0            # seconds a request waits for a category average being worked out before answering "pending"
CAT_FETCHES = 6            # NAV histories fetched at once while building an average
CAT_LOCK = 300
JUMP = 0.5                 # a one-day NAV move larger than 50% is a data error, not a market move: that fund is left out of the average
LONG_TTL = 2 * 86400
CHART_CAP = 300
ROLL_CAP = 260
COMPARE_TTL = 6 * 3600
NO_CACHE = "no-store"
ALPHA_NOTE = ("Excess return = the fund's return per year minus the category average's over the same days. It is measured against the category "
              "average, not the benchmark index: the index levels available here leave out dividends and go back five years only, while a fund's NAV "
              "keeps its dividends, so a benchmark comparison would flatter every fund.")
FACT_KEYS = ("aum", "exitLoad", "benchmark", "managers", "riskometer", "launchDate")


# ====================================================================================== categories

# The same SEBI category under the two wordings AMFI's NAV file uses side by side while fund houses move to the new names (seen October 2026:
# "Equity Scheme - Flexi Cap Fund" and "Equity Schemes - Flexi Cap Fund"). Most differ only by "Scheme(s)" and "Fund"; these two differ more.
_CAT_ALIASES = {
    "equityschemeelsstaxsaver": "equityschemeelss",
    "hybridschemebalancedadvantagedynamicassetallocation": "hybridschemedynamicassetallocationorbalancedadvantage",
}


def cat_key(category: str) -> str:
    """AMFI's category text as a key that is the same for both wordings of one category: 'Equity Schemes - Flexi Cap Fund' and
    'Equity Scheme - Flexi Cap Fund' -> 'equityschemeflexicap'. Categories with different meanings never share a key."""
    t = re.sub(r"\bfunds?\b", "", re.sub(r"\bschemes\b", "scheme", unicodedata.normalize("NFKD", category).lower()))
    k = re.sub(r"[^a-z0-9]+", "", t)
    return _CAT_ALIASES.get(k, k)


def short_category(category: str) -> str:
    return category.split(" - ", 1)[-1].strip()


async def variants(conn, category: str) -> List[str]:
    """Every wording of `category` among the active schemes (the category itself when none is found)."""
    k = cat_key(category)
    got = sorted({r["category"] for r in await conn.fetch("SELECT DISTINCT category FROM mf_schemes WHERE active") if cat_key(r["category"]) == k})
    return got or [category]


# ====================================================================================== the maths (pure, no I/O)

def _d(o: int) -> date:
    return date.fromordinal(o)


def _iso(o: Optional[int]) -> Optional[str]:
    return None if o is None else date.fromordinal(o).isoformat()


def _fmt(o: int) -> str:
    d = date.fromordinal(o)
    return f"{d.day} {d.strftime('%b %Y')}"


def span_label(months: int) -> str:
    if months % 12 == 0:
        y = months // 12
        return f"{y} year{'s' if y > 1 else ''}"
    return f"{months} months"


def rnd(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None or not math.isfinite(v) else round(v, n)


def window(days: Sequence[int], navs: Sequence[float], end: int, months: int) -> Tuple[Optional[Tuple[List[int], List[float]]], Optional[str]]:
    """The part of a series a period covers: from the latest NAV on or before the start date (`months` before `end`, at most mf.MAX_STALE days
    before it) to the latest NAV on or before `end` (also at most mf.MAX_STALE days before it). (None, why) when the series does not cover it."""
    if not days:
        return None, "No NAV history is loaded for this fund."
    start = mf.shift_months(_d(end), months).toordinal()
    i0, i1 = bisect_right(days, start) - 1, bisect_right(days, end) - 1
    if i0 < 0:
        return None, f"NAV history on file starts on {_fmt(days[0])}, less than {span_label(months)} before {_fmt(end)}."
    if start - days[i0] > mf.MAX_STALE:
        return None, f"No NAV within {mf.MAX_STALE} days before the start date ({_fmt(start)})."
    if i1 <= i0 or end - days[i1] > mf.MAX_STALE:
        return None, f"No NAV within {mf.MAX_STALE} days before the end date ({_fmt(end)})."
    return (list(days[i0:i1 + 1]), list(navs[i0:i1 + 1])), None


def point_return(days: Sequence[int], navs: Sequence[float], annualise: bool) -> float:
    """First to last NAV in percent: per year (CAGR, (end / start) ^ (365 / days) - 1) when `annualise`, else the total change."""
    ratio = navs[-1] / navs[0]
    span = days[-1] - days[0]
    return ((ratio ** (365.0 / span) - 1) if annualise and span > 0 else (ratio - 1)) * 100


def rolling(days: Sequence[int], navs: Sequence[float], months: int, annualise: bool) -> Tuple[List[int], List[float]]:
    """Rolling returns: one for each weekday NAV that has a whole window of `months` behind it inside the series. The window starts at the latest
    NAV on or before the same day `months` earlier (at most mf.MAX_STALE days before it). Per year when `annualise`, else the total change."""
    out_d: List[int] = []
    out_v: List[float] = []
    for j in range(1, len(days)):
        e = days[j]
        ed = _d(e)
        if ed.weekday() >= 5:
            continue
        s = mf.shift_months(ed, months).toordinal()
        i = bisect_right(days, s, 0, j) - 1
        if i < 0 or s - days[i] > mf.MAX_STALE:
            continue
        ratio, span = navs[j] / navs[i], e - days[i]
        out_v.append(((ratio ** (365.0 / span) - 1) if annualise else (ratio - 1)) * 100)
        out_d.append(e)
    return out_d, out_v


def roll_stats(d: Sequence[int], v: Sequence[float]) -> dict:
    """Lowest, median and highest rolling return (with the day each lowest / highest window ended) and the share of windows above zero."""
    if not v:
        return {"min": None, "minAt": None, "median": None, "max": None, "maxAt": None, "positive": None, "count": 0,
                "why": "The period is too short for a whole rolling window."}
    lo = min(range(len(v)), key=v.__getitem__)
    hi = max(range(len(v)), key=v.__getitem__)
    return {"min": rnd(v[lo]), "minAt": _iso(d[lo]), "median": rnd(statistics.median(v)), "max": rnd(v[hi]), "maxAt": _iso(d[hi]),
            "positive": rnd(100.0 * sum(1 for x in v if x > 0) / len(v), 1), "count": len(v), "why": None}


def tally(xd: Sequence, xv: Sequence[float], yd: Sequence, yv: Sequence[float]) -> dict:
    """How often x was higher than y, over the keys (days, months, years) both have: {a: x higher, b: y higher, ties, n}."""
    other = dict(zip(yd, yv))
    a = b = t = 0
    for k, x in zip(xd, xv):
        y = other.get(k)
        if y is None:
            continue
        if round(x - y, 6) == 0:
            t += 1
        elif x > y:
            a += 1
        else:
            b += 1
    return {"a": a, "b": b, "ties": t, "n": a + b + t}


def _end_of(key: Tuple[int, int]) -> int:
    y, m = key
    return date(y, 12, 31).toordinal() if m == 0 else date(y, m, calendar.monthrange(y, m)[1]).toordinal()


def _follows(k0: Tuple[int, int], k1: Tuple[int, int]) -> bool:
    if k0[1] == 0:
        return k1 == (k0[0] + 1, 0)
    return k1 == ((k0[0], k0[1] + 1) if k0[1] < 12 else (k0[0] + 1, 1))


def calendar_returns(days: Sequence[int], navs: Sequence[float], by: str) -> Dict[Tuple[int, int], float]:
    """Return over each calendar month (by='m') or year (by='y') wholly inside the series, in percent: the last NAV of the month ÷ the last NAV of
    the month before − 1. Both NAVs must sit within mf.MAX_STALE days of their month's end, so the partly covered first month and the unfinished
    current one are left out. Keys are (year, month) for months and (year, 0) for years."""
    ends: List[Tuple[Tuple[int, int], int, float]] = []
    for d, v in zip(days, navs):
        dd = _d(d)
        k = (dd.year, dd.month if by == "m" else 0)
        if ends and ends[-1][0] == k:
            ends[-1] = (k, d, v)
        else:
            ends.append((k, d, v))
    out: Dict[Tuple[int, int], float] = {}
    for (k0, d0, v0), (k1, d1, v1) in zip(ends, ends[1:]):
        if _follows(k0, k1) and _end_of(k0) - d0 <= mf.MAX_STALE and _end_of(k1) - d1 <= mf.MAX_STALE:
            out[k1] = (v1 / v0 - 1) * 100
    return out


def month_label(k: Tuple[int, int]) -> str:
    return date(k[0], k[1], 1).strftime("%b %Y")


def daily_returns(days: Sequence[int], navs: Sequence[float]) -> List[float]:
    """NAV changes from one weekday NAV to the next (weekend NAVs, which some debt funds publish, are left out; a holiday gap counts as one day)."""
    pts = [(d, v) for d, v in zip(days, navs) if _d(d).weekday() < 5]
    return [b[1] / a[1] - 1 for a, b in zip(pts, pts[1:])]


def drawdown(days: Sequence[int], navs: Sequence[float]) -> dict:
    """Largest fall from a NAV high to a later low inside the series (percent, 0 or negative), its two days, and the day the NAV first got back
    to the earlier high (None when it has not yet)."""
    if len(days) < 30:
        return {"value": None, "peak": None, "trough": None, "recovered": None, "why": "Too few NAVs to measure it."}
    peak_i, worst, wp, wt = 0, 0.0, 0, 0
    for i, v in enumerate(navs):
        if v > navs[peak_i]:
            peak_i = i
        dd = v / navs[peak_i] - 1
        if dd < worst:
            worst, wp, wt = dd, peak_i, i
    rec = next((days[k] for k in range(wt + 1, len(navs)) if navs[k] >= navs[wp]), None) if worst < 0 else None
    return {"value": rnd(worst * 100), "peak": _iso(days[wp]) if worst < 0 else None, "trough": _iso(days[wt]) if worst < 0 else None,
            "recovered": _iso(rec), "why": None}


def measure(days: Sequence[int], navs: Sequence[float], end: int, period: str) -> dict:
    """Everything worked out for one series (a fund or the category average) over a period ending on `end`. {'why': reason} when the series
    does not cover the period."""
    months, roll = PERIODS[period], ROLLING[period]
    win, why = window(days, navs, end, months)
    if win is None:
        return {"why": why}
    d, v = win
    ret = point_return(d, v, months > 12)
    rd, rv = rolling(d, v, roll, roll > 12)
    rets = daily_returns(d, v)
    need = 0.8 * 252 * months / 12
    vol = statistics.stdev(rets) * math.sqrt(252) * 100 if len(rets) >= max(need, 20) else None
    down = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets)) * math.sqrt(252) * 100 if vol is not None else None
    monthly = calendar_returns(d, v, "m")
    return {"why": None, "days": d, "navs": v, "ret": ret, "rd": rd, "rv": rv, "vol": vol, "down": down, "dd": drawdown(d, v),
            "monthly": monthly, "yearly": calendar_returns(d, v, "y"), "sharpe": (ret - RISK_FREE) / vol if vol else None}


# ====================================================================================== the category average (an equal-weighted index)

def weekday_grid(first: int, last: int) -> List[int]:
    return [o for o in range(first, last + 1) if _d(o).weekday() < 5]


class CategoryIndex:
    """Adds funds one at a time (only small running sums are kept, never every series at once) and gives the equal-weighted index: on each
    weekday it moves by the average NAV change, that day, of the funds that have a NAV on that day and the weekday before (a NAV is carried over
    holidays; a fund counts from its first NAV and stops after its last)."""

    def __init__(self, grid: List[int]):
        self.grid = grid
        self.sums = [0.0] * len(grid)
        self.counts = [0] * len(grid)
        self.real = [False] * len(grid)
        self.codes: List[int] = []
        self.starts: List[int] = []
        self.skipped: List[int] = []

    def add(self, code: int, days: Sequence[int], navs: Sequence[float]) -> bool:
        g, p, n = self.grid, 0, len(days)
        cur: Optional[float] = None
        moves: List[Tuple[int, float]] = []
        hits: List[int] = []
        first = None
        for k, gd in enumerate(g):
            if gd > days[-1]:
                break
            prev = cur
            while p < n and days[p] <= gd:
                if days[p] == gd:
                    hits.append(k)
                cur = navs[p]
                p += 1
            if cur is None:
                continue
            if first is None:
                first = gd
            if prev is not None:
                r = cur / prev - 1
                if abs(r) > JUMP:
                    self.skipped.append(code)
                    return False
                moves.append((k, r))
        if first is None or not moves:
            return False
        for k, r in moves:
            self.sums[k] += r
            self.counts[k] += 1
        for k in hits:
            self.real[k] = True
        self.codes.append(code)
        self.starts.append(first)
        return True

    def index(self) -> Tuple[List[int], List[float]]:
        """(days, values) starting at 100 on the first day any fund has a NAV; days on which no fund published a NAV are left out."""
        days: List[int] = []
        vals: List[float] = []
        level = 100.0
        for k, gd in enumerate(self.grid):
            if self.counts[k]:   # nothing moves before the first NAV day, so the index is 100 on it
                level *= 1 + self.sums[k] / self.counts[k]
            if self.real[k]:
                days.append(gd)
                vals.append(level)
        return days, vals


# ====================================================================================== NAV series

def _client(app) -> httpx.AsyncClient:
    c = getattr(app.state, "mf_client", None)
    if c is None:
        c = app.state.mf_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=True, headers={"User-Agent": mf.USER_AGENT})
    return c


def _agrees(days: Sequence[int], navs: Sequence[float], row, exact: bool = False) -> bool:
    """The series has AMFI's latest NAV on its date (or, unless `exact`, AMFI's previous NAV on its date: the mirror can lag AMFI by a day)."""
    pairs = [(row["nav_date"], row["nav"])] + ([] if exact else [(row.get("prev_date"), row.get("prev_nav"))])
    for d, v in pairs:
        if d is None or v is None or not days:
            continue
        i = bisect_right(days, d.toordinal()) - 1
        if i >= 0 and days[i] == d.toordinal() and abs(navs[i] - v) <= 1e-6 * max(1.0, v):
            return True
    return False


def parse_full(payload: dict, row) -> Optional[Tuple[List[int], List[float]]]:
    """The mirror's whole history for a scheme (mf.parse_mirror keeps five years only), cut at AMFI's latest NAV date and at CAT_SPAN days before
    it, or None when the answer is not for this scheme or does not agree with AMFI's own latest (or previous) NAV."""
    code = row["code"]
    try:
        if int(payload["meta"]["scheme_code"]) != code or payload.get("status", "SUCCESS") != "SUCCESS":
            return None
        pairs: Dict[int, float] = {}
        for x in payload["data"]:
            dd, mm, yy = x["date"].split("-")
            nav = mf.parse_nav(str(x["nav"]))
            if nav is not None:
                pairs[date(int(yy), int(mm), int(dd)).toordinal()] = nav
    except (KeyError, TypeError, ValueError):
        return None
    if not pairs or row["nav_date"] is None:
        return None
    last = row["nav_date"].toordinal()
    days = [d for d in sorted(pairs) if last - CAT_SPAN <= d <= last]
    navs = [pairs[d] for d in days]
    return (days, navs) if len(days) > 1 and _agrees(days, navs, row) else None


async def mirror_full(app, row) -> Optional[Tuple[List[int], List[float]]]:
    try:
        r = await _client(app).get(f"{mf.MIRROR_URL}/{row['code']}")
        if r.status_code != 200:
            return None
        return parse_full(r.json(), row)
    except (httpx.HTTPError, ValueError):
        return None


async def long_series(app, row) -> Optional[Tuple[List[int], List[float]]]:
    """Up to ten years of NAVs of one fund from the mirror, kept in Redis (packed) for LONG_TTL; a copy that no longer ends on AMFI's latest NAV
    date is fetched again."""
    redis = app.state.store.redis
    key = f"mf:cmp:long:{row['code']}"
    try:
        hit = await redis.get(key)
    except Exception:
        hit = None
    if hit is not None and len(hit) > 4:
        days, navs = mf.unpack_series(hit[4:], int.from_bytes(hit[:4], "little"))
        if _agrees(days, navs, row, exact=True):
            return days, navs
    got = await mirror_full(app, row)
    if got:
        try:
            await redis.set(key, got[0][0].to_bytes(4, "little") + mf.pack_series(*got), ex=LONG_TTL if _agrees(*got, row, exact=True) else 3600)
        except Exception:
            pass
    return got


MIRROR_NOTE = "NAV history: third-party mirror of AMFI data (api.mfapi.in)"


async def fund_series(app, row, period: str) -> Tuple[List[int], List[float], Optional[str], Optional[str]]:
    """(days, NAVs, source, note) for one fund: five years from mf.load_series, or for 10Y the mirror's longer history (falling back to the five years)."""
    if PERIODS[period] > 60:
        got = await long_series(app, row)
        if got:
            return got[0], got[1], "mirror", MIRROR_NOTE
    days, navs, _complete, source, note = await mf.load_series(app, row)
    return days, navs, (source if days else None), note


async def member_series(app, row) -> Optional[Tuple[List[int], List[float]]]:
    """A category member's history: the mirror's (up to ten years), else AMFI's stored five years, else None."""
    got = await mirror_full(app, row)
    if got:
        return got
    async with app.state.store.pool.acquire() as conn:
        h = await conn.fetchrow("SELECT blob, d0 FROM mf_history WHERE code = $1", row["code"])
    return mf.unpack_series(bytes(h["blob"]), h["d0"].toordinal()) if h else None


# ====================================================================================== category averages: built once per category, plan and NAV date

GROWTH = "s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL"
MEMBERS_SQL = f"""
WITH q AS (SELECT max(aum_end) AS e FROM mf_facts WHERE aum_lakh IS NOT NULL),
     fam AS (SELECT s.family, sum(f.aum_lakh) AS aum FROM mf_facts f JOIN mf_schemes s ON s.code = f.code, q
             WHERE f.aum_end = q.e AND s.category = ANY($1::text[]) GROUP BY s.family),
     pick AS (SELECT DISTINCT ON (s.family) s.family, s.code, s.name, s.nav, s.nav_date, s.prev_nav, s.prev_date FROM mf_schemes s
              WHERE {GROWTH} AND s.category = ANY($1::text[]) AND s.plan = $2 ORDER BY s.family, s.has_hist DESC, s.code)
SELECT pick.*, fam.aum FROM pick LEFT JOIN fam USING (family) ORDER BY fam.aum DESC NULLS LAST, pick.code
"""  # nosec B608 - GROWTH is a fixed filter; category and plan are bound parameters

_tasks: Dict[Tuple[str, str, date], asyncio.Task] = {}


def _cat_key(category: str, plan: str) -> str:
    return hashlib.blake2b(f"{category}|{plan}".encode(), digest_size=10).hexdigest()


async def build_category(app, names: List[str], plan: str, newest: date) -> dict:
    """Work out and store the average of a category (all its wordings, `names`) for `newest` (see the module notes). Returns the stored row."""
    category = cat_key(names[0])
    async with app.state.store.pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(MEMBERS_SQL, names, plan)]
    eligible, picked = len(rows), rows[:CAT_MAX]
    grid = weekday_grid(newest.toordinal() - CAT_SPAN, newest.toordinal())
    idx = CategoryIndex(grid)
    sem = asyncio.Semaphore(CAT_FETCHES)

    async def one(r):
        async with sem:
            s = await member_series(app, r)
        if s and len(s[0]) > 1:
            idx.add(r["code"], *s)
    await asyncio.gather(*(one(r) for r in picked))
    members = len(idx.codes)
    blob, d0, n = None, None, 0
    if members >= CAT_MIN:
        days, vals = idx.index()
        if len(days) > 1:
            blob, d0, n = mf.pack_series(days, vals), _d(days[0]), len(days)
    basis = (f"the {len(picked)} largest of the category's {eligible} funds by fund size (AUM)" if eligible > CAT_MAX and any(r["aum"] for r in picked)
             else f"{len(picked)} of the category's {eligible} funds (the ones with the lowest AMFI scheme codes)" if eligible > CAT_MAX
             else f"all {eligible} funds in the category")
    note = (f"Equal-weighted average of the {plan} plan, Growth option, of {members} funds: {basis}, those whose NAV history could be loaded."
            if blob else f"Fewer than {CAT_MIN} funds in this category ({plan} plan) have NAV history that could be loaded, so no average is shown.")
    if idx.skipped:
        note += f" {len(idx.skipped)} fund{'s were' if len(idx.skipped) > 1 else ' was'} left out for a one-day NAV jump of over {int(JUMP * 100)}% (a data error)."
    order = sorted(range(members), key=lambda i: idx.starts[i])
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("""INSERT INTO mf_cat_avg (category, plan, nav_date, d0, n, blob, eligible, members, codes, starts, note, built_at)
                              VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, now())
                              ON CONFLICT (category, plan) DO UPDATE SET nav_date = EXCLUDED.nav_date, d0 = EXCLUDED.d0, n = EXCLUDED.n, blob = EXCLUDED.blob,
                              eligible = EXCLUDED.eligible, members = EXCLUDED.members, codes = EXCLUDED.codes, starts = EXCLUDED.starts, note = EXCLUDED.note,
                              built_at = now()""",
                           category, plan, newest, d0, n, blob, eligible, members, [idx.codes[i] for i in order], [_d(idx.starts[i]) for i in order], note)
        return dict(await conn.fetchrow("SELECT * FROM mf_cat_avg WHERE category = $1 AND plan = $2", category, plan))


async def _build_once(app, names: List[str], plan: str, newest: date) -> dict:
    """build_category, but only one process at a time per category and plan (a Redis lock); a process that finds the lock taken waits for the row."""
    redis = app.state.store.redis
    category = cat_key(names[0])
    lock = f"mf:cmp:catlock:{_cat_key(category, plan)}"
    try:
        mine = bool(await redis.set(lock, "1", nx=True, ex=CAT_LOCK))
    except Exception:
        mine = True
    if not mine:
        for _ in range(CAT_LOCK):
            await asyncio.sleep(1)
            async with app.state.store.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM mf_cat_avg WHERE category = $1 AND plan = $2 AND nav_date >= $3", category, plan, newest)
            if row:
                return dict(row)
        raise RuntimeError("category average not built by the other process")
    try:
        return await build_category(app, names, plan, newest)
    finally:
        try:
            await redis.delete(lock)
        except Exception:
            pass


def _from_row(row: dict) -> dict:
    if not row["blob"]:
        return {"why": row["note"], "note": row["note"], "eligible": row["eligible"], "members": row["members"]}
    days, vals = mf.unpack_series(bytes(row["blob"]), row["d0"].toordinal())
    return {"days": days, "vals": vals, "why": None, "note": row["note"], "eligible": row["eligible"], "members": row["members"],
            "starts": [s.toordinal() for s in row["starts"]], "navDate": row["nav_date"]}


async def category_average(app, names: List[str], plan: str, wait: Optional[float] = None) -> dict:
    """The category average for the category's newest NAV date: from mf_cat_avg when it is current, else worked out now (one background task per
    category, plan and date). Answers {'pending': True, 'why': ...} when it is not ready within `wait` seconds; the next request picks it up.
    `names` are all wordings of the category (see `variants`); the average is stored under cat_key."""
    category = cat_key(names[0])
    async with app.state.store.pool.acquire() as conn:
        newest = await conn.fetchval("SELECT max(s.nav_date) FROM mf_schemes s WHERE " + GROWTH + " AND s.category = ANY($1::text[]) AND s.plan = $2", names, plan)  # nosec B608 - fixed filter text; values are bound
        row = await conn.fetchrow("SELECT * FROM mf_cat_avg WHERE category = $1 AND plan = $2", category, plan)
    if newest is None:
        return {"why": f"No fund in this category has a current NAV on the {plan} plan."}
    if row and row["nav_date"] >= newest:
        return _from_row(dict(row))
    key = (category, plan, newest)
    task = _tasks.get(key)
    if task is None:
        task = _tasks[key] = spawn(_build_once(app, names, plan, newest))
        task.add_done_callback(lambda _t, k=key: _tasks.pop(k, None))
    try:
        return _from_row(await asyncio.wait_for(asyncio.shield(task), CAT_WAIT if wait is None else wait))
    except asyncio.TimeoutError:
        return {"pending": True, "why": "The category average is being worked out (it needs the NAV history of every fund in the category). It appears here in a few seconds."}
    except Exception:
        log.warning("category average failed for %s / %s", category, plan, exc_info=True)
        return {"why": "The category average could not be worked out right now. Please try again in a moment."}


# ====================================================================================== facts

_TER = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*%")


async def fund_facts(pool, code: int, plan: str) -> dict:
    """The facts the Costs card shows, each {value, asOf, source, ...} or {unavailable: reason}, plus the TER as a number for the plain-English line."""
    try:
        from . import disclosure
        got = await disclosure.get_facts(pool, code)
    except Exception:
        log.warning("facts unavailable for %s", code, exc_info=True)
        got = None
    got = got if isinstance(got, dict) else {}
    none = {"unavailable": mf.NO_FACTS if not got else "Not published in the sources loaded for this scheme."}
    pick = lambda v: v if isinstance(v, dict) and ("value" in v or "unavailable" in v) else none   # noqa: E731
    ter = pick(got.get("terRegular" if plan == "Regular" else "terDirect"))
    m = _TER.match(str(ter.get("value") or "")) if "value" in ter else None
    return {"ter": ter, "terPct": float(m.group(1)) if m else None, **{k: pick(got.get(k)) for k in FACT_KEYS}}


# ====================================================================================== the payload

def _series(d: Sequence[int], v: Sequence[float], cap: int, scale: Optional[float] = None) -> dict:
    td, tv = mf.thin(list(d), list(v), cap)
    return {"t": [_iso(x) for x in td], "v": [round(x * scale, 2) if scale else round(x, 2) for x in tv]}


def _ret_block(m: dict) -> dict:
    if m["why"]:
        return {"value": None, "from": None, "to": None, "growth": None, "why": m["why"]}
    d, v = m["days"], m["navs"]
    return {"value": rnd(m["ret"]), "from": _iso(d[0]), "to": _iso(d[-1]), "growth": rnd(10000 * v[-1] / v[0], 0), "why": None}


def _risk_block(m: dict) -> dict:
    if m["why"]:
        nul = {"value": None, "why": m["why"]}
        return {"volatility": nul, "downside": nul, "maxDrawdown": {**nul, "peak": None, "trough": None, "recovered": None},
                "worstMonth": {**nul, "month": None}, "bestMonth": {**nul, "month": None}, "sharpe": nul}
    short = "Too few NAVs in the period to measure it."
    mo = m["monthly"]
    worst = min(mo, key=mo.__getitem__) if mo else None
    best = max(mo, key=mo.__getitem__) if mo else None
    no_month = "No whole calendar month in the period."
    return {"volatility": {"value": rnd(m["vol"]), "why": None if m["vol"] is not None else short},
            "downside": {"value": rnd(m["down"]), "why": None if m["down"] is not None else short},
            "maxDrawdown": m["dd"],
            "worstMonth": {"value": rnd(mo[worst]), "month": month_label(worst), "why": None} if worst else {"value": None, "month": None, "why": no_month},
            "bestMonth": {"value": rnd(mo[best]), "month": month_label(best), "why": None} if best else {"value": None, "month": None, "why": no_month},
            "sharpe": {"value": rnd(m["sharpe"]), "why": None} if m["sharpe"] is not None else {"value": None, "why": short}}


def _fund_meta(row, source: Optional[str], note: Optional[str], days: Sequence[int]) -> dict:
    return {"code": row["code"], "name": row["name"], "amc": row["amc"], "category": row["category"], "plan": row["plan"], "option": row["option_label"],
            "nav": row["nav"], "navDate": mf.iso(row["nav_date"]),
            "history": {"source": source, "from": _iso(days[0]) if days else None, "to": _iso(days[-1]) if days else None,
                        "note": note if source == "mirror" else None}}


def assemble(period: str, ra, rb, sa: Tuple, sb: Tuple, cat: dict, facts_a: dict, facts_b: dict, plan: str) -> dict:
    """The whole answer from the two funds' series (days, navs, source, note), the category average and the facts. Pure: tested without a database."""
    months, roll = PERIODS[period], ROLLING[period]
    (da, va, srca, notea), (db, vb, srcb, noteb) = sa, sb
    ends = [d[-1] for d in (da, db) if d]
    end = min(ends) if ends else None
    none = {"why": "No NAV history is loaded for this fund."}
    ma = measure(da, va, end, period) if end and da else none
    mb = measure(db, vb, end, period) if end and db else none
    if cat.get("days") and end:
        mc = measure(cat["days"], cat["vals"], end, period)
    else:
        mc = {"why": cat.get("why") or "No category average."}
    M = {"a": ma, "b": mb, "cat": mc}
    ok = {k: not m["why"] for k, m in M.items()}
    start = mf.shift_months(_d(end), months).toordinal() if end else None

    # returns
    rolling_out = {k: roll_stats(m["rd"], m["rv"]) if ok[k] else {**roll_stats([], []), "why": m["why"]} for k, m in M.items()}
    returns = {
        "kind": "cagr" if months > 12 else "absolute",
        "funds": {k: _ret_block(m) for k, m in M.items()},
        "rolling": {"months": roll, "label": span_label(roll), "kind": "cagr" if roll > 12 else "absolute", "funds": rolling_out,
                    "chart": {k: _series(m["rd"], m["rv"], ROLL_CAP) for k, m in M.items() if ok[k] and m["rd"]}},
        "growth": {k: _series(m["days"], m["navs"], CHART_CAP, 10000 / m["navs"][0]) for k, m in M.items() if ok[k]},
    }

    # risk
    risk = {"funds": {k: _risk_block(m) for k, m in M.items()}, "riskFree": RISK_FREE, "note": RISK_FREE_NOTE}

    # consistency
    both = ok["a"] and ok["b"]
    why_ab = ma["why"] or mb["why"]
    windows = tally(ma["rd"], ma["rv"], mb["rd"], mb["rv"]) if both else {"a": 0, "b": 0, "ties": 0, "n": 0}
    windows["why"] = why_ab if not both else (None if windows["n"] else "The period is too short for a whole rolling window.")
    mon = tally(list(ma["monthly"]), list(ma["monthly"].values()), list(mb["monthly"]), list(mb["monthly"].values())) if both else {"a": 0, "b": 0, "ties": 0, "n": 0}
    mon["why"] = why_ab if not both else (None if mon["n"] else "No whole calendar month in the period.")
    yrs = sorted(set(ma.get("yearly", {})) | set(mb.get("yearly", {})))
    rows = [{"year": y[0], "a": rnd(ma["yearly"].get(y)) if ok["a"] else None, "b": rnd(mb["yearly"].get(y)) if ok["b"] else None,
             "cat": rnd(mc["yearly"].get(y)) if ok["cat"] else None} for y in yrs]
    yt = tally(list(ma["yearly"]), list(ma["yearly"].values()), list(mb["yearly"]), list(mb["yearly"].values())) if both else {"a": 0, "b": 0, "ties": 0, "n": 0}
    years = {**yt, "rows": rows, "why": why_ab if not both else (None if yt["n"] else "No whole calendar year in the period: see the months instead.")}
    vs = {}
    for k in ("a", "b"):
        if not ok[k] or not ok["cat"]:
            vs[k] = {"beat": None, "n": 0, "pct": None, "why": M[k]["why"] or mc["why"]}
        else:
            t = tally(M[k]["rd"], M[k]["rv"], mc["rd"], mc["rv"])
            vs[k] = {"beat": t["a"], "n": t["n"], "pct": rnd(100.0 * t["a"] / t["n"], 1) if t["n"] else None,
                     "why": None if t["n"] else "The period is too short for a whole rolling window."}
    consistency = {"window": {"months": roll, "label": span_label(roll)}, "rolling": windows, "months": mon, "years": years, "vsCategory": vs}

    # costs and the excess return over the category average
    alpha = {}
    for k in ("a", "b"):
        if ok[k] and ok["cat"]:
            alpha[k] = {"value": rnd(M[k]["ret"] - mc["ret"]), "why": None}
        else:
            alpha[k] = {"value": None, "why": M[k]["why"] or mc["why"]}
    costs = {"funds": {"a": facts_a, "b": facts_b}, "alpha": alpha, "alphaBasis": "category average", "alphaNote": ALPHA_NOTE}

    members_at_start = sum(1 for s in cat.get("starts", []) if start is not None and s <= start) if cat.get("days") else None
    category = {"name": ra["category"], "short": short_category(ra["category"]), "plan": plan, "members": cat.get("members"), "eligible": cat.get("eligible"),
                "membersAtStart": members_at_start, "note": cat.get("note"), "why": mc["why"], "pending": bool(cat.get("pending")),
                "survivorship": "Funds that closed or merged are no longer in AMFI's list, so they are missing from the average; this can flatter the category a little."}
    plans_differ = ra["plan"] != rb["plan"]
    return {"period": period, "months": months, "from": _iso(start), "to": _iso(end), "pending": bool(cat.get("pending")),
            "funds": {"a": _fund_meta(ra, srca, notea, da), "b": _fund_meta(rb, srcb, noteb, db)},
            "why": {"a": ma["why"], "b": mb["why"]},
            "planNote": (f"Fund A is on the {ra['plan']} plan and Fund B on the {rb['plan']} plan. Plans of one fund differ only by cost, so compare Direct with "
                         f"Direct and Regular with Regular. The category average here is of the {plan} plan.") if plans_differ else None,
            "category": category, "returns": returns, "risk": risk, "consistency": consistency, "costs": costs}


async def compare_payload(app, ra, rb, period: str) -> dict:
    plan = ra["plan"] if ra["plan"] in PLANS else "Direct"
    pool = app.state.store.pool
    sa, sb = await asyncio.gather(fund_series(app, ra, period), fund_series(app, rb, period))
    async with pool.acquire() as conn:
        names = await variants(conn, ra["category"])
    cat, fa, fb = await asyncio.gather(category_average(app, names, plan), fund_facts(pool, ra["code"], ra["plan"]), fund_facts(pool, rb["code"], rb["plan"]))
    out = assemble(period, ra, rb, sa, sb, cat, fa, fb, plan)
    async with pool.acquire() as conn:
        out.update(await mf._facts(conn))
    return out


# ====================================================================================== API

async def _cached(request: Request, kind: str, key: str, build, ttl: int) -> Response:
    """Like mf.cached_json (Redis under the data version, ETag / 304), except that an answer still waiting for its category average is never kept."""
    store = request.app.state.store
    rk = f"mf:{await mf._version(store.redis)}:cmp:{kind}:{hashlib.blake2b(key.encode(), digest_size=12).hexdigest()}"
    try:
        hit = await store.redis.hmget(rk, ["body", "etag"])
    except Exception:
        hit = [None, None]
    if hit[0] is None:
        payload = await build()
        body = dumps(payload)
        etag = etag_for(body)
        if isinstance(payload, dict) and payload.get("pending"):
            return Response(content=body, media_type="application/json", headers={"Cache-Control": NO_CACHE})
        try:
            await store.redis.hset(rk, mapping={"body": body, "etag": etag})
            await store.redis.expire(rk, ttl)
        except Exception:
            pass
    else:
        body, etag = hit[0], hit[1].decode() if isinstance(hit[1], bytes) else hit[1]
    headers = {"ETag": etag, "Cache-Control": mf.CACHE_HEADER}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


FUND_FILTER = "s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.scheme_type = 'Open Ended'"


@router.get("/categories")
async def categories(request: Request) -> Response:
    """Open-ended categories with how many funds each has on the Direct and the Regular plan (one Growth option per fund, active ones only)."""
    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            rows = await conn.fetch(f"""SELECT s.category, count(DISTINCT s.family) FILTER (WHERE s.plan = 'Direct') AS direct,
                                               count(DISTINCT s.family) FILTER (WHERE s.plan = 'Regular') AS regular
                                        FROM mf_schemes s WHERE {FUND_FILTER} GROUP BY s.category ORDER BY s.category""")  # nosec B608 - fixed filter text, no input
            facts = await mf._facts(conn)
        merged: Dict[str, List] = {}
        for r in rows:   # both wordings of one category become one entry, named after the wording with more funds
            merged.setdefault(cat_key(r["category"]), []).append(r)
        cats = []
        for group in merged.values():
            group.sort(key=lambda r: (-(r["direct"] + r["regular"]), r["category"]))
            name = group[0]["category"]
            d, g = sum(r["direct"] for r in group), sum(r["regular"] for r in group)
            if max(d, g) >= 2:
                cats.append({"name": name, "short": short_category(name), "group": mf.category_group(name), "direct": d, "regular": g, "variants": [r["category"] for r in group]})
        cats.sort(key=lambda c: (c["group"].lower().replace("schemes", "scheme"), c["short"].lower()))
        return {"categories": cats, **facts}
    return await _cached(request, "cats", "all", build, COMPARE_TTL)


@router.get("/funds")
async def funds(request: Request, category: str = Query(..., min_length=1, max_length=160), plan: str = Query("Direct", pattern="^(Direct|Regular)$")) -> Response:
    """The funds of one category (both of its wordings) on one plan, one Growth option per fund, A to Z, with the launch date AMFI's scheme master
    gives (when loaded)."""
    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            rows = await conn.fetch(f"""SELECT DISTINCT ON (s.family) s.code, s.name, s.amc, s.r1y, s.r5y, f.launch_date
                                        FROM mf_schemes s LEFT JOIN mf_facts f ON f.code = s.code
                                        WHERE {FUND_FILTER} AND s.category = ANY($1::text[]) AND s.plan = $2
                                        ORDER BY s.family, s.has_hist DESC, s.code""", await variants(conn, category), plan)  # nosec B608 - fixed filter text; category and plan are bound
            facts = await mf._facts(conn)
        items = sorted(({"code": r["code"], "name": r["name"], "amc": r["amc"], "launch": mf.iso(r["launch_date"]), "r1y": mf.rnd(r["r1y"]), "r5y": mf.rnd(r["r5y"])}
                        for r in rows), key=lambda x: (x["name"].lower(), x["code"]))
        return {"category": category, "plan": plan, "funds": items, **facts}
    return await _cached(request, "funds", f"{category}|{plan}", build, COMPARE_TTL)


@router.get("")
async def head_to_head(request: Request, a: int = Query(..., ge=1, lt=10**7), b: int = Query(..., ge=1, lt=10**7),
                       period: str = Query("3Y", pattern="^(1Y|3Y|5Y|10Y)$")) -> Response:
    """Fund A against Fund B (same category) over a period: returns, risk, consistency and costs, each also against the category average."""
    if a == b:
        raise fail(400, "bad_request", "Choose two different funds.")

    async def build():
        ra, rb = await mf._scheme(request, a), await mf._scheme(request, b)
        for r, who in ((ra, "Fund A"), (rb, "Fund B")):
            if r["option_class"] != "Growth":
                raise fail(400, "bad_request", f"{who} is not a Growth option. Returns are compared for Growth options only: payouts lower the NAV of IDCW options.")
            if not r["active"]:
                raise fail(400, "bad_request", f"{who} has stopped publishing NAVs.")
        if cat_key(ra["category"]) != cat_key(rb["category"]):
            raise fail(400, "bad_request", "Fund Compare puts two funds of the same category side by side, and these two are in different categories. "
                                           "The 2 to 4 scheme compare can show any schemes together.")
        return await compare_payload(request.app, dict(ra), dict(rb), period)
    return await _cached(request, "h2h", f"{a}|{b}|{period}", build, COMPARE_TTL)
