"""FinLit Prism: the Gold plan's advanced financial-health rating (docs/prism/CONTRACT.md is the binding description).

    GET  /api/prism/status                                        is Prism connected? Public.
    GET  /api/prism/reports/latest?symbol=TCS&statement=...       the newest stored report for a company, without calculating;
                                                                  add &view=summary for the small card the stock page shows
    POST /api/prism/reports  {"symbol", "statement", "refresh"}   calculate, or reuse a stored report under 6 hours old
    GET  /api/prism/reports/{id}/pdf                              the PDF of exactly that calculation, while its snapshot lives (30 minutes)

The model runs in the site backend (site-api/backend, POST /api/premium-reports). Those routes are for administrators only, so this module
is the members' door: it checks the plan here (Gold, administrators, and the showcase companies for everyone), then calls the site backend
with a five-minute administrator token signed with the shared CMS_JWT_SECRET. That token never leaves this server.

A calculation used to take one to two minutes (some 250 provider calls, made a few at a time). It now makes the model's real requests together
and keeps what it learned, so a company takes about 5 to 15 seconds the first time and under a second the next (see "Speed" below), and:
  * the reader view of the newest report per company and statement basis is kept in Postgres (prism_reports) and reused for 6 hours;
  * the full signed snapshot, which the PDF renderer needs and the browser never sees, is kept in Redis for its 30 minutes, with the token
    subject it was signed for (the site backend renders the PDF only for that same subject);
  * each member may calculate 20 reports a day (by the Indian date; administrators are not limited; visitors, who may only open the
    showcase companies, are counted by address), at most 2 calculations run at once in a process, and a Redis lock makes a second request
    for the same company wait for the first one's answer instead of calculating it again.

Speed (nothing here changes a number; the model and the data it is fed are the same):
  * the model inputs of a company (statements, prices, ratios, ownership filings, industry list) are kept in Postgres (prism_inputs) for 24
    hours, packed; a repeat calculation (a recalculation after the 6 hours, say) then needs no provider call. "Recalculate" ignores them;
  * the one price-ratio row per industry peer that a median used is kept in Redis for 4 days, shared by every company of that industry;
  * a company opened with no rating starts calculating in the background (`background: true`), the page polls GET /api/prism/jobs and shows
    the rating when it is ready; the nightly pre-calculation covers every company with a full report and yields to a member who is waiting.

The rating describes a company's financial health from its filings and prices. It is not a recommendation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
from .prism_candles import supplied_candles

log = logging.getLogger("finlit.prism")
router = APIRouter(prefix="/api/prism")

PRISM_NAME = "FinLit Prism"
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
REPORT_ID = re.compile(r"^[a-f0-9]{32}\Z")   # \Z, not $: "$" also matches before a trailing newline
STATEMENTS = ("consolidated", "standalone")
REUSE_SECONDS = 6 * 3600           # a stored report younger than this is served instead of calculating again (unless refresh)
SNAPSHOT_SECONDS = 1800            # the site backend signs a snapshot for 30 minutes; it is never kept longer
DAILY_LIMIT = 20                   # calculations per member per Indian day; refreshes count, reuse does not
SLOTS = max(1, min(4, int(os.getenv("PRISM_SLOTS", "2") or 2)))   # calculations at once in this process; keep <= the site backend's PREMIUM_GENERATION_SLOTS
PDF_LIMIT = 30                     # PDF downloads per member (or visitor address) per 10 minutes; each is rendered by the site backend
TOKEN_SECONDS = 300
GENERATE_SECONDS = 170.0           # one calculation takes 60 to 120 seconds
LOCK_SECONDS = int(GENERATE_SECONDS) + 30
WAIT_STEP = 1.0                    # how often a request waiting for another one's calculation looks again
FAIL_SECONDS = 30                  # how long a failed calculation's answer is handed to the requests that waited for it
STATUS_SECONDS = 60                # the "is the site backend up" check is repeated at most this often
PING_SECONDS = 3.0
BUSY_RETRY = 30
SLOT_WAIT = 60.0                   # how long a request waits for a free calculation slot before it is told the service is busy
# Engineering details of the signed snapshot that the browser never receives.
INTERNAL = ("calculationTrace", "inputs", "inputHash", "snapshotReceipt", "snapshotExpiresAt")
HISTORY = ("quarterly", "annual", "latest")   # the parts of calculationTrace the report's financial history shows
# What readers may see of snapshot["technicalAssessment"] (docs/premium-st-lt-model.md, "Report contract"). Left out on purpose: inputHash,
# sourceCodeSha256, each factor's internal weight; the model says weights and implementation hashes are not shown to report readers.
TECH_TOP = ("modelVersion", "status", "asOf", "provider", "dailyBars", "usableDailyBars", "fresh")
TECH_HORIZON = ("score", "rating", "status", "horizon", "availableCount", "requiredCount", "stageCapped")
TECH_FACTOR = ("key", "label", "signal", "status", "detail")
TECH_SOURCE = ("provider", "asOf", "bars")

INPUT_SECONDS = 24 * 3600          # kept model inputs younger than this are reused
REFRESH_REUSE_SECONDS = 900        # ...but "Recalculate" reuses only inputs younger than this (a repeated click), so it really refetches
OBS_DAYS = 4                       # peer observations of the last four calendar days (IST) are offered to a calculation
OBS_TTL = 5 * 86400
UNIVERSE_TTL = 30 * 86400
JOB_WORKING_SECONDS = LOCK_SECONDS
JOB_DONE_SECONDS = 120
DEFAULT_EXPECTED = 12.0            # seconds a calculation is expected to take until some have been timed
RETRY_AFTER_BACKGROUND = 3.0       # the nightly job waits this long when the site backend says a member is waiting

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


def _plain(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _pick(source: Any, keys: Tuple[str, ...]) -> Dict[str, Any]:
    return {k: source[k] for k in keys if isinstance(source, dict) and k in source}


def _horizon(part: Any) -> Dict[str, Any]:
    """One horizon (shortTerm / longTerm) of the technical assessment; each factor loses its internal model `weight`."""
    out = _pick(part, TECH_HORIZON)
    out["factors"] = [_pick(f, TECH_FACTOR) for f in (part.get("factors") if isinstance(part, dict) else None) or [] if isinstance(f, dict)]
    return out


def technical_view(technical: Any) -> Optional[Dict[str, Any]]:
    """The ST/LT `technicalAssessment` as readers may see it, or None when the snapshot has none (older snapshots) or it is not an object.
    It is an allow-list: `inputHash`, `sourceCodeSha256`, factor weights and anything that is not a plain value (a raw candle or index
    series, were one ever added) are not passed on. Scores, ratings and verdict labels are copied exactly as the model produced them."""
    if not isinstance(technical, dict):
        return None
    out = _pick(technical, TECH_TOP)
    for key in ("shortTerm", "longTerm"):
        if key in technical:
            out[key] = _horizon(technical[key])
    if isinstance(technical.get("verdict"), dict):
        out["verdict"] = _pick(technical["verdict"], ("label", "tone"))
    if isinstance(technical.get("notes"), list):
        out["notes"] = [n for n in technical["notes"] if isinstance(n, str)]
    if isinstance(technical.get("observations"), dict):
        out["observations"] = {k: v for k, v in technical["observations"].items()
                               if _plain(v) or (isinstance(v, list) and len(v) <= 10 and all(isinstance(i, str) for i in v))}
    if isinstance(technical.get("benchmarkSources"), dict):
        out["benchmarkSources"] = {str(k): _pick(v, TECH_SOURCE) for k, v in technical["benchmarkSources"].items() if isinstance(v, dict)}
    if isinstance(technical.get("options"), dict):
        out["options"] = {k: v for k, v in technical["options"].items() if isinstance(v, bool)}
    return out


def reader_view(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """The snapshot without its engineering details, plus `financialHistory`: the three reader-safe tables of the calculation trace
    (quarterly and annual rows, and the key-ratio list), copied as they are. Nothing else of the trace (equations, hashes) is passed on.
    `technicalAssessment` (engine 3.6.10 and later) is passed on through `technical_view`; snapshots without it simply have no such key."""
    trace = snapshot.get("calculationTrace") or {}
    history = {key: trace.get(key) or [] for key in HISTORY}
    view = {**{k: v for k, v in snapshot.items() if k not in INTERNAL and k != "technicalAssessment"}, "financialHistory": history}
    technical = technical_view(snapshot.get("technicalAssessment"))
    if technical is not None:
        view["technicalAssessment"] = technical
    return view


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


def _lines(view: Dict[str, Any], bucket: str, count: int = 2) -> list:
    """The first `count` plain-English pros (or cons) of the review, taken part by part in the review's own order."""
    out = []
    for part in (view.get("review") or {}).get("parts") or []:
        out.extend(str(i["summary"]) for i in part.get(bucket) or [] if isinstance(i, dict) and i.get("summary"))
    return out[:count]


def _summary(row) -> Dict[str, Any]:
    """The compact card for the stock page, next to the basic score: no review body, no metrics. `parts` and `partWeights` are passed
    on exactly as the model gave them, so a part added later (Technical) appears without a change here."""
    view = json.loads(row["report"])
    rating = view.get("rating") or {}
    parts = None if rating.get("status") == "NOT RATED" else rating.get("parts")   # a company the model did not rate shows no category scores
    return {"id": row["id"], "final": rating.get("final"), "label": rating.get("label"), "status": rating.get("status"),
            "confidence": rating.get("confidence"), "parts": parts, "partWeights": rating.get("partWeights"),
            "generatedAt": row["generated_at"].isoformat(), "modelVersion": rating.get("modelVersion"),
            "topPros": _lines(view, "pros"), "topCons": _lines(view, "cons")}


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
async def latest(request: Request, symbol: str = Query("", max_length=40), statement: str = Query("consolidated", max_length=20),
                 view: str = Query("full", pattern="^(full|summary)$")) -> JSONResponse:
    wanted = target(symbol, statement)
    if not wanted:
        return _bad("Choose a company symbol and a statement basis (consolidated or standalone).")
    _, refusal = await _access(request, wanted[0])
    if refusal:
        return refusal
    row = await _stored(request.app.state.store, *wanted)
    if row is None:
        return _reply({"status": "none", "detail": f"No {PRISM_NAME} report has been calculated for this company yet."}, 404)
    return _reply({"summary": _summary(row)} if view == "summary" else _shape(row, cached=True))


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
    if refresh and ctx.role != "admin" and not has(ctx.plan, "gold"):
        # A free account may open a showcase report, but forcing new calculations spends the paid data providers' quota.
        return _reply({"status": "plan_required", "detail": f"Recalculating is part of the Gold plan. {PRISM_NAME} reports are refreshed automatically.", "plan": "gold"}, 403)
    background = body.get("background") is True     # answer at once (202) and calculate behind the page; it polls GET /api/prism/jobs
    row = await _stored(store, symbol, statement)
    if not refresh and _fresh(row):
        return _reply(_shape(row, cached=True))
    lock, token = f"prism:lock:{symbol}:{statement}", secrets.token_hex(8)
    if not await store.redis.set(lock, token, nx=True, ex=LOCK_SECONDS):
        if background:                     # somebody is already calculating it: the page just waits for that one
            return _reply(await _working(app, symbol, statement), 202)
        return await _wait_for(app, symbol, statement, lock, row["id"] if row else None)
    handed_over = False
    try:
        if not refresh:                    # finished by another request between our read and the lock
            row = await _stored(store, symbol, statement)
            if _fresh(row):
                return _reply(_shape(row, cached=True))
        if background:
            counter, renew = await _count(request, ctx)
            if renew:
                return _reply({"status": "limit", "detail": f"You have used today's {DAILY_LIMIT} {PRISM_NAME} calculations. Stored reports stay open."}, 429, renew)
            await _start_job(app, subject(ctx), symbol, statement, counter, refresh, lock, token)
            handed_over = True             # the job releases the lock when it ends
            return _reply(await _working(app, symbol, statement), 202)
        return await _calculate(request, ctx, symbol, statement, refresh)
    finally:
        if not handed_over:
            await _release(store, lock, token)


async def _release(store, lock: str, token: str) -> None:
    try:
        if (await store.redis.get(lock)) == token.encode():
            await store.redis.delete(lock)
    except Exception as exc:           # the lock expires by itself
        log.warning("prism lock %s not released: %s", lock, type(exc).__name__)


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


CANDLE_SECONDS = 60.0               # Dhan candles (see prism_candles.py) must not eat the calculation's time: after this, send none and the site backend falls back


async def _report_body(app, symbol: str, statement: str) -> Dict[str, Any]:
    """The body of POST /api/premium-reports. Dhan's daily candles are added as `suppliedCandles` when they could be fetched complete;
    otherwise the body is exactly what it always was and the site backend uses FinEdge/Upstox."""
    body: Dict[str, Any] = {"query": symbol, "statement_type": statement, "delivery": "inline"}
    try:
        candles = await asyncio.wait_for(supplied_candles(app.state, symbol), CANDLE_SECONDS)
    except Exception as exc:        # never let the extra source stop the calculation
        log.warning("prism candles for %s not sent: %s", symbol, type(exc).__name__)
        candles = None
    if candles:
        body["suppliedCandles"] = candles
    return body


async def _calculate(request: Request, ctx: Ctx, symbol: str, statement: str, refresh: bool = False) -> JSONResponse:
    app = request.app
    counter, renew = await _count(request, ctx)
    if renew:
        return _reply({"status": "limit", "detail": f"You have used today's {DAILY_LIMIT} {PRISM_NAME} calculations. Stored reports stay open."},
                      429, renew)
    status, body, retry = await _execute(app, subject(ctx), symbol, statement, counter, refresh)
    return _reply(body, status, retry)


async def _execute(app, sub: str, symbol: str, statement: str, counter: Optional[str], refresh: bool, *, keep: bool = True,
                   background: bool = False, kept_seconds: Optional[float] = None) -> Tuple[int, Dict[str, Any], Optional[int]]:
    """One calculation through the site backend, stored. (200, the report, None) or (status, an error body, Retry-After); a failure gives the
    member's counted calculation back. `background` is the nightly job: it yields to members and its failures are not remembered."""
    redis = app.state.store.redis
    r: Optional[httpx.Response] = None
    started = time.monotonic()
    try:
        try:   # a request waits its turn (up to SLOT_WAIT seconds) instead of being turned away while another company is calculating
            await asyncio.wait_for(_slots(app).acquire(), SLOT_WAIT)
        except asyncio.TimeoutError:
            if counter:
                await redis.decr(counter)
            return 429, {"status": "busy", "detail": f"{PRISM_NAME} is calculating other companies. Please try again in a minute."}, BUSY_RETRY
        try:
            payload = await _site_payload(app, symbol, statement, background=background, keep=keep,
                                          kept_seconds=(REFRESH_REUSE_SECONDS if refresh else INPUT_SECONDS) if kept_seconds is None else kept_seconds)
            r = await _call(app, "/api/premium-reports", sub, payload)
        finally:
            _slots(app).release()
    except httpx.HTTPError as exc:
        log.warning("prism calculation for %s did not reach the site backend: %s", symbol, type(exc).__name__)
    snapshot = _ready(r)
    if snapshot is None:
        if counter:
            await redis.decr(counter)      # nothing was calculated: it does not use up the member's allowance
        status, body, retry = _failure(r)
        if not background:
            await redis.set(f"prism:fail:{symbol}:{statement}", json.dumps([status, body, retry]), ex=FAIL_SECONDS)
        return status, body, retry
    cache = snapshot.pop("cache", None)    # not part of the signed snapshot: what the site backend asks us to keep
    view = reader_view(snapshot)
    until = await _keep_snapshot(redis, snapshot, sub, symbol)
    row = await _save(app.state.store, symbol, statement, view, until)
    await _remember(app, symbol, statement, cache, time.monotonic() - started)
    return 200, _shape(row, cached=False), None


# ------------------------------------------------------------------ what a calculation leaves behind for the next one
def _asof_days(now: Optional[datetime] = None) -> list:
    today = (now or datetime.now(timezone.utc)).astimezone(IST).date()
    return [(today - timedelta(days=i)).isoformat() for i in range(OBS_DAYS)]


async def _kept_inputs(store, symbol: str, statement: str, seconds: float) -> Optional[str]:
    if seconds <= 0:
        return None
    try:
        return await store.pool.fetchval("SELECT body FROM prism_inputs WHERE symbol = $1 AND statement = $2 AND fetched_at > now() - make_interval(secs => $3)",
                                         symbol, statement, float(seconds))
    except Exception as exc:
        log.warning("prism kept inputs for %s not read: %s", symbol, type(exc).__name__)
        return None


async def _kept_observations(redis, symbol: str, statement: str) -> Dict[str, Any]:
    """The peers' price-ratio rows an earlier calculation of this company looked up, if another company of its industry has since kept them
    for a recent day: {'consolidated|2026-10-26|pr:pb,pe|INFY': row}. The site backend uses only the ones for the as-of date it settles on."""
    try:
        raw = await redis.get(f"prism:univ:{statement}:{symbol}")
        symbols = json.loads(raw) if raw else []
        fields = [f"{kind}|{sym}" for sym in symbols[:500] for kind in ("pr:pb,pe", "pr:pb", "pr:pe", "ev")]
        out: Dict[str, Any] = {}
        for day in (_asof_days() if fields else []):
            for field, value in zip(fields, await redis.hmget(f"prism:obs:{statement}:{day}", fields)):
                if value:
                    out[f"{statement}|{day}|{field}"] = json.loads(value)
        return out
    except Exception as exc:
        log.warning("prism kept observations for %s not read: %s", symbol, type(exc).__name__)
        return {}


async def _site_payload(app, symbol: str, statement: str, *, background: bool, keep: bool, kept_seconds: float) -> Dict[str, Any]:
    body = await _report_body(app, symbol, statement)    # with Dhan's candles (`suppliedCandles`) when they could be fetched complete
    body.update({"priority": "background" if background else "interactive", "keep": keep, "cache": True})
    inputs = await _kept_inputs(app.state.store, symbol, statement, kept_seconds)
    if inputs:
        body["inputs"] = inputs
    observations = await _kept_observations(app.state.store.redis, symbol, statement)
    if observations:
        body["observations"] = observations
    return body


async def _remember(app, symbol: str, statement: str, cache: Any, seconds: float) -> None:
    """Keep the model inputs (24 hours, in Postgres), the new peer observations (4 days, in Redis) and how long a calculation from scratch
    took (the page's progress bar). Best effort: the report is already stored."""
    if not isinstance(cache, dict):
        return
    store = app.state.store
    try:
        packed = cache.get("inputs")
        if isinstance(packed, str) and packed:
            await store.pool.execute(
                """INSERT INTO prism_inputs (symbol, statement, body, fetched_at) VALUES ($1, $2, $3, now())
                   ON CONFLICT (symbol, statement) DO UPDATE SET body = EXCLUDED.body, fetched_at = EXCLUDED.fetched_at""", symbol, statement, packed)
            await store.pool.execute("DELETE FROM prism_inputs WHERE fetched_at < now() - interval '2 days'")
        new = cache.get("observations")
        by_day: Dict[str, Dict[str, str]] = {}
        for key, value in (new.items() if isinstance(new, dict) else []):
            parts = str(key).split("|", 3)
            if len(parts) == 4 and parts[0] == statement:
                by_day.setdefault(parts[1], {})[f"{parts[2]}|{parts[3]}"] = json.dumps(value, allow_nan=False)
        for day, mapping in by_day.items():
            await store.redis.hset(f"prism:obs:{statement}:{day}", mapping=mapping)
            await store.redis.expire(f"prism:obs:{statement}:{day}", OBS_TTL)
        universe = cache.get("universe")
        if isinstance(universe, list) and universe:
            await store.redis.set(f"prism:univ:{statement}:{symbol}", json.dumps([str(u) for u in universe][:500]), ex=UNIVERSE_TTL)
        if cache.get("inputsReused") is False and seconds > 0:    # only calculations a member waited for, from scratch, say how long that takes
            await store.redis.lpush("prism:durations", f"{seconds:.1f}")
            await store.redis.ltrim("prism:durations", 0, 19)
    except Exception as exc:
        log.warning("prism %s: what the calculation learned was not kept (%s)", symbol, type(exc).__name__)


async def _expected_seconds(redis) -> float:
    """How long a calculation from scratch usually takes (the median of the last twenty), for the progress bar."""
    try:
        values = sorted(float(v) for v in await redis.lrange("prism:durations", 0, 19))
        return round(values[len(values) // 2], 1) if values else DEFAULT_EXPECTED
    except Exception:
        return DEFAULT_EXPECTED


# ------------------------------------------------------------------ calculations that run behind the page
def _job_key(statement: str, symbol: str) -> str:
    return f"prism:job:{statement}:{symbol}"


async def _start_job(app, sub: str, symbol: str, statement: str, counter: Optional[str], refresh: bool, lock: str, token: str) -> None:
    redis = app.state.store.redis
    await redis.set(_job_key(statement, symbol), json.dumps({"state": "working", "startedAt": time.time()}), ex=JOB_WORKING_SECONDS)
    tasks = getattr(app.state, "prism_tasks", None)
    if tasks is None:
        tasks = app.state.prism_tasks = set()
    task = asyncio.create_task(_run_job(app, sub, symbol, statement, counter, refresh, lock, token))
    tasks.add(task)                         # a reference, or the task could be collected while it runs
    task.add_done_callback(tasks.discard)


async def _run_job(app, sub: str, symbol: str, statement: str, counter: Optional[str], refresh: bool, lock: str, token: str) -> None:
    store = app.state.store
    try:
        status, body, retry = await _execute(app, sub, symbol, statement, counter, refresh)
        done: Dict[str, Any] = {"state": "ready"} if status == 200 else {"state": "failed", "status": status, "code": body.get("status"), "detail": body.get("detail"), "retry": retry}
    except Exception as exc:                # whatever happens, the page is told: it must never wait for a job that no longer exists
        log.warning("prism job for %s failed: %s", symbol, type(exc).__name__)
        try:
            if counter:
                await store.redis.decr(counter)
        except Exception:
            pass
        done = {"state": "failed", "status": 502, "code": "unavailable", "detail": CALM, "retry": None}
    try:
        await store.redis.set(_job_key(statement, symbol), json.dumps({**done, "finishedAt": time.time()}), ex=JOB_DONE_SECONDS)
    finally:
        await _release(store, lock, token)


async def _working(app, symbol: str, statement: str) -> Dict[str, Any]:
    """The answer while a calculation of this company runs: when it started, how long it usually takes, how often to ask again."""
    redis = app.state.store.redis
    started = None
    try:
        raw = await redis.get(_job_key(statement, symbol))
        job = json.loads(raw) if raw else {}
        started = job.get("startedAt") if job.get("state") == "working" else None
        if started is None:       # a request that is waiting inline holds the lock: the time left on it says how long it has run
            left = await redis.ttl(f"prism:lock:{symbol}:{statement}")
            started = time.time() - (LOCK_SECONDS - left) if isinstance(left, int) and left > 0 else time.time()
    except Exception:
        started = started or time.time()
    return {"status": "working", "startedAt": started, "elapsedSeconds": round(max(0.0, time.time() - started), 1),
            "expectedSeconds": await _expected_seconds(redis), "pollSeconds": 2}


@router.get("/jobs")
async def job(request: Request, symbol: str = Query("", max_length=40), statement: str = Query("consolidated", max_length=20)) -> JSONResponse:
    """Where a calculation that was started with `background: true` is: working (with its elapsed seconds), ready (read /reports/latest),
    failed (with the reason and, for a Retry button, whether trying again can help) or none (nothing running, nothing stored)."""
    wanted = target(symbol, statement)
    if not wanted:
        return _bad("Choose a company symbol and a statement basis (consolidated or standalone).")
    _, refusal = await _access(request, wanted[0])
    if refusal:
        return refusal
    app = request.app
    redis = app.state.store.redis
    try:
        raw = await redis.get(_job_key(wanted[1], wanted[0]))
        state = json.loads(raw) if raw else None
        if state and state.get("state") == "working":
            elapsed = time.time() - float(state.get("startedAt") or 0)
            if elapsed > JOB_WORKING_SECONDS:   # the process that ran it is gone: say so instead of waiting for ever
                return _reply({"state": "failed", "status": 504, "code": "unavailable", "detail": CALM, "retry": None})
            return _reply({"state": "working", **(await _working(app, *wanted))})
        if state:
            return _reply(state)
        locked = await redis.exists(f"prism:lock:{wanted[0]}:{wanted[1]}")
    except Exception as exc:
        log.warning("prism job state for %s not read: %s", wanted[0], type(exc).__name__)
        locked = False
    if locked:
        return _reply({"state": "working", **(await _working(app, *wanted))})
    row = await _stored(app.state.store, *wanted)
    return _reply({"state": "ready"} if row is not None else {"state": "none"})



@router.get("/reports/{report_id}/pdf")
async def pdf(request: Request, report_id: str) -> Response:
    if not REPORT_ID.match(report_id):
        return _reply({"status": "not_found", "detail": "No such report."}, 404)
    app = request.app
    ctx = await current(request)
    allowed, wait = await app.state.limiter.hit("prism-pdf", ctx.user_id or "ip:" + ip_of(request), PDF_LIMIT, 600, fail_open=False)
    if not allowed:
        return _reply({"status": "limit", "detail": "Too many PDF downloads. Please wait a few minutes."}, 429, wait or 60)
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


# ------------------------------------------------------------------ nightly pre-calculation
PRE_FAIL_SECONDS = 20 * 3600       # a company the data cannot rate is not tried again until the next night
PRE_PAUSE_TRIES = 40               # times the nightly job waits for a member's calculation to finish before it gives that company up
PRE_PROGRESS_KEY = "prism:pre:last"


async def _pending(store, statement: str, days: int, limit: int, skip: list) -> list:
    """Companies we hold a full report for (the stored summary) that have no rating or an old one, never-rated first and then the biggest.
    Fresh ones are not listed, so a run that was stopped simply continues where it stopped, and `skip` leaves out what failed tonight."""
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT s.symbol FROM (SELECT DISTINCT symbol FROM snapshots WHERE section = 'summary') s "
            "LEFT JOIN listing_quotes q ON q.symbol = s.symbol LEFT JOIN prism_reports p ON p.symbol = s.symbol AND p.statement = $1 "
            "WHERE (p.symbol IS NULL OR p.generated_at < now() - make_interval(days => $2)) AND NOT (s.symbol = ANY($4::text[])) "
            "ORDER BY (p.symbol IS NULL) DESC, q.market_cap DESC NULLS LAST, s.symbol LIMIT $3", statement, days, limit, skip)
    return [r["symbol"] for r in rows]


async def precompute(store, settings, *, limit: int = 800, max_minutes: float = 100.0, days: int = 7, statement: str = "consolidated", client=None) -> Dict[str, Any]:
    """Calculate the rating of every company we hold a full report for that has none yet (or one older than `days`), one at a time (memory),
    never-rated first and then the biggest. The calculation is exactly the one a member's button runs, from the same inputs. It is resumable
    (what is stored counts as done), it gives way to a member who is waiting (the site backend turns it away while one is, and it waits a
    few seconds), and it stops at the time limit and after three failures in a row (a provider that is down or limiting requests should not
    be hammered). A company the data cannot rate is remembered for the night, so it does not block the ones behind it."""
    from types import SimpleNamespace
    app = SimpleNamespace(state=SimpleNamespace(store=store, settings=settings, prism_client=client))
    if not connected(settings):
        return {"status": "skipped", "reason": "not_configured"}
    redis = store.redis
    skip: list = []
    try:
        async for key in redis.scan_iter(match=f"prism:pre:fail:{statement}:*", count=200):
            skip.append((key.decode() if isinstance(key, bytes) else key).rsplit(":", 1)[1])
    except Exception:
        skip = []
    symbols = await _pending(store, statement, days, limit, skip)
    started, done, failed, streak, paused = time.monotonic(), 0, [], 0, 0
    attempted = 0
    try:
        for symbol in symbols:
            if time.monotonic() - started > max_minutes * 60 or streak >= 3:
                break
            attempted += 1
            code, r, snapshot = 0, None, None
            for _ in range(PRE_PAUSE_TRIES):
                try:
                    payload = await _site_payload(app, symbol, statement, background=True, keep=False, kept_seconds=0)
                    r = await _call(app, "/api/premium-reports", "prism:nightly", payload)
                except httpx.HTTPError as exc:
                    r = None
                    log.warning("prism nightly %s did not reach the site backend: %s", symbol, type(exc).__name__)
                code = r.status_code if r is not None else 0
                if code == 429 and r is not None and "member is waiting" in (_upstream_detail(r) or ""):
                    paused += 1                    # a member is waiting: let them go first
                    await asyncio.sleep(RETRY_AFTER_BACKGROUND)
                    continue
                break
            snapshot = _ready(r)
            if snapshot is None:
                failed.append(f"{symbol}:{code}")
                streak = streak + 1 if code in (0, 429, 502, 503) else 0   # a company the data cannot rate (404/422) is not a provider outage
                if streak == 0:
                    await redis.set(f"prism:pre:fail:{statement}:{symbol}", str(code), ex=PRE_FAIL_SECONDS)
                continue
            streak = 0
            cache = snapshot.pop("cache", None)
            await _save(store, symbol, statement, reader_view(snapshot), None)
            await _remember(app, symbol, statement, {k: v for k, v in (cache or {}).items() if k != "inputs"}, 0.0)   # 0: not timed, the nightly run has the peers kept
            done += 1
            await asyncio.sleep(0.2)
    finally:
        if client is None and getattr(app.state, "prism_client", None) is not None:
            await app.state.prism_client.aclose()
        if getattr(app.state, "prism_dhan", None) is not None:
            await app.state.prism_dhan.aclose()
    left = len(await _pending(store, statement, days, 5000, [])) if symbols else 0
    out = {"status": "ok" if done or not symbols else "partial", "calculated": done, "failed": failed[:10], "paused_for_members": paused,
           "remaining_candidates": left, "seconds": round(time.monotonic() - started)}
    try:
        await redis.set(PRE_PROGRESS_KEY, json.dumps({**out, "at": time.time()}), ex=7 * 86400)
    except Exception:
        pass
    return out
