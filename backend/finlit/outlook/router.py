"""POST /api/outlook/{symbol}: the Gold-only profit and revenue outlook. Reads the stored report sections and the screener table only (no provider calls). Information only, not investment advice."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from ..auth.entitlements import has
from ..auth.routes import SYMBOL, Ctx, fail, secure_ctx
from ..screener.data import get_table
from .inputs import build_inputs
from .model import HISTORY_YEARS, WeightError, default_weights, forecast, hist_from_inputs, sector_inputs, validate_weights
from .sector import peer_values

router = APIRouter(prefix="/api/outlook")
CACHE_SECONDS = 600
DISCLAIMER = "Estimates from the company's own history and its sector, not a prediction or advice. The weights are starting values and have not yet been validated."
SECTIONS = ("summary", "financials", "ratios", "segments")


class OutlookIn(BaseModel):
    kind: Literal["profit", "revenue"]
    horizon: Literal["short", "mid", "long"] = "short"
    weights: Optional[Dict[str, float]] = None
    normalise: bool = False
    statement: Literal["consolidated", "standalone"] = "consolidated"


async def gold_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "gold"):
        raise fail(403, "plan_required", "The profit and revenue outlook is part of the Gold plan.", plan="gold")
    return ctx


def build_response(kind: str, horizon: str, weights: Dict[str, float], custom: bool, sections: Dict[str, dict], symbol: str, statement: str, table=None) -> dict:
    inp = build_inputs(sections.get("summary"), sections.get("financials"), sections.get("ratios"), sections.get("segments"))
    hist = hist_from_inputs(inp)
    peers, groups, why = (None, {}, "The sector table is not available right now.")
    if table is not None:
        peers, groups, why = peer_values(kind, symbol, table.symbols, table.sector, table.industry, table.cols)
    result = forecast(kind, hist, horizon, weights, sector_inputs(kind, peers, groups, why))
    meta = (sections.get("summary") or {}).get("meta") or {}
    key = "revenue" if kind == "revenue" else "net_profit"
    reported = {p: (inp.pl.get(key) or {}).get(p) for p in inp.fy}
    used = hist.revenue if kind == "revenue" else hist.profit
    pts = [{"period": p, "valueCr": None if v is None else round(v, 2), "reportedCr": reported.get(p), "adjusted": kind == "profit" and p in hist.adjusted}
           for p, v in zip(hist.fy, used)][-HISTORY_YEARS:]
    return {
        "symbol": symbol, "statement": statement, "kind": kind, "mode": "custom" if custom else "model",
        "name": (((sections.get("summary") or {}).get("profile")) or {}).get("name"), "isLender": inp.lender,
        "asOf": {"yearly": inp.fy[-1] if inp.fy else None}, "reportGeneratedAt": meta.get("generatedAt"),
        "weights": weights, "defaultWeights": default_weights(kind, horizon), "adjustedYears": hist.adjusted if kind == "profit" else [],
        "history": {"unit": "Rs crore", "points": pts}, **result, "disclaimer": DISCLAIMER,
    }


@router.post("/{symbol}")
async def outlook(request: Request, symbol: str, body: OutlookIn, ctx: Ctx = Depends(gold_ctx)):
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise fail(400, "invalid_symbol", "That is not a stock symbol.")
    try:
        weights = validate_weights(body.kind, body.weights, body.horizon, body.normalise)
    except WeightError as exc:
        raise fail(422, "invalid_weights", str(exc))
    store = request.app.state.store
    for st in ([body.statement, "standalone"] if body.statement == "consolidated" else [body.statement]):
        hits = {n: await store.get_section(sym, st, n) for n in SECTIONS}
        if hits["summary"] and hits["financials"]:
            break
    else:
        raise fail(404, "not_ready", "This company's report is not stored yet. Open its page once (it is prepared in about a minute), then try again.")
    version = hashlib.sha1("|".join(f"{n}:{hits[n][1] if hits[n] else '-'}" for n in SECTIONS).encode()).hexdigest()[:16]  # nosec B324 - cache key
    whash = hashlib.sha1(json.dumps(sorted(weights.items())).encode()).hexdigest()[:12]  # nosec B324 - cache key
    key = f"outlook2:{sym}:{st}:{body.kind}:{body.horizon}:{whash if body.weights is not None else 'model'}:{version}"
    redis = store.redis
    payload = None
    try:
        payload = await redis.get(key)
    except Exception:
        payload = None
    if payload is None:
        sections = {n: (orjson.loads(hits[n][0]) if hits[n] else None) for n in SECTIONS}
        table = None
        try:
            table = await get_table(store)
        except Exception:   # the sector table is optional: the sector inputs then say why they are blank
            table = None
        payload = orjson.dumps(build_response(body.kind, body.horizon, weights, body.weights is not None, sections, sym, st, table))
        try:
            await redis.set(key, payload, ex=CACHE_SECONDS)
        except Exception:
            pass
    return Response(content=payload, media_type="application/json", headers={"Cache-Control": "private, no-store", "Vary": "Cookie"})
