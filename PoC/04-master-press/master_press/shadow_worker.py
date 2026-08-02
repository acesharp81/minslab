"""Low-priority OpenAI shadow evaluator, isolated from the web process."""

from __future__ import annotations

import signal
import time

from master_press.service import shadow_worker_tick


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        try:
            result = shadow_worker_tick()
            time.sleep(4.0 if result else 15.0)
        except Exception as error:
            print(f"Master Press shadow worker failed: {type(error).__name__}", flush=True)
            time.sleep(20.0)



if __name__ == "__main__":
    main()
