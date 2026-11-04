"""A synthetic NSE folder of the REAL size (the layout `fetch-nse` keeps), for measuring memory and time and for comparing two versions of the code.

    python big_fixture.py DEST                       # 2,800 stocks, Jan 2016 to Oct 2026, about 5.7 million rows (about 2 minutes)
    python big_fixture.py DEST --stocks 400 --start 2024-01-01 --end 2026-10-30     # a small one for tests

The stocks are real NSE symbols from data/nse_industries.json (so every stock has an industry). The data has the awkward cases the data layer must handle:
listings and delistings spread over the years, renames (in symbolchange.csv, and renames NSE did not file that only the ISIN links), a day where the old and
the new symbol both trade, stocks that move from EQ to BE/BZ, splits (filed in corporate_actions.txt and unfiled ones), holiday days that repeat the day before,
zero closes, locked (high = low) days, thin and liquid stocks, half-yearly AMFI market caps and index files. Everything comes from a seeded generator, so two
runs give the same files.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "last", "prev_close", "volume", "value", "trades"]
DATA = Path(__file__).resolve().parents[1] / "data"


def _calendar(start: str, end: str, rng) -> pd.DatetimeIndex:
    cal = pd.bdate_range(start, end)
    years = cal.year
    keep = np.ones(len(cal), bool)
    for y in np.unique(years):                                   # about 14 weekday holidays a year
        idx = np.flatnonzero(years == y)
        keep[rng.choice(idx, size=min(14, len(idx) // 10), replace=False)] = False
    return cal[keep]


def write_big_folder(root: Path, n_stocks: int = 2800, start: str = "2016-01-01", end: str = "2026-10-30", seed: int = 11,
                     with_amfi: bool = True, log=print, liq_mean: float = 16.8, cap_median: float = 2500.0) -> dict:
    """Write the folder; returns a small dict with the counts. `liq_mean` (log of the usual traded value in rupees; 16.8 is Rs 2 crore) and `cap_median`
    (Rs crore) set how many stocks pass the universe rules: raise them for a small folder in which every industry should have counted stocks."""
    rng = np.random.default_rng(seed)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    (root / "ref").mkdir(exist_ok=True)
    cls = json.loads((DATA / "nse_industries.json").read_text())["stocks"]
    pool = sorted(cls)
    names = sorted(rng.choice(pool, size=min(n_stocks, len(pool)), replace=False).tolist())
    N = len(names)
    cal = _calendar(start, end, rng)
    T = len(cal)
    ind_of = {k: v[0] for k, v in cls.items()}
    inds = sorted({ind_of[s] for s in names})
    ind_ix = np.array([inds.index(ind_of[s]) for s in names])

    # when each stock trades
    s0 = np.where(rng.random(N) < 0.55, 0, rng.integers(1, max(2, T - 300), N))
    e0 = np.full(N, T)
    gone = rng.random(N) < 0.10
    e0[gone] = np.minimum(T, s0[gone] + rng.integers(200, max(201, T), gone.sum()))
    # renames filed in symbolchange.csv (old name until the effective day) and renames only the ISIN links (3 quiet days between the two names)
    warm, tail = min(200, T // 4), min(100, T // 5)         # (200 and 100 days for the full ten years)
    order = rng.permutation(np.flatnonzero((e0 == T) & (s0 + 3 * warm < T)))
    filed, linked = order[:max(1, N // 70)], order[max(1, N // 70):max(2, N // 70) + max(1, N // 190)]
    ren_day = np.full(N, -1)
    ren_day[filed] = [rng.integers(s0[j] + warm, T - tail) for j in filed]
    ren_day[linked] = [rng.integers(s0[j] + warm, T - tail) for j in linked]
    old_name = {int(j): f"{names[j][:5]}Q{int(j) % 100}" for j in np.concatenate([filed, linked])}
    gap = np.zeros(N, int)
    gap[linked] = 3
    # series: mostly EQ; some are BE all their life; some move EQ -> BE (or BZ) late
    base_series = np.zeros(N, np.int8)
    base_series[rng.random(N) < 0.06] = 1
    move = np.where((base_series == 0) & (rng.random(N) < 0.06))[0]
    move_day = np.full(N, T + 1)
    move_day[move] = [rng.integers(s0[j] + 100, T + 50) for j in move]
    move_to = np.where(rng.random(N) < 0.7, 1, 2).astype(np.int8)
    # prices
    liq = rng.normal(liq_mean, 1.6, N)                             # log of the usual traded value in rupees
    price0 = np.exp(np.clip(rng.normal(5.4, 1.1, N), np.log(8), np.log(9000)))
    vol_daily = np.exp(rng.normal(np.log(0.017), 0.35, N))
    beta = np.clip(rng.normal(1.0, 0.3, N), 0.2, 2.0)
    prone = np.where(rng.random(N) < 0.08, 0.15, 0.002)       # chance of a locked (high = low) day
    mkt = rng.normal(0.0004, 0.009, T)
    crash = np.flatnonzero((cal >= "2020-03-02") & (cal <= "2020-03-23"))
    if len(crash):
        mkt[crash] = -0.03 + rng.normal(0, 0.01, len(crash))
        up = np.flatnonzero((cal > "2020-03-23") & (cal <= "2020-04-10"))
        mkt[up] = 0.018 + rng.normal(0, 0.01, len(up))
    indf = rng.normal(0, 0.008, (T, len(inds)))
    # splits: filed (corporate_actions.txt) or not
    split_ix = rng.choice(N, size=max(1, N // 25), replace=False)
    split_day = {int(j): int(rng.integers(s0[j] + 60, max(s0[j] + 61, e0[j] - 20))) for j in split_ix if e0[j] - s0[j] > 150}
    split_k = {j: int(rng.choice([2, 5, 10])) for j in split_day}
    filed_split = {j for j in split_day if rng.random() < 0.7}
    actions = [f"{names[j]} {cal[d]:%Y%m%d} 1/{split_k[j]} S" for j, d in sorted(split_day.items()) if j in filed_split]
    (root / "ref" / "corporate_actions.txt").write_text("\n".join(actions) + "\n")
    # symbolchange.csv, EQUITY_L.csv
    with open(root / "ref" / "symbolchange.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["NAME OF THE COMPANY", "OLD SYMBOL", "NEW SYMBOL", "EFFECTIVE DATE"])
        for j in filed:
            w.writerow([names[j].title() + " Limited", old_name[int(j)], names[j], cal[ren_day[j]].strftime("%d-%b-%Y").upper()])
    with open(root / "ref" / "EQUITY_L.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["SYMBOL", "NAME OF COMPANY", " SERIES", " DATE OF LISTING"])
        for k, s in enumerate(names):
            if e0[k] == T:
                w.writerow([s, s.title() + " Limited", "EQ", "01-JAN-2000"])
    isin = [f"INE{k:06d}01{k % 10}" for k in range(N)]
    logp = np.log(price0)
    last_close = np.full(N, np.nan)
    ends, nifty_path, rows_total = {}, np.cumsum(mkt), 0
    year_close = {}
    split_div = np.ones(N)                                      # raw price = path price / split_div
    month_last = {}
    for y in sorted(set(cal.year)):
        r0, r1 = int(np.searchsorted(cal.year, y, "left")), int(np.searchsorted(cal.year, y, "right"))
        ty = r1 - r0
        idio = rng.standard_t(4, (ty, N)) * vol_daily * 0.7
        ret = beta * mkt[r0:r1, None] + indf[r0:r1][:, ind_ix] + idio
        path = logp + np.cumsum(ret, axis=0)
        logp = path[-1].copy()
        px = np.exp(path)
        tt = np.arange(r0, r1)[:, None]
        act = (tt >= s0) & (tt < e0)
        for j in linked:                                        # the quiet days between the old and the new name
            act[:, j] &= ~((tt[:, 0] >= ren_day[j]) & (tt[:, 0] < ren_day[j] + gap[j]))
        raw = px.copy()
        for j, d in split_day.items():                          # the price as traded falls after the split day
            m = tt[:, 0] >= d
            raw[m, j] = px[m, j] / split_k[j]
        close = np.maximum(np.round(raw, 2), 0.05)
        prev = np.vstack([np.where(np.isnan(last_close), close[0], last_close)[None, :], close[:-1]])
        last_close = close[-1].copy()
        opn = np.round(prev * (1 + rng.normal(0, 0.004, close.shape)), 2)
        hi = np.round(np.maximum(opn, close) * (1 + np.abs(rng.normal(0, 0.006, close.shape))), 2)
        lo = np.round(np.minimum(opn, close) * (1 - np.abs(rng.normal(0, 0.006, close.shape))), 2)
        locked = rng.random(close.shape) < prone
        hi[locked] = lo[locked] = close[locked]
        value = np.exp(liq + rng.normal(0, 0.5, close.shape))
        vol = np.maximum(np.round(value / close), 1.0)
        value = np.round(close * vol, 2)
        trades = np.maximum(1, (value / 60000 * rng.uniform(0.5, 1.5, close.shape))).astype(int)
        close_z = rng.random(close.shape) < 0.0003                # a zero close is a bad print
        ti, ji = np.nonzero(act)
        sym = np.array(names, dtype=object)[ji]
        for j, od in old_name.items():
            m = (ji == j) & (ti + r0 < ren_day[j])
            sym[m] = od
        ser = np.where((ti + r0) >= move_day[ji], move_to[ji], base_series[ji])
        sername = np.array(["EQ", "BE", "BZ"], dtype=object)[ser]
        c = close[ti, ji]
        c = np.where(close_z[ti, ji], 0.0, c)
        df = pd.DataFrame({
            "date": cal[r0 + ti].strftime("%Y-%m-%d"), "symbol": sym, "series": sername, "isin": np.array(isin, dtype=object)[ji],
            "open": opn[ti, ji], "high": hi[ti, ji], "low": lo[ti, ji], "close": c, "last": c, "prev_close": prev[ti, ji],
            "volume": vol[ti, ji], "value": value[ti, ji], "trades": trades[ti, ji]})
        # the day both names trade (the old symbol in BE), so one key has two rows
        dup = []
        for j in filed[: max(1, len(filed) // 2)]:
            d = ren_day[j]
            if r0 <= d < r1:
                m = (ji == j) & (ti + r0 == d)
                if m.any():
                    extra = df[m].copy()
                    extra["symbol"], extra["series"] = old_name[int(j)], "BE"
                    dup.append(extra)
        if dup:
            df = pd.concat([df] + dup, ignore_index=True).sort_values(["date"], kind="stable")
        # NSE's holiday copies of the previous day (a Saturday)
        copies = []
        for d in rng.choice(np.arange(1, ty - 1), size=min(2, max(0, ty - 3)), replace=False) if ty > 4 else []:
            day = cal[r0 + int(d)]
            cp = df[df["date"] == day.strftime("%Y-%m-%d")].copy()
            cp["date"] = (day + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
            copies.append(cp)
        if copies:
            df = pd.concat([df] + copies, ignore_index=True).sort_values("date", kind="stable")
        rows_total += len(df)
        with gzip.open(root / f"bhav_{y}.csv.gz", "wt", newline="", compresslevel=3) as fh:
            df.to_csv(fh, index=False)
        year_close[y] = px[-1].copy()
        for t in range(r0, r1):
            month_last[(cal[t].year, cal[t].month)] = t
        # indices
        sl = slice(r0, r1)
        rows = []
        for nm, f in (("Nifty 50", 1.0), ("Nifty Bank", 1.3), ("Nifty Midcap 100", 1.1)):
            lv = 10000 * np.exp(f * nifty_path[sl])
            rows.append(pd.DataFrame({"date": cal[sl].strftime("%Y-%m-%d"), "index": nm, "open": lv, "high": lv * 1.004, "low": lv * 0.996, "close": lv,
                                      "volume": 1e8, "turnover_cr": 1e4, "pe": 20.0, "pb": 3.0, "div_yield": 1.0}))
        with gzip.open(root / f"idx_{y}.csv.gz", "wt", newline="", compresslevel=3) as fh:
            pd.concat(rows, ignore_index=True).to_csv(fh, index=False)
        log(f"{y}: {len(df):,} rows")
    if with_amfi:
        _write_amfi(root / "amfi", names, isin, s0, e0, cal, price0, rng, cap_median)
    return {"stocks": N, "days": T, "rows": rows_total, "industries": len(inds)}


def _write_amfi(folder: Path, names, isin, s0, e0, cal, price0, rng, cap_median: float = 2500.0) -> None:
    import openpyxl
    folder.mkdir(exist_ok=True)
    N = len(names)
    cap0 = np.exp(rng.normal(np.log(cap_median), 1.5, N))
    rank = np.argsort(-cap0)
    cat = np.array(["Small Cap"] * N, dtype=object)
    cat[rank[:100]], cat[rank[100:250]] = "Large Cap", "Mid Cap"
    first, last = cal[0], cal[-1]
    periods = [(y, h) for y in range(first.year, last.year + 1) for h in (1, 2)]
    for y, h in periods:
        end = pd.Timestamp(y, 6, 30) if h == 1 else pd.Timestamp(y, 12, 31)
        if end < first or end - pd.Timedelta(days=15) > last:
            continue
        t_end = int(np.searchsorted(cal.values, np.datetime64(end), "right")) - 1
        growth = np.exp(rng.normal(0.08 * (end.year - last.year), 0.15, N))
        wb = openpyxl.Workbook(write_only=True)
        ws = wb.create_sheet()
        ws.append([f"Average Market Capitalization of listed companies during the six months ended {end:%d %b %Y}"])
        ws.append(["Sr. No.", "Company name", "ISIN", "BSE Symbol", "BSE 6 month Avg Total Market Cap in (Rs. Crs.)", "NSE Symbol",
                   "NSE 6 month Avg Total Market Cap in (Rs. Crs.)", "MSEI Symbol", "MSEI cap", "Average of All Exchanges (Rs. Cr.)",
                   "Categorization as per SEBI Circular dated Oct 6, 2017"])
        n = 0
        for k, s in enumerate(names):
            if s0[k] > t_end or e0[k] <= max(0, t_end - 130) or k % 41 == 7:      # not listed then, gone, or missing from AMFI's list
                continue
            n += 1
            cap = round(float(cap0[k] * growth[k]), 2)
            ws.append([n, s.title(), isin[k], s, cap, s, cap, None, None, cap, cat[k]])
        wb.save(folder / f"{y}H{h}.xlsx")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("dest")
    ap.add_argument("--stocks", type=int, default=2800)
    ap.add_argument("--start", default="2016-01-01")
    ap.add_argument("--end", default="2026-10-30")
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--liq-mean", type=float, default=16.8)
    ap.add_argument("--cap-median", type=float, default=2500.0)
    a = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)
    print(write_big_folder(Path(a.dest), a.stocks, a.start, a.end, a.seed, liq_mean=a.liq_mean, cap_median=a.cap_median))
