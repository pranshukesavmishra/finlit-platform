"""GET /api/earnings-calls/{symbol} and /{symbol}/{fiscal year}/{quarter}.

The list of calls and the question labels are open to everyone. The ANSWERS are Gold (admins see everything); a lower plan gets 403 plan_required on the detail and never a
word of an answer. A Gold member may open EARNINGS_CALLS_PER_MONTH different calls a month (opening one already counted is free); the count is kept against a keyed hash of the
member, never the account. Everything served was generated and checked offline by the nightly job (finlit/earnings/service.py).
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Request, Response

from ..aliases import canonical
from ..auth.entitlements import LIMITS, has
from ..auth.routes import NO_STORE, fail
from ..auth.service import current
from . import service
from .questions import DISCLAIMER, NOT_COVERED, NOTE, QUESTIONS, public_questions
from .transcripts import quarter_label

router = APIRouter(prefix="/api/earnings-calls")


def _json(body, status: int = 200) -> Response:
    return Response(content=json.dumps(body, separators=(",", ":"), default=str), status_code=status, media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


def _gold(ctx) -> bool:
    return bool(ctx.authed and (has(ctx.plan, "gold") or ctx.role == "admin"))


def _limit() -> int:
    return LIMITS["gold"]["earnings_calls_per_month"]


def _call(c: dict) -> dict:
    return {"fiscalYear": c["fiscal_year"], "quarter": c["quarter"], "label": quarter_label(c["fiscal_year"], c["quarter"]),
            "callDate": c["call_date"].isoformat() if c["call_date"] else None, "filedAt": c["filed_at"].astimezone(service.IST).date().isoformat() if c["filed_at"] else None,
            "transcriptUrl": c["transcript_url"], "pages": c["pages"]}


async def _name(conn, symbol: str) -> Optional[str]:
    return await conn.fetchval("SELECT name FROM companies WHERE symbol = $1", symbol)


@router.get("/{symbol}")
async def calls(request: Request, symbol: str):
    sym = canonical(symbol)
    ctx = await current(request)
    gold = _gold(ctx)
    async with request.app.state.store.pool.acquire() as conn:
        rows = [c for c in await service.list_calls(conn, sym) if c["answers"] > 0]
        name = await _name(conn, sym)
        usage = None
        if gold and ctx.role != "admin":
            usage = {"used": await service.usage_count(conn, service.user_hash(request.app.state.settings.secret_key, ctx.user_id), service.month_key()), "limit": _limit()}
        elif gold:
            usage = {"used": 0, "limit": None}
    return _json({"symbol": sym, "name": name, "available": bool(rows), "locked": not gold, "calls": [_call(c) for c in rows], "questions": public_questions(),
                  "usage": usage, "note": NOTE, "disclaimer": DISCLAIMER})


@router.get("/{symbol}/{fy}/{q}")
async def detail(request: Request, symbol: str, fy: int, q: int):
    sym = canonical(symbol)
    if not (2000 <= fy <= 2100 and 1 <= q <= 4):
        raise fail(404, "not_found", "No such call.")
    ctx = await current(request)
    if not _gold(ctx):
        raise fail(403, "plan_required", "Earnings-call summaries are part of the Gold plan.", plan="gold")
    async with request.app.state.store.pool.acquire() as conn:
        call = await conn.fetchrow(
            "SELECT id, fiscal_year, quarter, call_date, filed_at, transcript_url, pages, text_chars FROM earnings_calls WHERE symbol = $1 AND fiscal_year = $2 AND quarter = $3 "
            "AND status IN ('text_ok', 'answered')", sym, fy, q)
        answers = await service.answers_for(conn, call["id"]) if call else {}
        name = await _name(conn, sym)
    if not call or not answers:
        raise fail(404, "not_found", "No summary of this call yet.")
    used: Optional[int] = None
    limit: Optional[int] = None
    if ctx.role != "admin":
        limit = _limit()
        allowed, used = await service.open_call(request.app.state.store.pool, service.user_hash(request.app.state.settings.secret_key, ctx.user_id), service.month_key(), call["id"], limit)
        if not allowed:
            raise fail(403, "limit_reached", f"You have opened {used} of {limit} earnings calls this month. Calls you already opened stay open.", used=used, limit=limit, plan="gold")
    items = []
    for qu in QUESTIONS:
        a = answers.get(qu.id)
        if a is None:
            items.append({"id": qu.id, "label": qu.label, "title": qu.title, "ready": False, "covered": False, "sentences": []})
        else:
            items.append({"id": qu.id, "label": qu.label, "title": qu.title, "ready": True, "covered": bool(a.get("covered")), "sentences":
                          [{"text": s["text"], "quote": s["quote"], "quoteRef": s.get("quote_ref") or ""} for s in a.get("sentences") or []],
                          "generatedAt": a.get("generatedAt")})
    return _json({"symbol": sym, "name": name, **_call(dict(call)), "questions": items, "usage": {"used": used if used is not None else 0, "limit": limit},
                  "summarisedByAi": True, "note": NOTE, "notCovered": NOT_COVERED, "disclaimer": DISCLAIMER})
