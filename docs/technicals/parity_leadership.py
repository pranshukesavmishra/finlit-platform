"""Parity check: our Leader / In line / Laggard engine (backend/finlit/leadership.py, pure functions) against finlit_technicals v1.1 (peers.py) on the SAME prices.

    python3 docs/technicals/parity_leadership.py /path/to/finlit_technicals_repo_root                  (prints the comparison)
    python3 docs/technicals/parity_leadership.py /path/to/finlit_technicals_repo_root --pins out.json   (writes backend/tests/fixtures/leadership_parity.json)

Needs numpy and pandas (the package does); not part of the test suite. The prices are made with plain `random` (the same generator is in
backend/tests/test_leadership.py, which compares our engine with the pinned package answers). A world is a stock, its peers, a sector index and a market
index, as weekly closes and weekly volumes. For the package the weeks are written as five flat daily bars each (same last close, same weekly volume), so both
engines read the same weekly figures. Compared for every weekly run of the last 60 weeks: how many are ranked, k, the stock's rank, the 12-month / 6-month /
3-month relative return, this week's label, the published label (the two-run stability rule) and the market 12-month figure.
"""
import json
import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(Path(sys.argv[1])))
sys.path.insert(0, str(ROOT / "backend"))

import pandas as pd  # noqa: E402
from finlit_technicals import peers as PR  # noqa: E402
from finlit import leadership as L  # noqa: E402

END = date(2026, 10, 23)   # a Friday
CODE = {1: "leader", 0: "in_line", -1: "laggard", None: None}

WORLDS = {
    "24 peers, sector index; one thin, one short, one stale": dict(n_peers=24, weeks=200, seed=1, thin=(3,), short=(5,), stale=(7,), midweek=(), sector=True, mcap=None),
    "24 peers, no sector index (peer average)": dict(n_peers=24, weeks=200, seed=1, thin=(3,), short=(5,), stale=(7,), midweek=(), sector=False, mcap=None),
    "9 peers, all rankable": dict(n_peers=9, weeks=160, seed=2, thin=(), short=(), stale=(), midweek=(), sector=True, mcap=None),
    "13 peers, one stops trading in the middle of the last week": dict(n_peers=13, weeks=160, seed=3, thin=(), short=(), stale=(), midweek=(4,), sector=True, mcap=None),
    "7 peers of which 3 are too new to rank until week 53 (too few until then)": dict(n_peers=7, weeks=140, seed=4, thin=(), short=(0, 1, 2), stale=(), midweek=(), sector=True, mcap=None),
}


def gauss(rnd):
    """A normal draw from two uniform ones (Box-Muller), so that only random.random() decides the numbers."""
    return math.sqrt(-2 * math.log(1 - rnd.random())) * math.cos(2 * math.pi * rnd.random())


def walk(rnd, weeks, drift, vol, p0):
    price, out = p0, []
    for _ in range(weeks):
        price *= math.exp(drift + vol * (sum(rnd.random() for _ in range(12)) - 6))
        out.append(price)
    return out


def pure_world(n_peers, weeks, seed, thin, short, stale, midweek, sector, mcap):
    """{symbol: (dates, closes, volumes)} of weekly bars (the date is the week's last trading day), plus the sector and the market index."""
    rnd = random.Random(seed)
    fridays = [END - timedelta(days=7 * (weeks - 1 - i)) for i in range(weeks)]
    world = {}
    for k, sym in enumerate(["STK"] + [f"P{i}" for i in range(n_peers)]):
        drift = 0.0030 if sym == "STK" else 0.0012 + 0.0015 * gauss(rnd)
        closes = walk(rnd, weeks, drift, 0.03 + 0.01 * (k % 3), 100.0)
        vols = [math.exp(13.5 + 0.4 * gauss(rnd)) for _ in range(weeks)]
        dates = list(fridays)
        if k and (k - 1) in thin:
            vols = [v * 0.0005 for v in vols]
        if k and (k - 1) in short:
            dates, closes, vols = dates[-70:], closes[-70:], vols[-70:]
        if k and (k - 1) in stale:
            dates, closes, vols = dates[:-2], closes[:-2], vols[:-2]
        if k and (k - 1) in midweek:
            dates = dates[:-1] + [dates[-1] - timedelta(days=2)]       # the last bar is the Wednesday of the last week
        world[sym] = (dates, closes, vols)
    world["SECTOR"] = (fridays, walk(rnd, weeks, 0.0012, 0.015, 1000.0), [0.0] * weeks)
    world["MARKET"] = (fridays, walk(rnd, weeks, 0.0010, 0.012, 20000.0), [0.0] * weeks)
    return world


def daily_frame(dates, closes, vols):
    """Five flat daily bars per weekly bar (a bar dated mid-week gets the days up to it), with the weekly volume split evenly."""
    rows = []
    for d, c, v in zip(dates, closes, vols):
        monday = d - timedelta(days=d.weekday())
        days = [monday + timedelta(days=i) for i in range(d.weekday() + 1)]
        rows += [(x, c, c, c, c, v / len(days)) for x in days]
    f = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close", "volume"]).set_index("date")
    f.index = pd.DatetimeIndex(f.index)
    return f


def package_runs(world, sector):
    syms = ["STK"] + [s for s in world if s not in ("STK", "SECTOR", "MARKET")]
    grp = PR.Group(0, ",".join(syms[1:]), "test", "NSE:SEC" if sector else "", "Test index" if sector else "peer average", "", "", ["NSE:" + s for s in syms])
    daily = {"NSE:" + s: daily_frame(*world[s]) for s in syms[1:]}
    return PR.compute(daily_frame(*world["STK"]), daily, grp, PR.PeerParams(), sector_daily=daily_frame(*world["SECTOR"]) if sector else None,
                      market_daily={"NSE:CNX500": daily_frame(*world["MARKET"])})


def our_runs(world, sector, ref_weeks):
    members = [L.Member(sym=s, prices=L.Prices(d, c, v), liquid=L.liquid_enough(d, c, v)) for s, (d, c, v) in world.items() if s not in ("SECTOR", "MARKET")]
    sidx, midx = (L.Prices(*world["SECTOR"][:2]) if sector else None), L.Prices(*world["MARKET"][:2])
    pub, last_raw, out = None, None, []
    for ref in ref_weeks:
        t = ref + timedelta(days=4)
        g = L.label_group(members, t, sidx, midx)
        me = next((x for x in g.rows if x.sym == "STK"), None)
        if g.n >= L.MIN_PEERS and me is not None:
            mret = L.ret(midx, t, L.RANK_WEEKS)
            raw = me.label
            pub, _ = L.settle(pub, last_raw, raw)
            last_raw = raw
            out.append({"ranked": g.n, "k": g.k, "rank": me.rank, "rel52": me.rel52, "rel26": me.rel26, "rel13": me.rel13, "rel52Market": me.ret52 - mret if mret is not None else None,
                        "raw": raw, "pub": pub, "direction": me.direction})
        else:
            out.append(None)
    return out


def compare(name, kw):
    world = pure_world(**kw)
    res = package_runs(world, kw["sector"])
    ours = our_runs(world, kw["sector"], [r.ref_week.date() for r in res.runs])
    pins, diffs = [], {}
    # The package runs on the first bar of a NEW week and calls a peer stale when it has no bar in that new week (TradingView's weekly [1]). The run here is made
    # after Friday's close, so the same peer is current when it has its bar in the week just ended. The one week where a peer's last bar is the ref week is
    # that convention and is not compared.
    edge = {(max(world[f"P{i}"][0]) - timedelta(days=max(world[f"P{i}"][0]).weekday())) for i in kw["stale"]}
    for r, o in list(zip(res.runs, ours))[-60:]:
        if r.ref_week.date() in edge:
            continue
        row = {"week": r.ref_week.date().isoformat(), "state": r.state}
        if r.state == 0:
            row.update(ranked=r.ranked, k=r.k, rank=r.rank, rel52=round(r.rel52, 9), rel26=round(r.rel26, 9), rel13=round(r.rel13, 9),
                       rel52Market=None if math.isnan(r.rel52m) else round(r.rel52m, 9), raw=CODE[r.raw], pub=CODE[r.pub])
        pins.append(row)
        if r.state == 0:
            if o is None:
                diffs.setdefault("ours cannot rank", []).append(row["week"])
                continue
            for key in ("ranked", "k", "rank", "raw", "pub"):
                if row[key] != o[key]:
                    diffs.setdefault(key, []).append((row["week"], row[key], o[key]))
            for key in ("rel52", "rel26", "rel13", "rel52Market"):
                if (row[key] is None) != (o[key] is None) or (row[key] is not None and abs(row[key] - o[key]) > 1e-8):
                    diffs.setdefault(key, []).append((row["week"], row[key], o[key]))
        elif o is not None:
            diffs.setdefault(f"package state {r.state}, ours ranks", []).append(row["week"])
    return pins, diffs, res


if __name__ == "__main__":
    out = {"_source": "finlit_technicals v1.1 (peers.compute) on the worlds of pure_world() in docs/technicals/parity_leadership.py; regenerate with --pins <file>"}
    for name, kw in WORLDS.items():
        pins, diffs, res = compare(name, kw)
        comparable = sum(1 for p in pins if p["state"] == 0)
        print(f"{name}: {comparable} comparable weekly runs of {len(pins)}; differences: " + (", ".join(f"{k} x{len(v)}" for k, v in diffs.items()) or "none"))
        for k, v in diffs.items():
            print("    ", k, v[:3])
        out[name] = {"params": kw, "runs": pins}
    if "--pins" in sys.argv:
        Path(sys.argv[sys.argv.index("--pins") + 1]).write_text(json.dumps(out, indent=0, sort_keys=True) + "\n")
