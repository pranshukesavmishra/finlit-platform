"""Score history, 'what changed' wording, score alerts and the three-year prune. Pure functions plus three small database helpers; the routes are in api.py.

One row per scheme per ISO week in mf_score_history (the last `score-mf` run of the week replaces the earlier ones, so running twice gives the same rows).
Everything the page says about change is built from those stored rows with neutral words: 'moved', 'ahead', 'behind'; never 'improved a lot' or advice."""

from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Optional, Sequence

log = logging.getLogger("finlit.mfscore")

RETENTION_DAYS = 3 * 366
PILLAR_COLS = (("performance", "perf"), ("risk", "risk"), ("cost", "cost"), ("quality", "quality"))
PILLAR_NAME = {"performance": "Performance", "risk": "Risk", "cost": "Cost", "quality": "Quality"}
MIN_SPAN_DAYS = 21          # a 'since last month' sentence needs two rows at least three weeks apart
LOOKBACK_DAYS = 28
BAND_ORDER = ("Poor", "Weak", "Average", "Healthy", "Strong")

HISTORY_INSERT = """INSERT INTO mf_score_history (key, week, run_date, kind, code, symbol, plan, grp, sub, final, perf, risk, cost, quality, label, status, rank, rank_of, percentile)
    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
    ON CONFLICT (key, week) DO UPDATE SET run_date = EXCLUDED.run_date, kind = EXCLUDED.kind, code = EXCLUDED.code, symbol = EXCLUDED.symbol, plan = EXCLUDED.plan, grp = EXCLUDED.grp,
      sub = EXCLUDED.sub, final = EXCLUDED.final, perf = EXCLUDED.perf, risk = EXCLUDED.risk, cost = EXCLUDED.cost, quality = EXCLUDED.quality, label = EXCLUDED.label,
      status = EXCLUDED.status, rank = EXCLUDED.rank, rank_of = EXCLUDED.rank_of, percentile = EXCLUDED.percentile"""


def week_of(d: date) -> date:
    """Monday of the ISO week."""
    return d - timedelta(days=d.weekday())


def history_row(r: tuple, run_date: date) -> tuple:
    """A job.row() tuple -> the history row (the columns are picked by position of job.UPSERT)."""
    (key, kind, code, symbol, plan, grp, _mtype, sub, _cat, _rd, _nd, final, _raw, perf, risk, cost, quality, label, status, _reason, _conf, _months, _cap, _flags, _pk, _pn,
     rank, rank_of, _scope, pct) = r[:30]
    return (key, week_of(run_date), run_date, kind, code, symbol, plan, grp, sub, final, perf, risk, cost, quality, label, status, rank, rank_of, pct)


def _f(v: Any) -> Optional[float]:
    return None if v is None else round(float(v), 1)


def point(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"date": r["run_date"].isoformat(), "week": r["week"].isoformat(), "final": _f(r["final"]), "label": r["label"], "status": r["status"],
            "pillars": {"performance": _f(r["perf"]), "risk": _f(r["risk"]), "cost": _f(r["cost"]), "quality": _f(r["quality"])},
            "rank": r["rank"], "rankOf": r["rank_of"], "percentile": None if r["percentile"] is None else int(r["percentile"])}


def changed_since(rows: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """rows oldest to newest (dicts with run_date, final, perf.. rank). The latest row against the row nearest 28 days before it (never nearer than 21 days):
    final score moved by X points, which part moved most, the rank change. None when the stored rows do not reach back far enough."""
    rated = [r for r in rows if r["final"] is not None]
    if len(rated) < 2:
        return None
    last = rated[-1]
    target = last["run_date"] - timedelta(days=LOOKBACK_DAYS)
    older = [r for r in rated[:-1] if (last["run_date"] - r["run_date"]).days >= MIN_SPAN_DAYS]
    if not older:
        return None
    prev = min(older, key=lambda r: abs((r["run_date"] - target).days))
    d_final = round(float(last["final"]) - float(prev["final"]), 1)
    moves = []
    for name, col in PILLAR_COLS:
        if last[col] is not None and prev[col] is not None:
            moves.append((name, round(float(last[col]) - float(prev[col]), 1)))
    big = max(moves, key=lambda m: abs(m[1])) if moves else None
    rank_from = prev["rank"] if prev["rank"] is not None and prev["rank_of"] is not None else None
    rank_to = last["rank"] if last["rank"] is not None and last["rank_of"] is not None else None
    return {"since": prev["run_date"].isoformat(), "until": last["run_date"].isoformat(), "from": _f(prev["final"]), "to": _f(last["final"]), "delta": d_final,
            "fromLabel": prev["label"], "toLabel": last["label"], "pillar": None if big is None else {"key": big[0], "name": PILLAR_NAME[big[0]], "delta": big[1]},
            "rankFrom": rank_from, "rankTo": rank_to, "rankOf": last["rank_of"], "text": change_text(prev, last, d_final, big, rank_from, rank_to)}


def _pts(x: float) -> str:
    return f"{abs(x):.1f}".rstrip("0").rstrip(".") + (" point" if abs(x) == 1 else " points")


def change_text(prev: Dict[str, Any], last: Dict[str, Any], d_final: float, big, rank_from, rank_to) -> str:
    if abs(d_final) < 0.05:
        s = f"The score is unchanged at {float(last['final']):.1f} since {prev['run_date'].strftime('%d %b %Y')}."
    else:
        s = (f"The score moved {'up' if d_final > 0 else 'down'} {_pts(d_final)}, from {float(prev['final']):.1f} to {float(last['final']):.1f}, "
             f"since {prev['run_date'].strftime('%d %b %Y')}.")
    if big and abs(big[1]) >= 0.5:
        s += f" {PILLAR_NAME[big[0]]} moved most ({'+' if big[1] > 0 else '-'}{abs(big[1]):.1f})."
    if prev["label"] and last["label"] and prev["label"] != last["label"]:
        s += f" The label moved from {prev['label']} to {last['label']}."
    if rank_from is not None and rank_to is not None and rank_from != rank_to:
        s += f" Its place in the category moved from {rank_from} to {rank_to} of {last['rank_of']}."
    elif rank_from is not None and rank_to is not None:
        s += f" Its place in the category is unchanged at {rank_to} of {last['rank_of']}."
    return s


# ------------------------------------------------------------------------------------------------------------------------------------ alerts
def alert_hit(kind: str, points: Optional[float], prev: Dict[str, Any], cur: Dict[str, Any]) -> bool:
    """band: the label changed between the two weekly rows; move: the final score moved by at least `points` either way."""
    if prev["final"] is None or cur["final"] is None:
        return False
    if kind == "band":
        return bool(prev["label"] and cur["label"] and prev["label"] != cur["label"])
    return points is not None and abs(float(cur["final"]) - float(prev["final"])) >= float(points) - 1e-9


def alert_text(name: str, prev: Dict[str, Any], cur: Dict[str, Any]) -> tuple:
    title = f"Score of {name}: {prev['label']} ({round(float(prev['final']))}) to {cur['label']} ({round(float(cur['final']))})"
    body = f"The FinLit Mutual Fund Health Score of {name} moved from {prev['label']} ({round(float(prev['final']))}) to {cur['label']} ({round(float(cur['final']))}). " \
           "It describes the fund's health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice."
    return title, body


async def fire_alerts(conn, week: date, keys: Iterable[str]) -> List[Dict[str, Any]]:
    """Inside the score transaction, after this week's rows are written: for every active alert on a scored fund, compare this week's row with the one before
    and, when the rule is met and this week has not been looked at yet, add the in-app notification. Returns the emails still to send (after the commit)."""
    keys = list(keys)
    if not keys:
        return []
    alerts = await conn.fetch("""SELECT a.id, a.user_id, a.key, a.name, a.kind, a.points, a.channels, u.email, s.prefs FROM mf_score_alerts a JOIN users u ON u.id = a.user_id
                                 LEFT JOIN user_state s ON s.user_id = u.id
                                 WHERE a.status = 'active' AND a.key = ANY($1::text[]) AND (a.last_week IS NULL OR a.last_week < $2)
                                   AND u.status = 'active' AND u.plan = 'gold' AND (u.plan_until IS NULL OR u.plan_until > now())""", keys, week)
    if not alerts:
        return []
    rows = await conn.fetch("""SELECT key, week, run_date, final, label FROM (SELECT *, row_number() OVER (PARTITION BY key ORDER BY week DESC) AS rn FROM mf_score_history
                               WHERE key = ANY($1::text[]) AND week <= $2) x WHERE rn <= 2 ORDER BY key, week""", list({a["key"] for a in alerts}), week)
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        by.setdefault(r["key"], []).append(dict(r))
    mails = []
    for a in alerts:
        pair = by.get(a["key"], [])
        if len(pair) == 2 and pair[1]["week"] == week and alert_hit(a["kind"], a["points"], pair[0], pair[1]):
            title, body = alert_text(a["name"], pair[0], pair[1])
            link = "/funds/" + a["key"][3:] if a["key"].startswith("mf:") else "/etfs/" + a["key"][4:]
            await conn.execute("INSERT INTO notifications (user_id, symbol, kind, title, body, link, push) VALUES ($1, $2, 'alert', $3, $4, $5, $6)",
                               a["user_id"], a["key"][:24], title, body, link, "browser" in (a["channels"] or []))
            await conn.execute("UPDATE mf_score_alerts SET fired_at = now(), fired_count = fired_count + 1 WHERE id = $1", a["id"])
            prefs = json.loads(a["prefs"]) if isinstance(a["prefs"], str) else (a["prefs"] or {})
            if "email" in (a["channels"] or []) and prefs.get("alerts") is not False:
                mails.append({"to": a["email"], "title": title, "body": body, "link": link})
        await conn.execute("UPDATE mf_score_alerts SET last_week = $2 WHERE id = $1", a["id"], week)
    return mails


async def send_mails(mails: Sequence[Dict[str, Any]], mailer, site_url: str) -> int:
    sent = 0
    for m in mails:
        subject = f"FinLit alert: {m['title']}"
        text = f"{m['title']}\n\n{m['body']}\n\nOpen it: {site_url}{m['link']}\n\nThis is a notification about a rule you set, not investment advice. Manage or switch off alerts at {site_url}/alerts.\n\nFinLit Ventures"
        try:
            await mailer.send(m["to"], subject, text)
            sent += 1
        except Exception:   # mail trouble must not stop the other members' alerts
            log.exception("score alert email failed")
    return sent


async def prune(conn, today: Optional[date] = None) -> int:
    """Rows older than three years go. Returns how many."""
    cut = (today or date.today()) - timedelta(days=RETENTION_DAYS)
    return int((await conn.execute("DELETE FROM mf_score_history WHERE week < $1", cut)).split()[-1])
