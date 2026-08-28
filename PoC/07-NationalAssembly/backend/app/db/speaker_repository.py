from __future__ import annotations

import uuid
from typing import Any


class SpeakerRepository:
    """Keep human-readable speaker corrections separate from source captions."""

    def __init__(self, connection: Any):
        self.connection = connection

    def options(self, broadcast_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT COALESCE(segment.speaker_label, '') AS source_speaker_label,
                   speaker_override.display_name, COUNT(*) AS segment_count,
                   MIN(segment.first_received_at), MAX(segment.last_received_at)
            FROM transcript_segments segment
            LEFT JOIN transcript_speaker_overrides speaker_override
              ON speaker_override.broadcast_id = segment.broadcast_id
             AND speaker_override.source_speaker_label = COALESCE(segment.speaker_label, '')
            WHERE segment.broadcast_id = %s
            GROUP BY COALESCE(segment.speaker_label, ''), speaker_override.display_name
            ORDER BY MIN(segment.first_received_at), COALESCE(segment.speaker_label, '')
            """,
            (broadcast_id,),
        ).fetchall()
        columns = (
            "source_speaker_label", "display_name", "segment_count",
            "first_at", "last_at",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def override_map(self, broadcast_ids: list[uuid.UUID]) -> dict[tuple[Any, str], str]:
        if not broadcast_ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT broadcast_id, source_speaker_label, display_name
            FROM transcript_speaker_overrides WHERE broadcast_id = ANY(%s)
            """,
            (broadcast_ids,),
        ).fetchall()
        return {(row[0], row[1]): row[2] for row in rows}

    def set_override(
        self, broadcast_id: uuid.UUID, source_speaker_label: str, display_name: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            INSERT INTO transcript_speaker_overrides (
                id, broadcast_id, source_speaker_label, display_name
            )
            SELECT %s, %s, %s, %s
            WHERE EXISTS (
                SELECT 1 FROM transcript_segments
                WHERE broadcast_id = %s AND COALESCE(speaker_label, '') = %s
            )
            ON CONFLICT (broadcast_id, source_speaker_label) DO UPDATE SET
                display_name = EXCLUDED.display_name, updated_at = now()
            RETURNING source_speaker_label, display_name, updated_at
            """,
            (
                uuid.uuid4(), broadcast_id, source_speaker_label, display_name,
                broadcast_id, source_speaker_label,
            ),
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            ("source_speaker_label", "display_name", "updated_at"), row, strict=True,
        ))

    def delete_override(self, broadcast_id: uuid.UUID, source_speaker_label: str) -> bool:
        row = self.connection.execute(
            """
            DELETE FROM transcript_speaker_overrides
            WHERE broadcast_id = %s AND source_speaker_label = %s
            RETURNING id
            """,
            (broadcast_id, source_speaker_label),
        ).fetchone()
        return row is not None

    def collection_overview(self, *, days: int = 7) -> dict[str, Any]:
        row = self.connection.execute(
            """
            WITH recent_broadcasts AS (
                SELECT * FROM live_broadcasts
                WHERE source_system = 'assembly.webcast.go.kr'
                  AND detected_at >= now() - (%s * interval '1 day')
            ), ordered_segments AS (
                SELECT segment.broadcast_id, segment.speaker_label,
                       lag(segment.speaker_label) OVER (
                           PARTITION BY segment.broadcast_id
                           ORDER BY segment.last_received_at, segment.source_segment_id
                       ) AS previous_speaker
                FROM transcript_segments segment
                JOIN recent_broadcasts broadcast ON broadcast.id = segment.broadcast_id
            )
            SELECT COUNT(DISTINCT broadcast.id), MIN(broadcast.detected_at),
                   MAX(COALESCE(broadcast.ended_at, broadcast.last_seen_at)),
                   COALESCE(SUM(EXTRACT(epoch FROM (
                       COALESCE(broadcast.ended_at, broadcast.last_seen_at)
                       - broadcast.detected_at
                   ))), 0),
                   (SELECT COUNT(*) FROM ordered_segments),
                   (SELECT COUNT(*) FROM ordered_segments
                    WHERE speaker_label IS DISTINCT FROM previous_speaker),
                   (SELECT COUNT(DISTINCT (broadcast_id, speaker_label))
                    FROM ordered_segments),
                   (SELECT COUNT(*) FROM transcript_speaker_overrides speaker_override
                    JOIN recent_broadcasts recent ON recent.id = speaker_override.broadcast_id)
            FROM recent_broadcasts broadcast
            """,
            (days,),
        ).fetchone()
        columns = (
            "broadcast_count", "period_start", "period_end", "captured_seconds",
            "segment_count", "utterance_count", "source_speaker_count",
            "named_speaker_count",
        )
        return dict(zip(columns, row, strict=True))
