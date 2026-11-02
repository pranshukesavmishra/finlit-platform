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
import time
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple
from urllib.parse import quote as urlquote

import httpx

from .config import Settings, get_settings
from .normalize.common import parse_date

log = logging.getLogger("finlit.finedge")

FIXTURE_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "finedge"
RETRY_STATUS = {429, 500, 502, 503, 504}
OPTIONAL = object()  # marker: endpoint failure should not fail the bundle


THROTTLE_STATUS = {429, 503}      # "too many requests" / "busy": the provider is asking us to slow down, which is not a failure of the data
MAX_RETRY_AFTER = 120.0           # never wait longer than this on one provider instruction
PACE_STEP, PACE_MAX, PACE_DECAY = 0.5, 8.0, 0.7
PACE_MAX_BOUNDED = 2.0            # the pace cap of a time-bounded job: a full rebuild fans out ~20 calls, and at 8 s each the queue alone is minutes   # adaptive pace: seconds between calls; doubles on a throttle, recovers on success


class FinEdgeError(RuntimeError):
    def __init__(self, path: str, status: Optional[int], message: str, retry_after: Optional[float] = None):
        super().__init__(f"{path}: {status} {message}")
        self.path, self.status, self.retry_after = path, status, retry_after

    @property
    def throttled(self) -> bool:
        """The provider said 'too many requests' / 'busy' (429, 503): slow down and ask again later; the company itself is fine."""
        return self.status in THROTTLE_STATUS


def parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Retry-After as seconds (a number, or an HTTP date); None when absent or unreadable. Capped at MAX_RETRY_AFTER."""
    if not value:
        return None
    value = value.strip()
    try:
        secs = float(value)
    except ValueError:
        try:
            from email.utils import parsedate_to_datetime
            from datetime import datetime, timezone
            secs = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except Exception:
            return None
    return max(0.0, min(secs, MAX_RETRY_AFTER))


def backoff_delay(attempt: int, retry_after: Optional[float] = None, base: float = 0.5, cap: float = 30.0) -> float:
    """How long to wait before retry number `attempt` (0 = first retry): the provider's Retry-After when it sent one, else exponential with jitter
    (half to full of base*2^attempt, capped), so many callers do not come back at the same moment."""
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_AFTER) + random.uniform(0, 0.25)
    d = min(cap, base * 2 ** attempt)
    return d * random.uniform(0.5, 1.0)


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
        "announcements": ("/corp-announcements", {"symbol": symbol.upper(), "from_date": f"{year - 1}-01-01", "to_date": f"{year}-12-31"}, 8),
    }


# What the first paint of a report needs: every part its score, key metrics, returns, statements and ratios are worked out from, so what is shown at
# first is final and correct (a score from half the inputs would be a wrong number). A company opened before it is stored is built from these first;
# the parts that feed only the ownership, peers, segments and announcements/events blocks (LATER below) are fetched afterwards, at low priority, and
# those blocks fill in by themselves. Every CORE_PART of the worker is in this set.
ESSENTIAL_KEYS = ("profile", "quote", "pl_annual", "bs_annual", "cf_annual", "pl_quarterly", "ratios_pr", "ratios_le", "ratios_li", "ratios_ef",
                  "growth", "basic", "daily_quotes", "daily_price_ratios", "dividends", "corporate_actions")

# Endpoints whose payload depends on consolidated vs standalone.
STATEMENT_KEYS = {"pl_annual", "bs_annual", "cf_annual", "pl_quarterly", "segments", "ratios_pr", "ratios_le",
                  "ratios_li", "ratios_ef", "growth", "basic", "daily_price_ratios", "annual_price_ratios"}


def _has_rows(payload: Any) -> bool:
    """True when the payload carries data: a non-empty list, or an object with at least one non-empty value
    other than the echoed symbol / label fields (each endpoint wraps its rows under a different key)."""
    if isinstance(payload, dict):
        return any(bool(v) for k, v in payload.items() if k not in {"symbol", "stock_symbol", "company_name", "ratio_type", "status"})
    return bool(payload)


def _rows_of(payload: Any) -> list:
    rows = payload.get("financials") if isinstance(payload, dict) else payload
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def latest_period_end(payload: Any) -> Optional[date]:
    ends = []
    for r in _rows_of(payload):
        d = parse_date(r.get("period_end")) or (parse_date(f"{r.get('year')}-03-31") if r.get("year") else None)
        if d:
            ends.append(d)
    return max(ends) if ends else None


def stale_reason(bundle: Dict[str, Any], standalone_annual: Any, standalone_quarterly: Any) -> Optional[Dict[str, Any]]:
    """None when the consolidated statements are current; else what is stale. Stale = the standalone latest quarter is at least two quarters
    (about 180 days) newer, or its latest financial year at least a year (about 360 days) newer."""
    cq, sq = latest_period_end(bundle.get("pl_quarterly")), latest_period_end(standalone_quarterly)
    ca, sa = latest_period_end(bundle.get("pl_annual")), latest_period_end(standalone_annual)
    q_stale = bool(cq and sq and (sq - cq).days >= 170)
    a_stale = bool(ca and sa and (sa - ca).days >= 360)
    if not (q_stale or a_stale):
        return None
    return {"consolidatedLatestQuarter": cq.isoformat() if cq else None, "standaloneLatestQuarter": sq.isoformat() if sq else None,
            "consolidatedLatestYear": ca.isoformat() if ca else None, "standaloneLatestYear": sa.isoformat() if sa else None}


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

class _NoLock:
    """An async context manager that does nothing (the normal-priority path of FinEdgeClient.get)."""
    async def __aenter__(self):
        return None

    async def __aexit__(self, *exc):
        return False


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
        # Background parts (the rest of a report whose key numbers are already shown) may use at most half of the slots, so a report somebody
        # is waiting on never queues behind them.
        self._low = asyncio.Semaphore(max(1, self.settings.finedge_concurrency // 2))
        self.calls = 0
        # Adaptive pacing, shared by every caller of this client: after a 429/503 calls are spaced `pace` seconds apart (and not before a Retry-After
        # has passed); every success shortens the spacing again until it is gone.
        self.pace = 0.0
        self.pace_max = PACE_MAX        # a time-bounded job lowers this (results: PACE_MAX_BOUNDED) so a throttled provider cannot stretch one call past the run's budget
        self.throttled = 0              # how many 429/503 answers this client has seen
        self._next_at = 0.0             # loop time before which the next call must not start
        self._clock = time.monotonic

    def _slow_down(self, retry_after: Optional[float]) -> None:
        self.throttled += 1
        self.pace = min(self.pace_max, max(PACE_STEP, self.pace * 2))
        wait = retry_after if retry_after is not None else self.pace
        if self.pace_max < PACE_MAX:      # a time-bounded job never holds the whole client back for longer than its cap
            wait = min(wait, self.pace_max)
        self._next_at = max(self._next_at, self._clock() + wait)

    def _recovered(self) -> None:
        if self.pace:
            self.pace = 0.0 if self.pace * PACE_DECAY < 0.1 else self.pace * PACE_DECAY

    async def _wait_turn(self) -> None:
        """Takes the next call slot: immediately when the provider has not asked us to slow down, else `pace` seconds after the previous slot."""
        if not self.pace and self._next_at <= self._clock():
            return
        now = self._clock()
        slot = max(now, self._next_at)
        self._next_at = slot + self.pace
        if slot > now:
            await asyncio.sleep(slot - now)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()

    async def aclose(self):
        await self._client.aclose()

    async def get(self, path: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10, retries: int = 3, low: bool = False, max_wait: Optional[float] = None) -> Any:
        """`max_wait` (seconds) bounds every wait this call makes between tries: a Retry-After longer than it is not waited for, the throttled error is
        raised at once instead (the caller skips the company and asks again on its next run); a backoff sleep is cut to it."""
        query = {**(params or {}), "token": self.settings.finedge_api_key}
        for attempt in range(retries + 1):
            await self._wait_turn()
            async with (self._low if low else _NoLock()), self._sem:
                self.calls += 1
                try:
                    response = await self._client.get(path, params=query, timeout=timeout)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    if attempt == retries:
                        raise FinEdgeError(path, None, type(exc).__name__) from exc
                    response = None
            retry_after = None
            if response is not None:
                if response.status_code < 400:
                    try:
                        body = response.json()
                    except ValueError as exc:
                        raise FinEdgeError(path, response.status_code, "non-JSON response") from exc
                    self._recovered()
                    return body
                if response.status_code in (401, 403):   # the key is not accepted: remembered for the admin alert (jobs/alerts), the error still goes to the caller
                    from .jobs.signals import report_refused
                    await report_refused(self.settings, "finedge", response.status_code)
                retry_after = parse_retry_after(response.headers.get("retry-after"))
                if response.status_code in THROTTLE_STATUS:
                    self._slow_down(retry_after)
                if response.status_code not in RETRY_STATUS or attempt == retries or (max_wait is not None and retry_after is not None and retry_after > max_wait):
                    raise FinEdgeError(path, response.status_code, response.text[:200], retry_after)
            delay = backoff_delay(attempt, retry_after)
            await asyncio.sleep(delay if max_wait is None else min(delay, max_wait))
        raise FinEdgeError(path, None, "exhausted retries")  # pragma: no cover

    async def _fetch_many(self, requests: Dict[str, Tuple[str, Dict[str, Any], float]], low: bool = False, on_part=None) -> Tuple[Dict[str, Any], Dict[str, str]]:
        async def one(key, spec):
            path, params, timeout = spec
            got, err = None, None
            try:
                got = await (self.get(path, params, timeout, low=True) if low else self.get(path, params, timeout))
            except FinEdgeError as exc:
                log.info("finedge %s failed: %s", key, exc)
                err = str(exc.status or "error")
            if on_part is not None:   # a part the provider does not have (404) also counts as done: the progress shown is "parts answered"
                try:
                    await on_part(key)
                except Exception:   # nosec B110 - a progress report must never fail a load
                    pass
            return key, got, err

        results = await asyncio.gather(*(one(k, spec) for k, spec in requests.items()))
        return {k: v for k, v, _ in results if v is not None}, {k: e for k, _, e in results if e}

    async def fetch_bundle(self, symbol: str, statement: str = "consolidated", only: Optional[Iterable[str]] = None, on_part=None, low: bool = False) -> Dict[str, Any]:
        """All raw payloads for one stock, fetched in parallel. Falls back to standalone when a
        company publishes no consolidated statements (common for single-entity companies).
        `only` limits the load to those parts (ESSENTIAL_KEYS for a first paint); fetch_rest() gets the others. `on_part(key)` is awaited as each part arrives."""
        symbol = symbol.strip().upper()
        requests = bundle_requests(symbol, statement)
        wanted = set(only) if only is not None else None
        if wanted is not None:
            requests = {k: v for k, v in requests.items() if k in wanted}
        bundle, errors = await self._fetch_many(requests, low=low, on_part=on_part)
        dropped = [k for k, why in errors.items() if why != "404"]   # 404 = the provider has no such data for this company: not a failure
        if dropped:   # a busy provider drops a few calls: ask once more for just those, a little later
            await asyncio.sleep(1.5)
            again, still = await self._fetch_many({k: requests[k] for k in dropped}, low=low)
            bundle.update({k: v for k, v in again.items() if v is not None})
            errors = {**{k: v for k, v in errors.items() if k not in dropped}, **still}
        effective = statement
        # Standalone only when the provider answered and has no consolidated accounts, never because the request failed.
        if statement == "consolidated" and "pl_annual" not in errors and not _has_rows(bundle.get("pl_annual")):
            standalone = {k: v for k, v in bundle_requests(symbol, "standalone").items() if k in STATEMENT_KEYS and (wanted is None or k in wanted)}
            fallback, fallback_errors = await self._fetch_many(standalone, low=low)
            if _has_rows(fallback.get("pl_annual")):
                for key in STATEMENT_KEYS:
                    bundle.pop(key, None)
                    errors.pop(key, None)
                bundle.update(fallback)
                errors.update(fallback_errors)
                effective = "standalone"
        if effective == "consolidated" and statement == "consolidated" and _has_rows(bundle.get("pl_annual")):
            await self._prefer_current_basis(symbol, bundle, errors, wanted)
            if bundle.get("basisChoice", {}).get("chosen") == "standalone":
                effective = "standalone"
        bundle.update(symbol=symbol, statement=effective, requestedStatement=statement, errors=errors)
        return bundle

    async def fetch_rest(self, bundle: Dict[str, Any], on_part=None) -> Dict[str, Any]:
        """The parts a first-paint load (fetch_bundle(only=ESSENTIAL_KEYS)) left out, on the basis that load settled on, at low priority. Merged into
        `bundle` (and its `errors`); a part that fails is recorded there and never raises."""
        symbol, basis = bundle["symbol"], bundle.get("statement") or "consolidated"
        wanted = {k: v for k, v in bundle_requests(symbol, basis).items() if k not in ESSENTIAL_KEYS and bundle.get(k) is None}
        errors = dict(bundle.get("errors") or {})
        if wanted:
            got, errs = await self._fetch_many(wanted, low=True, on_part=on_part)
            dropped = [k for k, why in errs.items() if why != "404"]
            if dropped:   # a busy provider drops a few calls: once more for just those
                await asyncio.sleep(1.0)
                again, still = await self._fetch_many({k: wanted[k] for k in dropped}, low=True, on_part=on_part)
                got.update({k: v for k, v in again.items() if v is not None})
                errs = {**{k: v for k, v in errs.items() if k not in dropped}, **still}
            bundle.update(got)
            for k in wanted:
                errors.pop(k, None)
            errors.update(errs)
        bundle["errors"] = errors
        return bundle

    async def _prefer_current_basis(self, symbol: str, bundle: Dict[str, Any], errors: Dict[str, str], wanted: Optional[set] = None) -> None:
        """Some companies' consolidated statements stop years before their standalone ones (SBFC: consolidated quarters end Mar 2025, standalone
        Sep 2026). Two small extra calls (standalone annual and quarterly P&L; the annual one also serves the revenue guard) find out. When the
        consolidated set is stale, the whole statement set is replaced by the standalone one, so no page mixes the two bases."""
        small = {k: v for k, v in bundle_requests(symbol, "standalone").items() if k in ("pl_annual", "pl_quarterly")}
        got, _errs = await self._fetch_many(small)
        if got.get("pl_annual") is not None:
            bundle["pl_annual_standalone"] = got["pl_annual"]   # worker + snapshot.basis_gaps reuse this instead of fetching it again
        stale = stale_reason(bundle, got.get("pl_annual"), got.get("pl_quarterly"))
        if not stale:
            return
        rest = {k: v for k, v in bundle_requests(symbol, "standalone").items() if k in STATEMENT_KEYS and k not in small and (wanted is None or k in wanted)}
        fallback, fallback_errors = await self._fetch_many(rest)
        for key in STATEMENT_KEYS:
            bundle.pop(key, None)
            errors.pop(key, None)
        bundle.update(fallback)
        bundle.update({k: v for k, v in got.items()})
        errors.update(fallback_errors)
        bundle.pop("pl_annual_standalone", None)
        bundle["basisChoice"] = {"chosen": "standalone", "requested": "consolidated", "reason": "stale_consolidated", **stale}

    async def stock_symbols(self) -> list:
        payload = await self.get("/stock-symbols", timeout=30)
        return payload if isinstance(payload, list) else (payload or {}).get("data") or []
