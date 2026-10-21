"""Graph Studio saved views. A view is a named layout of charts; the plan limits are enforced here, not in the browser.

The chart data itself comes from the ordinary stock endpoints (which already trim ratios, valuation history and segments by plan),
so a saved view can never reveal anything its owner's plan does not include. The mirror of GRAPH_LIMITS lives in
frontend/src/lib/graphLimits.ts; a test keeps the two equal.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator

from .auth.routes import NO_STORE, SYMBOL, Ctx, fail, secure_ctx

router = APIRouter(prefix="/api")

CHARTS = ("line", "area", "column", "bar", "combo", "pie", "candlestick", "scatter", "heatmap")
LAYOUTS = {"1x1": 1, "1x2": 2, "2x2": 4, "2x3": 6, "3x3": 9}
GRAPH_LIMITS: Dict[str, Dict[str, Any]] = {
    "basic": {"cells": 4, "companies": 2, "series": 3, "views": 2, "charts": ["line", "area", "column", "bar", "combo", "pie"]},
    "silver": {"cells": 6, "companies": 3, "series": 4, "views": 10, "charts": ["line", "area", "column", "bar", "combo", "pie", "candlestick", "scatter"]},
    "gold": {"cells": 9, "companies": 6, "series": 6, "views": 50, "charts": list(CHARTS)},
}
ID = r"^[a-z0-9_]{1,40}$"
INDEX_SYM = re.compile(r"^IDX:[A-Z0-9]{2,24}$")


def limits_for(plan: str) -> Dict[str, Any]:
    return GRAPH_LIMITS.get(plan, GRAPH_LIMITS["basic"])


class SeriesIn(BaseModel):
    s: str = Field(max_length=32)   # a company symbol, or an index as IDX:code
    m: str = Field(pattern=ID)
    as_: Optional[Literal["bar", "line"]] = Field(default=None, alias="as")

    @field_validator("s")
    @classmethod
    def _sym(cls, v: str) -> str:
        v = v.strip().upper()
        if not (SYMBOL.match(v) or INDEX_SYM.match(v)):
            raise ValueError("bad symbol")
        return v

    model_config = {"populate_by_name": True}


class CellIn(BaseModel):
    chart: Literal[CHARTS]  # type: ignore[valid-type]
    series: List[SeriesIn] = Field(default_factory=list, max_length=9)
    mode: Optional[Literal["corr", "grid"]] = None
    tf: Optional[Literal["values", "change", "index"]] = None
    x: Optional[int] = Field(default=None, ge=0, le=8)
    y: Optional[int] = Field(default=None, ge=0, le=8)


class ConfigIn(BaseModel):
    v: Literal[1] = 1
    layout: Literal["1x1", "1x2", "2x2", "2x3", "3x3"]
    basis: Literal["annual", "quarterly"] = "annual"
    range: Literal["1Y", "3Y", "5Y", "MAX"] = "5Y"
    cells: List[CellIn] = Field(max_length=9)


class ViewIn(BaseModel):
    config: ConfigIn


def clean_name(name: str) -> str:
    name = " ".join(name.split())
    if not 1 <= len(name) <= 60:
        raise fail(422, "bad_name", "Give the view a name of up to 60 characters.")
    return name


def check_plan(cfg: ConfigIn, plan: str) -> None:
    lim = limits_for(plan)
    if len(cfg.cells) > LAYOUTS[cfg.layout]:
        raise fail(422, "bad_layout", "More charts than the layout has room for.")
    if LAYOUTS[cfg.layout] > lim["cells"]:
        raise fail(403, "plan_limit", f"Your plan includes layouts of up to {lim['cells']} charts.", plan="silver" if plan == "basic" else "gold")
    tier = "silver" if plan == "basic" else "gold"
    if len({s.s for c in cfg.cells for s in c.series if not s.s.startswith("IDX:")}) > lim["companies"]:
        raise fail(403, "plan_limit", f"Your plan includes up to {lim['companies']} companies in one view.", plan=tier)
    for c in cfg.cells:
        if c.chart not in lim["charts"]:
            raise fail(403, "plan_limit", f"The {c.chart} chart is not part of your plan.", plan=tier)
        if len(c.series) > lim["series"]:
            raise fail(403, "plan_limit", f"Your plan includes up to {lim['series']} series in one chart.", plan=tier)


def view_json(r: Any) -> Dict[str, Any]:
    cfg = json.loads(r["config"]) if isinstance(r["config"], str) else r["config"]
    return {"name": r["name"], "config": cfg, "updatedAt": r["updated_at"].isoformat()}


@router.get("/me/graph-views")
async def list_views(request: Request, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT name, config, updated_at FROM graph_views WHERE user_id = $1 ORDER BY updated_at DESC", ctx.user_id)
    body = {"views": [view_json(r) for r in rows], "limits": limits_for(ctx.plan), "plan": ctx.plan}
    return Response(content=json.dumps(body), media_type="application/json", headers=NO_STORE)


@router.put("/me/graph-views/{name}")
async def save_view(request: Request, name: str, body: ViewIn, ctx: Ctx = Depends(secure_ctx)):
    name = clean_name(name)
    check_plan(body.config, ctx.plan)
    lim = limits_for(ctx.plan)
    payload = json.dumps(body.config.model_dump(by_alias=True, exclude_none=True))
    async with request.app.state.store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", "graph_views:" + str(ctx.user_id))   # two quick saves cannot both slip under the limit
            exists = await conn.fetchval("SELECT 1 FROM graph_views WHERE user_id = $1 AND name = $2", ctx.user_id, name)
            if not exists and await conn.fetchval("SELECT count(*) FROM graph_views WHERE user_id = $1", ctx.user_id) >= lim["views"]:
                raise fail(403, "plan_limit", f"Your plan includes {lim['views']} saved views. Delete one or upgrade.", plan="silver" if ctx.plan == "basic" else "gold")
            await conn.execute("INSERT INTO graph_views (user_id, name, config) VALUES ($1, $2, $3::jsonb) "
                               "ON CONFLICT (user_id, name) DO UPDATE SET config = EXCLUDED.config, updated_at = now()", ctx.user_id, name, payload)
    return {"status": "saved", "name": name}


@router.delete("/me/graph-views/{name}")
async def delete_view(request: Request, name: str, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM graph_views WHERE user_id = $1 AND name = $2", ctx.user_id, clean_name(name))
    return {"status": "deleted"}
