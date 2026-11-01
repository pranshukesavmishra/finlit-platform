"""The counts behind the filter panel, in one call: /api/mf/filters?screen=1&<the same filters as the list>.

Every number answers "if the other filters stay as they are, how many funds would this choice give?" (faceted counts): the options of a group are counted
with every filter EXCEPT their own group applied. A slider's histogram is counted the same way, so moving one slider never flattens its own picture.
Every numeric field also says "N of M funds have this figure": M funds pass the other filters, N of them have the figure. The rest are the "no data" count.

All SQL here is parametrised through spec.where(); the numeric expressions and edges come from the fixed registry in spec.py."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from . import spec
from .spec import CAP_CHIPS, HOUSE, MAT_BANDS, NUMS, NUM_BY_KEY, PASSIVE_KEYS, Screen, source

SCATTER_MAX = 400
FLOW_MONTHS = 6
TOP_SECTORS = 40


async def _count(conn, scr: Screen, exclude: Sequence[str]) -> int:
    src, args = source(scr.preds, scr.family, exclude)
    return await conn.fetchval(f"SELECT count(*) FROM {src}", *args)  # nosec B608 - fixed text; every value is a bound parameter


async def _grouped(conn, scr: Screen, exclude: Sequence[str], expr: str) -> Dict[Any, int]:
    src, args = source(scr.preds, scr.family, exclude)
    rows = await conn.fetch(f"SELECT {expr} AS v, count(*) AS n FROM {src} GROUP BY 1", *args)  # nosec B608 - `expr` is a literal from this module
    return {r["v"]: r["n"] for r in rows}


async def _each(conn, scr: Screen, exclude: Sequence[str], conds: Dict[str, str]) -> Dict[str, int]:
    """Several overlapping counts in one pass: {name: number of rows where its condition holds}."""
    src, args = source(scr.preds, scr.family, exclude)
    cols = ", ".join(f"count(*) FILTER (WHERE {c}) AS c{i}" for i, c in enumerate(conds.values()))
    row = await conn.fetchrow(f"SELECT {cols} FROM {src}", *args)  # nosec B608 - conditions are literals from spec.py
    return {k: row[f"c{i}"] for i, k in enumerate(conds)}


async def _histogram(conn, scr: Screen, num: spec.Num) -> dict:
    src, args = source(scr.preds, scr.family, ["rng:" + num.key])
    args.append(spec.hist_thresholds(num))
    rows = await conn.fetch(
        f"SELECT CASE WHEN ({num.expr}) IS NULL THEN -1 ELSE width_bucket(({num.expr})::float8, ${len(args)}::float8[]) END AS b, count(*) AS n FROM {src} GROUP BY 1",  # nosec B608 - expr from the registry
        *args)
    bins = [0] * (len(num.edges) - 1)
    missing = 0
    for r in rows:
        if r["b"] < 0:
            missing = r["n"]
        else:
            bins[min(r["b"], len(bins) - 1)] += r["n"]
    n = sum(bins)
    return {"edges": list(num.edges), "bins": bins, "n": n, "m": n + missing}


def _chip_counts(by_cat: Dict[str, int], keys_of: Dict[str, Tuple[str, ...]], by_key: Dict[str, List[str]]) -> Dict[str, int]:
    return {chip: sum(by_cat.get(name, 0) for k in ks for name in by_key.get(k, [])) for chip, ks in keys_of.items()}


async def build(conn, scr: Screen, ctx: spec.Ctx, classify, fields: Optional[Set[str]] = None) -> dict:
    out: Dict[str, Any] = {}
    out["total"] = await _count(conn, scr, ())

    # ---- numeric fields: histogram and "N of M have this figure"
    numeric: Dict[str, dict] = {}
    for num in NUMS:
        if fields is not None and num.key not in fields:
            continue
        numeric[num.key] = await _histogram(conn, scr, num)
    out["numeric"] = numeric

    # ---- categories
    cat_type = await _grouped(conn, scr, ["type"], "category")
    tabs: Dict[str, int] = {}
    for name, n in cat_type.items():
        tabs[classify(name)[0]] = tabs.get(classify(name)[0], 0) + n
    out["type"] = tabs
    cat_subs = await _grouped(conn, scr, ["subs"], "category")
    subs: Dict[str, dict] = {}
    for name, n in cat_subs.items():
        tab, key, label = classify(name)
        s = subs.setdefault(key, {"key": key, "label": label, "tab": tab, "n": 0})
        s["n"] += n
    out["subs"] = sorted(subs.values(), key=lambda s: (-s["n"], s["label"]))
    by_cap = await _grouped(conn, scr, ["cap"], "category")
    out["cap"] = _chip_counts(by_cap, CAP_CHIPS, ctx.by_key)
    by_style = await _grouped(conn, scr, ["style"], "category")
    passive_names = {n for k in PASSIVE_KEYS for n in ctx.by_key.get(k, [])}
    out["style"] = {"passive": sum(n for c, n in by_style.items() if c in passive_names), "active": sum(n for c, n in by_style.items() if c not in passive_names)}
    by_mat = await _grouped(conn, scr, ["mat"], "category")
    out["mat"] = _chip_counts(by_mat, MAT_BANDS, ctx.by_key)
    struct = await _grouped(conn, scr, ["struct"], "CASE WHEN lower(scheme_type) LIKE 'open%' THEN 'open' WHEN lower(scheme_type) LIKE 'close%' THEN 'close' WHEN lower(scheme_type) LIKE 'interval%' THEN 'interval' END")
    out["struct"] = {k: struct.get(k, 0) for k in spec.STRUCTS}

    # ---- fund house, plan, option, instrument, status, freshness, size basis
    amcs = await _grouped(conn, scr, ["amcs"], "amc")
    out["amcs"] = sorted(({"name": k, "n": v} for k, v in amcs.items()), key=lambda r: (-r["n"], r["name"]))
    out["house"] = await _each(conn, scr, ["house"], dict(HOUSE))
    out["plans"] = {k: v for k, v in (await _grouped(conn, scr, ["plans"], "plan")).items()}
    out["options"] = {k: v for k, v in (await _grouped(conn, scr, ["options"], "option_class")).items()}
    inst = await _grouped(conn, scr, ["inst"], "CASE WHEN COALESCE(x_is_etf, false) THEN 'etf' ELSE 'fund' END")
    out["inst"] = {"fund": inst.get("fund", 0), "etf": inst.get("etf", 0)}
    st = await _grouped(conn, scr, ["status"], "CASE WHEN active THEN 'active' ELSE 'stopped' END")
    out["status"] = {"active": st.get("active", 0), "stopped": st.get("stopped", 0)}
    newest = "(SELECT max(nav_date) FROM mf_schemes WHERE active)"
    out["fresh"] = await _each(conn, scr, ["fresh"], {"today": f"nav_date >= {newest}", "week": f"nav_date >= {newest} - 7"})
    basis = await _grouped(conn, scr, ["aumbasis"], "aum_kind")
    out["aumbasis"] = {"q": basis.get("q", 0), "m": basis.get("m", 0)}
    out["aumrank"] = await _each(conn, scr, ["aumrank"], dict(spec.AUMRANK))
    out["exit"] = await _each(conn, scr, ["exit"], dict(spec.EXITS))
    out["chk"] = await _each(conn, scr, ["chk"], {str(n): f"chk_pass >= {n}" for n in (3, 4, 5)})
    out["chk_each"] = await _each(conn, scr, ["chk_each"], {k: f"(chk_mask & {b}) = {b} AND (chk_bits & {b}) = {b}" for k, b in spec.CHECK_BITS.items()})
    out["tick"] = await _each(conn, scr, ["tick"], {k: v for k, v in spec.TICKS.items()})

    # ---- rank inside the category: how many funds have a figure for each period
    out["rk"] = await _each(conn, scr, [f"rk:{p}" for p in spec.RK_PERIODS], {p: f"{k} IS NOT NULL" for p, (k, _n) in spec.RK_PERIODS.items()})

    # ---- tags, sectors
    src, args = source(scr.preds, scr.family, ["tags"])
    rows = await conn.fetch(f"SELECT t, count(*) AS n FROM (SELECT unnest(x_tags) AS t FROM {src}) z GROUP BY 1", *args)  # nosec B608
    tag_n = {r["t"]: r["n"] for r in rows}
    tags = await conn.fetch("SELECT tag, kind, label FROM mf_tags WHERE active ORDER BY kind, label")
    out["tags"] = [{"tag": t["tag"], "kind": t["kind"], "label": t["label"], "n": tag_n.get(t["tag"], 0)} for t in tags]
    src, args = source(scr.preds, scr.family, ["sector"])
    rows = await conn.fetch(f"SELECT s, count(*) AS n FROM (SELECT jsonb_object_keys(x_sectors) AS s FROM {src} AND x_sectors IS NOT NULL) z GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {TOP_SECTORS}", *args)  # nosec B608
    out["sectors"] = [{"name": r["s"], "n": r["n"]} for r in rows]
    out["portfolio"] = await _each(conn, scr, ["pfdate"], {"latest": "x_port_asof >= (SELECT max(x_port_asof) FROM mf_screen) - 5",
                                                            "prev": "x_port_asof < (SELECT max(x_port_asof) FROM mf_screen) - 5 AND x_port_asof >= (SELECT max(x_port_asof) FROM mf_screen) - 40",
                                                            "older": "x_port_asof < (SELECT max(x_port_asof) FROM mf_screen) - 40", "none": "x_port_asof IS NULL"})

    # ---- the category's market view
    out["cflow"] = await _each(conn, scr, ["cflow"], {"pos": "x_cf_flow > 0", "neg": "x_cf_flow < 0", "none": "x_cf_flow IS NULL"})
    out["cstreak"] = await _each(conn, scr, ["cstreak"], {"up": "x_cf_streak = 3", "down": "x_cf_streak = -3"})
    out["csize"] = await _each(conn, scr, ["csize"], {"lt1": "x_cf_share < 1", "1to5": "x_cf_share >= 1 AND x_cf_share <= 5", "gt5": "x_cf_share > 5"})

    # ---- what was worked out, and when
    built = await conn.fetchrow("""SELECT count(*) AS rows, max(x_run) AS run, max(x_port_asof) AS port, max(x_cf_month) AS flow,
                                          count(*) FILTER (WHERE cardinality(x_tags) > 0) AS tagged,
                                          count(*) FILTER (WHERE x_tags && COALESCE((SELECT array_agg(tag) FROM mf_tags WHERE kind = 'index'), '{}')) AS indexed
                                   FROM mf_screen""")
    out["built"] = {"rows": built["rows"], "run": built["run"].isoformat() if built["run"] else None, "portfolioDate": built["port"].isoformat() if built["port"] else None,
                    "flowMonth": built["flow"].isoformat() if built["flow"] else None, "tagged": built["tagged"], "indexTagged": built["indexed"]}

    # ---- the return-vs-risk scatter of the result: the largest funds first, never more than SCATTER_MAX points
    src, args = source(scr.preds, scr.family)
    glue = "AND"
    pts = await conn.fetch(f"SELECT code, name, category, r3y, x_vol3 AS vol FROM {src} {glue}"  # nosec B608
                           f" r3y IS NOT NULL AND x_vol3 IS NOT NULL ORDER BY aum_lakh DESC NULLS LAST, code LIMIT {SCATTER_MAX}", *args)
    total_pts = await conn.fetchval(f"SELECT count(*) FROM {src} {glue} r3y IS NOT NULL AND x_vol3 IS NOT NULL", *args)  # nosec B608
    out["scatter"] = {"points": [[p["code"], p["name"], round(p["r3y"], 2), round(p["vol"], 2)] for p in pts], "eligible": total_pts, "shown": len(pts)}

    # ---- category flow bars: the selected sub-categories, else the six with most funds in the result
    keys = list(scr.subs) or [s["key"] for s in out["subs"][:6]]
    flows: List[dict] = []
    if keys:
        rows = await conn.fetch("SELECT ckey, month, net_flow, aum FROM mf_cat_flow WHERE ckey = ANY($1::text[]) AND month > (SELECT max(month) - interval '6 months' FROM mf_cat_flow) ORDER BY ckey, month", keys[:8])
        label_of = {s["key"]: s["label"] for s in out["subs"]}
        by: Dict[str, dict] = {}
        for r in rows:
            f = by.setdefault(r["ckey"], {"key": r["ckey"], "label": label_of.get(r["ckey"]) or r["ckey"], "months": [], "net": []})
            f["months"].append(r["month"].isoformat()[:7])
            f["net"].append(None if r["net_flow"] is None or not math.isfinite(r["net_flow"]) else round(r["net_flow"], 0))
        flows = list(by.values())
    out["flows"] = flows
    return out
