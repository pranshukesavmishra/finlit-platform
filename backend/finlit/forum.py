"""Discussion forum: one board per company plus a site-wide index. Information and opinion only (see forum_rules.py).

Where it lives: this is the research API (not the site API), because it needs member accounts, sessions, CSRF and the
administrator two-step sign-in (`admin_ctx`, which honours ADMIN_REQUIRE_MFA). The site API has no member accounts.

Rules enforced here, on the server, whatever the website does:
* anyone may read; posting, voting and reporting need a signed-in, email-confirmed member of any plan (the forum is not a paid feature);
* a public handle (never the email or account name) must be chosen once, with the guidelines accepted, before the first post;
* every write is rate limited per member and per address, duplicates are refused, text is cleaned to plain text, contact details,
  buy/sell calls and bad links are refused, hype is held for a moderator;
* enough member reports hide a post at once; administrators work a queue; nothing is physically deleted by members.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Literal, Optional

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import BaseModel, Field

from . import forum_rules as rules
from .auth.routes import NO_STORE, SYMBOL, Ctx, admin_ctx, fail, ip_of, limit, secure_ctx
from .auth.service import audit, current

router = APIRouter(prefix="/api")

EDIT_WINDOW_SECONDS = 15 * 60          # the author may change a post for this long after writing it
REPORT_HIDE_AT = 3                     # different members who must report a post before it is hidden pending review
MIN_ACCOUNT_AGE_SECONDS = 5 * 60       # a brand-new account waits a few minutes before its first post (stops drive-by spam)
TRUSTED_AFTER = 3                      # standing posts after which a member's links are no longer held
PER_PAGE_MAX = 50
REPLIES_PER_PAGE = 30
SORTS = {"active": "p.last_activity_at DESC, p.id DESC", "recent": "p.created_at DESC, p.id DESC", "top": "p.upvotes DESC, p.created_at DESC, p.id DESC"}
REPORT_REASONS = ("advice", "promotion", "contact", "abuse", "spam", "misleading", "other")
RULES_PUBLIC = {"titleMin": rules.TITLE_MIN, "titleMax": rules.TITLE_MAX, "bodyMin": rules.BODY_MIN, "bodyMax": rules.BODY_MAX, "replyMin": rules.REPLY_MIN,
                "replyMax": rules.REPLY_MAX, "maxLinks": rules.MAX_LINKS, "editWindowMinutes": EDIT_WINDOW_SECONDS // 60, "reportHideAt": REPORT_HIDE_AT}


def out(body: Any, status: int = 200) -> Response:
    import json
    return Response(content=json.dumps(body), media_type="application/json", headers=NO_STORE, status_code=status)


def pool_of(request: Request):
    return request.app.state.store.pool


# ------------------------------------------------------------------ models
class ProfileIn(BaseModel):
    handle: str = Field(min_length=1, max_length=40)
    accept: bool = False


class ThreadIn(BaseModel):
    symbol: str = Field(max_length=24)
    title: str = Field(max_length=400)
    body: str = Field(max_length=20000)


class ReplyIn(BaseModel):
    body: str = Field(max_length=20000)


class EditIn(BaseModel):
    title: Optional[str] = Field(default=None, max_length=400)
    body: str = Field(max_length=20000)


class ReportIn(BaseModel):
    reason: Literal["advice", "promotion", "contact", "abuse", "spam", "misleading", "other"]
    note: Optional[str] = Field(default=None, max_length=300)


class BanIn(BaseModel):
    days: int = Field(ge=1, le=3650)
    reason: str = Field(default="", max_length=200)


class NoteIn(BaseModel):
    note: str = Field(default="", max_length=300)


# ------------------------------------------------------------------ shaping
POST_SELECT = """SELECT p.id, p.thread_id, p.symbol, c.name AS company, p.user_id, p.title, p.body, p.status, p.upvotes, p.created_at, p.edited_at, p.last_activity_at,
                        p.flag_reasons, pr.handle, (u.role = 'admin') AS staff, extract(epoch FROM (now() - p.created_at)) AS age_s,
                        EXISTS (SELECT 1 FROM forum_votes v WHERE v.post_id = p.id AND v.user_id = $1::uuid) AS voted,
                        (SELECT count(*) FROM forum_posts r WHERE r.thread_id = p.id AND r.status = 'visible') AS replies
                 FROM forum_posts p JOIN companies c ON c.symbol = p.symbol JOIN users u ON u.id = p.user_id LEFT JOIN forum_profiles pr ON pr.user_id = p.user_id """

TOMBSTONE = {"deleted": "Deleted by its author.", "removed": "Removed by a moderator for breaking the community guidelines.",
             "hidden": "Hidden while moderators review reports from members.", "held": "Waiting for a moderator to look at it. Only you can see this for now."}


def post_json(r: Any, ctx: Ctx, *, preview: bool = False) -> Dict[str, Any]:
    mine = ctx.user_id is not None and str(r["user_id"]) == ctx.user_id
    shown = r["status"] == "visible" or (mine and r["status"] in ("held", "hidden"))
    body = r["body"] if shown else None
    if body is not None and preview and len(body) > 220:
        body = body[:217].rstrip() + "..."
    open_for_edit = mine and r["status"] in ("visible", "held") and r["age_s"] <= EDIT_WINDOW_SECONDS
    return {"id": r["id"], "threadId": r["thread_id"] or r["id"], "kind": "reply" if r["thread_id"] else "thread", "symbol": r["symbol"], "company": r["company"],
            "title": r["title"] if shown else None, "body": body,
            "author": {"handle": r["handle"] or "member", "staff": bool(r["staff"])},
            "createdAt": r["created_at"].isoformat(), "editedAt": r["edited_at"].isoformat() if r["edited_at"] else None,
            "lastActivityAt": r["last_activity_at"].isoformat(), "upvotes": r["upvotes"], "voted": bool(r["voted"]), "replies": int(r["replies"]) if not r["thread_id"] else 0,
            "status": r["status"], "mine": mine, "note": None if shown and r["status"] == "visible" else TOMBSTONE.get(r["status"]),
            "canEdit": bool(open_for_edit), "editableSeconds": max(0, int(EDIT_WINDOW_SECONDS - r["age_s"])) if open_for_edit else 0}


def valid_uuid(raw: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        raise fail(404, "not_found", "That member does not exist.")


def is_mod(ctx: Ctx) -> bool:
    return ctx.role == "admin" and ctx.mfa_ok


async def my_profile(conn, ctx: Ctx):
    return await conn.fetchrow("SELECT handle, banned_until, banned_reason, (banned_until IS NOT NULL AND banned_until > now()) AS banned FROM forum_profiles WHERE user_id = $1", ctx.user_id)


async def posting_member(request: Request, conn, ctx: Ctx, *, write: str = "post"):
    """Everything a member needs before writing: a handle (with the guidelines accepted), not banned, and an account that is not brand new."""
    prof = await my_profile(conn, ctx)
    if prof is None and write in ("vote", "report"):
        return None     # voting and reporting need no public name
    if prof is None:
        raise fail(403, "handle_required", "Choose a public name and accept the community guidelines before you post.")
    if prof["banned"] and write != "report":
        raise fail(403, "banned", f"You cannot post in the forum until {prof['banned_until'].strftime('%d %b %Y')}." + (f" Reason: {prof['banned_reason']}" if prof["banned_reason"] else ""))
    if write == "post" and MIN_ACCOUNT_AGE_SECONDS > 0:
        age = await conn.fetchval("SELECT extract(epoch FROM (now() - created_at)) FROM users WHERE id = $1", ctx.user_id)
        if age is not None and age < MIN_ACCOUNT_AGE_SECONDS:
            wait = int((MIN_ACCOUNT_AGE_SECONDS - age) // 60) + 1
            raise fail(403, "account_too_new", f"New accounts can post after {MIN_ACCOUNT_AGE_SECONDS // 60} minutes. Please try again in about {wait} minute{'s' if wait != 1 else ''}.")
    return prof


async def judge(conn, ctx: Ctx, kind: str, title: Optional[str], body: str, *, exclude_id: Optional[int] = None) -> Dict[str, Any]:
    """Clean and check a draft. Returns {title, body, hash, hold}; raises the member-facing error when it breaks a rule."""
    title = rules.clean_text(title) if title is not None else None
    body = rules.clean_text(body)
    problem = rules.check_lengths(kind, title, body)
    if problem:
        raise fail(422, "bad_length", problem)
    standing = await conn.fetchval("SELECT count(*) FROM forum_posts WHERE user_id = $1 AND status = 'visible'", ctx.user_id)
    whole = f"{title}\n{body}" if title else body
    verdict = rules.check_text(whole, trusted=standing >= TRUSTED_AFTER)
    if not verdict.ok:
        raise fail(422, verdict.code, verdict.message)
    digest = rules.content_hash(whole)
    dup = await conn.fetchval(
        """SELECT 1 FROM forum_posts WHERE content_hash = $1 AND ($2::bigint IS NULL OR id <> $2) AND status <> 'deleted'
              AND ((user_id = $3 AND created_at > now() - interval '24 hours') OR created_at > now() - interval '1 hour') LIMIT 1""", digest, exclude_id, ctx.user_id)
    if dup:
        raise fail(409, "duplicate", "That has already been posted. Please do not repeat the same message.")
    return {"title": title, "body": body, "hash": digest, "hold": verdict.hold}


# ------------------------------------------------------------------ profile
@router.get("/forum/me")
async def forum_me(request: Request):
    """Who the viewer is in the forum (always answerable, also for visitors) and the limits the writing forms should show."""
    ctx = await current(request)
    base: Dict[str, Any] = {"signedIn": ctx.authed, "handle": None, "canPost": False, "banned": False, "moderator": is_mod(ctx), "rules": RULES_PUBLIC}
    if ctx.authed:
        async with pool_of(request).acquire() as conn:
            prof = await my_profile(conn, ctx)
        base["handle"] = prof["handle"] if prof else None
        base["banned"] = bool(prof and prof["banned"])
        base["canPost"] = bool(prof) and not base["banned"]
        base["bannedUntil"] = prof["banned_until"].isoformat() if prof and prof["banned"] else None
    return out(base)


@router.post("/forum/profile", status_code=201)
async def forum_profile(request: Request, body: ProfileIn, ctx: Ctx = Depends(secure_ctx)):
    """Choose the public name, once. It is shown instead of the email or the account name, and it cannot be changed later (so a name is never swapped to impersonate someone)."""
    if not body.accept:
        raise fail(422, "accept_required", "Please accept the community guidelines to join the discussion.")
    handle = body.handle.strip()
    problem = rules.check_handle(handle)
    if problem:
        raise fail(422, "bad_handle", problem)
    await limit(request, "forum_profile", ip_of(request), 10, 3600)
    async with pool_of(request).acquire() as conn:
        if await my_profile(conn, ctx):
            raise fail(409, "handle_exists", "You already have a forum name.")
        try:
            await conn.execute("INSERT INTO forum_profiles (user_id, handle) VALUES ($1, $2)", ctx.user_id, handle)
        except asyncpg.UniqueViolationError:
            raise fail(409, "handle_taken", "That name is taken. Please choose another.")
    return out({"status": "created", "handle": handle}, 201)


# ------------------------------------------------------------------ reading
async def known_symbol(request: Request, symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not SYMBOL.match(symbol):
        raise fail(400, "invalid_symbol", "That is not a valid company symbol.")
    async with pool_of(request).acquire() as conn:
        if not await conn.fetchval("SELECT 1 FROM companies WHERE symbol = $1", symbol):
            raise fail(404, "unknown_company", "We do not have that company.")
    return symbol


@router.get("/forum/threads")
async def list_threads(request: Request, symbol: str = Query("", max_length=24), sort: Literal["active", "recent", "top"] = "active", q: str = Query("", max_length=60),
                       page: int = Query(1, ge=1, le=2000), per: int = Query(20, ge=1, le=PER_PAGE_MAX)):
    ctx = await current(request)
    sym = await known_symbol(request, symbol) if symbol.strip() else None
    like = "%" + re.sub(r"([\\%_])", r"\\\1", q.strip().lower()) + "%" if q.strip() else None
    async with pool_of(request).acquire() as conn:
        rows = await conn.fetch(f"""{POST_SELECT} WHERE p.thread_id IS NULL AND p.status = 'visible' AND ($2::text IS NULL OR p.symbol = $2)
                                    AND ($3::text IS NULL OR lower(p.title) LIKE $3) ORDER BY {SORTS[sort]} LIMIT $4 OFFSET $5""", ctx.user_id, sym, like, per, (page - 1) * per)
        total = await conn.fetchval("SELECT count(*) FROM forum_posts p WHERE p.thread_id IS NULL AND p.status = 'visible' AND ($1::text IS NULL OR p.symbol = $1) AND ($2::text IS NULL OR lower(p.title) LIKE $2)", sym, like)
    return out({"threads": [post_json(r, ctx, preview=True) for r in rows], "total": total, "page": page, "per": per, "pages": max(1, -(-total // per)), "sort": sort, "symbol": sym})


@router.get("/forum/companies")
async def active_companies(request: Request, limit_: int = Query(12, ge=1, le=30, alias="limit")):
    """Companies with discussion in the last 30 days, most recently active first. Real counts only: an empty forum returns an empty list."""
    async with pool_of(request).acquire() as conn:
        rows = await conn.fetch(
            """SELECT p.symbol, c.name, count(*) AS threads, max(p.last_activity_at) AS last_at,
                      sum((SELECT count(*) FROM forum_posts r WHERE r.thread_id = p.id AND r.status = 'visible')) AS replies
               FROM forum_posts p JOIN companies c ON c.symbol = p.symbol
               WHERE p.thread_id IS NULL AND p.status = 'visible' AND p.last_activity_at > now() - interval '30 days'
               GROUP BY p.symbol, c.name ORDER BY max(p.last_activity_at) DESC LIMIT $1""", limit_)
    return out({"companies": [{"symbol": r["symbol"], "name": r["name"], "threads": r["threads"], "replies": int(r["replies"] or 0), "lastActivityAt": r["last_at"].isoformat()} for r in rows]})


@router.get("/forum/stats")
async def company_stats(request: Request, symbol: str = Query(max_length=24)):
    """Counts for the 'Discussion' link on a stock page."""
    sym = await known_symbol(request, symbol)
    async with pool_of(request).acquire() as conn:
        row = await conn.fetchrow(
            """SELECT count(*) AS threads, max(last_activity_at) AS last_at,
                      coalesce(sum((SELECT count(*) FROM forum_posts r WHERE r.thread_id = p.id AND r.status = 'visible')), 0) AS replies
               FROM forum_posts p WHERE p.symbol = $1 AND p.thread_id IS NULL AND p.status = 'visible'""", sym)
    return out({"symbol": sym, "threads": row["threads"], "replies": int(row["replies"]), "lastActivityAt": row["last_at"].isoformat() if row["last_at"] else None})


@router.get("/forum/threads/{tid}")
async def get_thread(request: Request, tid: int, page: int = Query(1, ge=1, le=2000)):
    ctx = await current(request)
    if tid > 2**62:
        raise fail(404, "not_found", "That discussion does not exist.")
    async with pool_of(request).acquire() as conn:
        root = await conn.fetchrow(f"{POST_SELECT} WHERE p.id = $2 AND p.thread_id IS NULL", ctx.user_id, tid)
        if root is None:
            raise fail(404, "not_found", "That discussion does not exist.")
        mine = ctx.authed and str(root["user_id"]) == ctx.user_id
        if root["status"] in ("deleted", "removed"):
            raise fail(410, "removed", TOMBSTONE[root["status"]])
        if root["status"] in ("held", "hidden") and not (mine or is_mod(ctx)):
            raise fail(404, "not_found", "That discussion does not exist.")
        see_all = is_mod(ctx)
        total = await conn.fetchval("SELECT count(*) FROM forum_posts WHERE thread_id = $1 AND (status <> 'held' OR user_id = $2::uuid OR $3)", tid, ctx.user_id, see_all)
        replies = await conn.fetch(f"{POST_SELECT} WHERE p.thread_id = $2 AND (p.status <> 'held' OR p.user_id = $1::uuid OR $3) ORDER BY p.created_at, p.id LIMIT $4 OFFSET $5",
                                   ctx.user_id, tid, see_all, REPLIES_PER_PAGE, (page - 1) * REPLIES_PER_PAGE)
    return out({"thread": post_json(root, ctx), "replies": [post_json(r, ctx) for r in replies], "total": total, "page": page, "per": REPLIES_PER_PAGE,
                "pages": max(1, -(-total // REPLIES_PER_PAGE))})


# ------------------------------------------------------------------ writing
async def write_limits(request: Request, ctx: Ctx, kind: str) -> None:
    if kind == "ip":
        await limit(request, "forum_ip", ip_of(request), 60, 3600)     # every attempt, accepted or not
        return
    if kind == "thread":
        await limit(request, "forum_thread", ctx.user_id, 3, 3600)
        await limit(request, "forum_thread_day", ctx.user_id, 8, 86400)
    else:
        await limit(request, "forum_reply", ctx.user_id, 10, 600)
        await limit(request, "forum_reply_day", ctx.user_id, 80, 86400)


async def store_post(conn, ctx: Ctx, symbol: str, thread_id: Optional[int], checked: Dict[str, Any]) -> int:
    status = "held" if checked["hold"] else "visible"
    pid = await conn.fetchval(
        """INSERT INTO forum_posts (thread_id, symbol, user_id, title, body, content_hash, status, flag_reasons)
           VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id""",
        thread_id, symbol, ctx.user_id, checked["title"], checked["body"], checked["hash"], status, checked["hold"])
    if thread_id and status == "visible":
        await conn.execute("UPDATE forum_posts SET last_activity_at = now() WHERE id = $1", thread_id)
    return pid


@router.post("/forum/threads", status_code=201)
async def create_thread(request: Request, body: ThreadIn, ctx: Ctx = Depends(secure_ctx)):
    symbol = await known_symbol(request, body.symbol)
    await write_limits(request, ctx, "ip")
    async with pool_of(request).acquire() as conn:
        await posting_member(request, conn, ctx)
        checked = await judge(conn, ctx, "thread", body.title, body.body)
        await write_limits(request, ctx, "thread")      # only posts that pass the rules use up the member's allowance
        pid = await store_post(conn, ctx, symbol, None, checked)
        row = await conn.fetchrow(f"{POST_SELECT} WHERE p.id = $2", ctx.user_id, pid)
    return out({"status": "held" if checked["hold"] else "posted", "post": post_json(row, ctx),
                **({"detail": "Thanks. A moderator will look at this before others can see it."} if checked["hold"] else {})}, 201)


@router.post("/forum/threads/{tid}/replies", status_code=201)
async def create_reply(request: Request, tid: int, body: ReplyIn, ctx: Ctx = Depends(secure_ctx)):
    if tid > 2**62:
        raise fail(404, "not_found", "That discussion does not exist.")
    async with pool_of(request).acquire() as conn:
        root = await conn.fetchrow("SELECT id, symbol, status FROM forum_posts WHERE id = $1 AND thread_id IS NULL", tid)
        if root is None or root["status"] != "visible":
            raise fail(404 if root is None else 409, "not_found" if root is None else "thread_closed", "You can only reply to a discussion that is open.")
        await write_limits(request, ctx, "ip")
        await posting_member(request, conn, ctx)
        checked = await judge(conn, ctx, "reply", None, body.body)
        await write_limits(request, ctx, "reply")
        pid = await store_post(conn, ctx, root["symbol"], tid, checked)
        row = await conn.fetchrow(f"{POST_SELECT} WHERE p.id = $2", ctx.user_id, pid)
    return out({"status": "held" if checked["hold"] else "posted", "post": post_json(row, ctx),
                **({"detail": "Thanks. A moderator will look at this before others can see it."} if checked["hold"] else {})}, 201)


async def own_post(conn, ctx: Ctx, pid: int):
    row = await conn.fetchrow("SELECT id, thread_id, user_id, status, symbol, title, extract(epoch FROM (now() - created_at)) AS age_s FROM forum_posts WHERE id = $1", pid)
    if row is None or str(row["user_id"]) != ctx.user_id:
        raise fail(404, "not_found", "That post does not exist.")   # not "forbidden": other people's posts are not probed
    return row


@router.patch("/forum/posts/{pid}")
async def edit_post(request: Request, pid: int, body: EditIn, ctx: Ctx = Depends(secure_ctx)):
    if pid > 2**62:
        raise fail(404, "not_found", "That post does not exist.")
    await limit(request, "forum_edit", ctx.user_id, 20, 3600)
    async with pool_of(request).acquire() as conn:
        row = await own_post(conn, ctx, pid)
        await posting_member(request, conn, ctx, write="edit")
        if row["status"] not in ("visible", "held"):
            raise fail(409, "not_editable", "This post can no longer be changed.")
        if row["age_s"] > EDIT_WINDOW_SECONDS:
            raise fail(403, "edit_window_closed", f"Posts can be edited for {EDIT_WINDOW_SECONDS // 60} minutes after they are written. You can delete it and write it again.")
        if row["thread_id"] is None and body.title is None:
            raise fail(422, "bad_length", "The title needs a few words.")
        checked = await judge(conn, ctx, "reply" if row["thread_id"] else "thread", body.title if row["thread_id"] is None else None, body.body, exclude_id=pid)
        status = "held" if (checked["hold"] or row["status"] == "held") else "visible"
        await conn.execute("UPDATE forum_posts SET title = $2, body = $3, content_hash = $4, status = $5, flag_reasons = $6, edited_at = now() WHERE id = $1",
                           pid, checked["title"], checked["body"], checked["hash"], status, checked["hold"] if checked["hold"] else [])
        full = await conn.fetchrow(f"{POST_SELECT} WHERE p.id = $2", ctx.user_id, pid)
    return out({"status": "held" if status == "held" else "saved", "post": post_json(full, ctx)})


@router.delete("/forum/posts/{pid}")
async def delete_post(request: Request, pid: int, ctx: Ctx = Depends(secure_ctx)):
    """Soft delete by the author, at any time: the text stops being served, the row stays for the moderation trail."""
    if pid > 2**62:
        raise fail(404, "not_found", "That post does not exist.")
    async with pool_of(request).acquire() as conn:
        row = await own_post(conn, ctx, pid)
        if row["status"] in ("deleted", "removed"):
            return out({"status": row["status"]})
        await conn.execute("UPDATE forum_posts SET status = 'deleted' WHERE id = $1", pid)
    return out({"status": "deleted"})


async def visible_post(conn, pid: int):
    if pid > 2**62:
        raise fail(404, "not_found", "That post does not exist.")
    row = await conn.fetchrow("SELECT id, user_id, status FROM forum_posts WHERE id = $1", pid)
    if row is None or row["status"] != "visible":
        raise fail(404, "not_found", "That post does not exist.")
    return row


@router.put("/forum/posts/{pid}/vote")
async def vote(request: Request, pid: int, ctx: Ctx = Depends(secure_ctx)):
    await limit(request, "forum_vote", ctx.user_id, 60, 60)
    async with pool_of(request).acquire() as conn:
        row = await visible_post(conn, pid)
        if str(row["user_id"]) == ctx.user_id:
            raise fail(403, "own_post", "You cannot upvote your own post.")
        await posting_member(request, conn, ctx, write="vote")
        async with conn.transaction():
            if await conn.fetchval("INSERT INTO forum_votes (post_id, user_id) VALUES ($1, $2) ON CONFLICT DO NOTHING RETURNING 1", pid, ctx.user_id):
                await conn.execute("UPDATE forum_posts SET upvotes = upvotes + 1 WHERE id = $1", pid)
        n = await conn.fetchval("SELECT upvotes FROM forum_posts WHERE id = $1", pid)
    return out({"upvotes": n, "voted": True})


@router.delete("/forum/posts/{pid}/vote")
async def unvote(request: Request, pid: int, ctx: Ctx = Depends(secure_ctx)):
    await limit(request, "forum_vote", ctx.user_id, 60, 60)
    async with pool_of(request).acquire() as conn:
        await visible_post(conn, pid)
        async with conn.transaction():
            if await conn.fetchval("DELETE FROM forum_votes WHERE post_id = $1 AND user_id = $2 RETURNING 1", pid, ctx.user_id):
                await conn.execute("UPDATE forum_posts SET upvotes = greatest(upvotes - 1, 0) WHERE id = $1", pid)
        n = await conn.fetchval("SELECT upvotes FROM forum_posts WHERE id = $1", pid)
    return out({"upvotes": n, "voted": False})


@router.post("/forum/posts/{pid}/report")
async def report(request: Request, pid: int, body: ReportIn, ctx: Ctx = Depends(secure_ctx)):
    """Any signed-in member may report a post once. After REPORT_HIDE_AT different members have, it is hidden until a moderator decides."""
    await limit(request, "forum_report", ctx.user_id, 10, 3600)
    async with pool_of(request).acquire() as conn:
        row = await visible_post(conn, pid)
        if str(row["user_id"]) == ctx.user_id:
            raise fail(403, "own_post", "You cannot report your own post. Delete it instead.")
        note = rules.clean_text(body.note or "")[:300] or None
        async with conn.transaction():
            fresh = await conn.fetchval("INSERT INTO forum_reports (post_id, reporter_id, reason, note) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1", pid, ctx.user_id, body.reason, note)
            open_n = await conn.fetchval("SELECT count(*) FROM forum_reports WHERE post_id = $1 AND resolved_at IS NULL", pid)
            hidden = False
            if open_n >= REPORT_HIDE_AT:
                hidden = bool(await conn.fetchval(
                    "UPDATE forum_posts SET status = 'hidden', moderation_note = $2 WHERE id = $1 AND status = 'visible' RETURNING 1", pid, f"Hidden automatically after {open_n} reports."))
    return out({"status": "reported" if fresh else "already_reported", "hidden": hidden})


# ------------------------------------------------------------------ moderation (administrators, two-step sign-in required)
def queue_json(r: Any, reports: List[Any]) -> Dict[str, Any]:
    return {"id": r["id"], "threadId": r["thread_id"] or r["id"], "kind": "reply" if r["thread_id"] else "thread", "symbol": r["symbol"], "title": r["title"], "body": r["body"],
            "status": r["status"], "flagReasons": list(r["flag_reasons"]), "createdAt": r["created_at"].isoformat(), "moderationNote": r["moderation_note"],
            "author": {"userId": str(r["user_id"]), "handle": r["handle"] or "member", "banned": bool(r["banned"]), "email": r["email"]},
            "reports": [{"reason": x["reason"], "note": x["note"], "at": x["created_at"].isoformat(), "by": x["handle"] or "member"} for x in reports]}


@router.get("/admin/forum/queue")
async def mod_queue(request: Request, kind: Literal["open", "held", "hidden", "recent"] = "open", page: int = Query(1, ge=1, le=1000), ctx: Ctx = Depends(admin_ctx)):
    """What needs a decision: posts held by the keyword rules, posts hidden by member reports, and (kind=recent) the latest posts of any status to review proactively."""
    cond = {"open": "p.status IN ('held', 'hidden')", "held": "p.status = 'held'", "hidden": "p.status = 'hidden'", "recent": "TRUE"}[kind]
    per = 25
    async with pool_of(request).acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT p.id, p.thread_id, p.symbol, p.user_id, p.title, p.body, p.status, p.flag_reasons, p.created_at, p.moderation_note, pr.handle, u.email,
                       (pr.banned_until IS NOT NULL AND pr.banned_until > now()) AS banned
                FROM forum_posts p JOIN users u ON u.id = p.user_id LEFT JOIN forum_profiles pr ON pr.user_id = p.user_id
                WHERE {cond} ORDER BY p.created_at {'DESC' if kind == 'recent' else 'ASC'}, p.id LIMIT $1 OFFSET $2""", per, (page - 1) * per)  # nosec B608 - cond and order are fixed values, input is bound
        reps = await conn.fetch("""SELECT r.post_id, r.reason, r.note, r.created_at, pr.handle FROM forum_reports r LEFT JOIN forum_profiles pr ON pr.user_id = r.reporter_id
                                   WHERE r.post_id = ANY($1::bigint[]) AND r.resolved_at IS NULL ORDER BY r.created_at""", [r["id"] for r in rows])
        counts = await conn.fetchrow("SELECT count(*) FILTER (WHERE status = 'held') AS held, count(*) FILTER (WHERE status = 'hidden') AS hidden FROM forum_posts")
        total = await conn.fetchval(f"SELECT count(*) FROM forum_posts p WHERE {cond}")  # nosec B608 - cond comes from a fixed mapping
    by_post: Dict[int, List[Any]] = {}
    for x in reps:
        by_post.setdefault(x["post_id"], []).append(x)
    return out({"items": [queue_json(r, by_post.get(r["id"], [])) for r in rows], "counts": {"held": counts["held"], "hidden": counts["hidden"]}, "total": total, "page": page, "per": per})


async def moderate(request: Request, pid: int, ctx: Ctx, status: str, resolution: str, note: str, action: str) -> Response:
    if pid > 2**62:
        raise fail(404, "not_found", "That post does not exist.")
    async with pool_of(request).acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT id, thread_id FROM forum_posts WHERE id = $1 FOR UPDATE", pid)
            if row is None:
                raise fail(404, "not_found", "That post does not exist.")
            await conn.execute("UPDATE forum_posts SET status = $2, moderated_by = $3, moderated_at = now(), moderation_note = NULLIF($4, ''), flag_reasons = CASE WHEN $2 = 'visible' THEN '{}' ELSE flag_reasons END WHERE id = $1",
                               pid, status, ctx.user_id, note)
            await conn.execute("UPDATE forum_reports SET resolved_at = now(), resolved_by = $2, resolution = $3 WHERE post_id = $1 AND resolved_at IS NULL", pid, ctx.user_id, resolution)
            if status == "visible" and row["thread_id"]:
                await conn.execute("UPDATE forum_posts SET last_activity_at = now() WHERE id = $1", row["thread_id"])
    await audit(pool_of(request), ctx.user_id, action, str(pid), ip_of(request), note=note)
    return out({"status": status})


@router.post("/admin/forum/posts/{pid}/approve")
async def mod_approve(request: Request, pid: int, body: NoteIn = NoteIn(), ctx: Ctx = Depends(admin_ctx)):
    """Show a held or hidden (or wrongly removed) post; the reports against it are closed as dismissed."""
    return await moderate(request, pid, ctx, "visible", "dismissed", body.note, "forum_approve")


@router.post("/admin/forum/posts/{pid}/remove")
async def mod_remove(request: Request, pid: int, body: NoteIn = NoteIn(), ctx: Ctx = Depends(admin_ctx)):
    """Take a post down for breaking the guidelines; the reports against it are closed as upheld."""
    return await moderate(request, pid, ctx, "removed", "upheld", body.note, "forum_remove")


@router.post("/admin/forum/users/{uid}/ban")
async def mod_ban(request: Request, uid: str, body: BanIn, ctx: Ctx = Depends(admin_ctx)):
    uid = valid_uuid(uid)
    if uid == ctx.user_id:
        raise fail(400, "self", "You cannot ban yourself.")
    async with pool_of(request).acquire() as conn:
        done = await conn.fetchval("UPDATE forum_profiles SET banned_until = now() + $2 * interval '1 day', banned_reason = NULLIF($3, '') WHERE user_id = $1::uuid RETURNING 1", uid, body.days, body.reason)
    if not done:
        raise fail(404, "not_found", "That member has no forum profile.")
    await audit(pool_of(request), ctx.user_id, "forum_ban", uid, ip_of(request), days=body.days, reason=body.reason)
    return out({"status": "banned", "days": body.days})


@router.delete("/admin/forum/users/{uid}/ban")
async def mod_unban(request: Request, uid: str, ctx: Ctx = Depends(admin_ctx)):
    uid = valid_uuid(uid)
    async with pool_of(request).acquire() as conn:
        done = await conn.fetchval("UPDATE forum_profiles SET banned_until = NULL, banned_reason = NULL WHERE user_id = $1::uuid RETURNING 1", uid)
    if not done:
        raise fail(404, "not_found", "That member has no forum profile.")
    await audit(pool_of(request), ctx.user_id, "forum_unban", uid, ip_of(request))
    return out({"status": "unbanned"})
