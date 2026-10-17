"""Read-only stock API. Every response is precomputed bytes from Redis (Postgres on a cold cache).

Latency budget per request: one Redis round trip (~0.2 ms on the same VPS) + framework overhead.
Responses carry an ETag and `stale-while-revalidate`, so Cloudflare and the browser can serve
repeat views without reaching the origin at all.
"""

from __future__ import annotations

import hashlib
import re
import time
from contextlib import asynccontextmanager
from typing import Optional

import orjson
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from .auth import routes as auth_routes
from .auth.entitlements import has, redact_section, redact_universe, varies_by_plan
from .auth.mailer import ConsoleMailer, ResendMailer
from .auth.service import current
from .config import Settings, get_settings
from .security import RateLimiter, SecurityHeadersMiddleware, client_ip
from .snapshot import PRICE_RANGES, SECTIONS
from .store import Store

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
CACHE_STOCK = "public, max-age=60, stale-while-revalidate=600"
CACHE_INDEX = "public, max-age=300, stale-while-revalidate=86400"
PUBLIC_SECTIONS = set(SECTIONS) - {"price"}  # full daily history only via ranges
UNLIMITED_PATHS = ("/api/health",)
MAX_BODY = 64 * 1024  # every request body in this API is small JSON
CACHE_PRIVATE = "private, no-cache"  # the browser keeps a copy but asks (cheap 304) every time, so a new plan shows at once


class RateLimitMiddleware:
    """Per-client request budget for every API route (health checks excluded)."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app, self.settings = app, settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http" or scope["path"].startswith(UNLIMITED_PATHS) or scope["method"] == "OPTIONS":
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
        too_big = JSONResponse({"status": "too_large", "detail": "Request is too large."}, status_code=413,
                               headers={"Cache-Control": "no-store"})
        if declared and declared.isdigit() and int(declared) > self.limit:
            return await too_big(scope, receive, send)
        seen = 0

        async def counted():
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.limit:
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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or await Store.connect(settings)
        app.state.limiter = RateLimiter(app.state.store.redis)
        app.state.settings = settings
        if settings.mail_mode == "resend" and settings.resend_api_key:
            app.state.mailer = ResendMailer(settings.resend_api_key, settings.mail_from)
        else:
            app.state.mailer = ConsoleMailer(app.state.store.pool)
        yield
        if store is None:
            await app.state.store.close()

    docs = not settings.is_production  # no public schema or Swagger UI in production
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

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # never leak internals
        return JSONResponse({"status": "error", "detail": "Something went wrong."}, status_code=500,
                            headers={"Cache-Control": "no-store"})

    def cached(request: Request, body: bytes, etag: str, cache: str, started: float) -> Response:
        timing = f"app;dur={(time.perf_counter() - started) * 1000:.2f}"
        headers = {"ETag": etag, "Cache-Control": cache, "Server-Timing": timing}
        if etag in (request.headers.get("if-none-match") or ""):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    async def missing(request: Request, symbol: str, statement: str) -> JSONResponse:
        store: Store = app.state.store
        if await store.company(symbol):
            # Each new stock costs ~21 upstream calls: cap per client and in total, failing closed.
            ip = request.scope.get("state", {}).get("client_ip") or client_ip(request.scope, settings.client_ip_header)
            allowed, retry = await app.state.limiter.hit("queue", ip, settings.queue_limit_per_hour, 3600, fail_open=False)
            if not allowed or await store.queue_length() >= settings.queue_max_pending:
                return JSONResponse({"status": "busy", "symbol": symbol, "detail": "Please try this stock again shortly."},
                                    status_code=429, headers={"Retry-After": str(retry or 60), "Cache-Control": "no-store"})
            await store.enqueue(symbol, statement)
            return JSONResponse({"status": "queued", "symbol": symbol, "detail": "Preparing this stock's report."},
                                status_code=202, headers={"Retry-After": "3", "Cache-Control": "no-store"})
        return JSONResponse({"status": "not_found", "symbol": symbol}, status_code=404, headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/health")
    async def health():
        status = await app.state.store.ping()
        ok = all(status.values())
        body = {"ok": ok} if settings.is_production else {"ok": ok, **status}  # no internals in production
        return JSONResponse(body, status_code=200 if ok else 503, headers={"Cache-Control": "no-store"})

    @app.get("/api/stocks/search-index")
    async def search_index(request: Request):
        started = time.perf_counter()
        body, packed, etag = await app.state.store.search_index()
        if "gzip" in (request.headers.get("accept-encoding") or "") and request.headers.get("if-none-match") != etag:
            response = cached(request, packed, etag, CACHE_INDEX, started)
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Vary"] = "Accept-Encoding"
            return response
        return cached(request, body, etag, CACHE_INDEX, started)

    @app.get("/api/stocks/{symbol}/price")
    async def price(request: Request, symbol: str, range: str = Query("1Y"), statement: str = Query("consolidated")):
        return await section(request, symbol, f"price-{range.upper()}", statement)

    @app.get("/api/stocks/{symbol}")
    async def summary(request: Request, symbol: str, statement: str = Query("consolidated")):
        return await section(request, symbol, "summary", statement)

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
            rows = await app.state.store.screener_rows()
            out = []
            for r in rows:
                r = {k: v for k, v in r.items() if k not in ("statement", "model", "updated_at")}
                for k, v in list(r.items()):
                    if v is not None and not isinstance(v, (int, str, bool, float)):
                        r[k] = float(v)
                out.append(r)
            out = redact_universe(out, level, set(settings.showcase_symbols))
            body = orjson.dumps({"rows": out})
            etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
            try:
                await redis.hset(f"universe:{level}", mapping={"body": body, "etag": etag})
                await redis.expire(f"universe:{level}", 180)
            except Exception:
                pass
        else:
            body, etag = hit[0], hit[1].decode()
        response = cached(request, body, etag, CACHE_PRIVATE, started)
        response.headers["Vary"] = "Cookie"
        return response

    app.include_router(auth_routes.router)
    return app

