import asyncio
import json
from types import SimpleNamespace

import httpx
from fastapi import FastAPI

from finlit import premium


class FakeRedis:
    def __init__(self): self.d = {}
    async def get(self, k): return self.d.get(k)
    async def set(self, k, v, nx=False, ex=None):
        if nx and k in self.d: return None
        self.d[k] = v; return True
    async def delete(self, k): self.d.pop(k, None)
    async def exists(self, k): return k in self.d


def make(handler):
    app = FastAPI()
    app.include_router(premium.router)
    app.state.store = SimpleNamespace(redis=FakeRedis())
    app.state.settings = SimpleNamespace(site_api_url="http://site", cms_jwt_secret="s" * 40)
    app.state.premium_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://site")
    app.dependency_overrides[premium.premium_ctx] = lambda: SimpleNamespace(role="investor", plan="gold")
    return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_second_call_is_served_from_the_saved_copy_and_token_is_sent():
    calls = []
    def up(request):
        calls.append(request); return httpx.Response(200, json={"items": [1]})
    app, c = make(up)
    a = await c.get("/api/premium/markets/ipo")
    b = await c.get("/api/premium/markets/ipo")
    assert a.headers["x-cache"] == "miss" and b.headers["x-cache"] == "hit" and b.json() == {"items": [1]}
    assert len(calls) == 1 and calls[0].headers["authorization"].startswith("Bearer ey")


async def test_stale_copy_is_served_at_once_and_refreshed_behind():
    n = {"i": 0}
    def up(request):
        n["i"] += 1; return httpx.Response(200, json={"v": n["i"]})
    app, c = make(up)
    await c.get("/api/premium/markets/results")
    key = next(iter(app.state.store.redis.d))
    hit = json.loads(app.state.store.redis.d[key]); hit["t"] -= 10_000; app.state.store.redis.d[key] = json.dumps(hit)
    r = await c.get("/api/premium/markets/results")
    assert r.headers["x-cache"] == "stale" and r.json() == {"v": 1}
    await asyncio.sleep(0.05)
    assert (await c.get("/api/premium/markets/results")).json() == {"v": 2}


async def test_bad_input_is_rejected_before_any_upstream_call():
    def up(request): raise AssertionError("must not call upstream")
    app, c = make(up)
    assert (await c.get("/api/premium/markets/nope")).status_code == 404
    assert (await c.get("/api/premium/markets/ipo?from_date=yesterday")).status_code == 400
    assert (await c.get("/api/premium/commodities/abc")).status_code == 400
    assert (await c.get("/api/premium/markets/announcements?symbol=a;b")).status_code == 422
    assert (await c.get("/api/premium/fundamentals/browse?group=x&value=y")).status_code == 422


async def test_provider_failure_without_a_saved_copy_is_a_friendly_502():
    app, c = make(lambda r: httpx.Response(502, json={"detail": "bad"}))
    r = await c.get("/api/premium/commodities")
    assert r.status_code == 502


async def test_basic_member_is_refused_by_the_real_gate():
    from finlit import premium as p
    ctx = SimpleNamespace(role="investor", plan="basic")
    try:
        await p.premium_ctx(None, ctx)
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 403
    else:
        raise AssertionError("basic must be refused")


async def test_provider_auth_error_is_not_passed_on_as_a_sign_in_problem():
    app, c = make(lambda r: httpx.Response(401, json={"detail": "FinEdge key rejected"}))
    assert (await c.get("/api/premium/fundamentals?query=RELIANCE")).status_code == 502
