"""Gold-only upgrades of the Mutual Fund Health Score: score history, the fund score screener (list, facets, CSV), the category leaderboard, the history of
several funds at once (Fund Compare) and the member's score alerts. Included BEFORE finlit.mf's router, like api.py.

Gating is the server's, as in api.py: below Gold the answer is `locked` with no value, no order and no row (a Basic or Silver account cannot tell a locked
fund from a missing one, and the screener returns no fund at all). Answers that carry values are `private, no-store`; a Gold answer is kept in Redis for ten
minutes only AFTER the plan check, under a key made of the query, so no other plan can reach it (the check comes first, every time)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import statistics
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..alertengine import ALERT_LIMITS
from ..auth.entitlements import has
from ..auth.routes import NO_STORE, Ctx, fail, limit, secure_ctx
from . import MODEL_VERSION, scorehist
from .api import DISCLAIMER, METHOD_URL, PRIVATE, _json, _sub_label, may_see, resolve_mf
from .groups import GROUP_NAMES
from .scorehist import PILLAR_NAME

router = APIRouter(prefix="/api/mf")
CACHE_SECONDS = 600
LABELS = ("Strong", "Healthy", "Average", "Weak", "Poor")
STATUSES = ("RATED", "PROVISIONAL")
MAX_PAGE = 200
CSV_MAX = 6000

# screener sort key -> SQL expression (fixed text: nothing a caller sends is ever put in a statement)
SORT_SQL = {"final": "m.final", "perf": "m.perf", "risk": "m.risk", "cost": "m.cost", "quality": "m.quality", "name": "lower(COALESCE(s.name, e.display_name))",
            "category": "m.sub", "plan": "m.plan", "aum": "s.aum_lakh", "age": "age_years", "ter": "s.ter", "r1y": "COALESCE(s.r1y, e.ret_1y)",
            "r3y": "COALESCE(s.r3y, e.cagr_3y)", "r5y": "COALESCE(s.r5y, e.cagr_5y)"}
SELECT = """SELECT m.key, m.kind, m.code, m.symbol, m.plan, m.grp, m.sub, m.category, m.final, m.label, m.status, m.reason, m.perf, m.risk, m.cost, m.quality, m.rank, m.rank_of,
       m.months, m.confidence, m.flags, m.run_date, COALESCE(s.name, e.display_name) AS name, COALESCE(s.amc, e.fund_house) AS amc, s.aum_lakh, s.ter,
       COALESCE(s.r1y, e.ret_1y) AS r1y, COALESCE(s.r3y, e.cagr_3y) AS r3y, COALESCE(s.r5y, e.cagr_5y) AS r5y,
       COALESCE(round(((m.run_date - f.launch_date) / 365.25)::numeric, 1)::float8, round(m.months / 12.0, 1)::float8) AS age_years
       FROM mf_scores m LEFT JOIN mf_schemes s ON s.code = m.code LEFT JOIN etf_funds e ON e.symbol = m.symbol AND m.kind = 'etf' LEFT JOIN mf_facts f ON f.code = m.code"""


def locked(**extra: Any) -> JSONResponse:
    return _json({"locked": True, "plan": "gold", "items": [], "total": None, "disclaimer": DISCLAIMER, "method": METHOD_URL, **extra})


async def cached(request: Request, name: str, params: Any, build) -> Any:
    """Redis for ten minutes, AFTER the plan check. A failed cache never fails the answer."""
    redis = request.app.state.store.redis
    key = "mfs:up:" + name + ":" + hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:24]
    try:
        hit = await redis.get(key)
        if hit:
            return json.loads(hit)
    except Exception:  # nosec B110 - cache trouble: build the answer
        pass
    body = await build()
    try:
        await redis.set(key, json.dumps(body, default=str), ex=CACHE_SECONDS)
    except Exception:  # nosec B110
        pass
    return body


# ------------------------------------------------------------------------------------------------------------------------------------ screener
def item_of(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"key": r["key"], "kind": r["kind"], "code": r["code"], "symbol": r["symbol"], "name": r["name"] or r["symbol"] or r["key"], "amc": r["amc"], "plan": r["plan"],
            "group": r["grp"], "sub": r["sub"], "categoryLabel": _sub_label(r["category"]) if r["kind"] == "mf" else "Exchange-traded fund", "final": r["final"], "label": r["label"],
            "status": r["status"], "reason": r["reason"], "pillars": {"performance": r["perf"], "risk": r["risk"], "cost": r["cost"], "quality": r["quality"]},
            "rank": r["rank"], "rankOf": r["rank_of"], "aumCr": None if r["aum_lakh"] is None else round(r["aum_lakh"] / 100.0, 1), "ageYears": r["age_years"],
            "ter": r["ter"], "r1y": r["r1y"], "r3y": r["r3y"], "r5y": r["r5y"], "fullData": r["confidence"] is not None and r["confidence"] >= 0.999,
            "flags": list(r["flags"] or [])}


def screener_query(q: Dict[str, Any]):
    where, args = ["m.final IS NOT NULL" if q["rated_only"] else "TRUE"], []

    def arg(v):
        args.append(v)
        return f"${len(args)}"
    if q["plan"] != "all":
        where.append(f"m.plan = {arg(q['plan'])}")
    if q["subs"]:
        where.append(f"m.sub = ANY({arg(q['subs'])}::text[])")
    if q["groups"]:
        where.append(f"m.grp = ANY({arg(q['groups'])}::text[])")
    if q["labels"]:
        where.append(f"m.label = ANY({arg(q['labels'])}::text[])")
    if q["status"]:
        where.append(f"m.status = {arg(q['status'])}")
    for col, lo, hi in (("m.final", q["min"], q["max"]), ("m.perf", q["perf_min"], q["perf_max"]), ("m.risk", q["risk_min"], q["risk_max"]),
                        ("m.cost", q["cost_min"], q["cost_max"]), ("m.quality", q["quality_min"], q["quality_max"]),
                        ("(s.aum_lakh / 100.0)", q["aum_min"], q["aum_max"]), ("COALESCE(round(((m.run_date - f.launch_date) / 365.25)::numeric, 1), round(m.months / 12.0, 1))", q["age_min"], q["age_max"])):
        if lo is not None:
            where.append(f"{col} >= {arg(lo)}")
        if hi is not None:
            where.append(f"{col} <= {arg(hi)}")
    if q["ter_max"] is not None:
        where.append(f"s.ter <= {arg(q['ter_max'])}")
    if q["full"]:
        where.append("m.confidence >= 0.999")
    if q["text"]:
        where.append(f"(COALESCE(s.name, e.display_name) ILIKE {arg('%' + q['text'].replace('%', '').replace('_', '') + '%')})")
    return " AND ".join(where), args


def read_query(request: Request) -> Dict[str, Any]:
    g = request.query_params

    def num(k: str, lo: float = -1e9, hi: float = 1e9) -> Optional[float]:
        v = g.get(k)
        if v in (None, ""):
            return None
        try:
            x = float(v)
        except ValueError:
            raise fail(400, "bad_request", f"{k} must be a number.")
        if not lo <= x <= hi:
            raise fail(400, "bad_request", f"{k} is out of range.")
        return x

    def lst(k: str, allowed=None, maxn: int = 60) -> List[str]:
        out = [x.strip() for x in (g.get(k) or "").split(",") if x.strip()][:maxn]
        if allowed is not None and any(x not in allowed for x in out):
            raise fail(400, "bad_request", f"Unknown value in {k}.")
        if any(len(x) > 60 for x in out):
            raise fail(400, "bad_request", f"Unknown value in {k}.")
        return out
    plan = g.get("plan", "Direct")
    if plan not in ("Direct", "Regular", "ETF", "all"):
        raise fail(400, "bad_request", "Unknown plan.")
    status = g.get("status", "")
    if status and status not in STATUSES:
        raise fail(400, "bad_request", "Unknown status.")
    sort = g.get("sort", "final")
    if sort not in SORT_SQL:
        raise fail(400, "bad_request", "Unknown sort column.")
    direction = g.get("dir", "desc")
    if direction not in ("asc", "desc"):
        raise fail(400, "bad_request", "Unknown direction.")
    try:
        off = int(g.get("offset", "0"))
        lim = int(g.get("limit", "50"))
    except ValueError:
        raise fail(400, "bad_request", "limit and offset must be whole numbers.")
    if not 0 <= off <= 100000 or not 1 <= lim <= CSV_MAX:
        raise fail(400, "bad_request", "limit or offset is out of range.")
    q = {"plan": plan, "subs": lst("sub"), "groups": lst("group", set(GROUP_NAMES)), "labels": lst("labels", set(LABELS)), "status": status,
         "min": num("min", 0, 100), "max": num("max", 0, 100), "perf_min": num("perf_min", 0, 100), "perf_max": num("perf_max", 0, 100), "risk_min": num("risk_min", 0, 100),
         "risk_max": num("risk_max", 0, 100), "cost_min": num("cost_min", 0, 100), "cost_max": num("cost_max", 0, 100), "quality_min": num("quality_min", 0, 100),
         "quality_max": num("quality_max", 0, 100), "aum_min": num("aum_min", 0, 1e8), "aum_max": num("aum_max", 0, 1e8), "age_min": num("age_min", 0, 200), "age_max": num("age_max", 0, 200),
         "ter_max": num("ter_max", 0, 20), "full": g.get("full") in ("1", "true"), "rated_only": g.get("scored", "1") != "0", "text": (g.get("q") or "").strip()[:60],
         "sort": sort, "dir": direction, "offset": off, "limit": lim}
    return q


async def run_screener(request: Request, q: Dict[str, Any]) -> Dict[str, Any]:
    where, args = screener_query(q)
    order = f"{SORT_SQL[q['sort']]} {'ASC' if q['dir'] == 'asc' else 'DESC'} NULLS LAST, m.key"
    async with request.app.state.store.pool.acquire() as conn:
        total = await conn.fetchval(f"SELECT count(*) FROM mf_scores m LEFT JOIN mf_schemes s ON s.code = m.code LEFT JOIN etf_funds e ON e.symbol = m.symbol AND m.kind = 'etf' LEFT JOIN mf_facts f ON f.code = m.code WHERE {where}", *args)  # nosec B608 - fixed column text; every value is a bound parameter
        rows = await conn.fetch(f"{SELECT} WHERE {where} ORDER BY {order} LIMIT {int(q['limit'])} OFFSET {int(q['offset'])}", *args)  # nosec B608 - fixed text; limit and offset are range-checked integers
        run = await conn.fetchval("SELECT max(run_date) FROM mf_scores")
    return {"locked": False, "total": total, "runDate": run.isoformat() if run else None, "items": [item_of(dict(r)) for r in rows], "disclaimer": DISCLAIMER, "method": METHOD_URL, "model": MODEL_VERSION}


def safe_cell(v: Any) -> Any:
    """A spreadsheet reads a cell that starts with = + - @ as a formula: those start with an apostrophe in the file."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


CSV_COLUMNS = [("Fund", "name"), ("Fund house", "amc"), ("Plan", "plan"), ("Category", "categoryLabel"), ("Score", "final"), ("Label", "label"), ("Status", "status"),
               ("Performance", "performance"), ("Risk", "risk"), ("Cost", "cost"), ("Quality", "quality"), ("Rank in category", "rank"), ("Funds ranked", "rankOf"),
               ("AUM (Rs crore)", "aumCr"), ("Age (years)", "ageYears"), ("Expense ratio (%)", "ter"), ("1Y return (%)", "r1y"), ("3Y return (% a year)", "r3y"), ("5Y return (% a year)", "r5y")]


def csv_text(items: List[Dict[str, Any]], run_date: Optional[str]) -> str:
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow([c for c, _ in CSV_COLUMNS])
    for it in items:
        row = {**it, **it["pillars"]}
        w.writerow([safe_cell("" if row.get(k) is None else row[k]) for _, k in CSV_COLUMNS])
    w.writerow([])
    w.writerow([safe_cell(f"FinLit Mutual Fund Health Score, worked out {run_date or 'n/a'}. {DISCLAIMER}")])
    return out.getvalue()


@router.get("/score-screener")
async def score_screener(request: Request):
    """The Fund Score Screener list. Gold only: below that, `locked` and no fund (the list itself would say who scores what)."""
    q = read_query(request)
    if not await may_see(request):
        return locked()
    if request.query_params.get("format") == "csv":
        q["limit"], q["offset"] = min(q["limit"], CSV_MAX), 0
        body = await run_screener(request, q)
        return Response(csv_text(body["items"], body["runDate"]), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="finlit-fund-scores.csv"', "Cache-Control": PRIVATE, "Vary": "Cookie"})
    return _json(await cached(request, "screen", q, lambda: run_screener(request, q)))


@router.get("/score-screener/facets")
async def score_facets(request: Request):
    """Sub-categories with the number of scored funds per plan, for the filter. Gold only (the list is the screener's, not a public one)."""
    if not await may_see(request):
        return locked(categories=[])

    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            rows = await conn.fetch("SELECT sub, plan, grp, min(category) AS category, count(*) AS n FROM mf_scores WHERE final IS NOT NULL GROUP BY sub, plan, grp ORDER BY sub")
            run = await conn.fetchval("SELECT max(run_date) FROM mf_scores")
        subs: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            d = subs.setdefault(r["sub"], {"sub": r["sub"], "label": _sub_label(r["category"]) if r["plan"] != "ETF" else "Exchange-traded funds", "group": r["grp"], "n": {}})
            d["n"][r["plan"]] = r["n"]
        return {"locked": False, "categories": sorted(subs.values(), key=lambda x: x["label"] or ""), "groups": GROUP_NAMES, "runDate": run.isoformat() if run else None,
                "disclaimer": DISCLAIMER, "method": METHOD_URL}
    return _json(await cached(request, "facets", {}, build))


# ------------------------------------------------------------------------------------------------------------------------------------ leaderboard
def spread_of(vals: List[float]) -> Dict[str, Optional[float]]:
    v = sorted(vals)
    if not v:
        return {"median": None, "p25": None, "p75": None, "min": None, "max": None}
    qs = statistics.quantiles(v, n=4, method="inclusive") if len(v) >= 2 else [v[0]] * 3
    return {"median": round(statistics.median(v), 1), "p25": round(qs[0], 1), "p75": round(qs[2], 1), "min": round(v[0], 1), "max": round(v[-1], 1)}


@router.get("/leaderboard")
async def leaderboard(request: Request, sub: str = Query(..., min_length=1, max_length=60), plan: str = Query("Direct", pattern="^(Direct|Regular|ETF)$")):
    """Every scored fund of one category and plan, highest score first, with the category's median and spread. Gold only."""
    if not await may_see(request):
        return locked(sub=sub, plan=plan, stats=None)

    async def build():
        async with request.app.state.store.pool.acquire() as conn:
            rows = await conn.fetch(f"{SELECT} WHERE m.sub = $1 AND m.plan = $2 AND m.final IS NOT NULL ORDER BY m.final DESC, m.key LIMIT 400", sub, plan)  # nosec B608 - fixed text
            n_all = await conn.fetchval("SELECT count(*) FROM mf_scores WHERE sub = $1 AND plan = $2", sub, plan)
            run = await conn.fetchval("SELECT max(run_date) FROM mf_scores")
        items = [item_of(dict(r)) for r in rows]
        near = any("NEAR_IDENTICAL" in it["flags"] for it in items)
        stats = {**spread_of([it["final"] for it in items]), "n": len(items), "notRated": max(0, n_all - len(items))}
        for k in ("performance", "risk", "cost", "quality"):
            stats[k] = spread_of([it["pillars"][k] for it in items if it["pillars"][k] is not None])["median"]
        label = items[0]["categoryLabel"] if items else None
        return {"locked": False, "sub": sub, "plan": plan, "categoryLabel": label, "items": items, "stats": stats, "nearIdentical": near,
                "nearIdenticalText": "Funds in this category are near-identical: their returns differ by a few hundredths of a percentage point, so cost carries the most weight and small score gaps mean little." if near else None,
                "runDate": run.isoformat() if run else None, "disclaimer": DISCLAIMER, "method": METHOD_URL}
    return _json(await cached(request, "board", [sub, plan], build))


# ------------------------------------------------------------------------------------------------------------------------------------ history
async def history_rows(conn, key: str) -> List[Dict[str, Any]]:
    rows = await conn.fetch("SELECT * FROM mf_score_history WHERE key = $1 ORDER BY week", key)
    return [dict(r) for r in rows]


def history_body(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    first = rows[0]["run_date"] if rows else None
    note = None
    if len(rows) < 2:
        note = "Not enough history yet: the score is stored weekly" + (f" from {first.strftime('%d %b %Y')}" if first else ", starting with the next weekly run") + "."
    return {"locked": False, "key": key, "points": [scorehist.point(r) for r in rows], "count": len(rows), "firstDate": first.isoformat() if first else None, "note": note,
            "changes": scorehist.changed_since(rows), "disclaimer": DISCLAIMER, "method": METHOD_URL}


def locked_history(**extra: Any) -> JSONResponse:
    return _json({"locked": True, "plan": "gold", "points": [], "count": None, "firstDate": None, "note": None, "changes": None, "disclaimer": DISCLAIMER, "method": METHOD_URL, **extra})


@router.get("/scores/history")
async def many_history(request: Request, codes: str = Query("", max_length=200), symbols: str = Query("", max_length=200)):
    """The final-score lines of up to 10 funds (Fund Compare overlay). Gold only."""
    try:
        ids = list(dict.fromkeys(int(x) for x in codes.split(",") if x.strip()))
    except ValueError:
        raise fail(400, "bad_request", "codes must be scheme codes separated by commas.")
    syms = list(dict.fromkeys(x.strip().upper() for x in symbols.split(",") if x.strip().isalnum()))
    if len(ids) + len(syms) > 10 or any(not 0 < c < 10 ** 7 for c in ids):
        raise fail(400, "bad_request", "Up to 10 funds.")
    if not await may_see(request):
        return locked_history(series={})
    keys = [f"mf:{c}" for c in ids] + [f"etf:{s}" for s in syms]
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT key, week, run_date, final, label FROM mf_score_history WHERE key = ANY($1::text[]) ORDER BY key, week", keys)
    series: Dict[str, List[Dict[str, Any]]] = {k: [] for k in keys}
    for r in rows:
        series[r["key"]].append({"date": r["run_date"].isoformat(), "final": None if r["final"] is None else round(float(r["final"]), 1), "label": r["label"]})
    return _json({"locked": False, "series": series, "disclaimer": DISCLAIMER, "method": METHOD_URL})


@router.get("/{code}/score/history")
async def mf_history(request: Request, code: int):
    if not 0 < code < 10 ** 7:
        raise fail(404, "not_found", "No mutual fund scheme has this code.")
    async with request.app.state.store.pool.acquire() as conn:
        row, _inh, why = await resolve_mf(conn, code)
        if why == "unknown":
            raise fail(404, "not_found", "No mutual fund scheme has this code.")
        if not await may_see(request, code):
            return locked_history()
        rows = await history_rows(conn, row["key"]) if row else []
    return _json(history_body(rows, row["key"] if row else f"mf:{code}"))


@router.get("/etf/{symbol}/score/history")
async def etf_history(request: Request, symbol: str):
    sym = symbol.strip().upper()
    if not sym.isalnum() or len(sym) > 20:
        raise fail(404, "not_found", "No exchange-traded fund has this symbol.")
    if not await may_see(request):
        return locked_history()
    async with request.app.state.store.pool.acquire() as conn:
        rows = await history_rows(conn, f"etf:{sym}")
    return _json(history_body(rows, f"etf:{sym}"))


# ------------------------------------------------------------------------------------------------------------------------------------ alerts
class ScoreAlertIn(BaseModel):
    code: Optional[int] = Field(default=None, ge=1, le=9999999)
    symbol: Optional[str] = Field(default=None, max_length=20, pattern="^[A-Za-z0-9]+$")
    kind: Literal["band", "move"]
    points: Optional[float] = Field(default=None, ge=1, le=50)
    channels: List[str] = Field(default_factory=lambda: ["app"], max_length=3)


def alert_view(r: Any) -> Dict[str, Any]:
    return {"id": str(r["id"]), "key": r["key"], "name": r["name"], "kind": r["kind"], "points": r["points"], "channels": list(r["channels"]), "status": r["status"],
            "firedCount": r["fired_count"], "firedAt": r["fired_at"].isoformat() if r["fired_at"] else None, "createdAt": r["created_at"].isoformat()}


def need_gold(ctx: Ctx) -> None:
    if not (has(ctx.plan, "gold") or ctx.role == "admin"):
        raise fail(403, "plan_required", "Score alerts are part of the Gold plan.", plan="gold")


def json_nostore(body: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=NO_STORE)


@router.get("/score-alerts")
async def my_alerts(request: Request, ctx: Ctx = Depends(secure_ctx)):
    need_gold(ctx)
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM mf_score_alerts WHERE user_id = $1 ORDER BY created_at DESC", ctx.user_id)
    return json_nostore({"alerts": [alert_view(r) for r in rows]})


@router.post("/score-alerts", status_code=201)
async def add_alert(request: Request, body: ScoreAlertIn, ctx: Ctx = Depends(secure_ctx)):
    need_gold(ctx)
    await limit(request, "alertw", ctx.user_id, 60, 600)
    if (body.code is None) == (body.symbol is None):
        raise fail(422, "bad_request", "Give a scheme code or an ETF symbol.")
    if body.kind == "move" and body.points is None:
        raise fail(422, "value_required", "Choose how many points the score has to move.")
    if any(c not in ("app", "email", "browser") for c in body.channels):
        raise fail(422, "bad_channel", "Notify via in-app, email or browser.")
    channels = ["app"] + [c for c in ("email", "browser") if c in body.channels]
    key = f"mf:{body.code}" if body.code else f"etf:{body.symbol.upper()}"
    async with request.app.state.store.pool.acquire() as conn:
        if body.code:
            row, _inh, why = await resolve_mf(conn, body.code)
            if row is None:
                raise fail(404 if why == "unknown" else 422, "not_scored", "This scheme has no score to follow.")
            key = row["key"]
            name = await conn.fetchval("SELECT name FROM mf_schemes WHERE code = $1", body.code)
        else:
            name = await conn.fetchval("SELECT display_name FROM etf_funds WHERE symbol = $1", body.symbol.upper())
            if name is None:
                raise fail(404, "not_found", "No exchange-traded fund has this symbol.")
        if await conn.fetchval("SELECT 1 FROM mf_score_alerts WHERE user_id = $1 AND key = $2 AND kind = $3", ctx.user_id, key, body.kind):
            raise fail(409, "duplicate", "You already follow this.")
        cap = ALERT_LIMITS["gold"]
        used = await conn.fetchval("SELECT (SELECT count(*) FROM alerts WHERE user_id = $1 AND status <> 'done') + (SELECT count(*) FROM mf_score_alerts WHERE user_id = $1)", ctx.user_id)
        if used >= cap:
            raise fail(403, "plan_limit", f"Your plan includes {cap} alerts at a time. Remove one that has finished.", plan="gold")
        r = await conn.fetchrow("INSERT INTO mf_score_alerts (user_id, key, name, kind, points, channels) VALUES ($1, $2, $3, $4, $5, $6) RETURNING *",
                                ctx.user_id, key, name, body.kind, body.points if body.kind == "move" else None, channels)
    return json_nostore(alert_view(r), 201)


@router.delete("/score-alerts/{alert_id}")
async def drop_alert(request: Request, alert_id: str, ctx: Ctx = Depends(secure_ctx)):
    need_gold(ctx)
    try:
        import uuid
        uid = uuid.UUID(alert_id)
    except ValueError:
        raise fail(404, "not_found", "No such alert.")
    async with request.app.state.store.pool.acquire() as conn:
        n = int((await conn.execute("DELETE FROM mf_score_alerts WHERE id = $1 AND user_id = $2", uid, ctx.user_id)).split()[-1])
    if not n:
        raise fail(404, "not_found", "No such alert.")
    return json_nostore({"ok": True})
