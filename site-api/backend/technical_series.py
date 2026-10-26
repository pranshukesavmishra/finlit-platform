"""Small deterministic series operators used by the scoring-only Pine port."""
import math
import statistics
from datetime import date, timedelta


def rolling(values, length, operation, full=True):
    result = []
    for i in range(len(values)):
        window = values[max(0,i-length+1):i+1]
        result.append(operation(window) if (not full or len(window) == length) and all(v is not None for v in window) else None)
    return result


def sma(values, length):
    return rolling(values, length, lambda w: sum(w) / len(w))


def percentrank(values, length):
    result = []
    for i, value in enumerate(values):
        previous = values[max(0,i-length):i]
        result.append(100 * sum(v <= value for v in previous) / length if value is not None and len(previous) == length and all(v is not None for v in previous) else None)
    return result


def linreg(values, length):
    xs = list(range(length))
    mean = (length - 1) / 2
    denominator = sum((x - mean) ** 2 for x in xs)
    def endpoint(window):
        avg = sum(window) / length
        slope = sum((x - mean) * (y - avg) for x,y in zip(xs,window)) / denominator
        return avg + slope * mean
    return rolling(values, length, endpoint)


def benchmark_pack(bars, ema):
    """All index returns/highs use that index's own history, before date alignment."""
    closes = [row["close"] for row in bars]
    high20 = rolling(closes,20,max,False)
    high252 = rolling(closes,252,max,False)
    low5, low20 = rolling(closes,5,min,False), rolling(closes,20,min,False)
    e50, e200 = ema(closes,50), ema(closes,200)
    result = {}
    for i,row in enumerate(bars):
        result[row["date"]] = {
            "close": closes[i], "e50": e50[i], "e200": e200[i], "hi20": high20[i], "hi252": high252[i],
            "ll": i >= 5 and low5[i] < low20[i-5],
            "ret": math.log(closes[i]/closes[i-1]) if i else None,
            **{f"r{n}": closes[i] / closes[i-n] - 1 if i >= n else None for n in (21,63,126,189,252)},
        }
    return result


def relative_strength(bars, packs, shares_cr):
    closes = [row["close"] for row in bars]
    ret_s = [None] + [math.log(b/a) for a,b in zip(closes,closes[1:])]
    picked, names = [], []
    for row in bars:
        cap = shares_cr * row["close"] if shares_cr is not None and shares_cr > 0 else None
        name = "Nifty 500" if cap is None else "Nifty 50" if cap >= 107000 else "Nifty Midcap 100" if cap >= 32800 else "Nifty Smallcap 100"
        selected = packs.get(name,{}).get(row["date"], {})
        fallback = packs.get("Nifty 500",{}).get(row["date"], {})
        picked.append({key: selected.get(key) if selected.get(key) is not None else fallback.get(key) for key in ("close","e50","e200","hi20","hi252","ll","ret","r21","r63","r126","r189","r252")})
        names.append(name if selected.get("close") is not None else "Nifty 500")
    raw_st, raw_lt, betas = [], [], []
    for i,row in enumerate(bars):
        beta = 1.
        a, b = ret_s[max(0,i-125):i+1], [p["ret"] for p in picked[max(0,i-125):i+1]]
        if len(a) == 126 and all(x is not None for x in a+b):
            mean_a, mean_b = statistics.mean(a), statistics.mean(b)
            variance = sum((x-mean_b)**2 for x in b)
            if variance > 0:
                beta = sum((x-mean_a)*(y-mean_b) for x,y in zip(a,b)) / variance
        beta = max(.3,min(3.,beta))
        betas.append(beta)
        excess = {n: closes[i]/closes[i-n]-1-beta*picked[i][f"r{n}"] if i>=n and picked[i][f"r{n}"] is not None else None for n in (21,63,126,189,252)}
        raw_st.append(.6*excess[21]+.4*excess[63] if excess[21] is not None and excess[63] is not None else None)
        raw_lt.append(.4*excess[63]+.2*excess[126]+.2*excess[189]+.2*excess[252] if all(excess[n] is not None for n in (63,126,189,252)) else None)
    return picked, names, betas, percentrank(raw_st,126), percentrank(raw_lt,252)


def ema(values, length):
    """Pine's recursive EMA, seeded at the first valid observation."""
    result, previous = [], None
    for value in values:
        if value is None:
            previous = None
        elif previous is None:
            previous = value
        else:
            previous += 2 / (length + 1) * (value - previous)
        result.append(previous)
    return result


def rma(values, length):
    result, window, previous = [], [], None
    for value in values:
        if value is None:
            window, previous = [], None
        elif previous is None:
            window.append(value)
            if len(window) == length:
                previous = sum(window) / length
        else:
            previous += (value - previous) / length
        result.append(previous)
    return result


def rsi(closes):
    changes = [None] + [b - a if a is not None and b is not None else None for a, b in zip(closes, closes[1:])]
    gain = rma([None if x is None else max(x, 0) for x in changes], 14)
    loss = rma([None if x is None else max(-x, 0) for x in changes], 14)
    return [None if g is None or l is None or g == l == 0 else 100 if l == 0 else 100 - 100 / (1 + g / l) for g, l in zip(gain, loss)]


def macd(closes):
    fast, slow = ema(closes, 12), ema(closes, 26)
    line = [a - b if a is not None and b is not None else None for a, b in zip(fast, slow)]
    signal = ema(line, 9)
    histogram = [a - b if a is not None and b is not None else None for a, b in zip(line, signal)]
    return line, signal, histogram


def atr_adx(bars):
    tr, plus, minus = [None], [None], [None]
    for previous, current in zip(bars, bars[1:]):
        if any(row[k] is None for row, k in ((previous, "close"), (previous, "high"), (previous, "low"), (current, "high"), (current, "low"))):
            tr.append(None); plus.append(None); minus.append(None)
            continue
        up, down = current["high"] - previous["high"], previous["low"] - current["low"]
        tr.append(max(current["high"] - current["low"], abs(current["high"] - previous["close"]), abs(current["low"] - previous["close"])))
        plus.append(up if up > down and up > 0 else 0)
        minus.append(down if down > up and down > 0 else 0)
    atr_tr = tr[:]
    if bars:
        atr_tr[0] = bars[0]["high"] - bars[0]["low"]
    atr, p, m = rma(atr_tr, 14), rma(plus, 14), rma(minus, 14)
    dx = [None if a is None or b is None else 0 if a + b == 0 else 100 * abs(a - b) / (a + b) for a, b in zip(p, m)]
    return atr, rma(dx, 14)


def obv(bars):
    result, total = [], 0
    for i, bar in enumerate(bars):
        if bar["volume"] is None or bar["close"] is None:
            total = None
        elif total is None or (i and bars[i - 1]["close"] is None):
            total = 0  # A new baseline; dependent EMA warmups restart after the gap.
        elif i:
            total += (1 if bar["close"] > bars[i - 1]["close"] else -1 if bar["close"] < bars[i - 1]["close"] else 0) * bar["volume"]
        result.append(total)
    return result


def weekly_closes(bars, as_of):
    # Pine request.security W uses indicator[1] throughout the current daily week.
    last_day = date.fromisoformat(bars[-1]["date"]) if bars else as_of
    cutoff = last_day - timedelta(days=last_day.weekday())
    grouped = {}
    for bar in bars:
        day = date.fromisoformat(bar["date"])
        if day < cutoff:
            week = day.isocalendar()[:2]
            if week not in grouped or grouped[week] is not None:
                grouped[week] = bar["close"]
    return list(grouped.values())
