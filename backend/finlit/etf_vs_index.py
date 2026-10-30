"""ETF vs index fund: ETFs and direct-plan index funds that follow the SAME index, side by side (sub page of the ETF section, /etfs/compare-index-funds).

Where each figure comes from (nothing else is shown; every blank carries its reason):
  * which products follow which index   the benchmark each fund house states (finlit.portfolios, from fund-house and AMFI disclosures) when we have
                                        it, else the index named in the scheme's registered name. A product whose benchmark and name point at two
                                        different indices is left out. The text is normalised ("Nifty 50 TRI" and "NIFTY 50 Index (TRI)" are both Nifty 50),
                                        and a variant ("Nifty 50 Equal Weight", "Nifty 500 Value 50", ...) never counts as the plain index.
                                        Each product's own benchmark is shown with its return type (TRI, price, or "not stated") and never mixed silently.
  * ETF history     the exchange close from etf_history (NSE, via our price providers), or the ETF's AMFI NAV when a stored NAV history covers the
                    same period (almost never: AMFI NAV history is stored for Growth schemes only). The basis used is named per product.
  * fund history   AMFI NAV of the Growth option, Direct plan unless the Regular plan is asked for (finlit.mf_compare.fund_series: AMFI's own stored
                    history, the checked mirror for up to ten years).
  * index levels   daily closing levels of the PRICE index from the index data provider (finlit.indices, five years). The total-return (TRI) index
                    is not stored. Funds and ETFs reinvest dividends, a price index does not, so a return gap against it is mostly the index's dividend
                    yield. That is why the tracking difference against the index is shown with that label and the "tracking" line of the summary
                    uses tracking error (which dividends barely move) only.
  * costs           expense ratio (TER) from AMFI's TER file or the fund house's own TER page, exit load and minimum from the disclosure facts. Brokerage,
                    bid-ask spread and impact cost of buying an ETF are NOT known to us and are not estimated.

All measures run on the dates every chosen product has a price or NAV for ("common dates"), so each product is measured over the same days.
Pure maths first (no I/O, tested), then the two endpoints (`/options`, `/compare`). Information only, never advice."""

from __future__ import annotations

import asyncio
import calendar
import json
import logging
import math
import re
import statistics
import time
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from fastapi import APIRouter, Query, Request, Response

from . import etf, mf, mf_compare
from .auth.routes import fail

log = logging.getLogger("finlit.etf_vs_index")
router = APIRouter(prefix="/api/etf-vs-index")

DISCLAIMER = "Information only, not investment advice. Past returns do not guarantee future returns."
GAP_DAYS = 10            # a look-back price must exist within this many days on or before the target date
PER_YEAR = 252           # trading days a year used to annualise volatility and tracking error (a convention, not a measurement)
MIN_RETURNS = 60         # daily returns needed for a volatility or downside figure
MIN_TE = 240             # daily return differences needed for a tracking error: about one year of overlapping days
MIN_COMMON = 30          # common dates needed for anything at all
MIN_ROLL = 60            # rolling windows needed for rolling statistics
MAX_PRODUCTS = 4
CHART_CAP = 700
OPT_TTL = 900
COMPARE_TTL = 1800
# Tolerances below which two products are called level (stated on the page too)
TOL_RETURN = 0.25        # percentage points a year
TOL_COST = 0.02          # percentage points of expense ratio
TOL_TRACK = 0.10         # percentage points of tracking error
TOL_FALL = 0.50          # percentage points of maximum fall
TOL_VOL = 0.30           # percentage points of volatility
TOLERANCES = {"return": TOL_RETURN, "cost": TOL_COST, "tracking": TOL_TRACK, "fall": TOL_FALL, "volatility": TOL_VOL}
DRAG_BASE = 1_000_000    # rupees: "per year on Rs 10 lakh"
PERIODS: Tuple[Tuple[str, int, str], ...] = (("1M", 1, "1 month"), ("3M", 3, "3 months"), ("6M", 6, "6 months"), ("1Y", 12, "1 year"), ("3Y", 36, "3 years"), ("5Y", 60, "5 years"))
TRACK_PERIODS: Tuple[Tuple[str, int, str], ...] = (("1Y", 12, "1 year"), ("3Y", 36, "3 years"), ("5Y", 60, "5 years"))


# ====================================================================================== which index does a product follow

# key, label, price-index code at the index data provider (None: not carried), pattern on the normalised text
INDICES: Tuple[Tuple[str, str, Optional[str], str], ...] = (
    ("nifty50", "Nifty 50", "NIF50", r"NIFTY ?50"),
    ("niftynext50", "Nifty Next 50", "NIFNEX50", r"NIFTY NEXT ?50"),
    ("sensex", "BSE Sensex", "SNSXSENSEX", r"SENSEX"),
    ("niftybank", "Nifty Bank", "NIFBAN", r"NIFTY BANK|BANK NIFTY"),
    ("nifty100", "Nifty 100", "NIF100", r"NIFTY ?100"),
    ("nifty200", "Nifty 200", "NIF200", r"NIFTY ?200"),
    ("nifty500", "Nifty 500", "NIF500", r"NIFTY ?500"),
    ("midcap150", "Nifty Midcap 150", "NIFMID150", r"NIFTY MID ?CAP ?150"),
    ("midcap100", "Nifty Midcap 100", "NIFMID100", r"NIFTY MID ?CAP ?100"),
    ("midcap50", "Nifty Midcap 50", "NIFMID50", r"NIFTY MID ?CAP ?50"),
    ("smallcap250", "Nifty Smallcap 250", "NIFSMA250", r"NIFTY SMALL ?CAP ?250"),
    ("smallcap100", "Nifty Smallcap 100", "NIFSMA100", r"NIFTY SMALL ?CAP ?100"),
    ("smallcap50", "Nifty Smallcap 50", "NIFSMA50", r"NIFTY SMALL ?CAP ?50"),
    ("largemid250", "Nifty LargeMidcap 250", "NIFLAR250", r"NIFTY LARGE ?MID ?CAP ?250"),
    ("midsmall400", "Nifty MidSmallcap 400", "NIFMID400", r"NIFTY MID ?SMALL ?CAP ?400"),
    ("niftyit", "Nifty IT", "NIFIT", r"NIFTY IT"),
    ("finserv", "Nifty Financial Services", "NIFFINSER", r"NIFTY FIN(?:ANCIAL)? SERVICES?"),
    ("pvtbank", "Nifty Private Bank", "NIFPRIBAN", r"NIFTY P(?:RI)?VT? BANK|NIFTY PRIVATE BANK"),
    ("totalmarket", "Nifty Total Market", "NIFTOTMAR", r"NIFTY TOTAL MARKET"),
)
INDEX_BY: Dict[str, Tuple[str, str, Optional[str], str]] = {k[0]: k for k in INDICES}
_PATTERNS = [(k, re.compile(r"(?<![A-Z0-9])(?:" + p + r")(?![A-Z0-9])")) for k, _l, _c, p in INDICES]
# A bare "Nifty" scheme name (SBI Nifty Index Fund, Nifty BeES) means the Nifty 50; only used when nothing more specific is found.
_BARE_NIFTY = re.compile(r"(?<![A-Z0-9])NIFTY(?: INDEX| ETF| BEES)(?![A-Z0-9])|(?<![A-Z0-9])NIFTYBEES(?![A-Z0-9])")
_NOISE = {"INDEX", "INDICES", "TRI", "TR", "TOTAL", "RETURN", "RETURNS", "PRICE", "PR", "ETF", "ETFS", "FUND", "FUNDS", "PLAN", "DIRECT", "REGULAR", "GROWTH", "OPTION", "FOF",
          "IDCW", "THE", "OF", "SCHEME", "MUTUAL", "EXCHANGE", "TRADED", "UNITS", "BEES", "FOR", "AND"}
# a word right after the index name that makes it a different (strategy or variant) index
_VARIANT = {"EQUAL", "WEIGHT", "VALUE", "MOMENTUM", "QUALITY", "ALPHA", "LOW", "VOL", "VOLATILITY", "DIVIDEND", "ARBITRAGE", "USD", "SHARIAH", "STEP", "FUTURES", "ENHANCED",
            "TOP", "MULTIFACTOR", "FACTOR", "EX", "SECTOR", "LEADERS", "NEXT", "ESG", "MULTICAP", "EQ", "TILT", "SELECT", "CAPPED", "LEVERAGED", "INVERSE", "TACTICAL"}


def norm(text: Optional[str]) -> str:
    """Upper case, every run of other characters one space: 'S&P BSE Sensex (TRI)' -> 'S P BSE SENSEX TRI'."""
    return re.sub(r"[^A-Z0-9]+", " ", str(text or "").upper()).strip()


def return_type(text: Optional[str]) -> Optional[str]:
    """'TRI' when the benchmark text says total return, 'price' when it says price return, else None (the fund house does not say)."""
    n = norm(text)
    if re.search(r"(?<![A-Z0-9])TRI(?![A-Z0-9])|TOTAL RETURN", n):
        return "TRI"
    if re.search(r"PRICE RETURN|(?<![A-Z0-9])PRI(?![A-Z0-9])", n):
        return "price"
    return None


def _scan(text: Optional[str]) -> Tuple[set, bool]:
    """(index keys the text names, whether it names a variant of a known index such as 'Nifty 50 Equal Weight')."""
    n = norm(text)
    found: set = set()
    variant = False
    if not n:
        return found, variant
    for key, rx in _PATTERNS:
        for m in rx.finditer(n):
            rest = [w for w in n[m.end():].split() if w not in _NOISE]
            before = [w for w in n[:m.start()].split() if w not in _NOISE]
            if (rest and (rest[0] in _VARIANT or rest[0].isdigit())) or (before and before[-1] in _VARIANT):   # the variant word can come first: "Equal Weight Nifty 50"
                variant = True
                continue
            found.add(key)
    if not found and not variant and _BARE_NIFTY.search(n):
        found.add("nifty50")
    return found, variant


def detect(text: Optional[str]) -> Optional[str]:
    """The index key a text names, or None when it names none, a variant of one, or two different ones."""
    found, _variant = _scan(text)
    return next(iter(found)) if len(found) == 1 else None


def classify(benchmark: Optional[str], names: Sequence[Optional[str]]) -> dict:
    """{key, basis, returnType, conflict}: the benchmark the fund house states decides; the name decides when none is stored; if they disagree, or
    either one names a variant index, the product is not classified (conflict True)."""
    bfound, bvar = _scan(benchmark)
    bkey = next(iter(bfound)) if len(bfound) == 1 else None
    scans = [_scan(n) for n in names if n]
    nkey = next((next(iter(f)) for f, _v in scans if len(f) == 1), None)
    nvar = any(v for _f, v in scans)
    rtype = return_type(benchmark) if benchmark else None
    if (bkey and nkey and bkey != nkey) or (bkey and nvar) or (nkey and bvar):
        return {"key": None, "basis": None, "returnType": rtype, "conflict": True}
    if bkey:
        return {"key": bkey, "basis": "benchmark", "returnType": rtype, "conflict": False}
    if nkey:
        return {"key": nkey, "basis": "name", "returnType": rtype, "conflict": False}
    return {"key": None, "basis": None, "returnType": rtype, "conflict": False}


# ====================================================================================== the maths (pure, no I/O)
# `days` are date ordinals in ascending order, `vals` prices or NAVs of the same length.

def fmt_day(o: int) -> str:
    d = date.fromordinal(o)
    return f"{d.day} {d.strftime('%b %Y')}"


def iso(o: Optional[int]) -> Optional[str]:
    return None if o is None else date.fromordinal(o).isoformat()


def back(o: int, months: int) -> int:
    return etf.month_back(date.fromordinal(o), months).toordinal()


def rnd(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None or not math.isfinite(v) else round(v, n)


def at_or_before(days: Sequence[int], target: int, gap: int = GAP_DAYS) -> Optional[int]:
    """Index of the last day on or before `target`, provided it is no more than `gap` days earlier."""
    i = bisect_right(days, target) - 1
    return i if i >= 0 and target - days[i] <= gap else None


def align(series: Dict[str, Tuple[Sequence[int], Sequence[float]]]) -> Tuple[List[int], Dict[str, List[float]]]:
    """Keep only the days EVERY series has a value for (a NAV on a day the exchange was shut, or a missing close, drops out for all)."""
    if not series:
        return [], {}
    common = set.intersection(*[set(d) for d, _ in series.values()])
    days = sorted(common)
    out = {}
    for k, (d, v) in series.items():
        m = dict(zip(d, v))
        out[k] = [m[x] for x in days]
    return days, out


def subset(days: Sequence[int], vals: Sequence[float], keep: Sequence[int]) -> List[float]:
    m = dict(zip(days, vals))
    return [m[x] for x in keep]


def daily_returns(vals: Sequence[float]) -> List[float]:
    return [vals[i] / vals[i - 1] - 1 for i in range(1, len(vals)) if vals[i - 1] > 0]


def period_return(days: Sequence[int], vals: Sequence[float], months: Optional[int], label: str = "") -> dict:
    """Point-to-point return from the last day on/before the look-back date to the last day, and the yearly rate (CAGR) when the span exceeds a year.
    months None: since the first day. {value, cagr, from, to, why}: value and cagr in percent, or None with the reason."""
    if len(days) < 2:
        return {"value": None, "cagr": None, "from": None, "to": None, "why": "Not enough common dates."}
    end = len(days) - 1
    if months is None:
        i = 0
    else:
        target = back(days[end], months)
        i = at_or_before(days, target)
        if i is None:
            return {"value": None, "cagr": None, "from": None, "to": iso(days[end]),
                    "why": f"Common history starts on {fmt_day(days[0])}, after the {label or str(months) + ' months'} start date ({fmt_day(target)})."}
    if vals[i] <= 0:
        return {"value": None, "cagr": None, "from": None, "to": None, "why": "A price of zero or less in the history."}
    r = vals[end] / vals[i] - 1
    span = (days[end] - days[i]) / 365
    cagr = (1 + r) ** (1 / span) - 1 if span >= 1 and 1 + r > 0 else None
    return {"value": rnd(r * 100), "cagr": rnd(cagr * 100) if cagr is not None else None, "from": iso(days[i]), "to": iso(days[end]), "why": None, "_raw": r, "_span": span}


def rolling_returns(days: Sequence[int], vals: Sequence[float], months: int = 12) -> Tuple[List[int], List[float]]:
    """For every day, the return over the `months` before it (percent), from the last day on/before the look-back date. Days with no such start are skipped."""
    ed, rv = [], []
    for k, d in enumerate(days):
        t = back(d, months)
        if t < days[0]:
            continue
        i = at_or_before(days, t)
        if i is None or i >= k:
            continue
        ed.append(d)
        rv.append((vals[k] / vals[i] - 1) * 100)
    return ed, rv


def roll_stats(vals: Sequence[float]) -> dict:
    if len(vals) < MIN_ROLL:
        return {"count": len(vals), "why": f"Only {len(vals)} one-year windows ({MIN_ROLL} needed): not enough history."}
    return {"count": len(vals), "median": rnd(statistics.median(vals)), "best": rnd(max(vals)), "worst": rnd(min(vals)), "mean": rnd(statistics.fmean(vals)),
            "positive": rnd(100 * sum(v > 0 for v in vals) / len(vals), 1), "why": None}


def head_to_head(a: Sequence[float], b: Sequence[float]) -> dict:
    """Share of windows in which `a` was ahead of / level with / behind `b` (two decimals of a percentage point count as level)."""
    n = min(len(a), len(b))
    ahead = sum(round(a[i], 2) > round(b[i], 2) for i in range(n))
    tie = sum(round(a[i], 2) == round(b[i], 2) for i in range(n))
    return {"ahead": rnd(100 * ahead / n, 1) if n else None, "level": rnd(100 * tie / n, 1) if n else None, "behind": rnd(100 * (n - ahead - tie) / n, 1) if n else None, "windows": n}


def xirr(flows: Sequence[Tuple[int, float]]) -> Optional[float]:
    """Annual rate r (as a fraction) at which the dated cash flows add up to zero: sum(amount / (1 + r) ^ ((day - first day) / 365)) = 0. Bisection;
    None when the flows do not change sign or no rate between -99.99% and +10 000% solves it."""
    if not flows or not any(a < 0 for _, a in flows) or not any(a > 0 for _, a in flows):
        return None
    d0 = min(d for d, _ in flows)

    def f(r: float) -> float:
        return sum(a / (1 + r) ** ((d - d0) / 365) for d, a in flows)

    lo, hi = -0.9999, 100.0
    flo, fhi = f(lo), f(hi)
    if flo == 0:
        return lo
    if fhi == 0:
        return hi
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = f(mid)
        if fm == 0 or (hi - lo) < 1e-12:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return (lo + hi) / 2


def sip_days(days: Sequence[int], start: int) -> List[int]:
    """Instalment days: the same day of the month as `start`, each moved to the first common day on or after it; none after the last day. Unique."""
    s = date.fromordinal(start)
    out: List[int] = []
    y, m = s.year, s.month
    last = days[-1]
    while True:
        t = date(y, m, min(s.day, calendar.monthrange(y, m)[1])).toordinal()
        if t > last:
            break
        i = bisect_left(days, t)
        if i < len(days) and (not out or days[i] != out[-1]):
            out.append(days[i])
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def sip_result(days: Sequence[int], vals: Sequence[float], start: int, amount: float) -> dict:
    """A monthly SIP of `amount` from `start`: units bought each instalment day at that day's price, valued at the last price. XIRR over the dated flows."""
    ds = sip_days(days, max(start, days[0]))
    if not ds:
        return {"why": "No instalment falls inside the common history."}
    m = dict(zip(days, vals))
    units = sum(amount / m[d] for d in ds)
    invested = amount * len(ds)
    value = units * vals[-1]
    out = {"installments": len(ds), "invested": rnd(invested, 2), "units": round(units, 4), "value": rnd(value, 2), "gain": rnd(value - invested, 2),
           "gainPct": rnd((value / invested - 1) * 100), "first": iso(ds[0]), "last": iso(ds[-1]), "endDate": iso(days[-1]), "endPrice": vals[-1], "xirr": None, "xirrWhy": None, "why": None}
    if days[-1] - ds[0] < 365:
        out["xirrWhy"] = "The SIP has run less than a year, so a yearly rate would mislead."
    else:
        r = xirr([(d, -amount) for d in ds] + [(days[-1], value)])
        out["xirr"] = rnd(r * 100) if r is not None else None
        out["xirrWhy"] = None if r is not None else "The rate could not be solved from these cash flows."
    return out


def lump_result(days: Sequence[int], vals: Sequence[float], start: int, amount: float) -> dict:
    i = bisect_left(days, max(start, days[0]))
    if i >= len(days) - 1:
        return {"why": "The start date is on or after the last common date."}
    units = amount / vals[i]
    value = units * vals[-1]
    span = (days[-1] - days[i]) / 365
    cagr = (value / amount) ** (1 / span) - 1 if span >= 1 and value > 0 else None
    return {"startDate": iso(days[i]), "startPrice": vals[i], "endDate": iso(days[-1]), "endPrice": vals[-1], "units": round(units, 4), "value": rnd(value, 2),
            "gain": rnd(value - amount, 2), "gainPct": rnd((value / amount - 1) * 100), "cagr": rnd(cagr * 100) if cagr is not None else None, "why": None}


def tracking_error(pv: Sequence[float], iv: Sequence[float]) -> Tuple[Optional[float], int, Optional[str]]:
    """Standard deviation of the daily return differences (product minus index) times the square root of 252, in percent. Needs about a year of days."""
    rp, ri = daily_returns(pv), daily_returns(iv)
    n = min(len(rp), len(ri))
    if n < MIN_TE:
        return None, n, f"Only {n} overlapping daily returns ({MIN_TE} needed, about one year): not enough history."
    diffs = [rp[i] - ri[i] for i in range(n)]
    return rnd(statistics.stdev(diffs) * math.sqrt(PER_YEAR) * 100, 3), n, None


def volatility(vals: Sequence[float]) -> Tuple[Optional[float], Optional[str]]:
    r = daily_returns(vals)
    if len(r) < MIN_RETURNS:
        return None, f"Only {len(r)} daily returns ({MIN_RETURNS} needed)."
    return rnd(statistics.stdev(r) * math.sqrt(PER_YEAR) * 100), None


def downside_deviation(vals: Sequence[float]) -> Tuple[Optional[float], Optional[str]]:
    """Square root of the average squared daily loss (gains count as zero), times the square root of 252, in percent."""
    r = daily_returns(vals)
    if len(r) < MIN_RETURNS:
        return None, f"Only {len(r)} daily returns ({MIN_RETURNS} needed)."
    return rnd(math.sqrt(sum(min(x, 0.0) ** 2 for x in r) / len(r)) * math.sqrt(PER_YEAR) * 100), None


def max_drawdown(days: Sequence[int], vals: Sequence[float]) -> dict:
    """Largest fall from a high to a later low (percent, negative) with the two dates; 0 when the price never closed below an earlier high."""
    if len(vals) < 2:
        return {"value": None, "peak": None, "trough": None}
    peak_i, worst, w_peak, w_trough = 0, 0.0, 0, 0
    for k, v in enumerate(vals):
        if v > vals[peak_i]:
            peak_i = k
        dd = v / vals[peak_i] - 1
        if dd < worst:
            worst, w_peak, w_trough = dd, peak_i, k
    return {"value": rnd(worst * 100), "peak": iso(days[w_peak]) if worst < 0 else None, "trough": iso(days[w_trough]) if worst < 0 else None}


def best_worst_day(days: Sequence[int], vals: Sequence[float]) -> dict:
    if len(vals) < 2:
        return {"best": None, "worst": None}
    rs = [(vals[i] / vals[i - 1] - 1, days[i]) for i in range(1, len(vals))]
    b, w = max(rs), min(rs)
    return {"best": {"value": rnd(b[0] * 100), "date": iso(b[1])}, "worst": {"value": rnd(w[0] * 100), "date": iso(w[1])}}


def slice_from(days: Sequence[int], vals: Dict[str, List[float]], months: Optional[int]) -> Tuple[Optional[List[int]], Dict[str, List[float]], Optional[str]]:
    """The common series from the last day on/before `months` back from the end (the whole series when months is None)."""
    if months is None:
        return list(days), vals, None
    i = at_or_before(days, back(days[-1], months))
    if i is None:
        return None, {}, f"Common history starts on {fmt_day(days[0])}, less than {months // 12 if months % 12 == 0 else months} {'years' if months % 12 == 0 and months > 12 else 'year' if months == 12 else 'months'} before {fmt_day(days[-1])}."
    return list(days[i:]), {k: v[i:] for k, v in vals.items()}, None


# ---------------------------------------------------------------------------------------------- the summary by category

def _lead(vals: Dict[str, Optional[float]], higher: bool, tol: float) -> dict:
    """Who is ahead on one measure: {leaders, level, values}. Products within `tol` of the best are level with it."""
    have = {k: v for k, v in vals.items() if v is not None}
    if len(have) < 2:
        return {"leaders": [], "level": False, "values": vals, "gap": None}
    best = max(have.values()) if higher else min(have.values())
    leaders = [k for k, v in have.items() if abs(v - best) <= tol + 1e-12]
    gap = abs(best - sorted(have.values(), reverse=higher)[len(leaders)]) if len(leaders) < len(have) else 0.0
    return {"leaders": leaders, "level": len(leaders) == len(have), "values": vals, "gap": rnd(gap, 3)}


def summary_rows(names: Dict[str, str], returns: Dict[str, dict], costs: Dict[str, Optional[float]], te: Dict[str, Optional[float]], risk: Dict[str, dict],
                 period: Optional[str], risk_window: Optional[str]) -> List[dict]:
    """Descriptive rows, one per measure: who was ahead, or 'level' inside the stated tolerance. No weighting and no overall ranking."""
    rows: List[dict] = []
    if period:
        vals = {k: (r[period].get("cagr") if period in ("3Y", "5Y") else r[period].get("value")) for k, r in returns.items()}
        unit = "a year" if period in ("3Y", "5Y") else "in total"
        label = dict((p, l) for p, _m, l in PERIODS)[period]
        rows.append({"category": "Returns", "measure": f"Higher return over {label}", "unit": f"% {unit}", "tol": TOL_RETURN, **_lead(vals, True, TOL_RETURN)})
    rows.append({"category": "Cost", "measure": "Lower expense ratio", "unit": "% a year", "tol": TOL_COST, **_lead(costs, False, TOL_COST)})
    rows.append({"category": "Tracking", "measure": "Smaller tracking error", "unit": "% a year", "tol": TOL_TRACK, **_lead(te, False, TOL_TRACK)})
    if risk_window:
        rows.append({"category": "Risk", "measure": "Smaller maximum fall", "unit": "%", "tol": TOL_FALL,
                     **_lead({k: (abs(r["maxDrawdown"]["value"]) if r["maxDrawdown"]["value"] is not None else None) for k, r in risk.items()}, False, TOL_FALL)})
        rows.append({"category": "Risk", "measure": "Smaller volatility", "unit": "% a year", "tol": TOL_VOL, **_lead({k: r["volatility"] for k, r in risk.items()}, False, TOL_VOL)})
    for r in rows:
        r["windowLabel"] = risk_window if r["category"] == "Risk" else (period if r["category"] == "Returns" else None)
        if r["level"]:
            r["text"] = f"{r['measure']}: level (within {r['tol']:g} percentage points)"
        elif r["leaders"]:
            r["text"] = f"{r['measure']}: " + " and ".join(names[k] for k in r["leaders"])
        else:
            r["text"] = f"{r['measure']}: not enough data to say"
    return rows


def summary_sentence(names: Dict[str, str], rows: List[dict], end: Optional[str], period: Optional[str]) -> str:
    """One plain sentence per measure that has an answer, built from the numbers, then the standing caution."""
    parts: List[str] = []
    for r in rows:
        have = {k: v for k, v in r["values"].items() if v is not None}
        if len(have) < 2:
            continue
        shown = ", ".join(f"{names[k]} {v:.2f}" for k, v in have.items())
        parts.append(f"{r['measure'].lower()} ({r['unit']}): {shown}" + (" (level within the tolerance)" if r["level"] else ""))
    head = f"Up to {fmt_day(date.fromisoformat(end).toordinal())}, on the days all of these have a price: " if end else ""
    body = "; ".join(parts) + "." if parts else "There is not enough common history to compare these products."
    return head + body + " Differences of this size can reverse in other periods. Information only, not investment advice."


# ====================================================================================== data: options (which products follow which index)

BM_SQL = """SELECT s.isin, s.code, d.value FROM mf_schemes s JOIN disclosure_facts d ON d.fkey = s.family AND d.kind = 'benchmark'
            WHERE s.isin = ANY($1::text[]) OR s.code = ANY($2::int[])"""
FUNDS_SQL = """SELECT DISTINCT ON (s.family, s.plan) s.code, s.name, s.amc, s.plan, s.nav_date, s.has_hist
               FROM mf_schemes s
               WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.scheme_type = 'Open Ended'
                 AND s.category ILIKE '%index fund%' AND s.category NOT ILIKE '%debt%' AND s.plan = ANY($1::text[])
                 AND s.name !~* '(\\mfof\\M|fund of fund|\\metf\\M)'
               ORDER BY s.family, s.plan, s.has_hist DESC, s.code"""
FUND_EXCLUDE = re.compile(r"\bfof\b|fund of fund|\betf\b", re.I)


def _bm_text(v) -> Optional[str]:
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return v
    return (v or {}).get("name") if isinstance(v, dict) else None


async def build_options(app, plan: str) -> dict:
    cache = await etf._load(app)
    rows = [r for r in cache["rows"] if r.get("asset_class") in (None, "equity")]
    plans = ["Direct"] if plan == "Direct" else ["Direct", "Regular"]
    async with app.state.store.pool.acquire() as conn:
        funds = [dict(r) for r in await conn.fetch(FUNDS_SQL, plans)]
        try:
            bms = await conn.fetch(BM_SQL, [r["isin"] for r in rows], [f["code"] for f in funds])
        except Exception:   # the disclosure tables may not exist yet: names decide
            log.warning("benchmark facts not readable", exc_info=True)
            bms = []
    by_isin = {b["isin"]: _bm_text(b["value"]) for b in bms if b["isin"]}
    by_code = {b["code"]: _bm_text(b["value"]) for b in bms}
    etfs, fnds, unmatched, conflicts = [], [], 0, 0
    for r in rows:
        bm = by_isin.get(r["isin"])
        c = classify(bm, [etf.tidy_scheme(r.get("scheme_name")), r.get("display_name"), r.get("short_name"), r.get("exchange_name")])
        conflicts += c["conflict"]
        if c["key"]:
            etfs.append({"symbol": r["symbol"], "name": r["display_name"], "fundHouse": r.get("fund_house"), "index": c["key"], "indexBasis": c["basis"], "returnType": c["returnType"],
                         "benchmark": bm, "firstDate": r["first_date"].isoformat() if r.get("first_date") else None, "priceDate": r["price_date"].isoformat() if r.get("price_date") else None})
    for f in funds:
        if FUND_EXCLUDE.search(f["name"]):
            continue
        bm = by_code.get(f["code"])
        c = classify(bm, [f["name"]])
        conflicts += c["conflict"]
        if c["key"]:
            fnds.append({"code": f["code"], "name": f["name"], "amc": f["amc"], "plan": f["plan"], "index": c["key"], "indexBasis": c["basis"], "returnType": c["returnType"],
                         "benchmark": bm, "navDate": f["nav_date"].isoformat() if f["nav_date"] else None})
        else:
            unmatched += 1
    idx = []
    for key, label, code, _p in INDICES:
        ne, nf = sum(e["index"] == key for e in etfs), sum(f["index"] == key for f in fnds)
        if ne or nf:
            idx.append({"key": key, "label": label, "code": code, "etfCount": ne, "fundCount": nf, "ready": bool(ne and nf)})
    etfs.sort(key=lambda e: (e["name"].lower(), e["symbol"]))
    fnds.sort(key=lambda f: (f["name"].lower(), f["code"]))
    return {"indices": idx, "etfs": etfs, "funds": fnds, "plan": plan, "unmatchedFunds": unmatched, "conflicts": conflicts, "asOf": cache.get("asOf"),
            "source": "Index of each product: the benchmark in fund-house and AMFI disclosures we have, else the index named in the scheme's registered name.", "disclaimer": DISCLAIMER}


@router.get("/options")
async def options(request: Request, plan: str = Query("Direct", pattern="^(Direct|All)$")) -> Response:
    """The benchmark indices that ETFs and index funds in our data follow, with the products of each. Direct plans by default."""
    app = request.app
    c = getattr(app.state, "evi_opts", None) or {}
    hit = c.get(plan)
    if not hit or time.time() - hit[0] > OPT_TTL:
        hit = (time.time(), json.dumps(await build_options(app, plan), default=etf._default, separators=(",", ":")))
        c[plan] = hit
        app.state.evi_opts = c
    return Response(content=hit[1], media_type="application/json", headers={"Cache-Control": f"public, max-age={OPT_TTL // 3}"})


# ====================================================================================== data: series and facts

async def index_levels(app, key: str) -> Tuple[List[int], List[float], Optional[str]]:
    """Daily closing levels (price index) from the index data provider's saved copy; (days, levels, None) or ([], [], reason)."""
    code = INDEX_BY[key][2]
    if not code:
        return [], [], "The index data provider does not carry this index."
    from . import indices
    try:
        raw = await indices._cached(app, f"idx:px:{code}", 3600 if indices.market_open() else 6 * 3600, lambda: indices._fetch_levels(app, code))
    except Exception as exc:
        log.warning("index levels failed for %s: %s", code, type(exc).__name__)
        raw = None
    if raw is None:
        return [], [], "The index levels are not available right now."
    rows = indices.shape_levels(raw, indices.HISTORY_YEARS)["rows"]
    if len(rows) < 2:
        return [], [], "The index data provider returned no usable levels."
    return [date.fromisoformat(r["d"]).toordinal() for r in rows], [r["c"] for r in rows], None


def _pct_of(text) -> Optional[float]:
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*%", str(text or ""))
    return float(m.group(1)) if m else None


async def etf_series(app, r: dict) -> Tuple[List[int], List[float], str, Optional[str]]:
    """(days, values, basis, note) of one ETF: the exchange close (after any split break), or its stored AMFI NAV when that history covers the same period."""
    h, why = await etf._history(app, r["symbol"], r)
    if not h or len(h["dates"]) < 2:
        return [], [], "price", why or "No price history."
    brk = r.get("break_date")
    k = max(bisect_right(h["dates"], brk) - 1, 0) if brk else 0
    days, closes = [d.toordinal() for d in h["dates"][k:]], list(h["closes"][k:])
    note = f"Prices before {brk.strftime('%d %b %Y')} are left out: the source shows a jump there that looks like a split or a bad price." if brk else None
    try:
        async with app.state.store.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT h.blob, h.d0 FROM mf_history h JOIN mf_schemes s ON s.code = h.code WHERE s.isin = $1 OR s.isin_reinvest = $1 LIMIT 1", r["isin"])
    except Exception:
        row = None
    if row:
        nd, nv = mf.unpack_series(bytes(row["blob"]), row["d0"].toordinal())
        if nd and nd[0] <= days[0] + 31 and nd[-1] >= days[-1] - 7:
            return nd, nv, "nav", None
    return days, closes, "price", note


async def facts_of(pool, key) -> dict:
    try:
        from . import disclosure
        got = await disclosure.get_facts(pool, key)
    except Exception:
        log.warning("facts unavailable for %s", key, exc_info=True)
        got = None
    return got if isinstance(got, dict) else {}


def _fact(f, why: str) -> dict:
    if isinstance(f, dict) and "value" in f:
        return {"value": f["value"], "asOf": f.get("asOf"), "source": f.get("source"), "note": f.get("note")}
    return {"value": None, "why": (f or {}).get("unavailable") if isinstance(f, dict) and f.get("unavailable") else why}


# ====================================================================================== the comparison

def _ids(csv: str, kind: str) -> List[str]:
    out: List[str] = []
    for s in csv.split(","):
        s = s.strip()
        if s and s not in out:
            out.append(s)
    return out


def _thin(days: List[int], cap: int) -> List[int]:
    n = len(days)
    if n <= cap:
        return list(range(n))
    step = math.ceil((n - 1) / (cap - 1))
    return sorted(set(range(n - 1, -1, -step)) | {0})


def compute(prods: List[dict], series: Dict[str, Tuple[List[int], List[float]]], index: Optional[Tuple[List[int], List[float]]], index_why: Optional[str],
            sip_amount: float, lump_amount: float, from_day: Optional[int]) -> dict:
    """Every measure from the series. `prods` carry id, name, kind; `series` is keyed by id. Pure."""
    ids = [p["id"] for p in prods]
    names = {p["id"]: p["label"] for p in prods}
    days, vals = align({k: series[k] for k in ids})
    out: dict = {"common": {"days": len(days)}}
    if len(days) < MIN_COMMON:
        out["common"].update(**{"why": f"The chosen products share only {len(days)} dates with a price: not enough to compare.", "from": None, "to": None})
        return out
    end = days[-1]
    out["common"].update(**{"from": iso(days[0]), "to": iso(end), "why": None})
    # 1 performance
    rets: Dict[str, dict] = {k: {} for k in ids}
    for k in ids:
        for key, months, label in PERIODS:
            rets[k][key] = period_return(days, vals[k], months, label)
        rets[k]["since"] = period_return(days, vals[k], None)
    roll: Dict[str, dict] = {}
    rolled = {k: rolling_returns(days, vals[k], 12) for k in ids}
    for k in ids:
        roll[k] = roll_stats(rolled[k][1])
    ref = ids[0]
    h2h = {k: head_to_head(rolled[k][1], rolled[ref][1]) for k in ids[1:]} if len(rolled[ref][1]) >= MIN_ROLL else {}
    start = max(from_day if from_day else days[0], days[0])
    if not from_day:   # default SIP start: five years before the last common date, or the first common date when the history is shorter
        start = max(days[0], back(end, 60))
    sip = {k: sip_result(days, vals[k], start, sip_amount) for k in ids}
    lump = {k: lump_result(days, vals[k], start, lump_amount) for k in ids}
    for res, key in ((sip, "value"), (lump, "value")):
        base = res[ref].get(key)
        for k in ids:
            v = res[k].get(key)
            res[k]["diffVsRef"] = None if base is None or v is None or k == ref else {"rupees": rnd(v - base, 2), "pct": rnd((v / base - 1) * 100)}
    # 3 tracking, against the price index and against the first product
    track: Dict[str, dict] = {k: {"td": {}, "gap": {}} for k in ids}
    te: Dict[str, Optional[float]] = {}
    idx_days: List[int] = []
    idx_vals: Dict[str, List[float]] = {}
    if index:
        iset = set(index[0])
        idx_days = [d for d in days if d in iset]
        if len(idx_days) >= MIN_COMMON:
            idx_vals = {k: subset(days, vals[k], idx_days) for k in ids}
            iv = subset(index[0], index[1], idx_days)
        else:
            index_why = index_why or f"The index levels share only {len(idx_days)} dates with the products."
            idx_days = []
    for k in ids:
        for key, months, label in TRACK_PERIODS:
            g = period_return(days, vals[k], months, label)
            gr = period_return(days, vals[ref], months, label)
            td_entry: dict = {"value": None, "annual": None, "why": index_why or "No index levels."}
            if idx_days:
                p, i = period_return(idx_days, idx_vals[k], months, label), period_return(idx_days, iv, months, label)
                if p["value"] is None or i["value"] is None:
                    td_entry = {"value": None, "annual": None, "why": p["why"] or i["why"]}
                else:
                    ann = (p["cagr"] - i["cagr"]) if p["cagr"] is not None and i["cagr"] is not None else None
                    td_entry = {"value": rnd(p["value"] - i["value"]), "annual": rnd(ann) if ann is not None else None, "why": None, "product": p["value"], "index": i["value"],
                                "from": p["from"], "to": p["to"]}
            track[k]["td"][key] = td_entry
            if k != ref:
                track[k]["gap"][key] = {"value": rnd(g["value"] - gr["value"]) if g["value"] is not None and gr["value"] is not None else None,
                                        "why": g["why"] or gr["why"]}
        if idx_days:
            t, n, why = tracking_error(idx_vals[k], iv)
            track[k]["te"] = {"value": t, "returns": n, "why": why, "from": iso(idx_days[0]), "to": iso(idx_days[-1])}
            te[k] = t
        else:
            track[k]["te"] = {"value": None, "returns": 0, "why": index_why or "No index levels."}
            te[k] = None
    # 4 risk, per window
    risk: Dict[str, Dict[str, dict]] = {}
    for key, months in (("1Y", 12), ("3Y", 36), ("5Y", 60), ("all", None)):
        sd, sv, why = slice_from(days, vals, months)
        if sd is None:
            risk[key] = {"why": why}
            continue
        block = {}
        for k in ids:
            v, vwhy = volatility(sv[k])
            dsd, dwhy = downside_deviation(sv[k])
            rd, rv = rolling_returns(sd, sv[k], 12)
            block[k] = {"volatility": v, "volatilityWhy": vwhy, "maxDrawdown": max_drawdown(sd, sv[k]), "downside": dsd, "downsideWhy": dwhy,
                        "worstRolling": ({"value": rnd(min(rv)), "end": iso(rd[rv.index(min(rv))])} if len(rv) >= MIN_ROLL else None),
                        "worstRollingWhy": None if len(rv) >= MIN_ROLL else f"Only {len(rv)} one-year windows in this period.", **best_worst_day(sd, sv[k]), "from": iso(sd[0]), "to": iso(sd[-1]), "days": len(sd)}
        risk[key] = {"products": block, "from": iso(sd[0]), "to": iso(sd[-1])}
    # the summary by category: the longest return period every product has, the longest risk window every product has
    period = next((p for p in ("5Y", "3Y", "1Y") if all(rets[k][p]["value"] is not None for k in ids)), None)
    rwin = next((w for w in ("5Y", "3Y", "1Y", "all") if w in risk and "products" in risk[w]), None)
    # chart
    pick = _thin(days, CHART_CAP)
    cd = [days[i] for i in pick]
    chart = {"t": [iso(d) for d in cd], "v": {k: [round(vals[k][i], 4) for i in pick] for k in ids}, "index": None, "indexWhy": index_why}
    if index:
        im = index[0]
        ivals = []
        for d in cd:
            j = at_or_before(im, d, 5)
            ivals.append(round(index[1][j], 2) if j is not None else None)
        chart["index"] = ivals
        if ivals[0] is None:
            chart["index"], chart["indexWhy"] = None, f"Index levels on file start on {fmt_day(im[0])}, after the first common date ({fmt_day(days[0])}); choose a shorter period to see the index line."
    out.update(returns=rets, rolling={"stats": roll, "headToHead": h2h, "ref": ref, "windows": len(rolled[ref][1])}, sip=sip, lump=lump, startDay=iso(start),
               tracking=track, risk=risk, chart=chart, _te=te, _period=period, _rwin=rwin, _names=names, _vals=vals, _days=days)
    return out


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


async def compare_payload(request: Request, index: str, etfs: List[str], funds: List[int], plan: str, sip_amount: float, lump_amount: float, from_day: Optional[date]) -> dict:
    app = request.app
    cache = await etf._load(app)
    label = INDEX_BY[index][1]
    prods: List[dict] = []
    pool = app.state.store.pool
    # ETFs
    for s in etfs:
        r = cache["by"].get(s)
        if not r:
            raise fail(404, "unknown_etf", f"No ETF with the symbol {s}.")
        prods.append({"id": s, "kind": "etf", "label": s, "row": r})
    for c in funds:
        row = dict(await mf._scheme(request, c))
        if row["option_class"] != "Growth" or not row["active"] or row["scheme_type"] != "Open Ended" or "index fund" not in row["category"].lower():
            raise fail(400, "bad_request", f"Scheme {c} is not an active Growth option of an open-ended index fund.")
        if plan == "Direct" and row["plan"] != "Direct":
            raise fail(400, "regular_plan", f"{row['name']} is a {row['plan']} plan. Direct plans are compared by default; include regular plans to choose it.")
        prods.append({"id": str(c), "kind": "fund", "label": row["name"], "row": row})
    facts = await asyncio.gather(*[facts_of(pool, p["row"]["isin"] if p["kind"] == "etf" else p["row"]["code"]) for p in prods])
    for p, f in zip(prods, facts):
        bm = (f.get("benchmark") or {}).get("value") if isinstance(f.get("benchmark"), dict) else None
        names = [etf.tidy_scheme(p["row"].get("scheme_name")), p["row"].get("display_name"), p["row"].get("short_name")] if p["kind"] == "etf" else [p["row"]["name"]]
        c = classify(bm if isinstance(bm, str) else None, names)
        if c["key"] != index:
            raise fail(400, "index_mismatch", f"{p['label']} does not follow the {label} (its benchmark is " + (f"'{bm}'" if bm else "not stored; its name points elsewhere") + ").")
        p["class"], p["facts"], p["bm"] = c, f, bm if isinstance(bm, str) else None
    # series
    async def load(p):
        if p["kind"] == "etf":
            d, v, basis, note = await etf_series(app, p["row"])
            return d, v, basis, note, ("AMFI NAV" if basis == "nav" else "NSE closing price")
        d, v, src, note = await mf_compare.fund_series(app, p["row"], "10Y")
        return d, v, "nav", note, ("AMFI NAV (mirror of AMFI data)" if src == "mirror" else "AMFI NAV")
    loaded = await asyncio.gather(*[load(p) for p in prods], index_levels(app, index))
    il = loaded[-1]
    series, missing = {}, []
    for p, (d, v, basis, note, src) in zip(prods, loaded[:-1]):
        p["basis"], p["note"], p["source"] = basis, note, src
        p["first"], p["last"] = (iso(d[0]), iso(d[-1])) if d else (None, None)
        if len(d) >= 2:
            series[p["id"]] = (d, v)
        else:
            missing.append(p["label"])
    notes: List[str] = []
    if any(p["basis"] == "price" for p in prods if p["kind"] == "etf"):
        notes.append("An ETF is measured on its exchange closing price (its NAV history is not stored), a fund on its AMFI NAV. A closing price can sit a little above or below the NAV (premium or discount), which adds a small amount of day-to-day noise.")
    rts = {p["class"]["returnType"] for p in prods}
    if len(rts - {None}) > 1 or (rts - {None} and None in rts):
        notes.append("The products state their benchmark differently (" + ", ".join(sorted(f"{p['label']}: {p['class']['returnType'] or 'return type not stated'}" for p in prods)) + "). This page compares the products with each other and with the price index; it does not treat the benchmarks as the same series.")
    for p in prods:
        if p["note"]:
            notes.append(f"{p['label']}: {p['note']}")
    ends = [date.fromisoformat(p["last"]).toordinal() for p in prods if p.get("last")]
    if ends and max(ends) - min(ends) > 7:
        notes.append("The products' latest dates differ by more than a week, so the comparison ends on the earliest of them.")
    use = [p for p in prods if p["id"] in series]
    body: dict = {}
    if len(use) >= 2:
        idx = (il[0], il[1]) if il[0] else None
        body = compute(use, series, idx, il[2], sip_amount, lump_amount, from_day.toordinal() if from_day else None)
    else:
        body = {"common": {"days": 0, "why": "At least two of the chosen products need a price history: " + ", ".join(missing) + " has none right now."}}
    # costs
    costs = {}
    for p in prods:
        f, row = p["facts"], p["row"]
        ter_fact = f.get("ter") if p["kind"] == "etf" else f.get("terRegular" if row["plan"] == "Regular" else "terDirect")
        ter = _fact(ter_fact, "Not published in the sources loaded for this scheme.")
        pct = _pct_of(ter.get("value"))
        costs[p["id"]] = {"ter": ter, "terPct": pct, "dragPerYear": round(DRAG_BASE * pct / 100) if pct is not None else None,
                          "exitLoad": _fact(f.get("exitLoad"), "Not published in the sources loaded for this scheme."),
                          "minimum": _fact(f.get("minInvestment"), "Not published in the sources loaded for this scheme.") if p["kind"] == "etf" else
                          {"value": None, "why": "A minimum SIP amount is stated in each scheme's own documents; no free machine-readable official source was found, so none is shown."},
                          "aum": _fact(f.get("aum"), "Not published in the sources loaded for this scheme.")}
    extra = {}
    for p in prods:
        if p["kind"] == "etf":
            extra[p["id"]] = {"premium": etf.row_view(p["row"]).get("premium"), "navDate": p["row"]["nav_date"].isoformat() if p["row"].get("nav_date") else None}
    # summary
    summ = None
    if "_te" in body:
        names = body["_names"]
        tpct = {k: costs[k]["terPct"] for k in names}
        rows = summary_rows(names, body["returns"], tpct, body["_te"], {k: v for k, v in (body["risk"].get(body["_rwin"], {}).get("products") or {}).items()}, body["_period"], body["_rwin"])
        summ = {"rows": rows, "sentence": summary_sentence(names, rows, body["common"]["to"], body["_period"]), "tolerances": TOLERANCES}
    return {"index": {"key": index, "label": label, "code": INDEX_BY[index][2], "levels": "price index, dividends not included", "why": il[2]},
            "plan": plan,
            "products": [{"id": p["id"], "kind": p["kind"], "name": p["row"].get("display_name") if p["kind"] == "etf" else p["row"]["name"], "label": p["label"], "house": p["row"].get("fund_house") if p["kind"] == "etf" else p["row"]["amc"],
                          "plan": "Exchange traded" if p["kind"] == "etf" else p["row"]["plan"], "benchmark": p["bm"], "indexBasis": p["class"]["basis"], "returnType": p["class"]["returnType"],
                          "basis": p["basis"], "source": p["source"], "first": p["first"], "last": p["last"]} for p in prods],
            **_clean(body), "costs": costs, "etfExtra": extra, "summary": summ, "notes": notes, "tolerances": TOLERANCES,
            "inputs": {"sip": sip_amount, "lump": lump_amount, "dragBase": DRAG_BASE},
            "asOf": body.get("common", {}).get("to"), "generatedAt": datetime.now(timezone.utc).isoformat(), "disclaimer": DISCLAIMER}


@router.get("/compare")
async def compare(request: Request, index: str = Query(..., pattern="^[a-z0-9]{3,20}$"), etfs: str = Query("", max_length=120, alias="etf"), funds: str = Query("", max_length=120, alias="fund"),
                  plan: str = Query("Direct", pattern="^(Direct|All)$"), sip: float = Query(10000, ge=100, le=10_000_000), lump: float = Query(100000, ge=1000, le=1_000_000_000),
                  start: Optional[date] = Query(None)) -> Response:
    """One or more ETFs and one or more direct-plan index funds that follow the same index: returns, costs, tracking, risk and a SIP / lump-sum calculation."""
    if index not in INDEX_BY:
        raise fail(400, "bad_request", "Unknown index.")
    syms = [s.upper() for s in _ids(etfs, "etf")]
    if any(not etf.SYMBOL_RE.match(s) for s in syms):
        raise fail(400, "bad_request", "Unknown ETF symbol.")
    try:
        codes = [int(c) for c in _ids(funds, "fund")]
    except ValueError:
        raise fail(400, "bad_request", "Fund codes must be numbers.")
    if any(not 0 < c < 10**7 for c in codes):
        raise fail(400, "bad_request", "Unknown fund code.")
    if not syms or not codes or len(syms) + len(codes) > MAX_PRODUCTS:
        raise fail(400, "bad_request", f"Choose at least one ETF and one index fund, {MAX_PRODUCTS} products at most.")
    if start and (start > date.today() or start.year < 2000):
        raise fail(400, "bad_request", "The start date is out of range.")
    key = f"{index}|{','.join(syms)}|{','.join(map(str, codes))}|{plan}|{sip}|{lump}|{start}"
    return await mf_compare._cached(request, "evi", key, lambda: compare_payload(request, index, syms, codes, plan, sip, lump, start), COMPARE_TTL)
