"""Async FinEdge client.

The old backend made ~20–40 sequential `requests.get` calls with an 18 s timeout each, on the
request path. Here every endpoint for a stock is fetched concurrently (bounded by a semaphore so
we stay inside FinEdge rate limits), with retries on 429/5xx, and only ever by the worker.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import random
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import quote as urlquote

import httpx

from .config import Settings, get_settings

log = logging.getLogger("finlit.finedge")

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "finedge"
RETRY_STATUS = {429, 500, 502, 503, 504}
OPTIONAL = object()  # marker: endpoint failure should not fail the bundle


class FinEdgeError(RuntimeError):
    def __init__(self, path: str, status: Optional[int], message: str):
        super().__init__(f"{path}: {status} {message}")
        self.path, self.status = path, status


def _p(symbol: str) -> str:
    return urlquote(symbol.strip().upper(), safe="")


def bundle_requests(symbol: str, statement: str) -> Dict[str, Tuple[str, Dict[str, Any], float]]:
    """bundle key -> (path, params, timeout seconds). `statement` is consolidated | standalone."""
    s, t = _p(symbol), ("c" if statement == "consolidated" else "s")
    year = date.today().year
    return {
        "profile": (f"/company-profile/{s}", {}, 8),
        "peers": (f"/peers/{s}", {}, 8),
        "quote": ("/quote", {"symbol": symbol.upper()}, 5),
        "pl_annual": (f"/financials/{s}", {"statement_type": t, "statement_code": "pl", "period": "annual"}, 12),
        "bs_annual": (f"/financials/{s}", {"statement_type": t, "statement_code": "bs", "period": "annual"}, 12),
        "cf_annual": (f"/financials/{s}", {"statement_type": t, "statement_code": "cf", "period": "annual"}, 12),
        "pl_quarterly": (f"/financials/{s}", {"statement_type": t, "statement_code": "pl", "period": "quarterly"}, 12),
        "segments": (f"/segment-revenue/{s}", {"statement_type": t, "statement_code": "pl", "period": "annual"}, 10),
        "ratios_pr": (f"/ratios/{s}", {"statement_type": t, "ratio_type": "pr"}, 10),
        "ratios_le": (f"/ratios/{s}", {"statement_type": t, "ratio_type": "le"}, 10),
        "ratios_li": (f"/ratios/{s}", {"statement_type": t, "ratio_type": "li"}, 10),
        "ratios_ef": (f"/ratios/{s}", {"statement_type": t, "ratio_type": "ef"}, 10),
        "growth": (f"/financial-metrics/{s}", {"statement_type": t, "ratio_type": "gr"}, 10),
        "basic": (f"/basic-financials/{s}", {"statement_type": t, "statement_code": "pl"}, 10),
        "daily_quotes": (f"/daily-quotes/{s}", {"from": str(year - 6), "to": str(year)}, 15),
        "daily_price_ratios": (f"/daily-price-ratios/{s}", {"statement_type": t, "from": str(year - 1), "to": str(year)}, 12),
        "annual_price_ratios": (f"/annual-price-ratios/{s}", {"statement_type": t}, 10),
        "shareholding": (f"/shareholdings/pattern/{s}", {"period": "quarterly"}, 10),
        "dividends": (f"/dividend/{s}", {}, 8),
        "corporate_actions": ("/corporate-actions/all", {"symbol": symbol.upper(), "from_date": f"{year - 6}-01-01", "to_date": f"{year + 1}-12-31"}, 10),
        "announcements": ("/corp-announcements", {"symbol": symbol.upper()}, 8),
    }


# Endpoints whose payload depends on consolidated vs standalone.
STATEMENT_KEYS = {"pl_annual", "bs_annual", "cf_annual", "pl_quarterly", "segments", "ratios_pr", "ratios_le",
                  "ratios_li", "ratios_ef", "growth", "basic", "daily_price_ratios", "annual_price_ratios"}


def _has_rows(payload: Any) -> bool:
    rows = payload.get("financials") if isinstance(payload, dict) else payload
    return bool(rows)


# ---------------------------------------------------------------- fixture transport

def _load_fixture(name: str) -> Any:
    path = FIXTURE_DIR / name
    if name.endswith(".gz"):
        with gzip.open(path, "rt") as fh:
            return json.load(fh)
    return json.loads(path.read_text())


def fixture_transport(fixture_dir: Path = FIXTURE_DIR) -> httpx.MockTransport:
    """Serve recorded FinEdge payloads. Matching is by path plus the params the fixture recorded;
    statement_type, dates and token are ignored so any request shape the client makes resolves."""
    index = json.loads((fixture_dir / "index.json").read_text())["fixtures"]
    prefix = urlquote("/api/v1", safe="/")

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.startswith(prefix):
            path = path[len(prefix):]
        params = dict(request.url.params)
        for entry in index:
            if entry["path"] != path:
                continue
            if all(str(params.get(k, "")).lower() == str(v).lower() for k, v in entry["match"].items()):
                return httpx.Response(200, json=_load_fixture(entry["file"]))
        return httpx.Response(404, json={"message": f"no fixture for {path}"})

    return httpx.MockTransport(handler)


# ---------------------------------------------------------------- client

class FinEdgeClient:
    def __init__(self, settings: Optional[Settings] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.settings = settings or get_settings()
        if transport is None and self.settings.finedge_mode == "fixtures":
            transport = fixture_transport()
        if transport is None and not self.settings.finedge_api_key:
            raise RuntimeError("FINEDGE_API_KEY is not set (or use FINEDGE_MODE=fixtures for offline work)")
        self._client = httpx.AsyncClient(
            base_url=self.settings.finedge_base_url,
            transport=transport,
            headers={"Accept": "application/json", "User-Agent": "finlit-platform/1.0"},
            http2=False,
            limits=httpx.Limits(max_connections=self.settings.finedge_concurrency * 2, max_keepalive_connections=16),
        )
        self._sem = asyncio.Semaphore(self.settings.finedge_concurrency)
        self.calls = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10, retries: int = 3) -> Any:
        query = {**(params or {}), "token": self.settings.finedge_api_key}
        for attempt in range(retries + 1):
            async with self._sem:
                self.calls += 1
                try:
                    response = await self._client.get(path, params=query, timeout=timeout)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt == retries:
                        raise FinEdgeError(path, None, type(exc).__name__) from exc
                    response = None
            if response is not None:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise FinEdgeError(path, response.status_code, "non-JSON response") from exc
                if response.status_code not in RETRY_STATUS or attempt == retries:
                    raise FinEdgeError(path, response.status_code, response.text[:200])
                retry_after = response.headers.get("retry-after")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 0.5 * 2 ** attempt
            else:
                delay = 0.5 * 2 ** attempt
            await asyncio.sleep(delay + random.uniform(0, 0.25))
        raise FinEdgeError(path, None, "exhausted retries")  # pragma: no cover

    async def _fetch_many(self, requests: Dict[str, Tuple[str, Dict[str, Any], float]]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        async def one(key, spec):
            path, params, timeout = spec
            try:
                return key, await self.get(path, params, timeout), None
            except FinEdgeError as exc:
                log.info("finedge %s failed: %s", key, exc)
                return key, None, str(exc.status or "error")

        results = await asyncio.gather(*(one(k, spec) for k, spec in requests.items()))
        return {k: v for k, v, _ in results if v is not None}, {k: e for k, _, e in results if e}

    async def fetch_bundle(self, symbol: str, statement: str = "consolidated") -> Dict[str, Any]:
        """All raw payloads for one stock, fetched in parallel. Falls back to standalone when a
        company publishes no consolidated statements (common for single-entity companies)."""
        symbol = symbol.strip().upper()
        requests = bundle_requests(symbol, statement)
        bundle, errors = await self._fetch_many(requests)
        effective = statement
        if statement == "consolidated" and not _has_rows(bundle.get("pl_annual")):
            standalone = {k: v for k, v in bundle_requests(symbol, "standalone").items() if k in STATEMENT_KEYS}
            fallback, fallback_errors = await self._fetch_many(standalone)
            if _has_rows(fallback.get("pl_annual")):
                for key in STATEMENT_KEYS:
                    bundle.pop(key, None)
                    errors.pop(key, None)
                bundle.update(fallback)
                errors.update(fallback_errors)
                effective = "standalone"
        bundle.update(symbol=symbol, statement=effective, requestedStatement=statement, errors=errors)
        return bundle

    async def stock_symbols(self) -> list:
        payload = await self.get("/stock-symbols", timeout=30)
        return payload if isinstance(payload, list) else (payload or {}).get("data") or []
