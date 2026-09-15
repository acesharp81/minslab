from __future__ import annotations

import fcntl
import threading
from contextlib import contextmanager
from pathlib import Path


class BatchAlreadyRunning(RuntimeError):
    pass


_registry_guard = threading.Lock()
_local_locks: dict[str, threading.Lock] = {}


@contextmanager
def exclusive_collection_lock(data_dir: Path):
    """Prevent overlapping collection from HTTP, CLI, timers, and processes."""
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_path = (data_dir / "poc08-collection.lock").resolve()
    with _registry_guard:
        local_lock = _local_locks.setdefault(str(lock_path), threading.Lock())
    if not local_lock.acquire(blocking=False):
        raise BatchAlreadyRunning("다른 수집·분석 배치가 이미 실행 중입니다.")
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise BatchAlreadyRunning("다른 수집·분석 배치가 이미 실행 중입니다.") from exc
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
            local_lock.release()
