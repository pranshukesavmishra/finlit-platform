"""Scoring-only ST/LT v14.3 port; additive to the financial-health model.

Pine defines formulas; FinEdge, calculations and Upstox supply the observations.
No missing signal is filled or silently removed from the denominator.
"""
from datetime import date
import hashlib
import json

try:
    from .technical_series import ema, rma, rsi, macd, atr_adx, obv, weekly_closes
except ImportError:
    from technical_series import ema, rma, rsi, macd, atr_adx, obv, weekly_closes

try:
    from .financial_records import field_date, first, items, num
except ImportError:
    from financial_records import field_date, first, items, num


MODEL_VERSION = "st-lt-14.3"
SOURCE_SHA256 = "8fd234be9c7c76f750eb315530f525e9a8b8359ee90efbb183e524f8e618e078"
# Keys, reader labels and source weights. The last slot is reserved for a reason.
ST = (
    ("ema_stack", "EMA alignment", 10, None),
    ("price_ema20", "Price and short-term trend", 8, None),
    ("macd", "Daily MACD", 6, None),
    ("rsi", "Daily RSI", 8, None),
    ("obv", "Buying and selling volume", 4, None),
    ("rs_rating", "Relative strength rating", 8, None),
    ("extension", "Price extension", 4, None),
    ("consolidation", "9 EMA consolidation", 10, None),
    ("squeeze", "Volatility squeeze", 5, None),
    ("gap", "Opening gap", 3, None),
    ("sector", "Sector relative strength", 4, None),
    ("candles", "Candle and price action", 10, None),
    ("sfp", "Swing failure", 8, None),
    ("leadership", "Relative strength leadership", 6, None),
    ("value_migration", "Value-area migration", 6, None),
)
LT = (
    ("stage", "Market stage", 18, None),
    ("rs_rating", "Relative strength rating", 12, None),
    ("leadership", "Relative strength leadership", 10, None),
    ("sector", "Sector relative strength", 8, None),
    ("price_ema200", "Price vs long-term trend", 7, None),
    ("volume_persistence", "Breakout volume persistence", 7, None),
    ("sfp", "Major swing failure", 6, None),
    ("ema200_slope", "Long-term trend direction", 5, None),
    ("ema50_200", "Medium vs long-term trend", 5, None),
    ("weekly_rsi", "Weekly RSI", 5, None),
    ("weekly_macd", "Weekly MACD", 5, None),
    ("structure", "52-week price structure", 5, None),
    ("obv_trend", "Long-term volume trend", 5, None),
    ("ema100_200", "Long-term EMA alignment", 2, None),
)


def normalise_bars(payload, as_of):
    """Preserve missing/invalid observations; never manufacture OHLC from close."""
    result = {}
    for row in items(payload, "price", "quotes", "data", "prices"):
        day = field_date(row)
        if not day or day > as_of:
            continue
        aliased = {
            "open": ("open", "open_price", "openPrice"),
            "high": ("high", "high_price", "highPrice"),
            "low": ("low", "low_price", "lowPrice"),
            "close": ("close", "close_price", "closePrice"),
            "volume": ("volume", "tradedVolume"),
        }
        # The provider pads days it has no trading record for (a holiday, a missed feed) with an all-zero row. That is not a session and the chart
        # has no bar there: keep it out, as the financial-health inputs already do (premium_data). A zero beside real prices or volume stays a bad bar,
        # and a row with missing (not zero) values stays a gap. (Before this, one such row, e.g. on 3 Sep 2026, cut the usable history to the
        # bars after it and withheld both scores.)
        if all(first(row, *names) == 0 for names in aliased.values()):
            continue
        bar = {"date": day.isoformat()}
        for key, aliases in aliased.items():
            value = first(row, *aliases)
            bar[key] = value if value is not None and (value >= 0 if key == "volume" else value > 0) else None
        if all(bar[k] is not None for k in ("open", "high", "low", "close")):
            if not bar["low"] <= min(bar["open"], bar["close"]) <= max(bar["open"], bar["close"]) <= bar["high"]:
                bar.update(open=None, high=None, low=None)
        result[day] = bar
    return [result[day] for day in sorted(result)]


def has_ohlcv(bars, count=252):
    return len(bars) >= count and all(all(row[k] is not None for k in ("open", "high", "low", "close", "volume")) for row in bars[-count:])


def resolve_technical_prices(primary, provider, as_of, fallback=None):
    """Choose one series; never splice exchanges or fill absent candle values."""
    bars = normalise_bars(primary, as_of)
    provider = "Upstox" if "upstox" in str(provider).lower() else "FinEdge" if "finedge" in str(provider).lower() else provider
    notes = []
    fresh = lambda rows: bool(rows) and 0 <= (as_of - date.fromisoformat(rows[-1]["date"])).days <= 10
    if (not has_ohlcv(bars) or not fresh(bars)) and fallback:
        try:
            candidate = normalise_bars(fallback(), as_of)
            if has_ohlcv(candidate) and fresh(candidate):
                bars, provider = candidate, "Upstox"
                notes.append("Daily candles use one Upstox series because the dashboard price source did not provide complete OHLCV history.")
            else:
                notes.append("The secondary provider did not supply sufficient complete daily candles.")
        except Exception:
            notes.append("The secondary daily-candle request was unavailable.")
    return {"bars": bars, "provider": provider or "Unavailable", "notes": notes, "throughDate": as_of.isoformat()}


def score_rating(score):
    if score is None:
        return "Unavailable"
    return "Strong Buy" if score >= 50 else "Buy" if score >= 20 else "Hold" if score > -20 else "Reduce" if score > -50 else "Sell"


def combine_verdict(st, lt):
    if st is None or lt is None:
        return {"label": "Unavailable", "tone": "muted"}
    band = lambda x: 0 if x >= 20 else 2 if x <= -20 else 1
    labels = (("STRONG BUY", "BUY", "BOUNCE ONLY, DON'T INVEST"),
              ("ACCUMULATE ON DIPS", "HOLD", "REDUCE"),
              ("BUY THE DIP, WAIT FOR ST TURN", "REDUCE", "SELL / AVOID"))
    tones = (("positive", "positive", "caution"), ("positive", "caution", "negative"), ("positive", "negative", "negative"))
    a, b = band(st), band(lt)
    return {"label": labels[a][b], "tone": tones[a][b]}


def summarise_signals(specs, signals, sector_enabled=False, value_enabled=True, stage=None):
    """Only explicitly disabled options leave the PDF denominator."""
    rows = []
    for key, label, weight, rule in specs:
        disabled = (key == "sector" and not sector_enabled) or (key == "value_migration" and not value_enabled)
        signal, detail = signals.get(key, (None, rule or "Required complete daily OHLCV history is unavailable or too short for this signal."))
        signal = num(signal)
        if signal is not None and not -1 <= signal <= 1:
            signal, detail = None, "Signal is outside the model's permitted range."
        rows.append({"key": key, "label": label, "weight": weight, "signal": None if disabled else signal,
                     "status": "disabled" if disabled else "available" if signal is not None else "unavailable",
                     "detail": "Optional factor is switched off." if disabled else detail})
    enabled = [row for row in rows if row["status"] != "disabled"]
    known = [row for row in enabled if row["signal"] is not None]
    denominator = sum(row["weight"] for row in enabled)
    complete = len(known) == len(enabled)
    # LT stage is a mandatory safeguard as well as a scored component.
    has_stage = any(row["key"] == "stage" for row in enabled)
    if has_stage and stage not in (1, 2, 3, 4):
        complete = False
    raw_score = 100 * sum(row["weight"] * row["signal"] for row in known) / denominator if complete else None
    score = min(raw_score, 19) if raw_score is not None and has_stage and stage in (3, 4) else raw_score
    capped = score is not None and score != raw_score
    return {"score": score, "rating": score_rating(score),
            "status": "ready" if complete else "incomplete", "availableCount": len(known), "requiredCount": len(enabled),
            "stageCapped": capped, **({"uncappedScore": raw_score} if capped else {}), "factors": rows}


def build_technical_assessment(price_input, as_of, benchmarks=None, shares_cr=None):
    try:
        from .technical_scoring import scoring_signals
    except ImportError:
        from technical_scoring import scoring_signals
    bars = price_input.get("bars", [])
    last_bad = max((i for i,row in enumerate(bars) if any(row.get(k) is None for k in ("open","high","low","close","volume"))), default=-1)
    valid = bars[last_bad+1:]
    fresh = bool(valid) and 0 <= (as_of-date.fromisoformat(valid[-1]["date"])).days <= 10
    st, lt, observations = scoring_signals(valid, benchmarks or {}, shares_cr, as_of) if fresh else ({},{},{})
    short = summarise_signals(ST,st)
    long = summarise_signals(LT,lt,stage=observations.get("stage"))
    notes = list(price_input.get("notes", []))
    used_names = observations.get("benchmarksUsed", list((benchmarks or {}).keys()))
    for name, value in (benchmarks or {}).items():
        if name not in used_names:
            continue
        notes.extend(value.get("notes", []))
    if short["score"] is None or long["score"] is None:
        notes.append("An assessment is unavailable where required price or benchmark history is missing. Missing signals are listed below.")
    if not fresh:
        notes.append("Complete daily OHLCV history is missing or more than 10 calendar days old.")
    if last_bad>=0:
        notes.append(f"Only the {len(valid)} consecutive complete candles after the latest data gap can be used; missing candles were not filled.")
    if price_input.get("provider") == "Upstox":
        notes.append("Daily candles use Upstox. Corporate-action adjustment has not been independently verified against FinEdge's adjusted closing-price history.")
    notes.append("Scores use the latest completed daily session; weekly signals use the preceding week.")
    if shares_cr is None:
        notes.append("Shares outstanding are unavailable, so benchmark selection falls back to Nifty 500 under the model's rule.")
    digest = hashlib.sha256(json.dumps({"prices":bars,"benchmarks":benchmarks or {},"shares_cr":shares_cr,"source":SOURCE_SHA256},sort_keys=True,allow_nan=False).encode()).hexdigest()
    return {"modelVersion":MODEL_VERSION, "sourceCodeSha256":SOURCE_SHA256, "inputHash":digest, "status":"ready" if short["score"] is not None and long["score"] is not None else "incomplete",
            "asOf":bars[-1]["date"] if bars else None, "provider":price_input.get("provider","Unavailable"),
            "dailyBars":len(bars), "usableDailyBars":len(valid), "fresh":fresh,
            "shortTerm":{**short,"horizon":"5–20 sessions"}, "longTerm":{**long,"horizon":"6–18 months"},
            "verdict":combine_verdict(short["score"],long["score"]), "notes":list(dict.fromkeys(notes)),
            "observations":observations,
            "benchmarkSources":{name:{"provider":value.get("provider"), "asOf":value["bars"][-1]["date"] if value.get("bars") else None, "bars":len(value.get("bars",[]))} for name,value in (benchmarks or {}).items()},
            "options":{"sectorRS":False,"valueMigration":True}}
