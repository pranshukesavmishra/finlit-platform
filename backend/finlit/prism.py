"""FinLit Prism: the Gold plan's advanced financial-health rating (docs/prism/CONTRACT.md is the binding description).

    GET  /api/prism/status                                        is Prism connected? Public.
    GET  /api/prism/reports/latest?symbol=TCS&statement=...       the newest stored report for a company, without calculating
    POST /api/prism/reports  {"symbol", "statement", "refresh"}   calculate, or reuse a stored report under 6 hours old
    GET  /api/prism/reports/{id}/pdf                              the PDF of exactly that calculation, while its snapshot lives (30 minutes)

The model runs in the site backend (site-api/backend, POST /api/premium-reports). Those routes are for administrators only, so this module
is the members' door: it checks the plan here (Gold, administrators, and the showcase companies for everyone), then calls the site backend
with a five-minute administrator token signed with the shared CMS_JWT_SECRET. That token never leaves this server.

One calculation takes one to two minutes and many provider calls, so:
  * the reader view of the newest report per company and statement basis is kept in Postgres (prism_reports) and reused for 6 hours;
  * the full signed snapshot, which the PDF renderer needs and the browser never sees, is kept in Redis for its 30 minutes, with the token
    subject it was signed for (the site backend renders the PDF only for that same subject);
  * each member may calculate 20 reports a day (by the Indian date; administrators are not limited; visitors, who may only open the
    showcase companies, are counted by address), at most 2 calculations run at once in a process, and a Redis lock makes a second request
    for the same company wait for the first one's answer instead of calculating it again.

The rating describes a company's financial health from its filings and prices. It is not a recommendation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import httpx
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from .auth.entitlements import has
from .auth.routes import IST, NO_STORE, ip_of, pre_session_guard, secure_ctx
from .auth.service import Ctx, current
from .premium import gateway_token

log = logging.getLogger("finlit.prism")
router = APIRouter(prefix="/api/prism")

PRISM_NAME = "FinLit Prism"
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
REPORT_ID = re.compile(r"^[a-f0-9]{32}$")
STATEMENTS = ("consolidated", "standalone")
REUSE_SECONDS = 6 * 3600           # a stored report younger than this is served instead of calculating again (unless refresh)
SNAPSHOT_SECONDS = 1800            # the site backend signs a snapshot for 30 minutes; it is never kept longer
DAILY_LIMIT = 20                   # calculations per member per Indian day; refreshes count, reuse does not
SLOTS = 2                          # calculations running at once in this process
TOKEN_SECONDS = 300
GENERATE_SECONDS = 170.0           # one calculation takes 60 to 120 seconds
LOCK_SECONDS = int(GENERATE_SECONDS) + 30
WAIT_STEP = 1.0                    # how often a request waiting for another one's calculation looks again
FAIL_SECONDS = 30                  # how long a failed calculation's answer is handed to the requests that waited for it
STATUS_SECONDS = 60                # the "is the site backend up" check is repeated at most this often
PING_SECONDS = 3.0
BUSY_RETRY = 30
# Engineering details of the signed snapshot that the browser never receives.
INTERNAL = ("calculationTrace", "inputs", "inputHash", "snapshotReceipt", "snapshotExpiresAt")

CALM = f"{PRISM_NAME} could not finish this calculation just now. Please try again in a few minutes."
NOT_CONNECTED = f"{PRISM_NAME} is not connected right now. Please try again later."


def _reply(body: Dict[str, Any], status: int = 200, retry: Optional[int] = None) -> JSONResponse:
    headers = {**NO_STORE, "Retry-After": str(retry)} if retry else NO_STORE
    return JSONResponse(body, status_code=status, headers=headers)


def _bad(detail: str) -> JSONResponse:
    return _reply({"status": "bad_request", "detail": detail}, 422)


def _client(app) -> httpx.AsyncClient:
    """One client for every call to the site backend, with a read timeout long enough for a whole calculation."""
    client = getattr(app.state, "prism_client", None)
    if client is None:
        client = app.state.prism_client = httpx.AsyncClient(base_url=app.state.settings.site_api_url, limits=httpx.Limits(max_connections=8),
                                                            timeout=httpx.Timeout(GENERATE_SECONDS, connect=10.0), follow_redirects=False)
    return client


def _slots(app) -> asyncio.Semaphore:
    slots = getattr(app.state, "prism_slots", None)
    if slots is None:
        slots = app.state.prism_slots = asyncio.Semaphore(SLOTS)
    return slots


def connected(settings) -> bool:
    """The site backend is configured and the shared secret is long enough for it to accept our tokens (it refuses shorter ones)."""
    return bool(settings.site_api_url) and len(settings.cms_jwt_secret.encode()) >= 32


def subject(ctx: Ctx) -> str:
    return f"prism:{ctx.user_id}" if ctx.authed else "prism:visitor"


def reader_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in snapshot.items() if k not in INTERNAL}


def target(symbol: Any, statement: Any) -> Optional[Tuple[str, str]]:
    """(SYMBOL, statement) when both are valid, else None."""
    if not isinstance(symbol, str) or not isinstance(statement, str):
        return None
    symbol, statement = symbol.strip().upper(), statement.strip().lower()
    return (symbol, statement) if SYMBOL.match(symbol) and statement in STATEMENTS else None


async def _access(request: Request, symbol: str) -> Tuple[Ctx, Optional[JSONResponse]]:
    """Gold members and administrators see every company; the showcase companies are open to everyone, as on the rest of the site."""
    ctx = await current(request)
    if symbol in request.app.state.settings.showcase_symbols or ctx.role == "admin" or has(ctx.plan, "gold"):
        return ctx, None
    detail = f"{PRISM_NAME} is part of the Gold plan." if ctx.authed else f"Sign in with the Gold plan to see {PRISM_NAME}."
    return ctx, _reply({"status": "plan_required", "detail": detail, "plan": "gold"}, 403)


# ------------------------------------------------------------------ storage
async def _stored(store, symbol: str, statement: str):
    return await store.pool.fetchrow("SELECT id, report, generated_at, pdf_until FROM prism_reports WHERE symbol = $1 AND statement = $2",
                                     symbol, statement)


def _shape(row, cached: bool) -> Dict[str, Any]:
    """The PrismReport of a stored row: the reader view, whether it came from storage, and until when its PDF can be downloaded."""
    until = row["pdf_until"]
    live = until is not None and until > datetime.now(timezone.utc)
    return {**json.loads(row["report"]), "cached": cached, "pdfAvailableUntil": until.isoformat() if live else None}


def _fresh(row) -> bool:
    return row is not None and (datetime.now(timezone.utc) - row["generated_at"]).total_seconds() < REUSE_SECONDS


async def _save(store, symbol: str, statement: str, view: Dict[str, Any], pdf_until: Optional[datetime]):
    rating = view.get("rating") or {}
    final = rating.get("final")
    return await store.pool.fetchrow(
        """INSERT INTO prism_reports (symbol, statement, id, report, model_version, final, label, status, generated_at, pdf_until)
           VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, now(), $9)
           ON CONFLICT (symbol, statement) DO UPDATE SET id = EXCLUDED.id, report = EXCLUDED.report, model_version = EXCLUDED.model_version,
               final = EXCLUDED.final, label = EXCLUDED.label, status = EXCLUDED.status, generated_at = EXCLUDED.generated_at, pdf_until = EXCLUDED.pdf_until
           RETURNING id, report, generated_at, pdf_until""",
        symbol, statement, view["id"], json.dumps(view, allow_nan=False), rating.get("modelVersion"),
        float(final) if isinstance(final, (int, float)) else None, rating.get("label"), rating.get("status"), pdf_until)


async def _keep_snapshot(redis, snapshot: Dict[str, Any], sub: str, symbol: str) -> Optional[datetime]:
    """Keep the signed snapshot for the PDF until it expires (at most 30 minutes). Returns that time, or None when it could not be kept:
    the report is still shown, only without a PDF."""
    try:
        expires = datetime.fromisoformat(str(snapshot["snapshotExpiresAt"]))
        expires = expires if expires.tzinfo else expires.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        ttl = min(SNAPSHOT_SECONDS, int((expires - now).total_seconds()))
        if ttl <= 0:
            return None
        await redis.set(f"prism:snap:{snapshot['id']}", json.dumps({"sub": sub, "symbol": symbol, "snapshot": snapshot}, allow_nan=False), ex=ttl)
        return now + timedelta(seconds=ttl)
    except Exception as exc:
        log.warning("prism snapshot not kept for %s: %s", symbol, type(exc).__name__)
        return None


# ------------------------------------------------------------------ the site backend
async def _call(app, path: str, sub: str, payload: Dict[str, Any]) -> httpx.Response:
    token = gateway_token(app.state.settings.cms_jwt_secret, ttl=TOKEN_SECONDS, sub=sub)
    return await _client(app).post(path, json=payload, headers={"Authorization": f"Bearer {token}"})


def _ready(r: Optional[httpx.Response]) -> Optional[Dict[str, Any]]:
    """The signed snapshot from a successful inline calculation, or None."""
    if r is None or r.status_code != 200:
        return None
    try:
        body = r.json()
    except ValueError:
        return None
    ok = isinstance(body, dict) and body.get("state") == "ready" and REPORT_ID.match(str(body.get("id"))) and isinstance(body.get("snapshotReceipt"), str)
    return body if ok else None


def _upstream_detail(r: httpx.Response) -> Optional[str]:
    try:
        detail = r.json().get("detail")
    except (ValueError, AttributeError):
        return None
    return detail if isinstance(detail, str) and len(detail) <= 200 else None


def _refused(r: httpx.Response) -> Tuple[int, Dict[str, Any]]:
    # The site backend accepts any HS256 token signed with its CMS_JWT_SECRET: a refusal means the two services hold different secrets.
    log.error("site backend refused the Prism token (HTTP %s): CMS_JWT_SECRET differs between the research API and the site backend", r.status_code)
    return 503, {"status": "unavailable", "detail": NOT_CONNECTED}


def _failure(r: Optional[httpx.Response]) -> Tuple[int, Dict[str, Any], Optional[int]]:
    """(status, body, Retry-After) for a calculation the site backend did not complete."""
    code = r.status_code if r is not None else 0
    if code == 404:
        return 404, {"status": "not_found", "detail": "No listed company was found for this symbol."}, None
    if code in (400, 422):
        return 422, {"status": "bad_request", "detail": _upstream_detail(r) or "This company cannot be rated as asked."}, None
    if code == 429:
        retry = r.headers.get("retry-after", "")
        return 429, {"status": "busy", "detail": f"{PRISM_NAME} is busy. Please try again shortly."}, int(retry) if retry.isdigit() else BUSY_RETRY
    if code in (401, 403):
        return (*_refused(r), None)
    if r is not None and code < 500:
        log.warning("site backend answered a Prism calculation with HTTP %s", code)
    return 502, {"status": "unavailable", "detail": CALM}, None


# ------------------------------------------------------------------ limits
def _until_midnight(now: datetime) -> int:
    t = now.astimezone(IST)
    tomorrow = datetime.combine(t.date() + timedelta(days=1), datetime.min.time(), tzinfo=IST)
    return max(1, int((tomorrow - t).total_seconds()))


async def _count(request: Request, ctx: Ctx) -> Tuple[Optional[str], Optional[int]]:
    """Count one calculation against today's allowance. (counter key to refund on failure, None) or (None, seconds until it renews)."""
    if ctx.role == "admin":
        return None, None
    now = datetime.now(timezone.utc)
    who = ctx.user_id or "ip:" + ip_of(request)
    key = f"prism:day:{who}:{now.astimezone(IST):%Y%m%d}"
    redis = request.app.state.store.redis
    used = await redis.incr(key)
    if used == 1:
        await redis.expire(key, 2 * 86400)
    if used > DAILY_LIMIT:
        await redis.decr(key)
        return None, _until_midnight(now)
    return key, None


# ------------------------------------------------------------------ routes
@router.get("/status")
async def prism_status(request: Request) -> JSONResponse:
    app, reason = request.app, None
    if not connected(app.state.settings):
        reason = "not_configured"
    elif not await _reachable(app):
        reason = "not_reachable"
    try:
        version = await app.state.store.pool.fetchval("SELECT model_version FROM prism_reports ORDER BY generated_at DESC LIMIT 1")
    except Exception:
        version = None
    return _reply({"name": PRISM_NAME, "available": reason is None, "reason": reason, "modelVersion": version})


async def _reachable(app) -> bool:
    """Whether the site backend answers its root within 3 seconds; remembered for a minute so the page can ask freely."""
    seen = getattr(app.state, "prism_ping", None)
    now = time.monotonic()
    if seen and now - seen[0] < STATUS_SECONDS:
        return seen[1]
    try:
        ok = (await _client(app).get("/api/", timeout=PING_SECONDS)).status_code == 200
    except httpx.HTTPError:
        ok = False
    app.state.prism_ping = (now, ok)
    return ok


@router.get("/reports/latest")
async def latest(request: Request, symbol: str = Query("", max_length=40), statement: str = Query("consolidated", max_length=20)) -> JSONResponse:
    wanted = target(symbol, statement)
    if not wanted:
        return _bad("Choose a company symbol and a statement basis (consolidated or standalone).")
    _, refusal = await _access(request, wanted[0])
    if refusal:
        return refusal
    row = await _stored(request.app.state.store, *wanted)
    if row is None:
        return _reply({"status": "none", "detail": f"No {PRISM_NAME} report has been calculated for this company yet."}, 404)
    return _reply(_shape(row, cached=True))


@router.post("/reports")
async def create(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _bad("Send the company symbol and statement basis.")
    wanted = target(body.get("symbol"), body.get("statement", "consolidated"))
    if not wanted:
        return _bad("Choose a company symbol and a statement basis (consolidated or standalone).")
    symbol, statement = wanted
    ctx, refusal = await _access(request, symbol)
    if refusal:
        return refusal
    if ctx.authed:
        await secure_ctx(request)          # a signed-in member's request must come from our pages (Origin and CSRF token)
    else:
        pre_session_guard(request)         # a visitor (showcase company) has no session, but a browser's Origin must still be ours
    app = request.app
    if not connected(app.state.settings):
        return _reply({"status": "unavailable", "detail": NOT_CONNECTED}, 503)
    store = app.state.store
    # Visitors may open a showcase report but not order a new calculation of one that is still fresh.
    refresh = body.get("refresh") is True and ctx.authed
    row = await _stored(store, symbol, statement)
    if not refresh and _fresh(row):
        return _reply(_shape(row, cached=True))
    lock, token = f"prism:lock:{symbol}:{statement}", secrets.token_hex(8)
    if not await store.redis.set(lock, token, nx=True, ex=LOCK_SECONDS):
        return await _wait_for(app, symbol, statement, lock, row["id"] if row else None)
    try:
        if not refresh:                    # finished by another request between our read and the lock
            row = await _stored(store, symbol, statement)
            if _fresh(row):
                return _reply(_shape(row, cached=True))
        return await _calculate(request, ctx, symbol, statement)
    finally:
        try:
            if (await store.redis.get(lock)) == token.encode():
                await store.redis.delete(lock)
        except Exception as exc:           # the lock expires by itself
            log.warning("prism lock for %s not released: %s", symbol, type(exc).__name__)


async def _wait_for(app, symbol: str, statement: str, lock: str, before: Optional[str]) -> JSONResponse:
    """Another request is calculating this company: wait for its answer and hand over the same result (or the same failure)."""
    redis = app.state.store.redis
    for _ in range(int(LOCK_SECONDS / WAIT_STEP)):
        await asyncio.sleep(WAIT_STEP)
        if not await redis.exists(lock):
            break
    row = await _stored(app.state.store, symbol, statement)
    if row is not None and row["id"] != before:
        return _reply(_shape(row, cached=True))
    failed = await redis.get(f"prism:fail:{symbol}:{statement}")
    if failed:
        status, body, retry = json.loads(failed)
        return _reply(body, status, retry)
    # It ended without calculating (both slots were taken, or its member had used the day's allowance): this request may simply try again.
    return _reply({"status": "busy", "detail": f"{PRISM_NAME} is busy. Please try again shortly."}, 429, 5)


async def _calculate(request: Request, ctx: Ctx, symbol: str, statement: str) -> JSONResponse:
    app = request.app
    redis = app.state.store.redis
    if _slots(app).locked():
        return _reply({"status": "busy", "detail": f"{PRISM_NAME} is calculating other reports. Please try again shortly."}, 429, BUSY_RETRY)
    counter, renew = await _count(request, ctx)
    if renew:
        return _reply({"status": "limit", "detail": f"You have used today's {DAILY_LIMIT} {PRISM_NAME} calculations. Stored reports stay open."},
                      429, renew)
    sub = subject(ctx)
    r: Optional[httpx.Response] = None
    try:
        async with _slots(app):
            r = await _call(app, "/api/premium-reports", sub, {"query": symbol, "statement_type": statement, "delivery": "inline"})
    except httpx.HTTPError as exc:
        log.warning("prism calculation for %s did not reach the site backend: %s", symbol, type(exc).__name__)
    snapshot = _ready(r)
    if snapshot is None:
        if counter:
            await redis.decr(counter)      # nothing was calculated: it does not use up the member's allowance
        status, body, retry = _failure(r)
        await redis.set(f"prism:fail:{symbol}:{statement}", json.dumps([status, body, retry]), ex=FAIL_SECONDS)
        return _reply(body, status, retry)
    view = reader_view(snapshot)
    until = await _keep_snapshot(redis, snapshot, sub, symbol)
    row = await _save(app.state.store, symbol, statement, view, until)
    return _reply(_shape(row, cached=False))


@router.get("/reports/{report_id}/pdf")
async def pdf(request: Request, report_id: str) -> Response:
    if not REPORT_ID.match(report_id):
        return _reply({"status": "not_found", "detail": "No such report."}, 404)
    app = request.app
    raw = await app.state.store.redis.get(f"prism:snap:{report_id}")
    kept = json.loads(raw) if raw else None
    symbol = kept["symbol"] if kept else await app.state.store.pool.fetchval("SELECT symbol FROM prism_reports WHERE id = $1", report_id)
    if symbol is None:
        return _reply({"status": "not_found", "detail": "No such report."}, 404)
    _, refusal = await _access(request, symbol)
    if refusal:
        return refusal
    if kept is None:
        return _expired()
    if not connected(app.state.settings):
        return _reply({"status": "unavailable", "detail": NOT_CONNECTED}, 503)
    snapshot = dict(kept["snapshot"])
    receipt = snapshot.pop("snapshotReceipt")
    try:
        r = await _call(app, "/api/premium-reports/pdf", kept["sub"], {"report": snapshot, "receipt": receipt})
    except httpx.HTTPError as exc:
        log.warning("prism PDF for %s did not reach the site backend: %s", symbol, type(exc).__name__)
        return _reply({"status": "unavailable", "detail": "The PDF could not be prepared just now. Please try again in a moment."}, 502)
    if r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf"):
        filename = f"FinLit-Prism-{symbol}-{report_id[:8]}.pdf"
        return Response(content=r.content, media_type="application/pdf",
                        headers={**NO_STORE, "Content-Disposition": f'attachment; filename="{filename}"', "X-Content-Type-Options": "nosniff"})
    if r.status_code == 400:               # the site backend no longer accepts this snapshot (expired or changed)
        await app.state.store.redis.delete(f"prism:snap:{report_id}")
        return _expired()
    if r.status_code in (401, 403):
        status, body = _refused(r)
        return _reply(body, status)
    log.warning("site backend answered a Prism PDF with HTTP %s", r.status_code)
    return _reply({"status": "unavailable", "detail": "The PDF could not be prepared just now. Please try again in a moment."}, 502)


def _expired() -> JSONResponse:
    return _reply({"status": "expired", "detail": "The PDF of this calculation is no longer available. Recalculate to download a fresh one."}, 410)
