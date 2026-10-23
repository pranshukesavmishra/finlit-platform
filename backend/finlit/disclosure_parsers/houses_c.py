"""Monthly-portfolio listers for the smaller fund houses (group C). Same contract as amcs.py: each lister only LISTS the files for the wanted month-ends
(FileRef), never downloads them; an empty list means 'not published yet'. Every URL pattern here was fetched from the development sandbox.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import Dict, List, Optional
from urllib.parse import quote, unquote, urljoin

import httpx

from .amcs import BROWSER_UA, Adapter, FileRef, _eom, file_month, get_text, page_lister

XLS = (".xlsx", ".xls", ".zip")
BROWSER = {"User-Agent": BROWSER_UA}


def text_month(text: str) -> Optional[date]:
    """The month-end named in a link title such as 'Monthly Portfolio Disclosure - September, 2026' (same rules as file_month)."""
    return file_month("/" + re.sub(r"[/\\?]+", " ", text or ""))


def _is_xls(url: str) -> bool:
    return unquote(url).lower().split("?")[0].endswith(XLS)


def _want(months: List[date]):
    w = {(m.year, m.month) for m in months}
    return lambda d: bool(d) and (d.year, d.month) in w


def labelled_lister(key: str, page: str, rx: str, name_group: Optional[int] = None):
    """A lister for a page whose file names say nothing (GUIDs) but whose link text does: `rx` captures (url, label[, scheme name]); the month comes
    from the label. One FileRef per url; a third group, when given, is the scheme name (one file per scheme)."""
    pat = re.compile(rx, re.I | re.S)

    async def lister(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
        html = (await get_text(client, page, headers=BROWSER)).replace('\\"', '"')     # Next.js pages carry their data as escaped JSON
        want = _want(months)
        out: Dict[str, FileRef] = {}
        for m in pat.finditer(html):
            url = urljoin(page, m.group(1).replace("&amp;", "&").strip())
            label = re.sub(r"<[^>]+>|\s+", " ", m.group(2)).strip()
            d = text_month(label) or file_month(url)
            if want(d) and _is_xls(url) and url not in out:
                nm = re.sub(r"\s+", " ", m.group(name_group)).strip() if name_group else None
                out[url] = FileRef(key, url, d, nm or None, label[:80])
        return list(out.values())
    return lister


# -------------------------------------------------------------------------------------------------------------- Mahindra Manulife
# The downloads page is a JS app; its own API answers JSON whose body is AES-CBC encrypted with a key and IV that ship in the site's public JS bundle
# (transport obfuscation only: no login, cookie or captcha). Category 52 is 'Monthly Portfolio Disclosure', one workbook per month for every scheme.
MM_API = "https://investorapi.mahindramanulife.com/api/v1/web/preLogin/downloads/category/52"
MM_SITE = "https://www.mahindramanulife.com"
MM_KEY, MM_IV = "mahindra2024mahindra2024mahindra", "hasnainsheikh202"


def _aes_cbc_json(payload: str, key: bytes, iv: bytes):
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    d = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    raw = d.update(base64.b64decode(payload)) + d.finalize()
    u = padding.PKCS7(128).unpadder()
    raw = u.update(raw) + u.finalize()
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        return json.loads(raw.decode("latin-1"))


async def _mm_keys(client: httpx.AsyncClient):
    """The key and IV as the current bundle defines them (const X="<32 chars>",Y="<16 chars>",...=enc.Utf8.parse(X)), for when they rotate."""
    html = await get_text(client, MM_SITE + "/", headers=BROWSER)
    for src in re.findall(r'src="(/assets/index-[^"]+\.js)"', html):
        js = await get_text(client, MM_SITE + src, headers=BROWSER)
        m = re.search(r'="([^"]{32})",\w+="([^"]{16})",\w+=\w+\.enc\.Utf8\.parse\(', js)
        if m:
            return m.group(1).encode(), m.group(2).encode()
    return None


def _walk_files(node, out: list) -> None:
    if isinstance(node, dict):
        for f in node.get("files") or []:
            out.append(f)
        for s in node.get("subcategories") or []:
            _walk_files(s, out)
    elif isinstance(node, list):
        for s in node:
            _walk_files(s, out)


async def list_mahindra(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    r = await client.get(MM_API, headers={**BROWSER, "Referer": MM_SITE + "/downloads"})
    r.raise_for_status()
    body = r.json()
    if isinstance(body, dict) and "payload" in body:
        try:
            body = _aes_cbc_json(body["payload"], MM_KEY.encode(), MM_IV.encode())
        except Exception:
            keys = await _mm_keys(client)
            if not keys:
                raise
            body = _aes_cbc_json(body["payload"], *keys)
    files: list = []
    _walk_files(body.get("data") if isinstance(body, dict) else body, files)
    want = _want(months)
    out: Dict[str, FileRef] = {}
    for f in files:
        title, url = str(f.get("title") or ""), str(f.get("fileUrl") or "")
        d = text_month(title)
        if want(d) and _is_xls(url) and "portfolio" in title.lower() and "fortnight" not in title.lower():
            out[url] = FileRef("mahindra", url, d, None, title[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Bank of India
# The Investor Corner 'Monthly Portfolio' tab is filled by the site's own AjaxService (10 documents a page, newest first): one workbook per month.
BOI_API = "https://www.boimf.in/AjaxService.asmx/GetDocuments"


async def list_boi(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    want = _want(months)
    oldest = _eom(min(months))
    out: Dict[str, FileRef] = {}
    for page in range(4):
        r = await client.post(BOI_API, json={"pagno": page, "category": None, "fromDate": None, "toDate": None, "LibraryName": "InvestorCorner",
                                             "folderName": "MONTHLY PORTFOLIO", "CategoryValue": "no"},
                              headers={**BROWSER, "X-Requested-With": "XMLHttpRequest", "Referer": "https://www.boimf.in/investor-corner"})
        r.raise_for_status()
        docs = (json.loads(r.json().get("d") or "{}") or {}).get("Documents") or []
        if not docs:
            break
        older = False
        for doc in docs:
            url, name = str(doc.get("FolderUrl") or ""), str(doc.get("DocName") or "")
            d = text_month(name) or file_month(url)
            if d and d < oldest:
                older = True
            if want(d) and _is_xls(url):
                out[url] = FileRef("boi", url, d, None, name[:80])
        if older:
            break
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Bajaj Finserv
# WordPress downloads plugin: the page carries a public nonce (window.bajajDownloads), and admin-ajax 'bajaj_get_downloads' answers the links for one
# section, financial year ('2026-27') and month name. Section 757 is 'Monthly Portfolio' (one workbook per month for every scheme).
BAJAJ_PAGE = "https://www.bajajamc.com/downloads"
BAJAJ_AJAX = "https://www.bajajamc.com/wp-admin/admin-ajax.php"
BAJAJ_SECTION = "757"


async def list_bajaj(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    html = await get_text(client, BAJAJ_PAGE, headers=BROWSER)
    m = re.search(r'bajajDownloads\s*=\s*\{[^}]*"nonce"\s*:\s*"([0-9a-f]+)"', html)
    if not m:
        raise ValueError("bajajamc.com downloads page carries no nonce")
    nonce = m.group(1)
    sec = re.search(r'data-section-id="(\d+)"[^>]*data-filter="year_month"[^>]*>\s*<button[^>]*>(?:(?!</button>).)*?bd-accordion-title">\s*Monthly Portfolio\s*<', html, re.S)
    section = sec.group(1) if sec else BAJAJ_SECTION
    out: Dict[str, FileRef] = {}
    for me in months:
        fy = me.year if me.month >= 4 else me.year - 1
        r = await client.post(BAJAJ_AJAX, data={"action": "bajaj_get_downloads", "nonce": nonce, "section_id": section,
                                                "year": f"{fy}-{(fy + 1) % 100:02d}", "month": me.strftime("%B")},
                              headers={**BROWSER, "Referer": BAJAJ_PAGE, "X-Requested-With": "XMLHttpRequest"})
        r.raise_for_status()
        j = r.json()
        if not j.get("success"):
            raise ValueError(f"bajajamc.com downloads service refused: {str(j)[:120]}")
        for href in re.findall(r'href="([^"]+)"', (j.get("data") or {}).get("html") or ""):
            url = href.replace("&amp;", "&")
            d = file_month(url) or me
            if _is_xls(url) and (d.year, d.month) == (me.year, me.month) and "portfolio" in unquote(url).lower():
                out[url] = FileRef("bajaj", url, me, None, unquote(url.rsplit("/", 1)[-1])[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- WhiteOak Capital
# The 'Scheme Portfolio' page reads the site's public Strapi CMS: collection scheme-portfolios, one xlsx per scheme and month (period 'Monthly').
WOC_API = "https://cms.whiteoakamc.com/api/scheme-portfolios"


async def list_whiteoak(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    want = _want(months)
    oldest = _eom(min(months))
    out: Dict[str, FileRef] = {}
    for page in range(1, 6):
        r = await client.get(WOC_API, params={"sort[0]": "published_date:desc", "sort[1]": "id:desc", "populate": "*", "filters[period][$eq]": "Monthly",
                                              "pagination[page]": page, "pagination[pageSize]": 100}, headers=BROWSER)
        r.raise_for_status()
        rows = r.json().get("data") or []
        if not rows:
            break
        older = False
        for row in rows:
            a = row.get("attributes") or {}
            f = ((a.get("doc_file") or {}).get("data") or {}).get("attributes") or {}
            url = f.get("url") or a.get("doc_link") or ""
            title = str(a.get("doc_name") or "")
            d = text_month(title) or file_month(url)
            if d and d < oldest:
                older = True
            if want(d) and _is_xls(url) and "fortnight" not in title.lower():
                nm = re.sub(r"\s+", " ", str(a.get("scheme_name") or "")).strip() or None
                out[url] = FileRef("whiteoak", url, d, nm, title[:80])
        if older:
            break
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- JM Financial
# The downloads pages are a React app; its API (plain JSON POST) answers 'data' AES-CBC encrypted with the key and IV published in the site's own JS
# bundle (REACT_APP_AES_KEY / REACT_APP_AES_IV): transport obfuscation, no login. Sub-category 'Monthly Portfolio of Schemes' lists one xlsx per scheme.
JM_API = "https://jmmfapi.jmfinancialmf.com/api/"
JM_SITE = "https://www.jmfinancialmf.com/"
JM_KEY, JM_IV = "6fa979f20126cb08aa645a8f495f6d85", "I8zyA4lVhMCaJ5Kg"


async def _jm_post(client: httpx.AsyncClient, fn: str, body: dict):
    r = await client.post(JM_API + fn, json=body, headers={**BROWSER, "Referer": JM_SITE})
    r.raise_for_status()
    data = r.json().get("data")
    if isinstance(data, str) and data:
        try:
            return _aes_cbc_json(data, JM_KEY.encode(), JM_IV.encode())
        except Exception:
            js = await get_text(client, JM_SITE, headers=BROWSER)
            for src in re.findall(r'src="(/static/js/main\.[0-9a-f]+\.js)"', js):
                b = await get_text(client, urljoin(JM_SITE, src), headers=BROWSER)
                k, v = re.search(r'REACT_APP_AES_KEY:"([^"]+)"', b), re.search(r'REACT_APP_AES_IV:"([^"]+)"', b)
                if k and v:
                    return _aes_cbc_json(data, k.group(1).encode(), v.group(1).encode())
            raise
    return data or []


async def list_jm(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    sub = await _jm_post(client, "GetDownloadNewSub", {"IVSubCategoryName": "Monthly Portfolio of Schemes"})
    if not sub:
        raise ValueError("jmfinancialmf.com has no 'Monthly Portfolio of Schemes' download category")
    rows = await _jm_post(client, "GetDownloadNew", {"IICategoryID": str(sub[0]["DownloadCategoryID"]), "IISubCategoryID": str(sub[0]["DownloadSubCategoryID"]),
                                                    "IVsearch": ""})
    want = _want(months)
    out: Dict[str, FileRef] = {}
    for row in rows or []:
        title, fn = re.sub(r"\s+", " ", str(row.get("Title") or "")).strip(), str(row.get("FileName") or "")
        d = text_month(title) or file_month(fn)
        if not (want(d) and _is_xls(fn)):
            continue
        url = urljoin(JM_SITE, quote(fn.lstrip("/"), safe="/,()&'"))
        m = re.search(r"portfolio\s*-\s*(.+?)\s*-\s*[A-Za-z]{3,9}\.?\s*\d", title, re.I)
        out[url] = FileRef("jm", url, d, m.group(1).strip() if m else None, title[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- 360 ONE
# The downloads page embeds its document groups as JSON ('Monthly Portfolio 2026' -> fileName 'September', fileUrl on the house's S3 bucket);
# one workbook per month for every scheme, named IN_MF_MONTHLY_PORTFOLIO_<Mon><yyyy>_....
list_oneamc = page_lister("oneamc", "https://www.360.one/asset/mutual-funds/downloads/",
                          r'(https://s3\.ap-south-1\.amazonaws\.com/x-web-s3\.360\.one/IN_MF_MONTHLY_PORTFOLIO_[A-Za-z0-9_]+\.xlsx?)')


# -------------------------------------------------------------------------------------------------------------- Quantum
# The 'All Funds' portfolio page links one workbook per month (GUID file names); the month is in the link's own label ('September 2026 - All Funds').
list_quantum = labelled_lister("quantum", "https://www.quantumamc.com/portfolio/combined/-1/1/0/0",
                               r"GTMcodeforxml\('([^']+\.xlsx?)',\s*'[^']*',\s*'([^']*All Funds[^']*)'")


# -------------------------------------------------------------------------------------------------------------- Shriram
# The statutory-disclosures page links (and embeds as JSON, for earlier financial years) one workbook per month on the house's CDN.
list_shriram = page_lister("shriram", "https://www.shriramamc.in/investor-statutory-disclosures",
                           r'(https://cdn\.shriramamc\.in/uploads/Statutory-disclosure/Monthly--Fortnightly--Weekly-Portfolio-of-Scheme\(s\)/'
                           r'Monthly-Portfolio[^"\\<>]*?\.xlsx?)(?![A-Za-z])')


# -------------------------------------------------------------------------------------------------------------- Jio BlackRock
# Next.js page; its year/month filter calls the page's own server action getDisclosureL3Data(l2Id, {year: 'FI2026-2027', month: 'September'}, 'MF')
# (a POST to the page with a Next-Action header). The action id changes with each deploy, so it is read from the page's JS chunk every run.
# One xlsx per scheme on the house's Azure CDN, plus one 'JioBlackRock Mutual Fund' file that repeats them (skipped).
JIO_PAGE = "https://www.jioblackrockamc.com/statutory-disclosure/disclosures/monthly-portfolio-disclosure"
JIO_SITE = "https://www.jioblackrockamc.com/"


async def _jio_action_id(client: httpx.AsyncClient) -> str:
    html = await get_text(client, JIO_PAGE, headers=BROWSER)
    for src in sorted(set(re.findall(r'(/_next/static/chunks/app/[^"]*?/page-[0-9a-f]+\.js)', html)), key=lambda x: "l2Id" not in x):
        js = await get_text(client, urljoin(JIO_SITE, src), headers=BROWSER)
        m = re.search(r'createServerReference\)\("([0-9a-f]{20,})",[^)]*?"getDisclosureL3Data"\)', js)
        if m:
            return m.group(1)
    raise ValueError("jioblackrockamc.com: getDisclosureL3Data action not found in the page's scripts")


async def list_jio(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    aid = await _jio_action_id(client)
    out: Dict[str, FileRef] = {}
    for me in months:
        fy = me.year if me.month >= 4 else me.year - 1
        r = await client.post(JIO_PAGE, content=json.dumps(["monthly-portfolio-disclosure", {"year": f"FI{fy}-{fy + 1}", "month": me.strftime("%B")}, "MF"]),
                              headers={**BROWSER, "Next-Action": aid, "Accept": "text/x-component", "Content-Type": "text/plain;charset=UTF-8",
                                       "Referer": JIO_PAGE})
        r.raise_for_status()
        body = None
        for line in r.text.splitlines():
            _, _, v = line.partition(":")
            if v.startswith("{") and '"data"' in v:
                body = json.loads(v)
        if body is None:
            raise ValueError(f"jioblackrockamc.com: odd server-action answer: {r.text[:120]}")
        for row in body.get("data") or []:
            title = str(row.get("title") or "")
            url = str((row.get("file") or {}).get("url") or "")
            m = re.match(r"(.+?)\s*-\s*Monthly-Portfolio-(\d{2})-(\d{2})-(\d{4})", title, re.I)
            if not (m and _is_xls(url)):
                continue
            d = _eom(date(int(m.group(4)), int(m.group(3)), 1))
            nm = m.group(1).strip()
            if (d.year, d.month) == (me.year, me.month) and not re.search(r"mutual\s+fund$", nm, re.I):
                out[url] = FileRef("jio", url, d, nm, title[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- The Wealth Company
# Next.js page 'Portfolio documents > Monthly' carries its download list (25 a page, newest first, ?page=N) in the page's own data: one xlsx per scheme,
# named 'Monthly - The Wealth Company Arbitrage Fund - Sep 30, 2026', with uploadDate the month-end.
WEALTHCO_PAGE = "https://www.wealthcompanyamc.in/literature-forms/portfolio-documents/monthly/"
_WEALTHCO_ROW = re.compile(r'"uploadDate":"(\d{4})-(\d{2})-\d{2}"[^{}]*?"name":"Monthly\s*-\s*(.+?)\s*-\s*[A-Za-z]{3,9}\.?\s*\d{1,2},?\s*\d{4}[^"]*"'
                           r'[^{}]*?"attachment":\{[^{}]*?"url":"([^"]+)"')


async def list_wealthco(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    want = _want(months)
    oldest = _eom(min(months))
    out: Dict[str, FileRef] = {}
    for page in range(1, 6):
        html = await get_text(client, WEALTHCO_PAGE + (f"?page={page}" if page > 1 else ""), headers=BROWSER)
        rows = _WEALTHCO_ROW.findall(html.replace('\\"', '"'))
        if not rows:
            break
        older = False
        for y, mo, name, path in rows:
            d = _eom(date(int(y), int(mo), 1))
            if d < oldest:
                older = True
            url = urljoin(WEALTHCO_PAGE, path)
            if want(d) and _is_xls(url):
                out[url] = FileRef("wealthco", url, d, re.sub(r"\s+", " ", name).strip(), f"{name} {d:%b %Y}"[:80])
        if older:
            break
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Angel One
# The downloads page carries every file link (WordPress CMS uploads); one xlsx per scheme, 'Monthly-Portfolio-September-2026-Angel-One-<scheme>.xlsx'.
list_angelone = page_lister("angelone", "https://www.angelonemf.com/downloads",
                            r'(https://cms\.angelonemf\.com/amc-cms/wp-content/uploads/[^"\\\s<>]*?Monthly-Portfolio[^"\\\s<>]*?\.xlsx?)(?![A-Za-z])')


# -------------------------------------------------------------------------------------------------------------- Capitalmind
# The statutory-disclosures page links one xlsx per scheme and month ('CMFLEXI_Monthly_Portfolio_Disclosure_September_2026_....xlsx').
list_capitalmind = page_lister("capitalmind", "https://www.capitalmindmf.com/statutory-disclosures.html",
                               r'(/uploads/(?![A-Za-z0-9_]*Fortnightly)[A-Za-z0-9_]*Portfolio_Disclosure[A-Za-z0-9_]*\.xlsx?)(?![A-Za-z])')


# -------------------------------------------------------------------------------------------------------------- Old Bridge
# The statutory-disclosures page has a 'Monthly Portfolio' block (below the half-yearly one): one xlsx per scheme and month, file names vary
# ('OBMF_Flexi_Cap_Portfolio_Sept_26_....xlsx', 'OBFX_<hash>.xlsx'), so the month and scheme come from the link's own label
# ('Old Bridge Flexi Cap Fund - September 2026').
list_oldbridge = labelled_lister("oldbridge", "https://www.oldbridgemf.com/statutory-disclosures.html",
                                 r'<a href="([^"]+\.xlsx?)"[^>]*?aria-label="Download ((Old Bridge [^"]*?Fund)\s*-\s*[A-Za-z]+\s+\d{4})[^"]*"',
                                 name_group=3)


# -------------------------------------------------------------------------------------------------------------- Choice
# The disclosures page's 'Monthly portfolio' tab reads the site's own JSON API (POST {}): per scheme, its reports with report_date and a file path on
# doc.choicemf.com, one xlsx per scheme and month.
CHOICE_API = "https://choicemf.com/api/monthly-portfolio-report/portfolio-website-list"
CHOICE_DOCS = "https://doc.choicemf.com/"


async def list_choice(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    r = await client.post(CHOICE_API, json={}, headers={**BROWSER, "Referer": "https://www.choicemf.com/disclosures/monthly-portfolio"})
    r.raise_for_status()
    want = _want(months)
    out: Dict[str, FileRef] = {}
    for sch in ((r.json().get("body") or {}).get("data") or []):
        nm = re.sub(r"\s+", " ", str(sch.get("scheme_name") or "")).strip() or None
        for rep in sch.get("reports") or []:
            try:
                d = _eom(date.fromisoformat(str(rep.get("report_date"))[:10]))
            except ValueError:
                continue
            url = urljoin(CHOICE_DOCS, quote(str(rep.get("file_path") or "").lstrip("/"), safe="/"))
            if want(d) and _is_xls(url):
                out[url] = FileRef("choice", url, d, nm, f"{nm} {d:%b %Y}"[:80])
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- AlphaGrep
# The site (alphagrepmf.ai, an Angular app) reads its public Strapi CMS: collection 'portfolios', each entry a scheme, an accordion ('Monthly'),
# and one .xls named after the month ('September_2026.xls').
AG_API = "https://cmsweb.alphagrepmf.ai/api/portfolios"
AG_CMS = "https://cmsweb.alphagrepmf.ai/"


async def list_alphagrep(client: httpx.AsyncClient, months: List[date]) -> List[FileRef]:
    want = _want(months)
    out: Dict[str, FileRef] = {}
    for page in range(1, 6):
        r = await client.get(AG_API, params={"populate": "*", "pagination[page]": page, "pagination[pageSize]": 100, "sort[0]": "id:desc"}, headers=BROWSER)
        r.raise_for_status()
        j = r.json()
        for row in j.get("data") or []:
            if str((row.get("accordian_name") or {}).get("Name") or "").strip().lower() != "monthly":
                continue
            f = row.get("file") or {}
            url = urljoin(AG_CMS, str(f.get("url") or ""))
            d = file_month(str(f.get("name") or "")) or file_month(url) or text_month(str(row.get("title") or ""))
            nm = re.sub(r"\s+", " ", str((row.get("scheme") or {}).get("Name") or "")).strip() or None
            if want(d) and _is_xls(url):
                out[url] = FileRef("alphagrep", url, d, nm, f"{nm} {d:%b %Y}"[:80])
        pg = (j.get("meta") or {}).get("pagination") or {}
        if page >= int(pg.get("pageCount") or 1):
            break
    return list(out.values())


# -------------------------------------------------------------------------------------------------------------- Monarch
# The site named in AMFI's member list is monarchamc.in; 'Portfolio holdings > Monthly' links one .xls per month for its one scheme.
list_monarch = page_lister("monarch", "https://www.monarchamc.in/forms-downloads/portfolio-holdings/monthly",
                           r'((?:https://www\.monarchamc\.in)?/uploads/Monthly_Portfolio[A-Za-z0-9_]*\.xlsx?)(?![A-Za-z])')


# -------------------------------------------------------------------------------------------------------------- Carnelian
# The statutory-disclosures page lists its documents as JSON items {file: {url: '/api/documents/file/...'}, name}. As of October 2026 it carries
# no portfolio statement (only AUM / complaints reports), so this lists nothing until a 'portfolio' document appears there.
list_carnelian = labelled_lister("carnelian", "https://www.carnelianmf.com/statutory-disclosures",
                                 r'"url":"(/api/documents/file/[^"]+)"[^{}]*?"name":"((?![^"]*fortnight)[^"]*portfolio[^"]*)"')


ADAPTERS: List[Adapter] = [
    Adapter("mahindra", "Mahindra Manulife Mutual Fund", r"^mahindra\s+manulife", list_mahindra, "mahindramanulife.com"),
    Adapter("boi", "Bank of India Mutual Fund", r"^bank\s+of\s+india", list_boi, "boimf.in"),
    Adapter("bajaj", "Bajaj Finserv Mutual Fund", r"^bajaj\s+finserv", list_bajaj, "bajajamc.com"),
    Adapter("whiteoak", "WhiteOak Capital Mutual Fund", r"^white\s*oak", list_whiteoak, "mf.whiteoakamc.com"),
    Adapter("jm", "JM Financial Mutual Fund", r"^jm\s+financial", list_jm, "jmfinancialmf.com"),
    Adapter("oneamc", "360 ONE Mutual Fund", r"^360\s*one", list_oneamc, "360.one"),
    Adapter("quantum", "Quantum Mutual Fund", r"^quantum", list_quantum, "quantumamc.com"),
    Adapter("shriram", "Shriram Mutual Fund", r"^shriram", list_shriram, "shriramamc.in"),
    Adapter("jio", "Jio BlackRock Mutual Fund", r"^jio", list_jio, "jioblackrockamc.com"),
    Adapter("wealthco", "The Wealth Company Mutual Fund", r"wealth\s+company", list_wealthco, "wealthcompanyamc.in"),
    Adapter("angelone", "Angel One Mutual Fund", r"^angel\s*one", list_angelone, "angelonemf.com"),
    Adapter("capitalmind", "Capitalmind Mutual Fund", r"^capitalmind", list_capitalmind, "capitalmindmf.com"),
    Adapter("oldbridge", "Old Bridge Mutual Fund", r"^old\s*bridge", list_oldbridge, "oldbridgemf.com"),
    Adapter("choice", "Choice Mutual Fund", r"^choice", list_choice, "choicemf.com"),
    Adapter("alphagrep", "AlphaGrep Mutual Fund", r"^alpha\s*grep", list_alphagrep, "alphagrepmf.ai"),
    Adapter("carnelian", "Carnelian Mutual Fund", r"^carnelian", list_carnelian, "carnelianmf.com"),
    Adapter("monarch", "Monarch Mutual Fund", r"^monarch", list_monarch, "monarchamc.in"),
]
