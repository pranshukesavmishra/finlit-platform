"""Built-in Sector Rotation alerts for the industries of the stocks on a member's watchlist (docs/SECTORS.md, "Sector Rotation").

    corner  "My stock's industry moved corner": the industry's confirmed corner changed at the week's close (after two weekly closes in the new one)
    rank    "Industry climbed or fell 5+ places in 4 weeks": the 4-week rank change reached 5 places this week, having been under 5 the week before

Both are worked out from the nightly rotation file alone: it carries each group's weeks in its corner, the corner it came from and its rank at each of the last 26
weekly closes, so this week's reading and last week's are both in it. They are sent only once the week has closed (`week_closed`), so a corner that is still
"this week's reading" is never announced; the confirmed one is. Dedupe is the primary key of auto_alert_sent (user, symbol, kind, period), where the period is the
week's closing date. Silver and Gold members (the same family as the other built-in alerts); a member switches them off with the preferences rotationCorner and
rotationRank. The messages describe what the industry's returns and rank did against the average industry; they are information, never advice."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from . import sector_data as sd
from .alertengine import deliver, watchlist_symbols
from .auth.mailer import Mailer

log = logging.getLogger("finlit.rotation_alerts")
PER_RUN = 10                 # at most this many per member per run
MOVE_PLACES = 5
FOOTER = "This describes how the industry's past returns compare with the average industry. It is information, not investment advice."
KINDS = {"corner": "rotation_corner", "rank": "rotation_rank"}
PREF = {"corner": "rotationCorner", "rank": "rotationRank"}
PREF_DEFAULT = {"corner": True, "rank": False}      # the rank alert is opt-in


def _hist(row: Dict[str, Any]) -> List[Optional[int]]:
    return [h.get("rank") for h in row.get("rank_history") or []]


def events_for(row: Dict[str, Any], week_closed: bool = True) -> List[Dict[str, Any]]:
    """The alert events of one group's rotation row (empty until the week has closed)."""
    if not week_closed:
        return []
    out: List[Dict[str, Any]] = []
    if row.get("weeks_in_corner") == 1 and row.get("previous_corner_name") and row.get("corner_name"):
        out.append({"kind": "corner", "period": str(row.get("corner_since")), "from": row["previous_corner_name"], "to": row["corner_name"]})
    ch = row.get("rank_change_4w")
    if ch is not None and abs(ch) >= MOVE_PLACES:
        h = _hist(row)
        before = (h[-6] - h[-2]) if len(h) >= 6 and h[-6] is not None and h[-2] is not None else None     # last week's 4-week change
        if before is None or abs(before) < MOVE_PLACES or (before > 0) != (ch > 0):
            out.append({"kind": "rank", "period": str((row.get("rank_history") or [{}])[-1].get("date")), "change": int(ch)})
    return out


def message(symbol: str, row: Dict[str, Any], ev: Dict[str, Any]) -> tuple:
    where = f"rank {row['rank']} of {row['ranked']}" if row.get("rank") and row.get("ranked") else "no rank this week"
    if ev["kind"] == "corner":
        title = f"{symbol} – its industry, {row['name']}, moved from {ev['from']} to {ev['to']}"
        body = (f"{row['name']} was {ev['from']} and has been {ev['to']} since this week's close, after two weekly closes there ({where}). "
                f"Over 6 months it is {abs(row['strength_pts']):.1f} points {'ahead of' if row['strength_pts'] >= 0 else 'behind'} the average industry. {FOOTER}")
    else:
        n = abs(ev["change"])
        title = f"{symbol} – its industry, {row['name']}, {'climbed' if ev['change'] > 0 else 'fell'} {n} places in 4 weeks"
        body = f"{row['name']} {'climbed' if ev['change'] > 0 else 'fell'} {n} places in the rotation ranking over the last 4 weekly closes and is now {where}. {FOOTER}"
    return title, body


async def auto_rotation_alerts(pool, mailer: Mailer, site_url: str, release=None) -> int:
    """Send this week's rotation alerts to the watchlists of Silver and Gold members. `release` is a live release folder (default: the one `current` points at)."""
    rel = release or sd.live_release()
    rmap = sd.read_json(rel / "rotation" / "_map.json") if rel else None
    if not isinstance(rmap, dict) or not rmap.get("week_closed"):
        return 0
    by_slug = {r["slug"]: r for r in rmap.get("rows", []) if isinstance(r, dict) and r.get("slug")}
    events = {slug: events_for(r, True) for slug, r in by_slug.items()}
    if not any(events.values()):
        return 0
    sent = 0
    async with pool.acquire() as conn:
        users = await conn.fetch(
            "SELECT u.id, u.email, s.watchlist, s.prefs FROM users u JOIN user_state s ON s.user_id = u.id "
            "WHERE u.status = 'active' AND u.email_verified_at IS NOT NULL AND u.plan IN ('silver', 'gold') "
            "AND (u.plan_until IS NULL OR u.plan_until > now())")
        group_of: Dict[str, Optional[str]] = {}
        for u in users:
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            wanted = {k for k in KINDS if (prefs.get(PREF[k]) if PREF[k] in prefs else PREF_DEFAULT[k]) is True}
            if not wanted:
                continue
            n = 0
            for sym in watchlist_symbols(u["watchlist"]):
                if not sd.SYMBOL.match(sym):
                    continue
                if sym not in group_of:
                    doc = sd.read_json(rel / f"{sym}.json")
                    group_of[sym] = (((doc or {}).get("sector") or {}).get("group") or {}).get("slug") if isinstance(doc, dict) else None
                slug = group_of[sym]
                for ev in events.get(slug or "", []):
                    if ev["kind"] not in wanted or n >= PER_RUN:
                        continue
                    try:
                        new = await conn.fetchval("INSERT INTO auto_alert_sent (user_id, symbol, kind, period) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1",
                                                  u["id"], sym, KINDS[ev["kind"]], ev["period"])
                        if not new:
                            continue
                        title, body = message(sym, by_slug[slug], ev)
                        await deliver(conn, mailer, site_url, {"id": u["id"], "email": u["email"], "prefs": u["prefs"]},
                                      {"id": None, "symbol": sym, "channels": ["app", "browser"]}, title, body, "/sectors/rotation")
                        n += 1
                        sent += 1
                    except Exception:   # one member's trouble must not stop the rest
                        log.exception("built-in rotation alert failed for %s", sym)
    log.info("built-in rotation alerts: %d sent", sent)
    return sent
