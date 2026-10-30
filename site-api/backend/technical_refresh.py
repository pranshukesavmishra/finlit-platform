"""The technical (ST/LT) assessment on its own, without the heavy financial-health report.

The research API refreshes every stored Prism report's technical view once a day, after the close (`refresh-technicals`). It cannot rerun the whole
report for that (60 to 120 seconds of provider calls each), and the technical scores need only the stock's and the four indices' daily candles
(supplied by the research API from Dhan) and the shares outstanding that picks the benchmark. This function runs EXACTLY the functions the full
report runs, in the same order, on the same inputs:

    supplied candles -> prices_with_supplied -> benchmarks_with_supplied -> build_technical_assessment

so the numbers are identical to the full report's (tests/test_technical_refresh.py proves it, bar for bar). It never reaches FinEdge for the stock's
candles: without a valid supplied Dhan series there is nothing to refresh from, and the stored view is left as it is (the caller is told why).
The index series fall back to FinEdge/Upstox exactly as in the full report when a supplied one is missing.
"""
try:
    from .premium_supplied_candles import supplied_price_input, supplied_benchmarks, benchmarks_with_supplied
    from .premium_technical import build_technical_assessment, last_completed_session
except ImportError:
    from premium_supplied_candles import supplied_price_input, supplied_benchmarks, benchmarks_with_supplied
    from premium_technical import build_technical_assessment, last_completed_session


class NoUsableCandles(Exception):
    """The supplied stock series is missing or failed the checks (the reason is in the premium.supplied_candles log)."""


def technical_only(supplied, now, shares_cr=None, quote_price=None, benchmark_fallback=None):
    """The `technicalAssessment` dict (as in a full report) for supplied candles at `now`, or raises NoUsableCandles.
    `benchmark_fallback(as_of, required_dates)` loads the index history when a supplied index series is unusable (FinEdge, then Upstox)."""
    as_of = last_completed_session(now)
    price_input = supplied_price_input(supplied, as_of, quote_price)
    if price_input is None:
        raise NoUsableCandles("The supplied daily candles for the stock are missing or failed the checks.")
    required = [row["date"] for row in price_input["bars"][-505:]]
    if benchmark_fallback is None:
        benchmarks = supplied_benchmarks(supplied, as_of, required)
    else:
        benchmarks = benchmarks_with_supplied(supplied, as_of, required, lambda: benchmark_fallback(as_of, required))
    return build_technical_assessment(price_input, as_of, benchmarks, shares_cr)

