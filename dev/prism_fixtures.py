"""Recorded FinEdge answers for the site backend, so FinLit Prism (the premium reports) runs locally without provider keys.

DEVELOPMENT ONLY. Used by dev/site_api_dev.py (--prism-fixtures, on by default when FINEDGE_API_KEY is empty or "dev").
The data is site-api/backend/tests/fixtures/premium_stock_audit_2026_10_18.json: minimized FinEdge responses retrieved on
17-18 October 2026 for eight companies (RELIANCE, TCS, MARUTI, NTPC, DLF, HDFCBANK, BAJFINANCE, HDFCLIFE), consolidated basis.
The same file drives the site backend's own end-to-end report tests (test_premium_shared_sources.py).

What is real: the dashboard loader, the resolution/recovery code, the model, the review and the PDF all run unchanged.
What is not: only those eight companies resolve; standalone answers with the consolidated figures; no industry peers
(valuation medians come from the recorded ratios or group fills); no Upstox (no second-source recovery, no ticker).
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

FIXTURE = Path("tests") / "fixtures" / "premium_stock_audit_2026_10_18.json"


def install(server, backend_dir: Path) -> list:
    """Point the site backend's FinEdge and Upstox access at the recorded answers. Returns the symbols available."""
    stocks = {item["symbol"]: item["raw"] for item in json.loads((backend_dir / FIXTURE).read_text())["stocks"]}

    def raw_for(path: str):
        symbol = path.rstrip("/").split("/")[-1].upper()
        return stocks.get(symbol)

    def finedge_get(path, params=None):
        params = params or {}
        if path == "/stock-symbols":
            return [{"symbol": s, "name": raw["profile"].get("name") or s} for s, raw in stocks.items()]
        if path == "/quote":
            symbol = str(params.get("symbol") or "").upper()
            return deepcopy(stocks[symbol]["quote"]) if symbol in stocks else {}
        raw = raw_for(path)
        if raw is None:
            return {}
        if path.startswith("/company-profile/"):
            return deepcopy(raw["profile"])
        if path.startswith("/daily-quotes/"):
            return deepcopy(raw["prices"])
        if path.startswith("/daily-price-ratios/"):
            return deepcopy(raw.get("ratios", {}))
        if path.startswith("/shareholdings/"):
            section = path.split("/")[2]
            return deepcopy(raw.get(section, {})) if section in ("summary", "distribution", "declaration") else {}
        if path.startswith("/financials/"):
            code, period = params.get("statement_code"), params.get("period")
            section = {"pl": "annual" if period == "annual" else "quarterly",
                       "bs": "balance" if period == "annual" else "balance_recent", "cf": "cashflow"}.get(code)
            return deepcopy(raw.get(section, {})) if section else {}
        return {}  # peers, segments, ratio tables, events: not recorded

    finedge_get._handles_transient_retries = True  # local answers: nothing to retry

    def no_upstox(_path, _params=None, default=None):
        return default if default is not None else {}

    server._finedge_get = finedge_get
    server._finedge_symbol_cache.update(items=None, fetched_at=0.0)
    server._try_resolve_upstox_instrument = lambda *_queries: {}
    server._safe_upstox_get = no_upstox
    return sorted(stocks)
