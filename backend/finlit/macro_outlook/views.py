"""The payloads the website reads: every one is built from STORED snapshots (never from an external source) and cached in Redis."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import engine as E
from . import seed as SEED
from .store import CACHE_PREFIX, BASIS_TEXT, f, iso, jd, load_config

DISCLAIMER = ("The Macro & Sector Outlook is an informational model of sector-level macroeconomic conditions. It is not a company-specific assessment, forecast, "
              "or investment recommendation.")
MODEL_NOTE = SEED.MODEL_NOTE
PERIODS = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "ALL": None}
TTL = 900
LATEST_SQL = ("SELECT DISTINCT ON (s.sector_id) s.*, m.sector_code, m.name AS sector_name FROM sector_macro_scores s JOIN sector_master m ON m.id = s.sector_id "
              "WHERE s.model_version = $1 {extra} ORDER BY s.sector_id, s.snapshot_date DESC, (s.basis = 'live') DESC, s.id DESC")


async def cached(redis, key: str, build, ttl: int = TTL):
    try:
        hit = await redis.get(CACHE_PREFIX + key)
        if hit:
            return json.loads(hit)
    except Exception:   # nosec B110 - Redis down: rebuild from Postgres
        pass
    value = await build()
    if value is not None:
        try:
            await redis.set(CACHE_PREFIX + key, json.dumps(value, default=str), ex=ttl)
        except Exception:   # nosec B110
            pass
    return value


def snapshot_view(r: Dict[str, Any]) -> Dict[str, Any]:
    ok = r["status"] == "ok"
    cfgj = jd(r["config"]) or {}
    return {"sector": {"code": r["sector_code"], "name": r["sector_name"]}, "status": r["status"], "score": f(r["score"]), "label": r["label"], "tone": E.tone_of(r["label"]),
            "weightedSignal": f(r["weighted_signal"]), "coverage": f(r["coverage"]), "minCoverage": f(r["min_coverage"]), "snapshotDate": iso(r["snapshot_date"]),
            "asOf": iso(r["as_of"]), "modelVersion": r["model_version"], "basis": r["basis"], "snapshotId": r["id"], "drivers": jd(r["top_drivers"]) or [],
            "missing": jd(r["missing"]) or [], "criticalMissing": jd(r["critical_missing"]) or [], "reason": None if ok else (cfgj.get("reason") or "Insufficient Data"),
            "explanation": jd(r["explanation"]) or {}, "config": cfgj}


async def impact(conn, version: int) -> Dict[str, Any]:
    rows = await conn.fetch(LATEST_SQL.format(extra=""), version)
    sectors = [snapshot_view(dict(r)) for r in rows]
    sectors.sort(key=lambda s: (s["score"] is None, -(s["score"] or 0), s["sector"]["name"]))
    asof = max((s["snapshotDate"] for s in sectors), default=None)
    return {"modelVersion": version, "asOf": asof, "count": len(sectors), "sectors": sectors, "disclaimer": DISCLAIMER}


def _change(cur: Optional[float], prev: Optional[float]) -> Tuple[Optional[float], str]:
    if cur is None or prev is None:
        return None, "none"
    d = round(cur - prev, 6)
    return d, "up" if d > 1e-9 else "down" if d < -1e-9 else "flat"


async def indicators(conn, version: int) -> Dict[str, Any]:
    cfg, meta = await load_config(conn, version)
    defs = {r["indicator_code"]: dict(r) for r in await conn.fetch("SELECT * FROM macro_indicator_defs ORDER BY sort_order")}
    cur = {r["indicator_code"]: dict(r) for r in await conn.fetch("SELECT * FROM macro_indicators")}
    sig = {r["indicator_code"]: dict(r) for r in await conn.fetch(
        "SELECT DISTINCT ON (indicator_code) * FROM macro_indicator_signals WHERE model_version = $1 ORDER BY indicator_code, calculation_date DESC", version)}
    out = []
    for code, d in defs.items():
        st = meta["indicators"].get(code) or {}
        if not st.get("active", True):
            continue
        c, s = cur.get(code), sig.get(code)
        value, prev = (f(c["value"]) if c else None), (f(c["prev_value"]) if c else None)
        ch, direction = _change(value, prev)
        status = c["status"] if c else "Missing"
        out.append({"code": code, "name": d["name"], "group": d["group_code"], "unit": d["unit"], "frequency": d["frequency"], "value": value, "valueText": E.value_text(value, d["unit"]) if value is not None else None,
                    "prevValue": prev, "prevText": E.value_text(prev, d["unit"]) if prev is not None else None, "prevDate": iso(c["prev_observation_date"]) if c else None,
                    "change": ch, "direction": direction, "signal": f(s["final_signal"]) if s and status in ("Available", "Revised") else None,
                    "level": f(s["level_signal"]) if s else None, "momentum": f(s["momentum_signal"]) if s else None, "observationDate": iso(c["observation_date"]) if c else None,
                    "publicationDate": iso(c["publication_date"]) if c else None, "dateBasis": BASIS_TEXT.get(c["pub_date_basis"] or "", "") if c else "",
                    "source": d["source_name"], "sourceUrl": d["source_url"], "status": status, "detail": c["detail"] if c else "no data", "note": d["reading_note"]})
    return {"modelVersion": version, "groups": [{"code": c, "name": n} for c, n in SEED.GROUPS], "indicators": out,
            "signalNote": "A positive signal means the indicator is high or rising against its reference; a negative one low or falling. Each sector's sensitivity says whether that helps or weighs on it."}


async def sector_detail(conn, code: str, version: int) -> Optional[Dict[str, Any]]:
    r = await conn.fetchrow(LATEST_SQL.format(extra="AND m.sector_code = $2"), version, code)
    if r is None:
        return None
    v = snapshot_view(dict(r))
    cons = await conn.fetch("SELECT c.*, d.name, d.group_code FROM sector_macro_contributions c JOIN macro_indicator_defs d ON d.indicator_code = c.indicator_code WHERE c.score_id = $1 "
                            "ORDER BY abs(coalesce(c.contribution, 0)) DESC, c.indicator_code", r["id"])
    v["contributions"] = [{"code": c["indicator_code"], "name": c["name"], "group": c["group_code"], "value": f(c["value"]), "unit": c["unit"],
                           "valueText": E.value_text(f(c["value"]), c["unit"] or "") if c["value"] is not None else None, "observationDate": iso(c["observation_date"]),
                           "publicationDate": iso(c["publication_date"]), "dateBasis": BASIS_TEXT.get(c["pub_date_basis"] or "", ""), "status": c["status"], "level": f(c["level_signal"]),
                           "momentum": f(c["momentum_signal"]), "signal": f(c["signal"]), "coefficient": f(c["coefficient"]), "weight": f(c["weight"]), "contribution": f(c["contribution"]),
                           "direction": c["direction"], "critical": c["critical"], "counted": c["counted"], "reason": c["reason"]} for c in cons]
    v["deltas"] = await deltas(conn, r["sector_id"], version, r["snapshot_date"], f(r["score"]))
    return v


async def history_rows(conn, sector_id: int, version: int) -> List[Dict[str, Any]]:
    rows = await conn.fetch("SELECT DISTINCT ON (snapshot_date) snapshot_date, score, label, status, basis, model_version FROM sector_macro_scores WHERE sector_id = $1 AND model_version = $2 "
                            "ORDER BY snapshot_date, (basis = 'live') DESC, id DESC", sector_id, version)
    return [{"date": r["snapshot_date"], "score": f(r["score"]), "label": r["label"], "status": r["status"], "basis": r["basis"]} for r in rows]


async def deltas(conn, sector_id: int, version: int, latest: date, score: Optional[float]) -> Dict[str, Any]:
    rows = [r for r in await history_rows(conn, sector_id, version) if r["score"] is not None and r["date"] < latest]
    out: Dict[str, Any] = {}
    for name, days in (("1M", 30), ("3M", 91), ("6M", 182), ("1Y", 365)):
        want = latest - timedelta(days=days)
        prior = [r for r in rows if r["date"] <= want]
        # only a snapshot within 20 days of the wanted date counts as "then"
        pick = prior[-1] if prior and (want - prior[-1]["date"]).days <= 20 else None
        out[name] = None if pick is None or score is None else {"score": pick["score"], "change": round(score - pick["score"], 2), "date": pick["date"].isoformat()}
    return out


async def history(conn, code: str, period: str, version: int) -> Optional[Dict[str, Any]]:
    sec = await conn.fetchrow("SELECT id, name FROM sector_master WHERE sector_code = $1", code)
    if sec is None:
        return None
    rows = await history_rows(conn, sec["id"], version)
    days = PERIODS[period]
    if days and rows:
        cut = rows[-1]["date"] - timedelta(days=days)
        rows = [r for r in rows if r["date"] >= cut]
    return {"sector": {"code": code, "name": sec["name"]}, "period": period, "modelVersion": version, "midpoint": 50,
            "points": [{"date": r["date"].isoformat(), "score": r["score"], "label": r["label"], "status": r["status"], "basis": r["basis"]} for r in rows],
            "note": "Points marked reconstructed were calculated afterwards from stored observations; where a publication date was not recorded the observation date was used, so they may "
                    "include figures a few days before their release. Snapshots are never overwritten."}


async def methodology(conn, version: int) -> Dict[str, Any]:
    cfg, meta = await load_config(conn, version)
    defs = await conn.fetch("SELECT * FROM macro_indicator_defs ORDER BY sort_order")
    n = await conn.fetchval("SELECT count(*) FROM sector_master WHERE active")
    return {
        "modelVersion": cfg.version, "effectiveFrom": iso(meta["effectiveFrom"]), "assumptionsNote": MODEL_NOTE, "disclaimer": DISCLAIMER,
        "scoreMeaning": "A sector-level score from 0 to 100. 50 is neutral: the macro indicators in the model, weighted for this sector, net out. Above 50 the current readings tend to support the sector; below 50 they tend to weigh on it. It describes the sector's macroeconomic backdrop, not a company, and it is separate from the Fundamental and Technical scores.",
        "bands": [{"min": m, "label": l} for m, l in cfg.bands],
        "indicators": [{"code": d["indicator_code"], "name": d["name"], "group": d["group_code"], "unit": d["unit"], "frequency": d["frequency"], "source": d["source_name"], "sourceUrl": d["source_url"],
                        "note": d["reading_note"], "normalisation": jd(meta["indicators"].get(d["indicator_code"], {}).get("norm") or d["norm"]), "active": meta["indicators"].get(d["indicator_code"], {}).get("active", True)}
                       for d in defs],
        "normalisation": "Each indicator becomes a signal between -1 and +1: Indicator Signal = (Level Signal + Momentum Signal) / 2, each capped at +-1. The level compares the latest reading with a reference or its own recent history; the momentum compares it with the reading about a quarter earlier. If no earlier reading exists, the level alone is used and the page says so.",
        "sensitivities": f"Each of the {n} sectors has a coefficient from -1.00 to +1.00 per relevant indicator (direction and strength), a weight, and critical flags. These are model assumptions: they are not proof of cause and have not been validated or backtested.",
        "formula": ["Contribution = Indicator Signal x Sensitivity x Weight",
                    "Weighted Signal = Signal Scale x sum of Contributions of valid indicators / sum of Weights of valid indicators",
                    f"Macro Score = 50 + 50 x tanh(Weighted Signal / K), with K = {cfg.k:g} and Signal Scale = {cfg.signal_scale:g} in this version",
                    f"Coverage = valid weight / total weight. Below {cfg.min_coverage * 100:.0f}%, or with a critical indicator missing, the answer is Insufficient Data: no score is shown, and nothing is filled with zero or neutral."],
        "drivers": "The two largest absolute contributions. Ties are broken by the configured indicator priority, then the fresher observation.",
        "sources": "Official statistics (MoSPI, RBI, FBIL) and commodity price vendors, stored centrally. The company page reads only stored results and never calls a source.",
        "updates": "Recalculated every evening after the macro, flows and commodity jobs, and again when a new observation arrives. The date shown is the date of the snapshot.",
        "limitations": ["Sensitivities and thresholds are initial assumptions that have not been validated or backtested.",
                        "Publication dates are the observation date where the release date was not recorded, so reconstructed history can include figures slightly before their release.",
                        "Global demand, sector-specific prices (steel, coal, cotton, passenger traffic) and asset quality are not in the model yet.",
                        "A sector score is the same for every company in the sector; a diversified company is weighted by reported segment revenue only where that data is reliable.",
                        "Stale or missing indicators are excluded, so a score can rest on fewer inputs; the coverage figure says how many."],
    }


async def run_info(conn, version: int) -> Dict[str, Any]:
    last = await conn.fetchrow("SELECT status, finished_at, started_at, error FROM macro_run_log WHERE status <> 'running' ORDER BY id DESC LIMIT 1")
    ok = await conn.fetchval("SELECT max(finished_at) FROM macro_run_log WHERE status IN ('ok','partial')")
    cfg, _ = await load_config(conn, version)
    return {"lastOk": iso(ok), "lastStatus": last["status"] if last else None, "lastFinished": iso(last["finished_at"]) if last else None, "staleAfterHours": cfg.stale_after_hours}


def stale_state(info: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """A snapshot is current only while the engine has refreshed recently and the latest refresh did not fail. Otherwise the last snapshot is served with this warning."""
    now = now or datetime.now(timezone.utc)
    if not info.get("lastOk"):
        return {"isStale": True, "since": None, "message": "The macro engine has not completed a refresh yet.", "reason": "never_ran"}
    last_ok = datetime.fromisoformat(info["lastOk"])
    hours = (now - last_ok).total_seconds() / 3600
    if info.get("lastStatus") == "failed":
        return {"isStale": True, "since": info["lastOk"], "message": f"The latest refresh failed. Showing the last successful snapshot from {last_ok.date().isoformat()}.", "reason": "refresh_failed"}
    if hours > info.get("staleAfterHours", 48):
        return {"isStale": True, "since": info["lastOk"], "message": f"Not refreshed for {int(hours)} hours. Showing the last successful snapshot from {last_ok.date().isoformat()}.", "reason": "overdue"}
    return {"isStale": False, "since": None, "message": None, "reason": None}
