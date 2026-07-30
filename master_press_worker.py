from __future__ import annotations

import fcntl
import os
import signal
import sys
import time
from pathlib import Path

from env_utils import load_project_env


load_project_env()

BASE_DIR = Path(__file__).resolve().parent
# This is deliberately the same lock used by main.py.  Either the web process
# or this standalone runner may own the pipeline, never both.
LOCK_PATH = BASE_DIR / "data" / "master_press_workers.lock"

STOP = False


def _stop_handler(_signum, _frame):
    global STOP
    STOP = True


def acquire_lock():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate(0)
    handle.write(f"pid={os.getpid()} started_at={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    handle.flush()
    return handle


def main() -> int:
    signal.signal(signal.SIGINT, _stop_handler)
    signal.signal(signal.SIGTERM, _stop_handler)

    lock_handle = acquire_lock()
    if lock_handle is None:
        print("master_press_worker: another worker is already running", file=sys.stderr)
        return 1

    from importlib import util

    backend_path = BASE_DIR / "PoC" / "04-master-press" / "backend.py"
    spec = util.spec_from_file_location("master_press_backend_worker", backend_path)
    module = util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    print("master_press_worker: started", flush=True)
    try:
        while not STOP:
            progressed = False
            try:
                cycle = module.worker_tick()
                progressed = bool((cycle or {}).get("organizations") or (cycle or {}).get("cases"))
                progressed = bool(module.common_worker_tick()) or progressed
                progressed = bool(module.embedding_worker_tick()) or progressed
                progressed = bool(module.case_worker_tick(False)) or progressed
            except Exception as error:
                text = str(error).lower()
                print(f"master_press_worker: cycle failed: {error}", file=sys.stderr, flush=True)
                time.sleep(8 if "locked" in text else 4)
                continue
            time.sleep(12 if progressed else 30)
    finally:
        try:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        lock_handle.close()
        print("master_press_worker: stopped", flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
