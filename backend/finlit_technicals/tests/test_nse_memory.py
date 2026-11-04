"""FinLit memory patches to nse.py (FINLIT_PATCHES.md): same answers as the original code, far less memory."""
import numpy as np
import pandas as pd

from finlit_technicals import nse


def original_drop_repeated_days(b, share=0.95):
    """The v2.0.1 code, verbatim."""
    eq = b[b["series"] == "EQ"]
    sig = {d: set(map(tuple, g[["symbol", "open", "high", "low", "close", "volume"]].round(4).to_numpy().tolist()))
           for d, g in eq.groupby("date")}
    drop, prev = [], None
    for d in sorted(sig):
        cur = sig[d]
        if prev is not None and len(cur) >= share * len(prev) and len(cur & prev) >= share * len(cur):
            drop.append(d)
            continue
        prev = cur
    return b[~b["date"].isin(drop)].reset_index(drop=True), drop


def make(n_days=60, n_stocks=80, seed=5, repeat_days=(10, 11, 40), nan_rows=True):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=n_days)
    frames, prev = [], None
    for t, d in enumerate(dates):
        if t in repeat_days and prev is not None:
            f = prev.copy()
            f["date"] = d
        else:
            c = 100 + rng.normal(0, 3, n_stocks).round(2)
            f = pd.DataFrame({"date": d, "symbol": [f"S{i}" for i in range(n_stocks)], "series": ["EQ" if i % 7 else "BE" for i in range(n_stocks)],
                              "isin": [f"INE{i:05d}01010" for i in range(n_stocks)], "open": c, "high": c + 1, "low": c - 1, "close": c,
                              "volume": rng.integers(1000, 9000, n_stocks).astype(float), "value": c * 1000, "trades": 10})
        prev = f
        frames.append(f)
    b = pd.concat(frames, ignore_index=True)
    if nan_rows:
        b.loc[b.index[::97], "close"] = np.nan
    return b


def test_drop_repeated_days_drops_exactly_the_days_the_original_drops():
    for kw in ({}, {"repeat_days": ()}, {"repeat_days": (1, 2, 3, 4)}, {"nan_rows": False}, {"seed": 9, "n_stocks": 30}):
        b = make(**kw)
        new, dropped = nse.drop_repeated_days(b)
        old, was = original_drop_repeated_days(b)
        assert [pd.Timestamp(x) for x in dropped] == [pd.Timestamp(x) for x in was], kw
        pd.testing.assert_frame_equal(new, old)


def test_the_dropped_days_are_the_copied_ones():
    b = make(repeat_days=(10, 11, 40), nan_rows=False)
    _, dropped = nse.drop_repeated_days(b)
    days = pd.bdate_range("2024-01-01", periods=60)
    assert [pd.Timestamp(x) for x in dropped] == [days[10], days[11], days[40]]


def test_load_bhav_gives_the_same_values_with_shared_strings(tmp_path):
    from nse_fixture import write_folder
    write_folder(tmp_path)
    b = nse.load_bhav(tmp_path)
    assert b["symbol"].dtype == object and b["series"].isin(nse.MAIN).all() and not b["symbol"].str.startswith(" ").any()
    ids = {id(x) for x in b["symbol"].to_numpy()}
    assert len(ids) == b["symbol"].nunique()          # one string object per symbol, not one per row


def test_drop_repeated_days_one_file_at_a_time_drops_the_same_days_and_keeps_the_same_rows():
    """The panel is built a yearly file at a time (nse.build_panel_files): the rule fed in pieces must give what it gives on the whole."""
    for kw in ({}, {"repeat_days": (1, 2, 3, 4)}, {"nan_rows": True, "seed": 9, "n_stocks": 30}):
        b = make(**kw)
        whole, dropped = nse.drop_repeated_days(b)
        for cut in ([20], [11, 12, 41], [1, 2, 3, 4, 5]):                    # cuts that fall right after, on and before the repeated days
            days = sorted(b["date"].unique())
            edges = [days[0]] + [days[c] for c in cut] + [days[-1] + pd.Timedelta(days=1)]
            dropper, kept = nse._DayDropper(), []
            for lo, hi in zip(edges[:-1], edges[1:]):
                part = b[(b["date"] >= lo) & (b["date"] < hi)]
                gone = dropper.feed(part)
                kept.append(part[~part["date"].isin(gone)])
            assert [pd.Timestamp(x) for x in dropper.drop] == [pd.Timestamp(x) for x in dropped], (kw, cut)
            pd.testing.assert_frame_equal(pd.concat(kept, ignore_index=True), whole)
