"""Leader / In line / Laggard: how a stock's last 12 months compare with the peers in its industry and with two indices.

The label describes PAST relative price performance only. It is never a buy, sell or hold signal, and the wording here and in the front end says so.

Layout of this file
  1. Pure functions (no database, no clock): weekly prices, relative returns, ranking, labels, direction, the fundamental check, the stability rule,
     the display strings and the sector backtest. Every rule of the developer spec lives here and is tested in tests/test_leadership.py.
  2. The weekly job: reads stored weekly closes (the price-MAX section), index levels and the screener's scores, writes `leadership` and
     `leadership_history`; the quarterly job writes `sector_reliability`.
  3. The API: /api/stocks/{symbol}/leadership and /api/stocks/{symbol}/leadership-history (registered before the generic section route).

Parameters (52-week ranking window, 13-week direction window, 30% ends, +-5 point direction threshold, 6 peers, 52 weeks of history, 7-day staleness,
Rs 1 crore liquidity, 2-week stability) are the module constants below; nothing is tuned per sector.
"""

from __future__ import annotations

import bisect
import json
import logging
import math
import re
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

log = logging.getLogger("finlit.leadership")

# ---------------------------------------------------------------------------------------------------------------- parameters
RANK_WEEKS = 52          # ranking window
DIRECTION_WEEKS = 13     # "gaining / weakening" window
MID_WEEKS = 26           # tie-break and shown, not ranked on
END_SHARE_TENTHS = 3     # the top and bottom 30% (ceil(3n / 10) stocks each)
DIRECTION_THRESHOLD = 0.05
MIN_PEERS = 6
MIN_WEEKS = 52
STALE_DAYS = 7
LIQUIDITY_FLOOR_RUPEES = 1e7        # Rs 1 crore of median daily traded value over about 3 months
STABILITY_RUNS = 2
STALE_AFTER_RUNS = 2
BREAK_DOWN, BREAK_UP = -0.20, 0.40  # a weekly move this large on a corporate-action date is held, not labelled
RELIABILITY_MIN_CHECKS = 120        # 10 years of 4-weekly checks
CHECK_EVERY_WEEKS = 4
LOOK_AHEAD_WEEKS = 26
PERIODS: List[Tuple[str, int, int]] = [("2005-09", 2005, 2009), ("2010-14", 2010, 2014), ("2015-19", 2015, 2019), ("2020-26", 2020, 2100)]
CONSISTENT_OVERALL, CONSISTENT_EACH, MIXED_OVERALL = 0.55, 0.50, 0.50

LABELS = ("leader", "in_line", "laggard")
CHIP = {"leader": "Leader", "in_line": "In line", "laggard": "Laggard"}
REASON_TEXT = {"history": "Not enough price history to compare with peers yet", "stale": "Not enough price history to compare with peers yet",
               "liquidity": "Too thinly traded to compare with peers", "group": "Too few comparable companies to rank"}


# ---------------------------------------------------------------------------------------------------------------- 1. pure functions
def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def norm_industry(text: str) -> str:
    """Industry names compared ignoring case, '&' versus 'and', and punctuation (the data provider is not consistent about them)."""
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower().replace("&", " and ")).strip()


def iso(d: Any) -> Optional[date]:
    if isinstance(d, date):
        return d
    try:
        return date.fromisoformat(str(d)[:10])
    except (TypeError, ValueError):
        return None


class Prices:
    """A weekly (or any) close series, oldest first. Closes that are missing or not positive are dropped."""

    def __init__(self, dates: Sequence[Any], closes: Sequence[Any]):
        pairs = {}
        for d, c in zip(dates, closes):
            dd = iso(d)
            try:
                cc = float(c)
            except (TypeError, ValueError):
                continue
            if dd is not None and cc > 0 and math.isfinite(cc):
                pairs[dd] = cc
        self.dates: List[date] = sorted(pairs)
        self.closes: List[float] = [pairs[d] for d in self.dates]

    def __len__(self) -> int:
        return len(self.dates)

    def count_upto(self, t: date) -> int:
        return bisect.bisect_right(self.dates, t)

    def close_on(self, t: date, max_age: int = STALE_DAYS) -> Optional[float]:
        """The last close on or before `t`, if it is no more than `max_age` days older than `t`."""
        i = bisect.bisect_right(self.dates, t)
        if i == 0 or (t - self.dates[i - 1]).days > max_age:
            return None
        return self.closes[i - 1]

    def last_date(self) -> Optional[date]:
        return self.dates[-1] if self.dates else None


def ret(p: Prices, t: date, weeks: int) -> Optional[float]:
    """Price return over `weeks` weeks ending at `t`, as a fraction (0.05 = 5%). None when either end has no fresh enough close."""
    a, b = p.close_on(t), p.close_on(t - timedelta(days=7 * weeks))
    if a is None or b is None:
        return None
    return a / b - 1.0


@dataclass
class Member:
    sym: str
    prices: Prices
    mcap: float = 0.0
    fund: Optional[float] = None       # fundamental score: the mean of the four pillars
    liquid: bool = True
    name: str = ""


def exclusion(m: Member, t: date) -> Optional[str]:
    """Why a stock cannot be ranked on date `t`, or None. history: fewer than 52 weekly closes; stale: last close more than 7 days old; liquidity."""
    if m.prices.count_upto(t) < MIN_WEEKS:
        return "history"
    if m.prices.close_on(t) is None:
        return "stale"
    if ret(m.prices, t, RANK_WEEKS) is None:   # a hole in the year-old end of the series
        return "history"
    if not m.liquid:
        return "liquidity"
    return None


def top_count(n: int) -> int:
    """k = ceil(0.3 * n), in integer arithmetic so 0.3 * 10 can never round to 3.0000000000000004."""
    return -(-END_SHARE_TENTHS * n // 10)


def choose_group(industry: Sequence[Member], sector: Sequence[Member], t: date) -> Tuple[Optional[str], List[Member], Dict[str, str]]:
    """The peer group: the industry, or the wider sector when fewer than 6 of the industry's stocks can be ranked; None when even that is too small.
    Returns (kind, members, excluded) with `excluded` = {symbol: reason} for every stock of the chosen group that cannot be ranked."""
    for kind, group in (("industry", industry), ("sector", sector)):
        ok = [m for m in group if exclusion(m, t) is None]
        if len(ok) >= MIN_PEERS:
            return kind, list(group), {m.sym: why for m in group if (why := exclusion(m, t))}
    return None, list(industry), {m.sym: why for m in industry if (why := exclusion(m, t))}


@dataclass
class Row:
    sym: str
    rank: int = 0
    label: str = "in_line"
    direction: Optional[str] = None
    rel13: Optional[float] = None
    rel26: Optional[float] = None
    rel52: float = 0.0
    rel52_market: Optional[float] = None
    ret52: float = 0.0
    market_ret52: Optional[float] = None
    fund_rank: Optional[int] = None
    fund_n: int = 0
    fundamental: Optional[str] = None
    mcap: float = 0.0


@dataclass
class Group:
    rows: List[Row]
    n: int
    k: int
    kind: str                               # "index" or "peer_average": what the sector benchmark is
    sector_ret52: Optional[float] = None
    market_ret52: Optional[float] = None
    excluded: Dict[str, str] = field(default_factory=dict)


def label_group(members: Sequence[Member], t: date, sector_idx: Optional[Prices], market_idx: Optional[Prices], excluded: Optional[Dict[str, str]] = None) -> Group:
    """Rank one peer group on date `t` and label it (steps 1 to 7 of the spec; the stability rule is `settle`)."""
    excluded = dict(excluded or {})
    ok: List[Member] = []
    for m in members:
        why = exclusion(m, t)
        if why:
            excluded[m.sym] = why
        else:
            ok.append(m)
    use_index = sector_idx is not None and all(ret(sector_idx, t, w) is not None for w in (DIRECTION_WEEKS, MID_WEEKS, RANK_WEEKS))
    own = {m.sym: {w: ret(m.prices, t, w) for w in (DIRECTION_WEEKS, MID_WEEKS, RANK_WEEKS)} for m in ok}
    if use_index:
        bench = {w: ret(sector_idx, t, w) for w in (DIRECTION_WEEKS, MID_WEEKS, RANK_WEEKS)}   # type: ignore[arg-type]
    else:   # no index (or no history for it): the equal-weighted mean of the peers' returns stands in, and the tooltip says so
        bench = {w: statistics.fmean([r[w] for r in own.values() if r[w] is not None]) if any(r[w] is not None for r in own.values()) else None
                 for w in (DIRECTION_WEEKS, MID_WEEKS, RANK_WEEKS)}
    mkt52 = ret(market_idx, t, RANK_WEEKS) if market_idx is not None else None
    rows: List[Row] = []
    for m in ok:
        r = own[m.sym]
        rel = {w: (r[w] - bench[w]) if r[w] is not None and bench[w] is not None else None for w in r}
        if rel[RANK_WEEKS] is None:
            excluded[m.sym] = "history"
            continue
        rows.append(Row(sym=m.sym, rel13=rel[DIRECTION_WEEKS], rel26=rel[MID_WEEKS], rel52=rel[RANK_WEEKS], ret52=r[RANK_WEEKS] or 0.0, mcap=m.mcap or 0.0,
                        rel52_market=(r[RANK_WEEKS] - mkt52) if mkt52 is not None and r[RANK_WEEKS] is not None else None))
    # highest 12-month relative return first; ties: higher 6-month relative return, then the larger company
    rows.sort(key=lambda x: (-x.rel52, -(x.rel26 if x.rel26 is not None else -1e9), -x.mcap))
    n = len(rows)
    k = top_count(n)
    for i, row in enumerate(rows, start=1):
        row.rank = i
        row.label = "leader" if i <= k and row.rel52 > 0 else "laggard" if i > n - k and row.rel52 < 0 else "in_line"
        if row.rel13 is not None:
            row.direction = "gaining" if row.rel13 >= DIRECTION_THRESHOLD - 1e-12 else "weakening" if row.rel13 <= -DIRECTION_THRESHOLD + 1e-12 else None
    # fundamental check: the same members ranked on their fundamental score
    by_sym = {m.sym: m for m in ok}
    funded = sorted((r for r in rows if by_sym[r.sym].fund is not None), key=lambda r: (-(by_sym[r.sym].fund or 0.0), -r.mcap))
    fn = len(funded)
    if fn >= MIN_PEERS:
        kf = top_count(fn)
        for j, r in enumerate(funded, start=1):
            r.fund_rank, r.fund_n = j, fn
            if r.label == "leader" and j > fn - kf:
                r.fundamental = "below_peers"
            elif r.label == "laggard" and j <= kf:
                r.fundamental = "stronger_than_price"
    return Group(rows=rows, n=n, k=k, kind="index" if use_index else "peer_average", sector_ret52=bench[RANK_WEEKS], market_ret52=mkt52, excluded=excluded)


def settle(published: Optional[str], last_raw: Optional[str], raw: str, runs: int = STABILITY_RUNS) -> Tuple[str, bool]:
    """The stability rule: a new label is published only when the same raw label has come out in 2 consecutive weekly runs; otherwise the published
    one stays. A stock's first label is published at once. Returns (published label, whether it changed)."""
    if published is None:
        return raw, True
    if raw == published:
        return published, False
    if runs <= 2 and raw == last_raw:
        return raw, True
    return published, False


def find_breaks(p: Prices, t: date, action_dates: Iterable[Any], weeks: int = RANK_WEEKS) -> List[Tuple[date, float]]:
    """Weekly moves in the last `weeks` weeks that look like an unadjusted corporate action: below -20% or above +40% in a week that contains a
    corporate-action date (a demerger the price series is not adjusted for: Motherson, January 2022, is the known case)."""
    acts = [d for d in (iso(a) for a in action_dates) if d]
    out: List[Tuple[date, float]] = []
    lo = t - timedelta(days=7 * weeks)
    for i in range(1, len(p.dates)):
        d0, d1 = p.dates[i - 1], p.dates[i]
        if d1 > t or d1 < lo:
            continue
        move = p.closes[i] / p.closes[i - 1] - 1.0
        if (move < BREAK_DOWN or move > BREAK_UP) and any(d0 < a <= d1 + timedelta(days=3) for a in acts):
            out.append((d1, move))
    return out


# ------------------------------------------------------------------------------------------------------------------ display strings
def ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def pts(x: Optional[float], plus: bool = True) -> str:
    """A fraction as percentage points with one decimal and a real minus sign: -0.072 -> '−7.2'; +0.012 -> '+1.2'."""
    if x is None:
        return "—"
    v = round(x * 100, 1)
    if v == 0:
        v = 0.0
    s = f"{abs(v):.1f}"
    return ("+" if v > 0 and plus else "−" if v < 0 else "") + s


def display(*, label: Optional[str], rank: Optional[int], ranked: Optional[int], group_short: str, sector_name: str, market_name: Optional[str],
            rel52: Optional[float], rel52_market: Optional[float], direction: Optional[str], fundamental: Optional[str], fund_rank: Optional[int],
            fund_n: Optional[int], reason: Optional[str] = None) -> Dict[str, Any]:
    """Every string the site shows for the label, built once so the subheading, the Peers tab and the bottom section never disagree.
    Wording rules: 'has outperformed', 'is behind', 'pts' for percentage points; never buy, sell, avoid or strong buy."""
    if label is None:
        return {"chip": None, "line": REASON_TEXT.get(reason or "history"), "note": None, "tooltip": None}
    parts = {"rank": f"{ordinal(rank or 0)} of {ranked} {group_short} peers", "sector": {"pts": pts(rel52), "name": sector_name, "v": rel52},
             "market": {"pts": pts(rel52_market), "name": market_name, "v": rel52_market} if rel52_market is not None and market_name else None, "direction": direction}
    line = f"{parts['rank']} · {parts['sector']['pts']} pts vs {sector_name}"
    if parts["market"]:
        line += f" · {parts['market']['pts']} pts vs {market_name}"
    line += " (12 months)"
    if direction:
        line += f" · {direction} over 3 months"
    note = None
    if fundamental == "below_peers" and fund_rank and fund_n:
        note = f"Price is leading, but fundamentals rank {ordinal(fund_rank)} of {fund_n}"
    elif fundamental == "stronger_than_price" and fund_rank and fund_n:
        note = f"Fundamentals rank {ordinal(fund_rank)} of {fund_n}, stronger than the price"
    tip = (f"Based on price performance over the last 12 months compared with {ranked} {group_short} companies and {sector_name}. "
           "Describes the past; not a recommendation.")
    return {"chip": CHIP[label], "line": line, "parts": parts, "note": note, "tooltip": tip}


# ------------------------------------------------------------------------------------------------------------------------- backtest
@dataclass
class Check:
    on: date
    hit: bool
    gap: float          # mean forward return of the top group minus that of the bottom group, as a fraction
    n: int


def backtest_checks(members: Sequence[Member], sector_idx: Optional[Prices], dates: Iterable[date],
                    forward_weeks: int = LOOK_AHEAD_WEEKS) -> List[Check]:
    """Every check date: rank the group on 12-month relative return as it stood THEN (no later information), then compare the mean return over the
    next 6 months of the top 30% with that of the bottom 30%. A check needs at least 6 rankable stocks."""
    out: List[Check] = []
    for t in dates:
        g = label_group(members, t, sector_idx, None)
        if g.n < MIN_PEERS:
            continue
        end = t + timedelta(days=7 * forward_weeks)
        by = {m.sym: m for m in members}

        def fwd(sym: str) -> Optional[float]:
            p = by[sym].prices
            a, b = p.close_on(t), p.close_on(end)
            return None if a is None or b is None else b / a - 1.0

        top = [x for x in (fwd(r.sym) for r in g.rows[:g.k]) if x is not None]
        bottom = [x for x in (fwd(r.sym) for r in g.rows[g.n - g.k:]) if x is not None]
        if not top or not bottom:
            continue
        gap = statistics.fmean(top) - statistics.fmean(bottom)
        out.append(Check(on=t, hit=gap > 0, gap=gap, n=g.n))
    return out


def summarise_checks(checks: Sequence[Check]) -> Dict[str, Any]:
    """Tier from the stored checks. consistent: overall hit rate at least 55% and at least 50% in every five-year period; mixed: overall at least 50%
    otherwise; not_reliable: below 50%; insufficient: under 120 checks (10 years). A frequency over the past, never a probability of future returns."""
    n = len(checks)
    hit = sum(c.hit for c in checks)
    periods = []
    for name, y0, y1 in PERIODS:
        sel = [c for c in checks if y0 <= c.on.year <= y1]
        if sel:
            periods.append({"years": name, "hitRate6m": round(sum(c.hit for c in sel) / len(sel), 4), "checks": len(sel)})
    rate = hit / n if n else None
    if n < RELIABILITY_MIN_CHECKS or rate is None:
        tier = "insufficient"
    elif rate >= CONSISTENT_OVERALL and all(p["hitRate6m"] >= CONSISTENT_EACH for p in periods):
        tier = "consistent"
    elif rate >= MIXED_OVERALL:
        tier = "mixed"
    else:
        tier = "not_reliable"
    return {"tier": tier, "hitRate6m": None if rate is None else round(rate, 4), "checks": n, "periods": periods,
            "from": checks[0].on.isoformat()[:7] if checks else None, "to": checks[-1].on.isoformat()[:7] if checks else None}


def reliability_sentence(group_name: str, rel: Optional[Dict[str, Any]]) -> str:
    """The sentence on the card, worded from the tier only (never from a hard-coded sector name)."""
    if not rel or rel.get("tier") in (None, "insufficient"):
        return "Not enough history to judge"
    rate = round((rel.get("hitRate6m") or 0) * 100)
    since = (rel.get("from") or "")[:4]
    periods = rel.get("periods") or []
    if rel["tier"] == "consistent":
        return f"In {group_name}, leaders have kept beating laggards: {rate}% of checks since {since}, and in every five-year period."
    if rel["tier"] == "mixed":
        lo = min((p["hitRate6m"] for p in periods), default=None)
        hi = max((p["hitRate6m"] for p in periods), default=None)
        span = f", from {round(lo * 100)}% in {periods[[p['hitRate6m'] for p in periods].index(lo)]['years']} to {round(hi * 100)}% in {periods[[p['hitRate6m'] for p in periods].index(hi)]['years']}" if lo is not None and hi is not None and lo != hi else ""
        return f"In {group_name}, leadership has held in some periods and not others: {rate}% of checks since {since}{span}."
    return f"In {group_name}, past leaders have not tended to stay ahead: {rate}% of checks since {since}."


# ---------------------------------------------------------------------------------------------------------------- 2. the weekly job
def last_friday(on: Optional[date] = None) -> date:
    d = on or datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    return d - timedelta(days=(d.weekday() - 4) % 7)


def run_dates(as_of: date, backfill_from: Optional[date] = None, every: int = CHECK_EVERY_WEEKS) -> List[date]:
    """The Fridays to compute: just `as_of`, or, to backfill, every `every` weeks from `backfill_from` up to and including `as_of`."""
    if not backfill_from:
        return [as_of]
    start = last_friday(backfill_from)
    out: List[date] = []
    d = as_of
    while d >= start:
        out.append(d)
        d -= timedelta(days=7 * every)
    return sorted(out)


def size_bucket(rank: Optional[int]) -> str:
    """AMFI convention on market-cap rank: 1 to 100 large, 101 to 250 mid, 251 and below small."""
    return "large" if rank is not None and rank <= 100 else "mid" if rank is not None and rank <= 250 else "small"


def liquid_enough(prices_dates: Sequence[Any], closes: Sequence[Any], volumes: Sequence[Any], floor: float = LIQUIDITY_FLOOR_RUPEES) -> bool:
    """Median daily traded value, estimated from the last 13 weekly bars (weekly volume x close / 5 sessions), against the Rs 1 crore floor.
    A series without volumes is not excluded: unknown is not thin."""
    vals = []
    for c, v in list(zip(closes, volumes))[-13:]:
        try:
            vals.append(float(c) * float(v) / 5.0)
        except (TypeError, ValueError):
            continue
    return True if len(vals) < 4 else statistics.median(vals) >= floor


async def _index_prices(store, settings, code: str) -> Optional[Prices]:
    """Weekly-or-daily closes of an index: the saved copy the API keeps in Redis, else one call to the data provider."""
    from . import indices
    raw = None
    try:
        got = await store.redis.get(f"idx:px:{code}")
        raw = json.loads(got)["v"] if got else None
    except Exception:
        raw = None
    if raw is None:
        from types import SimpleNamespace
        app = SimpleNamespace(state=SimpleNamespace(settings=settings))
        try:
            raw = await indices._fetch_levels(app, code)
        except Exception as exc:   # a missing index falls back to the peer average; the run goes on
            log.warning("index %s unavailable for the leadership run: %s", code, type(exc).__name__)
            return None
    rows = indices.shape_levels(raw, indices.HISTORY_YEARS)["rows"]
    p = Prices([r["d"] for r in rows], [r["c"] for r in rows])
    return p if len(p) else None


async def _load_universe(store) -> List[dict]:
    async with store.pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ON (s.symbol) s.symbol, s.statement, COALESCE(c.name, s.symbol) AS name, COALESCE(NULLIF(s.industry, ''), NULLIF(c.industry, ''), NULLIF(s.sector, '')) AS industry, "
            "COALESCE(NULLIF(s.macro_sector, ''), NULLIF(s.sector, ''), NULLIF(c.sector, '')) AS sector, COALESCE(q.market_cap, s.market_cap)::float8 AS mcap, s.pillar_quality AS pq, s.pillar_growth AS pg, "
            "s.pillar_profitability AS pp, s.pillar_balance AS pb FROM scores s JOIN companies c ON c.symbol = s.symbol "
            "LEFT JOIN listing_quotes q ON q.symbol = s.symbol WHERE s.model = 'v1' "
            "ORDER BY s.symbol, (s.statement = 'consolidated') DESC, s.updated_at DESC")
    return [dict(r) for r in rows]


async def _market_cap_ranks(store) -> Dict[str, int]:
    async with store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT symbol FROM listing_quotes WHERE market_cap IS NOT NULL ORDER BY market_cap DESC")
    return {r["symbol"]: i for i, r in enumerate(rows, start=1)}


async def _load_prices(store, rows: List[dict]) -> Dict[str, Tuple[Prices, bool]]:
    """Stored weekly closes (the price-MAX section) per stock, with the liquidity verdict. A stock whose report is not stored has none."""
    out: Dict[str, Tuple[Prices, bool]] = {}
    by_statement: Dict[str, List[str]] = {}
    for r in rows:
        by_statement.setdefault(r["statement"], []).append(r["symbol"])
    async with store.pool.acquire() as conn:
        for st, syms in by_statement.items():
            for i in range(0, len(syms), 100):
                chunk = syms[i:i + 100]
                for rec in await conn.fetch("SELECT symbol, body FROM snapshots WHERE statement = $1 AND section = 'price-MAX' AND symbol = ANY($2::text[])", st, chunk):
                    try:
                        s = json.loads(rec["body"]).get("series") or {}
                        t, c = s.get("t") or [], s.get("c") or []
                        out[rec["symbol"]] = (Prices(t, c), liquid_enough(t, c, s.get("v") or []))
                    except (ValueError, TypeError):
                        continue
    return out


async def _action_dates(store, statement: str, sym: str) -> List[str]:
    async with store.pool.acquire() as conn:
        body = await conn.fetchval("SELECT body FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = 'events'", sym, statement)
    try:
        return [a["date"] for a in (json.loads(body).get("actions") or []) if a.get("date") and "dividend" not in str(a.get("type") or "")] if body else []
    except (ValueError, TypeError, AttributeError):
        return []


async def run(store, settings, *, as_of: Optional[date] = None, backfill_from: Optional[date] = None) -> Dict[str, Any]:
    """The weekly run (after Friday's close): label every stock that has a peer group, publish through the stability rule, store the rank history.
    `backfill_from` also computes every 4th Friday back to that date, so the history chart starts with years of points rather than an empty chart."""
    as_of = as_of or last_friday()
    dates = run_dates(as_of, backfill_from)
    universe = await _load_universe(store)
    mcap_rank = await _market_cap_ranks(store)
    async with store.pool.acquire() as conn:
        cfg = {norm_industry(r["industry"]): dict(r) for r in await conn.fetch("SELECT * FROM leadership_benchmarks")}
        mk = {r["bucket"]: dict(r) for r in await conn.fetch("SELECT * FROM leadership_market")}
        state = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, label, raw_label, label_since, stale_runs FROM leadership")}
    prices = await _load_prices(store, universe)
    index_codes = {c["sector_code"] for c in cfg.values()} | {m["code"] for m in mk.values()}
    idx: Dict[str, Optional[Prices]] = {code: await _index_prices(store, settings, code) for code in sorted(index_codes)}

    members: Dict[str, Member] = {}
    meta: Dict[str, dict] = {}
    for r in universe:
        if r["symbol"] not in prices:
            continue
        p, liquid = prices[r["symbol"]]
        pillars = [r.get(k) for k in ("pq", "pg", "pp", "pb")]
        fund = statistics.fmean(pillars) if all(x is not None for x in pillars) else None
        members[r["symbol"]] = Member(sym=r["symbol"], prices=p, mcap=r["mcap"] or 0.0, fund=fund, liquid=liquid, name=r["name"])
        meta[r["symbol"]] = r
    by_industry: Dict[str, List[Member]] = {}
    by_sector: Dict[str, List[Member]] = {}
    for sym, m in members.items():
        by_industry.setdefault(meta[sym]["industry"] or "", []).append(m)
        by_sector.setdefault(meta[sym]["sector"] or "", []).append(m)

    published: Dict[str, Tuple[Optional[str], Optional[str], Optional[date]]] = {s: (v["label"], v["raw_label"], v["label_since"]) for s, v in state.items()}
    history_rows: List[tuple] = []
    latest: Dict[str, dict] = {}
    held_syms: Dict[str, List[str]] = {}
    why_not: Dict[str, str] = {}
    for t in dates:
        final = t == dates[-1]
        if final:
            why_not.clear()
        for industry, group in by_industry.items():
            if not industry:
                continue
            sector_name = meta[group[0].sym]["sector"] or ""
            kind, chosen, excluded = choose_group(group, by_sector.get(sector_name, group), t)
            if kind is None:
                if final:
                    for m in group:
                        why_not[m.sym] = exclusion(m, t) or "group"
                continue
            conf = cfg.get(norm_industry(industry))
            sidx = idx.get(conf["sector_code"]) if conf and kind == "industry" else None   # a widened group has no single sector index
            g = label_group(chosen, t, sidx, None, excluded)
            if g.n < MIN_PEERS:
                if final:
                    for m in group:
                        why_not[m.sym] = g.excluded.get(m.sym, "group")
                continue
            if final:
                for sym_, why in g.excluded.items():
                    if meta[sym_]["industry"] == industry:
                        why_not[sym_] = why
            short = (conf["group_short"] if conf and kind == "industry" else (sector_name if kind == "sector" else industry))
            gname = (conf["group_name"] if conf and kind == "industry" else (sector_name if kind == "sector" else industry))
            for row in g.rows:
                if meta[row.sym]["industry"] != industry:   # a wider-sector group also ranks other industries' stocks; each stock is written once, by its own industry
                    continue
                mrow = mk.get(size_bucket(mcap_rank.get(row.sym)))
                midx = idx.get(mrow["code"]) if mrow else None
                mret = ret(midx, t, RANK_WEEKS) if midx is not None else None
                row.market_ret52 = mret
                row.rel52_market = row.ret52 - mret if mret is not None else None
                pub, last_raw, since = published.get(row.sym, (None, None, None))
                new_pub, changed = settle(pub, last_raw, row.label)
                if changed or since is None:
                    since = t
                published[row.sym] = (new_pub, row.label, since)
                history_rows.append((row.sym, t, row.rank, g.n, new_pub, row.direction, row.rel52, row.rel52_market))
                if final:
                    latest[row.sym] = {"row": row, "g": g, "kind": kind, "industry": industry, "gname": gname, "short": short, "published": new_pub, "since": since,
                                       "conf": conf, "sector_name": (conf["sector_name"] if conf and g.kind == "index" else "peer average"),
                                       "market_name": mrow["name"] if mrow and mret is not None else None, "sidx_code": conf["sector_code"] if conf and g.kind == "index" else None,
                                       "midx_code": mrow["code"] if mrow and mret is not None else None, "group_id": slug(industry if kind == "industry" else sector_name)}

    # corporate-action gaps: hold the label (keep the previous published one) and raise a data alert
    for sym, v in latest.items():
        p = members[sym].prices
        cand = [i for i in range(1, len(p.dates)) if as_of - timedelta(days=364) <= p.dates[i] <= as_of
                and not BREAK_DOWN <= p.closes[i] / p.closes[i - 1] - 1 <= BREAK_UP]
        if cand:
            acts = await _action_dates(store, meta[sym]["statement"], sym)
            if find_breaks(p, as_of, acts):
                held_syms.setdefault(sym, []).append("corporate-action gap")
                log.warning("leadership label held for %s: a weekly move beyond %s/%s on a corporate-action date", sym, BREAK_DOWN, BREAK_UP)

    async with store.pool.acquire() as conn:
        async with conn.transaction():
            if history_rows:
                await conn.executemany(
                    "INSERT INTO leadership_history (symbol, run_date, rank, ranked, label, direction, rel52, rel52_market) VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
                    "ON CONFLICT (symbol, run_date) DO UPDATE SET rank = EXCLUDED.rank, ranked = EXCLUDED.ranked, label = EXCLUDED.label, direction = EXCLUDED.direction, "
                    "rel52 = EXCLUDED.rel52, rel52_market = EXCLUDED.rel52_market", history_rows)
            recs = []
            for sym, v in latest.items():
                row, g = v["row"], v["g"]
                held = sym in held_syms
                label = state.get(sym, {}).get("label") if held and state.get(sym, {}).get("label") else v["published"]
                recs.append((sym, members[sym].name, as_of, v["group_id"], v["gname"], v["short"], v["kind"], g.n, row.rank, label, row.label, v["since"], row.direction,
                             row.rel13, row.rel26, row.rel52, row.rel52_market, v["sidx_code"] or "peer_average", v["sector_name"], g.kind, g.sector_ret52,
                             v["midx_code"], v["market_name"], row.market_ret52, row.fundamental, row.fund_rank, row.fund_n or None, members[sym].mcap, held))
            if recs:
                await conn.executemany(
                    "INSERT INTO leadership (symbol, name, as_of, group_id, group_name, group_short, group_kind, ranked, rank, label, raw_label, label_since, direction, rel13, rel26, rel52, "
                    "rel52_market, sector_code, sector_name, sector_kind, sector_ret52, market_code, market_name, market_ret52, fundamental, fund_rank, fund_n, market_cap, held, stale_runs, updated_at) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,0,now()) "
                    "ON CONFLICT (symbol) DO UPDATE SET name = EXCLUDED.name, as_of = EXCLUDED.as_of, group_id = EXCLUDED.group_id, group_name = EXCLUDED.group_name, "
                    "group_short = EXCLUDED.group_short, group_kind = EXCLUDED.group_kind, ranked = EXCLUDED.ranked, rank = EXCLUDED.rank, label = EXCLUDED.label, "
                    "raw_label = EXCLUDED.raw_label, label_since = EXCLUDED.label_since, direction = EXCLUDED.direction, rel13 = EXCLUDED.rel13, rel26 = EXCLUDED.rel26, "
                    "rel52 = EXCLUDED.rel52, rel52_market = EXCLUDED.rel52_market, sector_code = EXCLUDED.sector_code, sector_name = EXCLUDED.sector_name, "
                    "sector_kind = EXCLUDED.sector_kind, sector_ret52 = EXCLUDED.sector_ret52, market_code = EXCLUDED.market_code, market_name = EXCLUDED.market_name, "
                    "market_ret52 = EXCLUDED.market_ret52, fundamental = EXCLUDED.fundamental, fund_rank = EXCLUDED.fund_rank, fund_n = EXCLUDED.fund_n, "
                    "market_cap = EXCLUDED.market_cap, held = EXCLUDED.held, stale_runs = 0, updated_at = now()", recs)
            await conn.execute("DELETE FROM leadership_excluded")
            gone = {s: w for s, w in why_not.items() if s not in latest}
            if gone:
                await conn.executemany("INSERT INTO leadership_excluded (symbol, reason, as_of) VALUES ($1, $2, $3)", [(s, w, as_of) for s, w in gone.items()])
            # stocks that had a label last week but no fresh prices this week keep it; two missed runs in a row flag it stale
            missing = [s for s in state if s not in latest]
            if missing:
                await conn.execute("UPDATE leadership SET stale_runs = stale_runs + 1 WHERE symbol = ANY($1::text[]) AND as_of < $2", missing, as_of)
            await conn.execute("DELETE FROM leadership_history WHERE run_date < current_date - 2200")
    churn = sum(1 for s, v in latest.items() if s in state and state[s].get("label") and state[s]["label"] != v["published"])
    covered = len(latest)
    out = {"asOf": as_of.isoformat(), "runs": len(dates), "labelled": covered, "withPrices": len(members), "history": len(history_rows), "churn": churn,
           "churnPct": round(100 * churn / max(1, len([s for s in latest if s in state])), 1), "held": sorted(held_syms), "indices": {c: (len(p) if p else 0) for c, p in idx.items()}}
    log.info("leadership run %s", out)
    return out


async def backtest(store, settings) -> Dict[str, Any]:
    """The quarterly backtest behind the reliability card: for every peer group with at least 6 rankable stocks, the share of 4-weekly checks on which the
    top 30% beat the bottom 30% over the next 6 months. It can only use the weekly history the site stores, so a group with under 10 years of checks is
    stored as 'insufficient' and the card says so; it never invents a tier."""
    universe = await _load_universe(store)
    prices = await _load_prices(store, universe)
    async with store.pool.acquire() as conn:
        cfg = {norm_industry(r["industry"]): dict(r) for r in await conn.fetch("SELECT * FROM leadership_benchmarks")}
    groups: Dict[str, List[dict]] = {}
    for r in universe:
        if r["symbol"] in prices and r["industry"]:
            groups.setdefault(r["industry"], []).append(r)
    done = {}
    today = last_friday()
    for industry, rows in groups.items():
        ms = [Member(sym=r["symbol"], prices=prices[r["symbol"]][0], mcap=r["mcap"] or 0.0, liquid=prices[r["symbol"]][1]) for r in rows]
        starts = [m.prices.dates[0] for m in ms if m.prices.dates]
        if len(ms) < MIN_PEERS or not starts:
            continue
        conf = cfg.get(norm_industry(industry))
        sidx = await _index_prices(store, settings, conf["sector_code"]) if conf else None
        first = sorted(starts)[MIN_PEERS - 1] + timedelta(days=7 * MIN_WEEKS)   # the first date six stocks have a year of prices
        dates = []
        d = last_friday(first)
        while d <= today - timedelta(days=7 * LOOK_AHEAD_WEEKS):
            dates.append(d)
            d += timedelta(days=7 * CHECK_EVERY_WEEKS)
        res = summarise_checks(backtest_checks(ms, sidx, dates))
        done[industry] = res
        async with store.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO sector_reliability (group_id, group_name, tier, hit_rate, checks, periods, window_start, window_end, method, computed_at) VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8, 'rel12', now()) "
                "ON CONFLICT (group_id) DO UPDATE SET group_name = EXCLUDED.group_name, tier = EXCLUDED.tier, hit_rate = EXCLUDED.hit_rate, checks = EXCLUDED.checks, "
                "periods = EXCLUDED.periods, window_start = EXCLUDED.window_start, window_end = EXCLUDED.window_end, computed_at = now()",
                slug(industry), (conf["group_name"] if conf else industry), res["tier"], res["hitRate6m"], res["checks"], json.dumps(res["periods"]),
                dates[0] if dates else None, dates[-1] if dates else None)
    return {"groups": {k: {"tier": v["tier"], "checks": v["checks"]} for k, v in done.items()}}
