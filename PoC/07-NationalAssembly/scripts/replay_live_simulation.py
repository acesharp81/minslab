#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "backend"))

from app.experiments.live_replay import load_and_replay  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a synthetic live caption stream")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_DIR / "backend/tests/fixtures/synthetic_live_broadcast.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_DIR / "web/data/live_magazine.json",
    )
    parser.add_argument("--trace", action="store_true", help="print caption events in replay order")
    args = parser.parse_args()

    def emit(event: dict[str, object]) -> None:
        state = "FINAL" if event["is_final"] else "PARTIAL"
        print(f"[{event['at_ms']:>5}ms] {state:<7} {event['broadcast_id']} {event['segment_id']} · {event['text']}")

    result = load_and_replay(args.input, args.output, emit=emit if args.trace else None)
    print(json.dumps({
        "simulation_id": result["simulation_id"],
        "events": result["event_count"],
        "segments": result["segment_count"],
        "magazine_cards": len(result["magazine"]),
        "output": str(args.output),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
