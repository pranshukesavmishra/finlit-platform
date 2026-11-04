"""NSE's own daily files as the price source: every main-board stock (including ones later delisted), adjusted for
splits, bonuses, rights and demergers, plus the closes of every NSE index.

The folder is the one `python -m finlit_technicals fetch-nse --dir FOLDER` keeps up to date:
    bhav_<year>.csv.gz        one row per security and trading day (NSE's bhavcopy): date,symbol,series,isin,open,
                              high,low,close,last,prev_close,volume,value,trades
    idx_<year>.csv.gz         closes of every NSE index: date,index,open,high,low,close,...
    ref/symbolchange.csv      NSE's old -> new symbol changes
    ref/EQUITY_L.csv          stocks listed today (names, listing dates)
    ref/corporate_actions.txt corporate actions fetched after the bundled list (optional)
    amfi/<yyyy>H<n>.xlsx      AMFI half-yearly average market caps (used by the universe rules)

    nse = NseHistory("~/dhan_alerts/nse_history")
    nse.daily("SAMBHV")            # adjusted open/high/low/close/volume, like any other source in sources.py
    nse.index("NSE:NIFTY")         # Nifty 50 closes
    nse.panel                      # every stock at once (used by the universe and the sector engine)

How a stock is followed: by its current symbol, through NSE's symbol changes; a rename missing from that file is
linked by ISIN (same issuer and security type, trading resumes within 20 days). Adjustments come from NSE's
corporate actions (bundled for 2016 - Oct 2026 in data/nse_corporate_actions.txt; newer ones fetched daily):
the stated ratio for splits, bonuses and consolidations, the theoretical ex-rights price for rights issues, the
opening gap for demergers, and any move no price band allows (below 35% or above 2.8x of the last close) is treated
as an unrecorded action.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import hashlib
import mmap
import os
import pickle
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .peers import norm_symbol
from .sources import COLUMNS, INDICES

MAIN = ("EQ", "BE", "BZ")
SERIES_RANK = {"EQ": 0, "BE": 1, "BZ": 2}
DATA_DIR = Path(__file__).resolve().parent / "data"
BUNDLED_ACTIONS = DATA_DIR / "nse_corporate_actions.txt"
INDEX_ALIASES = {"NIFTY MIDCAP 100": ["NIFTY FREE MIDCAP 100"], "NIFTY SMALLCAP 100": ["NIFTY FREE SMALL 100"]}
CACHE_VERSION = "3"          # 3: the panel is kept as plain .npy files in .finlit_cache/panel/ (opened with mmap), no longer one pickle


# ─── reading the files ────────────────────────────────────────────────────────────────────────────────────────────
def _shared(s: pd.Series, strip: bool = False) -> pd.Series:
    """The same strings with one object per distinct value (missing stays NaN)."""
    codes, uniq = pd.factorize(s.str.strip() if strip else s)
    values = np.append(np.array([sys.intern(x) if isinstance(x, str) else x for x in uniq], dtype=object), np.nan)    # code -1 (missing) picks the last element
    return pd.Series(values[codes], index=s.index, dtype=object)


def _bhav_files(folder: str | Path) -> list:
    files = sorted(glob.glob(os.path.join(str(folder), "bhav_[0-9][0-9][0-9][0-9].csv.gz")))
    if not files:
        raise FileNotFoundError(f"{folder}: no bhav_<year>.csv.gz files (run: python -m finlit_technicals fetch-nse)")
    return files


def _read_year(f: str) -> pd.DataFrame:
    """The main-board rows (series EQ, BE, BZ) of one yearly bhavcopy file, dates still as text."""
    d = pd.read_csv(f, dtype={"symbol": str, "series": str, "isin": str},
                    usecols=["date", "symbol", "series", "isin", "open", "high", "low", "close", "volume",
                             "value", "trades"])
    d["series"] = d["series"].str.strip()
    d = d[d["series"].isin(MAIN)].copy()
    # FinLit patch: one shared string object per distinct symbol / series / ISIN instead of one per row (the same values; far less memory)
    d["symbol"], d["series"], d["isin"] = _shared(d["symbol"], True), _shared(d["series"]), _shared(d["isin"])
    return d


def load_bhav(folder: str | Path) -> pd.DataFrame:
    """All main-board rows (series EQ, BE, BZ) from the yearly bhavcopy files."""
    parts = [_read_year(f) for f in _bhav_files(folder)]
    b = pd.concat(parts, ignore_index=True)
    b["date"] = pd.to_datetime(b["date"])
    return b


def _row_hashes(eq: pd.DataFrame, offset: int = 0) -> np.ndarray:
    """One 64-bit hash per EQ row of (symbol, open, high, low, close, volume rounded to 4 places). A row with a missing number never equals another row.
    `offset`: how many EQ rows came before these (when the files are read one at a time), so a row's number is the same as when all are read at once."""
    cols = eq[["symbol", "open", "high", "low", "close", "volume"]]
    h = pd.util.hash_pandas_object(cols.assign(**{c: cols[c].round(4) for c in ("open", "high", "low", "close", "volume")}), index=False).to_numpy(np.uint64).copy()
    bad = cols[["open", "high", "low", "close", "volume"]].isna().any(axis=1).to_numpy()
    if bad.any():
        h[bad] = (np.arange(len(h), dtype=np.uint64)[bad] + np.uint64(offset + 1)) * np.uint64(0x9E3779B97F4A7C15)
    return h


class _DayDropper:
    """The rule of `drop_repeated_days`, fed one file at a time: only the previous kept day's hashes are held between files."""

    def __init__(self, share: float = 0.95):
        self.share, self.prev, self.drop, self.n_eq = share, None, [], 0

    def feed(self, b: pd.DataFrame) -> list:
        """The days of this file to drop (also added to `self.drop`). Files must come in date order and hold whole days."""
        eq = b[b["series"] == "EQ"]
        if not len(eq):
            return []
        h = _row_hashes(eq, self.n_eq)
        self.n_eq += len(eq)
        dates = eq["date"].to_numpy()
        order = np.argsort(dates, kind="stable")
        sd = dates[order]
        cuts = np.flatnonzero(np.r_[True, sd[1:] != sd[:-1], True])
        gone = []
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            cur = np.unique(h[order[lo:hi]])
            d = pd.Timestamp(sd[lo])
            if self.prev is not None and len(cur) >= self.share * len(self.prev) and np.isin(cur, self.prev, assume_unique=True).sum() >= self.share * len(cur):
                gone.append(d)
                continue
            self.prev = cur
        self.drop += gone
        return gone


def drop_repeated_days(b: pd.DataFrame, share: float = 0.95) -> tuple:
    """NSE serves the previous day's file on some holidays; drop days whose EQ rows repeat the day before.

    FinLit patch: the same rule, with each row reduced to a 64-bit hash and only the previous kept day held, instead of a Python set of tuples for every day
    (those alone took about 1.5 GB for ten years of NSE files). The days dropped are identical (tests/test_nse_memory.py compares with the original)."""
    dropper = _DayDropper(share)
    dropper.feed(b)
    drop = dropper.drop
    return b[~b["date"].isin(drop)].reset_index(drop=True), drop


def load_symbol_changes(path: str | Path) -> Dict[str, List[tuple]]:
    """old symbol -> [(effective date, new symbol), ...] sorted by date."""
    out: Dict[str, List[tuple]] = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        rd = csv.reader(f)
        next(rd, None)
        for r in rd:
            if len(r) < 4 or not r[1].strip() or not r[2].strip():
                continue
            try:
                eff = dt.datetime.strptime(r[3].strip().title(), "%d-%b-%Y").date()
            except ValueError:
                continue
            out.setdefault(r[1].strip(), []).append((eff, r[2].strip()))
    for v in out.values():
        v.sort()
    return out


def resolve(symbol: str, day: dt.date, changes: Dict[str, List[tuple]]) -> str:
    """The symbol a stock trading as `symbol` on `day` uses after every later change."""
    seen = set()
    s = symbol
    while s in changes and s not in seen:
        seen.add(s)
        nxt = [(eff, new) for eff, new in changes[s] if day < eff]
        if not nxt:
            break
        s = nxt[0][1]
    return s


def _link_span(b: pd.DataFrame):
    """Per key: first and last date it trades (rows with a usable ISIN) and the issuer part of its last and first ISIN. None when no row has an ISIN."""
    has = b.dropna(subset=["isin"])
    has = has[has["isin"].str.len() >= 9]
    if has.empty:
        return None
    return has.groupby("key").agg(first=("date", "min"), last=("date", "max"),
                                  code=("isin", lambda s: s.iloc[-1][3:9]), code0=("isin", lambda s: s.iloc[0][3:9]))


def _merge_spans(spans: list):
    """The `_link_span` of the whole history from the spans of its files, read in order (first and last date: min and max; the codes: from the last / first file that has the key)."""
    spans = [x for x in spans if x is not None]
    if not spans:
        return None
    return pd.concat(spans).groupby(level=0).agg(first=("first", "min"), last=("last", "max"), code=("code", "last"), code0=("code0", "first"))


def _links_from_span(span, end_all, max_gap_days: int = 20) -> Dict[str, str]:
    by_code: Dict[str, list] = {}
    for k, r in span.iterrows():
        by_code.setdefault(r["code0"], []).append(k)
    rename = {}
    for k, r in span.iterrows():
        if r["last"] >= end_all - pd.Timedelta(days=5):
            continue
        for k2 in by_code.get(r["code"], []):
            gap = (span.loc[k2, "first"] - r["last"]).days
            if k2 != k and 0 < gap <= max_gap_days:
                rename[k] = k2

    def final(k):
        seen = set()
        while k in rename and k not in seen:
            seen.add(k)
            k = rename[k]
        return k
    return {k: final(k) for k in rename}


def link_by_isin(b: pd.DataFrame, max_gap_days: int = 20) -> Dict[str, str]:
    """Renames missing from NSE's symbol change file: a key that stops trading and a key that starts within
    `max_gap_days` with the same issuer and security type in the ISIN. Returns old key -> new key."""
    span = _link_span(b)
    if span is None:
        return {}
    return _links_from_span(span, b["date"].max(), max_gap_days)


def _symbol_keys(b: pd.DataFrame, changes: Dict[str, List[tuple]]) -> None:
    """Adds b["key"]: the symbol the stock trades under today, through NSE's symbol changes (before the ISIN links)."""
    pairs = b.loc[b["symbol"].isin(list(changes)), ["symbol", "date"]].drop_duplicates()
    keymap = {(s, d): resolve(s, d, changes) for s, d in zip(pairs["symbol"].to_numpy(), pairs["date"].dt.date.to_numpy())}
    if keymap:
        mapped = pd.Series(keymap).reindex(pd.MultiIndex.from_arrays([b["symbol"], b["date"].dt.date])).to_numpy()
        b["key"] = np.where(pd.isna(mapped), b["symbol"].to_numpy(), mapped)
    else:
        b["key"] = b["symbol"]


def _one_row_per_key_day(b: pd.DataFrame, links: Dict[str, str]) -> pd.DataFrame:
    """Applies the ISIN links; one row per key and day (EQ preferred over BE, BZ), sorted by key and date."""
    if links:
        b["key"] = b["key"].map(lambda k: links.get(k, k))
    b["srank"] = b["series"].map(SERIES_RANK).fillna(9)
    b = b.sort_values(["key", "date", "srank"]).drop_duplicates(["key", "date"], keep="first")
    return b.drop(columns="srank").reset_index(drop=True)


def add_keys(b: pd.DataFrame, changes: Dict[str, List[tuple]]) -> tuple:
    """key = the symbol the stock trades under today; one row per key and day (EQ preferred over BE, BZ)."""
    _symbol_keys(b, changes)
    links = link_by_isin(b)
    return _one_row_per_key_day(b, links), links


# ─── corporate actions ────────────────────────────────────────────────────────────────────────────────────────────
NICE = sorted({a / b for a in range(1, 13) for b in range(1, 13) if a < b} | {1 / x for x in (15, 20, 25, 50, 100)})


def load_actions(*paths) -> list:
    """(symbol, ex_date, factor, type) rows. Lines: "SYM YYYYMMDD a/b B|S|C" (factor a/b on prices before the
    ex-date), "SYM YYYYMMDD R new:held premium face_value" (rights), "SYM YYYYMMDD D" (demerger)."""
    out, seen = [], set()
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or line in seen:
                continue
            seen.add(line)
            parts = line.split()
            try:
                sym, d = parts[0], pd.Timestamp(dt.datetime.strptime(parts[1], "%Y%m%d"))
                if parts[2] == "D":
                    out.append((sym, d, None, "D"))
                elif parts[2] == "R":
                    if parts[4] == "?":
                        continue
                    a, b = parts[3].split(":")
                    out.append((sym, d, ("R", float(a), float(b), float(parts[4]) + float(parts[5])), "R"))
                else:
                    a, b = parts[2].split("/")
                    out.append((sym, d, float(a) / float(b), parts[3]))
            except (IndexError, ValueError):
                continue
    return out


def adjustment_blocks(dates, keys, close, opens, actions, changes, rep: Optional[dict] = None, block: Optional[int] = None):
    """Yields (first column, last column, factors) for blocks of columns: per day and stock, the factor that multiplies all earlier prices (1 = nothing
    happened). Every column is worked out on its own, so any block size gives the same numbers; `rep` is filled in as the blocks are consumed.

    FinLit patch: `close` and `opens` may be memory-mapped T x N arrays and only one block of columns is held at a time."""
    T, N = close.shape
    rep = rep if rep is not None else {}
    rep.update({"applied": 0, "corrected": 0, "rights": 0, "demerger": 0, "not_matched": 0})
    kidx = {k: i for i, k in enumerate(keys)}
    by_col: Dict[int, list] = {}
    for sym, d, fac, typ in actions:
        j = kidx.get(resolve(sym, d.date(), changes), kidx.get(sym))
        if j is None:
            rep["not_matched"] += 1
            continue
        by_col.setdefault(j, []).append((d, fac, typ))
    unrecorded = 0
    step = N if not block or block >= N else int(block)
    for j0 in range(0, max(N, 1), max(step, 1)):
        j1 = min(N, j0 + step)
        cl = np.array(close[:, j0:j1], dtype=np.float64, order="C")
        op = opens[:, j0:j1]
        f = np.ones((T, j1 - j0))
        last_close = pd.DataFrame(cl).ffill().shift(1).to_numpy()
        by_day: Dict[tuple, list] = {}
        for j in range(j0, j1):
            for d, fac, typ in by_col.get(j, ()):
                t = int(np.searchsorted(dates.values, np.datetime64(d)))
                while t < T and np.isnan(cl[t, j - j0]):
                    t += 1
                if t >= T or t == 0 or np.isnan(last_close[t, j - j0]):
                    rep["not_matched"] += 1
                    continue
                by_day.setdefault((t, j), []).append((fac, typ))
        for (t, j), acts in by_day.items():
            c = j - j0
            P = last_close[t, c]
            ratio = cl[t, c] / P
            o = op[t, c]
            oratio = (o if not np.isnan(o) else cl[t, c]) / P
            rights = [a for a in acts if a[1] == "R"]
            for a in rights:
                _, new, held, issue = a[0]
                if issue < P:
                    fr = (held * P + new * issue) / ((held + new) * P)
                    if fr < 0.97:
                        f[t, c] *= fr
                        rep["rights"] += 1
            stated = [a for a in acts if a[1] not in ("D", "R")]
            if not stated:
                if not rights and oratio < 0.9:          # demerger: the opening gap
                    f[t, c] *= oratio
                    rep["demerger"] += 1
                continue
            fac = float(np.prod([a[0] for a in stated]))
            if fac * 0.75 <= ratio <= fac * 1.33:
                f[t, c] *= fac
                rep["applied"] += 1
                continue
            nice = min(NICE, key=lambda x: abs(np.log(ratio / x)))   # a split and a bonus filed as one action, say
            if abs(np.log(ratio / nice)) < np.log(1.12) and nice < 0.95:
                f[t, c] *= nice
                rep["corrected"] += 1
        with np.errstate(invalid="ignore", divide="ignore"):
            r = cl / last_close
        odd = ((r < 0.35) | (r > 2.8)) & (f == 1) & ~np.isnan(r)
        f[odd] = r[odd]
        unrecorded += int(odd.sum())
        rep["unrecorded"] = unrecorded
        yield j0, j1, f
    rep["unrecorded"] = unrecorded


def adjustment_factors(dates, keys, close, opens, actions, changes) -> tuple:
    """Per day and stock, the factor that multiplies all earlier prices (1 = nothing happened)."""
    T, N = close.shape
    f = np.ones((T, N))
    rep: dict = {}
    for j0, j1, blk in adjustment_blocks(dates, keys, close, opens, actions, changes, rep):
        f[:, j0:j1] = blk
    return f, rep


def cumulative_factors(f: np.ndarray) -> np.ndarray:
    """The product of the adjustment factors after each day (adjusted = raw * cum)."""
    logf = np.log(f)
    return np.exp(np.flipud(np.cumsum(np.flipud(logf), axis=0)) - logf)


# ─── the panel ────────────────────────────────────────────────────────────────────────────────────────────────────
def release_mapped(arr, flush: bool = False) -> None:
    """Gives the resident pages of a memory-mapped array back to the system (they are read from the file again when needed; `flush` writes a writable map first).
    A no-op for an ordinary array or where madvise is not available."""
    mm = getattr(arr, "_mmap", None)
    if mm is None or not hasattr(mmap, "MADV_DONTNEED"):
        return
    try:
        if flush:
            arr.flush()
        mm.madvise(mmap.MADV_DONTNEED)
    except (OSError, ValueError, AttributeError):
        pass


PANEL_ARRAYS = ("close", "open", "high", "low", "volume", "value", "trades", "series", "cum")


@dataclass
class Panel:
    """Every main-board stock on every trading day. Prices are as traded (raw); `cum` turns them into today's terms
    (adjusted = raw * cum). Arrays are T x N; nan (or -1 for series) when the stock did not trade that day.
    The arrays are plain numpy arrays, or read-only memory maps of the cache files (NseHistory), which behave the same."""
    dates: pd.DatetimeIndex
    keys: List[str]
    close: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    value: np.ndarray          # traded value, rupees
    trades: np.ndarray
    series: np.ndarray         # 0 EQ, 1 BE, 2 BZ, -1 not traded
    cum: np.ndarray            # product of the adjustment factors after each day
    isin: Dict[str, str] = field(default_factory=dict)
    links: Dict[str, str] = field(default_factory=dict)
    report: Dict[str, int] = field(default_factory=dict)
    _adj: Optional[np.ndarray] = None

    @property
    def adj(self) -> np.ndarray:
        """Adjusted closes, T x N. Holds a second copy of the market in memory: the sector engine reads `adj_col` / `adj_at` instead."""
        if self._adj is None:
            self._adj = np.round(self.close.astype(float), 2) * self.cum
        return self._adj

    def adj_col(self, j: int) -> np.ndarray:
        """The same numbers as adj[:, j], worked out for one stock."""
        return np.round(np.asarray(self.close[:, j]).astype(float), 2) * np.asarray(self.cum[:, j])

    def adj_at(self, t: int, j: int) -> float:
        """The same number as adj[t, j]."""
        t = t % len(self.dates)
        return float((np.round(np.asarray(self.close[t:t + 1, j]).astype(float), 2) * np.asarray(self.cum[t:t + 1, j]))[0])

    def col(self, key: str) -> int:
        return self.keys.index(key)

    def release_pages(self) -> None:
        """Gives the pages of memory-mapped arrays back (they are read again from the cache file when needed); a no-op for ordinary arrays."""
        for name in PANEL_ARRAYS:
            release_mapped(getattr(self, name))


def build_panel(b: pd.DataFrame, actions: list, changes, links=None) -> Panel:
    dates = pd.DatetimeIndex(sorted(b["date"].unique()))
    keys = sorted(b["key"].unique())
    ti = pd.Index(dates).get_indexer(b["date"])
    ki = pd.Index(keys).get_indexer(b["key"])
    T, N = len(dates), len(keys)

    def mat(col, dtype=np.float32):
        m = np.full((T, N), np.nan, dtype=dtype)
        m[ti, ki] = b[col].to_numpy(dtype=dtype)
        return m

    close = mat("close", np.float64)
    close[close <= 0] = np.nan
    opn = mat("open")
    series = np.full((T, N), -1, dtype=np.int8)
    series[ti, ki] = b["series"].map(SERIES_RANK).fillna(9).to_numpy(dtype=np.int8)
    f, rep = adjustment_factors(dates, keys, close, opn, actions, changes)
    cum = cumulative_factors(f)
    isin = b.drop_duplicates("key", keep="last").set_index("key")["isin"].to_dict()
    return Panel(dates=dates, keys=keys, close=close.astype(np.float32), open=opn, high=mat("high"), low=mat("low"),
                 volume=mat("volume"), value=mat("value"), trades=mat("trades"), series=series, cum=cum,
                 isin={k: v for k, v in isin.items() if isinstance(v, str)}, links=links or {}, report=rep)


class _NotChunkable(Exception):
    """The yearly files overlap in dates, so they cannot be read one at a time; the panel is built in memory instead."""


_MATRIX_DTYPES = {"close": np.float32, "open": np.float32, "high": np.float32, "low": np.float32, "volume": np.float32, "value": np.float32,
                  "trades": np.float32, "series": np.int8, "cum": np.float64}


def _new_matrix(path: Path, dtype, shape):
    """A new T x N .npy file, one stock after the other (Fortran order): a stock's whole history is one contiguous piece of the file, so reading some stocks
    through the memory map brings in only their pages, not a page of every day of the year for each of them."""
    return np.lib.format.open_memmap(str(path), mode="w+", dtype=dtype, shape=shape, fortran_order=True)


def build_panel_files(folder: str | Path, actions: list, changes, dest: Path, block: int = 256, log=None) -> dict:
    """The panel of `build_panel(*add_keys(drop_repeated_days(load_bhav(folder))))`, built one yearly file at a time and written as plain .npy files into `dest`
    (one per array, T x N, same dtypes). Returns what is not an array (dates, keys, isin, links, report).

    FinLit patch: the original holds all 5.7 million rows (about 1 GB) and the dense matrices (about 700 MB) at once. Here a file is read twice (first for the days to
    drop, the keys and the ISIN links, which need the whole history; then to fill that year's rows of the matrices) and the adjustment factors are worked out
    for blocks of stocks, so the peak is a year of rows plus a block. Every number is produced by the same operations as in `build_panel`
    (tests/test_nse_memory.py compares the two bit for bit)."""
    say = log or (lambda *_: None)
    files = _bhav_files(folder)
    # pass 1: the days to drop, the key of every row, and what the ISIN links need
    dropper, spans, ukeys, dset, end_all, prev_max = _DayDropper(), [], set(), set(), None, None
    for f in files:
        d = _read_year(f)
        d["date"] = pd.to_datetime(d["date"])
        if len(d):
            lo, hi = d["date"].min(), d["date"].max()
            if prev_max is not None and lo <= prev_max:
                raise _NotChunkable(f"{os.path.basename(f)} starts at {lo.date()}, not after the file before it ({prev_max.date()})")
            prev_max = hi
        gone = dropper.feed(d)
        if gone:
            d = d[~d["date"].isin(gone)]
        if d.empty:
            continue
        _symbol_keys(d, changes)
        spans.append(_link_span(d))
        ukeys.update(d["key"].unique())
        dset.update(d["date"].unique())
        mx = d["date"].max()
        end_all = mx if end_all is None else max(end_all, mx)
        say(f"pass 1: {os.path.basename(f)}")
        del d
    if not dset:
        raise ValueError(f"{folder}: no main-board rows")
    span = _merge_spans(spans)
    links = {} if span is None else _links_from_span(span, end_all)
    dates = pd.DatetimeIndex(sorted(dset))
    keys = sorted({links.get(k, k) for k in ukeys})
    T, N = len(dates), len(keys)
    kindex = pd.Index(keys)
    dest.mkdir(parents=True, exist_ok=True)
    mats = {name: _new_matrix(dest / f"{name}.npy", dt, (T, N)) for name, dt in _MATRIX_DTYPES.items() if name != "cum"}
    close64 = _new_matrix(dest / "close64.tmp.npy", np.float64, (T, N))      # the unrounded closes the adjustment factors are worked out from
    isin_last: Dict[str, object] = {}
    # pass 2: the same files again, each year's rows go into place
    dropped = dropper.drop
    for f in files:
        d = _read_year(f)
        d["date"] = pd.to_datetime(d["date"])
        if dropped:
            d = d[~d["date"].isin(dropped)]
        if d.empty:
            continue
        _symbol_keys(d, changes)
        d = _one_row_per_key_day(d, links)
        ti = dates.get_indexer(d["date"])
        ki = kindex.get_indexer(d["key"])
        t0 = int(ti.min())
        t1 = int(ti.max()) + 1
        tl = ti - t0
        rows = t1 - t0

        def band(col, dtype=np.float32):
            m = np.full((rows, N), np.nan, dtype=dtype)
            m[tl, ki] = d[col].to_numpy(dtype=dtype)
            return m
        def put(m, a):
            m[t0:t1] = a
            release_mapped(m, flush=True)               # written: its pages need not stay in memory
        c = band("close", np.float64)
        c[c <= 0] = np.nan
        put(close64, c)
        put(mats["close"], c.astype(np.float32))
        for name in ("open", "high", "low", "volume", "value", "trades"):
            put(mats[name], band(name))
        ser = np.full((rows, N), -1, dtype=np.int8)
        ser[tl, ki] = d["series"].map(SERIES_RANK).fillna(9).to_numpy(dtype=np.int8)
        put(mats["series"], ser)
        last = d.drop_duplicates("key", keep="last")
        isin_last.update(zip(last["key"].tolist(), last["isin"].tolist()))
        say(f"pass 2: {os.path.basename(f)}")
        del d, c, ser, last
    for m in mats.values():
        m.flush()
    close64.flush()
    del mats
    # the adjustment factors and their running product, a block of stocks at a time
    close64 = np.load(dest / "close64.tmp.npy", mmap_mode="r")
    opens = np.load(dest / "open.npy", mmap_mode="r")
    cum = _new_matrix(dest / "cum.npy", np.float64, (T, N))
    rep: dict = {}
    for j0, j1, f in adjustment_blocks(dates, keys, close64, opens, actions, changes, rep, block=block):
        cum[:, j0:j1] = cumulative_factors(f)
        for m in (cum, close64, opens):
            release_mapped(m, flush=True)
        say(f"adjusted stocks {j1}/{N}")
    cum.flush()
    del cum, close64, opens
    os.remove(dest / "close64.tmp.npy")
    isin = {k: isin_last[k] for k in sorted(isin_last) if isinstance(isin_last[k], str)}
    return {"dates": dates, "keys": keys, "isin": isin, "links": links, "report": rep, "shape": (T, N)}


def open_panel(src: Path, meta: dict) -> Panel:
    """A Panel whose arrays are read-only memory maps of the .npy files in `src`."""
    arr = {name: np.load(src / f"{name}.npy", mmap_mode="r") for name in PANEL_ARRAYS}
    for name, a in arr.items():
        if a.shape != tuple(meta["shape"]) or a.dtype != _MATRIX_DTYPES[name]:
            raise ValueError(f"{name}.npy does not match the panel it belongs to")
    return Panel(dates=meta["dates"], keys=meta["keys"], isin=meta["isin"], links=meta["links"], report=meta["report"], **arr)


def load_indices(folder: str | Path) -> pd.DataFrame:
    files = sorted(glob.glob(os.path.join(str(folder), "idx_[0-9][0-9][0-9][0-9].csv.gz")))
    if not files:
        return pd.DataFrame(columns=["date", "index", "open", "high", "low", "close", "volume"])
    d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    d["name"] = d["index"].astype(str).str.upper().str.strip()
    return d


# ─── the source ───────────────────────────────────────────────────────────────────────────────────────────────────
class NseHistory:
    """A price source (daily / index, like CsvFolder) built from NSE's daily files, plus the whole panel."""

    def __init__(self, folder: str | Path, actions_file: Optional[str | Path] = None, cache: bool = True, chunked: bool = True):
        self.folder = Path(folder).expanduser()
        self.actions_files = [BUNDLED_ACTIONS, self.folder / "ref" / "corporate_actions.txt"]
        if actions_file:
            self.actions_files.append(Path(actions_file))
        self.cache = cache
        self.chunked = chunked          # False: build the panel in memory in one go, as v2.0.1 did (the reference the tests compare with)
        self._panel: Optional[Panel] = None
        self._idx: Optional[pd.DataFrame] = None
        self._changes = None
        self._kidx: Optional[Dict[str, int]] = None
        self._names: Optional[Dict[str, str]] = None

    # building
    def _signature(self) -> str:
        h = hashlib.sha1(CACHE_VERSION.encode())
        files = sorted(glob.glob(str(self.folder / "bhav_*.csv.gz"))) + [str(self.folder / "ref" / "symbolchange.csv")]
        files += [str(p) for p in self.actions_files]
        for f in files:
            if os.path.exists(f):
                st = os.stat(f)
                h.update(f"{os.path.basename(f)}:{st.st_size}:{int(st.st_mtime)}".encode())
        return h.hexdigest()

    @property
    def changes(self):
        if self._changes is None:
            self._changes = load_symbol_changes(self.folder / "ref" / "symbolchange.csv")
        return self._changes

    @property
    def cache_dir(self) -> Path:
        return self.folder / ".finlit_cache" / "panel"

    def _open_cached(self, sig: str) -> Optional[Panel]:
        """The panel from the cache folder when it is complete and was built from these files; None (so it is rebuilt) when it is missing, stale or partial."""
        try:
            with open(self.cache_dir / "meta.pkl", "rb") as fh:
                meta = pickle.load(fh)
            if meta.get("sig") != sig or meta.get("version") != CACHE_VERSION:
                return None
            return open_panel(self.cache_dir, meta)
        except Exception:      # noqa: BLE001  (a stale or partial cache is rebuilt)
            return None

    def _build_cached(self, sig: str) -> Optional[Panel]:
        """Builds the panel one year at a time into the cache folder and opens it. None when the cache cannot be written or the files cannot be read one at a time."""
        root = self.folder / ".finlit_cache"
        tmp = root / f"panel-building-{os.getpid()}"
        try:
            root.mkdir(exist_ok=True)
            for old in root.glob("panel-building-*"):      # left by a run that was killed
                shutil.rmtree(old, ignore_errors=True)
            meta = build_panel_files(self.folder, load_actions(*self.actions_files), self.changes, tmp)
            meta.update(sig=sig, version=CACHE_VERSION)
            with open(tmp / "meta.pkl.tmp", "wb") as fh:          # written last: a folder without it is an unfinished build
                pickle.dump(meta, fh, protocol=4)
            os.replace(tmp / "meta.pkl.tmp", tmp / "meta.pkl")
            shutil.rmtree(self.cache_dir, ignore_errors=True)
            os.replace(tmp, self.cache_dir)
            try:
                (root / "panel.pkl").unlink()            # the cache of earlier versions: one 285 MB pickle that had to be loaded whole
            except OSError:
                pass
            return open_panel(self.cache_dir, meta)
        except (OSError, _NotChunkable):
            shutil.rmtree(tmp, ignore_errors=True)
            return None

    @property
    def panel(self) -> Panel:
        if self._panel is None:
            sig = self._signature()
            if self.cache and self.chunked:
                self._panel = self._open_cached(sig) or self._build_cached(sig)
            if self._panel is None:
                b = load_bhav(self.folder)
                b, _ = drop_repeated_days(b)
                b, links = add_keys(b, self.changes)
                self._panel = build_panel(b, load_actions(*self.actions_files), self.changes, links)
        return self._panel

    @property
    def calendar(self) -> pd.DatetimeIndex:
        return self.panel.dates

    def key(self, symbol: str) -> Optional[str]:
        """The panel key (today's symbol) for a symbol, old symbols included."""
        p = self.panel
        if self._kidx is None:
            self._kidx = {k: i for i, k in enumerate(p.keys)}
            self._norm = {norm_symbol(k): k for k in p.keys}
        s = symbol.split(":")[-1].strip().upper()
        s = self._norm.get(norm_symbol(s), s)
        if s in self._kidx:
            return s
        s2 = resolve(s, dt.date(1990, 1, 1), self.changes)
        s2 = p.links.get(s2, s2)
        return s2 if s2 in self._kidx else None

    def symbols(self) -> List[str]:
        return list(self.panel.keys)

    def names(self) -> Dict[str, str]:
        """Company names of stocks listed today (from ref/EQUITY_L.csv)."""
        if self._names is None:
            self._names = {}
            path = self.folder / "ref" / "EQUITY_L.csv"
            if path.exists():
                d = pd.read_csv(path)
                d.columns = [c.strip().upper() for c in d.columns]
                if "SYMBOL" in d and "NAME OF COMPANY" in d:
                    self._names = dict(zip(d["SYMBOL"].astype(str).str.strip(), d["NAME OF COMPANY"].astype(str).str.strip()))
        return self._names

    # the PriceSource interface
    def daily(self, symbol: str) -> Optional[pd.DataFrame]:
        k = self.key(symbol)
        if k is None:
            return None
        p = self.panel
        j = self._kidx[k]
        ok = ~np.isnan(p.close[:, j])
        if not ok.any():
            return None
        c = p.cum[ok, j]

        def adj(a):
            return np.round(a[ok, j].astype(float), 2) * c
        df = pd.DataFrame({"open": adj(p.open), "high": adj(p.high), "low": adj(p.low), "close": adj(p.close),
                           "volume": np.round(p.volume[ok, j].astype(float)) / c},
                          index=pd.DatetimeIndex(p.dates[ok], name="date"))
        return df[COLUMNS]

    def index(self, code: str) -> Optional[pd.DataFrame]:
        if self._idx is None:
            self._idx = load_indices(self.folder)
        info = INDICES.get(code)
        name = (info["nse"] if info else code.split(":")[-1]).upper()
        d = self._idx[self._idx["name"].isin([name] + INDEX_ALIASES.get(name, []))]
        if d.empty:
            return None
        d = d.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        out = pd.DataFrame({c: pd.to_numeric(d[c], errors="coerce") for c in ("open", "high", "low", "close", "volume")
                            if c in d})
        for c in ("open", "high", "low"):
            out[c] = out[c].fillna(out["close"])
        out["volume"] = out.get("volume", pd.Series(0.0, index=out.index)).fillna(0.0)
        out.index.name = "date"
        return out[COLUMNS]
