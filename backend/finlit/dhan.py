"""Dhan market-data API (DhanHQ v2): a second, independent source of prices and history, and the public instrument file.

Two parts:
  * the instrument file (public, no account): every NSE/BSE equity with ISIN, surveillance flag, margin eligibility and F&O status;
  * DhanClient (needs the Data API subscription): batch last prices and daily candles, with its own 24-hour access token renewed
    by the server from the client id, PIN and an authenticator (TOTP) secret, so nobody pastes a token every day.

Off and invisible without DHAN_CLIENT_ID. Secrets never appear in logs or error text (the token call carries the PIN and code in its URL,
so the HTTP library's request log is silenced here and errors never repeat the URL).
"""

from __future__ import annotations

import asyncio
import base64
import csv
import hashlib
import hmac
import io
import json
import logging
import struct
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import httpx

from .config import Settings, get_settings

log = logging.getLogger("finlit.dhan")
logging.getLogger("httpx").setLevel(logging.WARNING)   # its INFO lines print full URLs, and the token call's URL holds the PIN and code
INSTRUMENTS_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
TOKEN_KEY = "dhan:token"
RENEW_BEFORE = 2 * 3600          # seconds of life left at which a token is replaced
RETRY_STATUS = {429, 500, 502, 503, 504}
IST = timezone(timedelta(hours=5, minutes=30))


class DhanError(RuntimeError):
    """Any failure talking to Dhan. The text never holds a URL, PIN, code or token."""


# ------------------------------------------------------------------------------------------------------------------ one-time codes

def totp(secret: str, at: Optional[float] = None, digits: int = 6, step: int = 30) -> str:
    """RFC 6238 time-based one-time code (SHA-1), as authenticator apps make it."""
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret.replace(" ", "")) % 8), casefold=True)
    msg = struct.pack(">Q", int((time.time() if at is None else at) // step))
    h = hmac.new(key, msg, hashlib.sha1).digest()
    o = h[-1] & 0x0F
    return str((struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % 10 ** digits).zfill(digits)


# ------------------------------------------------------------------------------------------------------------------ instrument file

def _f(v: Any) -> Optional[float]:
    try:
        x = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def parse_instruments(lines: Iterable[str]) -> List[dict]:
    """Equity rows (NSE and BSE) from the detailed instrument file, each marked with whether the stock has futures (and the lot size).

    Streams line by line: the file is about 36 MB and only the equity rows and the futures' underlyings are kept.
    """
    out: Dict[tuple, dict] = {}
    fut: Dict[str, int] = {}                 # NSE underlying symbol -> lot size of its futures
    for r in csv.DictReader(lines):
        seg, inst, exch = r.get("SEGMENT"), r.get("INSTRUMENT"), r.get("EXCH_ID")
        if exch == "NSE" and seg == "D" and inst == "FUTSTK":
            sym, lot = (r.get("UNDERLYING_SYMBOL") or "").strip(), _f(r.get("LOT_SIZE"))
            if sym and sym not in fut and lot:
                fut[sym] = int(lot)
        elif seg == "E" and inst == "EQUITY" and exch in ("NSE", "BSE"):
            sid = (r.get("SECURITY_ID") or "").strip()
            sym = (r.get("UNDERLYING_SYMBOL") or r.get("SYMBOL_NAME") or "").strip()
            if not sid or not sym:
                continue
            isin = (r.get("ISIN") or "").strip()
            mtf = _f(r.get("MTF_LEVERAGE"))
            out[(exch, sid)] = {
                "exch": exch, "security_id": sid, "symbol": sym, "isin": isin if isin and isin != "NA" else None,
                "name": (r.get("DISPLAY_NAME") or r.get("SYMBOL_NAME") or "").strip() or None, "series": (r.get("SERIES") or "").strip() or None,
                "asm_gsm": (r.get("ASM_GSM_FLAG") or "").strip() or None,
                "asm_gsm_cat": None if (r.get("ASM_GSM_CATEGORY") or "NA").strip() in ("", "NA") else r["ASM_GSM_CATEGORY"].strip(),
                "mtf_leverage": mtf if mtf and mtf > 0 else None, "fno": False, "lot_size": None}
    for row in out.values():
        if row["exch"] == "NSE" and row["symbol"] in fut:
            row["fno"], row["lot_size"] = True, fut[row["symbol"]]
    return list(out.values())


async def fetch_instruments(client: Optional[httpx.AsyncClient] = None) -> List[dict]:
    """Download the file to a temporary file (never all in memory) and read it line by line."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=180.0), follow_redirects=True)
    try:
        with tempfile.TemporaryFile() as tmp:
            async with client.stream("GET", INSTRUMENTS_URL) as resp:
                if resp.status_code != 200:
                    raise DhanError(f"instrument file: HTTP {resp.status_code}")
                async for chunk in resp.aiter_bytes():
                    tmp.write(chunk)
            tmp.seek(0)
            return parse_instruments(io.TextIOWrapper(tmp, encoding="utf-8", errors="replace", newline=""))
    except httpx.HTTPError as e:
        raise DhanError("instrument file: " + type(e).__name__) from None
    finally:
        if own:
            await client.aclose()


async def save_instruments(store, rows: List[dict]) -> int:
    """Replace the table with these rows in one transaction. Refuses a short answer (a broken download must not empty the table)."""
    if len(rows) < 5000:
        raise DhanError(f"instrument file looks incomplete ({len(rows)} equities); kept what was stored")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM dhan_instruments")
            await conn.executemany(
                "INSERT INTO dhan_instruments (exch, security_id, symbol, isin, name, series, asm_gsm, asm_gsm_cat, mtf_leverage, fno, lot_size) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",
                [(r["exch"], r["security_id"], r["symbol"], r["isin"], r["name"], r["series"], r["asm_gsm"], r["asm_gsm_cat"], r["mtf_leverage"],
                  r["fno"], r["lot_size"]) for r in rows])
    return len(rows)


# ------------------------------------------------------------------------------------------------------------------ authenticated client

class DhanClient:
    def __init__(self, settings: Optional[Settings] = None, redis: Any = None, http: Optional[httpx.AsyncClient] = None):
        self.settings = settings or get_settings()
        self.redis = redis
        self._http = http or httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=10.0))
        self._own = http is None
        self._token: Optional[Dict[str, Any]] = None
        self._lock = asyncio.Lock()
        self._last_call = 0.0

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.dhan_client_id and ((s.dhan_pin and s.dhan_totp_secret) or s.dhan_access_token))

    async def aclose(self) -> None:
        if self._own:
            await self._http.aclose()

    async def __aenter__(self) -> "DhanClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def token(self, force: bool = False) -> str:
        """A token with at least two hours left: generated by the server when PIN and TOTP secret are set, else the pasted one."""
        s = self.settings
        async with self._lock:
            now = time.time()
            if not force and self._token and self._token["exp"] - now > RENEW_BEFORE:
                return self._token["token"]
            if s.dhan_pin and s.dhan_totp_secret:
                if not force and self.redis is not None:
                    try:
                        raw = await self.redis.get(TOKEN_KEY)
                        cached = json.loads(raw) if raw else None
                        if cached and cached["exp"] - now > RENEW_BEFORE:
                            self._token = cached
                            return cached["token"]
                    except Exception:
                        pass
                self._token = await self._generate()
                if self.redis is not None:
                    try:
                        await self.redis.set(TOKEN_KEY, json.dumps(self._token), ex=max(60, int(self._token["exp"] - now)))
                    except Exception:
                        pass
                return self._token["token"]
            if s.dhan_access_token:
                self._token = {"token": s.dhan_access_token, "exp": now + 24 * 3600}   # its real expiry is unknown: a refused call says so
                return s.dhan_access_token
            raise DhanError("Dhan is not configured")

    async def _generate(self) -> Dict[str, Any]:
        s = self.settings
        try:
            r = await self._http.post(s.dhan_auth_url.rstrip("/") + "/app/generateAccessToken",
                                      params={"dhanClientId": s.dhan_client_id, "pin": s.dhan_pin, "totp": totp(s.dhan_totp_secret)})
            body = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError) as e:
            raise DhanError("token request failed: " + type(e).__name__) from None
        tok = body.get("accessToken")
        if not tok:
            raise DhanError(f"Dhan refused to make a token (HTTP {r.status_code}): check the client id, PIN and authenticator secret")
        try:
            exp = datetime.fromisoformat(body["expiryTime"]).replace(tzinfo=IST).timestamp()
        except (KeyError, ValueError):
            exp = time.time() + 23 * 3600
        return {"token": tok, "exp": exp}

    async def _post(self, path: str, body: dict, min_gap: float = 0.0) -> Any:
        """POST with the token headers; 429/5xx retried; a refused token is renewed once. min_gap paces calls (Dhan: quote calls 1 per second)."""
        tried_renew = False
        for attempt in range(4):
            wait = self._last_call + min_gap - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()
            headers = {"access-token": await self.token(), "client-id": self.settings.dhan_client_id, "Content-Type": "application/json", "Accept": "application/json"}
            try:
                r = await self._http.post(self.settings.dhan_base_url.rstrip("/") + path, json=body, headers=headers)
            except httpx.HTTPError as e:
                if attempt == 3:
                    raise DhanError(f"{path}: {type(e).__name__}") from None
                await asyncio.sleep(1 + attempt)
                continue
            if r.status_code in (401, 403) and not tried_renew and self.settings.dhan_pin and self.settings.dhan_totp_secret:
                tried_renew = True
                await self.token(force=True)
                continue
            if r.status_code in (401, 403):
                raise DhanError(f"{path}: token refused (HTTP {r.status_code}); a pasted token lasts 24 hours")
            if r.status_code in RETRY_STATUS and attempt < 3:
                await asyncio.sleep(2 ** attempt)
                continue
            if r.status_code != 200:
                raise DhanError(f"{path}: HTTP {r.status_code}")
            try:
                return r.json()
            except ValueError:
                raise DhanError(f"{path}: unreadable answer") from None
        raise DhanError(f"{path}: gave up")

    async def profile(self) -> dict:
        """Account status: token validity and whether the Data API subscription is active (GET /profile). Only the status fields are returned."""
        try:
            r = await self._http.get(self.settings.dhan_base_url.rstrip("/") + "/profile", headers={"access-token": await self.token()})
            body = r.json() if r.status_code == 200 else {}
        except (httpx.HTTPError, ValueError) as e:
            raise DhanError("profile: " + type(e).__name__) from None
        if r.status_code in (401, 403):
            raise DhanError(f"profile: token refused (HTTP {r.status_code})")
        return {k: body.get(k) for k in ("tokenValidity", "activeSegment", "dataPlan", "dataValidity")}

    async def ltp(self, ids: Dict[str, List[int]]) -> Dict[str, Dict[str, float]]:
        """Last traded price for {"NSE_EQ": [security ids]} (at most 1,000 in all): {"NSE_EQ": {"2885": 1420.5}}."""
        if sum(len(v) for v in ids.values()) > 1000:
            raise DhanError("at most 1,000 instruments per request")
        body = await self._post("/marketfeed/ltp", ids, min_gap=1.05)
        out: Dict[str, Dict[str, float]] = {}
        for seg, items in ((body or {}).get("data") or {}).items():
            out[seg] = {k: float(v["last_price"]) for k, v in (items or {}).items() if isinstance(v, dict) and _f(v.get("last_price")) is not None}
        return out

    async def daily(self, security_id: str, segment: str, start: date, end: date, instrument: str = "EQUITY") -> List[dict]:
        """Daily candles from start up to (not including) end: [{"day", "open", "high", "low", "close", "volume"}], oldest first."""
        body = await self._post("/charts/historical", {"securityId": str(security_id), "exchangeSegment": segment, "instrument": instrument,
                                                        "expiryCode": 0, "oi": False, "fromDate": start.isoformat(), "toDate": end.isoformat()})
        ts = (body or {}).get("timestamp") or []
        cols = {k: (body or {}).get(k) or [] for k in ("open", "high", "low", "close", "volume")}
        if not ts or any(len(v) != len(ts) for v in cols.values()):
            return []
        return [{"day": datetime.fromtimestamp(t, IST).date(), **{k: v[i] for k, v in cols.items()}} for i, t in enumerate(ts)]


async def check(settings: Optional[Settings] = None, redis: Any = None) -> dict:
    """Prove the credentials work end to end: token, then RELIANCE's last price and its last few daily candles. Prints no secret."""
    settings = settings or get_settings()
    out: Dict[str, Any] = {"configured": False}
    async with DhanClient(settings, redis) as c:
        if not c.configured:
            out["why"] = "set DHAN_CLIENT_ID with either DHAN_PIN and DHAN_TOTP_SECRET (recommended) or DHAN_ACCESS_TOKEN"
            return out
        out["configured"], out["mode"] = True, "auto-renewing token" if settings.dhan_pin and settings.dhan_totp_secret else "pasted token"
        await c.token()
        out["token"] = "ok"
        out["account"] = await c.profile()
        rows = await fetch_instruments()
        out["instruments"] = len(rows)
        ril = next((r for r in rows if r["exch"] == "NSE" and r["symbol"] == "RELIANCE"), None)
        out["reliance"] = ril
        if ril:
            out["ltp"] = (await c.ltp({"NSE_EQ": [int(ril["security_id"])]})).get("NSE_EQ", {}).get(ril["security_id"])
            today = datetime.now(IST).date()
            out["candles"] = [{**k, "day": k["day"].isoformat()} for k in (await c.daily(ril["security_id"], "NSE_EQ", today - timedelta(days=10), today + timedelta(days=1)))[-3:]]
    return out
