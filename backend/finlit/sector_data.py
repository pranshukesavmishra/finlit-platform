"""Sector pages: where the files live, how the nightly job swaps a new set in, and how the API reads them.

The nightly job (finlit/sector_job.py, command `refresh-sectors`) runs the finlit_technicals batch into a NEW folder and then makes it the live one in a single
step, so a reader never meets half-written files:

    $SECTOR_OUT_DIR/                      default /data/sectors
        current -> releases/20261029-1934     a symlink; renamed over the old one in one operation (os.replace)
        releases/20261029-1934/               _summary.json, <SYMBOL>.json (one per stock), sectors/_board.json, sectors/<slug>.json, rotation/_map.json, rotation/<slug>.json, _sectors_meta.json
        releases/20261028-1931/               the one before (kept so a request that is still reading it finishes; older ones are deleted)
        last_run.json                         how the last run ended (ok, or why not), written on every run, success or failure

Nothing in this module imports numpy or pandas: the website process only reads JSON. The heavy package is imported by sector_job.py, in the job process only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
from collections import OrderedDict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_NSE_DIR = "/data/nse"
DEFAULT_OUT_DIR = "/data/sectors"
KEEP_RELEASES = 2
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&_.\-]{0,23}$")      # NSE symbols (M&M, BAJAJ-AUTO); must not start with a dot or dash
META_NAME = "_sectors_meta.json"
# Addresses that were renamed by a newer grouping: old slug -> the slug that replaced it (NSE's Capital Goods sector of one small industry is now named after it).
SLUG_ALIASES = {"capital-goods": "agricultural-commercial-construction-vehicles"}
LAST_RUN = "last_run.json"


def nse_dir(env: Optional[Dict[str, str]] = None) -> Path:
    return Path((env or os.environ).get("SECTOR_NSE_DIR") or DEFAULT_NSE_DIR)


def out_dir(env: Optional[Dict[str, str]] = None) -> Path:
    return Path((env or os.environ).get("SECTOR_OUT_DIR") or DEFAULT_OUT_DIR)


def enabled(env: Optional[Dict[str, str]] = None) -> bool:
    return str((env or os.environ).get("SECTORS_ENABLED", "0")).strip() == "1"


# ------------------------------------------------------------------------------------------------ writing: the atomic swap
def atomic_write(path: Path, text: str) -> None:
    """Write a small file so a reader sees either the old content or the new, never a part."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix="." + path.name + ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def building_dir(out: Path, stamp: str) -> Path:
    """A fresh folder the batch writes into. The leading dot keeps it out of every listing of releases."""
    d = out / "releases" / f".building-{stamp}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def publish(building: Path, out: Path, stamp: str) -> Path:
    """Make a finished folder the live one: rename it into place, then point `current` at it with one atomic rename. Returns the release folder."""
    final = out / "releases" / stamp
    if final.exists():
        shutil.rmtree(final)
    os.replace(building, final)
    link_tmp = out / ".current.new"
    if link_tmp.is_symlink() or link_tmp.exists():
        link_tmp.unlink()
    os.symlink(os.path.join("releases", stamp), link_tmp)
    os.replace(link_tmp, out / "current")
    prune(out, KEEP_RELEASES)
    return final


def prune(out: Path, keep: int) -> None:
    rel = out / "releases"
    live = os.path.realpath(out / "current") if (out / "current").exists() else None
    done = sorted((p for p in rel.iterdir() if p.is_dir() and not p.name.startswith(".")), key=lambda p: p.name, reverse=True) if rel.is_dir() else []
    for p in done[keep:]:
        if live and os.path.realpath(p) == live:
            continue
        shutil.rmtree(p, ignore_errors=True)
    for p in (rel.iterdir() if rel.is_dir() else []):      # a building folder left by a run that was killed
        if p.name.startswith(".building-") and p.is_dir():
            try:
                age = datetime.now().timestamp() - p.stat().st_mtime
            except OSError:
                continue
            if age > 6 * 3600:
                shutil.rmtree(p, ignore_errors=True)


def write_last_run(out: Path, info: Dict[str, Any]) -> None:
    atomic_write(out / LAST_RUN, json.dumps(info, ensure_ascii=False, default=str))


# ------------------------------------------------------------------------------------------------ reading
def live_release(out: Optional[Path] = None) -> Optional[Path]:
    """The folder `current` points at, resolved ONCE (a request keeps reading from the same release even if a swap happens meanwhile), or None."""
    out = out or out_dir()
    cur = out / "current"
    try:
        real = Path(os.path.realpath(cur))
    except OSError:
        return None
    return real if (real / "sectors" / "_board.json").is_file() else None


_cache: "OrderedDict[Tuple[str, int, int], Any]" = OrderedDict()
_lock = threading.Lock()
CACHE_MAX = 80


def read_json(path: Path) -> Any:
    """Parsed JSON of a file, remembered until the file changes (keyed by path, size and modification time). None when it is missing or unreadable."""
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_size, st.st_mtime_ns)
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    with _lock:
        _cache[key] = value
        while len(_cache) > CACHE_MAX:
            _cache.popitem(last=False)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def resolve_slug(slug: str) -> str:
    """A renamed group's old address answers with the new group's page."""
    return SLUG_ALIASES.get(slug, slug)


def board_slugs(board: Dict[str, Any]) -> set:
    return {r["slug"] for r in board.get("rows", []) if isinstance(r, dict) and r.get("slug")}


def read_last_run(out: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    v = read_json((out or out_dir()) / LAST_RUN)
    return v if isinstance(v, dict) else None


def board_date(out: Optional[Path] = None) -> Optional[date]:
    """The data date of the live board (what the freshness check compares with the expected session), or None."""
    rel = live_release(out)
    board = read_json(rel / "sectors" / "_board.json") if rel else None
    try:
        return date.fromisoformat(str(board["date"])[:10]) if board else None
    except (KeyError, ValueError, TypeError):
        return None


def not_loaded_reason(out: Optional[Path] = None, env: Optional[Dict[str, str]] = None) -> str:
    """One public-safe sentence saying why no sector data can be shown. Starts with 'Sector data is not loaded yet:'."""
    out = out or out_dir(env)
    if not enabled(env):
        return "Sector data is not loaded yet: the nightly sector job is switched off on this server."
    last = read_last_run(out)
    if last is None:
        return "Sector data is not loaded yet: the first nightly run has not finished."
    why = str(last.get("reason") or last.get("error") or last.get("status") or "the last run did not finish")
    return f"Sector data is not loaded yet: the last run ended with '{last.get('status', 'no result')}' ({why[:240]})."


def sector_meta(rel: Optional[Path]) -> Dict[str, Any]:
    v = read_json(rel / META_NAME) if rel else None
    return v if isinstance(v, dict) else {}
