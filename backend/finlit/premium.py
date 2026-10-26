"""Gold-plan market and fundamentals tools.

The data comes from the site backend's FinEdge feeds (market events, indices, commodities, raw fundamentals). Those feeds are slow on
the first call, so this gateway keeps every answer in Redis and serves it instantly: fresh for a few minutes, then "stale while
revalidate" for a day (the member gets the saved copy at once and a background call refreshes it). A warmer keeps the default views
hot, so the pages open in well under a second. Gold members and administrators only; the check is made here, not in the browser.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import re
import time
from typing import Dict, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, Query, Request, Response

from .auth.entitlements import has
from .auth.routes import NO_STORE, Ctx, fail, secure_ctx
from .background import spawn

log = logging.getLogger("finlit.premium")
router = APIRouter(prefix="/api/premium")

FRESH_SECONDS = {"markets": 300, "commodities": 900, "fundamentals": 900, "search": 3600}
STALE_SECONDS = 24 * 3600
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SECTIONS = ("ipo", "results", "announcements", "transcripts", "indices", "valuations")


async def premium_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "gold"):
        raise fail(403, "plan_required", "The market and fundamentals dashboards are part of the Gold plan.", plan="gold")
    return ctx


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def gateway_token(secret: str, ttl: int = 120, sub: str = "premium-gateway") -> str:
    """A short-lived token the site backend accepts; it never leaves this server. `sub` names who it is for (FinLit Prism binds its
    signed snapshots to it, so the PDF of a report must be asked for with the same subject)."""
    now = int(time.time())
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"sub": sub, "role": "admin", "iat": now, "exp": now + ttl}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    return f"{head}.{body}.{sig}"


def _client(app) -> httpx.AsyncClient:
    client = getattr(app.state, "premium_client", None)
    if client is None:
        client = app.state.premium_client = httpx.AsyncClient(base_url=app.state.settings.site_api_url, timeout=httpx.Timeout(45.0, connect=10.0),
                                                              limits=httpx.Limits(max_connections=12))
    return client


def _key(path: str, params: Dict[str, str]) -> str:
    raw = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
    return "prem:" + hashlib.sha1(raw.encode()).hexdigest()  # nosec B324 - cache key, not security


async def _upstream(app, path: str, params: Dict[str, str]) -> Tuple[int, bytes]:
    settings = app.state.settings
    if not settings.site_api_url or len(settings.cms_jwt_secret.encode()) < 32:
        return 503, json.dumps({"detail": "This tool is not connected yet."}).encode()
    try:
        r = await _client(app).get(path, params=params, headers={"Authorization": "Bearer " + gateway_token(settings.cms_jwt_secret)})
    except httpx.HTTPError as exc:
        log.warning("premium upstream unreachable: %s", type(exc).__name__)
        return 502, json.dumps({"detail": "The data provider is not answering. Please try again in a moment."}).encode()
    return r.status_code, r.content


async def _refresh(app, key: str, path: str, params: Dict[str, str], fresh: int) -> Optional[bytes]:
    """Fetch once even when many members ask together, and store the answer."""
    redis = app.state.store.redis
    lock = key + ":lock"
    got = await redis.set(lock, "1", nx=True, ex=50)
    if not got:
        for _ in range(100):  # someone else is fetching: wait for their answer instead of a second slow call
            await asyncio.sleep(0.3)
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)["b"].encode()
            if not await redis.exists(lock):
                break
    status, body = await _upstream(app, path, params)
    try:
        if status == 200:
            await redis.set(key, json.dumps({"t": time.time(), "f": fresh, "b": body.decode()}), ex=STALE_SECONDS)
        await redis.delete(lock)
    except Exception:
        pass
    return body if status == 200 else None


async def cached_get(request: Request, kind: str, path: str, params: Dict[str, str]) -> Response:
    app = request.app
    key, fresh = _key(path, params), FRESH_SECONDS[kind]
    redis = app.state.store.redis
    try:
        raw = await redis.get(key)
    except Exception:
        raw = None
    if raw:
        hit = json.loads(raw)
        age = time.time() - hit["t"]
        if age > fresh:
            spawn(_refresh(app, key, path, params, fresh))  # serve the saved copy now, update behind the scenes
        return Response(content=hit["b"], media_type="application/json", headers={**NO_STORE, "X-Cache": "hit" if age <= fresh else "stale", "X-Data-Age": str(int(age))})
    status, body = await _upstream(app, path, params)
    if status == 200:
        try:
            await redis.set(key, json.dumps({"t": time.time(), "f": fresh, "b": body.decode()}), ex=STALE_SECONDS)
        except Exception:
            pass
        return Response(content=body, media_type="application/json", headers={**NO_STORE, "X-Cache": "miss"})
    if status in (400, 404, 422):
        return Response(content=body, status_code=status, media_type="application/json", headers=NO_STORE)
    # Anything else (the provider refusing our key, timing out, failing) is the provider's problem, never the member's session.
    raise fail(502, "provider_unavailable", "This data is temporarily unavailable. Please try again in a moment.")


def _date(v: Optional[str]) -> Optional[str]:
    if v is None or v == "":
        return None
    if not DATE.match(v):
        raise fail(400, "bad_request", "Use dates like 2026-10-19.")
    return v


@router.get("/markets/{section}")
async def markets(request: Request, section: str, from_date: Optional[str] = None, to_date: Optional[str] = None,
                  symbol: Optional[str] = Query(None, max_length=30, pattern=r"^[A-Za-z0-9.&-]*$"),
                  index_symbol: Optional[str] = Query(None, max_length=60, pattern=r"^[A-Za-z0-9_.& -]*$"), _ctx: Ctx = Depends(premium_ctx)):
    if section not in SECTIONS:
        raise fail(404, "not_found", "Unknown market section.")
    params = {k: v for k, v in {"from_date": _date(from_date), "to_date": _date(to_date), "symbol": symbol or None, "index_symbol": index_symbol or None}.items() if v}
    return await cached_get(request, "markets", f"/api/market-data/{section}", params)


@router.get("/commodities")
async def commodities(request: Request, category: str = Query("monthly_index", pattern=r"^(monthly_index|core_infra)$"), _ctx: Ctx = Depends(premium_ctx)):
    return await cached_get(request, "commodities", "/api/commodities", {"category": category})


@router.get("/commodities/{code}")
async def commodity(request: Request, code: str, _ctx: Ctx = Depends(premium_ctx)):
    if not re.fullmatch(r"[0-9]{1,12}", code):
        raise fail(400, "bad_request", "Select a valid commodity code.")
    return await cached_get(request, "commodities", f"/api/commodities/{code}", {})


@router.get("/fundamentals/search")
async def fundamentals_search(request: Request, query: str = Query(..., min_length=2, max_length=80), _ctx: Ctx = Depends(premium_ctx)):
    return await cached_get(request, "search", "/api/stocks/admin/fundamentals/search", {"query": query.strip().lower()})


@router.get("/fundamentals/browse")
async def fundamentals_browse(request: Request, group: str = Query(..., pattern=r"^(sector|industry)$"), value: str = Query(..., min_length=1, max_length=120),
                              _ctx: Ctx = Depends(premium_ctx)):
    return await cached_get(request, "search", "/api/stocks/admin/fundamentals/browse", {"group": group, "value": value.strip()})


@router.get("/fundamentals")
async def fundamentals(request: Request, query: str = Query(..., min_length=2, max_length=80),
                       statement_type: str = Query("consolidated", pattern=r"^(consolidated|standalone)$"),
                       period: str = Query("yearly", pattern=r"^(yearly|quarterly)$"), _ctx: Ctx = Depends(premium_ctx)):
    return await cached_get(request, "fundamentals", "/api/stocks/admin/fundamentals", {"query": query.strip(), "statement_type": statement_type, "period": period})


WARM = [("/api/market-data/ipo", {}), ("/api/market-data/results", {}), ("/api/market-data/announcements", {}), ("/api/market-data/transcripts", {}),
        ("/api/market-data/indices", {}), ("/api/commodities", {"category": "monthly_index"}), ("/api/commodities", {"category": "core_infra"})]


async def warmer(app, every: int = 240) -> None:
    """Keep the default dashboard views fresh so the first member of the day does not wait on the data provider."""
    await asyncio.sleep(20)
    while True:
        for path, params in WARM:
            try:
                key = _key(path, params)
                kind = "commodities" if "commodities" in path else "markets"
                raw = await app.state.store.redis.get(key)
                if not raw or time.time() - json.loads(raw)["t"] > FRESH_SECONDS[kind] * 0.6:
                    await _refresh(app, key, path, params, FRESH_SECONDS[kind])
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("premium warm-up skipped %s: %s", path, type(exc).__name__)
            await asyncio.sleep(2)
        await asyncio.sleep(every)
