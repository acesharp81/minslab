"""Read host CPU and memory usage from the Linux proc filesystem."""

from __future__ import annotations

import time
from pathlib import Path


PROC_STAT = Path("/proc/stat")
PROC_MEMINFO = Path("/proc/meminfo")


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


def read_memory_percent(path: Path = PROC_MEMINFO) -> float:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, remainder = line.partition(":")
        if separator:
            values[key] = int(remainder.strip().split()[0])
    total = values.get("MemTotal", 0)
    available = values.get("MemAvailable", values.get("MemFree", 0))
    if total <= 0:
        raise ValueError("/proc/meminfo 메모리 정보를 읽을 수 없습니다.")
    return round(max(0.0, min(100.0, (1.0 - available / total) * 100.0)), 2)


def read_system_usage(cpu_sample_seconds: float = 0.15) -> dict:
    before = read_cpu_snapshot()
    time.sleep(max(0.05, float(cpu_sample_seconds)))
    after = read_cpu_snapshot()
    return {
        "cpu_percent": calculate_cpu_percent(before, after),
        "memory_percent": read_memory_percent(),
    }
