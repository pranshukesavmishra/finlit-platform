"""DCF calculator, server side (Gold). The valuation itself runs in the browser (frontend/src/lib/dcf.ts: pure, instant, tested); the server
gives a Gold member a listed company's inputs from its stored report, and keeps the member's saved scenarios.

GET    /api/dcf/company/{symbol}     free cash flow history, net debt and its parts, shares, price and market capitalisation
GET    /api/dcf/scenarios            the member's saved scenarios
PUT    /api/dcf/scenarios/{name}     save (create or replace) one; at most MAX_SCENARIOS
DELETE /api/dcf/scenarios/{name}

Every figure comes from the company's stored report (₹ crore; FCF = cash from operations − capital expenditure, as the report's cash
flow statement shows it), with its period, so the page can say where each input came from.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator

from .auth.entitlements import has
from .auth.routes import NO_STORE, SYMBOL, Ctx, fail, secure_ctx

router = APIRouter(prefix="/api/dcf")
MAX_SCENARIOS = 50


async def gold_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "gold"):
        raise fail(403, "plan_required", "The DCF calculator is part of the Gold plan.", plan="gold")
    return ctx


def _series(table: Optional[dict], key: str) -> List[Optional[float]]:
    rows = (table or {}).get("rows") or {}
    return list(rows.get(key) or [])


def _num(v: Any) -> Optional[float]:
    return float(v) if isinstance(v, (int, float)) and math.isfinite(v) else None


def cagr(first: Optional[float], last: Optional[float], years: int) -> Optional[float]:
    """Compound annual growth in %, only between two positive values (a growth rate across a sign change means nothing)."""
    if first is None or last is None or first <= 0 or last <= 0 or years <= 0:
        return None
    return ((last / first) ** (1 / years) - 1) * 100


def company_inputs(summary: dict, financials: dict) -> Dict[str, Any]:
    """The calculator's inputs from a company's stored summary and financials sections (both already parsed)."""
    yearly = financials.get("yearly") or {}
    cf, bs, pl = yearly.get("cf") or {}, yearly.get("bs") or {}, yearly.get("pl") or {}
    periods = list(cf.get("periods") or [])
    fcf, op, capex = _series(cf, "free_cash_flow"), _series(cf, "operating"), _series(cf, "capex")
    history = [{"period": p, "fcf": _num(fcf[k] if k < len(fcf) else None), "operating": _num(op[k] if k < len(op) else None),
                "capex": _num(capex[k] if k < len(capex) else None)} for k, p in enumerate(periods)]
    history = [h for h in history if h["fcf"] is not None][-10:]
    vals = [h["fcf"] for h in history]
    latest = history[-1] if history else None
    avg = lambda n: sum(vals[-n:]) / n if len(vals) >= n else None   # noqa: E731

    bsp = list(bs.get("periods") or [])
    at = lambda key: _num(_series(bs, key)[-1]) if bsp and _series(bs, key) else None   # noqa: E731
    borrowings, cash, investments = at("borrowings"), at("cash"), at("investments")
    net_debt = None if borrowings is None and cash is None else (borrowings or 0.0) - (cash or 0.0)

    quote, profile, quality = summary.get("quote") or {}, summary.get("profile") or {}, summary.get("dataQuality") or {}
    price, mcap = _num(quote.get("price")), _num(quote.get("marketCapCr"))
    diluted = [v for v in _series(pl, "diluted_shares_cr") if _num(v) and v > 0]
    plp = list(pl.get("periods") or [])

    notes: List[str] = []
    lender = bool(quality.get("isBank"))
    if lender:
        notes.append("This is a bank or lender: its cash flow statement mixes customer deposits and loans with the business's own cash, so a "
                     "free-cash-flow DCF does not fit it. Lenders are usually valued on earnings, dividends or book value (P/B with ROE).")
    if latest and latest["fcf"] <= 0:
        notes.append(f"Free cash flow was negative in {latest['period']}. The calculator needs a positive starting FCF: use an average of "
                     "several years, or wait for a positive year.")
    last3 = vals[-3:]
    if len(last3) == 3 and min(last3) > 0 and max(last3) > 2 * min(last3):
        notes.append("Free cash flow moved a lot over the last three years; an average is a steadier starting point than one year.")
    return {
        "symbol": (summary.get("meta") or {}).get("symbol") or profile.get("symbol"),
        "name": profile.get("name"), "sector": profile.get("sector") or profile.get("macroSector"),
        "statement": (summary.get("meta") or {}).get("statement"), "isBank": lender,
        "price": price, "priceAsOf": quote.get("asOf"), "marketCap": mcap,
        "shares": {"diluted": diluted[-1] if diluted else None, "period": plp[-1] if diluted and plp else None,
                   "implied": (mcap / price) if mcap and price else None},
        "fcf": {"history": history, "latest": latest, "avg3": avg(3), "avg5": avg(5),
                "cagr3": cagr(vals[-4], vals[-1], 3) if len(vals) >= 4 else None,
                "cagr5": cagr(vals[-6], vals[-1], 5) if len(vals) >= 6 else None},
        "netDebt": {"value": net_debt, "borrowings": borrowings, "cash": cash, "investments": investments, "period": bsp[-1] if bsp else None},
        "unit": "₹ crore", "notes": notes,
    }


@router.get("/company/{symbol}")
async def company(request: Request, symbol: str, statement: Literal["consolidated", "standalone"] = "consolidated", ctx: Ctx = Depends(gold_ctx)):
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise fail(400, "invalid_symbol", "That is not a stock symbol.")
    store = request.app.state.store
    for st in ([statement, "standalone"] if statement == "consolidated" else [statement]):
        s, f = await store.get_section(sym, st, "summary"), await store.get_section(sym, st, "financials")
        if s and f:
            body = company_inputs(orjson.loads(s[0]), orjson.loads(f[0]))
            body["statement"] = st
            return Response(content=orjson.dumps(body), media_type="application/json", headers={"Cache-Control": "private, no-cache", "Vary": "Cookie"})
    raise fail(404, "not_ready", "This company's report is not stored yet. Open its page once (it is prepared in about a minute), then try again.")


# ------------------------------------------------------------------------------------------------------------- saved scenarios

def _finite(v: float) -> float:
    if not math.isfinite(v):
        raise ValueError("must be a finite number")
    return v


class Inputs(BaseModel):
    fcf0: float = Field(ge=-1e9, le=1e9)
    r: float = Field(ge=-100, le=100)
    g1: float = Field(ge=-100, le=1000)
    g2: float = Field(ge=-100, le=1000)
    gT: float = Field(ge=-100, le=100)
    marketCap: float = Field(ge=0, le=1e9)
    price: float = Field(ge=0, le=1e9)
    netDebt: float = Field(ge=-1e9, le=1e9)
    mos: float = Field(ge=0, le=100)
    midYear: bool = False
    shares: Optional[float] = Field(default=None, ge=0, le=1e7)
    tvMethod: Literal["gordon", "exit"] = "gordon"
    exitMultiple: Optional[float] = Field(default=None, ge=0, le=1000)
    g1Preset: Optional[Literal["conservative", "moderate", "aggressive", "custom"]] = None
    g2Preset: Optional[Literal["conservative", "moderate", "aggressive", "custom"]] = None

    _f = field_validator("fcf0", "r", "g1", "g2", "gT", "marketCap", "price", "netDebt", "mos")(_finite)


class ScenarioIn(BaseModel):
    inputs: Inputs
    symbol: Optional[str] = Field(default=None, max_length=24)
    note: Optional[str] = Field(default=None, max_length=500)

    @field_validator("symbol")
    @classmethod
    def _sym(cls, v: Optional[str]) -> Optional[str]:
        if v and not SYMBOL.match(v.strip().upper()):
            raise ValueError("bad symbol")
        return v.strip().upper() if v else None


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not 1 <= len(name) <= 80:
        raise fail(422, "bad_name", "Give the scenario a name of up to 80 characters.")
    return name


@router.get("/scenarios")
async def list_scenarios(request: Request, ctx: Ctx = Depends(gold_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, symbol, inputs, note, updated_at FROM dcf_scenarios WHERE user_id = $1 ORDER BY updated_at DESC", ctx.user_id)
    out = [{"name": r["name"], "symbol": r["symbol"], "note": r["note"], "updatedAt": r["updated_at"].isoformat(),
            "inputs": json.loads(r["inputs"]) if isinstance(r["inputs"], str) else r["inputs"]} for r in rows]
    return Response(content=json.dumps({"scenarios": out, "max": MAX_SCENARIOS}), media_type="application/json", headers=NO_STORE)


@router.put("/scenarios/{name}")
async def save_scenario(request: Request, name: str, body: ScenarioIn, ctx: Ctx = Depends(gold_ctx)):
    name = clean_name(name)
    async with request.app.state.store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "dcf_scenarios:" + str(ctx.user_id))   # two quick saves cannot pass the limit
            exists = await conn.fetchval("SELECT 1 FROM dcf_scenarios WHERE user_id = $1 AND name = $2", ctx.user_id, name)
            if not exists and await conn.fetchval("SELECT count(*) FROM dcf_scenarios WHERE user_id = $1", ctx.user_id) >= MAX_SCENARIOS:
                raise fail(403, "limit", f"You can keep {MAX_SCENARIOS} saved scenarios. Delete one first.")
            await conn.execute(
                "INSERT INTO dcf_scenarios (user_id, name, symbol, inputs, note) VALUES ($1, $2, $3, $4::jsonb, $5) "
                "ON CONFLICT (user_id, name) DO UPDATE SET symbol = EXCLUDED.symbol, inputs = EXCLUDED.inputs, note = EXCLUDED.note, updated_at = now()",
                ctx.user_id, name, body.symbol, json.dumps(body.inputs.model_dump()), body.note)
    return {"status": "saved", "name": name}


@router.delete("/scenarios/{name}")
async def delete_scenario(request: Request, name: str, ctx: Ctx = Depends(gold_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM dcf_scenarios WHERE user_id = $1 AND name = $2", ctx.user_id, clean_name(name))
    return {"status": "deleted"}
