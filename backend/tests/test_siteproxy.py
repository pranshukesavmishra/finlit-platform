import httpx
import pytest
from fastapi import FastAPI

from finlit.api import BodyLimitMiddleware
from finlit.siteproxy import register_catch_all, register_stock_admin


def make_app(handler):
    app = FastAPI()
    app.state.site_client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://site")
    register_stock_admin(app, "http://site")

    @app.get("/api/stocks/{symbol}/{section}")  # a research route that would otherwise capture /api/stocks/admin/...
    async def research(symbol: str, section: str):
        return {"research": True}

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    register_catch_all(app, "http://site")
    return app


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def test_unowned_api_paths_are_forwarded_with_method_query_body_and_auth_only():
    seen = {}

    def upstream(request: httpx.Request):
        seen.update(method=request.method, url=str(request.url), auth=request.headers.get("authorization"), cookie=request.headers.get("cookie"),
                    body=request.content, ctype=request.headers.get("content-type"))
        return httpx.Response(201, json={"id": 1}, headers={"x-extra": "kept", "access-control-allow-origin": "*", "content-length": "999"})

    r = await client(make_app(upstream)).post("/api/content/admin/items?x=1", json={"a": 1}, headers={"Authorization": "Bearer t", "Cookie": "session=secret"})
    assert r.status_code == 201 and r.json() == {"id": 1} and r.headers["x-extra"] == "kept"
    assert "access-control-allow-origin" not in r.headers  # the site backend's CORS must not leak through this origin
    assert seen["method"] == "POST" and seen["url"] == "http://site/api/content/admin/items?x=1"
    assert seen["auth"] == "Bearer t" and seen["cookie"] is None  # CMS token goes through, the research session cookie does not
    assert seen["body"] == b'{"a":1}' and seen["ctype"] == "application/json"


async def test_research_routes_win_but_stocks_admin_goes_to_the_site_backend():
    def upstream(request: httpx.Request):
        return httpx.Response(200, json={"site": request.url.path})

    c = client(make_app(upstream))
    assert (await c.get("/api/stocks/TCS/summary")).json() == {"research": True}
    assert (await c.get("/api/health")).json() == {"ok": True}
    assert (await c.get("/api/stocks/admin/fundamentals")).json() == {"site": "/api/stocks/admin/fundamentals"}
    assert (await c.get("/api/portfolio/report")).json() == {"site": "/api/portfolio/report"}


async def test_sleeping_site_backend_gives_a_clean_502():
    def upstream(request: httpx.Request):
        raise httpx.ConnectError("down")

    r = await client(make_app(upstream)).get("/api/content")
    assert r.status_code == 502 and r.json()["status"] == "site_unavailable" and r.headers["retry-after"] == "5"


async def test_upstream_errors_pass_through_unchanged():
    r = await client(make_app(lambda req: httpx.Response(401, json={"detail": "Administrator authentication is required."}))).get("/api/content/admin/items")
    assert r.status_code == 401 and r.json()["detail"].startswith("Administrator")


async def test_only_the_admin_upload_paths_may_exceed_the_small_body_limit():
    app = make_app(lambda req: httpx.Response(200, json={"ok": True}))
    app.add_middleware(BodyLimitMiddleware)
    c = client(app)
    big = b"x" * (200 * 1024)
    token = {"Authorization": "Bearer t"}
    assert (await c.post("/api/content/admin/upload", content=big, headers=token)).status_code == 200
    assert (await c.post("/api/content/admin/upload", content=big)).status_code == 413          # no token: the small limit applies
    assert (await c.post("/api/contact", content=big)).status_code == 413
    assert (await c.request("GET", "/api/content", content=big)).status_code == 413              # a body on a GET is limited too
    assert (await c.post("/api/content/admin/upload", content=b"x" * (17 * 1024 * 1024), headers=token)).status_code == 413


async def test_the_site_backends_password_only_cms_sign_in_is_never_forwarded():
    calls = []

    def upstream(request: httpx.Request):
        calls.append(request.url.path)
        return httpx.Response(200, json={"token": "would-skip-the-authenticator"})

    c = client(make_app(upstream))
    for path in ("/api/content/admin/login", "/api/content/admin/login/", "/api/Content/Admin/Login", "/api/content/admin/./login",
                 "/api/content/x/../admin/login", "/api/content//admin/login", "/api/stocks/admin/../../content/admin/login"):
        r = await c.post(path, json={"email": "a@b.c", "password": "x"})
        assert r.status_code == 404 and "token" not in r.json(), path
    assert calls == []
    assert (await c.get("/api/content/admin/items")).status_code == 200   # the rest of the CMS (token-protected upstream) still goes through
