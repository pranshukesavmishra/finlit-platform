"""HTTP routes of the Macro & Sector Outlook.

Public, read-only, free for everyone (docs/MACRO-OUTLOOK.md, "Plan gating"); they read stored snapshots through Redis and never call an external source:
    GET /api/stocks/{symbol}/macro-outlook        (also /api/companies/{symbol}/macro-outlook)
    GET /api/macro/sector-impact
    GET /api/macro/sectors/{sector}/indicators
    GET /api/macro/sectors/{sector}/history?period=1M|3M|6M|1Y|ALL
    GET /api/macro/methodology
Admin (role protected, Origin + CSRF checked like every admin write, every change audited and creating a new model version): /api/admin/macro/*
"""
from __future__ import annotations

import json
import re
from decimal import Decimal
from datetime import date
from typing import Any, Dict, List, Literal, Optional

import orjson
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from ..auth.routes import Ctx, admin_ctx, fail, ip_of
from ..auth.service import audit
from ..background import etag_matches
from ..store import etag_for
from . import engine as E
from . import seed as SEED
from . import store as ST
from . import views as V

router = APIRouter()


def _plain(o: Any) -> Any:
    if isinstance(o, Decimal):
        return float(o)
    raise TypeError(type(o).__name__)


def dumps(value: Any) -> bytes:
    return orjson.dumps(value, default=_plain, option=orjson.OPT_NON_STR_KEYS)


admin = APIRouter(prefix="/api/admin/macro")
SYMBOL = re.compile(r"^[A-Z0-9&_.\-]{1,24}$")
CODE = re.compile(r"^[a-z0-9_]{1,40}$")
CACHE = "public, max-age=300, stale-while-revalidate=900"


def reply(request: Request, payload: Any, status: int = 200, cache: str = CACHE) -> Response:
    body = dumps(payload)
    etag = etag_for(body)
    headers = {"ETag": etag, "Cache-Control": cache if status == 200 else "no-store"}
    if status == 200 and etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, status_code=status, media_type="application/json", headers=headers)


async def active_version(store) -> Optional[int]:
    async with store.pool.acquire() as conn:
        return await conn.fetchval("SELECT model_version FROM macro_model_configuration WHERE active")


async def run_state(store, version: int) -> Dict[str, Any]:
    async def build():
        async with store.pool.acquire() as conn:
            return await V.run_info(conn, version)
    return await V.cached(store.redis, f"runinfo:{version}", build, 60)


# ------------------------------------------------------------------------------------------------------------ public
@router.get("/api/macro/sector-impact")
async def sector_impact(request: Request, sort: Literal["score", "name"] = "score", order: Literal["asc", "desc"] = "desc",
                        sentiment: str = Query("", max_length=40), q: str = Query("", max_length=60)) -> Response:
    store = request.app.state.store
    version = await active_version(store)
    if version is None:
        return reply(request, {"status": "pending", "detail": "The macro model has not been set up yet."}, 503)

    async def build():
        async with store.pool.acquire() as conn:
            return await V.impact(conn, version)
    body = await V.cached(store.redis, f"impact:{version}", build)
    sectors = list(body["sectors"])
    if sentiment:
        sectors = [s for s in sectors if s["label"].lower() == sentiment.lower()]
    if q:
        sectors = [s for s in sectors if q.lower() in s["sector"]["name"].lower()]
    if sort == "name":
        sectors.sort(key=lambda s: s["sector"]["name"].lower(), reverse=order == "desc")
    else:
        sectors.sort(key=lambda s: (s["score"] is None, (s["score"] or 0) * (1 if order == "asc" else -1), s["sector"]["name"]))
    info = await run_state(store, version)
    return reply(request, {**body, "sectors": sectors, "count": len(sectors), "stale": V.stale_state(info), "updatedAt": info.get("lastOk")})


async def _sector(store, code: str, version: int) -> Optional[Dict[str, Any]]:
    async def build():
        async with store.pool.acquire() as conn:
            return await V.sector_detail(conn, code, version)
    return await V.cached(store.redis, f"sector:{code}:{version}", build)


@router.get("/api/macro/sectors/{sector}/indicators")
async def sector_indicators(request: Request, sector: str) -> Response:
    store = request.app.state.store
    version = await active_version(store)
    code = await _sector_code(store, sector)
    if version is None or code is None:
        return reply(request, {"status": "unknown_sector", "detail": "That sector is not in the macro model."}, 404)
    d = await _sector(store, code, version)
    if d is None:
        return reply(request, {"status": "pending", "detail": "No snapshot has been calculated for this sector yet."}, 503)
    info = await run_state(store, version)
    return reply(request, {**d, "stale": V.stale_state(info), "disclaimer": V.DISCLAIMER})


async def _sector_code(store, ident: str) -> Optional[str]:
    async with store.pool.acquire() as conn:
        if ident.isdigit():
            return await conn.fetchval("SELECT sector_code FROM sector_master WHERE id = $1", int(ident))
        if not CODE.match(ident):
            return None
        return await conn.fetchval("SELECT sector_code FROM sector_master WHERE sector_code = $1", ident)


@router.get("/api/macro/sectors/{sector}/history")
async def sector_history(request: Request, sector: str, period: Literal["1M", "3M", "6M", "1Y", "ALL"] = "3M") -> Response:
    store = request.app.state.store
    version = await active_version(store)
    code = await _sector_code(store, sector)
    if version is None or code is None:
        return reply(request, {"status": "unknown_sector", "detail": "That sector is not in the macro model."}, 404)

    async def build():
        async with store.pool.acquire() as conn:
            return await V.history(conn, code, period, version)
    return reply(request, await V.cached(store.redis, f"history:{code}:{period}:{version}", build))


@router.get("/api/macro/methodology")
async def methodology(request: Request) -> Response:
    store = request.app.state.store
    version = await active_version(store)
    if version is None:
        return reply(request, {"status": "pending", "detail": "The macro model has not been set up yet."}, 503)

    async def build():
        async with store.pool.acquire() as conn:
            return await V.methodology(conn, version)
    return reply(request, await V.cached(store.redis, f"method:{version}", build, 3600))


async def indicators_payload(store, version: int) -> Dict[str, Any]:
    async def build():
        async with store.pool.acquire() as conn:
            return await V.indicators(conn, version)
    return await V.cached(store.redis, f"indicators:{version}", build)


def _company_base(symbol: str, name: str, version: int, info: Dict[str, Any]) -> Dict[str, Any]:
    return {"symbol": symbol, "company": name, "modelVersion": version, "stale": V.stale_state(info), "disclaimer": V.DISCLAIMER, "assumptionsNote": V.MODEL_NOTE}


def _strip(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in d.items() if k not in ("config", "snapshotId")}


async def company_outlook(store, symbol: str) -> tuple[int, Dict[str, Any]]:
    version = await active_version(store)
    if version is None:
        return 503, {"status": "pending", "detail": "The macro model has not been set up yet."}
    async with store.pool.acquire() as conn:
        co = await conn.fetchrow("SELECT symbol, name FROM companies WHERE symbol = $1", symbol)
        if co is None:
            return 404, {"status": "unknown_company", "detail": "This company is not in our list."}
        rows = [dict(r) for r in await conn.fetch(
            "SELECT m.is_primary, m.revenue_weight, m.segment_name, m.effective_from, m.source, m.basis_label, s.sector_code, s.name FROM company_sector_mapping m "
            "JOIN sector_master s ON s.id = m.sector_id WHERE m.symbol = $1 AND m.effective_to IS NULL ORDER BY m.is_primary DESC, m.revenue_weight DESC NULLS LAST", symbol)]
        unm = await conn.fetchrow("SELECT reason FROM company_macro_unmapped WHERE symbol = $1", symbol) if not rows else None
    info = await run_state(store, version)
    base = _company_base(co["symbol"], co["name"], version, info)
    primary = next((r for r in rows if r["is_primary"]), None)
    if primary is None:
        return 200, {**base, "status": "not_mapped", "reason": unm["reason"] if unm else "The company has not been assigned to a macro sector yet (the mapping runs nightly).",
                     "pending": unm is None}
    segs = [r for r in rows if not r["is_primary"] and r["revenue_weight"] is not None]
    inds = await indicators_payload(store, version)
    if not segs:
        d = await _sector(store, primary["sector_code"], version)
        if d is None:
            return 200, {**base, "status": "pending", "reason": "No snapshot has been calculated for this sector yet.", "mapping": _mapping(primary, None)}
        return 200, {**base, **_strip(d), "mapping": _mapping(primary, None), "indicators": _merge(inds, d), "groups": inds["groups"], "signalNote": inds["signalNote"]}
    # revenue-weighted: Company score = sum of segment weight x sector score, over sectors that have a score (they must hold the minimum coverage of the weight)
    parts = []
    for r in segs:
        d = await _sector(store, r["sector_code"], version)
        parts.append((r, d))
    cfg = parts[0][1]["config"] if parts and parts[0][1] else {}
    min_cov = float(cfg.get("minCoverage", 0.7))
    valid = [(r, d) for r, d in parts if d and d["status"] == "ok"]
    vw = sum(float(r["revenue_weight"]) for r, _ in valid)
    lead = max(parts, key=lambda p: float(p[0]["revenue_weight"]))[1]
    seg_view = [{"sector": r["sector_code"], "name": r["name"], "weight": float(r["revenue_weight"]), "segments": r["segment_name"], "score": d["score"] if d else None,
                 "label": d["label"] if d else "Insufficient Data", "tone": d["tone"] if d else "none"} for r, d in parts]
    out = {**base, "mapping": _mapping(primary, segs), "segments": seg_view, "indicators": _merge(inds, lead) if lead else inds["indicators"], "groups": inds["groups"], "signalNote": inds["signalNote"]}
    if not valid or vw + 1e-9 < min_cov:
        return 200, {**out, "status": "insufficient_data", "score": None, "label": E.INSUFFICIENT, "tone": "none", "coverage": round(vw, 4), "minCoverage": min_cov, "drivers": [],
                     "reason": f"segment sectors with a score hold only {vw * 100:.0f}% of revenue weight (minimum {min_cov * 100:.0f}%)", "snapshotDate": lead["snapshotDate"] if lead else None,
                     "asOf": lead["asOf"] if lead else None, "explanation": {}, "deltas": {}}
    score = round(sum(float(r["revenue_weight"]) / vw * d["score"] for r, d in valid), 2)
    label = E.band_of(score, tuple((b["min"], b["label"]) for b in cfg.get("bands", [{"min": m, "label": l} for m, l in E.DEFAULT_BANDS])))
    drv = []
    for r, d in valid:
        for x in d["drivers"]:
            drv.append({**x, "contribution": x["contribution"] * float(r["revenue_weight"]) / vw, "viaSector": r["name"]})
    drv.sort(key=lambda x: (-round(abs(x["contribution"]), 6), x["code"]))
    return 200, {**out, "status": "ok", "score": score, "label": label, "tone": E.tone_of(label), "coverage": round(vw, 4), "minCoverage": min_cov, "drivers": drv[:2],
                 "snapshotDate": lead["snapshotDate"], "asOf": lead["asOf"], "basis": lead["basis"], "reason": None, "explanation": lead.get("explanation", {}),
                 "deltas": {}, "weightedSignal": None,
                 "note": "Revenue-weighted across the company's reported segments; " + (segs[0]["basis_label"] or "")}


def _mapping(primary: Dict[str, Any], segs: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    return {"sector": primary["sector_code"], "sectorName": primary["name"], "effectiveFrom": primary["effective_from"].isoformat(), "source": primary["source"], "rule": primary["basis_label"],
            "basis": "revenue_weighted" if segs else "primary",
            "note": ("Weighted by reported segment revenue." if segs else
                     ("Based on the company's primary business sector; segment revenue weights are not used" + (" (diversified company without reliable segment data)." if primary["sector_code"] == "diversified" else ".")))}


def _merge(inds: Dict[str, Any], d: Dict[str, Any]) -> List[Dict[str, Any]]:
    by = {c["code"]: c for c in d.get("contributions", [])}
    out = []
    for i in inds["indicators"]:
        c = by.get(i["code"])
        out.append({**i, "sensitivity": None if c is None else {"coefficient": c["coefficient"], "weight": c["weight"], "critical": c["critical"], "contribution": c["contribution"],
                                                                 "counted": c["counted"], "reason": c["reason"]}})
    return out


@router.get("/api/stocks/{symbol}/macro-outlook")
@router.get("/api/companies/{symbol}/macro-outlook")
async def macro_outlook(request: Request, symbol: str) -> Response:
    sym = symbol.strip().upper()
    if not SYMBOL.match(sym):
        return reply(request, {"status": "invalid_symbol"}, 400)
    status, body = await company_outlook(request.app.state.store, sym)
    return reply(request, body, status)


# ------------------------------------------------------------------------------------------------------------ admin
class Change(BaseModel):
    sector: str = Field(max_length=40)
    indicator: str = Field(max_length=40)
    coefficient: Optional[float] = Field(default=None, ge=-1, le=1)
    weight: Optional[float] = Field(default=None, gt=0, le=10)
    critical: Optional[bool] = None
    remove: bool = False


class SensitivityIn(BaseModel):
    changes: List[Change] = Field(min_length=1, max_length=400)
    note: str = Field(min_length=3, max_length=300)


class BandIn(BaseModel):
    min: float = Field(ge=0, le=100)
    label: str = Field(min_length=2, max_length=30)


class IndicatorIn(BaseModel):
    active: Optional[bool] = None
    priority: Optional[int] = Field(default=None, ge=1, le=1000)
    stale_after_days: Optional[int] = Field(default=None, ge=1, le=800)
    norm: Optional[Dict[str, Any]] = None


class ConfigIn(BaseModel):
    k: Optional[float] = Field(default=None, gt=0, le=100)
    signal_scale: Optional[float] = Field(default=None, gt=0, le=100)
    min_coverage: Optional[float] = Field(default=None, ge=0, le=1)
    stale_after_hours: Optional[int] = Field(default=None, ge=1, le=720)
    bands: Optional[List[BandIn]] = None
    indicators: Optional[Dict[str, IndicatorIn]] = None
    note: str = Field(min_length=3, max_length=300)


class MappingIn(BaseModel):
    symbol: str = Field(max_length=24)
    sector: Optional[str] = Field(default=None, max_length=40)        # None: go back to the label map
    segments: Optional[List[Dict[str, Any]]] = None                    # [{"sector": code, "weight": 0.6, "name": "segment"}]
    note: str = Field(default="", max_length=300)


class LabelRuleIn(BaseModel):
    kind: Literal["sector", "industry", "symbol", "segment"]
    match: Literal["exact", "contains"] = "exact"
    pattern: str = Field(min_length=1, max_length=120)
    sector: str = Field(max_length=40)
    priority: int = Field(default=30, ge=1, le=100)
    active: bool = True
    note: str = Field(default="", max_length=200)


class ActivateIn(BaseModel):
    version: int = Field(ge=1)
    note: str = Field(min_length=3, max_length=300)


async def log_change(conn, request: Request, ctx: Ctx, action: str, entity: str, key: str, old: Any, new: Any, version: Optional[int], note: str = "") -> None:
    await conn.execute("INSERT INTO macro_audit_log (actor, action, entity, entity_key, old_value, new_value, model_version, note, ip) VALUES ($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9)",
                       ctx.email or ctx.user_id or "admin", action, entity, key, json.dumps(old, default=str), json.dumps(new, default=str), version, note, ip_of(request))


async def new_version(conn, parent: int, ctx: Ctx, note: str, k=None, scale=None, cov=None, stale=None, bands=None, indicators=None) -> int:
    """Copy a model version (configuration, indicator settings, every sensitivity) to the next number, apply the changes to the copy and make it the active one.
    The old version and every snapshot calculated with it stay exactly as they were."""
    row = await conn.fetchrow("SELECT * FROM macro_model_configuration WHERE model_version = $1", parent)
    nv = await conn.fetchval("SELECT max(model_version) + 1 FROM macro_model_configuration")
    await conn.execute("UPDATE macro_model_configuration SET active = false WHERE active")
    await conn.execute("INSERT INTO macro_model_configuration (model_version, k, signal_scale, min_coverage, stale_after_hours, bands, indicators, active, parent_version, change_note, created_by) "
                       "VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,true,$8,$9,$10)", nv, k if k is not None else row["k"], scale if scale is not None else row["signal_scale"],
                       cov if cov is not None else row["min_coverage"], stale if stale is not None else row["stale_after_hours"],
                       json.dumps(bands) if bands is not None else json.dumps(V.jd(row["bands"])), json.dumps(indicators) if indicators is not None else json.dumps(V.jd(row["indicators"])),
                       parent, note, ctx.email or ctx.user_id or "admin")
    await conn.execute("INSERT INTO sector_sensitivity (model_version, sector_id, indicator_code, coefficient, weight, critical, normalisation_method, effective_from, effective_to, active) "
                       "SELECT $1, sector_id, indicator_code, coefficient, weight, critical, normalisation_method, CURRENT_DATE, NULL, active FROM sector_sensitivity WHERE model_version = $2", nv, parent)
    return nv


async def recalc_after(request: Request, version: int, actor: str) -> Dict[str, Any]:
    store = request.app.state.store
    out = await ST.run(store, "admin", actor=actor)
    return {"calculated": out.get("calc"), "reconstructed": out.get("reconstructed")}


@admin.get("/overview")
async def a_overview(request: Request, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        cfg, meta = await ST.load_config(conn)
        health = [dict(r) for r in await conn.fetch(
            "SELECT d.indicator_code, d.name, d.group_code, d.source_name, d.frequency, d.stale_after_days, i.value, i.unit, i.observation_date, i.publication_date, i.pub_date_basis, i.status, i.detail, "
            "i.revision_number, i.retrieved_at, (SELECT count(*) FROM macro_indicator_history h WHERE h.indicator_code = d.indicator_code) AS rows, "
            "(SELECT count(*) FROM macro_indicator_history h WHERE h.indicator_code = d.indicator_code AND h.status = 'Invalid') AS invalid, "
            "(SELECT count(*) FROM macro_indicator_history h WHERE h.indicator_code = d.indicator_code AND h.revision_number > 1) AS revised "
            "FROM macro_indicator_defs d LEFT JOIN macro_indicators i ON i.indicator_code = d.indicator_code ORDER BY d.sort_order")]
        versions = [dict(r) for r in await conn.fetch("SELECT model_version, k, signal_scale, min_coverage, stale_after_hours, active, parent_version, change_note, created_by, effective_from "
                                                      "FROM macro_model_configuration ORDER BY model_version DESC")]
        runs = [dict(r) for r in await conn.fetch("SELECT id, started_at, finished_at, trigger, status, as_of, model_version, error, detail FROM macro_run_log ORDER BY id DESC LIMIT 15")]
        counts = dict(await conn.fetchrow("SELECT (SELECT count(*) FROM company_sector_mapping WHERE is_primary AND effective_to IS NULL) AS mapped, (SELECT count(*) FROM company_macro_unmapped) AS unmapped, "
                                          "(SELECT count(*) FROM sector_macro_scores) AS snapshots"))
        revised = [dict(r) for r in await conn.fetch("SELECT indicator_code, observation_date, revision_number, value, detail, retrieved_at FROM macro_indicator_history WHERE revision_number > 1 ORDER BY retrieved_at DESC LIMIT 15")]
        invalid = [dict(r) for r in await conn.fetch("SELECT indicator_code, observation_date, value, detail, retrieved_at FROM macro_indicator_history WHERE status = 'Invalid' ORDER BY retrieved_at DESC LIMIT 15")]
        info = await V.run_info(conn, cfg.version)
    return JSONResponse(json.loads(dumps({"config": {**cfg.as_json(), "indicators": meta["indicators"], "note": meta["note"]}, "health": health, "versions": versions, "runs": runs, "counts": counts,
                                          "revised": revised, "invalid": invalid, "stale": V.stale_state(info), "bands": [{"min": m, "label": l} for m, l in cfg.bands]})), headers={"Cache-Control": "no-store"})


@admin.get("/sensitivities")
async def a_sens(request: Request, version: Optional[int] = Query(None, ge=1), ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        v = version or await conn.fetchval("SELECT model_version FROM macro_model_configuration WHERE active")
        rows = await conn.fetch("SELECT s.sector_code, s.name AS sector, x.indicator_code, x.coefficient, x.weight, x.critical, x.active FROM sector_sensitivity x JOIN sector_master s ON s.id = x.sector_id "
                                "WHERE x.model_version = $1 ORDER BY s.sort_order, x.indicator_code", v)
    return JSONResponse(json.loads(dumps({"version": v, "rows": [dict(r) for r in rows]})), headers={"Cache-Control": "no-store"})


@admin.post("/sector-sensitivity")
async def a_set_sens(request: Request, body: SensitivityIn, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            cur = await conn.fetchval("SELECT model_version FROM macro_model_configuration WHERE active")
            sectors = {r["sector_code"]: r["id"] for r in await conn.fetch("SELECT id, sector_code FROM sector_master")}
            inds = {r["indicator_code"] for r in await conn.fetch("SELECT indicator_code FROM macro_indicator_defs")}
            for c in body.changes:
                if c.sector not in sectors or c.indicator not in inds:
                    raise fail(422, "unknown_name", f"Unknown sector or indicator: {c.sector} / {c.indicator}")
                if c.coefficient is not None and round(c.coefficient, 2) != c.coefficient:
                    raise fail(422, "bad_coefficient", "Coefficients have at most two decimals.")
            nv = await new_version(conn, cur, ctx, body.note)
            for c in body.changes:
                old = await conn.fetchrow("SELECT coefficient, weight, critical FROM sector_sensitivity WHERE model_version = $1 AND sector_id = $2 AND indicator_code = $3", nv, sectors[c.sector], c.indicator)
                oldv = None if old is None else {"coefficient": float(old["coefficient"]), "weight": float(old["weight"]), "critical": old["critical"]}
                if c.remove:
                    await conn.execute("DELETE FROM sector_sensitivity WHERE model_version = $1 AND sector_id = $2 AND indicator_code = $3", nv, sectors[c.sector], c.indicator)
                    newv = None
                else:
                    coef = c.coefficient if c.coefficient is not None else (oldv or {}).get("coefficient")
                    w = c.weight if c.weight is not None else (oldv or {}).get("weight", 1.0)
                    crit = c.critical if c.critical is not None else (oldv or {}).get("critical", False)
                    if coef is None:
                        raise fail(422, "coefficient_required", "A new sensitivity needs a coefficient.")
                    await conn.execute("INSERT INTO sector_sensitivity (model_version, sector_id, indicator_code, coefficient, weight, critical) VALUES ($1,$2,$3,$4,$5,$6) "
                                       "ON CONFLICT (model_version, sector_id, indicator_code) DO UPDATE SET coefficient = EXCLUDED.coefficient, weight = EXCLUDED.weight, critical = EXCLUDED.critical, active = true",
                                       nv, sectors[c.sector], c.indicator, coef, w, crit)
                    newv = {"coefficient": coef, "weight": w, "critical": crit}
                await log_change(conn, request, ctx, "sensitivity_change", "sector_sensitivity", f"{c.sector}/{c.indicator}", oldv, newv, nv, body.note)
            await log_change(conn, request, ctx, "model_version_created", "model", str(nv), {"parent": cur}, {"version": nv, "changes": len(body.changes)}, nv, body.note)
    await audit(store.pool, ctx.user_id, "macro_sensitivity_change", str(nv), ip_of(request), changes=len(body.changes))
    return {"status": "saved", "version": nv, **await recalc_after(request, nv, ctx.email or "admin")}


@admin.post("/config")
async def a_config(request: Request, body: ConfigIn, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    bands = None
    if body.bands is not None:
        bs = sorted(body.bands, key=lambda b: -b.min)
        if bs[-1].min != 0 or len({b.min for b in bs}) != len(bs) or len(bs) < 2:
            raise fail(422, "bad_bands", "Bands must have distinct lower limits and the lowest must start at 0.")
        bands = [{"min": b.min, "label": b.label} for b in bs]
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            cur_cfg, meta = await ST.load_config(conn)
            ind = None
            if body.indicators:
                ind = json.loads(json.dumps(meta["indicators"]))
                for code, ch in body.indicators.items():
                    if code not in ind:
                        raise fail(422, "unknown_indicator", f"Unknown indicator {code}")
                    for k, v in ch.model_dump(exclude_none=True).items():
                        if k == "norm":
                            for part in ("level", "momentum"):
                                m = (v.get(part) or {}).get("method")
                                if m and m not in ("threshold", "hump", "pct_vs_mean", "percentile", "zscore", "change", "pct_change", "none"):
                                    raise fail(422, "bad_method", f"Unknown normalisation method {m}")
                        ind[code][k] = v
            nv = await new_version(conn, cur_cfg.version, ctx, body.note, body.k, body.signal_scale, body.min_coverage, body.stale_after_hours, bands, ind)
            new_cfg, new_meta = await ST.load_config(conn, nv)
            old_j, new_j = cur_cfg.as_json(), new_cfg.as_json()
            for key in new_j:
                if old_j.get(key) != new_j[key]:
                    await log_change(conn, request, ctx, "config_change", "model_configuration", key, old_j.get(key), new_j[key], nv, body.note)
            if ind is not None:
                for code in body.indicators or {}:
                    await log_change(conn, request, ctx, "indicator_change", "indicator", code, meta["indicators"][code], ind[code], nv, body.note)
            await log_change(conn, request, ctx, "model_version_created", "model", str(nv), {"parent": cur_cfg.version}, {"version": nv}, nv, body.note)
    await audit(store.pool, ctx.user_id, "macro_config_change", str(nv), ip_of(request))
    return {"status": "saved", "version": nv, **await recalc_after(request, nv, ctx.email or "admin")}


@admin.post("/activate-version")
async def a_activate(request: Request, body: ActivateIn, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            cur = await conn.fetchval("SELECT model_version FROM macro_model_configuration WHERE active")
            if not await conn.fetchval("SELECT 1 FROM macro_model_configuration WHERE model_version = $1", body.version):
                raise fail(404, "unknown_version")
            await conn.execute("UPDATE macro_model_configuration SET active = false WHERE active")
            await conn.execute("UPDATE macro_model_configuration SET active = true WHERE model_version = $1", body.version)
            await log_change(conn, request, ctx, "model_version_activated", "model", str(body.version), {"active": cur}, {"active": body.version}, body.version, body.note)
    await ST.invalidate_cache(store.redis)
    return {"status": "activated", "version": body.version, **await recalc_after(request, body.version, ctx.email or "admin")}


@admin.post("/recalculate")
async def a_recalc(request: Request, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    out = await ST.run(store, "admin", actor=ctx.email or "admin")
    async with store.pool.acquire() as conn:
        await log_change(conn, request, ctx, "recalculate", "run", str(out["runId"]), None, {"status": out["status"], "calc": out.get("calc")}, None, "manual recalculation")
    return {"status": out["status"], "runId": out["runId"], "calc": out.get("calc"), "ingest": out.get("ingest"), "unusable": out.get("unusable")}


@admin.get("/mapping")
async def a_mapping(request: Request, q: str = Query("", max_length=40), unmapped: bool = False, ctx: Ctx = Depends(admin_ctx)):
    like = f"%{q.strip().lower()}%"
    async with request.app.state.store.pool.acquire() as conn:
        if unmapped:
            rows = await conn.fetch("SELECT u.symbol, c.name, NULL::text AS sector_code, NULL::text AS sector, u.reason, u.sector_label, u.industry_label FROM company_macro_unmapped u JOIN companies c ON c.symbol = u.symbol "
                                    "WHERE $1 = '%%' OR lower(c.name) LIKE $1 OR c.symbol LIKE upper($2) ORDER BY c.symbol LIMIT 60", like if q.strip() else "%%", q.strip().upper() + "%")
        else:
            rows = await conn.fetch("SELECT c.symbol, c.name, s.sector_code, s.name AS sector, m.source, m.basis_label AS reason, c.sector AS sector_label, c.industry AS industry_label, m.effective_from "
                                    "FROM companies c LEFT JOIN company_sector_mapping m ON m.symbol = c.symbol AND m.is_primary AND m.effective_to IS NULL LEFT JOIN sector_master s ON s.id = m.sector_id "
                                    "WHERE $1 = '%%' OR lower(c.name) LIKE $1 OR c.symbol LIKE upper($2) ORDER BY c.symbol LIMIT 60", like if q.strip() else "%%", q.strip().upper() + "%")
        total = await conn.fetchrow("SELECT (SELECT count(*) FROM company_sector_mapping WHERE is_primary AND effective_to IS NULL) AS mapped, (SELECT count(*) FROM company_macro_unmapped) AS unmapped")
        segs = [dict(r) for r in await conn.fetch("SELECT m.symbol, s.sector_code, m.revenue_weight, m.segment_name, m.source FROM company_sector_mapping m JOIN sector_master s ON s.id = m.sector_id "
                                                  "WHERE NOT m.is_primary AND m.effective_to IS NULL AND m.symbol = ANY($1::text[])", [r["symbol"] for r in rows])]
    return JSONResponse(json.loads(dumps({"rows": [dict(r) for r in rows], "segments": segs, "mapped": total["mapped"], "unmapped": total["unmapped"]})), headers={"Cache-Control": "no-store"})


@admin.post("/mapping")
async def a_set_mapping(request: Request, body: MappingIn, ctx: Ctx = Depends(admin_ctx)):
    store = request.app.state.store
    sym = body.symbol.strip().upper()
    if not SYMBOL.match(sym):
        raise fail(422, "bad_symbol")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            if not await conn.fetchval("SELECT 1 FROM companies WHERE symbol = $1", sym):
                raise fail(404, "unknown_company")
            ids = {r["sector_code"]: r["id"] for r in await conn.fetch("SELECT id, sector_code FROM sector_master")}
            old = [dict(r) for r in await conn.fetch("SELECT s.sector_code, m.revenue_weight, m.is_primary, m.source FROM company_sector_mapping m JOIN sector_master s ON s.id = m.sector_id "
                                                     "WHERE m.symbol = $1 AND m.effective_to IS NULL", sym)]
            if body.sector is not None and body.sector not in ids:
                raise fail(422, "unknown_sector")
            if body.segments:
                tot = sum(float(s.get("weight", 0)) for s in body.segments)
                if abs(tot - 1) > 0.001 or any(s.get("sector") not in ids or float(s.get("weight", 0)) <= 0 for s in body.segments):
                    raise fail(422, "bad_segments", "Segment weights must be positive and total 100%, each with a known sector.")
            await conn.execute("UPDATE company_sector_mapping SET effective_to = CURRENT_DATE WHERE symbol = $1 AND effective_to IS NULL", sym)
            if body.sector is not None:
                await conn.execute("INSERT INTO company_sector_mapping (symbol, sector_id, is_primary, source, basis_label, created_by) VALUES ($1,$2,true,'admin',$3,$4)",
                                   sym, ids[body.sector], body.note or "set by an administrator", ctx.email or "admin")
                await conn.execute("DELETE FROM company_macro_unmapped WHERE symbol = $1", sym)
                for s in body.segments or []:
                    await conn.execute("INSERT INTO company_sector_mapping (symbol, sector_id, revenue_weight, is_primary, segment_name, source, basis_label, created_by) VALUES ($1,$2,$3,false,$4,'admin',$5,$6)",
                                       sym, ids[s["sector"]], float(s["weight"]), str(s.get("name") or "")[:200] or None, body.note or "set by an administrator", ctx.email or "admin")
            await log_change(conn, request, ctx, "mapping_change", "company_mapping", sym, [{**o, "revenue_weight": f_(o["revenue_weight"])} for o in old],
                             {"sector": body.sector, "segments": body.segments}, None, body.note)
        if body.sector is None:
            await ST.sync_mappings(conn, ST.today_ist())
            await ST.sync_segments(conn, ST.today_ist())
    await ST.invalidate_cache(store.redis)
    return {"status": "saved", "symbol": sym}


def f_(v: Any) -> Optional[float]:
    return None if v is None else float(v)


@admin.get("/label-map")
async def a_labels(request: Request, kind: str = Query("", max_length=10), ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, label_kind, match_type, pattern, sector_code, priority, note, active FROM macro_label_map WHERE $1 = '' OR label_kind = $1 ORDER BY label_kind, sector_code, pattern", kind)
    return JSONResponse(json.loads(dumps({"rows": [dict(r) for r in rows]})), headers={"Cache-Control": "no-store"})


@admin.post("/label-map")
async def a_set_label(request: Request, body: LabelRuleIn, ctx: Ctx = Depends(admin_ctx)):
    from ..presets.industry import key as label_key
    store = request.app.state.store
    pattern = body.pattern.strip().upper() if body.kind == "symbol" else label_key(body.pattern)
    if not pattern:
        raise fail(422, "bad_pattern")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            if not await conn.fetchval("SELECT 1 FROM sector_master WHERE sector_code = $1", body.sector):
                raise fail(422, "unknown_sector")
            old = await conn.fetchrow("SELECT sector_code, priority, active, note FROM macro_label_map WHERE label_kind = $1 AND match_type = $2 AND pattern = $3", body.kind, body.match, pattern)
            await conn.execute("INSERT INTO macro_label_map (label_kind, match_type, pattern, sector_code, priority, note, active) VALUES ($1,$2,$3,$4,$5,$6,$7) "
                               "ON CONFLICT (label_kind, match_type, pattern) DO UPDATE SET sector_code = EXCLUDED.sector_code, priority = EXCLUDED.priority, note = EXCLUDED.note, active = EXCLUDED.active",
                               body.kind, body.match, pattern, body.sector, body.priority, body.note, body.active)
            await log_change(conn, request, ctx, "label_rule_change", "label_map", f"{body.kind}/{body.match}/{pattern}", dict(old) if old else None,
                             {"sector": body.sector, "priority": body.priority, "active": body.active}, None, body.note)
        res = await ST.sync_mappings(conn, ST.today_ist())
    await ST.invalidate_cache(store.redis)
    return {"status": "saved", "pattern": pattern, **res}


@admin.get("/contributions")
async def a_contrib(request: Request, sector: str = Query(..., max_length=40), snapshot: Optional[int] = Query(None, ge=1), ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        if snapshot is None:
            snapshot = await conn.fetchval("SELECT s.id FROM sector_macro_scores s JOIN sector_master m ON m.id = s.sector_id WHERE m.sector_code = $1 ORDER BY s.snapshot_date DESC, s.id DESC LIMIT 1", sector)
        snap = await conn.fetchrow("SELECT s.*, m.sector_code, m.name AS sector_name FROM sector_macro_scores s JOIN sector_master m ON m.id = s.sector_id WHERE s.id = $1", snapshot)
        if snap is None:
            raise fail(404, "no_snapshot")
        rows = await conn.fetch("SELECT * FROM sector_macro_contributions WHERE score_id = $1 ORDER BY abs(coalesce(contribution, 0)) DESC, indicator_code", snapshot)
        recent = await conn.fetch("SELECT id, snapshot_date, basis, status, score, model_version FROM sector_macro_scores WHERE sector_id = $1 ORDER BY snapshot_date DESC, id DESC LIMIT 30", snap["sector_id"])
    return JSONResponse(json.loads(dumps({"snapshot": V.snapshot_view(dict(snap)), "contributions": [dict(r) for r in rows], "recent": [dict(r) for r in recent]})), headers={"Cache-Control": "no-store"})


@admin.get("/audit")
async def a_audit(request: Request, limit: int = Query(100, ge=1, le=500), ctx: Ctx = Depends(admin_ctx)):
    async with request.app.state.store.pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, at, actor, action, entity, entity_key, old_value, new_value, model_version, note FROM macro_audit_log ORDER BY id DESC LIMIT $1", limit)
    return JSONResponse(json.loads(dumps({"events": [{**dict(r), "old_value": V.jd(r["old_value"]), "new_value": V.jd(r["new_value"])} for r in rows]})), headers={"Cache-Control": "no-store"})
