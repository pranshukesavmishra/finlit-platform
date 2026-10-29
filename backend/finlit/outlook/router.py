"""POST /api/outlook/{symbol}: the Gold-only profit and revenue outlook. Reads the stored report sections only (no provider calls) and never
returns parameter-level detail or thresholds. Information only, not investment advice."""

from __future__ import annotations

import hashlib
import json
from typing import Dict, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel

from ..auth.entitlements import has
from ..auth.routes import SYMBOL, Ctx, fail, secure_ctx
from .compose import WeightError, compose, validate_weights
from .inputs import build_inputs
from .rangecalc import growth_range

router = APIRouter(prefix="/api/outlook")
CACHE_SECONDS = 600
DISCLAIMER = "Scenario from the company's reported history. Not a forecast, not advice. Information only, not investment advice."
SECTIONS = ("summary", "financials", "ratios", "segments")


class OutlookIn(BaseModel):
    kind: Literal["profit", "revenue"]
    weights: Optional[Dict[str, float]] = None
    statement: Literal["consolidated", "standalone"] = "consolidated"


async def gold_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "gold"):
        raise fail(403, "plan_required", "The profit and revenue outlook is part of the Gold plan.", plan="gold")
    return ctx


def build_response(kind: str, weights: Dict[str, float], custom: bool, sections: Dict[str, dict], symbol: str, statement: str) -> dict:
    inp = build_inputs(sections.get("summary"), sections.get("financials"), sections.get("ratios"), sections.get("segments"))
    result = compose(kind, inp, weights)
    raw = result.pop("_raw_score")
    meta = (sections.get("summary") or {}).get("meta") or {}
    return {
        "symbol": symbol, "statement": statement, "kind": kind, "mode": "custom" if custom else "model",
        "name": (((sections.get("summary") or {}).get("profile")) or {}).get("name"),
        "isLender": inp.lender, "asOf": {"yearly": inp.fy[-1] if inp.fy else None, "quarterly": inp.qp[-1] if inp.qp else None},
        "reportGeneratedAt": meta.get("generatedAt"), **result,
        "range": growth_range(kind, inp, raw), "disclaimer": DISCLAIMER,
    }


@router.post("/{symbol}")
async def outlook(request: Request, symbol: str, body: OutlookIn, ctx: Ctx = Depends(gold_ctx)):
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise fail(400, "invalid_symbol", "That is not a stock symbol.")
    try:
        weights = validate_weights(body.kind, body.weights)
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
    key = f"outlook:{sym}:{st}:{body.kind}:{whash if body.weights is not None else 'model'}:{version}"
    redis = store.redis
    payload = None
    try:
        payload = await redis.get(key)
    except Exception:
        payload = None
    if payload is None:
        sections = {n: (orjson.loads(hits[n][0]) if hits[n] else None) for n in SECTIONS}
        payload = orjson.dumps(build_response(body.kind, weights, body.weights is not None, sections, sym, st))
        try:
            await redis.set(key, payload, ex=CACHE_SECONDS)
        except Exception:
            pass
    return Response(content=payload, media_type="application/json", headers={"Cache-Control": "private, no-store", "Vary": "Cookie"})
