"""Screener endpoints. The filters, the plan check and the answer all live here: the website only draws what it is sent."""

from __future__ import annotations

import csv
import io
import time
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from ..auth.routes import NO_STORE, fail
from ..auth.service import current
from .catalog import BY_KEY, CAPS, CATALOG, GROUP_LABEL, GROUPS, HIDDEN, INDEX_LISTS, VARIANTS, allowed
from .data import get_table

router = APIRouter(prefix="/api/screener")
BASIC_ROWS = 25
# The table opens with company, market cap and price only; the website adds a column for each filter the visitor adds (and takes it away with the filter).
DEFAULT_COLUMNS = ["market_cap", "price"]


class Rng(BaseModel):
    min: Optional[float] = Field(default=None, ge=-1e12, le=1e12)
    max: Optional[float] = Field(default=None, ge=-1e12, le=1e12)


class Cats(BaseModel):
    sector: List[str] = Field(default_factory=list, max_length=40)
    industry: List[str] = Field(default_factory=list, max_length=60)
    index: List[str] = Field(default_factory=list, max_length=20)
    cap: List[Literal["Large", "Mid", "Small"]] = Field(default_factory=list, max_length=3)
    band: List[Literal["strong", "healthy", "mixed", "watch"]] = Field(default_factory=list, max_length=4)


class Sort(BaseModel):
    key: str = Field(default="market_cap", max_length=40)
    dir: Literal["asc", "desc"] = "desc"


class Query_(BaseModel):
    filters: Dict[str, Rng] = Field(default_factory=dict, max_length=60)
    cats: Cats = Field(default_factory=Cats)
    q: str = Field(default="", max_length=60)
    sort: Sort = Field(default_factory=Sort)
    columns: List[str] = Field(default_factory=list, max_length=40)
    offset: int = Field(default=0, ge=0, le=10000)
    limit: int = Field(default=50, ge=1, le=100)

    @field_validator("filters")
    @classmethod
    def known(cls, v: Dict[str, Rng]) -> Dict[str, Rng]:
        for k in v:
            if k not in BY_KEY:
                raise ValueError(f"unknown filter {k}")
        return v


def _plan(ctx) -> str:
    return ctx.plan if ctx.authed else "basic"


def _locked(plan: str, keys: List[str]) -> Dict[str, str]:
    return {k: BY_KEY[k].tier for k in keys if k in BY_KEY and not allowed(plan, BY_KEY[k].tier)}


def _refuse(locked: Dict[str, str], what: str):
    tier = "gold" if "gold" in locked.values() else "silver"
    names = ", ".join(BY_KEY[k].label for k in list(locked)[:3])
    return fail(403, "plan_required", f"{what} {names} {'is' if len(locked) == 1 else 'are'} part of the {tier.title()} plan.", plan=tier, keys=list(locked))


def _table(request: Request):
    return get_table(request.app.state.store)


@router.get("/catalog")
async def catalog(request: Request):
    """Every filter, grouped, with its plan, a plain-words hint and where companies sit (for sliders and placeholders)."""
    ctx = await current(request)
    plan = _plan(ctx)
    t = await _table(request)
    groups = []
    for gid, label in GROUPS:
        ms = [m for m in CATALOG if m.group == gid]
        groups.append({"id": gid, "label": label, "tier": "gold" if gid == "model" else "basic", "metrics": [
            {"key": m.key, "label": m.label, "unit": m.unit, "better": m.better, "tier": m.tier, "say": m.say, "digits": m.digits,
             "locked": not allowed(plan, m.tier), "stats": t.stats.get(m.key), "hidden": m.key in HIDDEN, "variants": VARIANTS.get(m.key)} for m in ms]})
    body = {
        "plan": plan, "total": t.n, "withReport": t.n_full, "updatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t.loaded)),
        "groups": groups,
        "sectors": [{"name": n, "n": c} for n, c in t.sectors],
        "industries": [{"name": n, "sector": s, "n": c} for n, s, c in t.industries],
        "indices": [{"code": c, "label": INDEX_LISTS[c][0], "n": len(t.members.get(c, ()))} for c in INDEX_LISTS if t.members.get(c)],
        "caps": [{"name": c, "n": sum(1 for x in t.cap if x == c)} for c in CAPS],
        "bands": [{"key": b, "label": b.title(), "locked": not allowed(plan, "gold")} for b in ("strong", "healthy", "mixed", "watch")],
        "limits": {"rows": BASIC_ROWS if plan == "basic" else None, "export": allowed(plan, "silver")},
        "defaultColumns": DEFAULT_COLUMNS,
    }
    return Response(content=__import__("json").dumps(body, separators=(",", ":")), media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


def _run(t, body: Query_, plan: str):
    filters = {k: v.model_dump() for k, v in body.filters.items() if v.min is not None or v.max is not None}
    cols = [c for c in (body.columns or DEFAULT_COLUMNS)]
    bad = [c for c in cols if c not in BY_KEY]
    if bad:
        raise fail(400, "bad_request", "Unknown column.")
    need = list(filters) + [c for c in cols] + ([body.sort.key] if body.sort.key in BY_KEY else [])
    locked = _locked(plan, need)
    if body.cats.band and not allowed(plan, "gold"):
        locked["overall"] = "gold"
    if locked:
        raise _refuse(locked, "Filtering or showing")
    if body.sort.key not in BY_KEY and body.sort.key not in ("name", "symbol"):
        raise fail(400, "bad_request", "Unknown sort.")
    idx = t.match(filters, body.cats.model_dump(), body.q)
    idx = t.sort(idx, body.sort.key, body.sort.dir == "desc")
    return idx, cols


@router.post("/query")
async def query(request: Request, body: Query_):
    started = time.perf_counter()
    plan = _plan(await current(request))
    t = await _table(request)
    idx, cols = _run(t, body, plan)
    total = len(idx)
    capped = plan == "basic" and total > BASIC_ROWS
    lim = min(body.limit, BASIC_ROWS) if plan == "basic" else body.limit
    off = 0 if plan == "basic" else body.offset
    page = idx[off: off + lim]
    rows = [t.row(i, cols) for i in page]
    if not allowed(plan, "silver"):  # the score band is a model output: below Silver only the free showcase companies keep it, as on the universe list
        showcase = set(request.app.state.settings.showcase_symbols)
        for r in rows:
            if r["symbol"] not in showcase:
                r["band"] = None
    out = {"total": total, "offset": off, "limit": lim, "capped": capped, "columns": cols, "rows": rows,
           "took": round((time.perf_counter() - started) * 1000, 1)}
    return Response(content=__import__("json").dumps(out, separators=(",", ":")), media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


@router.post("/export")
async def export(request: Request, body: Query_):
    ctx = await current(request)
    plan = _plan(ctx)
    if not allowed(plan, "silver"):
        raise fail(403, "plan_required", "Downloading results is part of the Silver plan.", plan="silver")
    t = await _table(request)
    idx, cols = _run(t, body, plan)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Symbol", "Company", "Sector", "Size"] + [BY_KEY[c].label + (f" ({BY_KEY[c].unit})" if BY_KEY[c].unit not in ("flag", "n", "pts") else "") for c in cols])
    for i in idx[:10000]:
        r = t.row(i, cols)
        w.writerow([r["symbol"], r["name"], r["sector"] or "", r["cap"] or ""] + ["" if r["v"][c] is None else r["v"][c] for c in cols])
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={**NO_STORE, "Content-Disposition": 'attachment; filename="finlit-screen.csv"'})
