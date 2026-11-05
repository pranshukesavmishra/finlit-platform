"""Database side of the Macro & Sector Outlook: reading the stored macro series as observations with provenance, the nightly calculation, immutable
snapshots, company mapping, and the cached payloads the website reads. Nothing here (or anywhere on the company-page path) calls an external source."""
from __future__ import annotations

import email.utils
import json
import logging
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .. import macro as M
from .. import macro_sources as S
from ..presets.industry import key as label_key
from . import engine as E
from . import seed as SEED

log = logging.getLogger("finlit.macro_outlook")
IST = timezone(timedelta(hours=5, minutes=30))
COMMODITY_CODES = {"brent": "BRENT", "copper": "COPPER", "aluminium": "ALUMINIUM", "natgas": "NATGAS"}
ASSUMED, FIRST_SEEN, SAME_DAY, ANNOUNCED, SOURCE = "assumed_observation_date", "first_seen", "same_day", "derived_from_announcements", "source_publication_date"
BASIS_TEXT = {ASSUMED: "publication date not recorded: observation date used", FIRST_SEEN: "date first retrieved by FinLit", SAME_DAY: "published the same day",
              ANNOUNCED: "derived from dated RBI announcements", SOURCE: "publication date from the source"}
CACHE_PREFIX = "macro:outlook:"


def today_ist() -> date:
    return datetime.now(IST).date()


def f(v: Any) -> Optional[float]:
    return None if v is None else float(v)


def jd(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def iso(d: Any) -> Optional[str]:
    return d.isoformat() if d is not None else None


# ------------------------------------------------------------------------------------------------------------ the model configuration
async def load_config(conn, version: Optional[int] = None) -> Tuple[E.ModelConfig, Dict[str, Any]]:
    row = await (conn.fetchrow("SELECT * FROM macro_model_configuration WHERE model_version = $1", version) if version else
                 conn.fetchrow("SELECT * FROM macro_model_configuration WHERE active"))
    if row is None:
        raise LookupError("no macro model configuration")
    bands = tuple((float(b["min"]), b["label"]) for b in sorted(jd(row["bands"]), key=lambda b: -b["min"]))
    cfg = E.ModelConfig(row["model_version"], float(row["k"]), float(row["signal_scale"]), float(row["min_coverage"]), bands, row["stale_after_hours"])
    return cfg, {"indicators": jd(row["indicators"]), "active": row["active"], "note": row["change_note"], "createdBy": row["created_by"], "effectiveFrom": row["effective_from"],
                 "parent": row["parent_version"]}


async def load_defs(conn) -> Dict[str, Dict[str, Any]]:
    return {r["indicator_code"]: dict(r) for r in await conn.fetch("SELECT * FROM macro_indicator_defs ORDER BY sort_order")}


async def load_rules(conn, version: int, as_of: date) -> Dict[str, List[E.Rule]]:
    rows = await conn.fetch("SELECT s.sector_code, x.indicator_code, x.coefficient, x.weight, x.critical, x.normalisation_method FROM sector_sensitivity x JOIN sector_master s ON s.id = x.sector_id "
                            "WHERE x.model_version = $1 AND x.active AND (x.effective_to IS NULL OR x.effective_to >= $2) ORDER BY s.sort_order, x.indicator_code", version, as_of)
    out: Dict[str, List[E.Rule]] = {}
    for r in rows:
        out.setdefault(r["sector_code"], []).append(E.Rule(r["indicator_code"], float(r["coefficient"]), float(r["weight"]), r["critical"], r["normalisation_method"] or ""))
    return out


# ------------------------------------------------------------------------------------------------------------ reading what the platform already collects
class Collected:
    """code -> {observation date: (value, basis kind, publication date or None)}, plus a reason for each code that has nothing."""

    def __init__(self) -> None:
        self.points: Dict[str, Dict[date, Tuple[float, str, Optional[date]]]] = {}
        self.why_missing: Dict[str, str] = {}

    def put(self, code: str, pts: Dict[date, float], kind: str, kinds: Optional[Dict[date, str]] = None, pub: Optional[Dict[date, date]] = None) -> None:
        if pts:
            self.points[code] = {d: (float(v), (kinds or {}).get(d, kind), (pub or {}).get(d)) for d, v in pts.items()}


def _parse_pub(text: Any) -> Optional[date]:
    if not text:
        return None
    t = str(text).strip()
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        pass
    try:
        return email.utils.parsedate_to_datetime(t).date()
    except (TypeError, ValueError):
        return None


async def collect(conn, today: date) -> Collected:
    raw = await M.load_points(conn)
    live = await M.get_meta(conn, "repo_live") or {"decisions": []}
    decisions = M.load_decisions() + [S.Decision(date.fromisoformat(x["date"]), x["rate"], x["bp"], x["source"]) for x in live["decisions"]]
    series, _b, _n = M.derive(raw, decisions, today)
    labels = await M.get_meta(conn, "cpi_labels") or {}
    out = Collected()
    out.put("CPI", series.get("cpi", {}), ASSUMED)
    food = next((k for k, l in labels.items() if re.match(r"food", str(l), re.I)), None)
    out.put("FOOD_CPI", series.get(food, {}) if food else {}, ASSUMED)
    out.put("WPI", series.get("wpi", {}), ASSUMED)
    repo = series.get("repo", {})
    out.put("REPO_RATE", repo, ANNOUNCED)
    act: Dict[date, float] = {}
    for d, v in repo.items():
        old = repo.get(S.month_end(d.year - 1, d.month))
        if old is not None:
            act[d] = round((v - old) * 100, 2)
    out.put("REPO_ACTION", act, ANNOUNCED)
    wss = await M.get_meta(conn, "rbi_wss") or {}
    pub = _parse_pub(wss.get("published"))
    for code, key in (("BANK_CREDIT", "credit_yoy"), ("DEPOSIT_GROWTH", "deposits_yoy")):
        pts = series.get(key, {})
        known = {}
        if pts and wss.get("banksAsOf") and pub:
            d0 = date.fromisoformat(wss["banksAsOf"])
            if d0 in pts and pub >= d0:
                known = {d0: pub}
        out.put(code, pts, ASSUMED, kinds={d: SOURCE for d in known}, pub=known)
    for code, key in (("GDP", "gdp"), ("IIP", "iip"), ("IIP_CAPITAL", "iip_capital"), ("IIP_INFRA", "iip_infra"), ("IIP_DURABLES", "iip_durables"),
                      ("IIP_NONDURABLES", "iip_nondurables"), ("UNEMPLOYMENT", "unemployment")):
        out.put(code, series.get(key, {}), ASSUMED)
    daily = set(raw.get("usdinr_d", {}))
    out.put("USDINR", series.get("usdinr", {}), ASSUMED, kinds={d: SAME_DAY for d in daily})
    rows = await conn.fetch("SELECT day, symbol, value FROM commodity_snapshots WHERE kind = 'intl_usd' AND symbol = ANY($1::text[]) ORDER BY day", list(COMMODITY_CODES))
    by: Dict[str, Dict[date, float]] = {}
    for r in rows:
        by.setdefault(COMMODITY_CODES[r["symbol"]], {})[r["day"]] = float(r["value"])
    for code, pts in by.items():
        out.put(code, pts, SAME_DAY)
    for code in COMMODITY_CODES.values():
        if code not in out.points:
            out.why_missing[code] = "no price history stored: the commodity worker has no vendor key on the server (METALS_DEV_API_KEY / METALPRICE_API_KEY)"
    for d in SEED.INDICATORS:
        out.why_missing.setdefault(d[0], "the stored macro series for it is empty (the macro job has not loaded it yet)")
    return out


async def ingest(conn, today: date, col: Collected, defs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """Persist observations with provenance, record a revision when a stored observation changes, refresh the current-reading table."""
    summary: Dict[str, Any] = {"new": 0, "revised": 0, "invalid": 0}
    now = datetime.now(timezone.utc)
    for code, d in defs.items():
        pts = col.points.get(code, {})
        existing: Dict[date, Tuple[int, float, str]] = {}
        for r in await conn.fetch("SELECT DISTINCT ON (observation_date) observation_date, revision_number, value, status FROM macro_indicator_history WHERE indicator_code = $1 "
                                  "ORDER BY observation_date, revision_number DESC", code):
            existing[r["observation_date"]] = (r["revision_number"], float(r["value"]), r["status"])
        has_history = bool(existing)
        lo, hi = f(d["valid_min"]), f(d["valid_max"])
        rows = []
        for od, (v, kind, pubd) in sorted(pts.items()):
            v6 = round(v, 6)
            bad = od > today + timedelta(days=1) or (lo is not None and v < lo) or (hi is not None and v > hi)
            cur = existing.get(od)
            if cur is not None and (round(cur[1], 6) == v6) and (cur[2] == "Invalid") == bad:
                continue
            if bad:
                if cur is None or cur[2] != "Invalid":
                    rows.append((code, od, od, kind if kind != ASSUMED else ASSUMED, v6, d["unit"], (cur[0] + 1) if cur else 1, "Invalid", d["source_name"], d["source_url"], d["frequency"],
                                 f"out of the plausible range {lo}..{hi} or dated in the future", now))
                    summary["invalid"] += 1
                continue
            if cur is None:
                if kind == ASSUMED:
                    pd_, basis = (today, FIRST_SEEN) if has_history else (od, ASSUMED)
                elif kind == SOURCE and pubd:
                    pd_, basis = pubd, SOURCE
                else:
                    pd_, basis = od, kind
                rows.append((code, od, pd_, basis, v6, d["unit"], 1, "Available", d["source_name"], d["source_url"], d["frequency"], None, now))
                summary["new"] += 1
            else:
                rows.append((code, od, today, FIRST_SEEN, v6, d["unit"], cur[0] + 1, "Revised", d["source_name"], d["source_url"], d["frequency"], f"was {cur[1]:g}", now))
                summary["revised"] += 1
        if rows:
            await conn.executemany("INSERT INTO macro_indicator_history (indicator_code, observation_date, publication_date, pub_date_basis, value, unit, revision_number, status, source, source_url, "
                                   "frequency, detail, retrieved_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13) ON CONFLICT DO NOTHING", rows)
        await refresh_current(conn, code, d, today, col.why_missing.get(code, ""))
    return summary


async def refresh_current(conn, code: str, d: Dict[str, Any], today: date, why: str) -> None:
    rows = await conn.fetch("SELECT DISTINCT ON (observation_date) * FROM macro_indicator_history WHERE indicator_code = $1 AND status <> 'Invalid' ORDER BY observation_date DESC, revision_number DESC LIMIT 2", code)
    bad = await conn.fetchval("SELECT count(*) FROM macro_indicator_history WHERE indicator_code = $1 AND status = 'Invalid' AND observation_date > $2", code, today - timedelta(days=366))
    if not rows:
        await conn.execute("INSERT INTO macro_indicators (indicator_code, unit, source, source_url, frequency, status, detail, retrieved_at) VALUES ($1,$2,$3,$4,$5,'Missing',$6, now()) "
                           "ON CONFLICT (indicator_code) DO UPDATE SET value = NULL, observation_date = NULL, publication_date = NULL, pub_date_basis = NULL, prev_value = NULL, "
                           "prev_observation_date = NULL, status = 'Missing', detail = EXCLUDED.detail, retrieved_at = now()", code, d["unit"], d["source_name"], d["source_url"], d["frequency"], why or "no data")
        return
    cur, prev = rows[0], (rows[1] if len(rows) > 1 else None)
    age = (today - cur["observation_date"]).days
    status = "Stale" if age > d["stale_after_days"] else ("Revised" if cur["revision_number"] > 1 else "Available")
    detail = f"{age} days since the observation date" + ("; some recent readings were rejected as invalid" if bad else "")
    await conn.execute(
        "INSERT INTO macro_indicators (indicator_code, value, unit, observation_date, publication_date, pub_date_basis, source, source_url, frequency, status, detail, prev_value, prev_observation_date, "
        "revision_number, retrieved_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14, now()) ON CONFLICT (indicator_code) DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit, "
        "observation_date = EXCLUDED.observation_date, publication_date = EXCLUDED.publication_date, pub_date_basis = EXCLUDED.pub_date_basis, source = EXCLUDED.source, source_url = EXCLUDED.source_url, "
        "frequency = EXCLUDED.frequency, status = EXCLUDED.status, detail = EXCLUDED.detail, prev_value = EXCLUDED.prev_value, prev_observation_date = EXCLUDED.prev_observation_date, "
        "revision_number = EXCLUDED.revision_number, retrieved_at = now()",
        code, cur["value"], d["unit"], cur["observation_date"], cur["publication_date"], cur["pub_date_basis"], d["source_name"], d["source_url"], d["frequency"], status, detail,
        prev["value"] if prev else None, prev["observation_date"] if prev else None, cur["revision_number"])


async def load_history(conn) -> Dict[str, List[E.Obs]]:
    out: Dict[str, List[E.Obs]] = {}
    for r in await conn.fetch("SELECT indicator_code, observation_date, publication_date, value, revision_number, status, pub_date_basis FROM macro_indicator_history ORDER BY indicator_code, observation_date"):
        out.setdefault(r["indicator_code"], []).append(E.Obs(r["observation_date"], r["publication_date"], float(r["value"]), r["revision_number"], r["status"], r["pub_date_basis"]))
    return out


# ------------------------------------------------------------------------------------------------------------ the calculation
def indicator_results(history: Dict[str, List[E.Obs]], defs: Dict[str, Dict[str, Any]], settings: Dict[str, Any], as_of: date) -> Dict[str, E.IndicatorResult]:
    out: Dict[str, E.IndicatorResult] = {}
    for code, d in defs.items():
        st = settings.get(code) or {}
        if not st.get("active", True):
            continue
        out[code] = E.indicator_result(code, d["name"], d["unit"], st.get("norm") or d["norm"] and jd(d["norm"]) or {}, int(st.get("stale_after_days", d["stale_after_days"])),
                                       E.known_series(history.get(code, []), as_of), as_of)
    return out


def _jsonable(o: Any) -> Any:
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(type(o).__name__)


async def calculate(conn, as_of: date, version: Optional[int] = None, basis: str = "live", history: Optional[Dict[str, List[E.Obs]]] = None) -> Dict[str, Any]:
    """Score every active sector as of `as_of` with one model version and store immutable snapshots. Re-running with identical inputs stores nothing new."""
    cfg, meta = await load_config(conn, version)
    defs = await load_defs(conn)
    history = history if history is not None else await load_history(conn)
    results = indicator_results(history, defs, meta["indicators"], as_of)
    rules = await load_rules(conn, cfg.version, as_of)
    prio = {c: int(meta["indicators"].get(c, {}).get("priority", 100)) for c in defs}
    names = {c: d["name"] for c, d in defs.items()}
    sectors = await conn.fetch("SELECT id, sector_code, name FROM sector_master WHERE active ORDER BY sort_order")
    stamp = datetime.now(timezone.utc) if basis == "live" else datetime(as_of.year, as_of.month, as_of.day, 23, 59, 59, tzinfo=IST)
    created, insufficient, ok = 0, 0, 0
    for res in results.values():
        await conn.execute(
            "INSERT INTO macro_indicator_signals (indicator_code, model_version, calculation_date, observation_date, value, level_signal, momentum_signal, final_signal, status, coverage) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) ON CONFLICT (indicator_code, model_version, calculation_date) DO UPDATE SET observation_date = EXCLUDED.observation_date, value = EXCLUDED.value, "
            "level_signal = EXCLUDED.level_signal, momentum_signal = EXCLUDED.momentum_signal, final_signal = EXCLUDED.final_signal, status = EXCLUDED.status, coverage = EXCLUDED.coverage, calculated_at = now()",
            res.code, cfg.version, as_of, res.observation_date, res.value, res.level, res.momentum, res.signal, res.status,
            None if res.signal is None else (1.0 if res.level is not None and res.momentum is not None else 0.5))
    for s in sectors:
        sr = rules.get(s["sector_code"], [])
        if not sr:
            continue
        sc = E.score_sector(s["sector_code"], sr, results, cfg, prio)
        expl = E.explain(sc.label, s["name"], sc.contributions, sr, names) if sc.status == "ok" else \
            {"headline": f"{s['name']}: Insufficient Data. {sc.reason}.", "supporting": [], "adverse": [], "monitor": [{"code": m, "name": names.get(m, m), "why": "no usable reading", "critical": m in sc.critical_missing} for m in sc.missing][:3]}
        drivers = [{"code": c.indicator, "name": c.name, "contribution": c.contribution, "sign": "+" if (c.contribution or 0) > 0 else "-", "value": c.value, "unit": c.unit,
                    "valueText": E.value_text(c.value, c.unit)} for c in sc.drivers]
        async with conn.transaction():
            sid = await conn.fetchval(
                "INSERT INTO sector_macro_scores (sector_id, model_version, snapshot_date, as_of, basis, status, score, label, weighted_signal, coverage, min_coverage, critical_missing, missing, "
                "top_drivers, explanation, config, inputs_hash) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb,$13::jsonb,$14::jsonb,$15::jsonb,$16::jsonb,$17) "
                "ON CONFLICT (sector_id, model_version, basis, snapshot_date, inputs_hash) DO NOTHING RETURNING id",
                s["id"], cfg.version, as_of, stamp, basis, sc.status, sc.score, sc.label, sc.weighted_signal, sc.coverage, sc.min_coverage, json.dumps(sc.critical_missing),
                json.dumps(sc.missing), json.dumps(drivers), json.dumps(expl), json.dumps({**cfg.as_json(), "reason": sc.reason}), sc.inputs_hash)
            if sid is None:
                continue
            created += 1
            insufficient += sc.status != "ok"
            ok += sc.status == "ok"
            await conn.executemany(
                "INSERT INTO sector_macro_contributions (score_id, indicator_code, value, unit, observation_date, publication_date, pub_date_basis, status, level_signal, momentum_signal, signal, "
                "coefficient, weight, contribution, direction, critical, counted, reason) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)",
                [(sid, c.indicator, c.value, c.unit, c.observation_date, c.publication_date, c.pub_basis or None, c.status, c.level, c.momentum, c.signal, c.coefficient, c.weight,
                  c.contribution, c.direction, c.critical, c.counted, c.reason or None) for c in sc.contributions])
    return {"asOf": as_of.isoformat(), "version": cfg.version, "basis": basis, "created": created, "ok": ok, "insufficient": insufficient, "sectors": len(sectors)}


def month_ends(today: date, months: int) -> List[date]:
    out, y, m = [], today.year, today.month
    for _ in range(months):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(S.month_end(y, m))
    return sorted(out)


async def reconstruct(conn, today: date, version: int, months: int = 24) -> int:
    """Month-end snapshots for the past, from the stored observations as they were published by then. Publication dates not recorded are the observation
    dates (labelled), so these snapshots are marked 'reconstructed' and the website says so."""
    if await conn.fetchval("SELECT count(*) FROM sector_macro_scores WHERE model_version = $1 AND basis = 'reconstructed'", version):
        return 0
    history = await load_history(conn)
    n = 0
    for d in month_ends(today, months):
        n += (await calculate(conn, d, version, "reconstructed", history))["created"]
    return n


# ------------------------------------------------------------------------------------------------------------ company to sector
def resolve(rules: List[Dict[str, Any]], symbol: str, sector_label: Optional[str], industry_label: Optional[str]) -> Optional[Tuple[str, str]]:
    """(macro sector, the rule that decided it) from the reviewable label map: named symbol first, then an exact Sector label, an exact Industry label,
    then wording rules on the Sector label and on the Industry label. None when no rule matches."""
    sk, ik = label_key(sector_label), label_key(industry_label)
    tiers = [("symbol", "exact", symbol.upper()), ("label", "exact", sk), ("label", "exact", ik), ("label", "contains", sk), ("label", "contains", ik)]
    for kind, match, text in tiers:
        if not text:
            continue
        # the Sector and Industry labels share one vocabulary: a rule of kind 'sector' or 'industry' applies to either label
        hits = [r for r in rules if (r["label_kind"] == kind or (kind == "label" and r["label_kind"] in ("sector", "industry"))) and r["match_type"] == match and (r["pattern"] == text if match == "exact" else r["pattern"] in text)]
        if hits:
            r = sorted(hits, key=lambda r: (r["priority"], -len(r["pattern"]), r["pattern"]))[0]
            return r["sector_code"], f"{'name' if kind == 'symbol' else 'label'} {match} '{r['pattern']}'"
    return None


async def sync_mappings(conn, today: date) -> Dict[str, int]:
    """Give every company a primary sector from the label map (or an explicit 'not mapped' reason). Mappings an administrator set are never touched; a changed
    mapping closes the old row (effective_to) and opens a new one, so the history is kept."""
    rules = [dict(r) for r in await conn.fetch("SELECT label_kind, match_type, pattern, sector_code, priority FROM macro_label_map WHERE active")]
    ids = {r["sector_code"]: r["id"] for r in await conn.fetch("SELECT id, sector_code FROM sector_master")}
    cur = {r["symbol"]: dict(r) for r in await conn.fetch("SELECT symbol, sector_id, source, id FROM company_sector_mapping WHERE is_primary AND effective_to IS NULL")}
    close, opened, unmapped, drop_unmapped = [], [], [], []
    mapped = 0
    for c in await conn.fetch("SELECT symbol, name, sector, industry FROM companies"):
        sym = c["symbol"]
        old = cur.get(sym)
        if old and old["source"] == "admin":
            mapped += 1
            continue
        hit = resolve(rules, sym, c["sector"], c["industry"])
        if hit:
            mapped += 1
            if old and old["sector_id"] == ids[hit[0]]:
                continue
            if old:
                close.append((old["id"],))
            opened.append((sym, ids[hit[0]], today, "label_map", f"{hit[1]} (sector: {c['sector'] or '-'}; industry: {c['industry'] or '-'})"))
            drop_unmapped.append((sym,))
        else:
            if old:
                close.append((old["id"],))
            why = ("the company has no Sector or Industry label" if not (c["sector"] or c["industry"]) else
                   f"no label-map rule matches its Sector '{c['sector'] or '-'}' / Industry '{c['industry'] or '-'}'")
            unmapped.append((sym, why, c["sector"], c["industry"]))
    if close:
        await conn.executemany("UPDATE company_sector_mapping SET effective_to = CURRENT_DATE WHERE id = $1", close)
    if opened:
        await conn.executemany("INSERT INTO company_sector_mapping (symbol, sector_id, is_primary, effective_from, source, basis_label) VALUES ($1,$2,true,$3,$4,$5)", opened)
    if drop_unmapped:
        await conn.executemany("DELETE FROM company_macro_unmapped WHERE symbol = $1", drop_unmapped)
    if unmapped:
        await conn.executemany("INSERT INTO company_macro_unmapped (symbol, reason, sector_label, industry_label) VALUES ($1,$2,$3,$4) ON CONFLICT (symbol) DO UPDATE SET reason = EXCLUDED.reason, "
                               "sector_label = EXCLUDED.sector_label, industry_label = EXCLUDED.industry_label, checked_at = now()", unmapped)
    return {"mapped": mapped, "unmapped": len(unmapped), "changed": len(opened)}


MIN_SEGMENT_SHARE = 0.80


def segment_weights(latest: List[Dict[str, Any]], rules: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Dict[str, Any]]], str]:
    """Revenue weights per macro sector from a company's reported segments, or (None, why). Only the mapped segments count; they must hold at least 80% of the
    segment revenue, and their weights are normalised over the mapped revenue (the rule is recorded). Nothing is invented: no reported revenue, no weights."""
    segs = [(str(s.get("name") or ""), float(s["revenue"])) for s in latest if isinstance(s.get("revenue"), (int, float)) and s["revenue"] > 0]
    total = sum(r for _, r in segs)
    if len(segs) < 2 or total <= 0:
        return None, "no reliable segment revenue is reported"
    seg_rules = [{**r, "label_kind": "sector"} for r in rules if r["label_kind"] == "segment"]
    by: Dict[str, Dict[str, Any]] = {}
    mapped = 0.0
    for name, rev in segs:
        hit = resolve(seg_rules, "", name, None)
        if hit:
            mapped += rev
            e = by.setdefault(hit[0], {"revenue": 0.0, "segments": []})
            e["revenue"] += rev
            e["segments"].append(name)
    if mapped / total < MIN_SEGMENT_SHARE:
        return None, f"only {mapped / total * 100:.0f}% of reported segment revenue maps to a covered sector (needs {MIN_SEGMENT_SHARE * 100:.0f}%)"
    for e in by.values():
        e["weight"] = round(e["revenue"] / mapped, 6)
    return by, f"weights normalised over the mapped segments ({mapped / total * 100:.0f}% of segment revenue)"


async def sync_segments(conn, today: date) -> Dict[str, int]:
    rules = [dict(r) for r in await conn.fetch("SELECT label_kind, match_type, pattern, sector_code, priority FROM macro_label_map WHERE active")]
    ids = {r["sector_code"]: r["id"] for r in await conn.fetch("SELECT id, sector_code FROM sector_master")}
    n = 0
    for c in await conn.fetch("SELECT m.symbol FROM company_sector_mapping m JOIN sector_master s ON s.id = m.sector_id WHERE m.is_primary AND m.effective_to IS NULL AND s.sector_code = 'diversified'"):
        sym = c["symbol"]
        body = await conn.fetchval("SELECT body FROM snapshots WHERE symbol = $1 AND section = 'segments' ORDER BY (statement = 'consolidated') DESC LIMIT 1", sym)
        weights, why = (None, "no stored segment data")
        if body:
            try:
                weights, why = segment_weights((jd(body) or {}).get("latest") or [], rules)
            except Exception:
                weights, why = None, "segment data could not be read"
        old = {r["segment_name"]: r for r in await conn.fetch("SELECT id, sector_id, segment_name, revenue_weight FROM company_sector_mapping WHERE symbol = $1 AND NOT is_primary AND source = 'segments_auto' AND effective_to IS NULL", sym)}
        want = {(sc): (e["weight"], ", ".join(e["segments"])[:200]) for sc, e in (weights or {}).items()}
        same = {r["segment_name"] for r in old.values()} == {w[1] for w in want.values()} and all(
            abs(float(r["revenue_weight"]) - next(w[0] for k, w in want.items() if w[1] == r["segment_name"])) < 1e-4 for r in old.values())
        if same and (bool(old) == bool(want)):
            continue
        for r in old.values():
            await conn.execute("UPDATE company_sector_mapping SET effective_to = CURRENT_DATE WHERE id = $1", r["id"])
        for sc, (w, segs) in want.items():
            await conn.execute("INSERT INTO company_sector_mapping (symbol, sector_id, revenue_weight, is_primary, segment_name, effective_from, source, basis_label) VALUES ($1,$2,$3,false,$4,$5,'segments_auto',$6)",
                               sym, ids[sc], w, segs, today, why)
            n += 1
    return {"segmentRows": n}


# ------------------------------------------------------------------------------------------------------------ the whole nightly run
async def fingerprint(conn) -> str:
    a = await conn.fetchrow("SELECT count(*) AS n, max(d) AS d, sum(v) AS s FROM macro_points")
    b = await conn.fetchrow("SELECT count(*) AS n, max(day) AS d FROM commodity_snapshots WHERE kind = 'intl_usd'")
    c = await conn.fetchrow("SELECT count(*) AS n, max(updated_at) AS u FROM companies")
    return f"{a['n']}|{a['d']}|{round(float(a['s'] or 0), 3)}|{b['n']}|{b['d']}|{c['n']}"


async def invalidate_cache(redis) -> None:
    try:
        keys = [k async for k in redis.scan_iter(match=CACHE_PREFIX + "*", count=200)]
        if keys:
            await redis.delete(*keys)
    except Exception:   # nosec B110 - cache only
        pass


async def run(store, trigger: str = "job", today: Optional[date] = None, actor: str = "system", reconstruct_months: int = 24) -> Dict[str, Any]:
    """ingest -> validate -> persist -> revisions -> signals -> scores -> snapshots -> cache. Never calls an external source: it reads the tables the macro, flows and
    commodity jobs fill. A failure is recorded in macro_run_log and leaves the last snapshot in place (served with a stale warning)."""
    today = today or today_ist()
    async with store.pool.acquire() as conn:
        run_id = await conn.fetchval("INSERT INTO macro_run_log (trigger, status, as_of) VALUES ($1,'running',$2) RETURNING id", trigger, today)
        try:
            await SEED.ensure_seed(conn)
            defs = await load_defs(conn)
            col = await collect(conn, today)
            ing = await ingest(conn, today, col, defs)
            maps = await sync_mappings(conn, today)
            segs = await sync_segments(conn, today)
            cfg, _ = await load_config(conn)
            calc = await calculate(conn, today, cfg.version, "live")
            rec = await reconstruct(conn, today, cfg.version, reconstruct_months) if reconstruct_months else 0
            fp = await fingerprint(conn)
            missing = [r["indicator_code"] for r in await conn.fetch("SELECT indicator_code FROM macro_indicators WHERE status IN ('Missing','Stale','Invalid')")]
            detail = {"ingest": ing, "mapping": maps, "segments": segs, "calc": calc, "reconstructed": rec, "unusable": missing, "actor": actor}
            status = "ok" if not missing else "partial"
            await conn.execute("UPDATE macro_run_log SET finished_at = now(), status = $2, model_version = $3, fingerprint = $4, detail = $5::jsonb WHERE id = $1", run_id, status, cfg.version, fp, json.dumps(detail))
        except Exception as exc:
            log.exception("macro outlook run failed")
            await conn.execute("UPDATE macro_run_log SET finished_at = now(), status = 'failed', error = $2 WHERE id = $1", run_id, f"{type(exc).__name__}: {exc}"[:500])
            raise
    await invalidate_cache(store.redis)
    return {"status": status, "runId": run_id, **detail}


async def has_new_data(store) -> Optional[bool]:
    """The job probe: did the stored macro, commodity or company tables change since the last successful run?"""
    async with store.pool.acquire() as conn:
        last = await conn.fetchval("SELECT fingerprint FROM macro_run_log WHERE status IN ('ok','partial') ORDER BY id DESC LIMIT 1")
        if last is None:
            return True
        return (await fingerprint(conn)) != last
