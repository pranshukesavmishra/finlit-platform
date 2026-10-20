"""Account endpoints: sign up, sign in, sessions, security settings, saved state and admin tools.

Every protected route re-checks identity and plan on the server. State-changing requests that rely on the session cookie
must also carry the session's CSRF token and come from an allowed origin.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import Settings
from ..security import client_ip
from . import crypto, mailer as mail
from .entitlements import LIMITS, PLANS, has
from .service import ANON, Ctx, audit, cookie_name, create_session, current, forget_cached, revoke_all

SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
IST = ZoneInfo("Asia/Kolkata")
router = APIRouter(prefix="/api")
NO_STORE = {"Cache-Control": "no-store"}
SCREEN_KEYS = {"market_cap", "price", "change_pct", "return_1m", "return_1y", "pe", "pb", "dividend_yield", "roe", "roce", "operating_margin",
               "sales_cagr", "profit_cagr", "debt_to_equity", "overall", "pillar_quality", "pillar_growth", "pillar_profitability",
               "pillar_balance", "pillar_technical"}
PALETTES = ("gold", "champagne", "bronze", "graphite", "midnight", "emerald")


def fail(status: int, code: str, detail: str = "", **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"status": code, "detail": detail, **extra})


def ip_of(request: Request) -> str:
    st: Settings = request.app.state.settings
    return request.scope.get("state", {}).get("client_ip") or client_ip(request.scope, st.client_ip_header)


def origin_allowed(request: Request) -> bool:
    st: Settings = request.app.state.settings
    origin = request.headers.get("origin")
    if origin is None:
        return False
    host = request.headers.get("host", "")
    return origin in set(st.cors_origins) | {st.public_site_url} or origin in (f"https://{host}", f"http://{host}")


def pre_session_guard(request: Request) -> None:
    """Sign-up, sign-in and reset requests: a browser always sends Origin, so a wrong one is a cross-site attempt."""
    origin = request.headers.get("origin")
    if origin is not None and not origin_allowed(request):
        raise fail(403, "bad_origin", "This request did not come from the FinLit website.")


async def limit(request: Request, name: str, key: str, count: int, seconds: int) -> None:
    allowed, retry = await request.app.state.limiter.hit(name, key, count, seconds, fail_open=False)
    if not allowed:
        raise HTTPException(status_code=429, detail={"status": "rate_limited", "detail": "Too many attempts. Please wait and try again.",
                                                      "retryAfter": retry}, headers={"Retry-After": str(retry)})


async def user_ctx(request: Request) -> Ctx:
    ctx = await current(request)
    if not ctx.authed:
        raise fail(401, "auth_required", "Please sign in.")
    return ctx


async def secure_ctx(request: Request) -> Ctx:
    """Signed-in and, for anything that changes data, proven to come from our own pages (Origin + CSRF token)."""
    ctx = await user_ctx(request)
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if not origin_allowed(request):
            raise fail(403, "bad_origin", "This request did not come from the FinLit website.")
        sent = request.headers.get("x-csrf-token", "")
        if not sent or not hmac.compare_digest(sent, ctx.csrf):
            raise fail(403, "bad_csrf", "Your session needs to be refreshed. Reload the page and try again.")
    return ctx


async def admin_ctx(request: Request, ctx: Ctx = Depends(secure_ctx)) -> Ctx:
    if ctx.role != "admin":
        raise fail(403, "forbidden", "Administrators only.")
    if not ctx.mfa_ok:
        raise fail(403, "mfa_required", "Sign in with your authenticator code to use admin tools.")
    return ctx


def need_plan(ctx: Ctx, tier: str) -> None:
    if not has(ctx.plan, tier):
        raise fail(403, "plan_required", f"This is part of the {tier.title()} plan.", plan=tier)


# ------------------------------------------------------------------ models
class SignUp(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)
    name: Optional[str] = Field(default=None, max_length=80)
    accept_terms: bool = False


class SignIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=200)
    code: Optional[str] = Field(default=None, max_length=12)


class EmailOnly(BaseModel):
    email: str = Field(max_length=254)


class TokenOnly(BaseModel):
    token: str = Field(min_length=20, max_length=100)


class ResetIn(TokenOnly):
    password: str = Field(min_length=1, max_length=200)


class ChangePw(BaseModel):
    current: str = Field(max_length=200)
    new: str = Field(max_length=200)


class ProfileIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)


class CodeIn(BaseModel):
    code: str = Field(max_length=12)


class PasswordIn(BaseModel):
    password: str = Field(max_length=200)


class PlanRequestIn(BaseModel):
    plan: Literal["silver", "gold"]
    note: Optional[str] = Field(default=None, max_length=300)


class WMeta(BaseModel):
    note: Optional[str] = Field(default=None, max_length=200)
    target: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    added: int = Field(default=0, ge=0)


class WList(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]{1,16}$")
    name: str = Field(min_length=1, max_length=28)
    symbols: List[str] = Field(max_length=1000)

    @field_validator("symbols")
    @classmethod
    def symbols_ok(cls, v: List[str]) -> List[str]:
        out = []
        for s in v:
            s = s.strip().upper()
            if not SYMBOL.match(s):
                raise ValueError("bad symbol")
            if s not in out:
                out.append(s)
        return out


class Holding(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9]{1,16}$")
    symbol: str
    qty: float = Field(gt=0, le=1_000_000_000)
    price: float = Field(ge=0, le=100_000_000)  # average buy price per share
    date: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    note: Optional[str] = Field(default=None, max_length=200)

    @field_validator("symbol")
    @classmethod
    def symbol_ok(cls, v: str) -> str:
        v = v.strip().upper()
        if not SYMBOL.match(v):
            raise ValueError("bad symbol")
        return v


class PortfolioIn(BaseModel):
    holdings: List[Holding] = Field(max_length=500)


class WatchlistIn(BaseModel):
    lists: List[WList] = Field(max_length=50)
    meta: Dict[str, WMeta] = Field(default_factory=dict, max_length=1000)


class Range(BaseModel):
    min: Optional[float] = Field(default=None, ge=-1e12, le=1e12)
    max: Optional[float] = Field(default=None, ge=-1e12, le=1e12)


class ScreenState(BaseModel):
    ranges: Dict[str, Range] = Field(default_factory=dict, max_length=60)
    sectors: List[str] = Field(default_factory=list, max_length=40)
    bands: List[Literal["strong", "healthy", "mixed", "watch"]] = Field(default_factory=list, max_length=4)
    industries: List[str] = Field(default_factory=list, max_length=60)
    indices: List[str] = Field(default_factory=list, max_length=20)
    caps: List[Literal["Large", "Mid", "Small"]] = Field(default_factory=list, max_length=3)
    sort: Optional[str] = Field(default=None, max_length=40)
    dir: Optional[Literal["asc", "desc"]] = None
    cols: List[str] = Field(default_factory=list, max_length=14)

    @field_validator("ranges")
    @classmethod
    def keys_ok(cls, v: Dict[str, Range]) -> Dict[str, Range]:
        from ..screener.catalog import BY_KEY
        if any(k not in SCREEN_KEYS and k not in BY_KEY for k in v):
            raise ValueError("unknown filter")
        return v

    @field_validator("sectors")
    @classmethod
    def sectors_ok(cls, v: List[str]) -> List[str]:
        if any(len(s) > 60 for s in v):
            raise ValueError("sector too long")
        return v


class Screen(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    state: ScreenState


class ScreensIn(BaseModel):
    screens: List[Screen] = Field(max_length=100)


class Widget(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_]{1,24}$")
    on: bool = True
    size: Literal["half", "full"] = "half"


class PrefsIn(BaseModel):
    theme: Optional[Literal["light", "dark"]] = None
    palette: Literal["gold", "champagne", "bronze", "graphite", "midnight", "emerald"] = "gold"
    density: Literal["comfortable", "compact"] = "comfortable"
    alerts: bool = True
    screenAlerts: bool = True
    profitGap: bool = True
    digest: bool = False
    dashboard: List[Widget] = Field(default_factory=list, max_length=30)


# ------------------------------------------------------------------ helpers
def public_user(row: Any) -> Dict[str, Any]:
    return {"id": str(row["id"]), "email": row["email"], "name": row["name"], "role": row["role"], "plan": row["plan"],
            "verified": row["email_verified_at"] is not None, "mfa": row["totp_enabled_at"] is not None}


def email_hash(email: str) -> str:
    return crypto.token_hash("email:" + email)[:32]


async def issue_token(pool, user_id: str, kind: str, ttl: timedelta) -> str:
    raw, th = crypto.new_token()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE email_tokens SET used_at = now() WHERE user_id = $1 AND kind = $2 AND used_at IS NULL", user_id, kind)
        await conn.execute("INSERT INTO email_tokens (user_id, kind, token_hash, expires_at) VALUES ($1, $2, $3, $4)",
                           user_id, kind, th, datetime.now(timezone.utc) + ttl)
    return raw


async def consume_token(pool, raw: str, kind: str) -> Optional[str]:
    """Mark a token used and return its user id, or None when unknown, used or expired."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE email_tokens SET used_at = now() WHERE token_hash = $1 AND kind = $2 AND used_at IS NULL AND expires_at > now() RETURNING user_id",
            crypto.token_hash(raw), kind)
    return str(row["user_id"]) if row else None


def set_session_cookie(request: Request, response: Response, raw: str, role: str) -> None:
    from .service import session_limits
    st: Settings = request.app.state.settings
    absolute, _ = session_limits(st, role)
    response.set_cookie(cookie_name(st), raw, max_age=int(absolute.total_seconds()), httponly=True, secure=st.cookie_secure,
                        samesite=st.cookie_samesite, path="/")


def clear_session_cookie(request: Request, response: Response) -> None:
    st: Settings = request.app.state.settings
    response.delete_cookie(cookie_name(st), path="/", secure=st.cookie_secure, httponly=True, samesite=st.cookie_samesite)


GENERIC_SIGNUP = {"status": "check_email", "detail": "If that address can be used, we have sent a message to confirm it."}


# ------------------------------------------------------------------ sign up / verify / sign in
@router.post("/auth/register", status_code=202)
async def register(request: Request, body: SignUp):
    pre_session_guard(request)
    st: Settings = request.app.state.settings
    pool = request.app.state.store.pool
    ip = ip_of(request)
    await limit(request, "reg", ip, 8, 3600)
    email = crypto.normalise_email(body.email)
    if not email:
        raise fail(422, "invalid_email", "Enter a valid email address.")
    if not body.accept_terms:
        raise fail(422, "terms_required", "Please accept the Terms and Privacy notice to create an account.")
    problem = crypto.password_problem(body.password, email)
    if problem:
        raise fail(422, "weak_password", problem)
    await limit(request, "regmail", email_hash(email), 3, 3600)
    name = (body.name or "").strip()[:80] or None
    async with pool.acquire() as conn:
        exists = await conn.fetchrow("SELECT id, name FROM users WHERE lower(email) = $1", email)
    if exists:
        subject, text = mail.already_mail(f"{st.public_site_url}/login")
        await request.app.state.mailer.send(email, subject, text)
        return Response(content=json.dumps(GENERIC_SIGNUP), status_code=202, media_type="application/json", headers=NO_STORE)
    pw = await crypto.hash_password(body.password)
    async with pool.acquire() as conn:
        try:
            uid = await conn.fetchval("INSERT INTO users (email, name, password_hash, email_verified_at) VALUES ($1, $2, $3, CASE WHEN $4 THEN now() END) RETURNING id",
                                      email, name, pw, st.auto_verify_email)
        except Exception:  # a parallel sign-up won the unique index: behave like the existing-account branch
            return Response(content=json.dumps(GENERIC_SIGNUP), status_code=202, media_type="application/json", headers=NO_STORE)
    await audit(pool, str(uid), "register", email_hash(email), ip, terms=True)
    if st.auto_verify_email:  # staging only (refused in production): the account is already confirmed
        return Response(content=json.dumps({"status": "created", "detail": "Your account is ready. Sign in to continue."}), status_code=201,
                        media_type="application/json", headers=NO_STORE)
    raw = await issue_token(pool, str(uid), "verify", timedelta(hours=24))
    subject, text = mail.verify_mail(f"{st.public_site_url}/verify-email?token={raw}", name)
    await request.app.state.mailer.send(email, subject, text)
    return Response(content=json.dumps(GENERIC_SIGNUP), status_code=202, media_type="application/json", headers=NO_STORE)


@router.post("/auth/verify-email")
async def verify_email(request: Request, body: TokenOnly):
    pre_session_guard(request)
    await limit(request, "verify", ip_of(request), 30, 3600)
    pool = request.app.state.store.pool
    uid = await consume_token(pool, body.token, "verify")
    if not uid:
        raise fail(400, "invalid_token", "This link has expired or was already used. Request a new one from the sign-in page.")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, now()) WHERE id = $1", uid)
    await forget_cached(request.app, uid)
    await audit(pool, uid, "verify_email", None, ip_of(request))
    return Response(content=json.dumps({"status": "verified"}), media_type="application/json", headers=NO_STORE)


@router.post("/auth/resend-verification", status_code=202)
async def resend_verification(request: Request, body: EmailOnly):
    pre_session_guard(request)
    st: Settings = request.app.state.settings
    pool = request.app.state.store.pool
    await limit(request, "resend", ip_of(request), 8, 3600)
    email = crypto.normalise_email(body.email)
    if email:
        await limit(request, "resendmail", email_hash(email), 3, 3600)
        async with pool.acquire() as conn:
            u = await conn.fetchrow("SELECT id, name FROM users WHERE lower(email) = $1 AND email_verified_at IS NULL AND status = 'active'", email)
        if u:
            raw = await issue_token(pool, str(u["id"]), "verify", timedelta(hours=24))
            subject, text = mail.verify_mail(f"{st.public_site_url}/verify-email?token={raw}", u["name"])
            await request.app.state.mailer.send(email, subject, text)
    return Response(content=json.dumps(GENERIC_SIGNUP), status_code=202, media_type="application/json", headers=NO_STORE)


@router.post("/auth/login")
async def login(request: Request, response: Response, body: SignIn):
    pre_session_guard(request)
    pool = request.app.state.store.pool
    ip = ip_of(request)
    await limit(request, "login", ip, 20, 600)
    email = crypto.normalise_email(body.email)
    invalid = fail(401, "invalid_credentials", "Email or password is not correct.")
    if not email:
        await crypto.verify_password(crypto.DUMMY_HASH, body.password)
        raise invalid
    await limit(request, "loginmail", email_hash(email), 12, 900)
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT * FROM users WHERE lower(email) = $1", email)
    if u is None:
        await crypto.verify_password(crypto.DUMMY_HASH, body.password)
        raise invalid
    now = datetime.now(timezone.utc)
    if u["locked_until"] and u["locked_until"] > now:
        retry = int((u["locked_until"] - now).total_seconds())
        raise HTTPException(status_code=429, detail={"status": "locked", "detail": "Too many wrong attempts. Try again in a few minutes, or reset your password.",
                                                      "retryAfter": retry}, headers={"Retry-After": str(retry)})
    ok = await crypto.verify_password(u["password_hash"], body.password)

    async def count_failure() -> None:
        async with pool.acquire() as conn:
            n = await conn.fetchval("UPDATE users SET failed_logins = failed_logins + 1 WHERE id = $1 RETURNING failed_logins", u["id"])
            if n >= 8:
                await conn.execute("UPDATE users SET failed_logins = 0, locked_until = now() + interval '15 minutes' WHERE id = $1", u["id"])
        await audit(pool, str(u["id"]), "login_failed", None, ip)

    if not ok or u["status"] != "active":
        if ok is False:
            await count_failure()
        raise invalid
    if u["email_verified_at"] is None:
        raise fail(403, "email_not_verified", "Confirm your email first. We sent you a link when you signed up.")
    mfa_ok = False
    if u["totp_enabled_at"]:
        if not body.code:
            raise HTTPException(status_code=401, detail={"status": "mfa_required", "detail": "Enter the 6-digit code from your authenticator app."})
        secret = crypto.decrypt_secret(request.app.state.settings.secret_key, u["totp_secret_enc"] or "")
        step = crypto.verify_totp(secret, body.code, u["totp_last_step"]) if secret else None
        if step is None:
            await count_failure()
            raise fail(401, "invalid_code", "That code is not correct or was already used.")
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET totp_last_step = $2 WHERE id = $1", u["id"], step)
        mfa_ok = True
    elif u["role"] == "admin" and not request.app.state.settings.admin_require_mfa:
        mfa_ok = True   # the owner chose to run without the authenticator for now (ADMIN_REQUIRE_MFA=0)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET failed_logins = 0, locked_until = NULL, last_login_at = now() WHERE id = $1", u["id"])
    if crypto.needs_rehash(u["password_hash"]):
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET password_hash = $2 WHERE id = $1", u["id"], await crypto.hash_password(body.password))
    raw, csrf = await create_session(request.app, u, ip, request.headers.get("user-agent", ""), mfa_ok)
    set_session_cookie(request, response, raw, u["role"])
    response.headers.update(NO_STORE)
    await audit(pool, str(u["id"]), "login", None, ip, mfa=mfa_ok)
    plan = u["plan"] if not (u["plan_until"] and u["plan_until"] < now) else "basic"
    user = {**public_user(u), "plan": plan, "mfaOk": mfa_ok}
    return {"user": user, "csrf": csrf, "mfaSetupRequired": u["role"] == "admin" and not u["totp_enabled_at"] and request.app.state.settings.admin_require_mfa}


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    st: Settings = request.app.state.settings
    ctx = await current(request)
    if ctx.authed:
        if not origin_allowed(request):
            raise fail(403, "bad_origin")
        token = request.cookies.get(cookie_name(st), "")
        async with request.app.state.store.pool.acquire() as conn:
            await conn.execute("DELETE FROM sessions WHERE token_hash = $1", crypto.token_hash(token))
        await forget_cached(request.app, ctx.user_id, crypto.token_hash(token))
        await audit(request.app.state.store.pool, ctx.user_id, "logout", None, ip_of(request))
    clear_session_cookie(request, response)
    response.headers.update(NO_STORE)
    return {"status": "signed_out"}


@router.post("/auth/forgot", status_code=202)
async def forgot(request: Request, body: EmailOnly):
    pre_session_guard(request)
    st: Settings = request.app.state.settings
    pool = request.app.state.store.pool
    await limit(request, "forgot", ip_of(request), 8, 3600)
    email = crypto.normalise_email(body.email)
    if email:
        await limit(request, "forgotmail", email_hash(email), 3, 3600)
        async with pool.acquire() as conn:
            u = await conn.fetchrow("SELECT id FROM users WHERE lower(email) = $1 AND status = 'active'", email)
        if u:
            raw = await issue_token(pool, str(u["id"]), "reset", timedelta(hours=1))
            subject, text = mail.reset_mail(f"{st.public_site_url}/reset-password?token={raw}")
            await request.app.state.mailer.send(email, subject, text)
            await audit(pool, str(u["id"]), "password_reset_requested", None, ip_of(request))
    return Response(content=json.dumps({"status": "check_email", "detail": "If an account exists for that address, we have sent a reset link."}),
                    status_code=202, media_type="application/json", headers=NO_STORE)


@router.post("/auth/reset")
async def reset(request: Request, body: ResetIn):
    pre_session_guard(request)
    pool = request.app.state.store.pool
    await limit(request, "reset", ip_of(request), 15, 3600)
    async with pool.acquire() as conn:
        peek = await conn.fetchrow("SELECT u.email FROM email_tokens t JOIN users u ON u.id = t.user_id WHERE t.token_hash = $1 AND t.kind = 'reset' "
                                   "AND t.used_at IS NULL AND t.expires_at > now()", crypto.token_hash(body.token))
    if not peek:
        raise fail(400, "invalid_token", "This link has expired or was already used. Request a new one.")
    problem = crypto.password_problem(body.password, peek["email"])
    if problem:
        raise fail(422, "weak_password", problem)
    uid = await consume_token(pool, body.token, "reset")
    if not uid:
        raise fail(400, "invalid_token", "This link has expired or was already used. Request a new one.")
    pw = await crypto.hash_password(body.password)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash = $2, password_changed_at = now(), failed_logins = 0, locked_until = NULL, "
                           "email_verified_at = COALESCE(email_verified_at, now()) WHERE id = $1", uid, pw)
    await revoke_all(request.app, uid)
    await audit(pool, uid, "password_reset", None, ip_of(request))
    return Response(content=json.dumps({"status": "password_changed"}), media_type="application/json", headers=NO_STORE)


# ------------------------------------------------------------------ who am I
def limits_for(plan: str) -> Dict[str, int]:
    return LIMITS.get(plan, LIMITS["basic"])


@router.get("/auth/me")
async def me(request: Request):
    ctx = await current(request)
    body = {"user": ctx.public() if ctx.authed else None, "plan": ctx.plan, "limits": limits_for(ctx.plan), "csrf": ctx.csrf if ctx.authed else None,
            "showcase": sorted(request.app.state.settings.showcase_symbols)}  # the free example companies: their reports are sent in full to everyone
    return Response(content=json.dumps(body), media_type="application/json", headers={**NO_STORE, "Vary": "Cookie"})


@router.patch("/me")
async def update_profile(request: Request, body: ProfileIn, ctx: Ctx = Depends(secure_ctx)):
    name = (body.name or "").strip()[:80] or None
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET name = $2 WHERE id = $1", ctx.user_id, name)
    await forget_cached(request.app, ctx.user_id)
    return {"status": "saved", "name": name}


@router.post("/me/password")
async def change_password(request: Request, body: ChangePw, ctx: Ctx = Depends(secure_ctx)):
    pool = request.app.state.store.pool
    await limit(request, "chpw", ctx.user_id, 8, 900)
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT password_hash, email FROM users WHERE id = $1", ctx.user_id)
    if not await crypto.verify_password(u["password_hash"], body.current):
        raise fail(403, "wrong_password", "Your current password is not correct.")
    problem = crypto.password_problem(body.new, u["email"])
    if problem:
        raise fail(422, "weak_password", problem)
    pw = await crypto.hash_password(body.new)
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET password_hash = $2, password_changed_at = now() WHERE id = $1", ctx.user_id, pw)
    await revoke_all(request.app, ctx.user_id, keep_session=ctx.session_id)
    await audit(pool, ctx.user_id, "password_changed", None, ip_of(request))
    return {"status": "password_changed"}


@router.get("/me/sessions")
async def list_sessions(request: Request, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, created_at, last_seen_at, ip, user_agent FROM sessions WHERE user_id = $1 AND expires_at > now() ORDER BY last_seen_at DESC", ctx.user_id)
    return {"sessions": [{"id": str(r["id"]), "createdAt": r["created_at"].isoformat(), "lastSeenAt": r["last_seen_at"].isoformat(),
                          "ip": r["ip"], "agent": (r["user_agent"] or "")[:120], "current": str(r["id"]) == ctx.session_id} for r in rows]}


@router.delete("/me/sessions/{sid}")
async def end_session(request: Request, sid: str, ctx: Ctx = Depends(secure_ctx)):
    if not re.fullmatch(r"[0-9a-f-]{36}", sid):
        raise fail(400, "invalid_id")
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = $1 AND user_id = $2", sid, ctx.user_id)
    await forget_cached(request.app, ctx.user_id)
    return {"status": "ended"}


@router.post("/me/sessions/end-others")
async def end_others(request: Request, ctx: Ctx = Depends(secure_ctx)):
    await revoke_all(request.app, ctx.user_id, keep_session=ctx.session_id)
    return {"status": "ended"}


# ------------------------------------------------------------------ authenticator app
@router.post("/me/mfa/setup")
async def mfa_setup(request: Request, ctx: Ctx = Depends(secure_ctx)):
    if ctx.totp:
        raise fail(409, "mfa_enabled", "Two-step sign-in is already on.")
    secret = crypto.new_totp_secret()
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET totp_secret_enc = $2, totp_last_step = 0 WHERE id = $1", ctx.user_id,
                           crypto.encrypt_secret(request.app.state.settings.secret_key, secret))
    return {"secret": secret, "uri": crypto.totp_uri(secret, ctx.email or "")}


@router.post("/me/mfa/enable")
async def mfa_enable(request: Request, body: CodeIn, ctx: Ctx = Depends(secure_ctx)):
    pool = request.app.state.store.pool
    await limit(request, "mfa", ctx.user_id, 10, 900)
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT totp_secret_enc, totp_enabled_at, totp_last_step FROM users WHERE id = $1", ctx.user_id)
    if u["totp_enabled_at"] or not u["totp_secret_enc"]:
        raise fail(409, "mfa_state", "Start set-up again.")
    secret = crypto.decrypt_secret(request.app.state.settings.secret_key, u["totp_secret_enc"])
    step = crypto.verify_totp(secret, body.code, u["totp_last_step"]) if secret else None
    if step is None:
        raise fail(400, "invalid_code", "That code is not correct. Check the time on your phone and try again.")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET totp_enabled_at = now(), totp_last_step = $2 WHERE id = $1", ctx.user_id, step)
        await conn.execute("UPDATE sessions SET mfa_ok = true WHERE id = $1", ctx.session_id)
    await forget_cached(request.app, ctx.user_id)
    await audit(pool, ctx.user_id, "mfa_enabled", None, ip_of(request))
    return {"status": "enabled"}


@router.post("/me/mfa/disable")
async def mfa_disable(request: Request, body: CodeIn, ctx: Ctx = Depends(secure_ctx)):
    pool = request.app.state.store.pool
    if ctx.role == "admin":
        raise fail(403, "forbidden", "Administrators must keep two-step sign-in on.")
    await limit(request, "mfa", ctx.user_id, 10, 900)
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT totp_secret_enc, totp_last_step FROM users WHERE id = $1", ctx.user_id)
    secret = crypto.decrypt_secret(request.app.state.settings.secret_key, u["totp_secret_enc"] or "") if u["totp_secret_enc"] else None
    if not secret or crypto.verify_totp(secret, body.code, u["totp_last_step"]) is None:
        raise fail(400, "invalid_code", "That code is not correct.")
    async with pool.acquire() as conn:
        await conn.execute("UPDATE users SET totp_secret_enc = NULL, totp_enabled_at = NULL WHERE id = $1", ctx.user_id)
    await forget_cached(request.app, ctx.user_id)
    await audit(pool, ctx.user_id, "mfa_disabled", None, ip_of(request))
    return {"status": "disabled"}


@router.delete("/me")
async def delete_account(request: Request, response: Response, body: PasswordIn, ctx: Ctx = Depends(secure_ctx)):
    """Erasure on request: the account, sessions and saved state are deleted. Audit rows keep only an opaque id."""
    pool = request.app.state.store.pool
    await limit(request, "delacct", ctx.user_id, 5, 900)
    async with pool.acquire() as conn:
        u = await conn.fetchrow("SELECT password_hash, role FROM users WHERE id = $1", ctx.user_id)
    if u["role"] == "admin":
        raise fail(403, "forbidden", "Administrator accounts are removed by another administrator.")
    if not await crypto.verify_password(u["password_hash"], body.password):
        raise fail(403, "wrong_password", "Your password is not correct.")
    await forget_cached(request.app, ctx.user_id)
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE id = $1", ctx.user_id)
    await audit(pool, None, "account_deleted", crypto.token_hash(ctx.user_id)[:16], ip_of(request))
    clear_session_cookie(request, response)
    return {"status": "deleted"}


# ------------------------------------------------------------------ saved state
@router.get("/me/state")
async def get_state(request: Request, ctx: Ctx = Depends(secure_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT watchlist, screens, prefs, portfolio FROM user_state WHERE user_id = $1", ctx.user_id)
    parse = lambda v, d: (json.loads(v) if isinstance(v, str) else v) if v else d  # noqa: E731
    return Response(content=json.dumps({"watchlist": parse(row["watchlist"], {}) if row else {}, "screens": parse(row["screens"], []) if row else [],
                                        "prefs": parse(row["prefs"], {}) if row else {}, "portfolio": parse(row["portfolio"], {}) if row else {}}), media_type="application/json", headers=NO_STORE)


async def save_state(request: Request, ctx: Ctx, column: str, value: Any) -> None:
    sql = {"watchlist": "watchlist", "screens": "screens", "prefs": "prefs", "portfolio": "portfolio"}[column]  # fixed names, never user input
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute(f"INSERT INTO user_state (user_id, {sql}) VALUES ($1, $2::jsonb) "  # nosec B608 - column is from the fixed map above
                           f"ON CONFLICT (user_id) DO UPDATE SET {sql} = EXCLUDED.{sql}, updated_at = now()", ctx.user_id, json.dumps(value))


@router.put("/me/watchlist")
async def put_watchlist(request: Request, body: WatchlistIn, ctx: Ctx = Depends(secure_ctx)):
    need_plan(ctx, "silver")
    lim = limits_for(ctx.plan)
    if len(body.lists) > lim["watchlist_lists"]:
        raise fail(403, "plan_limit", f"Your plan includes {lim['watchlist_lists']} lists.", plan="gold")
    total = {s for lst in body.lists for s in lst.symbols}
    if len(total) > lim["watchlist_symbols"]:
        raise fail(403, "plan_limit", f"Your plan includes {lim['watchlist_symbols']} stocks.", plan="gold")
    ids = [lst.id for lst in body.lists]
    if len(set(ids)) != len(ids):
        raise fail(422, "duplicate_list")
    meta = {k: v.model_dump() for k, v in body.meta.items() if SYMBOL.match(k)}
    await save_state(request, ctx, "watchlist", {"lists": [lst.model_dump() for lst in body.lists], "meta": meta})
    return {"status": "saved"}


@router.put("/me/portfolio")
async def put_portfolio(request: Request, body: PortfolioIn, ctx: Ctx = Depends(secure_ctx)):
    need_plan(ctx, "silver")
    cap = limits_for(ctx.plan)["holdings"]
    if len(body.holdings) > cap:
        raise fail(403, "plan_limit", f"Your plan includes {cap} holdings.", plan="gold")
    ids = [h.id for h in body.holdings]
    if len(set(ids)) != len(ids):
        raise fail(422, "duplicate_holding")
    await save_state(request, ctx, "portfolio", {"holdings": [h.model_dump() for h in body.holdings]})
    return {"status": "saved"}


@router.put("/me/screens")
async def put_screens(request: Request, body: ScreensIn, ctx: Ctx = Depends(secure_ctx)):
    if len(body.screens) > limits_for(ctx.plan)["screens"]:
        raise fail(403, "plan_limit", "Your plan has reached its saved-screen limit.", plan="silver")
    await save_state(request, ctx, "screens", [s.model_dump() for s in body.screens])
    return {"status": "saved"}


@router.put("/me/prefs")
async def put_prefs(request: Request, body: PrefsIn, ctx: Ctx = Depends(secure_ctx)):
    await save_state(request, ctx, "prefs", body.model_dump(exclude_none=True))
    return {"status": "saved"}


@router.post("/me/plan-request", status_code=201)
async def plan_request(request: Request, body: PlanRequestIn, ctx: Ctx = Depends(secure_ctx)):
    pool = request.app.state.store.pool
    if has(ctx.plan, body.plan):
        raise fail(409, "already_included", "Your plan already includes this.")
    await limit(request, "planreq", ctx.user_id, 5, 86400)
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM plan_requests WHERE user_id = $1 AND plan = $2 AND status = 'open'", ctx.user_id, body.plan)
        if not exists:
            await conn.execute("INSERT INTO plan_requests (user_id, plan, note) VALUES ($1, $2, $3)", ctx.user_id, body.plan, (body.note or "").strip() or None)
    await audit(pool, ctx.user_id, "plan_requested", body.plan, ip_of(request))
    return {"status": "requested"}


# ------------------------------------------------------------------ administrators
class AdminUserPatch(BaseModel):
    plan: Optional[Literal["basic", "silver", "gold"]] = None
    plan_days: Optional[int] = Field(default=None, ge=1, le=3650)
    role: Optional[Literal["investor", "admin"]] = None
    status: Optional[Literal["active", "disabled"]] = None
    verify_email: Optional[bool] = None  # true = the administrator confirms this member's email by hand (no mail service needed)


@router.get("/admin/users")
async def admin_users(request: Request, q: str = Query("", max_length=80), page: int = Query(1, ge=1, le=10000), ctx: Ctx = Depends(admin_ctx)):
    like = f"%{q.strip().lower()}%"
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, email, name, role, plan, plan_until, status, email_verified_at, totp_enabled_at, created_at, last_login_at, "
                                "count(*) OVER () AS total FROM users WHERE $1 = '%%' OR lower(email) LIKE $1 OR lower(coalesce(name, '')) LIKE $1 "
                                "ORDER BY created_at DESC LIMIT 25 OFFSET $2", like if q.strip() else "%%", (page - 1) * 25)
    return {"total": rows[0]["total"] if rows else 0, "page": page, "users": [{
        "id": str(r["id"]), "email": r["email"], "name": r["name"], "role": r["role"], "plan": r["plan"],
        "planUntil": r["plan_until"].isoformat() if r["plan_until"] else None, "status": r["status"], "verified": r["email_verified_at"] is not None,
        "mfa": r["totp_enabled_at"] is not None, "createdAt": r["created_at"].isoformat(),
        "lastLoginAt": r["last_login_at"].isoformat() if r["last_login_at"] else None} for r in rows]}


@router.patch("/admin/users/{uid}")
async def admin_patch(request: Request, uid: str, body: AdminUserPatch, ctx: Ctx = Depends(admin_ctx)):
    if not re.fullmatch(r"[0-9a-f-]{36}", uid):
        raise fail(400, "invalid_id")
    if uid == ctx.user_id and (body.role == "investor" or body.status == "disabled"):
        raise fail(409, "self_change", "You cannot remove your own access.")
    pool = request.app.state.store.pool
    sets, args = [], [uid]
    if body.plan is not None:
        args.append(body.plan)
        sets.append(f"plan = ${len(args)}")
        until = datetime.now(timezone.utc) + timedelta(days=body.plan_days) if body.plan_days and body.plan != "basic" else None
        args.append(until)
        sets.append(f"plan_until = ${len(args)}")
    if body.role is not None:
        args.append(body.role)
        sets.append(f"role = ${len(args)}")
    if body.status is not None:
        args.append(body.status)
        sets.append(f"status = ${len(args)}")
    if body.verify_email:
        sets.append("email_verified_at = COALESCE(email_verified_at, now())")
    if not sets:
        raise fail(422, "nothing_to_change")
    async with pool.acquire() as conn:
        done = await conn.fetchval(f"UPDATE users SET {', '.join(sets)} WHERE id = $1 RETURNING id", *args)  # nosec B608 - fragments are fixed strings
        if body.plan in ("silver", "gold"):
            await conn.execute("UPDATE plan_requests SET status = 'granted', resolved_at = now() WHERE user_id = $1 AND status = 'open' AND plan = $2", uid, body.plan)
    if done is None:
        raise fail(404, "not_found")
    if body.status == "disabled":
        await revoke_all(request.app, uid)
    else:
        await forget_cached(request.app, uid)
    await audit(pool, ctx.user_id, "admin_user_change", uid, ip_of(request), **body.model_dump(exclude_none=True))
    return {"status": "saved"}


@router.get("/admin/plan-requests")
async def admin_plan_requests(request: Request, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT r.id, r.plan, r.note, r.created_at, u.id AS uid, u.email, u.plan AS current FROM plan_requests r "
                                "JOIN users u ON u.id = r.user_id WHERE r.status = 'open' ORDER BY r.created_at LIMIT 100")
    return {"requests": [{"id": r["id"], "plan": r["plan"], "note": r["note"], "createdAt": r["created_at"].isoformat(), "userId": str(r["uid"]),
                          "email": r["email"], "currentPlan": r["current"]} for r in rows]}


@router.post("/admin/plan-requests/{rid}/decline")
async def admin_decline(request: Request, rid: int, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE plan_requests SET status = 'declined', resolved_at = now() WHERE id = $1 AND status = 'open'", rid)
    await audit(request.app.state.store.pool, ctx.user_id, "plan_request_declined", str(rid), ip_of(request))
    return {"status": "declined"}


@router.get("/admin/data-health")
async def admin_data_health(request: Request, ctx: Ctx = Depends(admin_ctx)):
    return Response(content=json.dumps(await request.app.state.store.health()), media_type="application/json", headers=NO_STORE)


# ------------------------------------------------------------------ news, result dates, documents
class FeedIn(BaseModel):
    kind: Literal["news", "result", "document"]
    title: str = Field(min_length=3, max_length=300)
    symbol: Optional[str] = Field(default=None, max_length=24)
    company: Optional[str] = Field(default=None, max_length=120)
    source: Optional[str] = Field(default=None, max_length=80)
    link: Optional[str] = Field(default=None, max_length=400)
    item_date: _date
    category: Optional[str] = Field(default=None, max_length=80)
    period: Optional[str] = Field(default=None, max_length=24)
    summary: Optional[str] = Field(default=None, max_length=600)

    @field_validator("link")
    @classmethod
    def link_ok(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^https://[^\s<>\"']+$", v):
            raise ValueError("link must start with https://")
        return v or None

    @field_validator("symbol")
    @classmethod
    def sym_ok(cls, v: Optional[str]) -> Optional[str]:
        if v and not SYMBOL.match(v.strip().upper()):
            raise ValueError("bad symbol")
        return v.strip().upper() if v else None


FEED_COLS = "kind, title, symbol, company, source, link, item_date, category, period, summary"


def feed_json(r: Any) -> Dict[str, Any]:
    return {"id": r["id"], "kind": r["kind"], "title": r["title"], "symbol": r["symbol"], "company": r["company"], "source": r["source"], "link": r["link"],
            "date": r["item_date"].isoformat(), "category": r["category"], "period": r["period"], "summary": r["summary"], "auto": r["auto"]}


@router.get("/feed")
async def feed(request: Request, kind: Literal["news", "result", "document"] = "news", symbol: str = Query("", max_length=1200), q: str = Query("", max_length=80),
               upcoming: bool = False, limit: int = Query(60, ge=1, le=3000), before: Optional[_date] = None,
               from_date: Optional[_date] = None, to_date: Optional[_date] = None):
    """Public. `symbol` may be one symbol or several separated by commas (a watchlist). `upcoming=true` returns dates from today on, soonest first."""
    syms = [x.strip().upper() for x in symbol.split(",") if x.strip()][:60]
    if any(not SYMBOL.match(x) for x in syms):
        raise fail(400, "invalid_symbol")
    windowed = from_date is not None and to_date is not None and 0 <= (to_date - from_date).days <= 62
    if limit > 200 and not windowed:
        raise fail(400, "bad_request", "A long list needs a date window of two months or less.")
    where, args = ["kind = $1"], [kind]
    if windowed:
        args += [from_date, to_date]
        where.append(f"item_date BETWEEN ${len(args) - 1} AND ${len(args)}")
    if syms:
        args.append(syms)
        where.append(f"symbol = ANY(${len(args)}::text[])")
    if q.strip():
        args.append(f"%{q.strip().lower()}%")
        where.append(f"(lower(title) LIKE ${len(args)} OR lower(coalesce(company, '')) LIKE ${len(args)})")
    if upcoming:
        args.append(datetime.now(IST).date())
        where.append(f"item_date >= ${len(args)}")
    elif before:
        args.append(before)
        where.append(f"item_date < ${len(args)}")
    args.append(limit)
    order = "item_date ASC, id" if upcoming else "item_date DESC, id DESC"
    sql = "SELECT * FROM feed_items WHERE " + " AND ".join(where) + f" ORDER BY {order} LIMIT ${len(args)}"  # nosec B608 - fragments are fixed; values are bound
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch(sql, *args)
    return Response(content=json.dumps({"items": [feed_json(r) for r in rows]}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=60, stale-while-revalidate=300"})


@router.post("/admin/feed", status_code=201)
async def feed_create(request: Request, body: FeedIn, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        new_id = await conn.fetchval(f"INSERT INTO feed_items ({FEED_COLS}) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id", *[getattr(body, c) for c in FEED_COLS.split(", ")])  # nosec B608
    await audit(request.app.state.store.pool, ctx.user_id, "feed_added", str(new_id), ip_of(request), kind=body.kind)
    return {"id": new_id}


@router.delete("/admin/feed/{fid}")
async def feed_delete(request: Request, fid: int, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM feed_items WHERE id = $1", fid)
    await audit(request.app.state.store.pool, ctx.user_id, "feed_removed", str(fid), ip_of(request))
    return {"status": "deleted"}


# ------------------------------------------------------------------ IPO calendar
from datetime import date as _date  # noqa: E402


class IpoIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    symbol: Optional[str] = Field(default=None, max_length=24)
    kind: Literal["mainboard", "sme"] = "mainboard"
    sector: Optional[str] = Field(default=None, max_length=60)
    open_date: _date
    close_date: _date
    listing_date: Optional[_date] = None
    price_low: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    price_high: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    lot_size: Optional[int] = Field(default=None, ge=1, le=10_000_000)
    issue_size_cr: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    listing_price: Optional[float] = Field(default=None, ge=0, le=1_000_000)
    note: Optional[str] = Field(default=None, max_length=400)
    link: Optional[str] = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def dates_ok(self) -> "IpoIn":
        if self.close_date < self.open_date:
            raise ValueError("the issue cannot close before it opens")
        if self.listing_date and self.listing_date < self.close_date:
            raise ValueError("listing cannot be before the close")
        if self.price_low is not None and self.price_high is not None and self.price_high < self.price_low:
            raise ValueError("price band is the wrong way round")
        return self

    @field_validator("link")
    @classmethod
    def link_ok(cls, v: Optional[str]) -> Optional[str]:
        if v and not re.match(r"^https://[^\s<>\"']+$", v):
            raise ValueError("link must start with https://")
        return v or None

    @field_validator("symbol")
    @classmethod
    def sym_ok(cls, v: Optional[str]) -> Optional[str]:
        if v and not SYMBOL.match(v.strip().upper()):
            raise ValueError("bad symbol")
        return v.strip().upper() if v else None


def ipo_status(row: Any, today: _date) -> str:
    if row["open_date"] > today:
        return "upcoming"
    if row["close_date"] >= today:
        return "open"
    if row["listing_date"] and row["listing_date"] <= today:
        return "listed"
    return "closed"


def ipo_json(row: Any, today: _date) -> Dict[str, Any]:
    f = lambda v: float(v) if v is not None else None  # noqa: E731
    return {"id": row["id"], "name": row["name"], "symbol": row["symbol"], "kind": row["kind"], "sector": row["sector"], "status": ipo_status(row, today),
            "openDate": row["open_date"].isoformat(), "closeDate": row["close_date"].isoformat(), "listingDate": row["listing_date"].isoformat() if row["listing_date"] else None,
            "priceLow": f(row["price_low"]), "priceHigh": f(row["price_high"]), "lotSize": row["lot_size"], "issueSizeCr": f(row["issue_size_cr"]),
            "listingPrice": f(row["listing_price"]), "note": row["note"], "link": row["link"]}


IPO_COLS = "name, symbol, kind, sector, open_date, close_date, listing_date, price_low, price_high, lot_size, issue_size_cr, listing_price, note, link"


@router.get("/ipos")
async def list_ipos(request: Request):
    """Public. Nearest first: open and upcoming issues, then the recent past."""
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM ipos ORDER BY open_date DESC LIMIT 300")
    today = datetime.now(IST).date()   # India's date: an IPO opening today must read "Open" from midnight IST, not 05:30
    return Response(content=json.dumps({"ipos": [ipo_json(r, today) for r in rows]}), media_type="application/json",
                    headers={"Cache-Control": "public, max-age=120, stale-while-revalidate=600"})


@router.post("/admin/ipos", status_code=201)
async def ipo_create(request: Request, body: IpoIn, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        new_id = await conn.fetchval(f"INSERT INTO ipos ({IPO_COLS}) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING id",  # nosec B608 - fixed column list
                                     *[getattr(body, c) for c in IPO_COLS.split(", ")])
    await audit(request.app.state.store.pool, ctx.user_id, "ipo_added", str(new_id), ip_of(request), name=body.name)
    return {"id": new_id}


@router.put("/admin/ipos/{iid}")
async def ipo_update(request: Request, iid: int, body: IpoIn, ctx: Ctx = Depends(admin_ctx)):
    cols = IPO_COLS.split(", ")
    sets = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(cols))
    async with request.app.state.store.pool.acquire() as conn:
        done = await conn.fetchval(f"UPDATE ipos SET {sets}, updated_at = now() WHERE id = $1 RETURNING id", iid, *[getattr(body, c) for c in cols])  # nosec B608 - fixed column list
    if done is None:
        raise fail(404, "not_found")
    await audit(request.app.state.store.pool, ctx.user_id, "ipo_changed", str(iid), ip_of(request), name=body.name)
    return {"status": "saved"}


@router.delete("/admin/ipos/{iid}")
async def ipo_delete(request: Request, iid: int, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        await conn.execute("DELETE FROM ipos WHERE id = $1", iid)
    await audit(request.app.state.store.pool, ctx.user_id, "ipo_removed", str(iid), ip_of(request))
    return {"status": "deleted"}


@router.get("/admin/audit")
async def admin_audit(request: Request, ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT at, actor_id, action, target, ip, meta FROM audit_events ORDER BY id DESC LIMIT 200")
    return {"events": [{"at": r["at"].isoformat(), "actor": str(r["actor_id"]) if r["actor_id"] else None, "action": r["action"],
                        "target": r["target"], "ip": r["ip"], "meta": json.loads(r["meta"]) if isinstance(r["meta"], str) else r["meta"]} for r in rows]}


__all__ = ["router", "PLANS", "PALETTES", "ANON"]


# ------------------------------------------------------------------ one sign-in for the website's CMS
def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@router.post("/me/cms-token")
async def cms_token(request: Request, ctx: Ctx = Depends(admin_ctx)):
    """Administrators who signed in (with their authenticator code) get an 8-hour token for the blog/CMS tools, so there is no second login.
    It is the same HS256 token the site backend issues itself; both services share CMS_JWT_SECRET."""
    secret = request.app.state.settings.cms_jwt_secret
    if len(secret.encode()) < 32:
        raise fail(503, "cms_not_configured", "The content tools are not connected yet (CMS_JWT_SECRET is missing).")
    user = await request.app.state.store.pool.fetchrow("SELECT email FROM users WHERE id = $1", ctx.user_id)
    now, ttl = int(time.time()), 8 * 3600
    head = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64(json.dumps({"sub": user["email"], "role": "admin", "iat": now, "exp": now + ttl}, separators=(",", ":")).encode())
    sig = _b64(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest())
    await audit(request.app.state.store.pool, ctx.user_id, "cms_token", None, ip_of(request))
    return Response(content=json.dumps({"token": f"{head}.{body}.{sig}", "expiresIn": ttl}), media_type="application/json", headers=NO_STORE)
