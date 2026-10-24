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
import zlib
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import orjson

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
# The rows behind both levels, kept in Redis: a rebuild reads only the companies whose score or listing row changed since the last one (about 5,800 rows
# of ~80 bytes is half a megabyte, and the minute-by-minute prices would otherwise make every two-minute rebuild read all of it).
RAW_KEY = "search-quotes:raw"
FULL_EVERY = 6 * 3600     # all rows again (also catches companies that left or joined and a changed logo)
MARGIN = 120
PROBE_SQL = ("SELECT (SELECT count(*) FROM scores WHERE model = 'v1') AS sn, (SELECT max(changed_at) FROM scores WHERE model = 'v1') AS sa, "
             "(SELECT count(*) FROM listing_quotes) AS ln, (SELECT max(updated_at) FROM listing_quotes) AS la, (SELECT count(*) FROM companies) AS cn")


def _num(v):
    return None if v is None else round(float(v), 2)


def session_of(at: datetime) -> date:
    """The trading day a price saved at `at` belongs to: a row written before 15:30 IST or on a weekend carries the previous weekday's close
    (exchange holidays are not known here, so a holiday is labelled as the day before it)."""
    t = at.astimezone(IST)
    d = t.date() if (t.hour, t.minute) >= (15, 30) else t.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def quote_rows(rows, level: str, showcase: set) -> list:
    """The compact rows above. Basic: scores are blanked to "locked" except for the showcase companies."""
    out = []
    for r in rows:
        # The report's price is a snapshot from whenever it was loaded; the listing row is refreshed after each close. The report wins only when it is from a LATER
        # trading day than the listing row (its write time is not comparable with a trade time: a Saturday write must not beat Friday's closing quote).
        use_report = r["sp"] is not None and (r["qp"] is None or r["qt"] is None or (r["su"] is not None and session_of(r["su"]) > r["qt"].astimezone(IST).date()))
        price, chg, at = (r["sp"], r["sc"], r["su"]) if use_report else (r["qp"], r["qc"], r["qt"])
        score, band = r["overall"], r["band"]
        if score is not None and not has(level, "silver") and r["symbol"] not in showcase:
            score, band = None, "locked"
        logo = logo_path(r["sha8"])
        if price is None and score is None and band is None and logo is None:
            continue                                   # nothing to add to the name list
        when = None if not at or price is None else (session_of(at) if use_report else at.astimezone(IST).date())   # a score row's time is when it was written, not when it traded
        out.append([r["symbol"], _num(price), _num(chg), when.isoformat() if when else None,
                    score, band, logo])
    return out


def _rec(r) -> dict:
    return {k: (float(v) if isinstance(v, Decimal) else v.isoformat() if isinstance(v, datetime) else v) for k, v in dict(r).items()}


def _hydrate(rec: dict) -> dict:
    return {k: (datetime.fromisoformat(v) if k in ("su", "qt") and v else v) for k, v in rec.items()}


async def _raw_rows(store) -> list:
    """QUOTES_SQL's rows, in company order, from Redis plus whatever changed since (see RAW_KEY). Falls back to reading everything."""
    state, now = None, time.time()
    try:
        raw = await store.redis.get(RAW_KEY)
        state = orjson.loads(zlib.decompress(raw)) if raw else None
    except Exception:
        state = None
    async with store.pool.acquire() as conn:
        try:
            p = await conn.fetchrow(PROBE_SQL)
        except Exception:   # a column the probe needs is missing (migrations not applied yet): read everything, as before
            p = None
        sig = None if p is None else {"sn": p["sn"], "sa": p["sa"].isoformat() if p["sa"] else None, "ln": p["ln"], "la": p["la"].isoformat() if p["la"] else None, "cn": p["cn"]}
        old = state and state.get("sig")
        if sig and old and now - state["full_at"] < FULL_EVERY and sig["cn"] == old["cn"] and sig["sn"] >= old["sn"] and sig["ln"] >= old["ln"]:
            if sig == old:
                return state["rows"]
            def since(k):
                return datetime.fromisoformat(old[k]) - timedelta(seconds=MARGIN) if old[k] else datetime.fromtimestamp(0, timezone.utc)
            changed = await conn.fetch(
                "SELECT * FROM (" + QUOTES_SQL + ") q WHERE q.symbol IN (SELECT symbol FROM scores WHERE model = 'v1' AND changed_at > $1 "  # nosec B608 - fixed text
                "UNION SELECT symbol FROM listing_quotes WHERE updated_at > $2)", since("sa"), since("la"))
            by = {r["symbol"]: i for i, r in enumerate(state["rows"])}
            rows = list(state["rows"])
            for r in changed:
                rec = _rec(r)
                if r["symbol"] in by:
                    rows[by[r["symbol"]]] = rec
                else:
                    rows.append(rec)
            state = {"sig": sig, "full_at": state["full_at"], "rows": rows}
        else:
            state = {"sig": sig, "full_at": now, "rows": [_rec(r) for r in await conn.fetch(QUOTES_SQL)]}
    try:
        await store.redis.set(RAW_KEY, zlib.compress(orjson.dumps(state), 6), ex=2 * FULL_EVERY)
    except Exception:   # nosec B110 - Redis down: the rows just read are used once
        pass
    return state["rows"]


async def build(app, level: str):
    store = app.state.store
    rows = [_hydrate(r) for r in await _raw_rows(store)]
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
