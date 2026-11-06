"""The staged nightly job (panel written year by year and memory-mapped, universe in blocks, scoring in separate processes) gives the SAME answers as the
single-process v2.4.1 code: the panel arrays are equal bit for bit, and every file the job releases is equal byte for byte.

The reference is a frozen copy of the v2.4.1 modules (tests/reference_v201/); the data is a seeded synthetic NSE folder (big_fixture.py),
small here and 2,800 stocks / 10 years in the measurements of docs/SECTORS.md (tests/measure_job.py runs the same comparison at that size, with the memory table).
"""
import gzip
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))
import big_fixture  # noqa: E402
import nse_fixture  # noqa: E402
from reference_v201 import ref_batch, ref_nse, ref_sectors, ref_universe  # noqa: E402

from finlit_technicals import NseHistory, SectorEngine, nse, staged  # noqa: E402
from finlit_technicals import universe as U  # noqa: E402

ARRAYS = nse.PANEL_ARRAYS


def small_market(tmp_path, stocks=130, start="2025-01-01", end="2026-10-30", seed=11):
    big_fixture.write_big_folder(tmp_path / "nse", stocks, start, end, seed, log=lambda *_: None, liq_mean=18.5, cap_median=30000.0)   # most stocks pass the universe rules
    return tmp_path / "nse"


def same_array(a, b):
    return a.dtype == b.dtype and a.shape == b.shape and np.array_equal(a, b, equal_nan=a.dtype.kind == "f")


def assert_same_panel(new, ref):
    assert new.keys == ref.keys and new.dates.equals(ref.dates) and new.dates.dtype == ref.dates.dtype
    for name in ARRAYS:
        assert same_array(getattr(new, name), getattr(ref, name)), name
    assert new.isin == ref.isin and list(new.isin) == list(ref.isin) and new.links == ref.links
    assert new.report == ref.report and list(new.report) == list(ref.report)


def tree_differences(a: Path, b: Path) -> list:
    """Files that differ byte for byte (_summary.json: everything but the clock-dependent generated / seconds)."""
    fa = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    diff = [] if fa == fb else [f"file lists differ: {sorted(set(fa) ^ set(fb))[:5]}"]
    for f in fa:
        if f not in fb:
            continue
        if f == "_summary.json":
            x, y = json.loads((a / f).read_text()), json.loads((b / f).read_text())
            for d in (x, y):
                d["meta"].pop("generated")
                d["meta"].pop("seconds")
            if json.dumps(x) != json.dumps(y):
                diff.append(f)
        elif (a / f).read_bytes() != (b / f).read_bytes():
            diff.append(f)
    return diff


# ─── the panel ────────────────────────────────────────────────────────────────────────────────────────────────────
def test_panel_files_equal_the_in_memory_panel_bit_for_bit(tmp_path):
    for k, d in enumerate((nse_fixture.write_folder(tmp_path / "a"), small_market(tmp_path / "b"))):
        new = NseHistory(d).panel
        assert isinstance(new.close, np.memmap) and not new.close.flags.writeable          # read from the cache folder, nothing held in memory
        assert all(getattr(new, n).flags.f_contiguous for n in ARRAYS)                       # one stock after the other: a stock's history is one piece of the file
        assert_same_panel(new, ref_nse.NseHistory(d, cache=False).panel)
        assert new.report["not_matched"] >= 0 and (k == 0 or new.links)                     # the market has ISIN-linked renames to link


def test_panel_blocks_of_any_size_give_the_same_numbers(tmp_path):
    d = small_market(tmp_path)
    src = NseHistory(d)
    ref = ref_nse.NseHistory(d, cache=False).panel
    for block in (1, 7, 64):
        dest = tmp_path / f"blocks{block}"
        meta = nse.build_panel_files(d, nse.load_actions(*src.actions_files), src.changes, dest, block=block)
        assert_same_panel(nse.open_panel(dest, meta), ref)


def test_the_adjusted_close_of_a_column_is_the_adjusted_close_of_the_matrix(tmp_path):
    p = NseHistory(small_market(tmp_path)).panel
    full = p.adj
    for j in (0, 5, len(p.keys) - 1):
        assert same_array(p.adj_col(j), full[:, j])
        for t in (-1, 0, 100):
            a, b = p.adj_at(t, j), full[t, j]
            assert a == b or (np.isnan(a) and np.isnan(b))


def test_the_cache_is_reused_and_a_stale_or_partial_cache_is_rebuilt(tmp_path):
    d = small_market(tmp_path)
    cache = d / ".finlit_cache" / "panel"
    first = NseHistory(d).panel
    assert (cache / "meta.pkl").exists() and not list((d / ".finlit_cache").glob("panel-building-*")) and not (cache / "close64.tmp.npy").exists()
    calls = []
    real = nse.build_panel_files
    nse.build_panel_files = lambda *a, **k: calls.append(1) or real(*a, **k)          # counts the rebuilds
    try:
        _cache_checks(d, cache, first, calls)
    finally:
        nse.build_panel_files = real


def _cache_checks(d, cache, first, calls):
    assert_same_panel(NseHistory(d).panel, first)
    assert calls == []                                                          # current cache: opened, not rebuilt
    f = d / "bhav_2026.csv.gz"                                                  # NSE's newest file changed (size and time): stale
    f.write_bytes(f.read_bytes() + b"")
    import os
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 5))
    assert_same_panel(NseHistory(d).panel, first)
    assert calls == [1]
    (cache / "meta.pkl").unlink()                                               # a build that never finished: no meta file
    assert_same_panel(NseHistory(d).panel, first)
    assert calls == [1, 1]
    with open(cache / "cum.npy", "r+b") as fh:                                  # a file cut short
        fh.truncate(200)
    assert_same_panel(NseHistory(d).panel, first)
    assert calls == [1, 1, 1]
    (d / ".finlit_cache" / "panel-building-99").mkdir()                          # left by a killed run
    (cache / "meta.pkl").unlink()
    NseHistory(d).panel
    assert not (d / ".finlit_cache" / "panel-building-99").exists()
    legacy = d / ".finlit_cache" / "panel.pkl"
    legacy.write_bytes(b"old")
    (cache / "meta.pkl").unlink()
    NseHistory(d).panel
    assert not legacy.exists()                                                  # the cache of earlier versions is removed once the new one is built


def test_a_cache_folder_that_cannot_be_written_falls_back_to_building_in_memory(tmp_path):
    d = small_market(tmp_path)
    (d / ".finlit_cache").write_text("a file where the folder should be")
    p = NseHistory(d).panel
    assert not isinstance(p.close, np.memmap)
    assert_same_panel(p, ref_nse.NseHistory(d, cache=False).panel)


def test_yearly_files_that_overlap_in_dates_fall_back_to_building_in_memory(tmp_path):
    d = small_market(tmp_path, stocks=60, start="2025-01-01", end="2026-06-30")
    with gzip.open(d / "bhav_2025.csv.gz", "rt") as fh:
        y25 = pd.read_csv(fh, dtype=str)
    with gzip.open(d / "bhav_2026.csv.gz", "rt") as fh:
        y26 = pd.read_csv(fh, dtype=str)
    extra = y25[y25["date"] >= "2025-12-20"]                                    # the end of 2025 repeated inside the 2026 file
    with gzip.open(d / "bhav_2026.csv.gz", "wt", newline="") as fh:
        pd.concat([extra, y26]).to_csv(fh, index=False)
    p = NseHistory(d).panel
    assert not isinstance(p.close, np.memmap)
    assert_same_panel(p, ref_nse.NseHistory(d, cache=False).panel)


# ─── the universe ─────────────────────────────────────────────────────────────────────────────────────────────────
def test_the_universe_is_the_same_for_any_block_and_when_lean(tmp_path):
    d = small_market(tmp_path)
    src = NseHistory(d)
    full = SectorEngine(src)
    full._build()
    p, caps = full.panel, full.universe.inputs["caps"]
    ref = ref_universe.build_universe(ref_nse.NseHistory(d, cache=False).panel, full.rules, caps, full.universe.inputs["mscale"])
    assert np.array_equal(ref.member, full.universe.member)
    for k, v in ref.inputs.items():
        assert same_array(v, full.universe.inputs[k]), k
    for block in (7, 64):
        u = U.build_universe(p, full.rules, caps, full.universe.inputs["mscale"], block=block)
        assert np.array_equal(u.member, ref.member)
        for k, v in ref.inputs.items():
            assert same_array(v, u.inputs[k]), (block, k)
    lean = SectorEngine(src, lean=True)
    lean._build()
    assert np.array_equal(lean.member, full.member)
    for k, v in ref.inputs.items():
        w = lean.universe.inputs[k]
        if k in ("vscale", "mscale"):
            assert same_array(v, w)
        else:
            assert same_array(v[-1], w.row), k
    cols = np.flatnonzero(~full.member[-1])[:40]
    for j in cols:                                                                 # the reasons a stock is left out are the same
        assert U.why_not(lean.universe, int(j)) == ref_universe.why_not(ref, int(j))
    assert json.dumps(lean.universe_summary()) == json.dumps(full.universe_summary())


# ─── the whole job ────────────────────────────────────────────────────────────────────────────────────────────────
def run_reference(nse_folder: Path, out: Path) -> list:
    """The v2.4.1 single process (the frozen reference)."""
    src = ref_nse.NseHistory(nse_folder, cache=False)
    eng = ref_sectors.SectorEngine(src)
    return ref_batch.run(ref_batch.nse_symbols(eng), src, out, engine=eng)


def test_the_staged_job_releases_the_same_files_byte_for_byte(tmp_path):
    d = small_market(tmp_path, stocks=170, start="2024-03-01")
    old = tmp_path / "old"
    ref_summary = run_reference(d, old)
    new = tmp_path / "new"
    done = []
    summary = staged.run_staged(d, new, progress=lambda i, n, s: done.append((i, n)), parts=3)
    board = json.loads((new / "sectors" / "_board.json").read_text())
    assert board["rows"] and board["too_few_stocks"] and len(summary) > 100                  # a board with readings, and groups with too few stocks
    assert tree_differences(old, new) == []
    assert json.dumps(summary) == json.dumps(ref_summary)
    assert done[-1] == (len(summary), len(summary)) and [i for i, _ in done] == list(range(1, len(summary) + 1))
    assert not list(tmp_path.glob("new.work"))                                              # the work folder is removed


def test_parts_of_any_count_and_a_symbol_list_give_the_same_files(tmp_path):
    d = small_market(tmp_path, stocks=90, start="2025-01-01")
    src = ref_nse.NseHistory(d, cache=False)
    eng = ref_sectors.SectorEngine(src)
    syms = ref_batch.nse_symbols(eng)[::3]
    old = tmp_path / "old"
    ref_batch.run(syms, src, old, engine=eng)
    for parts in (1, 5):
        new = tmp_path / f"new{parts}"
        staged.run_staged(d, new, syms, parts=parts)
        assert tree_differences(old, new) == [], parts


def test_a_stage_that_fails_stops_the_run_and_says_which(tmp_path):
    import pytest
    with pytest.raises(RuntimeError, match="'panel' step ended with code"):
        staged.run_staged(tmp_path / "no-such-folder", tmp_path / "out")
    assert not (tmp_path / "out.work").exists()


def test_a_stopped_run_continues_with_its_finished_parts_and_gives_the_same_files(tmp_path):
    """The server's job limit stops a long build part-way (5 Nov 2026: about 2.5 hours against 90 minutes). With resume=True the next call keeps the plan
    and the finished score parts and runs only the rest; the released files are still byte for byte those of the single-process run."""
    import pytest
    d = small_market(tmp_path, stocks=120, start="2024-06-01")
    old = tmp_path / "old"
    run_reference(d, old)
    new = tmp_path / "new"
    real = staged._stage
    calls = []
    stop = [True]

    def stopping(stage, args, *a, **k):
        calls.append((stage, args[args.index("--part") + 1] if "--part" in args else None))
        if stop[0] and calls[-1] == ("score", "1"):
            stop[0] = False
            raise RuntimeError("stopped by the time limit")
        return real(stage, args, *a, **k)
    staged._stage = stopping
    try:
        with pytest.raises(RuntimeError, match="time limit"):
            staged.run_staged(d, new, parts=3, resume=True)
        assert (tmp_path / "new.work" / "part-0.pkl").is_file()                  # the finished part is kept
        calls.clear()
        done = []
        staged.run_staged(d, new, parts=3, resume=True, progress=lambda i, n, s: done.append(i))
    finally:
        staged._stage = real
    assert ("prepare", None) not in calls and ("score", "0") not in calls and ("score", "1") in calls and ("score", "2") in calls
    assert tree_differences(old, new) == []
    assert done and not (tmp_path / "new.work").exists()        # the work folder goes once the set is whole


def test_a_kept_work_folder_is_not_reused_for_another_stock_list_or_part_count(tmp_path):
    d = small_market(tmp_path, stocks=60, start="2025-03-01")
    new = tmp_path / "new"
    work = tmp_path / "new.work"
    work.mkdir()
    (work / "key.json").write_text(json.dumps({"symbols": None, "parts": 9}))
    (work / "plan.json").write_text(json.dumps({"symbols": ["NOPE"], "parts": [[0]]}))
    (work / "part-0.pkl").write_bytes(b"not a part")
    summary = staged.run_staged(d, new, parts=2, resume=True)
    assert len(summary) > 10 and all(s.get("symbol") != "NOPE" for s in summary)
