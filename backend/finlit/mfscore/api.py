"""GET /api/mf/{code}/score, GET /api/mf/etf/{symbol}/score and GET /api/mf/scores: the Mutual Fund Health Score, read from mf_scores.

Plan gating, enforced here and not only on the page: the score is a Gold feature. A Basic or Silver account (or a visitor) gets
a locked answer with no value, no pillar, no breakdown, no rank and no order: a locked field is present and null, so the browser cannot tell a locked value from a
missing one (as the screener's list does). Schemes named in MF_SCORE_SHOWCASE (scheme codes, none by default: the site has no free fund showcase list) stay open to everyone.
Answers that depend on the plan are private and never stored by a shared cache.

Placement: this router is included BEFORE finlit.mf's, whose /api/mf/{code} would otherwise claim /api/mf/scores."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..auth.entitlements import has
from ..auth.routes import fail
from ..auth.service import current
from . import MODEL_VERSION
from .dashboard import summarize
from .groups import GROUP_NAMES
from .reasons import texts
from .sheets import PILLAR_NAMES, PILLARS, WEIGHTS

router = APIRouter(prefix="/api/mf")

DISCLAIMER = "Describes the fund's health from its past NAVs, costs and holdings; not a recommendation. Information only, not investment advice."
METHOD_URL = "/methodology/mf-score"
PRIVATE = "private, no-store"
SYMBOL_RE = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
SORTS = {"final": "final", "perf": "perf", "risk": "risk", "cost": "cost", "quality": "quality", "rank": "percentile", "name": "key"}
LIST_COLS = "key, kind, code, symbol, plan, grp, sub, category, final, label, status, reason, perf, risk, cost, quality, rank, rank_of, rank_scope, percentile, flags, confidence, run_date"
NOT_SCORED = {
    "idcw": "Not scored: IDCW and other options inherit the Growth plan's score.",
    "inactive": "Not scored: this scheme has stopped publishing NAVs.",
    "no_plan": "Not scored: the plan (Direct or Regular) is not stated for this scheme.",
    "etf_no_price": "Not scored: this exchange-traded fund has no exchange price history loaded yet.",
    "not_yet": "Not scored yet: the daily score run has not reached this scheme.",
}


def showcase() -> set:
    return {int(x) for x in os.getenv("MF_SCORE_SHOWCASE", "").replace(" ", "").split(",") if x.isdigit()}


async def may_see(request: Request, code: Optional[int] = None) -> bool:
    """Gold (an admin too), or a showcase scheme."""
    if code is not None and code in showcase():
        return True
    ctx = await current(request)
    return has(ctx.plan, "gold") or ctx.role == "admin"


async def require_score_plan(request: Request) -> None:
    """For routes whose ORDER would say what the value says (the fund list sorted by score)."""
    if not await may_see(request):
        raise fail(403, "plan_required", "The Mutual Fund Health Score is part of the Gold plan.", plan="gold")


def _load(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def pillars_view(group: str, r: Dict[str, Any], values: bool = True) -> List[Dict[str, Any]]:
    flags = (_load(r["breakdown"]) or {}).get("pillarFlags", {}) if values else {}
    out = []
    for p, w in zip(PILLARS, WEIGHTS[group]):
        score = r[{"performance": "perf", "risk": "risk", "cost": "cost", "quality": "quality"}[p]] if values else None
        out.append({"key": p, "name": PILLAR_NAMES[p], "weight": w, "score": None if score is None else round(float(score), 1), "allNotApplicable": bool(flags.get(p))})
    return out


def locked_payload(group: Optional[str], plan: Optional[str], **extra: Any) -> Dict[str, Any]:
    """What a plan below Gold gets: the model's fixed shape (pillar names and weights, which are not values) and nothing a fund scored."""
    return {"locked": True, "plan": "gold", "detail": "The FinLit Mutual Fund Health Score is part of the Gold plan.", "group": group, "groupName": GROUP_NAMES.get(group or ""),
            "fundPlan": plan, "final": None, "label": None, "status": None, "pillars": [{"key": p, "name": PILLAR_NAMES[p], "weight": w, "score": None} for p, w in zip(PILLARS, WEIGHTS[group])] if group in WEIGHTS else [],
            "disclaimer": DISCLAIMER, "method": METHOD_URL, "model": MODEL_VERSION, **extra}


def rank_view(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if r["rank"] is None:
        return None
    return {"rank": r["rank"], "of": r["rank_of"], "scope": r["rank_scope"], "percentile": None if r["percentile"] is None else int(r["percentile"]),
            "category": r["category"], "categoryLabel": _sub_label(r["category"]), "plan": r["plan"]}


def _sub_label(category: Optional[str]) -> Optional[str]:
    if not category:
        return None
    try:
        from ..mf import classify
        return classify(category)[2]
    except Exception:
        return category


PEER_TEXT = texts()["peerSets"]


def payload(r: Dict[str, Any], *, inherited: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One stored score row -> the answer of /api/mf/{code}/score (values included: the caller has checked the plan)."""
    b = _load(r["breakdown"]) or {}
    t = texts()["metrics"]
    metrics = []
    tx = texts()
    for m in b.get("metrics", []):
        table = {"F": "gaps", "N": "na", "S": "substitutes"}.get(m["state"])
        metrics.append({**m, "label": t.get(m["id"], {}).get("label", m["id"]), "whyText": (tx.get(table, {}).get(m.get("why") or "") if table else None)})
    n_f = sum(1 for m in metrics if m["state"] == "F")
    n_all = sum(1 for m in metrics if m["state"] != "N")
    rated = r["final"] is not None
    reasons = b.get("reasons") or {}
    return {
        "locked": False, "key": r["key"], "kind": r["kind"], "code": r["code"], "symbol": r["symbol"], "plan": r["plan"], "group": r["grp"], "groupName": GROUP_NAMES.get(r["grp"]),
        "type": r["mtype"], "category": r["category"], "categoryLabel": _sub_label(r["category"]) if r["kind"] == "mf" else "Exchange-traded fund", "runDate": r["run_date"].isoformat(),
        "navDate": r["nav_date"].isoformat() if r["nav_date"] else None, "status": r["status"], "reason": r["reason"], "final": r["final"] if rated else None,
        "label": r["label"], "rawFinal": r["raw_final"] if rated else None, "cap": r["cap"], "pillars": pillars_view(r["grp"], r, rated), "confidence": r["confidence"],
        "months": r["months"], "flags": list(r["flags"] or []), "rank": rank_view(r) if rated else None,
        "peers": {"kind": r["peer_kind"], "n": r["peer_n"], "text": PEER_TEXT.get(r["peer_kind"] or "", None)},
        "family": b.get("family"), "nearIdentical": "NEAR_IDENTICAL" in (r["flags"] or []),
        "reasons": {"strengths": reasons.get("strengths", []), "watchouts": reasons.get("watchouts", []), "gaps": reasons.get("gaps", []),
                    "notApplicable": reasons.get("notApplicable", []), "substitutions": reasons.get("substitutions", [])},
        "filled": {"n": n_f, "of": n_all}, "metrics": metrics if rated else [], "inherited": inherited, "model": r["model"], "disclaimer": DISCLAIMER, "method": METHOD_URL,
    }


def _json(body: Dict[str, Any], status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers={"Cache-Control": PRIVATE, "Vary": "Cookie"})


async def _row(conn, key: str):
    r = await conn.fetchrow("SELECT * FROM mf_scores WHERE key = $1", key)
    return dict(r) if r else None


@router.get("/scores")
async def scores(request: Request, group: str = Query("", max_length=12), category: str = Query("", max_length=160), plan: str = Query("", max_length=10),
                 codes: str = Query("", max_length=1200), symbols: str = Query("", max_length=2400), sort: str = Query("final", max_length=10), dir: str = Query("desc", pattern="^(asc|desc)$"),
                 status: str = Query("", max_length=12), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0, le=100000)) -> JSONResponse:
    """Scores for tables: by scheme codes (up to 100: the funds on the page), or a group / category, sorted. Gold only; below that the values are
    null for the codes asked and a list query returns nothing (its order would leak the ranking)."""
    if sort not in SORTS:
        raise fail(400, "bad_request", "Unknown sort column.")
    if group and group not in GROUP_NAMES:
        raise fail(400, "bad_request", "Unknown group.")
    if plan and plan not in ("Direct", "Regular", "ETF"):
        raise fail(400, "bad_request", "Unknown plan.")
    if status and status not in ("RATED", "PROVISIONAL", "NOT RATED"):
        raise fail(400, "bad_request", "Unknown status.")
    try:
        ids = list(dict.fromkeys(int(x) for x in codes.split(",") if x.strip()))
    except ValueError:
        raise fail(400, "bad_request", "codes must be scheme codes separated by commas.")
    if len(ids) > 100 or any(not 0 < c < 10 ** 7 for c in ids):
        raise fail(400, "bad_request", "Up to 100 scheme codes.")
    syms = list(dict.fromkeys(x.strip().upper() for x in symbols.split(",") if x.strip()))
    if len(syms) > 100 or any(not SYMBOL_RE.match(x) for x in syms):
        raise fail(400, "bad_request", "Up to 100 ETF symbols.")
    seen = showcase()
    full = await may_see(request)
    if not full and not ids and not syms:
        return _json({"locked": True, "plan": "gold", "total": None, "items": [], "disclaimer": DISCLAIMER, "method": METHOD_URL})
    where, args = [], []

    def arg(v):
        args.append(v)
        return f"${len(args)}"
    if ids or syms:   # the funds on a page: scheme codes and/or ETF symbols
        picks = ([f"code = ANY({arg(ids)}::int[])"] if ids else []) + ([f"(kind = 'etf' AND symbol = ANY({arg(syms)}::text[]))"] if syms else [])
        where.append("(" + " OR ".join(picks) + ")")
    for col, v in (("grp", group), ("category", category), ("plan", plan), ("status", status)):
        if v:
            where.append(f"{col} = {arg(v)}")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    order = f"{SORTS[sort]} {'ASC' if dir == 'asc' else 'DESC'} NULLS LAST, key"
    async with request.app.state.store.pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT count(*) FROM mf_scores {w}", *args)  # nosec B608 - fixed column names; every value is a bound parameter
        rows = await conn.fetch(f"SELECT {LIST_COLS} FROM mf_scores {w} ORDER BY {order} LIMIT {limit} OFFSET {offset}", *args)  # nosec B608 - column list and sort come from fixed maps; limit and offset are range-checked integers
        run = await conn.fetchval("SELECT max(run_date) FROM mf_scores")
    items = []
    for r in rows:
        open_ = full or (r["code"] is not None and r["code"] in seen)
        item = {"code": r["code"], "symbol": r["symbol"], "plan": r["plan"], "group": r["grp"]}
        if open_:
            item.update(final=r["final"], label=r["label"], status=r["status"], reason=r["reason"], pillars={"performance": r["perf"], "risk": r["risk"], "cost": r["cost"], "quality": r["quality"]},
                        rank=r["rank"], rankOf=r["rank_of"], rankScope=r["rank_scope"], percentile=None if r["percentile"] is None else int(r["percentile"]), flags=list(r["flags"] or []),
                        confidence=r["confidence"], category=r["category"])
        else:
            item.update(final=None, label=None, status=None, reason=None, pillars=None, rank=None, rankOf=None, rankScope=None, percentile=None, flags=[], confidence=None, category=None)
        items.append(item)
    if syms:   # an ETF asked for with no row: say why (a symbol the exchange list does not know is left out)
        have_s = {i["symbol"] for i in items}
        gone = [x for x in syms if x not in have_s]
        if gone:
            async with request.app.state.store.pool.acquire() as conn:
                known = {r["symbol"] for r in await conn.fetch("SELECT symbol FROM etf_funds WHERE symbol = ANY($1::text[])", gone)}
            for x in gone:
                if x in known:
                    items.append({"code": None, "symbol": x, "plan": "ETF", "group": None, "final": None, "label": None, "status": None, "pillars": None, "rank": None, "rankOf": None,
                                  "rankScope": None, "percentile": None, "flags": [], "confidence": None, "category": None, "reason": NOT_SCORED["etf_no_price"] if full else None})
    if ids:   # a scheme asked for with no row: say why (the page shows the reason, never a blank)
        have = {i["code"] for i in items}
        missing = [c for c in ids if c not in have]
        if missing:
            async with request.app.state.store.pool.acquire() as conn:
                info = {r["code"]: r for r in await conn.fetch("SELECT code, option_class, active, plan, category, isin FROM mf_schemes WHERE code = ANY($1::int[])", missing)}
            for c in missing:
                s = info.get(c)
                if s is None:
                    continue
                items.append({"code": c, "symbol": None, "plan": s["plan"], "group": None, "final": None, "label": None, "status": None, "pillars": None, "rank": None, "rankOf": None,
                              "rankScope": None, "percentile": None, "flags": [], "confidence": None, "category": None,
                              "reason": (NOT_SCORED["inactive"] if not s["active"] else NOT_SCORED["idcw"] if s["option_class"] != "Growth" else NOT_SCORED["no_plan"] if s["plan"] not in ("Direct", "Regular") else NOT_SCORED["not_yet"]) if full else None})
    return _json({"locked": not full, "total": total if full else None, "runDate": run.isoformat() if run else None, "items": items, "disclaimer": DISCLAIMER, "method": METHOD_URL, "model": MODEL_VERSION})


@router.get("/scores/categories")
async def category_scores(request: Request) -> JSONResponse:
    """The Funds dashboard: median Health score, number scored and band counts per sub-category, over scored Direct-plan mutual funds. Gold only; a
    plan below that gets `locked` and no number at all (the cards would otherwise show what the list hides). `runDate` is null until the score job has run."""
    if not await may_see(request):
        return _json({"locked": True, "plan": "gold", "items": {}, "runDate": None, "disclaimer": DISCLAIMER, "method": METHOD_URL})
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT sub, final FROM mf_scores WHERE kind = 'mf' AND plan = 'Direct' AND final IS NOT NULL")
        run = await conn.fetchval("SELECT max(run_date) FROM mf_scores")
    return _json({"locked": False, "plan": "Direct", "runDate": run.isoformat() if run else None, "items": summarize((r["sub"], r["final"]) for r in rows),
                  "disclaimer": DISCLAIMER, "method": METHOD_URL, "model": MODEL_VERSION})


async def resolve_mf(conn, code: int):
    """(row, inherited, reason): the score row for a scheme code, or the Growth plan's row it inherits, or why there is none."""
    r = await _row(conn, f"mf:{code}")
    if r:
        return r, None, None
    s = await conn.fetchrow("SELECT code, name, family, plan, option_class, active, isin, category FROM mf_schemes WHERE code = $1", code)
    if s is None:
        return None, None, "unknown"
    if s["option_class"] != "Growth":
        g = await conn.fetchrow("SELECT code, name FROM mf_schemes WHERE family = $1 AND plan = $2 AND option_class = 'Growth' AND active ORDER BY code LIMIT 1", s["family"], s["plan"])
        if g is None:
            g = await conn.fetchrow("SELECT code, name FROM mf_schemes WHERE family = $1 AND option_class = 'Growth' AND active ORDER BY (plan = 'Direct') DESC, code LIMIT 1", s["family"])
        if g:
            gr = await _row(conn, f"mf:{g['code']}")
            if gr:
                return gr, {"code": g["code"], "name": g["name"], "why": "This option pays out or has no Growth NAV of its own, so it carries the score of the Growth plan of the same fund."}, None
        return None, None, "idcw"
    if not s["active"]:
        return None, None, "inactive"
    if s["plan"] not in ("Direct", "Regular"):
        return None, None, "no_plan"
    # an ETF category scheme: scored from its exchange prices, found by ISIN
    from ..mf import classify
    from .groups import ETF_SUBS
    if classify(s["category"])[1] in ETF_SUBS and s["isin"]:
        e = await conn.fetchrow("SELECT symbol, display_name FROM etf_funds WHERE isin = $1", s["isin"])
        if e:
            er = await _row(conn, f"etf:{e['symbol']}")
            if er:
                return er, {"symbol": e["symbol"], "name": e["display_name"], "why": "This is an exchange-traded fund: it is scored from its exchange prices on the ETF page."}, None
        return None, None, "etf_no_price"
    return None, None, "not_yet"


@router.get("/{code}/score")
async def score_of(request: Request, code: int) -> JSONResponse:
    if not 0 < code < 10 ** 7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")
    async with request.app.state.store.pool.acquire() as conn:
        row, inherited, why = await resolve_mf(conn, code)
        if why == "unknown":
            raise fail(404, "not_found", "No mutual fund scheme has this code.")
    return await _answer(request, row, inherited, why, code)


@router.get("/etf/{symbol}/score")
async def etf_score(request: Request, symbol: str) -> JSONResponse:
    sym = symbol.strip().upper()
    if not sym.isalnum() or len(sym) > 20:
        raise fail(404, "not_found", "No exchange-traded fund has this symbol.")
    async with request.app.state.store.pool.acquire() as conn:
        row = await _row(conn, f"etf:{sym}")
        known = row is not None or await conn.fetchval("SELECT 1 FROM etf_funds WHERE symbol = $1", sym)
    if not known:
        raise fail(404, "not_found", "No exchange-traded fund has this symbol.")
    return await _answer(request, row, None, None if row else "etf_no_price", None)


async def _answer(request: Request, row, inherited, why, code: Optional[int]) -> JSONResponse:
    if not await may_see(request, code):
        return _json(locked_payload(row["grp"] if row else None, row["plan"] if row else None))
    if row is None:
        return _json({"locked": False, "final": None, "status": "NOT SCORED", "reason": NOT_SCORED.get(why or "not_yet", NOT_SCORED["not_yet"]), "pillars": [], "reasons": {}, "metrics": [],
                      "disclaimer": DISCLAIMER, "method": METHOD_URL, "model": MODEL_VERSION})
    body = payload(row, inherited=inherited)
    if row["final"] is not None:   # the category's median parts, for the radar: the same category and plan (the tracking family for index funds and ETFs)
        body["categoryMedian"] = await category_median(request, row)
    return _json(body)


async def category_median(request: Request, row) -> Dict[str, Any]:
    async with request.app.state.store.pool.acquire() as conn:
        m = await conn.fetchrow("SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY perf) AS perf, percentile_cont(0.5) WITHIN GROUP (ORDER BY risk) AS risk, "
                                "percentile_cont(0.5) WITHIN GROUP (ORDER BY cost) AS cost, percentile_cont(0.5) WITHIN GROUP (ORDER BY quality) AS quality, "
                                "percentile_cont(0.5) WITHIN GROUP (ORDER BY final) AS final, count(*) AS n FROM mf_scores WHERE sub = $1 AND plan = $2 AND final IS NOT NULL", row["sub"], row["plan"])
    r1 = lambda v: None if v is None else round(float(v), 1)  # noqa: E731
    return {"performance": r1(m["perf"]), "risk": r1(m["risk"]), "cost": r1(m["cost"]), "quality": r1(m["quality"]), "final": r1(m["final"]), "n": m["n"],
            "plan": row["plan"], "categoryLabel": _sub_label(row["category"]) if row["kind"] == "mf" else "Exchange-traded funds"}
