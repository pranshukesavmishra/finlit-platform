"""Industry peer benchmarks using the canonical financial adapter and provider budget."""
import re
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

try:
    from .financial_records import num, items, first, field_date
    from .premium_provider import provider_get
    from .premium_data import adapt_inputs
    from .benchmark_resolution import select_reported_benchmarks
except ImportError:
    from financial_records import num, items, first, field_date
    from premium_provider import provider_get
    from premium_data import adapt_inputs
    from benchmark_resolution import select_reported_benchmarks

_BENCHMARK_OBSERVATIONS = {}
_BENCHMARK_CACHE_SECONDS = 15 * 60

def peer_benchmark(get, peers, statement_type, as_of, group=None, metrics=None):
    """Median of available positive industry observations, with explicit coverage."""
    selected = set(metrics) if metrics is not None else {"pe", "pb", "ev_ebitda"}
    symbols = peers.get("peers", []) if isinstance(peers, dict) else []
    symbols = sorted({str(value).upper() for value in symbols if re.fullmatch(r"[A-Za-z0-9.&-]{1,30}", str(value))})
    meta = {"source": "FinEdge industry peer universe", "asOf": as_of.isoformat(), "universeCount": len(symbols), "fetchedCount": 0, "positiveCounts": {}, "basis": statement_type}
    meta["metrics"] = {}
    if not selected or not symbols or len(symbols) > 500:
        return {}, {**meta, "note": "No peer calculation required, or industry universe unavailable or exceeds the on-demand limit."}
    def fetch(symbol):
        cache_key = (get, symbol, statement_type, as_of)
        cached = _BENCHMARK_OBSERVATIONS.get(cache_key)
        if cached and time.monotonic() - cached[0] < _BENCHMARK_CACHE_SECONDS:
            return cached[1]
        try:
            p = provider_get(get, f"/daily-price-ratios/{symbol}", {"statement_type": "c" if statement_type == "consolidated" else "s", "from": str(as_of.year - 1), "to": str(as_of.year)})
            rows = [r for r in items(p, "price_ratios", "data") if field_date(r) and 0 <= (as_of - field_date(r)).days <= 31]
            row = max(rows, key=field_date) if rows else None
            if row is None or any(num(row.get(key)) is None for key in selected & {"pe", "pb"}):
                derived = derive_peer_price_ratios(get, symbol, statement_type, as_of)
                if derived:
                    row = {**derived, **(row or {})}
                    for key in ("pe", "pb"):
                        if num(row.get(key)) is None and key in derived:
                            row[key] = derived[key]
            if row is not None:
                if len(_BENCHMARK_OBSERVATIONS) >= 2000:
                    _BENCHMARK_OBSERVATIONS.pop(next(iter(_BENCHMARK_OBSERVATIONS)))
                _BENCHMARK_OBSERVATIONS[cache_key] = (time.monotonic(), row)
            return row
        except Exception: return None
    records = []
    if selected & {"pe", "pb"}:
        with ThreadPoolExecutor(max_workers=4) as pool:
            records = list(pool.map(fetch, symbols))
    meta["fetchedCount"] = sum(row is not None for row in records)
    meta["missingSymbols"] = [symbol for symbol, row in zip(symbols, records) if row is None]
    result = {}
    meta["calculatedPeerCount"] = sum(row is not None and row.get("source") == "calculated_finedge_quote_and_financials" for row in records)
    # Partial coverage is allowed, but never presented as a complete-industry median.
    for key in ("pe", "pb"):
        if key not in selected:
            continue
        positive = [num(row.get(key)) for row in records if row and num(row.get(key)) is not None and num(row[key]) > 0]
        meta["positiveCounts"][key] = len(positive)
        observed = sum(row is not None and num(row.get(key)) is not None for row in records)
        meta["metrics"]["industry_median_" + key] = {
            "value": statistics.median(positive) if len(positive) >= 5 else None,
            "provider": "FinEdge", "scope": "industry", "method": "available peer median",
            "positiveCount": len(positive), "observedCount": observed, "universeCount": len(symbols),
            "partial": observed < len(symbols), "statementBasis": statement_type, "asOf": as_of.isoformat()}
        if len(positive) >= 5:
            result["industry_median_" + key] = statistics.median(positive)
    if "ev_ebitda" in selected and group in ("HEAVY", "UTILITY") and len(symbols) <= 100:
        def enterprise_multiple(symbol):
            cache_key = (get, symbol, statement_type, as_of, "ev_ebitda")
            cached = _BENCHMARK_OBSERVATIONS.get(cache_key)
            if cached and time.monotonic() - cached[0] < _BENCHMARK_CACHE_SECONDS:
                return cached[1]
            try:
                typ = "c" if statement_type == "consolidated" else "s"
                quote = provider_get(get, "/quote", {"symbol": symbol})
                balance = provider_get(get, f"/financials/{symbol}", {"statement_type": typ, "statement_code": "bs", "period": "quarterly"})
                income = provider_get(get, f"/financials/{symbol}", {"statement_type": typ, "statement_code": "pl", "period": "quarterly"})
                value = derive_peer_ev_ebitda({"quote": quote, "balance_recent": balance, "quarterly": income}, symbol, statement_type, as_of)
                if value is not None:
                    if len(_BENCHMARK_OBSERVATIONS) >= 2000:
                        _BENCHMARK_OBSERVATIONS.pop(next(iter(_BENCHMARK_OBSERVATIONS)))
                    _BENCHMARK_OBSERVATIONS[cache_key] = (time.monotonic(), value)
                return value
            except Exception:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            multiples = list(pool.map(enterprise_multiple, symbols))
        positive = [value for value in multiples if value is not None and value > 0]
        meta["evCalculatedCount"] = sum(v is not None for v in multiples)
        meta["positiveCounts"]["ev_ebitda"] = len(positive)
        meta["evMissingSymbols"] = [symbol for symbol, value in zip(symbols, multiples) if value is None]
        meta["metrics"]["industry_median_ev_ebitda"] = {
            "value": statistics.median(positive) if len(positive) >= 5 else None,
            "provider": "FinEdge", "scope": "industry", "method": "available peer median",
            "positiveCount": len(positive), "observedCount": meta["evCalculatedCount"], "universeCount": len(symbols),
            "partial": meta["evCalculatedCount"] < len(symbols), "statementBasis": statement_type, "asOf": as_of.isoformat()}
        if len(positive) >= 5:
            result["industry_median_ev_ebitda"] = statistics.median(positive)
    meta["note"] = "Medians use at least five available positive multiples from the FinEdge industry peer universe. Coverage and exclusions are disclosed for each benchmark; partial coverage is not a complete-industry median."
    return result, meta

def derive_peer_price_ratios(get, symbol, statement_type, as_of):
    """Calculate missing observations from dated FinEdge quote/financial inputs."""
    try:
        quote_payload = provider_get(get, '/quote', {'symbol': symbol})
        quote = quote_payload.get(symbol, {}) if isinstance(quote_payload, dict) else {}
        observed = field_date({'date': str(quote.get('tradetime') or quote.get('date') or '')[:10]})
        if not observed or not 0 <= (as_of-observed).days <= 10:
            return None
        typ = 'c' if statement_type == 'consolidated' else 's'
        income = provider_get(get, f'/financials/{symbol}', {'statement_type':typ,'statement_code':'pl','period':'quarterly'})
        balance = provider_get(get, f'/financials/{symbol}', {'statement_type':typ,'statement_code':'bs','period':'quarterly'})
        d,_,_,meta,_,_ = adapt_inputs({'profile':{'industry':'Auto Components'},'quote':quote_payload,'quarterly':income,'balance_recent':balance}, symbol, as_of, statement_type)
        row = {'quote_date': observed.isoformat(), 'source':'calculated_finedge_quote_and_financials'}
        eps = d['eps_q'][-4:]
        if d['price'] is not None and len(eps)==4 and all(v is not None for v in eps):
            row['pe'] = d['price']/sum(eps) if sum(eps)>0 else 0.
        cap = first(quote,'market_cap','marketCap')
        end = date.fromisoformat(meta['balanceAsOf']) if meta['balanceAsOf'] else None
        if cap is not None and cap>0 and d['net_worth'] is not None and end and (as_of-end).days<=200:
            row['pb'] = cap/d['net_worth'] if d['net_worth']>0 else 0.
        return row if 'pe' in row or 'pb' in row else None
    except Exception:
        return None

def derive_peer_ev_ebitda(raw, symbol, statement_type, as_of):
    """Same enterprise-value definition and raw financial adapter as the report."""
    quote = raw.get('quote', {}).get(symbol, {})
    observed = field_date({'date': str(quote.get('tradetime') or quote.get('date') or '')[:10]})
    market_cap = first(quote, 'market_cap', 'marketCap')
    if not observed or not 0 <= (as_of-observed).days <= 10 or market_cap is None or market_cap <= 0:
        return None
    inputs, _, _, meta, _, _ = adapt_inputs({**raw, 'profile': {'industry': 'Oil refining'}}, symbol, as_of, statement_type)
    q = inputs['operating_profit_q'][-4:]
    if len(q) != 4 or any(v is None for v in q) or inputs['total_debt'] is None or inputs['cash'] is None:
        return None
    balance_day = date.fromisoformat(meta['balanceAsOf']) if meta['balanceAsOf'] else None
    quarter_day = date.fromisoformat(meta['quarterlyAsOf']) if meta['quarterlyAsOf'] else None
    if not balance_day or not quarter_day or (as_of-balance_day).days > 200 or (as_of-quarter_day).days > 200:
        return None
    ebitda = sum(q)
    # A known nonpositive denominator is an excluded observation, not a missing input.
    return (market_cap + inputs['total_debt'] - inputs['cash']) / ebitda if ebitda > 0 else 0.


def resolve_report_benchmarks(get, raw, statement_type, as_of, group, price_as_of=None):
    """Select reported comparisons first, calculating only unresolved peer metrics."""
    # Match benchmark observations to the report price date, not a later market close.
    try: benchmark_date = date.fromisoformat(price_as_of or as_of.isoformat())
    except ValueError: benchmark_date = as_of
    reported, reported_meta = select_reported_benchmarks(raw.get("benchmarkObservations", []))
    wanted = [key for key in ("pe", "pb") if "industry_median_" + key not in reported]
    if group in ("HEAVY", "UTILITY") and "industry_median_ev_ebitda" not in reported:
        wanted.append("ev_ebitda")
    benchmarks, benchmark_meta = peer_benchmark(get, raw.get("peers", {}), statement_type, min(benchmark_date, as_of), group, wanted)
    benchmarks.update(reported)
    benchmark_meta.setdefault("metrics", {}).update(reported_meta)
    providers = sorted({item["provider"] for item in benchmark_meta["metrics"].values() if item.get("value") is not None})
    if providers:
        benchmark_meta["source"] = " / ".join(providers)
    benchmark_meta["reportedObservations"] = raw.get("benchmarkObservations", [])
    benchmark_meta["policyVersion"] = "2026-10-24-provider-first"
    return benchmarks, benchmark_meta
