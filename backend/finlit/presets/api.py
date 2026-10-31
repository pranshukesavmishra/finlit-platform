"""GET /api/screener/presets, /presets/{id} and /presets/{id}/export. Gold only (as the Prism columns of the Advanced score screener); admins see everything.
The server never sends a value above the plan: below Gold the list carries names and card text only (count null, locked true) and the detail answers 403."""
from __future__ import annotations

import csv
import io
from typing import List

from fastapi import APIRouter, Request, Response

from ..auth.entitlements import has
from ..auth.routes import NO_STORE, fail
from ..auth.service import current
from . import engine, service
from .registry import ALL, BY_ID, DISCLAIMER, GROUPS, Preset, render_card

router = APIRouter(prefix="/api/screener/presets")
API_ONLY = ("exportRows",)


def _gold(ctx) -> bool:
    return bool(ctx.authed and (has(ctx.plan, "gold") or ctx.role == "admin"))


def _json(body, status: int = 200) -> Response:
    import json
    return Response(content=json.dumps(body, separators=(",", ":"), default=str), status_code=status, media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


def _chips(p: Preset) -> List[dict]:
    return [{"id": c.id, "label": c.label, "default": c.default, "description": c.description} for c in p.chips]


def _card(p: Preset, gold: bool, cached: dict | None) -> dict:
    live = p.status == "live" and p.kind != "quickview"
    return {"id": p.id, "name": p.name, "group": p.group, "cardText": render_card(p, (cached or {}).get("of", {}).get("n") if cached else None), "count": cached["count"] if (gold and cached) else None,
            "asOf": cached["asOf"] if (gold and cached) else None, "status": p.status, "blockedReason": p.blocked_reason, "chips": _chips(p), "howItWorks": list(p.how_it_works),
            "locked": not gold, "kind": p.kind, "handledBy": "frontend" if p.kind == "quickview" else "server", "computed": bool(live and cached), "disclaimer": DISCLAIMER}


async def _resolve(request: Request, pid: str):
    p = BY_ID.get(pid)
    if p is None:
        raise fail(404, "not_found", "No such screen.")
    ctx = await current(request)
    if not _gold(ctx):
        raise fail(403, "plan_required", "Prebuilt screens are part of the Gold plan.", plan="gold")
    if p.kind in ("blocked", "quickview"):
        raise fail(409, "blocked" if p.kind == "blocked" else "not_a_server_screen",
                   p.blocked_reason or "This quick view is handled by the page itself.", blockedReason=p.blocked_reason)
    try:
        active = engine.resolve_chips(p, request.query_params.getlist("chip") or None)
    except engine.UnknownChip as exc:
        raise fail(422, "unknown_chip", str(exc))
    return p, ctx, active


async def _body(request: Request, p: Preset, active: List[str]) -> dict:
    body = await service.get_result(request.app.state.store, p, active)
    if body is None:
        raise fail(503, "computing", "This screen is being prepared. Try again in a few seconds.")
    return body


@router.get("")
async def listing(request: Request):
    ctx = await current(request)
    gold = _gold(ctx)
    store = request.app.state.store
    by_group = {g: [] for g, _ in GROUPS}
    as_of = None
    for p in ALL:
        cached = None
        if gold and p.status == "live" and p.kind != "quickview":
            cached = await service.read_cached(store, p.id, engine.chip_key([c.id for c in p.chips if c.default]))
            as_of = max(filter(None, [as_of, (cached or {}).get("asOf")]), default=as_of)
        by_group[p.group].append(_card(p, gold, cached))
    return _json({"asOf": as_of, "groups": [{"id": g, "name": n, "presets": by_group[g]} for g, n in GROUPS if by_group[g]]})


@router.get("/{pid}")
async def detail(request: Request, pid: str):
    p, ctx, active = await _resolve(request, pid)
    body = await _body(request, p, active)
    await service.log_usage(request.app.state.store, p.id, "open")
    return _json({k: v for k, v in body.items() if k not in API_ONLY})


@router.get("/{pid}/export")
async def export(request: Request, pid: str):
    p, ctx, active = await _resolve(request, pid)
    body = await _body(request, p, active)
    cols = body["columns"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Symbol"] + [c["label"] for c in cols])
    for r in body.get("exportRows", []):
        w.writerow([r["symbol"]] + ["" if r.get(c["key"]) is None else r[c["key"]] for c in cols])
    w.writerow([])
    w.writerow([DISCLAIMER + f" {p.name}, as of {body['asOf']}."])
    await service.log_usage(request.app.state.store, p.id, "export")
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={**NO_STORE, "Content-Disposition": f'attachment; filename="finlit-{p.id}.csv"'})
