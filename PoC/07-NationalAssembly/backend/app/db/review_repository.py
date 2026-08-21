from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any


class ReviewRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def claim_ended_broadcast(
        self, worker_id: str, lease_seconds: int = 120
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT id FROM live_broadcasts
                WHERE lifecycle_status = 'ENDED'
                  AND review_status IN ('READY', 'RETRY_WAIT')
                  AND review_attempts < 5
                  AND ended_at < now() - interval '60 seconds'
                  AND (review_lease_expires_at IS NULL OR review_lease_expires_at < now())
                ORDER BY ended_at, id
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE live_broadcasts broadcast
            SET review_status = 'PROCESSING', review_lease_owner = %s,
                review_lease_expires_at = now() + (%s * interval '1 second'),
                updated_at = now()
            FROM candidate WHERE broadcast.id = candidate.id
            RETURNING broadcast.id, broadcast.external_id, broadcast.institution,
                      broadcast.committee_name, broadcast.title, broadcast.detected_at,
                      broadcast.ended_at, broadcast.thumbnail_url
            """,
            (worker_id, lease_seconds),
        ).fetchone()
        if not row:
            return None
        columns = (
            "broadcast_id", "external_id", "institution", "committee_name",
            "title", "detected_at", "ended_at", "thumbnail_url",
        )
        return dict(zip(columns, row, strict=True))

    def final_caption_revisions(self, broadcast_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (segment.id)
                   revision.id, segment.id, segment.source_segment_id,
                   revision.event_cursor, revision.text, revision.speaker_label,
                   revision.received_at, revision.content_hash
            FROM transcript_segments segment
            JOIN transcript_segment_revisions revision ON revision.segment_id = segment.id
            WHERE segment.broadcast_id = %s AND revision.is_final = true
            ORDER BY segment.id, revision.event_cursor DESC
            """,
            (broadcast_id,),
        ).fetchall()
        columns = (
            "revision_id", "segment_id", "source_segment_id", "cursor", "text",
            "speaker_label", "received_at", "content_hash",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        return sorted(items, key=lambda item: item["cursor"])

    def save_review(
        self,
        broadcast: dict[str, Any],
        topics: list[dict[str, Any]],
        *,
        generator_version: str,
        classification_method: str,
        generated_at: datetime,
    ) -> uuid.UUID | None:
        from psycopg.types.json import Jsonb

        broadcast_id = broadcast["broadcast_id"]
        if not topics:
            self.connection.execute(
                """
                UPDATE live_broadcasts
                SET review_status = 'NO_CONTENT', review_lease_owner = NULL,
                    review_lease_expires_at = NULL, updated_at = now()
                WHERE id = %s
                """,
                (broadcast_id,),
            )
            return None
        source_cursor = max(
            int(cursor)
            for topic in topics
            for cursor in [topic.get("last_cursor", 0)]
        )
        if source_cursor == 0:
            revision_ids = [
                revision_id
                for topic in topics
                for revision_id in topic["evidence_revision_ids"]
            ]
            source_cursor = self.connection.execute(
                """
                SELECT COALESCE(MAX(event_cursor), 0)
                FROM transcript_segment_revisions WHERE id = ANY(%s)
                """,
                (revision_ids,),
            ).fetchone()[0]
        review_row = self.connection.execute(
            """
            INSERT INTO broadcast_reviews (
                id, broadcast_id, generator_version, source_last_event_cursor,
                classification_method, generated_at, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id, generator_version, source_last_event_cursor)
            DO UPDATE SET metadata = EXCLUDED.metadata RETURNING id
            """,
            (
                uuid.uuid4(), broadcast_id, generator_version, source_cursor,
                classification_method, generated_at,
                Jsonb({"topic_count": len(topics), "abstractive_summary": False}),
            ),
        ).fetchone()
        review_id = review_row[0]
        for topic in topics:
            topic_row = self.connection.execute(
                """
                INSERT INTO broadcast_review_topics (
                    id, review_id, topic, major_quote, speaker_label, ministries,
                    committees, segment_count, representative_revision_id, sort_order
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (review_id, topic) DO UPDATE SET
                    major_quote = EXCLUDED.major_quote,
                    speaker_label = EXCLUDED.speaker_label,
                    ministries = EXCLUDED.ministries,
                    committees = EXCLUDED.committees,
                    segment_count = EXCLUDED.segment_count,
                    representative_revision_id = EXCLUDED.representative_revision_id,
                    sort_order = EXCLUDED.sort_order
                RETURNING id
                """,
                (
                    uuid.uuid4(), review_id, topic["topic"], topic["major_quote"],
                    topic.get("speaker_label"), topic["ministries"],
                    topic["committees"], topic["segment_count"],
                    topic["representative_revision_id"], topic["sort_order"],
                ),
            ).fetchone()
            topic_id = topic_row[0]
            for position, revision_id in enumerate(topic["evidence_revision_ids"]):
                self.connection.execute(
                    """
                    INSERT INTO broadcast_review_evidence (
                        review_topic_id, revision_id, position
                    ) VALUES (%s, %s, %s)
                    ON CONFLICT (review_topic_id, revision_id)
                    DO UPDATE SET position = EXCLUDED.position
                    """,
                    (topic_id, revision_id, position),
                )
        self.connection.execute(
            """
            UPDATE live_broadcasts
            SET review_status = 'COMPLETED', review_lease_owner = NULL,
                review_lease_expires_at = NULL, updated_at = now()
            WHERE id = %s
            """,
            (broadcast_id,),
        )
        return review_id

    def fail_review(self, broadcast_id: uuid.UUID, worker_id: str) -> None:
        self.connection.execute(
            """
            UPDATE live_broadcasts
            SET review_attempts = review_attempts + 1,
                review_status = CASE WHEN review_attempts + 1 >= 5
                    THEN 'FAILED' ELSE 'RETRY_WAIT' END,
                review_lease_owner = NULL, review_lease_expires_at = NULL,
                updated_at = now()
            WHERE id = %s AND review_lease_owner = %s
            """,
            (broadcast_id, worker_id),
        )

    def list_magazine(
        self,
        *,
        institution: str | None = None,
        scope: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        where = ["broadcast.review_status = 'COMPLETED'"]
        parameters: list[Any] = []
        if institution:
            where.append("broadcast.institution = %s")
            parameters.append(institution)
        if scope:
            where.append("(%s = ANY(topic.ministries) OR %s = ANY(topic.committees))")
            parameters.extend([scope, scope])
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            WITH latest_review AS (
                SELECT DISTINCT ON (broadcast_id) id, broadcast_id, generated_at,
                       classification_method
                FROM broadcast_reviews
                ORDER BY broadcast_id, generated_at DESC, id DESC
            )
            SELECT topic.id, broadcast.institution, broadcast.title,
                   broadcast.detected_at, topic.speaker_label, topic.major_quote,
                   topic.topic, topic.ministries, topic.committees,
                   broadcast.thumbnail_url, review.generated_at,
                   review.classification_method, topic.segment_count,
                   topic.representative_revision_id,
                   publication.official_url, publication.pdf_url,
                   publication.conference_id, publication.body_contract_status,
                   publication.reconciliation_status,
                   publication.publication_stage, publication.body_authority_status,
                   publication.utterance_count, broadcast.source_system
            FROM latest_review review
            JOIN live_broadcasts broadcast ON broadcast.id = review.broadcast_id
            JOIN broadcast_review_topics topic ON topic.review_id = review.id
            LEFT JOIN LATERAL (
                SELECT publication.official_url, publication.pdf_url,
                       publication.conference_id, publication.body_contract_status,
                       publication.reconciliation_status,
                       document.publication_stage,
                       document.authority_status AS body_authority_status,
                       document.utterance_count
                FROM broadcast_official_publications publication
                LEFT JOIN LATERAL (
                    SELECT publication_stage, authority_status, utterance_count
                    FROM official_transcript_documents
                    WHERE publication_id = publication.id
                    ORDER BY retrieved_at DESC, id DESC LIMIT 1
                ) document ON true
                WHERE publication.broadcast_id = broadcast.id
                ORDER BY publication.matched_at DESC, publication.id DESC LIMIT 1
            ) publication ON true
            WHERE {' AND '.join(where)}
            ORDER BY broadcast.ended_at DESC, topic.sort_order
            LIMIT %s
            """,
            parameters,
        ).fetchall()
        columns = (
            "card_id", "institution", "meeting_title", "meeting_date",
            "speaker_label", "major_quote", "topic", "ministries", "committees",
            "image_url", "generated_at", "classification_method", "segment_count",
            "evidence_revision_id",
            "official_url", "official_pdf_url", "official_conference_id",
            "official_body_status", "official_reconciliation_status",
            "official_publication_stage", "official_body_authority_status",
            "official_utterance_count", "source_system",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        for item in items:
            item["meeting_date"] = item["meeting_date"].date().isoformat()
            item["simulation"] = item["source_system"] == "poc07.demo"
            image_url = item.get("image_url")
            allowed_demo_image = item["simulation"] and isinstance(image_url, str) and image_url.startswith("assets/magazine/")
            if not isinstance(image_url, str) or not (image_url.startswith("https://") or allowed_demo_image):
                item["image_url"] = None
            item["image_alt"] = (
                "실제 방송이 아닌 E2E 데모 이미지" if item["simulation"]
                else "국회 공식 생중계 썸네일" if item["image_url"] else ""
            )
            item["authority_status"] = "PROVISIONAL"
            item["reconciliation_status"] = "UNRESOLVED"
            for field in ("official_url", "official_pdf_url"):
                value = item.get(field)
                if not isinstance(value, str) or not value.startswith("https://"):
                    item[field] = None
            item["official_published"] = bool(
                item["official_url"] or item["official_pdf_url"]
            )
        return items
