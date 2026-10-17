"""Target-price alerts: when a stock on a Silver or Gold member's watchlist crosses the target price they set, send one email.

Runs from the worker every few minutes in market hours. A stock only alerts when it *crosses* its target (the side changes
since the last check), at most once a day per stock, and never for members who switched alerts off in their preferences.
"""

from __future__ import annotations

import json
import logging
from typing import List, Tuple

from .auth.mailer import Mailer

log = logging.getLogger("finlit.alerts")


def alert_mail(symbol: str, name: str, price: float, target: float, link: str) -> Tuple[str, str]:
    above = price >= target
    return (f"{symbol} crossed your target of ₹{target:,.2f}",
            f"{name} ({symbol}) is now ₹{price:,.2f}, {'above' if above else 'below'} the target of ₹{target:,.2f} you set in your FinLit watchlist.\n\n"
            f"Open it: {link}\n\nThis is a price notification, not investment advice. Turn alerts off any time in Account → Appearance.\n\nFinLit Ventures")


async def check_alerts(pool, mailer: Mailer, site_url: str) -> int:
    async with pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT u.id, u.email, s.watchlist, s.prefs FROM user_state s JOIN users u ON u.id = s.user_id "
            "WHERE u.status = 'active' AND u.email_verified_at IS NOT NULL AND u.plan IN ('silver', 'gold') "
            "AND (u.plan_until IS NULL OR u.plan_until > now()) AND s.watchlist <> '{}'::jsonb")
        sent = 0
        for u in users:
            wl = json.loads(u["watchlist"]) if isinstance(u["watchlist"], str) else u["watchlist"]
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            targets = {sym: m["target"] for sym, m in (wl.get("meta") or {}).items() if m.get("target")}
            if not targets or prefs.get("alerts") is False:
                continue
            prices = {r["symbol"]: (r["price"], r["name"]) for r in await conn.fetch(
                "SELECT DISTINCT ON (symbol) symbol, price, name FROM scores WHERE symbol = ANY($1::text[]) AND price IS NOT NULL "
                "ORDER BY symbol, updated_at DESC", list(targets))}
            for sym, target in targets.items():
                if sym not in prices:
                    continue
                price, name = float(prices[sym][0]), prices[sym][1] or sym
                side = 1 if price >= float(target) else -1
                prev = await conn.fetchrow("SELECT side, target, alerted_at FROM alert_state WHERE user_id = $1 AND symbol = $2", u["id"], sym)
                crossed = prev is not None and float(prev["target"]) == float(target) and prev["side"] != side
                recent = prev is not None and prev["alerted_at"] is not None and await conn.fetchval("SELECT $1::timestamptz > now() - interval '1 day'", prev["alerted_at"])
                if crossed and not recent:
                    subject, body = alert_mail(sym, name, price, float(target), f"{site_url}/stocks/{sym}")
                    try:
                        await mailer.send(u["email"], subject, body)
                        sent += 1
                    except Exception:  # mail trouble must not stop the other members' alerts
                        log.exception("alert mail failed")
                        continue
                await conn.execute(
                    "INSERT INTO alert_state (user_id, symbol, target, side, alerted_at) VALUES ($1, $2, $3, $4, CASE WHEN $5 THEN now() END) "
                    "ON CONFLICT (user_id, symbol) DO UPDATE SET target = EXCLUDED.target, side = EXCLUDED.side, "
                    "alerted_at = CASE WHEN $5 THEN now() ELSE alert_state.alerted_at END",
                    u["id"], sym, target, side, bool(crossed and not recent))
    log.info("alerts: %d sent", sent)
    return sent
