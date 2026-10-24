"""Query builder endpoints: type a query, get the companies that match; keep queries as named baskets.

POST /api/screener/ql/validate   parse and check only: every problem with its position, the ratios found, and how we read the query
POST /api/screener/ql/run        the matching companies (columns = the ratios used + market cap + price), sortable and paged
POST /api/screener/ql/export     the same as a CSV file (Silver)
GET  /api/screener/ql/ratios     every ratio with its names, unit, plan, definition and an example
GET/POST/PUT/DELETE /api/screener/baskets...   the member's saved queries

The language and its errors are in ql.py; the evaluation (three-valued, missing data never matches) in qeval.py. The website only draws what it is sent.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import time
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from ..auth.routes import NO_STORE, Ctx, fail, secure_ctx
from ..auth.service import current
from ..auth.routes import limits_for
from .api import BASIC_ROWS, DEFAULT_COLUMNS
from .catalog import BY_KEY, CATALOG, GROUP_LABEL, allowed
from .data import Table, get_table
from .qaliases import ALIAS, definition, display_names
from .ql import MAX_CHARS, MAX_CONDITIONS, TIER_NAME, Analysis, Problem, analyze, canonical, count_conditions, fmt_in, metrics_in, reading
from .qeval import data_warnings, run

router = APIRouter(prefix="/api/screener")
UNIT_LABEL = {"Cr": "₹ crore", "Rs": "₹", "%": "%", "x": "times", "d": "days", "n": "count", "pts": "points", "flag": "yes / no"}
OPERATORS = [
    {"op": ">", "say": "greater than"}, {"op": ">=", "say": "at least"}, {"op": "<", "say": "less than"}, {"op": "<=", "say": "at most"},
    {"op": "=", "say": "equal to"}, {"op": "!=", "say": "not equal to"},
]
# Starter queries. Every one is checked against the real catalogue by the tests, so none can name a ratio we do not have.
EXAMPLES = [
    {"id": "large-profitable", "title": "Large and profitable", "about": "Big companies earning a good return on the owners' money.", "query": "Market cap > 50000 Cr\nROE > 15"},
    {"id": "quality", "title": "Quality compounders", "about": "High return on capital, steady growth, little debt.", "query": "ROCE > 20\nSales growth 5 years > 12\nDebt to equity < 0.5"},
    {"id": "low-debt-growth", "title": "Low debt, growing profit", "about": "Profit compounding for 5 years while borrowing little.", "query": "Debt to equity < 0.3\nProfit growth 5 years > 15\nInterest coverage > 5"},
    {"id": "value", "title": "Value", "about": "Priced low against earnings and book value, with a decent return.", "query": "P/E < 15 AND P/B < 2 AND ROE > 12"},
    {"id": "dividend", "title": "High dividend", "about": "Pays out a good yield without stretching its profit.", "query": "Dividend yield > 3\nDividend payout < 70\nDebt to equity < 1"},
    {"id": "own-history", "title": "Cheaper than its own past", "about": "P/E below its own 5-year average.", "query": "P/E < P/E 5 year average\nROE > 12"},
    {"id": "promoters", "title": "Promoters hold a lot", "about": "High promoter holding and a dividend paid.", "query": "Promoter holding > 60\nPays a dividend = yes"},
    {"id": "small-clean", "title": "Small and clean", "about": "Small companies with low debt and a high return on capital.", "query": "Market cap < 5000 Cr AND Debt to equity < 0.5 AND ROCE > 18"},
    {"id": "either", "title": "Cheap or fast-growing", "about": "Shows OR with brackets: either a low P/E or fast sales growth, with low debt.", "query": "(P/E < 12 OR Sales growth 3 years > 25)\nDebt to equity < 1"},
]


def plan_of(ctx) -> str:
    return ctx.plan if ctx.authed else "basic"


async def _table(request: Request) -> Table:
    return await get_table(request.app.state.store)


def _json(body: Any, status: int = 200) -> Response:
    return Response(content=json.dumps(body, separators=(",", ":")), status_code=status, media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


def _split(a: Analysis) -> Dict[str, Any]:
    return {"errors": [p.to_dict(a.text) for p in a.problems if p.severity == "error"], "warnings": [p.to_dict(a.text) for p in a.problems if p.severity != "error"]}


def _metric_info(key: str, plan: str) -> dict:
    m = BY_KEY[key]
    return {"key": key, "label": m.label, "unit": m.unit, "unitLabel": UNIT_LABEL[m.unit], "tier": m.tier, "locked": not allowed(plan, m.tier), "digits": m.digits}


def describe(a: Analysis, plan: str) -> dict:
    """What validate says about a query."""
    body: Dict[str, Any] = {"ok": a.ok, **_split(a), "limits": {"chars": MAX_CHARS, "conditions": MAX_CONDITIONS}, "plan": plan}
    if a.root is not None:
        body["metrics"] = [_metric_info(k, plan) for k in metrics_in(a.root)]
        body["conditions"] = count_conditions(a.root)
        if a.ok:
            body["reading"] = reading(a.root)
            body["canonical"] = canonical(a.root)
    else:
        body["metrics"], body["conditions"] = [], 0
    return body


class Sort(BaseModel):
    key: str = Field(default="market_cap", max_length=40)
    dir: Literal["asc", "desc"] = "desc"


class QueryIn(BaseModel):
    query: str = Field(default="", max_length=20000)


class RunIn(QueryIn):
    sort: Optional[Sort] = None
    columns: List[str] = Field(default_factory=list, max_length=40)
    recent: bool = False
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=50, ge=1, le=100)


@router.post("/ql/validate")
async def validate(request: Request, body: QueryIn):
    plan = plan_of(await current(request))
    return _json(describe(analyze(body.query, plan), plan))


def _problem(code: str, message: str) -> dict:
    return {"code": code, "severity": "error", "message": message, "start": 0, "end": 0, "line": 1, "col": 1, "text": "", "fixes": []}


def _prepare(t: Table, body: RunIn, plan: str):
    """(analysis, columns, sort key, descending, error list). Errors are returned, never raised: the page shows them next to the query."""
    a = analyze(body.query, plan)
    errors = [p.to_dict(a.text) for p in a.problems if p.severity == "error"]
    warnings = [p.to_dict(a.text) for p in a.problems if p.severity != "error"]
    cols: List[str] = []
    if a.ok:
        cols = list(DEFAULT_COLUMNS) + [k for k in metrics_in(a.root) if k not in DEFAULT_COLUMNS]
    for k in body.columns:
        if k not in BY_KEY:
            errors.append(_problem("unknown_column", f"We don't have a column called '{k}'."))
        elif not allowed(plan, BY_KEY[k].tier):
            tier = TIER_NAME[BY_KEY[k].tier]
            errors.append({**_problem("plan_locked", f"The column {BY_KEY[k].label} is part of the {tier} plan."), "plan": BY_KEY[k].tier})
        elif k not in cols:
            cols.append(k)
    sort = body.sort or Sort()
    if sort.key not in ("name", "symbol") and sort.key not in BY_KEY:
        errors.append(_problem("unknown_sort", "We can't sort by that."))
    elif sort.key in BY_KEY and not allowed(plan, BY_KEY[sort.key].tier):
        errors.append({**_problem("plan_locked", f"Sorting by {BY_KEY[sort.key].label} is part of the {TIER_NAME[BY_KEY[sort.key].tier]} plan."), "plan": BY_KEY[sort.key].tier})
    if body.recent and t.latest_quarter() is None:
        errors.append(_problem("recent_unavailable", "We can't tell which quarter is the latest yet, so 'only recent results' is off for now."))
    return a, cols, sort, errors, warnings


def _execute(t: Table, body: RunIn, plan: str) -> Dict[str, Any]:
    started = time.perf_counter()
    a, cols, sort, errors, warnings = _prepare(t, body, plan)
    if errors or not a.ok:
        return {"ok": False, "errors": errors, "warnings": warnings}
    res = run(t, a.root, body.recent)
    warnings += [p.to_dict(a.text) for p in data_warnings(t, a.root)]
    idx = t.sort(res.index, sort.key, sort.dir == "desc")
    total = len(idx)
    capped = plan == "basic" and total > BASIC_ROWS
    lim = min(body.limit, BASIC_ROWS) if plan == "basic" else body.limit
    off = 0 if plan == "basic" else body.offset
    out = {
        "ok": True, "total": total, "offset": off, "limit": lim, "capped": capped, "columns": cols, "sort": {"key": sort.key, "dir": sort.dir},
        "rows": [t.row(i, cols) for i in idx[off: off + lim]], "warnings": warnings, "reading": reading(a.root), "canonical": canonical(a.root),
        "universe": t.n, "withReport": t.n_full,
        "leftOut": {"total": len(res.unknown), "divisionByZero": res.divzero, "metrics": res.per_metric},
        "recent": res.recent, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t.loaded)),
    }
    out["took"] = round((time.perf_counter() - started) * 1000, 1)
    return out


@router.post("/ql/run")
async def run_query(request: Request, body: RunIn):
    plan = plan_of(await current(request))
    t = await _table(request)
    return _json(await asyncio.to_thread(_execute, t, body, plan))


def _cell(v: Any) -> Any:
    return ("'" + v) if isinstance(v, str) and v[:1] in "=+-@" else v    # a company name must never run as a spreadsheet formula


@router.post("/ql/export")
async def export(request: Request, body: RunIn):
    plan = plan_of(await current(request))
    if not allowed(plan, "silver"):
        raise fail(403, "plan_required", "Downloading results is part of the Silver plan.", plan="silver")
    t = await _table(request)
    a, cols, sort, errors, _ = _prepare(t, body, plan)
    if errors or not a.ok:
        raise fail(422, "invalid_query", "Fix the problems in the query first.", errors=errors)
    res = await asyncio.to_thread(run, t, a.root, body.recent)
    idx = t.sort(res.index, sort.key, sort.dir == "desc")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Symbol", "Company", "Sector", "Size"] + [BY_KEY[c].label + (f" ({BY_KEY[c].unit})" if BY_KEY[c].unit not in ("flag", "n", "pts") else "") for c in cols])
    for i in idx[:10000]:
        r = t.row(i, cols)
        w.writerow([r["symbol"], _cell(r["name"]), r["sector"] or "", r["cap"] or ""] + ["" if r["v"][c] is None else r["v"][c] for c in cols])
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8", headers={**NO_STORE, "Content-Disposition": 'attachment; filename="finlit-query.csv"'})


def _nice(x: float) -> str:
    if x == 0:
        return "0"
    mag = 10 ** (len(str(int(abs(x)))) - 1) if abs(x) >= 10 else (1 if abs(x) >= 1 else 0.1)
    step = mag / 2 if abs(x) >= 10 else mag
    return f"{round(x / step) * step:g}"


def _example(key: str, t: Table) -> str:
    m = BY_KEY[key]
    label = m.label
    if m.unit == "flag":
        return f"{label} = yes"
    st = t.stats.get(key)
    mid = st["p50"] if st else 10
    val = _nice(mid)
    op = "<" if m.better == "lower" else ">"
    return f"{label} {op} {val}{' Cr' if m.unit == 'Cr' else ''}"


_ratios_cache: Dict[Any, Any] = {}


@router.get("/ql/ratios")
async def ratios(request: Request):
    """Every ratio a query can use, for the 'Show all ratios' drawer, the autocomplete and the 'Add a condition' helper."""
    plan = plan_of(await current(request))
    t = await _table(request)
    ck = (plan, t.loaded)
    if ck not in _ratios_cache:
        _ratios_cache.clear()
        items = []
        for m in CATALOG:
            items.append({**_metric_info(m.key, plan), "group": m.group, "groupLabel": GROUP_LABEL[m.group], "better": m.better, "names": display_names(m.key),
                          "definition": definition(m.key), "example": _example(m.key, t), "stats": ({k: t.stats[m.key][k] for k in ("min", "p10", "p50", "p90", "max")} if m.key in t.stats else None)})
        q = t.latest_quarter()
        examples = []
        for ex in EXAMPLES:
            a = analyze(ex["query"], plan)
            need = max((BY_KEY[k].tier for k in metrics_in(a.root)), key=lambda x: ["basic", "silver", "gold"].index(x)) if a.root else "basic"
            examples.append({**ex, "plan": need, "locked": not allowed(plan, need)})
        _ratios_cache[ck] = {
            "ratios": items, "operators": OPERATORS, "examples": examples, "plan": plan, "aliases": len(ALIAS),
            "limits": {"chars": MAX_CHARS, "conditions": MAX_CONDITIONS, "rows": BASIC_ROWS if plan == "basic" else None, "export": allowed(plan, "silver")},
            "recentResults": {"available": q is not None, "quarterEnd": q, "companies": sum(1 for x in t.q_end if q is not None and x == q)},
            "total": t.n, "withReport": t.n_full, "defaultColumns": DEFAULT_COLUMNS,
        }
    return _json(_ratios_cache[ck])


# ------------------------------------------------------------------------------------------------------------------------------ baskets
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
COUNT_BUDGET = 2.0      # seconds a basket list may spend counting; the rest show their last count, marked stale
_counts: Dict[Any, Any] = {}


class BasketIn(BaseModel):
    name: str = Field(max_length=200)
    query: str = Field(max_length=20000)
    note: Optional[str] = Field(default=None, max_length=300)
    columns: List[str] = Field(default_factory=list, max_length=12)
    sort: Optional[Sort] = None
    recent: bool = False


class BasketPatch(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    query: Optional[str] = Field(default=None, max_length=20000)
    note: Optional[str] = Field(default=None, max_length=300)
    columns: Optional[List[str]] = Field(default=None, max_length=12)
    sort: Optional[Sort] = None
    recent: Optional[bool] = None


class DuplicateIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not 1 <= len(name) <= 80:
        raise fail(422, "bad_name", "Give the basket a name of up to 80 characters.")
    return name


def _check_columns(cols: List[str], plan: str) -> List[str]:
    out: List[str] = []
    for k in cols:
        if k not in BY_KEY:
            raise fail(422, "bad_column", f"We don't have a column called '{k}'.")
        if not allowed(plan, BY_KEY[k].tier):
            raise fail(403, "plan_required", f"The column {BY_KEY[k].label} is part of the {TIER_NAME[BY_KEY[k].tier]} plan.", plan=BY_KEY[k].tier)
        if k not in out:
            out.append(k)
    return out


def _check_query(query: str, plan: str) -> None:
    a = analyze(query, plan)
    if not a.ok:
        errs = [p.to_dict(a.text) for p in a.problems if p.severity == "error"]
        locked = [e for e in errs if e["code"] == "plan_locked"]
        raise fail(403 if locked and len(locked) == len(errs) else 422, "plan_required" if locked and len(locked) == len(errs) else "invalid_query",
                   (locked[0]["message"] if locked and len(locked) == len(errs) else "This query has problems. Fix them before saving it as a basket."), errors=errs,
                   **({"plan": locked[0]["plan"]} if locked and len(locked) == len(errs) else {}))


def _parse_json(v: Any, default: Any) -> Any:
    if v is None:
        return default
    return json.loads(v) if isinstance(v, str) else v


def _count_one(t: Table, plan: str, query: str, recent: bool) -> Dict[str, Any]:
    key = (t.loaded, plan, query, recent)
    if key in _counts:
        return _counts[key]
    a = analyze(query, plan)
    if not a.ok:
        locked = any(p.code == "plan_locked" for p in a.problems)
        out = {"status": "locked" if locked else "invalid", "count": None, "problems": len([p for p in a.problems if p.severity == "error"])}
    else:
        try:
            res = run(t, a.root, recent)
            out = {"status": "ok", "count": len(res.index), "leftOut": len(res.unknown)}
        except ValueError:
            out = {"status": "invalid", "count": None, "problems": 1}
    if len(_counts) > 2000:
        _counts.clear()
    _counts[key] = out
    return out


def _view(r, count: Optional[Dict[str, Any]] = None, stale: bool = False) -> Dict[str, Any]:
    out = {"id": str(r["id"]), "name": r["name"], "query": r["query"], "note": r["note"], "columns": _parse_json(r["columns"], []), "sort": _parse_json(r["sort"], None),
           "recent": r["recent"], "createdAt": r["created_at"].isoformat(), "updatedAt": r["updated_at"].isoformat(),
           "count": r["last_count"], "countedAt": r["counted_at"].isoformat() if r["counted_at"] else None, "status": "ok", "stale": True}
    if count is not None and not stale:
        out.update({"count": count["count"], "status": count["status"], "leftOut": count.get("leftOut"), "stale": False})
    return out


COLS = "id, name, query, note, columns, sort, recent, last_count, counted_at, created_at, updated_at"


async def _owned(conn, ctx: Ctx, basket_id: str):
    if not UUID.match(basket_id):
        raise fail(404, "not_found", "That basket was not found.")
    row = await conn.fetchrow(f"SELECT {COLS} FROM query_baskets WHERE id = $1 AND user_id = $2", basket_id, ctx.user_id)
    if not row:
        raise fail(404, "not_found", "That basket was not found.")
    return row


@router.get("/baskets")
async def list_baskets(request: Request, ctx: Ctx = Depends(secure_ctx)):
    t = await _table(request)
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT {COLS} FROM query_baskets WHERE user_id = $1 ORDER BY updated_at DESC", ctx.user_id)
        started, out, fresh = time.perf_counter(), [], []
        for r in rows:
            over = time.perf_counter() - started > COUNT_BUDGET
            c = None if over else await asyncio.to_thread(_count_one, t, ctx.plan, r["query"], r["recent"])
            v = _view(r, c, stale=over)
            if c and c["status"] == "ok" and c["count"] != r["last_count"]:
                fresh.append((r["id"], c["count"]))
            out.append(v)
        for bid, n in fresh:
            await conn.execute("UPDATE query_baskets SET last_count = $2, counted_at = now() WHERE id = $1", bid, n)
    return _json({"baskets": out, "max": limits_for(ctx.plan)["baskets"], "plan": ctx.plan})


@router.get("/baskets/{basket_id}")
async def get_basket(request: Request, basket_id: str, ctx: Ctx = Depends(secure_ctx)):
    t = await _table(request)
    async with request.app.state.store.pool.acquire() as conn:
        r = await _owned(conn, ctx, basket_id)
    return _json({"basket": _view(r, await asyncio.to_thread(_count_one, t, ctx.plan, r["query"], r["recent"]))})


async def _insert(conn, ctx: Ctx, name: str, query: str, note: Optional[str], columns: List[str], sort: Optional[dict], recent: bool):
    cap = limits_for(ctx.plan)["baskets"]
    async with conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "query_baskets:" + str(ctx.user_id))     # two quick saves cannot pass the limit
        if await conn.fetchval("SELECT count(*) FROM query_baskets WHERE user_id = $1", ctx.user_id) >= cap:
            raise fail(403, "limit", f"Your plan keeps {cap} baskets. Delete one first, or upgrade for more.", max=cap)
        if await conn.fetchval("SELECT 1 FROM query_baskets WHERE user_id = $1 AND lower(name) = lower($2)", ctx.user_id, name):
            raise fail(409, "name_taken", f"You already have a basket called '{name}'. Pick another name.")
        return await conn.fetchrow(
            f"INSERT INTO query_baskets (user_id, name, query, note, columns, sort, recent) VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7) RETURNING {COLS}",
            ctx.user_id, name, query, note, json.dumps(columns), json.dumps(sort) if sort else None, recent)


@router.post("/baskets")
async def create_basket(request: Request, body: BasketIn, ctx: Ctx = Depends(secure_ctx)):
    name = clean_name(body.name)
    _check_query(body.query, ctx.plan)
    cols = _check_columns(body.columns, ctx.plan)
    t = await _table(request)
    async with request.app.state.store.pool.acquire() as conn:
        r = await _insert(conn, ctx, name, body.query, (body.note or "").strip() or None, cols, body.sort.model_dump() if body.sort else None, body.recent)
    return _json({"basket": _view(r, await asyncio.to_thread(_count_one, t, ctx.plan, r["query"], r["recent"]))}, 201)


@router.put("/baskets/{basket_id}")
async def update_basket(request: Request, basket_id: str, body: BasketPatch, ctx: Ctx = Depends(secure_ctx)):
    t = await _table(request)
    async with request.app.state.store.pool.acquire() as conn:
        cur = await _owned(conn, ctx, basket_id)
        name = clean_name(body.name) if body.name is not None else cur["name"]
        query = body.query if body.query is not None else cur["query"]
        if body.query is not None:
            _check_query(query, ctx.plan)
        cols = _check_columns(body.columns, ctx.plan) if body.columns is not None else _parse_json(cur["columns"], [])
        note = ((body.note or "").strip() or None) if body.note is not None else cur["note"]
        sort = body.sort.model_dump() if body.sort else _parse_json(cur["sort"], None)
        recent = cur["recent"] if body.recent is None else body.recent
        if name.lower() != cur["name"].lower() and await conn.fetchval("SELECT 1 FROM query_baskets WHERE user_id = $1 AND lower(name) = lower($2)", ctx.user_id, name):
            raise fail(409, "name_taken", f"You already have a basket called '{name}'. Pick another name.")
        r = await conn.fetchrow(
            f"UPDATE query_baskets SET name = $3, query = $4, note = $5, columns = $6::jsonb, sort = $7::jsonb, recent = $8, updated_at = now() "
            f"WHERE id = $1 AND user_id = $2 RETURNING {COLS}", basket_id, ctx.user_id, name, query, note, json.dumps(cols), json.dumps(sort) if sort else None, recent)
    return _json({"basket": _view(r, await asyncio.to_thread(_count_one, t, ctx.plan, r["query"], r["recent"]))})


@router.post("/baskets/{basket_id}/duplicate")
async def duplicate_basket(request: Request, basket_id: str, body: DuplicateIn, ctx: Ctx = Depends(secure_ctx)):
    t = await _table(request)
    async with request.app.state.store.pool.acquire() as conn:
        cur = await _owned(conn, ctx, basket_id)
        names = {r["lower"] for r in await conn.fetch("SELECT lower(name) FROM query_baskets WHERE user_id = $1", ctx.user_id)}
        if body.name:
            name = clean_name(body.name)
        else:
            base, n = f"Copy of {cur['name']}"[:76], 1
            name = base
            while name.lower() in names:
                n += 1
                name = f"{base} ({n})"
        r = await _insert(conn, ctx, name, cur["query"], cur["note"], _parse_json(cur["columns"], []), _parse_json(cur["sort"], None), cur["recent"])
    return _json({"basket": _view(r, await asyncio.to_thread(_count_one, t, ctx.plan, r["query"], r["recent"]))}, 201)


@router.delete("/baskets/{basket_id}")
async def delete_basket(request: Request, basket_id: str, ctx: Ctx = Depends(secure_ctx)):
    if not UUID.match(basket_id):
        raise fail(404, "not_found", "That basket was not found.")
    async with request.app.state.store.pool.acquire() as conn:
        done = await conn.execute("DELETE FROM query_baskets WHERE id = $1 AND user_id = $2", basket_id, ctx.user_id)
    if done.endswith(" 0"):
        raise fail(404, "not_found", "That basket was not found.")
    return {"status": "deleted"}
