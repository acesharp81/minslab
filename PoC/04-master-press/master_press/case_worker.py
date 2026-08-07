"""Dedicated primary case-batch worker."""

from __future__ import annotations

import argparse
import signal
import time
import traceback

from master_press.service import case_worker_tick


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=("mini", "oss", "single"), default="mini")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while _running:
        try:
            progressed = bool(case_worker_tick(False, slot=args.slot))
            time.sleep(0.5 if progressed else 3.0)
        except Exception as error:
            print(f"Master Press case worker failed: {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
            time.sleep(5.0)


if __name__ == "__main__":
    main()
