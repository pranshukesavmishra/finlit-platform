"""Plain data carried through the scoring engine: one input record per fund, one result per metric, one score per fund."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Sequence, Tuple

STATES = ("A", "Z", "S", "F", "N")
STATE_TEXT = {"A": "Actual", "Z": "Negative", "S": "Substituted", "F": "Filled with the group value", "N": "Not applicable"}


@dataclass
class FundIn:
    """Everything the model reads about one fund. Every field may be None: a gap is shown as a gap, never invented."""
    key: str                                   # 'mf:<AMFI code>' or 'etf:<SYMBOL>'
    kind: str                                  # 'mf' | 'etf'
    name: str
    plan: str                                  # Direct | Regular | ETF
    group: str                                 # EQ-LARGE ... OT-OTHER (finlit.mfscore.groups)
    sub: str                                   # sub-category key (finlit.mf.classify)
    sub_label: str = ""
    category: str = ""                         # AMFI's own category text
    code: Optional[int] = None
    symbol: Optional[str] = None
    amc: str = ""
    isin: Optional[str] = None
    nav_date: Optional[date] = None
    mdays: Sequence[int] = ()                  # month-end NAV dates (ordinals), oldest first, latest NAV last
    mnavs: Sequence[float] = ()
    r1y: Optional[float] = None                # percent; 3 and 5 year are a year (CAGR); ETFs: price returns without dividends
    r3y: Optional[float] = None
    r5y: Optional[float] = None
    sip3y: Optional[float] = None
    sip5y: Optional[float] = None
    mdd: Optional[float] = None                # stored month-end fall over 3 years (0 or negative)
    aum_lakh: Optional[float] = None           # family total, rupees lakh
    ter: Optional[float] = None                # percent a year, the fund's own plan
    ter_date: Optional[date] = None
    launch: Optional[date] = None
    exit_text: Optional[str] = None
    benchmark: Optional[str] = None
    risk_text: Optional[str] = None
    has_portfolio: bool = False
    equity_pct: Optional[float] = None
    other_pct: Optional[float] = None
    split_sum: Optional[float] = None          # what the asset split adds up to (percent)
    top10: Optional[float] = None
    sector_top: Optional[float] = None
    turnover_cr: Optional[float] = None        # ETF: average traded value, rupees crore a day
    premium: Optional[float] = None            # ETF: price against NAV, percent
    traded_on_nav_date: Optional[bool] = None  # ETF: did it trade on the NAV's own day
    family_key: Optional[str] = None           # passive: the tracking family (index)


@dataclass
class Res:
    """One metric of one fund: state, the figures behind it and its points."""
    id: str
    pillar: str
    state: str
    value: Optional[float] = None              # the measured quantity as the spec defines it (excess, ratio, difference, level ...)
    own: Optional[float] = None                # the fund's own figure the value was built from
    peer: Optional[float] = None               # the peer median it was measured against
    peer_n: int = 0
    scope: Optional[str] = None                # 'sub' | 'grp' | 'fam' | None
    points: Optional[float] = None
    limits: Optional[Tuple[float, float]] = None
    wt: float = 0.0                            # weight inside its pillar (sheet)
    weight: float = 0.0                        # share of the final score, percent (after N is dropped and the pillar re-divided)
    gv: Optional[float] = None                 # group value used when the state is F
    why: Optional[str] = None                  # cause code for F, N and S
    rule: Optional[str] = None                 # Appendix Z rule name when a zero was handled (Kind B or C)
    cred: float = 1.0


@dataclass
class Score:
    key: str
    kind: str
    group: str
    plan: str
    status: str = "NOT RATED"                  # RATED | PROVISIONAL | NOT RATED
    final: Optional[float] = None
    raw_final: Optional[float] = None
    cap: Optional[str] = None                  # text when the weak-fund cap lowered the score
    label: Optional[str] = None
    pillars: Dict[str, Optional[float]] = field(default_factory=dict)
    pillar_flags: Dict[str, bool] = field(default_factory=dict)   # pillar had every metric N: neutral 50
    confidence: Optional[float] = None
    months: int = 0
    reason: Optional[str] = None               # why NOT RATED
    flags: List[str] = field(default_factory=list)
    metrics: List[Res] = field(default_factory=list)
    peer_kind: Optional[str] = None            # sub | grp | fam | None: the widest peer set any metric needed first
    peer_n: int = 0
    rank: Optional[int] = None
    rank_of: Optional[int] = None
    rank_scope: Optional[str] = None
    percentile: Optional[float] = None
    reasons: Dict[str, Any] = field(default_factory=dict)
    counters: Dict[str, int] = field(default_factory=dict)       # Appendix Z.3: zero-handling rules hit by this fund
    near_identical: bool = False
