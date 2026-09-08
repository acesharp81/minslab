from __future__ import annotations

import uuid
from typing import Any

from psycopg.types.json import Jsonb


class WatchOperationsRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def review_queue(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT verification.id, verification.status, verification.verification_method,
                   verification.verified_at, match.excerpt, match.speaker_label,
                   utterance.text, utterance.speaker_name,
                   broadcast.title, publication.official_url,
                   decision.decision, decision.note, decision.reviewed_by,
                   decision.reviewed_at
            FROM watch_match_official_verifications verification
            JOIN watch_matches match ON match.id = verification.match_id
            JOIN watch_sessions session ON session.id = match.session_id
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            JOIN official_transcript_documents document
              ON document.id = verification.official_document_id
            LEFT JOIN broadcast_official_publications publication
              ON publication.id = document.publication_id
            LEFT JOIN official_transcript_utterances utterance
              ON utterance.id = verification.official_utterance_id
            LEFT JOIN LATERAL (
                SELECT item.decision, item.note, item.reviewed_by, item.reviewed_at
                FROM watch_review_decisions item
                WHERE item.verification_id = verification.id
                ORDER BY item.reviewed_at DESC LIMIT 1
            ) decision ON true
            WHERE verification.status = 'REVIEW_REQUIRED'
               OR decision.decision = 'DEFER'
            ORDER BY verification.verified_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
        columns = (
            "verification_id", "automatic_status", "verification_method",
            "verified_at", "live_excerpt", "live_speaker", "official_text",
            "official_speaker", "meeting_title", "official_source_url",
            "latest_decision", "latest_note", "reviewed_by", "reviewed_at",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def decide(
        self, verification_id: uuid.UUID, *, decision: str, note: str,
        reviewed_by: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT status FROM watch_match_official_verifications WHERE id = %s
            """,
            (verification_id,),
        ).fetchone()
        if not row:
            return None
        decision_id = uuid.uuid4()
        result = self.connection.execute(
            """
            INSERT INTO watch_review_decisions (
                id, verification_id, automatic_status, decision, note, reviewed_by
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id, verification_id, automatic_status, decision, note,
                      reviewed_by, reviewed_at
            """,
            (decision_id, verification_id, row[0], decision, note, reviewed_by),
        ).fetchone()
        return dict(zip((
            "decision_id", "verification_id", "automatic_status", "decision",
            "note", "reviewed_by", "reviewed_at",
        ), result, strict=True))

    def audit_broadcast(self, broadcast_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH revisions AS (
                SELECT revision.event_cursor, revision.is_final,
                       revision.received_at, segment.id AS segment_id,
                       lag(revision.received_at) OVER (
                           ORDER BY revision.event_cursor
                       ) AS previous_received_at
                FROM transcript_segment_revisions revision
                JOIN transcript_segments segment ON segment.id = revision.segment_id
                WHERE segment.broadcast_id = %s
            ), segment_states AS (
                SELECT segment_id,
                       bool_or(is_final) AS has_final,
                       bool_or(NOT is_final) AS has_partial
                FROM revisions GROUP BY segment_id
            )
            SELECT broadcast.id, broadcast.title, broadcast.lifecycle_status,
                   COUNT(revisions.event_cursor),
                   COUNT(*) FILTER (WHERE revisions.is_final),
                   COUNT(*) FILTER (WHERE NOT revisions.is_final),
                   COUNT(DISTINCT revisions.event_cursor),
                   COUNT(*) FILTER (
                       WHERE revisions.previous_received_at IS NOT NULL
                         AND revisions.received_at - revisions.previous_received_at
                             > interval '2 minutes'
                   ),
                   COALESCE((SELECT COUNT(*) FROM segment_states
                             WHERE has_final AND has_partial), 0),
                   EXISTS (
                       SELECT 1 FROM meeting_official_integrations integration
                       WHERE integration.broadcast_id = broadcast.id
                         AND integration.status = 'READY'
                   )
            FROM live_broadcasts broadcast
            LEFT JOIN revisions ON true
            WHERE broadcast.id = %s
            GROUP BY broadcast.id
            """,
            (broadcast_id, broadcast_id),
        ).fetchone()
        if not row:
            return None
        (
            identity, title, lifecycle_status, revision_count, final_count,
            partial_count, distinct_cursors, reconnect_gap_count,
            partial_to_final_segments, official_ready,
        ) = row
        checks = {
            "caption_contract_observed": revision_count > 0,
            "final_revision_observed": final_count > 0,
            "cursor_unique": revision_count == distinct_cursors,
            "partial_to_final_observed": partial_to_final_segments > 0,
            "reconnect_gap_free": reconnect_gap_count == 0,
            "official_reconciliation_ready": bool(official_ready),
            "official_reconciliation_applicable": lifecycle_status == "ENDED",
        }
        if not revision_count:
            status = "PENDING"
        elif not checks["final_revision_observed"] or not checks["cursor_unique"]:
            status = "REVIEW_REQUIRED"
        elif lifecycle_status == "ENDED" and not official_ready:
            status = "PENDING"
        else:
            status = "PASS"
        self.connection.execute(
            """
            INSERT INTO live_regression_audits (
                id, broadcast_id, status, checks, revision_count, final_count,
                partial_count, reconnect_gap_count
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                uuid.uuid4(), identity, status, Jsonb(checks), revision_count,
                final_count, partial_count, reconnect_gap_count,
            ),
        )
        return {
            "broadcast_id": identity, "title": title,
            "lifecycle_status": lifecycle_status, "status": status,
            "checks": checks, "revision_count": int(revision_count),
            "final_count": int(final_count), "partial_count": int(partial_count),
            "reconnect_gap_count": int(reconnect_gap_count),
        }

    def audit_recent(self, *, limit: int = 20, include_test: bool = False) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id FROM live_broadcasts
            WHERE (%s OR source_system NOT IN (
              'poc07.demo', 'poc07.test', 'poc07.replay.local', 'poc07.replay.kakao'
            ))
            ORDER BY COALESCE(ended_at, last_seen_at, detected_at, created_at) DESC LIMIT %s
            """,
            (include_test, limit),
        ).fetchall()
        return [item for row in rows if (item := self.audit_broadcast(row[0]))]

    def latest_audits(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (audit.broadcast_id)
                   audit.broadcast_id, broadcast.title, broadcast.lifecycle_status,
                   audit.status, audit.checks, audit.revision_count,
                   audit.final_count, audit.partial_count,
                   audit.reconnect_gap_count, audit.audited_at
            FROM live_regression_audits audit
            JOIN live_broadcasts broadcast ON broadcast.id = audit.broadcast_id
            ORDER BY audit.broadcast_id, audit.audited_at DESC
            """
        ).fetchall()
        columns = (
            "broadcast_id", "title", "lifecycle_status", "status", "checks",
            "revision_count", "final_count", "partial_count",
            "reconnect_gap_count", "audited_at",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        return sorted(items, key=lambda item: item["audited_at"], reverse=True)[:limit]
