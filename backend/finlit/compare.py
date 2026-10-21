"""Custom comparison: every screener measure for 1 to 4 companies side by side, plus the member's saved measure sets.

The measures, their units, their "better" direction and their plan come from the screener catalogue (read only). The plan check is made here, on
the server: a locked measure is refused, never sent. Every selected measure comes back for every company: a number, or null with the reason.
"""

from __future__ import annotations

import json
import re
from typing import List

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator

from .auth.entitlements import LIMITS
from .auth.routes import NO_STORE, SYMBOL, fail, need_plan, secure_ctx, user_ctx
from .auth.service import Ctx, current
from .screener.catalog import BY_KEY, GROUP_LABEL, allowed
from .screener.compute import MULTIPLES
from .screener.data import get_table

router = APIRouter(prefix="/api/compare")
MAX_METRICS = 200   # the whole catalogue fits; the website itself offers fewer at a time
SET_LIMITS = {"silver": 10, "gold": 30}   # saved measure sets kept in the account (Basic keeps them in the browser only)
KEY = re.compile(r"^[a-z0-9_]{2,40}$")


def _plan(ctx: Ctx) -> str:
    return ctx.plan if ctx.authed else "basic"


def reason_missing(key: str) -> str:
    """Why a figure can be blank, in plain words, from what kind of measure it is. Never a guess at the number."""
    m = BY_KEY[key]
    if key in MULTIPLES or m.unit == "x" and m.group == "valuation":
        return "Not meaningful: earnings, cash flow or book value is zero or negative, or the company does not report it"
    if m.group == "banks":
        return "Applies to banks and lenders only, or not reported"
    if m.group == "quarterly":
        return "No quarterly result on file for this company"
    if m.group == "model":
        return "FinLit has not scored this company yet"
    if m.group == "ownership":
        return "No shareholding pattern on file"
    if m.group == "trading":
        return "Not enough price history"
    if m.group in ("growth",) or key.endswith(("_3y", "_5y", "_7y")) or "cagr" in key:
        return "Not enough years of reported data"
    return "Not reported for this company"


class MetricsIn(BaseModel):
    symbols: List[str] = Field(min_length=1, max_length=10)
    keys: List[str] = Field(min_length=1, max_length=MAX_METRICS)

    @field_validator("symbols")
    @classmethod
    def clean_symbols(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for s in v:
            s = s.strip().upper()
            if not SYMBOL.match(s):
                raise ValueError("bad symbol")
            if s not in out:
                out.append(s)
        return out

    @field_validator("keys")
    @classmethod
    def clean_keys(cls, v: List[str]) -> List[str]:
        out: List[str] = []
        for k in v:
            if not KEY.match(k) or k not in BY_KEY:
                raise ValueError(f"unknown measure {k}")
            if k not in out:
                out.append(k)
        return out


@router.post("/metrics")
async def metrics(request: Request, body: MetricsIn):
    plan = _plan(await current(request))
    cap = LIMITS.get(plan, LIMITS["basic"])["compare"]
    if len(body.symbols) > cap:
        raise fail(403, "plan_limit", f"Your plan compares up to {cap} companies at once.", plan="gold")
    locked = [k for k in body.keys if not allowed(plan, BY_KEY[k].tier)]
    if locked:
        tier = "gold" if any(BY_KEY[k].tier == "gold" for k in locked) else "silver"
        names = ", ".join(BY_KEY[k].label for k in locked[:3])
        raise fail(403, "plan_required", f"{names} {'is' if len(locked) == 1 else 'are'} part of the {tier.title()} plan.", plan=tier, keys=locked)
    t = await get_table(request.app.state.store)
    companies, values = [], {k: {} for k in body.keys}
    for sym in body.symbols:
        i = t.pos.get(sym)
        if i is None:
            companies.append({"symbol": sym, "name": sym, "sector": None, "cap": None, "known": False})
            for k in body.keys:
                values[k][sym] = {"v": None, "why": "This company is not in the FinLit list yet"}
            continue
        row = t.row(i, body.keys)
        companies.append({"symbol": sym, "name": row["name"], "sector": row["sector"], "cap": row["cap"], "known": True})
        for k in body.keys:
            v = row["v"][k]
            values[k][sym] = {"v": v, "why": None if v is not None else reason_missing(k)}
    meta = [{"key": k, "label": BY_KEY[k].label, "group": BY_KEY[k].group, "groupLabel": GROUP_LABEL[BY_KEY[k].group], "unit": BY_KEY[k].unit,
             "better": BY_KEY[k].better, "digits": BY_KEY[k].digits, "say": BY_KEY[k].say, "tier": BY_KEY[k].tier} for k in body.keys]
    out = {"plan": plan, "companies": companies, "metrics": meta, "values": values}
    return Response(content=json.dumps(out, separators=(",", ":")), media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


# ------------------------------------------------------------------ saved measure sets (Silver and Gold accounts)
class SavedSet(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    keys: List[str] = Field(min_length=1, max_length=MAX_METRICS)

    @field_validator("name")
    @classmethod
    def trimmed(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty name")
        return v

    @field_validator("keys")
    @classmethod
    def known(cls, v: List[str]) -> List[str]:
        if any(k not in BY_KEY for k in v) or len(set(v)) != len(v):
            raise ValueError("unknown or repeated measure")
        return v


class SetsIn(BaseModel):
    sets: List[SavedSet] = Field(max_length=max(SET_LIMITS.values()))


@router.get("/sets")
async def get_sets(request: Request, ctx: Ctx = Depends(user_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT sets FROM compare_sets WHERE user_id = $1", ctx.user_id)
    raw = row["sets"] if row else []
    sets = json.loads(raw) if isinstance(raw, str) else raw
    return Response(content=json.dumps({"sets": sets, "limit": SET_LIMITS.get(ctx.plan, 0)}), media_type="application/json", headers=NO_STORE)


@router.put("/sets")
async def put_sets(request: Request, body: SetsIn, ctx: Ctx = Depends(secure_ctx)):
    need_plan(ctx, "silver")
    if len(body.sets) > SET_LIMITS[ctx.plan]:
        raise fail(403, "plan_limit", f"Your plan keeps up to {SET_LIMITS[ctx.plan]} saved sets.", plan="gold")
    if len({s.name.lower() for s in body.sets}) != len(body.sets):
        raise fail(422, "duplicate_name", "Two sets share a name.")
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("INSERT INTO compare_sets (user_id, sets) VALUES ($1, $2::jsonb) ON CONFLICT (user_id) DO UPDATE SET sets = EXCLUDED.sets, updated_at = now()",
                           ctx.user_id, json.dumps([s.model_dump() for s in body.sets]))
    return {"status": "saved"}
