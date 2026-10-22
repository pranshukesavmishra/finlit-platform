"""The one common shape every parser produces, and the validator that decides whether a parsed file may be stored.

Percentages are kept exactly as published: a file that gives fractions (0.0148 for 1.48 %) is scaled by 100 once and rounded to 6 decimals only to
remove floating-point noise, never to round a published figure.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional

ASSET_CLASSES = ("equity", "debt", "cash", "other")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

# Tolerances, stated once (they are quoted in SOURCES.md):
GRAND_TOTAL_TOL = 0.5          # the file's own published total must be within 0.5 percentage points of 100
SUM_TOL_BASE = 0.1             # the parsed rows must add up to the published total within 0.1 + 0.002 per row (rounding of many small rows), at most 1.0
SUM_TOL_PER_ROW = 0.002
NO_TOTAL_TOL = 1.0             # a file with no published total: rows must add up to 100 within 1.0 + 0.002 per row, at most 2.0
BAD_ISIN_SHARE = 0.05          # more than 5 % of rows with a failing ISIN means the columns were misread: the file is refused


def isin_ok(s: Optional[str]) -> bool:
    """12 characters, country letters, and the ISO 6166 check digit (Luhn over the letters expanded to numbers)."""
    if not s or not ISIN_RE.match(s):
        return False
    digits = "".join(str(int(ch, 36)) for ch in s)
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


@dataclass
class Holding:
    name: str
    isin: Optional[str]
    sector: Optional[str]            # the industry, for equity rows; None for debt rows (the column holds a rating there)
    asset_class: str                 # equity | debt | cash | other
    pct_nav: float                   # percent of net assets as published (100 = whole fund)
    qty: Optional[float] = None
    value_lakh: Optional[float] = None


@dataclass
class Portfolio:
    scheme_key: str                  # AMFI scheme code or ETF ISIN once resolved; the parsers fill it with the scheme's published name
    as_of: date
    source_name: str
    source_url: str
    holdings: List[Holding] = field(default_factory=list)
    scheme_name: str = ""
    net_assets_lakh: Optional[float] = None     # the file's own GRAND TOTAL / net assets, rupees lakh
    published_total_pct: Optional[float] = None
    benchmark: Optional[str] = None
    notes: List[str] = field(default_factory=list)   # things the validator or parser wants the report to show
    aliases: List[str] = field(default_factory=list)  # other names the file gives the scheme ('formerly known as ...'), used only to match it to AMFI's list


@dataclass
class Fact:
    """One fact with its own date and source, or an explicit reason it is unavailable."""
    value: object = None
    as_of: Optional[date] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    unavailable: Optional[str] = None

    def json(self) -> dict:
        if self.unavailable or self.value is None:
            return {"unavailable": self.unavailable or "Not published in the sources loaded."}
        out = {"value": self.value, "asOf": self.as_of.isoformat() if self.as_of else None, "source": self.source}
        if self.source_url:
            out["sourceUrl"] = self.source_url
        return out


@dataclass
class Facts:
    aum: Fact = field(default_factory=Fact)
    aum_date: Optional[date] = None
    ter_regular: Fact = field(default_factory=Fact)
    ter_direct: Fact = field(default_factory=Fact)
    ter_date: Optional[date] = None
    exit_load_text: Fact = field(default_factory=Fact)
    benchmark: Fact = field(default_factory=Fact)
    managers: Fact = field(default_factory=Fact)
    riskometer: Fact = field(default_factory=Fact)
    launch_date: Fact = field(default_factory=Fact)
    min_investment: Fact = field(default_factory=Fact)


@dataclass
class Verdict:
    ok: bool
    problems: List[str]
    warnings: List[str]
    total_pct: float = 0.0


DERIVATIVE = re.compile(r"\b(futures?|fut|options?|swaps?|irs|fra|short)\b", re.I)


def validate(p: Portfolio, today: Optional[date] = None) -> Verdict:
    """Decide whether a parsed portfolio may be stored. Every failure is a plain sentence for the report; nothing is 'fixed' silently."""
    problems: List[str] = []
    warnings: List[str] = []
    today = today or date.today()
    hs = p.holdings
    if not p.scheme_name:
        problems.append("no scheme name found in the file")
    if not hs:
        problems.append("no holdings parsed (header or rows not recognised)")
        return Verdict(False, problems, warnings)
    if not (date(2015, 1, 1) <= p.as_of <= today):
        problems.append(f"date {p.as_of} is outside 2015-01-01..{today}")
    bad_isin = 0
    for h in hs:
        if h.asset_class not in ASSET_CLASSES:
            problems.append(f"unknown asset class {h.asset_class!r} on {h.name!r}")
        if h.pct_nav is None or isinstance(h.pct_nav, bool) or not isinstance(h.pct_nav, (int, float)) or math.isnan(h.pct_nav):
            problems.append(f"percent is not a number on {h.name!r}")
            continue
        if h.pct_nav < 0 and h.asset_class in ("equity", "debt") and not DERIVATIVE.search(h.name or ""):
            problems.append(f"negative percent {h.pct_nav} on {h.asset_class} row {h.name!r}")   # a short future / swap leg is negative by nature
        if h.pct_nav > 110.0:
            problems.append(f"percent {h.pct_nav} above 110 on {h.name!r}")
        elif h.pct_nav > 101.0:
            warnings.append(f"percent {h.pct_nav} above 101 on {h.name!r} (a fund of funds with negative cash can hold slightly more than its net assets)")
        if h.isin is not None and not isin_ok(h.isin) and h.asset_class in ("equity", "debt"):
            bad_isin += 1
        if h.qty is not None and h.qty < 0 and h.asset_class in ("equity", "debt"):
            warnings.append(f"negative quantity on {h.name!r}")
    n_isin = sum(1 for h in hs if h.asset_class in ("equity", "debt"))
    if bad_isin > BAD_ISIN_SHARE * n_isin:
        problems.append(f"{bad_isin} of {n_isin} equity/debt ISINs fail the check digit (more than {int(BAD_ISIN_SHARE * 100)} %): columns misread")
    if bad_isin:
        warnings.append(f"{bad_isin} equity/debt ISIN(s) failed the check digit; they are dropped from their rows when stored")
    total = sum(h.pct_nav for h in hs if isinstance(h.pct_nav, (int, float)) and not math.isnan(h.pct_nav))
    n = len(hs)
    if p.published_total_pct is not None:
        if abs(p.published_total_pct - 100.0) > GRAND_TOTAL_TOL:
            problems.append(f"the file's own total is {p.published_total_pct:.4f} %, not about 100 (tolerance {GRAND_TOTAL_TOL})")
        tol = min(1.0, SUM_TOL_BASE + SUM_TOL_PER_ROW * n)
        if abs(total - p.published_total_pct) > tol:
            problems.append(f"parsed rows add up to {total:.4f} % but the file's total is {p.published_total_pct:.4f} % (tolerance {tol:.2f}): rows missing or double counted")
    else:
        tol = min(2.0, NO_TOTAL_TOL + SUM_TOL_PER_ROW * n)
        if abs(total - 100.0) > tol:
            problems.append(f"parsed rows add up to {total:.4f} %, not about 100 (tolerance {tol:.2f}; the file gives no total)")
    return Verdict(not problems, problems, warnings, total)


def clean_for_store(p: Portfolio) -> int:
    """Drop (set to None) any ISIN that fails its check digit; the row itself stays as published. Returns how many were dropped."""
    n = 0
    for h in p.holdings:
        if h.isin is not None and not isin_ok(h.isin):
            h.isin = None
            n += 1
    return n
