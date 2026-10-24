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
MODEL = {"overall", "pillar_quality", "pillar_growth", "pillar_profitability", "pillar_balance", "pillar_technical", "fundamental_score", "score_change",
         "strengths_count", "watchouts_count"}
LEGACY_KEYS = {"change_pct": "ret_1d", "return_1m": "ret_1m", "return_1y": "ret_1y", "sales_cagr": "sales_cagr_5y", "profit_cagr": "profit_cagr_5y"}


def matches(row: Dict[str, Any], state: Dict[str, Any], members: Dict[str, set] = None) -> bool:
    """Does one company (a `scores` row with its metrics) match a saved screen? Same rules as the screener page."""
    raw = row.get("metrics")
    metrics = json.loads(raw) if isinstance(raw, str) else (raw or {})
    for key, rg in (state.get("ranges") or {}).items():
        key = LEGACY_KEYS.get(key, key)
        v = metrics.get(key)
        if v is None:
            v = row.get({v2: k2 for k2, v2 in LEGACY_KEYS.items()}.get(key, key))
        if v is None:
            return False
        v = float(v)
        if rg.get("min") is not None and v < rg["min"]:
            return False
        if rg.get("max") is not None and v > rg["max"]:
            return False
    sectors = state.get("sectors") or []
    if sectors and (row.get("macro_sector") or row.get("sector")) not in sectors:
        return False
    if state.get("industries") and row.get("industry") not in state["industries"]:
        return False
    if state.get("indices") and members is not None and not any(row["symbol"] in members.get(c, ()) for c in state["indices"]):
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
        # only the figures the members' screens filter on leave the database (each company carries ~250; a screen uses a handful)
        from .screener.data import LEGACY
        used = sorted({LEGACY_KEYS.get(k, k) for u in users for sc in ((json.loads(u["screens"]) if isinstance(u["screens"], str) else u["screens"]) or [])
                       for k in ((sc.get("state") or {}).get("ranges") or {})})
        cols = ", ".join(sorted(set(LEGACY.values())))   # the flat columns `matches` falls back to
        universe = [dict(r) for r in await conn.fetch(
            f"SELECT DISTINCT ON (symbol) symbol, name, sector, macro_sector, industry, band, {cols}, "  # nosec B608 - fixed column names
            "(SELECT jsonb_object_agg(e.key, e.value) FROM jsonb_each(metrics) e WHERE e.key = ANY($1::text[])) AS metrics "
            "FROM scores WHERE model = 'v1' ORDER BY symbol, updated_at DESC", used)]
        members: Dict[str, set] = {}
        for r in await conn.fetch("SELECT index_code, symbol FROM index_members"):
            members.setdefault(r["index_code"], set()).add(r["symbol"])
        for u in users:
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            if prefs.get("screenAlerts") is False:
                continue
            for sc in (json.loads(u["screens"]) if isinstance(u["screens"], str) else u["screens"]) or []:
                state = sc.get("state") or {}
                # model filters are a Silver feature; never reveal scores to a Basic member through an email
                gold = u["plan"] == "gold"
                from .screener.catalog import BY_KEY, allowed
                keys = {LEGACY_KEYS.get(k, k) for k in (state.get("ranges") or {})}
                # members only get alerts for filters their plan includes; never reveal locked data through an email
                if not all(k in BY_KEY and allowed(u["plan"], BY_KEY[k].tier) for k in keys) or (state.get("bands") and not gold):
                    continue
                hit = [r for r in universe if matches(r, state, members)]
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
