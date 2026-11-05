"""Sector Pulse over HTTP (docs/SECTORS.md).

    GET /api/sectors                          the board: every industry and sector group with a reading
    GET /api/sectors/status                   public, read-only: the date of the data, stocks counted, how the last nightly run ended (and why not)
    GET /api/sectors/{slug}                   one industry page
    GET /api/technicals/{symbol}/sector       a stock inside its industry (Gold)
    GET /api/rotation                         Sector Rotation: corners, ranking, paths, rank history, study (every plan)
    GET /api/rotation/{slug}                  one group's rotation card (industry page)

All four read the static JSON the nightly job wrote (finlit/sector_data.py): no database, no pandas. What a plan may see is decided HERE, on the server
(auth/entitlements.py: redact_sector_*): a locked field is present and null, and `locked` names the plan that opens it. Basic sees the state and breadth of
every group; Silver adds the ranked stock tables and the leader flags; Gold adds the stock page's "Sector & peers" cards and the peer label. Administrators see all.

When there is nothing to show the answer is 503 with a sentence that starts "Sector data is not loaded yet:" and says why, never a bare error.
The slug is checked against the board (a fixed list), the symbol against NSE's character set, and the file is always inside the live release folder.
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, Optional

import orjson
from fastapi import APIRouter, Request, Response

from . import sector_data as sd
from .auth.entitlements import redact_rotation_map, redact_sector_board, redact_sector_industry, redact_sector_stock, sector_plan
from .auth.service import current
from .background import etag_matches

router = APIRouter()
PRIVATE_CACHE = "private, max-age=300, must-revalidate"      # the answer depends on the plan (Cookie), so no shared cache may keep it
NO_STORE = "no-store"


def _reply(request: Request, payload: Any, started: float, status: int = 200, cache: str = PRIVATE_CACHE) -> Response:
    body = orjson.dumps(payload)
    headers = {"Cache-Control": cache, "Vary": "Cookie", "Server-Timing": f"app;dur={(time.perf_counter() - started) * 1000:.2f}"}
    if status == 200:
        etag = '"' + hashlib.sha1(body).hexdigest()[:20] + '"'  # nosec B324 - cache validator, not security
        headers["ETag"] = etag
        if etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", status_code=status, headers=headers)


def _not_loaded(request: Request, started: float) -> Response:
    reason = sd.not_loaded_reason()
    return _reply(request, {"available": False, "status": "not_loaded", "reason": reason, "detail": reason}, started, status=503, cache=NO_STORE)


def _not_found(request: Request, started: float, reason: str) -> Response:
    return _reply(request, {"available": False, "status": "not_found", "reason": reason, "detail": reason}, started, status=404, cache=NO_STORE)


async def _plan(request: Request) -> str:
    ctx = await current(request)
    return sector_plan(ctx.plan, ctx.role)


# status first: /api/sectors/{slug} would otherwise claim it
@router.get("/api/sectors/status")
async def status(request: Request) -> Response:
    started = time.perf_counter()
    out = sd.out_dir()
    rel = sd.live_release(out)
    meta = sd.sector_meta(rel)
    last = sd.read_last_run(out)
    board = sd.read_json(rel / "sectors" / "_board.json") if rel else None
    body: Dict[str, Any] = {
        "enabled": sd.enabled(), "loaded": bool(board),
        "dataDate": board.get("date") if board else None,
        "stocksCounted": board.get("stocks_counted") if board else None, "groups": board.get("groups") if board else None,
        "industries": board.get("industries") if board else None,
        "stockFiles": meta.get("stocks"), "stockErrors": meta.get("errors"), "builtAt": meta.get("built_at"), "seconds": meta.get("seconds"),
        "lastRun": ({k: last.get(k) for k in ("status", "at", "reason", "dataDate", "fetch", "seconds", "stocks", "errors")} if last else None),
        "rotationLoaded": bool(rel and (rel / "rotation" / "_map.json").is_file()),
        "reason": None if board else sd.not_loaded_reason(out),
    }
    return _reply(request, body, started, cache="public, max-age=60")


@router.get("/api/sectors")
async def board(request: Request) -> Response:
    started = time.perf_counter()
    rel = sd.live_release()
    data = sd.read_json(rel / "sectors" / "_board.json") if rel else None
    if not data:
        return _not_loaded(request, started)
    return _reply(request, redact_sector_board(data, await _plan(request)), started)


@router.get("/api/sectors/{slug}")
async def industry(slug: str, request: Request) -> Response:
    started = time.perf_counter()
    rel = sd.live_release()
    data = sd.read_json(rel / "sectors" / "_board.json") if rel else None
    if not data:
        return _not_loaded(request, started)
    slug = sd.resolve_slug(slug)
    if not sd.SLUG.match(slug) or slug not in sd.board_slugs(data):       # only a slug the board lists is ever turned into a file name
        return _not_found(request, started, "There is no industry or sector group with this address. The groups that are read are listed on Sector Pulse.")
    page = sd.read_json(rel / "sectors" / f"{slug}.json")
    if not page:
        reason = "Sector data is not loaded yet: this industry's page is missing from the current data set. It is rebuilt at the next nightly run."
        return _reply(request, {"available": False, "status": "not_loaded", "reason": reason, "detail": reason}, started, status=503, cache=NO_STORE)
    return _reply(request, redact_sector_industry(page, await _plan(request)), started)


@router.get("/api/technicals/{symbol}/sector")
async def stock_sector(symbol: str, request: Request) -> Response:
    started = time.perf_counter()
    rel = sd.live_release()
    if rel is None:
        return _not_loaded(request, started)
    sym = symbol.strip().upper()
    if not sd.SYMBOL.match(sym):
        return _not_found(request, started, "This is not an NSE symbol.")
    path = rel / f"{sym}.json"
    if path.parent != rel:      # belt and braces: the file must sit directly in the release folder
        return _not_found(request, started, "This is not an NSE symbol.")
    doc = sd.read_json(path)
    if not isinstance(doc, dict):
        return _not_found(request, started, f"No sector reading for {sym}. It did not trade on the last session, or NSE has not classified its industry yet.")
    return _reply(request, redact_sector_stock(doc.get("sector"), sym, await _plan(request)), started)



# ------------------------------------------------------------------------------------------------ Sector Rotation
def _rotation_missing(request: Request, started: float) -> Response:
    """No rotation file in the live release (a set built before rotation existed, or a build where rotation failed): say so in words. The site process never computes it (no pandas here)."""
    if sd.live_release() is None:
        return _not_loaded(request, started)
    reason = "Rotation data is not loaded yet: the current data set has no rotation files. They are written by the next nightly sector run."
    return _reply(request, {"available": False, "status": "not_loaded", "reason": reason, "detail": reason}, started, status=503, cache=NO_STORE)


@router.get("/api/rotation")
async def rotation_map(request: Request) -> Response:
    started = time.perf_counter()
    rel = sd.live_release()
    data = sd.read_json(rel / "rotation" / "_map.json") if rel else None
    if not data:
        return _rotation_missing(request, started)
    return _reply(request, redact_rotation_map(data, await _plan(request)), started)


@router.get("/api/rotation/{slug}")
async def rotation_card(slug: str, request: Request) -> Response:
    started = time.perf_counter()
    rel = sd.live_release()
    data = sd.read_json(rel / "rotation" / "_map.json") if rel else None
    if not data:
        return _rotation_missing(request, started)
    slug = sd.resolve_slug(slug)
    if not sd.SLUG.match(slug) or slug not in {r.get("slug") for r in data.get("rows", [])}:       # only a slug the map lists is ever turned into a file name
        why = "This group has no rotation reading: it has fewer than 8 counted stocks, or there is no group with this address."
        return _not_found(request, started, why)
    card = sd.read_json(rel / "rotation" / f"{slug}.json")
    if not card:
        reason = "Rotation data is not loaded yet: this group's rotation card is missing from the current data set. It is rebuilt at the next nightly run."
        return _reply(request, {"available": False, "status": "not_loaded", "reason": reason, "detail": reason}, started, status=503, cache=NO_STORE)
    return _reply(request, card, started)
