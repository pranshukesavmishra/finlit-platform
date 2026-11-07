"""POST /api/diversification: the Diversification card (docs/DIVERSIFICATION.md).

The request carries share names only. Any other field (quantity, amount, price, date, ...) is refused with 422, so none can reach the server by accident.
Data: the site's own stored adjusted weekly closes (price-MAX, weekly bars from January 2020) and NIFTY 50 daily closes reduced to ISO weeks.

Plans: the endpoint is open, like the Compare page and the stored prices it reads (Equity portfolio keeps its own Silver gate on the page). The one part that
comes from a paid data set, the style tilt (FinLit Prism parts), is sent to Gold only, as the screener does; the card shows why it is blank.
Information only, not investment advice.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

import orjson
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth.entitlements import has
from ..auth.routes import fail
from ..auth.service import current
from ..indices import IST, _cached, _fetch_levels, shape_levels
from ..security import client_ip
from . import sectors as sec

log = logging.getLogger("finlit.diversification")
router = APIRouter(prefix="/api/diversification")

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
MAX_STOCKS = 100
CACHE_SECONDS = 6 * 3600
STYLE_TILT_TIER = "gold"            # FinLit Prism parts are a Gold feature on the screener; the tilt is derived from them
PRISM_STATUSES = ("RATED", "PROVISIONAL")
TILT_LOCKED = {"locked": STYLE_TILT_TIER, "reason": "The style tilt is built from FinLit Prism ratings, which are part of the Gold plan."}


class DiversificationIn(BaseModel):
    """Share names only. extra='forbid': quantity, amount, price, date and every other field give a 422."""
    model_config = ConfigDict(extra="forbid")
    symbols: List[str] = Field(min_length=1, max_length=MAX_STOCKS)
    benchmark: Literal["NIF50"] = "NIF50"
    horizon: Literal["weekly", "monthly", "yearly"] = "weekly"

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


def now_ist() -> datetime:
    return datetime.now(IST)


def unfinished_week(now: datetime) -> str:
    """The ISO week that is not finished yet: always the current one. Saturday and Sunday count too, because the stored Friday close is written by the
    nightly refresh and may not be there yet. The newest week the card uses is therefore the last one completed before this one."""
    from .calc import iso_week_key
    return iso_week_key(now.date())


async def _prices(app, symbols: List[str]) -> Dict[str, Any]:
    store = app.state.store
    sem = asyncio.Semaphore(16)

    async def one(sym: str):
        async with sem:
            for stmt in ("consolidated", "standalone"):
                hit = await store.get_section(sym, stmt, "price-MAX")
                if hit:
                    body = orjson.loads(hit[0])
                    series = body.get("series") or {}
                    pairs = [(t, c) for t, c in zip(series.get("t") or [], series.get("c") or []) if c is not None and c > 0]
                    if pairs:
                        return sym, {"t": [p[0] for p in pairs], "c": [p[1] for p in pairs]}
            return sym, None

    out = {}
    for sym, series in await asyncio.gather(*(one(s) for s in symbols)):
        if series:
            out[sym] = series
    return out


async def _index(app) -> Optional[List[dict]]:
    raw = await _cached(app, "idx:px:NIF50", 6 * 3600, lambda: _fetch_levels(app, "NIF50"))
    rows = shape_levels(raw, 5)["rows"] if raw else []
    return rows or None


def _facts(rows: List[dict]) -> Dict[str, dict]:
    return {r["symbol"]: r for r in rows}


async def _prism_universe(app) -> List[dict]:
    """The rated or provisional companies' Prism parts (the style-tilt universe), kept in Redis for half an hour."""
    from .. import prism_screen
    redis = app.state.store.redis
    try:
        raw = await redis.get("div:prism:v1")
    except Exception:
        raw = None
    if raw:
        return json.loads(raw)
    cards = prism_screen.cards(await app.state.store.prism_cards(None))
    rows = [{"symbol": s, **{k: v.get(k) for k in ("prism_fundamental", "prism_valuation", "prism_quality", "prism_risk", "prism_st_score", "prism_lt_score")}}
            for s, v in cards.items() if v.get("prism_status") in PRISM_STATUSES]
    try:
        await redis.set("div:prism:v1", json.dumps(rows), ex=1800)
    except Exception:
        pass
    return rows


def _build(prices: dict, index_rows: List[dict], symbols: List[str], facts: Dict[str, dict], horizon: str, week: str, month: str,
           spellings: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """The CPU part (pandas, numpy, scipy, scikit-learn): runs in a worker thread."""
    from . import calc
    sectors = {s: sec.macro_sector((facts.get(s) or {}).get("sector"), s) for s in symbols}
    sectors = {s: v for s, v in sectors.items() if v != sec.UNMAPPED}                 # calc names the missing ones 'Not classified'
    groups = {s: g for s in symbols for g in [sec.business_group(s)] if g}
    sizes = {s: calc.size_band((facts.get(s) or {}).get("rank")) for s in symbols}
    mcap = {s: (facts.get(s) or {}).get("mcap") for s in symbols}
    names = {s: (facts.get(s) or {}).get("name") or s for s in symbols}
    px = dict(prices)
    px["__NIFTY"] = {"rows": index_rows}
    core = calc.weekly_view(px, symbols, sectors, mcap, groups, sizes, week, names)
    unknown = [s for s in symbols if s not in facts]
    for s in unknown:                                                                    # not in FinLit's company list: said, not guessed
        if not any(e["symbol"] == s for e in core["excluded"]):
            core["excluded"].append({"symbol": s, "reason": "unknown", "weeks": 0})
        else:
            next(e for e in core["excluded"] if e["symbol"] == s)["reason"] = "unknown"
    core["names"] = names
    _one_score(core, prices, index_rows, symbols, facts, spellings or {}, week)
    if "score" not in core:
        core["needsThree"] = True
    if horizon == "weekly":
        return core
    view = calc.horizon_view(px, symbols, horizon, month)
    out = {"horizon": horizon, "scoreVersion": core["scoreVersion"], "included": view["included"], "excluded": view["excluded"], "spread": core["spread"], "names": names}
    if "score" in core:
        out["score"] = core["score"]                                                     # the score never changes with the horizon
    else:
        out["needsThree"] = True
    out.update({k: v for k, v in view.items() if k not in ("horizon", "included", "excluded", "scoreVersion")})
    if "headline" not in view:
        out["viewNote"] = "Fewer than 3 stocks have enough monthly prices for this view."
    return out


def _one_score(core: Dict[str, Any], prices: dict, index_rows: List[dict], symbols: List[str], facts: Dict[str, dict], spellings: Dict[str, str], week: str) -> None:
    """One score for one list on the whole site: the score, its two parts and 'moves like N' are the ones the Equity portfolio page shows (the handover pack's
    engine, finlit/portfolio_page), so the card and the page never disagree. The card's own pair, group, risk and market figures keep their windows."""
    from ..portfolio_page import inputs
    meta = inputs.build_meta([s for s in symbols if s in facts], facts, spellings)
    if len(meta) < 3:
        return
    page = inputs.run({k: v for k, v in prices.items() if k != "__NIFTY"}, index_rows, meta, week)
    score = inputs.card_score(page)
    if score is None:
        core.pop("score", None)
        core.pop("headline", None)
        return
    core["score"] = {**core.get("score", {}), **score}
    if "headline" in core:
        core["headline"]["effectiveStocks"] = page["score"]["effective_stocks"]
        core["headline"]["effectiveStocksRounded"] = int(page["score"]["effective_stocks"] + 0.5)


@router.post("")
async def diversification(request: Request, body: DiversificationIn) -> Response:
    app = request.app
    ip = request.scope.get("state", {}).get("client_ip") or client_ip(request.scope, app.state.settings.client_ip_header)
    allowed, retry = await app.state.limiter.hit("diversification", ip, 30, 60, fail_open=False)
    if not allowed:
        return Response(orjson.dumps({"status": "rate_limited", "detail": "Too many requests. Please wait and try again.", "retryAfter": retry}), status_code=429,
                        media_type="application/json", headers={"Retry-After": str(retry), "Cache-Control": "no-store"})
    ctx = await current(request)
    symbols = body.symbols
    now = now_ist()
    week, month = unfinished_week(now), f"{now.year}-{now.month:02d}"
    key = "div:v2:" + ":".join([week, body.horizon, hashlib.sha1(",".join(sorted(symbols)).encode()).hexdigest()[:24]])   # nosec B324 - cache key
    redis = app.state.store.redis
    try:
        cached = await redis.get(key)
    except Exception:
        cached = None
    if cached:
        result = orjson.loads(cached)
    else:
        facts = _facts(await app.state.store.diversification_facts(symbols))
        prices = await _prices(app, [s for s in symbols if s in facts])
        index_rows = await _index(app)
        if not index_rows:
            raise fail(502, "provider_unavailable", "NIFTY 50 prices are not available right now, so the comparison cannot be worked out. Please try again in a moment.")
        from ..portfolio_page.api import _sector_spellings
        result = await asyncio.to_thread(_build, prices, index_rows, symbols, facts, body.horizon, week, month, await _sector_spellings(app))
        try:
            await redis.set(key, orjson.dumps(result), ex=CACHE_SECONDS)
        except Exception:
            pass
    # The style tilt depends on the caller's plan and on the live Prism ratings, so it is added after the cache.
    if "score" in result:
        if ctx.role == "admin" or has(ctx.plan, STYLE_TILT_TIER):
            from . import calc
            tilt = calc.style_tilt(await _prism_universe(app), symbols)
            tilt["sentence"] = calc.tilt_sentence(tilt["parts"])
            result = {**result, "styleTilt": tilt}
        else:
            result = {**result, "styleTilt": TILT_LOCKED}
    return Response(orjson.dumps(result), media_type="application/json", headers={"Cache-Control": "private, no-store", "Vary": "Cookie"})
