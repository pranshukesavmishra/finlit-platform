"""TradingView Pine v6 built-ins re-implemented on numpy arrays, with Pine's rules for na (NaN here).

Every function takes and returns float arrays of the same length as its input, bar 0 first. The rules that
decide whether the Python scores match the chart:
  sma / stdev / correlation / median / linreg   na until the window is full; any na inside the window -> na
  ema / rma                                    na until `length` clean values, then seeded with their SMA
                                               (alpha 2/(n+1) for ema, 1/n for rma), as TradingView does
  rsi / atr / dmi / macd / obv                 built on the two above, as in the Pine reference
  highest / lowest                             na for the first length-1 bars; na values inside are skipped
  percentrank                                  share of the previous `length` values <= the current one,
                                               divided by `length` (na values count as not <=)
  pivothigh / pivotlow                         the pivot must beat every bar on its left strictly and be at
                                               least equal to every bar on its right (the first of two equal
                                               highs is the pivot)
  barssince                                    bars since the condition was last true; na if never
"""
from __future__ import annotations

from typing import Tuple

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

NA = np.nan


def arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def nz(x, v: float = 0.0):
    x = arr(x)
    return np.where(np.isnan(x), v, x)


def shift(x, k: int = 1) -> np.ndarray:
    """x[k] in Pine: the value k bars ago (na before the first bar)."""
    x = arr(x)
    if k == 0:
        return x.copy()
    out = np.full(x.shape, NA)
    if k < len(x):
        out[k:] = x[:-k]
    return out


def change(x, k: int = 1) -> np.ndarray:
    x = arr(x)
    return x - shift(x, k)


def fixnan(x) -> np.ndarray:
    x = arr(x).copy()
    last = NA
    for i in range(len(x)):
        if np.isnan(x[i]):
            x[i] = last
        else:
            last = x[i]
    return x


def _windows(x: np.ndarray, n: int) -> np.ndarray:
    """(len(x) - n + 1, n) view of the trailing windows."""
    return sliding_window_view(x, n)


def _full(x: np.ndarray, n: int, vals: np.ndarray) -> np.ndarray:
    out = np.full(x.shape, NA)
    if n <= len(x):
        out[n - 1:] = vals
    return out


def sma(x, n: int) -> np.ndarray:
    x = arr(x)
    if n < 1 or n > len(x):
        return np.full(x.shape, NA)
    w = _windows(x, n)
    return _full(x, n, w.mean(axis=1))          # a NaN anywhere in the window gives NaN


def sma_var(x, lengths) -> np.ndarray:
    """ta.sma with a series length (one length per bar)."""
    x = arr(x)
    out = np.full(x.shape, NA)
    for i, n in enumerate(lengths):
        n = int(n)
        if n >= 1 and i - n + 1 >= 0:
            out[i] = x[i - n + 1:i + 1].mean()
    return out


def _seeded(x: np.ndarray, n: int, alpha: float) -> np.ndarray:
    s = sma(x, n)
    out = np.full(x.shape, NA)
    prev = NA
    for i in range(len(x)):
        v = s[i] if np.isnan(prev) else alpha * x[i] + (1.0 - alpha) * prev
        out[i] = v
        prev = v
    return out


def ema(x, n: int) -> np.ndarray:
    return _seeded(arr(x), n, 2.0 / (n + 1.0))


def rma(x, n: int) -> np.ndarray:
    return _seeded(arr(x), n, 1.0 / n)


def seed_ema(x, n: int) -> np.ndarray:
    """EMA that starts at the first bar (f_seedEma in the ST/LT scripts)."""
    x = arr(x)
    a = 2.0 / (n + 1.0)
    out = np.full(x.shape, NA)
    s = NA
    for i in range(len(x)):
        s = x[i] if np.isnan(s) else a * x[i] + (1 - a) * s
        out[i] = s
    return out


def rsi(x, n: int = 14) -> np.ndarray:
    x = arr(x)
    ch = change(x)
    u = np.where(np.isnan(ch), NA, np.maximum(ch, 0.0))
    d = np.where(np.isnan(ch), NA, np.maximum(-ch, 0.0))
    ru, rd = rma(u, n), rma(d, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        res = np.where(rd == 0, 100.0, np.where(ru == 0, 0.0, 100.0 - 100.0 / (1.0 + ru / rd)))
    return np.where(np.isnan(ru) | np.isnan(rd), NA, res)


def true_range(h, l, c, handle_na: bool) -> np.ndarray:
    h, l, c = arr(h), arr(l), arr(c)
    pc = shift(c)
    tr = np.fmax(np.fmax(h - l, np.abs(h - pc)), np.abs(l - pc))
    tr = np.where(np.isnan(pc), (h - l) if handle_na else NA, tr)
    return tr


def atr(h, l, c, n: int = 14) -> np.ndarray:
    return rma(true_range(h, l, c, True), n)


def dmi(h, l, c, di_len: int = 14, adx_len: int = 14) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    h, l = arr(h), arr(l)
    up = change(h)
    down = -change(l)
    plus_dm = np.where(np.isnan(up), NA, np.where((up > down) & (up > 0), up, 0.0))
    minus_dm = np.where(np.isnan(down), NA, np.where((down > up) & (down > 0), down, 0.0))
    trur = rma(true_range(h, l, c, False), di_len)
    with np.errstate(divide="ignore", invalid="ignore"):
        plus = fixnan(100.0 * rma(plus_dm, di_len) / trur)
        minus = fixnan(100.0 * rma(minus_dm, di_len) / trur)
        s = plus + minus
        adx = 100.0 * rma(np.abs(plus - minus) / np.where(s == 0, 1.0, s), adx_len)
    return plus, minus, adx


def macd(x, fast: int = 12, slow: int = 26, sig: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    line = ema(x, fast) - ema(x, slow)
    signal = ema(line, sig)
    return line, signal, line - signal


def obv(c, v) -> np.ndarray:
    s = np.sign(change(c)) * arr(v)
    return np.cumsum(nz(s))


def stdev(x, n: int) -> np.ndarray:
    """Population standard deviation (Pine's default, biased=true)."""
    x = arr(x)
    if n > len(x):
        return np.full(x.shape, NA)
    w = _windows(x, n)
    return _full(x, n, w.std(axis=1))


def correlation(a, b, n: int) -> np.ndarray:
    a, b = arr(a), arr(b)
    if n > len(a):
        return np.full(a.shape, NA)
    wa, wb = _windows(a, n), _windows(b, n)
    da = wa - wa.mean(axis=1, keepdims=True)
    db = wb - wb.mean(axis=1, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = (da * db).sum(axis=1) / np.sqrt((da * da).sum(axis=1) * (db * db).sum(axis=1))
    return _full(a, n, r)


def median(x, n: int) -> np.ndarray:
    x = arr(x)
    if n > len(x):
        return np.full(x.shape, NA)
    w = _windows(x, n)
    return _full(x, n, np.median(w, axis=1))


def _roll_skipna(x: np.ndarray, n: int, fn) -> np.ndarray:
    if n > len(x):
        return np.full(x.shape, NA)
    w = _windows(x, n)
    with np.errstate(all="ignore"):
        allna = np.isnan(w).all(axis=1)
        filled = np.where(np.isnan(w), -np.inf if fn is np.max else np.inf, w)
        vals = fn(filled, axis=1)
    vals = np.where(allna, NA, vals)
    return _full(x, n, vals)


def highest(x, n: int) -> np.ndarray:
    return _roll_skipna(arr(x), n, np.max)


def lowest(x, n: int) -> np.ndarray:
    return _roll_skipna(arr(x), n, np.min)


def percentrank(x, n: int) -> np.ndarray:
    x = arr(x)
    out = np.full(x.shape, NA)
    for i in range(n, len(x)):
        if np.isnan(x[i]):
            continue
        prev = x[i - n:i]
        out[i] = 100.0 * np.count_nonzero(prev <= x[i]) / n
    return out


def linreg(x, n: int, offset: int = 0) -> np.ndarray:
    x = arr(x)
    if n > len(x):
        return np.full(x.shape, NA)
    w = _windows(x, n)
    t = np.arange(n, dtype=float)
    tm = t.mean()
    wm = w.mean(axis=1)
    slope = ((t - tm) * (w - wm[:, None])).sum(axis=1) / ((t - tm) ** 2).sum()
    intercept = wm - slope * tm
    return _full(x, n, intercept + slope * (n - 1 - offset))


def barssince(cond) -> np.ndarray:
    cond = np.asarray(cond, dtype=bool)
    out = np.full(cond.shape, NA)
    last = -1
    for i, c in enumerate(cond):
        if c:
            last = i
        if last >= 0:
            out[i] = i - last
    return out


def _pivot(src: np.ndarray, left: int, right: int, high: bool) -> np.ndarray:
    out = np.full(src.shape, NA)
    for i in range(left + right, len(src)):
        j = i - right
        p = src[j]
        if np.isnan(p):
            continue
        lw = src[j - left:j]
        rw = src[j + 1:i + 1]
        if np.isnan(lw).any() or np.isnan(rw).any():
            continue
        if high:
            ok = (lw < p).all() and (rw <= p).all()
        else:
            ok = (lw > p).all() and (rw >= p).all()
        if ok:
            out[i] = p
    return out


def pivothigh(src, left: int, right: int) -> np.ndarray:
    return _pivot(arr(src), left, right, True)


def pivotlow(src, left: int, right: int) -> np.ndarray:
    return _pivot(arr(src), left, right, False)


def gt(a, b) -> np.ndarray:
    """a > b with na -> false (Pine v6 comparisons of na are false)."""
    with np.errstate(invalid="ignore"):
        return np.asarray(arr(a) > arr(b))


def ge(a, b) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.asarray(arr(a) >= arr(b))


def lt(a, b) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.asarray(arr(a) < arr(b))


def le(a, b) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return np.asarray(arr(a) <= arr(b))


def sg(cond) -> np.ndarray:
    """f_sg: +1 when true, -1 otherwise."""
    return np.where(np.asarray(cond, dtype=bool), 1.0, -1.0)
