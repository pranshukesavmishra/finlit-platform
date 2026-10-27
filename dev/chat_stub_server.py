"""Runs the REAL site backend (site-api/backend/server.py, its /api/chat handler and tool loop) with a stand-in for Gemini, for local end-to-end checks
without a GEMINI_API_KEY. The stand-in asks for tools the way Gemini would (here: a quote for the symbol written in the question) and then answers
using ONLY what the tool returned. MCP_INTERNAL_URL decides which MCP endpoint the chat uses (default http://127.0.0.1:8000/mcp).
Usage:  python dev/chat_stub_server.py [--port 8011]      then   curl -s localhost:8011/api/chat -H 'content-type: application/json' -d '{"message":"price of RELIANCE"}'
"""
import argparse
import os
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MONGO_URL", "mongodb://stub.invalid:27017")
os.environ.setdefault("DB_NAME", "finlit_chat_stub")
os.environ["GEMINI_API_KEY"] = "stub-not-a-real-key"
sys.path[:0] = [str(ROOT), str(ROOT / "site-api")]


def install_stub_gemini():
    log = []

    def generate_content(**kw):
        contents, config = kw["contents"], kw["config"]
        last = contents[-1]
        replies = [p["function_response"] for p in last.get("parts", []) if isinstance(p, dict) and "function_response" in p] if isinstance(last, dict) else []
        question = contents[0]["parts"][0]["text"] if isinstance(contents[0], dict) else ""
        log.append({"tools_offered": [d["name"] for t in (config.get("tools") or []) for d in t["tool"]["function_declarations"]], "replies": len(replies)})
        sym = re.search(r"\b([A-Z][A-Z0-9&.-]{1,19})\b", question)
        if config.get("tools") and not replies and sym:
            call = SimpleNamespace(name="get_stock_quote", args={"symbol": sym.group(1)})
            return SimpleNamespace(text="", function_calls=[call], candidates=[SimpleNamespace(finish_reason="STOP", content={"role": "model", "parts": [{"function_call": {"name": call.name, "args": call.args}}]})])
        if replies:
            r = replies[0]["response"]
            if "error" in r:
                return SimpleNamespace(text="I could not get that figure: " + r["error"], function_calls=None, candidates=[SimpleNamespace(finish_reason="STOP")])
            q = (r.get("data") or {}).get("quote") or {}
            text = f"{r['data']['name']} last traded at Rs {q.get('price')} ({q.get('changePct')}% on the day), as of {r.get('asOf')}. 52-week range: {q.get('low52')} to {q.get('high52')}."
            return SimpleNamespace(text=text, function_calls=None, candidates=[SimpleNamespace(finish_reason="STOP")])
        return SimpleNamespace(text="General education answer (no figure was asked for, so no tool was used).", function_calls=None, candidates=[SimpleNamespace(finish_reason="STOP")])

    fake_types = SimpleNamespace(GenerateContentConfig=lambda **kw: kw, Tool=lambda **kw: {"tool": kw}, FunctionDeclaration=lambda **kw: kw, AutomaticFunctionCallingConfig=lambda **kw: kw)
    fake_genai = SimpleNamespace(Client=lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)), types=fake_types)
    google = types.ModuleType("google")
    google.genai = fake_genai
    sys.modules["google"], sys.modules["google.genai"] = google, fake_genai
    return log


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8011)
    args = ap.parse_args()
    install_stub_gemini()
    from backend import server  # noqa: E402
    from fastapi import FastAPI  # noqa: E402
    import uvicorn  # noqa: E402
    app = FastAPI()
    app.include_router(server.api_router)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
