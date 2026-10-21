"""Member alerts: the metric catalogue, the evaluator the worker runs, and delivery (in-app notification, email, browser flag).

An alert is "tell me when <metric> of <company> goes above/below <value>" or "tell me about new <event> for <company>".
Threshold alerts fire when the condition *turns* true (a crossing), never on every check while it stays true. The catalogue below
is mirrored by frontend/src/lib/alertCatalog.ts; a test keeps the two lists of metric keys identical.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .analytics.indicators import ema, rsi
from .auth.mailer import Mailer

log = logging.getLogger("finlit.alertengine")

# key -> (label, unit, live, tier, ops).  live = checked every few minutes in market hours; the rest after the nightly load.
# tier: "basic" metrics are open to every member; "silver" metrics (model scores, fundamentals, filings) need Silver.
M = Dict[str, Any]
METRICS: Dict[str, M] = {
    "price":          dict(label="Price", unit="₹", live=True, tier="basic", ops=("above", "below")),
    "change_pct":     dict(label="Day change", unit="%", live=True, tier="basic", ops=("above", "below")),
    "move_abs":       dict(label="Move in a day (either way)", unit="%", live=True, tier="basic", ops=("above",)),
    "volume_x":       dict(label="Volume vs 20-day average", unit="×", live=False, tier="basic", ops=("above",)),
    "rsi14":          dict(label="RSI (14)", unit="", live=False, tier="basic", ops=("above", "below")),
    "ema50_gap":      dict(label="Price vs 50-day average", unit="%", live=False, tier="silver", ops=("above", "below")),
    "ema200_gap":     dict(label="Price vs 200-day average", unit="%", live=False, tier="silver", ops=("above", "below")),
    "from_high52":    dict(label="Distance from 52-week high", unit="%", live=False, tier="basic", ops=("below",)),
    "from_low52":     dict(label="Distance from 52-week low", unit="%", live=False, tier="basic", ops=("below",)),
    "return_1m":      dict(label="1-month return", unit="%", live=False, tier="silver", ops=("above", "below")),
    "return_1y":      dict(label="1-year return", unit="%", live=False, tier="silver", ops=("above", "below")),
    "overall":        dict(label="FinLit score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pillar_quality": dict(label="Quality score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pillar_growth":  dict(label="Growth score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pillar_profitability": dict(label="Profitability score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pillar_balance": dict(label="Balance-sheet score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pillar_technical": dict(label="Technical score", unit="", live=False, tier="silver", ops=("above", "below")),
    "pe":             dict(label="P/E", unit="×", live=False, tier="silver", ops=("above", "below")),
    "pb":             dict(label="P/B", unit="×", live=False, tier="silver", ops=("above", "below")),
    "dividend_yield": dict(label="Dividend yield", unit="%", live=False, tier="silver", ops=("above", "below")),
    "market_cap":     dict(label="Market cap", unit="Cr", live=False, tier="silver", ops=("above", "below")),
    "roe":            dict(label="ROE", unit="%", live=False, tier="silver", ops=("above", "below")),
    "roce":           dict(label="ROCE", unit="%", live=False, tier="silver", ops=("above", "below")),
    "operating_margin": dict(label="Operating margin", unit="%", live=False, tier="silver", ops=("above", "below")),
    "debt_to_equity": dict(label="Debt to equity", unit="×", live=False, tier="silver", ops=("above", "below")),
    "q_net_profit":   dict(label="Net profit (latest quarter)", unit="Cr", live=False, tier="silver", ops=("above", "below")),
    "q_revenue":      dict(label="Revenue (latest quarter)", unit="Cr", live=False, tier="silver", ops=("above", "below")),
    "rev_profit_gap": dict(label="Revenue vs profit growth gap", unit="pp", live=False, tier="silver", ops=("above",)),
    "promoter_chg":   dict(label="Promoter holding change", unit="pp", live=False, tier="silver", ops=("above", "below")),
    "fii_chg":        dict(label="FII holding change", unit="pp", live=False, tier="silver", ops=("above", "below")),
    "news_keyword":   dict(label="News or filing mentions", unit="", live=False, tier="basic", ops=("event",)),
    "new_filing":     dict(label="Any new filing", unit="", live=False, tier="silver", ops=("event",)),
    "result_soon":    dict(label="Results due within (days)", unit="days", live=False, tier="basic", ops=("event",)),
}
SCORE_COLUMNS = {"price", "change_pct", "return_1m", "return_1y", "overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance",
                 "pillar_technical", "pe", "pb", "dividend_yield", "market_cap", "roe", "roce", "operating_margin", "debt_to_equity"}
TECH = {"rsi14", "ema50_gap", "ema200_gap", "volume_x", "from_high52", "from_low52"}
SNAP = {"q_net_profit", "q_revenue", "rev_profit_gap", "promoter_chg", "fii_chg"}
EVENTS = {"news_keyword", "new_filing", "result_soon"}
CHANNELS = ("app", "email", "browser")
ALERT_LIMITS = {"basic": 3, "silver": 30, "gold": 300}
RANK = {"basic": 0, "silver": 1, "gold": 2}
COOLDOWN_HOURS = 1  # a repeating alert never fires twice inside this window


def allowed(plan: str, metric: str) -> bool:
    return METRICS[metric]["tier"] == "basic" or RANK.get(plan, 0) >= 1


def fmt(metric: str, v: float) -> str:
    unit = METRICS[metric]["unit"]
    n = f"{abs(v):,.2f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{abs(v):,.0f}"
    sign = "-" if v < 0 else ("+" if metric in ("promoter_chg", "fii_chg") and v > 0 else "")
    if unit == "₹":
        return f"{sign}₹{n}"
    if unit in ("%", "×", "pp"):
        return f"{sign}{n}{unit if unit != 'pp' else ' pp'}"
    if unit == "Cr":
        return f"{sign}₹{n} Cr"
    return f"{sign}{n}"


GAP_TEXT = "The anticipated difference between revenue and profit is >= {limit} percent thus please check the report thoroughly."


def quarter_gap(rows: Dict[str, Any]) -> Optional[Dict[str, float]]:
    """Revenue growth against net-profit growth, latest quarter over the same quarter a year earlier (the newest result is the last entry).
    Needs five quarters and a positive base for both, since a growth rate on a loss or zero is meaningless. gap is the absolute difference in points."""
    rev, prof = rows.get("revenue") or [], rows.get("net_profit") or []
    if len(rev) < 5 or len(prof) < 5:
        return None
    r1, r0, p1, p0 = rev[-1], rev[-5], prof[-1], prof[-5]
    if None in (r1, r0, p1, p0) or r0 <= 0 or p0 <= 0:
        return None
    rg, pg = (r1 / r0 - 1) * 100, (p1 / p0 - 1) * 100
    return {"gap": round(abs(rg - pg), 2), "rev": round(rg, 1), "profit": round(pg, 1)}


def headline(a: Dict[str, Any], v: Optional[float], extra: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(title, body) of the notification for a threshold alert that just crossed."""
    meta = METRICS[a["metric"]]
    if a["metric"] == "rev_profit_gap" and v is not None:
        d = extra or {}
        detail = f" Revenue {d['rev']:+.0f}% and net profit {d['profit']:+.0f}% against the same quarter last year." if "rev" in d and "profit" in d else ""
        return (f"{a['symbol']} – revenue and profit growth are {v:.0f} points apart",
                GAP_TEXT.format(limit=f"{float(a['value']):g}") + detail)
    side = "above" if a["op"] == "above" else "below"
    title = f"{a['symbol']} – {meta['label']} is now {fmt(a['metric'], v)}, {side} your target of {fmt(a['metric'], float(a['value']))}"
    return title, f"{meta['label']} for {a['symbol']} crossed {fmt(a['metric'], float(a['value']))} ({side}). It is {fmt(a['metric'], v)} now."


# ------------------------------------------------------------------ data
async def load_values(conn, symbols: List[str], needed: set) -> Dict[str, Dict[str, Optional[float]]]:
    out: Dict[str, Dict[str, Optional[float]]] = {s: {} for s in symbols}
    cols = sorted(needed & SCORE_COLUMNS | ({"change_pct"} if "move_abs" in needed else set()))
    if cols:
        # fixed column names from the catalogue above, never member input
        sql = "SELECT DISTINCT ON (symbol) symbol, " + ", ".join(cols) + " FROM scores WHERE symbol = ANY($1::text[]) ORDER BY symbol, (model = 'v1') DESC, updated_at DESC"  # nosec B608
        for r in await conn.fetch(sql, symbols):
            for c in cols:
                out[r["symbol"]][c] = float(r[c]) if r[c] is not None else None
    for s in symbols:
        cp = out[s].get("change_pct")
        out[s]["move_abs"] = abs(cp) if cp is not None else None
    if needed & TECH:
        bars: Dict[str, List[Any]] = {}
        for r in await conn.fetch("SELECT symbol, close, high, low, volume FROM price_daily WHERE symbol = ANY($1::text[]) AND day > current_date - 420 ORDER BY symbol, day", symbols):
            bars.setdefault(r["symbol"], []).append(r)
        for s, rows in bars.items():
            closes = [float(r["close"]) for r in rows]
            price = closes[-1]
            r14 = rsi(closes, 14)[-1] if len(closes) > 14 else None
            e50, e200 = (ema(closes, 50)[-1] if len(closes) >= 50 else None), (ema(closes, 200)[-1] if len(closes) >= 200 else None)
            year = rows[-252:]
            hi = max(float(r["high"] if r["high"] is not None else r["close"]) for r in year)
            lo = min(float(r["low"] if r["low"] is not None else r["close"]) for r in year)
            vols = [r["volume"] for r in rows[-21:-1] if r["volume"]]
            out[s].update({
                "rsi14": round(r14, 2) if r14 is not None else None,
                "ema50_gap": round((price - e50) / e50 * 100, 2) if e50 else None,
                "ema200_gap": round((price - e200) / e200 * 100, 2) if e200 else None,
                "from_high52": round((hi - price) / hi * 100, 2) if hi else None,
                "from_low52": round((price - lo) / lo * 100, 2) if lo else None,
                "volume_x": round(rows[-1]["volume"] / (sum(vols) / len(vols)), 2) if rows[-1]["volume"] and len(vols) >= 10 else None,
            })
    if needed & SNAP:
        seen = set()
        for r in await conn.fetch("SELECT symbol, section, body FROM snapshots WHERE symbol = ANY($1::text[]) AND section IN ('financials', 'ownership') "
                                  "ORDER BY (statement = 'consolidated') DESC", symbols):
            if (r["symbol"], r["section"]) in seen:
                continue
            seen.add((r["symbol"], r["section"]))
            try:
                body = json.loads(r["body"])
            except ValueError:
                continue
            if r["section"] == "financials":
                rows = ((body.get("quarterly") or {}).get("pl") or {}).get("rows") or {}
                for key, col in (("net_profit", "q_net_profit"), ("revenue", "q_revenue")):
                    vals = [x for x in rows.get(key) or [] if x is not None]
                    out[r["symbol"]][col] = float(vals[-1]) if vals else None
                g = quarter_gap(rows)
                if g:
                    qpl = (body.get("quarterly") or {}).get("pl") or {}
                    g["period"] = (qpl.get("periods") or [None])[-1]
                    g["end"] = (qpl.get("periodEnds") or [None])[-1]
                out[r["symbol"]]["rev_profit_gap"] = g["gap"] if g else None
                out[r["symbol"]]["_gap_detail"] = g
            else:
                series = body.get("series") or {}
                for key, col in (("promoters", "promoter_chg"), ("fii", "fii_chg")):
                    vals = [x for x in series.get(key) or [] if x is not None]
                    out[r["symbol"]][col] = round(float(vals[-1]) - float(vals[-2]), 2) if len(vals) >= 2 else None
    return out


async def current_value(conn, symbol: str, metric: str) -> Optional[float]:
    """Today's value of one metric, for the "currently 31.2" hint and to record the starting side when an alert is created."""
    if metric in EVENTS:
        return None
    return (await load_values(conn, [symbol], {metric})).get(symbol, {}).get(metric)


async def newest_feed_id(conn, symbol: str) -> int:
    return int(await conn.fetchval("SELECT coalesce(max(id), 0) FROM feed_items WHERE symbol = $1", symbol))


async def event_hits(conn, a: Dict[str, Any]) -> Tuple[List[Any], int]:
    """New feed items for an event alert (those with an id above the last one seen) and the highest id now."""
    seen = int(a["last_value"] or 0)
    if a["metric"] == "result_soon":
        days = int(a["value"] or 7)
        rows = await conn.fetch("SELECT id, title, item_date, category, link FROM feed_items WHERE symbol = $1 AND kind = 'result' AND id > $2 "
                                "AND item_date BETWEEN current_date AND current_date + $3::int ORDER BY id", a["symbol"], seen, days)
    elif a["metric"] == "new_filing":
        rows = await conn.fetch("SELECT id, title, item_date, category, link FROM feed_items WHERE symbol = $1 AND kind IN ('document', 'result') AND id > $2 ORDER BY id", a["symbol"], seen)
    else:
        kw = "%" + (a["keyword"] or "").lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        rows = await conn.fetch("SELECT id, title, item_date, category, link FROM feed_items WHERE symbol = $1 AND id > $2 "
                                "AND (lower(title) LIKE $3 OR lower(coalesce(summary, '')) LIKE $3) ORDER BY id", a["symbol"], seen, kw)
    top = await newest_feed_id(conn, a["symbol"]) if a["metric"] != "result_soon" else max([int(r["id"]) for r in rows] + [seen])
    return list(rows), max(top, seen)


# ------------------------------------------------------------------ delivery
def email_body(title: str, body: str, link: str) -> Tuple[str, str]:
    return (f"FinLit alert: {title}",
            f"{title}\n\n{body}\n\nOpen it: {link}\n\nThis is a notification about a rule you set, not investment advice. Manage or switch off alerts at {link.split('/stocks')[0]}/alerts.\n\nFinLit Ventures")


async def deliver(conn, mailer: Mailer, site_url: str, user: Dict[str, Any], a: Dict[str, Any], title: str, body: str, link: str) -> None:
    channels = set(a["channels"] or [])
    await conn.execute("INSERT INTO notifications (user_id, alert_id, symbol, kind, title, body, link, push) VALUES ($1, $2, $3, 'alert', $4, $5, $6, $7)",
                       user["id"], a["id"], a["symbol"], title, body, link, "browser" in channels)
    prefs = json.loads(user["prefs"]) if isinstance(user["prefs"], str) else (user["prefs"] or {})
    if "email" in channels and prefs.get("alerts") is not False:
        subject, text = email_body(title, body, f"{site_url}{link}")
        try:
            await mailer.send(user["email"], subject, text)
        except Exception:  # mail trouble must not stop the other members' alerts
            log.exception("alert email failed")


# ------------------------------------------------------------------ built-in alert: revenue and profit moved apart
AUTO_GAP_LIMIT = 15.0     # percentage points
AUTO_GAP_RECENT_DAYS = 120   # only for a quarter that ended lately: an old result is not news
AUTO_GAP_PER_RUN = 10     # at most this many per member per run, so a first run cannot flood anyone


def watchlist_symbols(raw: Any) -> List[str]:
    """Every symbol on every list of a member's saved watchlist."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except ValueError:
        return []
    out: List[str] = []
    for lst in (data.get("lists") or []) if isinstance(data, dict) else []:
        for sym in (lst.get("symbols") or []) if isinstance(lst, dict) else []:
            if isinstance(sym, str) and sym and sym.upper() not in out:
                out.append(sym.upper())
    return out


async def auto_profit_gap(pool, mailer: Mailer, site_url: str, today: Optional[date] = None) -> int:
    """Silver and Gold members are told, once per company and quarter, when a company on their watchlist reported revenue growth and
    net-profit growth (each against the same quarter last year) at least AUTO_GAP_LIMIT points apart. A member can switch it off
    with the preference profitGap = false."""
    today = today or date.today()
    sent = 0
    async with pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT u.id, u.email, s.watchlist, s.prefs FROM users u JOIN user_state s ON s.user_id = u.id "
            "WHERE u.status = 'active' AND u.email_verified_at IS NOT NULL AND u.plan IN ('silver', 'gold') "
            "AND (u.plan_until IS NULL OR u.plan_until > now())")
        wl = {u["id"]: watchlist_symbols(u["watchlist"]) for u in users}
        symbols = sorted({x for v in wl.values() for x in v})
        if not symbols:
            return 0
        values = await load_values(conn, symbols, {"rev_profit_gap"})
        for u in users:
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            if prefs.get("profitGap") is False:
                continue
            n = 0
            for sym in wl[u["id"]]:
                d = (values.get(sym) or {}).get("_gap_detail")
                if not d or d["gap"] < AUTO_GAP_LIMIT or not d.get("period") or not d.get("end"):
                    continue
                try:
                    if (today - date.fromisoformat(str(d["end"])[:10])).days > AUTO_GAP_RECENT_DAYS:
                        continue
                except ValueError:
                    continue
                if n >= AUTO_GAP_PER_RUN:
                    break
                try:
                    fresh = await conn.fetchval("INSERT INTO auto_alert_sent (user_id, symbol, kind, period) VALUES ($1, $2, 'profit_gap', $3) ON CONFLICT DO NOTHING RETURNING 1",
                                                u["id"], sym, str(d["period"]))
                    if not fresh:
                        continue
                    title, body = headline({"symbol": sym, "metric": "rev_profit_gap", "op": "above", "value": AUTO_GAP_LIMIT}, d["gap"], d)
                    await deliver(conn, mailer, site_url, {"id": u["id"], "email": u["email"], "prefs": u["prefs"]},
                                  {"id": None, "symbol": sym, "channels": ["app", "browser"]}, title, body, f"/stocks/{sym}#quarter")
                    n += 1
                    sent += 1
                except Exception:   # one member's trouble must not stop the rest
                    log.exception("built-in profit-gap alert failed for %s", sym)
    log.info("built-in profit-gap alerts: %d sent", sent)
    return sent


# ------------------------------------------------------------------ the worker run
async def evaluate(pool, mailer: Mailer, site_url: str, kind: str = "all") -> int:
    """Check every active alert (kind: live, daily or all). Returns how many fired."""
    fired = 0
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT a.*, u.email, u.plan, u.id AS uid, s.prefs FROM alerts a JOIN users u ON u.id = a.user_id LEFT JOIN user_state s ON s.user_id = u.id "
            "WHERE a.status = 'active' AND u.status = 'active' AND u.email_verified_at IS NOT NULL")
        todo = []
        for r in rows:
            a = dict(r)
            meta = METRICS.get(a["metric"])
            if not meta or not allowed(a["plan"], a["metric"]):
                continue
            if kind == "live" and not meta["live"]:
                continue
            if kind == "daily" and meta["live"] and a["metric"] not in ("price", "change_pct", "move_abs"):
                continue
            todo.append(a)
        thresholds = [a for a in todo if a["op"] != "event"]
        values = await load_values(conn, sorted({a["symbol"] for a in thresholds}), {a["metric"] for a in thresholds}) if thresholds else {}
        for a in todo:
            user = {"id": a["uid"], "email": a["email"], "prefs": a["prefs"]}
            link = f"/stocks/{a['symbol']}"
            try:
                if a["op"] == "event":
                    hits, top = await event_hits(conn, a)
                    if hits:
                        h = hits[0]
                        more = f" (+{len(hits) - 1} more)" if len(hits) > 1 else ""
                        title = f"{a['symbol']} – {h['title']}{more}"
                        body = f"{METRICS[a['metric']]['label']}: {h['title']} ({h['category'] or 'update'}, {h['item_date']})."
                        await deliver(conn, mailer, site_url, user, a, title, body, link)
                        fired += 1
                    await conn.execute("UPDATE alerts SET last_value = $2, last_checked = now(), fired_count = fired_count + $3, "
                                       "last_fired_at = CASE WHEN $3 > 0 THEN now() ELSE last_fired_at END, status = CASE WHEN $3 > 0 AND repeat = 'once' THEN 'done' ELSE status END WHERE id = $1",
                                       a["id"], top, 1 if hits else 0)
                    continue
                v = values.get(a["symbol"], {}).get(a["metric"])
                if v is None:
                    await conn.execute("UPDATE alerts SET last_checked = now() WHERE id = $1", a["id"])
                    continue
                limit = float(a["value"])
                met = v >= limit if a["op"] == "above" else v <= limit
                crossed = met and a["met"] is False
                cooled = a["last_fired_at"] is None or await conn.fetchval("SELECT $1::timestamptz < now() - make_interval(hours => $2)", a["last_fired_at"], COOLDOWN_HOURS)
                fire = crossed and cooled
                if fire:
                    title, body = headline(a, v, values.get(a["symbol"], {}).get("_gap_detail"))
                    await deliver(conn, mailer, site_url, user, a, title, body, link)
                    fired += 1
                await conn.execute(
                    "UPDATE alerts SET met = $2, last_value = $3, last_checked = now(), fired_count = fired_count + $4, "
                    "last_fired_at = CASE WHEN $4 > 0 THEN now() ELSE last_fired_at END, status = CASE WHEN $4 > 0 AND repeat = 'once' THEN 'done' ELSE status END WHERE id = $1",
                    a["id"], met if not (crossed and not cooled) else False, v, 1 if fire else 0)
            except Exception:  # one broken alert must not stop the rest
                log.exception("alert %s failed", a["id"])
    log.info("alerts (%s): %d fired", kind, fired)
    if kind in ("daily", "all"):
        try:
            fired += await auto_profit_gap(pool, mailer, site_url)
            from .plalerts import auto_pl_flags   # imported here: plalerts uses deliver() from this module
            fired += await auto_pl_flags(pool, mailer, site_url)
        except Exception:
            log.exception("built-in alerts failed")
    return fired
