"""POST /api/portfolio/page: the figures behind the new Equity portfolio page (docs/PORTFOLIO-PAGE.md).

The body carries share names only (extra='forbid': quantity, amount, price, date or any other field gives a 422). The answer is the handover pack's
page object (metrics.build_page: score, co-movement grid, groups, share of risk, NIFTY 50 measures, readings and summary) worked out from the stored
adjusted weekly closes of the last 105 complete weeks and the NIFTY 50 closes on the same weeks, plus each share's name, sector, size band and market
value. It is kept in Redis by sorted names + the unfinished week, so it is recomputed when the list changes or a new week completes.

Plans: Silver and Gold (Basic is refused with 403 plan_required, as the other Equity portfolio tools). The style tilt is built from FinLit Prism ratings and
goes to Gold only, exactly as on the Diversification card; Silver gets a locked block with the reason. Price, today's change and the score columns come
from POST /api/portfolio/overview (they are live and plan specific), not from here.
Information only, not investment advice.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import Any, Dict, List

import orjson
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth.entitlements import has
from ..auth.routes import Ctx, fail, ip_of, secure_ctx
from ..diversification import api as div
from . import inputs

log = logging.getLogger("finlit.portfolio_page")
router = APIRouter(prefix="/api/portfolio")

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
MAX_SYMBOLS = 500
CACHE_SECONDS = 6 * 3600
CACHE_VERSION = "v1"
TILT_LOCKED = div.TILT_LOCKED
NO_STORE = {"Cache-Control": "private, no-store", "Vary": "Cookie"}


class PageIn(BaseModel):
    """Share names only. Any other field is a 422."""
    model_config = ConfigDict(extra="forbid")
    symbols: List[str] = Field(min_length=1, max_length=MAX_SYMBOLS)

    @field_validator("symbols")
    @classmethod
    def clean(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for s in v:
            s = s.strip().upper()
            if not SYMBOL.match(s):
                raise ValueError("bad symbol")
            if s not in out:
                out.append(s)
        return out


async def member_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "silver"):
        raise fail(403, "plan_required", "Equity portfolio is part of the Silver plan.", plan="silver")
    return ctx


async def _sector_spellings(app) -> Dict[str, str]:
    """Raw Sector label -> the one spelling the site shows (variant spellings merged, as the screener does)."""
    from ..presets.industry import sector_map
    redis = app.state.store.redis
    try:
        raw = await redis.get("pfpage:sectors:v1")
    except Exception:
        raw = None
    if raw:
        return orjson.loads(raw)
    async with app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT sector, count(*) AS n FROM companies WHERE sector IS NOT NULL AND sector <> '' GROUP BY sector")
    mapping = sector_map({r["sector"]: int(r["n"]) for r in rows})
    try:
        await redis.set("pfpage:sectors:v1", orjson.dumps(mapping), ex=3600)
    except Exception:
        pass
    return mapping


def _compute(prices: Dict[str, Any], index_rows: List[dict], meta: Dict[str, dict], week: str) -> dict:
    return inputs.run(prices, index_rows, meta, week)      # pandas + scipy: runs in a worker thread


@router.post("/page")
async def page(request: Request, body: PageIn, ctx: Ctx = Depends(member_ctx)) -> Response:
    app = request.app
    allowed, retry = await app.state.limiter.hit("portfolio_page", ip_of(request), 30, 60, fail_open=False)
    if not allowed:
        return Response(orjson.dumps({"status": "rate_limited", "detail": "Too many requests. Please wait and try again.", "retryAfter": retry}), status_code=429,
                        media_type="application/json", headers={"Retry-After": str(retry), "Cache-Control": "no-store"})
    symbols = body.symbols
    week = div.unfinished_week(div.now_ist())
    key = "pfpage:" + ":".join([CACHE_VERSION, week, hashlib.sha1(",".join(sorted(symbols)).encode()).hexdigest()[:24]])   # nosec B324 - cache key
    redis = app.state.store.redis
    try:
        cached = await redis.get(key)
    except Exception:
        cached = None
    if cached:
        result = orjson.loads(cached)
    else:
        facts = div._facts(await app.state.store.diversification_facts(symbols))
        known = [s for s in symbols if s in facts]
        unknown = [s for s in symbols if s not in facts]
        result: Dict[str, Any] = {"week": week, "symbols": known, "unknown": unknown, "page": None, "meta": {}, "noPrices": []}
        if known:
            prices = await div._prices(app, known)
            index_rows = await div._index(app)
            if not index_rows:
                raise fail(502, "provider_unavailable", "NIFTY 50 prices are not available right now, so the comparison cannot be worked out. Please try again in a moment.")
            meta = inputs.build_meta(known, facts, await _sector_spellings(app))
            try:
                page_obj = await asyncio.to_thread(_compute, prices, index_rows, meta, week)
            except AssertionError:
                log.exception("a reading failed the wording check")
                raise fail(500, "wording_check", "The readings could not be written for this list. This has been logged.")
            result.update({"page": page_obj, "meta": meta, "noPrices": [s for s in known if s not in prices]})
        try:
            await redis.set(key, orjson.dumps(result, option=orjson.OPT_SERIALIZE_NUMPY), ex=CACHE_SECONDS)
        except Exception:
            pass
    if result.get("page"):
        if ctx.role == "admin" or has(ctx.plan, div.STYLE_TILT_TIER):
            from ..diversification import calc
            tilt = calc.style_tilt(await div._prism_universe(app), result["symbols"])
            tilt["sentence"] = calc.tilt_sentence(tilt["parts"])
            result = {**result, "styleTilt": tilt}
        else:
            result = {**result, "styleTilt": TILT_LOCKED}
    return Response(orjson.dumps(result, option=orjson.OPT_SERIALIZE_NUMPY), media_type="application/json", headers=NO_STORE)
