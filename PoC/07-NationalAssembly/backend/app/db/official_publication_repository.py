from __future__ import annotations

import hashlib
import uuid
from datetime import date, datetime
from typing import Any

from ..adapters.official_minutes_body import OfficialMinutesBody, normalized_match_text
from ..services.official_transcript_insights import (
    CLASSIFICATION_METHOD as INSIGHT_METHOD,
    GENERATOR_VERSION as INSIGHT_VERSION,
    classify_official_utterance,
)
from .schedule_repository import SourceVersionInput


class OfficialPublicationRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def pending_dates(self, *, limit: int = 7) -> list[date]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT (ended_at AT TIME ZONE 'Asia/Seoul')::date AS meeting_date
            FROM live_broadcasts
            WHERE institution = 'LEGISLATURE' AND lifecycle_status = 'ENDED'
              AND ended_at >= now() - interval '30 days'
              AND official_status IN ('PENDING', 'NOT_PUBLISHED')
              AND (official_last_checked_at IS NULL
                   OR official_last_checked_at < now() - interval '1 hour')
            ORDER BY meeting_date
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]

    def pending_body_publications(self, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT publication.id, publication.broadcast_id, publication.meeting_id,
                   publication.conference_id, publication.official_url
            FROM broadcast_official_publications publication
            WHERE publication.official_url IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM official_transcript_documents document
                  WHERE document.publication_id = publication.id
                    AND (document.publication_stage = 'FINAL'
                         OR document.retrieved_at >= now() - interval '1 hour')
              )
            ORDER BY publication.matched_at, publication.id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        columns = ("publication_id", "broadcast_id", "meeting_id", "conference_id", "official_url")
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def pending_meeting_bodies(self, *, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (meeting.id)
                   meeting.id, external.external_id, minute.minutes_url
            FROM meetings meeting
            JOIN meeting_external_ids external ON external.meeting_id = meeting.id
              AND external.source_system = 'open.assembly.go.kr'
              AND external.id_type = 'CONF_ID'
            JOIN committee_minute_entries minute ON minute.meeting_id = meeting.id
            JOIN meeting_versions version ON version.meeting_id = meeting.id
            WHERE version.committee_name IN (
                    '행정안전위원회', '예산결산특별위원회', '법제사법위원회'
                  )
              AND minute.minutes_url IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM official_transcript_documents document
                  WHERE document.meeting_id = meeting.id
                    AND (document.publication_stage = 'FINAL'
                         OR document.retrieved_at >= now() - interval '1 hour')
              )
            ORDER BY meeting.id, version.scheduled_date DESC,
                     minute.created_at DESC, minute.id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        columns = ("meeting_id", "conference_id", "official_url")
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def pending_annotation_documents(self, *, limit: int = 20) -> list[uuid.UUID]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT document.id
            FROM official_transcript_documents document
            JOIN official_transcript_utterances utterance ON utterance.document_id = document.id
            LEFT JOIN official_utterance_annotations annotation
              ON annotation.utterance_id = utterance.id
             AND annotation.generator_version = %s
            WHERE annotation.id IS NULL
            ORDER BY document.id LIMIT %s
            """,
            (INSIGHT_VERSION, limit),
        ).fetchall()
        return [row[0] for row in rows]

    def annotate_document(self, document_id: uuid.UUID, generated_at: datetime) -> int:
        from psycopg.types.json import Jsonb

        rows = self.connection.execute(
            """
            SELECT utterance.id, utterance.text, utterance.text_hash,
                   (SELECT version.committee_name FROM meeting_versions version
                    WHERE version.meeting_id = document.meeting_id
                    ORDER BY version.created_at DESC, version.id DESC LIMIT 1)
            FROM official_transcript_utterances utterance
            JOIN official_transcript_documents document ON document.id = utterance.document_id
            WHERE document.id = %s
            ORDER BY utterance.sequence_number
            """,
            (document_id,),
        ).fetchall()
        inserted = 0
        for utterance_id, text, text_hash, committee_name in rows:
            labels = classify_official_utterance(text)
            row = self.connection.execute(
                """
                INSERT INTO official_utterance_annotations (
                    id, utterance_id, generator_version, classification_method,
                    topics, ministries, source_committee, generated_at, evidence_text_hash,
                    utterance_kind, evidence_keywords, topic_links, ministry_links
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (utterance_id, generator_version) DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), utterance_id, INSIGHT_VERSION, INSIGHT_METHOD,
                    labels["topics"], labels["ministries"], committee_name,
                    generated_at, text_hash, labels["utterance_kind"],
                    labels["evidence_keywords"], Jsonb(labels["topic_links"]),
                    Jsonb(labels["ministry_links"]),
                ),
            ).fetchone()
            inserted += int(row is not None)
        return inserted

    def reconcile_agenda_links(self) -> int:
        rows = self.connection.execute(
            """
            INSERT INTO official_utterance_agenda_links (
                id, utterance_id, agenda_item_id, reconciliation_status,
                match_method, match_confidence
            )
            SELECT gen_random_uuid(), utterance.id, agenda.id, 'MATCHED',
                   'EXACT_ITEM_REF_AGENDA_PREFIX', 1.0
            FROM official_transcript_utterances utterance
            JOIN official_transcript_documents document
              ON document.id = utterance.document_id
            JOIN agenda_items agenda ON agenda.meeting_id = document.meeting_id
            WHERE utterance.agenda_item_ref ~ '^item[1-9][0-9]*$'
              AND agenda.agenda_name ~ '^\\s*[1-9][0-9]*\\.'
              AND substring(utterance.agenda_item_ref from 5)::integer =
                  substring(agenda.agenda_name from '^\\s*([1-9][0-9]*)\\.')::integer
            ON CONFLICT (utterance_id, agenda_item_id, match_method) DO NOTHING
            RETURNING id
            """
        ).fetchall()
        return len(rows)

    def ingest_body(
        self,
        *,
        publication_id: uuid.UUID | None,
        meeting_id: uuid.UUID,
        expected_conference_id: str,
        source: SourceVersionInput,
        body: OfficialMinutesBody,
    ) -> dict[str, int | str]:
        from psycopg.types.json import Jsonb

        if body.conference_id != expected_conference_id:
            raise ValueError("official body conference id does not match publication")
        authority_status = "PROVISIONAL" if body.publication_stage == "TEMPORARY" else "OFFICIAL"
        document_id = self._upsert_source_document(source)
        version_id = self._upsert_source_version(document_id, source, authority_status)
        transcript_document_id = uuid.uuid4()
        row = self.connection.execute(
            """
            INSERT INTO official_transcript_documents (
                id, publication_id, meeting_id, source_document_version_id, conference_id,
                publication_stage, authority_status, extraction_status, status_text,
                title, utterance_count, parser_version, retrieved_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'EXTRACTED', %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id, source_document_version_id)
            DO UPDATE SET extraction_status = 'EXTRACTED', status_text = EXCLUDED.status_text,
                          utterance_count = EXCLUDED.utterance_count,
                          parser_version = EXCLUDED.parser_version
            RETURNING id
            """,
            (
                transcript_document_id, publication_id, meeting_id, version_id, body.conference_id,
                body.publication_stage, authority_status, body.status_text, body.title,
                len(body.utterances), source.parser_version, source.retrieved_at,
            ),
        ).fetchone()
        transcript_document_id = row[0]
        inserted = 0
        for utterance in body.utterances:
            result = self.connection.execute(
                """
                INSERT INTO official_transcript_utterances (
                    id, document_id, sequence_number, source_speaker_id,
                    source_span_id, agenda_item_ref, speaker_name, speaker_role,
                    text, text_hash, source_locator
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, source_span_id) DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), transcript_document_id, utterance.sequence_number,
                    utterance.source_speaker_id, utterance.source_span_id,
                    utterance.agenda_item_ref, utterance.speaker_name,
                    utterance.speaker_role, utterance.text, utterance.text_hash,
                    Jsonb({
                        "source_url": source.source_url,
                        "conference_id": body.conference_id,
                        "speaker_id": utterance.source_speaker_id,
                        "span_id": utterance.source_span_id,
                    }),
                ),
            ).fetchone()
            inserted += int(result is not None)
        reconciliation = {"live_final_revisions": 0, "matched": 0, "unresolved": 0}
        if publication_id is not None:
            self.connection.execute(
                """
                UPDATE broadcast_official_publications
                SET body_contract_status = 'TEXT_EXTRACTED'
                WHERE id = %s
                """,
                (publication_id,),
            )
            reconciliation = self._reconcile_exact(publication_id, transcript_document_id)
        return {
            "publication_stage": body.publication_stage,
            "utterances": len(body.utterances),
            "utterances_inserted": inserted,
            **reconciliation,
        }

    def _reconcile_exact(
        self, publication_id: uuid.UUID, document_id: uuid.UUID
    ) -> dict[str, int]:
        revisions = self.connection.execute(
            """
            SELECT DISTINCT ON (revision.segment_id) revision.id, revision.text
            FROM transcript_segment_revisions revision
            JOIN transcript_segments segment ON segment.id = revision.segment_id
            JOIN broadcast_official_publications publication
              ON publication.broadcast_id = segment.broadcast_id
            WHERE publication.id = %s AND revision.is_final
            ORDER BY revision.segment_id, revision.revision_number DESC
            """,
            (publication_id,),
        ).fetchall()
        utterances = self.connection.execute(
            "SELECT id, text FROM official_transcript_utterances WHERE document_id = %s",
            (document_id,),
        ).fetchall()
        official = [(item_id, normalized_match_text(text)) for item_id, text in utterances]
        matched = 0
        for revision_id, text in revisions:
            normalized = normalized_match_text(text)
            if len(normalized) < 20:
                continue
            candidates = [
                utterance_id for utterance_id, official_text in official
                if normalized in official_text or official_text in normalized
            ]
            if len(candidates) != 1:
                continue
            self.connection.execute(
                """
                INSERT INTO transcript_official_reconciliations (
                    id, transcript_revision_id, official_utterance_id,
                    reconciliation_status, match_method, match_confidence
                ) VALUES (%s, %s, %s, 'MATCHED', 'EXACT_NORMALIZED_SUBSTRING', 1.0)
                ON CONFLICT (transcript_revision_id, official_utterance_id, match_method)
                DO NOTHING
                """,
                (uuid.uuid4(), revision_id, candidates[0]),
            )
            matched += 1
        unresolved = len(revisions) - matched
        overall = "MATCHED" if revisions and unresolved == 0 else "UNRESOLVED"
        self.connection.execute(
            "UPDATE broadcast_official_publications SET reconciliation_status = %s WHERE id = %s",
            (overall, publication_id),
        )
        return {"live_final_revisions": len(revisions), "matched": matched, "unresolved": unresolved}

    def _upsert_source_document(self, source: SourceVersionInput) -> uuid.UUID:
        row = self.connection.execute(
            """
            INSERT INTO source_documents (
                id, source_system, source_type, external_id, canonical_url, first_seen_at
            ) VALUES (%s, 'record.assembly.go.kr', %s, %s, %s, %s)
            ON CONFLICT (source_system, source_type, external_id)
            DO UPDATE SET canonical_url = EXCLUDED.canonical_url RETURNING id
            """,
            (
                uuid.uuid4(), source.source_type,
                hashlib.sha256(source.source_url.encode("utf-8")).hexdigest(),
                source.source_url, source.retrieved_at,
            ),
        ).fetchone()
        return row[0]

    def _upsert_source_version(
        self, document_id: uuid.UUID, source: SourceVersionInput, authority_status: str
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

    def reconcile_date(self, meeting_date: date, checked_at: datetime) -> dict[str, int]:
        broadcasts = self.connection.execute(
            """
            SELECT id, committee_name
            FROM live_broadcasts
            WHERE institution = 'LEGISLATURE' AND lifecycle_status = 'ENDED'
              AND (ended_at AT TIME ZONE 'Asia/Seoul')::date = %s
            ORDER BY id
            """,
            (meeting_date,),
        ).fetchall()
        matched = unresolved = ambiguous = 0
        for broadcast_id, committee_name in broadcasts:
            candidates = self.connection.execute(
                """
                SELECT DISTINCT ON (mei.external_id)
                       cme.meeting_id, mei.external_id,
                       cme.source_document_version_id, cme.minutes_url, cme.pdf_url
                FROM committee_minute_entries cme
                JOIN meeting_external_ids mei ON mei.meeting_id = cme.meeting_id
                  AND mei.source_system = 'open.assembly.go.kr'
                  AND mei.id_type = 'CONF_ID'
                JOIN meeting_versions mv ON mv.meeting_id = cme.meeting_id
                JOIN source_document_versions sdv
                  ON sdv.id = cme.source_document_version_id
                WHERE mv.committee_name = %s AND mv.scheduled_date = %s
                ORDER BY mei.external_id, sdv.retrieved_at DESC, cme.id
                """,
                (committee_name, meeting_date),
            ).fetchall()
            if len(candidates) == 1:
                meeting_id, conference_id, version_id, official_url, pdf_url = candidates[0]
                self.connection.execute(
                    """
                    INSERT INTO broadcast_official_publications (
                        id, broadcast_id, meeting_id, conference_id,
                        source_document_version_id, official_url, pdf_url,
                        matched_at, match_method, match_confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                              'EXACT_COMMITTEE_SEOUL_DATE_UNIQUE', 1.0)
                    ON CONFLICT (broadcast_id, source_document_version_id, conference_id)
                    DO UPDATE SET official_url = EXCLUDED.official_url,
                                  pdf_url = EXCLUDED.pdf_url,
                                  matched_at = EXCLUDED.matched_at
                    """,
                    (
                        uuid.uuid4(), broadcast_id, meeting_id, conference_id,
                        version_id, official_url, pdf_url, checked_at,
                    ),
                )
                status = "PUBLISHED"
                matched += 1
            elif not candidates:
                status = "NOT_PUBLISHED"
                unresolved += 1
            else:
                status = "AMBIGUOUS"
                ambiguous += 1
            self.connection.execute(
                """
                UPDATE live_broadcasts
                SET official_status = %s, official_last_checked_at = %s,
                    official_check_attempts = official_check_attempts + 1,
                    updated_at = now()
                WHERE id = %s
                """,
                (status, checked_at, broadcast_id),
            )
        return {
            "broadcasts": len(broadcasts),
            "published": matched,
            "not_published": unresolved,
            "ambiguous": ambiguous,
        }
