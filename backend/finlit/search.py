"""Data for the site-wide search box beyond names: today's price and change, the score and band, and the logo of every company,
plus the fund-house logos for fund and ETF results.

The name list itself stays `/api/stocks/search-index` (public, cached for long, read by several tools). This payload is separate because
it changes every minute in market hours and because scores are a Silver feature: a Basic visitor gets "locked" instead of a score
(the free showcase company stays open), so the response is private and varies by cookie, built once per access level and kept in Redis.

Rows: [symbol, price, change %, price date (YYYY-MM-DD, India), score or null, band key or null or "locked", logo path or null].
Price and change come from the company's stored report when that is fresher (updated every minute in market hours), otherwise from the
nightly market-wide listing; the date always travels with the price, so an old close is never shown as today's move.
"""
from __future__ import annotations

import gzip
import time
from datetime import timezone, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import Response

from .auth.entitlements import has
from .auth.service import current
from .background import etag_matches
from .logos import AMC_SITES, amc_logos, logo_path
from .store import dumps, etag_for

router = APIRouter(prefix="/api/search")
IST = timezone(timedelta(hours=5, minutes=30))
TTL = 120
CACHE = "private, no-cache"

QUOTES_SQL = """
SELECT c.symbol, s.overall, s.band, s.price AS sp, s.change_pct AS sc, s.updated_at AS su,
       q.price AS qp, q.change_pct AS qc, coalesce(q.traded_at, q.updated_at) AS qt, g.sha8
FROM companies c
LEFT JOIN LATERAL (SELECT overall, band, price, change_pct, updated_at FROM scores
                   WHERE symbol = c.symbol AND model = 'v1' ORDER BY (statement = 'consolidated') DESC, updated_at DESC LIMIT 1) s ON true
LEFT JOIN listing_quotes q ON q.symbol = c.symbol
LEFT JOIN logos g ON g.owner_kind = 'stock' AND g.owner_key = c.symbol AND g.status IN ('ok', 'manual') AND g.sha8 IS NOT NULL
"""


def _num(v):
    return None if v is None else round(float(v), 2)


def quote_rows(rows, level: str, showcase: set) -> list:
    """The compact rows above. Basic: scores are blanked to "locked" except for the showcase companies."""
    out = []
    for r in rows:
        use_report = r["sp"] is not None and (r["qp"] is None or r["qt"] is None or (r["su"] and r["su"] >= r["qt"]))
        price, chg, at = (r["sp"], r["sc"], r["su"]) if use_report else (r["qp"], r["qc"], r["qt"])
        score, band = r["overall"], r["band"]
        if score is not None and not has(level, "silver") and r["symbol"] not in showcase:
            score, band = None, "locked"
        logo = logo_path(r["sha8"])
        if price is None and score is None and band is None and logo is None:
            continue                                   # nothing to add to the name list
        out.append([r["symbol"], _num(price), _num(chg), at.astimezone(IST).date().isoformat() if at and price is not None else None,
                    score, band, logo])
    return out


async def build(app, level: str):
    store = app.state.store
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(QUOTES_SQL)
    amc = await amc_logos(store)
    body = dumps({"fields": ["symbol", "price", "changePct", "priceDate", "score", "band", "logo"],
                  "rows": quote_rows(rows, level, set(app.state.settings.showcase_symbols)),
                  "amcLogos": {k: logo_path(v) for k, v in amc.items() if k in AMC_SITES},
                  "level": level, "builtAt": int(time.time())})
    packed = gzip.compress(body, compresslevel=6, mtime=0)
    etag = etag_for(body)
    try:
        key = f"search-quotes:{level}"
        await store.redis.hset(key, mapping={"body": body, "gzip": packed, "etag": etag.encode()})
        await store.redis.expire(key, TTL)
    except Exception:   # nosec B110 - Redis down: serve what was just built
        pass
    return body, packed, etag


@router.get("/quotes")
async def quotes(request: Request):
    level = "silver" if has((await current(request)).plan, "silver") else "basic"
    store = request.app.state.store
    try:
        hit = await store.redis.hmget(f"search-quotes:{level}", ["body", "gzip", "etag"])
    except Exception:
        hit = [None, None, None]
    if hit[0] is None or hit[1] is None or hit[2] is None:
        body, packed, etag = await build(request.app, level)
    else:
        body, packed, etag = hit[0], hit[1], hit[2].decode()
    headers = {"ETag": etag, "Cache-Control": CACHE, "Vary": "Cookie, Accept-Encoding"}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    if "gzip" in (request.headers.get("accept-encoding") or ""):
        return Response(content=packed, media_type="application/json", headers={**headers, "Content-Encoding": "gzip"})
    return Response(content=body, media_type="application/json", headers=headers)
