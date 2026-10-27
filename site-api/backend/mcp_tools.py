"""FinLit AI chat: the FinLit data tools, reached through the research API's MCP endpoint (tools/list and tools/call over HTTP).

The tool list is fetched from the endpoint and kept ten minutes, so the chatbot and the public MCP server can never disagree about what exists.
If the endpoint is unreachable the chat works as before, without tools. Nothing here logs question text, tool arguments or results."""

from __future__ import annotations

import json
import logging
import os
import threading
from time import monotonic
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("finlit.chat.tools")

DEFAULT_URL = "http://127.0.0.1:8000/mcp"
CACHE_SECONDS = 600
RETRY_AFTER_FAILURE_SECONDS = 60
LIST_TIMEOUT = (2.0, 6.0)          # connect, read (seconds)
CALL_TIMEOUT = (2.0, 20.0)
MAX_TOOL_ROUNDS = 4                # model -> tools -> model, at most this many times per question
MAX_CALLS_PER_ROUND = 4
MAX_RESULT_CHARS = 24_000          # what one tool result may add to the model's context
_lock = threading.Lock()
_cache: Dict[str, Any] = {"at": 0.0, "tools": [], "failed_at": None, "url": None}


def endpoint() -> str:
    """MCP_INTERNAL_URL, default the research API on this machine. Empty or 'off' switches the tools off."""
    url = os.environ.get("MCP_INTERNAL_URL")
    url = DEFAULT_URL if url is None else url.strip()
    return "" if url.lower() in ("", "off", "0", "none") else url


def _post(url: str, method: str, params: Optional[dict], client_ip: str, timeout: Tuple[float, float]) -> Any:
    headers = {"content-type": "application/json", "accept": "application/json"}
    if client_ip and client_ip != "unknown":
        headers["x-forwarded-for"] = client_ip[:64]      # the visitor's address, so the endpoint's per-address limit is theirs and not the whole chat's
    body = {"jsonrpc": "2.0", "id": 1, "method": method, **({"params": params} if params is not None else {})}
    r = requests.post(url, data=json.dumps(body), headers=headers, timeout=timeout, allow_redirects=False)
    if r.status_code == 429:
        raise RuntimeError("rate_limited")
    if r.status_code != 200:
        raise RuntimeError(f"http_{r.status_code}")
    payload = r.json()
    if "error" in payload:
        raise RuntimeError(f"rpc_{payload['error'].get('code')}")
    return payload["result"]


def get_tools(client_ip: str = "") -> List[Dict[str, Any]]:
    """The tools the endpoint offers (cached ten minutes; a failure is remembered for a minute so a down endpoint costs one quick attempt)."""
    url = endpoint()
    if not url:
        return []
    now = monotonic()
    with _lock:
        if _cache["url"] == url:
            if _cache["tools"] and now - _cache["at"] < CACHE_SECONDS:
                return _cache["tools"]
            if _cache["failed_at"] is not None and now - _cache["failed_at"] < RETRY_AFTER_FAILURE_SECONDS:
                return _cache["tools"] if _cache["tools"] else []
    try:
        tools = _post(url, "tools/list", {}, client_ip, LIST_TIMEOUT).get("tools") or []
        tools = [t for t in tools if isinstance(t, dict) and isinstance(t.get("name"), str)]
    except Exception as exc:
        logger.warning("FinLit tools unavailable (event=mcp_list_failed, exception_type=%s)", type(exc).__name__)
        with _lock:
            _cache.update(url=url, failed_at=now)     # keep the stale list, if any, while the endpoint is down
        return _cache["tools"]
    with _lock:
        _cache.update(url=url, at=now, tools=tools, failed_at=None)
    return tools


def reset_cache() -> None:
    with _lock:
        _cache.update(at=0.0, tools=[], failed_at=None, url=None)


# ------------------------------------------------------------------------------------------------------------- Gemini declarations
_KEEP = ("type", "description", "enum", "minimum", "maximum", "minItems", "maxItems", "required")


def gemini_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """The JSON Schema subset Gemini accepts for function parameters."""
    out = {k: schema[k] for k in _KEEP if k in schema}
    t = schema.get("type")
    if t == "array" and isinstance(schema.get("items"), dict):
        out["items"] = gemini_schema(schema["items"])
    if t == "object":
        props = {k: gemini_schema(v) for k, v in (schema.get("properties") or {}).items()}
        names = (schema.get("propertyNames") or {}).get("enum")
        extra = schema.get("additionalProperties")
        if names and isinstance(extra, dict):                      # a map with known keys: one property per key
            props.update({k: gemini_schema(extra) for k in names})
        if props:
            out["properties"] = props
        else:
            out.pop("required", None)
    return out


def declarations(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    decls = []
    for t in tools:
        params = gemini_schema(t.get("inputSchema") or {"type": "object"})
        d: Dict[str, Any] = {"name": t["name"], "description": (t.get("description") or "")[:900]}
        if params.get("properties"):
            d["parameters"] = params
        decls.append(d)
    return decls


# ------------------------------------------------------------------------------------------------------------- calling
def call_tool(name: str, args: Dict[str, Any], client_ip: str = "") -> Tuple[bool, Dict[str, Any]]:
    """Runs one tool. Returns (succeeded, what to give the model). A failure comes back as {"error": plain message}: the model is told, nothing is raised."""
    known = {t["name"] for t in get_tools(client_ip)}
    if name not in known:
        return False, {"error": "That tool does not exist."}
    try:
        result = _post(endpoint(), "tools/call", {"name": name, "arguments": args if isinstance(args, dict) else {}}, client_ip, CALL_TIMEOUT)
    except Exception as exc:
        logger.warning("FinLit tool call failed (event=mcp_call_failed, tool=%s, exception_type=%s)", name, type(exc).__name__)
        msg = "The data service is busy; ask again in a minute." if str(exc) == "rate_limited" else "The data service could not be reached right now."
        return False, {"error": msg}
    if result.get("isError"):
        text = " ".join(c.get("text", "") for c in result.get("content", []) if isinstance(c, dict))[:600]
        return False, {"error": text or "The tool reported an error."}
    data = result.get("structuredContent")
    if data is None:
        return False, {"error": "The tool returned no data."}
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    if len(text) > MAX_RESULT_CHARS:
        return True, {"note": "Result shortened to fit; the start of it follows.", "partialJson": text[:MAX_RESULT_CHARS]}
    return True, data
