from __future__ import annotations

import uuid
from typing import Any


class OfficialIntegrationRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def get_cached(
        self, meeting_brief_id: Any, official_document_id: Any,
        integration_version: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, meeting_brief_id, official_document_id,
                   integration_version, status, integrated_brief, changes,
                   speaker_stats, usage_metadata, generated_at
            FROM meeting_official_integrations
            WHERE meeting_brief_id = %s AND official_document_id = %s
              AND integration_version = %s
            LIMIT 1
            """,
            (meeting_brief_id, official_document_id, integration_version),
        ).fetchone()
        return self._row(row)

    def latest(self, broadcast_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, meeting_brief_id, official_document_id,
                   integration_version, status, integrated_brief, changes,
                   speaker_stats, usage_metadata, generated_at
            FROM meeting_official_integrations
            WHERE broadcast_id = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (broadcast_id,),
        ).fetchone()
        return self._row(row)

    def latest_for_brief(self, meeting_brief_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, meeting_brief_id, official_document_id,
                   integration_version, status, integrated_brief, changes,
                   speaker_stats, usage_metadata, generated_at
            FROM meeting_official_integrations
            WHERE meeting_brief_id = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (meeting_brief_id,),
        ).fetchone()
        return self._row(row)

    def latest_for_brief_document(
        self, meeting_brief_id: Any, official_document_id: Any,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, meeting_brief_id, official_document_id,
                   integration_version, status, integrated_brief, changes,
                   speaker_stats, usage_metadata, generated_at
            FROM meeting_official_integrations
            WHERE meeting_brief_id = %s AND official_document_id = %s
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (meeting_brief_id, official_document_id),
        ).fetchone()
        return self._row(row)

    def latest_for_brief_stage(
        self, meeting_brief_id: Any, publication_stage: str,
        integration_version: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT integration.id, integration.broadcast_id,
                   integration.meeting_brief_id, integration.official_document_id,
                   integration.integration_version, integration.status,
                   integration.integrated_brief, integration.changes,
                   integration.speaker_stats, integration.usage_metadata,
                   integration.generated_at
            FROM meeting_official_integrations integration
            JOIN official_transcript_documents document
              ON document.id = integration.official_document_id
            WHERE integration.meeting_brief_id = %s
              AND document.publication_stage = %s
              AND integration.integration_version = %s
              AND integration.status = 'READY'
            ORDER BY integration.generated_at DESC, integration.id DESC
            LIMIT 1
            """,
            (meeting_brief_id, publication_stage, integration_version),
        ).fetchone()
        return self._row(row)

    def official_utterance_id_map(
        self, source_document_id: Any, target_document_id: Any,
    ) -> dict[str, str]:
        rows = self.connection.execute(
            """
            SELECT source.id, target.id
            FROM official_transcript_utterances source
            JOIN official_transcript_utterances target
              ON target.document_id = %s
             AND (
                 target.source_span_id = source.source_span_id
                 OR (
                     target.sequence_number = source.sequence_number
                     AND target.text_hash = source.text_hash
                 )
             )
            WHERE source.document_id = %s
            ORDER BY source.sequence_number
            """,
            (target_document_id, source_document_id),
        ).fetchall()
        return {str(source_id): str(target_id) for source_id, target_id in rows}

    def save(
        self, *, broadcast_id: Any, meeting_brief_id: Any,
        official_document_id: Any, integration_version: str, status: str,
        integrated_brief: dict[str, Any], changes: list[dict[str, Any]],
        speaker_stats: dict[str, Any], usage_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        row = self.connection.execute(
            """
            INSERT INTO meeting_official_integrations (
                id, broadcast_id, meeting_brief_id, official_document_id,
                integration_version, status, integrated_brief, changes,
                speaker_stats, usage_metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_brief_id, official_document_id, integration_version)
            DO UPDATE SET status = EXCLUDED.status,
                          integrated_brief = EXCLUDED.integrated_brief,
                          changes = EXCLUDED.changes,
                          speaker_stats = EXCLUDED.speaker_stats,
                          usage_metadata = EXCLUDED.usage_metadata,
                          generated_at = now()
            RETURNING id, broadcast_id, meeting_brief_id, official_document_id,
                      integration_version, status, integrated_brief, changes,
                      speaker_stats, usage_metadata, generated_at
            """,
            (
                uuid.uuid4(), broadcast_id, meeting_brief_id,
                official_document_id, integration_version, status,
                Jsonb(integrated_brief), Jsonb(changes), Jsonb(speaker_stats),
                Jsonb(usage_metadata),
            ),
        ).fetchone()
        item = self._row(row)
        if item is None:
            raise RuntimeError("official integration was not saved")
        return item

    def reviewed_speaker_decisions(
        self, meeting_brief_id: Any, document_id: Any,
    ) -> list[dict[str, Any]]:
        """Load only active reviews whose official utterance belongs to this doc."""
        rows = self.connection.execute(
            """
            SELECT review.point_id, review.source_text_hash,
                   review.official_utterance_id, review.replacement_summary,
                   review.reviewed_by, review.reason, review.matcher_version
            FROM official_speaker_review_decisions review
            JOIN official_transcript_utterances utterance
              ON utterance.id = review.official_utterance_id
             AND utterance.document_id = review.official_document_id
            WHERE review.meeting_brief_id = %s
              AND review.official_document_id = %s
              AND review.status = 'ACTIVE'
            """,
            (meeting_brief_id, document_id),
        ).fetchall()
        columns = (
            "point_id", "source_text_hash", "official_utterance_id",
            "replacement_summary", "reviewed_by", "reason", "matcher_version",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def replace_part_matches(
        self, document_id: Any, segments: list[dict[str, Any]],
        matches: list[dict[str, Any]], *, match_method: str,
    ) -> int:
        """Replace only this document's source-piece matches; retain history."""
        revision_ids = list(dict.fromkeys(
            segment["revision_id"] for segment in segments
            if int(segment.get("source_part_count") or 0) > 1
            and segment.get("revision_id")
        ))
        if not revision_ids:
            return 0
        self.connection.execute(
            """
            DELETE FROM transcript_official_part_matches
            WHERE official_document_id = %s
              AND transcript_revision_id = ANY(%s)
            """,
            (document_id, revision_ids),
        )
        inserted = 0
        for match in matches:
            if int(match.get("source_part_count") or 0) <= 1:
                continue
            row = self.connection.execute(
                """
                INSERT INTO transcript_official_part_matches (
                    official_document_id, transcript_revision_id,
                    source_part_index, source_text_hash,
                    official_utterance_id, match_method, match_confidence
                )
                SELECT %s, %s, %s, %s, utterance.id, %s, %s
                FROM official_transcript_utterances utterance
                WHERE utterance.id = %s AND utterance.document_id = %s
                ON CONFLICT (official_document_id, transcript_revision_id,
                             source_part_index)
                DO UPDATE SET source_text_hash = EXCLUDED.source_text_hash,
                              official_utterance_id = EXCLUDED.official_utterance_id,
                              match_method = EXCLUDED.match_method,
                              match_confidence = EXCLUDED.match_confidence,
                              created_at = now()
                RETURNING source_part_index
                """,
                (
                    document_id, match["revision_id"],
                    match["source_part_index"], match["source_text_hash"],
                    match_method, match["confidence"],
                    match["official_utterance_id"], document_id,
                ),
            ).fetchone()
            inserted += int(row is not None)
        return inserted

    def replace_segment_matches(
        self, matches: list[dict[str, Any]], *, match_method: str,
        document_id: Any, revision_ids: list[Any],
    ) -> int:
        current_ids = list(dict.fromkeys(revision_ids))
        if not current_ids:
            return 0
        self.connection.execute(
            """
            DELETE FROM transcript_official_reconciliations reconciliation
            USING official_transcript_utterances utterance
            WHERE reconciliation.official_utterance_id = utterance.id
              AND utterance.document_id = %s
              AND reconciliation.match_method = %s
              AND reconciliation.transcript_revision_id = ANY(%s)
            """,
            (document_id, match_method, current_ids),
        )
        inserted = 0
        for match in matches:
            row = self.connection.execute(
                """
                INSERT INTO transcript_official_reconciliations (
                    id, transcript_revision_id, official_utterance_id,
                    reconciliation_status, match_method, match_confidence
                )
                SELECT %s, %s, utterance.id, 'MATCHED', %s, %s
                FROM official_transcript_utterances utterance
                WHERE utterance.id = %s AND utterance.document_id = %s
                ON CONFLICT (transcript_revision_id, official_utterance_id, match_method)
                DO UPDATE SET reconciliation_status = 'MATCHED',
                              match_confidence = EXCLUDED.match_confidence,
                              created_at = now()
                RETURNING id
                """,
                (
                    uuid.uuid4(), match["revision_id"],
                    match_method, match["confidence"],
                    match["official_utterance_id"], document_id,
                ),
            ).fetchone()
            inserted += int(row is not None)
        broadcast_rows = self.connection.execute(
            """
            SELECT DISTINCT segment.broadcast_id
            FROM transcript_segment_revisions revision
            JOIN transcript_segments segment ON segment.id = revision.segment_id
            WHERE revision.id = ANY(%s)
            """,
            (current_ids,),
        ).fetchall()
        if broadcast_rows:
            from .live_repository import LiveRepository

            LiveRepository(self.connection).refresh_official_context_stats(
                row[0] for row in broadcast_rows
            )
        return inserted

    @staticmethod
    def _row(row: Any) -> dict[str, Any] | None:
        if not row:
            return None
        columns = (
            "integration_id", "broadcast_id", "meeting_brief_id",
            "official_document_id", "integration_version", "status",
            "integrated_brief", "changes", "speaker_stats",
            "usage_metadata", "generated_at",
        )
        return dict(zip(columns, row, strict=True))
