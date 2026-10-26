"""FinLit Prism (finlit/prism.py) against real Postgres and Redis, with a fake site backend behind an httpx.MockTransport.

The fake answers POST /api/premium-reports with a REAL signed snapshot: tests/fixtures/prism/snapshot_example.json was made once with the
site backend's own pure pieces, so the stripping of internal fields is checked on the document the model really produces:

    cd site-api && PYTHONPATH=.:backend site-venv/bin/python ../backend/tests/fixtures/prism/make_fixture.py backend ../backend/tests/fixtures/prism/snapshot_example.json

where make_fixture.py (next to the fixture) runs premium_engine.score_company(premium_example.json, "MFG") (engine 3.6.10),
premium_trace.build_calculation_trace, premium_presentation.build_report_review, premium_technical.build_technical_assessment and
premium_snapshot.issue(report, "prism:fixture", "f" * 40) on the report dictionary that premium_service.generate_report builds (symbol TCS,
id "a" * 32), and writes the result with sorted keys. No provider is reachable offline, so the technicalAssessment is genuine engine output
for SYNTHETIC candles and index series (seeded random walks, see the script). The research API does not depend on PyJWT, so the fixture is
stored rather than built here.
"""

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from finlit import prism
from finlit.api import create_app
from finlit.auth.service import cookie_name, create_session
from test_integration import make_settings, store  # noqa: F401  (fixtures)

pytestmark = pytest.mark.integration
SECRET = "s" * 40
SNAPSHOT = json.loads((Path(__file__).parent / "fixtures" / "prism" / "snapshot_example.json").read_text())


def claims(token: str) -> dict:
    """The claims of an HS256 token, after checking its signature with the shared secret."""
    head, body, sig = token.split(".")
    want = base64.urlsafe_b64encode(hmac.new(SECRET.encode(), f"{head}.{body}".encode(), hashlib.sha256).digest()).rstrip(b"=").decode()
    assert hmac.compare_digest(sig, want)
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


class FakeSite:
    """The site backend's three routes Prism uses, with its require_admin and snapshot rules reduced to what Prism relies on."""

    def __init__(self):
        self.reports, self.pdfs, self.pings = [], [], 0
        self.issued = {}                  # id -> (token subject, signed snapshot)
        self.answer = None                # a canned httpx.Response (or exception) for the next calculations
        self.gate = None                  # an asyncio.Event a calculation waits for
        self.started = asyncio.Event()

    def snapshot(self, sub, query, statement):
        snap = copy.deepcopy(SNAPSHOT)
        snap.update(id=uuid.uuid4().hex, statementType=statement, snapshotExpiresAt=(datetime.now(timezone.utc) + timedelta(seconds=1800)).isoformat())
        snap["company"]["symbol"] = query
        snap["snapshotReceipt"] = secrets.token_urlsafe(40)
        self.issued[snap["id"]] = (sub, snap)
        return snap

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/":
            self.pings += 1
            return httpx.Response(200, json={"message": "FinLit Ventures site API"})
        sub = claims(request.headers["authorization"].removeprefix("Bearer "))["sub"]
        body = json.loads(request.content)
        if request.url.path == "/api/premium-reports":
            self.reports.append({"sub": sub, "body": body, "auth": request.headers["authorization"]})
            self.started.set()
            if self.gate:
                await self.gate.wait()
            if isinstance(self.answer, Exception):
                raise self.answer
            if self.answer is not None:
                return self.answer
            return httpx.Response(200, json=self.snapshot(sub, body["query"], body["statement_type"]))
        if request.url.path == "/api/premium-reports/pdf":
            self.pdfs.append(sub)
            issued_sub, signed = self.issued.get(body["report"].get("id"), (None, {}))
            unsigned = {k: v for k, v in signed.items() if k != "snapshotReceipt"}
            if self.answer is not None:
                return self.answer
            if sub != issued_sub or body["receipt"] != signed["snapshotReceipt"] or body["report"] != unsigned:
                return httpx.Response(400, json={"detail": "This report is expired or has changed. Generate a fresh report before downloading."})
            return httpx.Response(200, content=b"%PDF-1.4 prism", headers={"content-type": "application/pdf"})
        return httpx.Response(404, json={"detail": "Not Found"})


async def make_app(store, **overrides):  # noqa: F811
    app = create_app(make_settings(**{"site_api_url": "http://site", "cms_jwt_secret": SECRET, "showcase_symbols": ["RELIANCE"], **overrides}), store=store)
    fake = FakeSite()
    app.state.prism_client = httpx.AsyncClient(transport=httpx.MockTransport(fake), base_url="http://site")
    return app, fake


@pytest.fixture
async def env(store, monkeypatch):  # noqa: F811
    monkeypatch.setattr(prism, "WAIT_STEP", 0.02)
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
    app, fake = await make_app(store)
    async with app.router.lifespan_context(app):
        yield app, fake


def client(app, **headers):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Origin": "http://test", **headers})


async def member(app, plan="basic", role="investor"):
    async with app.state.store.pool.acquire() as conn:
        user = await conn.fetchrow("INSERT INTO users (email, password_hash, role, plan, email_verified_at) VALUES ($1, 'unused', $2, $3, now()) "
                                   "RETURNING id, role", f"{secrets.token_hex(5)}@example.com", role, plan)
    raw, csrf = await create_session(app, user, "127.0.0.1", "pytest", True)
    c = client(app, **{"X-CSRF-Token": csrf, "Cookie": f"{cookie_name(app.state.settings)}={raw}"})
    c.user_id = str(user["id"])
    return c


def generate(c, symbol="TCS", **extra):
    return c.post("/api/prism/reports", json={"symbol": symbol, "statement": "consolidated", **extra})


# ------------------------------------------------------------------ plan gating
async def test_only_gold_and_administrators_reach_prism_and_showcase_is_open(env):
    app, fake = env
    visitor = client(app)
    for c in (visitor, await member(app, "basic"), await member(app, "silver")):
        for r in (await generate(c), await c.get("/api/prism/reports/latest?symbol=TCS")):
            assert r.status_code == 403 and r.json()["status"] == "plan_required" and r.json()["plan"] == "gold"
            assert r.headers["cache-control"] == "no-store"
    assert fake.reports == []                                               # refused before any calculation
    assert (await generate(await member(app, "gold"))).status_code == 200
    assert (await generate(await member(app, "basic", role="admin"), "INFY")).status_code == 200
    r = await generate(visitor, "reliance")                                 # the showcase company is open to everyone
    assert r.status_code == 200 and r.json()["company"]["symbol"] == "RELIANCE"
    assert (await visitor.get("/api/prism/reports/latest?symbol=RELIANCE")).status_code == 200
    assert len(fake.reports) == 3


async def test_member_posts_need_our_origin_and_csrf_token(env):
    app, fake = env
    gold = await member(app, "gold")
    assert (await gold.post("/api/prism/reports", json={"symbol": "TCS"}, headers={"X-CSRF-Token": "wrong"})).status_code == 403
    assert (await client(app, Origin="https://evil.example").post("/api/prism/reports", json={"symbol": "RELIANCE"})).status_code == 403
    assert fake.reports == []


async def test_bad_input_is_a_422_before_anything_else(env):
    app, fake = env
    gold = await member(app, "gold")
    for body in ({"symbol": "DROP TABLE"}, {"symbol": "TCS", "statement": "annual"}, {"symbol": 5}, ["TCS"]):
        r = await gold.post("/api/prism/reports", json=body)
        assert r.status_code == 422 and r.json()["status"] == "bad_request", body
    assert (await gold.post("/api/prism/reports", content=b"not json", headers={"Content-Type": "application/json"})).status_code == 422
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS&statement=yearly")).status_code == 422
    assert fake.reports == []


# ------------------------------------------------------------------ the token and the document
async def test_token_is_a_five_minute_admin_token_for_the_member_or_the_visitor(env):
    app, fake = env
    gold = await member(app, "gold")
    await generate(gold)
    await generate(client(app), "RELIANCE")
    first, second = (claims(call["auth"].removeprefix("Bearer ")) for call in fake.reports)
    assert first["sub"] == f"prism:{gold.user_id}" and second["sub"] == "prism:visitor"
    for c in (first, second):
        assert c["role"] == "admin" and c["exp"] - c["iat"] == 300
    assert fake.reports[0]["body"] == {"query": "TCS", "statement_type": "consolidated", "delivery": "inline"}


async def test_internal_fields_are_stripped_and_the_full_snapshot_is_kept_for_the_pdf(env):
    app, fake = env
    gold = await member(app, "gold")
    r = await generate(gold)
    body = r.json()
    assert r.status_code == 200 and body["cached"] is False
    for key in prism.INTERNAL:
        assert key in SNAPSHOT and key not in body                     # present in the real document, never sent to the browser
    assert body["rating"]["modelVersion"] == SNAPSHOT["rating"]["modelVersion"] and body["review"] == SNAPSHOT["review"]
    assert body["rating"]["metrics"] and body["trends"] and body["inputMeta"]
    until = datetime.fromisoformat(body["pdfAvailableUntil"])
    assert timedelta(minutes=29) < until - datetime.now(timezone.utc) <= timedelta(minutes=30)
    row = await app.state.store.pool.fetchrow("SELECT * FROM prism_reports WHERE symbol = 'TCS' AND statement = 'consolidated'")
    stored = json.loads(row["report"])
    assert row["id"] == body["id"] and row["model_version"] == "3.6.10" and row["label"] == "AVERAGE" and row["status"] == "RATED"
    assert row["final"] == pytest.approx(SNAPSHOT["rating"]["final"])
    assert not set(prism.INTERNAL) & set(stored) and "cached" not in stored
    assert body["financialHistory"] == stored["financialHistory"] == prism.reader_view(SNAPSHOT)["financialHistory"]
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS")).json()["financialHistory"] == body["financialHistory"]
    kept = json.loads(await app.state.store.redis.get(f"prism:snap:{body['id']}"))
    assert kept["snapshot"]["snapshotReceipt"] and kept["snapshot"]["calculationTrace"] and kept["sub"].startswith("prism:")
    assert 1700 < await app.state.store.redis.ttl(f"prism:snap:{body['id']}") <= 1800


def test_reader_view_of_the_real_snapshot():
    view = prism.reader_view(SNAPSHOT)
    assert set(view) - set(SNAPSHOT) == {"financialHistory"} and set(SNAPSHOT) - set(view) == set(prism.INTERNAL)
    trace = SNAPSHOT["calculationTrace"]
    assert view["financialHistory"] == {k: trace[k] for k in ("quarterly", "annual", "latest")}   # verbatim, nothing more of the trace
    assert all(trace[k] for k in ("quarterly", "annual", "latest")) and "equation" not in json.dumps(view["financialHistory"]).lower()
    assert len(json.dumps(view)) < len(json.dumps(SNAPSHOT)) * 0.8       # the trace and inputs are most of the weight


# ------------------------------------------------------------------ ST/LT technical assessment (engine 3.6.10)
TECH = SNAPSHOT["technicalAssessment"]
SECRET_KEYS = {"inputHash", "sourceCodeSha256", "weight"}


def keys_anywhere(value, found=None):
    """Every dictionary key at any depth."""
    found = set() if found is None else found
    if isinstance(value, dict):
        for k, v in value.items():
            found.add(k)
            keys_anywhere(v, found)
    elif isinstance(value, list):
        for v in value:
            keys_anywhere(v, found)
    return found


def test_the_real_snapshot_carries_a_complete_technical_assessment():
    assert TECH["status"] == "ready" and TECH["modelVersion"] and SECRET_KEYS - {"weight"} <= set(TECH)
    for key, count in (("shortTerm", 14), ("longTerm", 13)):
        assert TECH[key]["status"] == "ready" and TECH[key]["availableCount"] == TECH[key]["requiredCount"] == count
        assert all("weight" in f for f in TECH[key]["factors"])           # present in the signed document, which the PDF renders


def test_technical_assessment_reaches_the_reader_without_hashes_weights_or_series():
    view = prism.reader_view(SNAPSHOT)["technicalAssessment"]
    assert not SECRET_KEYS & keys_anywhere(view) and not {"bars", "candles", "prices", "inputs"} & keys_anywhere({k: v for k, v in view.items() if k != "benchmarkSources"})
    for key in ("modelVersion", "status", "asOf", "provider", "fresh", "dailyBars", "usableDailyBars", "verdict", "notes", "observations"):
        assert view[key] == TECH[key]
    for key in ("shortTerm", "longTerm"):
        part, source = view[key], TECH[key]
        assert {k: v for k, v in part.items() if k != "factors"} == {k: v for k, v in source.items() if k != "factors"}   # scores and ratings are untouched
        assert [{k: v for k, v in f.items()} for f in part["factors"]] == [{k: v for k, v in f.items() if k != "weight"} for f in source["factors"]]
        assert set(part["factors"][0]) == {"key", "label", "signal", "status", "detail"}
    assert view["benchmarkSources"] == TECH["benchmarkSources"] and all(set(v) == {"provider", "asOf", "bars"} for v in view["benchmarkSources"].values())
    assert view["benchmarkSources"]["Nifty 50"]["bars"] == 700 and isinstance(view["benchmarkSources"]["Nifty 50"]["bars"], int)


def test_technical_view_drops_anything_that_is_not_for_readers():
    hostile = copy.deepcopy(TECH)
    hostile.update(inputHash="h", sourceCodeSha256="s", options={"sectorRS": False, "secret": "x"}, candles=[{"close": 1}], extra="x")
    hostile["observations"].update(series=[1, 2, 3], nested={"a": 1})
    hostile["benchmarkSources"]["Nifty 50"].update(bars=700, series=[1, 2], hash="x")
    hostile["shortTerm"]["factors"][0].update(weight=99, series=[1], hash="y")
    hostile["shortTerm"]["weights"] = [1]
    view = prism.technical_view(hostile)
    assert not SECRET_KEYS & keys_anywhere(view) and "candles" not in view and "extra" not in view
    assert view["options"] == {"sectorRS": False}
    assert "series" not in view["observations"] and "nested" not in view["observations"] and view["observations"]["benchmarksUsed"] == TECH["observations"]["benchmarksUsed"]
    assert "series" not in view["benchmarkSources"]["Nifty 50"] and "weights" not in view["shortTerm"]
    assert set(view["shortTerm"]["factors"][0]) == {"key", "label", "signal", "status", "detail"}


def test_snapshots_without_a_technical_assessment_still_work():
    older = {k: v for k, v in SNAPSHOT.items() if k != "technicalAssessment"}
    view = prism.reader_view(older)
    assert "technicalAssessment" not in view and view["rating"] == SNAPSHOT["rating"] and view["financialHistory"]
    for odd in (None, [], "x", 5):
        assert "technicalAssessment" not in prism.reader_view({**older, "technicalAssessment": odd})
    incomplete = prism.reader_view({**older, "technicalAssessment": {"status": "incomplete", "shortTerm": {"score": None, "factors": []}}})
    assert incomplete["technicalAssessment"] == {"status": "incomplete", "shortTerm": {"score": None, "factors": []}}


async def test_technical_assessment_is_served_stored_and_kept_whole_for_the_pdf(env):
    app, fake = env
    gold = await member(app, "gold")
    body = (await generate(gold)).json()
    assert body["technicalAssessment"] == prism.technical_view(TECH) and not SECRET_KEYS & keys_anywhere(body["technicalAssessment"])
    stored = json.loads((await app.state.store.pool.fetchrow("SELECT report FROM prism_reports WHERE symbol = 'TCS'"))["report"])
    assert stored["technicalAssessment"] == body["technicalAssessment"]
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS")).json()["technicalAssessment"] == body["technicalAssessment"]
    summary = (await gold.get("/api/prism/reports/latest?symbol=TCS&view=summary")).json()["summary"]
    assert "technicalAssessment" not in summary
    kept = json.loads(await app.state.store.redis.get(f"prism:snap:{body['id']}"))["snapshot"]
    assert kept["technicalAssessment"] == TECH and kept["technicalAssessment"]["inputHash"]      # the signed document is unchanged
    assert (await gold.get(f"/api/prism/reports/{body['id']}/pdf")).status_code == 200            # FakeSite compares it byte for byte with what it signed
    assert fake.pdfs


# ------------------------------------------------------------------ reuse, refresh and limits
async def test_stored_report_is_reused_for_six_hours_unless_refreshed(env):
    app, fake = env
    gold = await member(app, "gold")
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS")).json()["status"] == "none"
    first = (await generate(gold)).json()
    again = (await generate(await member(app, "gold"))).json()
    assert again["cached"] is True and again["id"] == first["id"] and len(fake.reports) == 1
    fresh = (await generate(gold, refresh=True)).json()
    assert fresh["cached"] is False and fresh["id"] != first["id"] and len(fake.reports) == 2
    latest = (await gold.get("/api/prism/reports/latest?symbol=tcs")).json()
    assert latest["id"] == fresh["id"] and latest["cached"] is True and latest["pdfAvailableUntil"]
    await app.state.store.pool.execute("UPDATE prism_reports SET generated_at = now() - interval '7 hours', pdf_until = now() - interval '6 hours'")
    old = (await gold.get("/api/prism/reports/latest?symbol=TCS")).json()
    assert old["pdfAvailableUntil"] is None                              # the snapshot of a stored report has expired
    assert (await generate(gold)).json()["cached"] is False and len(fake.reports) == 3
    standalone = (await gold.post("/api/prism/reports", json={"symbol": "TCS", "statement": "standalone"})).json()
    assert standalone["statementType"] == "standalone" and len(fake.reports) == 4


async def test_visitors_cannot_order_a_recalculation_of_a_fresh_showcase_report(env):
    app, fake = env
    visitor = client(app)
    await generate(visitor, "RELIANCE")
    assert (await generate(visitor, "RELIANCE", refresh=True)).json()["cached"] is True and len(fake.reports) == 1


async def test_daily_limit_counts_calculations_not_reuse_and_spares_administrators(env, monkeypatch):
    app, fake = env
    monkeypatch.setattr(prism, "DAILY_LIMIT", 2)
    gold = await member(app, "gold")
    assert (await generate(gold)).status_code == 200
    assert (await generate(gold)).json()["cached"] is True              # reuse does not count
    assert (await generate(gold, refresh=True)).status_code == 200
    r = await generate(gold, refresh=True)
    assert r.status_code == 429 and r.json()["status"] == "limit" and 0 < int(r.headers["retry-after"]) <= 86400
    assert (await generate(gold)).json()["cached"] is True              # stored reports stay open
    assert (await generate(await member(app, "gold"), refresh=True)).status_code == 200   # the limit is per member
    admin = await member(app, "gold", role="admin")
    for _ in range(3):
        assert (await generate(admin, refresh=True)).status_code == 200
    key = f"prism:day:{gold.user_id}:{datetime.now(prism.IST):%Y%m%d}"
    assert int(await app.state.store.redis.get(key)) == 2


async def test_failed_calculations_do_not_use_up_the_allowance(env, monkeypatch):
    app, fake = env
    monkeypatch.setattr(prism, "DAILY_LIMIT", 1)
    gold = await member(app, "gold")
    fake.answer = httpx.Response(502, json={"detail": "providers"})
    assert (await generate(gold)).status_code == 502
    fake.answer = None
    assert (await generate(gold)).status_code == 200


async def test_a_second_request_for_the_same_company_waits_for_the_first(env):
    app, fake = env
    fake.gate = asyncio.Event()
    a, b = await member(app, "gold"), await member(app, "gold")
    first = asyncio.create_task(generate(a))
    await asyncio.wait_for(fake.started.wait(), 5)
    second = asyncio.create_task(generate(b, refresh=True))
    await asyncio.sleep(0.2)
    assert not second.done()
    fake.gate.set()
    one, two = (await first).json(), (await second).json()
    assert len(fake.reports) == 1 and one["id"] == two["id"] and one["cached"] is False and two["cached"] is True


async def test_a_waiting_request_gets_the_same_failure(env):
    app, fake = env
    fake.gate, fake.answer = asyncio.Event(), httpx.Response(404, json={"detail": "No Indian listed equity was found for this query."})
    first = asyncio.create_task(generate(await member(app, "gold"), "NOPE"))
    await asyncio.wait_for(fake.started.wait(), 5)
    second = asyncio.create_task(generate(await member(app, "gold"), "NOPE"))
    await asyncio.sleep(0.1)
    fake.gate.set()
    assert [(await t).status_code for t in (first, second)] == [404, 404] and len(fake.reports) == 1


async def test_at_most_two_calculations_run_at_once(env):
    app, fake = env
    fake.gate = asyncio.Event()
    gold = await member(app, "gold")
    running = [asyncio.create_task(generate(gold, s)) for s in ("TCS", "INFY")]
    for _ in range(100):
        if len(fake.reports) == 2:
            break
        await asyncio.sleep(0.02)
    r = await generate(gold, "WIPRO")
    assert r.status_code == 429 and r.json()["status"] == "busy" and r.headers["retry-after"]
    fake.gate.set()
    assert [(await t).status_code for t in running] == [200, 200]


# ------------------------------------------------------------------ site backend errors
@pytest.mark.parametrize("answer, status, code", [
    (httpx.Response(404, json={"detail": "No Indian listed equity was found for this query."}), 404, "not_found"),
    (httpx.Response(422, json={"detail": "Several or partial company names match this search. Select the intended company symbol from the suggestions."}),
     422, "bad_request"),
    (httpx.Response(400, json={"detail": "Select a valid company symbol."}), 422, "bad_request"),
    (httpx.Response(429, json={"detail": "busy"}, headers={"Retry-After": "7"}), 429, "busy"),
    (httpx.Response(401, json={"detail": "Administrator session is invalid or expired."}), 503, "unavailable"),
    (httpx.Response(403, json={"detail": "no"}), 503, "unavailable"),
    (httpx.Response(500, text="boom"), 502, "unavailable"),
    (httpx.Response(502, json={"detail": "The financial data providers could not complete this report. Please retry."}), 502, "unavailable"),
    (httpx.Response(200, json={"id": "x", "state": "generating"}), 502, "unavailable"),
    (httpx.ReadTimeout("slow"), 502, "unavailable"),
    (httpx.ConnectError("down"), 502, "unavailable"),
])
async def test_site_backend_errors_are_mapped(env, answer, status, code, caplog):
    app, fake = env
    fake.answer = answer
    with caplog.at_level(logging.ERROR, logger="finlit.prism"):
        r = await generate(await member(app, "gold"))
    assert r.status_code == status and r.json()["status"] == code and r.headers["cache-control"] == "no-store"
    assert "boom" not in r.text and "providers" not in r.text            # upstream internals are not passed on
    if status == 429:
        assert r.headers["retry-after"] == "7"
    if status == 422:
        assert r.json()["detail"] == answer.json()["detail"]
    if status == 503:
        assert "CMS_JWT_SECRET" in caplog.text
    assert await app.state.store.pool.fetchval("SELECT count(*) FROM prism_reports") == 0


async def test_not_connected_without_the_shared_secret(store):  # noqa: F811
    app, fake = await make_app(store, cms_jwt_secret="short")
    async with app.router.lifespan_context(app):
        r = await generate(await member(app, "gold"))
        assert r.status_code == 503 and r.json()["status"] == "unavailable" and fake.reports == []


# ------------------------------------------------------------------ PDF
async def test_pdf_of_exactly_that_calculation(env):
    app, fake = env
    owner, other = await member(app, "gold"), await member(app, "gold")
    report = (await generate(owner)).json()
    r = await other.get(f"/api/prism/reports/{report['id']}/pdf")
    assert r.status_code == 200 and r.content == b"%PDF-1.4 prism" and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="FinLit-Prism-TCS-{report["id"][:8]}.pdf"'
    assert r.headers["cache-control"] == "no-store"
    assert fake.pdfs == [f"prism:{owner.user_id}"]                       # asked with the subject the snapshot was signed for
    assert (await (await member(app, "silver")).get(f"/api/prism/reports/{report['id']}/pdf")).status_code == 403


async def test_pdf_after_the_snapshot_is_gone_is_410_and_unknown_ids_404(env):
    app, fake = env
    gold = await member(app, "gold")
    report = (await generate(gold)).json()
    await app.state.store.redis.delete(f"prism:snap:{report['id']}")
    r = await gold.get(f"/api/prism/reports/{report['id']}/pdf")
    assert r.status_code == 410 and r.json()["status"] == "expired" and fake.pdfs == []
    assert (await gold.get(f"/api/prism/reports/{'b' * 32}/pdf")).status_code == 404
    assert (await gold.get("/api/prism/reports/not-an-id/pdf")).status_code == 404


async def test_pdf_refused_by_the_site_backend_as_changed_is_410(env):
    app, fake = env
    gold = await member(app, "gold")
    report = (await generate(gold)).json()
    fake.answer = httpx.Response(400, json={"detail": "This report is expired or has changed."})
    assert (await gold.get(f"/api/prism/reports/{report['id']}/pdf")).status_code == 410
    assert await app.state.store.redis.get(f"prism:snap:{report['id']}") is None


# ------------------------------------------------------------------ status
async def test_status_reports_connection_and_model_version(env):
    app, fake = env
    visitor = client(app)
    body = (await visitor.get("/api/prism/status")).json()
    assert body == {"name": "FinLit Prism", "available": True, "reason": None, "modelVersion": None}
    await generate(await member(app, "gold"))
    body = (await visitor.get("/api/prism/status")).json()
    assert body["modelVersion"] == "3.6.10" and fake.pings == 1            # the reachability check is remembered for a minute


async def test_status_when_unconfigured_or_unreachable(store):  # noqa: F811
    app, fake = await make_app(store, site_api_url="")
    async with app.router.lifespan_context(app):
        body = (await client(app).get("/api/prism/status")).json()
        assert body["available"] is False and body["reason"] == "not_configured" and fake.pings == 0
    app, _ = await make_app(store)

    def down(request):
        raise httpx.ConnectError("down")
    app.state.prism_client = httpx.AsyncClient(transport=httpx.MockTransport(down), base_url="http://site")
    async with app.router.lifespan_context(app):
        body = (await client(app).get("/api/prism/status")).json()
        assert body["available"] is False and body["reason"] == "not_reachable"


# ------------------------------------------------------------------ the generic site proxy
async def test_members_cannot_reach_premium_reports_through_the_site_proxy(env):
    """The catch-all forwards /api/premium-reports* like any site path, but without the member's session and with no token of ours, so the
    site backend's require_admin refuses it. Only administrators holding a CMS token get through, as before."""
    app, _ = env
    seen = []

    def site(request):
        seen.append(request)
        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer "):
            return httpx.Response(401, json={"detail": "Administrator authentication is required."})
        return httpx.Response(200, json={"ok": True})
    app.state.site_client = httpx.AsyncClient(transport=httpx.MockTransport(site), base_url="http://site")
    gold = await member(app, "gold")
    for path in ("/api/premium-reports", "/api/premium-reports/pdf"):
        r = await gold.post(path, json={"query": "TCS", "delivery": "inline"})
        assert r.status_code == 401
    assert all("authorization" not in s.headers and "cookie" not in s.headers for s in seen) and len(seen) == 2


# ------------------------------------------------------------------ stock page summary and the Technical part
async def test_summary_view_is_small_and_has_what_the_stock_page_needs(env):
    app, _ = env
    gold = await member(app, "gold")
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS&view=summary")).status_code == 404
    full = (await generate(gold)).json()
    r = await gold.get("/api/prism/reports/latest?symbol=TCS&view=summary")
    s = r.json()["summary"]
    assert list(r.json()) == ["summary"] and r.headers["cache-control"] == "no-store"
    assert set(s) == {"id", "final", "label", "status", "confidence", "parts", "partWeights", "generatedAt", "modelVersion", "topPros", "topCons"}
    assert s["id"] == full["id"] and s["final"] == full["rating"]["final"] and s["label"] == "AVERAGE" and s["status"] == "RATED"
    assert s["parts"] == SNAPSHOT["rating"]["parts"] and s["partWeights"] == SNAPSHOT["rating"]["partWeights"]
    assert len(s["topPros"]) == 2 and len(s["topCons"]) == 2 and all(isinstance(x, str) and x for x in s["topPros"] + s["topCons"])
    assert len(r.content) < len(json.dumps(full)) / 5
    assert (await gold.get("/api/prism/reports/latest?symbol=TCS&view=other")).status_code == 422
    assert (await client(app).get("/api/prism/reports/latest?symbol=TCS&view=summary")).status_code == 403


async def test_a_technical_part_passes_through_untouched(env):
    app, fake = env
    real = fake.snapshot

    def with_technical(sub, query, statement):
        snap = real(sub, query, statement)
        snap["rating"]["parts"]["technical"] = 61.5
        snap["rating"]["partWeights"]["technical"] = 0.1
        return snap
    fake.snapshot = with_technical
    gold = await member(app, "gold")
    report = (await generate(gold)).json()
    assert report["rating"]["parts"]["technical"] == 61.5 and report["rating"]["partWeights"]["technical"] == 0.1
    s = (await gold.get("/api/prism/reports/latest?symbol=TCS&view=summary")).json()["summary"]
    assert s["parts"]["technical"] == 61.5 and s["partWeights"]["technical"] == 0.1


# ------------------------------------------------------------------ review fixes (docs/prism/REVIEW.md)
async def test_only_gold_and_administrators_may_force_a_recalculation(env):
    app, fake = env
    basic = await member(app, "basic")
    assert (await generate(basic, "RELIANCE")).status_code == 200            # the showcase company is open
    r = await generate(basic, "RELIANCE", refresh=True)
    assert r.status_code == 403 and r.json()["status"] == "plan_required" and len(fake.reports) == 1
    assert (await generate(await member(app, "gold"), "RELIANCE", refresh=True)).status_code == 200


async def test_not_rated_summary_withholds_category_scores(env):
    app, fake = env
    real = fake.snapshot

    def not_rated(sub, query, statement):
        snap = real(sub, query, statement)
        snap["rating"].update(final=None, label="NOT RATED", status="NOT RATED")
        return snap
    fake.snapshot = not_rated
    gold = await member(app, "gold")
    await generate(gold)
    s = (await gold.get("/api/prism/reports/latest?symbol=TCS&view=summary")).json()["summary"]
    assert s["status"] == "NOT RATED" and s["final"] is None and s["parts"] is None


async def test_pdf_downloads_are_rate_limited_and_ids_must_be_exactly_32_hex(env, monkeypatch):
    app, fake = env
    monkeypatch.setattr(prism, "PDF_LIMIT", 2)
    gold = await member(app, "gold")
    rid = (await generate(gold)).json()["id"]
    assert [(await gold.get(f"/api/prism/reports/{rid}/pdf")).status_code for _ in range(2)] == [200, 200]
    r = await gold.get(f"/api/prism/reports/{rid}/pdf")
    assert r.status_code == 429 and r.json()["status"] == "limit" and r.headers["retry-after"]
    assert (await (await member(app, "gold")).get(f"/api/prism/reports/{rid}%0A/pdf")).status_code == 404


async def test_nightly_precompute_stores_ratings_in_order_and_stops_when_the_provider_is_down(store):  # noqa: F811
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
        await conn.execute("DELETE FROM snapshots WHERE symbol IN ('PZA', 'PZB')")
        for sym in ("PZA", "PZB"):
            await conn.execute("INSERT INTO snapshots (symbol, statement, section, body, etag, generated_at) VALUES ($1, 'consolidated', 'price-MAX', '{}', 'x', now())", sym)
    settings = make_settings(site_api_url="http://site", cms_jwt_secret=SECRET)
    fake = FakeSite()
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake), base_url="http://site")
    out = await prism.precompute(store, settings, limit=10, client=http)
    assert out["calculated"] >= 2 and out["failed"] == []
    rows = {r["symbol"] for r in await store.pool.fetch("SELECT symbol FROM prism_reports")}
    assert {"PZA", "PZB"} <= rows
    assert all(r["sub"] == "prism:nightly" for r in fake.reports)
    again = await prism.precompute(store, settings, limit=10, client=http)      # fresh ratings are left alone
    assert again["calculated"] == 0
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM prism_reports")
    fake.answer = httpx.Response(503, json={"detail": "down"})
    down = await prism.precompute(store, settings, limit=10, client=http)
    assert down["calculated"] == 0 and 0 < len(down["failed"]) <= 3     # stops after three failures in a row
    async with store.pool.acquire() as conn:
        await conn.execute("DELETE FROM snapshots WHERE symbol IN ('PZA', 'PZB')")
