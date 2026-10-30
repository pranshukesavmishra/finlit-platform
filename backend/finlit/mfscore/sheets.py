"""One configuration per group, exactly as the specification's formula sheets (Section 7), as data. The engine reads these tables and contains no
per-group code. Limits are written worst -> best, as in the spec: the first number scores 0 points, the second 100, scale() draws a line between.
Every limit is a starting value chosen by the designer, not fitted to FinLit's data (spec Section 12: calibrate and back-test before publishing).

Limit forms:
  (worst, best)                         a plain pair
  {"Direct": (w, b), "Regular": (w, b)} by plan (an ETF counts as Direct: it has one plan and no distribution cost)
  ("sym", "k3" | "k1")                  passive / other sheet: (-k * V, +k * V), V sized to the fund's tracking family (spec 7.5)
  ("abs_v",)                            OTHER sheet RET_ABS: (6, 6 + V)
  ("size", floor_cr, best_cr, cap_cr)   SIZE_FIT: min(scale(aum, floor, best), scale(aum, 2 x cap, cap)); cap None = first term only
  "step"                                points come from a step table (exit load, ETF liquidity), not from scale()
  None                                  the metric has no limits (state N for this group)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

PILLARS = ("performance", "risk", "cost", "quality")
PILLAR_NAMES = {"performance": "Performance", "risk": "Risk", "cost": "Cost", "quality": "Quality"}

# group -> pillar weights (Performance, Risk, Cost, Quality), percent of the final score (spec Section 0)
WEIGHTS: Dict[str, Tuple[int, int, int, int]] = {
    "EQ-LARGE": (35, 30, 15, 20), "EQ-BROAD": (35, 30, 15, 20), "EQ-MID": (35, 30, 15, 20), "EQ-SMALL": (35, 30, 15, 20), "EQ-THEME": (35, 30, 15, 20),
    "DB-CASH": (20, 30, 35, 15), "DB-ACCRUAL": (25, 35, 20, 20), "DB-DURATION": (30, 35, 15, 20), "DB-CREDIT": (25, 40, 15, 20),
    "HY-ARB": (20, 20, 45, 15), "HY-CONS": (25, 35, 20, 20), "HY-AGGR": (35, 30, 15, 20), "HY-DYN": (30, 35, 15, 20),
    "SOL": (30, 35, 15, 20), "OT-PASSIVE": (20, 15, 40, 25), "OT-OTHER": (30, 30, 20, 20),
}


@dataclass(frozen=True)
class Metric:
    id: str
    wt: float
    lim: object   # see the module docstring


Sheet = Dict[str, List[Metric]]   # pillar -> metrics
SHEETS: Dict[str, Sheet] = {}


def _build(groups: List[str], rows: Dict[str, List[Tuple]]) -> None:
    """rows: pillar -> [(metric id, weight, [limit of each group in `groups`] | single limit shared by all)]."""
    for gi, g in enumerate(groups):
        sheet = SHEETS.setdefault(g, {p: [] for p in PILLARS})
        for pillar, items in rows.items():
            for mid, wt, lim in items:
                one = lim[gi] if isinstance(lim, list) else lim
                sheet[pillar].append(Metric(mid, wt, one))


def _same(*pairs):
    return list(pairs)


# ---------------------------------------------------------------------------------------------------------------------------- 7.1 Equity
_EQ = ["EQ-LARGE", "EQ-BROAD", "EQ-MID", "EQ-SMALL", "EQ-THEME"]
_build(_EQ, {
    "performance": [
        ("RET_5Y_REL", 25, [(-3, 3), (-4, 4), (-5, 5), (-6, 6), (-8, 8)]),
        ("RET_3Y_REL", 20, [(-3, 3), (-4, 4), (-5, 5), (-6, 6), (-8, 8)]),
        ("RET_1Y_REL", 10, [(-6, 6), (-8, 8), (-10, 10), (-12, 12), (-15, 15)]),
        ("RET_ABS", 15, [(6, 15), (6, 17), (6, 20), (6, 22), (6, 20)]),
        ("SIP_REL", 10, [(-3, 3), (-4, 4), (-5, 5), (-6, 6), (-8, 8)]),
        ("HIT_RATE", 20, (40, 65)),
    ],
    "risk": [
        ("VOL_RATIO", 20, (1.35, 0.75)),
        ("DD_RATIO", 25, (1.4, 0.7)),
        ("DOWN_CAPTURE", 20, (115, 85)),
        ("SHARPE_REL", 20, (-0.5, 0.5)),
        ("WORST12_REL", 15, [(-6, 6), (-8, 8), (-10, 10), (-12, 12), (-15, 15)]),
    ],
    "cost": [
        ("TER_VS_PEER", 50, (1.5, 0.6)),
        ("TER_ABS", 30, {"Regular": (2.4, 0.8), "Direct": (1.4, 0.3)}),
        ("EXIT_LOAD", 20, "step"),
    ],
    "quality": [
        ("AGE", 25, (3, 10)),
        ("SIZE_FIT", 25, [("size", 100, 1000, None), ("size", 100, 1000, 60000), ("size", 100, 1000, 30000), ("size", 100, 1000, 20000), ("size", 100, 1000, 12000)]),
        ("EQUITY_INVESTED", 10, (80, 97)),
        ("TOP10_CONC_REL", 20, (12, -8)),
        ("SECTOR_CONC_REL", 20, [(12, -6), (12, -6), (12, -6), (12, -6), None]),   # N for THEME funds
    ],
})

# ---------------------------------------------------------------------------------------------------------------------------- 7.2 Debt
_DB = ["DB-CASH", "DB-ACCRUAL", "DB-DURATION", "DB-CREDIT"]
_build(_DB, {
    "performance": [
        ("RET_3Y_REL", 25, [(-0.4, 0.4), (-0.8, 0.8), (-1.2, 1.2), (-1.5, 1.5)]),
        ("RET_1Y_REL", 20, [(-0.4, 0.4), (-1, 1), (-2, 2), (-2.5, 2.5)]),
        ("RET_5Y_REL", 10, [(-0.4, 0.4), (-0.8, 0.8), (-1.2, 1.2), (-1.5, 1.5)]),
        ("RET_ABS", 20, [(5, 7.5), (5, 8), (4.5, 9), (5, 10)]),
        ("HIT_RATE", 25, (40, 65)),
    ],
    "risk": [
        ("WORST_MONTH", 30, [(0, 0.4), (-1, 0.3), (-3, -0.3), (-6, -0.5)]),
        ("MDD_ABS", 25, [(0.5, 0), (2, 0), (5, 0.5), (8, 0.5)]),
        ("VOL_RATIO", 15, (1.6, 0.6)),
        ("NEG_MONTHS", 15, [(10, 0), (25, 0), (35, 5), (30, 0)]),
        ("UNDERWATER", 15, [(20, 0), (50, 0), (70, 10), (60, 5)]),
    ],
    "cost": [
        ("TER_VS_PEER", 40, (1.6, 0.5)),
        ("FEE_SHARE", 40, (25, 2)),
        ("EXIT_LOAD", 20, "step"),
    ],
    "quality": [
        ("AGE", 20, (2, 8)),
        ("SIZE_FIT", 25, [("size", 500, 5000, None), ("size", 200, 2000, None), ("size", 200, 2000, None), ("size", 200, 2000, None)]),
        ("TOP10_CONC_REL", 20, (20, -10)),
        ("ASSET_FIT_DEBT", 15, (10, 0)),
        ("RISKOMETER_REL", 20, (1, -1)),
    ],
})

# ---------------------------------------------------------------------------------------------------------------------------- 7.3 Hybrid
_HY = ["HY-ARB", "HY-CONS", "HY-AGGR", "HY-DYN"]
_build(_HY, {
    "performance": [
        ("RET_5Y_REL", 20, [(-0.5, 0.5), (-1.5, 1.5), (-3.5, 3.5), (-3, 3)]),
        ("RET_3Y_REL", 20, [(-0.5, 0.5), (-1.5, 1.5), (-3.5, 3.5), (-3, 3)]),
        ("RET_1Y_REL", 10, [(-0.8, 0.8), (-3, 3), (-7, 7), (-6, 6)]),
        ("RET_ABS", 15, [(5, 7.5), (6, 10), (6, 15), (6, 13)]),
        ("SIP_REL", 10, [(-0.5, 0.5), (-1.5, 1.5), (-3.5, 3.5), (-3, 3)]),
        ("HIT_RATE", 25, (40, 65)),
    ],
    "risk": [
        ("VOL_RATIO", 20, (1.4, 0.7)),
        ("DD_RATIO", 25, (1.4, 0.7)),
        ("DOWN_CAPTURE", 20, (115, 85)),
        ("SHARPE_REL", 20, [(-1, 1), (-0.5, 0.5), (-0.5, 0.5), (-0.5, 0.5)]),
        ("WORST_MONTH", 15, [(-1, 0.3), (-3, -0.3), (-8, -2), (-6, -1)]),
    ],
    "cost": [
        ("TER_VS_PEER", 50, (1.5, 0.6)),
        ("TER_ABS", 30, [{"Direct": (0.9, 0.2), "Regular": (1.4, 0.5)}, {"Direct": (1.4, 0.3), "Regular": (2.3, 0.9)},
                         {"Direct": (1.6, 0.4), "Regular": (2.4, 1.0)}, {"Direct": (1.6, 0.4), "Regular": (2.4, 1.0)}]),
        ("EXIT_LOAD", 20, "step"),
    ],
    "quality": [
        ("AGE", 25, (3, 10)),
        ("SIZE_FIT", 25, ("size", 100, 1000, None)),
        ("TOP10_CONC_REL", 15, [None, (15, -8), (15, -8), (15, -8)]),            # N for ARB: holdings are arbitrage pairs
        ("RISKOMETER_REL", 15, (1, -1)),
        ("ALLOC_FIT", 20, [None, (15, 0), (15, 0), None]),                       # N for ARB and DYN: changing the equity share is the strategy
    ],
})

# ---------------------------------------------------------------------------------------------------------------------------- 7.4 Solution oriented
SHEETS["SOL"] = {
    "performance": [Metric("RET_5Y_REL", 20, (-3, 3)), Metric("RET_3Y_REL", 20, (-3, 3)), Metric("RET_1Y_REL", 5, (-6, 6)), Metric("RET_ABS", 20, (6, 13)),
                    Metric("SIP_REL", 10, (-3, 3)), Metric("HIT_RATE", 25, (40, 65))],
    "risk": [Metric("SHARPE_ABS", 25, (0, 1)), Metric("CALMAR", 20, (0.3, 1.5)), Metric("VOL_RATIO", 15, (1.4, 0.7)), Metric("DD_RATIO", 20, (1.4, 0.7)),
             Metric("DOWN_CAPTURE", 20, (115, 85))],
    "cost": [Metric("TER_VS_PEER", 60, (1.5, 0.6)), Metric("TER_ABS", 40, {"Regular": (2.4, 1.0), "Direct": (1.6, 0.4)}), Metric("EXIT_LOAD", 0, None)],   # N: lock-in
    "quality": [Metric("AGE", 30, (2, 7)), Metric("SIZE_FIT", 25, ("size", 100, 500, None)), Metric("TOP10_CONC_REL", 20, (15, -8)), Metric("RISKOMETER_REL", 25, (1, -1))],
}

# ---------------------------------------------------------------------------------------------------------------------------- 7.5 Others
# The weights in the table of 7.5 are the same for PASSIVE and OTHER; only the limits differ. Written as in the spec (RET_3Y_REL 25, RET_5Y_REL 20).
_OT = ["OT-PASSIVE", "OT-OTHER"]
_build(_OT, {
    "performance": [
        ("RET_3Y_REL", 25, ("sym", "k3")),
        ("RET_5Y_REL", 20, ("sym", "k3")),
        ("RET_1Y_REL", 10, ("sym", "k1")),
        ("RET_ABS", 15, [None, ("abs_v",)]),   # N for passive funds, whose return is set by their index
        ("SIP_REL", 10, ("sym", "k3")),
        ("HIT_RATE", 20, (40, 65)),
    ],
    "risk": [
        ("VOL_RATIO", 20, [(1.10, 0.95), (1.35, 0.75)]),
        ("DD_RATIO", 25, [(1.20, 0.90), (1.4, 0.7)]),
        ("DOWN_CAPTURE", 20, [(105, 95), (115, 85)]),
        ("SHARPE_REL", 20, [(-0.15, 0.15), (-0.5, 0.5)]),
        ("WORST12_REL", 15, ("sym", "k1")),
    ],
    "cost": [
        ("TER_VS_PEER", 50, (1.5, 0.6)),
        ("TER_ABS", 30, [{"Direct": (0.60, 0.05), "Regular": (1.00, 0.10)}, {"Direct": (1.5, 0.2), "Regular": (2.4, 0.8)}]),
        ("EXIT_LOAD", 20, "step"),
    ],
    "quality": [
        ("AGE", 20, (2, 8)),
        ("SIZE_FIT", 25, ("size", 100, 2000, None)),
        ("TOP10_CONC_REL", 15, [None, (15, -8)]),
        ("RISKOMETER_REL", 25, (1, -1)),
        ("ETF_LIQUIDITY", 20, [("step"), None]),
        ("ETF_PREMIUM", 20, [(1.0, 0.05), None]),
    ],
})
# the OTHER sheet marks the ETF-only metrics N; a PASSIVE index fund (not an ETF) gets state N for them in the engine

# family-sized limit multipliers (spec 7.5): k3 for 3 and 5 year and SIP excess, k1 for 1 year and worst-12-month excess
K_FAMILY = {"OT-PASSIVE": {"k3": 0.05, "k1": 0.10}, "OT-OTHER": {"k3": 0.25, "k1": 0.50}}

# Volatility floors used in ratios and Sharpe (spec Section 6, common definitions): percentage points a year
VOL_FLOOR_DEFAULT, VOL_FLOOR_DEBT, VOL_FLOOR_ARB = 1.0, 0.2, 0.5
DD_FLOOR_DEFAULT, DD_FLOOR_DEBT = 0.1, 0.1   # biggest fall floor, pp (spec: 0.1 for non-debt; 0.1 for debt in Z.1)
TER_FLOOR = 0.05
TER_MIN_REAL = 0.01    # a TER below this is a placeholder zero (Kind C)
FROZEN_VOL = 0.01      # VOL_M below this (pp) means a stale or frozen NAV
DOWN_FLOOR = -0.05     # down-capture denominator: never smaller in size than 0.05 pp
RISK_FREE = 6.0        # percent a year, the assumption the head-to-head page already uses
TER_MAX_AGE_DAYS = 45
MIN_PEERS = 8
MIN_PEERS_FAMILY = 3
MIN_GROUP_VALUES = 8   # funds with an actual value needed before a group value is a median (else 50)


def vol_floor(group: str) -> float:
    return VOL_FLOOR_DEBT if group.startswith("DB-") else VOL_FLOOR_ARB if group == "HY-ARB" else VOL_FLOOR_DEFAULT


def metric_ids(group: str) -> List[str]:
    return [m.id for p in PILLARS for m in SHEETS[group][p]]
