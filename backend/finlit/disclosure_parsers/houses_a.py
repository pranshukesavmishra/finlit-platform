"""Monthly-portfolio listers for UTI, Axis, Tata, Bandhan and HSBC Mutual Fund. Like amcs.py, each adapter only LISTS the files for the asked month-ends
(small requests); downloading, parsing and storing happen in the driver. Every endpoint here is the one the fund house's own website calls, found by
reading its pages and JavaScript, and was fetched live from the development sandbox (October 2026).
"""

from __future__ import annotations

import html
import re
from datetime import date
from typing import Dict, List, Optional

import httpx

from .amcs import MON_FULL, Adapter, FileRef, _eom, file_month, get_text, page_lister

_MONTH_NO = {m.lower(): i for i, m in enumerate(MON_FULL, 1)}
_MONTH_NO.update({m[:3].lower(): i for i, m in enumerate(MON_FULL, 1)})


def _tail_date(text: str) -> Optional[date]:
    """The '30 September 2026' at the end of a document title (scheme names can hold other dates, e.g. 'Gilt April 2028 Index Fund')."""
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s*,?\s*(20\d\d)\W*$", text)
    if not m or m.group(2)[:3].lower() not in _MONTH_NO:
        return None
    try:
        return date(int(m.group(3)), _MONTH_NO[m.group(2)[:3].lower()], int(m.group(1)))
    except ValueError:
        return None


def _strip_tail_date(text: str) -> str:
    return re.sub(r"[\s\-–]*\d{1,2}\s+[A-Za-z]+\s*,?\s*20\d\d\W*$", "", text).strip()


# -------------------------------------------------------------------------------------------------------------- UTI
# utimf.com is an Angular app whose 'Downloads' page reads its sections from the CMS (api/page/forms-and-downloads-downloads). The section
# 'Portfolio Disclosure - Scheme Wise' lists schemes per category (api/get-schemes-from-cat) and returns one xlsx per scheme and month
# (api/get-scheme-portfolio-disclosure). The 'Consolidate Portfolio Disclosure (All scheme)' zip holds every scheme stacked on ONE sheet (SCHEME CODE
# ... STARTS / ENDS blocks), which the one-sheet-one-scheme parser cannot split, so the per-scheme files are used.
UTI_BASE = "https://www.utimf.com/"
UTI_CATEGORIES = ("Equity", "Debt", "Hybrid", "FOF", "Liquid", "Solution Oriented", "ETF", "Index Fund")


async def list_uti(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    schemes: Dict[str, str] = {}
    for cat in UTI_CATEGORIES:
        r = await client.get(UTI_BASE + "api/get-schemes-from-cat", params={"fund_category": cat})
        r.raise_for_status()
        for row in (r.json() or {}).get("rows") or []:
            code = str(row.get("field_dofa_schcode") or "").strip()
            name = html.unescape(str(row.get("field_fund_name") or "")).strip()
            if code and name:
                schemes.setdefault(code, name)
    out: Dict[str, FileRef] = {}
    for code, name in schemes.items():
        for m in months:
            r = await client.get(UTI_BASE + "api/get-scheme-portfolio-disclosure",
                                 params={"dofa_scheme_code": code, "year": m.year, "month": MON_FULL[m.month - 1]})
            r.raise_for_status()
            for row in (r.json() or {}).get("rows") or []:
                url = (row.get("url") or row.get("doc") or "").strip()
                if url.lower().split("?")[0].endswith((".xlsx", ".xls")) and url not in out:
                    out[url] = FileRef("uti", url, m, name, f"{name} {m:%b %Y}")
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Axis
# axismf.com (Next.js) 'Statutory disclosures > Portfolios > Monthly Scheme Portfolios' posts to /cms/get-scheme-documents with the anonymous CMS token
# every visitor's page gets from /cms/token. Scheme code 'Consolidated' lists the one 'Monthly Portfolio dd-mm-yyyy' workbook (one sheet per scheme)
# next to weekly / ad-hoc files of that month.
AXIS_BASE = "https://www.axismf.com"


async def list_axis(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    r = await client.post(AXIS_BASE + "/cms/token", json={})
    r.raise_for_status()
    token = ((r.json() or {}).get("data") or {}).get("token")
    if not token:
        raise RuntimeError("axismf.com /cms/token returned no token")
    hdr = {"Authorization": token}
    out: Dict[str, FileRef] = {}
    for m in months:
        body = {"sdType": "yearMonthSchemeDocs", "sdID": "sdMonthSchemePortfolio", "year": str(m.year), "month": MON_FULL[m.month - 1],
                "schemeCode": "Consolidated"}
        r = await client.post(AXIS_BASE + "/cms/get-scheme-documents", json=body, headers=hdr)
        r.raise_for_status()
        for doc in ((r.json() or {}).get("data") or {}).get("documentList") or []:
            name = str(doc.get("documentName") or "")
            url = str(doc.get("docuementURL") or doc.get("documentURL") or "").strip()     # sic: the API spells it 'docuementURL'
            if not re.match(r"^\s*monthly\s+portfolio\b", name, re.I) or not url.lower().split("?")[0].endswith((".xlsx", ".xls")):
                continue
            d = file_month(url) or file_month(name.replace(" ", "_") + ".x")
            if d and (d.year, d.month) == (m.year, m.month) and url not in out:
                out[url] = FileRef("axis", url, _eom(d), None, name[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Tata
# tatamutualfund.com/schemes-related/portfolio (Next.js) embeds its whole document list in the page; the monthly files are one workbook per month
# ('Monthly Portfolio as on 30th September 2026.xlsx', one sheet per scheme) on betacms.tatamutualfund.com, which redirects to www.
list_tata = page_lister("tata", "https://www.tatamutualfund.com/schemes-related/portfolio",
                        r'(https://betacms\.tatamutualfund\.com/system/files/\d{4}-\d{2}/Monthly%20Portfolio%20as%20on%20[^"\\<>]+?\.xlsx?)(?=[\\"])')


# -------------------------------------------------------------------------------------------------------------- Bandhan
# bandhanmutual.com is a React app over a WordPress CMS (cmsnew.bandhanmutual.com). 'Disclosure of Detailed Scheme Portfolios' posts
# (finance-api posts/scheme-portfolios, newest first) carry one xlsx per scheme and month on storage.googleapis.com.
BANDHAN_API = "https://cmsnew.bandhanmutual.com/wp-json/finance-api/v1/posts/scheme-portfolios"


async def list_bandhan(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    wanted = {(m.year, m.month) for m in months}
    oldest = _eom(min(months))
    out: Dict[str, FileRef] = {}
    for page in range(1, 16):
        r = await client.get(BANDHAN_API, params={"posts_per_page": 100, "page": page, "acf_key": "disclosures_type",
                                                  "acf_value": "Monthly and Half-yearly Disclosures"})
        r.raise_for_status()
        posts = (r.json() or {}).get("data") or []
        if not posts:
            break
        older = 0
        for p in posts:
            title = re.sub(r"\s+", " ", html.unescape(str(p.get("title") or ""))).strip()
            d = _tail_date(title)
            if not d:
                continue
            if _eom(d) < oldest:
                older += 1
                continue
            if (d.year, d.month) not in wanted:
                continue
            name = _strip_tail_date(re.sub(r"^monthly\s+and\s+half[\s-]*yearly\s*-\s*", "", title, flags=re.I))
            for f in ((p.get("acf_fields") or {}).get("disclosure_files") or []):
                link = f.get("document_link")
                url = (link.get("url") if isinstance(link, dict) else str(link or "")).strip()
                if url.lower().split("?")[0].endswith((".xlsx", ".xls")) and url not in out:
                    out[url] = FileRef("bandhan", url, _eom(d), name, title[:80])
        if older == len(posts):
            break
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- HSBC
# assetmanagement.hsbc.co.in 'Document library' is one large server-rendered page (about 4.5 MB; it took up to two minutes to answer from the sandbox)
# linking one xlsx per scheme and month under -/media/files/attachments/india/mutual-funds/portfolios/document-DDMMYYYY/ (no file extension).
# The sheets carry no scheme name, so the link title supplies it.
HSBC_SITE = "https://www.assetmanagement.hsbc.co.in/"
HSBC_PAGE = HSBC_SITE + "en/mutual-funds/investor-resources/document-library"
_HSBC_A = re.compile(r'href="/?(-/media/+files/attachments/india/mutual-funds/portfolios/document-(\d{2})(\d{2})(\d{4})/[^"]+)"\s+title="([^"]+)"', re.I)


# HSBC shortens some link titles; spelled out as in AMFI's scheme list (each checked against it, October 2026)
_HSBC_ABBR = [(r"\bCRL\b", "CRISIL"), (r"\bIndx\b", "Index"), (r"\b50 50 Gl SDL\b", "50:50 Gilt Plus SDL"), (r"\bAp28\b", "Apr 2028"),
              (r"\bJune27\b", "June 2027"), (r"\bETF FOF\b", "ETF Fund of Fund"), (r"\bNifty Next 50 Fund\b", "Nifty Next 50 Index Fund")]


def _hsbc_name(name: str) -> str:
    for pat, full in _HSBC_ABBR:
        name = re.sub(pat, full, name, flags=re.I)
    return name


async def list_hsbc(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    page = await get_text(client, HSBC_PAGE, timeout=httpx.Timeout(300.0, connect=30.0))
    wanted = {(m.year, m.month) for m in months}
    out: Dict[str, FileRef] = {}
    for path, dd, mm, yyyy, title in _HSBC_A.findall(page):
        try:
            d = date(int(yyyy), int(mm), int(dd))
        except ValueError:
            continue
        if (d.year, d.month) not in wanted:
            continue
        url = HSBC_SITE + re.sub(r"/{2,}", "/", path)
        label = re.sub(r"\s*\((xlsx?|zip)[^)]*\)\s*$", "", html.unescape(title), flags=re.I).strip()
        name = _hsbc_name(_strip_tail_date(label))
        if name and url.lower() not in {k.lower() for k in out}:
            out[url] = FileRef("hsbc", url, _eom(d), name, label[:80])
    return list(out.values())


ADAPTERS: List[Adapter] = [
    Adapter("uti", "UTI Mutual Fund", r"^uti\b", list_uti, "utimf.com"),
    Adapter("axis", "Axis Mutual Fund", r"^axis\b", list_axis, "axismf.com"),
    Adapter("tata", "Tata Mutual Fund", r"^tata\b", list_tata, "tatamutualfund.com"),
    Adapter("bandhan", "Bandhan Mutual Fund", r"^bandhan\b", list_bandhan, "bandhanmutual.com"),
    Adapter("hsbc", "HSBC Mutual Fund", r"^hsbc\b", list_hsbc, "assetmanagement.hsbc.co.in"),
]
