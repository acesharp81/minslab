"""Main Master Press pipeline worker, isolated from the web process."""

from __future__ import annotations

import signal
import time
import traceback

from master_press.service import case_worker_tick, common_worker_tick, embedding_worker_tick, worker_tick


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        try:
            cycle = worker_tick() or {}
            progressed = bool(cycle.get("organizations") or cycle.get("cases"))
            progressed = bool(common_worker_tick()) or progressed
            progressed = bool(embedding_worker_tick()) or progressed
            progressed = bool(case_worker_tick(False)) or progressed
            time.sleep(12.0 if progressed else 30.0)
        except Exception as error:
            print(
                f"Master Press worker failed: {type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()
            time.sleep(10.0)



if __name__ == "__main__":
    main()
