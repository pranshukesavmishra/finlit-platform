"""The screener's in-memory table: one column of numbers per filter, so any filter combination answers in milliseconds.

Loaded from the `scores` table (+ index membership and score history); the rows are cached (see below), not re-read. Every listed company is in it: the ones whose full
report is stored carry all their figures; the rest carry what the nightly listing refresh stores (price, market cap, day change, 52-week range, volume)
and nothing else, so every other figure is unknown (a dash) for them and they are left out of a filter only when that filter is on a figure they lack. A column is a list of floats with
NaN where a value is unknown; a company with an unknown value never matches a filter on it (it is not guessed).
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import time
import zlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import asyncpg
import orjson

from .. import dhan
from ..advanced.catalog import METRIC_LIST as AX_METRICS
from ..advanced.derive import AGG_GROWTH, COMPONENTS
from .catalog import BY_KEY, CAPS, CATALOG, INDEX_LISTS
from .compute import METRICS_VERSION, MULTIPLES
from .listing import metrics_of

NAN = float("nan")
# advanced-chart figures (advanced/derive.py), plus the stored amounts behind them that index aggregates are summed from
AX_COLS = sorted({m.col for m in AX_METRICS if m.col.startswith("ax_")} | {f"ax_c_{c}" for c in COMPONENTS}
                 | {f"ax_{p}_{g}" for g in AGG_GROWTH for p in ("gc", "gp")})
log = logging.getLogger("finlit.screener")
# How the table stays current without re-reading the database (Neon bills every byte it sends: the full table is tens of megabytes, docs/NEON-EGRESS.md).
# The raw rows are kept compressed in Redis and in memory; a check is one tiny probe query, and only the rows that changed are fetched.
MARKET_GAP = 1800        # seconds between checks while the market is open: the live-quote job rewrites about 500 rows a minute, so prices here can be this old
OFF_GAP = 600            # outside market hours a check is a probe of a few bytes; rows are fetched only if it says something changed (the nightly jobs)
RECONCILE_EVERY = 6 * 3600   # also re-reads the symbol list (drops pruned companies, adds new ones), the companies, listing, index and score-history extras
FULL_EVERY = 7 * 86400   # every row again from Postgres (tens of MB): only a safety net, as every writer stamps changed_at
MARGIN = 120             # seconds of overlap on "changed since", for a transaction that committed after a later one
CACHE_KEY = "screener:rows"
CACHE_TTL = 7 * 86400
FORMAT = 1
IST = timezone(timedelta(hours=5, minutes=30))
# Columns kept on the old scores table before metrics existed: used until a company's metrics are rebuilt.
LEGACY = {"market_cap": "market_cap", "price": "price", "pe": "pe", "pb": "pb", "roe": "roe", "roce": "roce", "dividend_yield": "dividend_yield",
          "debt_to_equity": "debt_to_equity", "sales_cagr_5y": "sales_cagr", "profit_cagr_5y": "profit_cagr", "operating_margin": "operating_margin",
          "ret_1d": "change_pct", "ret_1m": "return_1m", "ret_1y": "return_1y", "overall": "overall", "pillar_quality": "pillar_quality",
          "pillar_growth": "pillar_growth", "pillar_profitability": "pillar_profitability", "pillar_balance": "pillar_balance", "pillar_technical": "pillar_technical"}


def _num(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return NAN
    return f if math.isfinite(f) else NAN


def _median(xs: List[float]) -> float:
    xs = sorted(x for x in xs if x == x)
    n = len(xs)
    return NAN if not n else (xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2)


def _pct(sorted_xs: List[float], p: float) -> float:
    return sorted_xs[min(len(sorted_xs) - 1, int(p * (len(sorted_xs) - 1)))]


class Table:
    def __init__(self, rows: List[dict], members: Dict[str, List[str]], score_move: Dict[str, float], fno: Optional[Dict[str, bool]] = None):
        self.loaded = time.time()
        self.symbols: List[str] = []
        self.name: List[str] = []
        self.sector: List[Optional[str]] = []
        self.industry: List[Optional[str]] = []
        self.band: List[Optional[str]] = []
        self.full: List[bool] = []   # True: the company's full report is stored; False: only the light listing row (quote figures)
        self.cols: Dict[str, List[float]] = {m.key: [] for m in CATALOG}
        # advanced charts: ax_* columns, the financial year they are for, why a value is missing, and whether the row has them at all
        self.ax: Dict[str, List[float]] = {c: [] for c in AX_COLS}
        self.ax_fy: List[Optional[str]] = []
        self.ax_sig_fy: List[Optional[str]] = []
        self.ax_miss: List[Dict[str, str]] = []
        self.ax_ready: List[bool] = []
        self.q_end: List[float] = []   # the quarter-end (yyyymmdd) the company's q_* figures are for; NaN when not stored
        for r in rows:
            raw = r.get("metrics")
            m: Dict[str, Any] = json.loads(raw) if isinstance(raw, str) else (raw or {})
            self.symbols.append(r["symbol"])
            self.name.append(r.get("name") or r["symbol"])
            self.sector.append(r.get("macro_sector") or r.get("sector"))
            self.industry.append(r.get("industry"))
            self.band.append(r.get("band"))
            self.full.append(bool(r.get("full", True)))
            for k, col in self.cols.items():
                v = m.get(k)
                if v is None and k in LEGACY and not m:
                    v = r.get(LEGACY[k])
                v = _num(v)
                col.append(NAN if v == v and k in MULTIPLES and v <= 0 else v)
            for k, col in self.ax.items():
                col.append(_num(m.get(k)))
            self.q_end.append(_num(m.get("q_period_end")))
            self.ax_fy.append(m.get("ax_fy") if isinstance(m.get("ax_fy"), str) else None)
            self.ax_sig_fy.append(m.get("ax_sig_fy") if isinstance(m.get("ax_sig_fy"), str) else None)
            self.ax_miss.append(m.get("ax_miss") if isinstance(m.get("ax_miss"), dict) else {})
            self.ax_ready.append(isinstance(m.get("ax_miss"), dict) and _num(m.get("m_ver")) >= METRICS_VERSION)
        n = len(self.symbols)
        self.n = n
        self.n_full = sum(self.full)
        self.pos = {s: i for i, s in enumerate(self.symbols)}
        # size bucket by SEBI's rule: the 100 largest are Large, the next 150 Mid, the rest Small
        order = sorted((i for i in range(n) if self.cols["market_cap"][i] == self.cols["market_cap"][i] and self.cols["market_cap"][i] > 0), key=lambda i: -self.cols["market_cap"][i])
        self.cap: List[Optional[str]] = [None] * n
        for rank, i in enumerate(order):
            self.cap[i] = CAPS[0] if rank < 100 else CAPS[1] if rank < 250 else CAPS[2]
        # against-the-sector valuation
        by_sector: Dict[str, List[int]] = {}
        for i, s in enumerate(self.sector):
            if s:
                by_sector.setdefault(s, []).append(i)
        for key, src in (("pe_vs_sector", "pe"), ("pb_vs_sector", "pb")):
            for s, idx in by_sector.items():
                vals = [self.cols[src][i] for i in idx if self.cols[src][i] == self.cols[src][i] and self.cols[src][i] > 0]
                med = _median(vals) if len(vals) >= 5 else NAN
                for i in idx:
                    v = self.cols[src][i]
                    if med == med and med > 0 and v == v and v > 0:
                        self.cols[key][i] = (v - med) / med * 100
        for sym, d in score_move.items():
            if sym in self.pos:
                self.cols["score_change"][self.pos[sym]] = d
        for sym, on in (fno or {}).items():   # companies Dhan's file does not match stay unknown, never "no"
            if sym in self.pos:
                self.cols["fno"][self.pos[sym]] = 1.0 if on else 0.0
        self.members: Dict[str, set] = {code: {s for s in syms if s in self.pos} for code, syms in members.items()}
        # facets and per-filter ranges for the filter panel
        self.sectors = self._facet(self.sector)
        self.industries: List[Tuple[str, Optional[str], int]] = []
        seen: Dict[str, Tuple[Optional[str], int]] = {}
        for sec, ind in zip(self.sector, self.industry):
            if ind:
                s0, c = seen.get(ind, (sec, 0))
                seen[ind] = (s0, c + 1)
        self.industries = sorted(((k, v[0], v[1]) for k, v in seen.items()), key=lambda t: t[0])
        self.stats: Dict[str, dict] = {}
        for k, col in self.cols.items():
            xs = sorted(x for x in col if x == x)
            if xs:
                lo, hi = _pct(xs, .02), _pct(xs, .98)    # the bars and slider cover the middle 96%: a few extreme values must not squash the rest
                if hi <= lo:
                    lo, hi = xs[0], xs[-1]
                bins = 28
                counts = [0] * bins
                if hi > lo:
                    for x in xs:
                        counts[min(bins - 1, max(0, int((x - lo) / (hi - lo) * bins)))] += 1
                self.stats[k] = {"min": xs[0], "p10": _pct(xs, .1), "p50": _pct(xs, .5), "p90": _pct(xs, .9), "max": xs[-1], "n": len(xs),
                                 "lo": lo, "hi": hi, "hist": counts}

    def latest_quarter(self, at_least: int = 25) -> Optional[int]:
        """The newest quarter-end (yyyymmdd) that at least `at_least` companies have reported: the quarter now being reported. None when the table cannot tell."""
        counts: Dict[int, int] = {}
        for q in self.q_end:
            if q == q:
                counts[int(q)] = counts.get(int(q), 0) + 1
        good = [q for q, c in counts.items() if c >= at_least]
        return max(good) if good else None

    @staticmethod
    def _facet(vals: List[Optional[str]]) -> List[Tuple[str, int]]:
        c: Dict[str, int] = {}
        for v in vals:
            if v:
                c[v] = c.get(v, 0) + 1
        return sorted(c.items(), key=lambda t: t[0])

    # ------------------------------------------------------------------ query
    def match(self, filters: Dict[str, Dict[str, Optional[float]]], cats: Dict[str, List[str]], q: str = "") -> List[int]:
        idx = range(self.n)
        for key, rg in filters.items():
            col, lo, hi = self.cols[key], rg.get("min"), rg.get("max")
            if BY_KEY[key].unit == "flag":  # yes/no: min 1 = only "yes", max 0 = only "no"
                idx = [i for i in idx if col[i] == col[i] and (lo is None or col[i] >= lo) and (hi is None or col[i] <= hi)]
            else:
                idx = [i for i in idx if col[i] == col[i] and (lo is None or col[i] >= lo) and (hi is None or col[i] <= hi)]
        if cats.get("sector"):
            want = set(cats["sector"]); idx = [i for i in idx if self.sector[i] in want]
        if cats.get("industry"):
            want = set(cats["industry"]); idx = [i for i in idx if self.industry[i] in want]
        if cats.get("cap"):
            want = set(cats["cap"]); idx = [i for i in idx if self.cap[i] in want]
        if cats.get("band"):
            want = set(cats["band"]); idx = [i for i in idx if self.band[i] in want]
        if cats.get("index"):
            allowed = set().union(*(self.members.get(c, set()) for c in cats["index"]))
            idx = [i for i in idx if self.symbols[i] in allowed]
        if q:
            t = q.strip().lower()
            idx = [i for i in idx if t in self.symbols[i].lower() or t in self.name[i].lower()]
        return list(idx)

    def sort(self, idx: List[int], key: str, desc: bool) -> List[int]:
        if key == "name":
            return sorted(idx, key=lambda i: self.name[i].lower(), reverse=desc)
        if key == "symbol":
            return sorted(idx, key=lambda i: self.symbols[i], reverse=desc)
        col = self.cols[key]
        known = [i for i in idx if col[i] == col[i]]
        rest = [i for i in idx if col[i] != col[i]]   # unknowns always last
        return sorted(known, key=lambda i: col[i], reverse=desc) + rest

    def row(self, i: int, columns: List[str]) -> dict:
        return {"symbol": self.symbols[i], "name": self.name[i], "sector": self.sector[i], "cap": self.cap[i], "band": self.band[i], "full": self.full[i],
                "v": {k: (None if self.cols[k][i] != self.cols[k][i] else round(self.cols[k][i], 4)) for k in columns}}


_table: Optional[Table] = None
_blob: Optional[bytes] = None    # the compressed raw rows behind _table (the same bytes as in Redis): kept instead of the parsed rows, which would take ~150 MB
_lock = asyncio.Lock()
_lock_loop: Any = None
_refreshing: Optional[asyncio.Task] = None
SCORE_COLS = ("symbol", "name", "sector", "macro_sector", "industry", "band", "metrics") + tuple(sorted(set(LEGACY.values())))
QUOTE_COLS = ("price", "change_pct", "market_cap", "high52", "low52", "volume")


def _the_lock() -> asyncio.Lock:
    """One lock per event loop: tests start a new loop each, and a lock left held by a task of a finished one must not block the next."""
    global _lock, _lock_loop
    loop = asyncio.get_running_loop()
    if _lock_loop is not loop:
        _lock, _lock_loop = asyncio.Lock(), loop
    return _lock


def _plain(r: Any) -> dict:
    """A database row as plain JSON-able values (numbers as floats: the table reads them with float() anyway). The metrics stay the JSON text the database
    sent: as parsed objects they would take four times the memory (the free server has 512 MB), and the table parses them row by row."""
    return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in dict(r).items()}


def _iso(v: Optional[datetime]) -> Optional[str]:
    return v.isoformat() if v else None


def in_market_hours(now: Optional[float] = None) -> bool:
    t = datetime.fromtimestamp(now if now is not None else time.time(), IST)
    return t.weekday() < 5 and 9 <= t.hour <= 15   # the hours the quote job runs


async def _probe(store) -> dict:
    """What decides whether anything changed: a few bytes."""
    async with store.pool.acquire() as conn:
        r = await conn.fetchrow(
            "SELECT (SELECT count(*) FROM scores WHERE model = 'v1') AS n, (SELECT max(changed_at) FROM scores WHERE model = 'v1') AS at, "
            "(SELECT count(*) FROM listing_quotes) AS lq, (SELECT max(updated_at) FROM listing_quotes) AS lat")
    return {"n": r["n"], "at": _iso(r["at"]), "lq": r["lq"], "lat": _iso(r["lat"])}


async def _score_rows(store, symbols: Optional[List[str]] = None, since: Optional[datetime] = None) -> Dict[str, dict]:
    """The row the table uses per symbol. DISTINCT ON prefers the consolidated statement, so a changed standalone row is judged against its sibling:
    the symbols that changed are picked first and ALL their rows are ranked again."""
    sql = f"SELECT DISTINCT ON (symbol) {', '.join(SCORE_COLS)} FROM scores WHERE model = 'v1'"  # nosec B608 - fixed column names
    args: list = []
    if since is not None:
        sql += " AND symbol IN (SELECT symbol FROM scores WHERE model = 'v1' AND changed_at > $1)"
        args = [since]
    elif symbols is not None:
        sql += " AND symbol = ANY($1::text[])"
        args = [symbols]
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(sql + " ORDER BY symbol, (statement = 'consolidated') DESC, updated_at DESC", *args)
    return {r["symbol"]: _plain(r) for r in rows}


async def _listing(store, state: dict) -> None:
    """Companies with no score (name, sector from the symbol list) and every company's nightly listing figures: both change a night at a time."""
    async with store.pool.acquire() as conn:
        light = await conn.fetch("SELECT c.symbol, c.name, c.sector, c.industry FROM companies c "
                                 "WHERE NOT EXISTS (SELECT 1 FROM scores s WHERE s.symbol = c.symbol AND s.model = 'v1') ORDER BY c.symbol")
        lq = await conn.fetch(f"SELECT symbol, {', '.join(QUOTE_COLS)} FROM listing_quotes")  # nosec B608 - fixed column names
    state["light"] = {r["symbol"]: _plain(r) for r in light}
    state["lq"] = {r["symbol"]: {k: v for k, v in _plain(r).items() if k != "symbol"} for r in lq}


async def _extras(store, state: dict) -> None:
    """Index membership and the 80-day score move: rows that change a day at a time."""
    mem: Dict[str, List[str]] = {}
    move: Dict[str, float] = {}
    async with store.pool.acquire() as conn:
        for r in await conn.fetch("SELECT index_code, symbol FROM index_members"):
            mem.setdefault(r["index_code"], []).append(r["symbol"])
        for r in await conn.fetch(
                "SELECT DISTINCT ON (h.symbol) h.symbol, s.overall - h.overall AS d FROM score_history h JOIN scores s ON s.symbol = h.symbol AND s.model = h.model "
                "WHERE h.model = 'v1' AND h.day <= current_date - 80 AND h.overall IS NOT NULL AND s.overall IS NOT NULL ORDER BY h.symbol, h.day DESC"):
            move[r["symbol"]] = float(r["d"])
    state["mem"], state["move"] = mem, move
    await _listing(store, state)


async def _fno(store, state: dict, symbols: Optional[List[str]] = None) -> None:
    """F&O from Dhan's daily instrument file, joined here rather than stored with the figures: it changes with the exchange's list, not the report.
    Known only for a company matched on NSE (where the contracts are): one matched by its BSE code alone stays unknown, never "no"."""
    got = await dhan.fno_flags(store, symbols if symbols is not None else sorted({*state["rows"], *state["light"]}))
    state["fno"] = {**(state["fno"] if symbols is not None else {}), **got}
    if symbols is None:
        state["ver"] = await dhan.instruments_version(store)


async def _full(store, now: float) -> dict:
    try:
        probe: Optional[dict] = await _probe(store)   # before the rows: a change made while they are read is then fetched again next time
    except asyncpg.UndefinedColumnError:   # the migration that adds changed_at has not run: every check is a full read, as before
        probe = None
    state: Dict[str, Any] = {"fmt": FORMAT, "full_at": now, "recon_at": now, "sig": probe, "fno": {}, "ver": ""}
    state["rows"] = await _score_rows(store)
    await _extras(store, state)
    await _fno(store, state)
    return state


async def _reconcile(store, state: dict) -> None:
    async with store.pool.acquire() as conn:
        live = {r["symbol"] for r in await conn.fetch("SELECT DISTINCT symbol FROM scores WHERE model = 'v1'")}
    for s in [s for s in state["rows"] if s not in live]:   # pruned companies
        del state["rows"][s]
    absent = sorted(live - state["rows"].keys())
    if absent:
        state["rows"].update(await _score_rows(store, symbols=absent))
    await _extras(store, state)
    await _fno(store, state)


async def _delta(store, state: dict, since: datetime) -> None:
    got = await _score_rows(store, since=since)
    new = [s for s in got if s not in state["rows"] and s not in state["light"]]
    for s in got:
        state["light"].pop(s, None)   # a company that has just been scored leaves the listing-only rows
    state["rows"].update(got)
    if new:
        await _fno(store, state, new)


async def _catch_up(store, state: dict, probe: dict, now: float) -> bool:
    """Bring the saved rows up to date by the smallest read that is enough. True when anything changed."""
    sig, changed = state["sig"], False
    deleted = probe["at"] == sig["at"] and probe["n"] != sig["n"]   # rows went and none were written: a prune
    if now - state["recon_at"] >= RECONCILE_EVERY or deleted:
        await _reconcile(store, state)
        state["recon_at"], changed = now, True
    else:
        if probe["at"] != sig["at"]:
            await _delta(store, state, datetime.fromisoformat(sig["at"]) - timedelta(seconds=MARGIN) if sig["at"] else datetime.fromtimestamp(0, timezone.utc))
            changed = True
        if (probe["lq"], probe["lat"]) != (sig["lq"], sig["lat"]):
            await _listing(store, state)
            changed = True
        if await dhan.instruments_version(store) != state["ver"]:
            await _fno(store, state)
            changed = True
    state["sig"] = probe
    return changed


def _pack(state: dict) -> bytes:
    return zlib.compress(orjson.dumps(state), 6)


def _unpack(blob: bytes) -> dict:
    return orjson.loads(zlib.decompress(blob))


def _build(state: dict) -> Table:
    rows = [state["rows"][s] for s in sorted(state["rows"])]
    lq = state["lq"]
    for i, r in enumerate(rows):   # a stored report that lacks the price or market cap (half-loaded) takes them from the listing row, where we hold them
        q, raw = lq.get(r["symbol"]), r.get("metrics")
        if not q or not raw or (isinstance(raw, str) and '"price"' in raw and '"market_cap"' in raw and "null" not in raw):
            continue   # (a report that holds both figures, and no null, needs no parsing to know it needs nothing)
        m = json.loads(raw) if isinstance(raw, str) else raw
        if m and any(m.get(k) is None and q.get(k) is not None for k in ("price", "market_cap")):
            rows[i] = {**r, "metrics": {**m, **{k: float(q[k]) for k in ("price", "market_cap") if m.get(k) is None and q.get(k) is not None}}}
    light = [with_listing({**r, **{k: lq.get(r["symbol"], {}).get(k) for k in QUOTE_COLS}}) for r in state["light"].values()]
    return Table(rows + light, state["mem"], state["move"], state["fno"])


async def _load(store) -> Table:
    """Every row from Postgres, no cache read or written."""
    return _build(await _full(store, time.time()))


async def _sync(store, force: bool = False) -> None:
    """Make `_table` current. Cheapest first: nothing changed (one probe); some rows changed (those rows only); a cache gone or old (everything).
    `force` ignores the saved rows and reads everything."""
    global _table, _blob
    now = time.time()
    key = f"{CACHE_KEY}:{getattr(store, 'db_tag', '')}"   # a different database (a new Neon project) never reuses another one's rows
    state, blob = None, None
    if not force:
        blob = _blob
        if blob is None:
            try:
                blob = await store.redis.get(key)
            except Exception:   # Redis missing or busy: Postgres has everything
                log.warning("screener rows not read from Redis; reading Postgres")
        if blob:
            try:
                state = await asyncio.to_thread(_unpack, blob)
            except Exception:
                state = None
            if state and (state.get("fmt") != FORMAT or not state.get("sig") or now - state["full_at"] >= FULL_EVERY):
                state = None
            if state:
                _blob = blob
    changed = persist = True
    if state is not None:
        try:
            probe = await _probe(store)
        except asyncpg.UndefinedColumnError:
            probe = None
        if probe is None or (probe["at"] and state["sig"]["at"] and probe["at"] < state["sig"]["at"]) or (probe["n"] == 0 and state["sig"]["n"]):
            state = None   # the database is not the one the rows came from (restored, replaced): start again
        else:
            changed = await _catch_up(store, state, probe, now)
            persist = state["recon_at"] == now   # Redis gets the rows after a full read or a reconcile, not after each delta: 8-13 MB written every 30 minutes would push the other keys out of a small Redis
    if state is None:
        state = await _full(store, now)
    if changed or _table is None:
        _table = await asyncio.to_thread(_build, state)
    else:
        _table.loaded = now   # nothing moved: the table in memory is as current as a new one would be
    if changed:
        _blob = await asyncio.to_thread(_pack, state)
        if persist:
            try:
                await store.redis.set(key, _blob, ex=CACHE_TTL)
            except Exception:
                log.warning("screener rows not saved to Redis")


def with_listing(r: dict) -> dict:
    """Row shape the Table reads. A company with no stored report gets its quote figures only (`full` False); no figure is ever made up."""
    return {"symbol": r["symbol"], "name": r.get("name"), "sector": r.get("sector"), "industry": r.get("industry"), "band": None, "full": False,
            "metrics": metrics_of(r)}


async def _refresh(store) -> None:
    async with _the_lock():
        try:
            await _sync(store)
        except Exception:
            log.exception("screener table not refreshed; the last one is kept")


async def get_table(store, force: bool = False) -> Table:
    """The in-memory table. Only the very first request after a start waits for it; after that an old table is served at once
    while a check runs in the background (stale-while-revalidate), so no visitor waits on the database."""
    global _refreshing
    if _table and not force:
        gap = MARKET_GAP if in_market_hours() else OFF_GAP
        if time.time() - _table.loaded >= gap and (_refreshing is None or _refreshing.done()):
            _refreshing = asyncio.create_task(_refresh(store))
        return _table
    async with _the_lock():
        if _table is None or force:
            await _sync(store, force)
    return _table  # type: ignore[return-value]


def reset() -> None:
    global _table, _blob
    _table = _blob = None
