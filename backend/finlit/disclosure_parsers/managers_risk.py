"""Risk-o-meter level, fund managers and benchmark per scheme, from the fund houses' own public web pages and files, and AMFI.

Every source here is what the fund house's (or AMFI's) public website shows any visitor, read with a normal browser User-Agent: no login,
no captcha, no cookie games. A value is stored only when the source states it as text (or, for Nippon India and Motilal Oswal, in the
file name of the risk-o-meter picture it shows, e.g. '/Riskometer/Very-High-Riskometer.png'); nothing is inferred or guessed.

Each `src_*` coroutine takes (client, index) and returns (rows, stats):
    rows   [(family, kind, as_of, value, source, source_url)]  kind in {"risk", "managers", "benchmark"}
           risk      {"scheme": "Very High", "benchmark": "High" | None}
           managers  {"names": ["Sailesh Raj Bhan", ...]}
           benchmark {"name": "Nifty 100 TRI"}
    stats  {"seen": n schemes read, "matched": n resolved to a family, "unmatched": [names...]}
`index` is finlit.portfolios.Index (load_index(pool)); names are resolved with index.resolve([name], AMC_RE[house]).
as_of is the date the source states for the figure when it states one, else the day it was read.

Sources (checked from the development sandbox, October 2026):
  amfi_te      amfiindia.com/api/tracking-error-data?MF_ID=..&strdt=dd-mmm-yyyy        benchmark of index funds and ETFs, every fund house
  dsp          dspim.com 'fund-performance-<month>.xlsx' (AMFI fund-performance layout)  benchmark + scheme and benchmark risk-o-meter
  sbi          sbimf.com /api/SchemeListingAPI/GetSchemeDetails (the site's anonymous token)  risk level + fund managers
  axis         axismf.com fund page (Next.js data 'schemesListResp', every scheme)        risk + benchmark (+ its risk) + managers
  nippon       mf.nipponindiaim.com FundsAndPerformance/Pages/<fund>.aspx                 risk (+ benchmark risk) from picture file names,
                                                                                         benchmark and managers as text
  tata         tatamutualfund.com category pages + fund pages (JSON-LD fundManager)       risk + benchmark + managers
  motilal      motilaloswalmf.com /query-index.json -> /mutual-funds/<fund> pages          risk + benchmark (+ its risk) + managers
  groww        growwmf.in home page list -> /mutual-funds/<fund> pages (Next.js data)      risk + benchmark (+ its risk) + managers
  mirae        miraeassetmf.co.in sitemap -> /mutual-fund-scheme/<cat>/<fund> pages       benchmark + managers (risk-o-meter is a picture only)
  whiteoak     mf.whiteoakamc.com/scheme-list/all-funds (Next.js data)                    risk only
  wealthco     wealthcompanyamc.in home page -> /our-funds/fund/<fund>/<id>/ pages         risk + benchmark (+ its risk) + managers
  shriram      shriramamc.in home page -> /mutual-funds/<fund> pages (Next.js data)        risk + benchmark + managers
  lic          licmf.com monthly 'Dashboard as on <date>.xlsx' (scheme dashboard)          benchmark + managers (risk-o-meters are pictures)
  canara       canararobeco.com monthly 'Canara-Dashboard-<Month>-<Year>.xlsx'             benchmark + managers (risk-o-meters are pictures)

Run: `python -m finlit.disclosure_parsers.managers_risk [--only sbi axis ...] [--write] [--json out.json]` prints per-source stats and
coverage per fund house (active scheme families) against DATABASE_URL; --write stores the rows with finlit.portfolios.put_facts.
"""

from __future__ import annotations

import asyncio
import html as _html
import io
import json
import logging
import re
import secrets
import string
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urljoin

import httpx

log = logging.getLogger("finlit.disclosure")

BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HEADERS = {"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "Accept-Language": "en-IN,en;q=0.9"}
CONCURRENCY = 4          # per-scheme page fetches in flight per fund house (polite)

Row = Tuple[str, str, Optional[date], dict, str, Optional[str]]

LEVELS = ("Low", "Low to Moderate", "Moderate", "Moderately High", "High", "Very High")
_LEVEL_KEY = {re.sub(r"[^a-z]", "", l.lower()): l for l in LEVELS}

AMC_RE = {
    "amfi": None,
    "dsp": re.compile(r"^DSP\b", re.I),
    "sbi": re.compile(r"^SBI\b", re.I),
    "axis": re.compile(r"^Axis\b", re.I),
    "nippon": re.compile(r"^Nippon\b", re.I),
    "tata": re.compile(r"^Tata\b", re.I),
    "motilal": re.compile(r"^Motilal\b", re.I),
    "groww": re.compile(r"^Groww\b", re.I),
    "mirae": re.compile(r"^Mirae\b", re.I),
    "whiteoak": re.compile(r"^WhiteOak\b", re.I),
    "wealthco": re.compile(r"Wealth Company", re.I),
    "shriram": re.compile(r"^Shriram\b", re.I),
    "lic": re.compile(r"^LIC\b", re.I),
    "canara": re.compile(r"^Canara\b", re.I),
}


# ------------------------------------------------------------------------------------------------------------- small helpers

def norm_level(text: Optional[str]) -> Optional[str]:
    """'VERY HIGH', 'Very High Risk', 'very-high-risk.png', 'Very-High-Riskometer.png', 'Low to Moderate' -> one of LEVELS; None otherwise.
    Only a whole match counts: anything that is not exactly one of the six SEBI levels (plus the words risk/riskometer/level) is refused."""
    if not text:
        return None
    t = str(text).rsplit("/", 1)[-1].lower()
    t = re.sub(r"\.(png|jpe?g|svg|gif|webp)$", "", t)
    t = re.sub(r"(riskometer|risk-o-meter|risk|level|indicator|scheme|benchmark|desktop|mobile|light|dark)", " ", t)
    k = re.sub(r"[^a-z]", "", t)
    return _LEVEL_KEY.get(k)


_HONORIFIC = re.compile(r"^(?:(?:mr|mrs|ms|miss|dr|shri|smt)(?:\.\s*|\s+))+", re.I)


def clean_person(name: str) -> Optional[str]:
    n = re.sub(r"\s+", " ", _html.unescape(name or "")).strip(" ,;|-")
    n = re.sub(r"\s*\((?:since|w\.e\.f|managing since)[^)]*\)", "", n, flags=re.I)
    n = _HONORIFIC.sub("", n).strip()
    if not n or len(n) > 80 or not re.search(r"[A-Za-z]{2}", n):
        return None
    return n


def uniq(seq: Iterable[str]) -> List[str]:
    out: List[str] = []
    for s in seq:
        if s and s not in out:
            out.append(s)
    return out


def text_of(fragment: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def next_flight_text(page: str) -> str:
    """The Next.js app-router payload (self.__next_f.push([1,"..."])) as one decoded string."""
    parts = []
    for m in re.finditer(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', page):
        try:
            parts.append(json.loads(m.group(1)))
        except ValueError:
            pass
    return "".join(parts)


def json_after(text: str, key: str, start: int = 0) -> Tuple[Any, int]:
    """The JSON value that follows '"key":' (first occurrence at/after start). (value, end offset) or (None, -1)."""
    i = text.find(f'"{key}":', start)
    if i < 0:
        return None, -1
    j = i + len(key) + 3
    try:
        v, end = json.JSONDecoder().raw_decode(text, j)
        return v, end
    except ValueError:
        return None, -1


def walk(obj) -> Iterable[dict]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)


def parse_date_any(s: Optional[str]) -> Optional[date]:
    s = (s or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        s = s[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%m/%d/%Y %H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


class Collector:
    """Builds rows for one source, resolving names to families and counting what matched."""

    def __init__(self, idx, house: str, source: str):
        self.idx, self.amc_re, self.source = idx, AMC_RE.get(house), source
        self.rows: List[Row] = []
        self.seen = 0
        self.matched = 0
        self.unmatched: List[str] = []
        self._fams: Dict[str, set] = {}

    def resolve(self, names: Sequence[str]) -> Optional[str]:
        self.seen += 1
        fam, _why = self.idx.resolve([n for n in names if n], self.amc_re)
        if fam is None:
            self.unmatched.append(next((n for n in names if n), "?"))
            return None
        self.matched += 1
        return fam

    def add(self, fam: str, kind: str, as_of: Optional[date], value: dict, url: Optional[str]) -> None:
        kinds = self._fams.setdefault(fam, set())
        if kind in kinds:          # first statement for a family wins (several plans of one scheme share it)
            return
        kinds.add(kind)
        self.rows.append((fam, kind, as_of, value, self.source, url))

    def scheme(self, names: Sequence[str], url: Optional[str], as_of: Optional[date], *, risk: Optional[str] = None,
               bench_risk: Optional[str] = None, managers: Sequence[str] = (), benchmark: Optional[str] = None) -> Optional[str]:
        risk, bench_risk = norm_level(risk), norm_level(bench_risk)
        mgrs = uniq(filter(None, (clean_person(m) for m in managers)))
        bm = re.sub(r"\s+", " ", _html.unescape(benchmark or "")).strip() or None
        if bm and bm.upper() in ("NA", "N/A", "-", "--"):
            bm = None
        if not (risk or mgrs or bm):
            return None
        fam = self.resolve(names)
        if fam is None:
            return None
        if risk:
            self.add(fam, "risk", as_of, {"scheme": risk, "benchmark": bench_risk}, url)
        if mgrs:
            self.add(fam, "managers", as_of, {"names": mgrs}, url)
        if bm:
            self.add(fam, "benchmark", as_of, {"name": bm}, url)
        return fam

    def result(self) -> Tuple[List[Row], dict]:
        return self.rows, {"seen": self.seen, "matched": self.matched, "unmatched": self.unmatched[:40], "rows": len(self.rows)}


async def get(client: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    last = None
    for attempt in range(3):
        try:
            r = await client.get(url, **kw)
            if r.status_code in (429, 502, 503, 504):
                raise httpx.HTTPStatusError(f"{r.status_code}", request=r.request, response=r)
            r.raise_for_status()
            return r
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (403, 404):
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
    raise last


async def gather_limited(coros, limit: int = CONCURRENCY):
    sem = asyncio.Semaphore(limit)

    async def one(c):
        async with sem:
            try:
                return await c
            except Exception as exc:          # one page failing never stops the others
                log.info("page failed: %r", exc)
                return None
    return await asyncio.gather(*(one(c) for c in coros))


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=httpx.Timeout(60.0), follow_redirects=True)


# ------------------------------------------------------------------------------------------------------------- AMFI tracking error

AMFI_MF_LIST = "https://www.amfiindia.com/api/populate-mf"
AMFI_TE = "https://www.amfiindia.com/api/tracking-error-data"
SRC_AMFI_TE = "AMFI tracking error disclosure (amfiindia.com/otherdata/tracking-error)"


async def src_amfi_te(client: httpx.AsyncClient, idx, today: Optional[date] = None):
    """Benchmark of every index fund and ETF, as each fund house files it with AMFI for its tracking-error disclosure."""
    c = Collector(idx, "amfi", SRC_AMFI_TE)
    today = today or date.today()
    houses = (await get(client, AMFI_MF_LIST)).json()
    ids = [h.get("mfId") for h in houses if isinstance(h, dict) and str(h.get("mfId") or "").isdigit()]
    # each fund house files on its own day: per house, the newest of the last 12 days that has rows
    async def one(mf_id):
        for back in range(1, 13):
            d = today - timedelta(days=back)
            got = (await get(client, AMFI_TE, params={"MF_ID": mf_id, "strdt": d.strftime("%d-%b-%Y")})).json()
            data = got.get("data") if isinstance(got, dict) else None
            if data:
                return d, data
        return None, []
    for got in await gather_limited([one(i) for i in ids]):
        day, data = got or (None, [])
        for r in data or []:
            if isinstance(r, dict) and r.get("Scheme_Name") and r.get("Benchmark"):
                c.scheme([r["Scheme_Name"]], "https://www.amfiindia.com/otherdata/tracking-error", day, benchmark=r["Benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- AMFI fund-performance layout (xlsx)

PERF_HEAD = ("scheme name", "benchmark", "riskometer scheme", "riskometer benchmark")


def parse_performance_xlsx(data: bytes) -> List[dict]:
    """Rows of a workbook in AMFI's fund-performance layout: Scheme Name | Benchmark | Riskometer Scheme | Riskometer Benchmark | NAV Date | ..."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            cols = None
            for row in ws.iter_rows(values_only=True):
                cells = [str(v).strip() if v is not None else "" for v in row]
                low = [re.sub(r"\s+", " ", v.lower()) for v in cells]
                if cols is None:
                    if all(h in low for h in PERF_HEAD):
                        cols = {h: low.index(h) for h in PERF_HEAD}
                        cols["nav date"] = low.index("nav date") if "nav date" in low else None
                    continue
                name = cells[cols["scheme name"]] if len(cells) > cols["scheme name"] else ""
                if not name or name.lower() == "scheme name" or name.lower().startswith(("disclaimer", "note")):
                    continue
                nd = None
                if cols["nav date"] is not None and len(row) > cols["nav date"]:
                    v = row[cols["nav date"]]
                    nd = v.date() if isinstance(v, datetime) else (v if isinstance(v, date) else parse_date_any(str(v or "")))
                out.append({"name": name, "benchmark": cells[cols["benchmark"]], "risk": cells[cols["riskometer scheme"]],
                            "bench_risk": cells[cols["riskometer benchmark"]], "nav_date": nd})
    finally:
        wb.close()
    return out


DSP_LIST = "https://www.dspim.com/mandatory-disclosures/portfolio-disclosures"
SRC_DSP = "DSP Mutual Fund, monthly fund performance file (dspim.com)"


async def src_dsp(client: httpx.AsyncClient, idx):
    c = Collector(idx, "dsp", SRC_DSP)
    page = (await get(client, DSP_LIST)).text
    links = re.findall(r'href="([^"]*fund-performance-[^"]+\.xlsx)"', page)
    if not links:
        return c.result()
    url = urljoin(DSP_LIST, links[0])             # the page lists the newest month first
    for r in parse_performance_xlsx((await get(client, url)).content):
        c.scheme([r["name"]], url, r["nav_date"], risk=r["risk"], bench_risk=r["bench_risk"], benchmark=r["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- SBI

SBI = "https://www.sbimf.com"
SRC_SBI = "SBI Mutual Fund website, scheme list (sbimf.com)"


def _sid(n: int = 30) -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(n))


async def src_sbi(client: httpx.AsyncClient, idx):
    """sbimf.com's own scheme list: the page asks /api/GenerateToken/Post/ for an anonymous visitor token, then the list (every fund, its
    RiskLevel and FundManagers, AsOnDate)."""
    c = Collector(idx, "sbi", SRC_SBI)
    r = await client.post(f"{SBI}/api/GenerateToken/Post/", json={"Requestid": str(uuid.uuid4()), "SessionId": _sid()})
    r.raise_for_status()
    tok = json.loads(r.json()["Data"])["CreateTokenResult"]["Data"]
    r = await client.post(f"{SBI}/api/SchemeListingAPI/GetSchemeDetails", headers={"Token": tok},
                          json={"Requestid": str(uuid.uuid4()), "SessionId": _sid(),
                                "Data": json.dumps({"FundId": None, "SchemeCodes": None, "SchemePlanType": None})})
    r.raise_for_status()
    funds = r.json()
    for f in funds if isinstance(funds, list) else []:
        if not isinstance(f, dict) or not f.get("FundName"):
            continue
        names = [f["FundName"]] + [s.get("SchemeName") for s in (f.get("Schemes") or []) if isinstance(s, dict)]
        mgrs = [m.get("Name") for m in (f.get("FundManagers") or []) if isinstance(m, dict)]
        c.scheme(names, f"{SBI}/mutual-fund", parse_date_any(f.get("AsOnDate")) or date.today(), risk=f.get("RiskLevel"), managers=mgrs)
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Axis

AXIS_PAGES = ("https://www.axismf.com/mutual-funds/debt-funds/axis-credit-risk-fund/io-dg/direct",)
SRC_AXIS = "Axis Mutual Fund website, fund pages (axismf.com)"


def parse_axis(page: str) -> List[dict]:
    """Every scheme the fund page carries in its 'schemesListResp' list (one entry per plan/option)."""
    flight = next_flight_text(page) or page.replace('\\"', '"')
    out = []
    pos = 0
    while True:
        arr, end = json_after(flight, "schemeInfo", pos)
        if end < 0:
            break
        pos = end
        for s in arr if isinstance(arr, list) else []:
            if not isinstance(s, dict) or not s.get("schemeTitle"):
                continue
            rk = s.get("riskoMeter") if isinstance(s.get("riskoMeter"), dict) else {}
            det = rk.get("riskometerDetails") if isinstance(rk.get("riskometerDetails"), dict) else {}
            bstat = det.get("benchmarkRiskStatus") or ""
            m = re.search(r"benchmark is (.+)$", bstat.strip(), re.I)
            out.append({"name": s["schemeTitle"], "risk": rk.get("riskType"), "benchmark": det.get("benchmark"),
                        "bench_risk": m.group(1) if m else None,
                        "managers": [x if isinstance(x, str) else (x or {}).get("name") for x in (s.get("fundManagers") or [])]})
    return out


async def src_axis(client: httpx.AsyncClient, idx):
    c = Collector(idx, "axis", SRC_AXIS)
    today = date.today()
    for url in AXIS_PAGES:
        for s in parse_axis((await get(client, url)).text):
            c.scheme([s["name"]], url, today, risk=s["risk"], bench_risk=s["bench_risk"], managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Nippon India

NIPPON = "https://mf.nipponindiaim.com"
NIPPON_LISTS = ("/our-products/by-asset-class/equity-funds", "/our-products/by-asset-class/debt-funds", "/our-products/by-asset-class/liquid-funds",
                "/our-products/by-asset-class/gold-funds", "/our-products/retirement-funds")
SRC_NIPPON = "Nippon India Mutual Fund website, fund pages (mf.nipponindiaim.com)"


def parse_nippon(page: str) -> dict:
    def by_id(i):
        m = re.search(rf'id="{i}"[^>]*>(.*?)</', page, re.S)
        return text_of(m.group(1)) if m else None

    def img(i):
        m = re.search(rf'<img[^>]*id="{i}"[^>]*src="([^"]+)"', page) or re.search(rf'<img[^>]*src="([^"]+)"[^>]*id="{i}"', page)
        return m.group(1) if m else None
    mg = re.search(r'id="[^"]*spanFundManagerTitle"[^>]*>(.*?)</span>', page, re.S)
    managers = [p for p in re.split(r"\s*[|,]\s*", text_of(mg.group(1))) if p] if mg else []
    return {"name": by_id("RiskometerScheme"), "risk": img("imgHeaderRisk"), "benchmark": by_id("RiskometerBenchmark"),
            "bench_risk": img("imgHeaderBenchmarkRisk"), "managers": managers}


async def src_nippon(client: httpx.AsyncClient, idx):
    c = Collector(idx, "nippon", SRC_NIPPON)
    links: List[str] = []
    try:                                           # the site map lists every fund page; the category pages show only their first page
        sm = (await get(client, NIPPON + "/sitemap.xml")).text
        links = uniq(urljoin(NIPPON, l) for l in re.findall(r"<(?:\w+:)?loc>\s*([^<]*/FundsAndPerformance/Pages/[^<]+\.aspx)\s*</(?:\w+:)?loc>", sm)
                     if "Constituents" not in l)
    except Exception as exc:
        log.info("nippon sitemap: %r", exc)
    for p in NIPPON_LISTS:
        try:
            t = (await get(client, NIPPON + p)).text
        except Exception as exc:
            log.info("nippon list %s: %r", p, exc)
            continue
        for l in re.findall(r"""href=['"]([^'"]*/FundsAndPerformance/Pages/[^'"]+\.aspx)['"]""", t):
            u = urljoin(NIPPON, l)
            if u not in links:
                links.append(u)

    async def one(u):
        return u, parse_nippon((await get(client, u)).text)
    today = date.today()
    for got in await gather_limited([one(u) for u in links]):
        if not got:
            continue
        u, s = got
        title = re.sub(r"-", " ", u.rsplit("/", 1)[-1][:-5]).replace("NipponIndia", "Nippon India")
        c.scheme([s["name"], title], u, today, risk=s["risk"], bench_risk=s["bench_risk"], managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Tata

TATA = "https://www.tatamutualfund.com"
TATA_LISTS = ("equity-funds", "debt-funds", "hybrid-funds", "index-funds", "etf-exchange-traded-funds", "liquid-funds", "overnight-funds",
              "investment-solutions-funds", "tax-savings-mutual-funds")
SRC_TATA = "Tata Mutual Fund website, fund lists and pages (tatamutualfund.com)"
_TATA_ROW = re.compile(r'"scheme_name":"((?:[^"\\]|\\.)+)","benchmark":"((?:[^"\\]|\\.)*)","secondary_benchmark":"(?:[^"\\]|\\.)*",'
                       r'"riskometer":"((?:[^"\\]|\\.)*)","scheme_slug":"([^"]+)"')


def parse_tata_list(page: str) -> List[dict]:
    t = page.replace('\\"', '"')
    dec = lambda v: json.loads(f'"{v}"')          # noqa: E731  (the values are JSON string bodies: '\\u0026' -> '&')
    return [{"name": dec(m.group(1)), "benchmark": dec(m.group(2)), "risk": dec(m.group(3)), "slug": m.group(4)} for m in _TATA_ROW.finditer(t)]


def parse_tata_page(page: str) -> dict:
    flight = next_flight_text(page)
    fm, _ = json_after(flight, "fundManagersData")
    names = [x.get("manager_name") for x in fm if isinstance(x, dict)] if isinstance(fm, list) else []
    if not names:                                  # the page's JSON-LD (schema.org) block names them too
        fm, _ = json_after(page.replace('\\"', '"'), "fundManager")
        names = [x.get("name") for x in fm if isinstance(x, dict)] if isinstance(fm, list) else []
    br = re.search(r'alt="Benchmark riskometer: ([^"]+)"', page)
    return {"managers": names, "bench_risk": br.group(1) if br else None}


async def src_tata(client: httpx.AsyncClient, idx):
    c = Collector(idx, "tata", SRC_TATA)
    schemes: Dict[str, dict] = {}
    hrefs: List[str] = []
    for cat in TATA_LISTS:
        try:
            t = (await get(client, f"{TATA}/mutual-funds/{cat}")).text
        except Exception as exc:
            log.info("tata list %s: %r", cat, exc)
            continue
        for s in parse_tata_list(t):
            schemes.setdefault(s["slug"], s)
        hrefs += re.findall(r'href="(/mutual-funds/tata-[^"?#]+)"', t)

    async def one(slug):
        cands = [h for h in hrefs if h.startswith(f"/mutual-funds/{slug}-")] or [f"/mutual-funds/{slug}-direct-growth"]
        u = TATA + sorted(cands, key=lambda h: ("direct-growth" not in h, len(h)))[0]
        return slug, u, parse_tata_page((await get(client, u)).text)
    pages = {g[0]: g[1:] for g in await gather_limited([one(s) for s in schemes]) if g}
    today = date.today()
    for slug, s in schemes.items():
        u, p = pages.get(slug, (f"{TATA}/mutual-funds/{slug}", {"managers": [], "bench_risk": None}))
        c.scheme([s["name"]], u, today, risk=s["risk"], bench_risk=p["bench_risk"], managers=p["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Motilal Oswal

MOTILAL = "https://www.motilaloswalmf.com"
SRC_MOTILAL = "Motilal Oswal Mutual Fund website, fund pages (motilaloswalmf.com)"


def _kv(page: str, key: str) -> List[str]:
    return [text_of(v) for v in re.findall(rf"<strong>{key}:</strong>\s*(.*?)</(?:li|p)>", page, re.S)]


def parse_motilal(page: str) -> dict:
    names = _kv(page, "schemeName")
    risk = _kv(page, "riskType")
    brisk = _kv(page, "benchmarkRisk")
    bm = _kv(page, "benchmark")
    return {"name": names[0] if names else None, "risk": risk[0] if len(set(risk)) == 1 else None,
            "bench_risk": brisk[0] if len(set(brisk)) == 1 else None, "benchmark": bm[0] if len(set(bm)) == 1 else None,
            "managers": _kv(page, "fundManagerName")}


async def src_motilal(client: httpx.AsyncClient, idx):
    c = Collector(idx, "motilal", SRC_MOTILAL)
    data = (await get(client, f"{MOTILAL}/query-index.json", params={"limit": 2000})).json().get("data") or []
    paths = [d["path"] for d in data if isinstance(d, dict) and re.fullmatch(r"/mutual-funds/motilal-oswal-[a-z0-9-]+", d.get("path") or "")]

    async def one(p):
        return p, parse_motilal((await get(client, MOTILAL + p)).text)
    today = date.today()
    for got in await gather_limited([one(p) for p in paths]):
        if not got:
            continue
        p, s = got
        title = p.rsplit("/", 1)[-1].replace("-", " ")
        c.scheme([s["name"], title], MOTILAL + p, today, risk=s["risk"], bench_risk=s["bench_risk"], managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Groww

GROWW = "https://www.growwmf.in"
SRC_GROWW = "Groww Mutual Fund website, fund pages (growwmf.in)"


def _next_data(page: str):
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def parse_groww(page: str) -> Optional[dict]:
    nd = _next_data(page)
    if nd is None:
        return None
    for d in walk(nd):
        if "fundManagerDetailsList" in d or "benchmarkRiskRating" in d:
            fms = [f.get("fundManagerName") for f in (d.get("fundManagerDetailsList") or [])
                   if isinstance(f, dict) and not f.get("fundManagerEndDate")]
            bl = d.get("benchmarkDetailsList") or []
            bm = bl[0].get("benchmarkName") if bl and isinstance(bl[0], dict) else None
            return {"name": d.get("schemeName") or d.get("fundName"), "risk": d.get("risk"), "bench_risk": d.get("benchmarkRiskRating"),
                    "benchmark": bm, "managers": fms, "as_of": d.get("benchmarkReturnsDate")}
    return None


async def src_groww(client: httpx.AsyncClient, idx):
    c = Collector(idx, "groww", SRC_GROWW)
    home = (await get(client, GROWW + "/")).text.replace('\\"', '"')
    ids = uniq(re.findall(r'"searchId":"([a-z0-9-]+)"', home))

    async def one(sid):
        u = f"{GROWW}/mutual-funds/{sid}"
        return u, sid, parse_groww((await get(client, u)).text)
    today = date.today()
    for got in await gather_limited([one(s) for s in ids]):
        if not got or not got[2]:
            continue
        u, sid, s = got
        c.scheme([s["name"], sid.replace("-", " ")], u, today, risk=s["risk"], bench_risk=s["bench_risk"], managers=s["managers"],
                 benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Mirae Asset

MIRAE = "https://www.miraeassetmf.co.in"
SRC_MIRAE = "Mirae Asset Mutual Fund website, fund pages (miraeassetmf.co.in)"


def parse_mirae(page: str) -> dict:
    def fact(label):
        m = re.search(rf'<h3 class="subheading_h3">\s*{label}\s*:?\s*</h3>(.*?)</div>', page, re.S | re.I)
        return [text_of(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", m.group(1), re.S)] if m else []
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    bm = fact("benchmark index")
    return {"name": text_of(title.group(1)).split("|")[0].strip() if title else None, "managers": fact("fund manager"),
            "benchmark": bm[0] if len(bm) == 1 else None}


async def src_mirae(client: httpx.AsyncClient, idx):
    c = Collector(idx, "mirae", SRC_MIRAE)
    sm = (await get(client, MIRAE + "/sitemap.xml")).text
    home = (await get(client, MIRAE + "/")).text
    links = uniq(l for l in re.findall(r"(/mutual-fund-scheme/[a-z-]+/[a-z0-9-]+)", sm + home)
                 if not re.match(r"/mutual-fund-scheme/(?:dividend|nav|idcw)-", l))

    async def one(l):
        return l, parse_mirae((await get(client, MIRAE + l)).text)
    today = date.today()
    for got in await gather_limited([one(l) for l in links]):
        if not got:
            continue
        l, s = got
        slug = l.rsplit("/", 1)[-1].replace("-", " ")
        c.scheme([slug, re.sub(r"\bfund of funds?\b", "fof", slug), s["name"]], MIRAE + l, today, managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- WhiteOak Capital

WHITEOAK = "https://mf.whiteoakamc.com/scheme-list/all-funds"
SRC_WHITEOAK = "WhiteOak Capital Mutual Fund website, all funds list (mf.whiteoakamc.com)"


async def src_whiteoak(client: httpx.AsyncClient, idx):
    """The all-funds list carries every plan's scheme_name and risk_type (managers and benchmark are not in it)."""
    c = Collector(idx, "whiteoak", SRC_WHITEOAK)
    t = (await get(client, WHITEOAK)).text
    flight = next_flight_text(t) or t.replace('\\"', '"')
    for m in re.finditer(r'"scheme_name":"((?:[^"\\]|\\.)+)"', flight):
        seg = flight[m.end(): m.end() + 1500]
        r = re.search(r'"risk_type":"([^"]*)"', seg)
        if r:
            c.scheme([json.loads(f'"{m.group(1)}"')], WHITEOAK, date.today(), risk=r.group(1))
    return c.result()


# ------------------------------------------------------------------------------------------------------------- The Wealth Company

WEALTHCO = "https://www.wealthcompanyamc.in"
SRC_WEALTHCO = "The Wealth Company Mutual Fund website, fund pages (wealthcompanyamc.in)"


def parse_wealthco(page: str) -> dict:
    f = next_flight_text(page) or page.replace('\\"', '"')
    sr, _ = json_after(f, "schemeRisk")
    br, _ = json_after(f, "benchmarkRisk")
    fm, _ = json_after(f, "fundManagers")
    bm, _ = json_after(f, "benchMark")
    return {"risk": sr.get("risk") if isinstance(sr, dict) else None, "bench_risk": br.get("risk") if isinstance(br, dict) else None,
            "managers": [x.get("name") for x in fm if isinstance(x, dict)] if isinstance(fm, list) else [],
            "benchmark": bm if isinstance(bm, str) else None}


async def src_wealthco(client: httpx.AsyncClient, idx):
    c = Collector(idx, "wealthco", SRC_WEALTHCO)
    t = (await get(client, WEALTHCO + "/")).text + (await get(client, WEALTHCO + "/our-funds/")).text   # the home page links each fund
    links = uniq(urljoin(WEALTHCO + "/", l) for l in re.findall(r'href="(/?our-funds/fund/[^"]+)"', t))

    async def one(u):
        return u, parse_wealthco((await get(client, u)).text)
    for got in await gather_limited([one(u) for u in links]):
        if not got:
            continue
        u, s = got
        slug = _html.unescape(u.rstrip("/").split("/")[-2]).replace("-", " ")
        c.scheme([slug], u, date.today(), risk=s["risk"], bench_risk=s["bench_risk"], managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- Shriram

SHRIRAM = "https://www.shriramamc.in"
SRC_SHRIRAM = "Shriram Mutual Fund website, fund pages (shriramamc.in)"


def parse_shriram(page: str, slug: str) -> dict:
    f = next_flight_text(page) or page.replace('\\"', '"')
    fm, _ = json_after(f, "fundManagementData")
    m = re.search(r'"schemename":"((?:[^"\\]|\\.)+)","benchmark":"((?:[^"\\]|\\.)*)","scheme_title_slug":"' + re.escape(slug) + '"', f)
    risks = set(re.findall(r'"risk_label":"([^"]*)"', f))
    return {"name": json.loads(f'"{m.group(1)}"') if m else None, "benchmark": json.loads(f'"{m.group(2)}"') if m else None,
            "risk": next(iter(risks)) if len(risks) == 1 else None,
            "managers": [x.get("name") for x in fm if isinstance(x, dict)] if isinstance(fm, list) else []}


async def src_shriram(client: httpx.AsyncClient, idx):
    c = Collector(idx, "shriram", SRC_SHRIRAM)
    t = (await get(client, SHRIRAM + "/")).text
    slugs = uniq(re.findall(r'href="/mutual-funds/([a-z0-9-]+)"', t))

    async def one(sl):
        u = f"{SHRIRAM}/mutual-funds/{sl}"
        return u, sl, parse_shriram((await get(client, u)).text, sl)
    for got in await gather_limited([one(sl) for sl in slugs]):
        if not got:
            continue
        u, sl, s = got
        if not s["name"]:                 # without the page's own scheme name the facts are not tied to a scheme
            continue
        c.scheme([s["name"]], u, date.today(), risk=s["risk"], managers=s["managers"], benchmark=s["benchmark"])
    return c.result()


# ------------------------------------------------------------------------------------------------------------- scheme dashboard (xlsx)

def split_managers(text: str) -> List[str]:
    """'Mr. A (Equity - managing since 07/04/26) & Mr. B (Debt ...)' -> ['A', 'B']: role and date notes are dropped. Names are the words
    after each honorific (Mr/Ms/Mrs/Dr); a cell without honorifics is split on '&', ',', ';' and new lines."""
    t = re.sub(r"\([^)]*\)?", " ", text or "", flags=re.S)                       # '(Managing scheme since ...)', also an unclosed one
    t = re.sub(r"\bFund\s+Man(?:a)?ger\s*[-:–]", " ", t, flags=re.I)
    t = re.sub(r"\s+(?:Equity|Debt|Commodity|Overseas|Gold|Silver|Arbitrage)\s*-\s*managing[^&\n]*", " ", t, flags=re.I)
    t = re.sub(r"\s*-\s*$|\s+-\s+", " ", t, flags=re.M)
    named = re.findall(r"\b(?:Mr|Ms|Mrs|Dr)\b\.?\s*([A-Z][A-Za-z'.]*(?:\s+[A-Z][A-Za-z'.]*){0,4})", t)
    parts = named or re.split(r"\s*(?:&|;|,|\n|\band\b)\s*", t)
    return uniq(filter(None, (clean_person(p) for p in parts)))


def parse_dashboard_xlsx(data: bytes) -> List[dict]:
    """SEBI/AMFI 'scheme dashboard' workbooks: a label column, then one block of columns per scheme. Rows used: 'Scheme Name',
    'Fund Manager', 'Benchmark Riskometer' ('First Tier Benchmark - <index>'). Values are read from the scheme's own column."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    out = []
    try:
        for ws in wb.worksheets:
            rows = [r for r in ws.iter_rows(values_only=True)]
            lab = lambda r: re.sub(r"\s+", " ", str(r[0] or "")).strip().lower() if r else ""   # noqa: E731
            head = next((r for r in rows[:10] if r and any(str(c or "").strip().lower() == "scheme name" for c in r)
                         and any(str(c or "").strip().lower().startswith("fund manager") for c in r)), None)
            if head is not None:                    # one row per scheme: Sr.No. | Scheme Name | ... | Benchmark | Fund Manager | ...
                h = [re.sub(r"\s+", " ", str(c or "")).strip().lower() for c in head]
                ni = h.index("scheme name")
                fi = next(i for i, x in enumerate(h) if x.startswith("fund manager"))
                bi = h.index("benchmark") if "benchmark" in h else None
                for r in rows:
                    if not r or len(r) <= max(ni, fi) or not str(r[0] or "").strip().isdigit() or not r[ni]:
                        continue
                    bmv = re.sub(r"\s+", " ", str(r[bi] or "")).strip() if bi is not None and len(r) > bi else ""
                    out.append({"name": re.sub(r"\s+", " ", str(r[ni])).strip(), "managers": split_managers(str(r[fi] or "")),
                                "benchmark": bmv if bmv and len(bmv) < 200 else None})
                continue
            names = next((r for r in rows if lab(r) == "scheme name"), None)
            if not names:
                continue
            fm = next((r for r in rows if lab(r).startswith("fund manager")), ())
            if not fm:                              # a sheet without a fund manager row (e.g. a product-label sheet) is not a dashboard
                continue
            bm = next((r for r in rows if lab(r).startswith("benchmark riskometer")), ())
            for i, v in enumerate(names):
                if i == 0 or not v or not str(v).strip():
                    continue
                name = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9)]+$", "", str(v).strip())
                b = str(bm[i]).strip() if i < len(bm) and bm[i] else ""
                b = re.sub(r"^(?:first\s+)?tier[\s-]*(?:1|i|one)?\s*benchmark\s*[-:–]\s*", "", b, flags=re.I) if b else ""
                out.append({"name": name, "managers": split_managers(str(fm[i])) if i < len(fm) and fm[i] else [],
                            "benchmark": b if b and len(b) < 200 and "suitable" not in b.lower() else None})
    finally:
        wb.close()
    return out


async def dashboard_rows(client: httpx.AsyncClient, c: "Collector", pages: Sequence[str], link_re: str):
    """Find the newest dashboard workbook linked from `pages` (first link on the page) and add its schemes to the collector."""
    url = None
    for page in pages:
        try:
            t = (await get(client, page)).text
        except Exception as exc:
            log.info("dashboard list %s: %r", page, exc)
            continue
        links = [_html.unescape(l) for l in re.findall(r'href="([^"]+\.xlsx)"', t) if re.search(link_re, l, re.I)]
        if links:
            url = urljoin(page, links[0])
            break
    if not url:
        return
    m = re.search(r"as-on-(\d{1,2})-([A-Za-z]+)-(\d{4})", url)
    m2 = re.search(r"Dashboard-([A-Za-z]+)-(\d{4})", url)
    if m:
        as_of = parse_date_any(f"{m.group(1)}-{m.group(2)[:3]}-{m.group(3)}")
    elif m2:                                          # 'Dashboard-September-2026': the month's last day
        first = parse_date_any(f"01-{m2.group(1)[:3]}-{m2.group(2)}")
        as_of = (date(first.year + first.month // 12, first.month % 12 + 1, 1) - timedelta(days=1)) if first else None
    else:
        as_of = None
    for r in parse_dashboard_xlsx((await get(client, url)).content):
        c.scheme([r["name"]], url, as_of or date.today(), managers=r["managers"], benchmark=r["benchmark"])


LIC_PAGES = ("https://www.licmf.com/downloads/scheme-related/dashboard", "https://www.licmf.com/downloads/risk-o-meter-disclosure")
SRC_LIC = "LIC Mutual Fund, monthly scheme dashboard (licmf.com)"
CANARA_PAGES = ("https://www.canararobeco.com/documents/statutory-disclosures/scheme-dashboard/",)
SRC_CANARA = "Canara Robeco Mutual Fund, monthly scheme dashboard (canararobeco.com)"


async def src_lic(client: httpx.AsyncClient, idx):
    """LIC's monthly 'Dashboard as on <date>' workbook: fund managers and first-tier benchmark of every scheme (its risk-o-meters are pictures)."""
    c = Collector(idx, "lic", SRC_LIC)
    await dashboard_rows(client, c, LIC_PAGES, r"Dashboard")
    return c.result()


async def src_canara(client: httpx.AsyncClient, idx):
    """Canara Robeco's monthly 'Canara-Dashboard-<Month>-<Year>.xlsx': benchmark and fund managers per scheme (risk-o-meters are pictures)."""
    c = Collector(idx, "canara", SRC_CANARA)
    await dashboard_rows(client, c, CANARA_PAGES, r"Dashboard")
    return c.result()


# ------------------------------------------------------------------------------------------------------------- all

SOURCES = {
    "amfi_te": src_amfi_te,
    "dsp": src_dsp,
    "sbi": src_sbi,
    "axis": src_axis,
    "nippon": src_nippon,
    "tata": src_tata,
    "motilal": src_motilal,
    "groww": src_groww,
    "mirae": src_mirae,
    "whiteoak": src_whiteoak,
    "wealthco": src_wealthco,
    "shriram": src_shriram,
    "lic": src_lic,
    "canara": src_canara,
}


async def collect(idx, only: Optional[Sequence[str]] = None, client: Optional[httpx.AsyncClient] = None) -> Tuple[List[Row], Dict[str, dict]]:
    """Run every source (or `only`); each fails alone. Returns (rows, {source: stats or {"error": ...}})."""
    own = client is None
    client = client or make_client()
    rows: List[Row] = []
    stats: Dict[str, dict] = {}
    try:
        for name, fn in SOURCES.items():
            if only and name not in only:
                continue
            try:
                r, s = await fn(client, idx)
                rows += r
                stats[name] = s
            except Exception as exc:
                log.warning("managers/risk source %s failed: %r", name, exc)
                stats[name] = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        if own:
            await client.aclose()
    return rows, stats


def merge_rows(rows: Sequence[Row]) -> List[Row]:
    """One row per (family, kind): a fund house's own statement beats AMFI's tracking-error benchmark; otherwise the first wins."""
    best: Dict[Tuple[str, str], Row] = {}
    for r in rows:
        k = (r[0], r[1])
        if k not in best or (best[k][4] == SRC_AMFI_TE and r[4] != SRC_AMFI_TE):
            best[k] = r
    return list(best.values())


# ------------------------------------------------------------------------------------------------------------- runner

async def _main(argv: Optional[Sequence[str]] = None) -> None:
    import argparse
    import os
    import asyncpg
    try:
        from ..portfolios import load_index, put_facts
    except ImportError:                                   # older layout
        from ..disclosure import load_index, put_facts    # type: ignore

    ap = argparse.ArgumentParser(description="Fetch risk-o-meter / fund managers / benchmark and report coverage")
    ap.add_argument("--only", nargs="*", help=f"sources to run: {', '.join(SOURCES)}")
    ap.add_argument("--write", action="store_true", help="store rows with put_facts")
    ap.add_argument("--json", help="write rows and stats to this file")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pool = await asyncpg.create_pool(os.environ.get("DATABASE_URL", "postgresql://finlit:finlit@127.0.0.1:5432/finlit_dev"), min_size=1, max_size=2)
    try:
        idx = await load_index(pool)
        rows, stats = await collect(idx, a.only)
        rows = merge_rows(rows)
        for k, v in stats.items():
            print(k, json.dumps({x: y for x, y in v.items() if x != "unmatched"}), "unmatched:", (v.get("unmatched") or [])[:12])
        if a.json:
            with open(a.json, "w") as fh:
                json.dump({"stats": stats, "rows": [[r[0], r[1], r[2].isoformat() if r[2] else None, r[3], r[4], r[5]] for r in rows]}, fh, indent=1)
        if a.write:
            print("stored", await put_facts(pool, rows))
        fams = {}
        for f, k, *_ in rows:
            fams.setdefault(f, set()).add(k)
        async with pool.acquire() as conn:
            act = await conn.fetch("SELECT amc, family FROM mf_schemes WHERE active GROUP BY amc, family")
        per: Dict[str, List[int]] = {}
        for r in act:
            p = per.setdefault(r["amc"], [0, 0, 0, 0])
            ks = fams.get(r["family"], set())
            p[0] += 1
            p[1] += "risk" in ks
            p[2] += "managers" in ks
            p[3] += "benchmark" in ks
        print(f"{'fund house':40} {'families':>8} {'risk':>5} {'mgrs':>5} {'bench':>5}")
        tot = [0, 0, 0, 0]
        for amc, p in sorted(per.items(), key=lambda kv: -kv[1][0]):
            tot = [x + y for x, y in zip(tot, p)]
            print(f"{amc[:40]:40} {p[0]:>8} {p[1]:>5} {p[2]:>5} {p[3]:>5}")
        print(f"{'TOTAL (active families)':40} {tot[0]:>8} {tot[1]:>5} {tot[2]:>5} {tot[3]:>5}")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(_main())
