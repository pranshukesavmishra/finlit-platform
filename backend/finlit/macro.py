"""India macro insights: load the official series (finlit/macro_sources.py says where each comes from), keep them in Postgres, check them,
and publish one ready-made page payload at /api/macro.

Worker `refresh-macro` runs nightly (and at boot when it has not run for a day). Each source is its own step: one that fails keeps the
last good data and says so in the payload's `runs`; nothing is ever filled in. The first run loads the full history (about 300 small
requests to MoSPI, paced); later runs ask only for the latest months.

TLS: MoSPI's servers need TLS renegotiation that OpenSSL 3 switches off by default (OP_LEGACY_SERVER_CONNECT); that one option is turned
on for MoSPI only. Certificates are always verified (against certifi's Mozilla roots, which include MoSPI's emSign chain).
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import certifi
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from . import macro_sources as S
from .background import etag_matches
from .store import dumps, etag_for

log = logging.getLogger("finlit.macro")
router = APIRouter(prefix="/api/macro")

MOSPI = "https://api.mospi.gov.in"
RBI_HOME = "https://www.rbi.org.in/"
RBI_RSS = "https://rbi.org.in/pressreleases_rss.xml"
USER_AGENT = "FinLit-data/1.0 (+https://finlitventures.com)"
PAUSE = 0.25                                  # seconds between two MoSPI requests
KEY = "macro:v1"
CACHE = "public, max-age=600, stale-while-revalidate=3600"
IST = timezone(timedelta(hours=5, minutes=30))
DECISIONS = Path(__file__).parent / "data" / "repo_decisions.json"
TARGET, BAND = 4.0, (2.0, 6.0)               # the Government's CPI target for the RBI, 1 April 2026 to 31 March 2031 (gazette, 25 March 2026)
FIRST_YEAR = 2013

# ---------------------------------------------------------------------------------------------------- what the page shows
SERIES: Dict[str, dict] = {
    "cpi": {"label": "CPI inflation", "short": "CPI", "unit": "%", "freq": "M", "source": "MoSPI", "what": "Retail prices: what households pay, year on year."},
    "cpi_rural": {"label": "CPI inflation, rural", "unit": "%", "freq": "M", "source": "MoSPI"},
    "cpi_urban": {"label": "CPI inflation, urban", "unit": "%", "freq": "M", "source": "MoSPI"},
    "wpi": {"label": "WPI inflation", "short": "WPI", "unit": "%", "freq": "M", "source": "MoSPI", "what": "Wholesale prices: what producers and traders pay, year on year."},
    "wpi_primary": {"label": "WPI: primary articles", "unit": "%", "freq": "M", "source": "MoSPI"},
    "wpi_fuel": {"label": "WPI: fuel and power", "unit": "%", "freq": "M", "source": "MoSPI"},
    "wpi_mfg": {"label": "WPI: manufactured products", "unit": "%", "freq": "M", "source": "MoSPI"},
    "wpi_food": {"label": "WPI: food index", "unit": "%", "freq": "M", "source": "MoSPI"},
    "gdp": {"label": "GDP growth", "short": "GDP", "unit": "%", "freq": "Q", "source": "NSO / MoSPI", "what": "Real GDP (constant prices), the quarter against the same quarter a year earlier."},
    "gdp_nominal": {"label": "Nominal GDP growth", "unit": "%", "freq": "Q", "source": "NSO / MoSPI", "what": "GDP at current prices, year on year."},
    "iip": {"label": "Industrial production", "short": "IIP", "unit": "%", "freq": "M", "source": "MoSPI", "what": "Index of Industrial Production, growth year on year."},
    "iip_mining": {"label": "IIP: mining", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_mfg": {"label": "IIP: manufacturing", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_elec": {"label": "IIP: electricity", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_capital": {"label": "IIP: capital goods", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_infra": {"label": "IIP: infrastructure and construction goods", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_durables": {"label": "IIP: consumer durables", "unit": "%", "freq": "M", "source": "MoSPI"},
    "iip_nondurables": {"label": "IIP: consumer non-durables", "unit": "%", "freq": "M", "source": "MoSPI"},
    "unemployment": {"label": "Unemployment rate", "short": "Jobs", "unit": "%", "freq": "M", "source": "PLFS / MoSPI", "what": "Persons aged 15 and above, rural and urban, current weekly status."},
    "unemployment_youth": {"label": "Youth unemployment (15-29)", "unit": "%", "freq": "M", "source": "PLFS / MoSPI"},
    "unemployment_urban": {"label": "Urban unemployment", "unit": "%", "freq": "M", "source": "PLFS / MoSPI"},
    "repo": {"label": "RBI repo rate", "short": "Repo", "unit": "%", "freq": "M", "source": "RBI", "what": "The policy rate: what banks pay to borrow from the RBI overnight."},
    "real_rate": {"label": "Real repo rate", "unit": "pp", "freq": "M", "source": "Derived: RBI repo rate minus CPI inflation", "what": "The repo rate minus CPI inflation of the same month."},
    "fx_reserves": {"label": "Forex reserves", "short": "Reserves", "unit": "US$ bn", "freq": "W", "source": "RBI", "what": "Foreign exchange reserves: currency assets, gold, SDRs and the IMF position."},
    "usdinr_d": {"label": "Rupee per US dollar, daily", "unit": "₹", "freq": "D", "source": "RBI / FBIL"},
    "usdinr": {"label": "Rupee per US dollar", "short": "USD/INR", "unit": "₹", "freq": "M", "source": "RBI / FBIL", "what": "Reference rate, monthly average (latest: today's FBIL reference rate)."},
    "credit_yoy": {"label": "Bank credit growth", "unit": "%", "freq": "F", "source": "RBI", "what": "Scheduled commercial banks' credit in India, year on year."},
    "deposits_yoy": {"label": "Bank deposit growth", "unit": "%", "freq": "F", "source": "RBI", "what": "Aggregate deposits, year on year."},
    "m3_yoy": {"label": "Money supply (M3) growth", "unit": "%", "freq": "F", "source": "RBI", "what": "Broad money, year on year."},
}
SOURCE_URL = {"MoSPI": "https://esankhyiki.mospi.gov.in", "NSO / MoSPI": "https://esankhyiki.mospi.gov.in", "PLFS / MoSPI": "https://esankhyiki.mospi.gov.in",
              "RBI": "https://www.rbi.org.in", "RBI / FBIL": "https://www.fbil.org.in"}
CARDS = ["cpi", "wpi", "gdp", "iip", "unemployment", "repo", "real_rate", "fx_reserves", "usdinr", "credit_yoy"]
RANGES = {"cpi": (-5, 30), "cpi_rural": (-5, 30), "cpi_urban": (-5, 30), "wpi": (-20, 40), "gdp": (-30, 30), "gdp_nominal": (-30, 40), "iip": (-70, 100),
          "unemployment": (0, 40), "unemployment_youth": (0, 60), "unemployment_urban": (0, 40), "repo": (1, 15), "fx_reserves": (100, 2500),
          "usdinr": (30, 250), "usdinr_d": (30, 250), "credit_yoy": (-20, 50), "deposits_yoy": (-20, 50), "m3_yoy": (-20, 50)}


def mospi_ssl() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=certifi.where())
    ctx.options |= getattr(ssl, "OP_LEGACY_SERVER_CONNECT", 0x4)
    return ctx


# ---------------------------------------------------------------------------------------------------- storage
async def save_points(conn, series: str, pts: S.Points) -> int:
    if not pts:
        return 0
    await conn.executemany("INSERT INTO macro_points (series, d, v) VALUES ($1, $2, $3) ON CONFLICT (series, d) DO UPDATE SET v = EXCLUDED.v",
                           [(series, d, float(v)) for d, v in pts.items()])
    return len(pts)


async def load_points(conn, prefix: Optional[str] = None) -> Dict[str, S.Points]:
    rows = await (conn.fetch("SELECT series, d, v FROM macro_points WHERE series LIKE $1", prefix + "%") if prefix else conn.fetch("SELECT series, d, v FROM macro_points"))
    out: Dict[str, S.Points] = {}
    for r in rows:
        out.setdefault(r["series"], {})[r["d"]] = r["v"]
    return out


async def get_meta(conn, key: str) -> Optional[dict]:
    raw = await conn.fetchval("SELECT body FROM macro_meta WHERE key = $1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def set_meta(conn, key: str, body) -> None:
    await conn.execute("INSERT INTO macro_meta (key, body, updated_at) VALUES ($1, $2::jsonb, now()) ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()",
                       key, json.dumps(body, default=str))


# ---------------------------------------------------------------------------------------------------- fetching
class Sources:
    """The two HTTP clients (MoSPI needs its own TLS options). `transport` replaces both in tests."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None):
        common = dict(timeout=60, headers={"User-Agent": USER_AGENT, "Accept": "application/json, text/html, */*"}, follow_redirects=True)
        self.mospi = httpx.AsyncClient(base_url=MOSPI, transport=transport, verify=mospi_ssl() if transport is None else True, **common)
        self.web = httpx.AsyncClient(transport=transport, **common)
        self.calls = 0

    async def aclose(self):
        await self.mospi.aclose()
        await self.web.aclose()

    async def get_json(self, path: str, **params) -> dict:
        for attempt in range(3):
            await asyncio.sleep(PAUSE)
            self.calls += 1
            try:
                r = await self.mospi.get(path, params={k: v for k, v in params.items() if v is not None})
                if r.status_code == 200:
                    return r.json()
                if r.status_code < 500:
                    raise RuntimeError(f"MoSPI {path} answered {r.status_code}: {r.text[:120]}")
            except (httpx.TransportError, ValueError) as exc:
                if attempt == 2:
                    raise RuntimeError(f"MoSPI {path}: {type(exc).__name__}") from exc
            await asyncio.sleep(2 * (attempt + 1))
        raise RuntimeError(f"MoSPI {path} kept failing")

    async def pages(self, path: str, limit: int, **params) -> List[dict]:
        """Every page of a paged MoSPI answer (at most 60, a guard against a runaway loop)."""
        first = await self.get_json(path, limit=limit, page=1, **params)
        out = S.rows(first)
        total = int((first.get("meta_data") or {}).get("totalPages") or 1)
        for p in range(2, min(total, 60) + 1):
            out += S.rows(await self.get_json(path, limit=limit, page=p, **params))
        return out

    async def get_text(self, url: str) -> str:
        self.calls += 1
        r = await self.web.get(url)
        if r.status_code != 200:
            raise RuntimeError(f"{url} answered {r.status_code}")
        return r.text


def months_between(a: date, b: date) -> List[Tuple[int, int]]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        y, m = (y + (m == 12), m % 12 + 1)
    return out


async def step_cpi(src: Sources, conn, today: date, full: bool) -> dict:
    """CPI base 2024. Back series (2013-2024, headline by sector) once; current series month by month (one request a month holds the
    headline and all 12 divisions for rural, urban and combined), from January 2025, later runs only the last three months."""
    n = 0
    if full or not await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'cpi_idx_back'"):
        for y in range(FIRST_YEAR, 2025):
            p = S.parse_cpi({"data": await src.pages("/api/cpi/getCPIData", 100, base_year="2024", series_code="Back", year=y, state_code=1, Format="JSON")})
            for k, pts in p.series.items():
                n += await save_points(conn, k + "_back" if k.endswith("_idx") else k, pts)
    latest = await conn.fetchval("SELECT max(d) FROM macro_points WHERE series = 'cpi_idx'")
    start = date(2025, 1, 1) if full or not latest else max(date(2025, 1, 1), date(latest.year, latest.month, 1) - timedelta(days=62))
    labels: Dict[str, str] = {}
    for y, m in months_between(start, today):
        p = S.parse_cpi(await src.get_json("/api/cpi/getCPIData", base_year="2024", series_code="Current", year=y, month_code=m, state_code=1, Format="JSON", limit=100))
        for k, pts in p.series.items():
            n += await save_points(conn, k, pts)
        labels.update(p.labels)
    if labels:
        await set_meta(conn, "cpi_labels", {**(await get_meta(conn, "cpi_labels") or {}), **labels})
    return {"points": n}


async def step_wpi(src: Sources, conn, today: date, full: bool) -> dict:
    n = 0
    have11 = await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'wpi11_idx'")
    groups11 = {"1000000000": "wpi11_idx", "1100000000": "wpi11_idx_primary", "1200000000": "wpi11_idx_fuel", "1300000000": "wpi11_idx_mfg", "2000000000": "wpi11_idx_food"}
    groups22 = {"1000000000": "wpi22_idx", "1100000000": "wpi22_idx_primary", "1200000000": "wpi22_idx_fuel", "1300000000": "wpi22_idx_mfg", "1400000000": "wpi22_idx_food"}
    if full or not have11:
        for y in range(FIRST_YEAR - 1, 2024):
            for code, key in groups11.items():
                n += await save_points(conn, key, S.parse_wpi_index({"data": await src.pages("/api/wpi/getWpiRecords", 200, base_year="2011-12", year=y, major_group_code=code, Format="JSON")}, code))
    years = range(2023, today.year + 1) if full or not await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'wpi22_idx'") else range(today.year - 1, today.year + 1)
    for y in years:
        for code, key in groups22.items():
            n += await save_points(conn, key, S.parse_wpi_index({"data": await src.pages("/api/wpi/getWpiRecords", 200, base_year="2022-23", year=y, major_group_code=code, Format="JSON")}, code))
    return {"points": n}


async def step_gdp(src: Sources, conn, today: date, full: bool) -> dict:
    n = 0
    for base, pre in (("2011-12", "gdp11"), ("2022-23", "gdp22")):
        if base == "2011-12" and not full and await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'gdp11_const'"):
            continue
        const, cur = S.parse_gdp({"data": await src.pages("/api/nas/getNASData", 200, base_year=base, series="Current", frequency_code=2, indicator_code=5, Format="JSON")})
        n += await save_points(conn, pre + "_const", const) + await save_points(conn, pre + "_cur", cur)
    return {"points": n}


async def step_iip(src: Sources, conn, today: date, full: bool) -> dict:
    n = 0
    have = await conn.fetchval("SELECT min(d) FROM macro_points WHERE series = 'iip'")
    if full or not have or have > date(2014, 1, 1):
        for y in range(FIRST_YEAR, 2024):          # the earlier base, general index only, until the 2022-23 base takes over
            p = S.parse_iip({"data": await src.pages("/api/iip/getIipData", 200, base_year="2011-12", frequency="Monthly", year=y, type="General", Format="JSON")})
            for k, pts in p.series.items():
                n += await save_points(conn, k + "_11", pts)
    years = range(2023, today.year + 1) if full or not have else range(today.year - 1, today.year + 1)
    for y in years:
        p = S.parse_iip({"data": await src.pages("/api/iip/getIipData", 200, base_year="2022-23", frequency="Monthly", year=y, Format="JSON")})
        for k, pts in p.series.items():
            n += await save_points(conn, k, pts)
    return {"points": n}


async def step_plfs(src: Sources, conn, today: date, full: bool) -> dict:
    n = 0
    have = await conn.fetchval("SELECT count(*) FROM macro_points WHERE series = 'unemployment'")
    for y in (range(2025, today.year + 1) if full or not have else range(today.year - 1, today.year + 1)):
        p = S.parse_plfs({"data": await src.pages("/api/plfs/getData", 200, indicator_code=3, frequency_code=3, year=y, Format="JSON")})
        for k, pts in p.series.items():
            n += await save_points(conn, k, pts)
    return {"points": n}


async def step_rbi_tables(src: Sources, conn, today: date, full: bool) -> dict:
    """Monthly reserves and exchange rates from the RBI tables MoSPI republishes: refreshed weekly (they change monthly at most)."""
    last = await get_meta(conn, "run:rbi_tables")
    if not full and last and last.get("status") == "ok" and (datetime.now(timezone.utc) - datetime.fromisoformat(last["at"])).days < 7:
        return {"skipped": "ran this week"}
    res = S.parse_rbi_reserves_monthly({"data": await src.pages("/api/rbi/getRbiRecords", 200, sub_indicator_code=47, Format="JSON")})
    fx = S.parse_rbi_usdinr_monthly({"data": await src.pages("/api/rbi/getRbiRecords", 200, sub_indicator_code=33, Format="JSON")})
    return {"points": await save_points(conn, "fx_reserves_m", res) + await save_points(conn, "usdinr_m", fx)}


async def step_rbi_home(src: Sources, conn, today: date, full: bool) -> dict:
    """Today's policy rates and FBIL reference rates. A repo rate that differs from the last recorded decision is recorded as a new
    decision dated the day it was first seen (the nightly run follows every MPC announcement within a day)."""
    got = S.parse_rbi_home(await src.get_text(RBI_HOME))
    if not got:
        raise RuntimeError("the Current Rates panel was not found on rbi.org.in")
    seen = today.isoformat()
    await set_meta(conn, "rbi_rates", {**got, "seenOn": seen})
    n = 0
    if got["fx"].get("usdinr") and got.get("fxAsOf"):
        n += await save_points(conn, "usdinr_d", {date.fromisoformat(got["fxAsOf"]): got["fx"]["usdinr"]})
    decisions = load_decisions()
    live = await get_meta(conn, "repo_live") or {"decisions": []}
    last = sorted([*decisions, *[S.Decision(date.fromisoformat(x["date"]), x["rate"], x["bp"], x["source"]) for x in live["decisions"]]], key=lambda d: d.date)[-1]
    if abs(got["rates"]["repo"] - last.rate) > 1e-9:
        bp = round((got["rates"]["repo"] - last.rate) * 100)
        live["decisions"].append({"date": seen, "rate": got["rates"]["repo"], "bp": bp, "source": "rbi.org.in Current Rates, first seen " + seen})
        await set_meta(conn, "repo_live", live)
        log.warning("repo rate change detected: %s -> %s", last.rate, got["rates"]["repo"])
    return {"points": n, "repo": got["rates"]["repo"]}


async def step_rbi_wss(src: Sources, conn, today: date, full: bool) -> dict:
    found = S.latest_wss_link(await src.get_text(RBI_RSS))
    if not found:
        last = await get_meta(conn, "rbi_wss")
        return {"skipped": "no WSS extract in RBI's latest press releases", "kept": (last or {}).get("reservesAsOf")}
    link, pub = found
    w = S.parse_wss_extract(await src.get_text(link))
    if not w:
        raise RuntimeError("the WSS extract had no reserves table")
    await set_meta(conn, "rbi_wss", {**w, "link": link, "published": pub})
    n = await save_points(conn, "fx_reserves_w", S.wss_reserve_points(w))
    for k, at in (("credit_yoy", "banksAsOf"), ("deposits_yoy", "banksAsOf"), ("m3_yoy", "moneyAsOf")):
        if w.get(k) is not None and w.get(at):
            n += await save_points(conn, k, {date.fromisoformat(w[at]): w[k]})
    return {"points": n, "asOf": w["reservesAsOf"]}


STEPS: List[Tuple[str, Callable]] = [("cpi", step_cpi), ("wpi", step_wpi), ("gdp", step_gdp), ("iip", step_iip), ("plfs", step_plfs),
                                    ("rbi_tables", step_rbi_tables), ("rbi_home", step_rbi_home), ("rbi_wss", step_rbi_wss)]


def load_decisions() -> List[S.Decision]:
    raw = json.loads(DECISIONS.read_text())
    return [S.Decision(date.fromisoformat(x["date"]), float(x["rate"]), int(x["bp"]), x.get("url") or raw["sourceUrl"]) for x in raw["decisions"]]


async def refresh(store, transport: Optional[httpx.AsyncBaseTransport] = None, today: Optional[date] = None, full: bool = False,
                  only: Optional[List[str]] = None) -> dict:
    today = today or datetime.now(IST).date()
    src = Sources(transport)
    started = time.perf_counter()
    result: Dict[str, dict] = {}
    try:
        for name, fn in STEPS:
            if only and name not in only:
                continue
            t0 = time.perf_counter()
            async with store.pool.acquire() as conn:
                try:
                    info = await fn(src, conn, today, full)
                    info = {"status": "skipped" if "skipped" in info else "ok", **info}
                except Exception as exc:              # one source failing never stops the others; its last good data stays
                    log.warning("macro step %s failed: %s", name, exc)
                    info = {"status": "failed", "reason": str(exc)[:200]}
                info.update(seconds=round(time.perf_counter() - t0, 1), at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                if info["status"] != "skipped":
                    await set_meta(conn, "run:" + name, info)
                result[name] = info
    finally:
        await src.aclose()
    payload = await publish(store, today)
    bad = [k for k, v in result.items() if v["status"] == "failed"]
    return {"status": "ok" if not bad else "partial" if len(bad) < len(result) else "failed", "steps": result, "calls": src.calls,
            "cards": len(payload["cards"]), "seconds": round(time.perf_counter() - started, 1)}


# ---------------------------------------------------------------------------------------------------- building the page
def _spliced(newer: S.Points, older: S.Points) -> S.Points:
    """The older series up to where the newer one begins, then the newer one (each kept as published or derived within its own base)."""
    if not newer:
        return dict(older)
    first = min(newer)
    return {**{d: v for d, v in older.items() if d < first}, **newer}


def _round(pts: S.Points, nd: int = 2) -> S.Points:
    return {d: round(v, nd) for d, v in pts.items()}


def derive(raw: Dict[str, S.Points], decisions: List[S.Decision], today: date) -> Tuple[Dict[str, S.Points], Dict[str, list], Dict[str, str]]:
    """Every page series from the stored points: (series, base breaks to mark on charts, method notes)."""
    out: Dict[str, S.Points] = {}
    breaks: Dict[str, list] = {}
    notes: Dict[str, str] = {}
    # CPI: MoSPI's own rate on the back series (2013-2024) and on the current series (from January 2026); for 2025, the first year of the
    # new base, MoSPI publishes no rate, so it is the current series' index against the back series' index of the same month (same base).
    for key in ("cpi", "cpi_rural", "cpi_urban"):
        pts = dict(raw.get(key, {}))
        back = raw.get(key + "_idx_back", {})
        for d, v in raw.get(key + "_idx", {}).items():
            if d.year == 2025 and d not in pts and back.get(S.month_end(2024, d.month)):
                pts[d] = round((v / back[S.month_end(2024, d.month)] - 1) * 100, 2)
        out[key] = pts
    notes["cpi"] = ("MoSPI's published inflation rate, base 2024 = 100: the back series for 2013-2024 and the current series from January 2026. "
                    "For the 12 months of 2025 (the new series' first year, for which MoSPI publishes no rate) the change is worked out from the "
                    "current series' index against the back series' index for the same month, both on base 2024.")
    breaks["cpi"] = [{"d": "2025-01-31", "label": "New series (base 2024)"}]
    for k in [k for k in raw if k.startswith("cpi_div_")]:
        out[k] = raw[k]
    # WPI: year on year within each base; the 2022-23 base from its first full year (2024), the 2011-12 base before it.
    for key in ("wpi", "wpi_primary", "wpi_fuel", "wpi_mfg", "wpi_food"):
        suffix = key[3:]
        out[key] = _spliced(S.yoy(raw.get("wpi22_idx" + suffix, {})), S.yoy(raw.get("wpi11_idx" + suffix, {})))
    notes["wpi"] = ("MoSPI publishes the wholesale index, not an inflation rate: each month is the index against the same month a year earlier, always "
                    "within one base (2011-12 = 100 until December 2023; 2022-23 = 100 from January 2024).")
    breaks["wpi"] = [{"d": "2024-01-31", "label": "Base 2022-23"}]
    # GDP: within each base, the quarter against the same quarter a year earlier.
    out["gdp"] = _spliced(S.yoy(raw.get("gdp22_const", {})), S.yoy(raw.get("gdp11_const", {})))
    out["gdp_nominal"] = _spliced(S.yoy(raw.get("gdp22_cur", {})), S.yoy(raw.get("gdp11_cur", {})))
    first22 = min(S.yoy(raw.get("gdp22_const", {})) or [None]) if raw.get("gdp22_const") else None
    breaks["gdp"] = [{"d": first22.isoformat(), "label": "Base 2022-23"}] if first22 else []
    notes["gdp"] = ("Quarterly GDP from the National Statistics Office: real (constant prices) and nominal (current prices), each quarter against "
                    "the same quarter a year earlier, within one base year (2011-12, then 2022-23 once it has a year of history).")
    # IIP: MoSPI's published growth, base 2022-23 where it exists, the 2011-12 base before.
    for key in ("iip", "iip_mining", "iip_mfg", "iip_elec", "iip_capital", "iip_infra", "iip_durables", "iip_nondurables"):
        out[key] = _spliced(raw.get(key, {}), raw.get(key + "_11", {}))
    notes["iip"] = "MoSPI's published growth rate of the Index of Industrial Production (base 2022-23; base 2011-12 before it)."
    for key in ("unemployment", "unemployment_youth", "unemployment_urban"):
        out[key] = raw.get(key, {})
    notes["unemployment"] = "Periodic Labour Force Survey, monthly estimate (published from January 2025), current weekly status."
    # Repo: the rate in force at each month end; today's from rbi.org.in.
    out["repo"] = S.repo_series(decisions, today)
    notes["repo"] = "The rate in force at each month end, from every RBI policy decision since April 2016; today's figure is read from rbi.org.in."
    # Real rate: repo at each CPI month end minus CPI.
    out["real_rate"] = {d: round(out["repo"][d] - v, 2) for d, v in out["cpi"].items() if d in out["repo"]}
    # Reserves: RBI's month-end figures, then weekly figures (and the two earlier weeks each weekly release states).
    weekly = raw.get("fx_reserves_w", {})
    out["fx_reserves"] = {**raw.get("fx_reserves_m", {}), **weekly}
    notes["fx_reserves"] = ("Month-end reserves from the RBI's tables (as republished by MoSPI), and weekly figures from the RBI's Weekly Statistical "
                            "Supplement from the week they were first read; a weekly release also states the change against end-March and a year "
                            "earlier, from which those two weeks are added.")
    out["usdinr"] = {**raw.get("usdinr_m", {}), **raw.get("usdinr_d", {})}
    out["usdinr_d"] = dict(raw.get("usdinr_d", {}))
    notes["usdinr"] = ("Monthly average of the reference rate (RBI tables, as republished by MoSPI), then the daily FBIL reference rate shown on "
                       "rbi.org.in from the day it was first read.")
    for key in ("credit_yoy", "deposits_yoy", "m3_yoy"):
        out[key] = raw.get(key, {})
    notes["credit_yoy"] = "Scheduled commercial banks, business in India, as the RBI's weekly statistical supplement states it, from the week it was first read."
    return out, breaks, notes


def checked(series: Dict[str, S.Points], today: date) -> Tuple[Dict[str, S.Points], List[str]]:
    """Publish-time checks: values inside a sane range, no date in the future. A failing point is left out and listed, never altered."""
    issues: List[str] = []
    out: Dict[str, S.Points] = {}
    for k, pts in series.items():
        lo, hi = RANGES.get(k, (-1e9, 1e9))
        keep = {}
        for d, v in pts.items():
            if d > today + timedelta(days=1):
                issues.append(f"{k} {d}: a date in the future")
            elif not (lo <= v <= hi):
                issues.append(f"{k} {d}: {v} outside {lo}..{hi}")
            else:
                keep[d] = v
        out[k] = dict(sorted(keep.items()))
    return out, issues


def period_label(d: date, freq: str) -> str:
    if freq == "Q":
        fy = d.year if d.month >= 4 else d.year - 1
        q = {6: 1, 9: 2, 12: 3, 3: 4}[d.month]
        return f"Q{q} FY{str(fy + 1)[2:]} ({['Apr-Jun', 'Jul-Sep', 'Oct-Dec', 'Jan-Mar'][q - 1]} {d.year})"
    if freq in ("W", "F", "D"):
        return d.strftime("%d %b %Y").lstrip("0")
    return d.strftime("%b %Y")


def card(key: str, pts: S.Points, extra: Optional[dict] = None) -> Optional[dict]:
    if not pts:
        return None
    meta = SERIES[key]
    ds = sorted(pts)
    d = ds[-1]
    v = pts[d]
    prev_d = ds[-2] if len(ds) > 1 else None
    change = round(v - pts[prev_d], 3) if prev_d else None
    year_d = S.month_end(d.year - 1, d.month) if meta["freq"] in ("M", "Q") else None
    unit = meta["unit"]
    out = {"key": key, "label": meta["label"], "value": round(v, 3), "unit": unit, "date": d.isoformat(), "period": period_label(d, meta["freq"]),
           "prev": round(pts[prev_d], 3) if prev_d else None, "prevPeriod": period_label(prev_d, meta["freq"]) if prev_d else None,
           "change": change, "changeUnit": "pp" if unit in ("%", "pp") else unit, "yearAgo": round(pts[year_d], 3) if year_d and year_d in pts else None,
           "source": meta["source"], "sourceUrl": SOURCE_URL.get(meta["source"]), "what": meta.get("what"),
           "spark": [[x.isoformat(), round(pts[x], 3)] for x in ds[-36:]]}
    if unit not in ("%", "pp") and prev_d:
        out["changePct"] = round((v / pts[prev_d] - 1) * 100, 2)
    return {**out, **(extra or {})}


def quarterly_avg(pts: S.Points) -> Dict[Tuple[int, int], float]:
    """Calendar-quarter averages of a monthly series (only quarters with all three months)."""
    acc: Dict[Tuple[int, int], List[float]] = {}
    for d, v in pts.items():
        acc.setdefault((d.year, (d.month - 1) // 3 + 1), []).append(v)
    return {k: round(sum(v) / 3, 2) for k, v in acc.items() if len(v) == 3}


def target_watch(cpi: S.Points) -> dict:
    """The accountability rule of the inflation-targeting framework: CPI inflation above 6% or below 2% for three consecutive quarters
    (quarterly averages) is a failure the RBI must explain to the Government."""
    q = quarterly_avg(cpi)
    keys = sorted(q)
    run, side = 0, None
    for k in reversed(keys):
        s = "above" if q[k] > BAND[1] else "below" if q[k] < BAND[0] else None
        if s is None or (side and s != side):
            break
        side, run = s, run + 1
    last = keys[-1] if keys else None
    return {"target": TARGET, "band": list(BAND), "quarters": [{"q": f"{y} Q{n}", "avg": q[(y, n)]} for y, n in keys[-8:]],
            "streak": run, "side": side, "lastQuarter": f"{last[0]} Q{last[1]}" if last else None,
            "rule": "If CPI inflation averages above 6% or below 2% for three quarters in a row, the RBI must report to the Government why, and what it will do."}


def insights(s: Dict[str, S.Points], wss: Optional[dict]) -> List[dict]:
    """Plain-language readings of the latest figures. Facts and the official framework only: no forecast, no advice."""
    out: List[dict] = []
    last = lambda k: (max(s[k]), s[k][max(s[k])]) if s.get(k) else (None, None)   # noqa: E731
    d, cpi = last("cpi")
    if cpi is not None:
        where = "above the 6% upper limit" if cpi > BAND[1] else "below the 2% lower limit" if cpi < BAND[0] else "above the 4% target but inside the 2-6% band" if cpi > TARGET else "at or below the 4% target, inside the 2-6% band"
        out.append({"key": "target", "tone": "warn" if cpi > BAND[1] or cpi < BAND[0] else "info", "title": f"Retail inflation is {cpi:.2f}%",
                    "text": f"In {d.strftime('%B %Y')} CPI inflation was {where} that the Government has set for the RBI (1 April 2026 to 31 March 2031)."})
    rd, rr = last("real_rate")
    _, repo = last("repo")
    if rr is not None and repo is not None:
        out.append({"key": "real", "tone": "info", "title": f"Real policy rate {'+' if rr >= 0 else '−'}{abs(rr):.2f} pp",
                    "text": f"The repo rate of {repo:.2f}% minus CPI inflation of {s['cpi'][rd]:.2f}% in {rd.strftime('%B %Y')}. "
                            + ("A positive real rate means policy money costs more than prices are rising." if rr > 0 else "A negative real rate means prices are rising faster than the policy rate.")})
    wd, wpi = last("wpi")
    if wpi is not None and cpi is not None and wd == d:
        gap = wpi - cpi
        out.append({"key": "pipeline", "tone": "warn" if gap > 2 else "info", "title": f"Wholesale {'above' if gap > 0 else 'below'} retail by {abs(gap):.2f} pp",
                    "text": f"WPI inflation was {wpi:.2f}% against CPI's {cpi:.2f}% in {wd.strftime('%B %Y')}. "
                            + ("Producer and trader prices rising faster than shop prices is a cost pressure that can reach retail prices later." if gap > 0 else "Shop prices are rising faster than wholesale prices.")})
    gd, g = last("gdp")
    _, gn = last("gdp_nominal")
    if g is not None and gn is not None and s["gdp_nominal"].get(gd) is not None:
        defl = s["gdp_nominal"][gd] - g
        out.append({"key": "deflator", "tone": "info", "title": f"GDP grew {g:.2f}% in real terms",
                    "text": f"{period_label(gd, 'Q')}: {s['gdp_nominal'][gd]:.2f}% at current prices, so prices across the whole economy (the GDP deflator) rose about {defl:.2f}%."})
    if wss and wss.get("reserves"):
        t = wss["reserves"]["total"]
        gold = wss["reserves"].get("gold", {}).get("usd")
        out.append({"key": "reserves", "tone": "info", "title": f"Reserves US${t['usd'] / 1000:.1f} bn",
                    "text": f"As on {date.fromisoformat(wss['reservesAsOf']).strftime('%d %B %Y').lstrip('0')}: {'down' if t['weekUsd'] < 0 else 'up'} US${abs(t['weekUsd']) / 1000:.2f} bn in the week and "
                            f"{'down' if t['yearUsd'] < 0 else 'up'} US${abs(t['yearUsd']) / 1000:.2f} bn on a year earlier" + (f"; gold is {gold / t['usd'] * 100:.1f}% of the total." if gold else ".")})
    cd, cr = last("credit_yoy")
    _, dp = last("deposits_yoy")
    if cr is not None and dp is not None:
        out.append({"key": "credit", "tone": "info", "title": f"Credit {'faster' if cr > dp else 'slower'} than deposits",
                    "text": f"Bank credit grew {cr:.1f}% and deposits {dp:.1f}% in the year to {cd.strftime('%d %B %Y').lstrip('0')}."})
    ud, ur = last("unemployment")
    _, yu = last("unemployment_youth")
    if ur is not None:
        out.append({"key": "jobs", "tone": "info", "title": f"Unemployment {ur:.1f}%",
                    "text": f"{ud.strftime('%B %Y')}, people aged 15 and above" + (f"; {yu:.1f}% for those aged 15-29." if yu is not None else ".")})
    return out


def coverage(series: Dict[str, S.Points], today: date) -> List[dict]:
    out = []
    for k in ["cpi", "wpi", "gdp", "iip", "unemployment", "repo", "fx_reserves", "usdinr", "credit_yoy"]:
        pts = series.get(k) or {}
        if pts:
            out.append({"key": k, "label": SERIES[k]["label"], "source": SERIES[k]["source"], "from": min(pts).isoformat(), "latest": max(pts).isoformat(),
                        "observations": len(pts), "ageDays": (today - max(pts)).days})
    return out


async def build(store, today: date) -> dict:
    async with store.pool.acquire() as conn:
        raw = await load_points(conn)
        rates = await get_meta(conn, "rbi_rates")
        wss = await get_meta(conn, "rbi_wss")
        labels = await get_meta(conn, "cpi_labels") or {}
        live = await get_meta(conn, "repo_live") or {"decisions": []}
        runs = {r["key"][4:]: (json.loads(r["body"]) if isinstance(r["body"], str) else r["body"]) for r in await conn.fetch("SELECT key, body FROM macro_meta WHERE key LIKE 'run:%'")}
    decisions = load_decisions() + [S.Decision(date.fromisoformat(x["date"]), x["rate"], x["bp"], x["source"]) for x in live["decisions"]]
    series, breaks, notes = derive(raw, decisions, today)
    series, issues = checked(series, today)
    if issues:
        log.warning("macro checks left out %d points: %s", len(issues), "; ".join(issues[:5]))
    cards = []
    for k in CARDS:
        c = card(k, series.get(k, {}))
        if not c:
            continue
        if k == "usdinr":                      # the day's reading against the previous day's, never against an old monthly average
            daily = series.get("usdinr_d") or {}
            ds = sorted(daily)
            c = card(k, daily) if len(ds) >= 2 else {**c, "change": None, "prev": None, "prevPeriod": None, "changePct": None}
            c["period"] = "FBIL reference rate, " + period_label(max(daily) if daily else date.fromisoformat(c["date"]), "D")
            c["spark"] = [[d.isoformat(), v] for d, v in list(series["usdinr"].items())[-36:]]
        if k == "fx_reserves" and wss and wss.get("reserves"):
            t = wss["reserves"]["total"]          # RBI's own week-on-week change, exact even when last week's release was not read
            c.update(value=round(t["usd"] / 1000, 3), date=wss["reservesAsOf"], period="Week ended " + period_label(date.fromisoformat(wss["reservesAsOf"]), "W"),
                     change=round(t["weekUsd"] / 1000, 3), prev=round((t["usd"] - t["weekUsd"]) / 1000, 3), prevPeriod="previous week",
                     changePct=round(t["weekUsd"] / (t["usd"] - t["weekUsd"]) * 100, 2), yearChange=round(t["yearUsd"] / 1000, 3))
        if k == "repo" and rates:
            c.update(value=rates["rates"]["repo"], period="In force today", date=rates.get("seenOn") or c["date"])
            lastd = max(decisions, key=lambda x: x.date)
            c.update(prev=round(lastd.rate - lastd.change_bp / 100, 2), prevPeriod=f"before {lastd.date.strftime('%d %b %Y').lstrip('0')}", change=round(lastd.change_bp / 100, 2),
                     lastDecision={"date": lastd.date.isoformat(), "bp": lastd.change_bp, "url": lastd.source})
        cards.append(c)
    divisions = [{"key": k, "label": labels.get(k, k), "points": [[d.isoformat(), v] for d, v in series[k].items()][-15:]}
                 for k in sorted([k for k in series if k.startswith("cpi_div_")]) if series[k]]
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "today": today.isoformat(),
        "cards": cards,
        "insights": insights(series, wss),
        "targetWatch": target_watch(series.get("cpi", {})),
        "series": {k: {"label": SERIES[k]["label"], "unit": SERIES[k]["unit"], "freq": SERIES[k]["freq"], "source": SERIES[k]["source"],
                       "sourceUrl": SOURCE_URL.get(SERIES[k]["source"]), "what": SERIES[k].get("what"), "note": notes.get(k), "breaks": breaks.get(k, []),
                       "points": [[d.isoformat(), v] for d, v in pts.items()]} for k, pts in series.items() if k in SERIES and pts},
        "cpiDivisions": divisions,
        "rates": rates, "reserves": wss,
        "decisions": [{"date": x.date.isoformat(), "rate": x.rate, "bp": x.change_bp, "url": x.source} for x in sorted(decisions, key=lambda x: x.date)],
        "coverage": coverage(series, today),
        "runs": runs, "issues": issues[:20],
        "sources": [{"name": "Ministry of Statistics and Programme Implementation (MoSPI), eSankhyiki", "url": "https://esankhyiki.mospi.gov.in", "covers": "CPI, WPI, GDP, IIP, PLFS; RBI handbook tables"},
                    {"name": "Reserve Bank of India", "url": "https://www.rbi.org.in", "covers": "Policy rates, Weekly Statistical Supplement (reserves, credit, deposits, money supply)"},
                    {"name": "Financial Benchmarks India (FBIL)", "url": "https://www.fbil.org.in", "covers": "Rupee reference rates, as shown on rbi.org.in"}],
        "disclaimer": "Every figure is reproduced from the official publisher or worked out from its published figures as described. Information only, not investment advice.",
    }
    return payload


async def publish(store, today: date) -> dict:
    payload = await build(store, today)
    body = dumps(payload)
    async with store.pool.acquire() as conn:
        await set_meta(conn, "payload", payload)
    try:
        await store.redis.hset(KEY, mapping={"body": body, "etag": etag_for(body).encode()})
        await store.redis.expire(KEY, 7 * 86400)
    except Exception:   # nosec B110 - Redis down: the route rebuilds from Postgres
        pass
    return payload


# ---------------------------------------------------------------------------------------------------- serving
@router.get("")
async def macro(request: Request):
    store = request.app.state.store
    try:
        hit = await store.redis.hmget(KEY, ["body", "etag"])
    except Exception:
        hit = [None, None]
    if hit[0] is None:
        async with store.pool.acquire() as conn:
            payload = await get_meta(conn, "payload")
        if not payload:
            return Response(content=dumps({"status": "loading", "detail": "Macro data has not been loaded yet. It loads nightly; check back soon."}),
                            status_code=503, media_type="application/json", headers={"Cache-Control": "no-store", "Retry-After": "600"})
        body = dumps(payload)
        etag = etag_for(body)
        try:
            await store.redis.hset(KEY, mapping={"body": body, "etag": etag.encode()})
            await store.redis.expire(KEY, 7 * 86400)
        except Exception:   # nosec B110 - cache only
            pass
    else:
        body, etag = hit[0], hit[1].decode()
    headers = {"ETag": etag, "Cache-Control": CACHE}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)
