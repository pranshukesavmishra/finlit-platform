"""The screener's in-memory table: one column of numbers per filter, so any filter combination answers in milliseconds.

Loaded from the `scores` table (+ index membership and score history) and kept for a few minutes. A column is a list of floats with
NaN where a value is unknown; a company with an unknown value never matches a filter on it (it is not guessed).
"""

from __future__ import annotations

import asyncio
import json
import math
import time
from typing import Any, Dict, List, Optional, Tuple

from .catalog import BY_KEY, CAPS, CATALOG, INDEX_LISTS
from .compute import MULTIPLES

NAN = float("nan")
TTL = 180
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
    def __init__(self, rows: List[dict], members: Dict[str, List[str]], score_move: Dict[str, float]):
        self.loaded = time.time()
        self.symbols: List[str] = []
        self.name: List[str] = []
        self.sector: List[Optional[str]] = []
        self.industry: List[Optional[str]] = []
        self.band: List[Optional[str]] = []
        self.cols: Dict[str, List[float]] = {m.key: [] for m in CATALOG}
        for r in rows:
            raw = r.get("metrics")
            m: Dict[str, Any] = json.loads(raw) if isinstance(raw, str) else (raw or {})
            self.symbols.append(r["symbol"])
            self.name.append(r.get("name") or r["symbol"])
            self.sector.append(r.get("macro_sector") or r.get("sector"))
            self.industry.append(r.get("industry"))
            self.band.append(r.get("band"))
            for k, col in self.cols.items():
                v = m.get(k)
                if v is None and k in LEGACY and not m:
                    v = r.get(LEGACY[k])
                v = _num(v)
                col.append(NAN if v == v and k in MULTIPLES and v <= 0 else v)
        n = len(self.symbols)
        self.n = n
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
        return {"symbol": self.symbols[i], "name": self.name[i], "sector": self.sector[i], "cap": self.cap[i], "band": self.band[i],
                "v": {k: (None if self.cols[k][i] != self.cols[k][i] else round(self.cols[k][i], 4)) for k in columns}}


_table: Optional[Table] = None
_lock = asyncio.Lock()


async def get_table(store, force: bool = False) -> Table:
    global _table
    if _table and not force and time.time() - _table.loaded < TTL:
        return _table
    async with _lock:
        if _table and not force and time.time() - _table.loaded < TTL:
            return _table
        async with store.pool.acquire() as conn:
            rows = [dict(r) for r in await conn.fetch(
                "SELECT DISTINCT ON (symbol) * FROM scores WHERE model = 'v1' ORDER BY symbol, (statement = 'consolidated') DESC, updated_at DESC")]
            mem: Dict[str, List[str]] = {}
            for r in await conn.fetch("SELECT index_code, symbol FROM index_members"):
                mem.setdefault(r["index_code"], []).append(r["symbol"])
            move: Dict[str, float] = {}
            for r in await conn.fetch(
                    "SELECT DISTINCT ON (h.symbol) h.symbol, s.overall - h.overall AS d FROM score_history h JOIN scores s ON s.symbol = h.symbol AND s.model = h.model "
                    "WHERE h.model = 'v1' AND h.day <= current_date - 80 AND h.overall IS NOT NULL AND s.overall IS NOT NULL ORDER BY h.symbol, h.day DESC"):
                move[r["symbol"]] = float(r["d"])
        _table = Table(rows, mem, move)
        return _table


def reset() -> None:
    global _table
    _table = None
