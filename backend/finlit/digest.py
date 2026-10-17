"""The weekly "week ahead" email, for members who switched it on in Account → Appearance.

One plain-text message: result dates for the stocks they follow, IPOs open or opening, how their stocks moved, and score changes.
Sent at most once per ISO week per member.
"""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import List

from .auth.mailer import Mailer

log = logging.getLogger("finlit.digest")


async def build(conn, user_id, symbols: List[str], today: date, site_url: str) -> str | None:
    horizon = today + timedelta(days=7)
    results = await conn.fetch("SELECT symbol, company, item_date, period FROM feed_items WHERE kind = 'result' AND item_date BETWEEN $1 AND $2 "
                               "AND (cardinality($3::text[]) = 0 OR symbol = ANY($3::text[])) ORDER BY item_date, symbol LIMIT 12", today, horizon, symbols)
    ipos = await conn.fetch("SELECT name, open_date, close_date, price_high, lot_size FROM ipos WHERE close_date >= $1 AND open_date <= $2 ORDER BY open_date LIMIT 6", today, horizon)
    moves = await conn.fetch("SELECT DISTINCT ON (symbol) symbol, name, change_pct, return_1m FROM scores WHERE symbol = ANY($1::text[]) AND change_pct IS NOT NULL "
                             "ORDER BY symbol, updated_at DESC", symbols) if symbols else []
    moves = sorted(moves, key=lambda r: abs(float(r["change_pct"])), reverse=True)[:5]
    changes = []
    for sym in symbols[:60]:
        h = await conn.fetch("SELECT day, overall FROM score_history WHERE symbol = $1 AND model = 'v1' AND overall IS NOT NULL ORDER BY day DESC LIMIT 40", sym)
        if len(h) >= 2:
            old = next((x for x in h if (h[0]["day"] - x["day"]).days >= 6), None)
            if old and abs(h[0]["overall"] - old["overall"]) >= 5:
                changes.append((sym, old["overall"], h[0]["overall"]))
    if not (results or ipos or moves or changes):
        return None
    out = ["Your week ahead on FinLit", ""]
    if results:
        out += ["RESULTS THIS WEEK"] + [f"  {r['item_date']:%a %d %b}  {r['symbol'] or r['company']}  {r['period'] or ''}".rstrip() for r in results] + [""]
    if ipos:
        out += ["IPOs OPEN OR OPENING"] + [f"  {r['name']}: {r['open_date']:%d %b} to {r['close_date']:%d %b}" + (f", up to ₹{float(r['price_high']):,.0f}, lot {r['lot_size']}" if r["price_high"] and r["lot_size"] else "") for r in ipos] + [""]
    if moves:
        out += ["YOUR BIGGEST MOVERS"] + [f"  {r['symbol']:<12} {float(r['change_pct']):+.1f}% today" for r in moves] + [""]
    if changes:
        out += ["SCORE CHANGES"] + [f"  {s:<12} {a} → {b}" for s, a, b in changes[:6]] + [""]
    out += [f"Open your dashboard: {site_url}/dashboard", "", "You get this because you switched on the weekly email. Turn it off in Account → Appearance. Information only, not investment advice.", "", "FinLit Ventures"]
    return "\n".join(out)


async def send_digests(pool, mailer: Mailer, site_url: str, today: date | None = None) -> int:
    today = today or date.today()
    week = today - timedelta(days=today.weekday())
    sent = 0
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT u.id, u.email, s.watchlist, s.prefs FROM user_state s JOIN users u ON u.id = s.user_id "
                                 "WHERE u.status = 'active' AND u.email_verified_at IS NOT NULL AND (s.prefs ->> 'digest') = 'true'")
        for u in users:
            if await conn.fetchval("SELECT 1 FROM digest_log WHERE user_id = $1 AND week = $2", u["id"], week):
                continue
            wl = json.loads(u["watchlist"]) if isinstance(u["watchlist"], str) else (u["watchlist"] or {})
            symbols = sorted({s for lst in wl.get("lists", []) for s in lst.get("symbols", [])})
            body = await build(conn, u["id"], symbols, today, site_url)
            if not body:
                continue
            try:
                await mailer.send(u["email"], "Your week ahead on FinLit", body)
            except Exception:
                log.exception("digest mail failed")
                continue
            await conn.execute("INSERT INTO digest_log (user_id, week) VALUES ($1, $2) ON CONFLICT DO NOTHING", u["id"], week)
            sent += 1
    log.info("digests: %d sent", sent)
    return sent
