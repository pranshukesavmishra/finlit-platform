"""Forwards the site backend's routes (blog and CMS, portfolio report, contact and enquiry forms, FinLit AI chat, market ticker)
to the separate site service, so the browser keeps talking to one address.

Set SITE_API_URL to that service (for example https://finlit-site-api.onrender.com). Everything under /api that this
research API does not own is forwarded as is: method, query, body, and the headers the site backend uses (Authorization for the
CMS login, Content-Type for forms and uploads). Cookies are not forwarded; the site backend does not use them.
"""

from __future__ import annotations

import logging
import posixpath

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

log = logging.getLogger("finlit.siteproxy")

FORWARD_REQUEST_HEADERS = {"authorization", "content-type", "accept", "accept-language", "user-agent", "cache-control", "pragma", "if-none-match", "range"}
SKIP_RESPONSE_HEADERS = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive", "server", "date",
                         "strict-transport-security", "access-control-allow-origin", "access-control-allow-credentials", "vary"}
METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]


def _client(app: FastAPI, base_url: str) -> httpx.AsyncClient:
    client = getattr(app.state, "site_client", None)
    if client is None:
        client = app.state.site_client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(75.0, connect=15.0),
                                                           limits=httpx.Limits(max_connections=40), follow_redirects=False)
    return client


def _clean(path: str) -> bool:
    """A path the site backend will read the same way it is checked here: no dot segments, no doubled slashes, no backslashes
    (the HTTP client resolves "./" and "../" before sending, so "/api/content/admin/./login" would otherwise slip past BLOCKED_PATHS)."""
    return "//" not in path and "\\" not in path and posixpath.normpath(path) == path.rstrip("/")


def _blocked(path: str) -> bool:
    return not _clean(path) or path.rstrip("/").lower() in BLOCKED_PATHS


async def forward(request: Request, base_url: str) -> Response:
    if _blocked(request.url.path):
        return _not_found()
    headers = {k: v for k, v in request.headers.items() if k.lower() in FORWARD_REQUEST_HEADERS}
    headers = {k: v for k, v in headers.items() if v.strip() and v.strip().lower() != "bearer"}  # blank Authorization -> 401 upstream, not a 502
    headers["accept-encoding"] = "identity"
    ip = (request.scope.get("state") or {}).get("client_ip")
    if ip:
        headers["x-forwarded-for"] = ip
    headers["x-forwarded-proto"] = request.headers.get("x-forwarded-proto", request.url.scheme)
    body = await request.body()
    try:
        upstream = await _client(request.app, base_url).request(request.method, request.url.path + (f"?{request.url.query}" if request.url.query else ""),
                                                                headers=headers, content=body or None)
    except httpx.HTTPError as exc:
        log.warning("site backend unreachable: %s", type(exc).__name__)
        return JSONResponse({"status": "site_unavailable", "detail": "This part of the site is waking up. Please try again in a moment."},
                            status_code=502, headers={"Cache-Control": "no-store", "Retry-After": "5"})
    out = {k: v for k, v in upstream.headers.items() if k.lower() not in SKIP_RESPONSE_HEADERS}
    return Response(content=upstream.content, status_code=upstream.status_code, headers=out)


def register_stock_admin(app: FastAPI, base_url: str) -> None:
    """/api/stocks/admin/* belongs to the site backend (CMS fundamentals tools) but would otherwise match the research API's
    /api/stocks/{symbol}/{section}. Call this BEFORE the research routes are added."""
    @app.api_route("/api/stocks/admin/{rest:path}", methods=METHODS, include_in_schema=False)
    async def stock_admin(rest: str, request: Request):
        return await forward(request, base_url)


# Never forwarded: the site backend's own password-only CMS sign-in. Administrators get CMS tokens from POST /api/me/cms-token,
# which needs their authenticator code; forwarding this would offer a way into the content tools without it.
BLOCKED_PATHS = {"/api/content/admin/login"}


def register_catch_all(app: FastAPI, base_url: str) -> None:
    """Every other /api path the research API does not answer goes to the site backend. Call this AFTER all research routes."""
    @app.api_route("/api/{rest:path}", methods=METHODS, include_in_schema=False)
    async def site_api(rest: str, request: Request):
        return await forward(request, base_url)


def _not_found() -> Response:
    return JSONResponse({"status": "not_found", "detail": "Sign in on the website: administrators reach the content tools from their account."},
                        status_code=404, headers={"Cache-Control": "no-store"})
