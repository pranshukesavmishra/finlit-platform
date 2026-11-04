"""The nightly batch in stages, each stage in its own process, so no process holds the whole run in memory (docs/SECTORS.md, "Memory and time").

    run_staged(nse_folder, out_folder, symbols, progress)  ->  the same summary list as batch.run(...), and the same files in out_folder

    panel    read the yearly bhavcopy files one at a time and write the market panel as .npy files into <nse>/.finlit_cache/panel (skipped when they are current)
    prepare  open the panel (memory-mapped), build the universe month by month for the WHOLE market, choose the stocks and split them into parts by industry group
    score    once per part: the same per-stock work as batch.run (score, peer label, the stock inside its industry), for the part's stocks only. Each part builds
             the whole-market universe itself, so every stock is judged against the full market whichever part it is in; the parts run one after the other
    merge    the stages that need every group and every stock's peer label: the board (counts, ordering, "too few stocks" lists), the industry pages, _summary.json

Nothing is approximated: every stage calls the functions batch.run calls, on the same inputs, and the files written are byte for byte those of batch.run
(finlit_technicals/tests/test_staged_equals_single_run.py proves it against a frozen copy of the v2.0.1 code). A stage that dies (killed for memory, say)
makes run_staged raise with the stage's last lines; the caller (finlit/sector_job.py) then keeps the previous release serving.

Run a stage by hand:  python -m finlit_technicals.staged score --nse NSE --work WORK --out OUT --part 0
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import resource
import shutil
import subprocess  # nosec B404 - runs this package's own stages with a fixed argument list
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

PROGRESS = "@@PROGRESS"
PEAK = "@@PEAK"
DEFAULT_PARTS = 4
RELEASE_EVERY = 4          # stocks between giving back the memory-mapped pages of the panel


def peak_mb() -> float:
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)       # kilobytes on Linux


# ------------------------------------------------------------------------------------------------ the stages (each runs in its own process)
def _open(nse: str):
    from . import NseHistory, SectorEngine
    src = NseHistory(Path(nse))
    return src, SectorEngine(src, lean=True)


def stage_panel(nse: str) -> None:
    from . import NseHistory
    p = NseHistory(Path(nse), cache=True).panel
    print(f"panel: {len(p.dates)} days x {len(p.keys)} stocks", flush=True)


def stage_prepare(nse: str, work: str, parts: int, symbols_file: Optional[str]) -> None:
    from .batch import nse_symbols
    _, eng = _open(nse)
    syms = json.loads(Path(symbols_file).read_text()) if symbols_file else nse_symbols(eng)
    group: List[Optional[str]] = []
    for s in syms:
        try:
            group.append(eng.home(s)[0])
        except LookupError:
            group.append(None)
    size: Dict[str, int] = {}
    for g in group:
        if g is not None:
            size[g] = size.get(g, 0) + 1
    n_parts = max(1, min(int(parts), len(syms)))
    load = [0] * n_parts
    where: Dict[str, int] = {}
    for g in sorted(size, key=lambda x: (-size[x], x)):          # whole industry groups, biggest first, into the lightest part
        k = min(range(n_parts), key=lambda i: (load[i], i))
        where[g] = k
        load[k] += size[g]
    out: List[List[int]] = [[] for _ in range(n_parts)]
    for i, g in enumerate(group):
        k = where[g] if g is not None else min(range(n_parts), key=lambda i2: (load[i2], i2))
        if g is None:
            load[k] += 1
        out[k].append(i)
    Path(work, "plan.json").write_text(json.dumps({"symbols": syms, "parts": out}))
    print(f"prepare: {len(syms)} stocks in {n_parts} parts {[len(x) for x in out]}; {len(eng.groups)} groups", flush=True)


def stage_score(nse: str, work: str, out: str, part: int) -> None:
    from .batch import amfi_caps, score_stocks
    from .sources import Cached
    plan = json.loads(Path(work, "plan.json").read_text())
    idx = plan["parts"][part]
    src, eng = _open(nse)
    cached = Cached(src)
    caps = amfi_caps(eng)           # the whole market's sizes: the peers of a stock are in other parts too
    syms = [plan["symbols"][i] for i in idx]
    p = eng.source.panel
    seen = [0]

    def progress(i: int, n: int, sym: str) -> None:
        print(f"{PROGRESS} {i} {n} {sym}", flush=True)
        seen[0] += 1
        if seen[0] % RELEASE_EVERY == 0:
            p.release_pages()
    lines, labels, homes = score_stocks(syms, cached, eng, Path(out), caps=caps, progress=progress)
    with open(Path(work, f"part-{part}.pkl.tmp"), "wb") as fh:
        pickle.dump({"lines": list(zip(idx, lines)), "labels": labels, "homes": homes, "groups": eng._res}, fh, protocol=4)
    os.replace(Path(work, f"part-{part}.pkl.tmp"), Path(work, f"part-{part}.pkl"))
    print(f"score: part {part}: {len(lines)} stocks, {len(eng._res)} groups", flush=True)


def stage_merge(nse: str, work: str, out: str, t0: float) -> None:
    from .batch import write_sector_files, write_summary
    plan = json.loads(Path(work, "plan.json").read_text())
    _, eng = _open(nse)
    lines: List[Any] = [None] * len(plan["symbols"])
    labels: Dict[str, str] = {}
    homes: Dict[str, tuple] = {}
    for k in range(len(plan["parts"])):
        with open(Path(work, f"part-{k}.pkl"), "rb") as fh:
            part = pickle.load(fh)           # nosec B301 - written a few minutes ago by this package's own score stage
        for i, line in part["lines"]:
            lines[i] = line
        labels.update(part["labels"])
        homes.update(part["homes"])
        eng._res.update(part["groups"])      # the groups the parts already worked out; any other is worked out here
    missing = [i for i, x in enumerate(lines) if x is None]
    if missing:
        raise RuntimeError(f"{len(missing)} stocks have no result (for example {plan['symbols'][missing[0]]})")
    out_p = Path(out)
    write_sector_files(eng, out_p, labels, homes)
    write_summary(out_p, lines, t0)
    Path(work, "summary.pkl").write_bytes(pickle.dumps(lines, protocol=4))
    print(f"merge: board and {len(eng._res)} industry pages written", flush=True)


# ------------------------------------------------------------------------------------------------ the runner (in the job process)
def _stage(stage: str, args: List[str], on_progress: Optional[Callable[[int, int, str], None]] = None, say: Callable[[str], None] = print) -> tuple:
    """Runs one stage in a child process. Returns (the child's peak memory in MB, seconds). Raises RuntimeError when it fails."""
    started = time.time()
    root = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": root + (os.pathsep + os.environ["PYTHONPATH"] if os.environ.get("PYTHONPATH") else ""), "PYTHONUNBUFFERED": "1"}
    cmd = [sys.executable, "-u", "-m", "finlit_technicals.staged", stage, *args]
    proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)   # nosec B603 - the job runs in its own process group, so the supervisor's kill reaches a stage too
    tail: deque = deque(maxlen=25)
    peak = 0.0
    try:
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip()
            if line.startswith(PROGRESS):
                _, i, n, sym = line.split(" ", 3)
                if on_progress:
                    on_progress(int(i), int(n), sym)
            elif line.startswith(PEAK):
                peak = float(line.split()[1])
            elif line:
                tail.append(line)
                say(line[:200])
        code = proc.wait()
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    if code != 0:
        why = "was killed (most likely out of memory)" if code in (-9, 137) else f"ended with code {code}"
        raise RuntimeError(f"the '{stage}' step {why}: " + " | ".join(list(tail)[-4:]))
    return peak, round(time.time() - started)


def run_staged(nse: str | Path, out: str | Path, symbols: Optional[List[str]] = None,
               progress: Optional[Callable[[int, int, str], None]] = None, parts: Optional[int] = None) -> List[Dict[str, Any]]:
    """The batch over NSE's files, in stages (see the module docstring). Same arguments and result as default_batch in finlit/sector_job.py."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.name}.work"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    n_parts = int(parts or os.environ.get("SECTOR_PARTS") or DEFAULT_PARTS)
    t0 = time.time()
    peaks: Dict[str, float] = {}
    secs: Dict[str, int] = {}
    try:
        sym_args: List[str] = []
        if symbols:
            (work / "symbols.json").write_text(json.dumps(list(symbols)))
            sym_args = ["--symbols-file", str(work / "symbols.json")]
        common = ["--nse", str(nse), "--work", str(work), "--out", str(out)]
        peaks["panel"], secs["panel"] = _stage("panel", ["--nse", str(nse)])
        peaks["prepare"], secs["prepare"] = _stage("prepare", [*common, "--parts", str(n_parts), *sym_args])
        plan = json.loads((work / "plan.json").read_text())
        total, done = len(plan["symbols"]), 0
        for k, idx in enumerate(plan["parts"]):
            base = done

            def relay(i: int, n: int, sym: str, base: int = base) -> None:
                if progress:
                    progress(base + i, total, sym)
            peaks[f"score{k}"], secs[f"score{k}"] = _stage("score", [*common, "--part", str(k)], relay)
            done += len(idx)
        peaks["merge"], secs["merge"] = _stage("merge", [*common, "--t0", repr(t0)])
        summary = pickle.loads((work / "summary.pkl").read_bytes())      # nosec B301 - written by the merge stage just now
        print("stages: peak memory MB " + ", ".join(f"{k} {v:g}" for k, v in peaks.items()), flush=True)
        print("stages: seconds " + ", ".join(f"{k} {v}" for k, v in secs.items()), flush=True)
        return summary
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m finlit_technicals.staged")
    ap.add_argument("stage", choices=["panel", "prepare", "score", "merge"])
    ap.add_argument("--nse", required=True)
    ap.add_argument("--work")
    ap.add_argument("--out")
    ap.add_argument("--part", type=int, default=0)
    ap.add_argument("--parts", type=int, default=DEFAULT_PARTS)
    ap.add_argument("--symbols-file")
    ap.add_argument("--t0", type=float, default=time.time())
    a = ap.parse_args(argv)
    if a.stage == "panel":
        stage_panel(a.nse)
    elif a.stage == "prepare":
        stage_prepare(a.nse, a.work, a.parts, a.symbols_file)
    elif a.stage == "score":
        stage_score(a.nse, a.work, a.out, a.part)
    else:
        stage_merge(a.nse, a.work, a.out, a.t0)
    print(f"{PEAK} {peak_mb()}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
