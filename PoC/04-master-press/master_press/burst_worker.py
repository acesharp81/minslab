"""Backlog-triggered GPT worker for common jobs or complete case batches."""

from __future__ import annotations

import argparse
import signal
import time
import traceback

from master_press.service import get_service


_running = True


def _stop(_signum, _frame) -> None:
    global _running
    _running = False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("common", "case"), required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    active = False
    below_stop_count = 0
    while _running:
        try:
            service = get_service()
            pending = (
                service.store.pending_article_analysis_jobs(include_deferred=True)
                if args.stage == "common"
                else service.store.pending_case_evaluation_bundles(include_deferred=True)
            )
            start_threshold = service.selected_burst_threshold()
            stop_threshold = service.selected_burst_stop_threshold()
            primary_available = service.stage_primary_available(args.stage)
            if not service.burst_provider_available():
                active = False
                time.sleep(3.0)
                continue
            if not active:
                if pending < start_threshold and primary_available:
                    time.sleep(3.0)
                    continue
                active = True
                below_stop_count = 0
            if pending <= stop_threshold and primary_available:
                below_stop_count += 1
                if below_stop_count >= 2:
                    active = False
                    time.sleep(3.0)
                    continue
            else:
                below_stop_count = 0
            model = service.selected_burst_model()
            provider = service._provider_for_switchable_llm_model(model)
            if args.stage == "common":
                result = service.process_next_article_analysis(provider, model, "burst")
            else:
                result = service.process_next_case_evaluation(provider, model, "burst")
            time.sleep(0.5 if result else 2.0)
        except Exception as error:
            print(f"Master Press {args.stage} burst worker failed: {type(error).__name__}: {error}", flush=True)
            traceback.print_exc()
            time.sleep(10.0)


if __name__ == "__main__":
    main()
