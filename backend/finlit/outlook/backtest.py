"""Back-test of the outlook model: forecast from the data that existed at an origin year, compare with what the company reported later. Pure functions;
scripts/outlook_backtest.py loads the stored history and prints the tables. See docs/outlook/BACKTEST.md. Not shown on the site: for the team's review."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median
from typing import Dict, Iterable, List, Optional

from .model import HORIZONS, MIN_PEERS, Hist, PARAMS, SECTOR_COLUMNS, company_inputs, default_weights, forecast, sector_inputs, sector_median


@dataclass
class Company:
    symbol: str
    hist: Hist
    sector: Optional[str] = None
    industry: Optional[str] = None
    size: Optional[str] = None      # size bucket, e.g. Large / Mid / Small


def _peer_growth(kind: str, key: str, peer: Hist, label: str) -> Optional[float]:
    """The peer's own `key` figure as it stood at fiscal year `label` (computed with the same functions as the company's inputs)."""
    if label not in peer.fy:
        return None
    n = peer.fy.index(label) + 1
    mine = company_inputs(kind, peer.upto(n))
    ck = key.replace("sec_", "co_")
    return mine[ck].raw if ck in mine else None


def sector_at(kind: str, company: Company, universe: Iterable[Company], label: str) -> dict:
    """Sector inputs as of `label`: medians of the peers' (same industry, else same sector) own figures at that year."""
    peers, groups = {}, {}
    for key in SECTOR_COLUMNS[kind]:
        pick = lambda match: [_peer_growth(kind, key, c.hist, label) for c in universe if c.symbol != company.symbol and match(c)]  # noqa: E731
        by_ind = [v for v in pick(lambda c: bool(company.industry) and c.industry == company.industry) if v is not None]
        by_sec = [v for v in pick(lambda c: bool(company.sector) and c.sector == company.sector) if v is not None]
        if len(by_ind) >= MIN_PEERS:
            peers[key], groups[key] = by_ind, f"{company.industry} (industry)"
        else:
            peers[key], groups[key] = by_sec, f"{company.sector} (sector)"
    return sector_inputs(kind, peers, groups)


def run(universe: List[Company], kinds=("revenue", "profit"), horizons=("short", "mid", "long"), min_history: int = 3) -> List[dict]:
    """One row per (company, kind, horizon, origin year) where the actual result at the end of the horizon is stored. The forecast uses only years up to
    the origin. Needs `min_history` reported years at the origin (fewer leave the model with too little to work from)."""
    rows: List[dict] = []
    for c in universe:
        for origin in range(min_history - 1, len(c.hist.fy)):
            past = c.hist.upto(origin + 1)
            for kind in kinds:
                for hz in horizons:
                    end = origin + HORIZONS[hz]["years"]
                    if end >= len(c.hist.fy):
                        continue
                    actual = (c.hist.revenue if kind == "revenue" else c.hist.profit)[end]
                    sec = sector_at(kind, c, universe, c.hist.fy[origin])
                    res = forecast(kind, past, hz, default_weights(kind, hz), sec)
                    fc = res["forecast"]
                    if not fc["available"] or actual is None:
                        continue
                    est = fc["years"][-1]["valueCr"]
                    rows.append({"symbol": c.symbol, "sector": c.sector or "Unknown", "size": c.size or "Unknown", "kind": kind, "horizon": hz, "origin": c.hist.fy[origin],
                                 "target": c.hist.fy[end], "estimate": est, "actual": actual, "error": est - actual,
                                 "ape": abs(est - actual) / abs(actual) * 100 if actual > 0 else None,
                                 "sectorInputs": sum(1 for p in PARAMS[kind] if p[2] == "sector" and sec[p[0]].value is not None)})
    return rows


def summarise(rows: List[dict], by: str = "horizon") -> List[dict]:
    """MAE (crore), MAPE and median APE (percent), and mean signed error as a share (bias), with the count, per `by` ('horizon', 'sector', 'size') within kind."""
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["kind"], r["horizon"] if by == "horizon" else (r["horizon"], r[by]))].append(r)
    out = []
    for (kind, g), rs in sorted(groups.items(), key=lambda kv: str(kv[0])):
        apes = [r["ape"] for r in rs if r["ape"] is not None]
        out.append({"kind": kind, "group": g, "n": len(rs), "maeCr": round(mean(abs(r["error"]) for r in rs), 1),
                    "mapePct": round(mean(apes), 1) if apes else None, "medianApePct": round(median(apes), 1) if apes else None,
                    "biasPct": round(mean((r["error"] / r["actual"]) * 100 for r in rs if r["actual"] > 0), 1) if apes else None})
    return out


def sample_ok(n: int, floor: int = 30) -> bool:
    return n >= floor and math.isfinite(n)
