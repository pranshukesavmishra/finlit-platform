"""The nightly sector run: atomic swap, the last good set keeps serving on any failure, honest reasons, the import path."""
import json
import os
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import sector_fakes as fakes
from finlit import sector_data as sd
from finlit import sector_job as sj

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 10, 29, 19, 34, tzinfo=IST)           # Thursday evening; the expected session is 2026-10-29
THU = date(2026, 10, 29)


class Store:
    """No database: record_run fails quietly, as it does when Postgres is down."""
    redis = None


def make_nse(root: Path, marker: str = "a") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for name in ("bhav_2026.csv.gz", "idx_2026.csv.gz"):
        f = root / name
        f.write_bytes(marker.encode())
        t = 1_700_000_000 + sum(map(ord, marker)) * 1000            # a file NSE updated has another modification time
        os.utime(f, (t, t))
    return root


def env_for(tmp_path, **extra):
    return {"SECTOR_NSE_DIR": str(tmp_path / "nse"), "SECTOR_OUT_DIR": str(tmp_path / "out"), "SECTORS_ENABLED": "1", **extra}


def good_batch(date_="2026-10-29", stocks=3, errors=0):
    calls = []

    def batch(nse, building, symbols, progress):
        calls.append(building)
        fakes.make_release(Path(building), date=date_, stocks=stocks, errors=errors)
        progress(stocks, stocks, "X")
        return [{"symbol": f"S{i}"} for i in range(stocks - errors)] + [{"symbol": "E", "error": "boom"}] * errors
    batch.calls = calls
    return batch


async def fetch_ok(nse, timeout):
    return {"status": "ok", "message": "up to date"}


@pytest.fixture(autouse=True)
def small_sets(monkeypatch):
    monkeypatch.setattr(sj, "MIN_STOCK_FILES", 1)
    sd.clear_cache()
    yield
    sd.clear_cache()


async def run(tmp_path, **kw):
    kw.setdefault("fetch_fn", fetch_ok)
    kw.setdefault("now", NOW)
    return await sj.refresh(Store(), env=env_for(tmp_path), **kw)


# ------------------------------------------------------------------------------------------------ the happy path and the swap
async def test_a_good_run_publishes_atomically_and_records_where_the_pages_read_it(tmp_path):
    make_nse(tmp_path / "nse")
    batch = good_batch()
    res = await run(tmp_path, batch_fn=batch)
    out = tmp_path / "out"
    assert res["status"] == "ok" and res["dataDate"] == "2026-10-29" and res["stocks"] == 3 and res["errors"] == 0 and res["fetch"]["status"] == "ok"
    assert sj.exit_code(res) == 0
    assert os.path.islink(out / "current") and (out / "current" / "sectors" / "_board.json").is_file()
    assert sd.board_date(out) == THU and sd.sector_meta(sd.live_release(out))["data_date"] == "2026-10-29"
    last = json.loads((out / "last_run.json").read_text())
    assert last["status"] == "ok" and last["dataDate"] == "2026-10-29" and "nse" not in last
    assert not [p for p in (out / "releases").iterdir() if p.name.startswith(".building")]        # no half-built folder is left


async def test_the_same_nse_files_do_not_trigger_a_second_build(tmp_path):
    make_nse(tmp_path / "nse")
    batch = good_batch()
    await run(tmp_path, batch_fn=batch)
    again = await run(tmp_path, batch_fn=batch)
    assert len(batch.calls) == 1 and again["status"] == "unchanged" and sj.exit_code(again) == 0
    make_nse(tmp_path / "nse", marker="b")                                       # a changed file: a new build
    await run(tmp_path, batch_fn=batch, now=NOW + timedelta(minutes=30))
    assert len(batch.calls) == 2


async def test_only_two_releases_are_kept_and_the_live_one_is_never_deleted(tmp_path):
    make_nse(tmp_path / "nse")
    for k in range(4):
        make_nse(tmp_path / "nse", marker=str(k))
        res = await run(tmp_path, batch_fn=good_batch(), now=NOW + timedelta(minutes=10 * k))
        assert res["status"] == "ok"
    names = sorted(p.name for p in (tmp_path / "out" / "releases").iterdir())
    assert len(names) == 2 and os.path.realpath(tmp_path / "out" / "current").endswith(names[-1])


# ------------------------------------------------------------------------------------------------ failures keep the last good set
async def test_a_crashing_batch_leaves_the_last_good_set_serving_and_says_why(tmp_path):
    make_nse(tmp_path / "nse")
    await run(tmp_path, batch_fn=good_batch())
    before = os.path.realpath(tmp_path / "out" / "current")
    make_nse(tmp_path / "nse", marker="changed")

    def broken(nse, building, symbols, progress):
        (Path(building) / "half.json").write_text("{")
        raise MemoryError("out of memory")
    res = await run(tmp_path, batch_fn=broken, now=NOW + timedelta(hours=1))
    assert res["status"] == "error" and "MemoryError" in res["reason"] and sj.exit_code(res) == 1
    assert os.path.realpath(tmp_path / "out" / "current") == before and sd.board_date(tmp_path / "out") == THU
    assert not [p for p in (tmp_path / "out" / "releases").iterdir() if p.name.startswith(".building")]
    assert json.loads((tmp_path / "out" / "last_run.json").read_text())["status"] == "error"


async def test_a_set_with_too_many_failed_stocks_is_not_published(tmp_path):
    make_nse(tmp_path / "nse")
    res = await run(tmp_path, batch_fn=good_batch(stocks=20, errors=5))
    assert res["status"] == "error" and "failed" in res["reason"] and not (tmp_path / "out" / "current").exists()


async def test_a_set_with_far_fewer_stocks_than_the_live_one_is_not_published(tmp_path):
    make_nse(tmp_path / "nse")
    await run(tmp_path, batch_fn=good_batch(stocks=100))
    make_nse(tmp_path / "nse", marker="x")
    res = await run(tmp_path, batch_fn=good_batch(stocks=20), now=NOW + timedelta(hours=1))
    assert res["status"] == "error" and "too few to replace" in res["reason"] and sd.sector_meta(sd.live_release(tmp_path / "out"))["stocks"] == 100


async def test_an_older_set_never_replaces_a_newer_one(tmp_path):
    make_nse(tmp_path / "nse")
    await run(tmp_path, batch_fn=good_batch(date_="2026-10-29"))
    make_nse(tmp_path / "nse", marker="x")
    res = await run(tmp_path, batch_fn=good_batch(date_="2026-10-28"), now=NOW + timedelta(hours=1))
    assert res["status"] == "error" and "older than the live set" in res["reason"] and sd.board_date(tmp_path / "out") == THU


async def test_a_missing_nse_folder_is_a_plain_sentence_not_a_traceback(tmp_path):
    res = await run(tmp_path, batch_fn=good_batch())
    assert res["status"] == "error" and "NSE data folder" in res["reason"] and "does not exist" in res["reason"] and sj.exit_code(res) == 1
    (tmp_path / "nse").mkdir()
    res = await run(tmp_path, batch_fn=good_batch())
    assert "no bhav_<year>.csv.gz files" in res["reason"]
    why = sd.not_loaded_reason(tmp_path / "out", env_for(tmp_path))
    assert why.startswith("Sector data is not loaded yet:") and "no bhav_" in why


async def test_nse_refusing_the_server_is_reported_and_the_old_data_keeps_serving(tmp_path):
    make_nse(tmp_path / "nse")
    await run(tmp_path, batch_fn=good_batch(date_="2026-10-28"), now=NOW - timedelta(days=1))

    async def refused(nse, timeout):
        return {"status": "refused", "message": "NSE's archive refused this server (HTTP 403). Run the download from a PC in India and copy the folder up (docs/SECTORS.md)."}
    batch = good_batch()
    res = await run(tmp_path, batch_fn=batch, fetch_fn=refused)
    assert res["status"] == "behind" and sj.exit_code(res) == 1 and "refused this server" in res["reason"] and "2026-10-28" in res["reason"] and "2026-10-29" in res["reason"]
    assert batch.calls == [] and sd.board_date(tmp_path / "out") == date(2026, 10, 28)           # nothing new to build; the old set serves
    assert res["fetch"]["status"] == "refused"


def test_fetch_output_is_turned_into_plain_words():
    assert sj.interpret_fetch(0, ["Done. 2700 trading days", "All set."])["status"] == "ok"
    p = sj.interpret_fetch(0, ["Done.", "3 days could not be fetched this run."])
    assert p["status"] == "partial" and "3 days" in p["message"]
    r = sj.interpret_fetch(1, ["Check old format (2017-01-02): FAILED (status 403)", "NSE's archive did not answer as expected."])
    assert r["status"] == "refused" and "data-centre" in r["message"] and "PC in India" in r["message"]
    assert sj.interpret_fetch(2, ["Traceback"])["status"] == "failed"


async def test_run_fetch_never_raises_when_the_child_cannot_start(tmp_path, monkeypatch):
    monkeypatch.setattr(sj, "quick_probe", lambda *a, **k: None)
    monkeypatch.setattr(sj.sys, "executable", str(tmp_path / "no-such-python"))
    r = await sj.run_fetch(tmp_path, 1)
    assert r["status"] == "failed" and "could not start" in r["message"]


async def test_run_fetch_stops_at_the_first_refusal_without_waiting_minutes(tmp_path, monkeypatch):
    monkeypatch.setattr(sj, "quick_probe", lambda *a, **k: "NSE's archive refused this server (HTTP 403).")
    r = await sj.run_fetch(tmp_path, 1)
    assert r["status"] == "refused" and "HTTP 403" in r["message"]


async def test_run_fetch_stops_a_child_that_runs_too_long(tmp_path, monkeypatch):
    monkeypatch.setattr(sj, "quick_probe", lambda *a, **k: None)
    script = tmp_path / "sleepy.py"
    script.write_text("import time\nprint('working', flush=True)\ntime.sleep(60)\n")
    real = sj.asyncio.create_subprocess_exec

    async def fake_exec(*cmd, **kw):
        return await real(sys_exe(), str(script), **{k: v for k, v in kw.items() if k in ("stdout", "stderr", "cwd")})
    monkeypatch.setattr(sj.asyncio, "create_subprocess_exec", fake_exec)
    r = await sj.run_fetch(tmp_path, 0.02)
    assert r["status"] == "timeout" and "carries on where it stopped" in r["message"]


def sys_exe():
    import sys
    return sys.executable


def test_quick_probe_reads_the_status_code(monkeypatch):
    import urllib.error
    import urllib.request

    class R:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n):
            return b"P"
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: R())
    assert sj.quick_probe(today=THU) is None

    def forbidden(*a, **k):
        raise urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", forbidden)
    assert "refused this server (HTTP 403)" in sj.quick_probe(today=THU)

    def missing(*a, **k):
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, None)
    monkeypatch.setattr(urllib.request, "urlopen", missing)
    assert sj.quick_probe(today=THU) is None                                     # NSE answered (no file for that day): reachable

    def timeout(*a, **k):
        raise TimeoutError("timed out")
    monkeypatch.setattr(urllib.request, "urlopen", timeout)
    assert "could not be reached" in sj.quick_probe(today=THU)


# ------------------------------------------------------------------------------------------------ importing a set built elsewhere
async def test_an_uploaded_set_is_checked_and_swapped_in_then_removed(tmp_path):
    up = fakes.make_release(tmp_path / "incoming" / "site_data")
    res = await sj.import_release(Store(), str(up), env=env_for(tmp_path), now=NOW)
    assert res["status"] == "ok" and res["dataDate"] == "2026-10-29" and sj.exit_code(res) == 0
    assert sd.board_date(tmp_path / "out") == THU and sd.sector_meta(sd.live_release(tmp_path / "out"))["source"] == "import" and not up.exists()


async def test_a_bad_upload_changes_nothing(tmp_path):
    await sj.import_release(Store(), str(fakes.make_release(tmp_path / "u1")), env=env_for(tmp_path), now=NOW)
    broken = fakes.make_release(tmp_path / "u2", date="2026-10-30")
    (broken / "sectors" / "banks.json").unlink()
    res = await sj.import_release(Store(), str(broken), env=env_for(tmp_path), now=NOW + timedelta(days=1))
    assert res["status"] == "error" and "industry pages were not written" in res["reason"] and sd.board_date(tmp_path / "out") == THU and broken.exists()
    res = await sj.import_release(Store(), str(tmp_path / "nothing"), env=env_for(tmp_path), now=NOW)
    assert res["status"] == "error" and "not the output of the batch" in res["reason"]
    old = fakes.make_release(tmp_path / "u3", date="2026-10-20")
    res = await sj.import_release(Store(), str(old), env=env_for(tmp_path), now=NOW)
    assert res["status"] == "error" and "older than the live set" in res["reason"]
    assert (await sj.import_release(Store(), str(old), env=env_for(tmp_path), now=NOW, force=True))["status"] == "ok"


# ------------------------------------------------------------------------------------------------ the swap is atomic for a reader
def test_the_current_link_is_replaced_in_one_step_and_a_reader_always_sees_a_whole_set(tmp_path):
    out = tmp_path / "out"
    for k, d in enumerate(("2026-10-27", "2026-10-28")):
        b = sd.building_dir(out, f"s{k}")
        fakes.make_release(b, date=d)
        sd.publish(b, out, f"s{k}")
        seen = sd.board_date(out)
        assert seen == date.fromisoformat(d)
    assert os.readlink(out / "current") == os.path.join("releases", "s1")
    assert sd.live_release(tmp_path / "does-not-exist") is None


# ------------------------------------------------------------------------------------------------ the real package on the package's own synthetic NSE folder
async def test_the_real_batch_runs_on_an_nse_folder_and_the_files_are_what_the_api_reads(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    monkeypatch.syspath_prepend(str(Path(sj.BACKEND_DIR) / "finlit_technicals" / "tests"))
    from nse_fixture import write_folder
    write_folder(tmp_path / "nse")
    monkeypatch.setattr(sj, "MIN_STOCK_FILES", 5)
    res = await sj.refresh(Store(), env=env_for(tmp_path), fetch=False, now=NOW)
    assert res["status"] in ("ok", "behind") and res["errors"] == 0 and res["stocks"] >= 5, res
    out = tmp_path / "out"
    board = sd.read_json(sd.live_release(out) / "sectors" / "_board.json")
    assert board["rows"] and board["disclaimer"] and board["date"] == res["dataDate"]
    assert all((sd.live_release(out) / "sectors" / f"{r['slug']}.json").is_file() for r in board["rows"])
    page = sd.read_json(sd.live_release(out) / "sectors" / f"{board['rows'][0]['slug']}.json")
    assert page["history"]["dates"] and page["summary"]
    assert (sd.live_release(out) / "TATASTEEL.json").is_file() and sd.read_json(sd.live_release(out) / "_summary.json")["meta"]["errors"] == 0
    assert res["peakMb"] and "nse_signature" in sd.sector_meta(sd.live_release(out))


# ------------------------------------------------------------------------------------------------ the staged batch (docs/SECTORS.md, "Memory and time")
def test_the_job_process_stays_light_and_the_peak_counts_the_stages():
    """The runner of the stages needs only the standard library: importing finlit_technicals in the job process would put numpy and pandas (about 100 MB) beside the
    stage that is working. The peak reported (status page, meta) is the largest of the job process and of the stages it ran."""
    import subprocess
    import sys
    code = ("import sys; sys.path.insert(0, %r); from finlit import sector_job as sj; m = sj.staged_runner(); "
            "assert callable(m.run_staged) and 'numpy' not in sys.modules and 'pandas' not in sys.modules and 'finlit_technicals' not in sys.modules") % str(Path(sj.BACKEND_DIR))
    assert subprocess.run([sys.executable, "-c", code], capture_output=True, text=True).returncode == 0
    child = subprocess.run([sys.executable, "-c", "x = bytearray(150 * 1024 * 1024); x[::4096] = b'1' * len(x[::4096])"])
    assert child.returncode == 0
    assert sj.peak_rss_mb() >= 150


async def test_the_single_process_batch_is_still_there_and_gives_the_same_files(tmp_path, monkeypatch):
    pytest.importorskip("pandas")
    monkeypatch.syspath_prepend(str(Path(sj.BACKEND_DIR) / "finlit_technicals" / "tests"))
    from nse_fixture import write_folder
    write_folder(tmp_path / "nse")
    for flag in ("0", "1"):
        building = tmp_path / f"b{flag}"
        monkeypatch.setenv("SECTOR_STAGED", flag)
        summary = sj.default_batch(tmp_path / "nse", building, None, lambda *a: None)
        assert len(summary) >= 5 and not [x for x in summary if "error" in x]
    import json
    a, b = tmp_path / "b0", tmp_path / "b1"
    files = sorted(p.relative_to(a) for p in a.rglob("*.json") if p.name != "_summary.json")
    assert files == sorted(p.relative_to(b) for p in b.rglob("*.json") if p.name != "_summary.json") and len(files) > 10
    assert all((a / f).read_bytes() == (b / f).read_bytes() for f in files)
    sa, sb = (json.loads((x / "_summary.json").read_text()) for x in (a, b))
    assert sa["stocks"] == sb["stocks"]


# ------------------------------------------------------------------------------------------------ rotation files and the clearing of renamed groups
def stale_page(release: Path, folder: str, slug="capital-goods"):
    (release / folder).mkdir(exist_ok=True)
    (release / folder / f"{slug}.json").write_text(json.dumps({"name": "Capital Goods"}))


async def test_a_new_build_never_carries_the_files_of_a_renamed_group(tmp_path):
    """The batch builds into a NEW folder and swaps it in, so capital-goods.json of the old release cannot survive in the live one."""
    def batch_with_rotation(nse, building, symbols, progress):
        fakes.make_release(Path(building), rotation=True)
        return [{"symbol": f"S{i}"} for i in range(3)]
    first = fakes.make_release(tmp_path / "first", rotation=True)
    stale_page(first, "sectors")
    stale_page(first, "rotation")
    assert (await sj.import_release(Store(), str(first), env=env_for(tmp_path), now=NOW - timedelta(days=1), force=True))["status"] == "ok"
    out = tmp_path / "out"
    live1 = sd.live_release(out)
    assert not (live1 / "sectors" / "capital-goods.json").exists() and not (live1 / "rotation" / "capital-goods.json").exists()   # an uploaded folder is cleared too
    nse = make_nse(tmp_path / "nse")
    res = await run(tmp_path, batch_fn=batch_with_rotation)
    assert res["status"] == "ok", res
    live = sd.live_release(out)
    assert live != live1 and (live / "rotation" / "_map.json").is_file() and sd.sector_meta(live)["rotation"] is True
    assert sorted(p.name for p in (live / "rotation").iterdir()) == sorted(["_map.json"] + [f"{s}.json" for s in fakes.SLUGS])
    assert not (live / "sectors" / "capital-goods.json").exists() and not (live / "rotation" / "capital-goods.json").exists()


def test_clear_orphans_removes_only_unlisted_group_files(tmp_path):
    rel = fakes.make_release(tmp_path / "rel", rotation=True)
    stale_page(rel, "sectors")
    stale_page(rel, "rotation")
    (rel / "sectors" / "_note.json").write_text("{}")
    removed = sj.clear_orphans(rel)
    assert removed == ["rotation/capital-goods.json", "sectors/capital-goods.json"]
    assert (rel / "sectors" / "banks.json").is_file() and (rel / "sectors" / "_note.json").is_file() and (rel / "rotation" / "banks.json").is_file()
    plain = fakes.make_release(tmp_path / "plain")           # a set with no rotation folder: nothing to clear there
    stale_page(plain, "sectors")
    assert sj.clear_orphans(plain) == ["sectors/capital-goods.json"]


async def test_a_rotation_map_with_a_missing_card_is_not_published_but_no_map_is_fine(tmp_path):
    bad = fakes.make_release(tmp_path / "bad", rotation=True)
    (bad / "rotation" / "banks.json").unlink()
    res = await sj.import_release(Store(), str(bad), env=env_for(tmp_path), now=NOW)
    assert res["status"] == "error" and "rotation cards were not written" in res["reason"] and sd.live_release(tmp_path / "out") is None
    none = fakes.make_release(tmp_path / "none")
    assert (await sj.import_release(Store(), str(none), env=env_for(tmp_path), now=NOW))["status"] == "ok"
    assert sd.sector_meta(sd.live_release(tmp_path / "out"))["rotation"] is False
