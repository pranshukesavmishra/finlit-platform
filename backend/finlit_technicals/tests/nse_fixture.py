"""A small synthetic NSE folder (the layout fetch-nse keeps) with the awkward cases the data layer must handle."""
from __future__ import annotations

import csv
import gzip
from pathlib import Path

import numpy as np
import pandas as pd

COLS = ["date", "symbol", "series", "isin", "open", "high", "low", "close", "last", "prev_close", "volume", "value",
        "trades"]
# NSE's Ferrous Metals industry (14 stocks that count + the awkward ones below)
FERROUS = ["TATASTEEL", "JSWSTEEL", "SAIL", "JINDALSTEL", "JSL", "NSLNISP", "KIRLFER", "IMFA", "SARDAEN",
           "MAITHANALL", "KIOCL", "JAIBALAJI", "SANDUMA", "VRAJ"]
LEADER = "KIRLFER"
LOW_VALUE, LOCKED, PENNY, IPO, TO_BE, DELISTED, SMALL_CAP = ("VASWANI", "VISACHROME", "SHYAMCENT", "VISL",
                                                             "MANAKSTEEL", "SALSTEEL", "PRAKASH")
OIL_GAS = ["GAIL", "IGL", "ONGC", "COALINDIA"]          # small industries: read together as their NSE sector
RENAMED_FROM = "VRAJOLD"                                 # VRAJ traded as VRAJOLD before RENAME_DAY (symbolchange.csv)
LINK_OLD, LINK_NEW = "ZZOLD", "SCANSTL"                  # a rename missing from symbolchange.csv: same ISIN issuer
SPLIT_DAY, RENAME_DAY, LINK_DAY, IPO_DAY, DELIST_DAY, BE_DAY, REPEAT_AFTER = 500, 200, 250, 450, 300, 600, 100
DAYS = 620


def isin(i: int) -> str:
    return f"INE{i:04d}01010"


def paths(days=DAYS, seed=3):
    """Prices: up-trend, a hard fall (washout), a sharp rebound on the same days (a thrust), then a steady rise."""
    rng = np.random.default_rng(seed)
    n = max(days, DAYS)
    cal = pd.bdate_range("2023-01-02", periods=n)[:days]
    out = {}
    names = FERROUS + [LOW_VALUE, LOCKED, PENNY, IPO, TO_BE, DELISTED, SMALL_CAP, LINK_NEW] + OIL_GAS
    for k, s in enumerate(names):
        drift = np.r_[np.full(400, 0.0015), np.full(150, -0.004), np.full(5, 0.03), np.full(n - 555, 0.002)]
        r = drift + rng.normal(0, 0.006, n)
        if s == LEADER:
            r[400:550] = 0.0025 + rng.normal(0, 0.002, 150)
        base = 12.0 if s == PENNY else 1000.0 if s == "TATASTEEL" else 100.0 + k
        out[s] = (base * np.exp(np.cumsum(r)))[:days]
    return cal, out


def write_folder(root: Path, days=DAYS) -> Path:
    cal, px = paths(days)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    for k, (s, c) in enumerate(px.items()):
        for t, d in enumerate(cal):
            sym, series, code = s, "EQ", isin(k)
            close = float(c[t])
            vol = 1_000_000.0
            if s == IPO and t < IPO_DAY:
                continue
            if s == DELISTED and t >= DELIST_DAY:
                continue
            if s == "VRAJ" and t < RENAME_DAY:
                sym = RENAMED_FROM
            if s == LINK_NEW:
                if t < LINK_DAY:
                    sym = LINK_OLD
                elif t < LINK_DAY + 2:
                    continue                      # two quiet days between the old and the new symbol
            if s == TO_BE and t >= BE_DAY:
                series = "BE"
            if s == LOW_VALUE:
                vol = 5_000.0
            if s == "TATASTEEL" and t >= SPLIT_DAY:
                close /= 10.0                      # a 1:10 split: prices as traded drop to a tenth
                vol *= 10
            hi, lo = close * 1.01, close * 0.99
            if s == LOCKED and t % 10 == 0:
                hi = lo = close                    # stuck at a price band one session in ten
            rows.append([d.date().isoformat(), sym, series, code, close, hi, lo, close, close, close, vol, close * vol, 1000])
    b = pd.DataFrame(rows, columns=COLS)
    # NSE's holiday copy of the previous day: same rows, next calendar day (a Saturday)
    rep_day = cal[REPEAT_AFTER]
    extra = b[b["date"] == rep_day.date().isoformat()].copy()
    extra["date"] = (rep_day + pd.Timedelta(days=1)).date().isoformat()
    b = pd.concat([b, extra], ignore_index=True).sort_values(["date", "symbol"])
    for y, g in b.groupby(b["date"].str[:4]):
        with gzip.open(root / f"bhav_{y}.csv.gz", "wt", newline="") as fh:
            g.to_csv(fh, index=False)
    nifty = 10000 * np.exp(np.linspace(0, 0.3, len(cal)))
    idx = pd.DataFrame({"date": [d.date().isoformat() for d in cal], "index": "Nifty 50", "open": nifty, "high": nifty,
                        "low": nifty, "close": nifty, "volume": 1e8, "turnover_cr": 1e4, "pe": 20, "pb": 3, "div_yield": 1})
    for y, g in idx.groupby(idx["date"].str[:4]):
        with gzip.open(root / f"idx_{y}.csv.gz", "wt", newline="") as fh:
            g.to_csv(fh, index=False)
    ref = root / "ref"
    ref.mkdir(exist_ok=True)
    with open(ref / "symbolchange.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["NAME OF THE COMPANY", "OLD SYMBOL", "NEW SYMBOL", "EFFECTIVE DATE"])
        w.writerow(["Vraj Iron and Steel Limited", RENAMED_FROM, "VRAJ", cal[RENAME_DAY].strftime("%d-%b-%Y").upper()])
    with open(ref / "EQUITY_L.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["SYMBOL", "NAME OF COMPANY", " SERIES", " DATE OF LISTING"])
        for s in px:
            w.writerow([s, s.title() + " Limited", "EQ", "01-JAN-2000"])
    (ref / "corporate_actions.txt").write_text(f"TATASTEEL {cal[SPLIT_DAY]:%Y%m%d} 1/10 S\n")
    write_amfi(root / "amfi", px, cal)
    return root


def write_amfi(folder: Path, px, cal):
    import openpyxl
    folder.mkdir(exist_ok=True)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Average Market Capitalization of listed companies during the six months ended 31 Dec 2022"])
    ws.append(["Sr. No.", "Company name", "ISIN", "BSE Symbol", "BSE 6 month Avg Total Market Cap in (Rs. Crs.)",
               "NSE Symbol", "NSE 6 month Avg Total Market Cap in (Rs. Crs.)", "MSEI Symbol", "MSEI cap",
               "Average of All Exchanges (Rs. Cr.)", "Categorization as per SEBI Circular dated Oct 6, 2017"])
    for k, s in enumerate(px):
        cap = 400.0 if s == SMALL_CAP else 5000.0 + k
        ws.append([k + 1, s.title(), isin(k), s, cap, s, cap, None, None, cap, "Small Cap"])
    wb.save(folder / "2022H2.xlsx")
