"""AMFI's public data, read from its own endpoints (no key). Each parser takes the raw answer and returns plain rows; nothing here touches the network or database.

  scheme master   https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0        CSV: launch date, minimum amount, per AMFI scheme code
  fund performance  POST https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance   JSON per sub-category: benchmark, risk-o-meter, AUM (crore)
  TER             https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID=..&Month=MM-YYYY..   JSON, one row per scheme per day: regular and direct TER
  average AUM     https://www.amfiindia.com/api/average-aum-schemewise?strType=Typewise&fyId=1&periodId=1   JSON, per AMFI scheme code, rupees lakh, quarterly average
  NSE equity list https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv     CSV: NSE symbol and ISIN of every listed share
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Dict, Iterable, List, Optional, Tuple

from .model import isin_ok

MONTH3 = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}


def parse_dmy(s: str) -> Optional[date]:
    """'19-Oct-2026' or '2026-10-19T00:00:00.000Z'."""
    s = (s or "").strip()
    m = re.match(r"^(\d{1,2})-([A-Za-z]{3})[a-z]*-(\d{4})$", s)
    if m and m.group(2).lower() in MONTH3:
        try:
            return date(int(m.group(3)), MONTH3[m.group(2).lower()], int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def fnum(v) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------ scheme master

@dataclass
class MasterRow:
    code: int
    launch: Optional[date]
    closure: Optional[date]
    min_text: str


def parse_scheme_master(text: str) -> List[MasterRow]:
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if not rows or [c.strip().lower() for c in rows[0][:3]] != ["amc", "code", "scheme name"]:
        return []
    out: List[MasterRow] = []
    for r in rows[1:]:
        if len(r) < 9 or not r[1].strip().isdigit():
            continue
        out.append(MasterRow(int(r[1]), parse_dmy(r[7]), parse_dmy(r[8]), r[6].strip()))
    return out


def min_amount(text: str) -> Optional[float]:
    """The first rupee amount in AMFI's free-text minimum ('Rs. 5000/- and in multiples of Re. 1', '5000/-', '500'). None for 'REFER SID' and the like."""
    t = text.strip()
    if not t or re.search(r"refer|sid|\bnil\b|not\s+applicable", t, re.I):
        return None
    m = re.search(r"(?:rs\.?|₹|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", t, re.I)
    if not m:
        return None
    v = fnum(m.group(1))
    return v if v and v > 0 else None


# ------------------------------------------------------------------------------------------ fund performance

@dataclass
class PerfRow:
    name: str
    benchmark: Optional[str]
    risk_scheme: Optional[str]
    risk_benchmark: Optional[str]
    nav_date: Optional[date]
    aum_crore: Optional[float]


def parse_performance(payload: dict) -> List[PerfRow]:
    if not isinstance(payload, dict) or payload.get("validationStatus") != "SUCCESS":
        return []
    out: List[PerfRow] = []
    for r in payload.get("data") or []:
        if not isinstance(r, dict) or not r.get("schemeName"):
            continue
        out.append(PerfRow(str(r["schemeName"]).strip(), (r.get("benchmark") or "").strip() or None, (r.get("riskometerScheme") or "").strip() or None,
                           (r.get("riskometerBenchmark") or "").strip() or None, parse_dmy(r.get("navDate") or ""), fnum(r.get("dailyAUM"))))
    return out


# ------------------------------------------------------------------------------------------ TER

@dataclass
class TerRow:
    name: str
    regular: Optional[float]
    direct: Optional[float]
    day: Optional[date]
    nsdl_code: str


def parse_ter_rows(rows: Iterable[dict]) -> List[TerRow]:
    out: List[TerRow] = []
    for r in rows:
        if not isinstance(r, dict) or not r.get("Scheme_Name"):
            continue
        out.append(TerRow(str(r["Scheme_Name"]).strip(), fnum(r.get("R_TER")), fnum(r.get("D_TER")), parse_dmy(str(r.get("TER_Date") or "")), str(r.get("NSDLSchemeCode") or "")))
    return out


def latest_ter(rows: Iterable[TerRow]) -> Dict[Tuple[str, str], TerRow]:
    """The newest day's row for each scheme (name and NSDL code)."""
    best: Dict[Tuple[str, str], TerRow] = {}
    for r in rows:
        if r.day is None:
            continue
        k = (r.nsdl_code, r.name)
        if k not in best or r.day > best[k].day:
            best[k] = r
    return best


# ------------------------------------------------------------------------------------------ average AUM

def parse_period_end(label: str) -> Optional[date]:
    """'July - September 2026' -> 2026-09-30."""
    m = re.match(r"^\s*([A-Za-z]+)\s*-\s*([A-Za-z]+)\s+(\d{4})\s*$", label or "")
    if not m or m.group(2)[:3].lower() not in MONTH3:
        return None
    mon, yr = MONTH3[m.group(2)[:3].lower()], int(m.group(3))
    nxt = date(yr + (mon == 12), mon % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def parse_average_aum(payload: dict) -> Tuple[Optional[str], Optional[date], Dict[int, float]]:
    """(period label, period end, {AMFI code: average AUM in rupees lakh}). A fund-of-funds' domestic AUM sits in its own column; the two are added."""
    if not isinstance(payload, dict):
        return None, None, {}
    label = payload.get("selectedPeriod")
    out: Dict[int, float] = {}
    for amc in payload.get("data") or []:
        for s in amc.get("schemes") or []:
            code = s.get("AMFI_Code")
            a = s.get("AverageAumForTheMonth") or {}
            vals = [fnum(a.get("ExcludingFundOfFundsDomesticButIncludingFundOfFundsOverseas")), fnum(a.get("FundOfFundsDomestic"))]
            if isinstance(code, int) and any(v is not None for v in vals):
                out[code] = out.get(code, 0.0) + sum(v for v in vals if v is not None)
    return label, parse_period_end(label or ""), out


# ------------------------------------------------------------------------------------------ NSE list

def parse_equity_list(text: str) -> Dict[str, str]:
    """{ISIN: NSE symbol} from EQUITY_L.csv; rows whose ISIN fails the check digit are left out."""
    out: Dict[str, str] = {}
    rd = csv.reader(io.StringIO(text.lstrip("﻿")))
    head = next(rd, None)
    if not head:
        return out
    cols = [h.strip().upper() for h in head]
    if "SYMBOL" not in cols or "ISIN NUMBER" not in cols:
        return out
    si, ii = cols.index("SYMBOL"), cols.index("ISIN NUMBER")
    for r in rd:
        if len(r) > max(si, ii):
            sym, isin = r[si].strip().upper(), r[ii].strip().upper()
            if sym and isin_ok(isin):
                out[isin] = sym
    return out
