"""Mutual funds: list, detail and compare, built on AMFI's own public files (no key, no paid service).

Sources, in order of preference
  1. https://portal.amfiindia.com/spages/NAVAll.txt  every scheme AMFI publishes (about 14,400, stopped ones included) with its latest NAV and date.
     The section header lines give the category ("Open Ended Schemes(Equity Scheme - Mid Cap Fund)"), a line below names the fund house.
  2. https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?mf=<id>&frmdt=DD-Mon-YYYY&todt=DD-Mon-YYYY  the official daily NAV history.
     It can only be asked for a whole fund house (the `scheme` parameter is ignored), about 13 MB and 9 s a year for a house of 400 schemes, so history is
     loaded one fund house at a time by `backfill`. The ids are the ones in the fund-house dropdown of amfiindia.com/net-asset-value/nav-history (AMC_IDS).
  3. https://api.mfapi.in/mf/<code>  a third-party mirror of the same AMFI data. Used only on demand, for a Growth scheme whose AMFI history has not been
     loaded (for example fund houses missing from AMFI's dropdown), and only after its newest NAV is checked against AMFI's NAVAll. The page always says so.

What is stored (the free database is small): every scheme with its latest NAV; the daily NAV series only for ACTIVE GROWTH options (Direct, Regular),
packed at ~3 bytes a point; returns, volatility and drawdown worked out when data arrives, so the list is a plain query. IDCW / dividend options are listed
with their own NAV but no returns: a payout lowers the NAV, so NAV-to-NAV change would understate what an investor earned.

Not here, on purpose: AUM, expense ratio, holdings, sector split, benchmark, manager, launch date, risk-o-meter. AMFI does not put them in the NAV files and
nothing is shown that cannot be checked against a source. This is information only, never advice.
"""

from __future__ import annotations

import array
import asyncio
import calendar
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
from .store import dumps, etag_for

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
MIRROR_TTL = 6 * 3600
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


def parse_navall(text: str) -> Parsed:
    """Parse NAVAll.txt (also the layout of the history download, minus the history-only columns). Never raises on a bad line: it is counted in `skipped`.
    Schemes without a usable NAV are still listed (nav None). A line is left out only when it has no scheme code or the wrong number of fields."""
    out = Parsed()
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
    return {"returns": trailing_returns(days, navs, complete), "vol1y": volatility(days, navs, 1, complete), "vol3y": volatility(days, navs, 3, complete),
            "mdd": max_drawdown(days, navs)}


def metric_columns(m: dict) -> Tuple[Optional[float], ...]:
    r = m["returns"]
    return (r["1m"]["value"], r["6m"]["value"], r["1y"]["value"], r["3y"]["value"], r["5y"]["value"], m["vol1y"]["value"], m["vol3y"]["value"], m["mdd"]["value"])


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
    prev_date = CASE WHEN nav_date = $10 AND $11::float8 IS NOT NULL THEN $12 ELSE prev_date END WHERE code = $1"""


async def _write_series(conn, items: List[Tuple[int, List[int], List[float], bool]]) -> None:
    """Store packed series and their worked-out numbers for (code, days, NAVs, complete) items."""
    hist, mets = [], []
    for code, days, navs, complete in items:
        days, navs = trim(days, navs)
        hist.append((code, len(days), date.fromordinal(days[0]), date.fromordinal(days[-1]), pack_series(days, navs), complete, "amfi"))
        prev = (navs[-2], date.fromordinal(days[-2])) if len(days) > 1 else (None, None)   # the NAV before the last one gives the day change
        mets.append((code, *metric_columns(metrics_for(days, navs, complete)), date.fromordinal(days[-1]), *prev))
    await conn.executemany(HIST_UPSERT, hist)
    await conn.executemany(METRICS_UPDATE, mets)


async def _meta(conn, key: str) -> Optional[dict]:
    raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def _set_meta(conn, key: str, value: dict) -> None:
    await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                       key, json.dumps(value, default=str))


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
    3. Today's NAV is appended to each stored history and the returns / volatility / drawdown are worked out again for those schemes.
    4. If whole days were missed (the job did not run), AMFI's industry-wide history for just those days fills the hole.
    `backfill_amc` (an AMC id, name or 'all') additionally loads five years of history for those fund houses: see `backfill`."""
    started = time.perf_counter()
    own = client is None
    client = client or make_client()
    try:
        text = await fetch_navall(client)
        parsed = parse_navall(text)
        async with store.pool.acquire() as conn:
            stored = await conn.fetchrow("SELECT count(*) AS n, max(nav_date) AS newest, count(*) FILTER (WHERE active) AS act FROM mf_schemes")
            why = verdict(parsed, stored["n"], stored["newest"], stored["act"])
        if why:
            log.error("mf refresh refused: %s", why)
            return {"status": "refused", "reason": why, "parsed": len(parsed.schemes), "stored": stored["n"], "skipped": parsed.skipped}
        newest = parsed.newest
        res = await apply_navall(store, parsed, newest)
        res["gapDays"] = await _repair_gaps(store, client, res.pop("_gap_since", None), newest)
        if backfill_amc:
            res["backfill"] = await backfill(store, settings, amc=backfill_amc, client=client)
        await _bump(store, newest)
        res["seconds"] = round(time.perf_counter() - started, 1)
        return res
    finally:
        if own:
            await client.aclose()


async def apply_navall(store, parsed: Parsed, newest: date) -> dict:
    """Write an accepted file (see refresh). Everything is one transaction: a failure leaves the previous data exactly as it was."""
    ss = parsed.schemes
    cols = list(zip(*[(s.code, s.name, s.isin, s.isin_reinvest, s.amc, s.scheme_type, s.category, s.plan, s.option_class, s.option_label, s.family, s.nav, s.nav_date, newest)
                      for s in ss]))
    seeded = appended = 0
    gap_since: Optional[date] = None
    async with store.pool.acquire() as conn, conn.transaction():
        before = await conn.fetchval("SELECT count(*) FROM mf_schemes")
        prev_meta = await _meta(conn, "refresh") or {}
        await conn.execute(UPSERT, *[list(c) for c in cols])
        await conn.execute("UPDATE mf_schemes SET active = (nav_date IS NOT NULL AND nav_date >= $1::date - $2::int)", newest, ACTIVE_DAYS)
        done = {r["amc_key"] for r in await conn.fetch("SELECT amc_key FROM mf_backfill")}
        # Schemes whose newest NAV is later than the last stored day of their history: append it (or, with no history row yet, start one for a
        # fund house that has had its history loaded: the scheme is new; `complete` stays false so a missing past is never called "younger").
        rows = await conn.fetch("""SELECT s.code, s.amc, s.nav, s.nav_date, h.blob, h.d0, h.d1, h.complete FROM mf_schemes s LEFT JOIN mf_history h USING (code)
                                   WHERE s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND (h.d1 IS NULL OR s.nav_date > h.d1)""")
        items = []
        for r in rows:
            nd = r["nav_date"].toordinal()
            if r["blob"] is None:
                if amc_key(r["amc"]) in done:
                    items.append((r["code"], [nd], [r["nav"]], False))
                    seeded += 1
                continue
            days, navs = unpack_series(bytes(r["blob"]), r["d0"].toordinal())
            if days[-1] == nd and navs[-1] == r["nav"]:
                continue
            if nd - days[-1] > 4 and (newest.toordinal() - nd) <= ACTIVE_DAYS:
                gap_since = min(gap_since or r["d1"], r["d1"])
            days, navs = merge_points((days, navs), ([nd], [r["nav"]]))
            items.append((r["code"], days, navs, bool(r["complete"])))
            appended += 1
        for i in range(0, len(items), 300):
            await _write_series(conn, items[i:i + 300])
        # Whole days were missed only when the previous run's newest date is itself more than 4 days old: then many schemes show the same hole.
        prev_newest = date.fromisoformat(prev_meta["navDate"]) if prev_meta.get("navDate") else None
        if not (prev_newest and (newest - prev_newest).days > 4):
            gap_since = None
        active = await conn.fetchval("SELECT count(*) FROM mf_schemes WHERE active")
        total = await conn.fetchval("SELECT count(*) FROM mf_schemes")
        with_hist = await conn.fetchval("SELECT count(*) FROM mf_history")
        res = {"status": "ok", "navDate": newest.isoformat(), "schemesInFile": len(ss), "schemesStored": total, "newSchemes": total - before, "active": active,
               "withHistory": with_hist, "historyAppended": appended, "historySeeded": seeded, "skipped": parsed.skipped,
               "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "_gap_since": gap_since}
        await _set_meta(conn, "refresh", {k: v for k, v in res.items() if not k.startswith("_")})
    return res


async def _repair_gaps(store, client, since: Optional[date], newest: date) -> int:
    """Fill NAV days a missed run left out, from AMFI's history for every fund house, 20 days at a time (about 15 MB each). Returns the days covered."""
    if since is None:
        return 0
    start, covered = since + timedelta(days=1), 0
    async with store.pool.acquire() as conn:
        wanted = {r["code"] for r in await conn.fetch(f"SELECT code FROM mf_schemes WHERE {HIST_WANTED} AND has_hist")}
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
    await _bump(store, None)
    return n


# ====================================================================================== history backfill (separate, resumable)

async def backfill(store, settings=None, amc: Optional[str] = "all", *, client: Optional[httpx.AsyncClient] = None, force: bool = False,
                   log_fn=print) -> dict:
    """Load five years of NAV history from AMFI for the active Growth schemes, ONE FUND HOUSE AT A TIME (AMFI cannot filter below a fund house).
    `amc` is an AMC id, part of a name, or 'all' (every house not done yet; `force` redoes them). A house is written only when all its yearly downloads
    succeeded, then recorded in mf_backfill, so an interrupted run simply continues. Cost for the whole industry: see the figures logged per house."""
    own = client is None
    client = client or make_client()
    out: Dict[str, object] = {"done": [], "skipped": [], "failed": [], "points": 0, "bytes": 0}
    try:
        async with store.pool.acquire() as conn:
            newest = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes")
            rows = await conn.fetch(f"SELECT code, amc, nav, nav_date FROM mf_schemes WHERE {HIST_WANTED}")
            done = {r["amc_key"] for r in await conn.fetch("SELECT amc_key FROM mf_backfill")}
        if newest is None:
            return {**out, "status": "empty", "reason": "no schemes stored yet: run refresh first"}
        by_amc: Dict[str, List[dict]] = {}
        names: Dict[str, str] = {}
        for r in rows:
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
        if out["done"]:
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
        items, points, mismatches = [], 0, 0
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
        for i in range(0, len(items), 200):
            await _write_series(conn, items[i:i + 200])
        await conn.execute("INSERT INTO mf_backfill (amc_key, amc, amc_id, schemes, points, bytes, note) VALUES ($1, $2, $3, $4, $5, $6, $7) "
                           "ON CONFLICT (amc_key) DO UPDATE SET amc = EXCLUDED.amc, amc_id = EXCLUDED.amc_id, schemes = EXCLUDED.schemes, points = EXCLUDED.points, "
                           "bytes = EXCLUDED.bytes, note = EXCLUDED.note, done_at = now()",
                           key, name, amc_id, len(items), points, total_bytes, f"{ok_windows} yearly downloads; {mismatches} newest-NAV mismatches against NAVAll")
    return {"amc": name, "schemes": len(items), "points": points, "bytes": total_bytes, "mismatches": mismatches, "windows": ok_windows}


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


async def mirror_series(app, row: dict) -> Optional[Tuple[List[int], List[float]]]:
    """The mirror's history for a scheme, only if its newest NAV agrees with AMFI's own latest NAV for the same day (else it is not used). Cached six hours."""
    code = row["code"]
    redis = app.state.store.redis
    key = f"mf:mirror:{code}"
    try:
        hit = await redis.get(key)
    except Exception:
        hit = None
    if hit is not None:
        raw = json.loads(hit)
        return (raw["d"], raw["v"]) if raw else None
    series = None
    try:
        client = getattr(app.state, "mf_client", None)
        if client is None:
            client = app.state.mf_client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0), follow_redirects=True, headers={"User-Agent": USER_AGENT})
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
        await redis.set(key, json.dumps({"d": series[0], "v": series[1]} if series else None), ex=MIRROR_TTL if series else 600)
    except Exception:
        pass
    return series


# ====================================================================================== API

LIST_COLS = "code, name, amc, category, scheme_type, plan, option_class, option_label, nav, nav_date, prev_nav, prev_date, active, has_hist, r1m, r6m, r1y, r3y, r5y, vol1y, vol3y, mdd, metrics_date"
SORTS = {"name": "name", "amc": "amc", "category": "category", "nav": "nav", "navDate": "nav_date", "r1m": "r1m", "r6m": "r6m", "r1y": "r1y", "r3y": "r3y", "r5y": "r5y",
         "vol1y": "vol1y", "vol3y": "vol3y", "mdd": "mdd", "change": "(CASE WHEN prev_nav > 0 THEN nav / prev_nav - 1 END)"}
PLANS = ("Direct", "Regular", "Unspecified")
OPTIONS = ("Growth", "IDCW", "Other")
RANGE_KEYS = {"1y": "r1y", "3y": "r3y", "5y": "r5y"}


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
    if row["r1m"] is not None or row["r6m"] is not None or row["r1y"] is not None or row["r3y"] is not None or row["r5y"] is not None:
        return None
    if not row["active"]:
        return "stopped"
    if row["option_class"] == "IDCW":
        return "idcw"
    if row["option_class"] != "Growth":
        return "unstated"
    return "no_history" if not row["has_hist"] else "short"


def list_item(r) -> dict:
    ch = day_change(r)
    return {"code": r["code"], "name": r["name"], "amc": r["amc"], "category": r["category"], "plan": r["plan"], "option": r["option_label"], "optionClass": r["option_class"],
            "nav": r["nav"], "navDate": iso(r["nav_date"]), "change": ch["pct"] if ch else None, "active": r["active"],
            "r1m": rnd(r["r1m"]), "r6m": rnd(r["r6m"]), "r1y": rnd(r["r1y"]), "r3y": rnd(r["r3y"]), "r5y": rnd(r["r5y"]),
            "vol1y": rnd(r["vol1y"]), "vol3y": rnd(r["vol3y"]), "mdd": rnd(r["mdd"]), "noReturns": why_no_returns(r)}


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
    if etag in (request.headers.get("if-none-match") or ""):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


async def _facts(conn) -> dict:
    """The data date and last-updated time every page shows."""
    ref = await _meta(conn, "refresh") or {}
    newest = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes WHERE active")
    return {"dataDate": iso(newest) or ref.get("navDate"), "updatedAt": ref.get("at"), "source": SOURCE, "disclaimer": DISCLAIMER}


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
                     plan: str = Query("", max_length=20), option: str = Query("", max_length=20), stopped: bool = False,
                     min1y: Optional[float] = Query(None, ge=-100, le=100000), max1y: Optional[float] = Query(None, ge=-100, le=100000),
                     min3y: Optional[float] = Query(None, ge=-100, le=100000), max3y: Optional[float] = Query(None, ge=-100, le=100000),
                     min5y: Optional[float] = Query(None, ge=-100, le=100000), max5y: Optional[float] = Query(None, ge=-100, le=100000),
                     sort: str = Query("", max_length=12), dir: str = Query("asc", pattern="^(asc|desc)$"),
                     page: int = Query(1, ge=1, le=2000), size: int = Query(50, ge=1, le=PAGE_MAX)) -> Response:
    """Schemes, filtered and sorted on the server (about 14,000 exist). The count is exact for the filters given. Without a chosen sort the order is by relevance
    when searching, otherwise A to Z. Schemes that stopped publishing NAVs are left out unless `stopped=true`."""
    if plan and plan not in PLANS or option and option not in OPTIONS:
        raise fail(400, "bad_request", "Unknown plan or option.")
    if sort and sort not in SORTS:
        raise fail(400, "bad_request", "Unknown sort column.")
    key = json.dumps([q.strip().lower(), category, amc, plan, option, stopped, min1y, max1y, min3y, max3y, min5y, max5y, sort, dir, page, size])

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
        for col, v in (("category", category), ("amc", amc), ("plan", plan), ("option_class", option)):
            if v:
                where.append(f"{col} = {arg(v)}")
        for col, lo, hi in (("r1y", min1y, max1y), ("r3y", min3y, max3y), ("r5y", min5y, max5y)):
            if lo is not None:
                where.append(f"{col} >= {arg(lo)}")
            if hi is not None:
                where.append(f"{col} <= {arg(hi)}")
        w = ("WHERE " + " AND ".join(where)) if where else ""
        if sort:
            order = f"{SORTS[sort]} {'DESC' if dir == 'desc' else 'ASC'} NULLS LAST, name, code"
        elif order_codes is not None:
            order = f"array_position({codes_ph}::int[], code)"
        else:
            order = "name, code"
        async with store.pool.acquire() as conn:
            total = await conn.fetchval(f"SELECT count(*) FROM mf_schemes {w}", *args)
            rows = await conn.fetch(f"SELECT {LIST_COLS} FROM mf_schemes {w} ORDER BY {order} LIMIT {size} OFFSET {(page - 1) * size}", *args)
            facts = await _facts(conn)
        return {"total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size)), "items": [list_item(r) for r in rows], **facts}
    return await cached_json(request, "list", key, build)


@router.get("/filters")
async def filters(request: Request) -> Response:
    """Categories and fund houses with how many schemes each has (active ones, and all), plus plan and option counts, for the filter menus."""
    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            cats = await conn.fetch("SELECT category, scheme_type, count(*) FILTER (WHERE active) AS active, count(*) AS total FROM mf_schemes GROUP BY 1, 2 ORDER BY 1, 2")
            amcs = await conn.fetch("SELECT amc, count(*) FILTER (WHERE active) AS active, count(*) AS total FROM mf_schemes GROUP BY 1 ORDER BY 1")
            plans = await conn.fetch("SELECT plan, count(*) FILTER (WHERE active) AS active FROM mf_schemes GROUP BY 1")
            opts = await conn.fetch("SELECT option_class, count(*) FILTER (WHERE active) AS active FROM mf_schemes GROUP BY 1")
            tot = await conn.fetchrow("SELECT count(*) AS total, count(*) FILTER (WHERE active) AS active, count(*) FILTER (WHERE has_hist) AS hist FROM mf_schemes")
            facts = await _facts(conn)
        merged: Dict[str, dict] = {}
        for c in cats:   # one category can appear under two scheme types (rare); the filter is by category text, so counts add up
            m = merged.setdefault(c["category"], {"name": c["category"], "group": category_group(c["category"]), "type": c["scheme_type"], "active": 0, "total": 0})
            m["active"] += c["active"]
            m["total"] += c["total"]
        return {"categories": list(merged.values()), "amcs": [{"name": a["amc"], "active": a["active"], "total": a["total"]} for a in amcs],
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
        return [], [], False, "none", "NAV history is not loaded for this scheme yet."
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
        return "NAV history for this scheme is not loaded yet."
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
    risk = risk_json(m) if m else {"vol1y": {"value": None, "why": empty["why"]}, "vol3y": {"value": None, "why": empty["why"]}, "maxDrawdown": {"value": None, "why": empty["why"], "peak": None, "trough": None, "since": None}}
    return {"code": row["code"], "name": row["name"], "isin": row["isin"], "isinReinvest": row["isin_reinvest"], "amc": row["amc"], "category": row["category"],
            "categoryGroup": category_group(row["category"]), "schemeType": row["scheme_type"], "plan": row["plan"], "optionClass": row["option_class"], "option": row["option_label"],
            "active": row["active"], "nav": row["nav"], "navDate": iso(row["nav_date"]), "prevNav": row["prev_nav"], "prevDate": iso(row["prev_date"]), "change": day_change(row),
            "returns": ret, "risk": risk, "returnsNote": returns_note(row, source, bool(days)) if not m else None,
            "series": series_block(days, navs) if m else {},
            "history": {"source": source if days else None, "from": iso(date.fromordinal(days[0])) if days else None, "to": iso(date.fromordinal(days[-1])) if days else None,
                        "points": len(days), "complete": complete, "note": note if source != "amfi" else None},
            "family": [{"code": k["code"], "name": k["name"], "plan": k["plan"], "optionClass": k["option_class"], "option": k["option_label"], "nav": k["nav"],
                        "navDate": iso(k["nav_date"]), "active": k["active"]} for k in kin],
            "notAvailable": NOT_AVAILABLE, **facts}


async def _scheme(request: Request, code: int):
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow(f"SELECT {LIST_COLS}, isin, isin_reinvest, family FROM mf_schemes WHERE code = $1", code)
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
            ret = returns_json(m) if m else {k: {"value": None, "kind": "cagr" if mo > 12 else "absolute", "from": None, "why": empty} for k, mo, _ in HORIZONS}
            risk = risk_json(m) if m else {"vol1y": {"value": None, "why": empty}, "vol3y": {"value": None, "why": empty}, "maxDrawdown": {"value": None, "why": empty, "peak": None, "trough": None, "since": None}}
            start = None   # index of the NAV the range starts from; None when this fund's history does not reach back that far
            if ok and len(days) > 1:
                start = 0 if range == "MAX" else bisect_right(days, shift_months(date.fromordinal(days[-1]), dict(RANGES)[range]).toordinal()) - 1
                start = start if start >= 0 else None
            spans.append((days, navs, start))
            funds.append({"code": r["code"], "name": r["name"], "amc": r["amc"], "category": r["category"], "plan": r["plan"], "option": r["option_label"], "optionClass": r["option_class"],
                          "nav": r["nav"], "navDate": iso(r["nav_date"]), "change": day_change(r), "active": r["active"], "returns": ret, "risk": risk,
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


@router.get("/{code}")
async def detail(request: Request, code: int) -> Response:
    if not 0 < code < 10**7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")

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
