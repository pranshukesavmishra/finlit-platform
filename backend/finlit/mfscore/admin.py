"""Administrator-only views of the Mutual Fund Health Score (GET /api/admin/mf-score/health and /calibration).

health: the last `score-mf` run, funds per status, the score histogram per group, how many measures used the group value (state F) per group and per
measure, the zero-handling counters of the last run (spec Appendix Z.3: expense ratio, fund size, top-10, equity share zeros), funds NOT RATED by reason,
the inputs most often missing, and the sizes of the peer sets.

calibration: an INTERNAL, DESCRIPTIVE look back, never shown on the public site and never a forecast. For funds with at least three years of month-end NAVs,
the funds are put into five equal groups by the score stored `months` ago, and the answer is each group's average rank of the return earned over the next
12 months (1 = the highest return, as a share of the funds). It says only whether, in the stored history, a higher score went with a higher later return."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from ..auth.routes import NO_STORE, Ctx, admin_ctx
from .reasons import texts

router = APIRouter(prefix="/api/admin/mf-score")
INTERNAL = "Internal, descriptive, not a forecast. Do not publish."
BUCKETS = [("0 to 7", 0, 7), ("8 to 19", 8, 19), ("20 to 49", 20, 49), ("50 to 99", 50, 99), ("100 or more", 100, 10 ** 9)]


def _hist(rows) -> Dict[str, List[int]]:
    out: Dict[str, List[int]] = {}
    for r in rows:
        h = out.setdefault(r["grp"], [0] * 10)
        h[min(9, max(0, int(r["b"]) - 1))] = r["n"]
    return out


async def health_report(pool) -> Dict[str, Any]:
    from ..mf import _meta
    t = texts()
    async with pool.acquire() as conn:
        run = await _meta(conn, "run:score-mf")
        status = {r["status"]: r["n"] for r in await conn.fetch("SELECT status, count(*) AS n FROM mf_scores GROUP BY status")}
        dist = _hist(await conn.fetch("SELECT grp, width_bucket(final, 0, 100.0001, 10) AS b, count(*) AS n FROM mf_scores WHERE final IS NOT NULL GROUP BY grp, b"))
        per_group = await conn.fetch("""SELECT grp, count(*) AS funds, count(*) FILTER (WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(breakdown->'metrics') m WHERE m->>'state' = 'F')) AS with_gap
                                        FROM mf_scores WHERE final IS NOT NULL GROUP BY grp ORDER BY grp""")
        filled_by_group = await conn.fetch("""SELECT grp, count(*) AS n FROM mf_scores, jsonb_array_elements(breakdown->'metrics') m WHERE final IS NOT NULL AND m->>'state' = 'F' GROUP BY grp""")
        missing = await conn.fetch("""SELECT m->>'id' AS id, COALESCE(m->>'why', '') AS why, count(*) AS n FROM mf_scores, jsonb_array_elements(breakdown->'metrics') m
                                      WHERE final IS NOT NULL AND m->>'state' = 'F' GROUP BY 1, 2 ORDER BY n DESC LIMIT 20""")
        nr = await conn.fetch("SELECT COALESCE(reason, 'no reason stored') AS reason, count(*) AS n FROM mf_scores WHERE status = 'NOT RATED' GROUP BY 1 ORDER BY n DESC LIMIT 20")
        peers = await conn.fetch("SELECT COALESCE(peer_kind, 'none') AS kind, peer_n FROM mf_scores WHERE peer_n IS NOT NULL")
        total = await conn.fetchval("SELECT count(*) FROM mf_scores")
        hist_n = await conn.fetchrow("SELECT count(*) AS n, min(week) AS first, max(week) AS last FROM mf_score_history")
    fg = {r["grp"]: r["n"] for r in filled_by_group}
    peer_hist: Dict[str, List[int]] = {}
    for r in peers:
        h = peer_hist.setdefault(r["kind"], [0] * len(BUCKETS))
        for i, (_n, lo, hi) in enumerate(BUCKETS):
            if lo <= r["peer_n"] <= hi:
                h[i] += 1
                break
    zr = (run or {}).get("zeroRules") or {}
    return {"internal": True, "lastRun": None if not run else {k: run.get(k) for k in ("at", "status", "runDate", "universe", "written", "removed", "partial", "seconds", "loadSeconds", "scoreSeconds", "alertsFired", "reason", "error")},
            "total": total, "status": status, "distribution": {"bins": [f"{i * 10} to {i * 10 + 10}" for i in range(10)], "byGroup": dist},
            "filled": [{"group": r["grp"], "funds": r["funds"], "withAGap": r["with_gap"], "measuresFilled": fg.get(r["grp"], 0)} for r in per_group],
            "zeroCounters": zr, "notRated": [{"reason": r["reason"], "n": r["n"]} for r in nr],
            "topMissing": [{"id": r["id"], "label": t["metrics"].get(r["id"], {}).get("label", r["id"]), "why": r["why"], "whyText": t["gaps"].get(r["why"], r["why"]), "n": r["n"]} for r in missing],
            "peerSizes": {"buckets": [b[0] for b in BUCKETS], "byKind": peer_hist}, "history": {"rows": hist_n["n"], "first": hist_n["first"], "last": hist_n["last"]}}


@router.get("/health")
async def health(request: Request, ctx: Ctx = Depends(admin_ctx)):
    return JSONResponse(json.loads(json.dumps(await health_report(request.app.state.store.pool), default=str)), headers=NO_STORE)


def ret_after(days: List[date], navs: List[float], start: date, months: int = 12):
    """Return (percent) from the first month-end NAV on or after `start` to the one `months` later, or None."""
    i = next((k for k, d in enumerate(days) if d >= start), None)
    if i is None:
        return None
    end_key = (days[i].year * 12 + days[i].month - 1) + months
    j = next((k for k in range(i + 1, len(days)) if days[k].year * 12 + days[k].month - 1 >= end_key), None)
    if j is None or not navs[i] or navs[i] <= 0 or navs[j] is None:
        return None
    return (navs[j] / navs[i] - 1) * 100.0


def quintile_table(pairs: List[tuple]) -> List[Dict[str, Any]]:
    """pairs: (score, later return). Five equal groups by score (5 = highest scores); per group: funds, average score, average return, average return rank (0 = best, 1 = worst)."""
    if len(pairs) < 25:
        return []
    ranked_ret = sorted(pairs, key=lambda p: -p[1])
    rank = {id(p): i / (len(pairs) - 1) for i, p in enumerate(ranked_ret)}
    ordered = sorted(pairs, key=lambda p: p[0])
    n = len(ordered)
    out = []
    for q in range(5):
        part = ordered[q * n // 5:(q + 1) * n // 5]
        out.append({"quintile": q + 1, "funds": len(part), "avgScore": round(sum(p[0] for p in part) / len(part), 1), "avgLaterReturn": round(sum(p[1] for p in part) / len(part), 2),
                    "avgReturnRank": round(sum(rank[id(p)] for p in part) / len(part), 3)})
    return out


@router.get("/calibration")
async def calibration(request: Request, months_ago: int = Query(12, ge=3, le=36), plan: str = Query("Direct", pattern="^(Direct|Regular)$"), ctx: Ctx = Depends(admin_ctx)):
    pool = request.app.state.store.pool
    async with pool.acquire() as conn:
        first = await conn.fetchval("SELECT min(week) FROM mf_score_history")
        asof = date.today() - timedelta(days=round(months_ago * 30.4375))
        rows = await conn.fetch("""SELECT DISTINCT ON (key) key, code, final, week FROM mf_score_history WHERE kind = 'mf' AND plan = $1 AND final IS NOT NULL
                                   AND week BETWEEN $2 AND $3 ORDER BY key, abs(week - $4::date)""", plan, asof - timedelta(days=14), asof + timedelta(days=14), asof)
        codes = [r["code"] for r in rows]
        navs = {r["code"]: r for r in await conn.fetch("SELECT code, days, navs FROM mf_monthly WHERE code = ANY($1::int[])", codes)} if codes else {}
    pairs = []
    for r in rows:
        m = navs.get(r["code"])
        if not m or not m["days"] or (r["week"] - m["days"][0]).days < 3 * 365:   # at least three years of month-end NAVs on the date the score was stored
            continue
        later = ret_after(list(m["days"]), list(m["navs"]), r["week"], 12)
        if later is not None:
            pairs.append((float(r["final"]), later))
    return JSONResponse({"internal": True, "label": INTERNAL, "monthsAgo": months_ago, "plan": plan, "asOf": asof.isoformat(), "historyStarts": first.isoformat() if first else None,
                         "funds": len(pairs), "quintiles": quintile_table(pairs),
                         "note": None if pairs else ("The stored score history is too short for this look back" + (f": it starts {first.isoformat()}." if first else ": no weekly rows are stored yet.")),
                         "how": "Funds with at least 3 years of month-end NAVs are split into five equal groups by the score stored on that date. Return rank runs from 0 (highest later 12-month return) to 1 (lowest). "
                                "A lower average rank for the higher-score groups means a higher score went with a higher later return in this sample; it does not say the next year will repeat it."},
                        headers=NO_STORE)
