"""Memory and CPU the supervisor looks at before it starts a job. A job that does not fit WAITS (with a reason); it is never silently skipped."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class Snapshot:
    free_mb: int
    load_per_cpu: float
    source: str = "cgroup"


def _read(path: str) -> Optional[str]:
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return None


def free_memory_mb(root: str = "/sys/fs/cgroup", meminfo: str = "/proc/meminfo") -> tuple:
    """(free MB, source). The container's memory limit minus what it uses, not counting page cache the kernel can drop (cgroup v2, then v1); without
    a limit, the machine's MemAvailable."""
    cands = ((f"{root}/memory.max", f"{root}/memory.current", f"{root}/memory.stat", "inactive_file", "cgroup2"),
             (f"{root}/memory/memory.limit_in_bytes", f"{root}/memory/memory.usage_in_bytes", f"{root}/memory/memory.stat", "total_inactive_file", "cgroup1"))
    for max_p, cur_p, stat_p, key, src in cands:
        mx, cur = _read(max_p), _read(cur_p)
        if mx and cur and mx.isdigit() and len(mx) < 16 and cur.isdigit():
            inactive = 0
            for line in (_read(stat_p) or "").splitlines():
                k, _, v = line.partition(" ")
                if k == key and v.isdigit():
                    inactive = int(v)
            return max(int(mx) - int(cur) + inactive, 0) // 1048576, src
    for line in (_read(meminfo) or "").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) // 1024, "meminfo"
    return 99999, "unknown"


class SystemResources:
    def snapshot(self) -> Snapshot:
        free, src = free_memory_mb()
        try:
            load = os.getloadavg()[0] / max(os.cpu_count() or 1, 1)
        except OSError:
            load = 0.0
        return Snapshot(free, load, src)


def disk_percent(path: str = "/") -> Optional[float]:
    try:
        st = os.statvfs(path)
        total, free = st.f_blocks * st.f_frsize, st.f_bavail * st.f_frsize
        return round(100.0 * (total - free) / total, 1) if total else None
    except OSError:
        return None
