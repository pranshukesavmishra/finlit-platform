"""Starting and watching the job processes. The supervisor talks to the small Handle interface; tests use a fake runner with the same shape."""
from __future__ import annotations

import os
import signal
import subprocess  # nosec B404 - fixed argument lists, no shell
import sys
import time
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Protocol

from .registry import Job


class Handle(Protocol):
    pid: int

    def poll(self) -> Optional[int]: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def last_activity(self) -> float: ...
    def rss_mb(self) -> Optional[int]: ...
    def tail(self) -> str: ...


def _rss_mb(pid: int) -> Optional[int]:
    """Peak resident size of the process (VmHWM), MB."""
    try:
        with open(f"/proc/{pid}/status") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return None


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def kill_group(pid: int, sig: int = signal.SIGKILL) -> bool:
    try:
        os.killpg(os.getpgid(pid), sig)
        return True
    except (OSError, ProcessLookupError):
        return False


class ProcHandle:
    def __init__(self, proc: subprocess.Popen, log_path: Path, hb_path: Path) -> None:
        self.proc, self.log_path, self.hb_path, self.pid = proc, log_path, hb_path, proc.pid
        self.started = time.time()
        self._peak: Optional[int] = None

    def poll(self) -> Optional[int]:
        return self.proc.poll()

    def terminate(self) -> None:
        kill_group(self.pid, signal.SIGTERM)

    def kill(self) -> None:
        kill_group(self.pid, signal.SIGKILL)

    def last_activity(self) -> float:
        t = self.started
        for p in (self.log_path, self.hb_path):
            try:
                t = max(t, p.stat().st_mtime)
            except OSError:
                pass
        return t

    def rss_mb(self) -> Optional[int]:
        v = _rss_mb(self.pid)
        if v is not None:
            self._peak = max(self._peak or 0, v)
        return self._peak

    def tail(self) -> str:
        try:
            with open(self.log_path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 2048))
                lines = [x for x in fh.read().decode("utf-8", "replace").splitlines() if x.strip()]
            return lines[-1][:300] if lines else ""
        except OSError:
            return ""


class ShardHandle:
    """Several processes that together are one job (the Prism pre-compute runs two workers side by side)."""
    def __init__(self, parts: List[Handle]) -> None:
        self.parts, self.pid = parts, parts[0].pid

    def poll(self) -> Optional[int]:
        codes = [p.poll() for p in self.parts]
        if any(c is None for c in codes):
            return None
        bad = [c for c in codes if c not in (0, None)]
        return bad[0] if bad else 0

    def terminate(self) -> None:
        for p in self.parts:
            p.terminate()

    def kill(self) -> None:
        for p in self.parts:
            p.kill()

    def last_activity(self) -> float:
        return max(p.last_activity() for p in self.parts)

    def rss_mb(self) -> Optional[int]:
        v = [p.rss_mb() for p in self.parts]
        return sum(x for x in v if x) or None

    def tail(self) -> str:
        return self.parts[0].tail()


class ProcessRunner:
    def __init__(self, python: Optional[str] = None, log_dir: str = "/tmp", nice: int = 15, oom_adj: int = 500, cwd: Optional[str] = None) -> None:  # nosec B108 - the container's own /tmp, where the job logs have always been
        self.python, self.log_dir, self.nice, self.oom_adj, self.cwd = python or os.environ.get("PYTHON") or sys.executable, Path(log_dir), nice, oom_adj, cwd
        self.hb_dir = self.log_dir / "finlit-jobs"

    def _preexec(self, nice: int, oom: int):
        def fn() -> None:    # runs in the child before exec: lower CPU priority, and the first to be killed when memory runs out
            try:
                os.nice(nice)
            except OSError:
                pass
            try:
                with open("/proc/self/oom_score_adj", "w") as fh:
                    fh.write(str(oom))
            except OSError:
                pass
        return fn

    def start(self, job: Job, extra_env: Optional[Mapping[str, str]] = None) -> Handle:
        self.hb_dir.mkdir(parents=True, exist_ok=True)
        parts: List[Handle] = []
        for k in range(job.shards):
            tag = job.name if job.shards == 1 else f"{job.name}-{k}"
            log_path, hb_path = self.log_dir / f"job-{tag}.log", self.hb_dir / f"{tag}.hb"
            try:
                if log_path.stat().st_size > 20 * 1024 * 1024:     # keep the log files from growing for ever
                    log_path.replace(log_path.with_suffix(".log.1"))
            except OSError:
                pass
            hb_path.touch()
            env = {**os.environ, "MALLOC_ARENA_MAX": os.environ.get("MALLOC_ARENA_MAX", "2"), "FINLIT_JOB_NAME": job.name, "FINLIT_JOB_HEARTBEAT": str(hb_path), **(extra_env or {})}
            args = [self.python, *job.argv]
            if job.shards > 1:
                args += ["--shard", f"{k}/{job.shards}"]
            with open(log_path, "ab") as out:
                out.write(f"\n--- {time.strftime('%F %T')} start {job.name}\n".encode())
                proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=self.cwd,  # nosec B603 - fixed list, no shell
                                        start_new_session=True, preexec_fn=self._preexec(self.nice if job.cls == "bulk" else 0, self.oom_adj))  # nosec B602
            parts.append(ProcHandle(proc, log_path, hb_path))
        return parts[0] if len(parts) == 1 else ShardHandle(parts)

    def reap_orphan(self, pid: Optional[int]) -> bool:
        """A job process left over from a supervisor that died: stop its whole process group, but only if the pid still looks like one of ours."""
        if not pid or not pid_alive(pid):
            return False
        try:
            cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
        except OSError:
            return False
        if " -m finlit." not in cmd:
            return False
        return kill_group(pid, signal.SIGKILL)
