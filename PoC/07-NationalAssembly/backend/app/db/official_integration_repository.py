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

    def replace_segment_matches(
        self, matches: list[dict[str, Any]], *, match_method: str,
    ) -> int:
        if not matches:
            return 0
        revision_ids = list({match["revision_id"] for match in matches})
        self.connection.execute(
            """
            DELETE FROM transcript_official_reconciliations
            WHERE match_method = %s AND transcript_revision_id = ANY(%s)
            """,
            (match_method, revision_ids),
        )
        inserted = 0
        for match in matches:
            row = self.connection.execute(
                """
                INSERT INTO transcript_official_reconciliations (
                    id, transcript_revision_id, official_utterance_id,
                    reconciliation_status, match_method, match_confidence
                ) VALUES (%s, %s, %s, 'MATCHED', %s, %s)
                ON CONFLICT (transcript_revision_id, official_utterance_id, match_method)
                DO UPDATE SET reconciliation_status = 'MATCHED',
                              match_confidence = EXCLUDED.match_confidence,
                              created_at = now()
                RETURNING id
                """,
                (
                    uuid.uuid4(), match["revision_id"],
                    match["official_utterance_id"], match_method,
                    match["confidence"],
                ),
            ).fetchone()
            inserted += int(row is not None)
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
