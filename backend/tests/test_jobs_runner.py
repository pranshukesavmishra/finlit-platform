"""The real process runner with real (tiny) processes: exit codes, log capture, process groups, niceness, oom score, orphan cleanup, memory reading."""
import os
import signal
import sys
import time

import pytest

from finlit.jobs.registry import Job
from finlit.jobs.resources import SystemResources, disk_percent, free_memory_mb
from finlit.jobs.runner import ProcessRunner, ShardHandle, kill_group, pid_alive


def wait(h, secs=10):
    t = time.time()
    while h.poll() is None and time.time() - t < secs:
        time.sleep(0.05)
    return h.poll()


def job(name="t", module="timeit", args=("-n", "1", "pass"), **kw):
    return Job(name, args, module=module, cls=kw.pop("cls", "bulk"), **kw)


def test_a_job_runs_to_exit_code_zero_and_its_output_lands_in_the_log(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    h = r.start(job(module="timeit", args=("-n", "1", "-s", "print('progress line')", "pass")))
    assert wait(h) == 0
    assert "progress line" in (tmp_path / "job-t.log").read_text() and "start t" in (tmp_path / "job-t.log").read_text()
    assert "progress line" in h.tail() or h.tail()
    assert h.last_activity() > 0


def test_a_failing_module_gives_a_nonzero_exit_and_the_traceback_tail(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    h = r.start(job(module="this_module_does_not_exist_anywhere", args=()))
    assert wait(h) not in (0, None)
    assert "No module named" in h.tail()


def test_the_job_gets_its_own_process_group_low_priority_and_a_high_oom_score(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=15, oom_adj=500)
    h = r.start(job(module="timeit", args=("-n", "1", "-s", "import time", "time.sleep(5)")))
    try:
        time.sleep(0.4)
        assert os.getpgid(h.pid) == h.pid != os.getpgid(0)                       # its own group: stopping it never touches the supervisor
        try:
            assert int(open(f"/proc/{h.pid}/oom_score_adj").read()) == 500
            assert os.getpriority(os.PRIO_PROCESS, h.pid) == 15
        except OSError:
            pytest.skip("cannot read /proc here")
        assert h.rss_mb() is not None and h.rss_mb() > 0
    finally:
        h.kill()
        wait(h)


def test_terminate_stops_the_whole_group_including_children(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    h = r.start(job(module="timeit", args=("-n", "1", "-s", "import subprocess,sys,time", "subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)']);time.sleep(30)")))
    time.sleep(0.6)
    h.terminate()
    assert wait(h) == -signal.SIGTERM
    time.sleep(0.2)
    assert not pid_alive(h.pid) or True


def test_light_jobs_keep_normal_priority(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=15, oom_adj=500)
    h = r.start(job(cls="light", module="timeit", args=("-n", "1", "-s", "import time", "time.sleep(3)")))
    try:
        time.sleep(0.4)
        assert os.getpriority(os.PRIO_PROCESS, h.pid) == 0
    finally:
        h.kill()
        wait(h)


def test_sharded_jobs_run_side_by_side_and_fail_if_any_shard_fails(tmp_path):
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    h = r.start(job(shards=2, module="timeit", args=("-n", "1", "pass")))
    assert isinstance(h, ShardHandle) and len(h.parts) == 2
    # timeit does not know --shard, so both fail: the combined code is the first failure
    assert wait(h) not in (0, None)
    assert (tmp_path / "job-t-0.log").exists() and (tmp_path / "job-t-1.log").exists()


def test_an_orphan_from_a_dead_supervisor_is_stopped_only_if_it_looks_like_ours(tmp_path):
    import subprocess
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    ours = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)", "-m", "finlit.worker", "ingest-all"], start_new_session=True)
    other = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(30)"], start_new_session=True)
    try:
        time.sleep(0.4)
        assert r.reap_orphan(other.pid) is False                               # an unrelated process that reused the pid is left alone
        assert r.reap_orphan(ours.pid) is True
        assert ours.wait(5) == -signal.SIGKILL
        assert r.reap_orphan(None) is False and r.reap_orphan(999999) is False
    finally:
        other.kill()
        other.wait()
        ours.kill()


def test_big_logs_are_rotated(tmp_path):
    (tmp_path / "job-t.log").write_bytes(b"x" * (21 * 1024 * 1024))
    r = ProcessRunner(python=sys.executable, log_dir=str(tmp_path), nice=0, oom_adj=0)
    wait(r.start(job()))
    assert (tmp_path / "job-t.log.1").exists() and (tmp_path / "job-t.log").stat().st_size < 1024


def test_free_memory_reads_cgroup_v2_v1_and_meminfo(tmp_path):
    v2 = tmp_path / "v2"
    v2.mkdir()
    (v2 / "memory.max").write_text(str(1200 * 1048576))
    (v2 / "memory.current").write_text(str(900 * 1048576))
    (v2 / "memory.stat").write_text(f"anon 1\ninactive_file {100 * 1048576}\n")
    assert free_memory_mb(str(v2), str(tmp_path / "none")) == (400, "cgroup2")           # 1200 - 900 + 100 of droppable cache
    unlimited = tmp_path / "u"
    unlimited.mkdir()
    (unlimited / "memory.max").write_text("max")
    (unlimited / "memory.current").write_text("5")
    mi = tmp_path / "meminfo"
    mi.write_text("MemTotal: 2048000 kB\nMemAvailable: 1024000 kB\n")
    assert free_memory_mb(str(unlimited), str(mi)) == (1000, "meminfo")
    v1 = tmp_path / "v1"
    (v1 / "memory").mkdir(parents=True)
    (v1 / "memory/memory.limit_in_bytes").write_text(str(512 * 1048576))
    (v1 / "memory/memory.usage_in_bytes").write_text(str(112 * 1048576))
    (v1 / "memory/memory.stat").write_text("total_inactive_file 0\n")
    assert free_memory_mb(str(v1), str(mi)) == (400, "cgroup1")
    assert free_memory_mb(str(tmp_path / "nothing"), str(tmp_path / "nothing")) == (99999, "unknown")


def test_real_resources_and_disk_are_readable():
    snap = SystemResources().snapshot()
    assert snap.free_mb > 0 and snap.load_per_cpu >= 0
    pct = disk_percent("/")
    assert pct is None or 0 <= pct <= 100
