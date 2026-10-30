"""The `score-mf` worker command: score every Growth scheme and every ETF once a day and store one row each in mf_scores.

Runs after refresh-portfolios in the night chain (the holdings it reads are then current) and takes the same lock as the other fund jobs. Loads the
whole universe (peer medians need it), scores it in memory in a few seconds, and writes in ONE transaction: a failed run leaves yesterday's scores untouched,
and running it twice gives the same rows. `--symbols` scores the whole universe but writes only those funds (AMFI scheme codes or ETF symbols);
`--limit` restricts the universe itself, so it is for testing only (its peer sets are not the real ones) and never removes other rows."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from . import MODEL_VERSION
from .engine import score_universe
from .groups import type_of_group
from .loader import load_etf, load_mf
from .model import FundIn, Score
from .toolkit import is_missing
from . import scorehist

log = logging.getLogger("finlit.mfscore")

UPSERT = """INSERT INTO mf_scores (key, kind, code, symbol, plan, grp, mtype, sub, category, run_date, nav_date, final, raw_final, perf, risk, cost, quality, label, status, reason,
                                 confidence, months, cap, flags, peer_kind, peer_n, rank, rank_of, rank_scope, percentile, breakdown, model, updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31::jsonb,$32, now())
            ON CONFLICT (key) DO UPDATE SET kind = EXCLUDED.kind, code = EXCLUDED.code, symbol = EXCLUDED.symbol, plan = EXCLUDED.plan, grp = EXCLUDED.grp, mtype = EXCLUDED.mtype,
              sub = EXCLUDED.sub, category = EXCLUDED.category, run_date = EXCLUDED.run_date, nav_date = EXCLUDED.nav_date, final = EXCLUDED.final, raw_final = EXCLUDED.raw_final,
              perf = EXCLUDED.perf, risk = EXCLUDED.risk, cost = EXCLUDED.cost, quality = EXCLUDED.quality, label = EXCLUDED.label, status = EXCLUDED.status, reason = EXCLUDED.reason,
              confidence = EXCLUDED.confidence, months = EXCLUDED.months, cap = EXCLUDED.cap, flags = EXCLUDED.flags, peer_kind = EXCLUDED.peer_kind, peer_n = EXCLUDED.peer_n,
              rank = EXCLUDED.rank, rank_of = EXCLUDED.rank_of, rank_scope = EXCLUDED.rank_scope, percentile = EXCLUDED.percentile, breakdown = EXCLUDED.breakdown,
              model = EXCLUDED.model, updated_at = now()"""


def _r(v: Optional[float], d: int = 4) -> Optional[float]:
    return None if is_missing(v) else round(float(v), d)


def breakdown(s: Score, f: Optional[FundIn] = None) -> Dict[str, Any]:
    """The per-metric breakdown stored with a score: value, state, points and weight of every measure, plus the reasons."""
    metrics = [{"id": r.id, "pillar": r.pillar, "state": r.state, "value": _r(r.value), "own": _r(r.own), "peer": _r(r.peer), "peerN": r.peer_n or None, "scope": r.scope,
                "points": _r(r.points, 2), "limits": [r.limits[0], r.limits[1]] if r.limits else None, "pillarWeight": r.wt, "weight": _r(r.weight, 3), "groupValue": _r(r.gv, 2),
                "why": r.why, "rule": r.rule, "cred": _r(r.cred, 3) if r.cred != 1.0 else None} for r in s.metrics]
    out: Dict[str, Any] = {"metrics": metrics, "reasons": s.reasons, "pillarFlags": s.pillar_flags, "counters": s.counters}
    if f is not None and f.group == "OT-PASSIVE":
        out["family"] = {"key": f.family_key, "index": f.benchmark}
    return out


def row(s: Score, f: FundIn, run_date: date) -> tuple:
    p = s.pillars
    return (s.key, s.kind, f.code, f.symbol, s.plan, s.group, type_of_group(s.group), f.sub, f.category, run_date, f.nav_date, _r(s.final, 1), _r(s.raw_final, 2),
            _r(p.get("performance"), 1), _r(p.get("risk"), 1), _r(p.get("cost"), 1), _r(p.get("quality"), 1), s.label, s.status, s.reason, _r(s.confidence, 3), s.months, s.cap,
            s.flags, s.peer_kind, s.peer_n or None, s.rank, s.rank_of, s.rank_scope, _r(s.percentile, 0), json.dumps(breakdown(s, f), separators=(",", ":")), MODEL_VERSION)


def today_ist() -> date:
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()


def summarise(scores: Sequence[Score]) -> Dict[str, Any]:
    """Counts for the log and /api/mf/status: scores per status, metric states, and the zero-handling rules hit (spec Z.3 calibration counters)."""
    states: Counter = Counter()
    zero: Counter = Counter()
    funds_with_gaps = 0
    by_group: Counter = Counter()
    for s in scores:
        by_group[s.group] += 1
        gaps = 0
        for r in s.metrics:
            states[r.state] += 1
            gaps += r.state == "F"
            if r.rule:
                zero[r.rule] += 1
        funds_with_gaps += gaps > 0
        for k, n in s.counters.items():
            zero["fund:" + k] += n
    return {"scores": len(scores), "byStatus": dict(Counter(s.status for s in scores)), "states": dict(states), "fundsWithAGap": funds_with_gaps,
            "zeroRules": dict(sorted(zero.items())), "groups": dict(sorted(by_group.items())), "flags": dict(Counter(f for s in scores for f in s.flags)),
            "capped": sum(1 for s in scores if s.cap), "nearIdentical": sum(1 for s in scores if s.near_identical)}


async def run(store, settings=None, *, symbols: Optional[Sequence[str]] = None, limit: Optional[int] = None, run_date: Optional[date] = None, mailer=None) -> dict:
    """Score the universe and store the result. Returns the counts."""
    t0 = time.perf_counter()
    run_date = run_date or today_ist()
    wanted_codes = [int(x) for x in (symbols or []) if str(x).isdigit()]
    wanted_syms = [str(x).upper() for x in (symbols or []) if not str(x).isdigit()]
    async with store.pool.acquire() as conn:
        mf_funds, _ = await load_mf(conn, limit=limit)
        etf_funds = await load_etf(conn, limit=limit)
    funds: List[FundIn] = mf_funds + etf_funds
    t_load = time.perf_counter() - t0
    if not funds:
        return {"status": "skipped", "reason": "no schemes loaded yet", "seconds": round(time.perf_counter() - t0, 1)}
    scores = await asyncio.to_thread(score_universe, funds, run_date)
    t_score = time.perf_counter() - t0 - t_load
    by_key = {f.key: f for f in funds}
    pick = [s for s in scores if not (wanted_codes or wanted_syms) or (by_key[s.key].code in wanted_codes) or (by_key[s.key].symbol in wanted_syms)]
    rows = [row(s, by_key[s.key], run_date) for s in pick]
    full = not (symbols or limit)
    async with store.pool.acquire() as conn, conn.transaction():
        mails: List[dict] = []
        if rows:
            await conn.executemany(UPSERT, rows)
            # history in the same transaction: one row per scheme per ISO week (this run replaces the week's earlier one), then the score alerts that row triggers
            await conn.executemany(scorehist.HISTORY_INSERT, [scorehist.history_row(r, run_date) for r in rows])
            mails = await scorehist.fire_alerts(conn, scorehist.week_of(run_date), [r[0] for r in rows])
        removed = 0
        if full:   # a fund that is no longer active or listed has no score any more
            removed = int((await conn.execute("DELETE FROM mf_scores WHERE run_date < $1", run_date)).split()[-1])
    if mails and mailer is not None:
        await scorehist.send_mails(mails, mailer, getattr(settings, "public_site_url", "") or "")
    out = {"status": "ok", "alertsFired": len(mails), "runDate": run_date.isoformat(), "universe": len(funds), "written": len(rows), "removed": removed, "partial": not full,
           "seconds": round(time.perf_counter() - t0, 1), "loadSeconds": round(t_load, 1), "scoreSeconds": round(t_score, 1), **summarise(scores)}
    log.info("score-mf: %s", json.dumps({k: v for k, v in out.items() if k not in ("zeroRules", "states", "groups")}, default=str))
    return out
