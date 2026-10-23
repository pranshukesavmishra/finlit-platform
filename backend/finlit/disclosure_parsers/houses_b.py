"""Monthly-portfolio listers for Motilal Oswal, Franklin Templeton, Sundaram, LIC, quant and Canara Robeco Mutual Fund (see amcs.py for the
contract: a lister returns FileRef(url, month_end, name_hint) and never raises for 'not published yet'; the driver downloads and parses).
Every URL pattern here was fetched from the development sandbox in October 2026. Union Mutual Fund (unionmf.com) has no lister: the
site could not be reached from the sandbox (connection refused or reset), so nothing about it could be checked."""

from __future__ import annotations

import html as _html
import re
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote, urljoin

import httpx

from .amcs import BROWSER_UA, Adapter, FileRef, _eom, file_month
from .sebi import MONTHS, parse_date_text

_BH = {"User-Agent": BROWSER_UA}
_MON_YEAR = re.compile(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,.\-_]*(20\d\d)", re.I)


def _month_of(text: str) -> Optional[date]:
    """The month-end named in a title such as 'Scheme Portfolio Details September 2026' (the last month name followed by a year)."""
    found = _MON_YEAR.findall(text or "")
    if not found:
        return None
    mon, yr = found[-1]
    return _eom(date(int(yr), MONTHS[mon[:3].lower()], 1))


# -------------------------------------------------------------------------------------------------------------- Motilal Oswal
MO_BASE = "https://www.motilaloswalmf.com"
MO_SEARCH = MO_BASE + "/content/aem-cloud-dept-backend-motilal-oswal/api/search-documents.json"


async def list_motilal(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One workbook for every scheme ('Scheme Portfolio Details <Month YYYY>', one sheet per scheme), listed by the downloads page's own document search
    (category 'month end portfolio', by upload year). The same category also holds the fortnightly and half-yearly files, which are left out."""
    wanted = {(m.year, m.month) for m in months}
    years = sorted({m.year for m in months} | {m.year + 1 for m in months if m.month == 12})
    out: Dict[str, FileRef] = {}
    for yr in years:
        r = await client.get(MO_SEARCH, params={"year": str(yr), "month": "", "type": "mf", "category": "month end portfolio"}, headers=_BH)
        r.raise_for_status()
        for it in (r.json() or {}).get("results") or []:
            title = re.sub(r"\s+", " ", str(it.get("title") or "")).strip()
            path = str(it.get("path") or "")
            if not re.search(r"scheme\s+portfolio\s+details", title, re.I) or not path.lower().endswith((".xlsx", ".xls")):
                continue
            d = _month_of(title)
            if d and (d.year, d.month) in wanted:
                url = MO_BASE + quote(path)
                out.setdefault(url, FileRef("motilal", url, d, None, title))
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Franklin Templeton
FT_BASE = "https://www.franklintempletonindia.com/"
FT_LIST = FT_BASE + "api/literature/v1/responseLitJson"


async def list_franklin(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One workbook for every scheme ('ISIN as on <date>', one sheet per scheme), listed under MONTHLY-PORTFOLIO-DSCLR by the reports page's own
    literature service; the page links each document as BASE/download/<literatureHref>."""
    wanted = {(m.year, m.month) for m in months}
    r = await client.get(FT_LIST, params={"type": "report"}, headers=_BH)
    r.raise_for_status()
    out: Dict[str, FileRef] = {}
    for cat in (r.json() or {}).get("FirstDropDown") or []:
        if cat.get("id") != "MONTHLY-PORTFOLIO-DSCLR":
            continue
        for it in (cat.get("dataRecords") or {}).get("linkdata") or []:
            href = str(it.get("literatureHref") or "")
            title = str(it.get("dctermsTitle") or "")
            if not href.lower().endswith((".xlsx", ".xls")):
                continue
            d = parse_date_text(title) or file_month(href)
            if d and (d.year, d.month) in wanted:
                url = href if href.startswith("http") else urljoin(FT_BASE, "download" + (href if href.startswith("/") else "/" + href))
                out.setdefault(url, FileRef("franklin", url, _eom(d), None, title[:80]))
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Sundaram
SU_PAGE = "https://www.sundarammutual.com/monthly-fortnightly-adhoc-portfolios"
_SU_AJAX = re.compile(r'src="(/ajax/Modules_Disclosure_Monthly_Fortnightly_Adhoc_Portfolios,[^"]+\.ashx)"', re.I)
_SU_LINK = re.compile(r"<a href='([^']+\.xlsx?)'[^>]*>(?:<i[^>]*></i>)?([^<]+)</a>", re.I)


async def list_sundaram(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """Two workbooks a month ('Monthly Portfolio Disclosure Equity & Fund of Funds - Sep 2026' and '... Fixed Income - Sep 2026', one sheet per scheme),
    listed by the portfolio page's own AjaxPro method GetCategory('Monthly'). The method's URL carries a build-specific name, so it is read from the page."""
    page = await client.get(SU_PAGE, headers=_BH)
    page.raise_for_status()
    m = _SU_AJAX.search(page.text)
    if not m:
        raise ValueError("Sundaram portfolio page no longer links its AjaxPro script")
    r = await client.post(urljoin(SU_PAGE, m.group(1)), params={"_method": "GetCategory", "_session": "no"}, content=b"Catid=Monthly",
                          headers={**_BH, "Referer": SU_PAGE, "Content-Type": "text/plain; charset=utf-8"})
    r.raise_for_status()
    body = r.text.replace("\\'", "'")
    wanted = {(x.year, x.month) for x in months}
    out: Dict[str, FileRef] = {}
    for href, title in _SU_LINK.findall(body):
        title = _html.unescape(title).strip()
        if "monthly portfolio" not in title.lower():
            continue
        d = _month_of(title)
        if d and (d.year, d.month) in wanted:
            url = urljoin(SU_PAGE, href)
            out.setdefault(url, FileRef("sundaram", url, d, None, title[:80]))
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- LIC
LIC_BASE = "https://www.licmf.com"
LIC_PAGE = LIC_BASE + "/downloads/monthly-portfolio"
_LIC_TYPE = re.compile(r"<option value=['\"](\d+)['\"]>\s*Monthly Portfolio", re.I)
_LIC_FILE = re.compile(r'<a href="([^"]+\.xlsx?)"[^>]*>.*?<span class="caption">([^<]+)</span>', re.I | re.S)


async def list_lic(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """Two workbooks a month ('Monthly Portfolio Equity as on ...' and '... Debt as on ...', one sheet per scheme), listed by the portfolio page's own
    'Consolidated Portfolio' tab: its form gives the id of the 'Monthly Portfolio' type, then one request per year and month gives the file links."""
    hx = {**_BH, "X-Requested-With": "XMLHttpRequest", "Referer": LIC_PAGE}
    r = await client.post(LIC_BASE + "/downloads/consolidated-portfolio", headers=hx)
    r.raise_for_status()
    m = _LIC_TYPE.search(r.text)
    if not m:
        raise ValueError("LIC consolidated portfolio form has no 'Monthly Portfolio' type")
    out: Dict[str, FileRef] = {}
    for mo in months:
        r = await client.post(LIC_BASE + "/downloads/consolidated-portfolio-files", data={"id": m.group(1), "month": str(mo.month), "year": str(mo.year)}, headers=hx)
        r.raise_for_status()
        for href, caption in _LIC_FILE.findall(r.text):
            caption = re.sub(r"\s+", " ", _html.unescape(caption)).strip()
            d = parse_date_text(caption) or _month_of(caption)
            if d and (d.year, d.month) == (mo.year, mo.month):
                url = urljoin(LIC_BASE + "/", quote(_html.unescape(href), safe="/:%"))
                out.setdefault(url, FileRef("lic", url, _eom(d), None, caption[:80]))
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- quant
QT_BASE = "https://quantmutual.com"
QT_PAGE = QT_BASE + "/statutory-disclosures"
_QT_LINK = re.compile(r"<a href='([^']+\.xlsx?)'[^>]*>([^<]+)</a>", re.I)


async def list_quant(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One workbook for every scheme a month (one sheet per scheme), listed by the statutory-disclosures page's own page method
    displaydisclouser(year, 'MONTHLY PORTFOLIO'); each link's text is the month ('September 2026')."""
    hx = {**_BH, "X-Requested-With": "XMLHttpRequest", "Referer": QT_PAGE, "Content-Type": "application/json; charset=utf-8"}
    wanted = {(m.year, m.month) for m in months}
    out: Dict[str, FileRef] = {}
    for yr in sorted({m.year for m in months}):
        r = await client.post(QT_BASE + "/statutorydisclosures.aspx/displaydisclouser", content=f"{{id:'{yr}',cat:'MONTHLY PORTFOLIO'}}".encode(), headers=hx)
        r.raise_for_status()
        for href, title in _QT_LINK.findall(str((r.json() or {}).get("d") or "")):
            title = _html.unescape(title).strip()
            d = _month_of(title) or file_month(href)
            if d and (d.year, d.month) in wanted:
                url = urljoin(QT_BASE + "/", href)
                out.setdefault(url, FileRef("quant", url, d, None, title[:80]))
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Canara Robeco
CR_PAGE = "https://www.canararobeco.com/documents/statutory-disclosures/scheme-dashboard/scheme-monthly-portfolio/"
_CR_ITEM = re.compile(r'<a href="([^"]+\.xlsx?)"\s+class="pdf-title[^"]*"[^>]*>([^<]+)</a>', re.I)


def _cr_name(title: str) -> str:
    """'LC – Canara Robeco Large Cap Fund – September 2026' -> 'Canara Robeco Large Cap Fund'."""
    t = re.sub(r"\s+", " ", _html.unescape(title)).strip()
    t = re.sub(r"^[A-Z]{1,4}\s*[–\-]\s*", "", t)
    t = re.sub(r"\s*[–\-]?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*[–\-]?\s*20\d\d\s*$", "", t, flags=re.I)
    return t.strip(" –-")


async def list_canara(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    """One xlsx per scheme, listed (10 a page) by the 'Scheme Monthly Portfolio' page when asked for a year and month. (The site's wp-json listing sits
    behind a CDN cache that ignores the query string, so it is not used.)"""
    out: Dict[str, FileRef] = {}
    for m in months:
        for page in range(1, 11):
            r = await client.get(CR_PAGE, params={"filteryear": str(m.year), "filtermonth": f"{m.month:02d}", "pagination": str(page)}, headers=_BH)
            r.raise_for_status()
            items = _CR_ITEM.findall(r.text)
            new = 0
            for href, title in items:
                url = urljoin(CR_PAGE, _html.unescape(href))
                d = _month_of(_html.unescape(title)) or file_month(url)
                if not d or (d.year, d.month) != (m.year, m.month) or url in out:
                    continue
                out[url] = FileRef("canara", url, d, _cr_name(title) or None, _html.unescape(title).strip()[:80])
                new += 1
            if not new or f"pagination={page + 1}" not in r.text.replace("&#038;", "&"):
                break
    return list(out.values())


ADAPTERS: List[Adapter] = [
    Adapter("motilal", "Motilal Oswal Mutual Fund", r"motilal", list_motilal, "motilaloswalmf.com"),
    Adapter("franklin", "Franklin Templeton Mutual Fund", r"franklin", list_franklin, "franklintempletonindia.com"),
    Adapter("sundaram", "Sundaram Mutual Fund", r"sundaram", list_sundaram, "sundarammutual.com"),
    Adapter("lic", "LIC Mutual Fund", r"^lic\b", list_lic, "licmf.com"),
    Adapter("quant", "quant Mutual Fund", r"^quant\s+mutual", list_quant, "quantmutual.com"),
    Adapter("canara", "Canara Robeco Mutual Fund", r"canara", list_canara, "canararobeco.com"),
]
