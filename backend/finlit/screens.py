"""Saved-screen alerts: tell a member when a company newly matches one of their saved screener filters.

The filter rules mirror the website's screener (frontend/src/lib/screener.ts `applyFilters`) so the email and the page agree.
The first check only remembers what already matches; later checks email the companies that are new.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from .auth.mailer import Mailer

log = logging.getLogger("finlit.screens")
COLUMNS = {"market_cap", "price", "change_pct", "return_1m", "return_1y", "pe", "pb", "dividend_yield", "roe", "roce", "operating_margin", "sales_cagr",
           "profit_cagr", "debt_to_equity", "overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical"}
MODEL = {"overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical"}


def matches(row: Dict[str, Any], state: Dict[str, Any]) -> bool:
    for key, rg in (state.get("ranges") or {}).items():
        if key not in COLUMNS:
            continue
        v = row.get(key)
        if v is None:
            return False
        v = float(v)
        if rg.get("min") is not None and v < rg["min"]:
            return False
        if rg.get("max") is not None and v > rg["max"]:
            return False
    sectors = state.get("sectors") or []
    if sectors and row.get("sector") not in sectors:
        return False
    bands = state.get("bands") or []
    if bands and row.get("band") not in bands:
        return False
    return True


def screen_mail(name: str, new: List[Dict[str, Any]], total: int, link: str) -> tuple:
    lines = "\n".join(f"  {r['symbol']:<12} {r.get('name') or ''}" for r in new[:12])
    more = f"\n  …and {len(new) - 12} more" if len(new) > 12 else ""
    return (f"{len(new)} new match{'es' if len(new) != 1 else ''} for your screen “{name}”",
            f"Your saved screen “{name}” now matches {total} companies. New since the last check:\n\n{lines}{more}\n\nOpen the screener: {link}\n\n"
            "This is a notification about your own filters, not investment advice. Turn these emails off in Account → Appearance.\n\nFinLit Ventures")


async def check_screens(pool, mailer: Mailer, site_url: str) -> int:
    sent = 0
    async with pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT u.id, u.email, u.plan, s.screens, s.prefs FROM user_state s JOIN users u ON u.id = s.user_id WHERE u.status = 'active' "
            "AND u.email_verified_at IS NOT NULL AND s.screens <> '[]'::jsonb")
        if not users:
            return 0
        universe = [dict(r) for r in await conn.fetch("SELECT DISTINCT ON (symbol) * FROM scores WHERE model = 'v1' ORDER BY symbol, updated_at DESC")]
        for u in users:
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            if prefs.get("screenAlerts") is False:
                continue
            paid = u["plan"] in ("silver", "gold")
            for sc in (json.loads(u["screens"]) if isinstance(u["screens"], str) else u["screens"]) or []:
                state = sc.get("state") or {}
                # model filters are a Silver feature; never reveal scores to a Basic member through an email
                rows = [r for r in universe if paid or not (set((state.get("ranges") or {})) & MODEL or state.get("bands"))]
                hit = [r for r in rows if matches(r, state)]
                seen = await conn.fetchval("SELECT seen FROM screen_state WHERE user_id = $1 AND screen_name = $2", u["id"], sc["name"])
                now = [r["symbol"] for r in hit]
                if seen is not None:
                    new = [r for r in hit if r["symbol"] not in set(seen)]
                    if new and len(new) < 100:  # a huge jump means the data changed under the screen, not news
                        subject, body = screen_mail(sc["name"], new, len(hit), f"{site_url}/screener")
                        try:
                            await mailer.send(u["email"], subject, body)
                            sent += 1
                        except Exception:
                            log.exception("screen mail failed")
                            continue
                await conn.execute("INSERT INTO screen_state (user_id, screen_name, seen) VALUES ($1, $2, $3) ON CONFLICT (user_id, screen_name) DO UPDATE SET seen = EXCLUDED.seen, updated_at = now()",
                                   u["id"], sc["name"], now)
    log.info("screen alerts: %d sent", sent)
    return sent
