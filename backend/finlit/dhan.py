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
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import httpx

from .config import Settings, get_settings

log = logging.getLogger("finlit.dhan")
logging.getLogger("httpx").setLevel(logging.WARNING)   # its INFO lines print full URLs, and the token call's URL holds the PIN and code
INSTRUMENTS_URL = "https://images.dhan.co/api-data/api-scrip-master-detailed.csv"
TOKEN_KEY = "dhan:token"
VERSION_KEY = "dhan:instruments:ver"   # bumped whenever the instrument file or the company list is reloaded: caches built from the join drop on a new value
SECMAP_KEY = "dhan:secmap"
PACE_KEY = "dhan:pace:quote"     # one market-quote call a second for the whole account, whichever process (web, quotes job, ETF job) makes it
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


def parse_instruments(lines: Iterable[str], indices: Optional[List[dict]] = None, on_row: Optional[Callable[[dict], None]] = None,
                      commodities: Optional[List[dict]] = None) -> List[dict]:
    """Equity rows (NSE and BSE) from the detailed instrument file, each marked with whether the stock has futures (and the lot size).
    Given a list as `indices`, the index rows (segment I, instrument INDEX: quoted under IDX_I) are added to it; they are never equities.
    Given a list as `commodities`, the MCX commodity futures (exchange MCX, instrument FUTCOM: quoted under MCX_COMM) are added to it.

    Streams line by line: the file is about 36 MB and only the equity rows and the futures' underlyings are kept. `on_row` sees every
    row on the way (options.LotCollector keeps the option series' lot sizes from the same pass).
    """
    out: Dict[tuple, dict] = {}
    fut: Dict[str, Tuple[str, int]] = {}     # NSE underlying symbol -> (expiry, lot size) of its nearest futures contract
    for r in csv.DictReader(lines):
        if on_row is not None:
            on_row(r)
        seg, inst, exch = r.get("SEGMENT"), r.get("INSTRUMENT"), r.get("EXCH_ID")
        if seg == "I" and inst == "INDEX" and exch in ("NSE", "BSE"):
            sid, sym = (r.get("SECURITY_ID") or "").strip(), (r.get("SYMBOL_NAME") or "").strip()
            if indices is not None and sid and sym:
                indices.append({"exch": exch, "security_id": sid, "symbol": sym, "name": (r.get("DISPLAY_NAME") or "").strip() or None})
        elif exch == "MCX" and inst == "FUTCOM":
            sid, sym, exp = (r.get("SECURITY_ID") or "").strip(), (r.get("UNDERLYING_SYMBOL") or "").strip(), (r.get("SM_EXPIRY_DATE") or "").strip()[:10]
            if commodities is not None and sid and sym and len(exp) == 10:
                commodities.append({"security_id": sid, "symbol": sym, "display_name": (r.get("DISPLAY_NAME") or "").strip() or sym, "expiry": exp,
                                    "tick_paise": _f(r.get("TICK_SIZE")), "upper": _f(r.get("SM_UPPER_LIMIT")), "lower": _f(r.get("SM_LOWER_LIMIT"))})
        elif exch == "NSE" and seg == "D" and inst == "FUTSTK":
            sym, lot, exp = (r.get("UNDERLYING_SYMBOL") or "").strip(), _f(r.get("LOT_SIZE")), (r.get("SM_EXPIRY_DATE") or "").strip() or "9999"
            if sym and lot and (sym not in fut or exp < fut[sym][0]):   # a revised lot size starts with later expiries: the nearest contract's is today's
                fut[sym] = (exp, int(lot))
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
                "mtf_leverage": mtf if mtf and mtf > 0 else None, "fno": False, "lot_size": None,
                "inst_type": (r.get("INSTRUMENT_TYPE") or "").strip() or None, "exch_name": (r.get("SYMBOL_NAME") or "").strip() or None}
    for row in out.values():
        if row["exch"] == "NSE" and row["symbol"] in fut:
            row["fno"], row["lot_size"] = True, fut[row["symbol"]][1]
    return list(out.values())


async def fetch_instruments(client: Optional[httpx.AsyncClient] = None, indices: Optional[List[dict]] = None,
                            on_row: Optional[Callable[[dict], None]] = None, commodities: Optional[List[dict]] = None) -> List[dict]:
    """Download the file to a temporary file (never all in memory) and read it line by line (index rows into `indices`, MCX futures into
    `commodities`, if given; `on_row` sees every row)."""
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
            return parse_instruments(io.TextIOWrapper(tmp, encoding="utf-8", errors="replace", newline=""), indices, on_row, commodities)
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
                "INSERT INTO dhan_instruments (exch, security_id, symbol, isin, name, series, asm_gsm, asm_gsm_cat, mtf_leverage, fno, lot_size, inst_type, exch_name) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)",
                [(r["exch"], r["security_id"], r["symbol"], r["isin"], r["name"], r["series"], r["asm_gsm"], r["asm_gsm_cat"], r["mtf_leverage"],
                  r["fno"], r["lot_size"], r.get("inst_type"), r.get("exch_name")) for r in rows])
    await bump_version(store)
    return len(rows)


async def save_indices(store, rows: List[dict]) -> int:
    """Replace dhan_indices with the file's index rows (about 190). A short list is refused, as for equities."""
    if len(rows) < 50:
        raise DhanError(f"instrument file looks incomplete ({len(rows)} indices); kept what was stored")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM dhan_indices")
            await conn.executemany("INSERT INTO dhan_indices (exch, security_id, symbol, name) VALUES ($1,$2,$3,$4) ON CONFLICT DO NOTHING",
                                   [(r["exch"], r["security_id"], r["symbol"], r.get("name")) for r in rows])
    return len(rows)


async def save_commodity_contracts(store, rows: List[dict], minimum: int = 100) -> int:
    """Replace dhan_commodity_contracts with the file's MCX futures (about 170). A short list is refused, as for equities: a broken download
    must not leave the commodity page with no contract to price."""
    if len(rows) < minimum:
        raise DhanError(f"instrument file looks incomplete ({len(rows)} MCX futures); kept what was stored")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM dhan_commodity_contracts")
            await conn.executemany(
                "INSERT INTO dhan_commodity_contracts (security_id, symbol, display_name, expiry, tick_paise, upper_limit, lower_limit) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING",
                [(r["security_id"], r["symbol"], r["display_name"], date.fromisoformat(r["expiry"]), r.get("tick_paise"), r.get("upper"), r.get("lower")) for r in rows])
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

    async def _cached(self) -> Optional[Dict[str, Any]]:
        if self.redis is None:
            return None
        try:
            raw = await self.redis.get(TOKEN_KEY)
            return json.loads(raw) if raw else None
        except Exception:
            return None

    async def token(self, force: bool = False) -> str:
        """A token with at least two hours left: generated by the server when PIN and TOTP secret are set, else the pasted one.

        Every process (web, quotes, ETF job) shares one token through Redis, and only one of them makes a new one at a time (a Redis lock):
        a new token may end the old one, so two processes renewing together would keep logging each other out. `force` (after a refusal)
        first takes a newer token another process already made."""
        s = self.settings
        async with self._lock:
            now = time.time()
            used = (self._token or {}).get("token")
            if not force and self._token and self._token["exp"] - now > RENEW_BEFORE:
                return self._token["token"]
            if s.dhan_pin and s.dhan_totp_secret:
                cached = await self._cached()
                if cached and cached["exp"] - now > RENEW_BEFORE and (not force or cached["token"] != used):
                    self._token = cached
                    return cached["token"]
                got = True
                if self.redis is not None:
                    try:
                        got = bool(await self.redis.set(TOKEN_KEY + ":lock", b"1", nx=True, ex=30))
                    except Exception:
                        got = True
                if not got:                                   # another process is making one: wait for it (up to 15 seconds)
                    for _ in range(30):
                        await asyncio.sleep(0.5)
                        cached = await self._cached()
                        if cached and cached["token"] != used and cached["exp"] - time.time() > RENEW_BEFORE:
                            self._token = cached
                            return cached["token"]
                try:
                    self._token = await self._generate()
                    if self.redis is not None:
                        try:
                            await self.redis.set(TOKEN_KEY, json.dumps(self._token), ex=max(60, int(self._token["exp"] - time.time())))
                        except Exception:
                            pass
                finally:
                    if self.redis is not None and got:
                        try:
                            await self.redis.delete(TOKEN_KEY + ":lock")
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
            if min_gap:
                await self._pace(min_gap)
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
                from .jobs.signals import report_refused
                await report_refused(self.settings, "dhan", r.status_code)
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

    async def _pace(self, gap: float) -> None:
        """Dhan's limit is per account, not per process: a Redis key that lives `gap` seconds is the turn to call (waits up to 20 seconds,
        then goes ahead; a 429 is retried anyway). Without Redis only this process's own pacing applies."""
        if self.redis is None:
            return
        for _ in range(200):
            try:
                if await self.redis.set(PACE_KEY, b"1", nx=True, px=int(gap * 1000)):
                    return
            except Exception:
                return
            await asyncio.sleep(0.1)

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

    async def quotes(self, ids: List[Tuple[str, str]]) -> Dict[Tuple[str, str], dict]:
        """Full quotes for [(segment, security id)], 1,000 per call and one call a second: {(segment, id): raw entry}."""
        out: Dict[Tuple[str, str], dict] = {}
        for i in range(0, len(ids), 1000):
            body: Dict[str, List[int]] = {}
            for seg, sid in ids[i:i + 1000]:
                body.setdefault(seg, []).append(int(sid))
            data = (await self._post("/marketfeed/quote", body, min_gap=1.05) or {}).get("data") or {}
            for seg, items in data.items():
                for sid, raw in (items or {}).items():
                    if isinstance(raw, dict):
                        out[(seg, str(sid))] = raw
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

    async def intraday(self, security_id: str, segment: str, interval: int, start: datetime, end: datetime, instrument: str = "EQUITY") -> List[dict]:
        """Minute candles (1, 5, 15, 25 or 60 minutes) from start to end: [{"at", "open", "high", "low", "close", "volume"}], oldest first, where
        "at" is the candle's start in Indian time (+05:30). A time without a zone is read as Indian time. Dhan answers at most 90 days per call:
        a longer span is refused here, before any call. Unequal arrays, as for daily(), mean no data; a candle with a missing price is left out."""
        if interval not in INTRADAY_INTERVALS:
            raise DhanError(f"intraday interval must be one of {', '.join(map(str, INTRADAY_INTERVALS))} minutes")
        s, e = _ist(start), _ist(end)
        if e <= s:
            raise DhanError("intraday: the end is not after the start")
        if e - s > timedelta(days=INTRADAY_MAX_DAYS):
            raise DhanError(f"intraday: at most {INTRADAY_MAX_DAYS} days per request")
        body = await self._post("/charts/intraday", {"securityId": str(security_id), "exchangeSegment": segment, "instrument": instrument,
                                                      "interval": interval, "oi": False, "fromDate": s.strftime("%Y-%m-%d %H:%M:%S"),
                                                      "toDate": e.strftime("%Y-%m-%d %H:%M:%S")}, min_gap=0.2)
        ts = (body or {}).get("timestamp") or []
        cols = {k: (body or {}).get(k) or [] for k in ("open", "high", "low", "close", "volume")}
        if not ts or any(len(v) != len(ts) for v in cols.values()):
            return []
        out: Dict[float, dict] = {}
        for i, t in enumerate(ts):
            at, px = _f(t), [_f(cols[k][i]) for k in ("open", "high", "low", "close")]
            if at is None or any(p is None or p <= 0 for p in px):
                continue
            vol = _f(cols["volume"][i])
            out[at] = {"at": datetime.fromtimestamp(at, IST), "open": px[0], "high": px[1], "low": px[2], "close": px[3],
                       "volume": int(vol) if vol is not None and vol >= 0 else None}
        return [out[k] for k in sorted(out)]


INTRADAY_INTERVALS = (1, 5, 15, 25, 60)
INTRADAY_MAX_DAYS = 90


def _ist(t: datetime) -> datetime:
    """Indian time, to the second: a time without a zone is taken as Indian time already."""
    return (t.replace(tzinfo=IST) if t.tzinfo is None else t.astimezone(IST)).replace(microsecond=0)


# ------------------------------------------------------------------------------------------------------------------ live quotes

EQUITY_SERIES = ("EQ", "BE", "BZ", "SM", "ST", "SZ")    # share series; a symbol can also carry bonds (N1..), warrants (W1) or debentures (D1)


# How a company is matched to its one Dhan row: the NSE share by trading symbol, else the BSE share by scrip code (Dhan's BSE security id is
# the BSE code). Shared by the live quotes and the stock page's trading facts, so both always describe the same instrument.
MATCH_SQL = (
    "FROM companies c "
    "LEFT JOIN dhan_instruments n ON n.exch = 'NSE' AND n.symbol = c.nse_code AND c.nse_code <> '' "
    "LEFT JOIN dhan_instruments b ON b.exch = 'BSE' AND b.security_id = c.bse_code AND c.bse_code <> '' "
    "WHERE c.symbol = ANY($1::text[]) AND (n.security_id IS NOT NULL OR b.security_id IS NOT NULL) "
    "ORDER BY c.symbol, (n.series = ANY($2::text[])) DESC NULLS LAST, (n.series = 'EQ') DESC NULLS LAST, (b.series = ANY($2::text[])) DESC NULLS LAST")
INFO_COLS = ("exch", "security_id", "series", "asm_gsm", "asm_gsm_cat", "mtf_leverage", "fno", "lot_size", "loaded_at")


async def instruments_version(store) -> str:
    """The stamp the instrument/company reloads bump; "" when Redis has none or is down (nothing is then cached by it)."""
    try:
        v = await store.redis.get(VERSION_KEY)
    except Exception:
        return ""
    return v.decode() if isinstance(v, bytes) else (v or "")


async def bump_version(store) -> None:
    try:
        await store.redis.incr(VERSION_KEY)
    except Exception:
        log.warning("instrument version not bumped: caches built from the file expire on their own")


async def security_map(store, symbols: List[str]) -> Dict[str, Tuple[str, str]]:
    """{our symbol: (Dhan segment, security id)}. Companies with no match are left out (renamed or delisted: they keep the main provider's quote).
    The join over companies and the whole instrument file is read once per reload of the file (VERSION_KEY): the quotes job runs every minute and the answer
    only changes with the file. A company with no match is remembered as such, so it is not asked again every minute."""
    if not symbols:
        return {}
    ver = await instruments_version(store)
    known: Dict[str, Any] = {}
    try:
        raw = await store.redis.get(SECMAP_KEY)
        got = json.loads(raw) if raw else None
        if got and got.get("ver") == ver:
            known = got["map"]
    except Exception:
        known = {}
    missing = [s for s in symbols if s not in known]
    if missing:
        async with store.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT DISTINCT ON (c.symbol) c.symbol, COALESCE(n.security_id, b.security_id) AS sid, "
                "CASE WHEN n.security_id IS NOT NULL THEN 'NSE_EQ' ELSE 'BSE_EQ' END AS seg " + MATCH_SQL, missing, list(EQUITY_SERIES))
        found = {r["symbol"]: [r["seg"], r["sid"]] for r in rows}
        known.update({s: found.get(s) for s in missing})
        try:   # 6 hours: the backstop for a bump that could not be recorded
            await store.redis.set(SECMAP_KEY, json.dumps({"ver": ver, "map": known}), ex=6 * 3600)
        except Exception:
            pass
    return {s: (known[s][0], known[s][1]) for s in symbols if known.get(s)}


async def fno_flags(store, symbols: List[str]) -> Dict[str, bool]:
    """{our symbol: on F&O} for the companies matched on NSE, where the contracts are. Only these two columns leave the database, not the whole instrument row."""
    if not symbols:
        return {}
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ON (c.symbol) c.symbol, (n.security_id IS NOT NULL) AS nse, CASE WHEN n.security_id IS NOT NULL THEN n.fno ELSE b.fno END AS fno " + MATCH_SQL,
            list(symbols), list(EQUITY_SERIES))
    return {r["symbol"]: bool(r["fno"]) for r in rows if r["nse"]}


async def instrument_rows(store, symbols: List[str]) -> Dict[str, dict]:
    """{our symbol: its matched Dhan row (INFO_COLS)}, the row security_map picks."""
    if not symbols:
        return {}
    cols = ", ".join(f"CASE WHEN n.security_id IS NOT NULL THEN n.{k} ELSE b.{k} END AS {k}" for k in INFO_COLS)
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(f"SELECT DISTINCT ON (c.symbol) c.symbol, {cols} " + MATCH_SQL, list(symbols), list(EQUITY_SERIES))  # nosec B608 - fixed column names
    return {r["symbol"]: dict(r) for r in rows}


def trading_facts(row: Optional[dict]) -> dict:
    """What the stock page says about trading the share, from its Dhan row. Only what is positively there is given:
      * surveillance only when the flag is Y. N is never turned into "not under surveillance" (the file may not carry every exchange list),
        and R (Dhan: "removed from block") is not shown: the shares flagged R trade on restricted series (BE, BZ, ST) all the same;
      * F&O (NSE) with the lot size of the nearest futures contract;
      * margin trading (Dhan's own list) only above 1x, since 1x lends nothing. Rounded down to one decimal, so "up to" never overstates it."""
    if not row:
        return {"matched": False}
    lev = row.get("mtf_leverage")
    lev = int(lev * 10 + 1e-6) / 10 if lev is not None and lev > 0 else None
    at = row.get("loaded_at")
    return {
        "matched": True, "exchange": row.get("exch"), "asOf": at.astimezone(IST).date().isoformat() if isinstance(at, datetime) else None,
        "surveillance": {"stage": row.get("asm_gsm_cat")} if row.get("asm_gsm") == "Y" else None,
        "fno": {"lotSize": row.get("lot_size")} if row.get("fno") and row.get("exch") == "NSE" else None,
        "mtf": {"leverage": lev} if lev is not None and lev > 1 else None,
    }


def _trade_time(text: Any) -> Optional[str]:
    """Dhan's "23/10/2026 15:29:58" (Indian time) as ISO with +05:30; its "01/01/1980 00:00:00" placeholder means no trade."""
    try:
        t = datetime.strptime(str(text).strip(), "%d/%m/%Y %H:%M:%S")
    except ValueError:
        return None
    return None if t.year < 2000 else t.replace(tzinfo=IST).isoformat()


def to_quote(raw: dict) -> dict:
    """One /marketfeed/quote entry in the shape of the report's quote (normalize.market.quote). Zeros Dhan sends for "no trade yet" are
    left out, never shown as prices; 52-week range and market cap are not in this feed and are left to the caller."""
    price = _f(raw.get("last_price"))
    if not price or price <= 0:
        return {}
    change = _f(raw.get("net_change"))
    prev = round(price - change, 2) if change is not None else None
    ohlc = raw.get("ohlc") if isinstance(raw.get("ohlc"), dict) else {}
    pos = lambda v: round(v, 2) if (v := _f(v)) and v > 0 else None   # noqa: E731
    vol = _f(raw.get("volume"))
    return {
        "price": round(price, 2), "change": round(change, 2) if change is not None and prev else None, "previousClose": prev if prev and prev > 0 else None,
        "changePct": round(change / prev * 100, 2) if change is not None and prev and prev > 0 else None,
        "open": pos(ohlc.get("open")), "high": pos(ohlc.get("high")), "low": pos(ohlc.get("low")),
        "volume": int(vol) if vol and vol > 0 else None, "upperCircuit": pos(raw.get("upper_circuit_limit")), "lowerCircuit": pos(raw.get("lower_circuit_limit")),
        "asOf": _trade_time(raw.get("last_trade_time")),
    }


def plausible(new: dict, old: dict, limit: float = 0.25) -> bool:
    """A Dhan quote is used only if its previous close is within 25% of the price we already hold: a wrong company match, or a split the
    report has not caught up with, falls back to the main provider instead of showing a wrong price."""
    ref = old.get("previousClose") or old.get("price")
    base = new.get("previousClose") or new.get("price")
    if not ref or not base:
        return True
    return abs(base / ref - 1) <= limit


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
        out["commodity_segment"] = "commodity" in str((out["account"] or {}).get("activeSegment") or "").lower()   # the commodity page needs MCX activated (error DH-903 otherwise)
        rows = await fetch_instruments()
        out["instruments"] = len(rows)
        ril = next((r for r in rows if r["exch"] == "NSE" and r["symbol"] == "RELIANCE"), None)
        out["reliance"] = ril
        if ril:
            out["ltp"] = (await c.ltp({"NSE_EQ": [int(ril["security_id"])]})).get("NSE_EQ", {}).get(ril["security_id"])
            today = datetime.now(IST).date()
            out["candles"] = [{**k, "day": k["day"].isoformat()} for k in (await c.daily(ril["security_id"], "NSE_EQ", today - timedelta(days=10), today + timedelta(days=1)))[-3:]]
    return out
