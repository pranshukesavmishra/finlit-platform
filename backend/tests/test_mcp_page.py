"""The public page (frontend/src/lib/mcpTools.ts) lists the tools and limits the server really has."""

import json
import re
from pathlib import Path

from finlit.mcp.server import DISCLAIMER, limits, tools_listing

TS = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "mcpTools.ts").read_text()


def test_the_page_lists_exactly_the_servers_tools_in_order():
    on_page = re.findall(r'\{ name: "([a-z_]+)", what: "', TS)
    assert on_page == [t["name"] for t in tools_listing()]


def test_the_page_limits_are_the_servers_defaults(monkeypatch):
    for name in ("MCP_RATE_PER_MINUTE", "MCP_DAILY_CAP"):
        monkeypatch.delenv(name, raising=False)
    page = dict(re.findall(r"(perMinute|perDay): (\d+)", TS))
    assert (int(page["perMinute"]), int(page["perDay"])) == (limits()["per_minute"], limits()["daily"])


def test_the_page_carries_the_same_disclaimer():
    assert json.loads(re.search(r"MCP_DISCLAIMER = (\".*\");", TS).group(1)) == DISCLAIMER
