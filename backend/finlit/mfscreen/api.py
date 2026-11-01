"""/api/mf/screen/*: small helpers of the Mutual Fund Screener panel (the list and the counts are /api/mf and /api/mf/filters?screen=1).
Included before the /api/mf router, whose /api/mf/{code} would otherwise claim these paths."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request, Response

from ..auth.routes import fail
from ..mf import cached_json

router = APIRouter(prefix="/api/mf/screen")
_SYMBOL = re.compile(r"^[A-Za-z0-9&\-]{2,20}$")


@router.get("/stocks")
async def stocks(request: Request, q: str = Query("", max_length=20)) -> Response:
    """NSE symbols that start with `q` and are held by at least one fund in the latest monthly portfolios, with how many fund families hold each.
    Feeds the "funds that hold this stock" filter. Information only."""
    term = q.strip()
    if not _SYMBOL.match(term):
        raise fail(400, "bad_request", "Type at least two letters or digits of an NSE symbol.")

    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT i.symbol, i.isin, count(DISTINCT h.fkey) AS families FROM disclosure_isin i JOIN mf_screen_hold h ON h.isin = i.isin
                   WHERE i.symbol ILIKE $1 || '%' GROUP BY 1, 2 ORDER BY 3 DESC, 1 LIMIT 10""", term)
        return {"items": [{"symbol": r["symbol"], "isin": r["isin"], "families": r["families"]} for r in rows]}
    return await cached_json(request, "screen-stocks", term.upper(), build, ttl=600)
