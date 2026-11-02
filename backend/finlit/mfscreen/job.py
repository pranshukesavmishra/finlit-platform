"""The `refresh-mf-screen` worker command: fill mf_screen (one row per scheme), mf_screen_hold and mf_cat_flow once a night.

It runs after the fund facts, the industry report and the portfolios have loaded (registry job "mf-screen", docs/JOBS.md), reads only tables we already hold
(mf_schemes, mf_monthly, mf_facts, mf_ter, disclosure_portfolios, disclosure_facts, mf_industry, etf_funds, mf_tags), works every figure out in memory in a few
seconds and writes it in ONE transaction. A failed run leaves last night's rows untouched; running it twice gives the same rows (rows are only rewritten
when a value differs). Nothing is fetched from the network. Nothing here is a score: the figures only describe past data."""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .. import mf
from ..mfscore import exitload
from . import calc

log = logging.getLogger("finlit.mfscreen")

PEER_MIN = calc.MIN_PEERS
ETF_KEYS = ("etf", "etf-debt", "gold-etf", "silver-etf")
INDUSTRY_PREFIX = {"equity": "Equity Scheme", "debt": "Debt Scheme", "hybrid": "Hybrid Scheme", "solution": "Solution Oriented Scheme"}
FLOW_KEEP_MONTHS = 13
BATCH = 1000

COLS: Tuple[str, ...] = (
    "x_code", "x_run", "x_ckey", "x_is_etf", "x_tags", "x_launch", "x_age", "x_house_aum_cr", "x_aum_rk", "x_aum_rn", "x_aum_share", "x_na_chg", "x_na_months",
    "x_ex1y", "x_ex3y", "x_ex5y", "x_rk1", "x_rn1", "x_rk3", "x_rn3", "x_rk5", "x_rn5", "x_consist", "x_n_months",
    "x_ter_rel", "x_ter_gap", "x_fee_share", "x_exit_pct", "x_exit_days", "x_exit_state",
    "x_vol1", "x_vol3", "x_worst_loss", "x_worst12_loss", "x_neg_share", "x_below_high", "x_down_cap", "x_sharpe", "x_worst_less",
    "x_up_month", "x_down_dev", "x_vol_rel", "x_cy1", "x_cy2", "x_cy3",
    "x_port_asof", "x_eq_pct", "x_debt_pct", "x_cash_pct", "x_other_pct", "x_n_hold", "x_top10", "x_max_hold", "x_top_sector", "x_top_sector_pct", "x_sectors",
    "x_cf_month", "x_cf_flow", "x_cf_streak", "x_cf_aum_mom", "x_cf_aum_yoy", "x_cf_folio_mom", "x_cf_share",
)
_NORM = re.compile(r"[^a-z0-9]+")


def norm_name(s: str) -> str:
    return " " + _NORM.sub(" ", (s or "").lower().replace("&", " and ")).strip() + " "


def r2(v: Optional[float], n: int = 4) -> Optional[float]:
    return None if v is None or v != v else round(float(v), n)


# ====================================================================================== pure parts

def tags_for(name: str, tab: str, tags: Sequence[dict], sectors: Optional[Dict[str, float]]) -> List[str]:
    """Rule 1: the scheme name holds one of the tag's keywords as whole words. Rule 2: the tag's sector words are found in sectors that hold at least
    `sector_min` percent of net assets in the latest portfolio. Only for tabs the tag applies to."""
    hay = norm_name(name)
    out = []
    for t in tags:
        if tab not in t["tabs"]:
            continue
        if any(norm_name(k) in hay for k in t["keywords"]):
            out.append(t["tag"])
        elif t["sectors"] and sectors:
            share = sum(p for sec, p in sectors.items() if any(w.lower() in sec.lower() for w in t["sectors"]))
            if share >= t["sector_min"]:
                out.append(t["tag"])
    return sorted(set(out))


def portfolio_figures(holdings: Sequence[Sequence[Any]]) -> dict:
    """Asset split, holdings count, top-10 and largest holding, sector map of one portfolio (holdings are [name, isin, sector, class, pct, qty, value])."""
    split = {"e": 0.0, "d": 0.0, "c": 0.0, "o": 0.0}
    sectors: Dict[str, float] = {}
    pcts: List[float] = []
    for h in holdings:
        cls, pct = h[3], float(h[4] or 0.0)
        split[cls if cls in split else "o"] += pct
        if cls != "c":
            pcts.append(pct)
        if cls == "e":
            sec = (h[2] or "").strip()
            if sec and sec.lower() != "not classified":
                sectors[sec] = sectors.get(sec, 0.0) + pct
    top = max(sectors.items(), key=lambda kv: kv[1]) if sectors else (None, None)
    srt = sorted(pcts, reverse=True)
    return {"eq": split["e"], "debt": split["d"], "cash": split["c"], "other": split["o"], "n": len(pcts), "top10": sum(srt[:10]) if srt else None,
            "max": srt[0] if srt else None, "top_sector": top[0], "top_sector_pct": top[1], "sectors": {k: round(v, 2) for k, v in sectors.items()} or None}


def exit_figures(text: Optional[str]) -> Tuple[Optional[str], Optional[float], Optional[int]]:
    """(state, highest load %, longest holding period in days) of an exit-load text; state None when the house gave no text."""
    if not text or not text.strip():
        return None, None, None
    p = exitload.parse(text)
    if p.points == 100:
        return "nil", 0.0, None
    if p.points is not None and p.load is not None:
        return "read", p.load, p.days
    return "unread", p.load, p.days


def industry_flows(rows: Sequence[dict], totals: Dict[date, float]) -> Dict[str, Dict[date, dict]]:
    """AMFI's category rows -> {sub-category key: {month: {net, aum, folios}}}: rows that fall in one sub-category are added up."""
    out: Dict[str, Dict[date, dict]] = defaultdict(dict)
    for r in rows:
        grp = r["grp"]
        label = f"{INDUSTRY_PREFIX[grp]} - {r['category']}" if grp in INDUSTRY_PREFIX else r["category"]
        key = mf.classify(label)[1]
        m = out[key].setdefault(r["month"], {"net": None, "aum": None, "folios": None})
        for src, dst in (("net_flow", "net"), ("aum", "aum"), ("folios", "folios")):
            if r[src] is not None:
                m[dst] = (m[dst] or 0) + r[src]
    return out


def category_view(flows: Dict[date, dict], totals: Dict[date, float]) -> Optional[dict]:
    """The latest month's figures of one sub-category: net flow, the three-month streak, net assets month on month and year on year, folios, share of the industry."""
    if not flows:
        return None
    months = sorted(flows)
    last = months[-1]
    mk = calc.month_key(last)
    at = {calc.month_key(m): flows[m] for m in months}
    cur = flows[last]
    last3 = [at.get(mk - i) for i in range(3)]
    streak = None
    if all(x is not None and x["net"] is not None for x in last3):
        streak = 3 if all(x["net"] > 0 for x in last3) else -3 if all(x["net"] < 0 for x in last3) else 0
    prev, yr = at.get(mk - 1), at.get(mk - 12)

    def pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
        return None if a is None or b is None or b <= 0 else (a / b - 1) * 100
    total = totals.get(last)
    return {"month": last, "flow": cur["net"], "streak": streak, "aum_mom": pct(cur["aum"], prev["aum"] if prev else None),
            "aum_yoy": pct(cur["aum"], yr["aum"] if yr else None), "folio_mom": pct(cur["folios"], prev["folios"] if prev else None),
            "share": (cur["aum"] / total * 100) if cur["aum"] and total else None, "aum": cur["aum"]}


def build_rows(schemes: Sequence[dict], monthly: Dict[int, Tuple[Sequence[date], Sequence[float]]], facts: Dict[int, dict], ters: Dict[int, Tuple[Optional[float], Optional[float]]],
               exits: Dict[str, Optional[str]], ports: Dict[str, List[dict]], flows: Dict[str, Dict[date, dict]], totals: Dict[date, float], etf_isins: set,
               tags: Sequence[dict], run: date) -> Tuple[List[tuple], List[tuple], dict]:
    """Everything the job writes, as plain data. schemes: dicts with the mf_schemes columns this needs. Returns (mf_screen rows, mf_screen_hold rows, stats)."""
    for s in schemes:
        s["tab"], s["ckey"], _ = mf.classify(s["category"])
    peers: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for s in schemes:
        if s["active"] and s["option_class"] == "Growth" and s["nav"] is not None:
            peers[(s["ckey"], s["plan"])].append(s)

    # ---- month-end figures per scheme (Growth, active, with a stored month-end series)
    fig: Dict[int, dict] = {}
    rets36: Dict[int, Dict[int, float]] = {}
    for s in schemes:
        if not (s["active"] and s["option_class"] == "Growth" and s["nav"] is not None and s["nav_date"] and s["code"] in monthly):
            continue
        by = calc.by_month(*monthly[s["code"]])
        end_mk = calc.month_key(s["nav_date"])
        f: dict = {"n_months": len(by)}
        w36 = calc.window(by, end_mk, 36)
        if w36:
            r = calc.returns(w36)
            f.update(vol3=calc.volatility(r), worst=calc.worst_loss(r), neg=calc.neg_share(r), below=calc.below_high(w36), up=calc.biggest_gain(r), down_dev=calc.downside_dev(r))
            rets36[s["code"]] = {end_mk - 36 + i: r[i] for i in range(36)}   # the month a return ENDS in: window months end_mk-1-36+1 .. end_mk-1
        w12 = calc.window(by, end_mk, 12)
        if w12:
            f["vol1"] = calc.volatility(calc.returns(w12))
        w48 = calc.window(by, end_mk, 48)
        if w48:
            f["worst12"] = calc.worst_rolling(w48, 12)
        f["sharpe"] = calc.sharpe(s["r3y"], f.get("vol3"))
        for i in (1, 2, 3):   # the three calendar years before the run's year, the same years for every fund
            if (run.year - i) * 12 + 11 <= end_mk - 1:   # December of that year is a full month of this fund's series
                f["cy%d" % i] = calc.calendar_return(by, run.year - i)
        fig[s["code"]] = f

    # ---- peer groups: medians, excess returns, ranks, downside capture
    gfig: Dict[int, dict] = defaultdict(dict)
    for (ck, plan), members in peers.items():
        n = len(members)
        if n < PEER_MIN:
            continue
        for col, ex, rk, rn in (("r1y", "ex1y", "rk1", "rn1"), ("r3y", "ex3y", "rk3", "rn3"), ("r5y", "ex5y", "rk5", "rn5")):
            vals = [m[col] for m in members if m[col] is not None]
            if len(vals) < PEER_MIN:
                continue
            med = calc.median(vals)
            for m in members:
                if m[col] is not None:
                    gfig[m["code"]][ex] = m[col] - med
                    gfig[m["code"]][rk] = calc.rank_desc(m[col], vals)
                    gfig[m["code"]][rn] = len(vals)
        tlist = [m["ter"] for m in members if m["ter"] is not None]
        if len(tlist) >= PEER_MIN:
            med = calc.median(tlist)
            if med and med > 0:
                for m in members:
                    if m["ter"] is not None:
                        gfig[m["code"]]["ter_rel"] = m["ter"] / med
        w12 = [fig[m["code"]]["worst12"] for m in members if m["code"] in fig and fig[m["code"]].get("worst12") is not None]
        med12 = calc.median(w12) if len(w12) >= PEER_MIN else None
        v3 = [fig[m["code"]]["vol3"] for m in members if m["code"] in fig and fig[m["code"]].get("vol3") is not None]
        medv = calc.median(v3) if len(v3) >= PEER_MIN else None
        own = [rets36[m["code"]] for m in members if m["code"] in rets36]
        pm = calc.peer_median_months(own) if len(own) >= PEER_MIN else {}
        for m in members:
            c = m["code"]
            if med12 is not None and c in fig and fig[c].get("worst12") is not None:
                gfig[c]["worst_less"] = fig[c]["worst12"] < med12
            if medv and medv > 0 and c in fig and fig[c].get("vol3") is not None:
                gfig[c]["vol_rel"] = fig[c]["vol3"] / medv
            if c in rets36 and pm:
                gfig[c]["down_cap"] = calc.down_capture(rets36[c], pm)
                gfig[c]["consist"] = calc.consistency(rets36[c], pm)

    # ---- size: house totals, rank among the families of the sub-category, share of the category
    fam_aum: Dict[str, float] = {}
    for s in schemes:
        if s["aum_lakh"] is not None and s["aum_lakh"] > 0:
            fam_aum[s["family"]] = max(fam_aum.get(s["family"], 0.0), s["aum_lakh"])
    house: Dict[str, float] = defaultdict(float)
    seen_family = set()
    fam_cat: Dict[str, List[float]] = defaultdict(list)
    for s in schemes:
        f = s["family"]
        if f in fam_aum and f not in seen_family:
            seen_family.add(f)
            house[s["amc"]] += fam_aum[f] / 100.0
            fam_cat[s["ckey"]].append(fam_aum[f])
    cview = {k: category_view(v, totals) for k, v in flows.items()}

    # ---- portfolio and net-assets change per family
    pfig: Dict[str, dict] = {}
    hold_rows: List[tuple] = []
    for fk, rows in ports.items():
        latest = rows[0]
        p = portfolio_figures(latest["holdings"])
        p["asof"] = latest["as_of"]
        na = [r for r in rows if r["net_assets_lakh"] and r["net_assets_lakh"] > 0]
        p["na_chg"] = (na[0]["net_assets_lakh"] / na[-1]["net_assets_lakh"] - 1) * 100 if len(na) >= 2 else None
        p["na_months"] = len(na)
        pfig[fk] = p
        agg: Dict[str, float] = defaultdict(float)
        for h in latest["holdings"]:
            if h[3] == "e" and h[1]:
                agg[h[1]] += float(h[4] or 0.0)
        hold_rows.extend((fk, isin, round(pct, 4), latest["as_of"]) for isin, pct in agg.items() if pct > 0)

    out: List[tuple] = []
    stats = {"schemes": len(schemes), "withRisk": 0, "withRank": 0, "withPortfolio": 0, "withExit": 0, "tagged": 0, "etf": 0}
    for s in schemes:
        c = s["code"]
        fa, g, f = facts.get(c, {}), gfig.get(c, {}), fig.get(c, {})
        tr = ters.get(c)
        pf = pfig.get(s["family"])
        cv = cview.get(s["ckey"])
        launch = fa.get("launch_date")
        ref = s["nav_date"] or run
        age = (ref - launch).days / 365.25 if launch and ref >= launch else None
        gap = tr[0] - tr[1] if tr and tr[0] and tr[1] and tr[0] > 0 and tr[1] > 0 else None
        ex_state, ex_pct, ex_days = exit_figures(exits.get(s["family"]))
        vals = fam_cat.get(s["ckey"], [])
        rk = calc.rank_desc(s["aum_lakh"], vals) if s["aum_lakh"] and vals else None
        share = None
        if cv and cv["aum"] and s["aum_lakh"]:
            share = s["aum_lakh"] / 100.0 / cv["aum"] * 100
            share = share if share <= 100 else None
        is_etf = (s["isin"] in etf_isins) or (s["isin_reinvest"] in etf_isins) or s["ckey"] in ETF_KEYS
        tg = tags_for(s["name"], s["tab"], tags, pf["sectors"] if pf else None)
        row = {
            "x_code": c, "x_run": run, "x_ckey": s["ckey"], "x_is_etf": bool(is_etf), "x_tags": tg, "x_launch": launch, "x_age": r2(age), "x_house_aum_cr": r2(house.get(s["amc"]), 2),
            "x_aum_rk": rk, "x_aum_rn": len(vals) if rk else None, "x_aum_share": r2(share), "x_na_chg": r2(pf["na_chg"]) if pf else None, "x_na_months": pf["na_months"] if pf else None,
            "x_ex1y": r2(g.get("ex1y")), "x_ex3y": r2(g.get("ex3y")), "x_ex5y": r2(g.get("ex5y")),
            "x_rk1": g.get("rk1"), "x_rn1": g.get("rn1"), "x_rk3": g.get("rk3"), "x_rn3": g.get("rn3"), "x_rk5": g.get("rk5"), "x_rn5": g.get("rn5"),
            "x_consist": r2(g.get("consist")), "x_n_months": f.get("n_months"),
            "x_ter_rel": r2(g.get("ter_rel")), "x_ter_gap": r2(gap), "x_fee_share": r2(calc.fee_share(s["ter"], s["r3y"])),
            "x_exit_pct": r2(ex_pct), "x_exit_days": ex_days, "x_exit_state": ex_state,
            "x_vol1": r2(f.get("vol1")), "x_vol3": r2(f.get("vol3")), "x_worst_loss": r2(f.get("worst")), "x_worst12_loss": r2(f.get("worst12")), "x_neg_share": r2(f.get("neg")),
            "x_below_high": r2(f.get("below")), "x_down_cap": r2(g.get("down_cap")), "x_sharpe": r2(f.get("sharpe")), "x_worst_less": g.get("worst_less"),
            "x_up_month": r2(f.get("up")), "x_down_dev": r2(f.get("down_dev")), "x_vol_rel": r2(g.get("vol_rel")),
            "x_cy1": r2(f.get("cy1")), "x_cy2": r2(f.get("cy2")), "x_cy3": r2(f.get("cy3")),
            "x_port_asof": pf["asof"] if pf else None, "x_eq_pct": r2(pf["eq"]) if pf else None, "x_debt_pct": r2(pf["debt"]) if pf else None, "x_cash_pct": r2(pf["cash"]) if pf else None,
            "x_other_pct": r2(pf["other"]) if pf else None, "x_n_hold": pf["n"] if pf else None, "x_top10": r2(pf["top10"]) if pf else None, "x_max_hold": r2(pf["max"]) if pf else None,
            "x_top_sector": pf["top_sector"] if pf else None, "x_top_sector_pct": r2(pf["top_sector_pct"]) if pf else None,
            "x_sectors": json.dumps(pf["sectors"]) if pf and pf["sectors"] else None,
            "x_cf_month": cv["month"] if cv else None, "x_cf_flow": r2(cv["flow"], 2) if cv else None, "x_cf_streak": cv["streak"] if cv else None,
            "x_cf_aum_mom": r2(cv["aum_mom"]) if cv else None, "x_cf_aum_yoy": r2(cv["aum_yoy"]) if cv else None, "x_cf_folio_mom": r2(cv["folio_mom"]) if cv else None,
            "x_cf_share": r2(cv["share"]) if cv else None,
        }
        out.append(tuple(row[k] for k in COLS))
        stats["withRisk"] += f.get("vol3") is not None
        stats["withRank"] += g.get("rk3") is not None
        stats["withPortfolio"] += pf is not None
        stats["withExit"] += ex_state is not None
        stats["tagged"] += bool(tg)
        stats["etf"] += bool(is_etf)
    return out, hold_rows, stats


# ====================================================================================== database parts

SCHEME_SQL = """SELECT code, name, amc, category, plan, option_class, family, isin, isin_reinvest, nav, nav_date, prev_nav, active, r1y, r3y, r5y, ter, aum_lakh, scheme_type
                FROM mf_schemes"""


async def _load(conn) -> dict:
    schemes = [dict(r) for r in await conn.fetch(SCHEME_SQL)]
    monthly: Dict[int, Tuple[Sequence[date], Sequence[float]]] = {}
    async with conn.transaction():
        async for r in conn.cursor("SELECT m.code, m.days, m.navs FROM mf_monthly m JOIN mf_schemes s ON s.code = m.code WHERE s.active AND s.option_class = 'Growth'", prefetch=200):
            monthly[r["code"]] = (r["days"], r["navs"])
    facts = {r["code"]: {"launch_date": r["launch_date"]} for r in await conn.fetch("SELECT code, launch_date FROM mf_facts")}
    ters = {r["code"]: (r["ter_regular"], r["ter_direct"]) for r in await conn.fetch(
        "SELECT f.code, t.ter_regular, t.ter_direct FROM mf_facts f JOIN mf_ter t ON t.name_key = f.name_key")}
    exits: Dict[str, Optional[str]] = {}
    for r in await conn.fetch("SELECT fkey, value FROM disclosure_facts WHERE kind = 'exitload'"):
        v = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]
        exits[r["fkey"]] = (v or {}).get("text")
    ports: Dict[str, List[dict]] = defaultdict(list)
    async with conn.transaction():
        async for r in conn.cursor("SELECT fkey, as_of, net_assets_lakh, holdings FROM disclosure_portfolios ORDER BY fkey, as_of DESC", prefetch=50):
            h = json.loads(r["holdings"]) if isinstance(r["holdings"], str) else r["holdings"]
            ports[r["fkey"]].append({"as_of": r["as_of"], "net_assets_lakh": r["net_assets_lakh"], "holdings": h if len(ports[r["fkey"]]) == 0 else []})
    industry = [dict(r) for r in await conn.fetch(
        "SELECT i.month, i.category, i.grp, i.net_flow, i.aum, i.folios FROM mf_industry i JOIN mf_industry_months m ON m.month = i.month AND m.status = 'ok' "
        "WHERE i.month > (SELECT max(month) - interval '13 months' FROM mf_industry)")]
    totals = {r["month"]: r["aum"] for r in await conn.fetch("SELECT month, aum FROM mf_industry_months WHERE status = 'ok' AND aum IS NOT NULL")}
    etf = {r["isin"] for r in await conn.fetch("SELECT isin FROM etf_funds WHERE isin IS NOT NULL")}
    tags = [{"tag": r["tag"], "keywords": list(r["keywords"]), "sectors": list(r["sectors"]), "sector_min": r["sector_min"], "tabs": list(r["tabs"])}
            for r in await conn.fetch("SELECT tag, keywords, sectors, sector_min, tabs FROM mf_tags WHERE active")]
    return {"schemes": schemes, "monthly": monthly, "facts": facts, "ters": ters, "exits": exits, "ports": dict(ports), "industry": industry, "totals": totals, "etf": etf, "tags": tags}


def _upsert_sql() -> str:
    cols = ", ".join(COLS)
    ph = ", ".join(f"${i + 1}" for i in range(len(COLS)))
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in COLS[1:])
    cmp_cols = [c for c in COLS[1:] if c != "x_run"]
    old = ", ".join(f"mf_screen.{c}" for c in cmp_cols)
    new = ", ".join(f"EXCLUDED.{c}" for c in cmp_cols)
    return f"INSERT INTO mf_screen ({cols}) VALUES ({ph}) ON CONFLICT (x_code) DO UPDATE SET {sets} WHERE ({old}) IS DISTINCT FROM ({new})"   # nosec B608 - column names are the constants above


async def run(store, settings=None) -> dict:
    t0 = time.perf_counter()
    async with store.pool.acquire() as conn:
        data = await _load(conn)
    if not data["schemes"]:
        return {"status": "skipped", "reason": "no schemes loaded"}
    run_day = datetime.now(timezone.utc).date()
    flows = industry_flows(data["industry"], data["totals"])
    rows, holds, stats = build_rows(data["schemes"], data["monthly"], data["facts"], data["ters"], data["exits"], data["ports"],
                                    flows, data["totals"], data["etf"], data["tags"], run_day)
    # json text for the jsonb column: asyncpg takes the text with the ::jsonb cast done by the column type via a codec-free path
    sql = _upsert_sql().replace(f"${COLS.index('x_sectors') + 1}", f"${COLS.index('x_sectors') + 1}::jsonb")
    async with store.pool.acquire() as conn:
        async with conn.transaction():
            for i in range(0, len(rows), BATCH):
                await conn.executemany(sql, rows[i:i + BATCH])
            await conn.execute("UPDATE mf_screen SET x_run = $1 WHERE x_run IS DISTINCT FROM $1", run_day)
            await conn.execute("DELETE FROM mf_screen_hold")
            if holds:
                await conn.copy_records_to_table("mf_screen_hold", records=holds, columns=["fkey", "isin", "pct", "as_of"])
            await conn.execute("DELETE FROM mf_cat_flow")
            flow_rows = [(k, m, v["net"], v["aum"], int(v["folios"]) if v["folios"] is not None else None) for k, months in flows.items() for m, v in months.items()]
            if flow_rows:
                await conn.copy_records_to_table("mf_cat_flow", records=flow_rows, columns=["ckey", "month", "net_flow", "aum", "folios"])
    await mf._bump(store, run_day)
    return {"status": "ok", "rows": len(rows), "holdings": len(holds), "flowRows": len(flow_rows), "seconds": round(time.perf_counter() - t0, 1), **stats}
