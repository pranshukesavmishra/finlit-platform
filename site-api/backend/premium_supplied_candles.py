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
  * one series never mixes providers: a series is either wholly supplied or wholly from the fallback;
  * plausibility: no close-to-close move over 40% in a day (a split or bonus that was not adjusted shows up as one), and, for the stock,
    a last close within 15% of the quote price when there is one. A series that fails is unusable (the fallback runs) and the reason is logged.
Nothing here raises for bad input: unusable data simply means "use the fallback".
"""
import logging
import math
import re
from datetime import date

try:
    from .premium_technical_sources import BENCHMARKS
    from .technical_series import fit_range
except ImportError:
    from premium_technical_sources import BENCHMARKS
    from technical_series import fit_range

PROVIDER = "Dhan"
MAX_ROWS = 2000                 # six years is about 1,550 sessions; anything larger is not what the research API sends
STOCK_MIN, INDEX_MIN, MAX_AGE_DAYS = 252, 505, 10
MAX_DAILY_MOVE = 0.40           # a close more than 40% away from the previous close is not a plausible adjusted series
MAX_QUOTE_GAP = 0.15            # the stock's last close more than 15% from the quote price: the series and the quote are not the same stock/price basis
DATE_TEXT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
log = logging.getLogger("premium.supplied_candles")
CODE_TO_NAME = {symbol: name for name, (symbol, _) in BENCHMARKS.items()}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _date(text):
    """A strict YYYY-MM-DD date or None (no week dates, no compact forms, no non-ASCII digits)."""
    if not isinstance(text, str) or not DATE_TEXT.fullmatch(text):
        return None
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None
    return day if day.isoformat() == text else None


def check_series(series, as_of, minimum, quote_price=None):
    """(clean bars [{date, open, high, low, close, volume}], None) or (None, the reason the series is not wholly valid)."""
    if not isinstance(series, dict):
        return None, "not an object"
    if series.get("provider") != PROVIDER:
        return None, "provider is not Dhan"
    rows = series.get("candles")
    if not isinstance(rows, list) or not minimum <= len(rows) <= MAX_ROWS:
        return None, "too few or too many candles"
    bars, previous, fixed = [], None, 0
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 6:
            return None, "a candle does not have six fields"
        day = _date(row[0])
        if day is None:
            return None, "a candle date is not YYYY-MM-DD"
        values = row[1:]
        if not all(_number(v) for v in values):
            return None, "a candle value is missing or not a finite number"
        o, h, l, c, v = values
        if min(o, h, l, c) <= 0 or v < 0:
            return None, "a candle is inconsistent"
        fitted = fit_range(o, h, l, c)
        if fitted is None:
            return None, "a candle is inconsistent"
        h, l = fitted
        if previous is not None and day <= previous:
            return None, "dates are not strictly increasing"
        previous = day
        if day <= as_of:
            bars.append({"date": row[0], "open": o, "high": h, "low": l, "close": c, "volume": v})
            fixed += (h, l) != (row[2], row[3])
    if fixed:
        log.info("supplied candles: %d candle(s) had an open or close within %.2f%% outside the high-low range and were fitted to it", fixed, 100 * 0.0005)
    if len(bars) < minimum or not 0 <= (as_of - date.fromisoformat(bars[-1]["date"])).days <= MAX_AGE_DAYS:
        return None, "too few sessions or the last session is too old"
    for before, after in zip(bars, bars[1:]):
        if abs(after["close"] / before["close"] - 1) > MAX_DAILY_MOVE:
            return None, f"close moves more than {MAX_DAILY_MOVE:.0%} in a day on {after['date']} (an unadjusted split or bad data)"
    if _number(quote_price) and quote_price > 0 and abs(bars[-1]["close"] / quote_price - 1) > MAX_QUOTE_GAP:
        return None, f"last close is more than {MAX_QUOTE_GAP:.0%} from the quote price"
    return bars, None


def parse_series(series, as_of, minimum, quote_price=None, label="series"):
    """Clean bars or None when the series is not wholly valid; the reason is logged."""
    bars, reason = check_series(series, as_of, minimum, quote_price)
    if bars is None and series is not None:
        log.warning("supplied candles: %s not used: %s", label, reason)
    return bars


def quote_price_from_raw(raw):
    """The quote price in the model's raw inputs ({"quote": {SYMBOL: {"current_price": ...}}}), or None."""
    quote = raw.get("quote") if isinstance(raw, dict) else None
    for item in (quote.values() if isinstance(quote, dict) else ()):
        price = item.get("current_price") if isinstance(item, dict) else None
        if _number(price) and price > 0:
            return price
    return None


def supplied_price_input(supplied, as_of, quote_price=None):
    """The technical price input for the stock from supplied candles, or None. `quote_price` (when known) must be within 15% of the last close."""
    bars = parse_series(supplied.get("stock") if isinstance(supplied, dict) else None, as_of, STOCK_MIN, quote_price, "stock")
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
        bars = parse_series(indices.get(code), as_of, INDEX_MIN, None, code)
        if bars is not None and required.issubset({row["date"] for row in bars}):
            # Full candles are kept (the model reads closes) so the technical input hash covers everything supplied.
            result[name] = {"bars": bars, "provider": PROVIDER, "notes": [f"{name} history uses Dhan."]}
    return result


def prices_with_supplied(supplied, as_of, fallback, quote_price=None):
    """Supplied stock candles when valid, else fallback() (the existing FinEdge/Upstox resolution)."""
    return supplied_price_input(supplied, as_of, quote_price) or fallback()


def benchmarks_with_supplied(supplied, as_of, required_dates, fallback):
    """Each index from supplied candles when valid; fallback() (the existing loader, all four) only for the rest."""
    chosen = supplied_benchmarks(supplied, as_of, required_dates)
    if len(chosen) == len(CODE_TO_NAME):
        return chosen
    loaded = fallback()
    return {name: chosen.get(name) or loaded[name] for name in loaded} if isinstance(loaded, dict) else chosen
