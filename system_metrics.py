"""Read host CPU and memory usage from the Linux proc filesystem."""

from __future__ import annotations

import os
import time
from pathlib import Path


PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")
PROC_PRESSURE_MEMORY = Path("/proc/pressure/memory")
PROC_PRESSURE_IO = Path("/proc/pressure/io")
PROC_VMSTAT = Path("/proc/vmstat")
PROC_SELF_CGROUP = Path("/proc/self/cgroup")
PROC_SELF_STATUS = Path("/proc/self/status")
CGROUP_ROOT = Path("/sys/fs/cgroup")


def read_cpu_snapshot(path: Path = PROC_STAT) -> tuple[int, int]:
    fields = path.read_text(encoding="utf-8").splitlines()[0].split()
    if not fields or fields[0] != "cpu":
        raise ValueError("/proc/stat CPU 정보를 읽을 수 없습니다.")
    values = [int(value) for value in fields[1:9]]
    if len(values) < 4:
        raise ValueError("/proc/stat CPU 정보가 충분하지 않습니다.")
    total = sum(values)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return total, idle


def calculate_cpu_percent(before: tuple[int, int], after: tuple[int, int]) -> float:
    total_delta = after[0] - before[0]
    idle_delta = after[1] - before[1]
    if total_delta <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1.0 - idle_delta / total_delta) * 100.0)), 2)


def read_memory_details(path: Path = PROC_MEMINFO) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, remainder = line.partition(":")
        if separator:
            values[key] = int(remainder.strip().split()[0])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if total <= 0:
        raise ValueError("/proc/meminfo 메모리 정보를 읽을 수 없습니다.")
    swap_total = values.get("SwapTotal", 0)
    swap_free = values.get("SwapFree", 0)
    return {
        "memory_percent": round(
            max(0.0, min(100.0, (1.0 - available / total) * 100.0)),
            2,
        ),
        "memory_total_bytes": total * 1024,
        "memory_available_bytes": available * 1024,
        "swap_percent": round(
            max(0.0, min(100.0, (1.0 - swap_free / swap_total) * 100.0)),
            2,
        ) if swap_total > 0 else 0.0,
    }


def read_memory_percent(path: Path = PROC_MEMINFO) -> float:
    return float(read_memory_details(path)["memory_percent"])


def read_memory_pressure_avg10(path: Path = PROC_PRESSURE_MEMORY) -> float:
    try:
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        values = dict(item.split("=", 1) for item in first_line.split()[1:] if "=" in item)
        return max(0.0, float(values.get("avg10", 0.0)))
    except (OSError, ValueError, IndexError):
        return 0.0


def read_io_pressure_avg10(path: Path = PROC_PRESSURE_IO) -> float:
    return read_memory_pressure_avg10(path)


def read_filesystem_usage(path: Path = Path("/")) -> dict:
    usage = os.statvfs(path)
    total_bytes = usage.f_blocks * usage.f_frsize
    available_bytes = usage.f_bavail * usage.f_frsize
    used_percent = (
        (1.0 - available_bytes / total_bytes) * 100.0 if total_bytes > 0 else 0.0
    )
    inode_total = usage.f_files
    inode_available = usage.f_favail
    inode_used_percent = (
        (1.0 - inode_available / inode_total) * 100.0 if inode_total > 0 else 0.0
    )
    return {
        "disk_total_bytes": max(0, int(total_bytes)),
        "disk_available_bytes": max(0, int(available_bytes)),
        "disk_used_percent": round(max(0.0, min(100.0, used_percent)), 2),
        "inode_used_percent": round(max(0.0, min(100.0, inode_used_percent)), 2),
    }


def read_oom_kills(path: Path = PROC_VMSTAT) -> int:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition(" ")
            if key == "oom_kill":
                return max(0, int(value.strip()))
    except (OSError, ValueError):
        pass
    return 0


def read_service_memory_bytes(
    cgroup_path: Path = PROC_SELF_CGROUP,
    cgroup_root: Path = CGROUP_ROOT,
    status_path: Path = PROC_SELF_STATUS,
) -> int:
    try:
        for line in cgroup_path.read_text(encoding="utf-8").splitlines():
            hierarchy, controllers, relative = line.split(":", 2)
            if hierarchy == "0" and not controllers:
                current_path = cgroup_root / relative.lstrip("/") / "memory.current"
                return max(0, int(current_path.read_text(encoding="utf-8").strip()))
    except (OSError, ValueError):
        pass
    try:
        for line in status_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("VmRSS:"):
                return max(0, int(line.split()[1]) * 1024)
    except (OSError, ValueError, IndexError):
        pass
    return 0


def read_system_usage(cpu_sample_seconds: float = 0.15) -> dict:
    before = read_cpu_snapshot()
    time.sleep(max(0.05, float(cpu_sample_seconds)))
    after = read_cpu_snapshot()
    memory = read_memory_details()
    total_bytes = int(memory["memory_total_bytes"])
    service_bytes = read_service_memory_bytes()
    return {
        "cpu_percent": calculate_cpu_percent(before, after),
        **memory,
        **read_filesystem_usage(),
        "memory_pressure_avg10": round(read_memory_pressure_avg10(), 2),
        "io_pressure_avg10": round(read_io_pressure_avg10(), 2),
        "oom_kills": read_oom_kills(),
        "service_memory_bytes": service_bytes,
        "service_memory_percent": round(
            service_bytes / total_bytes * 100.0,
            3,
        ) if total_bytes > 0 else 0.0,
    }
