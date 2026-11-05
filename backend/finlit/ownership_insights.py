"""Ownership insights for the company page (docs/OWNERSHIP.md).

    GET /api/stocks/{symbol}/ownership-insights    the stored output of finlit_technicals.ownership.analyse() for the company

The analysis is a pure function of a "pack": the quarterly shareholding the site already stores (the `ownership` section) plus, when we have it,
the premium fundamentals' ownership structure (share count, pledge, lock-in, shareholders) and named holders of 1% or more. The premium call is slow
(40 s or more for a company it has not cached), so it is made ONLY by the nightly job (`refresh-ownership`, bounded concurrency and time) and the
answer is kept; the page reads the stored row and never waits for it.

A page opened before its row exists is never left empty: the API builds the row at once from the stored shareholding (no premium part: the section
shows why "Also from the filing" is missing), saves it, and queues the company for the job's premium pass (`ownership:wanted`).
Registered before the generic /api/stocks/{symbol}/{section} route.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
import orjson
from fastapi import APIRouter, Query, Request, Response

from .background import etag_matches, spawn
from .premium import gateway_token
from .store import Store

log = logging.getLogger("finlit.ownership")
router = APIRouter()
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
STATEMENTS = ("consolidated", "standalone")
CACHE = "public, max-age=300, stale-while-revalidate=1800"
WANTED = "ownership:wanted"          # Redis sorted set: companies a visitor opened that have no premium part yet (score = when)
WANTED_MAX = 3000
RETRY_HOURS = 6.0                    # a premium call that failed is tried again after this long
REFRESH_DAYS = 25.0                  # the premium figures (pledge, lock-in, shareholders, named holders) change with each quarterly filing

# The reasons the page shows when "Also from the filing" is missing (every blank says why).
REASON_PENDING = "These details come from the data provider and are fetched overnight for each company; they appear here after the next run."
REASON_NOT_CONNECTED = "The data provider connection for these details is not set up on this server."
REASON_NONE = "The data provider has no shareholder, pledge, share-count or lock-in figures for this company."
REASON_FAILED = "The data provider did not answer the last time we asked; it is tried again automatically."


# ---------------------------------------------------------------------------------------------- the pure part
def _ownership():
    from finlit_technicals import ownership
    return ownership


def parse_body(raw: Any) -> Optional[dict]:
    """The stored `ownership` section as a dict, or None when it holds no quarters."""
    try:
        body = orjson.loads(raw) if isinstance(raw, (bytes, str)) else raw
    except Exception:
        return None
    if not isinstance(body, dict) or not body.get("periods") or not isinstance(body.get("series"), dict):
        return None
    return body


def latest_period(body: dict) -> Optional[str]:
    periods = body.get("periods") or []
    return periods[-1] if periods else None


def extra_from_premium(symbol: str, ownership_body: dict, premium: Optional[dict]) -> Optional[dict]:
    """The part of the premium fundamentals answer the analysis uses: {"structure": {...}, "holders": [...]}, or None when it holds neither."""
    if not isinstance(premium, dict):
        return None
    pack = _ownership().pack_from_site(ownership_body, premium, symbol)
    st = pack.get("structure") or {}
    has_structure = bool(st.get("periods")) and any(k != "periods" and any(v is not None for v in vals) for k, vals in st.items())
    holders = pack.get("holders") or []
    if not has_structure and not holders:
        return None
    return {"structure": st if has_structure else {}, "holders": holders}


def build_view(symbol: str, ownership_body: dict, extra: Optional[dict]) -> dict:
    """analyse() of the stored shareholding plus the premium part when there is one."""
    o = _ownership()
    pack = o.pack_from_site(ownership_body, None, symbol)
    if extra:
        if extra.get("structure"):
            pack["structure"] = extra["structure"]
        pack["holders"] = extra.get("holders") or []
    return o.analyse(pack)


def premium_block(state: str, reason: Optional[str], extra: Optional[dict]) -> Dict[str, Any]:
    return {"state": state, "reason": None if state == "ok" else reason,
            "has": {"structure": bool(extra and extra.get("structure")), "holders": bool(extra and extra.get("holders"))}}


def finish(view: dict, state: str, reason: Optional[str], extra: Optional[dict]) -> dict:
    """The JSON the page reads: the analysis plus where its premium part stands."""
    return {**view, "premium": premium_block(state, reason, extra)}


# ---------------------------------------------------------------------------------------------- storage
async def load_row(store: Store, symbol: str, statement: str) -> Optional[dict]:
    async with store.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT as_of, body::text AS body, extra::text AS extra, premium_state, premium_reason, premium_at, premium_tried_at, built_at "
                                "FROM ownership_insights WHERE symbol = $1 AND statement = $2", symbol, statement)
    if not r:
        return None
    return {"as_of": r["as_of"], "body": json.loads(r["body"]), "extra": json.loads(r["extra"]) if r["extra"] else None, "premium_state": r["premium_state"],
            "premium_reason": r["premium_reason"], "premium_at": r["premium_at"], "premium_tried_at": r["premium_tried_at"], "built_at": r["built_at"]}


async def save_row(conn, symbol: str, statement: str, view: dict, extra: Optional[dict], state: str, reason: Optional[str],
                   *, premium_ok: bool = False, tried: bool = False, replace: bool = True) -> None:
    """Insert or replace the row. `premium_ok`: the premium call just succeeded; `tried`: it was just attempted. replace=False only adds a missing row."""
    now = datetime.now(timezone.utc)
    body = finish({k: v for k, v in view.items() if k != "premium"}, state, reason, extra)
    sql = ("INSERT INTO ownership_insights(symbol, statement, as_of, rules_version, body, extra, premium_state, premium_reason, premium_at, premium_tried_at, built_at) "
           "VALUES($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11) ")
    if replace:
        sql += ("ON CONFLICT (symbol, statement) DO UPDATE SET as_of = EXCLUDED.as_of, rules_version = EXCLUDED.rules_version, body = EXCLUDED.body, extra = EXCLUDED.extra, "
                "premium_state = EXCLUDED.premium_state, premium_reason = EXCLUDED.premium_reason, "
                "premium_at = COALESCE(EXCLUDED.premium_at, ownership_insights.premium_at), premium_tried_at = COALESCE(EXCLUDED.premium_tried_at, ownership_insights.premium_tried_at), "
                "built_at = EXCLUDED.built_at")
    else:
        sql += "ON CONFLICT (symbol, statement) DO NOTHING"
    await conn.execute(sql, symbol, statement, view.get("as_of"), view.get("rules_version") or "", json.dumps(body, ensure_ascii=False),
                       json.dumps(extra, ensure_ascii=False) if extra else None, state, reason, now if premium_ok else None, now if tried else None, now)


async def mark_wanted(store: Store, symbol: str) -> None:
    try:
        if await store.redis.zcard(WANTED) < WANTED_MAX:
            await store.redis.zadd(WANTED, {symbol: time.time()}, nx=True)
    except Exception:   # nosec B110 - the queue is a convenience: the nightly run reaches every company anyway
        pass


# ---------------------------------------------------------------------------------------------- the API
def _reply(request: Request, payload: Dict[str, Any], started: float, status: int = 200, cache: str = CACHE) -> Response:
    body = orjson.dumps(payload)
    etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
    headers = {"ETag": etag, "Cache-Control": cache, "Server-Timing": f"app;dur={(time.perf_counter() - started) * 1000:.2f}"}
    if status == 200 and etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", status_code=status, headers=headers)


def from_row(row: dict) -> Dict[str, Any]:
    """The stored body with its premium block read from the row's own columns (the job may have changed the reason since the body was written)."""
    return {**row["body"], "premium": premium_block(row["premium_state"], row["premium_reason"], row["extra"])}


def served(row_or_view: Dict[str, Any], built_at: Optional[datetime], stored: bool) -> Dict[str, Any]:
    return {"available": True, **row_or_view, "builtAt": built_at.isoformat(timespec="seconds") if built_at else None, "stored": stored}


async def insights_for(store: Store, symbol: str, statement: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """(payload, reason). Reads the stored row; when the stored shareholding has a newer filing than the row, or no row exists, builds from the stored
    shareholding (and the kept premium part) at once. The second item is why there is nothing to show."""
    row = await load_row(store, symbol, statement)
    hit = await store.get_section(symbol, statement, "ownership")
    own = parse_body(hit[0]) if hit else None
    if own is None:
        if row:   # the shareholding block is gone but the analysis is kept: show it
            return served(from_row(row), row["built_at"], True), None
        return None, "The shareholding filings for this company have not been loaded yet."
    if row and row["as_of"] == latest_period(own):
        return served(from_row(row), row["built_at"], True), None
    extra = row["extra"] if row else None
    view = build_view(symbol, own, extra)
    state = row["premium_state"] if row else "missing"
    reason = (row["premium_reason"] if row else None) or REASON_PENDING
    payload = finish({k: v for k, v in view.items() if k != "premium"}, state, reason, extra)
    if not row:
        try:   # the first look at this company: keep the row so the next visitor reads it, and queue the premium part
            async with store.pool.acquire() as conn:
                await save_row(conn, symbol, statement, view, None, "missing", REASON_PENDING, replace=False)
        except Exception as exc:
            log.warning("ownership insights for %s not kept: %s", symbol, type(exc).__name__)
    if state != "ok" or row:
        await mark_wanted(store, symbol)
    return served(payload, datetime.now(timezone.utc), bool(row)), None


@router.get("/api/stocks/{symbol}/ownership-insights")
async def ownership_insights(request: Request, symbol: str, statement: str = Query("consolidated")) -> Response:
    started = time.perf_counter()
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        return _reply(request, {"status": "invalid_symbol"}, started, 400, "no-store")
    if statement not in STATEMENTS:
        return _reply(request, {"status": "invalid_statement"}, started, 400, "no-store")
    store: Store = request.app.state.store
    payload, reason = await insights_for(store, symbol, statement)
    if payload is None:
        return _reply(request, {"available": False, "symbol": symbol, "reason": reason}, started, 404, "no-store")
    return _reply(request, payload, started)


# ---------------------------------------------------------------------------------------------- the premium call (job only)
def connected(settings) -> bool:
    return bool(settings.site_api_url) and len(settings.cms_jwt_secret.encode()) >= 32


async def fetch_premium(client: httpx.AsyncClient, settings, symbol: str, statement: str) -> Tuple[Optional[dict], Optional[str]]:
    """The premium fundamentals answer for one company (40 s or more when the site has not cached it). (None, reason) when it cannot be had."""
    try:
        r = await client.get("/api/stocks/admin/fundamentals", params={"query": symbol, "statement_type": statement, "period": "yearly"},
                             headers={"Authorization": "Bearer " + gateway_token(settings.cms_jwt_secret, ttl=300)})
    except httpx.HTTPError as exc:
        return None, f"{REASON_FAILED} ({type(exc).__name__})"
    if r.status_code in (404, 422):
        return None, REASON_NONE
    if r.status_code != 200:
        return None, f"{REASON_FAILED} (HTTP {r.status_code})"
    try:
        return r.json(), None
    except ValueError:
        return None, REASON_FAILED


async def rebuild_one(store: Store, conn, symbol: str, statement: str, own: dict, row: Optional[dict], premium: Optional[dict], fail: Optional[str]) -> str:
    """Analyse one company and store the row. Returns what happened: ok | none | failed | rebuilt."""
    extra = row["extra"] if row else None
    if premium is not None:
        fresh = extra_from_premium(symbol, own, premium)
        if fresh:
            view = build_view(symbol, own, fresh)
            await save_row(conn, symbol, statement, view, fresh, "ok", None, premium_ok=True, tried=True)
            return "ok"
        view = build_view(symbol, own, extra)
        await save_row(conn, symbol, statement, view, extra, "ok" if extra else "missing", None if extra else REASON_NONE, tried=True)
        return "none"
    view = build_view(symbol, own, extra)
    state = row["premium_state"] if row else "missing"
    if fail:
        await save_row(conn, symbol, statement, view, extra, state, fail, tried=True)
        return "failed"
    await save_row(conn, symbol, statement, view, extra, state, (row["premium_reason"] if row else None) or REASON_PENDING)
    return "rebuilt"


def due_for_premium(row: Optional[dict], latest: Optional[str], now: datetime) -> Optional[int]:
    """None when the premium part of this company is current; else a rank (lower first): 0 never fetched, 1 a newer filing than the kept figures, 2 older than REFRESH_DAYS."""
    if row is None:
        return 0
    tried = row["premium_tried_at"]
    if tried and (now - tried).total_seconds() < RETRY_HOURS * 3600 and row["premium_state"] != "ok" and row["as_of"] == latest:
        return None
    if row["premium_state"] != "ok":
        return 0
    at = row["premium_at"]
    if row["as_of"] != latest:
        return 1
    if at is None or (now - at).total_seconds() > REFRESH_DAYS * 86400:
        return 2
    return None


async def refresh(store: Store, settings, *, max_minutes: float = 20.0, limit: int = 120, concurrency: int = 3, symbols: Optional[List[str]] = None,
                  statement: str = "consolidated", client: Optional[httpx.AsyncClient] = None) -> Dict[str, Any]:
    """The nightly run. Pass 1 (database only): every stored company gets a row, and a row older than the stored shareholding is built again.
    Pass 2: the premium call for the companies whose premium part is missing or old (visitors' companies first), at most `limit`, `concurrency` at a time,
    nothing new started after `max_minutes`. Resumable: a company is picked by what is missing, so the next run continues."""
    started = time.monotonic()
    deadline = started + max_minutes * 60
    now = datetime.now(timezone.utc)
    stats: Dict[str, Any] = {"companies": 0, "built": 0, "rebuilt": 0, "premium_ok": 0, "premium_none": 0, "premium_failed": 0, "left": 0, "premium": "connected"}
    todo: List[Tuple[int, float, str]] = []
    wanted: Dict[str, float] = {}
    try:
        wanted = {(m.decode() if isinstance(m, bytes) else m): s for m, s in await store.redis.zrange(WANTED, 0, -1, withscores=True)}
    except Exception:   # nosec B110
        pass
    last = ""
    while True:
        async with store.pool.acquire() as conn:
            if symbols:
                if last:
                    break
                rows = await conn.fetch("SELECT s.symbol, s.body FROM snapshots s WHERE s.section = 'ownership' AND s.statement = $1 AND s.symbol = ANY($2::text[]) ORDER BY s.symbol", statement, symbols)
            else:
                rows = await conn.fetch("SELECT s.symbol, s.body FROM snapshots s WHERE s.section = 'ownership' AND s.statement = $1 AND s.symbol > $2 ORDER BY s.symbol LIMIT 200", statement, last)
            if not rows:
                break
            existing = {r["symbol"]: r for r in await conn.fetch(
                "SELECT symbol, as_of, extra::text AS extra, premium_state, premium_reason, premium_at, premium_tried_at FROM ownership_insights WHERE statement = $1 AND symbol = ANY($2::text[])",
                statement, [r["symbol"] for r in rows])}
            for r in rows:
                sym = r["symbol"]
                last = sym
                own = parse_body(r["body"])
                if own is None:
                    continue
                stats["companies"] += 1
                e = existing.get(sym)
                row = None if e is None else {"as_of": e["as_of"], "extra": json.loads(e["extra"]) if e["extra"] else None, "premium_state": e["premium_state"],
                                              "premium_reason": e["premium_reason"], "premium_at": e["premium_at"], "premium_tried_at": e["premium_tried_at"]}
                latest = latest_period(own)
                rank = due_for_premium(row, latest, now)      # judged on the row as it was, before this pass rebuilds it
                try:
                    if row is None or row["as_of"] != latest:
                        await rebuild_one(store, conn, sym, statement, own, row, None, None)
                        stats["built" if row is None else "rebuilt"] += 1
                except Exception as exc:
                    log.warning("ownership insights for %s failed: %s: %s", sym, type(exc).__name__, exc)
                    continue
                if rank is not None:
                    todo.append((0 if sym in wanted else 1, rank, sym))
        if symbols:
            break
    todo.sort(key=lambda t: (t[0], t[1], t[2]))
    pending = [sym for _, _, sym in todo]
    if not connected(settings):
        stats.update(premium="not_connected", left=len(pending))
        async with store.pool.acquire() as conn:
            await conn.execute("UPDATE ownership_insights SET premium_reason = $1 WHERE premium_state = 'missing' AND premium_reason IS DISTINCT FROM $1 AND statement = $2",
                               REASON_NOT_CONNECTED, statement)
        return {"status": "ok", **stats}
    own_client = client is None
    client = client or httpx.AsyncClient(base_url=settings.site_api_url, timeout=httpx.Timeout(100.0, connect=10.0), limits=httpx.Limits(max_connections=concurrency))
    gate = asyncio.Semaphore(max(1, concurrency))
    batch = pending[:max(0, limit)]
    done = {"n": 0}

    async def one(sym: str) -> None:
        async with gate:
            if time.monotonic() > deadline:
                return
            premium, fail = await fetch_premium(client, settings, sym, statement)
            async with store.pool.acquire() as conn:
                hit = await conn.fetchrow("SELECT body FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = 'ownership'", sym, statement)
                own = parse_body(hit["body"]) if hit else None
                if own is None:
                    return
                row = await load_row(store, sym, statement)
                out = await rebuild_one(store, conn, sym, statement, own, row, premium, fail)
            done["n"] += 1
            stats["premium_" + out] = stats.get("premium_" + out, 0) + 1
            try:
                await store.redis.zrem(WANTED, sym)
            except Exception:   # nosec B110
                pass

    try:
        await asyncio.gather(*(one(s) for s in batch), return_exceptions=True)
    finally:
        if own_client:
            await client.aclose()
    stats["left"] = max(0, len(pending) - done["n"])
    stats["status"] = "ok" if time.monotonic() <= deadline else "partial"
    stats["seconds"] = round(time.monotonic() - started, 1)
    return stats
