"""Built-in alerts for the eight revenue-versus-profit divergence cases (finlit.plflags). Silver and Gold members are told, once per
company, case and period, when a company on their watchlist's latest result matches one. Dedupe is the primary key of auto_alert_sent
(user, symbol, kind = pl_flag_<case>, period). A member can switch these off with the preference profitGap = false, the same switch as
the revenue-versus-profit gap alert, since they are one family. Information only: the message says what the reported numbers did and
that it is worth a closer look, never what to do."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from .alertengine import deliver, watchlist_symbols
from .auth.mailer import Mailer
from .plflags import pl_flags, period_views

log = logging.getLogger("finlit.plalerts")

RECENT_DAYS = {"quarterly": 120, "annual": 200}   # an old result is not news
PER_RUN = 10                                       # at most this many per member per run, so a first run cannot flood anyone
FOOTER = "This is worth a closer look at the company's report. It describes reported numbers and is not investment advice."


def kind_of(flag: Dict[str, Any]) -> str:
    return f"pl_flag_{flag['case']}"


def _sg(v: float) -> str:
    return ("−" if v < 0 else "+" if v > 0 else "") + f"{abs(v):.1f}%"


def _view_line(v: Dict[str, Any], lender: bool) -> str:
    g = v["growth"]
    parts = [f"{n} {_sg(g[k])}" for n, k in (("revenue", "revenue"), ("net profit", "profit")) if g.get(k) is not None]
    if not lender and g.get("operating") is not None:
        parts.append(f"operating profit {_sg(g['operating'])}")
    return f"{v['period']} against {v['against']}: " + ", ".join(parts) if parts else ""


def message(symbol: str, flag: Dict[str, Any], views: Optional[Dict[str, Optional[Dict[str, Any]]]] = None, lender: bool = False) -> Tuple[str, str]:
    """The title names the period kind ('latest quarter' or 'latest year') so a quarterly result is never taken for the annual one. When both
    views exist, the body also gives the other one's figures."""
    quarter = flag["scope"] == "quarterly"
    title = f"{symbol} – {flag['title']}" + ("" if flag["case"] == 8 else " in the latest quarter" if quarter else " in the latest year") + f" ({flag['period']})"
    extra = []
    for sc in ("quarterly", "annual"):
        v = (views or {}).get(sc)
        if v:
            ln = _view_line(v, lender)
            if ln:
                extra.append(f"{'Latest quarter' if sc == 'quarterly' else 'Latest year'}, {ln}.")
    return title, " ".join([flag["text"], *extra, flag["why"], FOOTER])


def link_for(symbol: str, flag: Dict[str, Any]) -> str:
    return f"/stocks/{symbol}#{'quarter' if flag['scope'] == 'quarterly' else 'financials'}"


def is_recent(table: Optional[Dict[str, Any]], today: date) -> bool:
    ends = (table or {}).get("periodEnds") or []
    try:
        return bool(ends) and 0 <= (today - date.fromisoformat(str(ends[-1])[:10])).days <= RECENT_DAYS["quarterly" if (table or {}).get("period") == "quarterly" else "annual"]
    except (ValueError, TypeError):
        return False


def fresh_flags(body: Dict[str, Any], today: date, lender: bool = False) -> List[Dict[str, Any]]:
    """Flags for one company's financials section that are about a recently reported period. The yearly and the quarterly tables are tested
    separately, each with its own period, so a quarter that triggers is alerted as the quarter and a year as the year."""
    yearly = ((body.get("yearly") or {}).get("pl")) or None
    quarterly = ((body.get("quarterly") or {}).get("pl")) or None
    if yearly is not None:
        yearly = {**yearly, "period": "yearly"}
    if quarterly is not None:
        quarterly = {**quarterly, "period": "quarterly"}
    out = []
    for f in pl_flags(yearly, quarterly, lender):
        if is_recent(quarterly if f["scope"] == "quarterly" else yearly, today):
            out.append(f)
    return out


async def auto_pl_flags(pool, mailer: Mailer, site_url: str, today: Optional[date] = None) -> int:
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
        flags: Dict[str, List[Dict[str, Any]]] = {}
        views: Dict[str, Dict[str, Optional[Dict[str, Any]]]] = {}
        lenders = set()
        for r in await conn.fetch("SELECT symbol, (body::jsonb #>> '{dataQuality,isBank}') AS b FROM snapshots WHERE symbol = ANY($1::text[]) AND section = 'summary' ORDER BY (statement = 'consolidated') DESC", symbols):
            if r["b"] == "true":
                lenders.add(r["symbol"])
        seen = set()
        # only the two profit-and-loss tables the flags read, cut inside the database (a whole financials report is ~40 KB)
        for r in await conn.fetch("SELECT symbol, jsonb_build_object('yearly', jsonb_build_object('pl', body::jsonb #> '{yearly,pl}'), "
                                  "'quarterly', jsonb_build_object('pl', body::jsonb #> '{quarterly,pl}'))::text AS body FROM snapshots "
                                  "WHERE symbol = ANY($1::text[]) AND section = 'financials' ORDER BY (statement = 'consolidated') DESC", symbols):
            if r["symbol"] in seen:
                continue
            seen.add(r["symbol"])
            try:
                data = json.loads(r["body"])
                lend = r["symbol"] in lenders
                flags[r["symbol"]] = fresh_flags(data, today, lend)
                views[r["symbol"]] = period_views((data.get("yearly") or {}).get("pl"), (data.get("quarterly") or {}).get("pl"), lend)
            except (ValueError, TypeError, AttributeError):
                continue
        for u in users:
            prefs = json.loads(u["prefs"]) if isinstance(u["prefs"], str) else (u["prefs"] or {})
            if prefs.get("profitGap") is False:
                continue
            n = 0
            for sym in wl[u["id"]]:
                for f in flags.get(sym, []):
                    if n >= PER_RUN:
                        break
                    try:
                        new = await conn.fetchval("INSERT INTO auto_alert_sent (user_id, symbol, kind, period) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING RETURNING 1",
                                                  u["id"], sym, kind_of(f), f["period"])
                        if not new:
                            continue
                        title, body = message(sym, f, views.get(sym), sym in lenders)
                        await deliver(conn, mailer, site_url, {"id": u["id"], "email": u["email"], "prefs": u["prefs"]},
                                      {"id": None, "symbol": sym, "channels": ["app", "browser"]}, title, body, link_for(sym, f))
                        n += 1
                        sent += 1
                    except Exception:   # one member's trouble must not stop the rest
                        log.exception("built-in P&L flag alert failed for %s", sym)
    log.info("built-in P&L flag alerts: %d sent", sent)
    return sent
