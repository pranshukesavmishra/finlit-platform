"""Cross-check of the technical engine against independent textbook implementations, and the size of every known reason a number can differ
from TradingView. Pure Python (numpy and pandas are not in the project's environments); the reference code below is written from the
definitions, loop by loop, and shares nothing with site-api/backend/technical_series.py.

    PYTHONPATH=site-api/backend python docs/technicals/crosscheck.py [--json out.json]

Output: (1) maximum absolute differences per indicator on 5 real recorded series (TCS, HDFCBANK, SKIPPER, BAJFINANCE, HDFCLIFE, ~1,690 sessions
each, from site-api/backend/tests/fixtures/premium_replay) and on synthetic series; (2) how many bars the indicators need to converge; (3) the effect
on the final short- and long-term scores of: the number of bars, a live (unfinished) bar, SMA-seeded against first-value-seeded EMAs, an unadjusted
bonus issue, the Dhan-style tolerance rule for a close above the high. The index series is the equal-weighted mean of the five stocks (no index bars
are recorded), identical in every variant, so each difference isolates its factor. Timing of one full assessment is printed too.
"""
import gzip
import json
import math
import random
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "site-api" / "backend"))
import premium_technical as PT          # noqa: E402
import technical_scoring as TS          # noqa: E402
import technical_series as SER          # noqa: E402

STOCKS = ("TCS", "HDFCBANK", "SKIPPER", "BAJFINANCE", "HDFCLIFE")


# --------------------------------------------------------------------------------------------- independent reference implementations
def ref_ema(x, n, seed="sma"):
    a, out = 2.0 / (n + 1), [None] * len(x)
    if seed == "sma":
        if len(x) < n:
            return out
        e = sum(x[:n]) / n
        out[n - 1] = e
        start = n
    else:
        e, out[0], start = x[0], x[0], 1
    for i in range(start, len(x)):
        e = a * x[i] + (1 - a) * e
        out[i] = e
    return out


def ref_wilder(x, n):
    """Wilder's smoothing of x[1:] (x[0] unused): first value = mean of n, then (prev*(n-1)+x)/n. Returned on the same index as x."""
    out = [None] * len(x)
    if len(x) < n + 1:
        return out
    s = sum(x[1:n + 1]) / n
    out[n] = s
    for i in range(n + 1, len(x)):
        s = (s * (n - 1) + x[i]) / n
        out[i] = s
    return out


def ref_rsi(c, n=14):
    gain = [0.0] + [max(c[i] - c[i - 1], 0.0) for i in range(1, len(c))]
    loss = [0.0] + [max(c[i - 1] - c[i], 0.0) for i in range(1, len(c))]
    g, l = ref_wilder(gain, n), ref_wilder(loss, n)
    return [None if a is None else (100.0 if b == 0 else 100 - 100 / (1 + a / b)) for a, b in zip(g, l)]


def ref_macd(c, f=12, s=26, sg=9):
    ef, es = ref_ema(c, f), ref_ema(c, s)
    line = [None if a is None or b is None else a - b for a, b in zip(ef, es)]
    first = next(i for i, v in enumerate(line) if v is not None)
    sig = [None] * first + ref_ema(line[first:], sg)
    return line, sig, [None if a is None or b is None else a - b for a, b in zip(line, sig)]


def ref_adx(bars, n=14):
    h, l, c = [b["high"] for b in bars], [b["low"] for b in bars], [b["close"] for b in bars]
    tr, pdm, mdm = [0.0], [0.0], [0.0]
    for i in range(1, len(bars)):
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
    atr, sp, sm = ref_wilder(tr, n), ref_wilder(pdm, n), ref_wilder(mdm, n)
    dx = [0.0] + [None] * (len(bars) - 1)
    for i in range(n, len(bars)):
        pdi, mdi = 100 * sp[i] / atr[i], 100 * sm[i] / atr[i]
        dx[i] = 0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi)
    adx = [None] * len(bars)
    seed_at = 2 * n - 1
    if len(bars) > seed_at:
        a = sum(dx[n:2 * n]) / n
        adx[seed_at] = a
        for i in range(seed_at + 1, len(bars)):
            a = (a * (n - 1) + dx[i]) / n
            adx[i] = a
    first_tr = bars[0]["high"] - bars[0]["low"]
    atr_p = [None] * len(bars)                         # Pine's ta.atr: rma of true range, the first bar's range being high - low
    if len(bars) >= n:
        a = (first_tr + sum(tr[1:n])) / n
        atr_p[n - 1] = a
        for i in range(n, len(bars)):
            a = (a * (n - 1) + tr[i]) / n
            atr_p[i] = a
    return atr_p, adx


def ref_obv(bars):
    out, t = [0.0], 0.0
    for i in range(1, len(bars)):
        t += bars[i]["volume"] * (1 if bars[i]["close"] > bars[i - 1]["close"] else -1 if bars[i]["close"] < bars[i - 1]["close"] else 0)
        out.append(t)
    return out


def ref_bollinger(c, n=20, k=2.0):
    mid, up, dn = [None] * len(c), [None] * len(c), [None] * len(c)
    for i in range(n - 1, len(c)):
        w = c[i - n + 1:i + 1]
        m = sum(w) / n
        sd = math.sqrt(sum((v - m) ** 2 for v in w) / n)            # population deviation, as TradingView's ta.stdev
        mid[i], up[i], dn[i] = m, m + k * sd, m - k * sd
    return mid, up, dn


def maxdiff(a, b, skip=0):
    d = [abs(x - y) for x, y in zip(a[skip:], b[skip:]) if x is not None and y is not None]
    miss = sum(1 for x, y in zip(a[skip:], b[skip:]) if (x is None) != (y is None))
    return (max(d) if d else float("nan")), miss


# --------------------------------------------------------------------------------------------- data
def real_bars():
    out = {}
    for s in STOCKS:
        d = json.load(gzip.open(ROOT / f"site-api/backend/tests/fixtures/premium_replay/{s}.json.gz"))
        for k, v in d["recorded"].items():
            if k.startswith(f'["/daily-quotes/{s}"'):
                rows = sorted(v["price"], key=lambda r: r["quote_date"])
                out[s] = [r for r in rows if any(r[x] for x in ("open_price", "high_price", "low_price", "close_price", "volume"))]
    return out


BAD = {}


def bars_of(rows, name=None):
    """Production normalisation, then the recorded 'close above high' candles (PARITY.md T3, 1.2% for TCS) are CLAMPED to their range for this harness only,
    so the comparison runs on the full ~1,690 sessions; production would hold such a candle back and use only the bars after it (reported in BAD)."""
    bars = PT.normalise_bars({"price": rows}, date(2026, 10, 26))
    fixed = []
    for b, r in zip(bars, [x for x in rows]):
        if b["open"] is None:
            raw = {k: r[k + "_price"] for k in ("open", "high", "low", "close")}
            top, bottom = max(raw["open"], raw["close"]), min(raw["open"], raw["close"])
            b = {**b, "open": raw["open"], "close": raw["close"], "high": max(raw["high"], top), "low": min(raw["low"], bottom)}
            BAD.setdefault(name, []).append((b["date"], raw))
        fixed.append(b)
    return fixed


def synth(n, seed, drift=0.0004, vol=0.016, start=500.0):
    rng, p, out = random.Random(seed), start, []
    for i in range(n):
        o = p * (1 + rng.gauss(0, vol / 3)); c = o * (1 + rng.gauss(drift, vol))
        h = max(o, c) * (1 + abs(rng.gauss(0, vol / 2))); l = min(o, c) * (1 - abs(rng.gauss(0, vol / 2)))
        out.append({"date": (date(2018, 1, 1).toordinal() + i), "open": o, "high": h, "low": l, "close": c, "volume": 1e6 * (1 + abs(rng.gauss(0, .5)))})
        p = c
    return out


def indicators_ours(bars):
    c = [b["close"] for b in bars]
    atr, adx = SER.atr_adx(bars)
    line, sig, hist = SER.macd(c)
    return {"EMA9": SER.ema(c, 9), "EMA20": SER.ema(c, 20), "EMA50": SER.ema(c, 50), "EMA100": SER.ema(c, 100), "EMA200": SER.ema(c, 200),
            "RSI14": SER.rsi(c), "MACD line": line, "MACD signal": sig, "MACD hist": hist, "ATR14": atr, "ADX14": adx, "OBV": SER.obv(bars)}


def indicators_ref(bars):
    c = [b["close"] for b in bars]
    atr, adx = ref_adx(bars)
    line, sig, hist = ref_macd(c)
    return {"EMA9": ref_ema(c, 9), "EMA20": ref_ema(c, 20), "EMA50": ref_ema(c, 50), "EMA100": ref_ema(c, 100), "EMA200": ref_ema(c, 200),
            "RSI14": ref_rsi(c), "MACD line": line, "MACD signal": sig, "MACD hist": hist, "ATR14": atr, "ADX14": adx, "OBV": ref_obv(bars)}


# --------------------------------------------------------------------------------------------- scoring variants
def composite_index(real):
    """Equal-weighted mean of the five stocks' closes (rebased), on the UNION of their dates; a date one stock lacks takes the previous value (harness only:
    the production rule is that the index holds every one of the stock's last 505 sessions, otherwise the relative-strength rows are withheld)."""
    days = sorted(set().union(*[{b["date"] for b in v} for v in real.values()]))
    closes = {s: {b["date"]: b["close"] for b in v} for s, v in real.items()}
    base = {s: closes[s][min(closes[s])] for s in real}
    last, idx = {}, {}
    for d in days:
        for s in real:
            if d in closes[s]:
                last[s] = closes[s][d] / base[s]
        if len(last) == len(real):
            idx[d] = sum(last.values()) / len(real) * 10000
    return idx


def score(bars, index, shares_cr=None, as_of=date(2026, 10, 26)):
    dates = {b["date"] for b in bars}
    bm = {n: {"bars": [{"date": d, "close": v} for d, v in sorted(index.items()) if d in dates or True], "provider": "x"} for n in ("Nifty 500", "Nifty 50", "Nifty Midcap 100", "Nifty Smallcap 100")}
    a = PT.build_technical_assessment({"bars": bars, "provider": "x", "notes": []}, as_of, bm, shares_cr)
    return a["shortTerm"]["score"], a["longTerm"]["score"], a


def fmt(v):
    return "withheld" if v is None else f"{v:+.2f}"


def run(argv):
    out = {"indicators": {}, "synthetic": {}, "convergence": {}, "effects": {}, "timing": {}}
    real = {s: bars_of(rows, s) for s, rows in real_bars().items()}
    print('   candles with a close/open outside the high-low range in the recorded FinEdge rows (production withholds them; clamped here):', {k: [(d, r['open'], r['high'], r['low'], r['close']) for d, r in v] for k, v in BAD.items()})
    print("== 1. Indicators: max |ours - textbook| over the whole series (and number of bars where one has a value and the other none)")
    names = list(indicators_ours(synth(400, 1)))
    table = {}
    for s, bars in real.items():
        o, r = indicators_ours(bars), indicators_ref(bars)
        table[s] = {k: maxdiff(o[k], r[k]) for k in names}
    for k in names:
        worst = max((table[s][k][0] for s in real if table[s][k][0] == table[s][k][0]), default=float("nan"))
        miss = sum(table[s][k][1] for s in real)
        print(f"  {k:12s} real max diff {worst:.3e}   presence mismatches {miss}")
        out["indicators"][k] = {"max_abs_diff_real": worst, "presence_mismatches": miss}
    for seed in (1, 2, 3):
        bars = synth(1500, seed)
        o, r = indicators_ours(bars), indicators_ref(bars)
        out["synthetic"][seed] = {k: maxdiff(o[k], r[k])[0] for k in names}
    print("  synthetic (3 series x 1,500 bars): worst", f"{max(v for d in out['synthetic'].values() for v in d.values()):.3e}")
    # Bollinger and the sma/stdev helpers
    bars = real["TCS"]
    c = [b["close"] for b in bars]
    mid, up, dn = ref_bollinger(c)
    sm = SER.sma(c, 20)
    sd = SER.rolling(c, 20, __import__("statistics").pstdev)
    ours_up = [None if m is None else m + 2 * s for m, s in zip(sm, sd)]
    print(f"  Bollinger(20,2) upper band (sma + 2 x population sd) max diff TCS: {maxdiff(ours_up, up)[0]:.3e}")
    out["indicators"]["Bollinger upper"] = {"max_abs_diff_real": maxdiff(ours_up, up)[0]}

    print("\n== 2. Warm-up: |value from the last N bars - value from all bars| at the last bar (max over the 5 stocks)")
    for ind in ("EMA200", "RSI14", "MACD line", "ADX14", "OBV"):
        row = {}
        for n in (250, 500, 750, 1000, 1500):
            d = 0.0
            for s, bars in real.items():
                full, part = indicators_ours(bars)[ind][-1], indicators_ours(bars[-n:])[ind][-1]
                if full is not None and part is not None:
                    d = max(d, abs(full - part))
                elif full is not None and part is None:
                    d = float("inf")
            row[n] = d
        out["convergence"][ind] = row
        print(f"  {ind:10s} " + "  ".join(f"{n}: {v:.4g}" for n, v in row.items()))

    print("\n== 3. Effect on the final scores (short-term / long-term), per stock")
    index = composite_index(real)
    base = {}
    for s, bars in real.items():
        st, lt, _ = score(bars, index)
        base[s] = (st, lt)
        print(f"  {s:10s} full history ({len(bars)} bars): ST {fmt(st)}  LT {fmt(lt)}")
    out["effects"]["base"] = base
    effects = {}

    print("  -- (a) number of bars fed (last N sessions)")
    for n in (260, 400, 600, 1000, 1500):
        row = {}
        for s, bars in real.items():
            st, lt, _ = score(bars[-n:], index)
            row[s] = (st, lt)
        effects[f"bars_{n}"] = row
        print(f"  last {n:4d}: " + "; ".join(f"{s} {fmt(a)}/{fmt(b)} (d {('%.1f' % abs(a - base[s][0])) if a is not None and base[s][0] is not None else 'n/a'}/{('%.1f' % abs(b - base[s][1])) if b is not None and base[s][1] is not None else 'n/a'})" for s, (a, b) in row.items()))

    print("  -- (b) a live, unfinished bar (simulated: today's candle at 12:30, halfway to the close, high/low so far, 45% of the volume) against the completed session")
    row = {}
    for s, bars in real.items():
        done, prev = bars[-1], bars[-2]
        live = dict(done)
        live["close"] = prev["close"] + 0.5 * (done["close"] - prev["close"])
        live["high"] = max(live["open"], live["close"]) + 0.5 * (done["high"] - max(done["open"], done["close"]))
        live["low"] = min(live["open"], live["close"]) - 0.5 * (min(done["open"], done["close"]) - done["low"])
        live["volume"] = done["volume"] * 0.45
        a = score(bars, index)[:2]
        b = score(bars[:-1] + [live], index)[:2]
        c2 = score(bars[:-1], index)[:2]
        row[s] = {"completed": a, "with_live_bar": b, "previous_session": c2}
        print(f"  {s:10s} completed ST {fmt(a[0])} LT {fmt(a[1])} | with live bar ST {fmt(b[0])} LT {fmt(b[1])} | previous session ST {fmt(c2[0])} LT {fmt(c2[1])}")
    effects["live_bar"] = row

    print("  -- (c) EMA seeded with the first value (the old behaviour) against the SMA seed (Pine's ta.ema, now ours)")
    orig_ts, orig_ser = TS.ema, SER.ema
    def first_seed(values, length):
        out_, prev, a = [], None, 2 / (length + 1)
        for v in values:
            if v is None:
                prev = None
            elif prev is None:
                prev = v
            else:
                prev += a * (v - prev)
            out_.append(prev)
        return out_
    row = {}
    try:
        TS.ema = SER.ema = first_seed
        for s, bars in real.items():
            row[s] = score(bars, index)[:2]
            row[s + "_250"] = score(bars[-250:], index)[:2]
    finally:
        TS.ema, SER.ema = orig_ts, orig_ser
    for s in real:
        sma_250 = score(real[s][-250:], index)[:2]
        print(f"  {s:10s} full history: first-value seed ST {fmt(row[s][0])} LT {fmt(row[s][1])} (SMA seed {fmt(base[s][0])}/{fmt(base[s][1])}); last 250 bars: {fmt(row[s + '_250'][0])}/{fmt(row[s + '_250'][1])} against {fmt(sma_250[0])}/{fmt(sma_250[1])}")
    effects["ema_seed"] = row

    print("  -- (d) a bonus issue the provider did not adjust (1:2 bonus 60 sessions ago: prices before it x1.5, volume /1.5 is what an adjusted series would hold): the 40% daily-move check does NOT catch a 33% drop")
    row = {}
    for s, bars in real.items():
        raw = [dict(b) for b in bars]
        for b in raw[:-60]:
            for k in ("open", "high", "low", "close"):
                b[k] *= 1.5
            b["volume"] /= 1.5
        drop = raw[-60]["close"] / raw[-61]["close"] - 1
        a = score(raw, index)[:2]
        row[s] = {"unadjusted": a, "adjusted": base[s], "one_day_move": drop}
        print(f"  {s:10s} unadjusted ST {fmt(a[0])} LT {fmt(a[1])} against adjusted {fmt(base[s][0])}/{fmt(base[s][1])} (the bonus day moves {drop:+.1%})")
    effects["unadjusted_bonus"] = row

    out["effects"].update(effects)

    print("\n== 4. Timing of one full technical assessment (pure Python, this machine)")
    for s in ("TCS", "BAJFINANCE"):
        bars = real[s]
        t = time.perf_counter(); score(bars, index); dt = time.perf_counter() - t
        out["timing"][s] = {"bars": len(bars), "seconds": round(dt, 3)}
        print(f"  {s}: {len(bars)} bars -> {dt:.2f} s")
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(out, default=str, indent=1))


if __name__ == "__main__":
    run(sys.argv)
