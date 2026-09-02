from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Any

from ..config import get_settings
from ..db.connection import connect
from ..db.watch_repository import WatchRepository
from ..db.watch_test_repository import WatchTestRepository


LOGGER = logging.getLogger(__name__)


def process_revisions(connection: Any, limit: int = 200) -> int:
    state = connection.execute(
        "SELECT event_cursor FROM watch_worker_state WHERE worker_name = 'watch-alerts' FOR UPDATE"
    ).fetchone()
    cursor = int(state[0]) if state else 0
    rows = connection.execute(
        """
        SELECT revision.event_cursor, revision.id, segment.id, segment.broadcast_id,
               revision.text, revision.speaker_label, revision.is_final,
               revision.received_at, broadcast.title, broadcast.institution,
               broadcast.committee_name, broadcast.source_system
        FROM transcript_segment_revisions revision
        JOIN transcript_segments segment ON segment.id = revision.segment_id
        JOIN live_broadcasts broadcast ON broadcast.id = segment.broadcast_id
        WHERE revision.event_cursor > %s
        ORDER BY revision.event_cursor LIMIT %s
        """,
        (cursor, limit),
    ).fetchall()
    repository = WatchRepository(connection)
    changed_broadcasts: set[Any] = set()
    columns = (
        "cursor", "revision_id", "segment_id", "broadcast_id", "text",
        "speaker_label", "is_final", "received_at", "title", "institution",
        "committee_name", "source_system",
    )
    for row in rows:
        revision = dict(zip(columns, row, strict=True))
        repository.process_revision(revision)
        changed_broadcasts.add(revision["broadcast_id"])
        cursor = max(cursor, int(revision["cursor"]))
    for broadcast_id in changed_broadcasts:
        repository.rebuild_bundle_matches(broadcast_id)
    if rows:
        connection.execute(
            """
            UPDATE watch_worker_state SET event_cursor = %s, updated_at = now()
            WHERE worker_name = 'watch-alerts'
            """,
            (cursor,),
        )
    return len(rows)


def run_once(database_url: str, *, digest_enabled: bool = True) -> dict[str, int]:
    emitted = revisions = 0
    with connect(database_url) as connection:
        while WatchTestRepository(connection).emit_due(datetime.now(timezone.utc)):
            emitted += 1
        revisions = process_revisions(connection)
        repository = WatchRepository(connection)
        completion = repository.finalize_ended_sessions(digest_enabled=digest_enabled)
        verified = repository.refresh_official_verifications()
    return {
        "test_segments_emitted": emitted,
        "revisions_processed": revisions,
        **completion,
        "official_matches_verified": verified,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="관심주제 감지 및 테스트 방송 워커")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(level=settings.national_assembly_log_level)
    while True:
        try:
            result = run_once(
                settings.database_url,
                digest_enabled=settings.watch_digest_enabled,
            )
            if any(result.values()):
                LOGGER.info("watch worker processed %s", result)
        except Exception:  # noqa: BLE001 - persistent worker retries after logging
            LOGGER.exception("watch worker iteration failed")
        if args.once:
            return
        time.sleep(max(0.25, args.interval))


if __name__ == "__main__":
    main()
