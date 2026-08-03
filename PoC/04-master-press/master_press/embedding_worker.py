"""Dedicated local article-embedding worker."""

from __future__ import annotations

import signal
import time
import traceback

from master_press.service import embedding_worker_tick


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        try:
            result = embedding_worker_tick()
            # Keep draining while work exists; back off when the queue is empty.
            time.sleep(0.25 if result else 5.0)
        except Exception as error:
            print(
                f"Master Press embedding worker failed: {type(error).__name__}: {error}",
                flush=True,
            )
            traceback.print_exc()
            time.sleep(5.0)


if __name__ == "__main__":
    main()
