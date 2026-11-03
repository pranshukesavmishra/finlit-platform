"""GET /api/screener/presets, /presets/{id} and /presets/{id}/export. Gold only (as the Prism columns of the Advanced score screener); admins see everything.
The server never sends a value above the plan: below Gold the list carries names and card text only (count null, locked true) and the detail answers 403."""
from __future__ import annotations

import csv
import io
import re
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


def _allowed(ctx, tab: str) -> bool:
    """The Advanced tab's screens are Gold (Prism columns); the Basic tab's are Silver (FinLit score columns)."""
    return bool(ctx.authed and (has(ctx.plan, "gold" if tab == "advanced" else "silver") or ctx.role == "admin"))


def _tab_of(request: Request) -> str:
    return "basic" if request.query_params.get("tab") == "basic" else "advanced"


def _json(body, status: int = 200) -> Response:
    import json
    return Response(content=json.dumps(body, separators=(",", ":"), default=str), status_code=status, media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


def _chips(p: Preset) -> List[dict]:
    return [{"id": c.id, "label": c.label, "default": c.default, "description": c.description} for c in p.chips]


def _list_text(p: Preset, cached: dict | None) -> str | None:
    """What the card says about its list: "Top 10 of 40 that pass" (the Top 10 screens), "First 25 of 129" (a longer match), else nothing (the count says it all)."""
    if not cached or p.kind in ("themes",):
        return None
    n = cached["count"]
    return f"Top {p.limit} of {n} that pass" if p.top10 else f"First {p.limit} of {n} that pass" if n > p.limit else None


def _card(p: Preset, gold: bool, cached: dict | None) -> dict:
    live = p.status == "live" and p.kind != "quickview"
    return {"id": p.id, "name": p.name, "group": p.group, "cardText": render_card(p, (cached or {}).get("of", {}).get("n") if cached else None), "count": cached["count"] if (gold and cached) else None, "listText": _list_text(p, cached) if gold else None,
            "asOf": cached["asOf"] if (gold and cached) else None, "status": p.status, "blockedReason": p.blocked_reason, "chips": _chips(p), "howItWorks": list(p.how_it_works),
            "locked": not gold, "tab": p.tab, "kind": p.kind, "handledBy": "frontend" if p.kind == "quickview" else "server", "computed": bool(live and cached), "disclaimer": DISCLAIMER}


async def _resolve(request: Request, pid: str):
    p = BY_ID.get(pid)
    if p is None:
        raise fail(404, "not_found", "No such screen.")
    ctx = await current(request)
    if not _allowed(ctx, p.tab):
        need = "gold" if p.tab == "advanced" else "silver"
        raise fail(403, "plan_required", f"Prebuilt screens on this tab are part of the {need.title()} plan.", plan=need)
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
    tab = _tab_of(request)
    gold = _allowed(ctx, tab)
    store = request.app.state.store
    by_group = {g: [] for g, _ in GROUPS}
    as_of = None
    for p in ALL:
        if p.tab != tab:
            continue
        cached = None
        if gold and p.status == "live" and p.kind != "quickview":
            cached = await service.read_cached(store, p.id, engine.chip_key([c.id for c in p.chips if c.default]))
            as_of = max(filter(None, [as_of, (cached or {}).get("asOf")]), default=as_of)
        by_group[p.group].append(_card(p, gold, cached))
    return _json({"tab": tab, "asOf": as_of, "groups": [{"id": g, "name": n, "presets": by_group[g]} for g, n in GROUPS if by_group[g]]})


BADGE_GROUPS = ("top-rated", "themes")      # the screens a company page names: the highest-rated lists and the themes (a value or safety screen would read as a verdict on one company)
SYMBOL = re.compile(r"^[A-Z0-9&._-]{1,24}$")


@router.get("/for/{symbol}")
async def screens_for(request: Request, symbol: str):
    """The top-rated and theme screens a company is in, from the latest nightly results (every company that passes, not only the ones shown). Gold, like the screens."""
    ctx = await current(request)
    if not _gold(ctx):
        raise fail(403, "plan_required", "Prebuilt screens are part of the Gold plan.", plan="gold")
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise fail(422, "bad_symbol", "That is not a company symbol.")
    store, screens, as_of, ready = request.app.state.store, [], None, False
    for p in ALL:
        if p.tab != "advanced" or p.group not in BADGE_GROUPS or p.status != "live" or p.kind in ("blocked", "quickview"):
            continue
        cached = await service.read_cached(store, p.id, engine.chip_key([c.id for c in p.chips if c.default]))
        if not cached:
            continue
        ready = True
        as_of = max(filter(None, [as_of, cached.get("asOf")]), default=as_of)
        if any(r.get("symbol") == sym for r in (cached.get("exportRows") or cached.get("rows") or [])):
            screens.append({"id": p.id, "name": p.name, "group": p.group, "asOf": cached.get("asOf")})
    return _json({"symbol": sym, "screens": screens, "ready": ready, "asOf": as_of})


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
