"""Page queries and feedback: "Raise a Query" in a page's banner and "Share Feedback" at the foot of every page.

Every message is tagged with the page it came from (address, the name the page gives itself and a few short facts such as the company symbol), so the team
knows which feature it is about. Members write as themselves (the account is the way back to them); a visitor who is not signed in must leave an email address.

Rules enforced here, on the server, whatever the website does:
* the request must come from our own pages (Origin); a signed-in member also proves it with the CSRF token;
* text is cleaned to plain text, limited in length, and refused when it is only contact spam; ratings are 1 to 5;
* per-address and per-member limits, and an identical message is not stored twice within a day;
* the page address is kept without its query string, the context holds only short whitelisted facts (never free text from the member);
* administrators (with the two-step sign-in) read, filter and close them; nothing is ever shown to other members.
"""

from __future__ import annotations

import hmac
import json
import logging
import re
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from . import forum_rules as rules
from .auth.routes import NO_STORE, admin_ctx, fail, ip_of, limit, origin_allowed
from .auth.service import audit, current

router = APIRouter(prefix="/api")
log = logging.getLogger("finlit.page_feedback")

KINDS = ("query", "feedback")
QUERY_CATEGORIES = ("question", "issue", "clarification")
FEEDBACK_CATEGORIES = ("suggestion", "ui_ux", "praise", "other")
STATUSES = ("new", "read", "resolved")
MESSAGE_MIN, MESSAGE_MAX = 10, 2000
CONTEXT_KEYS = {"title": 120, "heading": 120, "symbol": 24, "section": 80, "plan": 12, "screen": 12, "theme": 8, "tab": 60}
EMAIL = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,24}$")
PATH = re.compile(r"^/[A-Za-z0-9._~!$&'()*+,;=:@%/\-]{0,198}$")


def out(body: Any, status: int = 200) -> Response:
    return Response(content=json.dumps(body), media_type="application/json", headers=NO_STORE, status_code=status)


class SendIn(BaseModel):
    kind: Literal["query", "feedback"]
    page: str = Field(max_length=300)                 # the address, "/stocks/RELIANCE" (any query string or fragment is dropped)
    pageName: str = Field(default="", max_length=120)
    context: Dict[str, Any] = Field(default_factory=dict)
    category: str = Field(default="", max_length=20)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    message: str = Field(default="", max_length=6000)
    email: Optional[str] = Field(default=None, max_length=254)


class HandleIn(BaseModel):
    status: Optional[Literal["new", "read", "resolved"]] = None
    note: Optional[str] = Field(default=None, max_length=1000)


def clean_path(raw: str) -> str:
    path = raw.strip().split("?", 1)[0].split("#", 1)[0]
    if len(path) > 1:
        path = path.rstrip("/")
    return path if PATH.match(path or "") else ""


def clean_context(raw: Dict[str, Any]) -> Dict[str, str]:
    """Only the whitelisted short facts, as plain text of the allowed length."""
    ctx: Dict[str, str] = {}
    for key, cap in CONTEXT_KEYS.items():
        v = raw.get(key)
        if isinstance(v, (str, int, float)) and not isinstance(v, bool):
            text = rules.clean_text(str(v))[:cap]
            if text:
                ctx[key] = text
    return ctx


def csrf_ok(request: Request, ctx) -> bool:
    return hmac.compare_digest(request.headers.get("x-csrf-token", ""), ctx.csrf or "")


@router.post("/page-feedback", status_code=201)
async def send(request: Request, body: SendIn):
    if not origin_allowed(request):
        raise fail(403, "bad_origin", "This request did not come from the FinLit website.")
    ctx = await current(request)
    if ctx.authed and not csrf_ok(request, ctx):
        raise fail(403, "bad_csrf", "Your session needs to be refreshed. Reload the page and try again.")
    page = clean_path(body.page)
    if not page:
        raise fail(422, "bad_page", "We could not tell which page this is about. Reload the page and try again.")
    allowed = QUERY_CATEGORIES if body.kind == "query" else FEEDBACK_CATEGORIES
    category = body.category if body.category in allowed else ("question" if body.kind == "query" else "other")
    message = rules.clean_text(body.message)
    rating = body.rating if body.kind == "feedback" else None
    if body.kind == "query" and len(message) < MESSAGE_MIN:
        raise fail(422, "message_short", f"Please write at least {MESSAGE_MIN} characters so we can help.")
    if body.kind == "feedback" and not message and rating is None:
        raise fail(422, "empty_feedback", "Choose a rating or write a few words.")
    if message and len(message) < 3:
        raise fail(422, "message_short", "Please write a few more words.")
    if len(message) > MESSAGE_MAX:
        raise fail(422, "message_long", f"Please keep it under {MESSAGE_MAX} characters.")
    email = None
    if not ctx.authed:
        email = (body.email or "").strip().lower()
        if not EMAIL.match(email):
            raise fail(422, "email_required", "Enter an email address so we can reply." if body.kind == "query" else "Enter an email address, or sign in, to send feedback.")
    await limit(request, "pf_ip", ip_of(request), 20, 3600)
    if ctx.authed:
        await limit(request, "pf_user", ctx.user_id, 12, 3600)
        await limit(request, "pf_user_day", ctx.user_id, 40, 86400)
    context = clean_context(body.context)
    name = rules.clean_text(body.pageName)[:120] or page
    pool = request.app.state.store.pool
    async with pool.acquire() as conn:
        dup = await conn.fetchval("SELECT id FROM page_feedback WHERE created_at > now() - interval '1 day' AND message = $1 AND page_path = $2 AND kind = $3 "
                                  "AND (($4::uuid IS NOT NULL AND user_id = $4::uuid) OR ($4::uuid IS NULL AND email = $5)) LIMIT 1", message, page, body.kind, ctx.user_id, email)
        if dup:
            return out({"status": "received", "id": dup, "duplicate": True}, 201)
        row_id = await conn.fetchval(
            """INSERT INTO page_feedback (kind, page_path, page_name, context, category, rating, message, email, user_id, plan)
               VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9, $10) RETURNING id""",
            body.kind, page, name, json.dumps(context), category, rating, message, email, ctx.user_id, ctx.plan if ctx.authed else None)
    await notify_team(request, row_id, body.kind, page, name, category, rating, message, email, ctx)
    return out({"status": "received", "id": row_id}, 201)


async def notify_team(request: Request, row_id: int, kind: str, page: str, name: str, category: str, rating: Optional[int], message: str, email: Optional[str], ctx) -> None:
    """A query is emailed to the team (feedback is only stored and read in the inbox, so the mailbox is for questions that wait for an answer).
    Best effort: the message is already stored, so a mail problem never fails the member's request."""
    to = getattr(request.app.state.settings, "feedback_notify_email", "") or ""
    if kind != "query" or not to:
        return
    who = (email or "a signed-in member") + (f" ({ctx.plan} plan)" if ctx.authed else "")
    subject = f"FinLit query on {name}"
    lines = [f"Query #{row_id} about: {name} ({page})", f"Type: {category}", f"From: {who}" + (f" - reply to {email}" if email else " - answer by email from the account (see the inbox)"), "", message,
             "", f"Open it: {request.app.state.settings.public_site_url}/admin/feedback"]
    try:
        await request.app.state.mailer.send(to, subject, "\n".join(lines))
    except Exception:   # never log the address or the text
        log.warning("page feedback notification not sent for #%s", row_id)


# ------------------------------------------------------------------ the team's side (administrators, two-step sign-in required)
def item(r: Any) -> Dict[str, Any]:
    return {"id": r["id"], "kind": r["kind"], "page": r["page_path"], "pageName": r["page_name"], "context": json.loads(r["context"]) if isinstance(r["context"], str) else (r["context"] or {}),
            "category": r["category"], "rating": r["rating"], "message": r["message"], "email": r["email"] or r["user_email"], "member": r["user_id"] is not None,
            "plan": r["plan"], "status": r["status"], "note": r["note"], "createdAt": r["created_at"].isoformat(), "handledAt": r["handled_at"].isoformat() if r["handled_at"] else None}


@router.get("/admin/page-feedback")
async def inbox(request: Request, kind: str = Query("", max_length=10), status: str = Query("", max_length=10), page: str = Query("", max_length=200),
                pg: int = Query(1, ge=1, le=1000), ctx=Depends(admin_ctx)):
    """The queries and feedback, newest first; filter by kind, status or page."""
    k = kind if kind in KINDS else None
    s = status if status in STATUSES else None
    p = clean_path(page) or None
    per = 25
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT f.*, u.email AS user_email FROM page_feedback f LEFT JOIN users u ON u.id = f.user_id
               WHERE ($1::text IS NULL OR f.kind = $1) AND ($2::text IS NULL OR f.status = $2) AND ($3::text IS NULL OR f.page_path = $3)
               ORDER BY f.created_at DESC, f.id DESC LIMIT $4 OFFSET $5""", k, s, p, per, (pg - 1) * per)
        total = await conn.fetchval("SELECT count(*) FROM page_feedback f WHERE ($1::text IS NULL OR f.kind = $1) AND ($2::text IS NULL OR f.status = $2) AND ($3::text IS NULL OR f.page_path = $3)", k, s, p)
        counts = await conn.fetchrow("SELECT count(*) FILTER (WHERE status = 'new') AS new, count(*) FILTER (WHERE kind = 'query' AND status <> 'resolved') AS open_queries FROM page_feedback")
    return out({"items": [item(r) for r in rows], "total": total, "page": pg, "per": per, "pages": max(1, -(-total // per)),
                "counts": {"new": counts["new"], "openQueries": counts["open_queries"]}})


@router.get("/admin/page-feedback/summary")
async def by_page(request: Request, ctx=Depends(admin_ctx)):
    """Which pages people write about most, with the average rating: where to look first."""
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT page_path, max(page_name) AS name, count(*) AS total, count(*) FILTER (WHERE kind = 'query') AS queries, count(*) FILTER (WHERE kind = 'feedback') AS feedback,
                      count(*) FILTER (WHERE status = 'new') AS fresh, round(avg(rating)::numeric, 2) AS avg_rating, count(rating) AS rated
               FROM page_feedback GROUP BY page_path ORDER BY count(*) DESC, page_path LIMIT 100""")
    return out({"pages": [{"page": r["page_path"], "name": r["name"], "total": r["total"], "queries": r["queries"], "feedback": r["feedback"], "new": r["fresh"],
                           "avgRating": float(r["avg_rating"]) if r["avg_rating"] is not None else None, "rated": r["rated"]} for r in rows]})


@router.patch("/admin/page-feedback/{fid}")
async def handle(request: Request, fid: int, body: HandleIn, ctx=Depends(admin_ctx)):
    if fid > 2**62:
        raise fail(404, "not_found", "That message does not exist.")
    note = rules.clean_text(body.note)[:1000] if body.note is not None else None
    async with request.app.state.store.pool.acquire() as conn:
        done = await conn.fetchval(
            """UPDATE page_feedback SET status = COALESCE($2, status), note = CASE WHEN $3::text IS NULL THEN note ELSE NULLIF($3, '') END, handled_by = $4::uuid, handled_at = now()
               WHERE id = $1 RETURNING id""", fid, body.status, note, ctx.user_id)
    if not done:
        raise fail(404, "not_found", "That message does not exist.")
    await audit(request.app.state.store.pool, ctx.user_id, "page_feedback_handle", str(fid), ip_of(request), status=body.status or "")
    return out({"status": "saved"})
