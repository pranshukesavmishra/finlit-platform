"""Category -> type -> group (spec Section 5) and the tracking family of index funds and ETFs (Section 7.5).

The category rule table is the one already in finlit.mf.classify (both spellings AMFI uses): it gives a tab and a sub-category key, and this
module maps those to the spec's groups. Nothing here reads a database."""

from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional, Tuple

TYPE_OF_TAB = {"equity": "Equity", "debt": "Debt", "hybrid": "Hybrid", "solution": "Solution Oriented", "other": "Others"}

# sub-category key (finlit.mf.classify) -> group. Anything not listed falls to the default of its tab (spec: Equity BROAD, Debt ACCRUAL, Hybrid AGGR, Others OTHER).
_EQUITY = {"large-cap": "EQ-LARGE", "mid-cap": "EQ-MID", "small-cap": "EQ-SMALL", "sectoral-thematic": "EQ-THEME"}
_DEBT = {"overnight": "DB-CASH", "liquid": "DB-CASH", "money-market": "DB-CASH", "ultra-short": "DB-CASH", "low-duration": "DB-CASH",
         "short-duration": "DB-ACCRUAL", "banking-psu": "DB-ACCRUAL", "corporate-bond": "DB-ACCRUAL", "floater": "DB-ACCRUAL",
         "medium-duration": "DB-DURATION", "medium-long-duration": "DB-DURATION", "long-duration": "DB-DURATION", "dynamic-bond": "DB-DURATION",
         "gilt": "DB-DURATION", "gilt-10y": "DB-DURATION", "credit-risk": "DB-CREDIT"}
_HYBRID = {"arbitrage": "HY-ARB", "conservative-hybrid": "HY-CONS", "equity-savings": "HY-CONS", "balanced-advantage": "HY-DYN", "multi-asset": "HY-DYN"}
_OTHER = {"index-funds": "OT-PASSIVE", "index-debt": "OT-PASSIVE", "gold-etf": "OT-PASSIVE", "silver-etf": "OT-PASSIVE", "etf": "OT-PASSIVE", "etf-debt": "OT-PASSIVE"}
_DEFAULT = {"equity": "EQ-BROAD", "debt": "DB-ACCRUAL", "hybrid": "HY-AGGR", "solution": "SOL", "other": "OT-OTHER"}
_TABLE = {"equity": _EQUITY, "debt": _DEBT, "hybrid": _HYBRID, "other": _OTHER, "solution": {}}

ETF_SUBS = frozenset({"etf", "gold-etf", "silver-etf", "etf-debt"})   # an AMFI scheme that is an exchange-traded fund: scored from its exchange prices
PASSIVE_SUBS = frozenset({"index-funds", "index-debt"}) | ETF_SUBS
# categories whose funds differ by a few hundredths of a percentage point: the page says "funds in this category are near-identical" (spec Sections 5 and 7.3).
NEAR_IDENTICAL_SUBS = frozenset({"overnight", "liquid", "arbitrage"})
GROUP_NAMES = {
    "EQ-LARGE": "Equity: Large Cap", "EQ-BROAD": "Equity: Broad (flexi, multi, large & mid, value, contra, focused, dividend yield, ELSS)", "EQ-MID": "Equity: Mid Cap",
    "EQ-SMALL": "Equity: Small Cap", "EQ-THEME": "Equity: Sectoral / Thematic", "DB-CASH": "Debt: Cash (overnight to low duration)",
    "DB-ACCRUAL": "Debt: Accrual (short duration, banking & PSU, corporate bond, floater)", "DB-DURATION": "Debt: Duration (medium to long, dynamic bond, gilt)",
    "DB-CREDIT": "Debt: Credit risk", "HY-ARB": "Hybrid: Arbitrage", "HY-CONS": "Hybrid: Conservative and equity savings", "HY-AGGR": "Hybrid: Aggressive and balanced",
    "HY-DYN": "Hybrid: Dynamic and multi asset", "SOL": "Solution oriented (retirement, children's)", "OT-PASSIVE": "Others: Index funds and ETFs", "OT-OTHER": "Others: Fund of funds and other",
}


def group_of(tab: str, sub: str) -> Tuple[str, str]:
    """(type name, group code) of a classified category."""
    tab = tab if tab in _DEFAULT else "other"
    return TYPE_OF_TAB[tab], _TABLE[tab].get(sub, _DEFAULT[tab])


def is_passive(group: str) -> bool:
    return group == "OT-PASSIVE"


# ------------------------------------------------------------------------------------------------------------- tracking family

_STRIP_WORDS = re.compile(r"\b(total\s+return\s+index|total\s+return|tri|index|indices|etf|exchange\s+traded\s+fund|exchange\s+traded|fund|fof|fund\s+of\s+funds?)\b")
_PLAN_WORDS = frozenset("direct regular plan plans growth option options idcw dividend payout reinvestment reinvest bonus scheme open ended an".split())
_HOUSE_STOP = frozenset("mutual fund asset management amc company limited ltd private pvt mf".split())


def _norm(s: str) -> str:
    t = unicodedata.normalize("NFKD", s or "").lower().replace("&", " and ")
    t = re.sub(r"[’'`]", "", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def tracking_key(benchmark: Optional[str], name: Optional[str] = None, amc: Optional[str] = None) -> Optional[str]:
    """The tracking family of a passive fund: the index it follows, as a key. From the benchmark text when there is one (lower case; the words TRI,
    Total Return Index and Index removed; spaces and punctuation removed: 'NIFTY 50 TRI' and 'Nifty 50 Index' agree). Without a benchmark the index
    name is taken from the scheme name by removing the fund house name, plan and option words and the words Index, Fund and ETF. None when nothing is left.
    True tracking error needs the index's total-return series, which FinLit does not hold: this only groups funds that follow the same index."""
    for text, from_name in ((benchmark, False), (name, True)):
        if not text or not text.strip():
            continue
        t = _norm(text)
        if from_name:
            house = {w for w in _norm(amc or "").split() if w not in _HOUSE_STOP}
            words = t.split()
            while words and (words[0] in house or words[0] in _HOUSE_STOP):
                words.pop(0)
            t = " ".join(w for w in words if w not in _PLAN_WORDS)
        t = _STRIP_WORDS.sub(" ", t)
        key = re.sub(r"[^a-z0-9]+", "", t)
        if from_name:
            key = re.sub(r"(?:direct|regular|plan|growth|option|idcw)+$", "", key)
        if key:
            return key
    return None


# ------------------------------------------------------------------------------------------------------------- risk-o-meter

RISK_LEVELS = (("very high", 5), ("moderately high", 3), ("low to moderate", 1), ("high", 4), ("moderate", 2), ("low", 0))


def risk_level(text: Optional[str]) -> Optional[int]:
    """SEBI risk-o-meter wording -> 0 Low, 1 Low to Moderate, 2 Moderate, 3 Moderately High, 4 High, 5 Very High; None when unreadable
    (never a guess). Level 0 is a real level, not a gap."""
    if not text:
        return None
    t = _norm(text)
    t = re.sub(r"^(?:risk(?:ometer)?|level|riskometer)\s*[:\-]?\s*", "", t)
    for phrase, level in RISK_LEVELS:
        if re.fullmatch(rf"{phrase}(?:\s+risk)?", t):
            return level
    return None


def type_of_group(group: str) -> str:
    return {"EQ": "Equity", "DB": "Debt", "HY": "Hybrid", "SOL": "Solution Oriented", "OT": "Others"}[group.split("-")[0]]
