"""Benchmark history: FinEdge first, then the existing Upstox candle connector."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Lock
from time import monotonic

try:
    from .financial_records import items, field_date, first
    from .premium_provider import provider_get
except ImportError:
    from financial_records import items, field_date, first
    from premium_provider import provider_get

# Verified against FinEdge /index/master and Upstox's official NSE instruments.
BENCHMARKS = {
    "Nifty 500": ("NIF500", "NSE_INDEX|Nifty 500"),
    "Nifty 50": ("NIF50", "NSE_INDEX|Nifty 50"),
    "Nifty Midcap 100": ("NIFMID100", "NSE_INDEX|NIFTY MIDCAP 100"),
    "Nifty Smallcap 100": ("NIFSMA100", "NSE_INDEX|NIFTY SMLCAP 100"),
}
_CACHE, _LOCK = {}, Lock()


def index_bars(payload, as_of):
    result = {}
    for row in items(payload, "rows", "price", "prices", "data"):
        day = field_date(row)
        close = first(row,"close_price","close","closePrice")
        if day and day <= as_of:
            result[day] = {"date": day.isoformat(), "close": close if close is not None and close > 0 else None}
    bars = [result[day] for day in sorted(result)]
    # Never skip an invalid bar in the middle of a return/percentile window.
    last_bad = max((i for i,row in enumerate(bars) if row["close"] is None), default=-1)
    return bars[last_bad+1:]


def load_benchmark_history(get, as_of, upstox=None, required_dates=None):
    key = (get, upstox, as_of.isoformat())
    required = set(required_dates or [])
    def usable(rows):
        return len(rows) >= 505 and (as_of-field_date(rows[-1])).days <= 10 and required.issubset({row['date'] for row in rows})
    existing = {}
    with _LOCK:
        cached = _CACHE.get(key)
        if cached and monotonic() - cached[0] < 900:
            if all(usable(value['bars']) for value in cached[1].values()):
                return cached[1]
            existing = cached[1]
    def fetch(item):
        name, (symbol, instrument) = item
        provider, notes = "FinEdge", []
        if name in existing:
            bars, provider = existing[name]['bars'], existing[name]['provider']
            notes.extend(existing[name].get('notes',[]))
        else:
            try:
                payload = provider_get(get,"/index/market-price/historical", {
                    "index_symbol":symbol, "from_date":(as_of-timedelta(days=365*6)).isoformat(), "to_date":as_of.isoformat()})
                bars = index_bars(payload, as_of)
            except Exception:
                bars = []
        if not usable(bars) and upstox:
            try:
                candidate = index_bars(upstox(instrument), as_of)
                if usable(candidate):
                    bars, provider = candidate, "Upstox"
                    notes.append(f"{name} history uses Upstox because FinEdge history was missing, stale, too short or lacked matching stock-session dates.")
            except Exception:
                notes.append(f"Secondary {name} history was unavailable.")
        return name, {"bars": bars, "provider": provider if bars else "Unavailable", "notes": notes}
    with ThreadPoolExecutor(max_workers=4) as pool:
        result = dict(pool.map(fetch, BENCHMARKS.items()))
    with _LOCK:
        for old_key, value in list(_CACHE.items()):
            if monotonic()-value[0] >= 900:
                _CACHE.pop(old_key, None)
        if len(_CACHE) >= 16:
            _CACHE.pop(next(iter(_CACHE)))
        # Cache only complete responses; transient failures can recover on retry.
        if all(usable(value['bars']) for value in result.values()):
            _CACHE[key] = (monotonic(), result)
    return result
