"""Market structure for the dashboard heat-maps: which listed companies belong to which index, from the exchange's published constituent lists that
the nightly `refresh-indices` job stores (screener/jobs.py). Public; one saved copy serves everyone. A list that has not been loaded is simply absent, and
the page then says it is grouping companies by FinLit's own sector classification instead."""
from __future__ import annotations

import json
import time

from fastapi import APIRouter, Request
from fastapi.responses import Response

router = APIRouter(prefix="/api/markets")
KEY, TTL = "markets:members", 3600


@router.get("/members")
async def members(request: Request) -> Response:
    store = request.app.state.store
    try:
        raw = await store.redis.get(KEY)
    except Exception:
        raw = None
    if raw is None:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT index_code, symbol FROM index_members ORDER BY index_code, symbol")
        out: dict = {}
        for r in rows:
            out.setdefault(r["index_code"], []).append(r["symbol"])
        raw = json.dumps({"indices": out, "builtAt": int(time.time())}, separators=(",", ":"))
        try:
            await store.redis.set(KEY, raw, ex=TTL)
        except Exception:   # nosec B110 - cache only
            pass
    body = raw if isinstance(raw, str) else raw.decode()
    return Response(content=body, media_type="application/json", headers={"Cache-Control": "public, max-age=600, stale-while-revalidate=3600"})
