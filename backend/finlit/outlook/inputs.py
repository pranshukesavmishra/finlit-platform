"""The company's stored report sections, put into one shape the scorers read. Pure: no I/O, no provider calls."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional


def _table(t: Optional[dict]) -> Dict[str, Dict[str, Optional[float]]]:
    """{row: {period: value}} from a stored {periods, rows} table."""
    t = t or {}
    periods = t.get("periods") or []
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for key, vals in (t.get("rows") or {}).items():
        out[key] = {p: (v if isinstance(v, (int, float)) and not isinstance(v, bool) else None) for p, v in zip(periods, vals or [])}
    return out


@dataclass
class Inputs:
    lender: bool = False
    fy: List[str] = field(default_factory=list)            # yearly period labels, oldest first (the P&L's)
    pl: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    bs: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    cf: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    ratios: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    qp: List[str] = field(default_factory=list)            # quarterly labels, oldest first
    qends: List[Optional[str]] = field(default_factory=list)
    q: Dict[str, Dict[str, Optional[float]]] = field(default_factory=dict)
    segments: List[dict] = field(default_factory=list)     # latest-year segment rows: {sharePct, growthPct}

    # ---- accessors: k = years (or quarters) back from the latest
    def y(self, key: str, k: int = 0) -> Optional[float]:
        return self._at(self.pl, self.fy, key, k)

    def b(self, key: str, k: int = 0) -> Optional[float]:
        return self._at(self.bs, self.fy, key, k)

    def c(self, key: str, k: int = 0) -> Optional[float]:
        return self._at(self.cf, self.fy, key, k)

    def r(self, key: str, k: int = 0) -> Optional[float]:
        return self._at(self.ratios, self.fy, key, k)

    def qv(self, key: str, k: int = 0) -> Optional[float]:
        return self._at(self.q, self.qp, key, k)

    @staticmethod
    def _at(tab: dict, periods: List[str], key: str, k: int) -> Optional[float]:
        if k < 0 or k >= len(periods):
            return None
        return (tab.get(key) or {}).get(periods[-1 - k])

    def quarters_contiguous(self, n: int) -> bool:
        """The last n quarters follow each other (about three months apart): no gap that would make 'same quarter last year' wrong."""
        if len(self.qp) < n:
            return False
        ends = []
        for e in self.qends[-n:]:
            try:
                ends.append(date.fromisoformat(str(e)[:10]))
            except ValueError:
                return False
        return all(80 <= (b - a).days <= 100 for a, b in zip(ends, ends[1:]))


def build_inputs(summary: Optional[dict], financials: Optional[dict], ratios: Optional[dict], segments: Optional[dict]) -> Inputs:
    fin = financials or {}
    yearly, quarterly = fin.get("yearly") or {}, fin.get("quarterly") or {}
    pl = yearly.get("pl") or {}
    qpl = quarterly.get("pl") or {}
    hist = ((ratios or {}).get("history")) or {}
    rt = _table({"periods": hist.get("periods"), "rows": hist.get("rows")})
    seg = [s for s in ((segments or {}).get("latest") or []) if isinstance(s, dict)]
    return Inputs(
        lender=bool(((summary or {}).get("dataQuality") or {}).get("isBank")),
        fy=list(pl.get("periods") or []), pl=_table(pl), bs=_table(yearly.get("bs")), cf=_table(yearly.get("cf")), ratios=rt,
        qp=list(qpl.get("periods") or []), qends=list(qpl.get("periodEnds") or []), q=_table(qpl), segments=seg)
