from __future__ import annotations

import uuid
from typing import Any

from ..domain.scope import NATIONAL_ASSEMBLY_BODIES, TARGET_COMMITTEES

class OfficialIntegrationJobRepository:
    """Durable, retryable queue for LIVE-to-official reconciliation."""

    def __init__(self, connection: Any):
        self.connection = connection

    def sync_pending(self, integration_version: str, *, limit: int = 100) -> int:
        rows = self.connection.execute(
            """
            WITH candidates AS (
                SELECT broadcast.id AS broadcast_id,
                       brief.id AS meeting_brief_id,
                       document.id AS official_document_id
                FROM live_broadcasts broadcast
                JOIN LATERAL (
                    SELECT id
                    FROM meeting_briefs
                    WHERE broadcast_id = broadcast.id
                    ORDER BY (provider IN ('mistral', 'openrouter')) DESC,
                             generated_at DESC, id DESC
                    LIMIT 1
                ) brief ON true
                JOIN LATERAL (
                    SELECT document.id
                    FROM broadcast_official_publications publication
                    JOIN official_transcript_documents document
                      ON document.meeting_id = publication.meeting_id
                     AND document.conference_id = publication.conference_id
                     AND document.extraction_status = 'EXTRACTED'
                    WHERE publication.broadcast_id = broadcast.id
                    ORDER BY (document.publication_stage = 'FINAL') DESC,
                             EXISTS (
                                 SELECT 1 FROM official_transcript_utterances utterance
                                 JOIN official_utterance_annotations annotation
                                   ON annotation.utterance_id = utterance.id
                                 WHERE utterance.document_id = document.id
                             ) DESC,
                             document.retrieved_at DESC, document.id DESC
                    LIMIT 1
                ) document ON true
                WHERE broadcast.lifecycle_status = 'ENDED'
                  AND (
                        broadcast.institution <> 'LEGISLATURE'
                        OR broadcast.committee_name = ANY(%s)
                      )
                  AND NOT EXISTS (
                      SELECT 1
                      FROM meeting_official_integrations integration
                      WHERE integration.meeting_brief_id = brief.id
                        AND integration.official_document_id = document.id
                        AND integration.integration_version = %s
                        AND integration.status = 'READY'
                        AND COALESCE(
                              integration.usage_metadata->>'reuse_reason', ''
                            ) <> 'TEMPORARY_UPDATE_DEFERRED'
                  )
                ORDER BY broadcast.ended_at DESC NULLS LAST, broadcast.id
                LIMIT %s
            )
            INSERT INTO meeting_official_integration_jobs (
                id, broadcast_id, meeting_brief_id, official_document_id,
                integration_version, status
            )
            SELECT gen_random_uuid(), broadcast_id, meeting_brief_id,
                   official_document_id, %s, 'PENDING'
            FROM candidates
            ON CONFLICT (meeting_brief_id, official_document_id, integration_version)
            DO UPDATE SET status = 'PENDING', last_error = NULL,
                          next_attempt_at = NULL, lease_owner = NULL,
                          lease_expires_at = NULL, completed_at = NULL,
                          updated_at = now()
            WHERE meeting_official_integration_jobs.status = 'READY'
            RETURNING id
            """,
            (
                [*TARGET_COMMITTEES, *NATIONAL_ASSEMBLY_BODIES],
                integration_version,
                limit,
                integration_version,
            ),
        ).fetchall()
        return len(rows)

    def claim(self, worker_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            UPDATE meeting_official_integration_jobs job
            SET status = 'PROCESSING', lease_owner = %s,
                lease_expires_at = now() + interval '30 minutes',
                attempt_count = attempt_count + 1,
                started_at = COALESCE(started_at, now()), updated_at = now()
            WHERE job.id = (
                SELECT candidate.id
                FROM meeting_official_integration_jobs candidate
                WHERE candidate.status = 'PENDING'
                   OR (candidate.status = 'RETRY_WAIT'
                       AND candidate.next_attempt_at <= now())
                   OR (candidate.status = 'PROCESSING'
                       AND candidate.lease_expires_at < now())
                ORDER BY
                    CASE candidate.status WHEN 'PENDING' THEN 0 ELSE 1 END,
                    candidate.next_attempt_at NULLS FIRST,
                    candidate.created_at, candidate.id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING job.id, job.broadcast_id, job.meeting_brief_id,
                      job.official_document_id, job.integration_version,
                      job.attempt_count, job.last_error
            """,
            (worker_id,),
        ).fetchone()
        if not row:
            return None
        columns = (
            "job_id", "broadcast_id", "meeting_brief_id",
            "official_document_id", "integration_version", "attempt_count",
            "last_error",
        )
        return dict(zip(columns, row, strict=True))

    def complete(self, job_id: Any) -> None:
        self.connection.execute(
            """
            UPDATE meeting_official_integration_jobs
            SET status = 'READY', last_error = NULL, next_attempt_at = NULL,
                lease_owner = NULL, lease_expires_at = NULL,
                completed_at = now(), updated_at = now()
            WHERE id = %s
            """,
            (job_id,),
        )

    def retry(self, job_id: Any, error: str) -> None:
        self.connection.execute(
            """
            UPDATE meeting_official_integration_jobs
            SET status = 'RETRY_WAIT', last_error = %s,
                next_attempt_at = now() + make_interval(
                    secs => LEAST(3600, 30 * (2 ^ LEAST(attempt_count, 7)))
                ),
                lease_owner = NULL, lease_expires_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (error[:160], job_id),
        )

    def latest(self, broadcast_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, status, attempt_count, last_error, next_attempt_at,
                   lease_expires_at, started_at, completed_at, created_at, updated_at
            FROM meeting_official_integration_jobs
            WHERE broadcast_id = %s
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (broadcast_id,),
        ).fetchone()
        if not row:
            return None
        columns = (
            "job_id", "status", "attempt_count", "last_error",
            "next_attempt_at", "lease_expires_at", "started_at",
            "completed_at", "created_at", "updated_at",
        )
        return dict(zip(columns, row, strict=True))
