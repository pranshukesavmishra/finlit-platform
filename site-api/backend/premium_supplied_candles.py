"""Daily candles supplied by the research API (FinLit addition, not an upstream file).

The research API fetches split/bonus-adjusted daily OHLCV from Dhan and sends it inside POST /api/premium-reports as
`suppliedCandles`: {"stock": {"provider": "Dhan", "candles": [[date, o, h, l, c, v], ...]},
                    "indices": {"NIF50": {...}, "NIFMID100": {...}, "NIFSMA100": {...}, "NIF500": {...}}}.
A supplied series is the FIRST choice for its own series when it is complete and valid; otherwise the caller's existing path
(FinEdge, then Upstox) runs unchanged. Rules, per series and the same as for the other providers:
  * the provider must be exactly "Dhan" (the label shown in the assessment must be true);
  * every row is [YYYY-MM-DD, open, high, low, close, volume] with finite numbers, open/high/low/close > 0, volume >= 0 and
    low <= min(open, close) <= max(open, close) <= high; one bad row rejects the whole series (no gap is kept, none is filled);
  * dates strictly increasing (no duplicates); rows after the model's last completed session (16:00 IST rule, `as_of`) are dropped;
  * stock: >= 252 rows and the last within 10 calendar days of `as_of`; index: >= 505 rows, the same freshness, and every
    one of the stock's last 505 session dates present (as for FinEdge/Upstox index history);
  * one series never mixes providers: a series is either wholly supplied or wholly from the fallback.
Nothing here raises for bad input: unusable data simply means "use the fallback".
"""
import math
from datetime import date

try:
    from .premium_technical_sources import BENCHMARKS
except ImportError:
    from premium_technical_sources import BENCHMARKS

PROVIDER = "Dhan"
MAX_ROWS = 2000                 # six years is about 1,550 sessions; anything larger is not what the research API sends
STOCK_MIN, INDEX_MIN, MAX_AGE_DAYS = 252, 505, 10
CODE_TO_NAME = {symbol: name for name, (symbol, _) in BENCHMARKS.items()}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def parse_series(series, as_of, minimum):
    """Clean bars [{date, open, high, low, close, volume}] or None when the series is not wholly valid."""
    if not isinstance(series, dict) or series.get("provider") != PROVIDER:
        return None
    rows = series.get("candles")
    if not isinstance(rows, list) or not minimum <= len(rows) <= MAX_ROWS:
        return None
    bars, previous = [], None
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 6 or not isinstance(row[0], str) or len(row[0]) != 10:
            return None
        try:
            day = date.fromisoformat(row[0])
        except ValueError:
            return None
        values = row[1:]
        if not all(_number(v) for v in values):
            return None
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v < 0 or not l <= min(o, c) <= max(o, c) <= h:
            return None
        if previous is not None and day <= previous:
            return None
        previous = day
        if day <= as_of:
            bars.append({"date": row[0], "open": o, "high": h, "low": l, "close": c, "volume": v})
    if len(bars) < minimum or not 0 <= (as_of - date.fromisoformat(bars[-1]["date"])).days <= MAX_AGE_DAYS:
        return None
    return bars


def supplied_price_input(supplied, as_of):
    """The technical price input for the stock from supplied candles, or None."""
    bars = parse_series(supplied.get("stock") if isinstance(supplied, dict) else None, as_of, STOCK_MIN)
    if bars is None:
        return None
    return {"bars": bars, "provider": PROVIDER, "throughDate": as_of.isoformat(),
            "notes": ["Daily candles use one Dhan series, which Dhan adjusts for splits and bonus issues. "
                      "That adjustment has not been independently verified against FinEdge's adjusted closing-price history."]}


def supplied_benchmarks(supplied, as_of, required_dates):
    """{benchmark name: {"bars", "provider", "notes"}} for each index series that is valid and covers the stock's sessions."""
    indices = supplied.get("indices") if isinstance(supplied, dict) else None
    if not isinstance(indices, dict):
        return {}
    required, result = set(required_dates or []), {}
    for code, name in CODE_TO_NAME.items():
        bars = parse_series(indices.get(code), as_of, INDEX_MIN)
        if bars is not None and required.issubset({row["date"] for row in bars}):
            # Full candles are kept (the model reads closes) so the technical input hash covers everything supplied.
            result[name] = {"bars": bars, "provider": PROVIDER, "notes": [f"{name} history uses Dhan."]}
    return result


def prices_with_supplied(supplied, as_of, fallback):
    """Supplied stock candles when valid, else fallback() (the existing FinEdge/Upstox resolution)."""
    return supplied_price_input(supplied, as_of) or fallback()


def benchmarks_with_supplied(supplied, as_of, required_dates, fallback):
    """Each index from supplied candles when valid; fallback() (the existing loader, all four) only for the rest."""
    chosen = supplied_benchmarks(supplied, as_of, required_dates)
    if len(chosen) == len(CODE_TO_NAME):
        return chosen
    loaded = fallback()
    return {name: chosen.get(name) or loaded[name] for name in loaded} if isinstance(loaded, dict) else chosen
