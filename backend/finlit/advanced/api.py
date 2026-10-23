"""Advanced charts endpoints (/api/advanced). The plan check, the figures and the statistics all live here; the website only draws.
Contract: docs/ADVANCED-CHARTS-API.md."""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
from datetime import date
from typing import Any, Dict, List, Literal, Optional, Tuple

import orjson
from fastapi import APIRouter, Query, Request, Response
from pydantic import BaseModel, Field, field_validator

from .. import indices as idx_mod
from ..auth.entitlements import has
from ..auth.routes import SYMBOL, fail
from ..auth.service import current
from ..graphviews import limits_for
from ..screener.catalog import INDEX_LISTS
from ..screener.data import get_table
from . import derive, index as index_mod, stats as S, table as T, tech as tech_mod
from .catalog import BY_ID, CAVEATS, METRICS, REASONS, catalog_json, history_tier

router = APIRouter(prefix="/api/advanced")
log = logging.getLogger("finlit.advanced")
PRIVATE = {"Cache-Control": "private, no-store", "Vary": "Cookie"}
METRIC_ID = re.compile(r"^[a-z0-9_]{1,24}$")
# Market series a beta or a yearly return can be compared with: indices whose daily levels the site already serves (/api/indices/{code}/history)
BENCHMARKS = {"NIF50": "NIFTY 50", "SNSXSENSEX": "BSE Sensex", "NIFBAN": "NIFTY Bank", "NIFMID100": "NIFTY Midcap 100",
              "NIFSMA100": "NIFTY Smallcap 100", "NIFIT": "NIFTY IT"}
HISTORY_TTL, TECH_TTL = 3600, 6 * 3600
_catalog_body: Optional[bytes] = None


def _h(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]   # cache key only


def _plan(ctx) -> str:
    return ctx.plan if ctx.authed else "basic"


def _json(body: Any, headers: Optional[dict] = None) -> Response:
    return Response(content=orjson.dumps(body), media_type="application/json", headers=headers or PRIVATE)


def _need(plan: str, tier: str, what: str) -> None:
    if not has(plan, tier):
        raise fail(403, "plan_required", f"{what} {'are' if what.endswith('s') else 'is'} part of the {tier.title()} plan.", plan=tier)


def _limit(plan: str, n: int) -> None:
    lim = limits_for(plan)["companies"]
    if n > lim:
        raise fail(403, "plan_limit", f"Your plan includes up to {lim} companies in one chart.", **({"plan": "gold"} if plan == "silver" else {"plan": "silver"} if plan not in ("gold",) else {}), limit=lim)


def _symbols(raw: List[str]) -> List[str]:
    out: List[str] = []
    for s in raw:
        s = (s or "").strip().upper()
        if not SYMBOL.match(s):
            raise fail(400, "bad_request", "Unknown symbol.")
        if s not in out:
            out.append(s)
    return out


# ------------------------------------------------------------------ catalogue
@router.get("/catalog")
async def catalog():
    global _catalog_body
    if _catalog_body is None:
        body = catalog_json()
        body["benchmarks"] = [{"code": c, "label": l} for c, l in BENCHMARKS.items()]
        body["indices"] = [{"code": c, "label": INDEX_LISTS[c][0]} for c in INDEX_LISTS]
        _catalog_body = orjson.dumps(body)
    return Response(content=_catalog_body, media_type="application/json", headers={"Cache-Control": "public, max-age=300"})


# ------------------------------------------------------------------ cross-section
class Universe(BaseModel):
    sector: List[str] = Field(default_factory=list, max_length=40)
    industry: List[str] = Field(default_factory=list, max_length=60)
    index: List[str] = Field(default_factory=list, max_length=20)
    cap: List[Literal["Large", "Mid", "Small"]] = Field(default_factory=list, max_length=3)
    mcapMin: Optional[float] = Field(default=None, ge=0, le=1e9)
    mcapMax: Optional[float] = Field(default=None, ge=0, le=1e9)
    lenders: Literal["auto", "exclude", "include", "only"] = "auto"
    sameFy: bool = False
    preset: bool = True


class Scale(BaseModel):
    x: Literal["lin", "log"] = "lin"
    y: Literal["lin", "log"] = "lin"


class CrossIn(BaseModel):
    pair: Optional[str] = Field(default=None, max_length=8)
    x: Optional[str] = Field(default=None, max_length=24)
    y: Optional[str] = Field(default=None, max_length=24)
    variant: Optional[Literal["forward"]] = None
    universe: Universe = Field(default_factory=Universe)
    scale: Optional[Scale] = None
    trim: bool = False
    highlight: List[str] = Field(default_factory=list, max_length=12)
    indices: List[str] = Field(default_factory=list, max_length=3)

    @field_validator("indices")
    @classmethod
    def _known_index(cls, v: List[str]) -> List[str]:
        out = []
        for c in v:
            c = c.strip().upper()
            if c not in INDEX_LISTS:
                raise ValueError("unknown index")
            if c not in out:
                out.append(c)
        return out


def _cross_core(t, body: CrossIn, plan: str) -> dict:
    _need(plan, "silver", "Advanced charts")
    if body.variant:
        _need(plan, "gold", "Forward-return charts")
    for m in (body.x, body.y):
        if m is not None and not METRIC_ID.match(m):
            raise fail(400, "bad_request", "Unknown metric.")
    if body.pair and body.pair not in BY_ID:
        raise fail(404, "unknown_pair", "There is no such chart.")
    d = body.model_dump()
    d.pop("indices", None)
    if body.scale is None:
        d.pop("scale")
    try:
        return T.compute(t, d)
    except ValueError as exc:
        raise fail(400, "bad_request", str(exc))


def _index_points(t, core: dict, codes: List[str]) -> List[dict]:
    xm, ym = METRICS[core["x"]["id"]], METRICS[core["y"]["id"]]
    mode = {"included": "include", "excluded": "exclude", "only": "only"}[core["lenders"]["mode"]]
    scale = {"x": core["x"]["scale"], "y": core["y"]["scale"]}
    return [index_mod.point(t, c, INDEX_LISTS[c][0], xm, ym, mode, scale, T.value_of, T.fy_of) for c in codes]


@router.post("/cross")
async def cross(request: Request, body: CrossIn):
    plan = _plan(await current(request))
    t = await get_table(request.app.state.store)
    core = _cross_core(t, body, plan)
    syms = _symbols(body.highlight)
    _limit(plan, len(syms))
    out = T.public(core, T.highlights(t, core, syms))
    out["indices"] = _index_points(t, core, body.indices)
    return _json(out)


# ------------------------------------------------------------------ history
async def _statement(store, sym: str) -> Optional[str]:
    async with store.pool.acquire() as conn:
        return await conn.fetchval("SELECT statement FROM scores WHERE symbol = $1 AND model = 'v1' ORDER BY (statement = 'consolidated') DESC, updated_at DESC LIMIT 1", sym)


async def _sections(store, sym: str, st: str, names: Tuple[str, ...]) -> Tuple[Dict[str, dict], str]:
    secs: Dict[str, dict] = {}
    tags: List[str] = []
    for nm in names:
        hit = await store.get_section(sym, st, nm)
        if hit is not None:
            secs[nm] = orjson.loads(hit[0])
            tags.append(hit[1])
    return secs, "|".join(tags)


async def _cached(store, key: str, ttl: int, build):
    try:
        raw = await store.redis.get(key)
    except Exception:
        raw = None
    if raw:
        return orjson.loads(raw)
    val = build()
    try:
        await store.redis.set(key, orjson.dumps(val), ex=ttl)
    except Exception:
        pass
    return val


async def company_history(store, sym: str) -> Optional[dict]:
    st = await _statement(store, sym)
    if st is None:
        return None
    etags = []
    for nm in ("financials", "ratios", "events", "summary"):
        e = await store.get_etag(sym, st, nm)
        etags.append(e or "")
    key = None
    if all(etags):
        key = "adv:h:" + sym + ":" + st + ":" + _h("|".join(etags))
        try:
            raw = await store.redis.get(key)
            if raw:
                return orjson.loads(raw)
        except Exception:
            pass
    secs, _ = await _sections(store, sym, st, ("financials", "ratios", "events", "summary", "price"))
    if "financials" not in secs:
        return None
    h = derive.history(secs)
    h["statement"] = st
    h["name"] = ((secs.get("summary") or {}).get("profile") or {}).get("name") or sym
    h["isBank"] = bool(((secs.get("summary") or {}).get("dataQuality") or {}).get("isBank"))
    if key:
        try:
            await store.redis.set(key, orjson.dumps(h), ex=HISTORY_TTL)
        except Exception:
            pass
    return h


async def _levels(app, code: str) -> List[Tuple[date, float]]:
    raw = await idx_mod._cached(app, f"idx:px:{code}", 3600 if idx_mod.market_open() else 6 * 3600, lambda: idx_mod._fetch_levels(app, code))
    rows = idx_mod.shape_levels(raw, idx_mod.HISTORY_YEARS)["rows"] if raw else []
    return [(date.fromisoformat(r["d"]), float(r["c"])) for r in rows]


def _close_at(levels: List[Tuple[date, float]], target: date) -> Optional[float]:
    best = None
    for d, c in levels:
        if d <= target:
            best = (d, c)
        else:
            break
    if best is None or (target - best[0]).days > derive.START_DAYS:
        return None
    return best[1]


def benchmark_years(levels: List[Tuple[date, float]], fys: List[str], ends: List[Optional[str]]) -> List[dict]:
    """The index's price return over each financial year (close on the year end / close on the previous year end - 1), same rules as ret_fy."""
    out = []
    for i, fy in enumerate(fys):
        e1 = date.fromisoformat(ends[i]) if ends[i] else None
        e0 = date.fromisoformat(ends[i - 1]) if i > 0 and ends[i - 1] else None
        if e1 is None or e0 is None or not derive.GAP_MIN <= (e1 - e0).days <= derive.GAP_MAX:
            out.append({"fy": fy, "value": None, "reason": "no_prev"})
            continue
        c0, c1 = _close_at(levels, e0), _close_at(levels, e1)
        if c0 is None or c1 is None:
            out.append({"fy": fy, "value": None, "reason": "short_history"})
        else:
            out.append({"fy": fy, "value": (c1 / c0 - 1.0) * 100.0, "reason": None})
    return out


def _history_body(hist: Dict[str, Optional[dict]], syms: List[str], x: str, y: str) -> List[dict]:
    comps = []
    for s in syms:
        h = hist.get(s)
        if h is None:
            comps.append({"s": s, "name": None, "status": "no_report", "points": [], "missing": [], "n": 0, "stats": None,
                          "reasonText": REASONS["no_report"]})
            continue
        pts, miss = [], []
        for i, fy in enumerate(h["fys"]):
            xv, yv = h["values"][x][i], h["values"][y][i]
            if xv is None or yv is None:
                if xv is None:
                    miss.append({"fy": fy, "axis": "x", "code": h["miss"][x][i], "text": REASONS.get(h["miss"][x][i], "")})
                if yv is None:
                    miss.append({"fy": fy, "axis": "y", "code": h["miss"][y][i], "text": REASONS.get(h["miss"][y][i], "")})
                continue
            pts.append({"fy": fy, "x": float(f"{xv:.10g}"), "y": float(f"{yv:.10g}")})
        st = S.analyse([(p["x"], p["y"], p["fy"]) for p in pts]) if pts else None
        if st and st.get("influence"):
            st["influence"]["max"]["s"] = st["influence"]["max"].pop("label")
        comps.append({"s": s, "name": h.get("name"), "status": "ok", "isBank": h.get("isBank"), "points": pts, "missing": miss, "n": len(pts),
                      "stats": S.round_sig(st) if st else None})
    return comps


async def _history(request: Request, plan: str, symbols: List[str], x: Optional[str], y: Optional[str], pair: Optional[str], bench: Optional[str]) -> dict:
    _need(plan, "silver", "Advanced charts")
    p = None
    if pair:
        p = BY_ID.get(pair)
        if p is None:
            raise fail(404, "unknown_pair", "There is no such chart.")
        if "history" not in p.get("modes", []):
            raise fail(400, "bad_request", "This chart has no history view.")
        x, y = p["x"], p["y"]
    if not x or not y or x not in METRICS or y not in METRICS:
        raise fail(400, "bad_request", "Unknown metric.")
    tier = history_tier(x, y)
    if tier is None:
        raise fail(400, "bad_request", "No yearly history is stored for one of these figures.")
    _need(plan, tier, "Full ratio and valuation history")
    syms = _symbols(symbols)
    if not syms:
        raise fail(400, "bad_request", "Add at least one company.")
    _limit(plan, len(syms))
    if bench is not None and bench not in BENCHMARKS:
        raise fail(400, "bad_request", "Unknown benchmark index.")
    store = request.app.state.store
    hist = {s: await company_history(store, s) for s in syms}
    xm, ym = METRICS[x], METRICS[y]
    notes = ["Series that trend over time can correlate even when they are unrelated.", "Statistics are per company (one point per year), never pooled across companies."]
    if p and p.get("mechanical"):
        notes.insert(0, p["mechanical"])
    if x in ("pe", "pb") or y in ("pe", "pb"):
        notes.append("Yearly P/E and P/B are the provider's: the average share price over the financial year / that year's EPS or book value per share.")
    out = {"pair": p["id"] if p else None,
           "x": {"id": x, "label": xm.label if x not in ("pe", "pb") else xm.label + " (yearly, average price)", "unit": xm.unit, "basis": "fy", "scale": "lin"},
           "y": {"id": y, "label": ym.label if y not in ("pe", "pb") else ym.label + " (yearly, average price)", "unit": ym.unit, "basis": "fy", "scale": "lin"},
           "companies": _history_body(hist, syms, x, y), "notes": notes, "caveats": list(CAVEATS), "benchmarks": []}
    if bench and ({"ret_fy", "tsr_fy"} & {x, y}):
        levels = await _levels(request.app, bench)
        rows = []
        for s in syms:
            h = hist.get(s)
            if h:
                rows.append({"s": s, "years": benchmark_years(levels, h["fys"], h["ends"]) if levels else
                             [{"fy": f, "value": None, "reason": "no_market"} for f in h["fys"]]})
        out["benchmarks"] = [{"code": bench, "label": BENCHMARKS[bench], "metric": "ret_fy",
                              "note": "Index price return over each company's financial year (dividends not included: no total-return index is stored).", "companies": rows}]
    return out


@router.get("/history")
async def history(request: Request, symbols: str = Query(..., max_length=200), x: Optional[str] = Query(None, max_length=24),
                  y: Optional[str] = Query(None, max_length=24), pair: Optional[str] = Query(None, max_length=8),
                  index: Optional[str] = Query(None, max_length=24)):
    plan = _plan(await current(request))
    return _json(await _history(request, plan, symbols.split(","), x, y, pair, index.upper() if index else None))


# ------------------------------------------------------------------ technical (company mode)
async def _tech(request: Request, plan: str, symbol: str, kind: str, h: int, market: str) -> dict:
    _need(plan, "gold", "Technical and forward-return charts")
    sym = _symbols([symbol])[0]
    if kind not in tech_mod.KINDS:
        raise fail(400, "bad_request", "Unknown chart.")
    if kind in ("rsi", "macd", "p52h") and h not in tech_mod.HORIZONS:
        raise fail(400, "bad_request", "h must be 5, 20 or 60.")
    if market not in BENCHMARKS:
        raise fail(400, "bad_request", "Unknown benchmark index.")
    store = request.app.state.store
    st = await _statement(store, sym)
    if st is None:
        raise fail(404, "no_report", REASONS["no_report"])
    pe = await store.get_etag(sym, st, "events") or ""
    secs, tag = await _sections(store, sym, st, ("price", "events", "summary"))
    if "price" not in secs:
        raise fail(404, "no_report", REASONS["no_report"])
    levels = await _levels(request.app, market) if kind == "beta" else None
    key = f"adv:t:{sym}:{st}:{kind}:{h}:{market if kind == 'beta' else ''}:{_h(tag + pe)}"

    def build():
        return tech_mod.run(secs.get("price"), (secs.get("events") or {}).get("actions") or [], kind, h, levels, BENCHMARKS[market])
    body = await _cached(store, key, TECH_TTL, build) if kind != "beta" or levels else build()
    name = ((secs.get("summary") or {}).get("profile") or {}).get("name") or sym
    return {"symbol": sym, "name": name, "market": {"code": market, "label": BENCHMARKS[market]} if kind == "beta" else None, **body}


@router.get("/tech")
async def tech(request: Request, symbol: str = Query(..., max_length=24), kind: str = Query(..., max_length=8), h: int = Query(20, ge=1, le=260),
               market: str = Query("NIF50", max_length=24)):
    plan = _plan(await current(request))
    return _json(await _tech(request, plan, symbol, kind, h, market.upper()))


# ------------------------------------------------------------------ export
class ExportIn(BaseModel):
    mode: Literal["cross", "history", "tech"] = "cross"
    pair: Optional[str] = Field(default=None, max_length=8)
    x: Optional[str] = Field(default=None, max_length=24)
    y: Optional[str] = Field(default=None, max_length=24)
    variant: Optional[Literal["forward"]] = None
    universe: Universe = Field(default_factory=Universe)
    scale: Optional[Scale] = None
    trim: bool = False
    highlight: List[str] = Field(default_factory=list, max_length=12)
    symbols: List[str] = Field(default_factory=list, max_length=12)
    symbol: Optional[str] = Field(default=None, max_length=24)
    kind: Optional[str] = Field(default=None, max_length=8)
    h: int = Field(default=20, ge=1, le=260)
    market: str = Field(default="NIF50", max_length=24)


def safe_cell(v: Any) -> Any:
    """Formula-injection guard: a text cell that a spreadsheet would run as a formula gets a leading apostrophe."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + v
    return v


def _stats_header(st: Optional[dict]) -> List[Tuple[str, Any]]:
    if not st:
        return [("n", 0)]
    pr, sp, ols, ts = st.get("pearson") or {}, st.get("spearman") or {}, st.get("ols") or {}, st.get("theilSen") or {}
    return [("n", st.get("n")), ("pearson_r", pr.get("r")), ("r_squared", pr.get("r2")), ("p_value", pr.get("p")), ("spearman_rho", sp.get("rho")),
            ("ols_slope", ols.get("slope")), ("ols_intercept", ols.get("intercept")), ("theil_sen_slope", ts.get("slope")),
            ("theil_sen_intercept", ts.get("intercept")), ("decision", (st.get("decision") or {}).get("rule")), ("line", (st.get("decision") or {}).get("line"))]


@router.post("/export")
async def export(request: Request, body: ExportIn):
    plan = _plan(await current(request))
    _need(plan, "silver", "Downloading chart data")
    buf = io.StringIO()
    w = csv.writer(buf)

    def head(rows: List[Tuple[str, Any]]):
        for k, v in rows:
            w.writerow(["# " + k, safe_cell(v) if v is not None else ""])
        for c in CAVEATS:
            w.writerow(["# caveat", c])
        w.writerow([])
    if body.mode == "cross":
        t = await get_table(request.app.state.store)
        cin = CrossIn(pair=body.pair, x=body.x, y=body.y, variant=body.variant, universe=body.universe, scale=body.scale, trim=body.trim, highlight=body.highlight)
        core = _cross_core(t, cin, plan)
        syms = set(_symbols(body.highlight))
        _limit(plan, len(syms))
        name = core["pair"] or f"{core['x']['id']}-{core['y']['id']}"
        head([("chart", f"{core['x']['label']} vs {core['y']['label']}"), ("pair", core["pair"]), ("as_of", core["tableBuiltAt"]),
              ("universe_total", core["universeTotal"]), ("method", core["method"])] + _stats_header(core["stats"]))
        w.writerow(["symbol", "name", "sector", "fy", "x", "y", "included", "reason", "highlighted"])
        xm, ym = METRICS[core["x"]["id"]], METRICS[core["y"]["id"]]
        for i in sorted(core["_universe"], key=lambda i: t.symbols[i]):
            xv, yv = T.value_of(t, xm, i), T.value_of(t, ym, i)
            stt = core["_status"].get(i)
            w.writerow([safe_cell(t.symbols[i]), safe_cell(t.name[i]), safe_cell(t.sector[i] or ""), T.fy_of(t, xm, ym, i) or "",
                        "" if xv != xv else xv, "" if yv != yv else yv, "no" if stt else "yes", stt[1] if stt else "",
                        "yes" if t.symbols[i] in syms else "no"])
    elif body.mode == "history":
        out = await _history(request, plan, body.symbols, body.x, body.y, body.pair, None)
        name = out["pair"] or f"{out['x']['id']}-{out['y']['id']}"
        head([("chart", f"{out['x']['label']} vs {out['y']['label']} (per company, by financial year)"), ("pair", out["pair"])])
        w.writerow(["symbol", "name", "fy", "x", "y", "included", "reason"])
        for c in out["companies"]:
            for p in c["points"]:
                w.writerow([safe_cell(c["s"]), safe_cell(c["name"] or ""), p["fy"], p["x"], p["y"], "yes", ""])
            for m in c["missing"]:
                w.writerow([safe_cell(c["s"]), safe_cell(c["name"] or ""), m["fy"], "", "", "no", f"{m['axis']}:{m['code']}"])
            for k, v in _stats_header(c["stats"]):
                w.writerow([safe_cell(c["s"]), "# " + k, "", safe_cell(v) if v is not None else "", "", "", ""])
    else:
        out = await _tech(request, plan, body.symbol or "", body.kind or "", body.h, body.market.upper())
        name = f"{out['symbol']}-{out['kind']}"
        head([("chart", f"{out['x']['label']} vs {out['y']['label']}"), ("symbol", out["symbol"]), ("grid", out["grid"]), ("as_of", out["asOf"])] + _stats_header(out["stats"]))
        w.writerow(["date", "x", "y", "included", "reason"])
        for p in out["points"]:
            w.writerow([p["d"], p["x"], p["y"], "yes", ""])
        for e in out["excluded"]:
            w.writerow(["", "", "", "no", f"{e['code']} x{e['count']}"])
    fname = re.sub(r"[^A-Za-z0-9._-]", "-", f"finlit-advanced-{name}.csv")
    return Response(content="﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={**PRIVATE, "Content-Disposition": f'attachment; filename="{fname}"'})


# ------------------------------------------------------------------ section 9 warning lists (not correlations)
def cfo_divergence(h: dict) -> List[dict]:
    """The spec's high-priority warning: revenue and net profit up but operating cash flow down, per financial year (YoY)."""
    out = []
    v = h["values"]
    for i, fy in enumerate(h["fys"]):
        gr, gn, gc = v["g_rev"][i], v["g_np"][i], v["g_cfo"][i]
        if gr is not None and gn is not None and gc is not None and gr > 0 and gn > 0 and gc < 0:
            out.append({"fy": fy, "id": "cfo_divergence", "title": "Revenue and net profit rose but operating cash flow fell",
                        "why": "Investigate receivables, inventory, working capital and accounting accruals before drawing conclusions.",
                        "revenueGrowth": gr, "profitGrowth": gn, "cfoGrowth": gc})
    return out


@router.get("/flags")
async def flags(request: Request, symbols: str = Query(..., max_length=200)):
    """Section 9: the "profit growth more than three times revenue growth" rule (plflags case 1, the same rule as the stock page) and the
    revenue-and-profit-up-but-CFO-down warning, for the selected companies. Information only, never a correlation."""
    from ..plflags import pl_flags
    plan = _plan(await current(request))
    _need(plan, "silver", "Advanced charts")
    syms = _symbols(symbols.split(","))
    _limit(plan, len(syms))
    store = request.app.state.store
    out = []
    for s in syms:
        st = await _statement(store, s)
        secs, _ = await _sections(store, s, st, ("financials",)) if st else ({}, "")
        fin = secs.get("financials")
        if not fin:
            out.append({"s": s, "status": "no_report", "reasonText": REASONS["no_report"], "threeX": [], "cfo": []})
            continue
        y = (fin.get("yearly") or {}).get("pl")
        q = (fin.get("quarterly") or {}).get("pl")
        fl = pl_flags({**y, "period": "yearly"} if y else None, {**q, "period": "quarterly"} if q else None)   # as plalerts.fresh_flags
        h = await company_history(store, s)
        out.append({"s": s, "status": "ok", "threeX": [f for f in fl if f.get("case") == 1], "cfo": cfo_divergence(h) if h else []})
    return _json({"companies": out, "caveats": list(CAVEATS),
                  "rule": "Profit growth more than 3 times revenue growth with profit up at least 10% (same rule as the stock page's P&L flags)."})
