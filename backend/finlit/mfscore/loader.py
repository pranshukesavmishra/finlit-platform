"""Database rows -> FundIn. The only module that knows our tables (see docs/mf-score/DATA-MAP.md for every input, its source and its gaps).

Two rules of the model are applied at read time because the feeds write a placeholder 0 where a figure was not reported (spec Appendix Z, Kind C): the
scoring engine treats TER below 0.01, AUM of 0, a top-10 share of 0, an equity share of 0 and an empty asset split as missing and counts every hit
(Z.3, rule 1). Nothing is changed in the stored feed rows."""

from __future__ import annotations

import json
import logging
from bisect import bisect_right
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .groups import ETF_SUBS, group_of, tracking_key
from .model import FundIn

log = logging.getLogger("finlit.mfscore")

MF_COLS = """s.code, s.name, s.amc, s.category, s.plan, s.family, s.isin, s.nav_date, s.r1y, s.r3y, s.r5y, s.sip3y, s.sip5y, s.mdd3y_m, s.aum_lakh, s.ter, s.ter_date,
             f.launch_date, m.days, m.navs"""
KEEP_MONTHS = 63


def _day(d) -> int:
    return d.toordinal()


async def load_facts(conn) -> Dict[str, Dict[str, Any]]:
    """family -> {exitload: text, benchmark: text, risk: text} from disclosure_facts (a few thousand small rows)."""
    out: Dict[str, Dict[str, Any]] = {}
    for r in await conn.fetch("SELECT fkey, kind, value FROM disclosure_facts WHERE kind IN ('exitload', 'benchmark', 'risk')"):
        v = json.loads(r["value"]) if isinstance(r["value"], str) else r["value"]
        d = out.setdefault(r["fkey"], {})
        if r["kind"] == "exitload":
            d["exitload"] = (v or {}).get("text")
        elif r["kind"] == "benchmark":
            d["benchmark"] = (v or {}).get("name")
        elif r["kind"] == "risk":
            d["risk"] = (v or {}).get("scheme")
    return out


def portfolio_summary(holdings: Iterable[Sequence[Any]]) -> Dict[str, Optional[float]]:
    """The figures the model reads from one monthly portfolio: asset split (equity, other, sum of all classes), the top-10 share of net assets (cash left out,
    as the fund page's own summary does) and the share of the largest sector among the equity rows. Holdings are [name, isin, sector, class e|d|c|o, pct, qty, value]."""
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
    return {"equity_pct": split["e"], "other_pct": split["o"], "split_sum": sum(split.values()), "top10": sum(sorted(pcts, reverse=True)[:10]),
            "sector_top": max(sectors.values()) if sectors else 0.0}


async def load_portfolios(conn, families: Optional[set] = None) -> Dict[str, Dict[str, Any]]:
    """family -> portfolio summary of the latest month-end, read through a cursor so the holdings of 2,000 families are never in memory together."""
    out: Dict[str, Dict[str, Any]] = {}
    async with conn.transaction():
        async for r in conn.cursor("SELECT DISTINCT ON (fkey) fkey, holdings, benchmark FROM disclosure_portfolios ORDER BY fkey, as_of DESC", prefetch=50):
            if families is not None and r["fkey"] not in families:
                continue
            raw = json.loads(r["holdings"]) if isinstance(r["holdings"], str) else r["holdings"]
            s = portfolio_summary(raw)
            s["benchmark"] = r["benchmark"]
            out[r["fkey"]] = s
    return out


def _apply_family(f: FundIn, facts: Dict[str, Any], port: Optional[Dict[str, Any]]) -> None:
    f.exit_text = facts.get("exitload")
    f.risk_text = facts.get("risk")
    f.benchmark = facts.get("benchmark") or (port or {}).get("benchmark")
    if port:
        f.has_portfolio = True
        f.equity_pct, f.other_pct, f.split_sum, f.top10, f.sector_top = port["equity_pct"], port["other_pct"], port["split_sum"], port["top10"], port["sector_top"]


async def load_mf(conn, codes: Optional[Sequence[int]] = None, limit: Optional[int] = None) -> Tuple[List[FundIn], Dict[int, Any]]:
    """Every active Growth scheme with a Direct or Regular plan, apart from ETFs (scored from their exchange prices). Returns (funds, family by code)."""
    from ..mf import classify
    where = "s.active AND s.option_class = 'Growth' AND s.nav IS NOT NULL AND s.plan IN ('Direct', 'Regular')"
    args: List[Any] = []
    if codes:
        args.append(list(codes))
        where += f" AND s.code = ANY(${len(args)}::int[])"
    sql = f"SELECT {MF_COLS} FROM mf_schemes s LEFT JOIN mf_monthly m ON m.code = s.code LEFT JOIN mf_facts f ON f.code = s.code WHERE {where} ORDER BY s.code"  # nosec B608 - fixed column list and filters; values are bound parameters
    if limit:
        sql += f" LIMIT {int(limit)}"
    facts = await load_facts(conn)
    rows = await conn.fetch(sql, *args)
    ports = await load_portfolios(conn, {r["family"] for r in rows})
    funds: List[FundIn] = []
    fam: Dict[int, str] = {}
    for r in rows:
        tab, sub, label = classify(r["category"])
        if sub in ETF_SUBS:
            continue
        mtype, group = group_of(tab, sub)
        f = FundIn(key=f"mf:{r['code']}", kind="mf", code=r["code"], name=r["name"], amc=r["amc"], category=r["category"], plan=r["plan"], group=group, sub=sub, sub_label=label,
                   isin=r["isin"], nav_date=r["nav_date"], r1y=r["r1y"], r3y=r["r3y"], r5y=r["r5y"], sip3y=r["sip3y"], sip5y=r["sip5y"], mdd=r["mdd3y_m"],
                   aum_lakh=r["aum_lakh"], ter=r["ter"], ter_date=r["ter_date"], launch=r["launch_date"])
        if r["days"]:
            f.mdays, f.mnavs = [_day(d) for d in r["days"][-KEEP_MONTHS:]], list(r["navs"][-KEEP_MONTHS:])
        _apply_family(f, facts.get(r["family"], {}), ports.get(r["family"]))
        if group == "OT-PASSIVE":
            f.family_key = tracking_key(f.benchmark, r["name"], r["amc"])
        funds.append(f)
        fam[r["code"]] = r["family"]
    return funds, fam


def month_series(dates: Sequence[date], closes: Sequence[float], break_date: Optional[date] = None) -> Tuple[List[int], List[float]]:
    """Daily closes -> the last close of each calendar month (the latest close included), newest KEEP_MONTHS months; closes before a break are left out."""
    days: List[int] = []
    navs: List[float] = []
    for d, v in zip(dates, closes):
        if break_date and d < break_date:
            continue
        o = d.toordinal()
        if days and date.fromordinal(days[-1]).replace(day=1) == d.replace(day=1):
            days[-1], navs[-1] = o, v
        else:
            days.append(o)
            navs.append(v)
    return days[-KEEP_MONTHS:], navs[-KEEP_MONTHS:]


async def load_etf(conn, symbols: Optional[Sequence[str]] = None, limit: Optional[int] = None) -> List[FundIn]:
    """Active ETFs: exchange closes from etf_history stand in for NAVs (price returns, no dividends), traded value and NAV premium from etf_funds, and the
    fund facts (expense ratio, size, launch date, risk-o-meter, benchmark) from the AMFI scheme found by ISIN."""
    from ..mf import fall_monthly, sip_return
    where, args = "e.active", []
    if symbols:
        args.append(list(symbols))
        where += f" AND e.symbol = ANY(${len(args)}::text[])"
    sql = f"""SELECT e.symbol, e.isin, e.display_name, e.fund_house, e.category, e.ret_1y, e.cagr_3y, e.cagr_5y, e.avg_turnover, e.nav, e.nav_date, e.nav_premium, e.break_date,
                     h.dates, h.closes, h.volumes
              FROM etf_funds e LEFT JOIN etf_history h ON h.symbol = e.symbol WHERE {where} ORDER BY e.symbol"""  # nosec B608 - fixed text; values are bound parameters
    if limit:
        sql += f" LIMIT {int(limit)}"
    rows = await conn.fetch(sql, *args)
    isins = [r["isin"] for r in rows if r["isin"]]
    kin = {}
    if isins:
        for k in await conn.fetch("""SELECT s.isin, s.isin_reinvest, s.code, s.family, s.ter, s.ter_date, s.aum_lakh, f.launch_date FROM mf_schemes s LEFT JOIN mf_facts f ON f.code = s.code
                                     WHERE s.isin = ANY($1::text[]) OR s.isin_reinvest = ANY($1::text[])""", isins):
            kin[k["isin"]] = k
            if k["isin_reinvest"]:
                kin.setdefault(k["isin_reinvest"], k)
    facts = await load_facts(conn)
    ports = await load_portfolios(conn, {k["family"] for k in kin.values()})
    funds: List[FundIn] = []
    for r in rows:
        k = kin.get(r["isin"])
        dates = list(r["dates"] or [])
        closes = list(r["closes"] or [])
        days, navs = month_series(dates, closes, r["break_date"])
        f = FundIn(key=f"etf:{r['symbol']}", kind="etf", symbol=r["symbol"], name=r["display_name"], amc=r["fund_house"] or "", category="Exchange traded fund", plan="ETF",
                   group="OT-PASSIVE", sub="etf", sub_label=r["category"] or "ETF", isin=r["isin"], nav_date=dates[-1] if dates else r["nav_date"], mdays=days, mnavs=navs,
                   r1y=r["ret_1y"], r3y=r["cagr_3y"], r5y=r["cagr_5y"], turnover_cr=(r["avg_turnover"] / 1e7) if r["avg_turnover"] is not None else None, premium=r["nav_premium"])
        if days:
            end = days[-1]
            f.sip3y, f.sip5y = sip_return(days, navs, end, navs[-1], 36), sip_return(days, navs, end, navs[-1], 60)
            f.mdd = fall_monthly(days, navs, end, navs[-1])
        if r["nav_date"] and r["nav_premium"] is not None and dates:
            i = bisect_right(dates, r["nav_date"]) - 1
            vols = list(r["volumes"] or [])
            j = i - (len(dates) - len(vols))
            f.traded_on_nav_date = bool(i >= 0 and dates[i] == r["nav_date"] and (j < 0 or j >= len(vols) or (vols[j] or 0) > 0))
        if k:
            f.code = None
            f.aum_lakh, f.ter, f.ter_date, f.launch = k["aum_lakh"], k["ter"], k["ter_date"], k["launch_date"]
            _apply_family(f, facts.get(k["family"], {}), ports.get(k["family"]))
        f.family_key = tracking_key(f.benchmark, r["display_name"], r["fund_house"])
        funds.append(f)
    return funds
