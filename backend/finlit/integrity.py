"""Nightly data-integrity audit: does what we show agree with what the provider says, and with itself?

Light on purpose (free host: 512 MB of memory, 5 GB a month of bandwidth). Each night it takes the next SAMPLE (40) companies after a stored cursor, so
a full lap of the market happens over a few weeks and a stopped run resumes where it left off. Per sampled company it makes ONE provider call (the
latest quarterly results); the price check reuses the nightly market-wide quote table (listing_quotes), so it costs no call at all.

Checks (each gives checked / bad counts, a few examples and a plain-words message):
  price        our stored price is present and within 20% of the provider's latest quote
  basis        the latest quarter in our stored report is not older than the provider's latest quarter (a stale statement basis)
  identities   profit and loss adds up (revenue less expenses is operating profit) and the EPS sign follows the profit
  declared     results declared more than 3 days ago must not still read "report being updated"
  risk         price history exists, so the risk figures (volatility, worst fall) must exist

The result is stored in mf_meta ('integrity:last') and shown, red / amber / green, in the admin Data health tab.
The pure functions below take plain numbers and dicts so tests need neither a database nor the provider.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("finlit.integrity")

SAMPLE = 40                  # companies per night, one provider call each
PRICE_TOLERANCE = 0.20       # stored price within 20% of the provider's quote
IDENTITY_TOLERANCE = 0.15    # operating profit vs revenue less expenses, as a share of revenue
DECLARED_GRACE_DAYS = 3
MIN_BARS_FOR_RISK = 250      # a year of daily prices
META_LAST, META_CURSOR = "integrity:last", "integrity:cursor"
EXAMPLES = 5
LEVELS = ("green", "amber", "red")


# ---------------------------------------------------------------- pure checks (each returns None when fine, else a short reason)

def check_price(ours: Optional[float], provider: Optional[float], tolerance: float = PRICE_TOLERANCE) -> Optional[str]:
    if not provider or provider <= 0:
        return None                      # the provider has no price: nothing to compare (the report must say why; see coverage.py)
    if ours is None or ours <= 0:
        return f"no price shown, the provider has {provider:g}"
    if abs(ours / provider - 1) > tolerance:
        return f"shows {ours:g}, the provider has {provider:g}"
    return None


def parse_day(v: Any) -> Optional[date]:
    s = str(v or "").strip()[:10].replace("-", "")
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8])) if len(s) == 8 else None
    except ValueError:
        return None


def check_basis(ours_latest: Any, provider_latest: Any, slack_days: int = 10) -> Optional[str]:
    """Our latest stored quarter must not be older than the provider's (the signature of a stale consolidated/standalone basis)."""
    o, p = parse_day(ours_latest), parse_day(provider_latest)
    if o is None or p is None:
        return None
    if p - o > timedelta(days=slack_days):
        return f"report stops at {o.isoformat()}, the provider has {p.isoformat()}"
    return None


def check_identities(table: Dict[str, Any], tolerance: float = IDENTITY_TOLERANCE) -> List[str]:
    """Problems in a profit-and-loss table ({'periods': [...], 'rows': {key: [...]}}): operating profit vs revenue less expenses, EPS sign vs profit."""
    rows, periods, out = (table or {}).get("rows") or {}, (table or {}).get("periods") or [], []

    def col(k: str, i: int) -> Optional[float]:
        a = rows.get(k) or []
        v = a[i] if i < len(a) else None
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    for i, per in enumerate(periods):
        rev, exp, op, eps, np_ = col("revenue", i), col("expenses", i), col("operating_profit", i), col("eps", i), col("net_profit", i)
        if rev and exp is not None and op is not None and abs(op - (rev - exp)) > tolerance * abs(rev):
            out.append(f"{per}: operating profit {op:g} but revenue {rev:g} less expenses {exp:g} is {rev - exp:g}")
        if eps and np_ and (eps > 0) != (np_ > 0):
            out.append(f"{per}: EPS {eps:g} has the opposite sign to profit {np_:g}")
    return out


def check_declared(declared_on: Optional[date], quarter_end: Optional[date], stored_latest: Any, today: date, grace: int = DECLARED_GRACE_DAYS) -> Optional[str]:
    """Declared more than `grace` days ago, yet our stored latest quarter is still older than the declared quarter."""
    if declared_on is None or quarter_end is None or (today - declared_on).days <= grace:
        return None
    s = parse_day(stored_latest)
    if s is None or s < quarter_end - timedelta(days=10):
        return f"declared {declared_on.isoformat()}, still shows quarter ending {s.isoformat() if s else 'none'}"
    return None


def check_risk(bars: int, volatility: Any, drawdown: Any) -> Optional[str]:
    if bars >= MIN_BARS_FOR_RISK and (volatility is None or drawdown is None):
        return f"{bars} days of prices but " + " and ".join(n for n, v in (("volatility", volatility), ("worst fall", drawdown)) if v is None) + " missing"
    return None


# ---------------------------------------------------------------- grading and wording

MESSAGES = {
    "price": ("Prices", "{bad} of {checked} companies show a price that is missing or more than 20% away from the provider's quote."),
    "basis": ("Latest quarter", "{bad} of {checked} sampled companies have an older latest quarter than the provider has (stale statements)."),
    "identities": ("Profit and loss adds up", "{bad} of {checked} sampled companies have a profit and loss that does not add up or an EPS with the wrong sign."),
    "declared": ("Declared results", "{bad} of {checked} companies declared results over 3 days ago but still read \"report being updated\"."),
    "risk": ("Risk figures", "{bad} of {checked} companies with price history lack a risk figure."),
}
OK_TEXT = "{checked} checked, all fine."


def grade(checked: int, bad: int) -> str:
    if bad == 0:
        return "green"
    return "amber" if bad <= max(2, round(0.03 * checked)) else "red"


def make_check(key: str, checked: int, bad_items: List[str]) -> Dict[str, Any]:
    label, msg = MESSAGES[key]
    bad = len(bad_items)
    level = grade(checked, bad) if checked else "green"
    text = msg.format(bad=bad, checked=checked) if bad else (OK_TEXT.format(checked=checked) if checked else "Nothing to check yet.")
    return {"key": key, "label": label, "level": level, "checked": checked, "bad": bad, "message": text, "examples": bad_items[:EXAMPLES]}


def overall(checks: List[Dict[str, Any]]) -> str:
    return max((c["level"] for c in checks), key=LEVELS.index, default="green")


# ---------------------------------------------------------------- the run

async def _meta_get(conn, key: str) -> Optional[dict]:
    raw = await conn.fetchval("SELECT value FROM mf_meta WHERE key = $1", key)
    return json.loads(raw) if isinstance(raw, str) else raw


async def _meta_set(conn, key: str, body: Any) -> None:
    await conn.execute("INSERT INTO mf_meta (key, value) VALUES ($1, $2::jsonb) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()",
                       key, json.dumps(body, default=str))


async def last_result(pool) -> Optional[dict]:
    """The stored result for the admin panel; None if the audit has never run or the table is missing."""
    try:
        async with pool.acquire() as conn:
            return await _meta_get(conn, META_LAST)
    except Exception:   # fresh database: show nothing rather than fail the whole panel
        return None


async def _price_check(conn) -> Tuple[int, List[str]]:
    rows = await conn.fetch(
        "SELECT DISTINCT ON (s.symbol) s.symbol, s.price::float8 AS ours, l.price::float8 AS theirs FROM scores s JOIN listing_quotes l ON l.symbol = s.symbol "
        "WHERE s.model = 'v1' AND l.price IS NOT NULL AND l.updated_at > now() - interval '3 days' ORDER BY s.symbol, (s.statement = 'consolidated') DESC, s.updated_at DESC")
    bad = [f"{r['symbol']}: {w}" for r in rows for w in [check_price(r["ours"], r["theirs"])] if w]
    return len(rows), bad


async def _declared_check(store, conn, today: date) -> Tuple[int, List[str]]:
    from .results import get_declarations, parse_quarter
    decls = await get_declarations(store)
    ends = sorted((parse_quarter(k), k) for k in decls if parse_quarter(k))
    if not ends:
        return 0, []
    qend, qkey = ends[-1]
    old = {s: d for s, d in decls[qkey].items() if (today - d.date).days > DECLARED_GRACE_DAYS}
    if not old:
        return 0, []
    got = {r["symbol"]: r["q"] for r in await conn.fetch(
        "SELECT DISTINCT ON (symbol) symbol, metrics->>'q_period_end' AS q FROM scores WHERE model = 'v1' AND symbol = ANY($1::text[]) "
        "ORDER BY symbol, (statement = 'consolidated') DESC, updated_at DESC", list(old))}
    bad = [f"{s}: {w}" for s, d in sorted(old.items()) for w in [check_declared(d.date, qend, got.get(s), today)] if w and s in got]
    return len(got), bad


async def _next_sample(conn, n: int) -> Tuple[List[Tuple[str, str]], str]:
    cur = (await _meta_get(conn, META_CURSOR) or {}).get("after", "")
    q = ("SELECT DISTINCT ON (symbol) symbol, statement FROM scores WHERE model = 'v1' AND symbol {op} $1 "
         "ORDER BY symbol, (statement = 'consolidated') DESC, updated_at DESC LIMIT $2")
    rows = await conn.fetch(q.format(op=">"), cur, n)
    if len(rows) < n:    # end of the lap: continue from the start
        rows = list(rows) + list(await conn.fetch(q.format(op=">"), "", n - len(rows)))
    picks = [(r["symbol"], r["statement"]) for r in rows]
    return picks, (picks[-1][0] if picks else "")


async def audit(store, client, sample: int = SAMPLE, today: Optional[date] = None) -> Dict[str, Any]:
    """Run all checks. `client` is a FinEdgeClient (one call per sampled company); returns the stored result."""
    from .finedge import bundle_requests, latest_period_end
    today = today or datetime.now(timezone.utc).date()
    res: Dict[str, List] = {k: [0, []] for k in MESSAGES}
    async with store.pool.acquire() as conn:
        res["price"][0], res["price"][1] = await _price_check(conn)
        try:
            res["declared"][0], res["declared"][1] = await _declared_check(store, conn, today)
        except Exception as exc:   # the declarations feed is optional for the rest of the audit
            log.warning("integrity: declared check skipped (%s)", type(exc).__name__)
        picks, cursor = await _next_sample(conn, sample)
    for sym, statement in picks:
        async with store.pool.acquire() as conn:
            fin = await conn.fetchval("SELECT body FROM snapshots WHERE symbol = $1 AND statement = $2 AND section = 'financials'", sym, statement)
            met = await conn.fetchrow(
                "SELECT metrics->>'volatility' AS v, metrics->>'max_drawdown' AS d, (SELECT count(*) FROM price_daily p WHERE p.symbol = $1) AS bars "
                "FROM scores WHERE symbol = $1 AND statement = $2 AND model = 'v1' ORDER BY updated_at DESC LIMIT 1", sym, statement)
        body = json.loads(fin) if fin else {}
        qpl, ypl = (body.get("quarterly") or {}).get("pl") or {}, (body.get("yearly") or {}).get("pl") or {}
        ends = [e for e in (qpl.get("periodEnds") or []) if e]
        if met:
            res["risk"][0] += 1
            w = check_risk(int(met["bars"] or 0), met["v"], met["d"])
            if w:
                res["risk"][1].append(f"{sym}: {w}")
        if ypl:
            res["identities"][0] += 1
            res["identities"][1] += [f"{sym} {x}" for x in check_identities(ypl)[:2]]
        path, params, timeout = bundle_requests(sym, statement)["pl_quarterly"]
        try:
            theirs = latest_period_end(await client.get(path, params, timeout))
        except Exception as exc:   # one company failing is not a finding
            log.info("integrity: %s provider call failed (%s)", sym, type(exc).__name__)
            continue
        res["basis"][0] += 1
        w = check_basis(max(ends) if ends else None, theirs.isoformat() if theirs else None)
        if w:
            res["basis"][1].append(f"{sym}: {w}")
    checks = [make_check(k, v[0], v[1]) for k, v in res.items()]
    out = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "level": overall(checks), "sampled": len(picks), "checks": checks}
    async with store.pool.acquire() as conn:
        await _meta_set(conn, META_LAST, out)
        await _meta_set(conn, META_CURSOR, {"after": cursor})
    return out
