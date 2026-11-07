"""Inputs of the Equity portfolio page engine (metrics.build_page) from the site's own stored data. No I/O: plain data in, pandas objects out.

  prices      {symbol: {"t": [dates], "c": [adjusted closes]}}   the stored weekly bars (price-MAX), any weekday inside the week
  index_rows  [{"d": "YYYY-MM-DD", "c": level}]                  NIFTY 50 daily closes
  week        the ISO week that is not finished yet ("2026-W45"): never used, so every figure comes from complete weeks

Every week is reduced to its last close and placed on that week's Friday, the way the handover pack's sample files are laid out. Information only, not investment advice.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import metrics

HISTORY_WEEKS = metrics.WEEKS + 1          # 105 closes give the 104 weekly returns
SIZE_CODE = {"Large": "L", "Mid": "M", "Small": "S"}


def iso_key(d: str) -> str:
    y, w, _ = datetime.strptime(str(d)[:10], "%Y-%m-%d").date().isocalendar()
    return f"{y}-W{w:02d}"


def friday_of(week: str) -> pd.Timestamp:
    y, w = week.split("-W")
    return pd.Timestamp(date.fromisocalendar(int(y), int(w), 5))


def week_closes(dates: Sequence[str], closes: Sequence[float]) -> "pd.Series":
    """The last close of every ISO week, keyed 'YYYY-Www'. Bars are put in date order first, so the last one of a week is its latest day."""
    pairs = sorted((str(d)[:10], float(c)) for d, c in zip(dates, closes) if c is not None and float(c) > 0)
    s = pd.Series([c for _, c in pairs], index=[iso_key(d) for d, _ in pairs], dtype="float64")
    return s[~s.index.duplicated(keep="last")]


def size_code(band: Optional[str]) -> str:
    """AMFI size band ('Large', 'Mid', 'Small') as the engine's code; 'U' when the company's market-value rank is not known."""
    return SIZE_CODE.get(band or "", "U")


def build_meta(symbols: Iterable[str], facts: Dict[str, dict], sector_of: Dict[str, str]) -> Dict[str, dict]:
    """The engine's meta for the listed companies the site knows (the order of `symbols` is kept). A company with no Sector label gets none: the engine
    names it and counts it as a sector of its own."""
    from ..diversification import calc
    out: Dict[str, dict] = {}
    for s in symbols:
        f = facts.get(s)
        if not f:
            continue
        label = (f.get("sector") or "").strip()
        out[s] = {"name": f.get("name") or s, "sector": sector_of.get(label, label) or None, "size": size_code(calc.size_band(f.get("rank"))),
                  "mcap_cr": float(f["mcap"]) if f.get("mcap") else None}
    return out


def build_frame(prices: Dict[str, Any], index_rows: Sequence[dict], symbols: Sequence[str], week: str,
                weeks: int = HISTORY_WEEKS) -> Tuple["pd.DataFrame", "pd.Series"]:
    """(weekly closes of every listed share, NIFTY 50 weekly closes) over the last `weeks` complete weeks on which the index traded, Fridays as the index.
    A share with no stored prices is an all-blank column, which the engine reports as having too little history."""
    nifty = week_closes([r["d"] for r in index_rows], [r["c"] for r in index_rows])
    nifty = nifty[nifty.index < week].tail(weeks)
    cols = {}
    for s in symbols:
        p = prices.get(s)
        cols[s] = week_closes(p["t"], p["c"]).reindex(nifty.index) if p and p.get("t") else pd.Series(np.nan, index=nifty.index)
    idx = pd.DatetimeIndex([friday_of(k) for k in nifty.index])
    frame = pd.DataFrame({s: pd.Series(v.values, index=idx) for s, v in cols.items()}, index=idx)
    return frame, pd.Series(nifty.values, index=idx, name="NIFTY 50")


def run(prices: Dict[str, Any], index_rows: Sequence[dict], meta: Dict[str, dict], week: str) -> dict:
    """The whole page object for the listed shares (metrics.build_page on the stored weekly closes)."""
    symbols = list(meta)
    frame, nifty = build_frame(prices, index_rows, symbols, week)
    page = metrics.build_page(frame, nifty, meta)
    page["first_k"] = first_k(frame, nifty, symbols, page)
    return page


FIRST_K = 12


def first_k(frame: "pd.DataFrame", nifty: "pd.Series", symbols: Sequence[str], page: dict) -> Optional[dict]:
    """Long lists only: how the first 12 shares of the list (in the order they were added) moved together, and what the rest added to 'moves like'.
    Same engine, same weeks; the first 12 are those with a year of prices among the first 12 names."""
    if page["layout"] != "long":
        return None
    r, _, _ = metrics.weekly_returns(frame, nifty)
    head = [s for s in symbols[:FIRST_K] if s in r.columns]
    if len(head) < 3:
        return None
    eff = round(metrics.effective_stocks(r[head].corr().values), 1)
    total = page["score"]["effective_stocks"]
    return {"k": len(head), "effective_stocks": eff, "rest": len(page["order"]) - len(head), "added": round(total - eff, 1)}


def card_score(page: dict) -> Optional[dict]:
    """The page's diversification score in the Diversification card's own score shape, so the card and the page always show the same figures."""
    if not page.get("order") or len(page["order"]) < 3:
        return None
    s = page["score"]
    return {"value": s["score"], "unrounded": float(s["score"]), "band": s["band"], "coMovement": s["comovement"], "sectorSpread": s["sector_spread"], "effectiveSectors": s["effective_sectors"]}
