"""/api/me/mf-portfolio: a member's mutual fund holdings (Silver and Gold; Basic is refused as for My portfolio).

    GET     ""                 the holdings, valued with the latest NAV, with the summary, allocation and concentration note
    POST    ""                 add a holding (or a purchase to the same fund and folio)
    PUT     "/{id}"            replace a holding's folio and purchases
    DELETE  "/{id}"            remove a holding
    POST    "/import-preview"  rows read from a file -> each row matched / choose / not_found / ignored / invalid / duplicate, nothing stored
    POST    "/import-commit"   the rows the member confirmed (each with the scheme chosen) -> stored

Plan rules are applied here, never left to the page: the Health Score and its four parts are Gold (an admin sees everything). Below Gold every holding
still comes back with its value, gain and returns, but `score` is `{locked: true}` with null fields and the score tables are not even read.
The number of funds a plan may hold is entitlements.LIMITS[plan]["mf_holdings"]. Writes need a signed-in session from our own pages (Origin + CSRF) and
are rate limited per member. Every query filters on the member's id. Information only, not investment advice.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .. import mf
from ..auth.entitlements import LIMITS, has
from ..auth.routes import Ctx, fail, limit, secure_ctx
from ..mfscore.api import NOT_SCORED
from . import DISCLAIMER, SCORE_DISCLAIMER
from .calc import NO_RETURNS, allocation, concentration, num, summarize, value_holding
from .match import Index, match_row
from .parse import Clean, Rejected, clean_folio, clean_row, strict_lot

router = APIRouter(prefix="/api/me/mf-portfolio")
NO_STORE = {"Cache-Control": "private, no-store", "Vary": "Cookie"}
MAX_IMPORT_ROWS = 2000
MAX_LOTS = 200
CELL_MAX = 300
SCHEME_COLS = mf.LIST_COLS + ", family, isin"


def reply(body: Dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=NO_STORE)


async def member_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin" and not has(ctx.plan, "silver"):
        raise fail(403, "plan_required", "My mutual funds is part of the Silver plan.", plan="silver")
    return ctx


def is_gold(ctx: Ctx) -> bool:
    return ctx.role == "admin" or has(ctx.plan, "gold")


def cap_for(ctx: Ctx) -> int:
    return LIMITS["gold" if ctx.role == "admin" else ctx.plan if ctx.plan in LIMITS else "basic"]["mf_holdings"]


def uid_of(s: str) -> uuid.UUID:
    try:
        return uuid.UUID(s)
    except ValueError:
        raise fail(404, "not_found", "No such holding.")


# ------------------------------------------------------------------------------------------------------------------------ the scheme index

_index_cache: Dict[str, Any] = {"ver": None, "index": None}


async def scheme_index(request: Request) -> Index:
    """Every scheme, built once per data version (a refresh of the fund data changes the version)."""
    store = request.app.state.store
    ver = await mf._version(store.redis)
    if _index_cache["ver"] != ver or _index_cache["index"] is None:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT code, name, amc, plan, option_class, option_label, active, isin, isin_reinvest, category, nav_date FROM mf_schemes")
        _index_cache["index"], _index_cache["ver"] = Index(rows), ver
    return _index_cache["index"]


# ------------------------------------------------------------------------------------------------------------------------ reading

async def holdings_of(conn, user_id: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT h.id, h.code, h.folio, l.id AS lot_id, l.units, l.invested, l.bought_on FROM mf_holdings h LEFT JOIN mf_holding_lots l ON l.holding_id = h.id "
        "WHERE h.user_id = $1 ORDER BY h.created_at, h.id, l.bought_on NULLS LAST, l.created_at, l.id", user_id)
    out: Dict[Any, Dict[str, Any]] = {}
    for r in rows:
        h = out.setdefault(r["id"], {"id": str(r["id"]), "code": r["code"], "folio": r["folio"], "lots": []})
        if r["lot_id"] is not None:        # a fund that is only followed (no units given) has no purchase lines
            h["lots"].append({"id": str(r["lot_id"]), "units": r["units"], "invested": r["invested"], "bought_on": r["bought_on"]})
    return list(out.values())


def _scheme_fields(s: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The fund's own facts for a row: name, house, plan, category, returns, expense ratio and size, each blank with its reason."""
    if s is None:
        return {"name": None, "amc": None, "plan": None, "option": None, "category": None, "categoryLabel": None, "active": False,
                "returns": {"r1y": None, "r3y": None, "r5y": None, "asOf": None, "why": "The scheme is no longer in the fund list."},
                "ter": None, "terDate": None, "terWhy": "The scheme is no longer in the fund list.", "aum": None, "aumAsOf": None, "aumWhy": "The scheme is no longer in the fund list."}
    item = mf.list_item(s)
    why = mf.why_no_returns(s)
    return {
        "name": s["name"], "amc": s["amc"], "plan": s["plan"], "option": s["option_label"] or s["option_class"], "optionClass": s["option_class"],
        "category": s["category"], "categoryLabel": mf.classify(s["category"])[2], "active": bool(s["active"]), "isin": s["isin"],
        "returns": {"r1y": item["r1y"], "r3y": item["r3y"], "r5y": item["r5y"], "asOf": item["retDate"], "why": NO_RETURNS.get(why or "") if why else None,
                    "partialWhy": None if why or all(item[k] is not None for k in ("r1y", "r3y", "r5y")) else "Some periods are blank because the fund is younger than that."},
        "ter": item["ter"], "terDate": item["terDate"], "terWhy": None if item["ter"] is not None else "The expense ratio has not been published for this scheme in AMFI's file.",
        "aum": item["aum"], "aumAsOf": item["aumAsOf"], "aumKind": item["aumKind"],
        "aumWhy": None if item["aum"] is not None else "The fund size has not been published for this scheme in AMFI's files.",
    }


async def scores_for(conn, codes: List[int]) -> Dict[int, Dict[str, Any]]:
    """Gold only: the Health Score of each scheme from mf_scores (an IDCW option carries its Growth plan's score, a scheme with none says why)."""
    from ..mfscore.api import resolve_mf
    rows = {r["code"]: dict(r) for r in await conn.fetch("SELECT * FROM mf_scores WHERE key = ANY($1::text[])", [f"mf:{c}" for c in codes])}
    out: Dict[int, Dict[str, Any]] = {}
    for c in codes:
        row, inherited, why = (rows.get(c), None, None) if c in rows else await resolve_mf(conn, c)
        if row is None:
            out[c] = {"locked": False, "final": None, "label": None, "status": "NOT SCORED", "reason": NOT_SCORED.get(why or "not_yet", NOT_SCORED["not_yet"]), "parts": None,
                      "runDate": None, "inherited": None}
            continue
        rated = row["final"] is not None
        out[c] = {"locked": False, "final": round(float(row["final"]), 1) if rated else None, "label": row["label"] if rated else None, "status": row["status"],
                  "reason": row["reason"], "runDate": row["run_date"].isoformat(),
                  "parts": {k: (None if row[k] is None else round(float(row[k]), 1)) for k in ("perf", "risk", "cost", "quality")} if rated else None,
                  "inherited": inherited}
        if out[c]["parts"]:
            out[c]["parts"] = {"performance": out[c]["parts"]["perf"], "risk": out[c]["parts"]["risk"], "cost": out[c]["parts"]["cost"], "quality": out[c]["parts"]["quality"]}
    return out


LOCKED_SCORE = {"locked": True, "final": None, "label": None, "status": None, "reason": None, "parts": None, "runDate": None, "inherited": None}


async def build_view(request: Request, ctx: Ctx) -> Dict[str, Any]:
    gold = is_gold(ctx)
    async with request.app.state.store.pool.acquire() as conn:
        held = await holdings_of(conn, ctx.user_id)
        codes = sorted({h["code"] for h in held})
        schemes = {r["code"]: dict(r) for r in await conn.fetch(f"SELECT {SCHEME_COLS} FROM mf_schemes WHERE code = ANY($1::int[])", codes)} if codes else {}  # nosec B608 - fixed column list; codes are bound
        data_date = await conn.fetchval("SELECT max(nav_date) FROM mf_schemes WHERE active")
        scores = await scores_for(conn, codes) if gold and codes else {}
    rows: List[Dict[str, Any]] = []
    for h in held:
        s = schemes.get(h["code"])
        row = {**value_holding(h, s, data_date), **_scheme_fields(s)}
        row["score"] = scores.get(h["code"]) if gold else LOCKED_SCORE
        rows.append(row)
    total = sum((Decimal(str(r["current"])) for r in rows if r["current"] is not None), Decimal(0))   # weight = share of the value of all valued funds
    for r in rows:
        r["weight"] = num(Decimal(str(r["current"])) / total * 100, 1) if r["current"] is not None and total > 0 else None
        r["weightWhy"] = None if r["weight"] is not None else (r["currentWhy"] or "The portfolio has no value yet.")
    summary = summarize(rows, score_locked=not gold)
    return {"plan": "gold" if gold else ctx.plan, "scoreLocked": not gold, "limit": cap_for(ctx), "count": len(rows), "dataDate": data_date.isoformat() if data_date else None,
            "holdings": rows, "summary": summary, "allocation": allocation(rows), "concentration": concentration(rows),
            "disclaimer": DISCLAIMER, "scoreDisclaimer": SCORE_DISCLAIMER}


@router.get("")
async def list_holdings(request: Request, ctx: Ctx = Depends(member_ctx)):
    return reply(await build_view(request, ctx))


# ------------------------------------------------------------------------------------------------------------------------ writing

class LotIn(BaseModel):
    units: Union[str, int, float, None] = None
    invested: Union[str, int, float, None] = None
    avgCost: Union[str, int, float, None] = None
    boughtOn: Union[str, None] = Field(default=None, max_length=40)

    @field_validator("units", "invested", "avgCost")
    @classmethod
    def short(cls, v: Any) -> Any:
        if isinstance(v, str) and len(v) > 40:
            raise ValueError("too long")
        return v


class AddIn(LotIn):
    code: int = Field(ge=1, lt=10 ** 7)
    folio: str = Field(default="", max_length=60)
    follow: bool = False       # true: only the fund is given (no units, cost or date): it is followed; a missing units figure without this is still refused


class UpdateIn(BaseModel):
    folio: Optional[str] = Field(default=None, max_length=60)
    lots: List[LotIn] = Field(min_length=1, max_length=MAX_LOTS)


def lot_of(l: LotIn) -> Tuple[Decimal, Optional[Decimal], Optional[date]]:
    try:
        return strict_lot(l.units, l.invested, l.avgCost, l.boughtOn)
    except ValueError as e:
        raise fail(422, "invalid_holding", str(e))


async def lock_member(conn, user_id: str) -> None:
    """One write at a time per member, so two requests cannot both squeeze under the plan's limit."""
    await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"mfp:{user_id}")


async def ensure_scheme(conn, code: int) -> None:
    if not await conn.fetchval("SELECT 1 FROM mf_schemes WHERE code = $1", code):
        raise fail(404, "unknown_scheme", "No mutual fund scheme has this code.")


@router.post("", status_code=201)
async def add_holding(request: Request, body: AddIn, ctx: Ctx = Depends(member_ctx)):
    await limit(request, "mfpw", ctx.user_id, 120, 600)
    follow = body.follow and body.units is None and body.invested is None and body.avgCost is None and body.boughtOn is None   # asked for, with nothing else given: the fund is followed, with no units or cost
    units, invested, bought = (None, None, None) if follow else lot_of(body)
    folio = clean_folio(body.folio)
    async with request.app.state.store.pool.acquire() as conn:
        async with conn.transaction():
            await lock_member(conn, ctx.user_id)
            await ensure_scheme(conn, body.code)
            hid = await conn.fetchval("SELECT id FROM mf_holdings WHERE user_id = $1 AND code = $2 AND folio = $3", ctx.user_id, body.code, folio)
            merged = hid is not None
            if hid is None:
                used = await conn.fetchval("SELECT count(*) FROM mf_holdings WHERE user_id = $1", ctx.user_id)
                if used >= cap_for(ctx):
                    raise fail(403, "plan_limit", f"Your plan includes {cap_for(ctx)} funds.", plan="gold")
                hid = await conn.fetchval("INSERT INTO mf_holdings (user_id, code, folio) VALUES ($1, $2, $3) RETURNING id", ctx.user_id, body.code, folio)
            elif follow:
                return reply({"status": "saved", "id": str(hid), "merged": True}, 201)            # already in the list: nothing to add
            elif await conn.fetchval("SELECT count(*) FROM mf_holding_lots WHERE holding_id = $1", hid) >= MAX_LOTS:
                raise fail(403, "plan_limit", f"A holding keeps up to {MAX_LOTS} purchases.")
            if not follow:
                await conn.execute("INSERT INTO mf_holding_lots (holding_id, units, invested, bought_on) VALUES ($1, $2, $3, $4)", hid, units, invested, bought)
            await conn.execute("UPDATE mf_holdings SET updated_at = now() WHERE id = $1", hid)
    return reply({"status": "saved", "id": str(hid), "merged": merged}, 201)


@router.put("/{hid}")
async def update_holding(request: Request, hid: str, body: UpdateIn, ctx: Ctx = Depends(member_ctx)):
    await limit(request, "mfpw", ctx.user_id, 120, 600)
    h = uid_of(hid)
    lots = [lot_of(l) for l in body.lots]
    async with request.app.state.store.pool.acquire() as conn:
        async with conn.transaction():
            await lock_member(conn, ctx.user_id)
            row = await conn.fetchrow("SELECT id, code, folio FROM mf_holdings WHERE id = $1 AND user_id = $2", h, ctx.user_id)
            if row is None:
                raise fail(404, "not_found", "No such holding.")
            folio = row["folio"] if body.folio is None else clean_folio(body.folio)
            if folio != row["folio"]:
                if await conn.fetchval("SELECT 1 FROM mf_holdings WHERE user_id = $1 AND code = $2 AND folio = $3 AND id <> $4", ctx.user_id, row["code"], folio, h):
                    raise fail(409, "duplicate_holding", "You already hold this fund under that folio. Edit that holding instead.")
                await conn.execute("UPDATE mf_holdings SET folio = $2 WHERE id = $1", h, folio)
            await conn.execute("DELETE FROM mf_holding_lots WHERE holding_id = $1", h)
            await conn.executemany("INSERT INTO mf_holding_lots (holding_id, units, invested, bought_on) VALUES ($1, $2, $3, $4)", [(h, u, i, d) for u, i, d in lots])
            await conn.execute("UPDATE mf_holdings SET updated_at = now() WHERE id = $1", h)
    return reply({"status": "saved", "id": str(h)})


@router.delete("/{hid}")
async def delete_holding(request: Request, hid: str, ctx: Ctx = Depends(member_ctx)):
    await limit(request, "mfpw", ctx.user_id, 120, 600)
    h = uid_of(hid)
    async with request.app.state.store.pool.acquire() as conn:
        n = int((await conn.execute("DELETE FROM mf_holdings WHERE id = $1 AND user_id = $2", h, ctx.user_id)).split()[-1])
    if not n:
        raise fail(404, "not_found", "No such holding.")
    return reply({"status": "deleted"})


# ------------------------------------------------------------------------------------------------------------------------ import

Cell = Union[str, int, float, None]


class RawRow(BaseModel):
    """One row of the file, the cells the browser mapped to our columns, as written. The server reads what they mean (parse.clean_row)."""
    row: int = Field(default=0, ge=0, le=10 ** 7)
    name: Cell = None
    isin: Cell = None
    amfi: Cell = None
    folio: Cell = None
    units: Cell = None
    avgCost: Cell = None
    invested: Cell = None
    current: Cell = None
    nav: Cell = None
    date: Cell = None
    kind: Cell = None

    @field_validator("name", "isin", "amfi", "folio", "units", "avgCost", "invested", "current", "nav", "date", "kind")
    @classmethod
    def cell(cls, v: Any) -> Any:
        if isinstance(v, str) and len(v) > CELL_MAX:
            raise ValueError("cell too long")
        return v


class PreviewIn(BaseModel):
    rows: List[RawRow] = Field(max_length=MAX_IMPORT_ROWS)


class CommitItem(BaseModel):
    code: int = Field(ge=1, lt=10 ** 7)
    folio: str = Field(default="", max_length=60)
    units: Union[str, int, float, None] = None
    invested: Union[str, int, float, None] = None
    boughtOn: Optional[str] = Field(default=None, max_length=40)


class CommitIn(BaseModel):
    items: List[CommitItem] = Field(min_length=1, max_length=MAX_IMPORT_ROWS)
    existing: Literal["skip", "replace"] = "skip"


def fund_view(s) -> Dict[str, Any]:
    return s.view()


@router.post("/import-preview")
async def import_preview(request: Request, body: PreviewIn, ctx: Ctx = Depends(member_ctx)):
    await limit(request, "mfpi", ctx.user_id, 30, 600)
    ix = await scheme_index(request)
    async with request.app.state.store.pool.acquire() as conn:
        have = {(r["code"], r["folio"]) for r in await conn.fetch("SELECT code, folio FROM mf_holdings WHERE user_id = $1", ctx.user_id)}
    out: List[Dict[str, Any]] = []
    seen: Dict[Tuple, int] = {}
    counts = defaultdict(int)
    for i, raw in enumerate(body.rows):
        c = clean_row(raw.model_dump())
        if isinstance(c, Rejected):
            out.append({"i": i, "row": c.row, "name": c.name, "isin": c.isin, "status": c.status, "reason": c.reason, "fund": None, "candidates": [], "warnings": []})
            counts[c.status] += 1
            continue
        m = match_row(ix, c)
        item: Dict[str, Any] = {"i": i, "row": c.row, "name": c.name, "isin": c.isin, "amfi": c.amfi, "folio": c.folio, "units": float(c.units),
                                "invested": float(c.invested) if c.invested is not None else None, "boughtOn": c.bought_on.isoformat() if c.bought_on else None,
                                "status": m.status, "via": m.via, "reason": m.reason, "warnings": c.warnings,
                                "fund": fund_view(m.scheme) if m.scheme and m.status == "matched" else None,
                                "suggested": fund_view(m.scheme) if m.scheme and m.status == "choose" else None,
                                "candidates": [fund_view(s) for s in (m.candidates or [])], "existing": False}
        if m.status == "matched":
            key = (m.scheme.code, c.folio, c.units, c.invested, c.bought_on)
            if key in seen:
                item.update(status="duplicate", reason=f"The same line as row {seen[key]} of the file (same fund, folio, units, amount and date): counted once.", fund=None)
            else:
                seen[key] = c.row or i + 1
                item["existing"] = (m.scheme.code, c.folio) in have
        counts[item["status"]] += 1
        out.append(item)
    used = len(have)
    return reply({"rows": out, "counts": {k: counts.get(k, 0) for k in ("matched", "choose", "not_found", "ignored", "invalid", "duplicate")}, "total": len(out),
                  "capacity": {"limit": cap_for(ctx), "used": used, "room": max(0, cap_for(ctx) - used)}, "disclaimer": DISCLAIMER})


@router.post("/import-commit")
async def import_commit(request: Request, body: CommitIn, ctx: Ctx = Depends(member_ctx)):
    await limit(request, "mfpc", ctx.user_id, 20, 600)
    groups: Dict[Tuple[int, str], List[Tuple[Decimal, Optional[Decimal], Optional[date]]]] = {}
    dupes = 0
    for n, it in enumerate(body.items, 1):
        try:
            lot = strict_lot(it.units, it.invested, None, it.boughtOn)
        except ValueError as e:
            raise fail(422, "invalid_row", f"Line {n}: {e}")
        g = groups.setdefault((it.code, clean_folio(it.folio)), [])
        if lot in g:
            dupes += 1
            continue
        g.append(lot)
    if any(len(g) > MAX_LOTS for g in groups.values()):
        raise fail(422, "too_many_lots", f"A holding keeps up to {MAX_LOTS} purchases.")
    added = replaced = skipped = 0
    async with request.app.state.store.pool.acquire() as conn:
        async with conn.transaction():
            await lock_member(conn, ctx.user_id)
            known = {r["code"] for r in await conn.fetch("SELECT code FROM mf_schemes WHERE code = ANY($1::int[])", sorted({c for c, _ in groups}))}
            bad = sorted({c for c, _ in groups} - known)
            if bad:
                raise fail(422, "unknown_scheme", f"Unknown scheme code {bad[0]}. Every row needs a fund chosen from the review.")
            have = {(r["code"], r["folio"]): r["id"] for r in await conn.fetch("SELECT id, code, folio FROM mf_holdings WHERE user_id = $1", ctx.user_id)}
            fresh = [k for k in groups if k not in have]
            cap = cap_for(ctx)
            if len(have) + len(fresh) > cap:
                raise fail(403, "plan_limit", f"Your plan includes {cap} funds. You hold {len(have)} and this import adds {len(fresh)} more. Remove some rows from the review.", plan="gold")
            for key, lots in groups.items():
                hid = have.get(key)
                if hid is not None and body.existing == "skip":
                    skipped += 1
                    continue
                if hid is None:
                    hid = await conn.fetchval("INSERT INTO mf_holdings (user_id, code, folio) VALUES ($1, $2, $3) RETURNING id", ctx.user_id, key[0], key[1])
                    added += 1
                else:
                    await conn.execute("DELETE FROM mf_holding_lots WHERE holding_id = $1", hid)
                    await conn.execute("UPDATE mf_holdings SET updated_at = now() WHERE id = $1", hid)
                    replaced += 1
                await conn.executemany("INSERT INTO mf_holding_lots (holding_id, units, invested, bought_on) VALUES ($1, $2, $3, $4)", [(hid, u, i, d) for u, i, d in lots])
    return reply({"status": "saved", "added": added, "replaced": replaced, "skipped": skipped, "duplicates": dupes}, 201)
