"""Shows what the sector job read for a few stocks, so it can be compared with NSE's own daily files (docs/SECTORS.md, "Data checks").

    python scripts/check_universe_inputs.py ASHIANA SURAJEST MAHSCOOTER TVSHLTD --nse /data/nse [--days 70]

For each stock: the series (EQ, BE, BZ) and the traded value in Rs crore of its last sessions, as stored from NSE's files, the median over the last 65
sessions (the number the universe rule compares with Rs 2 crore to join and Rs 1 crore to stay), and the same rows read straight from the yearly file.
Read-only: it changes nothing.
"""
import argparse
import gzip
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from finlit_technicals import NseHistory, SectorEngine  # noqa: E402
from finlit_technicals.peers import norm_symbol  # noqa: E402

NAMES = {0: "EQ", 1: "BE", 2: "BZ", -1: "-"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--nse", default="/data/nse")
    ap.add_argument("--days", type=int, default=8, help="sessions to print (the median always uses 65)")
    a = ap.parse_args()
    src = NseHistory(Path(a.nse))
    p = src.panel
    eng = SectorEngine(src)
    eng._build()
    last_year = sorted(Path(a.nse).glob("bhav_[0-9][0-9][0-9][0-9].csv.gz"))[-1]
    raw = pd.read_csv(gzip.open(last_year, "rt"), dtype={"symbol": str, "series": str})
    raw["symbol"] = raw["symbol"].str.strip()
    raw["series"] = raw["series"].str.strip()
    for s in a.symbols:
        key = norm_symbol(s)
        if key not in p.keys:
            print(f"{s}: not in the panel (no row in any bhavcopy under this symbol)")
            continue
        j = list(p.keys).index(key)
        val = np.nan_to_num(np.asarray(p.value[:, j], dtype=float)) / 1e7
        traded = ~np.isnan(np.asarray(p.close[:, j], dtype=float))
        med65 = float(np.median(np.where(traded, val, 0.0)[-65:]))
        print(f"\n{s}: median traded value over the last 65 sessions = Rs {med65:.2f} crore (join 2.00, stay 1.00); traded on {int(traded[-65:].sum())} of 65")
        mem = eng.member[:, j]
        flips = [t for t in range(1, len(mem)) if mem[t] != mem[t - 1]]
        med = pd.Series(np.where(traded, val, 0.0)).rolling(65, min_periods=65).median()
        print("  counted-in-the-universe changes (a stock joins at a monthly review at Rs 2 crore or more and stays down to Rs 1 crore):")
        print(f"    on {pd.Timestamp(p.dates[0]):%Y-%m-%d}: {'counted' if mem[0] else 'not counted'}")
        for t in flips[-12:]:
            print(f"    {pd.Timestamp(p.dates[t]):%Y-%m-%d}: {'joined' if mem[t] else 'left'} (65-session median the session before: Rs {med.iloc[t - 1]:.2f} crore)")
        print(f"  {'date':<11}{'panel series':<14}{'panel value Cr':>15}   {'file series':<12}{'file value Cr':>14}")
        for t in range(len(p.dates) - a.days, len(p.dates)):
            d = pd.Timestamp(p.dates[t]).strftime("%Y-%m-%d")
            r = raw[(raw["symbol"] == s) & (raw["date"].str[:10] == d)]
            fs = ",".join(r["series"]) or "-"
            fv = ",".join(f"{v / 1e7:.2f}" for v in r["value"]) or "-"
            print(f"  {d:<11}{NAMES.get(int(p.series[t, j]), '?'):<14}{val[t]:>15.2f}   {fs:<12}{fv:>14}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
