"""`refresh-sectors`: the nightly sector run (docs/SECTORS.md).

    1. fetch   (SECTOR_FETCH=1, default) bring the NSE data folder up to date with `python -m finlit_technicals fetch-nse`, in a child process with a time
               limit. NSE sometimes refuses data-centre servers: that is reported in plain words (run status, /api/sectors/status) and the run carries on
               with the files already in the folder. It never raises into the supervisor.
    2. build   run the finlit_technicals batch into a NEW folder, beside the live one. Nothing the website reads is touched.
    3. check   the new set must be complete (a board, the industry pages, stock files, few errors, not far fewer stocks than before).
    4. swap    rename it into place and repoint `current` in one atomic step (sector_data.publish). A failed or killed run leaves the last good set serving.
    5. record  the result goes to the job log, to Postgres (record_run, key run:refresh-sectors) and to last_run.json beside the data, which is what the
               pages read to say why they are blank.

A second way in, for a server that cannot hold the market panel in memory (docs/SECTORS.md, "Memory and time"): `refresh-sectors --import FOLDER` checks and swaps in
a batch output folder that was built elsewhere (the founder's PC, with `python -m finlit_technicals batch`), with the same checks and the same atomic swap.

Exit code (see worker.py): 0 when the new data is current or nothing newer exists; 1 when the run failed or the data is still older than the latest session
(the supervisor then retries after 30, 60, 120 minutes and tells the founder after three failures).

The heavy package (numpy, pandas) is imported only here, in the job process, never in the website process.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import sector_data as sd

log = logging.getLogger("finlit.sectors")
RUN_NAME = "refresh-sectors"
BACKEND_DIR = Path(__file__).resolve().parents[1]          # the folder that holds both finlit/ and finlit_technicals/
IST = timezone(timedelta(hours=5, minutes=30))
MAX_ERROR_SHARE = 0.05             # more stocks than this with an error in their own files: the set is not published
MIN_SHARE_OF_PREVIOUS = 0.8        # fewer stock files than this share of the live set: the set is not published
MIN_STOCK_FILES = 50
DEFAULT_FETCH_MIN = 40.0


# ------------------------------------------------------------------------------------------------ the NSE folder
def nse_files(nse: Path) -> List[Path]:
    out: List[Path] = []
    for pattern in ("bhav_*.csv.gz", "idx_*.csv.gz"):
        out += sorted(nse.glob(pattern))
    for sub in ("ref", "amfi"):
        d = nse / sub
        if d.is_dir():
            out += sorted(p for p in d.iterdir() if p.is_file())
    return out


def package_version() -> str:
    try:
        m = re.search(r'__version__\s*=\s*"([^"]+)"', (BACKEND_DIR / "finlit_technicals" / "__init__.py").read_text(encoding="utf-8"))
        return m.group(1) if m else "?"
    except OSError:
        return "?"


def signature(nse: Path) -> str:
    """Names, sizes and times of every file the batch reads, plus the package version: when it is unchanged, so is the answer."""
    h = hashlib.sha1(package_version().encode())     # nosec B324 - change detector, not security
    for p in nse_files(nse):
        st = p.stat()
        h.update(f"{p.relative_to(nse)}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def folder_problem(nse: Path) -> Optional[str]:
    """None when the folder holds what the batch needs, else one plain sentence."""
    if not nse.is_dir():
        return f"the NSE data folder {nse} does not exist on the server (docs/SECTORS.md, step 'Upload the NSE folder')"
    if not list(nse.glob("bhav_*.csv.gz")):
        return f"the NSE data folder {nse} has no bhav_<year>.csv.gz files (docs/SECTORS.md, step 'Upload the NSE folder')"
    if not list(nse.glob("idx_*.csv.gz")):
        return f"the NSE data folder {nse} has no idx_<year>.csv.gz files (docs/SECTORS.md, step 'Upload the NSE folder')"
    return None


# ------------------------------------------------------------------------------------------------ step 1: fetch
async def run_fetch(nse: Path, timeout_min: float, env: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Run `fetch-nse` in a child process. Returns {"status": ok|partial|refused|failed|timeout, "message": plain words}. Never raises."""
    refused = await asyncio.to_thread(quick_probe)
    if refused:
        return {"status": "refused", "message": refused}
    cmd = [sys.executable, "-m", "finlit_technicals", "fetch-nse", "--dir", str(nse)]
    lines: List[str] = []
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(BACKEND_DIR), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                                                    env={**os.environ, **(env or {}), "PYTHONPATH": str(BACKEND_DIR), "PYTHONUNBUFFERED": "1"})
    except Exception as exc:
        return {"status": "failed", "message": f"could not start the NSE download ({type(exc).__name__}: {exc})"[:300]}

    async def pump() -> None:
        assert proc.stdout is not None
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line:
                lines.append(line)
                del lines[:-60]
                print("fetch-nse:", line[:200], flush=True)       # keeps the job log (and the supervisor's stall watch) alive

    try:
        await asyncio.wait_for(asyncio.gather(pump(), proc.wait()), timeout=timeout_min * 60)
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        return {"status": "timeout", "message": f"the NSE download did not finish in {timeout_min:g} minutes and was stopped; it carries on where it stopped at the next run"}
    except Exception as exc:
        return {"status": "failed", "message": f"the NSE download broke ({type(exc).__name__}: {exc})"[:300]}
    return interpret_fetch(proc.returncode, lines)


def quick_probe(timeout: float = 20.0, today: Optional[date] = None) -> Optional[str]:
    """One request to NSE's archive with a short timeout. None when it answers (200 or 404), else a sentence saying it does not.
    fetch-nse itself retries a refused request for minutes; asking once first keeps a blocked server from holding the bulk lane for ten minutes every try."""
    import urllib.error
    import urllib.request
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from finlit_technicals import fetch
        day = today or datetime.now(IST).date()
        while day.weekday() >= 5:
            day -= timedelta(days=1)
        url = fetch.urls_for(day)[0][1]
        req = urllib.request.Request(url, headers={"User-Agent": fetch.UA, "Accept": "*/*", "Referer": "https://www.nseindia.com/"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:      # nosec B310 - fixed https URL of NSE's archive
                code = r.status
                r.read(1)             # a GET that reads one byte: some CDNs answer HEAD differently
        except urllib.error.HTTPError as e:
            code = e.code
    except Exception as exc:
        return f"NSE's archive could not be reached from this server ({type(exc).__name__}: {str(exc)[:120]}). NSE often refuses data-centre addresses; the data stays at the last files held (docs/SECTORS.md)."
    if code in (200, 404):
        return None
    return (f"NSE's archive refused this server (HTTP {code}). NSE often refuses data-centre addresses; the data stays at the last files held. "
            "Run the download from a PC in India and copy the folder up (docs/SECTORS.md).")


def interpret_fetch(code: Optional[int], lines: List[str]) -> Dict[str, Any]:
    text = "\n".join(lines)
    tail = " | ".join(lines[-3:])[:300]
    if code == 0:
        m = re.search(r"(\d+) days could not be fetched", text)
        if m and int(m.group(1)) > 0:
            return {"status": "partial", "message": f"{m.group(1)} days could not be fetched from NSE this time; they are retried at the next run. {tail}"[:400]}
        return {"status": "ok", "message": tail or "NSE files are up to date"}
    if "did not answer as expected" in text or "FAILED (status" in text:
        return {"status": "refused", "message": "NSE's archive did not answer this server (NSE often refuses data-centre addresses). The data stays at the last files held; "
                                               "run the download from a PC in India and copy the folder up (docs/SECTORS.md). " + tail}
    return {"status": "failed", "message": f"the NSE download ended with code {code}. {tail}"[:400]}


# ------------------------------------------------------------------------------------------------ step 2: build
def default_batch(nse: Path, building: Path, symbols: Optional[List[str]], progress: Callable[[int, int, str], None]) -> List[Dict[str, Any]]:
    """The finlit_technicals batch over NSE's files. One SectorEngine is built and handed to the batch, so the market panel is held once."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from finlit_technicals import NseHistory, SectorEngine
    from finlit_technicals.batch import nse_symbols, run
    src = NseHistory(nse)
    eng = SectorEngine(src)
    syms = symbols or nse_symbols(eng)
    return run(syms, src, building, progress=progress, engine=eng)


def peak_rss_mb() -> Optional[float]:
    try:
        import resource
        v = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss          # kilobytes on Linux
        return round(v / 1024.0, 1)
    except Exception:
        return None


# ------------------------------------------------------------------------------------------------ step 3: check
def check_release(building: Path, previous_stocks: Optional[int]) -> Optional[str]:
    """None when the new set may go live, else the reason it may not."""
    board = sd.read_json(building / "sectors" / "_board.json")
    if not isinstance(board, dict) or not board.get("rows"):
        return "the board file is missing or empty"
    missing = [r["slug"] for r in board["rows"] if not (building / "sectors" / f"{r['slug']}.json").is_file()]
    if missing:
        return f"{len(missing)} industry pages were not written (for example {missing[0]})"
    summ = sd.read_json(building / "_summary.json")
    if not isinstance(summ, dict):
        return "the summary file is missing"
    stocks = summ.get("stocks") or []
    errors = [s for s in stocks if "error" in s]
    written = len(stocks) - len(errors)
    if written < MIN_STOCK_FILES:
        return f"only {written} stock files were written"
    if len(errors) > MAX_ERROR_SHARE * len(stocks):
        return f"{len(errors)} of {len(stocks)} stocks failed (for example {errors[0].get('symbol')}: {errors[0].get('error', '')[:120]})"
    if previous_stocks and written < MIN_SHARE_OF_PREVIOUS * previous_stocks:
        return f"{written} stock files against {previous_stocks} in the live set: too few to replace it"
    return None


# ------------------------------------------------------------------------------------------------ the run
async def expected_data_date(store: Any, now: datetime) -> date:
    """The session the data should cover now: the technicals job's holiday-aware find when there is one, else the weekday rule."""
    from .jobs.schedule import expected_session
    exp = expected_session(now)
    try:
        from .prism_technical import current_target
        return min(exp, await current_target(store.redis, now))
    except Exception:
        return exp


async def refresh(store: Any, *, env: Optional[Dict[str, str]] = None, force: bool = False, fetch: Optional[bool] = None, symbols: Optional[List[str]] = None,
                  fetch_fn: Optional[Callable[..., Any]] = None, batch_fn: Optional[Callable[..., List[Dict[str, Any]]]] = None,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """The whole run. Returns the result dict (also recorded). `status`: ok | unchanged | behind | error."""
    env = dict(os.environ if env is None else env)
    now = now or datetime.now(IST)
    t0 = time.monotonic()
    nse, out = sd.nse_dir(env), sd.out_dir(env)
    res: Dict[str, Any] = {"status": "error", "nse": str(nse), "fetch": {"status": "off", "message": "not asked to download"}}
    try:
        res = await _refresh(store, env, nse, out, res, force, fetch, symbols, fetch_fn or run_fetch, batch_fn or default_batch, now)
    except Exception as exc:      # a bug or an out-of-disk must not take the supervisor down, and must be reported in words
        log.exception("refresh-sectors failed")
        res.update(status="error", reason=f"{type(exc).__name__}: {exc}"[:300])
    res["seconds"] = round(time.monotonic() - t0)
    res["peakMb"] = peak_rss_mb()
    res["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await finish(store, out, res)
    return res


async def _refresh(store, env, nse: Path, out: Path, res: Dict[str, Any], force: bool, fetch: Optional[bool], symbols, fetch_fn, batch_fn, now: datetime) -> Dict[str, Any]:
    problem = folder_problem(nse)
    if problem:
        return {**res, "status": "error", "reason": f"Cannot run: {problem}."}
    do_fetch = (str(env.get("SECTOR_FETCH", "1")).strip() != "0") if fetch is None else fetch
    if do_fetch:
        timeout = float(env.get("SECTOR_FETCH_MAX_MIN", DEFAULT_FETCH_MIN) or DEFAULT_FETCH_MIN)
        res["fetch"] = await fetch_fn(nse, timeout)
        print(f"fetch: {res['fetch']['status']}: {res['fetch']['message']}", flush=True)
        problem = folder_problem(nse)
        if problem:
            return {**res, "status": "error", "reason": f"Cannot run: {problem}."}
    expected = await expected_data_date(store, now)
    res["expected"] = expected.isoformat()
    live = sd.live_release(out)
    prev_meta = sd.sector_meta(live)
    live_date = sd.board_date(out)
    res["dataDate"] = live_date.isoformat() if live_date else None
    sig = signature(nse)
    if live and not force and not symbols and prev_meta.get("nse_signature") == sig:
        # the files are the ones the live set was built from: building again would give the same answer
        res["unchanged"] = True
        return {**res, **_verdict(live_date, expected, built=False, fetch=res["fetch"])}
    stamp = now.strftime("%Y%m%d-%H%M")
    building = sd.building_dir(out, stamp)
    progress_t = [time.monotonic()]

    def progress(i: int, n: int, sym: str) -> None:
        if time.monotonic() - progress_t[0] > 20 or i == n:
            progress_t[0] = time.monotonic()
            print(f"batch: {i}/{n} {sym}", flush=True)

    t_batch = time.monotonic()
    try:
        summary = await asyncio.to_thread(batch_fn, nse, building, symbols, progress)
    except BaseException:
        import shutil
        shutil.rmtree(building, ignore_errors=True)
        raise
    bad = [s for s in summary if "error" in s]
    why = check_release(building, prev_meta.get("stocks"))
    if why:
        import shutil
        shutil.rmtree(building, ignore_errors=True)
        return {**res, "status": "error", "reason": f"The new set was not published ({why}); the previous set keeps serving.", "stocks": len(summary), "errors": len(bad)}
    board = sd.read_json(building / "sectors" / "_board.json")
    new_date = date.fromisoformat(str(board["date"])[:10])
    if live_date and new_date < live_date and not force:
        import shutil
        shutil.rmtree(building, ignore_errors=True)
        return {**res, "status": "error", "reason": f"The new set is for {new_date}, older than the live set ({live_date}); the live set keeps serving.", "stocks": len(summary), "errors": len(bad)}
    meta = {"data_date": new_date.isoformat(), "built_at": now.strftime("%Y-%m-%d %H:%M IST"), "stocks": len(summary) - len(bad), "errors": len(bad),
            "groups": board.get("groups"), "stocks_counted": board.get("stocks_counted"), "nse_signature": sig, "package_version": package_version(),
            "batch_seconds": round(time.monotonic() - t_batch), "peak_mb": peak_rss_mb()}
    sd.atomic_write(building / sd.META_NAME, json.dumps(meta))
    sd.publish(building, out, stamp)
    sd.clear_cache()
    res.update(dataDate=new_date.isoformat(), stocks=meta["stocks"], errors=meta["errors"], groups=meta["groups"], stocksCounted=meta["stocks_counted"], release=stamp)
    return {**res, **_verdict(new_date, expected, built=True, fetch=res["fetch"])}


async def import_release(store: Any, folder: str, *, env: Optional[Dict[str, str]] = None, now: Optional[datetime] = None, force: bool = False) -> Dict[str, Any]:
    """Publish a batch output folder built somewhere else (`python -m finlit_technicals batch --nse nse --out site_data`, uploaded to the server).
    The folder is copied, checked exactly like a nightly build, and swapped in; it is deleted only after it went live. A bad folder changes nothing."""
    import shutil
    env = dict(os.environ if env is None else env)
    now = now or datetime.now(IST)
    t0 = time.monotonic()
    out = sd.out_dir(env)
    src = Path(folder)
    res: Dict[str, Any] = {"status": "error", "mode": "import", "fetch": {"status": "off", "message": "imported, nothing downloaded"}}
    building: Optional[Path] = None
    try:
        if not (src / "sectors" / "_board.json").is_file():
            raise ValueError(f"{src} is not the output of the batch (it has no sectors/_board.json)")
        stamp = now.strftime("%Y%m%d-%H%M")
        building = sd.building_dir(out, stamp)
        shutil.rmtree(building)
        shutil.copytree(src, building)
        live = sd.live_release(out)
        why = check_release(building, sd.sector_meta(live).get("stocks"))
        if why:
            raise ValueError(f"the uploaded set was not published ({why}); the previous set keeps serving")
        board = sd.read_json(building / "sectors" / "_board.json")
        new_date = date.fromisoformat(str(board["date"])[:10])
        live_date = sd.board_date(out)
        if live_date and new_date < live_date and not force:
            raise ValueError(f"the uploaded set is for {new_date}, older than the live set ({live_date}); use --force to replace it anyway")
        summ = sd.read_json(building / "_summary.json") or {}
        stocks = summ.get("stocks") or []
        bad = [x for x in stocks if "error" in x]
        meta = {"data_date": new_date.isoformat(), "built_at": "imported " + now.strftime("%Y-%m-%d %H:%M IST"), "stocks": len(stocks) - len(bad), "errors": len(bad),
                "groups": board.get("groups"), "stocks_counted": board.get("stocks_counted"), "nse_signature": None, "package_version": package_version(),
                "source": "import", "batch_meta": summ.get("meta")}
        sd.atomic_write(building / sd.META_NAME, json.dumps(meta))
        sd.publish(building, out, stamp)
        building = None
        sd.clear_cache()
        expected = await expected_data_date(store, now)
        res.update(status="ok", dataDate=new_date.isoformat(), expected=expected.isoformat(), stocks=meta["stocks"], errors=meta["errors"], groups=meta["groups"],
                   stocksCounted=meta["stocks_counted"], release=stamp,
                   reason=None if new_date >= expected else f"The uploaded data is for {new_date}; the latest session is {expected}.")
        shutil.rmtree(src, ignore_errors=True)
    except Exception as exc:
        log.warning("import-sectors failed: %s", exc)
        res.update(status="error", reason=f"{exc}"[:400] if isinstance(exc, ValueError) else f"{type(exc).__name__}: {exc}"[:300])
        if building is not None:
            shutil.rmtree(building, ignore_errors=True)
    res["seconds"] = round(time.monotonic() - t0)
    res["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    await finish(store, out, res)
    return res


def _verdict(data_date: Optional[date], expected: date, *, built: bool, fetch: Dict[str, Any]) -> Dict[str, Any]:
    """ok when the data covers the expected session; behind (a failure, so it is retried) when it does not, saying what the download said."""
    if data_date is not None and data_date >= expected:
        return {"status": "ok" if built else "unchanged", "reason": None if built else f"NSE files unchanged since the live set (data for {data_date})"}
    cause = ""
    if fetch.get("status") in ("refused", "failed", "timeout", "partial"):
        cause = f" The download said: {fetch['message']}"
    elif fetch.get("status") == "off":
        cause = " The download is switched off (SECTOR_FETCH=0), so new NSE files must be copied up by hand."
    else:
        cause = " NSE had not published a newer file when the download ran (it is tried again)."
    return {"status": "behind", "reason": f"The data is for {data_date or 'no date'}, the latest session is {expected}.{cause}"[:480]}


async def finish(store: Any, out: Path, res: Dict[str, Any]) -> None:
    """Record the result in the three places that show it: the job log, last_run.json, and Postgres (record_run) for /api/mf/status."""
    short = {k: v for k, v in res.items() if k != "nse"}
    print(json.dumps(short, default=str)[:3000], flush=True)
    try:
        sd.write_last_run(out, short)
    except OSError as exc:
        log.warning("could not write last_run.json: %s", exc)
    try:
        from .mf import record_run
        await record_run(store, RUN_NAME, short)
    except Exception:
        log.warning("could not record the %s result", RUN_NAME)


def exit_code(res: Dict[str, Any]) -> int:
    return 0 if res.get("status") in ("ok", "unchanged") else 1
