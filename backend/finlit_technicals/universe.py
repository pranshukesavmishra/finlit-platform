"""Which stocks count in an industry's breadth: rules set from NSE data (the Nov 2026 noise test), applied month by
month with only the information available at the time.

A stock counts when, at the monthly review (first trading day of the month, using data to the session before):
    series        trades in NSE's normal EQ series (not trade-for-trade BE/BZ, not SME)
    liquidity     median daily traded value over the last 65 sessions of Rs 2 crore or more to join; a member stays
                  until it falls below Rs 1 crore
    regular       traded on 62 or more of the last 65 sessions
    not locked    at most 1 of the last 65 sessions with high = low (stuck at a price band)
    price         Rs 20 or more
    size          AMFI 6-month average market cap of Rs 1,000 crore or more to join; stays until under Rs 800 crore
    seasoned      126 or more sessions traded since listing
Rupee floors are in today's money: earlier years use them scaled by NSE's turnover (liquidity) and AMFI's total
market cap (size) at the time. Between reviews a stock leaves at once if it moves off the EQ series or goes 5
sessions without a trade.

Why these numbers: in 175,000 stock-months (2017-2026) noise fell steadily as traded value rose and levelled off
around Rs 2-5 crore a day; a single locked session already doubled the stocks' return autocorrelation; prices under
Rs 20 had stale closes 3-10x as often; and correlation with the industry flattened above Rs 1,000 crore of market
cap. The thresholds were set on these noise measures before any return was looked at.
"""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np
import pandas as pd


@dataclass
class UniverseRules:
    join_value_cr: float = 2.0
    leave_value_cr: float = 1.0
    window: int = 65
    min_trade_days: int = 62
    max_locked_days: int = 1
    min_price: float = 20.0
    join_mcap_cr: float = 1000.0
    leave_mcap_cr: float = 800.0
    seasoning: int = 126
    stale_exit: int = 5
    scale_value: bool = True
    scale_mcap: bool = True
    use_mcap: bool = True


def load_amfi(folder: str) -> pd.DataFrame:
    """AMFI's half-yearly lists (amfi/<yyyy>H<n>.xlsx) -> period_end, isin, nse_symbol, mcap_cr, category."""
    try:
        import openpyxl
    except ImportError as e:                                        # pragma: no cover
        raise ImportError("Reading AMFI's market-cap lists needs openpyxl: pip install openpyxl") from e
    rows = []
    for f in sorted(glob.glob(os.path.join(folder, "[0-9][0-9][0-9][0-9]H[12].xlsx"))):
        per = os.path.basename(f)[:6]
        end = pd.Timestamp(int(per[:4]), 6, 30) if per[4:] == "H1" else pd.Timestamp(int(per[:4]), 12, 31)
        ws = openpyxl.load_workbook(f, read_only=True, data_only=True).worksheets[0]
        started = False
        for r in ws.iter_rows(values_only=True):
            if not started:
                started = bool(r and r[0] is not None and str(r[0]).strip().lower().startswith("sr"))
                continue
            if not r or len(r) < 11 or r[2] is None:
                continue
            try:
                cap = float(r[9])
            except (TypeError, ValueError):
                continue
            rows.append((end, str(r[2]).strip(), str(r[5] or "").strip().rstrip("*"), cap, str(r[10] or "").strip()))
    return pd.DataFrame(rows, columns=["period_end", "isin", "nse_symbol", "mcap_cr", "category"])


def amfi_matrix(p, amfi: pd.DataFrame, lag_days: int = 15):
    """Per day and stock: the AMFI average market cap of the latest list published before that day (Rs crore), and
    the lists' total relative to the latest (for scaling). A list counts as published `lag_days` after its period
    ends; days before the first list use the first list. Also returns the AMFI category (Large/Mid/Small Cap) today."""
    T, N = len(p.dates), len(p.keys)
    caps = np.full((T, N), np.nan)
    totals = np.full(T, np.nan)
    category: Dict[str, str] = {}
    if amfi is None or amfi.empty:
        return caps, np.ones(T), category
    periods = sorted(amfi["period_end"].unique())
    avail = [pd.Timestamp(x) + pd.Timedelta(days=lag_days) for x in periods]
    issuer = {k: v[3:9] for k, v in p.isin.items() if isinstance(v, str) and len(v) >= 9}
    for j_, per in enumerate(periods):
        lst = amfi[amfi["period_end"] == per]
        start = 0 if j_ == 0 else int(np.searchsorted(p.dates.values, np.datetime64(avail[j_])))
        end = T if j_ == len(periods) - 1 else int(np.searchsorted(p.dates.values, np.datetime64(avail[j_ + 1])))
        by_isin = dict(zip(lst["isin"], lst["mcap_cr"]))
        by_sym = dict(zip(lst["nse_symbol"], lst["mcap_cr"]))
        iss = lst.assign(code=lst["isin"].str[3:9]).drop_duplicates("code", keep=False)
        by_code = dict(zip(iss["code"], iss["mcap_cr"]))
        col = np.full(N, np.nan)
        for i, k in enumerate(p.keys):
            v = by_isin.get(p.isin.get(k))
            if v is None:
                v = by_sym.get(k)
            if v is None and k in issuer:
                v = by_code.get(issuer[k])          # ISINs change on a split; the issuer part does not
            if v is not None:
                col[i] = v
        if start < end:
            caps[start:end] = col
            totals[start:end] = float(np.nansum(lst["mcap_cr"].to_numpy()))
        if j_ == len(periods) - 1:
            cat_isin = dict(zip(lst["isin"], lst["category"]))
            cat_sym = dict(zip(lst["nse_symbol"], lst["category"]))
            for k in p.keys:
                c = cat_isin.get(p.isin.get(k)) or cat_sym.get(k)
                if c:
                    category[k] = c
    return caps, totals / totals[-1], category


def _rolling_sum(x: np.ndarray, w: int) -> np.ndarray:
    c = np.cumsum(np.vstack([np.zeros((1, x.shape[1])), x]), axis=0)
    return np.vstack([np.full((w - 1, x.shape[1]), np.nan), c[w:] - c[:-w]])


def market_scale(p, span: int = 250) -> np.ndarray:
    """NSE turnover (EQ series, 250-session average) relative to its latest value."""
    tv = np.empty(p.close.shape[0])
    step = 256                                            # rows at a time; each day's sum is taken over that day's own row, so the numbers are the same as for the whole matrix
    for a in range(0, len(tv), step):
        tv[a:a + step] = np.where(np.asarray(p.series[a:a + step]) == 0, np.nan_to_num(np.asarray(p.value[a:a + step]).astype(float)), 0.0).sum(1)
    s = pd.Series(tv).rolling(span, min_periods=20).mean().to_numpy()
    return s / s[-1]


@dataclass
class Universe:
    member: np.ndarray                 # T x N: counts in breadth that day
    inputs: Dict[str, np.ndarray]      # the rule inputs, for explanations
    rules: UniverseRules


class LastDay:
    """The last row of a T x N rule input, answering [t, j] for the last day only (a universe built with lean=True keeps no history of the rule inputs)."""

    def __init__(self, row: np.ndarray, T: int):
        self.row, self.T = np.asarray(row), T

    def __getitem__(self, key):
        t, j = key
        if t not in (-1, self.T - 1):
            raise IndexError("this universe keeps the rule inputs of the last day only (built with lean=True)")
        return self.row[j]


def build_universe(p, rules: UniverseRules = UniverseRules(), caps: Optional[np.ndarray] = None,
                   cap_scale: Optional[np.ndarray] = None, block: Optional[int] = None, lean: bool = False) -> Universe:
    """Who counts, day by day. Every stock is judged on its own numbers (plus two market-wide series, `vscale` and `mscale`), so the work can be done for
    blocks of `block` stocks at a time: the answer is the same for any block size.

    FinLit patch: `block` bounds the working memory (a block of stocks instead of ten T x N float64 matrices), and `lean=True` keeps the rule inputs of the
    last day only (the only day the explanations read) instead of the whole history; `inputs[name][-1, j]` and `why_not(u, j)` work as before."""
    T, N = p.close.shape
    step = N if not block or block >= N else int(block)
    vscale = market_scale(p) if rules.scale_value else np.ones(T)
    mscale = cap_scale if (rules.scale_mcap and cap_scale is not None) else np.ones(T)
    use_caps = rules.use_mcap and caps is not None
    months = pd.Series(p.dates.to_period("M"))
    review = set(int(x) for x in np.where(months.ne(months.shift()).to_numpy())[0])
    member = np.zeros((T, N), bool)
    names = ("median_value_cr", "trade_days", "locked_days", "price", "sessions", "seasoned", "eq", "since_trade")
    kept: Dict[str, np.ndarray] = {}
    for j0 in range(0, max(N, 1), max(step, 1)):
        j1 = min(N, j0 + step)
        cl = np.asarray(p.close[:, j0:j1])
        traded = ~np.isnan(cl)
        eq = np.asarray(p.series[:, j0:j1]) == 0
        val = np.where(traded, np.nan_to_num(np.asarray(p.value[:, j0:j1]).astype(float)), 0.0) / 1e7
        med_val = pd.DataFrame(val).rolling(rules.window, min_periods=rules.window).median().to_numpy()
        tdays = _rolling_sum(traded.astype(float), rules.window)
        ldays = _rolling_sum((traded & (np.asarray(p.high[:, j0:j1]) == np.asarray(p.low[:, j0:j1]))).astype(float), rules.window)
        sessions = np.cumsum(traded, axis=0)
        at_start = traded[:5].any(0)                     # trading when the files begin: listed long enough
        seasoned = (sessions >= rules.seasoning) | at_start[None, :]
        last_px = pd.DataFrame(cl.astype(float)).ffill().to_numpy()
        since = np.zeros((T, j1 - j0))
        run = np.zeros(j1 - j0)
        for t in range(T):
            run = np.where(traded[t], 0, run + 1)
            since[t] = run
        cur = np.zeros(j1 - j0, bool)
        for t in range(T):
            if t in review and t > 0:
                s = t - 1
                base = (eq[s] & seasoned[s] & (np.nan_to_num(tdays[s]) >= rules.min_trade_days)
                        & (np.nan_to_num(ldays[s], nan=99) <= rules.max_locked_days)
                        & (np.nan_to_num(last_px[s]) >= rules.min_price))
                mv = np.nan_to_num(med_val[s])
                liq_join, liq_stay = mv >= rules.join_value_cr * vscale[s], mv >= rules.leave_value_cr * vscale[s]
                if use_caps:
                    cap = np.nan_to_num(np.asarray(caps[s, j0:j1]))
                    size_join, size_stay = cap >= rules.join_mcap_cr * mscale[s], cap >= rules.leave_mcap_cr * mscale[s]
                else:
                    size_join = size_stay = np.ones(j1 - j0, bool)
                cur = base & np.where(cur, liq_stay & size_stay, liq_join & size_join)
            cur = cur & (eq[t] | ~traded[t]) & (since[t] < rules.stale_exit)
            member[t, j0:j1] = cur
        release = getattr(p, "release_pages", None)          # a memory-mapped panel gives the block's pages back
        if release is not None:
            release()
        part = dict(zip(names, (med_val, tdays, ldays, last_px, sessions, seasoned, eq, since)))
        part["caps"] = np.asarray(caps[:, j0:j1]) if caps is not None else np.full((T, j1 - j0), np.nan)
        for name, arr in part.items():
            if lean:
                kept.setdefault(name, np.empty(N, arr.dtype))[j0:j1] = arr[-1]
            else:
                kept.setdefault(name, np.empty((T, N), arr.dtype))[:, j0:j1] = arr
    if lean:
        inputs: Dict[str, object] = {k: LastDay(v, T) for k, v in kept.items()}
    else:
        inputs = dict(kept)
    inputs.update({"vscale": vscale, "mscale": mscale})
    order = ["median_value_cr", "trade_days", "locked_days", "price", "sessions", "seasoned", "eq", "vscale", "mscale", "caps", "since_trade"]
    return Universe(member=member, rules=rules, inputs={k: inputs[k] for k in order})


def why_not(u: Universe, j: int, t: int = -1) -> list:
    """Plain-English reasons a stock does not count today (empty when it counts). Uses today's readings, so a stock
    can pass them all and still wait for the next monthly review."""
    r, x = u.rules, u.inputs
    T = len(u.member)
    t = t % T
    out = []
    if not x["eq"][t, j]:
        out.append("not trading in NSE's normal EQ series (trade-for-trade or suspended)")
    if not x["seasoned"][t, j]:
        out.append(f"listed for fewer than {r.seasoning} sessions")
    mv, vs = x["median_value_cr"][t, j], x["vscale"][t]
    if np.isnan(mv) or mv < r.leave_value_cr * vs:
        out.append(f"median traded value under Rs {r.leave_value_cr:g} crore a day")
    elif mv < r.join_value_cr * vs and not u.member[t, j]:
        out.append(f"median traded value under Rs {r.join_value_cr:g} crore a day")
    if np.nan_to_num(x["trade_days"][t, j]) < r.min_trade_days:
        out.append(f"traded on fewer than {r.min_trade_days} of the last {r.window} sessions")
    if np.nan_to_num(x["locked_days"][t, j], nan=99) > r.max_locked_days:
        out.append("stuck at a price band (high = low) on more than one recent session")
    if np.nan_to_num(x["price"][t, j]) < r.min_price:
        out.append(f"price under Rs {r.min_price:g}")
    if r.use_mcap:
        cap, ms = x["caps"][t, j], x["mscale"][t]
        if np.isnan(cap):
            out.append("not in AMFI's market-cap list")
        elif cap < r.leave_mcap_cr * ms or (cap < r.join_mcap_cr * ms and not u.member[t, j]):
            out.append(f"AMFI average market cap under Rs {(r.leave_mcap_cr if u.member[t, j] else r.join_mcap_cr):,.0f} crore")
    if not out and not u.member[t, j]:
        out.append("meets the rules now; joins at the next monthly review")
    return out
