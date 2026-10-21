"""Where each fund house publishes its SEBI-mandated monthly portfolio, and how to list the files for a month. Each adapter only LISTS files (small requests);
downloading and parsing happen one file at a time in finlit/disclosure.py. Every URL pattern here was fetched from the development sandbox (see SOURCES.md).

An adapter returns FileRef(url, month_end, name_hint). It never raises for 'not published yet' (an empty list), only for a site that fails or answers oddly.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx

from .sebi import parse_date_text

UA = "Mozilla/5.0 (compatible; FinLitVentures/1.0; +https://finlitventures.com)"
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 FinLitVentures/1.0"
MAX_BYTES = 60 * 1024 * 1024


@dataclass
class FileRef:
    amc: str
    url: str
    month_end: Optional[date]          # the month the listing says the file is for (the file's own date is what is stored)
    name_hint: Optional[str] = None    # scheme name from the listing, for houses that publish one file per scheme
    label: str = ""


def month_ends(today: date, n: int = 3) -> List[date]:
    """The last n month-ends strictly before today, newest first."""
    out: List[date] = []
    y, m = today.year, today.month
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(date(y, m, calendar.monthrange(y, m)[1]))
    return out


def _eom(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


async def get_text(client: httpx.AsyncClient, url: str, **kw) -> str:
    r = await client.get(url, **kw)
    r.raise_for_status()
    return r.text


# -------------------------------------------------------------------------------------------------------------- Mirae Asset
MIRAE_API = "https://www.miraeassetmf.co.in/AjaxService/GetDownloadsData"
MIRAE_BASE = "https://www.miraeassetmf.co.in"


async def list_mirae(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One xlsx per scheme, listed (newest first, 10 000 characters of JSON a page) by the site's own download-list service."""
    wanted = {(m.year, m.month) for m in months}
    oldest = min(months)
    out: List[FileRef] = []
    page = 1
    while page <= 8:
        r = await client.post(MIRAE_API, json={"request": {"modulename": "portfolio_tab1", "pgno": page, "pgsize": 100}},
                              headers={"X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        j = r.json()
        if str(j.get("ReturnCode")) != "0":
            break
        data = j.get("Data") or []
        if not data:
            break
        stop = False
        for it in data:
            title = it.get("Title") or ""
            d = parse_date_text(title)
            m = re.search(r"\bfor\s+(.+)$", title, re.I)
            url = it.get("URL") or ""
            if not d or not m or not url:
                continue
            if _eom(d) < _eom(oldest):
                stop = True
                continue
            if (d.year, d.month) in wanted and url.lower().split("?")[0].endswith((".xlsx", ".xls")):
                out.append(FileRef("mirae", urljoin(MIRAE_BASE, url), d, m.group(1).strip(), title))
        if stop:
            break
        page += 1
    return out


# -------------------------------------------------------------------------------------------------------------- Invesco
INV_API = "https://www.invescomutualfund.com/api/CompleteMonthlyHoldings"
INV_CLASSES = ("equity", "hybrid", "fixed-income", "index-funds", "fund-of-funds")
MON_KEYS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


async def list_invesco(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    out: List[FileRef] = []
    for cls in INV_CLASSES:
        for yr in sorted({m.year for m in months}):
            r = await client.get(INV_API, params={"year": yr, "classification": cls})
            r.raise_for_status()
            rows = r.json()
            if not isinstance(rows, list):
                continue
            for row in rows:
                nm = re.sub(r"\s+", " ", str(row.get("Name") or "")).strip()
                for m in months:
                    if m.year != yr:
                        continue
                    url = (row.get(MON_KEYS[m.month - 1] + "Url") or "").strip()
                    if nm and url.lower().split("?")[0].endswith((".xlsx", ".xls")):
                        out.append(FileRef("invesco", url, m, nm, f"{nm} {m:%b %Y}"))
    return out


# -------------------------------------------------------------------------------------------------------------- DSP
DSP_PAGE = "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures"
_DSP_HREF = re.compile(r'https://www\.dspim\.com/media/pages/mandatory-disclosures/portfolio-disclosures/[^"\'<> ]+', re.I)


def dsp_file_date(filename: str) -> Optional[date]:
    t = unquote(filename).lower().rsplit(".", 1)[0]
    t = re.sub(r"[_\-]+", " ", t)
    t = re.sub(r"(\d)([a-z])", r"\1 \2", t)
    t = re.sub(r"([a-z])(\d)", r"\1 \2", t)
    return parse_date_text(t)


async def list_dsp(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """The page lists every file DSP has published since 2013 as plain links; the month-end bundles are 'monthend-portfolio...zip' (equity/hybrid workbook
    plus the debt workbook, one sheet per scheme)."""
    html = await get_text(client, DSP_PAGE)
    wanted = {(m.year, m.month) for m in months}
    seen: Dict[tuple, FileRef] = {}
    for url in sorted(set(_DSP_HREF.findall(html))):
        fn = url.rsplit("/", 1)[-1]
        if "monthend" not in fn.lower() and "month-end" not in fn.lower():
            continue
        d = dsp_file_date(fn)
        if d and (d.year, d.month) in wanted:
            seen[(d.year, d.month, fn)] = FileRef("dsp", url, _eom(d), None, fn)
    return list(seen.values())


# -------------------------------------------------------------------------------------------------------------- Aditya Birla Sun Life
ABSL_URL = "https://mutualfund.adityabirlacapital.com/-/media/bsl/files/resources/monthly-portfolio/{y}/{d}_abslmf_monthlydisclosure.zip"


async def list_absl(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One zip per month-end with one old-format workbook (about 100 sheets, one per scheme); the name is predictable. Asked with a range request of 1 byte."""
    out: List[FileRef] = []
    for m in months:
        url = ABSL_URL.format(y=m.year, d=m.strftime("%d%m%Y"))
        r = await client.get(url, headers={"Range": "bytes=0-0"})
        if r.status_code in (200, 206):
            out.append(FileRef("absl", url, m, None, f"ABSLMF {m:%b %Y}"))
        elif r.status_code not in (404, 403):
            r.raise_for_status()
    return out


# -------------------------------------------------------------------------------------------------------------- Nippon India
NIPPON_PAGE = "https://mf.nipponindiaim.com/investor-service/downloads/factsheet-portfolio-and-other-disclosures"
_NIP = re.compile(r'href="(/InvestorServices/FactsheetsDocuments/NIMF-MONTHLY-PORTFOLIO-(\d{1,2})-([A-Za-z]{3})-(\d{2,4})\.xlsx?)"', re.I)
_MON = {m.lower(): i for i, m in enumerate(MON_KEYS, 1)}


async def list_nippon(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One workbook for the whole fund house (about 110 sheets), linked on the disclosures page; its extension says .xls but it is an .xlsx."""
    html = await get_text(client, NIPPON_PAGE)
    wanted = {(m.year, m.month) for m in months}
    out: List[FileRef] = []
    for path, dd, mon, yy in _NIP.findall(html):
        y = int(yy) + (2000 if len(yy) == 2 else 0)
        mi = _MON.get(mon.lower())
        if mi and (y, mi) in wanted:
            out.append(FileRef("nippon", "https://mf.nipponindiaim.com" + path, date(y, mi, int(dd)), None, path.rsplit("/", 1)[-1]))
    return out


class Adapter:
    def __init__(self, key: str, title: str, amc_pattern: str, lister, site: str):
        self.key, self.title, self.site = key, title, site
        self.amc_re = re.compile(amc_pattern, re.I)
        self.list_files = lister


ADAPTERS: List[Adapter] = [
    Adapter("mirae", "Mirae Asset Mutual Fund", r"mirae", list_mirae, "miraeassetmf.co.in"),
    Adapter("invesco", "Invesco Mutual Fund", r"invesco", list_invesco, "invescomutualfund.com"),
    Adapter("dsp", "DSP Mutual Fund", r"\bdsp\b", list_dsp, "dspim.com"),
    Adapter("absl", "Aditya Birla Sun Life Mutual Fund", r"aditya\s+birla", list_absl, "adityabirlacapital.com"),
    Adapter("nippon", "Nippon India Mutual Fund", r"nippon", list_nippon, "nipponindiaim.com"),
]
