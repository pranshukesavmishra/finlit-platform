"""Measure the nightly sector job (memory, time) and prove two versions of the code release the same files. Used for the numbers in docs/SECTORS.md, section 8.

    python big_fixture.py /data/nse_big                                              # the folder of the real size (2,800 stocks, 2016 - Oct 2026, 5.7 million rows)
    python measure_job.py run     --tree OLD/backend --nse /data/nse_big --out /data/out_old --json old.json
    python measure_job.py run     --tree NEW/backend --nse /data/nse_big --out /data/out_new --json new.json
    python measure_job.py compare /data/out_old /data/out_new
    python measure_job.py table   old.json new.json

`run` starts `finlit.sector_job.default_batch` of the code tree in a fresh Python process (exactly what the nightly job calls) and samples /proc every 0.25 s
for the whole tree of processes it starts: the largest resident memory of any ONE process (what the container limit has to hold, besides the website), the
largest total of the tree, and how much of that is anonymous memory (the rest is file pages: shared libraries and the memory-mapped panel, which the kernel can
drop at any time). `compare` is the byte-for-byte check: _summary.json is compared without its clock fields (generated, seconds); a file that differs is then
loaded and compared value by value (strings and ints exactly, floats exactly), and every difference is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

CHILD = r'''
import sys, time, json, resource
sys.path.insert(0, {tree!r})
from pathlib import Path
from finlit import sector_job as sj
t = time.time()
syms = None
if {limit!r}:
    from finlit_technicals import NseHistory, SectorEngine
    from finlit_technicals.batch import nse_symbols
    e = SectorEngine(NseHistory(Path({nse!r}), cache=False)); syms = nse_symbols(e)[:{limit!r}]; del e
def prog(i, n, s):
    if i % 100 == 0 or i == n: print("batch", i, n, s, round(time.time() - t), flush=True)
res = sj.default_batch(Path({nse!r}), Path({out!r}), syms, prog)
print("DONE", len(res), round(time.time() - t), flush=True)
'''


def _status(pid: int) -> dict:
    d = {}
    try:
        for line in open(f"/proc/{pid}/status"):
            k, _, v = line.partition(":")
            if k in ("VmRSS", "VmHWM", "RssAnon", "RssFile"):
                d[k] = int(v.split()[0]) / 1024
    except OSError:
        pass
    return d


def _walk(pid: int) -> list:
    out = [pid]
    try:
        for c in open(f"/proc/{pid}/task/{pid}/children").read().split():
            out += _walk(int(c))
    except OSError:
        pass
    return out


def run(a) -> dict:
    out = Path(a.out)
    if out.exists():
        import shutil
        shutil.rmtree(out)
    code = CHILD.format(tree=a.tree, nse=a.nse, out=str(out), limit=a.limit)
    t0 = time.time()
    p = subprocess.Popen([sys.executable, "-u", "-c", code], cwd=a.tree, env={**os.environ, "PYTHONPATH": a.tree},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    peak = {"one_process_rss_mb": 0.0, "one_process_anon_mb": 0.0, "tree_rss_mb": 0.0, "tree_anon_mb": 0.0}
    stop = threading.Event()

    def sample() -> None:
        while not stop.is_set():
            rss = anon = 0.0
            for pid in _walk(p.pid):
                s = _status(pid)
                rss += s.get("VmRSS", 0)
                anon += s.get("RssAnon", 0)
                peak["one_process_rss_mb"] = max(peak["one_process_rss_mb"], s.get("VmRSS", 0), s.get("VmHWM", 0))
                peak["one_process_anon_mb"] = max(peak["one_process_anon_mb"], s.get("RssAnon", 0))
            peak["tree_rss_mb"] = max(peak["tree_rss_mb"], rss)
            peak["tree_anon_mb"] = max(peak["tree_anon_mb"], anon)
            time.sleep(0.25)
    th = threading.Thread(target=sample, daemon=True)
    th.start()
    log = []
    assert p.stdout is not None
    for line in p.stdout:
        print(line.rstrip(), flush=True)
        log.append(line.rstrip())
    p.wait()
    stop.set()
    th.join()
    res = {"tree": a.tree, "exit": p.returncode, "seconds": round(time.time() - t0), **{k: round(v, 1) for k, v in peak.items()},
           "stages": [x for x in log if x.startswith("stages:")]}
    print(json.dumps(res))
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1))
    return res


def _diff_values(x, y, path="") -> list:
    if type(x) is not type(y):
        return [f"{path}: {type(x).__name__} {x!r:.60} against {type(y).__name__} {y!r:.60}"]
    if isinstance(x, dict):
        d = [f"{path}: keys differ {sorted(set(x) ^ set(y))[:5]}"] if list(x) != list(y) else []
        for k in x:
            if k in y:
                d += _diff_values(x[k], y[k], f"{path}/{k}")
        return d
    if isinstance(x, list):
        d = [f"{path}: {len(x)} items against {len(y)}"] if len(x) != len(y) else []
        for i, (u, v) in enumerate(zip(x, y)):
            d += _diff_values(u, v, f"{path}[{i}]")
        return d
    return [] if x == y else [f"{path}: {x!r} against {y!r}"]


def compare(a: Path, b: Path) -> int:
    fa = sorted(p.relative_to(a).as_posix() for p in a.rglob("*") if p.is_file())
    fb = sorted(p.relative_to(b).as_posix() for p in b.rglob("*") if p.is_file())
    print(f"{len(fa)} files in {a}, {len(fb)} in {b}; same names: {fa == fb}")
    same = differ = 0
    detail = []
    for f in sorted(set(fa) & set(fb)):
        x, y = (a / f).read_bytes(), (b / f).read_bytes()
        if f == "_summary.json":
            jx, jy = json.loads(x), json.loads(y)
            for j in (jx, jy):
                j["meta"].pop("generated", None)
                j["meta"].pop("seconds", None)
            x, y = json.dumps(jx).encode(), json.dumps(jy).encode()
        if x == y:
            same += 1
        else:
            differ += 1
            detail.append((f, _diff_values(json.loads(x), json.loads(y))))
    print(f"byte for byte identical: {same}; different: {differ}")
    for f, d in detail[:20]:
        print(" ", f, "->", "identical after json load" if not d else f"{len(d)} value differences, first: {d[:3]}")
    return 0 if fa == fb and not differ else 1


def table(old: dict, new: dict) -> None:
    rows = [("Largest memory of any one process (MB)", "one_process_rss_mb"), ("  of which anonymous", "one_process_anon_mb"),
            ("Largest total of all processes at one moment (MB)", "tree_rss_mb"), ("  of which anonymous", "tree_anon_mb"), ("Time (seconds)", "seconds")]
    print(f"| {'':52} | before | after |\n|---|---|---|")
    for label, k in rows:
        print(f"| {label:52} | {old[k]:g} | {new[k]:g} |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--tree", required=True, help="the backend folder of the code to run (holds finlit/ and finlit_technicals/)")
    r.add_argument("--nse", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--limit", type=int, default=0, help="only the first N stocks")
    r.add_argument("--json")
    c = sub.add_parser("compare")
    c.add_argument("a")
    c.add_argument("b")
    t = sub.add_parser("table")
    t.add_argument("old")
    t.add_argument("new")
    a = ap.parse_args()
    if a.cmd == "run":
        return run(a)["exit"]
    if a.cmd == "compare":
        return compare(Path(a.a), Path(a.b))
    table(json.loads(Path(a.old).read_text()), json.loads(Path(a.new).read_text()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
