"""Mutual funds: list, detail and compare, built on AMFI's own public files (no key, no paid service).

Sources, in order of preference
  1. https://portal.amfiindia.com/spages/NAVAll.txt  every scheme AMFI publishes (about 14,400, stopped ones included) with its latest NAV and date.
     The section header lines give the category ("Open Ended Schemes(Equity Scheme - Mid Cap Fund)"), a line below names the fund house.
  2. https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?mf=<id>&frmdt=DD-Mon-YYYY&todt=DD-Mon-YYYY  the official daily NAV history.
     It can only be asked for a whole fund house (the `scheme` parameter is ignored), about 13 MB and 9 s a year for a house of 400 schemes, so history is
     loaded one fund house at a time by `backfill`. The ids are the ones in the fund-house dropdown of amfiindia.com/net-asset-value/nav-history (AMC_IDS).
  3. https://api.mfapi.in/mf/<code>  a third-party mirror of the same AMFI data. Used only on demand, for a Growth scheme whose AMFI history has not been
     loaded (for example fund houses missing from AMFI's dropdown), and only after its newest NAV is checked against AMFI's NAVAll. The page always says so.

What is stored (the free database is small): every scheme with its latest NAV, its previous NAV (the 1 day change), its 1, 3 and 5 year returns, its
SIP returns (worked out from about 60 month-end NAVs a scheme, table mf_monthly), fund size, expense ratio and checklist, so the list is a plain query. The daily NAV series (packed at ~3 bytes a point, with volatility, drawdown and the other periods) is kept only for the
100 "hot" schemes, answered from the mf_hot table / Redis in milliseconds; any other Growth scheme's series is fetched when somebody opens it and cached in
Redis for a few days. The 1 year and 5 year figures of the others are kept current each night from AMFI's industry-wide history for just the two start dates. IDCW / dividend options are listed
with their own NAV but no returns: a payout lowers the NAV, so NAV-to-NAV change would understate what an investor earned.

Not here, on purpose: AUM, expense ratio, holdings, sector split, benchmark, manager, launch date, risk-o-meter. AMFI does not put them in the NAV files and
nothing is shown that cannot be checked against a source. This is information only, never advice.
"""

from __future__ import annotations

import array
import asyncio
import calendar
import functools
import hashlib
import json
import logging
import math
import re
import statistics
import sys
import time
import unicodedata
import zlib
from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import httpx
from fastapi import APIRouter, Query, Request, Response

from .auth.routes import fail
from .config import MF_EXCLUDED_AMCS, MF_FEATURED_AMCS
from .store import dumps, etag_for
from .background import etag_matches

log = logging.getLogger("finlit.mf")
router = APIRouter(prefix="/api/mf")

NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx"
MIRROR_URL = "https://api.mfapi.in/mf"
USER_AGENT = "FinLitVentures-MF/1.0 (+https://finlitventures.com; reads AMFI's public NAV files once a day)"

KEEP_DAYS = 5 * 366 + 20      # history kept: five years and a little more, so the 5Y start day is always inside
ACTIVE_DAYS = 7               # a scheme whose last NAV is older than this, against the newest NAV in the file, has stopped publishing
MIN_KEEP_RATIO = 0.8          # a file with fewer schemes than this share of what is stored is refused, never applied
MAX_STALE = 7                 # a return's start NAV may be at most this many days before the start date (weekends, holidays)
SCALE = 100_000_000           # NAVs are stored as integers in 1e-8 units (AMFI gives up to 8 decimals)
PAGE_MAX = 100
COLD_TTL = 3 * 86400          # a scheme that is not hot stays in Redis this long after it was last opened
HOT_SIZE = 100
HOT_TTL = 36 * 3600
OPENS_KEY = "mf:opens"        # Redis hash: scheme code -> how many times it was opened (feeds the fallback hot ranking)
ANCHOR_DAYS = 14             # the window of AMFI history asked for around each return's start date
CACHE_HEADER = "public, max-age=300, stale-while-revalidate=3600"
DISCLAIMER = "Information only. Not investment advice. Past returns do not guarantee future returns."
SOURCE = "AMFI (Association of Mutual Funds in India), official NAV files"

NOT_AVAILABLE = {
    "items": ["Assets under management (AUM)", "Expense ratio (TER)", "Exit load", "Holdings", "Sector split", "Benchmark", "Fund manager", "Launch date", "Risk-o-meter"],
    "why": "AMFI publishes AUM and expense ratio in separate monthly files, not in the NAV file, and the other items only in each fund house's factsheet. They are not loaded yet, so nothing is shown rather than a guess.",
}

# Fund-house ids of AMFI's history download, from the dropdown on amfiindia.com/net-asset-value/nav-history (the page embeds the list; `parse_amc_ids` reads it).
AMC_IDS: Dict[str, int] = {
    "360 ONE Mutual Fund": 62, "Abakkus Mutual Fund": 85, "ABN AMRO Mutual Fund": 39, "Aditya Birla Sun Life Mutual Fund": 3, "AEGON Mutual Fund": 50,
    "Alliance Capital Mutual Fund": 1, "Angel One Mutual Fund": 80, "Axis Mutual Fund": 53, "Bajaj Finserv Mutual Fund": 75, "Bandhan Mutual Fund": 48,
    "Bank of India Mutual Fund": 46, "Baroda BNP Paribas Mutual Fund": 4, "Benchmark Mutual Fund": 36, "BNP Paribas Mutual Fund": 59,
    "Canara Robeco Mutual Fund": 32, "Capitalmind Mutual Fund": 81, "Choice Mutual Fund": 84, "Daiwa Mutual Fund": 60, "DBS Chola Mutual Fund": 31,
    "Deutsche Mutual Fund": 38, "DSP Mutual Fund": 6, "Edelweiss Mutual Fund": 47, "Fidelity Mutual Fund": 40, "Fortis Mutual Fund": 51,
    "Franklin Templeton Mutual Fund": 27, "GIC Mutual Fund": 8, "Goldman Sachs Mutual Fund": 49, "Groww Mutual Fund": 63, "HDFC Mutual Fund": 9,
    "Helios Mutual Fund": 76, "HSBC Mutual Fund": 37, "ICICI Prudential Mutual Fund": 20, "IDBI Mutual Fund": 57, "IL&F S Mutual Fund": 11,
    "IL&FS Mutual Fund (IDF)": 65, "ING Mutual Fund": 14, "Invesco Mutual Fund": 42, "ITI Mutual Fund": 70, "Jio BlackRock Mutual Fund": 82,
    "JM Financial Mutual Fund": 16, "JPMorgan Mutual Fund": 43, "Kotak Mahindra Mutual Fund": 17, "L&T Mutual Fund": 56, "LIC Mutual Fund": 18,
    "Mahindra Manulife Mutual Fund": 69, "Mirae Asset Mutual Fund": 45, "Morgan Stanley Mutual Fund": 19, "Motilal Oswal Mutual Fund": 55,
    "Navi Mutual Fund": 54, "Nippon India Mutual Fund": 21, "NJ Mutual Fund": 73, "Old Bridge Mutual Fund": 78, "PGIM India Mutual Fund": 58,
    "PineBridge Mutual Fund": 44, "PNB Mutual Fund": 34, "PPFAS Mutual Fund": 64, "Principal Mutual Fund": 10, "quant Mutual Fund": 13,
    "Quantum Mutual Fund": 41, "Samco Mutual Fund": 74, "SBI Mutual Fund": 22, "Shinsei Mutual Fund": 52, "Shriram Mutual Fund": 67,
    "Standard Chartered Mutual Fund": 2, "SUN F&C Mutual Fund": 24, "Sundaram Mutual Fund": 33, "Tata Mutual Fund": 25, "Taurus Mutual Fund": 26,
    "The Wealth Company Mutual Fund": 83, "Trust Mutual Fund": 72, "Unifi Mutual Fund": 79, "Union Mutual Fund": 61, "UTI Mutual Fund": 28,
    "WhiteOak Capital Mutual Fund": 71, "Zerodha Mutual Fund": 77, "Zurich India Mutual Fund": 29,
}


def amc_key(name: str) -> str:
    """Fund-house name as a comparable key: letters and digits only, 'mutual fund' dropped ("Axis Mutual Fund" and "AXIS MUTUAL FUND" agree)."""
    s = re.sub(r"[^a-z0-9]+", "", re.sub(r"mutual\s*fund", "", unicodedata.normalize("NFKD", name).lower()))
    return s or re.sub(r"[^a-z0-9]+", "", name.lower())


AMC_BY_KEY: Dict[str, int] = {amc_key(n): i for n, i in AMC_IDS.items()}


_HOUSE_WORDS = re.compile(r"\b(?:mutual\s+fund|mf|asset\s+management|asset\s+managers|amc|company|limited|ltd|private|pvt)\b")


def house_stem(name: str) -> str:
    """A fund-house name reduced to its distinctive words: lower case, punctuation gone, 'Mutual Fund' / 'Asset Management' / 'Limited' words dropped.
    'Trust Mutual Fund' -> 'trust', 'PGIM India Mutual Fund' -> 'pgim india', 'ASK MUTUAL FUND' -> 'ask'."""
    t = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", name).lower().replace("&", " and "))
    return re.sub(r"\s+", " ", _HOUSE_WORDS.sub(" ", t)).strip()


EXCLUDED_STEMS = frozenset(house_stem(n) for n in MF_EXCLUDED_AMCS)


def is_excluded_amc(name: str) -> bool:
    """True when the fund house is on config.MF_EXCLUDED_AMCS. The WHOLE distinctive name must equal an entry (so 'Trust' never matches 'Trustline' or
    'Union', 'ITI' never matches 'ITI' inside another word, and 'NJ' never matches 'NJ' inside a longer name)."""
    return house_stem(name) in EXCLUDED_STEMS


def parse_amc_ids(page: str) -> Dict[str, int]:
    """Fund-house ids from the HTML of AMFI's NAV history page (it embeds {"mfId":"53","mfName":"Axis Mutual Fund"} for the dropdown)."""
    text = page.replace('\\"', '"').replace("\\u0026", "&")
    return {re.sub(r"\s+", " ", n).strip(): int(i) for i, n in re.findall(r'"mfId":"(\d+)","mfName":"([^"]*)"', text)}


# ====================================================================================== parsing AMFI's files

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
CAT_RE = re.compile(r"^((?:open|close|closed|interval)\b[^();]*?)\s*\((.*)\)\s*$", re.I)
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")
_date_cache: Dict[str, Optional[date]] = {}


def parse_date(s: str) -> Optional[date]:
    """'19-Oct-2026' (AMFI) -> date, independent of locale; None when it is not a real date."""
    s = s.strip()
    if s in _date_cache:
        return _date_cache[s]
    out: Optional[date] = None
    p = s.split("-")
    if len(p) == 3 and p[0].isdigit() and p[2].isdigit() and p[1][:3].lower() in MONTHS:
        try:
            out = date(int(p[2]), MONTHS[p[1][:3].lower()], int(p[0]))
        except ValueError:
            out = None
    if len(_date_cache) < 20000:
        _date_cache[s] = out
    return out


def parse_nav(s: str) -> Optional[float]:
    """A positive finite NAV, or None for 'N.A.', '-', blanks, text, zero or negative numbers."""
    try:
        v = float(s.strip())
    except ValueError:
        return None
    return v if math.isfinite(v) and v > 0 else None


@dataclass
class Scheme:
    code: int
    name: str
    amc: str
    category: str
    scheme_type: str
    plan: str
    option_class: str
    option_label: str
    family: str
    isin: Optional[str]
    isin_reinvest: Optional[str]
    nav: Optional[float]
    nav_date: Optional[date]


@dataclass
class Parsed:
    schemes: List[Scheme] = field(default_factory=list)
    skipped: Dict[str, int] = field(default_factory=dict)   # what was left out or left blank, and how many
    header_ok: bool = False
    lines: int = 0

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1

    @property
    def newest(self) -> Optional[date]:
        return max((s.nav_date for s in self.schemes if s.nav_date), default=None)


def split_category(line: str) -> Optional[Tuple[str, str]]:
    """'Open Ended Schemes(Equity Scheme - Mid Cap Fund)' -> ('Open Ended', 'Equity Scheme - Mid Cap Fund'); None when the line is not a section header."""
    m = CAT_RE.match(line.strip())
    if not m:
        return None
    kind = re.sub(r"\s*schemes?$", "", re.sub(r"\s+", " ", m.group(1)).strip(), flags=re.I).strip()
    kind = {"Close": "Close Ended", "Closed": "Closed Ended", "Interval": "Interval Fund"}.get(kind, kind)
    return kind, re.sub(r"\s+", " ", m.group(2)).strip()


_IDCW = re.compile(r"idcw|dividend|income\s+distribution|payout|reinvest", re.I)


def clean_plan(raw: str, name: str) -> str:
    t = raw.lower()
    if "direct" in t:
        return "Direct"
    if "regular" in t:
        return "Regular"
    n = name.lower()
    if re.search(r"\bdirect\b", n):
        return "Direct"
    if re.search(r"\bregular\b", n):
        return "Regular"
    return "Unspecified"


def clean_option(raw: str, name: str) -> Tuple[str, str]:
    """(class, label). Class is Growth, IDCW (dividend / payout / reinvestment, which change the NAV) or Other (AMFI states no option, or a bonus option).
    AMFI's option column decides; the name is read only when the column is blank, and only its last ' - ' part (a fund can be called 'Dividend Yield Fund')."""
    raw = re.sub(r"\s+", " ", raw).strip()
    if raw:
        if _IDCW.search(raw):
            return "IDCW", raw
        if "growth" in raw.lower():
            return "Growth", raw
        return "Other", raw
    last = re.split(r"\s[-–]\s", name)[-1].strip().lower() if re.search(r"\s[-–]\s", name) else ""
    if last and _IDCW.search(last):
        return "IDCW", "IDCW"
    if re.fullmatch(r"(direct |regular )?(plan )?growth( option| plan)?", last):
        return "Growth", "Growth"
    return "Other", "Not stated"


_FREQ = r"(?:monthly|quarterly|weekly|daily|annual|annually|yearly|half[ -]?yearly|fortnightly|periodic|bi[ -]?monthly)"
_STEM = [
    re.compile(r"\b(?:payout|reinvestment|reinvest)\s+of\s+"),
    re.compile(rf"\b(?:{_FREQ}\s+)?(?:idcw|income distribution cum capital withdrawal|income distribution cum capital withdrawl|income distribution|dividend)\b(?:\s+(?:payout|reinvestment|reinvest|option|plan|sweep))*"),
    re.compile(r"\b(?:growth|bonus)\b(?:\s+(?:option|plan|payout|reinvestment|reinvest))*"),
    re.compile(r"\b(?:direct|regular)\b(?:\s+plan)?"),
    re.compile(r"\b(?:payout|reinvestment|reinvest)\b"),
]


def family_stem(name: str) -> str:
    """The scheme name without its plan and option words, so 'X Fund - Direct Plan - Growth' and 'X Fund - Regular Plan - IDCW' share a stem.
    Frequencies are removed only when they sit next to IDCW ('Monthly IDCW'), never alone: 'Monthly Interval Plan' and 'Quarterly Interval Plan' differ."""
    s = re.sub(r"[^a-z0-9 ]+", " ", unicodedata.normalize("NFKD", name).lower())
    for rx in _STEM:
        s = rx.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


IST = timezone(timedelta(hours=5, minutes=30))
FUTURE_DAYS = 1   # a NAV may carry tomorrow's date near midnight; anything later is a typo in the file and is not stored


def latest_allowed(today: Optional[date] = None) -> date:
    """The latest NAV date accepted: today in India plus a day. A row dated later (a typo such as 2062) would otherwise become the 'newest' date and
    make every correct file look older than what is stored."""
    return (today or india_today()) + timedelta(days=FUTURE_DAYS)


def india_today() -> date:
    return datetime.now(IST).date()


def parse_navall(text: str, today: Optional[date] = None) -> Parsed:
    """Parse NAVAll.txt (also the layout of the history download, minus the history-only columns). Never raises on a bad line: it is counted in `skipped`.
    Schemes without a usable NAV are still listed (nav None). A line is left out only when it has no scheme code or the wrong number of fields."""
    out = Parsed()
    limit = latest_allowed(today)
    seen: Dict[int, int] = {}
    kind, category, amc = "", "", ""
    for raw in text.split("\n"):
        out.lines += 1
        line = raw.strip().lstrip("﻿")
        if not line:
            continue
        if line.lower().startswith("scheme code"):
            out.header_ok = True
            continue
        if ";" not in line:
            cat = split_category(line)
            if cat:
                kind, category = cat
            else:
                amc = re.sub(r"\s+", " ", line)
            continue
        f = [x.strip() for x in line.split(";")]
        if len(f) != 8 or not f[0].isdigit():
            out.skip("malformed line")
            continue
        if not (amc and category):
            out.skip("row before a fund house or category line")
            continue
        code, name = int(f[0]), re.sub(r"\s+", " ", f[3])
        if not name:
            out.skip("no scheme name")
            continue
        nav, nav_date = parse_nav(f[6]), parse_date(f[7])
        if nav_date is not None and nav_date > limit:
            out.skip("NAV dated in the future")
            nav, nav_date = None, None
        if nav is None:
            out.skip("no usable NAV (N.A., dash, blank or zero)")
        if nav is not None and nav_date is None:
            out.skip("NAV with an unreadable date")
            nav = None
        plan = clean_plan(f[4], name)
        opt, label = clean_option(f[5], name)
        isin = f[1] if ISIN_RE.match(f[1]) else None
        isin2 = f[2] if ISIN_RE.match(f[2]) else None
        s = Scheme(code, name, amc, category, kind or "Open Ended", plan, opt, label, f"{amc_key(amc)}|{category}|{family_stem(name)}", isin, isin2,
                   nav, nav_date if nav is not None else None)
        if code in seen:
            out.skip("repeated scheme code (last line kept)")
            out.schemes[seen[code]] = s
        else:
            seen[code] = len(out.schemes)
            out.schemes.append(s)
    return out


def category_group(category: str) -> str:
    """'Equity Scheme - Mid Cap Fund' -> 'Equity Scheme' (the part before the first ' - ')."""
    return category.split(" - ")[0].strip() if " - " in category else category


# ====================================================================================== packed NAV series

def pack_series(days: Sequence[int], navs: Sequence[float]) -> bytes:
    """Ascending, unique day numbers (date ordinals) and NAVs -> zlib(count, day gaps as uint16, NAV changes as int64 in 1e-8 units). About 3 bytes a point."""
    gaps = array.array("H")
    steps = array.array("q")
    prev_day, prev = days[0], 0
    for d, v in zip(days, navs):
        gaps.append(d - prev_day)
        prev_day = d
        x = round(v * SCALE)
        steps.append(x - prev)
        prev = x
    if sys.byteorder == "big":   # stored little-endian everywhere
        gaps.byteswap()
        steps.byteswap()
    return zlib.compress(len(days).to_bytes(4, "little") + gaps.tobytes() + steps.tobytes(), 9)


def unpack_series(blob: bytes, first_day: int) -> Tuple[List[int], List[float]]:
    raw = zlib.decompress(blob)
    n = int.from_bytes(raw[:4], "little")
    gaps, steps = array.array("H"), array.array("q")
    gaps.frombytes(raw[4:4 + 2 * n])
    steps.frombytes(raw[4 + 2 * n:4 + 10 * n])
    if sys.byteorder == "big":
        gaps.byteswap()
        steps.byteswap()
    days, navs, d, x = [], [], first_day, 0
    for g, s in zip(gaps, steps):
        d += g
        x += s
        days.append(d)
        navs.append(x / SCALE)
    return days, navs


# ====================================================================================== returns, volatility, drawdown

HORIZONS = (("1m", 1, "1 month"), ("6m", 6, "6 months"), ("1y", 12, "1 year"), ("3y", 36, "3 years"), ("5y", 60, "5 years"))


def shift_months(d: date, months: int) -> date:
    """The date `months` earlier (day clamped to the month's end: 31 Mar minus one month is 28/29 Feb)."""
    y, m = divmod(d.year * 12 + d.month - 1 - months, 12)
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _fmt(d: date) -> str:
    return f"{d.day} {d.strftime('%b %Y')}"


def trailing_returns(days: List[int], navs: List[float], complete: bool) -> Dict[str, dict]:
    """Point-to-point returns to the last NAV, in percent. Start NAV = the latest NAV on or before the start date (one month, six months... earlier).
    Up to one year: (end / start - 1). Beyond one year: annualised, (end / start) ** (365 / days between the two NAV dates) - 1.
    A figure is None, with the reason, when the history does not reach back far enough or has a hole at the start date."""
    out: Dict[str, dict] = {}
    if not days:
        return {k: {"value": None, "kind": "cagr" if m > 12 else "absolute", "from": None, "why": "No NAV history is loaded for this scheme."} for k, m, _ in HORIZONS}
    end_day, end_nav = days[-1], navs[-1]
    end = date.fromordinal(end_day)
    for key, months, label in HORIZONS:
        kind = "cagr" if months > 12 else "absolute"
        target = shift_months(end, months).toordinal()
        i = bisect_right(days, target) - 1
        if i < 0:
            first = date.fromordinal(days[0])
            why = f"Younger than {label}: the first NAV on file is dated {_fmt(first)}." if complete else f"NAV history before {_fmt(first)} is not loaded yet."
            out[key] = {"value": None, "kind": kind, "from": None, "why": why}
        elif target - days[i] > MAX_STALE:
            out[key] = {"value": None, "kind": kind, "from": None, "why": f"No NAV within {MAX_STALE} days before the start date."}
        else:
            span = end_day - days[i]
            ratio = end_nav / navs[i]
            val = (ratio ** (365.0 / span) - 1) * 100 if kind == "cagr" and span > 0 else (ratio - 1) * 100
            out[key] = {"value": val, "kind": kind, "from": date.fromordinal(days[i]), "why": None}
    return out


def volatility(days: List[int], navs: List[float], years: int, complete: bool) -> dict:
    """Annualised volatility: standard deviation (sample) of daily NAV changes over the last `years`, times the square root of 252.
    Saturday and Sunday NAVs (some debt funds publish them) are left out so every fund is measured per trading day; a holiday gap counts as one day."""
    if not days:
        return {"value": None, "why": "No NAV history is loaded for this scheme."}
    end = date.fromordinal(days[-1])
    target = shift_months(end, 12 * years).toordinal()
    i = bisect_right(days, target) - 1
    if i < 0:
        first = date.fromordinal(days[0])
        return {"value": None, "why": f"Younger than {years} year{'s' if years > 1 else ''}: the first NAV on file is dated {_fmt(first)}." if complete
                else f"NAV history before {_fmt(first)} is not loaded yet."}
    pts = [(days[j], navs[j]) for j in range(i, len(days)) if date.fromordinal(days[j]).weekday() < 5]
    rets = [b[1] / a[1] - 1 for a, b in zip(pts, pts[1:])]
    if len(rets) < 0.8 * 252 * years:
        return {"value": None, "why": "Too few NAVs in the period to measure it."}
    return {"value": statistics.stdev(rets) * math.sqrt(252) * 100, "why": None}


def max_drawdown(days: List[int], navs: List[float]) -> dict:
    """Largest fall from a NAV high to a later low over the stored history (up to about five years), in percent (0 or negative)."""
    if len(days) < 30:
        return {"value": None, "why": "Too few NAVs to measure it."}
    peak_i, worst, w_peak, w_low = 0, 0.0, 0, 0
    for i, v in enumerate(navs):
        if v > navs[peak_i]:
            peak_i = i
        dd = v / navs[peak_i] - 1
        if dd < worst:
            worst, w_peak, w_low = dd, peak_i, i
    return {"value": worst * 100, "why": None, "peak": date.fromordinal(days[w_peak]), "trough": date.fromordinal(days[w_low]), "since": date.fromordinal(days[0])}


def metrics_for(days: List[int], navs: List[float], complete: bool) -> dict:
    out = {"returns": trailing_returns(days, navs, complete), "vol1y": volatility(days, navs, 1, complete), "vol3y": volatility(days, navs, 3, complete),
           "mdd": max_drawdown(days, navs)}
    md, mv = month_ends(days, navs)
    out["dash"] = dashboard_figures(md, mv, days[-1], navs[-1]) if days else (None, None, None)
    return out


def metric_columns(m: dict) -> Tuple[Optional[float], ...]:
    r = m["returns"]
    return (r["1m"]["value"], r["6m"]["value"], r["1y"]["value"], r["3y"]["value"], r["5y"]["value"], m["vol1y"]["value"], m["vol3y"]["value"], m["mdd"]["value"])


# ====================================================================================== SIP returns, from month-end NAVs
#
# A monthly SIP is worked out the same way for every scheme, from ONE NAV a month: the last NAV of each calendar month ("month-end NAV").
#   instalments  one equal amount on the month-end NAV day of each of the 36 (60) calendar months BEFORE the month of the latest NAV; each buys
#                amount / NAV units. A month whose last NAV is more than MAX_STALE days before the month's last day counts as missing.
#   value        all the units at the latest NAV, on the latest NAV's day.
#   return       the yearly rate (XIRR) that makes the instalments grow into that value: sum(flow / (1 + r) ** (days from the first flow / 365)) = 0.
# No figure when any instalment month is missing (a younger scheme, a hole in the history). The figure is a rate per year, not a total.

MONTHLY_KEEP = 63            # month-end NAVs kept per scheme: 60 instalment months, the current month and a spare
SIP_MONTHS = (36, 60)
FALL_MONTHS = 36             # the month-end fall is measured over the last 3 years, so funds of different ages are measured alike
FALL_MAX_HOLES = 3


def month_key(day: int) -> int:
    """Day number (date ordinal) -> month number (year * 12 + month - 1)."""
    d = date.fromordinal(day)
    return d.year * 12 + d.month - 1


def month_last_day(mk: int) -> int:
    y, m = divmod(mk, 12)
    return date(y, m + 1, calendar.monthrange(y, m + 1)[1]).toordinal()


def month_ends(days: Sequence[int], navs: Sequence[float]) -> Tuple[List[int], List[float]]:
    """Ascending daily (days, NAVs) -> the last NAV of each calendar month (the current month's latest NAV included)."""
    od: List[int] = []
    ov: List[float] = []
    for d, v in zip(days, navs):
        if od and month_key(od[-1]) == month_key(d):
            od[-1], ov[-1] = d, v
        else:
            od.append(d)
            ov.append(v)
    return od, ov


def merge_months(*parts: Tuple[Sequence[int], Sequence[float]], keep: int = MONTHLY_KEEP) -> Tuple[List[int], List[float]]:
    """Several (days, NAVs) pieces -> one month-end series: per calendar month the NAV of the LATEST day seen; the newest `keep` months."""
    by: Dict[int, Tuple[int, float]] = {}
    for days, navs in parts:
        for d, v in zip(days, navs):
            k = month_key(d)
            if k not in by or d >= by[k][0]:
                by[k] = (d, v)
    ks = sorted(by)[-keep:]
    return [by[k][0] for k in ks], [by[k][1] for k in ks]


def xirr(flows: Sequence[Tuple[int, float]]) -> Optional[float]:
    """Yearly rate r (a fraction) that sets the present value of dated cash flows to zero, as a spreadsheet's XIRR does: sum(a / (1 + r) ** (t / 365)),
    t = days since the first flow. Newton's method, then bisection when it does not settle. None without both a payment and a receipt, or without a root."""
    if not flows:
        return None
    t0 = min(d for d, _ in flows)
    ts = [(d - t0) / 365.0 for d, _ in flows]
    amts = [a for _, a in flows]
    if not (any(a < 0 for a in amts) and any(a > 0 for a in amts)):
        return None

    def npv(r: float) -> float:
        return sum(a * (1.0 + r) ** -t for a, t in zip(amts, ts))

    r = 0.1
    for _ in range(60):
        try:
            y = npv(r)
            dy = sum(-t * a * (1.0 + r) ** (-t - 1.0) for a, t in zip(amts, ts))
        except (OverflowError, ZeroDivisionError):
            break
        if dy == 0 or not math.isfinite(y) or not math.isfinite(dy):
            break
        nr = r - y / dy
        if nr <= -1.0 or not math.isfinite(nr):
            break
        if abs(nr - r) < 1e-12:
            return nr
        r = nr
    lo, hi = -0.999999, 1.0
    try:
        flo, fhi = npv(lo), npv(hi)
        while flo * fhi > 0 and hi < 1e6:
            hi *= 4
            fhi = npv(hi)
    except (OverflowError, ZeroDivisionError):
        return None
    if flo * fhi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        fm = npv(mid)
        if fm == 0 or hi - lo < 1e-13:
            return mid
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return (lo + hi) / 2


def sip_return(mdays: Sequence[int], mnavs: Sequence[float], end_day: int, end_nav: Optional[float], months: int) -> Optional[float]:
    """XIRR in percent a year of a monthly SIP of equal amounts over `months` months (see the rules above), or None when an instalment month is missing."""
    if not mdays or end_nav is None or end_nav <= 0:
        return None
    end_mk = month_key(end_day)
    by = {month_key(d): (d, v) for d, v in zip(mdays, mnavs)}
    flows: List[Tuple[int, float]] = []
    units = 0.0
    for mk in range(end_mk - months, end_mk):
        p = by.get(mk)
        if p is None or p[1] <= 0 or p[0] < month_last_day(mk) - MAX_STALE or p[0] >= end_day:
            return None
        units += 1.0 / p[1]
        flows.append((p[0], -1.0))
    flows.append((end_day, units * end_nav))
    r = xirr(flows)
    return None if r is None else r * 100


def fall_monthly(mdays: Sequence[int], mnavs: Sequence[float], end_day: int, end_nav: Optional[float], months: int = FALL_MONTHS) -> Optional[float]:
    """Largest fall (percent, 0 or negative) from a month-end NAV to a later month-end NAV (or the latest NAV) over the last `months` months.
    Needs the month-end of the first month and at most FALL_MAX_HOLES missing months, else None."""
    if end_nav is None or end_nav <= 0:
        return None
    end_mk = month_key(end_day)
    pts = [(month_key(d), v) for d, v in zip(mdays, mnavs) if end_mk - months <= month_key(d) < end_mk and v > 0]
    if not pts or pts[0][0] != end_mk - months or len(pts) < months - FALL_MAX_HOLES:
        return None
    peak, worst = pts[0][1], 0.0
    for v in [p[1] for p in pts] + [end_nav]:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst * 100


def dashboard_figures(mdays: Sequence[int], mnavs: Sequence[float], end_day: int, end_nav: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """(SIP 3 years, SIP 5 years, month-end fall over 3 years) for one scheme."""
    return (sip_return(mdays, mnavs, end_day, end_nav, SIP_MONTHS[0]), sip_return(mdays, mnavs, end_day, end_nav, SIP_MONTHS[1]),
            fall_monthly(mdays, mnavs, end_day, end_nav))


def trim(days: List[int], navs: List[float]) -> Tuple[List[int], List[float]]:
    cut = bisect_right(days, days[-1] - KEEP_DAYS)
    return (days[cut:], navs[cut:]) if cut else (days, navs)


def thin(days: List[int], navs: List[float], cap: int) -> Tuple[List[int], List[float]]:
    """At most `cap` points for a chart, always keeping the first and the last (every n-th NAV counting back from the last)."""
    n = len(days)
    if n <= cap:
        return days, navs
    step = math.ceil((n - 1) / (cap - 1))
    idx = sorted(set(range(n - 1, -1, -step)) | {0})
    return [days[i] for i in idx], [navs[i] for i in idx]


# ====================================================================================== tolerant search

def tokens(s: str) -> List[str]:
    return [t for t in re.split(r"[^a-z0-9]+", unicodedata.normalize("NFKD", s).lower()) if t]


def within(a: str, b: str, k: int) -> bool:
    """a and b differ by at most k edits (insert, delete, replace, swap of neighbours)."""
    if abs(len(a) - len(b)) > k:
        return False
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1] and prev2 is not None:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > k:
            return False
        prev2, prev = prev, cur
    return prev[-1] <= k


class SearchIndex:
    """Names and fund houses in memory (about 14,000 short strings) for typo- and space-tolerant search: 'hdfc mid cap', 'hdfcmidcap' and 'hdfc midcp' find HDFC Mid Cap."""

    def __init__(self, rows: Iterable[Tuple[int, str, str]]):
        self.codes: List[int] = []
        self.names: List[str] = []
        self.toks: List[List[str]] = []
        self.compact: List[str] = []
        vocab = set()
        for code, name, amc in rows:
            t = tokens(f"{name} {amc}")
            self.codes.append(code)
            self.names.append(name)
            self.toks.append(t)
            self.compact.append("".join(t))
            vocab.update(w for w in t if len(w) >= 4)
        self.vocab = sorted(vocab)
        self._near: Dict[str, List[str]] = {}

    def near(self, word: str) -> List[str]:
        if word not in self._near:
            k = 1 if len(word) <= 6 else 2
            self._near[word] = [v for v in self.vocab if abs(len(v) - len(word)) <= k and within(word, v, k)][:40]
        return self._near[word]

    def search(self, query: str, limit: int = 5000) -> Optional[List[int]]:
        """Scheme codes best match first, or None when the query has no letters or digits (then there is nothing to search for).
        Every word of the query must match: as a whole word (best), the start of a word, or anywhere in the name with spaces ignored; a word that
        matches nothing anywhere is also tried as the nearest real words (one or two typos)."""
        qt = tokens(query)
        if not qt:
            return None
        qc = "".join(qt)
        alts: List[List[Tuple[str, float]]] = []
        for t in qt:
            a = [(t, 1.0)]
            if len(t) >= 4 and not any(t in c for c in self.compact):
                a += [(w, 0.8) for w in self.near(t)]
            alts.append(a)
        scored: List[Tuple[float, int, str, int]] = []
        for i, cn in enumerate(self.compact):
            tn = self.toks[i]
            total = 0.0
            for a in alts:
                best = 0.0
                for w, mult in a:
                    if w in tn:
                        s = 3.0
                    elif any(x.startswith(w) for x in tn):
                        s = 2.5
                    elif w in cn:
                        s = 1.5
                    else:
                        continue
                    best = max(best, s * mult)
                if not best:
                    total = 0.0
                    break
                total += best
            if total:
                if qc in cn:   # the whole query, spaces ignored: 'midcap' against 'Mid Cap'
                    total += 2 + (1 if cn.startswith(qc) else 0)
                scored.append((-total, len(self.names[i]), self.names[i], self.codes[i]))
        scored.sort()
        return [s[3] for s in scored[:limit]]


# ====================================================================================== downloading AMFI's files

def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=30.0), follow_redirects=True, headers={"User-Agent": USER_AGENT})


async def _retry(fn, tries: int = 3, base: float = 3.0):
    """Run an async download, retrying transient failures (timeouts, resets, 5xx) with growing waits; the last error is raised."""
    for n in range(tries):
        try:
            return await fn()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            if n == tries - 1:
                raise
            log.warning("AMFI download failed (%s); retrying", exc.__class__.__name__)
            await asyncio.sleep(base * (n + 1))


async def fetch_navall(client: httpx.AsyncClient) -> str:
    async def go():
        r = await client.get(NAVALL_URL)
        r.raise_for_status()
        return r.content.decode("utf-8", "replace")
    return await _retry(go)


async def fetch_history(client: httpx.AsyncClient, frm: date, to: date, amc_id: Optional[int], wanted: set) -> Optional[Tuple[Dict[int, Tuple[array.array, array.array]], dict]]:
    """AMFI's NAV history for one fund house (or, without amc_id, every fund house) between two dates, read as a stream. Keeps only the `wanted` scheme codes.
    Returns ({code: (day numbers, NAVs)}, stats), or None when AMFI answers with its web form instead of data (no records for that selection)."""
    params = {"frmdt": f"{frm.day:02d}-{frm.strftime('%b')}-{frm.year}", "todt": f"{to.day:02d}-{to.strftime('%b')}-{to.year}"}
    if amc_id is not None:
        params["mf"] = str(amc_id)

    async def go():
        series: Dict[int, Tuple[array.array, array.array]] = {}
        stats = {"rows": 0, "kept": 0, "bytes": 0, "badRows": 0}
        async with client.stream("GET", HISTORY_URL, params=params) as r:
            r.raise_for_status()
            first = True
            async for raw in r.aiter_lines():
                line = raw.strip()
                if not line:
                    continue
                if first:
                    first = False
                    if not line.lower().startswith("scheme code"):
                        return None
                    continue
                if ";" not in line:
                    continue
                f = line.split(";")
                stats["rows"] += 1
                if len(f) < 8 or not f[0].isdigit():
                    stats["badRows"] += 1
                    continue
                code = int(f[0])
                if code not in wanted:
                    continue
                nav, d = parse_nav(f[6]), parse_date(f[7])
                if nav is None or d is None:
                    stats["badRows"] += 1
                    continue
                pair = series.get(code)
                if pair is None:
                    pair = series[code] = (array.array("l"), array.array("d"))
                pair[0].append(d.toordinal())
                pair[1].append(nav)
                stats["kept"] += 1
            stats["bytes"] = r.num_bytes_downloaded
        return series, stats
    return await _retry(go)


def merge_points(*parts: Tuple[Sequence[int], Sequence[float]]) -> Tuple[List[int], List[float]]:
    """Several (days, NAVs) pieces into one ascending series, one NAV a day (a later piece wins for a repeated day)."""
    by_day: Dict[int, float] = {}
    for days, navs in parts:
        for d, v in zip(days, navs):
            by_day[d] = v
    ds = sorted(by_day)
    return ds, [by_day[d] for d in ds]


# ====================================================================================== the nightly refresh

HIST_WANTED = "active AND option_class = 'Growth' AND nav IS NOT NULL"


def verdict(parsed: Parsed, stored: int, stored_newest: Optional[date], stored_active: int) -> Optional[str]:
    """Why a freshly downloaded file must NOT be applied, or None when it looks complete. Nothing stored is touched on a refusal."""
    n = len(parsed.schemes)
    if not parsed.header_ok:
        return "the file does not start with AMFI's column header (not the NAV file)"
    if n == 0:
        return "no scheme rows could be read"
    bad = sum(v for k, v in parsed.skipped.items() if k in ("malformed line", "row before a fund house or category line", "no scheme name"))
    if bad > 0.02 * parsed.lines:
        return f"{bad} of {parsed.lines} lines could not be read (more than 2%)"
    newest = parsed.newest
    if newest is None:
        return "no scheme has a readable NAV date"
    if stored and n < MIN_KEEP_RATIO * stored:
        return f"the file lists {n} schemes but {stored} are stored (less than {int(MIN_KEEP_RATIO * 100)}%)"
    if stored_newest and newest < stored_newest:
        return f"the newest NAV date in the file ({newest}) is older than the one stored ({stored_newest})"
    if stored_active:
        active = sum(1 for s in parsed.schemes if s.nav_date and (newest - s.nav_date).days <= ACTIVE_DAYS)
        if active < MIN_KEEP_RATIO * stored_active:
            return f"only {active} schemes have a current NAV but {stored_active} had one before (less than {int(MIN_KEEP_RATIO * 100)}%)"
    return None


UPSERT = """
INSERT INTO mf_schemes (code, name, isin, isin_reinvest, amc, scheme_type, category, plan, option_class, option_label, family, nav, nav_date, last_seen)
SELECT * FROM unnest($1::int[], $2::text[], $3::text[], $4::text[], $5::text[], $6::text[], $7::text[], $8::text[], $9::text[], $10::text[], $11::text[],
                     $12::float8[], $13::date[], $14::date[])
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name, isin = EXCLUDED.isin, isin_reinvest = EXCLUDED.isin_reinvest, amc = EXCLUDED.amc, scheme_type = EXCLUDED.scheme_type,
    category = EXCLUDED.category, plan = EXCLUDED.plan, option_class = EXCLUDED.option_class, option_label = EXCLUDED.option_label, family = EXCLUDED.family,
    prev_nav  = CASE WHEN EXCLUDED.nav IS NOT NULL AND mf_schemes.nav_date IS NOT NULL AND EXCLUDED.nav_date > mf_schemes.nav_date THEN mf_schemes.nav ELSE mf_schemes.prev_nav END,
    prev_date = CASE WHEN EXCLUDED.nav IS NOT NULL AND mf_schemes.nav_date IS NOT NULL AND EXCLUDED.nav_date > mf_schemes.nav_date THEN mf_schemes.nav_date ELSE mf_schemes.prev_date END,
    nav       = CASE WHEN EXCLUDED.nav IS NULL THEN mf_schemes.nav WHEN mf_schemes.nav_date IS NULL OR EXCLUDED.nav_date >= mf_schemes.nav_date THEN EXCLUDED.nav ELSE mf_schemes.nav END,
    nav_date  = CASE WHEN EXCLUDED.nav IS NULL THEN mf_schemes.nav_date WHEN mf_schemes.nav_date IS NULL OR EXCLUDED.nav_date >= mf_schemes.nav_date THEN EXCLUDED.nav_date ELSE mf_schemes.nav_date END,
    last_seen = EXCLUDED.last_seen, updated_at = now()
"""
HIST_UPSERT = """
INSERT INTO mf_history (code, n, d0, d1, blob, complete, source, updated_at) VALUES ($1, $2, $3, $4, $5, $6, $7, now())
ON CONFLICT (code) DO UPDATE SET n = EXCLUDED.n, d0 = EXCLUDED.d0, d1 = EXCLUDED.d1, blob = EXCLUDED.blob, complete = EXCLUDED.complete, source = EXCLUDED.source, updated_at = now()
"""
METRICS_UPDATE = """UPDATE mf_schemes SET has_hist = true, r1m = $2, r6m = $3, r1y = $4, r3y = $5, r5y = $6, vol1y = $7, vol3y = $8, mdd = $9, metrics_date = $10,
    prev_nav = CASE WHEN nav_date = $10 AND $11::float8 IS NOT NULL THEN $11 ELSE prev_nav END,
    prev_date = CASE WHEN nav_date = $10 AND $11::float8 IS NOT NULL THEN $12 ELSE prev_date END,
    sip3y = $13, sip5y = $14, mdd3y_m = $15 WHERE code = $1"""
MONTHLY_UPSERT = """INSERT INTO mf_monthly (code, days, navs, updated_at) VALUES ($1, $2::date[], $3::float8[], now())
    ON CONFLICT (code) DO UPDATE SET days = EXCLUDED.days, navs = EXCLUDED.navs, updated_at = now()"""


async def _write_series(conn, items: List[Tuple[int, List[int], List[float], bool]]) -> None:
    """Store packed series and their worked-out numbers for (code, days, NAVs, complete) items; their month-end NAVs go to mf_monthly too, so the SIP
    figures stay right when a scheme later leaves the hot set and its daily series is dropped."""
    hist, mets, months = [], [], {}
    for code, days, navs, complete in items:
        days, navs = trim(days, navs)
        hist.append((code, len(days), date.fromordinal(days[0]), date.fromordinal(days[-1]), pack_series(days, navs), complete, "amfi"))
        prev = (navs[-2], date.fromordinal(days[-2])) if len(days) > 1 else (None, None)   # the NAV before the last one gives the day change
        m = metrics_for(days, navs, complete)
        mets.append((code, *metric_columns(m), date.fromordinal(days[-1]), *prev, *m["dash"]))
        months[code] = month_ends(days, navs)
    await conn.executemany(HIST_UPSERT, hist)
    await conn.executemany(METRICS_UPDATE, mets)
    if months:
        old = {r["code"]: ([d.toordinal() for d in r["days"]], list(r["navs"]))
               for r in await conn.fetch("SELECT code, days, navs FROM mf_monthly WHERE code = ANY($1::int[])", list(months))}
        rows = []
        for code, piece in months.items():
            d, v = merge_months(old.get(code, ([], [])), piece)
            rows.append((code, [date.fromordinal(x) for x in d], v))
        await conn.executemany(MONTHLY_UPSERT, rows)


async def _meta(conn, key: str) -> Optional[dict]:
    raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def _set_meta(conn, key: str, value: dict) -> None:
    await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                       key, json.dumps(value, default=str))


async def record_run(store, cmd: str, info: dict) -> None:
    """One line per boot or nightly step (what ran, how it ended), readable at /api/mf/status: the host's logs are not reachable from outside."""
    try:
        async with store.pool.acquire() as conn:
            await _set_meta(conn, "run:" + cmd, {**info, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    except Exception:
        log.warning("could not record the %s result", cmd)


async def last_run_age_hours(store, cmd: str):
    """(hours since the step last ran, its status) from record_run, or (None, None) when it never ran."""
    try:
        async with store.pool.acquire() as conn:
            v = await _meta(conn, "run:" + cmd)
        at = datetime.fromisoformat(v["at"]) if v else None
        return ((datetime.now(timezone.utc) - at).total_seconds() / 3600, v.get("status")) if at else (None, None)
    except Exception:
        return None, None


async def _bump(store, newest: Optional[date]) -> None:
    """New data version: cached list and detail pages built from older data stop being served (their keys include the version)."""
    try:
        await store.redis.set("mf:ver", f"{newest}-{int(time.time())}")
    except Exception:
        log.warning("could not publish the mf data version to Redis")


async def refresh(store, settings=None, backfill_amc: Optional[str] = None, *, client: Optional[httpx.AsyncClient] = None) -> dict:
    """Nightly job (`python -m finlit.worker refresh-mf`, 21:10 IST): one download of NAVAll.txt, then a small write.

    1. The file is checked first (verdict): not AMFI's file, no rows, far fewer schemes than stored, or older than what is stored -> REFUSED, nothing changes.
    2. Every scheme's name, category and latest NAV are upserted (a missing or 'N.A.' NAV never overwrites a stored one; nothing is deleted).
    3. Today's NAV is appended to each stored history (the hot schemes') and their returns / volatility / drawdown are worked out again.
    4. If whole days were missed (the job did not run), AMFI's industry-wide history for just those days fills the hole.
    5. Every other Growth scheme gets its 1, 3 and 5 year returns worked out again from AMFI's history for just the three start dates (`refresh_anchors`).
    6. Month-end NAVs: today's NAV is folded into every Growth scheme's month-end series, month-ends not read yet come from AMFI's history (a few each
       run until five years are filled), and the SIP returns and month-end fall are worked out again (`refresh_monthly`).
    7. Fund size, expense ratio and the checklist are copied / worked out for the category table (`derive_dashboard`).
    8. The hot set is chosen and its pages are rebuilt (`refresh_hot`); the stored series of everything else is dropped.
    Fund houses on config.MF_EXCLUDED_AMCS are never loaded; their rows, if any, are deleted first (`prune_excluded`, idempotent).
    `backfill_amc` (an AMC id, name or 'all') additionally loads five years of history for those fund houses: see `backfill`."""
    started = time.perf_counter()
    own = client is None
    client = client or make_client()
    try:
        text = await fetch_navall(client)
        parsed = parse_navall(text)
        pruned = await prune_excluded(store)   # rows of unlisted fund houses are removed first, so the checks below compare like with like
        dropped = drop_excluded(parsed)
        async with store.pool.acquire() as conn:
            # a NAV stored with a future date (a typo in an earlier file) is forgotten, so it can neither block this file nor outrank today's NAV
            res_fix = await conn.execute("UPDATE mf_schemes SET nav_date = NULL WHERE nav_date > $1", latest_allowed())
            future_fixed = int(res_fix.split()[-1])
            if future_fixed:
                log.warning("mf refresh: %d stored NAV dates were in the future and were cleared", future_fixed)
            stored = await conn.fetchrow("SELECT count(*) AS n, max(nav_date) AS newest, count(*) FILTER (WHERE active) AS act FROM mf_schemes")
            why = verdict(parsed, stored["n"], stored["newest"], stored["act"])
        if why:
            log.error("mf refresh refused: %s", why)
            return {"status": "refused", "reason": why, "parsed": len(parsed.schemes), "stored": stored["n"], "skipped": parsed.skipped}
        newest = parsed.newest
        res = await apply_navall(store, parsed, newest)
        res["futureDatesCleared"] = future_fixed
        res["excludedSchemesSkipped"], res["excludedRowsPruned"] = dropped, pruned
        res["gapDays"] = await _repair_gaps(store, client, res.pop("_gap_since", None), newest)
        if backfill_amc:
            res["backfill"] = await backfill(store, settings, amc=backfill_amc, client=client)
        res["anchors"] = await refresh_anchors(store, client, newest)
        res["monthly"] = await _guarded("monthly", refresh_monthly(store, client, newest))
        res["dashboard"] = await _guarded("dashboard", derive_dashboard(store))
        res["hot"] = await refresh_hot(store, client)
        await _bump(store, newest)
        res["seconds"] = round(time.perf_counter() - started, 1)
        return res
    finally:
        if own:
            await client.aclose()


async def apply_navall(store, parsed: Parsed, newest: date) -> dict:
    """Write an accepted file (see refresh). Everything is one transaction: a failure leaves the previous data exactly as it was."""
    drop_excluded(parsed)   # normally done by refresh already; a direct call must not store them either
    ss = parsed.schemes
    cols = list(zip(*[(s.code, s.name, s.isin, s.isin_reinvest, s.amc, s.scheme_type, s.category, s.plan, s.option_class, s.option_label, s.family, s.nav, s.nav_date, newest)
                      for s in ss]))
    appended = 0
    gap_since: Optional[date] = None
    async with store.pool.acquire() as conn, conn.transaction():
        before = await conn.fetchval("SELECT count(*) FROM mf_schemes")
        prev_meta = await _meta(conn, "refresh") or {}
        await conn.execute(UPSERT, *[list(c) for c in cols])
        await conn.execute("UPDATE mf_schemes SET active = (nav_date IS NOT NULL AND nav_date >= $1::date - $2::int)", newest, ACTIVE_DAYS)
        # Schemes whose newest NAV is later than the last stored day of their history (only the hot ones have a history): append it. A scheme with no
        # stored history gets its 1 and 5 year figures from refresh_anchors instead.
        rows = await conn.fetch("""SELECT s.code, s.amc, s.nav, s.nav_date, h.blob, h.d0, h.d1, h.complete FROM mf_schemes s JOIN mf_history h USING (code)
                                   WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.nav_date > h.d1""")
        items = []
        for r in rows:
            nd = r["nav_date"].toordinal()
            days, navs = unpack_series(bytes(r["blob"]), r["d0"].toordinal())
            if days[-1] == nd and navs[-1] == r["nav"]:
                continue
            if nd - days[-1] > 4 and (newest.toordinal() - nd) <= ACTIVE_DAYS:
                gap_since = min(gap_since or r["d1"], r["d1"])
            days, navs = merge_points((days, navs), ([nd], [r["nav"]]))
            items.append((r["code"], days, navs, bool(r["complete"])))
            appended += 1
            if len(items) >= 300:   # written in batches: holding every series as Python lists at once needs hundreds of MB
                await _write_series(conn, items)
                items = []
        if items:
            await _write_series(conn, items)
        # Whole days were missed only when the previous run's newest date is itself more than 4 days old: then many schemes show the same hole.
        prev_newest = date.fromisoformat(prev_meta["navDate"]) if prev_meta.get("navDate") else None
        if not (prev_newest and (newest - prev_newest).days > 4):
            gap_since = None
        active = await conn.fetchval("SELECT count(*) FROM mf_schemes WHERE active")
        total = await conn.fetchval("SELECT count(*) FROM mf_schemes")
        with_hist = await conn.fetchval("SELECT count(*) FROM mf_history")
        res = {"status": "ok", "navDate": newest.isoformat(), "schemesInFile": len(ss), "schemesStored": total, "newSchemes": total - before, "active": active,
               "withHistory": with_hist, "historyAppended": appended, "skipped": parsed.skipped,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "_gap_since": gap_since}
        await _set_meta(conn, "refresh", {k: v for k, v in res.items() if not k.startswith("_")})
    return res


async def _repair_gaps(store, client, since: Optional[date], newest: date) -> int:
    """Fill NAV days a missed run left out, from AMFI's history for every fund house, 20 days at a time (about 15 MB each). Returns the days covered."""
    if since is None:
        return 0
    start, covered = since + timedelta(days=1), 0
    async with store.pool.acquire() as conn:
        wanted = {r["code"] for r in await conn.fetch(f"SELECT code FROM mf_schemes WHERE {HIST_WANTED} AND code IN (SELECT code FROM mf_history)")}  # nosec B608 - fixed column list and constant filter, no input
    pieces: Dict[int, List[Tuple[array.array, array.array]]] = {}
    while start <= newest and covered < 120:
        end = min(newest, start + timedelta(days=19))
        got = await fetch_history(client, start, end, None, wanted)
        if got:
            for code, pair in got[0].items():
                pieces.setdefault(code, []).append(pair)
        covered += (end - start).days + 1
        start = end + timedelta(days=1)
    if not pieces:
        return 0
    async with store.pool.acquire() as conn, conn.transaction():
        rows = await conn.fetch("SELECT code, blob, d0, complete FROM mf_history WHERE code = ANY($1::int[])", list(pieces))
        items = []
        for r in rows:
            days, navs = unpack_series(bytes(r["blob"]), r["d0"].toordinal())
            days, navs = merge_points((days, navs), *pieces[r["code"]])
            items.append((r["code"], days, navs, bool(r["complete"])))
        for i in range(0, len(items), 300):
            await _write_series(conn, items[i:i + 300])
    return covered


async def rebuild(store, batch: int = 300) -> int:
    """Work out every stored scheme's returns, volatility, drawdown and day change again from its stored series (no download). Run after the maths changes."""
    n = 0
    async with store.pool.acquire() as conn:
        codes = [r["code"] for r in await conn.fetch("SELECT code FROM mf_history ORDER BY code")]
    for i in range(0, len(codes), batch):
        async with store.pool.acquire() as conn, conn.transaction():
            items = []
            for r in await conn.fetch("SELECT code, blob, d0, complete FROM mf_history WHERE code = ANY($1::int[])", codes[i:i + batch]):
                days, navs = unpack_series(bytes(r["blob"]), r["d0"].toordinal())
                items.append((r["code"], days, navs, bool(r["complete"])))
            await _write_series(conn, items)
            n += len(items)
    # every other scheme's SIP figures from its stored month-end NAVs (no download), then fund size, expense ratio and the checklist
    async with store.pool.acquire() as conn:
        newest = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes")
    if newest:
        await refresh_monthly(store, None, newest)
    await derive_dashboard(store)
    await _bump(store, None)
    return n


# ====================================================================================== unlisted fund houses

def drop_excluded(parsed: Parsed) -> int:
    """Remove schemes of unlisted fund houses (config.MF_EXCLUDED_AMCS) from a parsed file; returns how many."""
    keep = [s for s in parsed.schemes if not is_excluded_amc(s.amc)]
    n = len(parsed.schemes) - len(keep)
    if n:
        parsed.schemes = keep
        parsed.skipped["scheme of an unlisted fund house"] = n
    return n


async def prune_excluded(store) -> int:
    """Delete what is stored for unlisted fund houses (schemes, their series, hot rows and the backfill record). Idempotent; touches only those houses."""
    async with store.pool.acquire() as conn, conn.transaction():
        gone = [r["amc"] for r in await conn.fetch("SELECT DISTINCT amc FROM mf_schemes") if is_excluded_amc(r["amc"])]
        n = 0
        if gone:
            n = await conn.fetchval("WITH d AS (DELETE FROM mf_schemes WHERE amc = ANY($1::text[]) RETURNING 1) SELECT count(*) FROM d", gone)
        marks = [r["amc_key"] for r in await conn.fetch("SELECT amc_key, amc FROM mf_backfill") if is_excluded_amc(r["amc"])]
        if marks:
            await conn.execute("DELETE FROM mf_backfill WHERE amc_key = ANY($1::text[])", marks)
    return n


# ====================================================================================== 1 year / 5 year figures for schemes without a stored series

async def refresh_anchors(store, client, newest: date) -> dict:
    """Keep the 1, 3 and 5 year returns of every active Growth scheme WITHOUT a stored series current, with three small downloads: AMFI's industry-wide
    history for the days around the 1, 3 and 5 year start dates. The figure is worked out exactly as for a stored series (`trailing_returns`: start NAV =
    the latest on or before the start date, at most MAX_STALE days back; 3 and 5 year = per year). If a download fails, the old figures stay with their
    old date (the 1 and 5 year ones are written together; the 3 year one on its own)."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("""SELECT s.code, s.nav, s.nav_date FROM mf_schemes s WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL
                                   AND NOT EXISTS (SELECT 1 FROM mf_history h WHERE h.code = s.code)""")
    out = {"schemes": len(rows), "updated": 0, "failed": []}
    if not rows:
        return out
    wanted = {r["code"] for r in rows}
    windows: Dict[str, Dict[int, Tuple[array.array, array.array]]] = {}
    for key, months in (("1y", 12), ("3y", 36), ("5y", 60)):
        t = shift_months(newest, months)
        try:
            got = await fetch_history(client, t - timedelta(days=ANCHOR_DAYS), t, None, wanted)
        except Exception as exc:   # a failed download must not stop the rest of the nightly job
            log.warning("mf anchors %s failed: %s", key, exc.__class__.__name__)
            got = None
        if got is None:
            out["failed"].append(key)
        else:
            windows[key] = got[0]
    # The previous NAV (the 1 day change) from AMFI's own history for the last week: the NAV file alone can miss a day when a fund house published late.
    try:
        got = await fetch_history(client, newest - timedelta(days=7), newest, None, wanted)
    except Exception as exc:
        log.warning("mf anchors 1d failed: %s", exc.__class__.__name__)
        got = None
    if got is None:
        out["failed"].append("1d")
    else:
        prevs = []
        for r in rows:
            pair = got[0].get(r["code"])
            before = [(d, v) for d, v in zip(pair[0], pair[1]) if d < r["nav_date"].toordinal()] if pair else []
            if before:
                d, v = max(before)
                prevs.append((r["code"], v, date.fromordinal(d)))
        async with store.pool.acquire() as conn:
            await conn.executemany("UPDATE mf_schemes SET prev_nav = $2, prev_date = $3 WHERE code = $1 AND (prev_date IS NULL OR $3::date >= prev_date)", prevs)
        out["previousNavs"] = len(prevs)
    if "1y" not in windows or "5y" not in windows:
        return out
    has3 = "3y" in windows
    upd = []
    for r in rows:
        end, vals = r["nav_date"].toordinal(), {}
        for key in windows:
            pair = windows[key].get(r["code"])
            days, navs = merge_points(([] if pair is None else pair[0], [] if pair is None else pair[1]), ([end], [r["nav"]]))
            ret = trailing_returns(days, navs, True)[key]
            vals[key] = ret["value"]
        upd.append((r["code"], vals["1y"], vals["5y"], r["nav_date"], vals.get("3y"), has3))
    async with store.pool.acquire() as conn, conn.transaction():
        await conn.executemany("""UPDATE mf_schemes SET r1y = $2, r5y = $3, metrics_date = $4, has_hist = (has_hist OR $2::float8 IS NOT NULL OR $3::float8 IS NOT NULL),
                                  r3y = CASE WHEN $6::boolean THEN $5::float8 ELSE r3y END,
                                  r1m = NULL, r6m = NULL, vol1y = NULL, vol3y = NULL, mdd = NULL WHERE code = $1""", upd)
    out["updated"] = len(upd)
    return out


async def _guarded(step: str, job) -> dict:
    """Run one of the nightly job's later steps; its failure is reported in the result and never stops the steps after it."""
    try:
        return await job
    except Exception as exc:
        log.exception("mf %s step failed", step)
        return {"status": "error", "error": f"{exc.__class__.__name__}: {exc}"[:300]}


# ====================================================================================== month-end NAVs (SIP returns) for every scheme

MONTH_WINDOW_DAYS = 8         # a month-end is read from AMFI's industry-wide history for the month's last 8 days (a month-end NAV may be 7 days early)
MONTH_FILL_SECONDS = 1200     # a run stops starting new month downloads after this long; the rest are read on the next runs
MONTH_FILL_FAILS = 3          # ...and after this many failed downloads in a row (AMFI is down: nothing is hammered)
MONTH_BATCH = 1000


def _same(a: Optional[float], b: Optional[float]) -> bool:
    return (a is None and b is None) or (a is not None and b is not None and abs(a - b) < 1e-9)


async def refresh_monthly(store, client: Optional[httpx.AsyncClient], newest: date, *, max_seconds: float = MONTH_FILL_SECONDS) -> dict:
    """Keep every active Growth scheme's month-end NAVs (mf_monthly) and the figures worked out from them current.
    1. Month-ends not read yet (the 60 months before the newest NAV's month; mf_meta 'monthly' remembers which were read) come from AMFI's industry-wide
       history for each month's last days: one download a month, newest first, at most `max_seconds` a run (the first run after deploy reads all
       five years, about 60 downloads of a few MB; afterwards one a month). No client: nothing is downloaded.
    2. Each scheme's stored month-ends, those downloads and its latest NAV (the current month) are merged (per month, the NAV of the latest day wins).
    3. Schemes without a stored daily series get their SIP 3 / 5 year figures and month-end fall worked out again (the hot ones get them from their
       daily series in _write_series, by the same rules)."""
    out: Dict[str, object] = {"status": "ok", "monthsRead": 0, "monthsFailed": 0, "monthsMissing": 0, "schemes": 0, "seriesWritten": 0, "figuresWritten": 0}
    end_mk = month_key(newest.toordinal())
    want_months = set(range(end_mk - SIP_MONTHS[-1], end_mk))
    async with store.pool.acquire() as conn:
        meta = await _meta(conn, "monthly") or {}
        wanted = {r["code"] for r in await conn.fetch(f"SELECT code FROM mf_schemes WHERE {HIST_WANTED}")}  # nosec B608 - constant filter, no input
    done = {int(m) for m in meta.get("read", []) if int(m) in want_months}
    pieces: Dict[int, Tuple[array.array, array.array]] = {}
    if client is not None and wanted:
        started, fails = time.perf_counter(), 0
        for mk in sorted(want_months - done, reverse=True):
            if time.perf_counter() - started > max_seconds or fails >= MONTH_FILL_FAILS:
                break
            last = month_last_day(mk)
            first = last - (MONTH_WINDOW_DAYS - 1)
            try:
                got = await fetch_history(client, date.fromordinal(first), date.fromordinal(last), None, wanted)
            except Exception as exc:   # a failed month is simply asked again next run
                log.warning("mf month-end %s failed: %s", mk, exc.__class__.__name__)
                got = None
            if got is None:
                fails += 1
                out["monthsFailed"] += 1   # type: ignore[operator]
                continue
            fails = 0
            for code, (ds, vs) in got[0].items():
                best = None
                for d, v in zip(ds, vs):
                    if first <= d <= last and (best is None or d > best[0]):
                        best = (d, v)
                if best:
                    p = pieces.get(code)
                    if p is None:
                        p = pieces[code] = (array.array("l"), array.array("d"))
                    p[0].append(best[0])
                    p[1].append(best[1])
            done.add(mk)
            out["monthsRead"] += 1   # type: ignore[operator]
    out["monthsMissing"] = len(want_months - done)
    after = 0
    while True:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("""SELECT s.code, s.nav, s.nav_date, s.sip3y, s.sip5y, s.mdd3y_m, m.days, m.navs,
                                              EXISTS (SELECT 1 FROM mf_history h WHERE h.code = s.code) AS series
                                       FROM mf_schemes s LEFT JOIN mf_monthly m ON m.code = s.code
                                       WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.code > $1 ORDER BY s.code LIMIT $2""", after, MONTH_BATCH)
        if not rows:
            break
        after = rows[-1]["code"]
        series_up, figs_up = [], []
        for r in rows:
            old = ([d.toordinal() for d in r["days"]], list(r["navs"])) if r["days"] else ([], [])
            end = r["nav_date"].toordinal()
            d, v = merge_months(old, pieces.get(r["code"], ((), ())), ([end], [r["nav"]]))
            if (d, v) != old:
                series_up.append((r["code"], [date.fromordinal(x) for x in d], v))
            if not r["series"]:
                figs = dashboard_figures(d, v, end, r["nav"])
                if not all(_same(a, b) for a, b in zip(figs, (r["sip3y"], r["sip5y"], r["mdd3y_m"]))):
                    figs_up.append((r["code"], *figs))
        async with store.pool.acquire() as conn, conn.transaction():
            if series_up:
                await conn.executemany(MONTHLY_UPSERT, series_up)
            if figs_up:
                await conn.executemany("UPDATE mf_schemes SET sip3y = $2, sip5y = $3, mdd3y_m = $4 WHERE code = $1", figs_up)
        out["schemes"] += len(rows)   # type: ignore[operator]
        out["seriesWritten"] += len(series_up)   # type: ignore[operator]
        out["figuresWritten"] += len(figs_up)   # type: ignore[operator]
    async with store.pool.acquire() as conn, conn.transaction():
        # a scheme that stopped publishing (or is no longer a Growth option with a NAV) keeps no month-ends and shows no SIP figure
        await conn.execute("""DELETE FROM mf_monthly m USING mf_schemes s WHERE s.code = m.code AND NOT (s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL)""")
        await conn.execute("""UPDATE mf_schemes SET sip3y = NULL, sip5y = NULL, mdd3y_m = NULL WHERE NOT (active AND option_class = 'Growth' AND nav IS NOT NULL)
                              AND (sip3y IS NOT NULL OR sip5y IS NOT NULL OR mdd3y_m IS NOT NULL)""")
        await _set_meta(conn, "monthly", {"read": sorted(done), "through": newest.isoformat(), "missing": out["monthsMissing"]})
    return out


# ====================================================================================== categories, the checklist, fund size and expense ratio
#
# AMFI files a scheme under a category line of its NAV file. Two generations of names are in use side by side ("Equity Scheme - Large Cap Fund" and
# "Equity Schemes - Large Cap Fund", "Debt Scheme - Low Duration Fund" and "Income/Debt Oriented Schemes - Ultra Short to Short Term Fund"), plus old
# category lines without a group ("ELSS", "Income", "Growth"). `classify` puts each name in one of five tabs and one sub-category, so one choice on the
# page covers both spellings. The page has the same table (frontend/src/lib/mfCategories.ts); keep the two in step.

TABS: Tuple[Tuple[str, str], ...] = (("equity", "Equity"), ("hybrid", "Hybrid"), ("debt", "Debt"), ("solution", "Solution Oriented"), ("other", "Others"))
TAB_KEYS = tuple(k for k, _ in TABS)


def _cnorm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s or "").lower()
    t = re.sub(r"[’'`*]", "", t).replace("&", " and ")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


_GROUP_TABS: Tuple[Tuple[str, str], ...] = (
    (r"^equity schemes?\b", "equity"), (r"^hybrid schemes?\b", "hybrid"), (r"^(debt schemes?|income debt oriented schemes?)\b", "debt"),
    (r"^(solution oriented schemes?|childrens? funds?|life cycle funds?)\b", "solution"),
    (r"^(other schemes?|index funds?|exchange traded funds?|fund of funds|overseas fund of funds)\b", "other"),
)
_LEGACY: Dict[str, Tuple[str, str, str]] = {   # category lines without a group (older and closed-ended schemes)
    "elss": ("equity", "elss", "ELSS (Tax Savings)"), "growth": ("equity", "equity-other", "Equity - Other"),
    "income": ("debt", "fixed-term", "Fixed Term & Interval"), "gilt": ("debt", "gilt", "Gilt"), "liquid": ("debt", "liquid", "Liquid"),
    "money market": ("debt", "money-market", "Money Market"), "balanced": ("hybrid", "hybrid-other", "Hybrid - Other"),
}
_SUBS: Dict[str, Tuple[Tuple[str, str, str], ...]] = {
    "equity": (
        (r"\bcontra\b", "contra", "Contra"), (r"\bdividend yield\b", "dividend-yield", "Dividend Yield"), (r"\belss\b|\btax saver\b", "elss", "ELSS (Tax Savings)"),
        (r"\bflexi ?cap\b", "flexi-cap", "Flexi Cap"), (r"\bfocused\b", "focused", "Focused"), (r"\blarge and mid ?cap\b", "large-mid-cap", "Large & Mid Cap"),
        (r"\blarge ?cap\b", "large-cap", "Large Cap"), (r"\bmid ?cap\b", "mid-cap", "Mid Cap"), (r"\bmulti ?cap\b", "multi-cap", "Multi Cap"),
        (r"\bsmall ?cap\b", "small-cap", "Small Cap"), (r"\bsectoral\b|\bthematic\b", "sectoral-thematic", "Sectoral / Thematic"), (r"\bvalue\b", "value", "Value"),
        (r"", "equity-other", "Equity - Other")),
    "debt": (
        (r"\bovernight\b", "overnight", "Overnight"), (r"\bliquid\b", "liquid", "Liquid"), (r"\bultra short to short\b|\blow duration\b", "low-duration", "Low Duration"),
        (r"\bultra short\b", "ultra-short", "Ultra Short Duration"), (r"\bmoney market\b", "money-market", "Money Market"),
        (r"\bmedium to long\b", "medium-long-duration", "Medium to Long Duration"), (r"\bmedium (duration|term)\b", "medium-duration", "Medium Duration"),
        (r"\bshort (duration|term)\b", "short-duration", "Short Duration"), (r"\blong (duration|term)\b", "long-duration", "Long Duration"),
        (r"\bdynamic (bond|term)\b", "dynamic-bond", "Dynamic Bond"), (r"\bcorporate bond\b", "corporate-bond", "Corporate Bond"),
        (r"\bcredit risk\b", "credit-risk", "Credit Risk"), (r"\bbanking and psu\b", "banking-psu", "Banking & PSU"),
        (r"\b10 ?year\b|\bconstant (duration|maturity)\b", "gilt-10y", "Gilt, 10-year Constant Duration"), (r"\bgilt\b", "gilt", "Gilt"),
        (r"\bfloat(er|ing)\b", "floater", "Floater"), (r"\bfixed term\b|\binterval\b", "fixed-term", "Fixed Term & Interval"), (r"", "debt-other", "Debt - Other")),
    "hybrid": (
        (r"\bconservative\b", "conservative-hybrid", "Conservative Hybrid"), (r"\bbalanced hybrid\b", "balanced-hybrid", "Balanced Hybrid"),
        (r"\bbalanced advantage\b|\bdynamic asset allocation\b", "balanced-advantage", "Balanced Advantage / Dynamic Asset Allocation"),
        (r"\baggressive\b", "aggressive-hybrid", "Aggressive Hybrid"), (r"\bmulti asset\b", "multi-asset", "Multi Asset Allocation"),
        (r"\barbitrage\b", "arbitrage", "Arbitrage"), (r"\bequity savings\b", "equity-savings", "Equity Savings"), (r"", "hybrid-other", "Hybrid - Other")),
    "solution": (
        (r"\bretirement\b", "retirement", "Retirement"), (r"\bchild", "childrens", "Children's"), (r"\blife cycle\b", "life-cycle", "Life Cycle"),
        (r"", "solution-other", "Solution Oriented - Other")),
    "other": (   # matched against the whole name: the group says as much as the rest here
        (r"\bgold\b", "gold-etf", "Gold ETFs"), (r"\bsilver\b", "silver-etf", "Silver ETFs"),
        (r"^index funds? debt\b", "index-debt", "Index Funds (Debt)"), (r"\bindex funds?\b", "index-funds", "Index Funds"),
        (r"\bdebt etf\b", "etf-debt", "ETFs (Debt)"), (r"\betfs?\b|\bexchange traded\b", "etf", "ETFs (Other)"),
        (r"\boverseas\b", "fof-overseas", "FoF Overseas"), (r"\bfof\b|\bfund of funds\b", "fof-domestic", "FoF Domestic"), (r"", "other", "Other")),
}


@functools.lru_cache(maxsize=4096)
def classify(category: str) -> Tuple[str, str, str]:
    """AMFI category name -> (tab, sub-category key, sub-category label). Every name gets one; anything unrecognised lands in Others."""
    n = _cnorm(category)
    head = _cnorm(category.split(" - ")[0]) if " - " in category else ""
    if not head and n in _LEGACY:
        return _LEGACY[n]
    tab = next((t for rx, t in _GROUP_TABS if re.search(rx, head or n)), "other")
    sub = n if tab == "other" else (_cnorm(category.split(" - ", 1)[1]) if " - " in category else n)
    for rx, key, label in _SUBS[tab]:
        if re.search(rx, sub):
            return tab, key, label
    return tab, f"{tab}-other", "Other"   # pragma: no cover - every table ends with a catch-all


# The checklist: plain pass/fail checks of a scheme against the other schemes of its sub-category and plan (Direct with Direct, Regular with Regular),
# active Growth options only. A check is "unknown" (not counted) when the scheme has no figure for it or fewer than CHECK_MIN_PEERS schemes have one.
CHECKS = (
    ("ret", "Long-term return above the category median (5 years per year; 3 years when the scheme has no 5 year figure)"),
    ("ter", "Expense ratio below the category median"),
    ("fall", "Smaller largest fall than the category median (month-end NAVs, last 3 years)"),
    ("size", "Fund size at least ₹500 crore (all plans together)"),
    ("age", "At least 5 years since launch"),
)
CHECK_MIN_PEERS = 3
CHECK_MIN_AUM_LAKH = 50_000.0   # ₹500 crore
CHECK_RET5_BIT = 32

DERIVE_FUND_FACTS = """
WITH q AS (SELECT max(aum_end) AS e FROM mf_facts WHERE aum_lakh IS NOT NULL),
fam_q AS (SELECT s.family, sum(f.aum_lakh) AS lakh, max(f.aum_end) AS asof FROM mf_facts f JOIN mf_schemes s ON s.code = f.code, q
          WHERE f.aum_end = q.e GROUP BY s.family),
fam_m AS (SELECT DISTINCT ON (fkey) fkey AS family, net_assets_lakh AS lakh, as_of AS asof FROM disclosure_portfolios
          WHERE net_assets_lakh IS NOT NULL AND net_assets_lakh > 0 ORDER BY fkey, as_of DESC),
own_t AS (SELECT s.code, s.family, t.ter_regular, t.ter_direct, t.ter_date FROM mf_schemes s JOIN mf_facts f ON f.code = s.code JOIN mf_ter t ON t.name_key = f.name_key),
fam_t AS (SELECT DISTINCT ON (family) family, ter_regular, ter_direct, ter_date FROM own_t ORDER BY family, ter_date DESC, code),
v AS (SELECT s.code,
             COALESCE(a.lakh, m.lakh) AS lakh, CASE WHEN a.lakh IS NOT NULL THEN a.asof ELSE m.asof END AS asof,
             CASE WHEN a.lakh IS NOT NULL THEN 'q' WHEN m.lakh IS NOT NULL THEN 'm' END AS kind,
             CASE s.plan WHEN 'Direct' THEN COALESCE(o.ter_direct, ft.ter_direct) WHEN 'Regular' THEN COALESCE(o.ter_regular, ft.ter_regular)
                         ELSE COALESCE(o.ter_regular, o.ter_direct, ft.ter_regular, ft.ter_direct) END AS ter,
             COALESCE(o.ter_date, ft.ter_date) AS ter_date
      FROM mf_schemes s LEFT JOIN fam_q a ON a.family = s.family LEFT JOIN fam_m m ON m.family = s.family
           LEFT JOIN own_t o ON o.code = s.code LEFT JOIN fam_t ft ON ft.family = s.family),
w AS (SELECT code, lakh, asof, kind, ter, CASE WHEN ter IS NULL THEN NULL ELSE ter_date END AS ter_date FROM v),
u AS (UPDATE mf_schemes s SET aum_lakh = w.lakh, aum_asof = w.asof, aum_kind = w.kind, ter = w.ter, ter_date = w.ter_date FROM w
      WHERE s.code = w.code AND (s.aum_lakh IS DISTINCT FROM w.lakh OR s.aum_asof IS DISTINCT FROM w.asof OR s.aum_kind IS DISTINCT FROM w.kind
                                 OR s.ter IS DISTINCT FROM w.ter OR s.ter_date IS DISTINCT FROM w.ter_date) RETURNING 1)
SELECT count(*) FROM u
"""
DERIVE_CHECKLIST = """
WITH cm AS (SELECT * FROM unnest($1::text[], $2::text[]) AS c(category, ckey)),
base AS (SELECT s.code, s.plan, cm.ckey, s.r3y, s.r5y, s.ter, s.mdd3y_m, s.aum_lakh, s.nav_date, f.launch_date
         FROM mf_schemes s JOIN cm ON cm.category = s.category LEFT JOIN mf_facts f ON f.code = s.code
         WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL),
med AS (SELECT ckey, plan,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY r5y) AS m5, count(r5y) AS n5,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY r3y) AS m3, count(r3y) AS n3,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY ter) AS mt, count(ter) AS nt,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY mdd3y_m) AS md, count(mdd3y_m) AS nd, count(*) AS n
        FROM base GROUP BY ckey, plan),
c AS (SELECT b.code,
             CASE WHEN b.r5y IS NOT NULL AND m.n5 >= $3 THEN b.r5y > m.m5 WHEN b.r3y IS NOT NULL AND m.n3 >= $3 THEN b.r3y > m.m3 END AS c0,
             (b.r5y IS NOT NULL AND m.n5 >= $3) AS used5,
             CASE WHEN b.ter IS NOT NULL AND m.nt >= $3 THEN b.ter < m.mt END AS c1,
             CASE WHEN b.mdd3y_m IS NOT NULL AND m.nd >= $3 THEN b.mdd3y_m > m.md END AS c2,
             CASE WHEN b.aum_lakh IS NOT NULL THEN b.aum_lakh >= $4 END AS c3,
             CASE WHEN b.r5y IS NOT NULL THEN true WHEN b.launch_date IS NOT NULL THEN b.launch_date <= (b.nav_date - interval '5 years')::date END AS c4
      FROM base b JOIN med m ON m.ckey = b.ckey AND m.plan = b.plan),
v AS (SELECT code,
             (CASE WHEN c0 THEN 1 ELSE 0 END + CASE WHEN c1 THEN 2 ELSE 0 END + CASE WHEN c2 THEN 4 ELSE 0 END + CASE WHEN c3 THEN 8 ELSE 0 END
              + CASE WHEN c4 THEN 16 ELSE 0 END + CASE WHEN c0 IS NOT NULL AND used5 THEN 32 ELSE 0 END)::smallint AS bits,
             (CASE WHEN c0 IS NOT NULL THEN 1 ELSE 0 END + CASE WHEN c1 IS NOT NULL THEN 2 ELSE 0 END + CASE WHEN c2 IS NOT NULL THEN 4 ELSE 0 END
              + CASE WHEN c3 IS NOT NULL THEN 8 ELSE 0 END + CASE WHEN c4 IS NOT NULL THEN 16 ELSE 0 END)::smallint AS mask,
             (COALESCE(c0::int, 0) + COALESCE(c1::int, 0) + COALESCE(c2::int, 0) + COALESCE(c3::int, 0) + COALESCE(c4::int, 0))::smallint AS pass,
             ((c0 IS NOT NULL)::int + (c1 IS NOT NULL)::int + (c2 IS NOT NULL)::int + (c3 IS NOT NULL)::int + (c4 IS NOT NULL)::int)::smallint AS known
      FROM c),
u AS (UPDATE mf_schemes s SET chk_bits = v.bits, chk_mask = v.mask, chk_pass = v.pass, chk_known = v.known FROM v
      WHERE s.code = v.code AND (s.chk_bits IS DISTINCT FROM v.bits OR s.chk_mask IS DISTINCT FROM v.mask) RETURNING 1),
x AS (UPDATE mf_schemes s SET chk_bits = NULL, chk_mask = NULL, chk_pass = NULL, chk_known = NULL
      WHERE s.chk_mask IS NOT NULL AND NOT EXISTS (SELECT 1 FROM v WHERE v.code = s.code) RETURNING 1)
SELECT ckey, plan, m5, n5, m3, n3, mt, nt, md, nd, n, (SELECT count(*) FROM u) AS changed, (SELECT count(*) FROM x) AS cleared FROM med
"""


async def derive_dashboard(store) -> dict:
    """Fund size and expense ratio per scheme (from the fund facts tables, as the scheme page shows them), then the checklist and the category medians
    behind it (kept in mf_meta 'dashboard' for the page's explanations). Plain SQL over the stored rows; a few seconds for the whole industry."""
    async with store.pool.acquire() as conn:
        cats = [r["category"] for r in await conn.fetch("SELECT DISTINCT category FROM mf_schemes")]
        keys = [classify(c)[1] for c in cats]
        async with conn.transaction():
            facts_changed = await conn.fetchval(DERIVE_FUND_FACTS)
            rows = await conn.fetch(DERIVE_CHECKLIST, cats, keys, CHECK_MIN_PEERS, CHECK_MIN_AUM_LAKH)
            peers = {f"{r['ckey']}|{r['plan']}": {"r5y": rnd(r["m5"]), "n5": r["n5"], "r3y": rnd(r["m3"]), "n3": r["n3"], "ter": rnd(r["mt"], 3), "nTer": r["nt"],
                                                   "fall": rnd(r["md"]), "nFall": r["nd"], "n": r["n"]} for r in rows}
            await _set_meta(conn, "dashboard", {"peers": peers, "minPeers": CHECK_MIN_PEERS, "minAumCrore": CHECK_MIN_AUM_LAKH / 100})
    _tab_cache["tabs"] = None   # categories may have changed with the data
    return {"status": "ok", "factsChanged": facts_changed, "checklistChanged": rows[0]["changed"] if rows else 0,
            "checklistCleared": rows[0]["cleared"] if rows else 0, "peerGroups": len(peers)}


# ====================================================================================== hot and cold

HOT_BASIS_FALLBACK = ("No verified fund size (AUM) is loaded yet, so this is NOT a ranking by size or quality: first the schemes opened most often on this site, "
                      "then a spread of Direct Growth schemes across the categories, A to Z within each category.")


async def choose_hot(store, n: int = HOT_SIZE) -> Tuple[str, List[int]]:
    """(basis text, scheme codes) of the hot set.
    1. By AUM when the disclosure module can name the largest schemes (`finlit.disclosure.top_by_aum(pool, n)` -> scheme codes), checked against what is stored.
    2. Otherwise the fallback: schemes opened most often (Redis counter, at least 3 opens), then a round-robin over categories of active Direct Growth schemes
       that have a 5 year figure (categories with the most schemes first, A to Z inside each). The basis text says plainly that this is not a size ranking."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT code, name, category, plan FROM mf_schemes WHERE active AND option_class = 'Growth' AND nav IS NOT NULL AND r5y IS NOT NULL")
    ok = {r["code"] for r in rows}
    try:
        from . import disclosure   # written by the data-source side; may not exist yet
        fn = getattr(disclosure, "top_by_aum", None)
        got = [int(c) for c in (await fn(store.pool, n) if fn else [])]
        got = [c for c in dict.fromkeys(got) if c in ok][:n]
        if len(got) >= n // 2:
            return "Largest schemes by assets under management (AUM): AMFI's average for the latest quarter, all plans of a scheme together.", got
    except Exception:
        log.debug("no AUM ranking available; using the fallback", exc_info=True)
    picked: List[int] = []
    try:
        counts = {int(k): int(v) for k, v in (await store.redis.hgetall(OPENS_KEY)).items()}
    except Exception:
        counts = {}
    for c, k in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        if k >= 3 and c in ok and len(picked) < n // 3:
            picked.append(c)
    by_cat: Dict[str, List[Tuple[str, int]]] = {}
    for r in rows:
        if r["plan"] == "Direct" and r["code"] not in picked:
            by_cat.setdefault(r["category"], []).append((r["name"], r["code"]))
    cats = sorted(by_cat, key=lambda c: (-len(by_cat[c]), c))
    for c in cats:
        by_cat[c].sort()
    i = 0
    while len(picked) < n and any(i < len(v) for v in by_cat.values()):
        for c in cats:
            if len(picked) < n and i < len(by_cat[c]):
                picked.append(by_cat[c][i][1])
        i += 1
    return HOT_BASIS_FALLBACK, picked[:n]


async def refresh_hot(store, client: Optional[httpx.AsyncClient] = None) -> dict:
    """Nightly: choose the hot set, make sure each hot scheme has its series stored (from the checked mirror when it is missing), drop the stored series of
    everything else (their 1 and 5 year figures stay in mf_schemes), rebuild the hot pages and copy them to Redis."""
    from types import SimpleNamespace
    basis, codes = await choose_hot(store)
    app = SimpleNamespace(state=SimpleNamespace(store=store, mf_client=client))
    async with store.pool.acquire() as conn:
        have = {r["code"] for r in await conn.fetch("SELECT code FROM mf_history WHERE code = ANY($1::int[])", codes)}
        todo = [dict(r) for r in await conn.fetch("SELECT code, nav, nav_date FROM mf_schemes WHERE code = ANY($1::int[]) AND code <> ALL($2::int[])", codes, list(have))]
    fetched = 0
    if client is not None:
        items = []
        for row in todo:
            got = await mirror_fetch(client, store.redis, row)
            if got:
                items.append((row["code"], list(got[0]), list(got[1]), False))
        if items:
            async with store.pool.acquire() as conn, conn.transaction():
                await _write_series(conn, items)
            fetched = len(items)
    async with store.pool.acquire() as conn, conn.transaction():
        dropped = await conn.fetchval("WITH d AS (DELETE FROM mf_history WHERE code <> ALL($1::int[]) RETURNING 1) SELECT count(*) FROM d", codes)
        # the 3 year return (refresh_anchors), the SIP figures and the month-end fall (refresh_monthly) are kept current for every scheme: they stay
        await conn.execute("""UPDATE mf_schemes SET r1m = NULL, r6m = NULL, vol1y = NULL, vol3y = NULL, mdd = NULL
                              WHERE code <> ALL($1::int[]) AND (r1m IS NOT NULL OR r6m IS NOT NULL OR vol1y IS NOT NULL OR vol3y IS NOT NULL OR mdd IS NOT NULL)""", codes)
    built = []
    for rank, code in enumerate(codes, 1):
        async with store.pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {LIST_COLS}, isin, isin_reinvest, family FROM mf_schemes WHERE code = $1", code)  # nosec B608 - fixed column list; code is a bound parameter
        built.append((rank, code, list_item(row), dumps(await detail_payload(app, row))))
    async with store.pool.acquire() as conn, conn.transaction():
        await conn.execute("DELETE FROM mf_hot")
        await conn.executemany("INSERT INTO mf_hot (code, rank, basis, item, detail) VALUES ($1, $2, $3, $4::jsonb, $5)",
                               [(code, rank, basis, json.dumps(item), detail if isinstance(detail, str) else detail.decode()) for rank, code, item, detail in built])
    async with store.pool.acquire() as conn:
        facts = await _facts(conn)
    await publish_hot(store, basis, built, facts)
    if dropped and dropped > 200:   # the freed space is only returned to the disk by a rewrite; the table is small afterwards
        try:
            async with store.pool.acquire() as conn:
                await conn.execute("VACUUM (FULL) mf_history")
        except Exception:
            log.warning("could not compact mf_history", exc_info=True)
    return {"hot": len(codes), "basis": "aum" if basis.startswith("Largest") else "fallback", "historyFetched": fetched, "historyDropped": dropped}


async def publish_hot(store, basis: str, built, facts: dict) -> None:
    """Copy the hot list and pages to Redis (no data version in the keys: they are rebuilt every night and live HOT_TTL)."""
    try:
        r = store.redis
        keep = {f"mf:hot:d:{code}" for _, code, _, _ in built}
        async for k in r.scan_iter("mf:hot:d:*"):
            if (k.decode() if isinstance(k, bytes) else k) not in keep:
                await r.delete(k)
        for _, code, _, detail in built:
            await r.set(f"mf:hot:d:{code}", detail, ex=HOT_TTL)
        await r.set("mf:hot:list", dumps({"basis": basis, "items": [{**item, "rank": rank} for rank, _, item, _ in built], **facts}), ex=HOT_TTL)
    except Exception:
        log.warning("could not copy the hot set to Redis")


# ====================================================================================== history backfill (separate, resumable)

async def backfill(store, settings=None, amc: Optional[str] = "all", *, client: Optional[httpx.AsyncClient] = None, force: bool = False,
                   log_fn=print, settle: bool = True) -> dict:
    """Load five years of NAV history from AMFI for the active Growth schemes, ONE FUND HOUSE AT A TIME (AMFI cannot filter below a fund house).
    `amc` is an AMC id, part of a name, or 'all' (every house not done yet; `force` redoes them). A house is written only when all its yearly downloads
    succeeded, then recorded in mf_backfill, so an interrupted run simply continues. Cost for the whole industry: see the figures logged per house."""
    own = client is None
    client = client or make_client()
    out: Dict[str, object] = {"done": [], "skipped": [], "failed": [], "points": 0, "bytes": 0}
    try:
        async with store.pool.acquire() as conn:
            newest = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes")
            rows = await conn.fetch(f"SELECT code, amc, nav, nav_date FROM mf_schemes WHERE {HIST_WANTED}")  # nosec B608 - fixed column list and constant filter, no input
            done = {r["amc_key"] for r in await conn.fetch("SELECT amc_key FROM mf_backfill")}
        if newest is None:
            return {**out, "status": "empty", "reason": "no schemes stored yet: run refresh first"}
        by_amc: Dict[str, List[dict]] = {}
        names: Dict[str, str] = {}
        for r in rows:
            if is_excluded_amc(r["amc"]):
                continue
            k = amc_key(r["amc"])
            by_amc.setdefault(k, []).append(dict(r))
            names[k] = r["amc"]
        want = (amc or "all").strip()
        picks = []
        for k, nm in sorted(names.items(), key=lambda kv: -len(by_amc[kv[0]])):
            ident = AMC_BY_KEY.get(k)
            if want.lower() != "all" and not (want.isdigit() and ident == int(want)) and want.lower() not in nm.lower():
                continue
            if k in done and not force:
                out["skipped"].append(nm)
                continue
            picks.append((k, nm, ident))
        for k, nm, ident in picks:
            t0 = time.perf_counter()
            if ident is None:
                async with store.pool.acquire() as conn:
                    await conn.execute("INSERT INTO mf_backfill (amc_key, amc, amc_id, note) VALUES ($1, $2, NULL, $3) ON CONFLICT (amc_key) DO UPDATE SET note = EXCLUDED.note, done_at = now()",
                                       k, nm, "no AMFI history id for this fund house; the mirror fallback serves its schemes")
                out["failed"].append(f"{nm}: no AMFI id")
                continue
            try:
                res = await _backfill_one(store, client, k, nm, ident, by_amc[k], newest)
            except Exception as exc:   # one fund house failing must not stop the others; it stays "not done" and is retried next run
                log.exception("backfill failed for %s", nm)
                out["failed"].append(f"{nm}: {exc.__class__.__name__}: {exc}")
                continue
            res["seconds"] = round(time.perf_counter() - t0, 1)
            out["done"].append(res)
            out["points"] += res["points"]
            out["bytes"] += res["bytes"]
            log_fn(f"backfill {nm}: {res['schemes']} schemes, {res['points']} points, {res['bytes'] / 1e6:.1f} MB downloaded, {res['seconds']} s")
        if out["done"] and settle:
            out["hot"] = await refresh_hot(store, client)   # series of everything but the hot schemes is dropped again; their figures stay
            await _bump(store, newest)
        out["status"] = "ok"
        return out
    finally:
        if own:
            await client.aclose()


async def _backfill_one(store, client, key: str, name: str, amc_id: int, schemes: List[dict], newest: date) -> dict:
    wanted = {s["code"] for s in schemes}
    start = newest - timedelta(days=KEEP_DAYS)
    pieces: Dict[int, List[Tuple[array.array, array.array]]] = {}
    total_bytes = ok_windows = 0
    frm = start
    while frm <= newest:
        to = min(newest, frm + timedelta(days=364))
        got = await fetch_history(client, frm, to, amc_id, wanted)
        if got is not None:
            ok_windows += 1
            total_bytes += got[1]["bytes"]
            for code, pair in got[0].items():
                pieces.setdefault(code, []).append(pair)
        frm = to + timedelta(days=1)
    async with store.pool.acquire() as conn, conn.transaction():
        if not pieces:
            await conn.execute("INSERT INTO mf_backfill (amc_key, amc, amc_id, schemes, note) VALUES ($1, $2, $3, 0, $4) "
                               "ON CONFLICT (amc_key) DO UPDATE SET note = EXCLUDED.note, done_at = now()", key, name, amc_id, "AMFI returned no history rows; the mirror fallback serves its schemes")
            return {"amc": name, "schemes": 0, "points": 0, "bytes": total_bytes}
        existing = {r["code"]: r for r in await conn.fetch("SELECT code, blob, d0 FROM mf_history WHERE code = ANY($1::int[])", list(pieces))}
        items, points, mismatches, written = [], 0, 0, 0
        latest = {s["code"]: s for s in schemes}
        for code, parts in pieces.items():
            ps = [(p[0], p[1]) for p in parts]
            if code in existing:
                ps.insert(0, unpack_series(bytes(existing[code]["blob"]), existing[code]["d0"].toordinal()))
            days, navs = merge_points(*ps)
            # AMFI's history and its NAVAll must agree on the newest day; a difference is counted and reported, never hidden.
            s = latest[code]
            if days[-1] == s["nav_date"].toordinal() and navs[-1] != s["nav"]:
                mismatches += 1
            items.append((code, days, navs, True))
            points += len(days)
            written += 1
            if len(items) >= 200:   # batches keep the memory flat on a small host
                await _write_series(conn, items)
                items = []
        if items:
            await _write_series(conn, items)
        await conn.execute("INSERT INTO mf_backfill (amc_key, amc, amc_id, schemes, points, bytes, note) VALUES ($1, $2, $3, $4, $5, $6, $7) "
                           "ON CONFLICT (amc_key) DO UPDATE SET amc = EXCLUDED.amc, amc_id = EXCLUDED.amc_id, schemes = EXCLUDED.schemes, points = EXCLUDED.points, "
                           "bytes = EXCLUDED.bytes, note = EXCLUDED.note, done_at = now()",
                           key, name, amc_id, written, points, total_bytes, f"{ok_windows} yearly downloads; {mismatches} newest-NAV mismatches against NAVAll")
    return {"amc": name, "schemes": written, "points": points, "bytes": total_bytes, "mismatches": mismatches, "windows": ok_windows}


# ====================================================================================== the mirror (fallback only)

def parse_mirror(payload: dict, code: int) -> Optional[Tuple[List[int], List[float]]]:
    """api.mfapi.in/mf/<code> -> ascending (days, NAVs), or None when the answer is not for this scheme or has no usable data."""
    try:
        if int(payload["meta"]["scheme_code"]) != code or payload.get("status", "SUCCESS") != "SUCCESS":
            return None
        pairs = {}
        for x in payload["data"]:
            dd, mm, yy = x["date"].split("-")
            nav = parse_nav(str(x["nav"]))
            if nav is not None:
                pairs[date(int(yy), int(mm), int(dd)).toordinal()] = nav
    except (KeyError, TypeError, ValueError):
        return None
    if not pairs:
        return None
    days = sorted(pairs)
    return trim(days, [pairs[d] for d in days])


async def mirror_fetch(client: httpx.AsyncClient, redis, row: dict) -> Optional[Tuple[List[int], List[float]]]:
    """The mirror's history for a scheme, only if its newest NAV agrees with AMFI's own latest NAV for the same day (else it is not used).
    This is the COLD path: a scheme that is not in the hot set is fetched when somebody opens it and kept in Redis for COLD_TTL with a 'last opened' stamp
    (rewritten at every open, so a scheme nobody opens for a few days simply expires: that is the prune). A cached copy that does not end on the scheme's
    current NAV date is not used."""
    code = row["code"]
    key = f"mf:cold:{code}"
    want = row["nav_date"].toordinal() if row["nav_date"] else None
    try:
        hit = await redis.get(key)
    except Exception:
        hit = None
    if hit is not None:
        raw = json.loads(hit)
        if not raw:
            return None
        if raw["d"] and raw["d"][-1] == want:
            raw["o"] = int(time.time())
            try:
                await redis.set(key, json.dumps(raw), ex=COLD_TTL)
            except Exception:
                pass
            return raw["d"], raw["v"]
    series = None
    try:
        r = await client.get(f"{MIRROR_URL}/{code}")
        if r.status_code == 200:
            series = parse_mirror(r.json(), code)
    except (httpx.HTTPError, ValueError):
        series = None
    if series and row["nav_date"] and row["nav"]:
        days, navs = series
        i = bisect_right(days, row["nav_date"].toordinal()) - 1
        if i < 0 or days[i] != row["nav_date"].toordinal() or abs(navs[i] - row["nav"]) > 1e-6 * max(1.0, row["nav"]):
            series = None   # the mirror disagrees with AMFI (or lags it): show nothing rather than a number we cannot confirm
    try:
        await redis.set(key, json.dumps({"d": series[0], "v": series[1], "o": int(time.time())} if series else None), ex=COLD_TTL if series else 600)
    except Exception:
        pass
    return series


async def mirror_series(app, row: dict) -> Optional[Tuple[List[int], List[float]]]:
    client = getattr(app.state, "mf_client", None)
    if client is None:
        client = app.state.mf_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=True, headers={"User-Agent": USER_AGENT})
    return await mirror_fetch(client, app.state.store.redis, row)


# ====================================================================================== API

LIST_COLS = ("code, name, amc, category, scheme_type, plan, option_class, option_label, nav, nav_date, prev_nav, prev_date, active, has_hist, r1m, r6m, r1y, r3y, r5y, "
             "vol1y, vol3y, mdd, metrics_date, sip3y, sip5y, mdd3y_m, aum_lakh, aum_asof, aum_kind, ter, ter_date, chk_pass, chk_known, chk_bits, chk_mask")
# The list shows returns over 1 day, 1, 3 and 5 years (3 and 5 per year), SIP returns over 3 and 5 years, fund size, expense ratio and the checklist.
# Volatility, drawdown and the other periods are on the scheme's own page.
SORTS = {"name": "name", "amc": "amc", "category": "category", "nav": "nav", "navDate": "nav_date", "r1y": "r1y", "r3y": "r3y", "r5y": "r5y",
         "change": "(CASE WHEN prev_nav > 0 THEN nav / prev_nav - 1 END)", "sip3y": "sip3y", "sip5y": "sip5y", "aum": "aum_lakh", "ter": "ter",
         "checklist": "(chk_pass * 8 + chk_known)"}
MAX_CATEGORIES = 80
PLANS = ("Direct", "Regular", "Unspecified")
OPTIONS = ("Growth", "IDCW", "Other", "All")   # no choice means Growth; "All" turns the default off


def rnd(v: Optional[float], n: int = 2) -> Optional[float]:
    return None if v is None else round(v, n)


def iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def day_change(row) -> Optional[dict]:
    """Change against the previous NAV AMFI gave for this scheme (named by its date: it can be a few days back for slow-reporting schemes)."""
    if row["nav"] and row["prev_nav"] and row["prev_nav"] > 0:
        return {"abs": round(row["nav"] - row["prev_nav"], 6), "pct": round((row["nav"] / row["prev_nav"] - 1) * 100, 2), "since": iso(row["prev_date"])}
    return None


def why_no_returns(row) -> Optional[str]:
    """A short code for why a scheme has no return figures at all (the page turns it into words); None when it has some."""
    if row["r1y"] is not None or row["r5y"] is not None:
        return None
    if not row["active"]:
        return "stopped"
    if row["option_class"] == "IDCW":
        return "idcw"
    if row["option_class"] != "Growth":
        return "unstated"
    return "no_history" if not row["has_hist"] else "short"


def checklist_item(r) -> Optional[dict]:
    """The checklist of a list row: passed / checked, which passed (bits) and which could be checked (mask), and the peer group whose medians it used."""
    if r["chk_mask"] is None:
        return None
    return {"pass": r["chk_pass"], "of": r["chk_known"], "bits": r["chk_bits"], "mask": r["chk_mask"], "peer": f"{classify(r['category'])[1]}|{r['plan']}"}


def list_item(r) -> dict:
    ch = day_change(r)
    aum = r["aum_lakh"]
    return {"code": r["code"], "name": r["name"], "amc": r["amc"], "category": r["category"], "plan": r["plan"], "option": r["option_label"], "optionClass": r["option_class"],
            "nav": r["nav"], "navDate": iso(r["nav_date"]), "change": ch["pct"] if ch else None, "changeSince": ch["since"] if ch else None, "active": r["active"],
            "r1y": rnd(r["r1y"]), "r3y": rnd(r["r3y"]), "r5y": rnd(r["r5y"]), "retDate": iso(r["metrics_date"]), "noReturns": why_no_returns(r),
            "sip3y": rnd(r["sip3y"]), "sip5y": rnd(r["sip5y"]), "fall3y": rnd(r["mdd3y_m"]),
            "aum": None if aum is None else round(aum / 100, 2), "aumAsOf": iso(r["aum_asof"]), "aumKind": r["aum_kind"],
            "ter": rnd(r["ter"], 2), "terDate": iso(r["ter_date"]), "checklist": checklist_item(r)}


async def _version(redis) -> str:
    try:
        v = await redis.get("mf:ver")
        return v.decode() if v else "0"
    except Exception:
        return "0"


async def cached_json(request: Request, kind: str, key: str, build, ttl: int = 900) -> Response:
    """Rendered JSON kept in Redis under the current data version (a refresh makes older copies unreachable), with ETag / 304 and a shared-cache header."""
    store = request.app.state.store
    rk = f"mf:{await _version(store.redis)}:{kind}:{hashlib.blake2b(key.encode(), digest_size=12).hexdigest()}"
    try:
        hit = await store.redis.hmget(rk, ["body", "etag"])
    except Exception:
        hit = [None, None]
    if hit[0] is None:
        body = dumps(await build())
        etag = etag_for(body)
        try:
            await store.redis.hset(rk, mapping={"body": body, "etag": etag})
            await store.redis.expire(rk, ttl)
        except Exception:
            pass
    else:
        body, etag = hit[0], hit[1].decode() if isinstance(hit[1], bytes) else hit[1]
    headers = {"ETag": etag, "Cache-Control": CACHE_HEADER}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


async def _facts(conn) -> dict:
    """The data date and last-updated time every page shows."""
    ref = await _meta(conn, "refresh") or {}
    newest = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes WHERE active")
    return {"dataDate": iso(newest) or ref.get("navDate"), "updatedAt": ref.get("at"), "source": SOURCE, "disclaimer": DISCLAIMER, "excludedAmcs": list(MF_EXCLUDED_AMCS)}


_index_cache: Dict[str, object] = {"ver": None, "index": None}


async def _search_index(store) -> SearchIndex:
    ver = await _version(store.redis)
    if _index_cache["ver"] != ver or _index_cache["index"] is None:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT code, name, amc FROM mf_schemes")
        _index_cache["index"], _index_cache["ver"] = await asyncio.to_thread(SearchIndex, [(r["code"], r["name"], r["amc"]) for r in rows]), ver
    return _index_cache["index"]   # type: ignore[return-value]


@router.get("")
async def list_funds(request: Request, q: str = Query("", max_length=80), category: str = Query("", max_length=160), amc: str = Query("", max_length=120),
                     categories: List[str] = Query([]), group: str = Query("", max_length=12),
                     plan: str = Query("", max_length=20), option: str = Query("", max_length=20), stopped: bool = False,
                     min1y: Optional[float] = Query(None, ge=-100, le=100000), max1y: Optional[float] = Query(None, ge=-100, le=100000),
                     min5y: Optional[float] = Query(None, ge=-100, le=100000), max5y: Optional[float] = Query(None, ge=-100, le=100000),
                     sort: str = Query("", max_length=12), dir: str = Query("asc", pattern="^(asc|desc)$"),
                     page: int = Query(1, ge=1, le=2000), size: int = Query(50, ge=1, le=PAGE_MAX)) -> Response:
    """Schemes, filtered and sorted on the server (about 14,000 exist). The count is exact for the filters given. Without a chosen sort the order is by relevance
    when searching, otherwise A to Z. Schemes that stopped publishing NAVs are left out unless `stopped=true`.
    Categories: `category` (one exact AMFI name), `categories` (exact AMFI names, the parameter repeated: categories=A&categories=B) and `group` (a whole tab:
    equity, hybrid, debt, solution, other; see `classify`). Given together, a scheme must match each one given."""
    if plan and plan not in PLANS or option and option not in OPTIONS:
        raise fail(400, "bad_request", "Unknown plan or option.")
    if sort and sort not in SORTS:
        raise fail(400, "bad_request", "Unknown sort column.")
    if group and group not in TAB_KEYS:
        raise fail(400, "bad_request", "Unknown category group: use equity, hybrid, debt, solution or other.")
    cats = sorted({c.strip() for c in categories if c.strip()})
    if len(cats) > MAX_CATEGORIES or any(len(c) > 160 for c in cats):
        raise fail(400, "bad_request", f"At most {MAX_CATEGORIES} categories of up to 160 characters each.")
    key = json.dumps([q.strip().lower(), category, amc, plan, option, stopped, min1y, max1y, min5y, max5y, sort, dir, page, size, cats, group])

    async def build():
        store = request.app.state.store
        where, args = [], []

        def arg(v):
            args.append(v)
            return f"${len(args)}"
        order_codes, codes_ph = None, ""
        if q.strip():
            order_codes = (await _search_index(store)).search(q)
            if order_codes is not None:
                codes_ph = arg(order_codes)
                where.append(f"code = ANY({codes_ph}::int[])")
        if not stopped:
            where.append("active")
        for col, v in (("category", category), ("amc", amc), ("plan", plan), ("option_class", "" if option == "All" else (option or "Growth"))):
            if v:
                where.append(f"{col} = {arg(v)}")
        if cats:
            where.append(f"category = ANY({arg(cats)}::text[])")
        if group:
            where.append(f"category = ANY({arg(await _tab_categories(store, group))}::text[])")
        for col, lo, hi in (("r1y", min1y, max1y), ("r5y", min5y, max5y)):
            if lo is not None:
                where.append(f"{col} >= {arg(lo)}")
            if hi is not None:
                where.append(f"{col} <= {arg(hi)}")
        w = ("WHERE " + " AND ".join(where)) if where else ""
        n_where = len(args)
        if sort:
            order = f"{SORTS[sort]} {'DESC' if dir == 'desc' else 'ASC'} NULLS LAST, name, code"
        elif order_codes is not None:
            order = f"array_position({codes_ph}::int[], code)"
        else:   # best-known fund houses first (the list in config), then A to Z
            feat = arg(list(MF_FEATURED_AMCS))
            order = f"COALESCE((SELECT min(u.i) FROM unnest({feat}::text[]) WITH ORDINALITY AS u(p, i) WHERE lower(amc) LIKE u.p || '%'), 999), name, code"  # nosec B608 - only a bound-parameter placeholder and fixed text; the house list is a bound array
        async with store.pool.acquire() as conn:
            total = await conn.fetchval(f"SELECT count(*) FROM mf_schemes {w}", *args[:n_where])  # nosec B608 - WHERE text is built from fixed column names; every value is a bound parameter
            rows = await conn.fetch(f"SELECT {LIST_COLS} FROM mf_schemes {w} ORDER BY {order} LIMIT {size} OFFSET {(page - 1) * size}", *args)  # nosec B608 - column list and sort come from fixed maps; size and page are range-checked integers
            facts = await _facts(conn)
            dash = await _meta(conn, "dashboard") or {}
        items = [list_item(r) for r in rows]
        want = {i["checklist"]["peer"] for i in items if i["checklist"]}
        peers = {k: v for k, v in (dash.get("peers") or {}).items() if k in want}
        return {"total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size)), "items": items, "peers": peers,
                "checklist": {"checks": [{"key": k, "rule": t} for k, t in CHECKS], "minPeers": CHECK_MIN_PEERS}, **facts}
    return await cached_json(request, "list", key, build)


_tab_cache: Dict[str, object] = {"ver": None, "tabs": None, "at": 0.0}
TAB_CACHE_SECONDS = 600


async def _tab_categories(store, tab: str) -> List[str]:
    """Every stored category name that `classify` puts in this tab (about 100 names in all; worked out once per data version)."""
    ver = await _version(store.redis)
    if _tab_cache["ver"] != ver or _tab_cache["tabs"] is None or time.monotonic() - float(_tab_cache["at"]) > TAB_CACHE_SECONDS:  # type: ignore[arg-type]
        async with store.pool.acquire() as conn:
            names = [r["category"] for r in await conn.fetch("SELECT DISTINCT category FROM mf_schemes")]
        tabs: Dict[str, List[str]] = {k: [] for k in TAB_KEYS}
        for n in names:
            tabs[classify(n)[0]].append(n)
        _tab_cache["tabs"], _tab_cache["ver"], _tab_cache["at"] = tabs, ver, time.monotonic()
    return list(_tab_cache["tabs"][tab])   # type: ignore[index]


@router.get("/filters")
async def filters(request: Request) -> Response:
    """Categories and fund houses with how many schemes each has (active ones, and all), plus plan and option counts, for the filter menus."""
    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            cats = await conn.fetch("""SELECT category, scheme_type, count(*) FILTER (WHERE active) AS active, count(*) AS total,
                                              count(*) FILTER (WHERE active AND option_class = 'Growth') AS growth,
                                              count(*) FILTER (WHERE active AND option_class = 'Growth' AND plan = 'Direct') AS direct,
                                              count(*) FILTER (WHERE active AND option_class = 'Growth' AND plan = 'Regular') AS regular
                                       FROM mf_schemes GROUP BY 1, 2 ORDER BY 1, 2""")
            amcs = await conn.fetch("SELECT amc, count(*) FILTER (WHERE active) AS active, count(*) AS total FROM mf_schemes GROUP BY 1 ORDER BY 1")
            plans = await conn.fetch("SELECT plan, count(*) FILTER (WHERE active) AS active FROM mf_schemes GROUP BY 1")
            opts = await conn.fetch("SELECT option_class, count(*) FILTER (WHERE active) AS active FROM mf_schemes GROUP BY 1")
            tot = await conn.fetchrow("SELECT count(*) AS total, count(*) FILTER (WHERE active) AS active, count(*) FILTER (WHERE has_hist) AS hist FROM mf_schemes")
            facts = await _facts(conn)
        merged: Dict[str, dict] = {}
        for c in cats:   # one category can appear under two scheme types (rare); the filter is by category text, so counts add up
            tab, sub, label = classify(c["category"])
            m = merged.setdefault(c["category"], {"name": c["category"], "group": category_group(c["category"]), "type": c["scheme_type"], "tab": tab, "key": sub,
                                                  "label": label, "active": 0, "total": 0, "growth": 0, "direct": 0, "regular": 0})
            for k in ("active", "total", "growth", "direct", "regular"):
                m[k] += c[k]
        return {"categories": list(merged.values()), "tabs": [{"key": k, "label": t} for k, t in TABS],
                "amcs": [{"name": a["amc"], "active": a["active"], "total": a["total"]} for a in amcs],
                "plans": [{"name": p["plan"], "active": p["active"]} for p in plans], "options": [{"name": o["option_class"], "active": o["active"]} for o in opts],
                "totals": {"schemes": tot["total"], "active": tot["active"], "withHistory": tot["hist"]}, **facts}
    return await cached_json(request, "filters", "all", build)


RANGES = (("1M", 1), ("6M", 6), ("1Y", 12), ("3Y", 36), ("5Y", 60))
RANGE_CAP = {"1M": 40, "6M": 200, "1Y": 380, "3Y": 450, "5Y": 450, "MAX": 450}


async def load_series(app, row) -> Tuple[List[int], List[float], bool, str, Optional[str]]:
    """(days, NAVs, complete, source, note) for a scheme: the stored AMFI series; else, for an active Growth scheme only, the checked mirror; else empty."""
    async with app.state.store.pool.acquire() as conn:
        h = await conn.fetchrow("SELECT blob, d0, complete FROM mf_history WHERE code = $1", row["code"])
    if h:
        days, navs = unpack_series(bytes(h["blob"]), h["d0"].toordinal())
        return days, navs, bool(h["complete"]), "amfi", None
    if row["active"] and row["option_class"] == "Growth":
        got = await mirror_series(app, row)
        if got:
            return got[0], got[1], False, "mirror", "NAV history: third-party mirror of AMFI data (api.mfapi.in)"
        return [], [], False, "none", "NAV history could not be fetched right now; try again in a moment."
    return [], [], False, "none", None


def series_block(days: List[int], navs: List[float]) -> Dict[str, dict]:
    """Chart series per range. A range is offered only if the history reaches back to its start; MAX (since the first NAV on file) only when no 5Y range covers it."""
    out: Dict[str, dict] = {}
    if len(days) < 2:
        return out
    end = date.fromordinal(days[-1])
    for key, months in RANGES:
        i = bisect_right(days, shift_months(end, months).toordinal()) - 1
        if i >= 0:
            d, v = thin(days[i:], navs[i:], RANGE_CAP[key])
            out[key] = {"t": [date.fromordinal(x).isoformat() for x in d], "v": v}
    if "5Y" not in out:
        d, v = thin(days, navs, RANGE_CAP["MAX"])
        out["MAX"] = {"t": [date.fromordinal(x).isoformat() for x in d], "v": v}
    return out


def returns_json(m: dict) -> dict:
    return {k: {"value": rnd(x["value"]), "kind": x["kind"], "from": iso(x["from"]), "why": x["why"]} for k, x in m["returns"].items()}


def ret_from_row(row, ret: dict) -> dict:
    """No series right now (a cold scheme whose history could not be fetched): the 1 and 5 year figures worked out nightly from AMFI's history are still true
    (the page says as of when), so they are kept; the other periods stay empty."""
    if row["option_class"] == "Growth" and row["active"] and (row["r1y"] is not None or row["r5y"] is not None):
        for k in ("1y", "5y"):
            v = row["r1y" if k == "1y" else "r5y"]
            ret[k] = {"value": rnd(v), "kind": ret[k]["kind"], "from": None, "why": None if v is not None else ret[k]["why"]}
    return ret


def risk_json(m: dict) -> dict:
    dd = m["mdd"]
    return {"vol1y": {"value": rnd(m["vol1y"]["value"]), "why": m["vol1y"]["why"]}, "vol3y": {"value": rnd(m["vol3y"]["value"]), "why": m["vol3y"]["why"]},
            "maxDrawdown": {"value": rnd(dd["value"]), "why": dd["why"], "peak": iso(dd.get("peak")), "trough": iso(dd.get("trough")), "since": iso(dd.get("since"))}}


def returns_note(row, source: str, has_series: bool) -> Optional[str]:
    if not row["active"]:
        return "This scheme has stopped publishing NAVs, so no current return is shown."
    if row["option_class"] == "IDCW":
        return "Returns are not worked out for IDCW (dividend) options: each payout lowers the NAV, so NAV-to-NAV change would understate what an investor earned. See the Growth option of the same fund."
    if row["option_class"] != "Growth":
        return "AMFI does not state a Growth option for this scheme, so NAV-to-NAV returns are not shown: any payout it made would be missing from them."
    if not has_series:
        return "NAV history is fetched when a scheme is opened and could not be fetched right now, so the risk figures are missing; try again in a moment."
    return None


async def detail_payload(app, row) -> dict:
    days, navs, complete, source, note = await load_series(app, row)
    m = metrics_for(days, navs, complete) if days and row["option_class"] == "Growth" and row["active"] else None
    async with app.state.store.pool.acquire() as conn:
        kin = await conn.fetch("SELECT code, name, plan, option_class, option_label, nav, nav_date, active FROM mf_schemes WHERE family = $1 AND code <> $2 ORDER BY plan, option_class, name LIMIT 40",
                               row["family"], row["code"])
        facts = await _facts(conn)
    empty = {"value": None, "kind": "absolute", "from": None, "why": returns_note(row, source, bool(days))}
    ret = returns_json(m) if m else {k: {**empty, "kind": "cagr" if mo > 12 else "absolute"} for k, mo, _ in HORIZONS}
    if not m:
        ret = ret_from_row(row, ret)
    risk = risk_json(m) if m else {"vol1y": {"value": None, "why": empty["why"]}, "vol3y": {"value": None, "why": empty["why"]}, "maxDrawdown": {"value": None, "why": empty["why"], "peak": None, "trough": None, "since": None}}
    change = day_change(row)
    if len(days) >= 2 and days[-1] == row["nav_date"].toordinal() if days and row["nav_date"] else False:
        # the 1 day change straight from the last two NAVs of the series (the scheme's own previous NAV date is named, it can be a few days back)
        change = {"abs": round(navs[-1] - navs[-2], 6), "pct": round((navs[-1] / navs[-2] - 1) * 100, 2), "since": date.fromordinal(days[-2]).isoformat()}
    return {"code": row["code"], "name": row["name"], "isin": row["isin"], "isinReinvest": row["isin_reinvest"], "amc": row["amc"], "category": row["category"],
            "categoryGroup": category_group(row["category"]), "schemeType": row["scheme_type"], "plan": row["plan"], "optionClass": row["option_class"], "option": row["option_label"],
            "active": row["active"], "nav": row["nav"], "navDate": iso(row["nav_date"]), "prevNav": row["prev_nav"], "prevDate": iso(row["prev_date"]), "change": change,
            "returns": ret, "risk": risk, "retDate": iso(row["metrics_date"]), "returnsNote": returns_note(row, source, bool(days)) if not m and ret["1y"]["value"] is None and ret["5y"]["value"] is None else None,
            "series": series_block(days, navs) if m else {},
            "history": {"source": source if days else None, "from": iso(date.fromordinal(days[0])) if days else None, "to": iso(date.fromordinal(days[-1])) if days else None,
                        "points": len(days), "complete": complete, "note": note if source != "amfi" else None},
            "family": [{"code": k["code"], "name": k["name"], "plan": k["plan"], "optionClass": k["option_class"], "option": k["option_label"], "nav": k["nav"],
                        "navDate": iso(k["nav_date"]), "active": k["active"]} for k in kin],
            "notAvailable": NOT_AVAILABLE, **facts}


async def _scheme(request: Request, code: int):
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT {LIST_COLS}, isin, isin_reinvest, family FROM mf_schemes WHERE code = $1", code)  # nosec B608 - fixed column list; the scheme code is a bound parameter
    if not row:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")
    return row


@router.get("/compare")
async def compare(request: Request, ids: str = Query("", max_length=60), range: str = Query("1Y", pattern="^(1M|6M|1Y|3Y|5Y|MAX)$")) -> Response:
    """2 to 4 schemes side by side: facts, returns, risk, and each NAV series rebased to 100 on the first day all of them have a NAV in the range."""
    try:
        codes = list(dict.fromkeys(int(x) for x in ids.split(",") if x.strip()))
    except ValueError:
        raise fail(400, "bad_request", "ids must be scheme codes separated by commas.")
    if not 2 <= len(codes) <= 4 or any(not 0 < c < 10**7 for c in codes):
        raise fail(400, "bad_request", "Compare 2 to 4 schemes: ids=code1,code2.")

    async def build():
        rows = [await _scheme(request, c) for c in codes]
        loaded = [await load_series(request.app, r) for r in rows]
        funds, spans = [], []
        for r, (days, navs, complete, source, note) in zip(rows, loaded):
            ok = bool(days) and r["option_class"] == "Growth" and r["active"]
            m = metrics_for(days, navs, complete) if ok else None
            empty = returns_note(r, source, bool(days))
            ret = returns_json(m) if m else ret_from_row(r, {k: {"value": None, "kind": "cagr" if mo > 12 else "absolute", "from": None, "why": empty} for k, mo, _ in HORIZONS})
            risk = risk_json(m) if m else {"vol1y": {"value": None, "why": empty}, "vol3y": {"value": None, "why": empty}, "maxDrawdown": {"value": None, "why": empty, "peak": None, "trough": None, "since": None}}
            start = None   # index of the NAV the range starts from; None when this fund's history does not reach back that far
            if ok and len(days) > 1:
                start = 0 if range == "MAX" else bisect_right(days, shift_months(date.fromordinal(days[-1]), dict(RANGES)[range]).toordinal()) - 1
                start = start if start >= 0 else None
            spans.append((days, navs, start))
            funds.append({"code": r["code"], "name": r["name"], "amc": r["amc"], "category": r["category"], "plan": r["plan"], "option": r["option_label"], "optionClass": r["option_class"],
                          "nav": r["nav"], "navDate": iso(r["nav_date"]), "change": day_change(r), "active": r["active"], "returns": ret, "risk": risk, "retDate": iso(r["metrics_date"]),
                          "history": {"source": source if days else None, "from": iso(date.fromordinal(days[0])) if days else None, "note": note if source != "amfi" else None}})
        # rebase: the common start is the latest of the funds' range starts; every fund shows its NAV on or before that day as 100
        chart = None
        if all(st is not None for _, _, st in spans):
            common = max(d[st] for d, _, st in spans)
            chart = {"from": date.fromordinal(common).isoformat(), "range": range, "series": []}
            for f, (d, v, _) in zip(funds, spans):
                i0 = bisect_right(d, common) - 1
                dd, vv = thin(d[i0:], v[i0:], RANGE_CAP[range])
                chart["series"].append({"code": f["code"], "t": [date.fromordinal(x).isoformat() for x in dd], "v": [round(x / v[i0] * 100, 4) for x in vv]})
        async with request.app.state.store.pool.acquire() as conn:
            facts = await _facts(conn)
        return {"funds": funds, "chart": chart, "chartNote": None if chart else "A rebased chart needs NAV history for every fund over this range; try a shorter one.", "notAvailable": NOT_AVAILABLE, **facts}
    return await cached_json(request, "compare", f"{codes}|{range}", build)


@router.get("/status")
async def run_status(request: Request) -> Response:
    """When each load step last ran and how it ended (no secrets: counts, statuses and our own error text)."""
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, value, updated_at FROM mf_meta WHERE key LIKE 'run:%' OR key = 'refresh'")
    body = {r["key"]: (json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]) for r in rows}
    return Response(content=json.dumps(body, default=str), media_type="application/json", headers={"Cache-Control": "no-store"})


@router.get("/hot")
async def hot_list(request: Request) -> Response:
    """The schemes kept ready (rebuilt every night): list rows with their rank, answered from Redis, else from the small mf_hot table."""
    store = request.app.state.store
    try:
        body = await store.redis.get("mf:hot:list")
    except Exception:
        body = None
    if body is None:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT rank, basis, item FROM mf_hot ORDER BY rank")
            facts = await _facts(conn)
        items = [{**(json.loads(r["item"]) if isinstance(r["item"], str) else r["item"]), "rank": r["rank"]} for r in rows]
        body = dumps({"basis": rows[0]["basis"] if rows else None, "items": items, **facts})
        if rows:
            try:
                await store.redis.set("mf:hot:list", body, ex=HOT_TTL)
            except Exception:
                pass
    return Response(content=body, media_type="application/json", headers={"Cache-Control": CACHE_HEADER})


FACT_KEYS = ("aum", "terRegular", "terDirect", "exitLoad", "benchmark", "managers", "riskometer", "launchDate", "minInvestment")
NO_FACTS = "The fund house's monthly disclosure is not loaded yet."
NO_PORTFOLIO = "The fund house's monthly portfolio disclosure is not loaded yet."


async def _disclosure(request: Request, fn_name: str, code: int):
    """Call finlit.disclosure.<fn_name>(pool, code) defensively: the module belongs to the data-source side and may not exist yet. None when unavailable."""
    try:
        from . import disclosure
        fn = getattr(disclosure, fn_name)
    except Exception:
        return None
    try:
        return await fn(request.app.state.store.pool, code)
    except Exception:
        log.warning("disclosure.%s failed for %s", fn_name, code, exc_info=True)
        return None


@router.get("/{code}/facts")
async def facts_route(request: Request, code: int) -> Response:
    """Fund facts, each {value, asOf, source} or {unavailable: reason}. Category and fund house come from AMFI's NAV file; the rest from the disclosure module."""
    if not 0 < code < 10**7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")

    async def build():
        row = await _scheme(request, code)
        got = await _disclosure(request, "get_facts", code)
        got = got if isinstance(got, dict) else {}
        out = {}
        for k in FACT_KEYS:
            v = got.get(k)
            out[k] = v if isinstance(v, dict) and ("value" in v or "unavailable" in v) else {"unavailable": NO_FACTS if not got else "Not published in the sources loaded for this scheme."}
        src = {"source": SOURCE, "asOf": iso(row["nav_date"])}
        out["category"] = {"value": row["category"], **src}
        out["amc"] = {"value": row["amc"], **src}
        return {"code": code, "facts": out, "order": [*FACT_KEYS, "category", "amc"]}
    return await cached_json(request, "facts", str(code), build)


@router.get("/{code}/portfolio")
async def portfolio_route(request: Request, code: int) -> Response:
    """The latest monthly portfolio (finlit.disclosure.get_portfolio) or {unavailable: reason}."""
    if not 0 < code < 10**7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")

    async def build():
        await _scheme(request, code)
        got = await _disclosure(request, "get_portfolio", code)
        return got if isinstance(got, dict) and got.get("holdings") is not None else {"unavailable": NO_PORTFOLIO if got is None else "No portfolio is published for this scheme in the sources loaded."}
    return await cached_json(request, "portfolio", str(code), build)


@router.get("/{code}")
async def detail(request: Request, code: int) -> Response:
    if not 0 < code < 10**7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")
    store = request.app.state.store
    try:
        await store.redis.hincrby(OPENS_KEY, str(code), 1)   # feeds the fallback hot ranking
    except Exception:
        pass
    try:
        hot = await store.redis.get(f"mf:hot:d:{code}")   # a hot scheme: finished page, no database work
    except Exception:
        hot = None
    if hot is not None:
        return Response(content=hot, media_type="application/json", headers={"Cache-Control": CACHE_HEADER, "ETag": etag_for(hot), "X-MF-Path": "hot"})

    async def build():
        return await detail_payload(request.app, await _scheme(request, code))
    return await cached_json(request, "detail", str(code), build)


# ====================================================================================== command line (local runs)

async def _main(argv: List[str]) -> int:
    """python -m finlit.mf refresh | backfill [--amc ID_OR_NAME|all] [--force] | rebuild   (uses DATABASE_URL / REDIS_URL like the worker)"""
    import argparse
    from .config import get_settings
    from .store import Store
    p = argparse.ArgumentParser(prog="finlit.mf")
    p.add_argument("cmd", choices=["refresh", "backfill", "rebuild"])
    p.add_argument("--amc", default="all")
    p.add_argument("--force", action="store_true")
    a = p.parse_args(argv)
    settings = get_settings()
    store = await Store.connect(settings, migrate=True)
    try:
        out = await (refresh(store, settings) if a.cmd == "refresh" else backfill(store, settings, amc=a.amc, force=a.force) if a.cmd == "backfill" else rebuild(store))
        print(json.dumps(out, indent=1, default=str))
    finally:
        await store.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main(sys.argv[1:])))
