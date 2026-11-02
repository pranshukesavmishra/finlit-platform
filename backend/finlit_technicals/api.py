"""The two indicators as functions that return JSON-ready dicts for the website.

    score(symbol, source, ...)        ST/LT Score Breakdown & Peers v1.2: scores, every component, trend alignment, peer row
    peer_label(symbol, source, ...)   Leader & Laggard vs Peers v1.0: label, rank, peers table, weekly history

`source` is anything with daily(symbol) and index(code) (see sources.py). Every value in the result is a plain
str / int / float / bool / None / list / dict, so json.dumps works as is (missing numbers are None, not NaN).
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from . import peers as PR
from . import stlt as S
from .peers import norm_symbol

CAP_WORDS = {"large": 1, "mid": 2, "small": 3, 1: 1, 2: 2, 3: 3}
BAND_NAMES = S.BAND_NAMES
GROUP_PRESETS = {"auto": "Auto", "it": "IT services", "pharma": "Pharmaceuticals", "pvtbank": "Private sector banks",
                 "psubank": "Public sector banks", "autosector": "Auto sector", "industry": "TradingView industry",
                 "sector": "TradingView sector (wider)", "custom": "Custom list"}
GROUP_KINDS = {1: "spec group", 2: "spec group", 3: "spec group", 4: "spec group", 5: "spec group",
               6: "industry", 7: "sector", 8: "industry", 0: "custom"}
ST_METHOD = ("15 components, weights 10+8+6+8+4+8+4+10+5+3+4+10+8+6+6 = 100. Sector RS (4) and value migration (6) drop "
             "out of the divisor when switched off. The first three are multiplied by the trend factor: ADX above 25 ×1, "
             "below 20 ×0.5, otherwise ×0.75. Points = weight × signal × 100 / weights in use.")
LT_METHOD = ("14 components, weights 7+5+5+2+5+5+12+5+5+18+8+7+6+10 = 100. Sector RS (8) drops out of the divisor when "
             "switched off. In Stage 3 or Stage 4 the score is capped at +19 (Neutral).")
SCORE_DISCLAIMER = "Describes the chart's technical picture; not investment advice."
PEER_DISCLAIMER = "Describes past price performance over 12 months; not a recommendation."


# ─── helpers ─────────────────────────────────────────────────────────────────────────────────────────────
def jsonable(x: Any) -> Any:
    """NaN / inf -> None, numpy and pandas scalars -> Python, dates -> 'YYYY-MM-DD'."""
    if isinstance(x, dict):
        return {str(k): jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [jsonable(v) for v in x]
    if isinstance(x, (pd.Timestamp, datetime, date, np.datetime64)):
        return pd.Timestamp(x).strftime("%Y-%m-%d")
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        v = float(x)
        return None if (math.isnan(v) or math.isinf(v)) else v
    return x


def _r(x: Optional[float], nd: int = 2) -> Optional[float]:
    if x is None:
        return None
    x = float(x)
    return None if (math.isnan(x) or math.isinf(x)) else round(x, nd)


def _pts(x: Optional[float]) -> Optional[float]:
    """A return difference as percentage points (0.299 -> 29.9)."""
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x) * 100, 2)


@lru_cache(maxsize=4)
def _db_from(path: str) -> PR.PeerDB:
    return PR.PeerDB.from_groups(json.loads(Path(path).read_text(encoding="utf-8")))


DEFAULT_GROUPS = str(Path(__file__).with_name("data") / "peer_groups.json")


def peer_db(path: Optional[str] = None) -> PR.PeerDB:
    """The peer lists (data/peer_groups.json, or your own file in the same format)."""
    return _db_from(path or DEFAULT_GROUPS)


def canonical(symbol: str, db: Optional[PR.PeerDB] = None) -> str:
    """The symbol as the peer lists spell it: bajaj-auto -> BAJAJ_AUTO, NSE:M_M -> M&M."""
    s = symbol.strip().upper().split(":")[-1]
    key = norm_symbol(s)
    for _, _, lst in (db or peer_db()).entries:
        for x in lst:
            if norm_symbol(x) == key:
                return x.upper()
    return s


def _cap_class(cap: Any) -> Optional[int]:
    if cap is None or cap == "":
        return None
    v = CAP_WORDS.get(cap if isinstance(cap, int) else str(cap).strip().lower())
    if v is None:
        raise ValueError(f"cap must be large, mid or small (got {cap!r})")
    return v


def _shares(mcap_cr: Optional[float], last_close: float) -> Optional[float]:
    """Share count from a market cap in Rs crore (the indicators recompute the cap on every bar from shares x close)."""
    if mcap_cr is None or not (mcap_cr > 0) or not (last_close > 0):
        return None
    return float(mcap_cr) * 1e7 / float(last_close)


def _load_stock(source, symbol: str) -> pd.DataFrame:
    df = source.daily(symbol)
    if df is None or len(df) == 0:
        raise LookupError(f"{symbol}: no daily prices from the source")
    return df


# ─── ST / LT scores ──────────────────────────────────────────────────────────────────────────────────────
def score_dict(res: S.StltResult) -> Dict[str, Any]:
    def rows(lst):
        return [{"key": r.key, "name": r.name, "reading": r.reading, "signal": _r(r.signal, 2) if r.on else None,
                 "weight": int(r.weight), "points": _r(r.points, 2) if r.on else None, "on": bool(r.on), "how": r.tip}
                for r in lst]

    cells = [{"st_band": BAND_NAMES[sb], "lt_band": BAND_NAMES[lb], "code": S.alignment_code(sb, lb),
              "label": S.alignment(sb, lb), "current": sb == res.s_band and lb == res.l_band}
             for sb in (1, 0, -1) for lb in (1, 0, -1)]
    out = {
        "indicator": "ST/LT Score Breakdown & Peers v1.2",
        "symbol": res.symbol,
        "date": res.date,
        "close": _r(res.close, 2),
        "bars": res.bars,
        "benchmark": res.bench_name,
        "short_term": {
            "score": _r(res.st_score, 2), "display": S.pround(res.st_score), "rating": S.rate(res.st_score),
            "rating_code": S.rating_code(res.st_score), "band": BAND_NAMES[res.s_band], "band_code": res.s_band,
            "raw": _r(res.st_raw, 2), "divisor": int(res.st_div),
            "trend_factor": {"adx": _r(res.adx, 1), "multiplier": _r(res.trend_mult, 2)},
            "method": ST_METHOD, "components": rows(res.st_rows),
        },
        "long_term": {
            "score": _r(res.lt_score, 2), "display": S.pround(res.lt_score), "rating": S.rate(res.lt_score),
            "rating_code": S.rating_code(res.lt_score), "band": BAND_NAMES[res.l_band], "band_code": res.l_band,
            "raw": _r(res.lt_raw, 2), "divisor": int(res.lt_div),
            "uncapped": _r(res.lt_norm, 2), "capped": bool(res.gated), "stage": int(res.stage),
            "method": LT_METHOD, "components": rows(res.lt_rows),
        },
        "trend_alignment": {
            "label": res.alignment, "code": S.alignment_code(res.s_band, res.l_band),
            "st_band": BAND_NAMES[res.s_band], "lt_band": BAND_NAMES[res.l_band],
            "how": f"Short-term {S.f_p(res.st_score)} ({BAND_NAMES[res.s_band]}) × long-term {S.f_p(res.lt_score)} "
                   f"({BAND_NAMES[res.l_band]}) = {res.alignment}",
            "rule": "Each score falls in a band: +20 or more = Positive, −20 or less = Negative, in between = Neutral. "
                    "The two bands together describe how the short-term and long-term trends line up.",
            "cells": cells,
        },
        "notes": list(res.notes),
        "disclaimer": SCORE_DISCLAIMER,
    }
    return jsonable(out)


def _benchmarks(source, p: S.StltParams, cap_class: Optional[int], shares: Optional[float]) -> Dict[str, pd.DataFrame]:
    need = {S.BENCH_SYMS.get(p.bench_choice, "NSE:CNX500")}
    if p.bench_choice == "auto":
        if cap_class:
            need.add({1: "NSE:NIFTY", 2: "NSE:CNXMIDCAP", 3: "NSE:CNXSMALLCAP"}[cap_class])
        elif shares:
            need |= {"NSE:NIFTY", "NSE:CNXMIDCAP", "NSE:CNXSMALLCAP"}
    out = {}
    for code in sorted(need):
        df = source.index(code)
        if df is not None and len(df):
            out[code] = df
    return out


def score(symbol: str, source, *, market_cap_cr: Optional[float] = None, cap: Any = None, bench: str = "auto",
          peers: bool = True, industry: Optional[str] = None, sector: Optional[str] = None,
          peer_list: Optional[str] = None, group: Optional[str] = None, peer_caps: Optional[Dict[str, float]] = None,
          params: Optional[S.StltParams] = None, groups_file: Optional[str] = None, cache: Optional[dict] = None) -> Dict[str, Any]:
    """ST / LT scores, their calculation and the trend alignment for the last bar, plus the peer row (as in v1.2).

    market_cap_cr   the stock's market cap in Rs crore (Auto benchmark: >= 1,07,000 Nifty 50, >= 32,800 Midcap 100,
                    else Smallcap 100; unknown = Nifty 500), or
    cap             "large" / "mid" / "small" to set the bucket directly
    bench           "auto" | "nifty500" | "nifty50" | "midcap100" | "smallcap100"
    peers           include the Leader / In line / Laggard row (v1.2 ranks up to 30 peers)
    industry, sector, peer_list, group, peer_caps: see peer_label()
    """
    db = peer_db(groups_file)
    symbol = canonical(symbol, db)
    stock = _load_stock(source, symbol)
    cap_class = _cap_class(cap)
    last_close = float(pd.to_numeric(stock["close"], errors="coerce").dropna().iloc[-1])
    shares = _shares(market_cap_cr, last_close)
    p = params or S.StltParams(bench_choice=bench)
    res = S.compute(stock, _benchmarks(source, p, cap_class, shares), p, symbol=symbol, shares=shares, cap_class=cap_class)
    out = score_dict(res)
    if peers:
        pr = _peer_result(symbol, stock, source, db, max_peers=30, market_cap_cr=market_cap_cr, cap_class=cap_class,
                          industry=industry, sector=sector, peer_list=peer_list, group=group, peer_caps=peer_caps, cache=cache)
        out["peers"] = peer_dict(pr, table=None, history_weeks=0)
    return out


# ─── Leader / In line / Laggard ──────────────────────────────────────────────────────────────────────────
def _peer_result(symbol: str, stock: pd.DataFrame, source, db: PR.PeerDB, *, max_peers: int, market_cap_cr, cap_class,
                 industry, sector, peer_list, group, peer_caps, cache) -> PR.PeerResult:
    pp = PR.PeerParams(max_peers=max_peers)
    if group:
        if group.lower() not in GROUP_PRESETS:
            raise ValueError(f"group must be one of {', '.join(GROUP_PRESETS)}")
        pp.preset = GROUP_PRESETS[group.lower()]
    if peer_list:
        pp.custom = peer_list
        if not group:
            pp.preset = "Custom list"
    grp = PR.resolve(symbol, db, pp, industry=industry, sector=sector)
    daily = {}
    for s in grp.symbols[1:]:
        df = source.daily(s.split(":")[-1])
        if df is not None and len(df):
            daily[s] = df
    sector_df = source.index(grp.sec_sym) if grp.sec_sym else None
    last_close = float(pd.to_numeric(stock["close"], errors="coerce").dropna().iloc[-1])
    sh0 = _shares(market_cap_cr, last_close)
    if cap_class is not None:
        need = [PR.MKT_SYMS[cap_class][0]]
    elif sh0:
        need = [PR.MKT_SYMS[k][0] for k in (1, 2, 3)]
    else:
        need = [PR.MKT_SYMS[0][0]]
    market = {}
    for code in need:
        df = source.index(code)
        if df is not None and len(df):
            market[code] = df
    shares: Dict[str, float] = {}
    if sh0:
        shares[grp.symbols[0]] = sh0
    for s, mc in (peer_caps or {}).items():
        key = "NSE:" + canonical(s, db)
        df = daily.get(key)
        if df is not None and key != grp.symbols[0]:
            v = _shares(mc, float(pd.to_numeric(df["close"], errors="coerce").dropna().iloc[-1]))
            if v:
                shares[key] = v
    return PR.compute(stock, daily, grp, pp, sector_daily=sector_df, market_daily=market, shares=shares,
                      cap_class=cap_class, cache=cache)


def peer_dict(res: PR.PeerResult, table: Optional[str] = "top10", history_weeks: int = 52) -> Dict[str, Any]:
    """table: "top10" (top 10 + this stock), "all", or None; history_weeks: weekly runs to include (0 = none)."""
    r = res.last
    g = res.group
    d = res.direction
    out: Dict[str, Any] = {
        "indicator": "Leader & Laggard vs Peers v1.0" if res.params.max_peers > 30 else "ST/LT Score Breakdown & Peers v1.2 (peer row)",
        "symbol": res.symbol,
        "label": res.chip,
        "label_code": res.pub,
        "this_week": PR.LABELS[r.raw] if r is not None and r.state == 0 else None,
        "pending": res.pending() or None,
        "since": res.pub_since,
        "changed_last_run": bool(res.changed),
        "status": res.line(),
        "state": None if r is None else int(r.state),
        "group": {"name": g.name, "kind": GROUP_KINDS.get(g.idx, "custom"), "peers_listed": len(g.symbols) - 1,
                  "industry": g.industry or None, "sector": g.sector or None},
        "week_ranked": None if r is None else r.ref_week,
        "rank": None if r is None else r.rank,
        "ranked": None if r is None else r.ranked,
        "leader_slots": None if r is None else r.k,
        "direction": {1: "gaining", -1: "weakening"}.get(d, "steady") if r is not None and r.state == 0 else None,
        "benchmarks": {"sector": None if r is None else r.bench_name, "sector_is_peer_average": bool(r is not None and r.bench_name == "peer average"),
                       "market": None if r is None else r.mkt_name},
        "relative_return_pts": {
            "vs_sector_3m": None if r is None else _pts(r.rel13),
            "vs_sector_6m": None if r is None else _pts(r.rel26),
            "vs_sector_12m": None if r is None else _pts(r.rel52),
            "vs_market_12m": None if r is None else _pts(r.rel52m),
        },
        "reliability": PR.rel_text(g.idx),
        "runs_last_52": {"leader": res.counts()[1], "in_line": res.counts()[0], "laggard": res.counts()[-1],
                         "runs": len(res.hist)},
        "rules": "Relative return = stock return minus index return over 13, 26 and 52 weeks. Peers ranked on the 52-week "
                 "figure vs the sector index (ties: 26 weeks, then market cap). k = ceil(30% of ranked peers). Leader = rank <= k "
                 "and 52-week figure above 0; Laggard = rank > n - k and below 0; otherwise In line. Gaining / weakening = "
                 "13-week figure at least +5 / at most -5 pts. A new label must come out 2 weekly runs in a row.",
        "notes": list(res.notes),
        "disclaimer": PEER_DISCLAIMER,
    }
    if table and r is not None:
        rows = r.rows
        ordv = PR.ordered(rows)
        n_r = len(ordv)
        kk = math.ceil(res.params.share / 100.0 * n_r)
        tbl: List[Dict[str, Any]] = []
        for k, i in enumerate(ordv):
            if table == "all" or k < 10 or i == 0:
                x52 = rows[i].r52 - r.b52
                lab = 1 if (k + 1 <= kk and x52 > 0) else -1 if (k + 1 > n_r - kk and x52 < 0) else 0
                shown = res.pub if (i == 0 and res.params.stable and res.pub is not None) else lab
                tbl.append({"rank": k + 1, "symbol": rows[i].symbol.split(":")[-1], "is_self": i == 0,
                            "status": PR.LABELS[shown], "this_week": PR.LABELS[lab],
                            "vs_sector_12m": _pts(x52), "vs_sector_3m": _pts(rows[i].r13 - r.b13),
                            "vs_market_12m": _pts(rows[i].r52 - r.m52)})
        out["table"] = tbl
        out["table_more"] = max(0, n_r - len(tbl))
        out["not_ranked"] = [{"symbol": x.symbol.split(":")[-1], "is_self": j == 0, "reason": PR._why(x)}
                             for j, x in enumerate(rows) if x.status != 0]
    if history_weeks:
        out["history"] = [{"week": h.ref_week, "run_date": h.date, "label": PR.LABELS[h.pub],
                           "this_week": PR.LABELS[h.raw] if h.state == 0 else None, "rank": h.rank, "ranked": h.ranked,
                           "vs_sector_12m": _pts(h.rel52), "vs_market_12m": _pts(h.rel52m), "vs_sector_3m": _pts(h.rel13)}
                          for h in res.runs[-history_weeks:]]
    return jsonable(out)


def peer_label(symbol: str, source, *, market_cap_cr: Optional[float] = None, cap: Any = None,
               industry: Optional[str] = None, sector: Optional[str] = None, peer_list: Optional[str] = None,
               group: Optional[str] = None, peer_caps: Optional[Dict[str, float]] = None, max_peers: int = 37,
               table: Optional[str] = "top10", history_weeks: int = 52, groups_file: Optional[str] = None,
               cache: Optional[dict] = None) -> Dict[str, Any]:
    """Leader / In line / Laggard vs industry peers (Leader & Laggard vs Peers v1.0).

    market_cap_cr / cap   the stock's size bucket picks the market index (Nifty 50 / Midcap 150 / Smallcap 250;
                          unknown = Nifty 500)
    industry, sector      TradingView industry / sector names, for a stock outside the peer lists (e.g. "Steel")
    peer_list             your own peers, "TCS,INFY,WIPRO" (used as the group unless `group` is given)
    group                 auto | it | pharma | pvtbank | psubank | autosector | industry | sector | custom
    peer_caps             {symbol: market cap Rs crore} for the peers (only breaks exact ties)
    max_peers             37 as in Leader & Laggard v1.0 (30 in ST/LT Breakdown v1.2)
    table                 "top10", "all" or None;  history_weeks: weekly runs to return (the indicator's lines)
    """
    db = peer_db(groups_file)
    symbol = canonical(symbol, db)
    stock = _load_stock(source, symbol)
    res = _peer_result(symbol, stock, source, db, max_peers=max_peers, market_cap_cr=market_cap_cr,
                       cap_class=_cap_class(cap), industry=industry, sector=sector, peer_list=peer_list, group=group,
                       peer_caps=peer_caps, cache=cache)
    return peer_dict(res, table=table, history_weeks=history_weeks)
