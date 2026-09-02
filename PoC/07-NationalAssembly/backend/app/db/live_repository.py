from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .schedule_repository import SourceVersionInput


@dataclass(frozen=True, slots=True)
class LiveBroadcastObservation:
    institution: str
    external_id: str
    committee_name: str | None
    title: str | None
    caption_source_status: str
    caption_websocket_url: str | None
    thumbnail_url: str | None
    observed_at: datetime
    source: SourceVersionInput
    source_system: str = "assembly.webcast.go.kr"
    media_stream_url: str | None = None


@dataclass(frozen=True, slots=True)
class CaptionRevision:
    source_segment_id: str
    text: str
    speaker_label: str | None
    is_final: bool
    received_at: datetime
    source_payload: dict[str, Any]
    source: SourceVersionInput
    start_offset_ms: int | None = None
    end_offset_ms: int | None = None


class LiveRepository:
    """Persist the server-owned LIVE lifecycle independently of any browser."""

    source_system = "assembly.webcast.go.kr"

    def __init__(self, connection: Any):
        self.connection = connection

    def observe_broadcast(self, observation: LiveBroadcastObservation) -> uuid.UUID:

        document_id = self._upsert_document(
            observation.source, observation.source_system
        )
        version_id = self._upsert_source_version(document_id, observation.source)
        candidate_id = uuid.uuid4()
        row = self.connection.execute(
            """
            INSERT INTO live_broadcasts (
                id, institution, source_system, external_id, committee_name, title,
                lifecycle_status, caption_source_status, detected_at, last_seen_at,
                latest_source_document_version_id, caption_websocket_url, capture_status
                , thumbnail_url, media_stream_url
            ) VALUES (%s, %s, %s, %s, %s, %s, 'LIVE', %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_system, external_id) DO UPDATE SET
                committee_name = EXCLUDED.committee_name,
                title = EXCLUDED.title,
                lifecycle_status = 'LIVE',
                caption_source_status = EXCLUDED.caption_source_status,
                last_seen_at = EXCLUDED.last_seen_at,
                ended_at = NULL,
                latest_source_document_version_id = EXCLUDED.latest_source_document_version_id,
                caption_websocket_url = EXCLUDED.caption_websocket_url,
                capture_status = CASE
                    WHEN live_broadcasts.capture_status = 'CAPTURING' THEN 'CAPTURING'
                    ELSE EXCLUDED.capture_status
                END,
                thumbnail_url = COALESCE(EXCLUDED.thumbnail_url, live_broadcasts.thumbnail_url),
                media_stream_url = COALESCE(EXCLUDED.media_stream_url, live_broadcasts.media_stream_url),
                review_status = 'PENDING', review_lease_owner = NULL,
                review_lease_expires_at = NULL,
                updated_at = now()
            RETURNING id
            """,
            (
                candidate_id,
                observation.institution,
                observation.source_system,
                observation.external_id,
                observation.committee_name,
                observation.title,
                observation.caption_source_status,
                observation.observed_at,
                observation.observed_at,
                version_id,
                observation.caption_websocket_url,
                (
                    "READY"
                    if observation.caption_websocket_url
                    else "AUDIO_READY"
                    if observation.media_stream_url
                    else "UNAVAILABLE"
                ),
                observation.thumbnail_url,
                observation.media_stream_url,
            ),
        ).fetchone()
        broadcast_id = row[0]
        self.connection.execute(
            """
            INSERT INTO live_broadcast_source_versions (
                broadcast_id, source_document_version_id, observed_at
            ) VALUES (%s, %s, %s)
            ON CONFLICT (broadcast_id, source_document_version_id) DO NOTHING
            """,
            (broadcast_id, version_id, observation.observed_at),
        )
        return broadcast_id

    def finish_broadcast(self, broadcast_id: uuid.UUID, ended_at: datetime) -> bool:
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET lifecycle_status = 'ENDED', ended_at = %s, last_seen_at = %s,
                capture_status = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN 'POST_PROCESSING' ELSE 'COMPLETED' END,
                capture_lease_owner = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN capture_lease_owner ELSE NULL END,
                capture_lease_expires_at = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN capture_lease_expires_at ELSE NULL END,
                review_status = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN 'PENDING' ELSE 'READY' END,
                updated_at = now()
            WHERE id = %s AND lifecycle_status = 'LIVE'
            RETURNING id
            """,
            (ended_at, ended_at, broadcast_id),
        ).fetchone()
        return row is not None

    def finish_poll(
        self, active_external_ids: Iterable[str], observed_at: datetime
    ) -> int:
        return self.finish_source_poll(
            self.source_system,
            active_external_ids,
            observed_at,
        )

    def finish_source_poll(
        self,
        source_system: str,
        active_external_ids: Iterable[str],
        observed_at: datetime,
    ) -> int:
        active = list(active_external_ids)
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET lifecycle_status = 'ENDED', ended_at = %s,
                capture_status = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN 'POST_PROCESSING' ELSE 'COMPLETED' END,
                capture_lease_owner = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN capture_lease_owner ELSE NULL END,
                capture_lease_expires_at = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN capture_lease_expires_at ELSE NULL END,
                review_status = CASE
                    WHEN institution = 'EXECUTIVE' AND capture_status = 'CAPTURING'
                    THEN 'PENDING' ELSE 'READY' END,
                updated_at = now()
            WHERE source_system = %s AND lifecycle_status = 'LIVE'
              AND NOT (external_id = ANY(%s))
            RETURNING id
            """,
            (observed_at, source_system, active),
        ).fetchall()
        return len(row)

    def claim_caption_capture(
        self, worker_id: str, lease_seconds: int = 45
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT id FROM live_broadcasts
                WHERE lifecycle_status = 'LIVE' AND caption_websocket_url IS NOT NULL
                  AND capture_status IN ('READY', 'RETRY_WAIT', 'CAPTURING')
                  AND (capture_lease_expires_at IS NULL OR capture_lease_expires_at < now())
                ORDER BY detected_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE live_broadcasts broadcast
            SET capture_status = 'CAPTURING', capture_lease_owner = %s,
                capture_lease_expires_at = now() + (%s * interval '1 second'),
                updated_at = now()
            FROM candidate WHERE broadcast.id = candidate.id
            RETURNING broadcast.id, broadcast.external_id,
                      broadcast.caption_websocket_url, broadcast.lifecycle_status
            """,
            (worker_id, lease_seconds),
        ).fetchone()
        if not row:
            return None
        return dict(
            zip(
                (
                    "broadcast_id",
                    "external_id",
                    "caption_websocket_url",
                    "lifecycle_status",
                ),
                row,
                strict=True,
            )
        )

    def claim_executive_audio_capture(
        self, worker_id: str, lease_seconds: int = 180
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT id FROM live_broadcasts
                WHERE institution = 'EXECUTIVE'
                  AND source_system = 'ktv.go.kr'
                  AND (
                    (
                      lifecycle_status = 'LIVE'
                      AND media_stream_url IS NOT NULL
                      AND capture_status IN ('AUDIO_READY', 'RETRY_WAIT', 'CAPTURING')
                    )
                    OR (
                      lifecycle_status = 'ENDED'
                      AND capture_status = 'POST_PROCESSING'
                    )
                  )
                  AND (capture_lease_expires_at IS NULL OR capture_lease_expires_at < now())
                ORDER BY (lifecycle_status = 'LIVE') DESC, detected_at
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE live_broadcasts broadcast
            SET capture_status = CASE
                    WHEN broadcast.lifecycle_status = 'ENDED' THEN 'POST_PROCESSING'
                    ELSE 'CAPTURING'
                END,
                capture_lease_owner = %s,
                capture_lease_expires_at = now() + (%s * interval '1 second'),
                updated_at = now()
            FROM candidate WHERE broadcast.id = candidate.id
            RETURNING broadcast.id, broadcast.external_id,
                      broadcast.media_stream_url, broadcast.lifecycle_status
            """,
            (worker_id, lease_seconds),
        ).fetchone()
        if not row:
            return None
        return dict(
            zip(
                ("broadcast_id", "external_id", "media_stream_url", "lifecycle_status"),
                row,
                strict=True,
            )
        )

    def heartbeat_capture(
        self, broadcast_id: uuid.UUID, worker_id: str, lease_seconds: int = 45
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET capture_lease_expires_at = now() + (%s * interval '1 second'),
                updated_at = now()
            WHERE id = %s AND lifecycle_status = 'LIVE'
              AND capture_status = 'CAPTURING' AND capture_lease_owner = %s
            RETURNING id
            """,
            (lease_seconds, broadcast_id, worker_id),
        ).fetchone()
        return row is not None

    def release_caption_capture(
        self,
        broadcast_id: uuid.UUID,
        worker_id: str,
        *,
        retry: bool,
        failed: bool = False,
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET capture_status = CASE
                    WHEN lifecycle_status = 'ENDED' AND %s THEN 'FAILED'
                    WHEN lifecycle_status = 'ENDED' AND %s THEN 'POST_PROCESSING'
                    WHEN lifecycle_status = 'ENDED' THEN 'COMPLETED'
                    WHEN %s THEN 'RETRY_WAIT' ELSE 'FAILED'
                END,
                capture_lease_owner = NULL, capture_lease_expires_at = NULL,
                review_status = CASE
                    WHEN lifecycle_status = 'ENDED' AND %s THEN 'FAILED'
                    WHEN lifecycle_status = 'ENDED' AND %s THEN 'PENDING'
                    WHEN lifecycle_status = 'ENDED' THEN 'READY'
                    ELSE review_status
                END,
                reconnect_attempts = reconnect_attempts + CASE WHEN %s THEN 1 ELSE 0 END,
                updated_at = now()
            WHERE id = %s AND capture_lease_owner = %s
            RETURNING id
            """,
            (failed, retry, retry, failed, retry, retry, broadcast_id, worker_id),
        ).fetchone()
        return row is not None

    def append_caption_revision(
        self, broadcast_id: uuid.UUID, revision: CaptionRevision
    ) -> tuple[uuid.UUID, bool]:
        from psycopg.types.json import Jsonb

        source_system_row = self.connection.execute(
            "SELECT source_system FROM live_broadcasts WHERE id = %s",
            (broadcast_id,),
        ).fetchone()
        source_system = (
            source_system_row[0] if source_system_row else self.source_system
        )
        document_id = self._upsert_document(revision.source, source_system)
        source_version_id = self._upsert_source_version(
            document_id, revision.source, authority_status="LIVE"
        )

        segment_row = self.connection.execute(
            """
            INSERT INTO transcript_segments (
                id, broadcast_id, source_segment_id, speaker_label,
                start_offset_ms, end_offset_ms, current_text, is_final,
                first_received_at, last_received_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id, source_segment_id) DO UPDATE SET
                speaker_label = CASE
                    WHEN EXCLUDED.last_received_at < transcript_segments.last_received_at
                      OR (transcript_segments.is_final AND NOT EXCLUDED.is_final)
                    THEN transcript_segments.speaker_label
                    ELSE COALESCE(EXCLUDED.speaker_label, transcript_segments.speaker_label)
                END,
                start_offset_ms = COALESCE(EXCLUDED.start_offset_ms, transcript_segments.start_offset_ms),
                end_offset_ms = COALESCE(EXCLUDED.end_offset_ms, transcript_segments.end_offset_ms),
                current_text = CASE
                    WHEN EXCLUDED.last_received_at < transcript_segments.last_received_at
                      OR (transcript_segments.is_final AND NOT EXCLUDED.is_final)
                    THEN transcript_segments.current_text
                    ELSE EXCLUDED.current_text
                END,
                is_final = transcript_segments.is_final OR EXCLUDED.is_final,
                last_received_at = GREATEST(
                    transcript_segments.last_received_at, EXCLUDED.last_received_at
                ),
                updated_at = now()
            RETURNING id
            """,
            (
                uuid.uuid4(),
                broadcast_id,
                revision.source_segment_id,
                revision.speaker_label,
                revision.start_offset_ms,
                revision.end_offset_ms,
                revision.text,
                revision.is_final,
                revision.received_at,
                revision.received_at,
            ),
        ).fetchone()
        segment_id = segment_row[0]
        content_hash = hashlib.sha256(
            json.dumps(
                {
                    "text": revision.text,
                    "speaker_label": revision.speaker_label,
                    "is_final": revision.is_final,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        inserted = self.connection.execute(
            """
            INSERT INTO transcript_segment_revisions (
                id, segment_id, revision_number, content_hash, text,
                speaker_label, is_final, received_at, source_payload,
                source_document_version_id
            )
            SELECT %s, %s, COALESCE(MAX(revision_number), 0) + 1, %s, %s,
                   %s, %s, %s, %s, %s
            FROM transcript_segment_revisions WHERE segment_id = %s
            ON CONFLICT (segment_id, content_hash) DO NOTHING
            RETURNING id
            """,
            (
                uuid.uuid4(),
                segment_id,
                content_hash,
                revision.text,
                revision.speaker_label,
                revision.is_final,
                revision.received_at,
                Jsonb(revision.source_payload),
                source_version_id,
                segment_id,
            ),
        ).fetchone()
        self.connection.execute(
            """
            UPDATE live_broadcasts
            SET last_caption_received_at = %s, updated_at = now()
            WHERE id = %s
            """,
            (revision.received_at, broadcast_id),
        )
        return segment_id, inserted is not None

    def active_transcript_snapshot(
        self,
        committee_name: str | None = None,
        broadcast_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        return self._transcript_snapshot(
            committee_name,
            lifecycle_status="LIVE",
            broadcast_id=broadcast_id,
        )

    def recent_transcript_snapshot(
        self, committee_name: str | None = None
    ) -> dict[str, Any]:
        return self._transcript_snapshot(committee_name, lifecycle_status="ENDED")

    def ended_transcript_snapshot(self, broadcast_id: uuid.UUID) -> dict[str, Any]:
        return self.broadcast_transcript_snapshot(
            broadcast_id, lifecycle_status="ENDED"
        )

    def broadcast_transcript_snapshot(
        self,
        broadcast_id: uuid.UUID,
        *,
        lifecycle_status: str,
    ) -> dict[str, Any]:
        return self._transcript_snapshot(
            None,
            lifecycle_status=lifecycle_status,
            broadcast_id=broadcast_id,
        )

    def test_transcript_snapshot(
        self,
        broadcast_id: uuid.UUID,
        *,
        lifecycle_status: str,
    ) -> dict[str, Any]:
        return self._transcript_snapshot(
            None,
            lifecycle_status=lifecycle_status,
            broadcast_id=broadcast_id,
            include_test=True,
        )

    def broadcast_reconciliation_details(
        self, broadcast_id: uuid.UUID
    ) -> dict[uuid.UUID, dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (reconciliation.transcript_revision_id)
                   reconciliation.transcript_revision_id,
                   reconciliation.reconciliation_status,
                   reconciliation.match_method, reconciliation.match_confidence,
                   utterance.id, utterance.sequence_number, utterance.speaker_name,
                   utterance.speaker_role, utterance.text,
                   utterance.source_locator, document.publication_stage,
                   document.authority_status
            FROM transcript_official_reconciliations reconciliation
            JOIN transcript_segment_revisions revision
              ON revision.id = reconciliation.transcript_revision_id
            JOIN transcript_segments segment ON segment.id = revision.segment_id
            LEFT JOIN official_transcript_utterances utterance
              ON utterance.id = reconciliation.official_utterance_id
            LEFT JOIN official_transcript_documents document
              ON document.id = utterance.document_id
            WHERE segment.broadcast_id = %s
            ORDER BY reconciliation.transcript_revision_id,
                     reconciliation.created_at DESC, reconciliation.id DESC
            """,
            (broadcast_id,),
        ).fetchall()
        columns = (
            "revision_id",
            "status",
            "match_method",
            "match_confidence",
            "official_utterance_id",
            "official_sequence_number",
            "official_speaker_name",
            "official_speaker_role",
            "official_text",
            "source_locator",
            "publication_stage",
            "official_authority_status",
        )
        result: dict[uuid.UUID, dict[str, Any]] = {}
        for row in rows:
            item = dict(zip(columns, row, strict=True))
            revision_id = item.pop("revision_id")
            locator = item.get("source_locator")
            item["source_locator"] = locator if isinstance(locator, dict) else None
            result[revision_id] = item
        return result

    def list_ended_broadcasts(
        self,
        committee_name: str | None = None,
        *,
        limit: int = 5,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        committee_filter = ""
        if committee_name:
            committee_filter = (
                " AND broadcast.institution = 'LEGISLATURE'"
                " AND broadcast.committee_name = %s"
            )
            parameters.append(committee_name)
        parameters.append(limit)
        parameters.append(offset)
        rows = self.connection.execute(
            f"""
            SELECT broadcast.id, broadcast.external_id, broadcast.institution,
                   broadcast.committee_name,
                   broadcast.title, broadcast.lifecycle_status, broadcast.source_system,
                   broadcast.caption_source_status, broadcast.capture_status,
                   broadcast.detected_at, broadcast.ended_at,
                   broadcast.last_caption_received_at, broadcast.thumbnail_url,
                   broadcast.review_status, broadcast.official_status,
                   broadcast.official_last_checked_at,
                   resume_activity.possible_resume_at,
                   executive_match.official_briefing_id,
                   executive_match.match_method,
                   caption_stats.segment_count, caption_stats.utterance_count,
                   caption_stats.source_speaker_count,
                   (SELECT COUNT(*) FROM transcript_speaker_overrides speaker_override
                    WHERE speaker_override.broadcast_id = broadcast.id)
                       AS named_speaker_count,
                   official_activity.generated_at AS official_integration_updated_at,
                   GREATEST(
                       COALESCE(broadcast.ended_at, broadcast.detected_at),
                       COALESCE(brief_activity.generated_at, '-infinity'::timestamptz),
                       COALESCE(official_activity.generated_at, '-infinity'::timestamptz)
                   ) AS result_updated_at
            FROM live_broadcasts broadcast
            LEFT JOIN LATERAL (
                SELECT MAX(
                    (schedule.scheduled_date + schedule.start_time)
                    AT TIME ZONE 'Asia/Seoul'
                ) AS possible_resume_at
                FROM schedule_entries schedule
                WHERE broadcast.institution = 'LEGISLATURE'
                  AND schedule.committee_name = broadcast.committee_name
                  AND schedule.scheduled_date =
                      (broadcast.ended_at AT TIME ZONE 'Asia/Seoul')::date
                  AND schedule.start_time >
                      (broadcast.ended_at AT TIME ZONE 'Asia/Seoul')::time
            ) resume_activity ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS segment_count,
                       COUNT(*) FILTER (
                           WHERE ordered.speaker_label IS DISTINCT FROM ordered.previous_speaker
                       ) AS utterance_count,
                       COUNT(DISTINCT ordered.speaker_label) AS source_speaker_count
                FROM (
                    SELECT segment.speaker_label,
                           lag(segment.speaker_label) OVER (
                               ORDER BY segment.last_received_at, segment.source_segment_id
                           ) AS previous_speaker
                    FROM transcript_segments segment
                    WHERE segment.broadcast_id = broadcast.id
                ) ordered
            ) caption_stats ON true
            LEFT JOIN LATERAL (
                SELECT brief.generated_at
                FROM meeting_briefs brief
                WHERE brief.broadcast_id = broadcast.id
                ORDER BY (brief.provider = 'mistral') DESC,
                         brief.generated_at DESC, brief.id DESC
                LIMIT 1
            ) brief_activity ON true
            LEFT JOIN LATERAL (
                SELECT integration.generated_at
                FROM meeting_official_integrations integration
                WHERE integration.broadcast_id = broadcast.id
                  AND integration.status = 'READY'
                ORDER BY integration.generated_at DESC, integration.id DESC
                LIMIT 1
            ) official_activity ON true
            LEFT JOIN executive_official_matches executive_match
              ON executive_match.broadcast_id = broadcast.id
            WHERE broadcast.lifecycle_status = 'ENDED'
              AND broadcast.source_system NOT IN ('poc07.demo', 'poc07.test')
              {committee_filter}
            ORDER BY broadcast.detected_at DESC, broadcast.id DESC
            LIMIT %s OFFSET %s
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id",
            "external_id",
            "institution",
            "committee_name",
            "title",
            "lifecycle_status",
            "source_system",
            "caption_source_status",
            "capture_status",
            "detected_at",
            "ended_at",
            "last_caption_received_at",
            "thumbnail_url",
            "review_status",
            "official_status",
            "official_last_checked_at",
            "possible_resume_at",
            "official_briefing_id",
            "executive_match_method",
            "segment_count",
            "utterance_count",
            "source_speaker_count",
            "named_speaker_count",
            "official_integration_updated_at",
            "result_updated_at",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        return items

    def broadcast_official_context(
        self, broadcast_id: uuid.UUID
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT broadcast.official_status, broadcast.official_last_checked_at,
                   broadcast.review_status, publication.conference_id,
                   publication.official_url, publication.pdf_url,
                   publication.reconciliation_status, publication.body_contract_status,
                   document.publication_stage, document.authority_status,
                   document.utterance_count,
                   (SELECT COUNT(*) FROM transcript_segments segment
                    WHERE segment.broadcast_id = broadcast.id AND segment.is_final)
                       AS final_segment_count,
                   (SELECT COUNT(DISTINCT reconciliation.transcript_revision_id)
                    FROM transcript_official_reconciliations reconciliation
                    JOIN transcript_segment_revisions revision
                      ON revision.id = reconciliation.transcript_revision_id
                    JOIN transcript_segments segment ON segment.id = revision.segment_id
                    WHERE segment.broadcast_id = broadcast.id
                      AND reconciliation.reconciliation_status = 'MATCHED')
                       AS matched_segment_count
            FROM live_broadcasts broadcast
            LEFT JOIN LATERAL (
                SELECT id, conference_id, official_url, pdf_url,
                       reconciliation_status, body_contract_status
                FROM broadcast_official_publications
                WHERE broadcast_id = broadcast.id
                ORDER BY matched_at DESC, id DESC LIMIT 1
            ) publication ON true
            LEFT JOIN LATERAL (
                SELECT publication_stage, authority_status, utterance_count
                FROM official_transcript_documents
                WHERE publication_id = publication.id
                ORDER BY retrieved_at DESC, id DESC LIMIT 1
            ) document ON true
            WHERE broadcast.id = %s AND broadcast.institution = 'LEGISLATURE'
              AND broadcast.lifecycle_status = 'ENDED'
            """,
            (broadcast_id,),
        ).fetchone()
        if not row:
            return None
        columns = (
            "official_status",
            "official_last_checked_at",
            "review_status",
            "conference_id",
            "official_url",
            "official_pdf_url",
            "reconciliation_status",
            "body_contract_status",
            "publication_stage",
            "official_authority_status",
            "official_utterance_count",
            "final_segment_count",
            "matched_segment_count",
        )
        item = dict(zip(columns, row, strict=True))
        item["unmatched_segment_count"] = max(
            0, item["final_segment_count"] - item["matched_segment_count"]
        )
        return item

    def broadcast_official_material(
        self,
        broadcast_id: uuid.UUID,
    ) -> dict[str, Any]:
        document_row = self.connection.execute(
            """
            SELECT document.id, document.conference_id, document.publication_stage,
                   document.authority_status, document.status_text, document.title,
                   document.utterance_count, document.retrieved_at,
                   publication.official_url, publication.pdf_url
            FROM broadcast_official_publications publication
            JOIN LATERAL (
                SELECT id, conference_id, publication_stage, authority_status,
                       status_text, title, utterance_count, retrieved_at
                FROM official_transcript_documents
                WHERE publication_id = publication.id
                ORDER BY
                    (publication_stage = 'FINAL') DESC,
                    EXISTS (
                        SELECT 1
                        FROM official_transcript_utterances candidate_utterance
                        JOIN official_utterance_annotations candidate_annotation
                          ON candidate_annotation.utterance_id = candidate_utterance.id
                        WHERE candidate_utterance.document_id =
                              official_transcript_documents.id
                    ) DESC,
                    retrieved_at DESC, id DESC
                LIMIT 1
            ) document ON true
            WHERE publication.broadcast_id = %s
            ORDER BY publication.matched_at DESC, publication.id DESC
            LIMIT 1
            """,
            (broadcast_id,),
        ).fetchone()
        if not document_row:
            return {"document": None, "utterances": []}
        document_columns = (
            "document_id",
            "conference_id",
            "publication_stage",
            "authority_status",
            "status_text",
            "title",
            "utterance_count",
            "retrieved_at",
            "official_url",
            "official_pdf_url",
        )
        document = dict(zip(document_columns, document_row, strict=True))
        rows = self.connection.execute(
            """
            SELECT utterance.id, utterance.sequence_number,
                   utterance.speaker_name, utterance.speaker_role,
                   utterance.text, utterance.source_locator,
                   COALESCE(annotation.topics, ARRAY[]::text[]),
                   COALESCE(annotation.ministries, ARRAY[]::text[]),
                   COALESCE(annotation.utterance_kind, 'OTHER'),
                   COALESCE(annotation.evidence_keywords, ARRAY[]::text[]),
                   COALESCE(
                       array_agg(DISTINCT agenda.agenda_name)
                           FILTER (WHERE agenda.agenda_name IS NOT NULL),
                       ARRAY[]::text[]
                   ) AS agenda_titles
            FROM official_transcript_utterances utterance
            LEFT JOIN LATERAL (
                SELECT topics, ministries, utterance_kind, evidence_keywords
                FROM official_utterance_annotations
                WHERE utterance_id = utterance.id
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
            ) annotation ON true
            LEFT JOIN official_utterance_agenda_links agenda_link
              ON agenda_link.utterance_id = utterance.id
             AND agenda_link.reconciliation_status = 'MATCHED'
            LEFT JOIN agenda_items agenda ON agenda.id = agenda_link.agenda_item_id
            WHERE utterance.document_id = %s
            GROUP BY utterance.id, utterance.sequence_number,
                     utterance.speaker_name, utterance.speaker_role,
                     utterance.text, utterance.source_locator,
                     annotation.topics, annotation.ministries,
                     annotation.utterance_kind, annotation.evidence_keywords
            ORDER BY utterance.sequence_number
            """,
            (document["document_id"],),
        ).fetchall()
        columns = (
            "utterance_id",
            "sequence_number",
            "speaker_name",
            "speaker_role",
            "text",
            "source_locator",
            "topics",
            "ministries",
            "utterance_kind",
            "evidence_keywords",
            "agenda_titles",
        )
        return {
            "document": document,
            "utterances": [dict(zip(columns, row, strict=True)) for row in rows],
        }

    def list_open_follow_up_tasks(
        self,
        committee_name: str | None = None,
        *,
        ministry: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        committee_filter = ""
        if committee_name:
            committee_filter = " AND broadcast.committee_name = %s"
            parameters.append(committee_name)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT ON (segment.id)
                   broadcast.id, broadcast.title, broadcast.committee_name,
                   broadcast.lifecycle_status, broadcast.ended_at,
                   broadcast.source_system, revision.id, revision.text,
                   revision.speaker_label, revision.received_at,
                   revision.source_payload
            FROM transcript_segments segment
            JOIN transcript_segment_revisions revision ON revision.segment_id = segment.id
            JOIN live_broadcasts broadcast ON broadcast.id = segment.broadcast_id
            WHERE broadcast.institution = 'LEGISLATURE'
              AND broadcast.source_system <> 'poc07.demo'
              AND revision.is_final = true
              AND (broadcast.lifecycle_status = 'LIVE'
                   OR broadcast.ended_at >= now() - interval '30 days')
              {committee_filter}
            ORDER BY segment.id, revision.event_cursor DESC
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id",
            "broadcast_title",
            "committee_name",
            "lifecycle_status",
            "ended_at",
            "source_system",
            "evidence_revision_id",
            "evidence_text",
            "speaker_label",
            "received_at",
            "source_payload",
        )
        evidence = [dict(zip(columns, row, strict=True)) for row in rows]
        evidence.sort(key=lambda item: item["received_at"])
        tasks: dict[tuple[Any, str], dict[str, Any]] = {}
        resolved_topics: set[tuple[Any, str]] = set()
        for item in evidence:
            payload = item.pop("source_payload", {})
            insight = payload.get("insight") if isinstance(payload, dict) else None
            if not isinstance(insight, dict):
                continue
            topic_id = str(insight.get("topic_id") or "other-live-topic")
            topic_key = (item["broadcast_id"], topic_id)
            if (
                insight.get("resolution") is True
                or insight.get("task_status") == "RESOLVED"
            ):
                resolved_topics.add(topic_key)
                for key in [
                    key
                    for key in tasks
                    if key[0] == item["broadcast_id"]
                    and tasks[key]["topic_id"] == topic_id
                ]:
                    tasks.pop(key, None)
                continue
            task_text = insight.get("task")
            if not isinstance(task_text, str) or insight.get("task_status") != "OPEN":
                continue
            resolved_topics.discard(topic_key)
            ministries = [
                value
                for value in insight.get("ministries", [])
                if isinstance(value, str) and value.strip()
            ]
            if ministry and ministry not in ministries:
                continue
            task_id = str(insight.get("task_id") or item["evidence_revision_id"])
            tasks[(item["broadcast_id"], task_id)] = {
                **item,
                "task_id": task_id,
                "task": task_text,
                "topic_id": topic_id,
                "topic": str(insight.get("topic") or "기타 현안"),
                "ministries": ministries,
                "authority_status": "PROVISIONAL",
            }
        result = sorted(
            tasks.values(), key=lambda item: item["received_at"], reverse=True
        )
        return result[:limit]

    def _transcript_snapshot(
        self,
        committee_name: str | None,
        *,
        lifecycle_status: str,
        broadcast_id: uuid.UUID | None = None,
        include_test: bool = False,
    ) -> dict[str, Any]:
        if lifecycle_status not in {"LIVE", "ENDED"}:
            raise ValueError("unsupported lifecycle status")
        parameters: list[Any] = [lifecycle_status]
        committee_filter = ""
        if committee_name:
            committee_filter = " AND committee_name = %s"
            parameters.append(committee_name)
        broadcast_filter = ""
        if broadcast_id:
            broadcast_filter = " AND id = %s"
            parameters.append(broadcast_id)
        order_and_limit = (
            "ORDER BY detected_at, external_id"
            if lifecycle_status == "LIVE"
            else "ORDER BY ended_at DESC NULLS LAST, detected_at DESC LIMIT 1"
        )
        test_filter = "" if include_test else "AND source_system <> 'poc07.test'"
        broadcasts = self.connection.execute(
            f"""
            SELECT id, external_id, committee_name, title, lifecycle_status,
                   source_system, capture_status, detected_at, last_seen_at,
                   last_caption_received_at, thumbnail_url, ended_at
            FROM live_broadcasts
            WHERE lifecycle_status = %s
              AND source_system <> 'poc07.demo'
              {test_filter}
            {committee_filter}
            {broadcast_filter}
            {order_and_limit}
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id",
            "external_id",
            "committee_name",
            "title",
            "lifecycle_status",
            "source_system",
            "capture_status",
            "detected_at",
            "last_seen_at",
            "last_caption_received_at",
            "thumbnail_url",
            "ended_at",
        )
        broadcast_items = [dict(zip(columns, row, strict=True)) for row in broadcasts]
        broadcast_ids = [item["broadcast_id"] for item in broadcast_items]
        if not broadcast_ids:
            return {"broadcasts": [], "segments": [], "cursor": 0}

        cursor = self.connection.execute(
            """
            SELECT COALESCE(MAX(revision.event_cursor), 0)
            FROM transcript_segment_revisions revision
            JOIN transcript_segments segment ON segment.id = revision.segment_id
            WHERE segment.broadcast_id = ANY(%s)
            """,
            (broadcast_ids,),
        ).fetchone()[0]
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (segment.id)
                   segment.id, revision.id, segment.broadcast_id, segment.source_segment_id,
                   revision.event_cursor, revision.text, revision.speaker_label,
                   revision.is_final, revision.received_at, revision.content_hash,
                   revision.source_payload
            FROM transcript_segments segment
            JOIN transcript_segment_revisions revision ON revision.segment_id = segment.id
            WHERE segment.broadcast_id = ANY(%s) AND revision.event_cursor <= %s
            ORDER BY segment.id, revision.event_cursor DESC
            """,
            (broadcast_ids, cursor),
        ).fetchall()
        segment_columns = (
            "segment_id",
            "revision_id",
            "broadcast_id",
            "source_segment_id",
            "cursor",
            "text",
            "speaker_label",
            "is_final",
            "received_at",
            "content_hash",
            "source_payload",
        )
        segments = [dict(zip(segment_columns, row, strict=True)) for row in rows]
        for item in segments:
            source_payload = item.pop("source_payload", {})
            speaker_segments = (
                source_payload.get("speaker_segments")
                if isinstance(source_payload, dict)
                else None
            )
            item["source_speaker_segments"] = (
                speaker_segments if isinstance(speaker_segments, list) else []
            )
            hint = (
                source_payload.get("insight")
                if isinstance(source_payload, dict)
                else None
            )
            item["insight_hint"] = hint if isinstance(hint, dict) else None
        segments.sort(key=lambda item: (item["received_at"], item["cursor"]))
        return {"broadcasts": broadcast_items, "segments": segments, "cursor": cursor}

    def transcript_events_after(
        self,
        cursor: int,
        *,
        committee_name: str | None = None,
        broadcast_id: uuid.UUID | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = [cursor]
        committee_filter = ""
        if committee_name:
            committee_filter = " AND broadcast.committee_name = %s"
            parameters.append(committee_name)
        broadcast_filter = ""
        if broadcast_id:
            broadcast_filter = " AND broadcast.id = %s"
            parameters.append(broadcast_id)
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT revision.event_cursor, segment.id, segment.broadcast_id,
                   broadcast.external_id, broadcast.committee_name, broadcast.title,
                   segment.source_segment_id, revision.text, revision.speaker_label,
                   revision.is_final, revision.received_at, revision.content_hash,
                   broadcast.lifecycle_status, revision.source_payload
            FROM transcript_segment_revisions revision
            JOIN transcript_segments segment ON segment.id = revision.segment_id
            JOIN live_broadcasts broadcast ON broadcast.id = segment.broadcast_id
            WHERE revision.event_cursor > %s
              AND broadcast.lifecycle_status = 'LIVE'
              AND broadcast.source_system NOT IN ('poc07.demo', 'poc07.test')
              {committee_filter} {broadcast_filter}
            ORDER BY revision.event_cursor
            LIMIT %s
            """,
            parameters,
        ).fetchall()
        columns = (
            "cursor",
            "segment_id",
            "broadcast_id",
            "external_id",
            "committee_name",
            "title",
            "source_segment_id",
            "text",
            "speaker_label",
            "is_final",
            "received_at",
            "content_hash",
            "lifecycle_status",
            "source_payload",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        for item in items:
            source_payload = item.pop("source_payload", {})
            speaker_segments = (
                source_payload.get("speaker_segments")
                if isinstance(source_payload, dict)
                else None
            )
            item["source_speaker_segments"] = (
                speaker_segments if isinstance(speaker_segments, list) else []
            )
            hint = (
                source_payload.get("insight")
                if isinstance(source_payload, dict)
                else None
            )
            item["insight_hint"] = hint if isinstance(hint, dict) else None
        return items

    def _upsert_document(
        self,
        source: SourceVersionInput,
        source_system: str | None = None,
    ) -> uuid.UUID:
        external_id = hashlib.sha256(source.source_url.encode("utf-8")).hexdigest()
        row = self.connection.execute(
            """
            INSERT INTO source_documents (
                id, source_system, source_type, external_id, canonical_url, first_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_system, source_type, external_id)
            DO UPDATE SET canonical_url = EXCLUDED.canonical_url RETURNING id
            """,
            (
                uuid.uuid4(),
                source_system or self.source_system,
                source.source_type,
                external_id,
                source.source_url,
                source.retrieved_at,
            ),
        ).fetchone()
        return row[0]

    def _upsert_source_version(
        self,
        document_id: uuid.UUID,
        source: SourceVersionInput,
        *,
        authority_status: str = "OFFICIAL",
    ) -> uuid.UUID:
        from psycopg.types.json import Jsonb

        row = self.connection.execute(
            """
            INSERT INTO source_document_versions (
                id, source_document_id, content_hash, source_url, raw_path,
                retrieved_at, parser_version, content_type, authority_status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_document_id, content_hash)
            DO UPDATE SET parser_version = EXCLUDED.parser_version RETURNING id
            """,
            (
                uuid.uuid4(),
                document_id,
                source.content_hash,
                source.source_url,
                str(source.raw_path),
                source.retrieved_at,
                source.parser_version,
                source.content_type,
                authority_status,
                Jsonb(source.metadata),
            ),
        ).fetchone()
        return row[0]
