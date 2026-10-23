"""Accounts end to end against real Postgres and Redis: sign-up, mail links, sessions, CSRF, lockout, MFA, plans, admin."""

import re

import httpx
import pytest

from finlit.api import create_app
from finlit.auth import crypto
from test_integration import ingested, make_settings, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
ORIGIN = {"Origin": "http://test"}
PW = "a-long-unusual-phrase-42"


@pytest.fixture
async def app(ingested):  # noqa: F811
    app = create_app(make_settings(), store=ingested)
    async with app.router.lifespan_context(app):
        yield app


def new_client(app, **kw):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", **kw)


@pytest.fixture
async def anon(app):
    async with new_client(app) as c:
        yield c


async def last_mail(app, to):
    async with app.state.store.pool.acquire() as conn:
        return await conn.fetchrow("SELECT subject, body FROM outbox WHERE to_email = $1 ORDER BY id DESC LIMIT 1", to)


async def token_from_mail(app, to):
    row = await last_mail(app, to)
    return re.search(r"token=([A-Za-z0-9_\-]+)", row["body"]).group(1)


async def signup(app, c, email, password=PW):
    r = await c.post("/api/auth/register", json={"email": email, "password": password, "name": "Asha", "accept_terms": True}, headers=ORIGIN)
    assert r.status_code == 202, r.text
    r = await c.post("/api/auth/verify-email", json={"token": await token_from_mail(app, email)}, headers=ORIGIN)
    assert r.status_code == 200, r.text


async def login(c, email, password=PW, **extra):
    r = await c.post("/api/auth/login", json={"email": email, "password": password, **extra}, headers=ORIGIN)
    return r


async def signed_in(app, email="asha@example.com", plan=None):
    c = new_client(app)
    await signup(app, c, email)
    if plan:
        async with app.state.store.pool.acquire() as conn:
            await conn.execute("UPDATE users SET plan = $2 WHERE lower(email) = $1", email, plan)
    r = await login(c, email)
    assert r.status_code == 200, r.text
    c.headers.update({**ORIGIN, "X-CSRF-Token": r.json()["csrf"]})
    return c


async def test_visitor_identity_and_plan(anon):
    r = await anon.get("/api/auth/me")
    body = r.json()
    assert body["user"] is None and body["plan"] == "basic" and body["csrf"] is None
    assert r.headers["cache-control"] == "no-store"


async def test_register_verify_login_logout(app, anon):
    r = await anon.post("/api/auth/register", json={"email": "Asha@Example.com", "password": PW, "accept_terms": True}, headers=ORIGIN)
    assert r.status_code == 202
    assert (await login(anon, "asha@example.com")).status_code == 403  # not verified yet
    mail = await last_mail(app, "asha@example.com")
    assert "Confirm" in mail["subject"] and PW not in mail["body"]
    token = await token_from_mail(app, "asha@example.com")
    assert (await anon.post("/api/auth/verify-email", json={"token": token}, headers=ORIGIN)).status_code == 200
    assert (await anon.post("/api/auth/verify-email", json={"token": token}, headers=ORIGIN)).status_code == 400  # single use
    r = await login(anon, "asha@example.com")
    assert r.status_code == 200 and r.json()["user"]["plan"] == "basic"
    cookie = r.headers["set-cookie"]
    assert "fl_session=" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
    me = (await anon.get("/api/auth/me")).json()
    assert me["user"]["email"] == "asha@example.com" and me["csrf"]
    async with app.state.store.pool.acquire() as conn:  # only the hash is stored
        stored = await conn.fetchval("SELECT token_hash FROM sessions LIMIT 1")
    assert stored != anon.cookies.get("fl_session") and len(stored) == 64
    out = await anon.post("/api/auth/logout", headers={**ORIGIN, "X-CSRF-Token": me["csrf"]})
    assert out.status_code == 200
    assert (await anon.get("/api/auth/me")).json()["user"] is None


async def test_signup_does_not_reveal_existing_accounts(app, anon):
    await signup(app, anon, "asha@example.com")
    first = await anon.post("/api/auth/register", json={"email": "new@example.com", "password": PW, "accept_terms": True}, headers=ORIGIN)
    again = await anon.post("/api/auth/register", json={"email": "asha@example.com", "password": PW, "accept_terms": True}, headers=ORIGIN)
    assert first.status_code == again.status_code == 202 and first.json() == again.json()
    assert "already" in (await last_mail(app, "asha@example.com"))["subject"].lower()


async def test_signup_rules(app, anon):
    bad = {"email": "x@example.com", "password": PW, "accept_terms": True}
    assert (await anon.post("/api/auth/register", json={**bad, "password": "short"}, headers=ORIGIN)).status_code == 422
    assert (await anon.post("/api/auth/register", json={**bad, "accept_terms": False}, headers=ORIGIN)).status_code == 422
    assert (await anon.post("/api/auth/register", json={**bad, "email": "nope"}, headers=ORIGIN)).status_code == 422
    assert (await anon.post("/api/auth/register", json=bad, headers={"Origin": "https://evil.example"})).status_code == 403


async def test_wrong_credentials_are_indistinguishable(app, anon):
    await signup(app, anon, "asha@example.com")
    a = await login(anon, "asha@example.com", "wrong-password-123")
    b = await login(anon, "nobody@example.com", "wrong-password-123")
    assert a.status_code == b.status_code == 401 and a.json() == b.json()


async def test_repeated_failures_are_slowed_the_same_way_for_real_and_unknown_accounts(app, anon):
    """No account-wide lock (an attacker could keep the owner out, and a 'locked' answer revealed which emails have accounts): the same budget
    applies per email and address, and a real and an unknown email are refused identically."""
    await signup(app, anon, "asha@example.com")
    real = [await login(anon, "asha@example.com", f"wrong-password-{i}") for i in range(11)]
    assert [r.status_code for r in real] == [401] * 10 + [429]
    unknown = [await login(anon, "nobody@example.com", f"wrong-password-{i}") for i in range(11)]
    assert {r.status_code for r in unknown} <= {401, 429} and unknown[-1].status_code == 429   # the per-address budget is shared, so it may end sooner
    assert real[-1].json()["detail"]["status"] == unknown[-1].json()["detail"]["status"] == "rate_limited"
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT locked_until IS NULL FROM users WHERE lower(email) = 'asha@example.com'")


async def test_login_rate_limit_per_email(app, anon):
    await signup(app, anon, "asha@example.com")
    codes = [(await login(anon, "asha@example.com", f"wrong-password-{i}")).status_code for i in range(14)]
    assert 429 in codes


async def test_csrf_and_origin_are_enforced(app):
    c = await signed_in(app)
    body = {"lists": [], "meta": {}}
    no_csrf = await c.put("/api/me/prefs", json={"palette": "gold"}, headers={"X-CSRF-Token": "wrong"})
    assert no_csrf.status_code == 403 and no_csrf.json()["detail"]["status"] == "bad_csrf"
    wrong_origin = await c.put("/api/me/prefs", json={"palette": "gold"}, headers={"Origin": "https://evil.example"})
    assert wrong_origin.status_code == 403 and wrong_origin.json()["detail"]["status"] == "bad_origin"
    no_origin = await c.put("/api/me/prefs", json={"palette": "gold"}, headers={"Origin": ""})
    assert no_origin.status_code == 403
    assert (await c.put("/api/me/prefs", json={"palette": "gold"})).status_code == 200
    assert body  # silence unused
    await c.aclose()


async def test_protected_routes_need_a_session(anon):
    for method, path in (("GET", "/api/me/state"), ("PUT", "/api/me/prefs"), ("GET", "/api/admin/users"), ("DELETE", "/api/me")):
        r = await anon.request(method, path, json={}, headers=ORIGIN)
        assert r.status_code == 401, path


async def test_forged_and_expired_sessions_rejected(app, anon):
    anon.cookies.set("fl_session", "x" * 43)
    assert (await anon.get("/api/auth/me")).json()["user"] is None
    c = await signed_in(app)
    assert (await c.get("/api/auth/me")).json()["user"]
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE sessions SET expires_at = now() - interval '1 minute'")
    await app.state.store.redis.flushdb()  # drop the cached identity so the database decides
    assert (await c.get("/api/auth/me")).json()["user"] is None
    await c.aclose()


async def test_password_reset_flow_revokes_sessions(app, anon):
    c = await signed_in(app)
    assert (await c.get("/api/auth/me")).json()["user"]
    r = await anon.post("/api/auth/forgot", json={"email": "asha@example.com"}, headers=ORIGIN)
    ghost = await anon.post("/api/auth/forgot", json={"email": "ghost@example.com"}, headers=ORIGIN)
    assert r.status_code == ghost.status_code == 202 and r.json() == ghost.json()
    assert await last_mail(app, "ghost@example.com") is None
    token = await token_from_mail(app, "asha@example.com")
    assert (await anon.post("/api/auth/reset", json={"token": token, "password": "short"}, headers=ORIGIN)).status_code == 422
    new = "another-strong-phrase-77"
    assert (await anon.post("/api/auth/reset", json={"token": token, "password": new}, headers=ORIGIN)).status_code == 200
    assert (await anon.post("/api/auth/reset", json={"token": token, "password": new}, headers=ORIGIN)).status_code == 400
    assert (await c.get("/api/auth/me")).json()["user"] is None  # old sessions are gone
    assert (await login(anon, "asha@example.com", PW)).status_code == 401
    assert (await login(anon, "asha@example.com", new)).status_code == 200
    await c.aclose()


async def test_change_password_and_sessions_list(app):
    c = await signed_in(app)
    other = new_client(app)
    assert (await login(other, "asha@example.com")).status_code == 200
    sessions = (await c.get("/api/me/sessions")).json()["sessions"]
    assert len(sessions) == 2 and sum(1 for s in sessions if s["current"]) == 1
    assert (await c.post("/api/me/password", json={"current": "wrong", "new": "brand-new-phrase-12"})).status_code in (400, 401, 403)
    assert (await c.post("/api/me/password", json={"current": PW, "new": "brand-new-phrase-12"})).status_code == 200
    assert (await other.get("/api/auth/me")).json()["user"] is None  # other devices signed out
    assert (await c.get("/api/auth/me")).json()["user"]  # this one stays
    await c.aclose()
    await other.aclose()


async def test_plan_redaction_on_the_server(app, anon):
    # visitor: showcase company open, everything else trimmed; same for Basic accounts
    rel = (await anon.get("/api/stocks/RELIANCE")).json()
    assert rel["score"]["overall"] is not None and rel["thesis"]
    app.state.settings.showcase_symbols[:] = ["SOMETHINGELSE"]
    r = await anon.get("/api/stocks/RELIANCE")
    assert r.headers["cache-control"].startswith("private") and "Cookie" in r.headers["vary"]
    body = r.json()
    assert body["score"]["overall"] is None and body["thesis"] is None and body["strengths"] == []
    ratios = (await anon.get("/api/stocks/RELIANCE/ratios")).json()
    assert 0 < len(ratios["history"]["rows"]) <= 5 and ratios["valuationHistory"]["rows"] == {}
    price = (await anon.get("/api/stocks/RELIANCE/price?range=1Y")).json()
    assert "ema200" not in price["series"] and set(price["technical"]) <= {"price", "ema50", "vsEma200Pct"}
    assert (await anon.get("/api/stocks/RELIANCE/segments")).json()["segments"] == {}
    assert (await anon.get("/api/screener/top")).status_code == 403
    rows = (await anon.get("/api/screener/universe")).json()["rows"]
    assert rows[0]["overall"] is None and rows[0]["pe"] is not None  # plain ratios stay open

    silver = await signed_in(app, "b@example.com", plan="silver")
    s = (await silver.get("/api/stocks/RELIANCE")).json()
    assert s["score"]["overall"] is not None and s["thesis"]
    hist = (await silver.get("/api/stocks/RELIANCE/ratios")).json()["history"]["rows"]
    assert hist and set(hist) <= {"gross_margin", "operating_margin", "net_margin", "roe", "roce"}
    assert (await silver.get("/api/screener/top")).status_code == 200
    assert "ema200" not in (await silver.get("/api/stocks/RELIANCE/price?range=1Y")).json()["series"]

    gold = await signed_in(app, "g@example.com", plan="gold")
    assert len((await gold.get("/api/stocks/RELIANCE/ratios")).json()["history"]["rows"]) > 5
    assert (await gold.get("/api/stocks/RELIANCE/price?range=1Y")).json()["series"].get("ema200")
    # a Gold response never reaches a Basic caller through the cache
    again = await anon.get("/api/stocks/RELIANCE/ratios")
    assert len(again.json()["history"]["rows"]) <= 5
    for c in (silver, gold):
        await c.aclose()


async def test_plan_change_applies_immediately(app):
    c = await signed_in(app, "asha@example.com")
    assert (await c.get("/api/auth/me")).json()["plan"] == "basic"
    async with app.state.store.pool.acquire() as conn:
        uid = await conn.fetchval("SELECT id FROM users")
        await conn.execute("UPDATE users SET plan = 'gold', plan_until = now() - interval '1 day' WHERE id = $1", uid)
    from finlit.auth.service import forget_cached
    await forget_cached(app, str(uid))
    assert (await c.get("/api/auth/me")).json()["plan"] == "basic"  # an expired plan counts as Basic
    await c.aclose()


async def test_saved_state_and_plan_limits(app):
    basic = await signed_in(app, "a@example.com")
    lists = {"lists": [{"id": "main", "name": "Core", "symbols": ["reliance", "TCS"]}], "meta": {"TCS": {"note": "check", "target": 4000}}}
    r = await basic.put("/api/me/watchlist", json=lists)
    assert r.status_code == 403 and r.json()["detail"]["status"] == "plan_required"

    silver = await signed_in(app, "b@example.com", plan="silver")
    assert (await silver.put("/api/me/watchlist", json=lists)).status_code == 200
    state = (await silver.get("/api/me/state")).json()
    assert state["watchlist"]["lists"][0]["symbols"] == ["RELIANCE", "TCS"] and state["watchlist"]["meta"]["TCS"]["target"] == 4000
    four = {"lists": [{"id": f"l{i}", "name": f"L{i}", "symbols": []} for i in range(4)], "meta": {}}
    assert (await silver.put("/api/me/watchlist", json=four)).json()["detail"]["status"] == "plan_limit"
    bad_symbol = {"lists": [{"id": "x", "name": "x", "symbols": ["A;DROP TABLE"]}], "meta": {}}
    assert (await silver.put("/api/me/watchlist", json=bad_symbol)).status_code == 422
    screen = {"screens": [{"name": "Quality", "state": {"ranges": {"roe": {"min": 15}}, "sectors": [], "bands": ["strong"]}}]}
    assert (await silver.put("/api/me/screens", json=screen)).status_code == 200
    unknown = {"screens": [{"name": "x", "state": {"ranges": {"__proto__": {"min": 1}}}}]}
    assert (await silver.put("/api/me/screens", json=unknown)).status_code == 422
    assert (await basic.put("/api/me/prefs", json={"palette": "midnight", "density": "compact", "dashboard": [{"id": "movers", "on": True, "size": "full"}]})).status_code == 200
    assert (await basic.get("/api/me/state")).json()["prefs"]["palette"] == "midnight"
    assert (await basic.put("/api/me/prefs", json={"palette": "neon"})).status_code == 422
    # one user never sees another's state
    assert (await silver.get("/api/me/state")).json()["prefs"] == {}
    for c in (basic, silver):
        await c.aclose()


async def test_plan_request_is_deduplicated(app):
    c = await signed_in(app)
    assert (await c.post("/api/me/plan-request", json={"plan": "silver", "note": "please"})).status_code == 201
    assert (await c.post("/api/me/plan-request", json={"plan": "silver"})).status_code == 201
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM plan_requests") == 1
    await c.aclose()


async def test_mfa_enrolment_and_login(app):
    c = await signed_in(app)
    setup = (await c.post("/api/me/mfa/setup")).json()
    secret = setup["secret"]
    assert setup["uri"].startswith("otpauth://totp/")
    import time
    code = crypto.totp_code(secret, int(time.time()) // 30)
    assert (await c.post("/api/me/mfa/enable", json={"code": "000000"})).status_code == 400
    assert (await c.post("/api/me/mfa/enable", json={"code": code})).status_code == 200
    async with app.state.store.pool.acquire() as conn:
        assert secret not in (await conn.fetchval("SELECT totp_secret_enc FROM users"))  # encrypted at rest
    other = new_client(app)
    r = await login(other, "asha@example.com")
    assert r.status_code == 401 and r.json()["detail"]["status"] == "mfa_required"
    assert (await login(other, "asha@example.com", code="000000")).status_code == 401
    assert (await login(other, "asha@example.com", code=code)).status_code == 401  # that code was used to enrol
    later = crypto.totp_code(secret, int(time.time()) // 30 + 1)
    assert (await login(other, "asha@example.com", code=later)).status_code == 200
    await c.aclose()
    await other.aclose()


async def make_admin(app, email="boss@example.com"):
    c = new_client(app)
    await signup(app, c, email)
    async with app.state.store.pool.acquire() as conn:
        await conn.execute("UPDATE users SET role = 'admin' WHERE lower(email) = $1", email)
    r = await login(c, email)
    assert r.status_code == 200 and r.json()["mfaSetupRequired"] is True
    c.headers.update({**ORIGIN, "X-CSRF-Token": r.json()["csrf"]})
    return c


async def test_admin_requires_mfa_and_regular_users_are_blocked(app):
    user = await signed_in(app, "u@example.com")
    for path in ("/api/admin/users", "/api/admin/plan-requests", "/api/admin/audit"):
        assert (await user.get(path)).json()["detail"]["status"] == "forbidden", path
    admin = await make_admin(app)
    assert (await admin.get("/api/admin/users")).json()["detail"]["status"] == "mfa_required"  # signed in, no second step yet
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    import time
    assert (await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    users = await admin.get("/api/admin/users")
    assert users.status_code == 200 and {u["email"] for u in users.json()["users"]} >= {"u@example.com", "boss@example.com"}
    assert "password_hash" not in users.text and "totp" not in users.text.replace("totpEnabled", "")
    assert (await admin.post("/api/me/mfa/disable", json={"code": "000000"})).status_code == 403  # admins cannot turn it off
    uid = next(u["id"] for u in users.json()["users"] if u["email"] == "u@example.com")
    assert (await admin.patch(f"/api/admin/users/{uid}", json={"plan": "gold", "plan_days": 30})).status_code == 200
    assert (await user.get("/api/auth/me")).json()["plan"] == "gold"  # takes effect at once
    assert (await admin.get("/api/admin/audit")).status_code == 200
    # nobody can lock themselves out of admin by accident
    me_id = next(u["id"] for u in users.json()["users"] if u["email"] == "boss@example.com")
    assert (await admin.patch(f"/api/admin/users/{me_id}", json={"role": "investor"})).status_code in (400, 403, 409)
    for c in (user, admin):
        await c.aclose()


async def test_delete_account_removes_everything(app):
    c = await signed_in(app)
    assert (await c.request("DELETE", "/api/me", json={"password": "wrong-password-123"})).status_code in (400, 401, 403)
    assert (await c.request("DELETE", "/api/me", json={"password": PW})).status_code == 200
    async with app.state.store.pool.acquire() as conn:
        assert await conn.fetchval("SELECT count(*) FROM users") == 0
        assert await conn.fetchval("SELECT count(*) FROM sessions") == 0
    assert (await c.get("/api/auth/me")).json()["user"] is None
    await c.aclose()


async def test_oversized_bodies_rejected(anon):
    r = await anon.post("/api/auth/login", content=b"x" * 70_000, headers={**ORIGIN, "Content-Type": "application/json"})
    assert r.status_code == 413


async def test_score_history_needs_silver_for_other_companies_and_data_health_is_admin_only(app, anon):
    app.state.settings.showcase_symbols[:] = ["SOMETHINGELSE"]
    assert (await anon.get("/api/stocks/RELIANCE/score-history")).status_code == 403
    silver = await signed_in(app, "b@example.com", plan="silver")
    assert len((await silver.get("/api/stocks/RELIANCE/score-history")).json()["points"]) == 1
    assert (await silver.get("/api/admin/data-health")).status_code == 403
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    import time
    await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})
    h = await admin.get("/api/admin/data-health")
    assert h.status_code == 200 and h.json()["loaded"] == 1
    for c in (silver, admin):
        await c.aclose()


async def test_target_price_alert_fires_once_on_a_crossing(app):
    from finlit.alerts import check_alerts
    pool = app.state.store.pool
    c = await signed_in(app, "b@example.com", plan="silver")
    wl = {"lists": [{"id": "main", "name": "x", "symbols": ["RELIANCE"]}], "meta": {"RELIANCE": {"target": 1200, "added": 1}}}
    assert (await c.put("/api/me/watchlist", json=wl)).status_code == 200
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scores SET price = 1100 WHERE symbol = 'RELIANCE'")
    mailer = app.state.mailer
    assert await check_alerts(pool, mailer, "http://test") == 0   # first look only records the side
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scores SET price = 1250 WHERE symbol = 'RELIANCE'")
    assert await check_alerts(pool, mailer, "http://test") == 1   # crossed upward
    mail = await last_mail(app, "b@example.com")
    assert "crossed your target" in mail["subject"] and "1,250.00" in mail["body"]
    assert await check_alerts(pool, mailer, "http://test") == 0   # no repeat while it stays above
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scores SET price = 1100 WHERE symbol = 'RELIANCE'")
    assert await check_alerts(pool, mailer, "http://test") == 0   # crossed back, but only one email a day per stock
    assert (await c.put("/api/me/prefs", json={"palette": "gold", "alerts": False})).status_code == 200
    await c.aclose()


async def test_ipo_calendar_public_read_admin_write(app, anon):
    import time
    from datetime import date, timedelta
    d = date.today()
    ipo = {"name": "Sample Industries Ltd", "kind": "mainboard", "open_date": str(d + timedelta(days=3)), "close_date": str(d + timedelta(days=5)),
           "listing_date": str(d + timedelta(days=10)), "price_low": 100, "price_high": 105, "lot_size": 140, "issue_size_cr": 500, "link": "https://example.com/rhp"}
    user = await signed_in(app, "u@example.com")
    assert (await user.post("/api/admin/ipos", json=ipo)).status_code == 403
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})
    assert (await admin.post("/api/admin/ipos", json={**ipo, "close_date": str(d)})).status_code == 422   # closes before it opens
    assert (await admin.post("/api/admin/ipos", json={**ipo, "link": "javascript:alert(1)"})).status_code == 422
    made = await admin.post("/api/admin/ipos", json=ipo)
    assert made.status_code == 201
    rows = (await anon.get("/api/ipos")).json()["ipos"]          # visitors can read it
    assert len(rows) == 1 and rows[0]["status"] == "upcoming" and rows[0]["priceHigh"] == 105.0
    iid = made.json()["id"]
    assert (await admin.put(f"/api/admin/ipos/{iid}", json={**ipo, "open_date": str(d - timedelta(days=1))})).status_code == 200
    assert (await anon.get("/api/ipos")).json()["ipos"][0]["status"] == "open"
    assert (await anon.delete(f"/api/admin/ipos/{iid}", headers=ORIGIN)).status_code == 401
    assert (await admin.delete(f"/api/admin/ipos/{iid}")).status_code == 200
    assert (await anon.get("/api/ipos")).json()["ipos"] == []
    for c in (user, admin):
        await c.aclose()


async def test_feed_admin_add_public_read_and_filters(app, anon):
    import time
    from datetime import date, timedelta
    d = date.today()
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})
    res = {"kind": "result", "title": "Q2 FY27 results", "symbol": "TCS", "company": "Tata Consultancy Services", "item_date": str(d + timedelta(days=4)), "period": "Q2 FY27", "category": "Board meeting"}
    assert (await anon.post("/api/admin/feed", json=res, headers=ORIGIN)).status_code == 401
    assert (await admin.post("/api/admin/feed", json={**res, "link": "http://insecure.example"})).status_code == 422
    made = await admin.post("/api/admin/feed", json=res)
    assert made.status_code == 201
    await admin.post("/api/admin/feed", json={"kind": "news", "title": "Sector update for IT services", "item_date": str(d), "source": "FinLit"})
    up = (await anon.get("/api/feed?kind=result&upcoming=true")).json()["items"]
    assert len(up) == 1 and up[0]["symbol"] == "TCS" and up[0]["period"] == "Q2 FY27"
    assert (await anon.get("/api/feed?kind=result&symbol=INFY")).json()["items"] == []
    assert len((await anon.get("/api/feed?kind=news&q=sector")).json()["items"]) == 1
    assert (await admin.delete(f"/api/admin/feed/{made.json()['id']}")).status_code == 200
    assert (await anon.get("/api/feed?kind=result&upcoming=true")).json()["items"] == []
    await admin.aclose()


async def test_portfolio_is_saved_per_plan_and_validated(app):
    basic = await signed_in(app, "a@example.com")
    h = {"holdings": [{"id": "h1", "symbol": "reliance", "qty": 10, "price": 1200.5, "date": "2025-01-15"}]}
    assert (await basic.put("/api/me/portfolio", json=h)).json()["detail"]["status"] == "plan_required"
    silver = await signed_in(app, "b@example.com", plan="silver")
    assert (await silver.put("/api/me/portfolio", json=h)).status_code == 200
    assert (await silver.get("/api/me/state")).json()["portfolio"]["holdings"][0]["symbol"] == "RELIANCE"
    for bad in ({"id": "h2", "symbol": "TCS", "qty": 0, "price": 1}, {"id": "h2", "symbol": "A;B", "qty": 1, "price": 1}, {"id": "h2", "symbol": "TCS", "qty": 1, "price": 1, "date": "tomorrow"}):
        assert (await silver.put("/api/me/portfolio", json={"holdings": [bad]})).status_code == 422
    many = {"holdings": [{"id": f"h{i}", "symbol": "TCS", "qty": 1, "price": 1} for i in range(31)]}
    assert (await silver.put("/api/me/portfolio", json=many)).json()["detail"]["status"] == "plan_limit"
    dup = {"holdings": [{"id": "x", "symbol": "TCS", "qty": 1, "price": 1}, {"id": "x", "symbol": "INFY", "qty": 1, "price": 1}]}
    assert (await silver.put("/api/me/portfolio", json=dup)).status_code == 422
    for c in (basic, silver):
        await c.aclose()


async def test_screen_alert_emails_only_new_matches(app):
    from finlit.screens import check_screens, matches
    pool = app.state.store.pool
    assert matches({"pe": 15, "sector": "IT", "band": "strong", "overall": 80}, {"ranges": {"pe": {"max": 20}}, "sectors": ["IT"], "bands": ["strong"]})
    assert not matches({"pe": 25}, {"ranges": {"pe": {"max": 20}}}) and not matches({"pe": None}, {"ranges": {"pe": {"max": 20}}})
    c = await signed_in(app, "b@example.com", plan="silver")
    screen = {"screens": [{"name": "Cheap", "state": {"ranges": {"pe": {"max": 30}}, "sectors": [], "bands": []}}]}
    assert (await c.put("/api/me/screens", json=screen)).status_code == 200
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scores SET pe = 50, metrics = jsonb_set(coalesce(metrics, '{}'::jsonb), '{pe}', '50') WHERE symbol = 'RELIANCE'")
    assert await check_screens(pool, app.state.mailer, "http://test") == 0      # first look just remembers
    async with pool.acquire() as conn:
        await conn.execute("UPDATE scores SET pe = 20, metrics = jsonb_set(coalesce(metrics, '{}'::jsonb), '{pe}', '20') WHERE symbol = 'RELIANCE'")
    assert await check_screens(pool, app.state.mailer, "http://test") == 1      # RELIANCE newly matches
    assert "RELIANCE" in (await last_mail(app, "b@example.com"))["body"]
    assert await check_screens(pool, app.state.mailer, "http://test") == 0      # nothing new the next time
    await c.aclose()


async def test_weekly_digest_is_opt_in_and_sent_once_a_week(app):
    from datetime import date, timedelta
    from finlit.digest import send_digests
    pool = app.state.store.pool
    c = await signed_in(app, "b@example.com", plan="silver")
    await c.put("/api/me/watchlist", json={"lists": [{"id": "m", "name": "x", "symbols": ["RELIANCE"]}], "meta": {}})
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO feed_items (kind, title, symbol, company, item_date, period) VALUES ('result', 'Board meeting', 'RELIANCE', 'Reliance', $1, 'Q2 FY27')", date.today() + timedelta(days=2))
    await c.put("/api/me/prefs", json={"palette": "gold", "digest": False})
    assert await send_digests(pool, app.state.mailer, "http://test") == 0       # nothing unless the member asked for it
    await c.put("/api/me/prefs", json={"palette": "gold", "digest": True})
    assert await send_digests(pool, app.state.mailer, "http://test") == 1
    mail = await last_mail(app, "b@example.com")
    assert "RESULTS THIS WEEK" in mail["body"] and "RELIANCE" in mail["body"] and "Account" in mail["body"]
    assert await send_digests(pool, app.state.mailer, "http://test") == 0       # once per week
    await c.aclose()


async def test_auto_verify_email_confirms_new_accounts_at_sign_up_for_staging(ingested):  # noqa: F811
    app = create_app(make_settings(auto_verify_email=True), store=ingested)
    async with app.router.lifespan_context(app):
        async with new_client(app) as c:
            r = await c.post("/api/auth/register", json={"email": "new@example.com", "password": PW, "name": "New", "accept_terms": True}, headers=ORIGIN)
            assert r.status_code == 201 and r.json()["status"] == "created"
            assert await last_mail(app, "new@example.com") is None  # no confirmation mail is needed
            assert (await login(c, "new@example.com")).status_code == 200  # and the member can sign in at once


async def test_without_auto_verify_a_new_member_cannot_sign_in_before_confirming(app, anon):
    r = await anon.post("/api/auth/register", json={"email": "later@example.com", "password": PW, "accept_terms": True}, headers=ORIGIN)
    assert r.status_code == 202
    assert (await login(anon, "later@example.com")).status_code in (401, 403)


def test_production_refuses_auto_verify_but_accepts_a_private_network_redis():
    from finlit.config import Settings
    base = dict(environment="production", finedge_mode="live", finedge_api_key="k", database_url="postgresql://u:p@db/finlit", secret_key="x" * 40,
                mail_mode="resend", resend_api_key="r", public_site_url="https://finlitventures.com", cors_origins=["https://finlitventures.com"],
                allowed_hosts=["finlitventures.com"])
    assert Settings(**base, redis_url="redis://red-abc123:6379").validate() == []  # Render's internal Redis has no password
    assert any("REDIS_URL" in p for p in Settings(**base, redis_url="redis://localhost:6379/0").validate())
    assert any("AUTO_VERIFY_EMAIL" in p for p in Settings(**base, redis_url="redis://red-abc123:6379", auto_verify_email=True).validate())

async def test_admin_gets_a_cms_token_the_site_backend_accepts(ingested):
    import base64, hashlib, hmac, json, time
    secret = "s" * 40
    app = create_app(make_settings(cms_jwt_secret=secret), store=ingested)
    async with app.router.lifespan_context(app):
        user = await signed_in(app, "m@example.com")
        assert (await user.post("/api/me/cms-token")).json()["detail"]["status"] == "forbidden"
        admin = await make_admin(app, "boss2@example.com")
        assert (await admin.post("/api/me/cms-token")).json()["detail"]["status"] == "mfa_required"
        s = (await admin.post("/api/me/mfa/setup")).json()["secret"]
        await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(s, int(time.time()) // 30)})
        r = await admin.post("/api/me/cms-token")
        assert r.status_code == 200, r.text
        head, body, sig = r.json()["token"].split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)  # noqa: E731
        assert base64.urlsafe_b64encode(hmac.new(secret.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode() == sig
        claims = json.loads(base64.urlsafe_b64decode(pad(body)))
        assert claims["role"] == "admin" and claims["sub"] == "boss2@example.com" and claims["exp"] > time.time() + 3600
        for c in (user, admin):
            await c.aclose()
    bare = create_app(make_settings(), store=ingested)
    async with bare.router.lifespan_context(bare):
        admin = await make_admin(bare, "boss3@example.com")
        s = (await admin.post("/api/me/mfa/setup")).json()["secret"]
        await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(s, int(time.time()) // 30)})
        assert (await admin.post("/api/me/cms-token")).json()["detail"]["status"] == "cms_not_configured"
        await admin.aclose()


async def test_admin_can_confirm_a_members_email_by_hand(app):
    import time
    member = new_client(app)
    r = await member.post("/api/auth/register", json={"email": "pending@example.com", "password": PW, "accept_terms": True}, headers=ORIGIN)  # not the signup helper: it confirms by mail
    assert r.status_code == 202
    assert (await login(member, "pending@example.com")).status_code in (401, 403)  # not confirmed, and no mail service to confirm with
    admin = await make_admin(app)
    secret = (await admin.post("/api/me/mfa/setup")).json()["secret"]
    assert (await admin.post("/api/me/mfa/enable", json={"code": crypto.totp_code(secret, int(time.time()) // 30)})).status_code == 200
    users = (await admin.get("/api/admin/users")).json()["users"]
    pending = next(u for u in users if u["email"] == "pending@example.com")
    assert pending["verified"] is False
    assert (await admin.patch(f"/api/admin/users/{pending['id']}", json={"verify_email": True})).status_code == 200
    assert (await login(member, "pending@example.com")).status_code == 200  # signs in at once
    assert next(u for u in (await admin.get("/api/admin/users")).json()["users"] if u["email"] == "pending@example.com")["verified"] is True


async def test_session_response_lists_the_free_example_companies(app, anon):
    me = (await anon.get("/api/auth/me")).json()
    assert "RELIANCE" in me["showcase"] and me["plan"] == "basic" and me["user"] is None
