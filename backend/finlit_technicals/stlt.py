"""ST / LT technical scores, their calculation and the trend alignment: a Python port of the TradingView indicator
"ST/LT Score Breakdown & Peers v1.2" (the scores of ST/LT Technical Score v14.3, unchanged). No data source
inside: pass daily OHLCV frames from any vendor.

Daily bars in, for the last bar out:
  short-term score  15 components, weights 10+8+6+8+4+8+4+10+5+3+4+10+8+6+6 = 100
  long-term score   14 components, weights 7+5+5+2+5+5+12+5+5+18+8+7+6+10 = 100
  each component    reading now, signal (-1 to +1), weight, points = weight x signal x 100 / weights in use
  trend alignment   short-term band x long-term band (+20 or more Positive, -20 or less Negative, else Neutral)
The labels describe the chart's condition (Very strong ... Very weak, "Strong on both timeframes" ...); there are
no trade calls, trade plans, entries or stops. Not investment advice.

Pine's rules for na, EMA seeding, weekly bars and the benchmark series are kept (see pine.py), so with the same
bars and the same settings the numbers match the chart. Inputs keep the Pine defaults (StltParams).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import pine as P
from .pine import NA, ge, gt, le, lt, sg, shift

# TradingView symbols of the benchmark indices and their names in the table
BENCH_SYMS = {"nifty500": "NSE:CNX500", "nifty50": "NSE:NIFTY", "midcap100": "NSE:CNXMIDCAP",
              "smallcap100": "NSE:CNXSMALLCAP"}
BENCH_NAMES = {"NSE:CNX500": "Nifty 500", "NSE:NIFTY": "Nifty 50", "NSE:CNXMIDCAP": "Midcap 100",
               "NSE:CNXSMALLCAP": "Smallcap 100"}
CHOICE_NAMES = {"auto": "Auto (by market cap)", "nifty500": "Nifty 500", "nifty50": "Nifty 50",
                "midcap100": "Nifty Midcap 100", "smallcap100": "Nifty Smallcap 100"}


@dataclass
class StltParams:
    bench_choice: str = "auto"          # auto | nifty500 | nifty50 | midcap100 | smallcap100
    large_cut: float = 107000.0         # Rs crore (AMFI large-cap cut-off)
    mid_cut: float = 32800.0
    sfp_on: bool = True
    sfp_vol: str = "Above-average volume"   # or "None"
    sfp_vol_mult: float = 1.0
    sfp_max_age: int = 5
    doji_strict: float = 0.10
    doji_body: float = 0.35
    poc_near_atr: float = 0.5
    tol_pct: float = 1.0
    max_dist: float = 2.0
    min_vol: float = 100000
    flat_band: float = 1.5
    fresh_bars: int = 60
    vol_mult: float = 1.5
    persist_mult: float = 1.2
    hard_block: bool = True
    fresh_only: bool = False
    base_lookback: int = 120
    rs_len_lt: int = 252
    rs_len_st: int = 126
    beta_len: int = 126
    rs_lead_len: int = 20
    idx_drop_pct: float = 4.0
    use_sector: bool = False
    sector_sym: str = "NSE:CNXAUTO"
    sector_len: int = 63
    bb_len: int = 20
    bb_mult: float = 2.0
    bb_pct_len: int = 126
    squeeze_thresh: float = 20
    expand_thresh: float = 80
    gap_thresh: float = 2.0
    ext_breakaway: float = 1.5
    ext_exhaustion: float = 3.0
    st_piv_lr: int = 5
    lt_piv_lr: int = 15
    vp_bars: int = 60
    vp_bins: int = 24
    use_climax: bool = True
    climax_gain: float = 25.0
    climax_ext: float = 7.0
    sqz_method: str = "TTM (BB inside Keltner)"   # or "BB width percentile"
    use_va_mig: bool = True
    vp_hist_bars: int = 750
    ipo_on: bool = True


@dataclass
class Row:
    name: str
    reading: str
    signal: float
    weight: float
    points: float
    on: bool = True
    tip: str = ""
    key: str = ""             # stable id for the website (ema_stack, rsi, stage ...)


ST_KEYS = ["ema_stack", "price_vs_ema20", "macd", "rsi", "obv", "rs_rating_short", "extension", "ema9_consolidation",
           "squeeze", "gap", "sector_rs", "price_action", "sfp", "rs_leadership", "value_area_migration"]
LT_KEYS = ["price_vs_ema200", "ema200_slope", "ema50_vs_ema200", "ema100_vs_ema200", "weekly_rsi", "weekly_macd",
           "rs_rating_long", "structure_52w", "obv_trend", "stage", "sector_rs", "volume_persistence", "major_sfp",
           "rs_leadership"]


def tips(p: "StltParams") -> Dict[str, Dict[str, str]]:
    """How each component turns its reading into a signal (the indicator's tooltips)."""
    st = {
        "ema_stack": "(±1 for EMA 9 vs 20, ±1 for EMA 20 vs 50) / 2 × trend factor",
        "price_vs_ema20": "(±1 close vs EMA 20, ±1 EMA 20 rising over 3 bars) / 2 × trend factor",
        "macd": "(±1 MACD vs signal, ±1 histogram rising) / 2 × trend factor",
        "rsi": "Bull regime (close and EMA 50 above EMA 200): 55-75 = +1, 75-80 = +0.5, above 80 = -0.5, 45-55 = +0.5, "
               "40-45 = 0, below 40 = -1. Bear regime: 60+ = 0, 40-60 = -0.5, below 40 = -1. Neutral: 55-70 = +1, "
               "70-80 = +0.5, 45-55 = 0, 30-45 = -0.5, else -1.",
        "obv": "+1 above, -1 below",
        "rs_rating_short": f"Raw = 0.6 × 21-day + 0.4 × 63-day beta-adjusted excess return, ranked over {p.rs_len_st} bars. "
                           "85+ = +1, 70-85 = +0.5, 40-70 = 0, 20-40 = -0.5, below 20 = -1.",
        "extension": "Under 2 ATR = +1, 2-3 ATR = -0.5, 3+ ATR = -1 (stretched)",
        "ema9_consolidation": f"Uptrend (close > EMA 50, 9 > 20 > 50) and close within {p.max_dist:g}% above EMA 9: scan match = +1, "
                              "4 of 5 touches = +0.75, 3 = +0.5, +0.25 for 2+ dojis. Mirror for a downtrend rejection: -0.5 / -1.",
        "squeeze": "Squeeze breakout +1, squeeze with positive momentum +0.5, squeeze otherwise -0.25, extended volatility -0.5",
        "gap": "Breakaway gap +1, exhaustion gap -1, gap down that closes lower -0.5",
        "sector_rs": "Above +5% = +1, +1-5% = +0.5, ±1% = 0, -1 to -5% = -0.5, below -5% = -1",
        "price_action": "Climax run -1; hammer / engulfing at EMA 9 above EMA 20 +1; doji at EMA 9 + POC +1; strong bull bar +0.75; "
                        "upper-wick rejection or bearish wide bar -1; doji at EMA 9 +0.5; +0.25 for a dry-volume pullback above EMA 20",
        "sfp": "Active bullish SFP +0.75 (+1 once confirmed), bearish -0.75 (-1 confirmed); if both, the newer one counts",
        "rs_leadership": "Strong leader while the index falls +1, holding up +0.5, lagging a weak index -0.5",
        "value_area_migration": "This swing's value area vs the previous swing's: entirely higher +1, POC higher +0.5, "
                                "POC lower -0.5, entirely lower -1",
    }
    lt = {
        "price_vs_ema200": "More than 2% above = +1, more than 2% below = -1, inside ±2% = 0",
        "ema200_slope": "+1 rising, -1 falling",
        "ema50_vs_ema200": "+1 above, -1 below",
        "ema100_vs_ema200": "+1 above, -1 below",
        "weekly_rsi": "55-75 = +1, 45-55 = 0, 40-45 or above 75 = -0.5, below 40 = -1",
        "weekly_macd": "(±1 vs signal, ±1 vs zero) / 2",
        "rs_rating_long": f"Raw = 0.4 × 63-day + 0.2 × 126 + 0.2 × 189 + 0.2 × 252-day beta-adjusted excess return, ranked over "
                          f"{p.rs_len_lt} bars. 85+ = +1, 70-85 = +0.5, 40-70 = 0, 20-40 = -0.5, below 20 = -1.",
        "structure_52w": "Within 15% of the 52W high and 30%+ above the low = +1; below 60% of the high = -1; else 0",
        "obv_trend": "+1 above, -1 below",
        "stage": f"Stage 2 fresh breakout +1, Stage 2 established +0.5, Stage 1 0, Stage 3 -0.75, Stage 4 -1. Stage from the "
                 f"150-day SMA slope (flat band ±{p.flat_band:g}%) and close vs it.",
        "sector_rs": "Same signal as the short-term sector row",
        "volume_persistence": "Within 10 bars of a base breakout: 2-3 heavy bars +1, 1 = 0, none -0.5. Later in Stage 2: 2-3 heavy bars +0.5.",
        "major_sfp": f"As the ST SFP, on the {p.lt_piv_lr}-bar swings, active 3× longer",
        "rs_leadership": "New 52W high while the index is down +1; RS line at a 52W high +1 (price still 3%+ below its high) or +0.75; "
                         "holding up vs a weak index +0.5; RS line at a 52W low -1; lagging a weak index -0.5",
    }
    return {"st": st, "lt": lt}


@dataclass
class StltResult:
    symbol: str
    date: pd.Timestamp
    close: float
    bars: int
    st_score: float
    lt_score: float
    st_raw: float
    lt_raw: float
    lt_norm: float
    st_div: float
    lt_div: float
    gated: bool
    stage: int
    s_band: int
    l_band: int
    alignment: str
    bench_name: str
    adx: float
    trend_mult: float
    st_rows: List[Row]
    lt_rows: List[Row]
    notes: List[str] = field(default_factory=list)
    series: Optional[pd.DataFrame] = None     # st / lt score on every bar (for checks and charts)


# ─── small text helpers (the Pine table's number formats) ───────────────────────────────────────────────
def _num(x: float, dec: int) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "NaN"
    return f"{x:.{dec}f}"


def f_s(x: float) -> str:
    """f_cxS: signal, 2 decimals with a + sign."""
    return "n/a" if x is None or math.isnan(x) else ("+" if x > 0 else "") + f"{x:.2f}"


def f_p(x: float) -> str:
    """f_cxP: points, 1 decimal with a + sign."""
    return "n/a" if x is None or math.isnan(x) else ("+" if x > 0 else "") + f"{x:.1f}"


def pround(x: float) -> int:
    """math.round in Pine: halves round away from zero (Python's round() rounds them to even)."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


RATINGS = {2: "Very strong", 1: "Strong", 0: "Neutral", -1: "Weak", -2: "Very weak"}
BAND_NAMES = {1: "Positive", 0: "Neutral", -1: "Negative"}
# short-term band x long-term band -> what the two trends look like together
ALIGNMENT = {
    (1, 1): "Strong on both timeframes",
    (1, 0): "Short-term strength, no long-term trend",
    (1, -1): "Short-term bounce within a long-term downtrend",
    (0, 1): "Long-term uptrend, short-term pause",
    (0, 0): "No clear trend",
    (0, -1): "Long-term downtrend, short-term flat",
    (-1, 1): "Short-term pullback within a long-term uptrend",
    (-1, 0): "Short-term weakness, no long-term trend",
    (-1, -1): "Weak on both timeframes",
}


def rating_code(x: float) -> int:
    """+2 at +50 or more, +1 at +20 or more, 0 in between, -1 at -20 or less, -2 at -50 or less."""
    return 2 if x >= 50 else 1 if x >= 20 else 0 if x > -20 else -1 if x > -50 else -2


def rate(x: float) -> str:
    return RATINGS[rating_code(x)]


def band(x: float) -> int:
    return 1 if x >= 20 else -1 if x <= -20 else 0


def band_text(x: float) -> str:
    return "Positive (≥ +20)" if x >= 20 else "Negative (≤ −20)" if x <= -20 else "Neutral (−20 to +20)"


def alignment(sb: int, lb: int) -> str:
    return ALIGNMENT[(sb, lb)]


def alignment_code(sb: int, lb: int) -> str:
    return f"st_{BAND_NAMES[sb].lower()}_lt_{BAND_NAMES[lb].lower()}"


# ─── bars ──────────────────────────────────────────────────────────────────────────────────────────────
def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLCV sorted by date, one row per day, no empty closes."""
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    d = df.copy()
    d.index = pd.to_datetime(d.index).normalize()
    d = d[~d.index.duplicated(keep="last")].sort_index()
    for k in ("open", "high", "low", "close", "volume"):
        if k not in d:
            d[k] = d["close"] if k != "volume" else 0.0
        d[k] = pd.to_numeric(d[k], errors="coerce").astype(float)
    d = d[d["close"].notna() & (d["close"] > 0)]
    d["volume"] = d["volume"].fillna(0.0)
    for k in ("open", "high", "low"):
        d[k] = d[k].fillna(d["close"])
    return d[["open", "high", "low", "close", "volume"]]


def week_start(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    """Monday of each date's week (TradingView's weekly bars run Monday to Sunday)."""
    idx = pd.DatetimeIndex(idx).normalize()
    return idx - pd.to_timedelta(idx.weekday, unit="D")


def weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly bars from daily bars, indexed by the week's Monday."""
    if len(df) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    g = df.groupby(week_start(df.index))
    w = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                      "close": g["close"].last(), "volume": g["volume"].sum()})
    w.index.name = "week"
    return w


def align(idx: pd.DatetimeIndex, s: pd.Series) -> np.ndarray:
    """A daily series from another symbol on these dates (request.security: the latest bar at or before)."""
    if s is None or len(s) == 0:
        return np.full(len(idx), NA)
    s = s[~s.index.duplicated(keep="last")].sort_index()
    return s.reindex(idx, method="ffill").to_numpy(dtype=float)


def bench_pack(b: pd.DataFrame, lead_len: int) -> pd.DataFrame:
    """f_bpack: every benchmark statistic on the index's own daily series."""
    c = b["close"].to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        pack = {
            "close": c,
            "hiN": P.highest(c, lead_len),
            "ll": np.where(lt(P.lowest(c, 5), shift(P.lowest(c, lead_len), 5)), 1.0, 0.0),
            "hi52": P.highest(c, 252),
            "ret": P.change(np.log(c)),
            "r21": c / shift(c, 21) - 1, "r63": c / shift(c, 63) - 1, "r126": c / shift(c, 126) - 1,
            "r189": c / shift(c, 189) - 1, "r252": c / shift(c, 252) - 1,
        }
    return pd.DataFrame(pack, index=b.index)


# ─── swing failure pattern state ────────────────────────────────────────────────────────────────────────
class _SFP:
    __slots__ = ("lvl", "hi", "lo", "bar", "conf", "conf_bar", "dead")

    def __init__(self):
        self.lvl = NA
        self.hi = NA
        self.lo = NA
        self.bar = None
        self.conf = False
        self.conf_bar = None
        self.dead = False

    def update(self, is_new: bool, lvl: float, is_bull: bool, i: int, h: float, l: float, c: float):
        if is_new:
            self.lvl, self.hi, self.lo, self.bar = lvl, h, l, i
            self.conf, self.conf_bar, self.dead = False, None, False
        elif self.bar is not None and not self.dead:
            if is_bull:
                if c < self.lo:
                    self.dead = True
                elif not self.conf and c > self.hi:
                    self.conf, self.conf_bar = True, i
            else:
                if c > self.hi:
                    self.dead = True
                elif not self.conf and c < self.lo:
                    self.conf, self.conf_bar = True, i

    def age(self, i: int) -> int:
        return 9999 if self.bar is None else i - self.bar


def _sfp_scan(levels: list, is_high: bool, h: float, l: float, c: float):
    """f_sfpScan: every swing level the bar trades through is used up; return the most extreme failed one."""
    swept, swept_bar = NA, None
    for k in range(len(levels) - 1, -1, -1):
        v, b = levels[k]
        hit = h > v if is_high else l < v
        if hit:
            failed = c < v if is_high else c > v
            if failed and (math.isnan(swept) or (v > swept if is_high else v < swept)):
                swept, swept_bar = v, b
            del levels[k]
    return swept, swept_bar


def _push(levels: list, v: float, b: int):
    if not math.isnan(v):
        levels.append((v, b))
        if len(levels) > 10:
            del levels[0]


def _sfp_sig(bull_a: bool, bu: _SFP, bear_a: bool, be: _SFP) -> float:
    sb = (1.0 if bu.conf else 0.75) if bull_a else 0.0
    sr = (-1.0 if be.conf else -0.75) if bear_a else 0.0
    if bull_a and bear_a:
        return sb if bu.bar > be.bar else sr
    return sb + sr


# ─── volume profile ─────────────────────────────────────────────────────────────────────────────────────
def volume_profile(h: np.ndarray, l: np.ndarray, v: np.ndarray, end: int, length: int, n_bins: int):
    """f_vp: range-distributed profile of bars end-length+1 .. end -> (POC, VAH, VAL)."""
    if length < 2:
        return NA, NA, NA
    hs = h[end - length + 1:end + 1]
    ls = l[end - length + 1:end + 1]
    vs = np.nan_to_num(v[end - length + 1:end + 1])
    hi_r, lo_r = float(np.max(hs)), float(np.min(ls))
    bin_sz = (hi_r - lo_r) / n_bins
    if not bin_sz > 0:
        return NA, NA, NA
    bins = np.zeros(n_bins)
    for hh, ll, vv in zip(hs, ls, vs):
        rng = hh - ll
        b0 = int(min(n_bins - 1, max(0, math.floor((ll - lo_r) / bin_sz))))
        b1 = int(min(n_bins - 1, max(0, math.floor((hh - lo_r) / bin_sz))))
        if rng <= 0 or b0 == b1:
            bins[b0] += vv
        else:
            for b in range(b0, b1 + 1):
                b_lo = lo_r + b * bin_sz
                ov = min(hh, b_lo + bin_sz) - max(ll, b_lo)
                if ov > 0:
                    bins[b] += vv * ov / rng
    poc_i = int(np.argmax(bins))
    total = bins.sum()
    inc = bins[poc_i]
    lo_i = hi_i = poc_i
    while inc < 0.7 * total and (lo_i > 0 or hi_i < n_bins - 1):
        vb = bins[lo_i - 1] if lo_i > 0 else -1.0
        va = bins[hi_i + 1] if hi_i < n_bins - 1 else -1.0
        if va >= vb:
            hi_i += 1
            inc += va
        else:
            lo_i -= 1
            inc += vb
    return lo_r + (poc_i + 0.5) * bin_sz, lo_r + (hi_i + 1) * bin_sz, lo_r + lo_i * bin_sz


# ─── the scores ─────────────────────────────────────────────────────────────────────────────────────────
def compute(df: pd.DataFrame, benches: Dict[str, pd.DataFrame], p: StltParams = StltParams(), symbol: str = "",
            shares: Optional[float] = None, cap_class: Optional[int] = None,
            sector: Optional[pd.DataFrame] = None) -> StltResult:
    """Scores for the last bar of `df` (daily OHLCV, oldest first).

    benches     {TradingView symbol: daily OHLCV} for the benchmark indices you have (NSE:CNX500, NSE:NIFTY,
                NSE:CNXMIDCAP, NSE:CNXSMALLCAP). A missing one counts as na, as on the chart.
    shares      shares outstanding (for the market-cap buckets of the Auto benchmark), or
    cap_class   1 large, 2 mid, 3 small to fix the bucket; with neither, Auto uses Nifty 500 (as Pine does
                when TradingView has no share count).
    sector      the sector index (only with use_sector).
    """
    d = clean(df)
    n = len(d)
    if n < 2:
        raise ValueError(f"{symbol or 'symbol'}: {n} daily bar(s); the scores need price history")
    idx = d.index
    o, h, l, c, v = (d[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close", "volume"))
    bi = np.arange(n)
    notes: List[str] = []
    np_err = np.seterr(divide="ignore", invalid="ignore")
    try:
        # core series
        e9, e20 = P.ema(c, 9), P.ema(c, 20)
        e50_std = P.ema(c, 50)
        e50 = np.where(p.ipo_on & np.isnan(e50_std), P.seed_ema(c, 50), e50_std)
        e100, e200 = P.ema(c, 100), P.ema(c, 200)
        atr14 = P.atr(h, l, c, 14)
        ext = (c - e20) / atr14
        _, _, adx14 = P.dmi(h, l, c, 14, 14)
        m_line, m_sig, m_hist = P.macd(c, 12, 26, 9)
        rsi14 = P.rsi(c, 14)
        obv_s = P.obv(c, v)
        av50_std = P.sma(v, 50)
        av50_yng = P.sma_var(v, np.maximum(1, np.minimum(50, bi - 4)))
        avg_vol50 = np.where(p.ipo_on & np.isnan(av50_std), av50_yng, av50_std)
        vol3 = P.sma(v, 3)
        hh20 = shift(P.highest(h, 20), 1)
        hi52_h = P.highest(h, 252)

        # weekly: MACD and RSI of the last completed week
        w = weekly(d)
        wc = w["close"].to_numpy(dtype=float)
        wm, ws, _ = P.macd(wc, 12, 26, 9)
        wr = P.rsi(wc, 14)
        pos = np.searchsorted(w.index.values, week_start(idx).values)
        w_macd, w_sig, w_rsi = shift(wm, 1)[pos], shift(ws, 1)[pos], shift(wr, 1)[pos]

        # benchmark (auto by market cap)
        bench_sym = BENCH_SYMS.get(p.bench_choice, "NSE:CNX500")
        is_auto = p.bench_choice == "auto"
        if cap_class is not None:
            cap_cls = np.full(n, int(cap_class))
        elif shares and shares > 0:
            mcap = shares * c / 1e7
            cap_cls = np.where(mcap >= p.large_cut, 1, np.where(mcap >= p.mid_cut, 2, 3))
        else:
            cap_cls = np.zeros(n, dtype=int)
        b_cls = cap_cls if is_auto else np.zeros(n, dtype=int)
        packs = {}
        for sym in ("NSE:CNX500", "NSE:NIFTY", "NSE:CNXMIDCAP", "NSE:CNXSMALLCAP"):
            src = benches.get(sym)
            if src is not None and len(src):
                bp = bench_pack(clean(src), p.rs_lead_len)
                packs[sym] = {k: align(idx, bp[k]) for k in bp.columns}
        empty = {k: np.full(n, NA) for k in ("close", "hiN", "ll", "hi52", "ret", "r21", "r63", "r126", "r189", "r252")}
        pm = packs.get(bench_sym, empty)
        pl_, pd_, ps_ = (packs.get(s, empty) for s in ("NSE:NIFTY", "NSE:CNXMIDCAP", "NSE:CNXSMALLCAP"))

        def pick(k):
            val = np.where(b_cls == 1, pl_[k], np.where(b_cls == 2, pd_[k], np.where(b_cls == 3, ps_[k], pm[k])))
            return np.where(np.isnan(val), pm[k], val)

        bench, b_hi_n, idx_ll, b_hi52 = pick("close"), pick("hiN"), gt(pick("ll"), 0.5), pick("hi52")
        ret_b, b_r21, b_r63, b_r126, b_r189, b_r252 = (pick(k) for k in ("ret", "r21", "r63", "r126", "r189", "r252"))
        last_cls = int(b_cls[-1])
        if last_cls == 1 and not math.isnan(pl_["close"][-1]):
            bench_name = "Nifty 50"
        elif last_cls == 2 and not math.isnan(pd_["close"][-1]):
            bench_name = "Midcap 100"
        elif last_cls == 3 and not math.isnan(ps_["close"][-1]):
            bench_name = "Smallcap 100"
        elif is_auto:
            bench_name = "Nifty 500"
        else:
            bench_name = CHOICE_NAMES.get(p.bench_choice, p.bench_choice)
        if math.isnan(bench[-1]):
            notes.append(f"no {bench_name} prices: the RS rows read as na")
        if is_auto and cap_class is None and not (shares and shares > 0):
            notes.append("market cap unknown: Auto benchmark = Nifty 500 (set the cap bucket to match TradingView)")

        # candle anatomy
        rng_t = h - l
        body_t = np.abs(c - o)
        pos_r = rng_t > 0
        safe = np.where(pos_r, rng_t, 1.0)
        clv = np.where(pos_r, (c - l) / safe, 0.5)
        up_wick = np.where(pos_r, (h - np.maximum(o, c)) / safe, 0.0)
        lo_wick = np.where(pos_r, (np.minimum(o, c) - l) / safe, 0.0)
        is_hammer = (lo_wick >= 0.5) & (clv >= 0.6)
        is_engulf = (c > o) & lt(shift(c), shift(o)) & ge(c, shift(o)) & le(o, shift(c))
        is_inside = le(h, shift(h)) & ge(l, shift(l))
        is_nr7 = le(rng_t, P.lowest(rng_t, 7))
        is_doji = pos_r & (body_t <= p.doji_strict * rng_t)
        is_small = pos_r & (body_t <= p.doji_body * rng_t)
        strong_bull = (c > o) & (clv >= 0.7) & (body_t >= 0.5 * rng_t)
        bear_wide = (c < o) & (clv <= 0.3) & ge(rng_t, 1.2 * atr14)
        up_reject = (up_wick >= 0.5) & ge(h, hh20 * 0.99)
        dry_up = lt(vol3, 0.8 * avg_vol50)
        doji_at_e9 = is_small & ge(c, e9) & le(l, e9 + 0.25 * atr14) & gt(c, e20) & gt(e9, e20)

        # beta and relative strength
        ret_s = P.change(np.log(c))
        beta_raw = P.correlation(ret_s, ret_b, p.beta_len) * (P.stdev(ret_s, p.beta_len) / P.stdev(ret_b, p.beta_len))
        beta = np.clip(P.nz(beta_raw, 1.0), 0.3, 3.0)

        def roc_adj(k, b_r):
            return (c / shift(c, k) - 1) - beta * b_r

        exc21, exc63, exc126 = roc_adj(21, b_r21), roc_adj(63, b_r63), roc_adj(126, b_r126)
        exc189, exc252 = roc_adj(189, b_r189), roc_adj(252, b_r252)
        rs_raw_lt = 0.4 * exc63 + 0.2 * exc126 + 0.2 * exc189 + 0.2 * exc252
        rs_raw_st = 0.6 * exc21 + 0.4 * exc63
        rs_rating_lt = P.percentrank(rs_raw_lt, p.rs_len_lt)
        rs_rating_st = P.percentrank(rs_raw_st, p.rs_len_st)

        def rs_sig(r):
            return np.where(ge(r, 85), 1.0, np.where(ge(r, 70), 0.5, np.where(ge(r, 40), 0.0, np.where(ge(r, 20), -0.5, -1.0))))

        # sector RS (off by default)
        if p.use_sector:
            sec_close = align(idx, clean(sector)["close"]) if sector is not None and len(sector) else np.full(n, NA)
        else:
            sec_close = pm["close"]
        sector_roc = (c / shift(c, p.sector_len) - 1) - (sec_close / shift(sec_close, p.sector_len) - 1)
        if p.use_sector:
            sector_sig = np.where(np.isnan(sector_roc), 0.0, np.where(gt(sector_roc, 0.05), 1.0, np.where(gt(sector_roc, 0.01), 0.5,
                         np.where(gt(sector_roc, -0.01), 0.0, np.where(gt(sector_roc, -0.05), -0.5, -1.0)))))
            if sector is None or not len(sector):
                notes.append(f"sector RS is on but {p.sector_sym} has no prices: it counts 0")
        else:
            sector_sig = np.zeros(n)

        # RS leadership
        rs_line = c / bench
        s_hi_n = P.highest(h, p.rs_lead_len)
        b_dd = (b_hi_n - bench) / b_hi_n * 100
        s_dd = (s_hi_n - c) / s_hi_n * 100
        idx_weak = ge(b_dd, p.idx_drop_pct)
        stk_hl = gt(P.lowest(l, 5), shift(P.lowest(l, p.rs_lead_len), 5))
        rs_leader = idx_weak & le(s_dd, 0.5 * b_dd) & gt(c, e50)
        rs_lead_strong = rs_leader & (le(s_dd, 3.0) | (idx_ll & stk_hl))
        rs_laggard = idx_weak & ge(s_dd, 1.5 * b_dd)
        rs_line_hi = ge(rs_line, P.highest(rs_line, 252))
        rs_line_lo = le(rs_line, P.lowest(rs_line, 252))
        first_to_high = ge(h, hi52_h) & lt(bench, 0.95 * b_hi52)
        s_rs_lead = np.where(rs_lead_strong, 1.0, np.where(rs_leader, 0.5, np.where(rs_laggard, -0.5, 0.0)))
        l_rs_lead = np.where(first_to_high, 1.0, np.where(rs_line_hi & lt(c, hi52_h * 0.97), 1.0, np.where(rs_line_hi, 0.75,
                    np.where(rs_leader, 0.5, np.where(rs_line_lo, -1.0, np.where(rs_laggard, -0.5, 0.0))))))

        # pivots
        ph_st, pl_st = P.pivothigh(h, p.st_piv_lr, p.st_piv_lr), P.pivotlow(l, p.st_piv_lr, p.st_piv_lr)
        ph_lt, pl_lt = P.pivothigh(h, p.lt_piv_lr, p.lt_piv_lr), P.pivotlow(l, p.lt_piv_lr, p.lt_piv_lr)

        # swing failure patterns (bar by bar, as the chart runs)
        sfp_vol_ok = np.ones(n, dtype=bool) if p.sfp_vol == "None" else ge(v, p.sfp_vol_mult * avg_vol50)
        lv_sh, lv_sl, lv_lh, lv_ll = [], [], [], []
        bull_s, bear_s, bull_l, bear_l = _SFP(), _SFP(), _SFP(), _SFP()
        s_sfp, l_sfp = np.zeros(n), np.zeros(n)
        act = None
        for i in range(n):
            bear_lv_s, _ = _sfp_scan(lv_sh, True, h[i], l[i], c[i])
            bull_lv_s, _ = _sfp_scan(lv_sl, False, h[i], l[i], c[i])
            bear_lv_l, _ = _sfp_scan(lv_lh, True, h[i], l[i], c[i])
            bull_lv_l, _ = _sfp_scan(lv_ll, False, h[i], l[i], c[i])
            _push(lv_sh, ph_st[i], i - p.st_piv_lr)
            _push(lv_sl, pl_st[i], i - p.st_piv_lr)
            _push(lv_lh, ph_lt[i], i - p.lt_piv_lr)
            _push(lv_ll, pl_lt[i], i - p.lt_piv_lr)
            ok = p.sfp_on and bool(sfp_vol_ok[i])
            bull_s.update(ok and not math.isnan(bull_lv_s), bull_lv_s, True, i, h[i], l[i], c[i])
            bear_s.update(ok and not math.isnan(bear_lv_s), bear_lv_s, False, i, h[i], l[i], c[i])
            bull_l.update(ok and not math.isnan(bull_lv_l), bull_lv_l, True, i, h[i], l[i], c[i])
            bear_l.update(ok and not math.isnan(bear_lv_l), bear_lv_l, False, i, h[i], l[i], c[i])
            b_sa = p.sfp_on and bull_s.age(i) <= p.sfp_max_age and not bull_s.dead
            r_sa = p.sfp_on and bear_s.age(i) <= p.sfp_max_age and not bear_s.dead
            b_la = p.sfp_on and bull_l.age(i) <= p.sfp_max_age * 3 and not bull_l.dead
            r_la = p.sfp_on and bear_l.age(i) <= p.sfp_max_age * 3 and not bear_l.dead
            s_sfp[i] = _sfp_sig(b_sa, bull_s, r_sa, bear_s)
            l_sfp[i] = _sfp_sig(b_la, bull_l, r_la, bear_l)
            act = (b_sa, r_sa, b_la, r_la)
        bull_s_act, bear_s_act, bull_l_act, bear_l_act = act

        # ST volume profile, developing, on the last vpHistBars bars; value-area migration
        bs_piv = P.barssince(~np.isnan(pl_st))
        st_poc, st_vah, st_val = np.full(n, NA), np.full(n, NA), np.full(n, NA)
        for i in range(max(0, n - 1 - p.vp_hist_bars), n):
            anchor = p.vp_bars if np.isnan(bs_piv[i]) else int(max(10, min(p.vp_bars, bs_piv[i] + p.st_piv_lr + 1)))
            st_poc[i], st_vah[i], st_val[i] = volume_profile(h, l, v, i, int(min(anchor, i)), p.vp_bins)
        poc_near = ~np.isnan(st_poc) & (le(np.abs(c - st_poc), p.poc_near_atr * atr14) | (le(l, st_poc) & ge(h, st_poc)))
        doji_poc = doji_at_e9 & poc_near
        va_mig = np.zeros(n)
        pv_poc = pv_vah = pv_val = NA
        for i in range(n):
            if not np.isnan(pl_st[i]) and i > 0 and not np.isnan(st_poc[i - 1]):
                pv_poc, pv_vah, pv_val = st_poc[i - 1], st_vah[i - 1], st_val[i - 1]
            if np.isnan(pv_vah) or np.isnan(st_val[i]):
                va_mig[i] = 0.0
            elif st_val[i] > pv_vah:
                va_mig[i] = 1.0
            elif st_vah[i] < pv_val:
                va_mig[i] = -1.0
            elif st_poc[i] > pv_poc:
                va_mig[i] = 0.5
            elif st_poc[i] < pv_poc:
                va_mig[i] = -0.5
        last_pv_vah = pv_vah
        va_mig_txt = ("No prior swing yet" if np.isnan(last_pv_vah) else
                      {1.0: "Value migrating up (above prior VA)", 0.5: "Overlapping, POC higher",
                       -0.5: "Overlapping, POC lower", -1.0: "Value migrating down"}.get(va_mig[-1], "Balanced"))

        # 9 EMA consolidation
        tol, dist = p.tol_pct / 100, p.max_dist / 100
        trend_up = gt(c, e50) & gt(e9, e20) & gt(e20, e50)
        trend_dn = lt(c, e50) & lt(e9, e20) & lt(e20, e50)
        tight_up = ge(c, e9) & lt((c - e9) / e9, dist)
        tight_dn = le(c, e9) & lt((e9 - c) / e9, dist)
        scan_match = (trend_up & tight_up & le(l, e9) & le(shift(l, 1), shift(e9, 1) * (1 + tol)) &
                      le(shift(l, 2), shift(e9, 2) * (1 + tol)) & le(shift(l, 3), shift(e9, 3)) & (v > p.min_vol))
        touch_up = np.zeros(n, dtype=int)
        touch_dn = np.zeros(n, dtype=int)
        dojis = np.zeros(n, dtype=int)
        for k in range(5):
            lk, hk, ck, ok_, ek = shift(l, k), shift(h, k), shift(c, k), shift(o, k), shift(e9, k)
            touch_up += (le(lk, ek * (1 + tol)) & ge(ck, ek * (1 - tol))).astype(int)
            touch_dn += (ge(hk, ek * (1 - tol)) & le(ck, ek * (1 + tol))).astype(int)
            dojis += (gt(hk, lk) & le(np.abs(ck - ok_), p.doji_body * (hk - lk)) & ge(ck, ek * (1 - tol))).astype(int)
        c_bull0 = np.where(trend_up & tight_up, np.where(scan_match, 1.0, np.where(touch_up >= 4, 0.75, np.where(touch_up >= 3, 0.5, 0.0))), 0.0)
        c_bull = np.where((c_bull0 > 0) & (dojis >= 2), np.minimum(1.0, c_bull0 + 0.25), c_bull0)
        c_bear = np.where(trend_dn & tight_dn, np.where(touch_dn >= 4, -1.0, np.where(touch_dn >= 3, -0.5, 0.0)), 0.0)
        s_cons = c_bull + c_bear

        # squeeze and gap
        basis = P.sma(c, p.bb_len)
        dev = p.bb_mult * P.stdev(c, p.bb_len)
        upper, lower = basis + dev, basis - dev
        bb_width = (upper - lower) / basis
        bb_width_pct = P.percentrank(bb_width, p.bb_pct_len)
        atr20 = P.atr(h, l, c, 20)
        kc_up, kc_lo = basis + 1.5 * atr20, basis - 1.5 * atr20
        sqz_on = lt(upper, kc_up) & gt(lower, kc_lo)
        hh20b, ll20b = P.highest(h, 20), P.lowest(l, 20)
        sqz_mom = P.linreg(c - ((hh20b + ll20b) / 2 + basis) / 2, 20, 0)
        sqz_prev = np.concatenate([[False], sqz_on[:-1]])
        bs_fire = P.barssince(sqz_prev & ~sqz_on)
        sqz_fired = le(bs_fire, 3) & ~sqz_on & gt(sqz_mom, 0) & gt(sqz_mom, shift(sqz_mom, 1))
        is_ttm = p.sqz_method.startswith("TTM")
        squeeze_now = sqz_on if is_ttm else lt(bb_width_pct, p.squeeze_thresh)
        expanded_now = gt(bb_width_pct, p.expand_thresh)
        squeeze_breakout = sqz_fired if is_ttm else (lt(shift(bb_width_pct, 3), p.squeeze_thresh) & gt(bb_width, shift(bb_width, 3) * 1.3) & gt(c, upper))
        mom_ok = gt(sqz_mom, 0) if is_ttm else ge(c, e20)
        s_squeeze = np.where(squeeze_breakout, 1.0, np.where(squeeze_now & mom_ok, 0.5, np.where(squeeze_now, -0.25, np.where(expanded_now, -0.5, 0.0))))

        gap_pct = (o - shift(c)) / shift(c) * 100
        is_gap_up = gt(gap_pct, p.gap_thresh)
        is_gap_dn = lt(gap_pct, -p.gap_thresh)
        breakaway = is_gap_up & lt(shift(ext, 1), p.ext_breakaway) & (c > o)
        exhaustion = is_gap_up & gt(shift(ext, 1), p.ext_exhaustion) & (c < o)
        s_gap = np.where(breakaway, 1.0, np.where(exhaustion, -1.0, np.where(is_gap_dn & lt(c, shift(c)), -0.5, 0.0)))

        # stage analysis
        sma150 = P.sma(c, 150)
        slope150 = sma150 / shift(sma150, 50) - 1
        prior_slope = shift(slope150, 50)
        flat_b = p.flat_band / 100
        base_res = shift(P.highest(h, 60), 1)
        hi_vol3 = P.highest(v, 3)
        brk = gt(c, base_res) & gt(hi_vol3, p.vol_mult * avg_vol50)
        bars_brk = P.barssince(brk)
        stage = np.where(gt(slope150, flat_b), np.where(gt(c, sma150), 2, 3),
                 np.where(lt(slope150, -flat_b), 4, np.where(gt(prior_slope, flat_b), 3,
                 np.where(gt(c, sma150) & le(bars_brk, 20), 2, 1)))).astype(int)
        last_non2 = np.ones(n, dtype=int)
        cur = 1
        for i in range(n):
            if stage[i] != 2:
                cur = stage[i]
            last_non2[i] = cur
        bars_in2 = P.barssince(stage != 2)
        fresh_s2 = (stage == 2) & (last_non2 == 1) & le(bars_in2, p.fresh_bars)
        l_stage_sig = np.where(stage == 2, np.where(fresh_s2, 1.0, 0.5), np.where(stage == 1, 0.0, np.where(stage == 3, -0.75, -1.0)))
        persist = (gt(v, avg_vol50 * p.persist_mult).astype(int) + gt(shift(v, 1), shift(avg_vol50, 1) * p.persist_mult).astype(int)
                   + gt(shift(v, 2), shift(avg_vol50, 2) * p.persist_mult).astype(int))
        near_brk = le(bars_brk, 10)
        vol_persist = np.where(near_brk & (persist >= 2), 1.0, np.where(near_brk & (persist == 1), 0.0,
                      np.where(near_brk & (persist == 0), -0.5, np.where((stage == 2) & (persist >= 2), 0.5, 0.0))))

        # climax run
        up_chg = c - shift(c)
        max_up60 = shift(P.highest(up_chg, 60), 1)
        max_rng60 = shift(P.highest(rng_t, 60), 1)
        gain15 = c / P.lowest(l, 15) - 1
        ext50 = (c - e50) / atr14
        big_up = gt(up_chg, 0) & ge(up_chg, max_up60) & ge(rng_t, max_rng60)
        climax_now = p.use_climax & (stage == 2) & ge(gain15, p.climax_gain / 100) & (big_up | exhaustion | ge(ext50, p.climax_ext))

        # short-term score
        mult = np.where(gt(adx14, 25), 1.0, np.where(lt(adx14, 20), 0.5, 0.75))
        e20_up = gt(P.change(e20, 3), 0)
        s_stack = (sg(gt(e9, e20)) + sg(gt(e20, e50))) / 2 * mult
        s_px20 = (sg(gt(c, e20)) + sg(e20_up)) / 2 * mult
        hist_up = gt(m_hist, shift(m_hist, 1))
        s_macd = (sg(gt(m_line, m_sig)) + sg(hist_up)) / 2 * mult
        bull_reg = gt(c, e200) & gt(e50, e200)
        bear_reg = lt(c, e200) & lt(e50, e200)
        r = rsi14
        s_rsi_bull = np.where(gt(r, 80), -0.5, np.where(gt(r, 75), 0.5, np.where(ge(r, 55), 1.0, np.where(ge(r, 45), 0.5, np.where(ge(r, 40), 0.0, -1.0)))))
        s_rsi_bear = np.where(ge(r, 60), 0.0, np.where(ge(r, 40), -0.5, -1.0))
        s_rsi_neu = np.where(ge(r, 55) & le(r, 70), 1.0, np.where(gt(r, 70) & le(r, 80), 0.5, np.where(ge(r, 45) & lt(r, 55), 0.0,
                    np.where(ge(r, 30) & lt(r, 45), -0.5, np.where(gt(r, 80), -0.5, -1.0)))))
        s_rsi = np.where(bull_reg, s_rsi_bull, np.where(bear_reg, s_rsi_bear, s_rsi_neu))
        obv_up = gt(obv_s, P.ema(obv_s, 20))
        s_obv = sg(obv_up)
        s_rs = rs_sig(rs_rating_st)
        s_ext = np.where(lt(ext, 2), 1.0, np.where(lt(ext, 3), -0.5, -1.0))
        at_e9 = le(l, e9 + 0.25 * atr14) & gt(c, e20)
        pa_raw = np.where(climax_now, -1.0, np.where((is_hammer | is_engulf) & at_e9, 1.0, np.where(doji_poc, 1.0,
                 np.where(strong_bull, 0.75, np.where(up_reject, -1.0, np.where(bear_wide, -1.0, np.where(doji_at_e9, 0.5, 0.0)))))))
        s_pa = np.clip(pa_raw + np.where(dry_up & gt(c, e20) & lt(c, shift(c, 3)), 0.25, 0.0), -1.0, 1.0)
        s_va = va_mig if p.use_va_mig else np.zeros(n)
        st_raw = (10 * s_stack + 8 * s_px20 + 6 * s_macd + 8 * s_rsi + 4 * s_obv + 8 * s_rs + 4 * s_ext + 10 * s_cons
                  + 5 * s_squeeze + 3 * s_gap + 4 * sector_sig + 10 * s_pa + 8 * s_sfp + 6 * s_rs_lead + 6 * s_va)
        st_div = 100 - (0 if p.use_sector else 4) - (0 if p.use_va_mig else 6)
        st_score = st_raw * 100 / st_div

        # long-term score
        d200 = c / e200 - 1
        l_px200 = np.where(gt(np.abs(d200), 0.02), np.sign(d200), 0.0)
        e200_up = gt(e200 - shift(e200, 20), 0)
        l_slope = sg(e200_up)
        l50 = sg(gt(e50, e200))
        l100 = sg(gt(e100, e200))
        l_wrsi = np.where(ge(w_rsi, 55) & le(w_rsi, 75), 1.0, np.where(ge(w_rsi, 45) & lt(w_rsi, 55), 0.0, np.where(lt(w_rsi, 40), -1.0, -0.5)))
        l_wmacd = (sg(gt(w_macd, w_sig)) + sg(gt(w_macd, 0))) / 2
        l_rs = rs_sig(rs_rating_lt)
        hi52, lo52 = P.highest(c, 252), P.lowest(c, 252)
        l_struct = np.where(ge(c, 0.85 * hi52) & ge(c, 1.3 * lo52), 1.0, np.where(lt(c, 0.6 * hi52), -1.0, 0.0))
        obv_lt = gt(P.ema(obv_s, 50), P.ema(obv_s, 150))
        l_obv = sg(obv_lt)
        lt_raw = (7 * l_px200 + 5 * l_slope + 5 * l50 + 2 * l100 + 5 * l_wrsi + 5 * l_wmacd + 12 * l_rs + 5 * l_struct + 5 * l_obv
                  + 18 * l_stage_sig + 8 * sector_sig + 7 * vol_persist + 6 * l_sfp + 10 * l_rs_lead)
        lt_div = 100 if p.use_sector else 92
        lt_norm = lt_raw * 100 / lt_div
        gated_s = (p.hard_block & ((stage == 3) | (stage == 4))) | (p.fresh_only & ~fresh_s2)
        lt_score = np.where(gated_s, np.minimum(lt_norm, 19.0), lt_norm)
    finally:
        np.seterr(**np_err)

    # ─── readings for the last bar (the calculation table's text) ───────────────────────────────────────
    i = n - 1
    yn = lambda b, y, no: y if bool(b) else no  # noqa: E731
    m_txt = f" · ADX {_num(adx14[i], 0)} → ×{mult[i]:.2f}"
    k_s, k_l = 100.0 / st_div, 100.0 / lt_div
    fmt = lambda x: _num(x, 2)  # noqa: E731

    def sfp_txt():
        if bull_s_act and (not bear_s_act or bull_s.bar > bear_s.bar):
            t = f"Bull SFP {fmt(bull_s.lvl)}" + (" (confirmed)" if bull_s.conf else f" (needs close > {fmt(bull_s.hi)})")
        elif bear_s_act:
            t = f"Bear SFP {fmt(bear_s.lvl)}" + (" (confirmed)" if bear_s.conf else f" (void on close > {fmt(bear_s.hi)})")
        else:
            t = "No active ST SFP"
        if bull_l_act and (not bear_l_act or bull_l.bar > bear_l.bar):
            t += f" · major bull SFP {fmt(bull_l.lvl)}"
        elif bear_l_act:
            t += f" · major bear SFP {fmt(bear_l.lvl)}"
        return t

    setup_txt = ("9 EMA pullback: scan match" if scan_match[i] else
                 f"Building: {touch_up[i]}/5 touches, {dojis[i]} dojis above 9 EMA" if c_bull[i] > 0 else
                 "Rejected below 9 EMA" if c_bear[i] < 0 else "No 9 EMA setup")
    blk = " (blocked)" if p.hard_block else ""
    stg = int(stage[i])
    stage_txt = ((("Stage 2: fresh breakout" if fresh_s2[i] else "Stage 2: established") if stg == 2 else
                  "Stage 1: basing" if stg == 1 else ("Stage 3: topping" + blk) if stg == 3 else ("Stage 4: declining" + blk)))
    candle_txt = ("Doji at 9 EMA + POC" if doji_poc[i] else "Hammer" if is_hammer[i] else "Bullish engulfing" if is_engulf[i] else
                  "Strong bull bar" if strong_bull[i] else "Bearish wide bar" if bear_wide[i] else "Upper-wick rejection" if up_reject[i] else
                  "Doji at 9 EMA" if doji_at_e9[i] else "Inside bar" if is_inside[i] else "NR7" if is_nr7[i] else "Doji" if is_doji[i] else "Plain bar")
    squeeze_txt = ("Squeeze breakout" if squeeze_breakout[i] else "Squeeze forming" if squeeze_now[i] else
                   "Extended vol" if expanded_now[i] else "Normal vol")
    gap_txt = "Breakaway gap" if breakaway[i] else "Exhaustion gap" if exhaustion[i] else "Gap down" if is_gap_dn[i] else "No gap"
    rs_lead_txt = ("New 52W high while index is down" if first_to_high[i] else
                   f"Leader: holding while index fell {_num(b_dd[i], 1)}%" if rs_lead_strong[i] else
                   "Holding up vs index" if rs_leader[i] else "Lagging a weak index" if rs_laggard[i] else
                   "RS line at 52W high" if rs_line_hi[i] else "Neutral")
    sec_txt = ("no sector data" if np.isnan(sector_roc[i]) else
               f"{_num(sector_roc[i] * 100, 1)}% vs {p.sector_sym if p.use_sector else bench_sym} over {p.sector_len} bars")
    regime = "bull regime" if bull_reg[i] else "bear regime" if bear_reg[i] else "neutral regime"

    def row(name, reading, sig, w_, scale, on=True, tip=""):
        s = float(sig)
        return Row(name, reading if on else "switched off", s, w_ if on else 0, (w_ * s * scale) if on else 0.0, on, tip)

    st_rows = [
        row("EMA stack", f"EMA 9 {yn(e9[i] > e20[i], '>', '<')} EMA 20 {yn(e20[i] > e50[i], '>', '<')} EMA 50" + m_txt, s_stack[i], 10, k_s),
        row("Price vs EMA 20", f"close {yn(c[i] > e20[i], 'above', 'below')} EMA 20, EMA 20 {yn(e20_up[i], 'rising', 'falling')}" + m_txt, s_px20[i], 8, k_s),
        row("MACD (12, 26, 9)", f"MACD {yn(m_line[i] > m_sig[i], 'above', 'below')} signal, histogram {yn(hist_up[i], 'rising', 'falling')}" + m_txt, s_macd[i], 6, k_s),
        row("RSI 14", f"RSI {_num(rsi14[i], 1)} · {regime}", s_rsi[i], 8, k_s),
        row("On-balance volume", f"OBV {yn(obv_up[i], 'above', 'below')} its 20 EMA", s_obv[i], 4, k_s),
        row("RS rating (short)", f"{_num(rs_rating_st[i], 0)} percentile · 21/63-day excess return vs {bench_name}, beta {beta[i]:.2f}", s_rs[i], 8, k_s),
        row("Extension above EMA 20", f"{_num(ext[i], 1)} ATR above EMA 20", s_ext[i], 4, k_s),
        row("9 EMA consolidation", setup_txt, s_cons[i], 10, k_s),
        row("Squeeze", squeeze_txt, s_squeeze[i], 5, k_s),
        row("Gap", gap_txt, s_gap[i], 3, k_s),
        row("Sector RS", sec_txt, sector_sig[i], 4, k_s, p.use_sector),
        row("Price action (candle)", candle_txt + (" · volume drying up" if dry_up[i] else ""), s_pa[i], 10, k_s),
        row("Swing failure (SFP)", sfp_txt() if (bull_s_act or bear_s_act) else "No active ST SFP", s_sfp[i], 8, k_s),
        row("RS leadership", rs_lead_txt, s_rs_lead[i], 6, k_s),
        row("Value-area migration", va_mig_txt, s_va[i], 6, k_s, p.use_va_mig),
    ]
    e200_chg = (e200[i] / e200[i - 20] - 1) * 100 if i >= 20 else NA
    if bull_l_act or bear_l_act:
        major = (f"Major bull SFP {fmt(bull_l.lvl)}" if bull_l_act and (not bear_l_act or bull_l.bar > bear_l.bar)
                 else f"Major bear SFP {fmt(bear_l.lvl)}")
    else:
        major = "No active major SFP"
    lt_rows = [
        row("Price vs EMA 200", f"close {f_p(d200[i] * 100)}% from EMA 200", l_px200[i], 7, k_l),
        row("EMA 200 slope", f"EMA 200 {yn(e200_up[i], 'rising', 'falling')} over 20 bars ({f_p(e200_chg)}%)", l_slope[i], 5, k_l),
        row("EMA 50 vs 200", f"EMA 50 {yn(e50[i] > e200[i], 'above', 'below')} EMA 200", l50[i], 5, k_l),
        row("EMA 100 vs 200", f"EMA 100 {yn(e100[i] > e200[i], 'above', 'below')} EMA 200", l100[i], 2, k_l),
        row("Weekly RSI 14", f"RSI {_num(w_rsi[i], 1)} (last completed week)", l_wrsi[i], 5, k_l),
        row("Weekly MACD", f"MACD {yn(w_macd[i] > w_sig[i], 'above', 'below')} signal, {yn(w_macd[i] > 0, 'above', 'below')} zero", l_wmacd[i], 5, k_l),
        row("RS rating (long)", f"{_num(rs_rating_lt[i], 0)} percentile · 3/6/9/12-month excess return vs {bench_name}", l_rs[i], 12, k_l),
        row("52-week structure", f"{_num(c[i] / hi52[i] * 100, 0)}% of the 52W high · {_num((c[i] / lo52[i] - 1) * 100, 0)}% above the 52W low", l_struct[i], 5, k_l),
        row("OBV trend", f"OBV EMA 50 {yn(obv_lt[i], 'above', 'below')} OBV EMA 150", l_obv[i], 5, k_l),
        row("Weinstein stage", f"{stage_txt} · 30W MA {f_p(slope150[i] * 100)}% over 50 bars", l_stage_sig[i], 18, k_l),
        row("Sector RS", sec_txt.replace(f" over {p.sector_len} bars", ""), sector_sig[i], 8, k_l, p.use_sector),
        row("Volume persistence", f"{persist[i]} of the last 3 bars above {p.persist_mult:g}× avg volume"
            + ("" if np.isnan(bars_brk[i]) else f" · breakout {int(bars_brk[i])} bars ago"), vol_persist[i], 7, k_l),
        row("Major swing failure", major, l_sfp[i], 6, k_l),
        row("RS leadership", rs_lead_txt + (" · RS line at 52W high" if rs_line_hi[i] else ""), l_rs_lead[i], 10, k_l),
    ]
    tp = tips(p)
    for r_, k_ in zip(st_rows, ST_KEYS):
        r_.key, r_.tip = k_, tp["st"][k_]
    for r_, k_ in zip(lt_rows, LT_KEYS):
        r_.key, r_.tip = k_, tp["lt"][k_]
    sb, lb = band(st_score[i]), band(lt_score[i])
    if n < 200:
        notes.append(f"only {n} daily bars: EMA 200 and the 52-week figures need more history")
    series = pd.DataFrame({"st": st_score, "lt": lt_score, "stage": stage}, index=idx)
    return StltResult(symbol=symbol, date=idx[-1], close=float(c[i]), bars=n, st_score=float(st_score[i]),
                      lt_score=float(lt_score[i]), st_raw=float(st_raw[i]), lt_raw=float(lt_raw[i]), lt_norm=float(lt_norm[i]),
                      st_div=float(st_div), lt_div=float(lt_div), gated=bool(gated_s[i]), stage=stg, s_band=sb, l_band=lb,
                      alignment=alignment(sb, lb), bench_name=bench_name, adx=float(adx14[i]), trend_mult=float(mult[i]),
                      st_rows=st_rows, lt_rows=lt_rows, notes=notes, series=series)


# ─── text output ────────────────────────────────────────────────────────────────────────────────────────
def _table(rows: List[Row], width: int = 46) -> List[str]:
    out = [f"  {'Component':<24} {'Signal':>6} {'Wt':>3} {'Points':>6}  Reading now"]
    for r in rows:
        sig = f_s(r.signal) if r.on else "-"
        pts = f_p(r.points) if r.on else "-"
        out.append(f"  {r.name:<24} {sig:>6} {int(r.weight):>3} {pts:>6}  {r.reading}")
    return out


def breakdown_text(res: StltResult) -> str:
    """The calculation table and the trend alignment as plain text (monospace)."""
    L = [f"{res.symbol} · {res.date:%d %b %Y} · close {res.close:,.2f} · {res.bars} daily bars · RS benchmark {res.bench_name}", ""]
    L.append(f"SHORT-TERM SCORE = Σ weight × signal × 100 / {res.st_div:.0f}")
    L += _table(res.st_rows)
    L.append(f"  Raw sum {f_p(res.st_raw)} (of ±{res.st_div:.0f})  × 100 / {res.st_div:.0f}  =  {f_p(res.st_score)}")
    L.append(f"  SHORT-TERM {'+' if res.st_score > 0 else ''}{pround(res.st_score)}  {rate(res.st_score)}")
    L.append("")
    L.append(f"LONG-TERM SCORE = Σ weight × signal × 100 / {res.lt_div:.0f}" + (", capped at +19 in Stage 3 / 4" if res.gated else ""))
    L += _table(res.lt_rows)
    L.append(f"  Raw sum {f_p(res.lt_raw)}  × 100 / {res.lt_div:.0f}  =  {f_p(res.lt_norm)}")
    if res.gated:
        L.append(f"  Stage cap: Stage {res.stage}: capped at +19 → {f_p(res.lt_score)}")
    L.append(f"  LONG-TERM {'+' if res.lt_score > 0 else ''}{pround(res.lt_score)}  {rate(res.lt_score)}")
    L.append("")
    L.append(f"TREND ALIGNMENT  {res.alignment}")
    L.append(f"  How: short-term {f_p(res.st_score)} → {band_text(res.st_score)}   ×   long-term {f_p(res.lt_score)} → {band_text(res.lt_score)}")
    for sbv in (1, 0, -1):
        mark = "▶" if res.s_band == sbv else " "
        L.append(f"  {mark} Short-term {BAND_NAMES[sbv]:<8}: " + "   ·   ".join(
            f"long-term {BAND_NAMES[lbv]} → {alignment(sbv, lbv)}" for lbv in (1, 0, -1)))
    for nt in res.notes:
        L.append(f"  note: {nt}")
    return "\n".join(L)
