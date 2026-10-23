"""Market indices: live prices for every NSE and BSE index, and each index's valuation history (P/E, P/B, dividend yield).

Straight from the data provider (FinEdge), not through the site backend. Answers are kept in Redis and served at once:
index prices are fresh for a minute while the market is open (15 minutes otherwise), valuation history for six hours; past that
the saved copy is still served instantly while one background call refreshes it. Prices are public (the strip at the top of
every page uses them); valuation history is a Gold tool.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
import time
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth.routes import NO_STORE, Ctx, fail
from .finedge import FinEdgeClient, FinEdgeError
from .premium import premium_ctx
from .background import spawn

log = logging.getLogger("finlit.indices")
router = APIRouter(prefix="/api/indices")
IST = ZoneInfo("Asia/Kolkata")
CODE = re.compile(r"^[A-Z0-9]{2,24}$")
KEEP = 7 * 24 * 3600            # how long a saved answer may still be served while a refresh runs
HISTORY_YEARS = 5
# Shown first, in this order: the strip at the top of the site and the key tiles on the dashboard.
KEY = ["NIF50", "SNSXSENSEX", "NIFBAN", "NIFMID100", "NIFSMA100", "NIFIT", "INDVIX"]

SECTOR = re.compile(r"\b(bank|it|pharma|auto|fmcg|metal|realty|energy|media|financial|fin serv|healthcare|oil|gas|consumer durables|chemicals|"
                    r"infra|commodit|capital goods|telecom|utilities|power|industrials|services sector|private bank|psu bank|insurance|"
                    r"cement|construction|textile|teck|tech|consumption|manufacturing|transport|logistics|defence|housing|rural|digital)\b", re.I)
BROAD = re.compile(r"^(nifty ?(50|100|200|500|next 50|midcap|smallcap|microcap|largemidcap|total market|midsmallcap|mid ?small)|"
                   r"bse (sensex|100|200|500|midcap|smallcap|largecap|allcap|large ?cap|mid ?cap|small ?cap|sensex next|150|250|400|1000)|"
                   r"nifty mid|nifty small|nifty large|nifty500|nifty total)", re.I)


def market_open(now: Optional[datetime] = None) -> bool:
    t = now or datetime.now(IST)
    return t.weekday() < 5 and (9, 0) <= (t.hour, t.minute) <= (15, 45)


def group_of(name: str, code: str) -> str:
    if code == "INDVIX" or "vix" in name.lower():
        return "Volatility"
    if BROAD.match(name.strip()) and not SECTOR.search(name):
        return "Broad market"
    if SECTOR.search(name):
        return "Sector"
    return "Strategy & theme"


def _num(v: Any, zero_is_none: bool = False) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or (zero_is_none and f == 0):
        return None
    return f


def shape_feed(payload: Any) -> Dict[str, Any]:
    rows = payload if isinstance(payload, list) else next((v for v in (payload or {}).values() if isinstance(v, list)), [])
    items = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        code, name = str(r.get("index_symbol") or "").strip().upper(), " ".join(str(r.get("index_name") or "").split())
        if not code or not name:
            continue
        items.append({"code": code, "name": name, "group": group_of(name, code), "exchange": "BSE" if code.startswith("SNSX") else "NSE",
                      "close": _num(r.get("close_price")), "changePct": _num(r.get("change_pct")), "points": _num(r.get("points_change")),
                      "open": _num(r.get("open_price")), "high": _num(r.get("high_price")), "low": _num(r.get("low_price")),
                      "pe": _num(r.get("pe"), True), "pb": _num(r.get("pb"), True), "divYield": _num(r.get("div_yield"), True),
                      "date": str(r.get("quote_date") or "")[:10] or None})
    order = {c: i for i, c in enumerate(KEY)}
    items.sort(key=lambda x: (order.get(x["code"], len(KEY)), x["exchange"] != "NSE", x["name"].lower()))
    as_of = max((x["date"] for x in items if x["date"]), default=None)
    return {"items": items, "key": [c for c in KEY if c in {x["code"] for x in items}], "asOf": as_of}


def _stats(values: List[float]) -> Optional[Dict[str, float]]:
    if len(values) < 2:
        return None
    now = values[-1]
    return {"now": now, "median": statistics.median(values), "mean": statistics.fmean(values), "sd": statistics.pstdev(values),
            "min": min(values), "max": max(values), "pctile": round(100 * sum(v <= now for v in values) / len(values), 1), "n": len(values)}


def shape_history(payload: Any, years: int) -> Dict[str, Any]:
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else payload
    out = []
    for r in rows or []:
        d = str((r or {}).get("quote_date") or "")[:10]
        if len(d) != 10:
            continue
        out.append({"d": d, "pe": _num(r.get("pe"), True), "pb": _num(r.get("pb"), True), "dy": _num(r.get("div_yield"), True)})
    out.sort(key=lambda x: x["d"])
    if out:
        cut = (date.fromisoformat(out[-1]["d"]) - timedelta(days=round(365.25 * years))).isoformat()
        out = [x for x in out if x["d"] >= cut]
    stats = {k: _stats([x[k] for x in out if x[k] is not None]) for k in ("pe", "pb", "dy")}
    return {"rows": out, "stats": stats, "from": out[0]["d"] if out else None, "to": out[-1]["d"] if out else None}


def shape_levels(payload: Any, years: int) -> Dict[str, Any]:
    """Daily closing level of an index (points), oldest first, for up to `years` back from its latest day."""
    rows = (payload or {}).get("rows") if isinstance(payload, dict) else payload
    out = []
    for r in rows or []:
        d = str((r or {}).get("quote_date") or "")[:10]
        c = _num((r or {}).get("close_price"), True)
        if len(d) == 10 and c is not None:
            out.append({"d": d, "c": c})
    out.sort(key=lambda x: x["d"])
    if out:
        cut = (date.fromisoformat(out[-1]["d"]) - timedelta(days=round(365.25 * years))).isoformat()
        out = [x for x in out if x["d"] >= cut]
    return {"rows": out, "from": out[0]["d"] if out else None, "to": out[-1]["d"] if out else None}


# ---------------------------------------------------------------- provider + cache

def _client(app) -> FinEdgeClient:
    c = getattr(app.state, "index_client", None)
    if c is None:
        c = app.state.index_client = FinEdgeClient(app.state.settings)
    return c


async def _fetch_feed(app) -> Dict[str, Any]:
    return shape_feed(await _client(app).get("/index/market-price/daily-feed", {}, timeout=20, retries=1))


async def _fetch_history(app, code: str) -> Any:
    today = datetime.now(IST).date()
    return await _client(app).get("/index/valuation/historical", {"index_symbol": code, "from_date": (today - timedelta(days=round(365.25 * HISTORY_YEARS) + 7)).isoformat(),
                                                                   "to_date": today.isoformat()}, timeout=25, retries=1)


async def _fetch_levels(app, code: str) -> Any:
    today = datetime.now(IST).date()
    return await _client(app).get("/index/market-price/historical", {"index_symbol": code, "from_date": (today - timedelta(days=round(365.25 * HISTORY_YEARS) + 7)).isoformat(),
                                                                      "to_date": today.isoformat()}, timeout=25, retries=1)


async def _cached(app, key: str, fresh: float, fetch) -> Optional[Dict[str, Any]]:
    """Saved copy at once (refreshed behind the scenes once it is older than `fresh` seconds); the provider is asked only when nothing is saved."""
    redis = app.state.store.redis
    try:
        raw = await redis.get(key)
    except Exception:
        raw = None
    if raw:
        hit = json.loads(raw)
        if time.time() - hit["t"] > fresh:
            spawn(_refresh(app, key, fetch))
        return hit["v"]
    return await _refresh(app, key, fetch, wait=True)


async def _refresh(app, key: str, fetch, wait: bool = False) -> Optional[Dict[str, Any]]:
    redis = app.state.store.redis
    try:
        if not await redis.set(key + ":lock", "1", nx=True, ex=30):
            if not wait:
                return None
            for _ in range(60):   # another request is already asking the provider: use its answer
                await asyncio.sleep(0.25)
                raw = await redis.get(key)
                if raw:
                    return json.loads(raw)["v"]
    except Exception:
        pass
    try:
        value = await fetch()
    except FinEdgeError as exc:
        log.warning("index data not refreshed (%s): %s", key, exc)
        value = None
    try:
        if value is not None:
            await redis.set(key, json.dumps({"t": time.time(), "v": value}), ex=KEEP)
        await redis.delete(key + ":lock")
    except Exception:
        pass
    return value


@router.get("")
async def indices(request: Request) -> Response:
    """Every index with today's level, move and valuation; the key indices first."""
    fresh = 60 if market_open() else 900
    data = await _cached(request.app, "idx:feed", fresh, lambda: _fetch_feed(request.app))
    if data is None:
        raise fail(502, "provider_unavailable", "Index prices are not available right now. Please try again in a moment.")
    return Response(json.dumps({**data, "marketOpen": market_open()}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=30"})


@router.get("/{code}/history")
async def history(request: Request, code: str, years: int = Query(5, ge=1, le=HISTORY_YEARS)) -> Response:
    """Daily closing level of one index in points for up to five years. Public, like the index prices; one saved copy per index serves every viewer."""
    code = code.strip().upper()
    if not CODE.match(code):
        raise fail(400, "bad_request", "Unknown index.")
    raw = await _cached(request.app, f"idx:px:{code}", 3600 if market_open() else 6 * 3600, lambda: _fetch_levels(request.app, code))
    if raw is None:
        raise fail(502, "provider_unavailable", "The index history is not available right now. Please try again in a moment.")
    out = shape_levels(raw, years)
    if not out["rows"]:
        raise fail(404, "not_found", "There is no price history for this index.")
    feed = await _cached(request.app, "idx:feed", 900, lambda: _fetch_feed(request.app)) or {"items": []}
    name = next((x["name"] for x in feed["items"] if x["code"] == code), code)
    return Response(json.dumps({"code": code, "name": name, "years": years, "unit": "points", **out}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=300"})


@router.get("/{code}/valuation")
async def valuation(request: Request, code: str, years: int = Query(5, ge=1, le=HISTORY_YEARS), ctx: Ctx = Depends(premium_ctx)) -> Response:
    """Daily P/E, P/B and dividend yield of one index for up to five years, with where today sits against that history."""
    code = code.strip().upper()
    if not CODE.match(code):
        raise fail(400, "bad_request", "Unknown index.")
    raw = await _cached(request.app, f"idx:val:{code}", 6 * 3600, lambda: _fetch_history(request.app, code))
    if raw is None:
        raise fail(502, "provider_unavailable", "The valuation history is not available right now. Please try again in a moment.")
    out = shape_history(raw, years)
    if not out["rows"]:
        raise fail(404, "not_found", "There is no valuation history for this index.")
    feed = await _cached(request.app, "idx:feed", 900, lambda: _fetch_feed(request.app)) or {"items": []}
    name = next((x["name"] for x in feed["items"] if x["code"] == code), code)
    return Response(json.dumps({"code": code, "name": name, "years": years, **out}), media_type="application/json", headers=NO_STORE)


async def warm(app) -> None:
    """Index prices for the strip, and NIFTY 50's history, ready before the first visitor asks."""
    try:
        await _cached(app, "idx:feed", 60, lambda: _fetch_feed(app))
        await _cached(app, "idx:val:NIF50", 6 * 3600, lambda: _fetch_history(app, "NIF50"))
    except Exception:
        log.exception("index warm-up failed")
