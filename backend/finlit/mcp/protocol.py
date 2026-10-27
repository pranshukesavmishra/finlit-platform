"""JSON-RPC 2.0 for the Model Context Protocol, stateless. No I/O here: the caller supplies the handlers for tools."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")   # newest first; a client asking for anything else is answered with the newest
SERVER_NAME = "finlit"
SERVER_VERSION = "1.0.0"
MAX_BATCH = 20

PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
INSTRUCTIONS = ("Read-only Indian stock market data from FinLit Ventures (company filings and market prices). Use the tools for every number; "
                "figures that are missing are returned as null and must be reported as missing. Each result carries source, asOf and a disclaimer: "
                "it describes the company's financial health from its filings and prices and is not a recommendation.")


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None):
        super().__init__(message)
        self.code, self.message, self.data = code, message, data


def error_response(id_: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def negotiate(requested: Any) -> str:
    return requested if isinstance(requested, str) and requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]


ToolLister = Callable[[], List[Dict[str, Any]]]
ToolCaller = Callable[[str, Dict[str, Any]], Awaitable[Dict[str, Any]]]


async def handle_one(msg: Any, list_tools: ToolLister, call_tool: ToolCaller) -> Optional[Dict[str, Any]]:
    """One JSON-RPC message -> its response, or None for a notification (and for a stray response object, which a server ignores)."""
    if not isinstance(msg, dict):
        return error_response(None, INVALID_REQUEST, "Invalid Request: expected a JSON object.")
    id_ = msg.get("id")
    has_id = "id" in msg
    if has_id and (isinstance(id_, bool) or not isinstance(id_, (str, int, float)) and id_ is not None):
        return error_response(None, INVALID_REQUEST, "Invalid Request: id must be a string or a number.")
    if msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        if "result" in msg or "error" in msg:
            return None     # a client's reply to a server request: this server sends none
        return error_response(id_ if has_id else None, INVALID_REQUEST, "Invalid Request: jsonrpc must be '2.0' and method a string.")
    method, params = msg["method"], msg.get("params")
    if params is not None and not isinstance(params, dict):
        return error_response(id_, INVALID_PARAMS, "Invalid params: expected an object.") if has_id else None
    params = params or {}
    if not has_id:      # notification: never answered, even if unknown
        return None
    try:
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": id_, "result": {
                "protocolVersion": negotiate(params.get("protocolVersion")),
                "capabilities": {"tools": {"listChanged": False}, "resources": {"listChanged": False}, "prompts": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "title": "FinLit Indian stock data", "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": id_, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"tools": list_tools()}}
        if method == "tools/call":
            name = params.get("name")
            args = params.get("arguments", {})
            if not isinstance(name, str):
                raise RpcError(INVALID_PARAMS, "Invalid params: name must be a string.")
            if args is None:
                args = {}
            if not isinstance(args, dict):
                raise RpcError(INVALID_PARAMS, "Invalid params: arguments must be an object.")
            return {"jsonrpc": "2.0", "id": id_, "result": await call_tool(name, args)}
        if method == "resources/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"resources": []}}
        if method == "resources/templates/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"resourceTemplates": []}}
        if method == "prompts/list":
            return {"jsonrpc": "2.0", "id": id_, "result": {"prompts": []}}
        if method in ("logging/setLevel", "resources/subscribe", "resources/unsubscribe", "completion/complete", "resources/read", "prompts/get"):
            raise RpcError(METHOD_NOT_FOUND if method in ("logging/setLevel", "resources/subscribe", "resources/unsubscribe", "completion/complete") else INVALID_PARAMS,
                           "Not supported by this server." if method != "resources/read" and method != "prompts/get" else "Unknown resource or prompt.")
        raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method[:80]}")
    except RpcError as e:
        return error_response(id_, e.code, e.message, e.data)
