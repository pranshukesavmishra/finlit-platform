"""Leader / In line / Laggard on the stock page.

    GET /api/stocks/{symbol}/leadership           the label, the numbers behind it, the wording, the reliability card and the peers
    GET /api/stocks/{symbol}/leadership-history   one row per weekly run, plus weekly closes of the stock and both benchmarks

Everything is read from tables the weekly job fills (finlit/leadership.py), so a page view costs one or two indexed reads. Open to every visitor:
the label describes past price performance and is never a recommendation. Registered before the generic /api/stocks/{symbol}/{section} route.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import orjson
from fastapi import APIRouter, Query, Request, Response

from . import indices
from .background import etag_matches
from .leadership import STALE_AFTER_RUNS, Prices, display, reliability_sentence
from .store import Store

router = APIRouter()
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
CACHE = "public, max-age=900, stale-while-revalidate=3600"
STATEMENTS = ("consolidated", "standalone")


def _f(x: Any) -> Optional[float]:
    return None if x is None else round(float(x), 6)


def _day(d: Any) -> Optional[str]:
    return d.isoformat() if d else None


def _reply(request: Request, payload: Dict[str, Any], started: float) -> Response:
    body = orjson.dumps(payload)
    etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
    headers = {"ETag": etag, "Cache-Control": CACHE, "Server-Timing": f"app;dur={(time.perf_counter() - started) * 1000:.2f}"}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


def _bad(status: str, code: int = 400) -> Response:
    return Response(content=orjson.dumps({"status": status}), media_type="application/json", status_code=code, headers={"Cache-Control": "no-store"})


def shape_reliability(row: Optional[dict]) -> Dict[str, Any]:
    """The reliability object of the spec from a `sector_reliability` row; a missing row is the same as 'insufficient'."""
    if not row:
        return {"tier": "insufficient", "hitRate6m": None, "checks": 0, "from": None, "to": None, "periods": []}
    periods = row["periods"]
    periods = json.loads(periods) if isinstance(periods, str) else (periods or [])
    return {"tier": row["tier"], "hitRate6m": _f(row["hit_rate"]), "checks": row["checks"], "from": _day(row["window_start"])[:7] if row["window_start"] else None,
            "to": _day(row["window_end"])[:7] if row["window_end"] else None, "periods": periods}


def shape(row: dict, rel: Optional[dict], peers: List[dict]) -> Dict[str, Any]:
    """The `leadership` object for a stock that has a label."""
    stale = (row["stale_runs"] or 0) >= STALE_AFTER_RUNS
    shown = display(label=row["label"], rank=row["rank"], ranked=row["ranked"], group_short=row["group_short"] or row["group_name"] or "",
                    sector_name=row["sector_name"] or "its peers", market_name=row["market_name"], rel52=_f(row["rel52"]), rel52_market=_f(row["rel52_market"]),
                    direction=row["direction"], fundamental=row["fundamental"], fund_rank=row["fund_rank"], fund_n=row["fund_n"])
    if row["sector_kind"] == "peer_average":
        shown["tooltip"] = (shown["tooltip"] or "").replace(f" and {row['sector_name']}", " and the average of those peers")
        shown["benchmarkNote"] = "There is no matching sector index, so the average return of the peers stands in for it."
    reliability = shape_reliability(rel)
    reliability["sentence"] = reliability_sentence(row["group_name"] or "this group", reliability)
    return {
        "available": True, "asOf": _day(row["as_of"]), "stale": stale, "held": bool(row["held"]),
        "peerGroup": {"id": row["group_id"], "name": row["group_name"], "short": row["group_short"], "kind": row["group_kind"], "ranked": row["ranked"]},
        "benchmarks": {"sector": {"code": row["sector_code"], "name": row["sector_name"], "kind": row["sector_kind"], "ret52": _f(row["sector_ret52"])},
                       "market": {"code": row["market_code"], "name": row["market_name"], "ret52": _f(row["market_ret52"])} if row["market_code"] else None},
        "rel": {"w13": _f(row["rel13"]), "w26": _f(row["rel26"]), "w52": _f(row["rel52"]), "w52Market": _f(row["rel52_market"])},
        "rank": row["rank"], "label": row["label"], "rawLabel": row["raw_label"], "direction": row["direction"],
        "fundamentalNote": row["fundamental"], "fundamentalRank": row["fund_rank"], "fundamentalOf": row["fund_n"], "labelSince": _day(row["label_since"]),
        "sectorReliability": reliability, "display": shown, "peers": peers,
    }


@router.get("/api/stocks/{symbol}/leadership")
async def leadership(request: Request, symbol: str) -> Response:
    started = time.perf_counter()
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        return _bad("invalid_symbol")
    store: Store = request.app.state.store
    async with store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM leadership WHERE symbol = $1", symbol)
        if row is None:
            why = await conn.fetchval("SELECT reason FROM leadership_excluded WHERE symbol = $1", symbol) or "history"
            return _reply(request, {"available": False, "reason": why, "display": display(label=None, rank=None, ranked=None, group_short="", sector_name="",
                                                                                           market_name=None, rel52=None, rel52_market=None, direction=None,
                                                                                           fundamental=None, fund_rank=None, fund_n=None, reason=why)}, started)
        rel = await conn.fetchrow("SELECT * FROM sector_reliability WHERE group_id = $1", row["group_id"])
        peer_rows = await conn.fetch("SELECT symbol, name, rank, label, direction, rel13, rel52, rel52_market, market_cap FROM leadership WHERE group_id = $1 AND as_of = $2 "
                                     "ORDER BY rank", row["group_id"], row["as_of"])
    peers = [{"symbol": p["symbol"], "name": p["name"], "rank": p["rank"], "label": p["label"], "direction": p["direction"], "rel13": _f(p["rel13"]),
              "rel52": _f(p["rel52"]), "rel52Market": _f(p["rel52_market"]), "marketCap": _f(p["market_cap"])} for p in peer_rows]
    return _reply(request, shape(dict(row), dict(rel) if rel else None, peers), started)


def _rebased(p: Prices, days: List[date]) -> List[Optional[float]]:
    """The series on the given days, rebased to 100 at its first available day (index levels are daily; stock bars are weekly)."""
    vals = [p.close_on(d) for d in days]
    first = next((v for v in vals if v is not None), None)
    return [None if v is None or first is None else round(v / first * 100, 3) for v in vals]


async def _levels(request: Request, code: Optional[str]) -> Optional[Prices]:
    if not code:
        return None
    try:
        raw = await indices._cached(request.app, f"idx:px:{code}", 6 * 3600, lambda: indices._fetch_levels(request.app, code))
        rows = indices.shape_levels(raw, indices.HISTORY_YEARS)["rows"]
    except Exception:
        return None
    p = Prices([r["d"] for r in rows], [r["c"] for r in rows])
    return p if len(p) else None


@router.get("/api/stocks/{symbol}/leadership-history")
async def leadership_history(request: Request, symbol: str, statement: str = Query("consolidated")) -> Response:
    started = time.perf_counter()
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        return _bad("invalid_symbol")
    if statement not in STATEMENTS:
        return _bad("invalid_statement")
    store: Store = request.app.state.store
    async with store.pool.acquire() as conn:
        now = await conn.fetchrow("SELECT sector_code, sector_kind, market_code FROM leadership WHERE symbol = $1", symbol)
        runs = await conn.fetch("SELECT run_date, rank, ranked, label, direction, rel52, rel52_market FROM leadership_history WHERE symbol = $1 ORDER BY run_date", symbol)
    if now is None or not runs:
        return _reply(request, {"available": False, "rows": [], "series": None}, started)
    rows = [{"date": r["run_date"].isoformat(), "rank": r["rank"], "ranked": r["ranked"], "label": r["label"], "direction": r["direction"],
             "rel52": _f(r["rel52"]), "rel52Market": _f(r["rel52_market"])} for r in runs]
    series = None
    hit = await store.get_section(symbol, statement, "price-MAX")
    if hit is not None:
        try:
            s = (json.loads(hit[0]).get("series") or {})
            stock = Prices(s.get("t") or [], s.get("c") or [])
        except (ValueError, TypeError):
            stock = Prices([], [])
        if len(stock):
            cut = stock.dates[-1] - timedelta(days=365 * 5 + 7)
            days = [d for d in stock.dates if d >= cut]
            sector = await _levels(request, now["sector_code"] if now["sector_kind"] == "index" else None)
            market = await _levels(request, now["market_code"])
            series = {"dates": [d.isoformat() for d in days], "stock": _rebased(stock, days), "sector": _rebased(sector, days) if sector else None,
                      "market": _rebased(market, days) if market else None}
    return _reply(request, {"available": True, "rows": rows, "series": series}, started)
