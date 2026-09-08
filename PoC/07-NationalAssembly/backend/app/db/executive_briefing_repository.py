from __future__ import annotations

from collections.abc import Iterable
from typing import Any


class ExecutiveBriefingRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def live_briefs_by_official_ids(
        self, official_briefing_ids: Iterable[str],
    ) -> dict[str, dict[str, Any]]:
        identifiers = list(dict.fromkeys(
            str(value) for value in official_briefing_ids if value
        ))
        if not identifiers:
            return {}
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (match.official_briefing_id)
                   match.official_briefing_id, broadcast.id, broadcast.title,
                   brief.brief, brief.authority_status, brief.generated_at
            FROM executive_official_matches match
            JOIN live_broadcasts broadcast ON broadcast.id = match.broadcast_id
            JOIN LATERAL (
                SELECT meeting.brief, meeting.authority_status,
                       meeting.generated_at, meeting.provider
                FROM meeting_briefs meeting
                WHERE meeting.broadcast_id = broadcast.id
                ORDER BY (meeting.provider = 'mistral') DESC,
                         meeting.generated_at DESC
                LIMIT 1
            ) brief ON true
            WHERE match.official_briefing_id = ANY(%s)
            ORDER BY match.official_briefing_id,
                     brief.generated_at DESC, broadcast.detected_at DESC
            """,
            (identifiers,),
        ).fetchall()
        return {
            str(official_id): {
                "broadcast_id": str(broadcast_id),
                "meeting_title": str(title or ""),
                "brief": dict(brief or {}),
                "authority_status": str(authority_status or "PROVISIONAL"),
                "generated_at": generated_at,
            }
            for (
                official_id, broadcast_id, title, brief,
                authority_status, generated_at,
            ) in rows
        }
