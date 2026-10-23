"""Read-only stock API. Every response is precomputed bytes from Redis (Postgres on a cold cache).

Latency budget per request: one Redis round trip (~0.2 ms on the same VPS) + framework overhead.
Responses carry an ETag and `stale-while-revalidate`, so Cloudflare and the browser can serve
repeat views without reaching the origin at all.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from typing import Optional

import orjson
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from . import alertapi, indices, notify, premium
from .aliases import SYMBOL_ALIASES
from . import results as results_api
from .screener import api as screener_api
from .advanced import api as advanced_api
from . import compare as compare_api
from . import etf as etf_api
from . import mf as mf_api
from . import graphviews as graphviews_api
from . import forum as forum_api
from . import dcf as dcf_api
from .auth import routes as auth_routes
from .auth.entitlements import has, redact_section, redact_universe, varies_by_plan
from .auth.mailer import ConsoleMailer, ResendMailer
from .auth.service import current
from .config import Settings, get_settings
from .siteproxy import register_catch_all, register_stock_admin
from .web import mount_frontend
from .security import RateLimiter, SecurityHeadersMiddleware, client_ip
from .snapshot import PRICE_RANGES, SECTIONS, SNAPSHOT_VERSION
from .store import Store
from .background import etag_matches, spawn

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
CACHE_STOCK = "public, max-age=60, stale-while-revalidate=600"
CACHE_INDEX = "public, max-age=300, stale-while-revalidate=86400"
PUBLIC_SECTIONS = set(SECTIONS) - {"price"}  # full daily history only via ranges
UNLIMITED_PATHS = ("/api/health", "/api/ping")
LIMITED_PREFIX = "/api/"   # website files (scripts, styles, images) are not counted: one page load fetches dozens, and many mobile users share one IP
MAX_BODY = 64 * 1024  # every request body in this API is small JSON
UPLOAD_PREFIXES = ("/api/content/admin/upload", "/api/portfolio/admin/upload")  # forwarded to the site backend, which caps files at 15 MB
MAX_UPLOAD_BODY = 16 * 1024 * 1024
CACHE_PRIVATE = "private, no-cache"  # the browser keeps a copy but asks (cheap 304) every time, so a new plan shows at once


class RateLimitMiddleware:
    """Per-client request budget for every API route (health checks excluded). Website files are not counted."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or not scope["path"].startswith(LIMITED_PREFIX) or scope["path"].startswith(UNLIMITED_PATHS) or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        state = scope["app"].state
        ip = client_ip(scope, self.settings.client_ip_header)
        scope.setdefault("state", {})["client_ip"] = ip
        allowed, retry = await state.limiter.hit("api", ip, self.settings.rate_limit_per_minute, 60)
        if not allowed:
            response = JSONResponse({"status": "rate_limited", "detail": "Too many requests. Please slow down."},
                                    status_code=429, headers={"Retry-After": str(retry), "Cache-Control": "no-store"})
            return await response(scope, receive, send)
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """Reject oversized request bodies before they are parsed (declared length first, then bytes actually received)."""

    def __init__(self, app: ASGIApp, limit: int = MAX_BODY):
        self.app, self.limit = app, limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            return await self.app(scope, receive, send)
        declared = dict(scope["headers"]).get(b"content-length")
        limit = MAX_UPLOAD_BODY if scope.get("path", "").startswith(UPLOAD_PREFIXES) else self.limit
        too_big = JSONResponse({"status": "too_large", "detail": "Request is too large."}, status_code=413,
                               headers={"Cache-Control": "no-store"})
        if declared and declared.isdigit() and int(declared) > limit:
            return await too_big(scope, receive, send)
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > limit:
                    raise _TooLarge()
            return message

        try:
            await self.app(scope, counted, send)
        except _TooLarge:
            await too_big(scope, receive, send)


class _TooLarge(Exception):
    pass


def create_app(settings: Optional[Settings] = None, store: Optional[Store] = None) -> FastAPI:
    settings = settings or get_settings()
    problems = settings.validate()
    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))

    async def build_universe(level: str):
        """Build the screener list for one access level and keep it in Redis (3 minutes)."""
        rows = await app.state.store.screener_rows()
        scored = {r["symbol"] for r in rows if r.get("overall") is not None}
        rows = rows + await app.state.store.light_rows()      # every listed company, so the screener counts all of them (unscored ones carry no figures but their price)
        out = []
        for r in rows:
            r = {k: v for k, v in r.items() if k not in ("statement", "model", "updated_at")}
            r["scored"] = r["symbol"] in scored        # decided before a plan's redaction removes the score, so the page can say how many are scored
            for k, v in list(r.items()):
                if v is not None and not isinstance(v, (int, str, bool, float)):
                    r[k] = float(v)
                if isinstance(r[k], float):
                    r[k] = round(r[k], 2)   # two decimals is all any list shows; it roughly halves the download
            out.append(r)
        out = redact_universe(out, level, set(settings.showcase_symbols))
        body = orjson.dumps({"rows": out})
        etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
        try:
            await app.state.store.redis.hset(f"universe:{level}", mapping={"body": body, "etag": etag})
            await app.state.store.redis.expire(f"universe:{level}", 180)
        except Exception:
            pass
        return body, etag

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or await Store.connect(settings)
        app.state.limiter = RateLimiter(app.state.store.redis)
        app.state.settings = settings
        if settings.mail_mode == "resend" and settings.resend_api_key:
            app.state.mailer = ResendMailer(settings.resend_api_key, settings.mail_from)
        else:
            app.state.mailer = ConsoleMailer(app.state.store.pool)
        warm = asyncio.create_task(premium.warmer(app)) if settings.site_api_url and settings.cms_jwt_secret else None

        async def keep_lists_warm():
            """Search list and screener list are built once at start, so the first visitor does not wait for them. Not repeated on a timer: that would keep the free database awake all day."""
            try:
                await app.state.store.search_index()
                for level in ("basic", "silver"):
                    await build_universe(level)
                from .screener.data import get_table
                await get_table(app.state.store)
                if settings.finedge_api_key or settings.finedge_mode == "fixtures":
                    await indices.warm(app)
            except Exception:
                logging.getLogger("finlit.api").exception("list warm-up failed")

        lists = asyncio.create_task(keep_lists_warm())
        yield
        lists.cancel()
        if getattr(app.state, "index_client", None):
            await app.state.index_client.aclose()
        if warm:
            warm.cancel()
        if store is None:
            await app.state.store.close()

    docs = settings.environment == "development"  # no public schema or Swagger UI on any deployed site (staging included)
    app = FastAPI(title="FinLit API", version="0.1.0", lifespan=lifespan,
                  docs_url="/api/docs" if docs else None, redoc_url=None,
                  openapi_url="/api/openapi.json" if docs else None)
    # Last added runs first: headers wrap everything, then host check, CORS, rate limit, gzip.
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["If-None-Match", "Content-Type", "X-CSRF-Token"],
                       expose_headers=["ETag", "Server-Timing", "Retry-After"], allow_credentials=True, max_age=600)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityHeadersMiddleware)

    @app.middleware("http")
    async def retired_symbols(request: Request, call_next):
        """/api/stocks/TATAMOTORS is answered from TMPV: old links, bookmarks and saved lists keep working after a demerger or a rename."""
        parts = request.scope.get("path", "").split("/")
        if len(parts) > 3 and parts[1] == "api" and parts[2] == "stocks" and parts[3].upper() in SYMBOL_ALIASES:
            parts[3] = SYMBOL_ALIASES[parts[3].upper()]
            request.scope["path"] = "/".join(parts)
        return await call_next(request)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # never leak internals
        return JSONResponse({"status": "error", "detail": "Something went wrong."}, status_code=500,
                            headers={"Cache-Control": "no-store"})

    def cached(request: Request, body: bytes, etag: str, cache: str, started: float) -> Response:
        timing = f"app;dur={(time.perf_counter() - started) * 1000:.2f}"
        headers = {"ETag": etag, "Cache-Control": cache, "Server-Timing": timing}
        if etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    async def missing(request: Request, symbol: str, statement: str) -> JSONResponse:
        store: Store = app.state.store
        if await store.company(symbol):
            # Each new stock costs ~21 upstream calls: cap per client and in total, failing closed.
            # Already being prepared: the page asks every few seconds while it waits, and those asks must not use up the visitor's allowance.
            pending = f"pending:{symbol.upper()}:{statement}"
            try:
                first = bool(await store.redis.set(pending, 1, nx=True, ex=300))
            except Exception:
                first = True
            if not first:
                return JSONResponse({"status": "queued", "symbol": symbol, "detail": "Preparing this stock's report."},
                                    status_code=202, headers={"Retry-After": "3", "Cache-Control": "no-store"})
            ip = request.scope.get("state", {}).get("client_ip") or client_ip(request.scope, settings.client_ip_header)
            allowed, retry = await app.state.limiter.hit("queue", ip, settings.queue_limit_per_hour, 3600, fail_open=False)
            if not allowed or await store.queue_length() >= settings.queue_max_pending:
                try:
                    await store.redis.delete(pending)
                except Exception:
                    pass
                return JSONResponse({"status": "busy", "symbol": symbol, "detail": "Please try this stock again shortly."},
                                    status_code=429, headers={"Retry-After": str(min(retry or 30, 60)), "Cache-Control": "no-store"})
            await store.enqueue(symbol, statement)
            return JSONResponse({"status": "queued", "symbol": symbol, "detail": "Preparing this stock's report."},
                                status_code=202, headers={"Retry-After": "3", "Cache-Control": "no-store"})
        return JSONResponse({"status": "not_found", "symbol": symbol}, status_code=404, headers={"Cache-Control": "public, max-age=300"})

    if settings.site_api_url:
        register_stock_admin(app, settings.site_api_url)  # must come before the /api/stocks/{symbol}/{section} routes

    @app.get("/api/ping")
    async def ping():
        """Always-cheap liveness check: touches no database, so platform health checks and keep-alive pings cannot keep a metered (serverless) database awake."""
        return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})

    @app.get("/api/health")
    async def health():
        status = await app.state.store.ping()
        ok = all(status.values())
        body = {"ok": ok, **status} if settings.environment == "development" else {"ok": ok}  # no internals on any deployed site
        return JSONResponse(body, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})

    @app.get("/api/stocks/search-index")
    async def search_index(request: Request):
        started = time.perf_counter()
        body, packed, etag = await app.state.store.search_index()
        if "gzip" in (request.headers.get("accept-encoding") or "") and not etag_matches(request.headers.get("if-none-match"), etag):
            response = cached(request, packed, etag, CACHE_INDEX, started)
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Vary"] = "Accept-Encoding"
            return response
        return cached(request, body, etag, CACHE_INDEX, started)

    @app.get("/api/stocks/{symbol}/price")
    async def price(request: Request, symbol: str, range: str = Query("1Y"), statement: str = Query("consolidated")):
        return await section(request, symbol, f"price-{range.upper()}", statement)

    async def broken(symbol: str, statement: str, body: bytes) -> bool:
        """True for a stored summary that is unusable (no price) or built by older code, and a rebuild has just been queued or is under way.
        False once the rebuild has been tried and the stored report is all that exists, so a company the provider has no price for still opens."""
        try:
            meta = orjson.loads(body)
            price = (meta.get("quote") or {}).get("price")
            stale = price in (None, 0) or int((meta.get("meta") or {}).get("version") or 0) < SNAPSHOT_VERSION
        except Exception:
            return False
        if not stale:
            # A company outside the always-refreshed set that somebody opens after a day: it opens at once as it is, and is rebuilt in the background
            # (at most once an hour), so the next visit has the newest quarter.
            try:
                made = datetime.fromisoformat(str((meta.get("meta") or {}).get("generatedAt")).replace("Z", "+00:00"))
                if (datetime.now(made.tzinfo) - made).total_seconds() > 24 * 3600 and await app.state.store.redis.set(f"refresh:{symbol}:{statement}", 1, nx=True, ex=3600):
                    await app.state.store.enqueue(symbol, statement)
            except Exception:
                pass
            return False
        store, key = app.state.store, f"repair:{symbol}:{statement}"
        try:
            if await store.redis.set(key, 1, nx=True, ex=1800):     # first time in half an hour: queue the rebuild and wait for it
                await store.enqueue(symbol, statement)
                await store.redis.set(f"pending:{symbol}:{statement}", 1, ex=300)
                return price in (None, 0)
            return price in (None, 0) and bool(await store.redis.exists(f"pending:{symbol}:{statement}"))   # rebuild still running: keep waiting
        except Exception:
            return False

    @app.get("/api/stocks/{symbol}")
    async def summary(request: Request, symbol: str, statement: str = Query("consolidated")):
        if SYMBOL.match(symbol):
            spawn(app.state.store.note_view(symbol))
        sym = symbol.strip().upper()
        if SYMBOL.match(sym):
            who = await current(request)
            if who.user_id:   # a signed-in member opening a company: it is kept stored and refreshed for them from now on
                spawn(app.state.store.touch_user_company(who.user_id, sym))
        if SYMBOL.match(sym) and statement in ("consolidated", "standalone"):
            hit = await app.state.store.get_section(sym, statement, "summary")
            if hit is not None and await broken(sym, statement, hit[0]):
                # A report saved while the provider was overloaded (no price or profile) is never shown: it is rebuilt, and the page waits for it.
                return JSONResponse({"status": "queued", "symbol": sym, "detail": "Refreshing this stock's report."},
                                    status_code=202, headers={"Retry-After": "3", "Cache-Control": "no-store"})
        return await section(request, symbol, "summary", statement)

    @app.get("/api/me/companies")
    async def my_companies(request: Request):
        """The companies this member follows (watchlist, portfolio) and has opened, most recent first, and whether each is ready to open instantly."""
        who = await current(request)
        if not who.user_id:
            return JSONResponse({"status": "unauthenticated"}, status_code=401, headers={"Cache-Control": "no-store"})
        rows = await app.state.store.my_companies(who.user_id)
        return JSONResponse({"companies": rows}, headers={"Cache-Control": "private, no-store", "Vary": "Cookie"})

    @app.get("/api/stocks/{symbol}/score-history")
    async def score_history(request: Request, symbol: str, statement: str = Query("consolidated")):
        """How the FinLit score has moved (one point per day it was computed). Silver and above, like the score itself."""
        symbol = symbol.strip().upper()
        if not SYMBOL.match(symbol) or statement not in ("consolidated", "standalone"):
            return JSONResponse({"status": "invalid"}, status_code=400)
        if symbol not in settings.showcase_symbols and not has((await current(request)).plan, "silver"):
            return JSONResponse({"status": "plan_required", "plan": "silver", "detail": "Score history is part of the Silver plan."},
                                status_code=403, headers={"Cache-Control": "no-store"})
        points = await app.state.store.score_history(symbol, statement)
        return JSONResponse({"symbol": symbol, "points": points}, headers={"Cache-Control": CACHE_PRIVATE, "Vary": "Cookie"})

    @app.get("/api/stocks/{symbol}/{name}")
    async def section(request: Request, symbol: str, name: str, statement: str = Query("consolidated")):
        started = time.perf_counter()
        symbol = symbol.strip().upper()
        if not SYMBOL.match(symbol):
            return JSONResponse({"status": "invalid_symbol"}, status_code=400)
        if statement not in ("consolidated", "standalone"):
            return JSONResponse({"status": "invalid_statement"}, status_code=400)
        allowed = PUBLIC_SECTIONS | {f"price-{r}" for r in PRICE_RANGES}
        if name not in allowed:
            return JSONResponse({"status": "unknown_section", "sections": sorted(allowed)}, status_code=404)
        hit = await app.state.store.get_section(symbol, statement, name)
        if hit is None:
            return await missing(request, symbol, statement)
        if not varies_by_plan(name):
            return cached(request, hit[0], hit[1], CACHE_STOCK, started)
        # Plan-dependent: the showcase company is fully open; everything else is trimmed to the caller's plan on the server.
        plan = "gold" if symbol in settings.showcase_symbols else (await current(request)).plan
        if plan == "gold":
            response = cached(request, hit[0], hit[1], CACHE_PRIVATE, started)
        else:
            body, etag = await redacted(symbol, statement, name, plan, hit)
            response = cached(request, body, etag, CACHE_PRIVATE, started)
        response.headers["Vary"] = "Cookie"
        return response

    async def redacted(symbol: str, statement: str, name: str, plan: str, hit) -> tuple:
        etag = '"' + hashlib.sha1(f"{hit[1]}|{plan}".encode()).hexdigest()[:20] + '"'  # nosec B324 - cache key, not security
        key = f"red:{symbol}:{statement}:{name}:{plan}:{etag}"
        redis = app.state.store.redis
        try:
            body = await redis.get(key)
        except Exception:
            body = None
        if body is None:
            body = orjson.dumps(redact_section(name, orjson.loads(hit[0]), plan))
            try:
                await redis.set(key, body, ex=3600)
            except Exception:
                pass
        return body, etag

    @app.get("/api/screener/top")
    async def top(request: Request, limit: int = Query(50, ge=1, le=200)):
        if not has((await current(request)).plan, "silver"):
            return JSONResponse({"status": "plan_required", "plan": "silver", "detail": "The ranked list is part of the Silver plan."},
                                status_code=403, headers={"Cache-Control": "no-store"})
        rows = await app.state.store.top_scores(limit=limit)
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif v is not None and not isinstance(v, (int, str, bool, float)):
                    r[k] = float(v)
        return JSONResponse({"rows": rows}, headers={"Cache-Control": CACHE_PRIVATE, "Vary": "Cookie"})

    @app.get("/api/screener/universe")
    async def universe(request: Request):
        """Every scored company in one response; the website filters and compares in the browser.
        Built once per few minutes and kept in Redis, one copy per access level (model scores are a Silver feature)."""
        started = time.perf_counter()
        level = "silver" if has((await current(request)).plan, "silver") else "basic"
        redis = app.state.store.redis
        try:
            hit = await redis.hmget(f"universe:{level}", ["body", "etag"])
        except Exception:
            hit = [None, None]
        if hit[0] is None:
            body, etag = await build_universe(level)
        else:
            body, etag = hit[0], hit[1].decode()
        response = cached(request, body, etag, CACHE_PRIVATE, started)
        response.headers["Vary"] = "Cookie"
        return response

    app.include_router(auth_routes.router)
    app.include_router(alertapi.router)
    app.include_router(premium.router)
    app.include_router(indices.router)
    app.include_router(notify.router)
    app.include_router(screener_api.router)
    app.include_router(advanced_api.router)
    app.include_router(compare_api.router)
    app.include_router(etf_api.router)
    app.include_router(mf_api.router)
    app.include_router(__import__("finlit.mf_compare", fromlist=["router"]).router)   # head-to-head Fund Compare, /api/mf-compare
    app.include_router(graphviews_api.router)
    app.include_router(forum_api.router)
    app.include_router(dcf_api.router)
    app.include_router(results_api.router)
    if settings.site_api_url:
        register_catch_all(app, settings.site_api_url)  # last: everything the research API does not own
    if settings.frontend_dist:  # one container serves the website and the API (see finlit/web.py)
        mount_frontend(app, Path(settings.frontend_dist))
    return app

