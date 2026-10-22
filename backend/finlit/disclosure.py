"""Fund disclosures: holdings, sector split, AUM, expense ratio, benchmark, risk-o-meter, launch date and minimum investment, from official free files only.

Read side (used by finlit/mf.py and finlit/etf.py, never raises on missing data)
    get_portfolio(pool, key)  the JSON contract of the fund pages: {asOf, previousAsOf, source, sourceUrl, holdings[], exited[], summary{}} or None
    get_facts(pool, key)      {aum, terRegular, terDirect, exitLoad, benchmark, managers, riskometer, launchDate, minInvestment}, each {value, asOf, source}
                              or {unavailable: reason}
  `key` is an AMFI scheme code (int or digits) or a scheme / ETF ISIN. Schemes are stored by FAMILY (mf_schemes.family): the plans and options of one scheme
  share the portfolio, the TER row, the benchmark.

Write side (the `refresh-disclosures` worker command)
    refresh(store, settings, only=None) -> dict
  Steps, each independent and each failing alone: AMFI scheme master (launch, minimum), NSE share list (ISIN -> symbol), AMFI fund performance (benchmark,
  risk-o-meter, AUM), AMFI TER, AMFI quarterly average AUM, then each fund house's monthly portfolio files (finlit/disclosure_parsers/amcs.py). One file is
  downloaded, parsed, validated and written at a time and freed before the next. A file that fails validation is reported and NOT stored; a short or odd answer
  never replaces a good row; only the latest 3 month-ends are kept per scheme. Nothing here keeps a timer or a connection open between runs.

Where no free official source was verified (exit load, fund manager) nothing is stored and the reason is returned.
This is information only, never advice.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import shutil
import sys
import tempfile
import unicodedata
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import httpx

from .config import MF_EXCLUDED_AMCS
from .disclosure_parsers import amfi
from .disclosure_parsers.amcs import ADAPTERS, BROWSER_UA, MAX_BYTES, UA, Adapter, FileRef, month_ends
from .disclosure_parsers.model import (ASSET_CLASSES, Fact, Facts, Holding, Portfolio, Verdict, isin_ok, validate)
from .disclosure_parsers.sebi import NotAPortfolio, open_workbook, parse_rows

log = logging.getLogger("finlit.disclosure")

__all__ = ["Holding", "Portfolio", "Facts", "Fact", "Verdict", "validate", "isin_ok", "get_portfolio", "get_facts", "refresh", "KEEP_MONTHS"]

KEEP_MONTHS = 3                      # monthly disclosures kept per scheme
MIN_KEEP_RATIO = 0.9                 # a re-read file with fewer holdings than this share of the stored one is not applied
CLS = {"equity": "e", "debt": "d", "cash": "c", "other": "o"}
CLS_BACK = {v: k for k, v in CLS.items()}
SRC_MASTER = "AMFI scheme master (portal.amfiindia.com)"
SRC_PERF = "AMFI fund performance (amfiindia.com/otherdata/fund-performance)"
SRC_TER = "AMFI TER of MF schemes (amfiindia.com/ter-of-mf-schemes)"
SRC_AAUM = "AMFI average AUM scheme-wise (amfiindia.com)"
SRC_DETAILS = "AMFI scheme details (amfiindia.com/otherdata/scheme-details)"
URL_MF_LIST = "https://www.amfiindia.com/api/populate-mf"
URL_SCHEMES = "https://www.amfiindia.com/api/populate-scheme"
URL_DETAILS = "https://www.amfiindia.com/api/scheme-details"
LOAD_MAX_AGE_DAYS = 25               # a scheme's load text is asked again after this many days
URL_MASTER = "https://portal.amfiindia.com/DownloadSchemeData_Po.aspx?mf=0"
URL_PERF = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi/fundperformance"
URL_PERF_SUB = "https://www.amfiindia.com/gateway/pollingsebi/api/amfi/getsubcategory"
URL_TER_MONTHS = "https://www.amfiindia.com/api/populate-ter-month"
URL_TER = "https://www.amfiindia.com/api/populate-te-rdata-revised"
URL_AAUM = "https://www.amfiindia.com/api/average-aum-schemewise"
URL_EQUITY_L = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"

NO_EXIT_LOAD = ("AMFI's scheme details leave the load blank for this scheme; it is published in the scheme's Scheme Information Document and factsheet (PDF, different layout at every fund house); "
                "no free machine-readable official source was verified, so none is shown.")
NO_MANAGERS = ("Fund managers are named in each scheme's factsheet and Scheme Information Document (PDF); no free machine-readable official source "
               "was verified, so none is shown.")


# ------------------------------------------------------------------------------------------------------------- names

_DROP = frozenset("direct regular plan plans growth option options idcw dividend payout reinvestment reinvest bonus the and of scheme".split())
_PAREN = re.compile(r"\([^)]*\)")
_FORMERLY = re.compile(r"\(\s*(?:formerly|erstwhile|earlier|ex)\b[\s\S]*$", re.I)


def name_key(name: str, drop_parens: bool = False, drop_fund: bool = False) -> str:
    """A scheme name reduced to a comparable key: lower case, punctuation gone, plan / option / filler words dropped, words sorted. 'X Fund - Direct Plan -
    Growth' and 'X FUND (An open ended ...)' agree. Collisions are detected by the caller (a key that maps to two families is refused, not guessed)."""
    s = unicodedata.normalize("NFKD", name or "").lower()
    if drop_parens:
        s = _PAREN.sub(" ", _FORMERLY.sub(" ", s))
    s = s.replace("&", " and ")
    s = re.sub(r"\b(mid|large|small|flexi|multi|micro)\s*-?\s*cap\b", r"\1cap", s)       # 'Mid Cap' and 'Midcap' are the same word in AMFI's own lists
    toks = {t for t in re.sub(r"[^a-z0-9]+", " ", s).split() if t not in _DROP and not (drop_fund and t == "fund")}
    return " ".join(sorted(toks))


_EXCLUDED_START = re.compile(r"^\W*(ask|abakkus|iti|lakshya|nj|pgim india|samco|taurus|trust(?:mf)?|unifi|zerodha)\b", re.I)


def looks_excluded(scheme_name: str) -> bool:
    """A scheme name that starts with an excluded fund house's name (the feeds carry no fund-house column): left out of the 'unmapped' lists."""
    return bool(_EXCLUDED_START.match(scheme_name or ""))


def _house_stem(name: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", unicodedata.normalize("NFKD", name).lower().replace("&", " and "))
    t = re.sub(r"\b(?:mutual\s+fund|mf|asset\s+management|asset\s+managers|amc|company|limited|ltd|private|pvt)\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


_EXCLUDED = frozenset(_house_stem(n) for n in MF_EXCLUDED_AMCS)


def excluded_amc(amc: str) -> bool:
    return _house_stem(amc) in _EXCLUDED


class Index:
    """The scheme families in mf_schemes, for matching names from other sources. Built once per run (about 14 000 rows)."""

    def __init__(self):
        self.amc: Dict[str, str] = {}                 # family -> AMC name
        self.codes: Dict[str, List[int]] = defaultdict(list)
        self.by_code: Dict[int, str] = {}
        self.keys: Dict[str, Set[str]] = defaultdict(set)         # name_key -> families
        self.keys_np: Dict[str, Set[str]] = defaultdict(set)      # parenthesis-free key -> families
        self.keys_nf: Dict[str, Set[str]] = defaultdict(set)      # parenthesis-free and without the word 'fund'

    def add(self, code: int, name: str, amc: str, family: str) -> None:
        self.amc[family] = amc
        self.codes[family].append(code)
        self.by_code[code] = family
        self.keys[name_key(name)].add(family)
        self.keys_np[name_key(name, True)].add(family)
        self.keys_nf[name_key(name, True, True)].add(family)

    def resolve(self, names: Sequence[str], amc_re: Optional[re.Pattern] = None) -> Tuple[Optional[str], str]:
        """(family, reason). The first name that matches exactly one family wins; a name matching several families is ambiguous and refused."""
        why = "no scheme with this name in AMFI's list"
        for nm in names:
            if not nm:
                continue
            for table, drop, nof in ((self.keys, False, False), (self.keys_np, True, False), (self.keys_nf, True, True)):
                fams = table.get(name_key(nm, drop, nof), set())
                if amc_re is not None:
                    fams = {f for f in fams if amc_re.search(self.amc.get(f, ""))}
                if len(fams) == 1:
                    return next(iter(fams)), ""
                if len(fams) > 1:
                    why = f"name matches {len(fams)} schemes ({', '.join(sorted(fams))[:120]}); not guessed"
        return None, why


async def load_index(pool) -> Index:
    idx = Index()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT code, name, amc, family FROM mf_schemes")
    for r in rows:
        if excluded_amc(r["amc"]):
            continue
        idx.add(r["code"], r["name"], r["amc"], r["family"])
    return idx


# ------------------------------------------------------------------------------------------------------------- writes

def pack_holdings(hs: Sequence[Holding]) -> str:
    return json.dumps([[h.name, h.isin, h.sector, CLS[h.asset_class], h.pct_nav, h.qty, h.value_lakh] for h in hs], separators=(",", ":"), ensure_ascii=False)


def unpack_holdings(raw) -> List[Holding]:
    arr = json.loads(raw) if isinstance(raw, str) else raw
    return [Holding(a[0], a[1], a[2], CLS_BACK.get(a[3], "other"), a[4], a[5], a[6]) for a in arr]


async def store_portfolio(pool, fkey: str, amc: str, p: Portfolio) -> str:
    """Write one validated portfolio and prune to the latest KEEP_MONTHS. Returns stored | kept_existing | too_old."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            newest = await conn.fetch("SELECT as_of, n FROM disclosure_portfolios WHERE fkey = $1 ORDER BY as_of DESC LIMIT $2", fkey, KEEP_MONTHS)
            have = {r["as_of"]: r["n"] for r in newest}
            if len(newest) >= KEEP_MONTHS and p.as_of < newest[-1]["as_of"]:
                return "too_old"
            if p.as_of in have and len(p.holdings) < MIN_KEEP_RATIO * have[p.as_of]:
                return "kept_existing"
            total = sum(h.pct_nav for h in p.holdings)
            await conn.execute(
                """INSERT INTO disclosure_portfolios (fkey, as_of, amc, scheme_name, source, source_url, net_assets_lakh, pct_total, n, benchmark, notes, holdings, fetched_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb, now())
                   ON CONFLICT (fkey, as_of) DO UPDATE SET amc = EXCLUDED.amc, scheme_name = EXCLUDED.scheme_name, source = EXCLUDED.source, source_url = EXCLUDED.source_url,
                     net_assets_lakh = EXCLUDED.net_assets_lakh, pct_total = EXCLUDED.pct_total, n = EXCLUDED.n, benchmark = EXCLUDED.benchmark, notes = EXCLUDED.notes,
                     holdings = EXCLUDED.holdings, fetched_at = now()""",
                fkey, p.as_of, amc, p.scheme_name, p.source_name, p.source_url, p.net_assets_lakh, round(total, 6), len(p.holdings), p.benchmark,
                json.dumps(p.notes), pack_holdings(p.holdings))
            await conn.execute("DELETE FROM disclosure_portfolios WHERE fkey = $1 AND as_of NOT IN (SELECT as_of FROM disclosure_portfolios WHERE fkey = $1 ORDER BY as_of DESC LIMIT $2)",
                               fkey, KEEP_MONTHS)
    return "stored"


async def put_facts(pool, rows: Sequence[Tuple[str, str, Optional[date], dict, str, Optional[str]]]) -> int:
    """Upsert (fkey, kind, as_of, value, source, url). A row older than the stored one for the same kind is ignored."""
    if not rows:
        return 0
    async with pool.acquire() as conn:
        await conn.executemany(
            """INSERT INTO disclosure_facts (fkey, kind, as_of, value, source, source_url, updated_at) VALUES ($1,$2,$3,$4::jsonb,$5,$6, now())
               ON CONFLICT (fkey, kind) DO UPDATE SET as_of = EXCLUDED.as_of, value = EXCLUDED.value, source = EXCLUDED.source, source_url = EXCLUDED.source_url, updated_at = now()
               WHERE disclosure_facts.as_of IS NULL OR EXCLUDED.as_of IS NULL OR EXCLUDED.as_of >= disclosure_facts.as_of""",
            [(f, k, d, json.dumps(v, separators=(",", ":")), s, u) for f, k, d, v, s, u in rows])
    return len(rows)


async def _run_done(pool, source: str, period: str) -> bool:
    async with pool.acquire() as conn:
        return bool(await conn.fetchval("SELECT 1 FROM disclosure_runs WHERE source = $1 AND period = $2 AND status = 'done'", source, period))


async def _run_mark(pool, source: str, period: str, status: str, detail: dict) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO disclosure_runs (source, period, status, detail, updated_at) VALUES ($1,$2,$3,$4::jsonb, now())
               ON CONFLICT (source, period) DO UPDATE SET status = EXCLUDED.status, detail = EXCLUDED.detail, updated_at = now()""",
            source, period, status, json.dumps(detail))


# ------------------------------------------------------------------------------------------------------------- reads

def _r6(x: float) -> float:
    return round(x, 6)


async def _family(conn, key) -> Optional[str]:
    k = str(key).strip()
    if not k:
        return None
    if k.isdigit():
        if len(k) > 9:
            return None
        return await conn.fetchval("SELECT family FROM mf_schemes WHERE code = $1", int(k))
    k = k.upper()
    if not re.fullmatch(r"[A-Z0-9]{12}", k):
        return None
    return await conn.fetchval("SELECT family FROM mf_schemes WHERE isin = $1 OR isin_reinvest = $1 LIMIT 1", k)


def _hkey(h: Holding) -> str:
    return h.isin or ("n:" + name_key(h.name))


def build_portfolio_json(cur: dict, prev: Optional[dict], symbols: Dict[str, str]) -> dict:
    hs = unpack_holdings(cur["holdings"])
    ph = unpack_holdings(prev["holdings"]) if prev else []
    pm: Dict[str, float] = {}
    for h in ph:
        pm[_hkey(h)] = pm.get(_hkey(h), 0.0) + h.pct_nav
    seen: Set[str] = set()
    out_h = []
    for h in hs:
        k = _hkey(h)
        seen.add(k)
        prevp = pm.get(k) if prev else None
        if not prev:
            change = None
        elif prevp is None:
            change = "new"
        elif abs(h.pct_nav - prevp) < 0.005:
            change = "unchanged"
        else:
            change = "increased" if h.pct_nav > prevp else "decreased"
        out_h.append({"name": h.name, "isin": h.isin, "sector": h.sector, "assetClass": h.asset_class, "pct": h.pct_nav, "qty": h.qty, "valueLakh": h.value_lakh,
                      "stockSymbol": symbols.get(h.isin) if h.isin else None, "prevPct": _r6(prevp) if prevp is not None else None, "change": change})
    exited = []
    if prev:
        for h in ph:
            if h.asset_class != "cash" and _hkey(h) not in seen:
                exited.append({"name": h.name, "isin": h.isin, "prevPct": h.pct_nav})
    split = {c: 0.0 for c in ASSET_CLASSES}
    sectors: Dict[str, float] = defaultdict(float)
    for h in hs:
        split[h.asset_class] += h.pct_nav
        if h.asset_class == "equity":
            sectors[h.sector or "Not classified"] += h.pct_nav
    top = sorted((h.pct_nav for h in hs if h.asset_class != "cash"), reverse=True)[:10]
    notes = cur["notes"] if isinstance(cur["notes"], list) else json.loads(cur["notes"] or "[]")
    res = {"asOf": cur["as_of"].isoformat(), "previousAsOf": prev["as_of"].isoformat() if prev else None, "source": cur["source"], "sourceUrl": cur["source_url"],
           "holdings": out_h, "exited": exited,
           "summary": {"count": len(hs), "top10Pct": _r6(sum(top)), "assetSplit": {c: _r6(v) for c, v in split.items()},
                       "sectors": [{"sector": s, "pct": _r6(v)} for s, v in sorted(sectors.items(), key=lambda kv: -kv[1])]}}
    if notes:
        res["notes"] = notes
    if cur["net_assets_lakh"] is not None:
        res["netAssetsLakh"] = cur["net_assets_lakh"]
    return res


async def get_portfolio(pool, key) -> Optional[dict]:
    """The latest stored monthly portfolio for a scheme code or ISIN in the fund-page contract, or None when nothing is stored."""
    async with pool.acquire() as conn:
        fkey = await _family(conn, key)
        if not fkey:
            return None
        rows = await conn.fetch("SELECT * FROM disclosure_portfolios WHERE fkey = $1 ORDER BY as_of DESC LIMIT 2", fkey)
        if not rows:
            return None
        cur = dict(rows[0])
        prev = dict(rows[1]) if len(rows) > 1 else None
        isins = list({h[1] for h in json.loads(cur["holdings"]) if h[1]})
        symbols: Dict[str, str] = {}
        if isins:
            got = await conn.fetch("SELECT i.isin, i.symbol FROM disclosure_isin i JOIN companies c ON c.symbol = i.symbol WHERE i.isin = ANY($1::text[])", isins)
            symbols = {r["isin"]: r["symbol"] for r in got}
    return build_portfolio_json(cur, prev, symbols)


def _iso(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


async def get_facts(pool, key) -> Optional[dict]:
    """AUM, TER (regular and direct), exit load, benchmark, managers, risk-o-meter, launch date and minimum investment. Each is {value, asOf, source} or
    {unavailable: reason}. None when the key is not a known scheme."""
    async with pool.acquire() as conn:
        fkey = await _family(conn, key)
        if not fkey:
            return None
        facts = {r["kind"]: dict(r) for r in await conn.fetch("SELECT kind, as_of, value, source, source_url FROM disclosure_facts WHERE fkey = $1", fkey)}
        port = await conn.fetchrow("SELECT as_of, source, source_url, net_assets_lakh, benchmark FROM disclosure_portfolios WHERE fkey = $1 ORDER BY as_of DESC LIMIT 1", fkey)

    def val(kind):
        f = facts.get(kind)
        if not f:
            return None
        v = f["value"]
        return (json.loads(v) if isinstance(v, str) else v), f

    out = Facts()
    # AUM: the newest dated figure among AMFI's daily AUM, the month-end net assets in the monthly portfolio, and AMFI's quarterly average
    cands: List[Tuple[date, int, dict]] = []
    a = val("aum_daily")
    if a:
        cands.append((a[1]["as_of"], 2, {"value": a[0]["crore"], "asOf": _iso(a[1]["as_of"]), "source": a[1]["source"] + " (AUM as shown beside the NAV date)", "basis": "daily", "unit": "crore"}))
    if port and port["net_assets_lakh"] is not None:
        cands.append((port["as_of"], 1, {"value": round(port["net_assets_lakh"] / 100.0, 4), "asOf": _iso(port["as_of"]), "source": port["source"] + " (net assets, month end)",
                                         "sourceUrl": port["source_url"], "basis": "month-end net assets", "unit": "crore"}))
    q = val("aum_q")
    if q:
        cands.append((q[1]["as_of"], 0, {"value": q[0]["crore"], "asOf": _iso(q[1]["as_of"]), "source": q[1]["source"] + " (average for the quarter, all plans)", "basis": "quarterly average", "unit": "crore"}))
    cands = [c for c in cands if c[0]]
    aum = max(cands, key=lambda c: (c[0], c[1]))[2] if cands else {"unavailable": "AUM is not loaded for this scheme: AMFI's performance and average-AUM files do not list it and no monthly portfolio is stored."}
    ter = val("ter")
    t_reg = t_dir = None
    if ter:
        v, f = ter
        base = {"asOf": _iso(f["as_of"]), "source": f["source"], "sourceUrl": f["source_url"]}
        if v.get("regular") is not None:
            t_reg = {"value": v["regular"], "unit": "percent", **base}
        if v.get("direct") is not None:
            t_dir = {"value": v["direct"], "unit": "percent", **base}
    bm = val("benchmark")
    if bm:
        benchmark = {"value": bm[0]["name"], "asOf": _iso(bm[1]["as_of"]), "source": bm[1]["source"]}
    elif port and port["benchmark"]:
        benchmark = {"value": port["benchmark"], "asOf": _iso(port["as_of"]), "source": port["source"], "sourceUrl": port["source_url"]}
    else:
        benchmark = {"unavailable": "AMFI's fund-performance list does not carry a benchmark for this scheme and the monthly portfolio file does not name one."}
    rk = val("risk")
    risk = ({"value": rk[0]["scheme"], "asOf": _iso(rk[1]["as_of"]), "source": rk[1]["source"], "benchmarkRisk": rk[0].get("benchmark")} if rk
            else {"unavailable": "AMFI's fund-performance list does not carry a risk-o-meter level for this scheme."})
    ln = val("launch")
    launch = ({"value": ln[0]["date"], "asOf": _iso(ln[1]["as_of"]), "source": ln[1]["source"]} if ln and ln[0].get("date")
              else {"unavailable": (ln[0].get("why") if ln else None) or "AMFI's scheme master has no usable launch date for this scheme."})
    mi = val("mininv")
    mininv = ({"value": mi[0]["amount"], "unit": "rupees", "text": mi[0].get("text"), "asOf": _iso(mi[1]["as_of"]), "source": mi[1]["source"]} if mi and mi[0].get("amount")
              else {"unavailable": (mi[0].get("why") if mi else None) or "AMFI's scheme master gives no clear minimum amount for this scheme (it says 'refer SID' or is blank)."})
    el = val("exitload")
    exit_load = ({"value": el[0]["text"], "asOf": _iso(el[1]["as_of"]), "source": el[1]["source"], "sourceUrl": el[1]["source_url"]} if el
                 else {"unavailable": NO_EXIT_LOAD})
    return {"aum": aum,
            "terRegular": t_reg or {"unavailable": "AMFI's TER list has no regular-plan expense ratio for this scheme."},
            "terDirect": t_dir or {"unavailable": "AMFI's TER list has no direct-plan expense ratio for this scheme (it may have no direct plan)."},
            "exitLoad": exit_load, "benchmark": benchmark, "managers": {"unavailable": NO_MANAGERS},
            "riskometer": risk, "launchDate": launch, "minInvestment": mininv}


# ------------------------------------------------------------------------------------------------------------- fetching

def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers={"User-Agent": UA}, timeout=httpx.Timeout(60.0, connect=20.0), follow_redirects=True,
                             limits=httpx.Limits(max_connections=2, max_keepalive_connections=1))


async def _retry(fn, tries: int = 3, base: float = 2.0):
    for i in range(tries):
        try:
            return await fn()
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in (400, 401, 403, 404):
                raise
            if i == tries - 1:
                raise
            await asyncio.sleep(base * (i + 1))


async def download(client: httpx.AsyncClient, url: str, dest: str, headers: Optional[dict] = None) -> int:
    """Stream a file to disk (never into memory), refusing more than MAX_BYTES."""
    async def go():
        n = 0
        async with client.stream("GET", url, headers=headers) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                async for chunk in r.aiter_bytes(1 << 16):
                    n += len(chunk)
                    if n > MAX_BYTES:
                        raise ValueError(f"file larger than {MAX_BYTES} bytes")
                    fh.write(chunk)
        return n
    return await _retry(go)


async def get_json(client: httpx.AsyncClient, url: str, **kw):
    async def go():
        r = await client.request(kw.pop("method", "GET"), url, **kw)
        r.raise_for_status()
        return r.json()
    return await _retry(go)


def _today() -> date:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


# ------------------------------------------------------------------------------------------------------------- steps: AMFI feeds

async def step_master(pool, client, idx: Index, today: date) -> dict:
    """Launch date and minimum investment from AMFI's scheme master (one CSV, 16 000 rows)."""
    r = await _retry(lambda: client.get(URL_MASTER))
    r.raise_for_status()
    rows = amfi.parse_scheme_master(r.text)
    del r
    if len(rows) < 5000:
        return {"status": "refused", "why": f"scheme master has {len(rows)} rows (expected about 16 000)"}
    by_fam: Dict[str, list] = defaultdict(list)
    for m in rows:
        f = idx.by_code.get(m.code)
        if f:
            by_fam[f].append(m)
    facts = []
    n_launch = n_min = 0
    for fam, ms in by_fam.items():
        dated = [m for m in ms if m.launch and date(1950, 1, 1) <= m.launch <= today]
        why_l = None
        if dated:
            first_all = min(m.launch for m in dated)
            clean = [m.launch for m in dated if m.closure is None]
            if clean and min(clean) == first_all:
                facts.append((fam, "launch", today, {"date": first_all.isoformat()}, SRC_MASTER, URL_MASTER))
                n_launch += 1
            else:
                why_l = "AMFI's scheme master lists a closure date against the earliest plan of this scheme, so its launch date is not reliable; none is shown."
        else:
            why_l = "AMFI's scheme master has no launch date for this scheme."
        if why_l:
            facts.append((fam, "launch", today, {"why": why_l}, SRC_MASTER, URL_MASTER))
        amounts = {amfi.min_amount(m.min_text) for m in ms if m.min_text.strip()}
        amounts.discard(None)
        texts = [m.min_text for m in ms if m.min_text.strip()]
        if len(amounts) == 1:
            amt = next(iter(amounts))
            facts.append((fam, "mininv", today, {"amount": amt, "text": texts[0][:200]}, SRC_MASTER, URL_MASTER))
            n_min += 1
        else:
            why = ("The plans of this scheme show different minimum amounts in AMFI's scheme master; none is shown." if len(amounts) > 1
                   else "AMFI's scheme master gives no clear minimum amount for this scheme (it says 'refer SID' or is blank).")
            facts.append((fam, "mininv", today, {"why": why}, SRC_MASTER, URL_MASTER))
    await put_facts(pool, facts)
    return {"status": "ok", "families": len(by_fam), "launch": n_launch, "minInvestment": n_min}


async def step_isin(pool, today: date) -> dict:
    async with httpx.AsyncClient(headers={"User-Agent": BROWSER_UA}, timeout=60.0, follow_redirects=True) as c:
        r = await _retry(lambda: c.get(URL_EQUITY_L))
        r.raise_for_status()
        m = amfi.parse_equity_list(r.text)
    if len(m) < 1500:
        return {"status": "refused", "why": f"NSE share list has {len(m)} usable rows (expected about 2 600)"}
    async with pool.acquire() as conn:
        await conn.executemany("INSERT INTO disclosure_isin (isin, symbol) VALUES ($1,$2) ON CONFLICT (isin) DO UPDATE SET symbol = EXCLUDED.symbol", list(m.items()))
    return {"status": "ok", "isins": len(m)}


async def _perf_date(client, today: date) -> Optional[date]:
    for back in range(1, 10):
        d = today - timedelta(days=back)
        j = await get_json(client, URL_PERF, method="POST", json={"maturityType": 1, "category": 1, "subCategory": 1, "mfid": 0, "reportDate": d.strftime("%d-%b-%Y")})
        if amfi.parse_performance(j):
            return d
    return None


async def step_performance(pool, client, idx: Index, today: date) -> dict:
    """Benchmark, risk-o-meter and AUM (rupees crore) for every scheme AMFI lists, one request per sub-category (about 50)."""
    d = await _perf_date(client, today)
    if d is None:
        return {"status": "refused", "why": "AMFI's fund-performance list was empty for each of the last 9 days"}
    rows: List[amfi.PerfRow] = []
    for mt in (1, 2):
        for cat in range(1, 7):
            subs = (await get_json(client, URL_PERF_SUB, method="POST", json={"category": cat})).get("data") or []
            for s in subs:
                j = await get_json(client, URL_PERF, method="POST",
                                   json={"maturityType": mt, "category": cat, "subCategory": s["id"], "mfid": 0, "reportDate": d.strftime("%d-%b-%Y")})
                rows.extend(amfi.parse_performance(j))
                await asyncio.sleep(0.15)
    if len(rows) < 1000:
        return {"status": "refused", "why": f"AMFI fund performance returned {len(rows)} schemes (expected about 2 100)"}
    facts, unmapped, dup = [], [], 0
    seen: Set[str] = set()
    for r in rows:
        fam, why = idx.resolve([r.name])
        if not fam:
            if not looks_excluded(r.name):
                unmapped.append(r.name)
            continue
        if fam in seen:
            dup += 1
            continue
        seen.add(fam)
        nd = r.nav_date or d
        if r.benchmark:
            facts.append((fam, "benchmark", nd, {"name": r.benchmark}, SRC_PERF, "https://www.amfiindia.com/otherdata/fund-performance"))
        if r.risk_scheme:
            facts.append((fam, "risk", nd, {"scheme": r.risk_scheme, "benchmark": r.risk_benchmark}, SRC_PERF, "https://www.amfiindia.com/otherdata/fund-performance"))
        if r.aum_crore is not None and r.aum_crore >= 0:
            facts.append((fam, "aum_daily", nd, {"crore": r.aum_crore}, SRC_PERF, "https://www.amfiindia.com/otherdata/fund-performance"))
    await put_facts(pool, facts)
    return {"status": "ok", "reportDate": d.isoformat(), "schemes": len(rows), "families": len(seen), "unmapped": len(unmapped), "unmappedSample": unmapped[:15], "duplicates": dup}


async def step_ter(pool, client, idx: Index, today: date) -> dict:
    """Regular and direct TER from AMFI's monthly workbook (one download, every scheme, every day of the month; the newest day per scheme is kept)."""
    fy = f"{today.year}-{today.year + 1}" if today.month >= 4 else f"{today.year - 1}-{today.year}"
    months = await get_json(client, URL_TER_MONTHS, params={"year": fy})
    if not months:
        return {"status": "refused", "why": f"AMFI lists no TER months for {fy}"}
    tmp = tempfile.mkdtemp(prefix="ter_")
    try:
        for mo in months[:2]:
            path = os.path.join(tmp, "ter.xlsx")
            await _download_params(client, URL_TER, path, {"MF_ID": "All", "Month": mo["MonthNumber"], "strCat": "-1", "strType": "-1", "excel": "true"})
            rows = read_ter_workbook(path)
            if rows:
                break
        else:
            return {"status": "refused", "why": "AMFI's TER workbook had no rows for the last two months"}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    best = amfi.latest_ter(rows)
    if len(best) < 800:
        return {"status": "refused", "why": f"AMFI TER file has {len(best)} schemes (expected about 1 900)"}
    facts, unmapped, ambiguous = [], [], 0
    by_fam: Dict[str, amfi.TerRow] = {}
    clash: Set[str] = set()
    for tr in best.values():
        fam, why = idx.resolve([tr.name])
        if not fam:
            if not looks_excluded(tr.name):
                unmapped.append(tr.name)
            continue
        cur = by_fam.get(fam)
        if cur is None or tr.day > cur.day:
            by_fam[fam] = tr
        elif tr.day == cur.day and (tr.regular, tr.direct) != (cur.regular, cur.direct):
            clash.add(fam)
    for fam in clash:
        by_fam.pop(fam, None)
        ambiguous += 1
    for fam, tr in by_fam.items():
        if tr.regular is None and tr.direct is None:
            continue
        facts.append((fam, "ter", tr.day, {"regular": tr.regular, "direct": tr.direct}, SRC_TER, "https://www.amfiindia.com/ter-of-mf-schemes"))
    await put_facts(pool, facts)
    return {"status": "ok", "month": mo["MonthNumber"], "schemes": len(best), "families": len(by_fam), "unmapped": len(unmapped), "unmappedSample": unmapped[:15], "ambiguous": ambiguous}


async def _download_params(client, url, dest, params):
    async def go():
        n = 0
        async with client.stream("GET", url, params=params) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                async for chunk in r.aiter_bytes(1 << 16):
                    n += len(chunk)
                    if n > MAX_BYTES:
                        raise ValueError("file too large")
                    fh.write(chunk)
        return n
    return await _retry(go)


def read_ter_workbook(path: str) -> List[amfi.TerRow]:
    """AMFI's TER workbook -> rows. The header is checked: if AMFI changes the columns nothing is read."""
    from .disclosure_parsers.sebi import excel_serial
    wb = open_workbook(path)
    try:
        it = wb.rows(0)
        head = [str(c or "").strip().lower() for c in next(it, [])]
        need = ["nsdl scheme code", "scheme name", "ter date", "regular plan - total ter (%)", "direct plan - total ter (%)"]
        if any(h not in head for h in need):
            return []
        ci = {h: head.index(h) for h in need}
        out: List[amfi.TerRow] = []
        for r in it:
            def g(k):
                i = ci[k]
                return r[i] if i < len(r) else None
            nm = g("scheme name")
            d = g("ter date")
            day = excel_serial(d) if isinstance(d, float) else amfi.parse_dmy(str(d or ""))
            if not nm or day is None:
                continue
            out.append(amfi.TerRow(str(nm).strip(), amfi.fnum(g("regular plan - total ter (%)")), amfi.fnum(g("direct plan - total ter (%)")), day, str(g("nsdl scheme code") or "")))
        return out
    finally:
        wb.close()


async def step_aaum(pool, client, idx: Index, today: date) -> dict:
    """AMFI's quarterly average AUM by scheme code (rupees lakh), summed over the plans of each scheme."""
    label = end = codes = None
    for fy, per in ((1, 1), (2, 1)):
        for attempt in range(8):      # AMFI's servers answer an empty 'Grand Total' now and then for the same request; asking again gives the data
            j = await get_json(client, URL_AAUM, params={"strType": "Typewise", "fyId": fy, "periodId": per})
            label, end, codes = amfi.parse_average_aum(j)
            if codes:
                break
            await asyncio.sleep(1.5)
        if codes:
            break
    if not codes or end is None or len(codes) < 3000:
        return {"status": "refused", "why": f"AMFI average AUM returned {len(codes or {})} scheme codes (expected about 8 500)"}
    fam_sum: Dict[str, float] = defaultdict(float)
    miss = 0
    for code, lakh in codes.items():
        f = idx.by_code.get(code)
        if f:
            fam_sum[f] += lakh
        else:
            miss += 1
    facts = [(f, "aum_q", end, {"crore": round(v / 100.0, 4)}, SRC_AAUM, "https://www.amfiindia.com/") for f, v in fam_sum.items()]
    await put_facts(pool, facts)
    return {"status": "ok", "period": label, "families": len(fam_sum), "codes": len(codes), "codesNotInOurList": miss}


_EXIT = re.compile(r"exit\s*load\s*[:\-]?\s*", re.I)
_NIL = re.compile(r"^(nil|none|not applicable|n\.?a\.?|no exit load)\W*$", re.I)


def exit_load_text(raw: str) -> Optional[str]:
    """The exit-load part of AMFI's 'load' text ('Entry Load: Nil Exit Load: 1% if redeemed within 1 year ...'), tidied. None when blank."""
    t = re.sub(r"\s+", " ", (raw or "")).strip()
    if not t or t.upper() in ("NA", "N.A.", "-"):
        return None
    m = _EXIT.search(t)
    if m:
        t = t[m.end():].strip(" ,;:-")
    t = re.sub(r"^entry\s*load\s*[:\-]?\s*(nil|not applicable|n\.?a\.?)\s*[,;.]?\s*", "", t, flags=re.I).strip()
    if not t:
        return None
    return "Nil" if _NIL.match(t) else t[:600]


async def step_loads(pool, client, idx: Index, today: date) -> dict:
    """Exit load text from AMFI's scheme details: one list call per fund house, then one call per scheme that matches an active scheme family here and has no
    load text from the last LOAD_MAX_AGE_DAYS days. Resumable: whatever was written stays; the next run asks only for the rest."""
    async with pool.acquire() as conn:
        active = {r["family"] for r in await conn.fetch("SELECT DISTINCT family FROM mf_schemes WHERE active")}
        fresh = {r["fkey"] for r in await conn.fetch("SELECT fkey FROM disclosure_facts WHERE kind = 'exitload' AND updated_at > now() - make_interval(days => $1)", LOAD_MAX_AGE_DAYS)}
    houses = await get_json(client, URL_MF_LIST)
    want: Dict[str, List[Tuple[str, str]]] = defaultdict(list)          # family -> [(mf id, AMFI scheme id)], newest id first
    unmapped = 0
    for h in houses or []:
        if excluded_amc(str(h.get("mfName") or "")):
            continue
        rows = await get_json(client, URL_SCHEMES, params={"MF_ID": h["mfId"]})
        for r in rows or []:
            fam, _ = idx.resolve([str(r.get("scheme_name") or "")])
            if not fam:
                unmapped += 1
            elif fam in active and fam not in fresh:
                want[fam].append((str(h["mfId"]), str(r["scheme_id"])))
        await asyncio.sleep(0.1)
    facts, asked, blank = [], 0, 0
    sem = asyncio.Semaphore(3)

    async def one(fam: str, cands: List[Tuple[str, str]]):
        nonlocal asked, blank
        for mf_id, sid in sorted(cands, key=lambda c: -int(c[1]) if c[1].isdigit() else 0)[:3]:   # the newest listing of a scheme first
            async with sem:
                asked += 1
                try:
                    d = ((await get_json(client, URL_DETAILS, params={"MF_ID": mf_id, "scheme_id": sid})).get("data") or [{}])[0]
                except Exception:
                    continue
            txt_ = exit_load_text(str(d.get("Scheme_load") or ""))
            if txt_:
                facts.append((fam, "exitload", today, {"text": txt_}, SRC_DETAILS, "https://www.amfiindia.com/otherdata/scheme-details"))
                return
        blank += 1

    items = list(want.items())
    for i in range(0, len(items), 60):                                   # written in batches, so an interrupted run keeps what it got
        await asyncio.gather(*[one(f, c) for f, c in items[i:i + 60]])
        await put_facts(pool, facts)
        facts.clear()
    return {"status": "ok", "families": len(want), "asked": asked, "blank": blank, "alreadyFresh": len(fresh & active), "namesNotMatched": unmapped}


# ------------------------------------------------------------------------------------------------------------- steps: fund houses

def _members(path: str) -> Iterable[Tuple[str, str]]:
    """(name, path) of each Excel file in a download: the file itself, or each workbook inside a zip, one extracted at a time (caller deletes)."""
    with open(path, "rb") as fh:
        magic = fh.read(4)
    if magic[:2] == b"PK" and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            if "xl/workbook.xml" in z.namelist():
                yield os.path.basename(path), path
                return
            for info in z.infolist():
                if info.filename.lower().endswith((".xlsx", ".xls")) and not info.filename.startswith("__MACOSX") and info.file_size < MAX_BYTES * 2:
                    dest = path + "." + re.sub(r"[^A-Za-z0-9]+", "_", info.filename)[-40:]
                    with z.open(info) as src, open(dest, "wb") as out:
                        shutil.copyfileobj(src, out)
                    try:
                        yield info.filename, dest
                    finally:
                        try:
                            os.remove(dest)
                        except OSError:
                            pass
        return
    yield os.path.basename(path), path


def process_workbook(path: str, ref: FileRef, adapter: Adapter, idx: Index, stats: dict, sink: list) -> None:
    """Parse every sheet of one workbook into `sink` as (family, Portfolio) after matching and validation; failures go into stats. Synchronous: the
    workbook is read, its sheets are parsed one at a time and the parsed rows are small."""
    wb = open_workbook(path)
    try:
        for i, (sname, _) in enumerate(wb.sheets):
            try:
                p = parse_rows(wb.rows(i), f"{adapter.title}, monthly portfolio disclosure", ref.url, as_of_hint=None, name_hint=ref.name_hint)
            except NotAPortfolio as exc:
                stats["sheets_skipped"] += 1
                if "no 'as on' date" in str(exc):
                    stats["failures"].append({"sheet": sname, "scheme": ref.name_hint, "why": str(exc)})
                continue
            except Exception as exc:        # a malformed sheet must not stop the rest of the workbook
                stats["failures"].append({"sheet": sname, "scheme": ref.name_hint, "why": f"parse error: {type(exc).__name__}: {exc}"[:200]})
                continue
            stats["sheets"] += 1
            fam, why = idx.resolve([p.scheme_name, *p.aliases], adapter.amc_re)
            if not fam:
                stats["unmapped"].append({"scheme": p.scheme_name, "why": why})
                continue
            v = validate(p, _today())
            if not v.ok:
                stats["rejected"].append({"scheme": p.scheme_name, "asOf": p.as_of.isoformat(), "problems": v.problems[:3]})
                continue
            from .disclosure_parsers.model import clean_for_store
            dropped = clean_for_store(p)
            if dropped:
                p.notes.append(f"{dropped} ISIN(s) failing the ISIN check digit are not shown")
            if v.warnings:
                stats["warnings"] += len(v.warnings)
            sink.append((fam, p))
    finally:
        wb.close()


async def step_amc(pool, client, adapter: Adapter, idx: Index, today: date, months: int, force: bool) -> dict:
    stats = {"files": 0, "sheets": 0, "sheets_skipped": 0, "stored": 0, "skipped_existing": 0, "kept_existing": 0, "too_old": 0, "warnings": 0,
             "rejected": [], "unmapped": [], "failures": [], "families": set(), "errors": []}
    mends = month_ends(today, months)
    refs = await adapter.list_files(client, mends)
    stats["listed"] = len(refs)
    tmp = tempfile.mkdtemp(prefix=f"disc_{adapter.key}_")
    try:
        for ref in refs:
            per_scheme = ref.name_hint is not None
            period = f"{ref.month_end:%Y-%m}:{ref.url.rsplit('/', 1)[-1].split('?')[0][:80]}"
            if per_scheme:
                fam, _ = idx.resolve([ref.name_hint], adapter.amc_re)
                if fam and not force and ref.month_end:
                    async with pool.acquire() as conn:
                        if await conn.fetchval("SELECT 1 FROM disclosure_portfolios WHERE fkey = $1 AND as_of = $2", fam, ref.month_end):
                            stats["skipped_existing"] += 1
                            continue
            elif not force and await _run_done(pool, adapter.key, period):
                stats["skipped_existing"] += 1
                continue
            path = os.path.join(tmp, "f.bin")
            try:
                await download(client, ref.url, path)
            except Exception as exc:
                stats["errors"].append(f"{ref.label}: {type(exc).__name__}: {str(exc)[:120]}")
                continue
            stats["files"] += 1
            before_fail = len(stats["failures"]) + len(stats["errors"])
            try:
                for mname, mpath in _members(path):
                    sink: list = []
                    try:
                        process_workbook(mpath, ref, adapter, idx, stats, sink)
                    except Exception as exc:
                        stats["errors"].append(f"{ref.label} / {mname}: {type(exc).__name__}: {str(exc)[:120]}")
                    for fam, p in sink:
                        res = await store_portfolio(pool, fam, idx.amc[fam], p)
                        if res == "stored":
                            stats["stored"] += 1
                            stats["families"].add(fam)
                        else:
                            stats[res] += 1
                    del sink
            finally:
                try:
                    os.remove(path)
                except OSError:
                    pass
            if not per_scheme and len(stats["errors"]) == 0:
                await _run_mark(pool, adapter.key, period, "done", {"sheets": stats["sheets"], "rejected": len(stats["rejected"]), "unmapped": len(stats["unmapped"])})
            await asyncio.sleep(0.3)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    stats["families"] = len(stats["families"])
    stats["status"] = "ok" if not stats["errors"] else "partial"
    return stats


# ------------------------------------------------------------------------------------------------------------- refresh

async def refresh(store, settings=None, only: Optional[Sequence[str]] = None, months: int = KEEP_MONTHS, force: bool = False,
                  client: Optional[httpx.AsyncClient] = None, today: Optional[date] = None) -> dict:
    """Run every step; each fails alone. Returns {status: ok|partial|failed, steps: {...}, amc: {key: counts}}. `only` limits it to named steps / fund houses
    (master, isin, performance, ter, aaum, or an adapter key like mirae)."""
    pool = store.pool
    today = today or _today()
    own = client is None
    client = client or make_client()
    want = {s.lower() for s in only} if only else None
    out: dict = {"status": "ok", "date": today.isoformat(), "steps": {}, "amc": {}}
    try:
        idx = await load_index(pool)
        if len(idx.by_code) < 1000:
            return {"status": "failed", "why": "mf_schemes is empty or short: run refresh-mf first", "steps": {}, "amc": {}}
        steps = [("master", lambda: step_master(pool, client, idx, today)), ("isin", lambda: step_isin(pool, today)),
                 ("performance", lambda: step_performance(pool, client, idx, today)), ("ter", lambda: step_ter(pool, client, idx, today)),
                 ("aaum", lambda: step_aaum(pool, client, idx, today)), ("loads", lambda: step_loads(pool, client, idx, today))]
        for name, fn in steps:
            if want and name not in want:
                continue
            try:
                out["steps"][name] = await fn()
            except Exception as exc:
                log.warning("disclosure step %s failed", name, exc_info=True)
                out["steps"][name] = {"status": "error", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
        for ad in ADAPTERS:
            if want and ad.key not in want:
                continue
            try:
                out["amc"][ad.key] = await step_amc(pool, client, ad, idx, today, months, force)
            except Exception as exc:
                log.warning("disclosure adapter %s failed", ad.key, exc_info=True)
                out["amc"][ad.key] = {"status": "error", "why": f"{type(exc).__name__}: {str(exc)[:200]}"}
    finally:
        if own:
            await client.aclose()
    results = [v.get("status") for v in [*out["steps"].values(), *out["amc"].values()]]
    if not results or all(s in ("error", "refused") for s in results):
        out["status"] = "failed"
    elif any(s in ("error", "refused", "partial") for s in results):
        out["status"] = "partial"
    return out


# ------------------------------------------------------------------------------------------------------------- reports

async def coverage(pool) -> dict:
    """Real counts per fund house: active scheme codes, and how many of them have holdings / TER / AUM / benchmark / risk-o-meter / launch / minimum."""
    sql = """
    SELECT s.amc,
           count(*) FILTER (WHERE s.active) AS codes,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_portfolios p WHERE p.fkey = s.family)) AS holdings,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind = 'ter')) AS ter,
           count(*) FILTER (WHERE s.active AND (EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind IN ('aum_daily','aum_q'))
                                                OR EXISTS (SELECT 1 FROM disclosure_portfolios p WHERE p.fkey = s.family AND p.net_assets_lakh IS NOT NULL))) AS aum,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind = 'benchmark')) AS benchmark,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind = 'risk')) AS risk,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind = 'launch' AND f.value ? 'date')) AS launch,
           count(*) FILTER (WHERE s.active AND EXISTS (SELECT 1 FROM disclosure_facts f WHERE f.fkey = s.family AND f.kind = 'mininv' AND f.value ? 'amount')) AS mininv
    FROM mf_schemes s GROUP BY s.amc ORDER BY codes DESC"""
    fam_sql = """
    SELECT s.amc, count(DISTINCT s.family) AS families,
           count(DISTINCT s.family) FILTER (WHERE EXISTS (SELECT 1 FROM disclosure_portfolios p WHERE p.fkey = s.family)) AS families_with_holdings
    FROM mf_schemes s WHERE s.active GROUP BY s.amc"""
    async with pool.acquire() as conn:
        rows = [dict(r) for r in await conn.fetch(sql)]
        fam = {r["amc"]: dict(r) for r in await conn.fetch(fam_sql)}
    for r in rows:
        r.update({k: v for k, v in fam.get(r["amc"], {}).items() if k != "amc"})
    return {"perAmc": rows, "excludedHidden": [r["amc"] for r in rows if excluded_amc(r["amc"])]}


async def size_report(pool) -> dict:
    """Bytes used by the disclosure tables (heap + TOAST + indexes) and the per-scheme average."""
    out = {}
    async with pool.acquire() as conn:
        for t in ("disclosure_portfolios", "disclosure_facts", "disclosure_isin", "disclosure_runs"):
            out[t] = {"bytes": await conn.fetchval("SELECT pg_total_relation_size($1::regclass)", t), "rows": await conn.fetchval(f"SELECT count(*) FROM {t}")}  # nosec B608 - t is one of the four literal table names above
        out["holdings_json_bytes"] = await conn.fetchval("SELECT coalesce(sum(pg_column_size(holdings)),0) FROM disclosure_portfolios")
        out["holdings_text_bytes"] = await conn.fetchval("SELECT coalesce(sum(length(holdings::text)),0) FROM disclosure_portfolios")
        out["avg_holdings"] = await conn.fetchval("SELECT coalesce(avg(n),0) FROM disclosure_portfolios")
    out["total_bytes"] = sum(v["bytes"] for k, v in out.items() if isinstance(v, dict))
    return out


# ------------------------------------------------------------------------------------------------------------- local use

async def _main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m finlit.disclosure")
    ap.add_argument("cmd", choices=["refresh", "coverage", "size"])
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--months", type=int, default=KEEP_MONTHS)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    from .config import get_settings
    from .store import Store
    settings = get_settings()
    store = await Store.connect(settings, migrate=True)
    try:
        if a.cmd == "refresh":
            res = await refresh(store, settings, a.only, a.months, a.force)
        elif a.cmd == "coverage":
            res = await coverage(store.pool)
        else:
            res = await size_report(store.pool)
        print(json.dumps(res, indent=1, default=str))
        return 0 if res.get("status", "ok") == "ok" else 1
    finally:
        await store.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    raise SystemExit(asyncio.run(_main(sys.argv[1:])))
