from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable

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
        from psycopg.types.json import Jsonb

        document_id = self._upsert_document(observation.source, observation.source_system)
        version_id = self._upsert_source_version(document_id, observation.source)
        candidate_id = uuid.uuid4()
        row = self.connection.execute(
            """
            INSERT INTO live_broadcasts (
                id, institution, source_system, external_id, committee_name, title,
                lifecycle_status, caption_source_status, detected_at, last_seen_at,
                latest_source_document_version_id, caption_websocket_url, capture_status
                , thumbnail_url
            ) VALUES (%s, %s, %s, %s, %s, %s, 'LIVE', %s, %s, %s, %s, %s, %s, %s)
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
                review_status = 'PENDING', review_lease_owner = NULL,
                review_lease_expires_at = NULL,
                updated_at = now()
            RETURNING id
            """,
            (
                candidate_id, observation.institution, observation.source_system,
                observation.external_id, observation.committee_name,
                observation.title, observation.caption_source_status,
                observation.observed_at, observation.observed_at, version_id,
                observation.caption_websocket_url,
                "READY" if observation.caption_websocket_url else "UNAVAILABLE",
                observation.thumbnail_url,
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
                capture_status = 'COMPLETED', capture_lease_owner = NULL,
                capture_lease_expires_at = NULL, review_status = 'READY',
                updated_at = now()
            WHERE id = %s AND lifecycle_status = 'LIVE'
            RETURNING id
            """,
            (ended_at, ended_at, broadcast_id),
        ).fetchone()
        return row is not None

    def finish_poll(self, active_external_ids: Iterable[str], observed_at: datetime) -> int:
        active = list(active_external_ids)
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET lifecycle_status = 'ENDED', ended_at = %s,
                capture_status = 'COMPLETED', capture_lease_owner = NULL,
                capture_lease_expires_at = NULL, review_status = 'READY',
                updated_at = now()
            WHERE source_system = %s AND lifecycle_status = 'LIVE'
              AND NOT (external_id = ANY(%s))
            RETURNING id
            """,
            (observed_at, self.source_system, active),
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
        return dict(zip(
            ("broadcast_id", "external_id", "caption_websocket_url", "lifecycle_status"),
            row,
            strict=True,
        ))

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
        self, broadcast_id: uuid.UUID, worker_id: str, *, retry: bool
    ) -> bool:
        row = self.connection.execute(
            """
            UPDATE live_broadcasts
            SET capture_status = CASE
                    WHEN lifecycle_status = 'ENDED' THEN 'COMPLETED'
                    WHEN %s THEN 'RETRY_WAIT' ELSE 'FAILED'
                END,
                capture_lease_owner = NULL, capture_lease_expires_at = NULL,
                reconnect_attempts = reconnect_attempts + CASE WHEN %s THEN 1 ELSE 0 END,
                updated_at = now()
            WHERE id = %s AND capture_lease_owner = %s
            RETURNING id
            """,
            (retry, retry, broadcast_id, worker_id),
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
        source_system = source_system_row[0] if source_system_row else self.source_system
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
                uuid.uuid4(), broadcast_id, revision.source_segment_id,
                revision.speaker_label, revision.start_offset_ms,
                revision.end_offset_ms, revision.text, revision.is_final,
                revision.received_at, revision.received_at,
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
                uuid.uuid4(), segment_id, content_hash, revision.text,
                revision.speaker_label, revision.is_final, revision.received_at,
                Jsonb(revision.source_payload), source_version_id, segment_id,
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
        self, committee_name: str | None = None
    ) -> dict[str, Any]:
        return self._transcript_snapshot(committee_name, lifecycle_status="LIVE")

    def recent_transcript_snapshot(
        self, committee_name: str | None = None
    ) -> dict[str, Any]:
        return self._transcript_snapshot(committee_name, lifecycle_status="ENDED")

    def ended_transcript_snapshot(self, broadcast_id: uuid.UUID) -> dict[str, Any]:
        return self._transcript_snapshot(
            None, lifecycle_status="ENDED", broadcast_id=broadcast_id
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
                   utterance.sequence_number, utterance.speaker_name,
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
            "revision_id", "status", "match_method", "match_confidence",
            "official_sequence_number", "official_speaker_name",
            "official_speaker_role", "official_text", "source_locator",
            "publication_stage", "official_authority_status",
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
        self, committee_name: str | None = None, *, limit: int = 5
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = []
        committee_filter = ""
        if committee_name:
            committee_filter = " AND broadcast.committee_name = %s"
            parameters.append(committee_name)
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            SELECT broadcast.id, broadcast.external_id, broadcast.committee_name,
                   broadcast.title, broadcast.lifecycle_status, broadcast.source_system,
                   broadcast.capture_status, broadcast.detected_at, broadcast.ended_at,
                   broadcast.last_caption_received_at, broadcast.thumbnail_url,
                   broadcast.review_status, broadcast.official_status,
                   broadcast.official_last_checked_at,
                   (SELECT COUNT(*) FROM transcript_segments segment
                    WHERE segment.broadcast_id = broadcast.id) AS segment_count
            FROM live_broadcasts broadcast
            WHERE broadcast.institution = 'LEGISLATURE'
              AND broadcast.lifecycle_status = 'ENDED'
              {committee_filter}
            ORDER BY broadcast.ended_at DESC NULLS LAST, broadcast.detected_at DESC
            LIMIT %s
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id", "external_id", "committee_name", "title",
            "lifecycle_status", "source_system", "capture_status", "detected_at",
            "ended_at", "last_caption_received_at", "thumbnail_url", "review_status",
            "official_status", "official_last_checked_at", "segment_count",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        for item in items:
            item["simulation"] = item["source_system"] == "poc07.demo"
        return items

    def broadcast_official_context(self, broadcast_id: uuid.UUID) -> dict[str, Any] | None:
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
            "official_status", "official_last_checked_at", "review_status",
            "conference_id", "official_url", "official_pdf_url",
            "reconciliation_status", "body_contract_status", "publication_stage",
            "official_authority_status", "official_utterance_count",
            "final_segment_count", "matched_segment_count",
        )
        item = dict(zip(columns, row, strict=True))
        item["unmatched_segment_count"] = max(
            0, item["final_segment_count"] - item["matched_segment_count"]
        )
        return item

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
              AND revision.is_final = true
              AND (broadcast.lifecycle_status = 'LIVE'
                   OR broadcast.ended_at >= now() - interval '30 days')
              {committee_filter}
            ORDER BY segment.id, revision.event_cursor DESC
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id", "broadcast_title", "committee_name", "lifecycle_status",
            "ended_at", "source_system", "evidence_revision_id", "evidence_text",
            "speaker_label", "received_at", "source_payload",
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
            if insight.get("resolution") is True or insight.get("task_status") == "RESOLVED":
                resolved_topics.add(topic_key)
                for key in [key for key in tasks if key[0] == item["broadcast_id"] and tasks[key]["topic_id"] == topic_id]:
                    tasks.pop(key, None)
                continue
            task_text = insight.get("task")
            if not isinstance(task_text, str) or insight.get("task_status") != "OPEN":
                continue
            resolved_topics.discard(topic_key)
            ministries = [
                value for value in insight.get("ministries", [])
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
                "simulation": item["source_system"] == "poc07.demo",
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
        broadcasts = self.connection.execute(
            f"""
            SELECT id, external_id, committee_name, title, lifecycle_status,
                   source_system, capture_status, detected_at, last_seen_at,
                   last_caption_received_at, thumbnail_url, ended_at
            FROM live_broadcasts
            WHERE institution = 'LEGISLATURE' AND lifecycle_status = %s
            {committee_filter}
            {broadcast_filter}
            {order_and_limit}
            """,
            parameters,
        ).fetchall()
        columns = (
            "broadcast_id", "external_id", "committee_name", "title",
            "lifecycle_status", "source_system", "capture_status", "detected_at", "last_seen_at",
            "last_caption_received_at", "thumbnail_url", "ended_at",
        )
        broadcast_items = [dict(zip(columns, row, strict=True)) for row in broadcasts]
        for item in broadcast_items:
            item["simulation"] = item["source_system"] == "poc07.demo"
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
            "segment_id", "revision_id", "broadcast_id", "source_segment_id", "cursor", "text",
            "speaker_label", "is_final", "received_at", "content_hash",
            "source_payload",
        )
        segments = [dict(zip(segment_columns, row, strict=True)) for row in rows]
        for item in segments:
            source_payload = item.pop("source_payload", {})
            hint = source_payload.get("insight") if isinstance(source_payload, dict) else None
            item["insight_hint"] = hint if isinstance(hint, dict) else None
        segments.sort(key=lambda item: (item["received_at"], item["cursor"]))
        return {"broadcasts": broadcast_items, "segments": segments, "cursor": cursor}

    def transcript_events_after(
        self,
        cursor: int,
        *,
        committee_name: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        parameters: list[Any] = [cursor]
        committee_filter = ""
        if committee_name:
            committee_filter = " AND broadcast.committee_name = %s"
            parameters.append(committee_name)
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
              AND broadcast.lifecycle_status = 'LIVE' {committee_filter}
            ORDER BY revision.event_cursor
            LIMIT %s
            """,
            parameters,
        ).fetchall()
        columns = (
            "cursor", "segment_id", "broadcast_id", "external_id",
            "committee_name", "title", "source_segment_id", "text",
            "speaker_label", "is_final", "received_at", "content_hash",
            "lifecycle_status",
            "source_payload",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        for item in items:
            source_payload = item.pop("source_payload", {})
            hint = source_payload.get("insight") if isinstance(source_payload, dict) else None
            item["insight_hint"] = hint if isinstance(hint, dict) else None
        return items

    def _upsert_document(
        self, source: SourceVersionInput, source_system: str | None = None,
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
                uuid.uuid4(), source_system or self.source_system, source.source_type, external_id,
                source.source_url, source.retrieved_at,
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
                uuid.uuid4(), document_id, source.content_hash, source.source_url,
                str(source.raw_path), source.retrieved_at, source.parser_version,
                source.content_type, authority_status, Jsonb(source.metadata),
            ),
        ).fetchone()
        return row[0]
