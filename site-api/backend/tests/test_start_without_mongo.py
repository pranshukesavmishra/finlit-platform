"""The site backend starts and serves FinLit Prism without MongoDB (MONGO_URL unset), as deploy/render-start.sh runs it when
only the Prism prerequisites are configured. Database routes must answer 503 at once, never hang on a server-selection timeout.

Runs in a fresh interpreter: conftest.py sets MONGO_URL for every other test, and the database client is created at import."""
import json
import os
import subprocess
import sys
from pathlib import Path

SITE_API = Path(__file__).resolve().parents[2]

SCRIPT = r'''
import asyncio, json, time
from copy import deepcopy
from backend import server, premium_service
from backend.tests.test_premium_reports import sample_report

example = json.load(open("backend/tests/premium_example.json"))
report = sample_report(example)
premium_service.generate_report = lambda *a: deepcopy(report)          # no provider calls
server._resolve_finedge_stock = lambda q: {"symbol": "EXAMPLE", "name": "Sample Engineering Ltd"}
import jwt
now = int(time.time())  # the research API's token shape (docs/prism/CONTRACT.md)
token = jwt.encode({"sub": "prism:test", "role": "admin", "iat": now, "exp": now + 300}, server.token_secret(), algorithm="HS256")
auth = {"authorization": "Bearer " + token}


async def startup(app):
    """Run the ASGI lifespan startup (the on_event("startup") hooks) as uvicorn does, and return the answer."""
    sent, done = [], asyncio.Event()
    async def receive():
        if not sent:
            return {"type": "lifespan.startup"}
        await asyncio.Event().wait()
    async def send(message):
        sent.append(message["type"])
        done.set()
    task = asyncio.create_task(app({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, receive, send))
    await asyncio.wait_for(done.wait(), 5)
    return sent[0], task


async def request(method, path, payload=None, headers=None):
    body = json.dumps(payload).encode() if payload is not None else b""
    messages, sent = [], False
    finished = asyncio.Event()
    async def receive():
        nonlocal sent
        if sent:
            await finished.wait()
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    async def send(message):
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body", False):
            finished.set()
    hdrs = {"host": "localhost", "content-type": "application/json", **(headers or {})}
    started = time.monotonic()
    await server.app({"type": "http", "http_version": "1.1", "method": method, "path": path, "raw_path": path.encode(),
                      "query_string": b"", "headers": [(k.encode(), v.encode()) for k, v in hdrs.items()], "scheme": "http",
                      "server": ("localhost", 80), "client": ("127.0.0.1", 123), "root_path": ""}, receive, send)
    start = next(m for m in messages if m["type"] == "http.response.start")
    raw = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    try:
        data = json.loads(raw)
    except ValueError:
        data = {"bytes": len(raw), "pdf": raw.startswith(b"%PDF")}
    headers = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return {"status": start["status"], "data": data, "headers": headers, "seconds": time.monotonic() - started}


async def main():
    out = {"dbType": type(server.db).__name__}
    out["startup"], task = await startup(server.app)
    out["root"] = await request("GET", "/api/")
    out["content"] = await request("GET", "/api/content")
    out["contentItem"] = await request("GET", "/api/content/some-article")
    out["portfolio"] = await request("GET", "/api/portfolio/report")
    out["contact"] = await request("POST", "/api/contact", {"name": "Asha Rao", "email": "a@example.com", "message": "Hello there, a test message."})
    out["adminItems"] = await request("GET", "/api/content/admin/items", headers=auth)
    gen = await request("POST", "/api/premium-reports", {"query": "EXAMPLE", "delivery": "inline"}, auth)
    snap = gen.pop("data")
    out["generate"] = {**gen, "state": snap.get("state"), "hasReceipt": bool(snap.get("snapshotReceipt"))}
    receipt = snap.pop("snapshotReceipt", "")
    out["pdf"] = await request("POST", "/api/premium-reports/pdf", {"report": snap, "receipt": receipt}, auth)
    task.cancel()
    print("RESULT " + json.dumps(out, default=str))

asyncio.run(main())
'''


def test_site_backend_starts_and_serves_prism_without_mongo():
    env = {k: v for k, v in os.environ.items() if k not in ("MONGO_URL", "DB_NAME")}
    env.update(PYTHONPATH=os.pathsep.join([str(SITE_API), str(SITE_API / "backend")]),
               CMS_JWT_SECRET="test-only-jwt-secret-with-more-than-32-bytes", FINEDGE_API_KEY="", UPSTOX_ACCESS_TOKEN="",
               RESEND_API_KEY="", HTTPS_PROXY="http://127.0.0.1:9", HTTP_PROXY="http://127.0.0.1:9")  # any provider call fails fast
    run = subprocess.run([sys.executable, "-c", SCRIPT], cwd=SITE_API, env=env, capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, run.stderr[-3000:]
    line = next(line for line in run.stdout.splitlines() if line.startswith("RESULT "))
    out = json.loads(line[len("RESULT "):])
    assert "MONGO_URL is not set" in run.stderr
    assert out["dbType"] == "_UnconfiguredDatabase"
    assert out["startup"] == "lifespan.startup.complete"
    assert out["root"]["status"] == 200
    # The public blog index keeps its empty state; the portfolio page shows the report shipped with the code.
    assert out["content"]["status"] == 200 and out["content"]["data"] == []
    assert out["content"]["headers"].get("x-cms-content-store") == "unavailable"
    assert out["portfolio"]["status"] == 200 and out["portfolio"]["data"]
    # Everything else that needs MongoDB fails fast and clearly.
    for key in ("contentItem", "contact", "adminItems"):
        assert out[key]["status"] == 503, (key, out[key])
        assert "not connected" in out[key]["data"]["detail"]
        assert out[key]["seconds"] < 1.0
    # FinLit Prism: inline generation and the signed-snapshot PDF.
    assert out["generate"]["status"] == 200 and out["generate"]["state"] == "ready" and out["generate"]["hasReceipt"]
    assert out["pdf"]["status"] == 200 and out["pdf"]["data"]["pdf"]


def test_unreachable_mongo_is_a_503_not_a_500(monkeypatch):
    from pymongo.errors import ServerSelectionTimeoutError
    from backend import server
    from backend.tests.test_premium_reports import asgi_request

    class Unreachable:
        def __getattr__(self, name):
            async def fail(*_a, **_k):
                raise ServerSelectionTimeoutError("test-mongo.invalid:27017: timed out")
            return type("Collection", (), {"find_one": staticmethod(fail)})()

    monkeypatch.setattr(server, "db", Unreachable())
    status, body = asgi_request(server.app, "GET", "/api/content/some-article")
    assert status == 503 and "temporarily unavailable" in body["detail"] and "test-mongo" not in str(body)


def test_generation_slots_setting(monkeypatch):
    from backend import server
    for raw, expected in (("", 2), ("1", 1), ("9", 4), ("0", 1), ("two", 2)):
        monkeypatch.setenv("PREMIUM_GENERATION_SLOTS", raw)
        assert server._generation_slots_setting() == expected


def test_fundamentals_cache_is_bounded_and_drops_expired_entries_first(monkeypatch):
    from backend import server
    cache = {}
    monkeypatch.setattr(server, "_stock_fundamentals_cache", cache)
    monkeypatch.setattr(server, "STOCK_FUNDAMENTALS_CACHE_ENTRIES", 4)
    now = server.monotonic()
    cache["old"] = {"fetched_at": now - server.STOCK_FUNDAMENTALS_CACHE_SECONDS - 1}
    for i in range(6):
        server._remember_stock_fundamentals(f"k{i}", {"fetched_at": now})
    assert list(cache) == ["k2", "k3", "k4", "k5"]
    server._remember_stock_fundamentals("k3", {"fetched_at": now + 1})  # a refresh moves to the newest place
    assert list(cache) == ["k2", "k4", "k5", "k3"] and cache["k3"]["fetched_at"] == now + 1
