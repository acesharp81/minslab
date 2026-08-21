from __future__ import annotations

import argparse
import json
import os
import socket
import time
from datetime import datetime, timezone

from ..services.broadcast_review import (
    CLASSIFICATION_METHOD,
    GENERATOR_VERSION,
    build_broadcast_review,
)


def process_one(database_url: str, worker_id: str) -> dict[str, object] | None:
    from ..db.connection import connect
    from ..db.review_repository import ReviewRepository

    with connect(database_url) as connection:
        broadcast = ReviewRepository(connection).claim_ended_broadcast(worker_id)
    if broadcast is None:
        return None
    try:
        with connect(database_url) as connection:
            repository = ReviewRepository(connection)
            segments = repository.final_caption_revisions(broadcast["broadcast_id"])
            topics = build_broadcast_review(broadcast, segments)
            review_id = repository.save_review(
                broadcast,
                topics,
                generator_version=GENERATOR_VERSION,
                classification_method=CLASSIFICATION_METHOD,
                generated_at=datetime.now(timezone.utc),
            )
        return {
            "event": "review.completed" if review_id else "review.no_content",
            "broadcast_id": str(broadcast["broadcast_id"]),
            "final_segments": len(segments),
            "topics": len(topics),
        }
    except Exception:
        with connect(database_url) as connection:
            ReviewRepository(connection).fail_review(broadcast["broadcast_id"], worker_id)
        raise


def main() -> None:
    from ..config import get_settings
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(description="Build PROVISIONAL reviews for ended broadcasts")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.interval <= 300:
        parser.error("interval must be between 1 and 300 seconds")
    settings = get_settings()
    apply_migrations(settings.database_url)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        try:
            result = process_one(settings.database_url, worker_id)
            if result is not None:
                print(json.dumps(result, ensure_ascii=False), flush=True)
                continue
        except Exception as exc:
            print(json.dumps({"event": "review.error", "error": type(exc).__name__}), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
