"""POST /mcp: the Streamable HTTP endpoint (stateless, JSON replies), its safeguards, the discovery file and the admin call counter."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse, Response

from ..auth.routes import Ctx, admin_ctx
from ..security import client_ip
from . import protocol
from .gateway import Gateway, ToolError
from .protocol import RpcError
from .schema import ArgError, validate
from .tools import BY_NAME, DISCLAIMER, TOOLS, Out

log = logging.getLogger("finlit.mcp")
router = APIRouter()
admin = APIRouter(prefix="/api/admin")
IST = ZoneInfo("Asia/Kolkata")
NO_STORE = {"Cache-Control": "no-store"}
COUNTER_DAYS = 45


def _int_env(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def enabled() -> bool:
    return os.getenv("MCP_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def limits() -> Dict[str, int]:
    return {"per_minute": _int_env("MCP_RATE_PER_MINUTE", 60), "daily": _int_env("MCP_DAILY_CAP", 1000),
            "max_body": _int_env("MCP_MAX_BODY_BYTES", 32 * 1024), "max_result": _int_env("MCP_MAX_RESULT_BYTES", 100_000)}


def tools_listing() -> List[Dict[str, Any]]:
    return [t.listing() for t in TOOLS]


# ------------------------------------------------------------------------------------------------------------- results
def _compact(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False, default=str)


def _lists(node: Any, path: tuple, found: List[tuple]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            _lists(v, path + (k,), found)
    elif isinstance(node, list):
        if len(node) > 1:
            found.append((len(_compact(node)), path, node))
        for i, v in enumerate(node[:3]):
            _lists(v, path + (i,), found)


def shrink(env: Dict[str, Any], cap: int) -> Dict[str, Any]:
    """Keeps a result under `cap` bytes by halving its biggest list (the newest entries for price and flow series, the first for ranked lists), and says so."""
    cuts: List[str] = []
    for _ in range(40):
        if len(_compact(env)) <= cap:
            break
        found: List[tuple] = []
        _lists(env["data"], (), found)
        if not found:
            break
        _, path, lst = max(found, key=lambda x: x[0])
        keep = max(1, len(lst) // 2)
        newest_last = path and path[-1] in ("prices", "days", "periods", "series")
        new = lst[-keep:] if newest_last else lst[:keep]
        parent: Any = env["data"]
        for p in path[:-1]:
            parent = parent[p]
        parent[path[-1]] = new
        cuts.append(f"{'.'.join(str(p) for p in path)}: {len(lst)} -> {keep}")
    if cuts:
        env["truncated"] = True
        env["notes"].append("The result was too large, so long lists were cut (" + "; ".join(cuts[:6]) + "). Ask for a narrower request to see the rest.")
    return env


def envelope(name: str, out: Out, extra_notes: List[str], cap: int) -> Dict[str, Any]:
    env: Dict[str, Any] = {"tool": name, "data": out.data, "source": out.source, "asOf": out.as_of, "disclaimer": DISCLAIMER,
                           "routes": out.routes, "notes": [n for n in [*extra_notes, *out.notes] if n], "truncated": False}
    if out.as_of is None:
        env["notes"].append("The date of this data is not available.")
    return shrink(env, cap)


def error_result(message: str) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


async def count_call(request: Request, name: str, ok: bool) -> None:
    try:
        redis = request.app.state.store.redis
        key = f"mcp:calls:{datetime.now(IST).date().isoformat()}"
        async with redis.pipeline(transaction=False) as pipe:
            pipe.hincrby(key, name if ok else f"{name}:error", 1)
            pipe.expire(key, COUNTER_DAYS * 86400)
            await pipe.execute()
    except Exception:   # nosec B110 - a counter must never break an answer
        pass


async def run_tool(request: Request, gw: Gateway, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    tool = BY_NAME.get(name)
    if tool is None:
        raise RpcError(protocol.INVALID_PARAMS, f"Unknown tool: {name[:60]}")
    try:
        clean, notes = validate(args, tool.listing()["inputSchema"])
        out = await tool.handler(gw, clean)
        env = envelope(name, out, notes, limits()["max_result"])
    except ArgError as e:
        await count_call(request, name, False)
        return error_result(f"Invalid arguments: {e}")
    except ToolError as e:
        await count_call(request, name, False)
        return error_result(str(e))
    except Exception:
        log.exception("mcp tool %s failed", name)
        await count_call(request, name, False)
        return error_result("Something went wrong while fetching this data. Please try again.")
    await count_call(request, name, True)
    return {"content": [{"type": "text", "text": _compact(env)}], "structuredContent": env, "isError": False}


# ------------------------------------------------------------------------------------------------------------- safeguards
def origin_allowed(request: Request) -> bool:
    """MCP's DNS-rebinding rule: a request that names an Origin must come from a host this site answers to. No Origin (a command-line or server client) is fine."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    st = request.app.state.settings
    hosts = [h.lower() for h in st.allowed_hosts]
    if "*" in hosts:
        return True
    if origin.rstrip("/") in [o.rstrip("/") for o in st.cors_origins]:
        return True
    host = (urlparse(origin).hostname or "").lower()
    return bool(host) and any(host == h.split(":")[0] or (h.startswith("*.") and host.endswith(h[1:])) for h in hosts)


def _fail(status: int, code: int, message: str, headers: Optional[Dict[str, str]] = None) -> JSONResponse:
    return JSONResponse(protocol.error_response(None, code, message), status_code=status, headers={**NO_STORE, **(headers or {})})


async def _rate_limit(request: Request, ip: str, messages: int, calls: int) -> Optional[JSONResponse]:
    lim, limiter = limits(), request.app.state.limiter
    for _ in range(max(1, messages)):
        ok, retry = await limiter.hit("mcp", ip, lim["per_minute"], 60)
        if not ok:
            return _fail(429, -32000, "Rate limit reached: too many requests per minute. Please slow down.", {"Retry-After": str(max(1, retry))})
    for _ in range(calls):
        ok, retry = await limiter.hit("mcpday", ip, lim["daily"], 86400)
        if not ok:
            return _fail(429, -32000, "The daily limit for this server was reached for your address. Please try again tomorrow.", {"Retry-After": str(max(60, retry))})
    return None


@router.post("/mcp", include_in_schema=False)
async def mcp_post(request: Request):
    if not enabled():
        return Response(status_code=404, headers=NO_STORE)
    if not origin_allowed(request):
        return _fail(403, -32000, "Origin not allowed.")
    if "json" not in (request.headers.get("content-type") or "").lower():
        return _fail(415, protocol.INVALID_REQUEST, "Content-Type must be application/json.")
    accept = (request.headers.get("accept") or "").lower()
    if accept and not any(x in accept for x in ("application/json", "*/*", "application/*")):
        return _fail(406, protocol.INVALID_REQUEST, "Accept must allow application/json.")
    ver = request.headers.get("mcp-protocol-version")
    if ver and ver not in protocol.SUPPORTED_VERSIONS:
        return _fail(400, protocol.INVALID_REQUEST, f"Unsupported MCP-Protocol-Version. Supported: {', '.join(protocol.SUPPORTED_VERSIONS)}.")
    lim = limits()
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > lim["max_body"]:
        return _fail(413, protocol.INVALID_REQUEST, "Request is too large.")
    raw = await request.body()
    if len(raw) > lim["max_body"]:
        return _fail(413, protocol.INVALID_REQUEST, "Request is too large.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _fail(400, protocol.PARSE_ERROR, "Parse error: the body is not valid JSON.")
    batch = isinstance(payload, list)
    messages = payload if batch else [payload]
    if batch and not messages:
        return _fail(400, protocol.INVALID_REQUEST, "Invalid Request: empty batch.")
    if len(messages) > protocol.MAX_BATCH:
        return _fail(400, protocol.INVALID_REQUEST, f"Invalid Request: at most {protocol.MAX_BATCH} messages in a batch.")
    ip = request.scope.get("state", {}).get("client_ip") or client_ip(request.scope, request.app.state.settings.client_ip_header)
    calls = sum(1 for m in messages if isinstance(m, dict) and m.get("method") == "tools/call")
    limited = await _rate_limit(request, ip, len(messages), calls)
    if limited:
        return limited
    gw = Gateway(request.app, request.headers.get("host", "localhost"), ip)

    async def call(name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        return await run_tool(request, gw, name, args)

    try:
        replies = []
        for m in messages:
            r = await protocol.handle_one(m, tools_listing, call)
            if r is not None:
                replies.append(r)
    finally:
        await gw.aclose()
    if not replies:
        return Response(status_code=202, headers=NO_STORE)
    body = replies if batch else replies[0]
    return Response(content=_compact(body), media_type="application/json", headers=NO_STORE)


@router.api_route("/mcp", methods=["GET", "PUT", "PATCH", "DELETE", "HEAD"], include_in_schema=False)
async def mcp_other(request: Request):
    if not enabled():
        return Response(status_code=404, headers=NO_STORE)
    dist = request.app.state.settings.frontend_dist
    if request.method in ("GET", "HEAD") and "text/html" in (request.headers.get("accept") or "") and dist:
        # A person opening the address in a browser gets the "Connect AI assistants" page; MCP clients send Accept: text/event-stream or application/json.
        from ..web import SITE_HEADERS
        index = os.path.join(dist, "index.html")
        if os.path.isfile(index):
            resp = FileResponse(index)
            resp.headers["Cache-Control"] = "no-cache"
            for k, v in SITE_HEADERS.items():
                resp.headers[k] = v
            return resp
    return JSONResponse(protocol.error_response(None, -32000, "Method not allowed: this server answers POST requests only (no sessions, no event stream)."),
                        status_code=405, headers={**NO_STORE, "Allow": "POST"})


@router.get("/.well-known/mcp.json", include_in_schema=False)
async def well_known(request: Request):
    if not enabled():
        return Response(status_code=404, headers=NO_STORE)
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    base = f"{proto}://{request.headers.get('host') or request.url.netloc}"
    body = {"name": protocol.SERVER_NAME, "title": "FinLit Indian stock data", "version": protocol.SERVER_VERSION,
            "description": "Free, read-only Indian stock, fund and market data for AI assistants. Describes financial health from filings and prices; not a recommendation.",
            "transport": "streamable-http", "endpoint": f"{base}/mcp", "protocolVersions": list(protocol.SUPPORTED_VERSIONS),
            "tools": len(TOOLS), "toolNames": [t.name for t in TOOLS], "authentication": "none", "readOnly": True,
            "documentation": f"{base}/mcp", "disclaimer": DISCLAIMER}
    return JSONResponse(body, headers={"Cache-Control": "public, max-age=300"})


@admin.get("/mcp-stats")
async def mcp_stats(request: Request, days: int = 7, ctx: Ctx = Depends(admin_ctx)):
    """Calls per tool per day (India dates), newest first. Fields ending :error count calls that came back as errors."""
    days = max(1, min(days, COUNTER_DAYS))
    redis, out = request.app.state.store.redis, {}
    today = datetime.now(IST).date()
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        raw = await redis.hgetall(f"mcp:calls:{d}")
        out[d] = {(k.decode() if isinstance(k, bytes) else k): int(v) for k, v in sorted(raw.items())}
    return JSONResponse({"enabled": enabled(), "limits": limits(), "days": out, "updatedAt": int(time.time())}, headers=NO_STORE)
