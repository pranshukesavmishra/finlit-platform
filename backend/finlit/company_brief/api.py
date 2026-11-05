"""Routes of the company brief (docs/COMPANY-BRIEF.md).

Public, read-only, free:
    GET /api/stocks/{symbol}/brief      the PUBLISHED brief, only when it passes validate() and its recorded checks; otherwise a reasoned empty state, never a guess.
Administrators (role + authenticator code + Origin/CSRF like every admin write; every change audited): /api/admin/company-brief/*
    GET  /drafts                list of briefs with their status, flags and check totals
    GET  /{symbol}              the whole draft and the published copy, its citation check, problems and flags, as plain text
    POST /{symbol}/approve | /reviewed | /reject | /unpublish | /rewrite
    PUT  /{symbol}/source       the annual report's address (not in the exchanges' feed)
    GET  /sources               companies with no annual report address, largest first
    GET  /runs                  the last nightly runs
Registered before the generic /api/stocks/{symbol}/{section} route.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from ..aliases import canonical
from ..auth.routes import Ctx, admin_ctx, fail, ip_of
from ..auth.service import audit
from . import core as B
from .service import valid_report_url

router = APIRouter()
admin = APIRouter(prefix="/api/admin/company-brief")
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")

REASONS = {
    "not_written": "Not written yet. Briefs are written overnight from each company's own filings, largest companies first.",
    "no_annual_report": "No annual report is on file for this company yet, so its brief has not been written.",
    "in_review": "Written and being reviewed. It is shown here once a person has read it.",
    "held_back": "A reviewer held this brief back. It is rewritten when the company files something new.",
    "failed_checks": "Its citations are being re-checked, so it is not shown for now.",
}


def _obj(v: Any) -> Any:
    return json.loads(v) if isinstance(v, (str, bytes)) else v


def _json(body: Any, status: int = 200, cache: str = "no-store") -> Response:
    return Response(content=json.dumps(body, separators=(",", ":"), default=str), status_code=status, media_type="application/json", headers={"Cache-Control": cache})


def empty(symbol: str, code: str, name: Optional[str] = None, detail: Optional[str] = None) -> dict:
    return {"symbol": symbol, "name": name, "state": "empty", "code": code, "reason": REASONS[code] if detail is None else detail, "disclaimer": B.DISCLAIMER, "compliance": B.STANDARD_COMPLIANCE}


def public_view(row: Optional[dict], src: Optional[dict], symbol: str, name: Optional[str], today: Optional[date] = None) -> dict:
    """What the page gets. The published copy only, and only when it still passes the gates."""
    today = today or datetime.now(timezone.utc).date()
    if row is None:
        if src and src.get("last_state") == "no_annual_report":
            return empty(symbol, "no_annual_report", name)
        return empty(symbol, "not_written", name)
    pub = _obj(row.get("published"))
    if pub is None:
        return empty(symbol, "held_back" if row["status"] == "rejected" else "in_review", name)
    ok, _ = B.publishable(pub, "published", _obj(row.get("published_checks")))
    if not ok:
        return empty(symbol, "failed_checks", name)
    plan = B.refresh_plan(pub, [], today.isoformat())
    return {"symbol": symbol, "name": name or pub.get("name"), "state": "published", "brief": {**pub, "status": "reviewed"}, "asOf": pub.get("as_of"),
            "reviewedAt": row["reviewed_at"].isoformat() if row.get("reviewed_at") else None, "stale": plan["stale"], "changes": pub.get("changes"),
            "checks": _public_checks(_obj(row.get("published_checks"))), "chips": {k: B.chip_label(k, d) for k, d in (pub.get("docs") or {}).items()},
            "waiting": row["status"] in ("draft", "reviewed") and row.get("published_at") is not None and row["written_at"] > row["published_at"],
            "disclaimer": pub.get("disclaimer") or B.DISCLAIMER, "compliance": B.STANDARD_COMPLIANCE}


def _public_checks(c: Optional[dict]) -> dict:
    c = c or {}
    return {"date": c.get("date"), "citations": c.get("citations", 0), "passed": c.get("passed", 0), "unchecked": len(c.get("unchecked") or []), "fixed": c.get("fixed") or [], "method": c.get("method")}


@router.get("/api/stocks/{symbol}/brief")
async def company_brief(request: Request, symbol: str):
    sym = canonical(symbol)
    if not SYMBOL.match(sym):
        return _json(empty(sym, "not_written", None), 200, "no-store")
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM company_briefs WHERE symbol = $1", sym)
        src = await conn.fetchrow("SELECT * FROM company_brief_sources WHERE symbol = $1", sym)
        name = await conn.fetchval("SELECT name FROM companies WHERE symbol = $1", sym)
    body = public_view(dict(row) if row else None, dict(src) if src else None, sym, name)
    return _json(body, 200, "public, max-age=300, stale-while-revalidate=900" if body["state"] == "published" else "public, max-age=60")


# ------------------------------------------------------------------------------------------------ admin
class Note(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class SourceIn(BaseModel):
    annual_report_url: Optional[str] = Field(default=None, max_length=600)


def _admin_row(r: dict, name: Optional[str]) -> dict:
    checks, problems, flags = _obj(r["checks"]) or {}, _obj(r["problems"]) or [], _obj(r["flags"]) or []
    return {"symbol": r["symbol"], "name": name, "status": r["status"], "asOf": r["as_of"].isoformat() if r["as_of"] else None, "writtenAt": r["written_at"].isoformat(),
            "writtenBy": r["written_by"], "parts": list(r["parts_written"] or []), "problems": problems, "flags": flags,
            "citations": checks.get("citations", 0), "passed": checks.get("passed", 0), "failed": len(checks.get("failed") or []), "unchecked": len(checks.get("unchecked") or []),
            "published": r.get("published") is not None, "publishedAt": r["published_at"].isoformat() if r.get("published_at") else None,
            "reviewedBy": r["reviewed_by"], "rewriteAsked": r["rewrite_asked"], "canPublish": not problems and not checks.get("failed") and bool(checks.get("citations"))}


@admin.get("/drafts")
async def a_drafts(request: Request, status: str = Query("", max_length=12), limit: int = Query(200, ge=1, le=500), ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT b.*, c.name AS cname FROM company_briefs b LEFT JOIN companies c ON c.symbol = b.symbol WHERE ($1 = '' OR b.status = $1) "
                                "ORDER BY (b.status = 'draft') DESC, b.written_at DESC LIMIT $2", status, limit)
        counts = {r["status"]: r["n"] for r in await conn.fetch("SELECT status, count(*) AS n FROM company_briefs GROUP BY status")}
        runs = await conn.fetch("SELECT id, started_at, finished_at, status, detail FROM company_brief_runs ORDER BY id DESC LIMIT 5")
    return _json({"briefs": [_admin_row(dict(r), r["cname"]) for r in rows], "counts": counts,
                  "runs": [{"id": r["id"], "at": (r["finished_at"] or r["started_at"]).isoformat(), "status": r["status"], "detail": _obj(r["detail"])} for r in runs]})


@admin.get("/sources")
async def a_sources(request: Request, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT c.symbol, c.name, s.annual_report_url, s.last_state, s.last_reason, s.attempts FROM companies c JOIN listing_quotes q ON q.symbol = c.symbol "
                                "LEFT JOIN company_brief_sources s ON s.symbol = c.symbol WHERE q.market_cap IS NOT NULL AND s.annual_report_url IS NULL "
                                "ORDER BY q.market_cap DESC LIMIT 100")
    return _json({"missing": [dict(r) for r in rows]})


@admin.get("/runs")
async def a_runs(request: Request, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, started_at, finished_at, status, detail FROM company_brief_runs ORDER BY id DESC LIMIT 30")
    return _json({"runs": [{"id": r["id"], "at": (r["finished_at"] or r["started_at"]).isoformat(), "status": r["status"], "detail": _obj(r["detail"])} for r in rows]})


@admin.get("/{symbol}")
async def a_one(request: Request, symbol: str, ctx: Ctx = Depends(admin_ctx)):
    sym = canonical(symbol)
    async with request.app.state.store.pool.acquire() as conn:
        r = await conn.fetchrow("SELECT b.*, c.name AS cname FROM company_briefs b LEFT JOIN companies c ON c.symbol = b.symbol WHERE b.symbol = $1", sym)
        src = await conn.fetchrow("SELECT * FROM company_brief_sources WHERE symbol = $1", sym)
    if r is None:
        return _json({"symbol": sym, "brief": None, "source": dict(src) if src else None}, 404)
    row = dict(r)
    brief = _obj(row["brief"])
    return _json({**_admin_row(row, row["cname"]), "brief": brief, "checks": _obj(row["checks"]), "text": B.as_text(brief), "publishedBrief": _obj(row["published"]),
                  "source": dict(src) if src else None, "reviewNote": row["review_note"]})


async def _act(request: Request, ctx: Ctx, symbol: str, action: str, note: Optional[str]):
    sym = canonical(symbol)
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT * FROM company_briefs WHERE symbol = $1 FOR UPDATE", sym)
            if r is None:
                raise fail(404, "no_brief", "There is no brief for this company yet.")
            row = dict(r)
            who = str(getattr(ctx, "email", None) or ctx.user_id)
            if action == "approve":
                brief, checks = _obj(row["brief"]), _obj(row["checks"]) or {}
                probs = B.validate(brief)
                if probs or checks.get("failed") or not checks.get("citations"):
                    raise fail(409, "not_publishable", "This brief cannot be published: " + ("; ".join(probs[:3]) if probs else "its citations are not all checked and passed."))
                old = _obj(row["published"])
                snap = {**brief, "changes": changes_note(old, brief, row["parts_written"])}
                await conn.execute("UPDATE company_briefs SET status = 'published', published = $2::jsonb, published_checks = $3::jsonb, published_at = now(), reviewed_by = $4, "
                                   "reviewed_at = now(), review_note = $5 WHERE symbol = $1", sym, json.dumps(snap), json.dumps(checks), who, note)
            elif action == "reviewed":
                await conn.execute("UPDATE company_briefs SET status = 'reviewed', reviewed_by = $2, reviewed_at = now(), review_note = $3 WHERE symbol = $1 AND status IN ('draft', 'reviewed')", sym, who, note)
            elif action == "reject":
                await conn.execute("UPDATE company_briefs SET status = 'rejected', reviewed_by = $2, reviewed_at = now(), review_note = $3 WHERE symbol = $1", sym, who, note)
            elif action == "unpublish":
                await conn.execute("UPDATE company_briefs SET published = NULL, published_checks = NULL, published_at = NULL, status = CASE WHEN status = 'published' THEN 'reviewed' ELSE status END, "
                                   "review_note = $2 WHERE symbol = $1", sym, note)
            elif action == "rewrite":
                await conn.execute("UPDATE company_briefs SET rewrite_asked = true WHERE symbol = $1", sym)
    await audit(store.pool, str(ctx.user_id), f"company_brief.{action}", sym, ip_of(request), note=note or "")
    return _json({"ok": True, "symbol": sym, "action": action})


def changes_note(old: Optional[dict], new: dict, parts: Optional[list]) -> Optional[dict]:
    """What changed since the brief that was showing: the dates and the parts rewritten. None for a first publication."""
    if not old:
        return None
    return {"since": old.get("as_of"), "now": new.get("as_of"), "parts": [p for p in (parts or []) if p != "gaps"]}


for _name in ("approve", "reviewed", "reject", "unpublish", "rewrite"):
    def _make(action: str):
        async def handler(request: Request, symbol: str, body: Note = Note(), ctx: Ctx = Depends(admin_ctx)):
            return await _act(request, ctx, symbol, action, body.note)
        handler.__name__ = f"a_{action}"
        return handler
    admin.post(f"/{{symbol}}/{_name}")(_make(_name))


@admin.put("/{symbol}/source")
async def a_source(request: Request, symbol: str, body: SourceIn, ctx: Ctx = Depends(admin_ctx)):
    sym = canonical(symbol)
    url = (body.annual_report_url or "").strip() or None
    if url and (why := valid_report_url(url)):
        raise fail(422, "bad_url", why)
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM companies WHERE symbol = $1", sym):
            raise fail(404, "unknown_company", "That company is not on FinLit.")
        await conn.execute("INSERT INTO company_brief_sources (symbol, annual_report_url, set_by, set_at, last_state, last_reason, attempts) VALUES ($1, $2, $3, now(), NULL, NULL, 0) "
                           "ON CONFLICT (symbol) DO UPDATE SET annual_report_url = $2, set_by = $3, set_at = now(), last_state = NULL, last_reason = NULL, attempts = 0",
                           sym, url, str(getattr(ctx, "email", None) or ctx.user_id))
    await audit(store.pool, str(ctx.user_id), "company_brief.source", sym, ip_of(request), url=url or "")
    return _json({"ok": True, "symbol": sym, "annual_report_url": url})
