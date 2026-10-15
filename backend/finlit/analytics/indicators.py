"""Technical indicators, computed once on the server (the old page recomputed them 7+ times per render)."""

from __future__ import annotations

from typing import List, Optional


def ema(values: List[float], window: int) -> List[Optional[float]]:
    """Exponential moving average; None until `window` values exist (seeded with the SMA)."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) < window:
        return out
    k = 2 / (window + 1)
    current = sum(values[:window]) / window
    out[window - 1] = current
    for i in range(window, len(values)):
        current = values[i] * k + current * (1 - k)
        out[i] = current
    return out


def rsi(values: List[float], window: int = 14) -> List[Optional[float]]:
    """Wilder's RSI."""
    out: List[Optional[float]] = [None] * len(values)
    if len(values) <= window:
        return out
    gains = losses = 0.0
    for i in range(1, window + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0)
        losses += max(-delta, 0)
    avg_gain, avg_loss = gains / window, losses / window
    out[window] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(window + 1, len(values)):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (window - 1) + max(delta, 0)) / window
        avg_loss = (avg_loss * (window - 1) + max(-delta, 0)) / window
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def last(values: List[Optional[float]]) -> Optional[float]:
    for value in reversed(values):
        if value is not None:
            return value
    return None


def technical_snapshot(closes: List[float]) -> dict:
    """Latest price position vs EMAs and RSI, as used by the Technical pillar."""
    if not closes:
        return {}
    price = closes[-1]
    e20, e50, e200 = last(ema(closes, 20)), last(ema(closes, 50)), last(ema(closes, 200))
    r = last(rsi(closes, 14))

    def gap(average):
        return round((price - average) / average * 100, 2) if average else None

    return {
        "price": price,
        "ema20": round(e20, 2) if e20 else None,
        "ema50": round(e50, 2) if e50 else None,
        "ema200": round(e200, 2) if e200 else None,
        "vsEma20Pct": gap(e20),
        "vsEma50Pct": gap(e50),
        "vsEma200Pct": gap(e200),
        "rsi14": round(r, 2) if r is not None else None,
        "rsiZone": None if r is None else ("oversold" if r < 30 else "overbought" if r > 70 else "neutral"),
    }
