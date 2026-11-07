"""Finding each company's annual report with no manual input (docs/COMPANY-BRIEF.md, "Annual report discovery").

Order: the administrator's override (never overwritten) > the exchange listings. NSE's public annual-reports listing first (it needs the session cookie its home
page sets, the same dance as the FII/DII and earnings-call jobs), BSE's listing as the fallback. Only addresses the exchanges themselves list are ever used: an
address is never built from a guess. The company's own website is NOT crawled (a crawler would be guessing); an administrator can still set it as the override.
The response shapes are written from the public listings and are UNVERIFIED from this build machine: parsing is defensive and a surprise is "none"/"error", never an invented URL.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlsplit

from ..earnings import transcripts as T

log = logging.getLogger("finlit.company_brief.discovery")
NSE_AR = "https://www.nseindia.com/api/annual-reports?index=equities&symbol={symbol}"
BSE_AR = "https://api.bseindia.com/BseIndiaAPI/api/AnnualReport_New/w?scripcode={code}"
BSE_FILES = "https://www.bseindia.com/bseplus/AnnualReport/{code}/{file}"
PDF = re.compile(r"\.pdf(?:$|[?#])", re.I)


def _year(*vals: Any) -> Optional[int]:
    """The year the financial year ENDS in, from 'toYr' (2025), 'FY 2024-25' or 'Year' (2025)."""
    for v in vals:
        m2 = re.search(r"(?<!\d)(20\d{2})\s*-\s*(\d{2})(?!\d)", str(v or ""))
        if m2:
            return int(m2.group(1)[:2] + m2.group(2))
        m = re.findall(r"(?<!\d)(20\d{2}|19\d{2})(?!\d)", str(v or ""))
        if m:
            return int(m[-1])
    return None


def parse_nse(payload: Any) -> List[Tuple[int, str]]:
    """(year, pdf address) for each report in NSE's listing. Only https PDFs on the exchange's own hosts."""
    rows = payload.get("data") if isinstance(payload, dict) else payload
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        url = str(r.get("fileName") or r.get("attchmntFile") or r.get("link") or "").strip()
        y = _year(r.get("toYr"), r.get("year"), r.get("financialYear"))
        if y is None and str(r.get("fromYr") or "").isdigit():
            y = int(str(r["fromYr"])[:4]) + 1
        if y and ok_url(url):
            out.append((y, url))
    return out


def parse_bse(payload: Any, code: str) -> List[Tuple[int, str]]:
    rows = payload.get("Table") if isinstance(payload, dict) else payload
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        f = str(r.get("PDFDownload") or r.get("pdfDownload") or r.get("FileName") or "").strip()
        if not f or "/" in f.replace("https://", "", 1) and not f.startswith("https://"):
            continue
        url = f if f.startswith("https://") else BSE_FILES.format(code=quote(code, safe=""), file=quote(f, safe=""))
        y = _year(r.get("Year"), r.get("year"), r.get("FinancialYear"))
        if y and ok_url(url):
            out.append((y, url))
    return out


def ok_url(url: str) -> bool:
    p = urlsplit(url or "")
    return p.scheme == "https" and bool(p.hostname) and bool(T.HOST_OK.match(p.hostname)) and p.port in (None, 443) and bool(PDF.search(url)) and len(url) < 500


def latest(rows: List[Tuple[int, str]]) -> Optional[Tuple[int, str]]:
    return max(rows, key=lambda r: (r[0], r[1])) if rows else None


def from_feed(rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The newest annual report among the exchange announcements the site already stores (feed_items: kind 'document', 'annual report' in the title or category).
    Needs no request to the exchanges: NSE and BSE answer the AWS server's listing requests with 403 (even through the relay), but the announcements come from the
    data provider and the PDFs themselves download fine. Only https PDFs on the exchanges' own hosts. The year is the one the financial year ends in: a report filed
    from April on is for the year ending that March; filed January to March, for the year before. None when no stored announcement qualifies."""
    best: Optional[Tuple[Any, str]] = None
    for r in rows or []:
        when, url = r.get("item_date"), str(r.get("link") or "").strip()
        text = f"{r.get('title') or ''} {r.get('category') or ''}".lower()
        if when is None or "annual report" not in text or not ok_url(url):
            continue
        if best is None or when > best[0]:
            best = (when, url)
    if best is None:
        return None
    when, url = best
    year = when.year if when.month >= 4 else when.year - 1
    return {"state": "found", "url": url, "year": year, "source": "feed", "detail": f"from the stored exchange announcements of {when.isoformat()}"}


async def discover(fetcher, symbol: str, bse_code: Optional[str] = None) -> Dict[str, Any]:
    """{'state': found|none|blocked|error, 'url', 'year', 'source', 'detail'}. NSE first, then BSE. Never raises."""
    detail: List[str] = []
    asked = 0
    for source in ("nse", "bse"):
        try:
            if source == "nse":
                rows = parse_nse(await fetcher.nse_annual_reports(symbol))
            elif bse_code and str(bse_code).isdigit():
                rows = parse_bse(await fetcher.bse_annual_reports(str(bse_code)), str(bse_code))
            else:
                detail.append("bse: no BSE code on file")
                continue
            asked += 1
        except T.BudgetSpent:
            return {"state": "error", "detail": "request budget spent", "source": None, "url": None, "year": None, "budget": True}
        except T.Blocked as e:
            detail.append(f"{source}: blocked ({e})")
            continue
        except T.FetchFailed as e:
            detail.append(f"{source}: {e}")
            continue
        best = latest(rows)
        if best:
            return {"state": "found", "url": best[1], "year": best[0], "source": source, "detail": "; ".join(detail)}
        detail.append(f"{source}: no annual report listed")
    needed = 1 + (1 if bse_code and str(bse_code).isdigit() else 0)
    state = "none" if asked >= needed else "blocked" if any("blocked" in d for d in detail) else "error"
    return {"state": state, "url": None, "year": None, "source": None, "detail": "; ".join(detail)}
