"""Section 8 company mode: one company's daily closes as a time series, indicator at day k against the return AFTER day k.

No look-ahead: the indicator at day k uses closes up to k only (analytics/indicators.rsi and .ema are causal); the return is
C[k+h] / C[k] - 1. Windows do not overlap: k = N-1-h, N-1-2h, ... so each forward return is used once (plan section 2c).
A window is left out (reason "jump") when a split/bonus or a one-day move beyond ln(1.8) falls inside the forward window or inside the
indicator's look-back (RSI 42 sessions, MACD 78 sessions, 52-week high 251 sessions), because such a jump makes both numbers wrong.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..analytics.indicators import ema, rsi
from . import stats as S
from .catalog import CAVEATS, METRICS, REASONS
from .derive import JUMP

HORIZONS = (5, 20, 60)
KINDS = ("rsi", "macd", "p52h", "volg", "beta")
LOOKBACK = {"rsi": 42, "macd": 78, "p52h": 251}
VOL_WINDOW = 20
BETA_WEEKS, BETA_MIN = 156, 104
PAIR_OF = {"rsi": "8.5", "macd": "8.6", "volg": "8.7", "beta": "8.8", "p52h": "8.10"}


def _d(v: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def indicator(closes: Sequence[float], kind: str) -> List[Optional[float]]:
    """The indicator value at every day, computed from closes up to that day only."""
    c = list(closes)
    n = len(c)
    if kind == "rsi":
        return rsi(c, 14)
    if kind == "macd":
        e12, e26 = ema(c, 12), ema(c, 26)
        line = [a - b if a is not None and b is not None else None for a, b in zip(e12, e26)]
        first = next((i for i, v in enumerate(line) if v is not None), None)
        out: List[Optional[float]] = [None] * n
        if first is None:
            return out
        sig = ema([v for v in line[first:]], 9)   # type: ignore[misc]
        for j, s in enumerate(sig):
            i = first + j
            if s is not None:
                out[i] = (line[i] - s) / c[i] * 100.0   # type: ignore[operator]
        return out
    if kind == "p52h":
        return [c[k] / max(c[k - 251:k + 1]) * 100.0 if k >= 251 else None for k in range(n)]
    raise ValueError(kind)


class Series:
    def __init__(self, price: Optional[dict], actions: Sequence[dict]):
        daily = (price or {}).get("daily") or {}
        rows = []
        for t, c, v in zip(daily.get("t") or [], daily.get("c") or [], (daily.get("v") or []) + [None] * len(daily.get("t") or [])):
            d = _d(t)
            try:
                cf = float(c)
            except (TypeError, ValueError):
                continue
            if d and cf > 0:
                rows.append((d, cf, v))
        self.dates = [r[0] for r in rows]
        self.closes = [r[1] for r in rows]
        self.vols = [r[2] for r in rows]
        self.n = len(rows)
        events = sorted(d for d in (_d(a.get("date")) for a in actions if any(k in str(a.get("type", "")) for k in ("bonus", "split"))) if d)
        bad = [False] * self.n
        for i in range(1, self.n):
            if abs(math.log(self.closes[i] / self.closes[i - 1])) > JUMP:
                bad[i] = True
        for e in events:   # the first trading day on or after an ex-date carries the re-basing
            for i, d in enumerate(self.dates):
                if d >= e:
                    if i > 0:
                        bad[i] = True
                    break
        self.prefix = [0] * (self.n + 1)
        for i in range(self.n):
            self.prefix[i + 1] = self.prefix[i] + (1 if bad[i] else 0)

    def clean(self, a: int, b: int) -> bool:
        """No jump/event day in (a, b]."""
        a, b = max(a, 0), min(b, self.n - 1)
        return b <= a or self.prefix[b + 1] - self.prefix[a + 1] == 0


def _excl(counts: Dict[str, int]) -> List[dict]:
    return [{"code": k, "count": v, "text": REASONS.get(k, k)} for k, v in sorted(counts.items()) if v]


def forward(series: Series, kind: str, h: int) -> Tuple[List[dict], Dict[str, int]]:
    ind = indicator(series.closes, kind)
    first = next((i for i, v in enumerate(ind) if v is not None), None)
    pts: List[dict] = []
    ex = {"jump": 0, "warmup": 0}
    if first is None:
        return pts, ex
    k = series.n - 1 - h
    while k >= first:
        if not series.clean(k - LOOKBACK[kind], k + h):
            ex["jump"] += 1
        else:
            r = (series.closes[k + h] / series.closes[k] - 1.0) * 100.0
            pts.append({"d": series.dates[k].isoformat(), "x": ind[k], "y": r})
        k -= h
    pts.reverse()
    return pts, ex


def volume(series: Series) -> Tuple[List[dict], Dict[str, int]]:
    pts: List[dict] = []
    ex = {"jump": 0, "no_volume": 0, "den_zero": 0}
    w = VOL_WINDOW
    e = series.n - 1
    while e - 2 * w >= 0:
        cur = series.vols[e - w + 1:e + 1]
        prev = series.vols[e - 2 * w + 1:e - w + 1]
        if not series.clean(e - 2 * w, e):
            ex["jump"] += 1
        elif any(v is None for v in cur + prev):
            ex["no_volume"] += 1
        elif sum(prev) <= 0:
            ex["den_zero"] += 1
        else:
            x = (sum(cur) / sum(prev) - 1.0) * 100.0
            y = abs(series.closes[e] / series.closes[e - w] - 1.0) * 100.0
            pts.append({"d": series.dates[e].isoformat(), "x": x, "y": y})
        e -= w
    pts.reverse()
    return pts, ex


def _weekly(dates: Sequence[date], closes: Sequence[float]) -> Dict[Tuple[int, int], Tuple[date, float, int]]:
    """ISO week -> (last date, last close, index of that day)."""
    out: Dict[Tuple[int, int], Tuple[date, float, int]] = {}
    for i, (d, c) in enumerate(zip(dates, closes)):
        out[tuple(d.isocalendar()[:2])] = (d, c, i)   # type: ignore[index]
    return out


def _prev_week(key: Tuple[int, int]) -> Tuple[int, int]:
    y, w = key
    d = date.fromisocalendar(y, w, 1).toordinal() - 7
    iso = date.fromordinal(d).isocalendar()
    return iso[0], iso[1]


def beta(series: Series, market: List[Tuple[date, float]]) -> Tuple[List[dict], Dict[str, int]]:
    sw = _weekly(series.dates, series.closes)
    mw = _weekly([d for d, _ in market], [c for _, c in market])
    ex = {"jump": 0, "no_market": 0}
    pts: List[dict] = []
    for key in sorted(sw):
        pk = _prev_week(key)
        if pk not in sw:
            continue
        if key not in mw or pk not in mw:
            ex["no_market"] += 1
            continue
        d1, c1, i1 = sw[key]
        _, c0, i0 = sw[pk]
        if not series.clean(i0, i1):
            ex["jump"] += 1
            continue
        pts.append({"d": d1.isoformat(), "x": (mw[key][1] / mw[pk][1] - 1.0) * 100.0, "y": (c1 / c0 - 1.0) * 100.0})
    if len(pts) > BETA_WEEKS:
        pts = pts[-BETA_WEEKS:]
    return pts, ex


def run(price: Optional[dict], actions: Sequence[dict], kind: str, h: int, market: Optional[List[Tuple[date, float]]] = None,
        market_label: str = "NIFTY 50") -> Dict[str, Any]:
    series = Series(price, actions)
    notes: List[str] = []
    if kind in ("rsi", "macd", "p52h"):
        if h not in HORIZONS:
            raise ValueError("h must be 5, 20 or 60")
        pts, ex = forward(series, kind, h)
        xm = METRICS["rsi" if kind == "rsi" else "macd_pct" if kind == "macd" else "p52h"]
        x = {"id": xm.id, "label": xm.label, "unit": xm.unit}
        y = {"id": "fwd_ret", "label": f"Return over the next {h} trading days (%)", "unit": "%"}
        grid = f"non-overlapping: signal days k = last-{h}, last-{2 * h}, ... (each forward window used once)"
    elif kind == "volg":
        pts, ex = volume(series)
        h = VOL_WINDOW
        x = {"id": "volg", "label": METRICS["volg"].label, "unit": "%"}
        y = {"id": "abs_ret", "label": METRICS["abs_ret"].label, "unit": "%"}
        grid = "non-overlapping 20-session windows, each compared with the 20 sessions before it"
    elif kind == "beta":
        pts, ex = beta(series, market or [])
        h = 5
        x = {"id": "mkt_ret", "label": f"{market_label} weekly return (%)", "unit": "%"}
        y = {"id": "stock_ret", "label": "Stock weekly return (%)", "unit": "%"}
        grid = f"ISO weeks (last close of each week), last {BETA_WEEKS} weeks with both prices; needs at least {BETA_MIN}"
        notes.append("The slope of the line is the beta: on average the share moved this many percent for each 1% move of the index.")
        if len(pts) < BETA_MIN:
            notes.append(f"Only {len(pts)} weeks with both prices: at least {BETA_MIN} are needed for a beta, so none is reported.")
    else:
        raise ValueError("unknown kind")
    st = S.analyse([(p["x"], p["y"], p["d"]) for p in pts]) if pts else None
    if st and st.get("influence"):
        st["influence"]["max"]["s"] = st["influence"]["max"].pop("label")
    beta_val = None
    if kind == "beta" and st and st.get("ols") and len(pts) >= BETA_MIN:
        beta_val = st["ols"]["slope"]
    if kind != "beta":
        notes.append("Each point uses only prices known on its signal day; the return is measured afterwards.")
    return {"kind": kind, "h": h, "pair": PAIR_OF[kind], "x": x, "y": y, "points": pts, "excluded": _excl(ex), "n": len(pts),
            "stats": S.round_sig(st) if st else None, "beta": S.round_sig(beta_val) if beta_val is not None else None,
            "grid": grid, "asOf": series.dates[-1].isoformat() if series.n else None, "notes": notes, "caveats": list(CAVEATS)}
