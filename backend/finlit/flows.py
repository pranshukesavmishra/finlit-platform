"""FII / DII institutional flows: load the official daily figures (finlit/flows_sources.py says where each comes from), keep them in Postgres,
check them, and publish one ready-made page payload at /api/flows (the `Flows` type in frontend/src/lib/flows.ts).

Worker `refresh-flows` runs nightly (NSDL posts the day's report in the evening, so there is a retry later) and at boot when it has not run
for a day. Each source is its own step: one that fails keeps the last good data and says so in the payload's `sources`; nothing is ever
filled in. The first run loads the full FPI history month by month (one request per month, paced); later runs ask only for the current and
the previous month, the latest DII report and the latest participant-wise open-interest files. Figures an administrator typed in
(source 'manual') are never overwritten by a nightly run.
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import time
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import flows_sources as S
from .auth.routes import NO_STORE, Ctx, admin_ctx, fail, ip_of
from .auth.service import audit
from .background import etag_matches
from .store import dumps, etag_for

log = logging.getLogger("finlit.flows")
router = APIRouter(prefix="/api/flows")
admin = APIRouter(prefix="/api/admin/flows")

NSDL = "https://www.fpi.nsdl.co.in/web"
NSE_HOME = "https://www.nseindia.com/"
NSE_FIIDII = "https://www.nseindia.com/api/fiidiiTradeReact"
NSE_OI = "https://archives.nseindia.com/content/nsccl/fao_participant_oi_{:%d%m%Y}.csv"
USER_AGENT = "FinLit-data/1.0 (+https://finlitventures.com)"
PAUSE = 1.0                                   # seconds between two requests to NSDL (a month of history is one request)
OI_PAUSE = 0.4
KEY = "flows:v1"
CACHE = "public, max-age=600, stale-while-revalidate=3600"
IST = timezone(timedelta(hours=5, minutes=30))
FIRST = date(2010, 1, 1)                      # the stock-exchange route is split out in NSDL's tables from at least 2010; before that the layout differs
DII_START = date(2026, 6, 1)                  # NSDL's first DII report; nothing earlier is published
DII_REASON = "NSDL publishes the DII report from 1 June 2026; earlier DII days are not available from any official free source, so they are left empty, never estimated."
INDEX, INDEX_LABEL = "NIF50", "Nifty 50"
DAYS_SHOWN_YEARS = 5
MIN_CORR = 30
STALE_AFTER_DAYS = 4                          # a long weekend plus the evening posting; older than this and the source is called stale
MOODS = [(-5000, "Heavy outflow"), (-500, "Mild outflow")]


# ---------------------------------------------------------------------------------------------------- storage
async def get_meta(conn, key: str) -> Optional[dict]:
    raw = await conn.fetchval("SELECT body FROM flows_meta WHERE key = $1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def set_meta(conn, key: str, body) -> None:
    await conn.execute("INSERT INTO flows_meta (key, body, updated_at) VALUES ($1, $2::jsonb, now()) ON CONFLICT (key) DO UPDATE SET body = EXCLUDED.body, updated_at = now()",
                       key, json.dumps(body, default=str))


FII_SQL = """
INSERT INTO flows_daily (d, fii_buy, fii_sell, fii_net, fii_source, fpi_equity_net, fpi_debt_net, fpi_hybrid_net, fpi_total_net, fpi_usd_mn, fpi_inr, updated_at)
VALUES ($1, $2, $3, $4, 'nsdl', $5, $6, $7, $8, $9, $10, now())
ON CONFLICT (d) DO UPDATE SET
  fii_buy    = CASE WHEN flows_daily.fii_source IN ('manual', 'nse') THEN flows_daily.fii_buy  ELSE EXCLUDED.fii_buy  END,
  fii_sell   = CASE WHEN flows_daily.fii_source IN ('manual', 'nse') THEN flows_daily.fii_sell ELSE EXCLUDED.fii_sell END,
  fii_net    = CASE WHEN flows_daily.fii_source = 'manual' THEN flows_daily.fii_net  ELSE EXCLUDED.fii_net  END,
  fii_source = CASE WHEN flows_daily.fii_source IN ('manual', 'nse') THEN flows_daily.fii_source ELSE 'nsdl' END,
  fpi_equity_net = EXCLUDED.fpi_equity_net, fpi_debt_net = EXCLUDED.fpi_debt_net, fpi_hybrid_net = EXCLUDED.fpi_hybrid_net,
  fpi_total_net = EXCLUDED.fpi_total_net, fpi_usd_mn = EXCLUDED.fpi_usd_mn, fpi_inr = EXCLUDED.fpi_inr, updated_at = now()"""
DII_SQL = """
INSERT INTO flows_daily (d, dii_buy, dii_sell, dii_net, dii_source, updated_at) VALUES ($1, $2, $3, $4, 'nsdl', now())
ON CONFLICT (d) DO UPDATE SET
  dii_buy    = CASE WHEN flows_daily.dii_source = 'manual' THEN flows_daily.dii_buy  ELSE EXCLUDED.dii_buy  END,
  dii_sell   = CASE WHEN flows_daily.dii_source IN ('manual', 'nse') THEN flows_daily.dii_sell ELSE EXCLUDED.dii_sell END,
  dii_net    = CASE WHEN flows_daily.dii_source = 'manual' THEN flows_daily.dii_net  ELSE EXCLUDED.dii_net  END,
  dii_source = CASE WHEN flows_daily.dii_source IN ('manual', 'nse') THEN flows_daily.dii_source ELSE 'nsdl' END, updated_at = now()"""


async def save_fpi(conn, days: List[S.FpiDay]) -> int:
    rows = [(x.d, x.equity.buy, x.equity.sell, x.equity.net, x.equity_total.net if x.equity_total else None, x.debt_net, x.hybrid_net,
             x.total.net if x.total else None, x.total.usd if x.total else None, x.rate) for x in days if x.equity is not None]
    if rows:
        await conn.executemany(FII_SQL, rows)
    return len(rows)


async def save_dii(conn, day: S.DiiDay) -> None:
    await conn.execute(DII_SQL, day.d, day.equity.buy, day.equity.sell, day.equity.net)


NSE_SQL = """
INSERT INTO flows_daily (d, fii_buy, fii_sell, fii_net, fii_source, dii_buy, dii_sell, dii_net, dii_source, updated_at)
VALUES ($1, $2, $3, $4, 'nse', $5, $6, $7, 'nse', now())
ON CONFLICT (d) DO UPDATE SET
  fii_buy  = CASE WHEN flows_daily.fii_source = 'manual' THEN flows_daily.fii_buy  ELSE EXCLUDED.fii_buy  END,
  fii_sell = CASE WHEN flows_daily.fii_source = 'manual' THEN flows_daily.fii_sell ELSE EXCLUDED.fii_sell END,
  fii_net  = CASE WHEN flows_daily.fii_source = 'manual' THEN flows_daily.fii_net  ELSE EXCLUDED.fii_net  END,
  fii_source = CASE WHEN flows_daily.fii_source = 'manual' THEN 'manual' ELSE 'nse' END,
  dii_buy  = CASE WHEN flows_daily.dii_source = 'manual' THEN flows_daily.dii_buy  ELSE EXCLUDED.dii_buy  END,
  dii_sell = CASE WHEN flows_daily.dii_source = 'manual' THEN flows_daily.dii_sell ELSE EXCLUDED.dii_sell END,
  dii_net  = CASE WHEN flows_daily.dii_source = 'manual' THEN flows_daily.dii_net  ELSE EXCLUDED.dii_net  END,
  dii_source = CASE WHEN flows_daily.dii_source = 'manual' THEN 'manual' ELSE 'nse' END, updated_at = now()"""


async def save_nse(conn, day: S.NseDay) -> None:
    await conn.execute(NSE_SQL, day.d, day.fii.buy, day.fii.sell, day.fii.net, day.dii.buy, day.dii.sell, day.dii.net)


async def save_oi(conn, day: S.OiDay) -> None:
    await conn.executemany("INSERT INTO flows_oi (d, participant, instrument, long_, short_) VALUES ($1, $2, $3, $4, $5) "
                           "ON CONFLICT (d, participant, instrument) DO UPDATE SET long_ = EXCLUDED.long_, short_ = EXCLUDED.short_",
                           [(day.d, p, i, lo, sh) for (p, i), (lo, sh) in day.rows.items()])


# ---------------------------------------------------------------------------------------------------- manual entry (administrators)
class SideIn(BaseModel):
    buy: Optional[float] = Field(default=None, ge=0, le=S.MAX_CRORE)
    sell: Optional[float] = Field(default=None, ge=0, le=S.MAX_CRORE)
    net: Optional[float] = Field(default=None, ge=-S.MAX_CRORE, le=S.MAX_CRORE)


class ManualIn(BaseModel):
    d: date
    fii: Optional[SideIn] = None
    dii: Optional[SideIn] = None


def manual_side(side: SideIn) -> Tuple[Optional[float], Optional[float], float]:
    """(buy, sell, net) as typed. The net is the typed net, or purchases minus sales when only those are typed; never anything else."""
    net = side.net
    if net is None:
        if side.buy is None or side.sell is None:
            raise ValueError("give the net, or both the purchases and the sales")
        net = round(side.buy - side.sell, 2)
    elif side.buy is not None and side.sell is not None and abs((side.buy - side.sell) - net) > S.TOLERANCE + 0.05:
        raise ValueError(f"net {net} does not equal purchases {side.buy} minus sales {side.sell}")
    return side.buy, side.sell, round(net, 2)


# One written-out statement per side, so no column name is ever built from text.
UPSERT = {
    "fii": ("INSERT INTO flows_daily (d, fii_buy, fii_sell, fii_net, fii_source, updated_at) VALUES ($1, $2, $3, $4, 'manual', now()) "
            "ON CONFLICT (d) DO UPDATE SET fii_buy = EXCLUDED.fii_buy, fii_sell = EXCLUDED.fii_sell, fii_net = EXCLUDED.fii_net, "
            "fii_source = 'manual', updated_at = now()"),
    "dii": ("INSERT INTO flows_daily (d, dii_buy, dii_sell, dii_net, dii_source, updated_at) VALUES ($1, $2, $3, $4, 'manual', now()) "
            "ON CONFLICT (d) DO UPDATE SET dii_buy = EXCLUDED.dii_buy, dii_sell = EXCLUDED.dii_sell, dii_net = EXCLUDED.dii_net, "
            "dii_source = 'manual', updated_at = now()"),
}
CLEAR = {
    "fii": ("UPDATE flows_daily SET fii_buy = NULL, fii_sell = NULL, fii_net = NULL, fii_source = NULL, updated_at = now() "
            "WHERE d = $1 AND fii_source = 'manual'"),
    "dii": ("UPDATE flows_daily SET dii_buy = NULL, dii_sell = NULL, dii_net = NULL, dii_source = NULL, updated_at = now() "
            "WHERE d = $1 AND dii_source = 'manual'"),
}


async def save_manual(conn, body: ManualIn, today: date) -> List[str]:
    if body.d > today:
        raise ValueError("that date is in the future")
    if body.d < date(2000, 1, 1):
        raise ValueError("that date is too early")
    done = []
    for name, side in (("fii", body.fii), ("dii", body.dii)):
        if side is None:
            continue
        buy, sell, net = manual_side(side)
        await conn.execute(UPSERT[name], body.d, buy, sell, net)
        done.append(name)
    if not done:
        raise ValueError("give fii, dii or both")
    return done


async def clear_manual(conn, d: date, side: str) -> int:
    n = 0
    for name in ("fii", "dii") if side == "both" else (side,):
        r = await conn.execute(CLEAR[name], d)
        n += int(r.split()[-1])
    await conn.execute("DELETE FROM flows_daily WHERE d = $1 AND fii_source IS NULL AND dii_source IS NULL AND fpi_total_net IS NULL AND fpi_equity_net IS NULL", d)
    return n


# ---------------------------------------------------------------------------------------------------- fetching
class Sources:
    """The one HTTP client (honest User-Agent, nothing else). `transport` replaces the network in tests; `nifty` returns FinEdge's index history."""

    def __init__(self, transport: Optional[httpx.AsyncBaseTransport] = None, nifty: Optional[Callable[[], Awaitable[object]]] = None, settings=None):
        self.web = httpx.AsyncClient(transport=transport, timeout=60, follow_redirects=True,
                                     headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/csv, */*"})
        self._nifty, self.settings = nifty, settings
        self.calls = 0

    async def aclose(self):
        await self.web.aclose()

    async def get(self, url: str, ok404: bool = False, pause: Optional[float] = None) -> Optional[str]:
        for attempt in range(3):
            await asyncio.sleep(PAUSE if pause is None else pause)
            self.calls += 1
            try:
                r = await self.web.get(url)
                if r.status_code == 200:
                    return r.text
                if r.status_code == 404 and ok404:
                    return None
                if r.status_code < 500 and r.status_code != 429:
                    raise RuntimeError(f"{url} answered {r.status_code}")
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise RuntimeError(f"{url}: {type(exc).__name__}") from exc
            await asyncio.sleep(3 * (attempt + 1))
        raise RuntimeError(f"{url} kept failing")

    async def form(self, url: str, on: date) -> str:
        """NSDL's own date form (ASP.NET): load the page for its hidden fields, then 'press View Report' with the date filled in."""
        page = await self.get(url)
        fields = form_fields(page or "")
        if "__VIEWSTATE" not in fields:
            raise RuntimeError(f"{url}: the date form was not in the page")
        fields.update({"__EVENTTARGET": "btnSubmit1", "__EVENTARGUMENT": "", "hdnDate": on.strftime("%d-%b-%Y"), "txtDate": on.strftime("%d-%b-%Y")})
        await asyncio.sleep(PAUSE)
        self.calls += 1
        r = await self.web.post(url, data=fields)
        if r.status_code != 200:
            raise RuntimeError(f"{url} answered {r.status_code} for {on}")
        return r.text

    async def nse_json(self) -> str:
        """NSE's report API wants the cookie its home page sets, and a browser-style agent (it refuses plain scripts)."""
        hdr = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
               "Accept": "application/json, text/plain, */*", "Referer": "https://www.nseindia.com/reports/fii-dii"}
        for attempt in range(3):
            self.calls += 2
            try:
                await self.web.get(NSE_HOME, headers=hdr)                # sets the session cookie (the page itself may be refused: the cookie is still set)
                r = await self.web.get(NSE_FIIDII, headers=hdr)
                if r.status_code == 200 and r.text.lstrip().startswith("["):
                    return r.text
            except httpx.TransportError:
                pass
            await asyncio.sleep(2 * (attempt + 1))
        raise RuntimeError("the exchange's FII/DII report did not answer")

    async def nifty(self):
        if self._nifty is not None:
            return await self._nifty()
        return await nifty_from_finedge(self.settings)


def form_fields(page: str) -> Dict[str, str]:
    import html as h
    import re
    out = {}
    for tag in re.findall(r"<input[^>]*>", page, re.I):
        if not re.search(r"type=[\"']hidden[\"']", tag, re.I):
            continue
        n, v = re.search(r"name=[\"']([^\"']+)[\"']", tag), re.search(r"value=[\"']([^\"']*)[\"']", tag)
        if n:
            out[n.group(1)] = h.unescape(v.group(1)) if v else ""
    return out


async def nifty_from_finedge(settings):
    """Nifty 50 daily closes through the same provider code as /api/indices/NIF50/history (finlit/indices.py), not new network code."""
    from . import indices
    from .config import get_settings
    app = SimpleNamespace(state=SimpleNamespace(settings=settings or get_settings()))
    try:
        return await indices._fetch_levels(app, INDEX)
    finally:
        c = getattr(app.state, "index_client", None)
        if c is not None:
            await c.aclose()


def month_ends(a: date, b: date) -> List[date]:
    out, y, m = [], a.year, a.month
    while (y, m) <= (b.year, b.month):
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        out.append(nxt - timedelta(days=1))
        y, m = nxt.year, nxt.month
    return out


def weekdays(a: date, b: date) -> List[date]:
    return [a + timedelta(days=i) for i in range((b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5]


# ---------------------------------------------------------------------------------------------------- the steps
async def step_fpi(src: Sources, conn, today: date, full: bool) -> dict:
    have = {r["m"] for r in await conn.fetch("SELECT DISTINCT to_char(d, 'YYYY-MM') AS m FROM flows_daily WHERE fii_source = 'nsdl'")}
    ends = month_ends(FIRST, today)
    prev_m = ends[-2]
    todo = [e for e in ends[:-2] if full or e.strftime("%Y-%m") not in have]
    saved = failed = 0
    problems: List[str] = []
    for e in todo + [prev_m]:                                  # missing months, then last month again (NSDL confirms provisional figures later)
        try:
            days = S.parse_fpi(await src.form(f"{NSDL}/Reports/Archive.aspx", min(e, today)))
            problems += [f"{x.d}: {p}" for x in days for p in x.problems]
            saved += await save_fpi(conn, days)
        except Exception as exc:
            failed += 1
            log.warning("flows: NSDL archive for %s failed: %s", e.strftime("%Y-%m"), exc)
    cur = S.parse_fpi(await src.get(f"{NSDL}/Reports/Monthly.aspx") or "")          # the month so far, then the latest reporting day
    latest_page = await src.get(f"{NSDL}/Reports/Latest.aspx") or ""
    latest = S.parse_fpi(latest_page)
    problems += [f"{x.d}: {p}" for x in cur + latest for p in x.problems]
    saved += await save_fpi(conn, cur + latest)
    if not (cur or latest):
        raise RuntimeError("NSDL's daily FPI tables could not be read (the page layout may have changed)")
    if failed and not saved:
        raise RuntimeError(f"all {failed} NSDL archive requests failed")
    newest = max((x.d for x in cur + latest if x.equity), default=None)
    info = {"rows": saved, "months": len(todo) + 1, "failedMonths": failed, "latest": newest.isoformat() if newest else None, "problems": problems[:10]}
    return info


async def step_dii(src: Sources, conn, today: date, full: bool) -> dict:
    empty = set((await get_meta(conn, "dii_empty") or {"dates": []})["dates"])
    have = {r["d"] for r in await conn.fetch("SELECT d FROM flows_daily WHERE dii_net IS NOT NULL")}
    manual = {r["d"] for r in await conn.fetch("SELECT d FROM flows_daily WHERE dii_source = 'manual'")}
    sessions = {r["d"] for r in await conn.fetch("SELECT d FROM flows_daily WHERE d >= $1 AND fii_net IS NOT NULL", DII_START)}
    recent = weekdays(today - timedelta(days=7), today)
    cand = sorted((set(weekdays(DII_START, today)) | sessions | set(recent)) - manual)
    todo = [d for d in cand if d in recent or (d not in have and d.isoformat() not in empty)]
    todo = todo if full or not have else todo[-40:]            # the first run reads every day since June; a nightly run never spends more than 40 requests here
    saved, notes = 0, []
    page = await src.get(f"{NSDL}/Users/DIIGenerateReport.aspx?Rep=L")
    latest = S.parse_dii(page or "")
    if latest is not None and latest.problems:             # the investor types do not add up to the total: a misread table is never published
        notes += [f"{latest.d}: not saved, " + p for p in latest.problems]
        latest = None
    if latest is not None:
        await save_dii(conn, latest)
        saved += 1
    for d in todo:
        if latest is not None and d == latest.d:
            continue
        try:
            day = S.parse_dii(await src.form(f"{NSDL}/Users/DIIGenerateReport.aspx?Rep=A", d))
        except Exception as exc:
            log.warning("flows: NSDL DII report for %s failed: %s", d, exc)
            continue
        if day is None:
            if d < today - timedelta(days=4):                  # a past day with no report is a holiday: not asked for again
                empty.add(d.isoformat())
        elif day.problems:
            notes += [f"{d}: not saved, " + p for p in day.problems]
        elif day.d == d:
            await save_dii(conn, day)
            saved += 1
    await set_meta(conn, "dii_empty", {"dates": sorted(empty)[-400:]})
    if latest is None and not saved and not have:
        raise RuntimeError("NSDL's DII report could not be read")
    return {"rows": saved, "latest": latest.d.isoformat() if latest else None, "problems": notes[:10]}


async def step_nse(src: Sources, conn, today: date, full: bool) -> dict:
    """The exchange's own FII/DII cash-market report (provisional figures for the latest session): what news and other sites quote for the day.
    It replaces NSDL's settlement-date figure for that day, which differs. Only the latest session is published, so older days stay as NSDL has them."""
    days = S.parse_nse(await src.nse_json())
    saved = 0
    for day in days:
        if day.problems:
            log.warning("flows: NSE report for %s not saved: %s", day.d, "; ".join(day.problems))
            continue
        await save_nse(conn, day)
        saved += 1
    if not saved:
        raise RuntimeError("the exchange's FII/DII report could not be read")
    return {"rows": saved, "latest": max(d.d for d in days).isoformat()}


async def step_oi(src: Sources, conn, today: date, full: bool) -> dict:
    empty = set((await get_meta(conn, "oi_empty") or {"dates": []})["dates"])
    have = {r["d"] for r in await conn.fetch("SELECT DISTINCT d FROM flows_oi")}
    span = weekdays(today - timedelta(days=60 if full else 14), today)
    saved, missing = 0, 0
    for d in span:
        if d in have and d < today - timedelta(days=2) or d.isoformat() in empty:
            continue
        text = await src.get(NSE_OI.format(d), ok404=True, pause=OI_PAUSE)
        day = S.parse_participant_oi(text) if text else None
        if day is None or day.d != d:
            missing += 1
            if d < today - timedelta(days=3):
                empty.add(d.isoformat())
            continue
        await save_oi(conn, day)
        saved += 1
    await conn.execute("DELETE FROM flows_oi WHERE d < $1", today - timedelta(days=150))
    await set_meta(conn, "oi_empty", {"dates": sorted(empty)[-200:]})
    latest = await conn.fetchval("SELECT max(d) FROM flows_oi")
    if latest is None:
        raise RuntimeError("no participant-wise open-interest file could be read")
    return {"rows": saved, "latest": latest.isoformat(), "notPublished": missing}


async def step_nifty(src: Sources, conn, today: date, full: bool) -> dict:
    from .indices import shape_levels
    out = shape_levels(await src.nifty(), DAYS_SHOWN_YEARS)
    rows = [(INDEX, date.fromisoformat(r["d"]), float(r["c"])) for r in out["rows"]]
    if not rows:
        raise RuntimeError("no Nifty 50 closes")
    await conn.executemany("INSERT INTO flows_index (code, d, close) VALUES ($1, $2, $3) ON CONFLICT (code, d) DO UPDATE SET close = EXCLUDED.close", rows)
    return {"rows": len(rows), "latest": out["to"]}


STEPS: List[Tuple[str, Callable]] = [("fii", step_fpi), ("dii", step_dii), ("nse", step_nse), ("oi", step_oi), ("nifty", step_nifty)]
STEP_NAMES = [n for n, _ in STEPS]


async def refresh(store, transport: Optional[httpx.AsyncBaseTransport] = None, today: Optional[date] = None, full: bool = False,
                  only: Optional[List[str]] = None, nifty: Optional[Callable[[], Awaitable[object]]] = None, settings=None) -> dict:
    today = today or datetime.now(IST).date()
    src = Sources(transport, nifty, settings)
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
                    info = {"status": "ok", **info}
                except Exception as exc:              # one source failing never stops the others; its last good data stays
                    log.warning("flows step %s failed: %s", name, exc)
                    info = {"status": "failed", "reason": str(exc)[:200]}
                info.update(seconds=round(time.perf_counter() - t0, 1), at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
                await set_meta(conn, "run:" + name, info)
                result[name] = info
    finally:
        await src.aclose()
    payload = await publish(store, today)
    bad = [k for k, v in result.items() if v["status"] == "failed"]
    return {"status": "ok" if not bad else "partial" if len(bad) < len(result) else "failed", "steps": result, "calls": src.calls,
            "sessions": payload["coverage"]["sessions"], "diiSessions": payload["coverage"]["diiSessions"], "seconds": round(time.perf_counter() - started, 1)}


# ---------------------------------------------------------------------------------------------------- the maths
class Row:
    __slots__ = ("d", "fb", "fs", "fn", "fsrc", "db", "ds", "dn", "dsrc")

    def __init__(self, d, fb=None, fs=None, fn=None, fsrc=None, db=None, ds=None, dn=None, dsrc=None):
        self.d, self.fb, self.fs, self.fn, self.fsrc, self.db, self.ds, self.dn, self.dsrc = d, fb, fs, fn, fsrc, db, ds, dn, dsrc


def r2(v: Optional[float]) -> Optional[float]:
    return None if v is None else round(v + 0.0, 2)


def checked(rows: List[Row], today: date) -> Tuple[List[Row], List[str]]:
    """Publish-time sanity: a day dated in the future, an amount no investor class trades in a day, or a net that is not purchases minus
    sales is left out of the page (and logged); the stored row is kept for the next look."""
    keep, issues = [], []
    for r in rows:
        why = None
        if r.d > today:
            why = "dated in the future"
        for name, b, s, n in (("FII", r.fb, r.fs, r.fn), ("DII", r.db, r.ds, r.dn)):
            if why or n is None:
                continue
            if abs(n) > S.MAX_CRORE or (b is not None and not 0 <= b <= S.MAX_CRORE) or (s is not None and not 0 <= s <= S.MAX_CRORE):
                why = f"{name} amount out of range"
            elif b is not None and s is not None and abs((b - s) - n) > S.TOLERANCE + 0.05:
                why = f"{name} net is not purchases minus sales"
        if why:
            issues.append(f"{r.d}: {why}")
        else:
            keep.append(r)
    return keep, issues


def mood_of(net: Optional[float]) -> Optional[str]:
    if net is None:
        return None
    if net <= -5000:
        return "Heavy outflow"
    if net < -500:
        return "Mild outflow"
    if net >= 5000:
        return "Heavy inflow"
    if net > 500:
        return "Mild inflow"
    return "Balanced"


def streak(series: List[Tuple[date, float]]) -> Optional[dict]:
    """Consecutive most-recent sessions with the same sign of net (flat when zero); velocity is the average net per session over the streak."""
    if not series:
        return None
    sign = lambda v: (v > 0) - (v < 0)          # noqa: E731
    s = sign(series[-1][1])
    run = []
    for d, v in reversed(series):
        if sign(v) != s:
            break
        run.append((d, v))
    total = round(sum(v for _, v in run), 2)
    return {"side": "buying" if s > 0 else "selling" if s < 0 else "flat", "days": len(run), "since": run[-1][0].isoformat(), "sum": total, "velocity": round(total / len(run), 2)}


def pearson(xs: List[float], ys: List[float]) -> Optional[float]:
    n = len(xs)
    if n < MIN_CORR:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    return round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / math.sqrt(sxx * syy), 3)


def correlation(rows: List[Row], closes: Dict[date, float]) -> Optional[dict]:
    """Pearson correlation of each class's daily net flow with the Nifty 50's daily % change, over the sessions both have; None under 30."""
    ds = sorted(closes)
    chg = {b: (closes[b] / closes[a] - 1) * 100 for a, b in zip(ds, ds[1:]) if closes[a]}
    f = [(r.fn, chg[r.d]) for r in rows if r.fn is not None and r.d in chg]
    g = [(r.dn, chg[r.d]) for r in rows if r.dn is not None and r.d in chg]
    if len(f) < MIN_CORR:
        return None
    return {"index": INDEX, "label": INDEX_LABEL, "fiiVsIndex": pearson([a for a, _ in f], [b for _, b in f]),
            "diiVsIndex": pearson([a for a, _ in g], [b for _, b in g]) if len(g) >= MIN_CORR else None, "days": len(f)}


def total(rows: List[Row], attr: str) -> Optional[float]:
    """Sum over a window, or None: with no session, or with any session missing the figure (a part-sum would pass for the whole)."""
    vals = [getattr(r, attr) for r in rows]
    return r2(sum(vals)) if vals and all(v is not None for v in vals) else None


def common(rows: List[Row]) -> Optional[dict]:
    """For a window that starts before the DII report exists: FII, DII and their sum over the sessions from the first DII day on, with the dates they
    cover, so a headline never sets a 12-month FII total against a 5-month DII total. None when the window has full DII (the plain totals say it), has
    none, or has a session without a figure after the first DII day (a part-sum is never given)."""
    first = next((i for i, r in enumerate(rows) if r.dn is not None), None)
    if first is None or first == 0:
        return None
    w = rows[first:]
    f, d = total(w, "fn"), total(w, "dn")
    if f is None or d is None:
        return None
    return {"from": w[0].d.isoformat(), "to": w[-1].d.isoformat(), "days": len(w), "fii": f, "dii": d, "overall": r2(f + d)}


def period(key: str, label: str, rows: List[Row], start: Optional[date], today: date) -> dict:
    return {"key": key, "label": label, "from": (rows[0].d if rows else start or today).isoformat(), "to": (rows[-1].d if rows else today).isoformat(), "days": len(rows),
            "fii": total(rows, "fn"), "diiNet": total(rows, "dn"), "fiiBuy": total(rows, "fb"), "fiiSell": total(rows, "fs"),
            "diiDays": sum(r.dn is not None for r in rows), "common": common(rows)}


def rolling(n: int, rows: List[Row], today: date) -> dict:
    w = rows[-n:]
    p = period(f"r{n}", f"Last {n} sessions", w, None, today)
    if len(w) < n:                                  # fewer sessions than the window asks for: the days are counted, the sums are not given
        p.update(fii=None, diiNet=None, fiiBuy=None, fiiSell=None, common=None)
    return p


def periods(rows: List[Row], today: date) -> List[dict]:
    wk = today - timedelta(days=today.weekday())
    fy = date(today.year if today.month >= 4 else today.year - 1, 4, 1)
    since = lambda s: [r for r in rows if s <= r.d <= today]       # noqa: E731
    return [period("week", "This week", since(wk), wk, today), period("month", "This month", since(today.replace(day=1)), today.replace(day=1), today),
            period("fy", "This financial year", since(fy), fy, today), period("cy", "This calendar year", since(date(today.year, 1, 1)), date(today.year, 1, 1), today),
            *[rolling(n, rows, today) for n in (30, 90, 365)]]


def grouped(rows: List[Row], fmt: str, name: str) -> List[dict]:
    out: Dict[str, List[Row]] = {}
    for r in rows:
        out.setdefault(r.d.strftime(fmt), []).append(r)
    return [{name: k, "fii": total(v, "fn"), "dii": total(v, "dn"), "days": len(v)} for k, v in sorted(out.items())]


def side(b, s, n) -> dict:
    return {"buy": r2(b), "sell": r2(s), "net": r2(n)}


def positioning(oi: List[dict]) -> Optional[dict]:
    if not oi:
        return None
    d = max(r["d"] for r in oi)
    got = {(r["participant"], r["instrument"]): r for r in oi if r["d"] == d}
    rows = []
    for p in ("FII", "DII", "Pro", "Client"):
        for i in S.INSTRUMENTS:
            r = got.get((p, i))
            if r:
                lo, sh = r["long_"], r["short_"]
                rows.append({"participant": p, "instrument": i, "long": lo, "short": sh, "net": None if lo is None or sh is None else lo - sh})
    return {"asOf": d.isoformat(), "rows": rows} if rows else None


def fpi_detail(rows: List[dict]) -> Optional[dict]:
    got = [r for r in rows if r["fpi_total_net"] is not None]
    if not got:
        return None
    r = got[-1]
    return {"asOf": r["d"].isoformat(), "equityNet": r2(r["fpi_equity_net"]), "debtNet": r2(r["fpi_debt_net"]), "hybridNet": r2(r["fpi_hybrid_net"]),
            "totalNet": r2(r["fpi_total_net"]), "usdMillion": r2(r["fpi_usd_mn"]), "inr": r["fpi_inr"]}


def source_status(last: Optional[date], today: date, run: Optional[dict]) -> Tuple[str, Optional[str]]:
    if last is None:
        return "unavailable", None
    late = (today - last).days > STALE_AFTER_DAYS
    return ("stale" if late else "ok"), last.isoformat()


def notes_for(rows: List[Row], issues: List[str], runs: Dict[str, dict], oi: Optional[dict], closes: Dict[date, float], today: date) -> List[dict]:
    f_last = max((r.d for r in rows if r.fn is not None and r.fsrc in ("nsdl", "nse")), default=None)
    d_last = max((r.d for r in rows if r.dn is not None and r.dsrc in ("nsdl", "nse")), default=None)
    man = [r for r in rows if "manual" in (r.fsrc, r.dsrc)]
    n_fii, n_dii = sum(r.fn is not None for r in rows), sum(r.dn is not None for r in rows)
    first_dii = min((r.d for r in rows if r.dn is not None), default=None)

    def run_note(key: str) -> str:
        r = runs.get(key) or {}
        return f" The last refresh failed ({r.get('reason')}); the last good figures are shown." if r.get("status") == "failed" else ""
    out = []
    st, ld = source_status(f_last, today, runs.get("fii"))
    out.append({"id": "fii", "label": "NSDL FPI Monitor: daily trends in FPI investments", "url": "https://www.fpi.nsdl.co.in/web/Reports/Latest.aspx",
                "covers": "FII (foreign portfolio investor) cash-market equity purchases, sales and net, stock-exchange route, Rs crore; the all-asset view (debt, hybrid) for the latest day",
                "status": st, "lastDate": ld,
                "note": f"{n_fii} sessions from {min((r.d for r in rows if r.fn is not None), default=today).isoformat()}. NSDL compiles the day's provisional figures from the exchanges and revises them as custodians confirm; "
                        "a day's report is posted in the evening." + run_note("fii") + (f" {len(issues)} day(s) left out by checks." if issues else "")})
    st, ld = source_status(d_last, today, runs.get("dii"))
    if d_last is None and not any(r.dsrc == "manual" for r in rows):
        out.append({"id": "dii", "label": "NSDL FPI Monitor: DII report", "url": "https://www.fpi.nsdl.co.in/web/Users/DIIGenerateReport.aspx?Rep=L", "covers": "DII (domestic institutional investor) cash-market flows",
                    "status": "unavailable", "lastDate": None,
                    "note": "No permitted official source is publishing domestic-institution flows to us right now. The exchanges' own FII/DII report is behind bot protection that does not answer an honest crawler, so DII figures are left empty rather than estimated." + run_note("dii")})
    else:
        out.append({"id": "dii", "label": "NSDL FPI Monitor: DII report", "url": "https://www.fpi.nsdl.co.in/web/Users/DIIGenerateReport.aspx?Rep=L",
                    "covers": "DII cash-market equity purchases, sales and net, stock-exchange route, Rs crore: banks, insurers, mutual funds, AIFs and others together",
                    "status": st if d_last else "ok", "lastDate": ld,
                    "note": f"{n_dii} sessions" + (f" from {first_dii.isoformat()}" if first_dii else "") + ". NSDL began publishing this report on 1 June 2026, so there is no earlier DII history from a permitted source. "
                            "Days before it are empty, and totals that span them show no DII figure rather than a part-sum." + run_note("dii")})
    if man:
        out.append({"id": "manual", "label": "Entered by FinLit from the exchange's published FII/DII report", "url": "https://www.nseindia.com/reports/fii-dii",
                    "covers": "Days an administrator typed in; they take the place of NSDL's figure for that side and day", "status": "ok", "lastDate": max(r.d for r in man).isoformat(),
                    "note": f"{len(man)} day(s). Definitions can differ slightly from NSDL's (the exchanges report their own trade data)."})
    if oi:
        st, ld = source_status(date.fromisoformat(oi["asOf"]), today, runs.get("oi"))
        out.append({"id": "participant-oi", "label": "NSE archive: participant-wise open interest", "url": "https://archives.nseindia.com/content/nsccl/fao_participant_oi_" + date.fromisoformat(oi["asOf"]).strftime("%d%m%Y") + ".csv",
                    "covers": "Futures and options open interest (contracts) of FII, DII, Pro and Client, end of day", "status": st, "lastDate": ld,
                    "note": "Options are calls and puts added together (long = held long, short = written); the file also splits calls from puts." + run_note("oi")})
    else:
        out.append({"id": "participant-oi", "label": "NSE archive: participant-wise open interest", "url": "https://archives.nseindia.com/content/nsccl/", "covers": "Futures and options open interest by participant",
                    "status": "unavailable", "lastDate": None, "note": "The file could not be read." + run_note("oi")})
    nse = [r for r in rows if "nse" in (r.fsrc, r.dsrc)]
    if nse:
        st, ld = source_status(max(r.d for r in nse), today, runs.get("nse"))
        out.append({"id": "nse-cash", "label": "NSE: FII/DII trading activity (cash market)", "url": "https://www.nseindia.com/reports/fii-dii", "covers": "The exchange's own daily FII and DII cash-market report, provisional",
                    "status": st, "lastDate": ld,
                    "note": f"{len(nse)} session(s) read from the exchange's report; these are the figures news sites quote for the day, and they take the place of NSDL's settlement-date figure for that day. "
                            "The exchange publishes only the latest session, so older days stay as NSDL has them." + run_note("nse")})
    else:
        out.append({"id": "nse-cash", "label": "NSE and BSE: FII/DII trading activity (cash market)", "url": "https://www.nseindia.com/reports/fii-dii", "covers": "The exchanges' own daily FII and DII cash-market report",
                    "status": "unavailable", "lastDate": None,
                    "note": "The exchange's report could not be read yet; NSDL's figures above are used meanwhile." + run_note("nse")})
    if closes:
        last = max(closes)
        st, ld = source_status(last, today, runs.get("nifty"))
        out.append({"id": "nifty", "label": "Nifty 50 daily closes (index data provider)", "url": "https://finlitventures.com/api/indices/NIF50/history", "covers": "Used for the flow-versus-index correlation only",
                    "status": st, "lastDate": ld, "note": "Pearson correlation of each day's net flow with the Nifty 50's same-day percentage change, over the sessions both have (shown from 30)." + run_note("nifty")})
    else:
        out.append({"id": "nifty", "label": "Nifty 50 daily closes (index data provider)", "url": "https://finlitventures.com/api/indices/NIF50/history", "covers": "Used for the flow-versus-index correlation only",
                    "status": "unavailable", "lastDate": None, "note": "No index history is loaded, so no correlation is shown." + run_note("nifty")})
    return out


async def build(store, today: date) -> dict:
    async with store.pool.acquire() as conn:
        recs = await conn.fetch("SELECT * FROM flows_daily ORDER BY d")
        oi = [dict(r) for r in await conn.fetch("SELECT * FROM flows_oi WHERE d = (SELECT max(d) FROM flows_oi)")]
        closes = {r["d"]: r["close"] for r in await conn.fetch("SELECT d, close FROM flows_index WHERE code = $1 ORDER BY d", INDEX)}
        runs = {r["key"][4:]: (json.loads(r["body"]) if isinstance(r["body"], str) else r["body"]) for r in await conn.fetch("SELECT key, body FROM flows_meta WHERE key LIKE 'run:%'")}
    rows = [Row(r["d"], r["fii_buy"], r["fii_sell"], r["fii_net"], r["fii_source"], r["dii_buy"], r["dii_sell"], r["dii_net"], r["dii_source"]) for r in recs]
    rows = [r for r in rows if r.fn is not None or r.dn is not None]
    rows, issues = checked(rows, today)
    if issues:
        log.warning("flows checks left out %d days: %s", len(issues), "; ".join(issues[:5]))
    cut = (rows[-1].d - timedelta(days=round(365.25 * DAYS_SHOWN_YEARS))) if rows else today
    shown = [r for r in rows if r.d >= cut]
    days = [{"d": r.d.isoformat(), "fii": side(r.fb, r.fs, r.fn), "dii": side(r.db, r.ds, r.dn) if r.dn is not None else None} for r in shown]
    last = shown[-1] if shown else None
    latest = None
    if last:
        both = last.fn is not None and last.dn is not None
        sells = last.fs is not None and last.ds is not None and (last.fs + last.ds) > 0
        latest = {"d": last.d.isoformat(), "fii": days[-1]["fii"], "dii": days[-1]["dii"], "combinedNet": r2(last.fn + last.dn) if both else None,
                  "fiiShareOfSelling": round(last.fs / (last.fs + last.ds), 4) if sells else None, "mood": mood_of(last.fn)}
    fser = [(r.d, r.fn) for r in rows if r.fn is not None]
    dser = [(r.d, r.dn) for r in rows if r.dn is not None]
    positions = positioning(oi)
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "today": today.isoformat(),
        "latest": latest,
        "streaks": {"fii": streak(fser), "dii": streak(dser)},
        "last30": {"fii": r2(sum(v for _, v in fser[-30:])) if len(fser) >= 30 else None, "dii": r2(sum(v for _, v in dser[-30:])) if len(dser) >= 30 else None, "days": min(30, len(fser))},
        "days": days,
        "periods": periods(rows, today),
        "monthly": grouped(rows, "%Y-%m", "m"),
        "yearly": grouped(rows, "%Y", "y"),
        "derivatives": positions,
        "fpi": fpi_detail([dict(r) for r in recs]),
        "correlation": correlation(shown, closes),
        "index": [{"d": r.d.isoformat(), "close": closes[r.d]} for r in shown if r.d in closes] or None,
        "coverage": {"from": days[0]["d"] if days else None, "to": days[-1]["d"] if days else None, "sessions": sum(r.fn is not None for r in shown), "diiSessions": sum(r.dn is not None for r in shown),
                     "diiFrom": next((r.d.isoformat() for r in shown if r.dn is not None), None), "diiPublishedFrom": DII_START.isoformat(), "diiReason": DII_REASON},
        "sources": notes_for(rows, issues, runs, positions, closes, today),
        "disclaimer": "Figures are reproduced from the official publishers (NSDL, NSE archives) in Rs crore, or worked out from them as described. NSDL's daily figures are provisional and are revised as custodians confirm trades. "
                      "A figure no permitted source publishes is left empty, never estimated. Information only, not investment advice.",
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
async def flows(request: Request):
    store = request.app.state.store
    try:
        hit = await store.redis.hmget(KEY, ["body", "etag"])
    except Exception:
        hit = [None, None]
    if hit[0] is None:
        async with store.pool.acquire() as conn:
            payload = await get_meta(conn, "payload")
        if not payload:
            return Response(content=dumps({"status": "loading", "detail": "Institutional flows have not been loaded yet. They load nightly; check back soon."}),
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


@admin.post("")
async def admin_enter(request: Request, body: ManualIn, ctx: Ctx = Depends(admin_ctx)):
    """Type in a day's FII and/or DII cash-market figures from the exchange's published report (Rs crore). Labelled 'manual' in the page's sources."""
    store = request.app.state.store
    today = datetime.now(IST).date()
    try:
        async with store.pool.acquire() as conn:
            done = await save_manual(conn, body, today)
    except ValueError as exc:
        raise fail(422, "invalid", str(exc))
    await audit(store.pool, ctx.user_id, "admin_flows_manual", body.d.isoformat(), ip_of(request), sides=done)
    payload = await publish(store, today)
    return Response(dumps({"ok": True, "d": body.d.isoformat(), "sides": done, "sessions": payload["coverage"]["sessions"]}), media_type="application/json", headers=NO_STORE)


@admin.delete("/{d}")
async def admin_clear(request: Request, d: date, side: str = "both", ctx: Ctx = Depends(admin_ctx)):
    """Remove a manually entered day (only manual figures; NSDL's are never deleted here)."""
    if side not in ("fii", "dii", "both"):
        raise fail(422, "invalid", "side is fii, dii or both")
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        n = await clear_manual(conn, d, side)
    await audit(store.pool, ctx.user_id, "admin_flows_manual_clear", d.isoformat(), ip_of(request), side=side, removed=n)
    await publish(store, datetime.now(IST).date())
    return Response(dumps({"ok": True, "removed": n}), media_type="application/json", headers=NO_STORE)
