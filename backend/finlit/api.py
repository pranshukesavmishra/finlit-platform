"""Read-only stock API. Every response is precomputed bytes from Redis (Postgres on a cold cache).

Latency budget per request: one Redis round trip (~0.2 ms on the same VPS) + framework overhead.
Responses carry an ETag and `stale-while-revalidate`, so Cloudflare and the browser can serve
repeat views without reaching the origin at all.
"""

from __future__ import annotations

import re
import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, Response

from .config import Settings, get_settings
from .snapshot import PRICE_RANGES, SECTIONS
from .store import Store

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
CACHE_STOCK = "public, max-age=60, stale-while-revalidate=600"
CACHE_INDEX = "public, max-age=300, stale-while-revalidate=86400"
PUBLIC_SECTIONS = set(SECTIONS) - {"price"}  # full daily history only via ranges


def create_app(settings: Optional[Settings] = None, store: Optional[Store] = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or await Store.connect(settings)
        yield
        if store is None:
            await app.state.store.close()

    app = FastAPI(title="FinLit API", version="0.1.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=5)
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"],
                       allow_headers=["If-None-Match"], expose_headers=["ETag", "Server-Timing"])

    def cached(request: Request, body: bytes, etag: str, cache: str, started: float) -> Response:
        timing = f"app;dur={(time.perf_counter() - started) * 1000:.2f}"
        headers = {"ETag": etag, "Cache-Control": cache, "Server-Timing": timing}
        if etag in (request.headers.get("if-none-match") or ""):
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    async def missing(symbol: str, statement: str) -> JSONResponse:
        store: Store = app.state.store
        if await store.company(symbol):
            await store.enqueue(symbol, statement)
            return JSONResponse({"status": "queued", "symbol": symbol, "detail": "Preparing this stock's report."},
                                status_code=202, headers={"Retry-After": "3", "Cache-Control": "no-store"})
        return JSONResponse({"status": "not_found", "symbol": symbol}, status_code=404, headers={"Cache-Control": "public, max-age=300"})

    @app.get("/api/health")
    async def health():
        status = await app.state.store.ping()
        return JSONResponse({"ok": all(status.values()), **status}, status_code=200 if all(status.values()) else 503,
                            headers={"Cache-Control": "no-store"})

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
            return await missing(symbol, statement)
        return cached(request, hit[0], hit[1], CACHE_STOCK, started)

    @app.get("/api/screener/top")
    async def top(limit: int = Query(50, ge=1, le=200)):
        rows = await app.state.store.top_scores(limit=limit)
        for r in rows:
            for k, v in list(r.items()):
                if hasattr(v, "isoformat"):
                    r[k] = v.isoformat()
                elif v is not None and not isinstance(v, (int, str, bool, float)):
                    r[k] = float(v)
        return JSONResponse({"rows": rows}, headers={"Cache-Control": CACHE_STOCK})

    return app

