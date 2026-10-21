"""Secondary data source (Upstox) for companies FinEdge sends little or nothing for (e.g. BSE 540084).

Used ONLY to fill what FinEdge left empty, section by section; FinEdge figures are never overwritten. Off and invisible without
UPSTOX_ACCESS_TOKEN. Request shapes and response parsing follow the old site (site-api/backend/server.py). Live Upstox behaviour has NOT
been verified in this repository (no token was available when it was written): field names are matched tolerantly and anything unreadable
is skipped rather than guessed. Units: Upstox fundamentals are in INR crore (the old site showed them as "Cr" without scaling); the
FinEdge-shaped rows built here are in rupees (x 1e7) because the normalizers divide by 1e7. LTP and candles are in rupees.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import random
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote as urlquote

import httpx

from . import coverage
from .config import Settings, get_settings

log = logging.getLogger("finlit.upstox")
CRORE = 10_000_000
STATUS_KEY = "upstox:status"
RETRY_STATUS = {429, 500, 502, 503, 504}
DISAGREE = 0.05

SECONDARY_NOTE = "Some figures come from our secondary data source."


class UpstoxTokenExpired(RuntimeError):
    """The access token was refused (401/403). Upstox tokens expire; the founder must paste a new one."""


class UpstoxError(RuntimeError):
    pass


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, dict):
        v = v.get("value")
    try:
        f = float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def _norm(text: Any) -> str:
    t = re.sub(r"\b(LIMITED|LTD)\b\.?", "", str(text or "").upper())
    return re.sub(r"[^A-Z0-9]", "", t)


# ---------------------------------------------------------------- client

class UpstoxClient:
    def __init__(self, settings: Optional[Settings] = None, redis: Any = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.settings, self.redis = settings or get_settings(), redis
        self.enabled = bool(self.settings.upstox_access_token)
        self.calls = 0
        self.expired = False
        self._sem = asyncio.Semaphore(3)
        self._http = httpx.AsyncClient(base_url=self.settings.upstox_base_url, transport=transport, timeout=12) if self.enabled else None

    async def aclose(self):
        if self._http:
            await self._http.aclose()

    async def _set_status(self, state: str) -> None:
        if self.redis is None:
            return
        try:
            await self.redis.set(STATUS_KEY, f"{state}|{int(time.time())}")
        except Exception:
            pass

    async def get(self, path: str, params: Optional[dict] = None, retries: int = 2) -> Any:
        """The `data` member of a successful Upstox reply. Raises UpstoxTokenExpired on 401/403."""
        if not self.enabled:
            raise UpstoxError("not configured")
        if self.expired:
            raise UpstoxTokenExpired("token expired")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.settings.upstox_access_token}"}
        for attempt in range(retries + 1):
            async with self._sem:
                self.calls += 1
                try:
                    r = await self._http.get(path, params=params or {}, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    r = None
                    if attempt == retries:
                        raise UpstoxError(type(exc).__name__) from exc
            if r is not None:
                if r.status_code in (401, 403):
                    self.expired = True
                    await self._set_status("expired")
                    raise UpstoxTokenExpired("token expired")
                if r.status_code < 400:
                    try:
                        body = r.json()
                    except ValueError as exc:
                        raise UpstoxError("non-JSON response") from exc
                    if not isinstance(body, dict) or body.get("status") != "success" or body.get("data") is None:
                        raise UpstoxError("unexpected payload")
                    await self._set_status("ok")
                    return body["data"]
                if r.status_code not in RETRY_STATUS or attempt == retries:
                    raise UpstoxError(f"HTTP {r.status_code}")
                ra = r.headers.get("retry-after")
                delay = float(ra) if ra and ra.isdigit() else 0.5 * 2 ** attempt
            else:
                delay = 0.5 * 2 ** attempt
            await asyncio.sleep(min(delay, 5) + random.uniform(0, 0.2))
        raise UpstoxError("exhausted retries")  # pragma: no cover

    async def safe(self, path: str, params: Optional[dict] = None, default: Any = None) -> Any:
        try:
            return await self.get(path, params)
        except UpstoxTokenExpired:
            raise
        except UpstoxError as exc:
            log.info("upstox %s: %s", path, exc)
            return default

    # ---- instrument resolver
    async def resolve(self, symbol: str, names: List[str], isin: Optional[str] = None) -> Optional[dict]:
        """Our company -> {isin, key, symbol}. Accepted only when the ISIN, the trading symbol/code or the full name matches exactly, so a
        similar-sounding company can never be mixed in."""
        cache = f"upstox:inst:{symbol}"
        if self.redis is not None:
            try:
                import json
                hit = await self.redis.get(cache)
                if hit:
                    return json.loads(hit) or None
            except Exception:
                pass
        wanted = {_norm(n) for n in [symbol, *names] if n}
        for q in [isin, *names, symbol]:
            if not q:
                continue
            data = await self.safe("/v2/instruments/search", {"query": str(q).strip()}, default=[])
            for it in data if isinstance(data, list) else []:
                if not isinstance(it, dict) or it.get("segment") not in ("NSE_EQ", "BSE_EQ") or not it.get("isin") or not it.get("instrument_key"):
                    continue
                if (isin and it["isin"].upper() == isin.upper()) or _norm(it.get("trading_symbol")) in wanted or _norm(it.get("name")) in wanted:
                    out = {"isin": it["isin"], "key": it["instrument_key"], "symbol": it.get("trading_symbol")}
                    if self.redis is not None:
                        try:
                            import json
                            await self.redis.set(cache, json.dumps(out), ex=30 * 86400)
                        except Exception:
                            pass
                    return out
        return None

    # ---- data
    async def key_ratios(self, isin: str):
        return await self.safe(f"/v2/fundamentals/{urlquote(isin, safe='')}/key-ratios", default=[])

    async def statement(self, isin: str, kind: str, statement: str, period: str):
        params = {"type": statement, "fs": "true"}
        if kind == "income-statement":
            params["time_period"] = period
        return await self.safe(f"/v2/fundamentals/{urlquote(isin, safe='')}/{kind}", params, default={})

    async def profile(self, isin: str):
        return await self.safe(f"/v2/fundamentals/{urlquote(isin, safe='')}/profile", default={})

    async def ltp(self, key: str):
        return await self.safe("/v3/market-quote/ltp", {"instrument_key": key}, default={})

    async def candles(self, key: str):
        to = datetime.now(timezone.utc).date()
        return await self.safe(f"/v3/historical-candle/{urlquote(key, safe='')}/days/1/{to.isoformat()}/{(to - timedelta(days=365 * 6)).isoformat()}", default={})


# ---------------------------------------------------------------- adapter (Upstox payload -> FinEdge-shaped raw rows, rupees)

_MON = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}


def period_end(label: Any) -> Optional[date]:
    """'Mar 2024' | 'March 2024' | '2024-03-31' | 'FY24' | 'FY2024' | '2024' -> period-end date (a bare year is the fiscal year ending March)."""
    t = str(label or "").strip().upper()
    m = re.match(r"^(\d{4})-(\d{2})(?:-(\d{2}))?", t)
    if m:
        y, mo = int(m[1]), int(m[2])
    else:
        m = re.search(r"\b([A-Z]{3})[A-Z]*[\s\-']*(\d{4})\b", t)
        if m and m[1] in _MON:
            y, mo = int(m[2]), _MON[m[1]]
        else:
            m = re.fullmatch(r"(?:FY\s*)?(\d{4}|\d{2})", t)
            if not m:
                return None
            y, mo = int(m[1]) + (2000 if len(m[1]) == 2 else 0), 3
    if not 1 <= mo <= 12 or not 1990 <= y <= 2100:
        return None
    return date(y, mo, calendar.monthrange(y, mo)[1])


def _series(payload: Any, key: str) -> Dict[str, Dict[date, float]]:
    """{category: {period_end: value in crore}}"""
    out: Dict[str, Dict[date, float]] = {}
    for row in (payload.get(key) if isinstance(payload, dict) else None) or []:
        if not isinstance(row, dict) or not row.get("category"):
            continue
        for pt in row.get("history") or []:
            d, v = period_end(pt.get("period")) if isinstance(pt, dict) else None, _num(pt.get("value")) if isinstance(pt, dict) else None
            if d and v is not None:
                out.setdefault(str(row["category"]).lower(), {})[d] = v
    return out


def income_rows(payload: Any) -> List[dict]:
    s = _series(payload, "income_statement")
    rev = s.get("revenue", {})
    rows = []
    for d in sorted(rev):
        g = lambda c: s.get(c, {}).get(d)
        oi, interest, dep, pbt, op, exc = g("other_income"), g("interest"), g("depreciation"), g("profit_before_tax"), g("operating_profit"), g("exceptional_items")
        r: Dict[str, Any] = {"period_end": d.isoformat(), "year": d.year + (1 if d.month > 3 else 0), "revenueFromOperations": rev[d] * CRORE}
        if oi is not None:
            r["otherIncome"] = oi * CRORE
            r["income"] = (rev[d] + oi) * CRORE
        if interest is not None:
            r["financeCosts"] = interest * CRORE
        if dep is not None:
            r["depreciationAndAmortisation"] = dep * CRORE
        if exc is not None:
            r["exceptionalItemsBeforeTax"] = exc * CRORE
        if pbt is not None:
            r["profitBeforeTax"] = pbt * CRORE
        if g("tax_expense") is not None:
            r["taxExpense"] = g("tax_expense") * CRORE
        if g("net_profit") is not None:
            r["profitLossForPeriod"] = g("net_profit") * CRORE
        if g("eps") is not None:
            r["eps"] = g("eps")                      # rupees per share, not scaled
        if "provisions_for_loan_loss" not in s:     # lenders: leave operating profit out rather than guess
            if op is None and None not in (pbt, interest, dep, oi):
                op = pbt + interest + dep - oi - (exc or 0)   # the old site's own derivation
            if op is not None and interest is not None and dep is not None:
                r["expenses"] = (rev[d] - op + interest + dep) * CRORE   # our convention: expenses include interest and depreciation
        rows.append(r)
    return rows


def balance_rows(payload: Any) -> List[dict]:
    rows = []
    for pt in (payload.get("history") if isinstance(payload, dict) else None) or []:
        d, a = period_end(pt.get("period")) if isinstance(pt, dict) else None, _num(pt.get("total_asset")) if isinstance(pt, dict) else None
        if d and a:
            rows.append({"period_end": d.isoformat(), "year": d.year + (1 if d.month > 3 else 0), "assets": a * CRORE})
    return sorted(rows, key=lambda r: r["period_end"])


def cash_rows(payload: Any) -> List[dict]:
    s = _series(payload, "cash_flow")
    names = {"cashFlowsFromOperatingActivities": ("operating", "cash_from_operating_activity"), "cashFlowsFromInvestingActivities": ("investing", "cash_from_investing_activity"),
             "cashFlowsFromFinancingActivities": ("financing", "cash_from_financing_activity")}
    dates = sorted({d for c in s.values() for d in c})
    rows = []
    for d in dates:
        r: Dict[str, Any] = {"period_end": d.isoformat(), "year": d.year + (1 if d.month > 3 else 0)}
        for field, cats in names.items():
            for c in cats:
                if d in s.get(c, {}):
                    r[field] = s[c][d] * CRORE
        if len(r) > 2:
            rows.append(r)
    return rows


def quote_payload(symbol: str, data: Any, key: str) -> Optional[dict]:
    """v3 LTP reply -> {SYMBOL: {current_price, change(%)}}. Prices are rupees."""
    for q in (data.values() if isinstance(data, dict) else []):
        if isinstance(q, dict) and (q.get("instrument_token") == key or len(data) == 1):
            p, cp = _num(q.get("last_price")), _num(q.get("cp"))
            if p and p > 0:
                return {symbol: {"current_price": p, "change": round((p - cp) / cp * 100, 2) if cp else None}}
    return None


def candle_payload(data: Any) -> Optional[dict]:
    rows = []
    for c in (data.get("candles") if isinstance(data, dict) else None) or []:
        if isinstance(c, list) and len(c) >= 6 and _num(c[4]):
            rows.append({"quote_date": str(c[0])[:10], "open_price": _num(c[1]), "high_price": _num(c[2]), "low_price": _num(c[3]), "close_price": _num(c[4]), "volume": _num(c[5])})
    return {"price": rows} if rows else None


def ratio_payload(data: Any) -> Optional[dict]:
    """Key ratios (percent values as the old site showed them) -> a FinEdge 'pr' TTM row (fractions). Only ROE and ROCE are carried; P/E and
    P/B are computed by FinLit from the figures it holds."""
    row: Dict[str, Any] = {"header": "TTM"}
    for it in data if isinstance(data, list) else []:
        name = _norm(it.get("name") if isinstance(it, dict) else "")
        v = _num(it.get("company_value") if isinstance(it, dict) else None)
        if v is not None and name in ("ROE", "ROCE"):
            row["returnOnEquity" if name == "ROE" else "returnOnCapital"] = v / 100
    return {"ratios": [row]} if len(row) > 1 else None


# ---------------------------------------------------------------- merge + reconcile

def _latest(rows: List[dict], key: str):
    for r in sorted(rows, key=lambda r: str(r.get("period_end")), reverse=True):
        v = _num(r.get(key))
        if v:
            return str(r.get("period_end"))[:4], v
    return None


def reconcile(bundle: dict, upstox_pl: List[dict], upstox_price: Optional[float]) -> List[dict]:
    """Where both sources hold a figure and differ by more than 5% on revenue, net profit or price, FinEdge is kept and the gap is returned."""
    out = []
    fe = (bundle.get("pl_annual") or {}).get("financials") if isinstance(bundle.get("pl_annual"), dict) else None
    for key, label in (("revenueFromOperations", "revenue"), ("profitLossForPeriod", "net profit")):
        a, b = _latest(fe or [], key), _latest(upstox_pl, key)
        if a and b and a[0] == b[0] and abs(a[1] - b[1]) / max(abs(b[1]), 1) > DISAGREE:
            out.append({"item": label, "period": a[0], "finedge": round(a[1] / CRORE, 2), "secondary": round(b[1] / CRORE, 2)})
    q = coverage._price(bundle.get("quote"), str(bundle.get("symbol")).upper())
    if q and upstox_price and abs(q - upstox_price) / upstox_price > DISAGREE:
        out.append({"item": "price", "finedge": q, "secondary": upstox_price})
    return out


async def supplement(bundle: dict, client: Optional[UpstoxClient], company: Optional[dict] = None) -> dict:
    """Fill the sections FinEdge left empty. Returns the same bundle (mutated); never touches a section FinEdge filled."""
    if client is None or not client.enabled:
        return bundle
    p = coverage.provider_side(bundle)
    need = {"quote": not p["quote"] and p["closes"] == 0, "pl": p["annual"] == 0, "bs": p["balance"] == 0, "cf": p["cash"] == 0, "ql": p["quarterly"] == 0}
    if not any(need.values()):
        return bundle
    symbol = str(bundle["symbol"]).upper()
    c = company or {}
    try:
        inst = await client.resolve(symbol, [n for n in (c.get("name"), c.get("bse_code") and str(c["bse_code"]), c.get("nse_code")) if n], c.get("isin"))
        if not inst:
            return bundle
        src: Dict[str, str] = {}
        stmt = bundle.get("statement") or "consolidated"

        async def stmts(kind, period):
            nonlocal stmt
            d = await client.statement(inst["isin"], kind, stmt, period)
            if not income_rows(d) and kind == "income-statement" and stmt == "consolidated":
                alt = await client.statement(inst["isin"], kind, "standalone", period)
                if income_rows(alt):
                    d, stmt = alt, "standalone"   # the company publishes standalone accounts only; later statements use the same basis
            return d
        compare_income = None
        if need["pl"] or p["annual"]:
            inc = await stmts("income-statement", "yearly")
            rows = income_rows(inc)
            if need["pl"] and rows:
                bundle["pl_annual"] = {"financials": rows}; src["pl_annual"] = "upstox"
            elif rows:
                compare_income = rows
        if need["ql"]:
            rows = income_rows(await stmts("income-statement", "quarterly"))
            if rows:
                bundle["pl_quarterly"] = {"financials": rows}; src["pl_quarterly"] = "upstox"
        if need["bs"]:
            rows = balance_rows(await stmts("balance-sheet", "yearly"))
            if rows:
                bundle["bs_annual"] = {"financials": rows}; src["bs_annual"] = "upstox"
        if need["cf"]:
            rows = cash_rows(await stmts("cash-flow", "yearly"))
            if rows:
                bundle["cf_annual"] = {"financials": rows}; src["cf_annual"] = "upstox"
        price = None
        if need["quote"]:
            q = quote_payload(symbol, await client.ltp(inst["key"]), inst["key"])
            if q:
                bundle["quote"] = q; src["quote"] = "upstox"
            h = candle_payload(await client.candles(inst["key"]))
            if h:
                bundle["daily_quotes"] = h; src["daily_quotes"] = "upstox"
        elif p["quote"]:
            q = quote_payload(symbol, await client.ltp(inst["key"]), inst["key"])
            price = q[symbol]["current_price"] if q else None
        if p["ratios"] == 0 and not p["ratios_ttm"] and src:
            r = ratio_payload(await client.key_ratios(inst["isin"]))
            if r:
                bundle["ratios_pr"] = r; src["ratios_pr"] = "upstox"
        prof = bundle.get("profile") if isinstance(bundle.get("profile"), dict) else {}
        if src and (not prof.get("description") or not prof.get("sector")):
            up = await client.profile(inst["isin"])
            if isinstance(up, dict) and (up.get("company_profile") or up.get("sector")):
                bundle["profile"] = {**prof, "description": prof.get("description") or up.get("company_profile"), "sector": prof.get("sector") or up.get("sector")}
                src["profile"] = "upstox"
        if src.get("pl_annual") or src.get("pl_quarterly"):
            bundle["statement"] = stmt
        bundle["_source"] = src
        bundle["_reconcile"] = reconcile(bundle, compare_income or [], price) if (compare_income or price) else []
        for item in bundle["_reconcile"]:
            log.warning("SOURCES DISAGREE %s: %s", symbol, item)
    except UpstoxTokenExpired:
        log.error("Upstox token expired: secondary source skipped for %s", symbol)
    except Exception:
        log.exception("secondary source failed for %s", symbol)
    return bundle


# ---------------------------------------------------------------- health (plain words)

async def health_line(redis: Any, settings: Optional[Settings] = None) -> dict:
    s = settings or get_settings()
    if not s.upstox_access_token:
        return {"state": "not_configured", "text": "Secondary source: not configured"}
    raw = None
    if redis is not None:
        try:
            raw = await redis.get(STATUS_KEY)
            raw = raw.decode() if isinstance(raw, bytes) else raw
        except Exception:
            raw = None
    if raw and raw.startswith("expired"):
        return {"state": "token_expired", "text": "Secondary source: token expired. Paste a fresh UPSTOX_ACCESS_TOKEN into the Render dashboard (see docs/SECOND-SOURCE.md); until then gaps stay empty."}
    return {"state": "connected", "text": "Secondary source: connected"}
