"""Dedicated common-analysis worker."""

from __future__ import annotations

import signal
import time
import traceback

from master_press.service import common_worker_tick


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        try:
            progressed = bool(common_worker_tick(False))
            time.sleep(0.25 if progressed else 2.0)
        except Exception as error:
            print(f"Master Press common worker failed: {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
            time.sleep(5.0)


if __name__ == "__main__":
    main()
