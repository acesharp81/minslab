from __future__ import annotations

import hashlib
import re
import uuid
from datetime import date, datetime
from typing import Any

from ..domain.scope import NATIONAL_ASSEMBLY_BODIES, TARGET_COMMITTEES
from ..adapters.official_minutes_body import (
    OfficialMinutesBody,
    explicit_spoken_agenda_ref,
    normalized_match_text,
)
from ..services.official_transcript_insights import (
    CLASSIFICATION_METHOD as INSIGHT_METHOD,
    GENERATOR_VERSION as INSIGHT_VERSION,
    classify_official_utterance,
)
from .schedule_repository import SourceVersionInput


class OfficialPublicationRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def pending_date_sources(self, *, limit: int = 7) -> list[dict[str, Any]]:
        """Poll only unpublished meetings, with less frequent older checks."""
        rows = self.connection.execute(
            """
            SELECT (detected_at AT TIME ZONE 'Asia/Seoul')::date AS meeting_date,
                   bool_or(committee_name = '본회의') AS plenary_due,
                   bool_or(committee_name <> '본회의') AS committee_due,
                   array_agg(id) AS broadcast_ids
            FROM live_broadcasts
            WHERE institution = 'LEGISLATURE' AND lifecycle_status = 'ENDED'
              AND committee_name = ANY(%s)
              AND ended_at >= now() - interval '180 days'
              AND source_system NOT IN (
                  'poc07.demo', 'poc07.test', 'poc07.replay.local',
                  'poc07.replay.kakao'
              )
              AND official_status IN ('PENDING', 'NOT_PUBLISHED')
              AND (
                  official_last_checked_at IS NULL
                  OR official_last_checked_at < now() - CASE
                      WHEN now() - ended_at < interval '2 days'
                          THEN interval '1 hour'
                      WHEN now() - ended_at < interval '7 days'
                          THEN interval '6 hours'
                      WHEN now() - ended_at < interval '30 days'
                          THEN interval '24 hours'
                      ELSE interval '7 days'
                  END
              )
            GROUP BY meeting_date
            ORDER BY min(official_last_checked_at) NULLS FIRST, meeting_date
            LIMIT %s
            """,
            ([*TARGET_COMMITTEES, *NATIONAL_ASSEMBLY_BODIES], limit),
        ).fetchall()
        return [
            {"date": row[0], "plenary_due": bool(row[1]),
             "committee_due": bool(row[2]), "broadcast_ids": row[3]}
            for row in rows
        ]

    def pending_dates(self, *, limit: int = 7) -> list[date]:
        return [item["date"] for item in self.pending_date_sources(limit=limit)]

    def pending_body_publications(self, *, limit: int = 5) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            WITH candidate AS (
                SELECT DISTINCT ON (publication.meeting_id, publication.conference_id)
                       publication.id, publication.broadcast_id,
                       publication.meeting_id, publication.conference_id,
                       publication.official_url, publication.body_contract_status,
                       publication.matched_at
                FROM broadcast_official_publications publication
                LEFT JOIN LATERAL (
                    SELECT id FROM official_transcript_documents document
                    WHERE document.publication_id = publication.id LIMIT 1
                ) linked ON true
                WHERE publication.official_url IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM official_transcript_documents document
                      WHERE document.meeting_id = publication.meeting_id
                        AND document.conference_id = publication.conference_id
                        AND (document.publication_stage = 'FINAL'
                             OR document.retrieved_at >= now() - interval '1 hour')
                  )
                ORDER BY publication.meeting_id, publication.conference_id,
                         (linked.id IS NOT NULL) DESC,
                         (publication.body_contract_status = 'LINK_ONLY') DESC,
                         publication.matched_at DESC, publication.id DESC
            )
            SELECT candidate.id, candidate.broadcast_id, candidate.meeting_id,
                   candidate.conference_id, candidate.official_url, broadcast.committee_name
            FROM candidate
            JOIN live_broadcasts broadcast ON broadcast.id = candidate.broadcast_id
            ORDER BY (candidate.body_contract_status = 'LINK_ONLY') DESC,
                     candidate.matched_at DESC, candidate.id DESC
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        columns = ("publication_id", "broadcast_id", "meeting_id", "conference_id", "official_url", "committee_name")
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
                  SELECT 1
                  FROM broadcast_official_publications publication
                  WHERE publication.meeting_id = meeting.id
                    AND publication.conference_id = external.external_id
              )
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
            SELECT document.id
            FROM official_transcript_documents document
            LEFT JOIN official_annotation_processing_state state
              ON state.document_id = document.id
             AND state.generator_version = %s
            WHERE state.document_id IS NULL
               OR (state.status = 'RETRY_WAIT'
                   AND state.next_attempt_at <= now())
               OR (state.status = 'SUCCEEDED'
                   AND state.utterance_count < document.utterance_count)
            ORDER BY (state.document_id IS NULL) DESC,
                     COALESCE(state.next_attempt_at, document.created_at),
                     document.id
            LIMIT %s
            """,
            (INSIGHT_VERSION, limit),
        ).fetchall()
        return [row[0] for row in rows]

    def record_annotation_document(
        self, document_id: uuid.UUID, *, succeeded: bool,
        error: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO official_annotation_processing_state (
                document_id, generator_version, utterance_count,
                status, attempt_count, next_attempt_at, last_error, completed_at
            )
            SELECT id, %s, utterance_count, %s, 1,
                   CASE WHEN %s THEN NULL ELSE now() + interval '5 minutes' END,
                   %s, CASE WHEN %s THEN now() ELSE NULL END
            FROM official_transcript_documents WHERE id = %s
            ON CONFLICT (document_id, generator_version)
            DO UPDATE SET utterance_count = EXCLUDED.utterance_count,
                          status = EXCLUDED.status,
                          attempt_count = official_annotation_processing_state.attempt_count + 1,
                          next_attempt_at = CASE WHEN EXCLUDED.status = 'SUCCEEDED'
                              THEN NULL ELSE now() + make_interval(secs => LEAST(
                                  86400, 300 * (2 ^ LEAST(
                                      official_annotation_processing_state.attempt_count, 8
                                  ))::integer
                              )) END,
                          last_error = EXCLUDED.last_error,
                          completed_at = EXCLUDED.completed_at,
                          updated_at = now()
            """,
            (
                INSIGHT_VERSION, "SUCCEEDED" if succeeded else "RETRY_WAIT",
                succeeded, error, succeeded, document_id,
            ),
        )

    def attach_preserved_documents(self) -> int:
        """Link bodies collected by meeting identity before a LIVE publication match."""
        rows = self.connection.execute(
            """
            UPDATE official_transcript_documents document
            SET publication_id = (
                SELECT publication.id AS publication_id
                FROM broadcast_official_publications publication
                WHERE publication.meeting_id = document.meeting_id
                  AND publication.conference_id = document.conference_id
                ORDER BY publication.matched_at DESC, publication.id DESC
                LIMIT 1
            )
            WHERE document.publication_id IS NULL
              AND EXISTS (
                  SELECT 1
                  FROM broadcast_official_publications publication
                  WHERE publication.meeting_id = document.meeting_id
                    AND publication.conference_id = document.conference_id
              )
            RETURNING document.id, document.publication_id
            """
        ).fetchall()
        if rows:
            publication_ids = list({row[1] for row in rows})
            self.connection.execute(
                """
                UPDATE broadcast_official_publications
                SET body_contract_status = 'TEXT_EXTRACTED'
                WHERE id = ANY(%s)
                """,
                (publication_ids,),
            )
        return len(rows)

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

    def pending_agenda_documents(self, *, limit: int = 5) -> list[uuid.UUID]:
        rows = self.connection.execute(
            """
            SELECT document.id
            FROM official_transcript_documents document
            JOIN LATERAL (
                SELECT count(*)::integer AS item_count
                FROM agenda_items agenda WHERE agenda.meeting_id = document.meeting_id
            ) agenda ON true
            LEFT JOIN official_agenda_reconciliation_state state
              ON state.document_id = document.id
            WHERE state.document_id IS NULL
               OR state.agenda_count <> agenda.item_count
               OR state.last_sequence < document.utterance_count
            ORDER BY COALESCE(state.updated_at, document.created_at), document.id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
        return [row[0] for row in rows]

    def reconcile_agenda_document(
        self, document_id: uuid.UUID, *, batch_size: int = 1000,
    ) -> dict[str, int | bool]:
        """Reconcile one bounded utterance batch for a document and agenda set."""
        document = self.connection.execute(
            """
            SELECT meeting_id, utterance_count
            FROM official_transcript_documents WHERE id = %s
            """,
            (document_id,),
        ).fetchone()
        if document is None:
            return {"links_inserted": 0, "complete": True}
        meeting_id, utterance_count = document
        agenda_rows = self.connection.execute(
            """
            SELECT id, agenda_name
            FROM agenda_items WHERE meeting_id = %s
            ORDER BY created_at, id
            """,
            (meeting_id,),
        ).fetchall()
        agenda_count = len(agenda_rows)
        previous = self.connection.execute(
            """
            SELECT agenda_count, last_sequence
            FROM official_agenda_reconciliation_state WHERE document_id = %s
            """,
            (document_id,),
        ).fetchone()
        last_sequence = previous[1] if previous and previous[0] == agenda_count else 0
        by_number: dict[int, list[uuid.UUID]] = {}
        for agenda_id, name in agenda_rows:
            match = re.match(r"^\s*([1-9][0-9]*)\.", name)
            if match:
                by_number.setdefault(int(match.group(1)), []).append(agenda_id)
        if by_number:
            utterances = self.connection.execute(
                """
                SELECT id, sequence_number, text, agenda_item_ref
                FROM official_transcript_utterances
                WHERE document_id = %s AND sequence_number > %s
                ORDER BY sequence_number LIMIT %s
                """,
                (document_id, last_sequence, batch_size),
            ).fetchall()
        else:
            utterances = []
            last_sequence = utterance_count
        inserted = 0
        for utterance_id, sequence_number, text, stored_ref in utterances:
            if stored_ref and re.fullmatch(r"item[1-9][0-9]*", stored_ref):
                for agenda_id in by_number.get(int(stored_ref[4:]), []):
                    row = self.connection.execute(
                        """
                        INSERT INTO official_utterance_agenda_links (
                            id, utterance_id, agenda_item_id,
                            reconciliation_status, match_method, match_confidence
                        ) VALUES (%s, %s, %s, 'MATCHED',
                                  'EXACT_ITEM_REF_AGENDA_PREFIX', 1.0)
                        ON CONFLICT (utterance_id, agenda_item_id, match_method)
                        DO NOTHING RETURNING id
                        """,
                        (uuid.uuid4(), utterance_id, agenda_id),
                    ).fetchone()
                    inserted += int(row is not None)
            explicit_ref = explicit_spoken_agenda_ref(text)
            if not explicit_ref or explicit_ref == stored_ref:
                continue
            targets = by_number.get(int(explicit_ref[4:]), [])
            if not targets:
                continue
            target = targets[-1]
            if stored_ref:
                self.connection.execute(
                    """
                    UPDATE official_utterance_agenda_links
                    SET reconciliation_status = 'CONFLICT'
                    WHERE utterance_id = %s AND agenda_item_id <> %s
                      AND reconciliation_status = 'MATCHED'
                      AND match_method = 'EXACT_ITEM_REF_AGENDA_PREFIX'
                    """,
                    (utterance_id, target),
                )
            row = self.connection.execute(
                """
                INSERT INTO official_utterance_agenda_links (
                    id, utterance_id, agenda_item_id,
                    reconciliation_status, match_method, match_confidence
                ) VALUES (%s, %s, %s, 'MATCHED',
                          'EXPLICIT_SPOKEN_ITEM_AGENDA_PREFIX', 1.0)
                ON CONFLICT (utterance_id, agenda_item_id, match_method)
                DO UPDATE SET reconciliation_status = 'MATCHED', match_confidence = 1.0
                WHERE official_utterance_agenda_links.reconciliation_status <> 'MATCHED'
                RETURNING id
                """,
                (uuid.uuid4(), utterance_id, target),
            ).fetchone()
            inserted += int(row is not None)
        if utterances:
            last_sequence = utterances[-1][1]
        complete = last_sequence >= utterance_count
        self.connection.execute(
            """
            INSERT INTO official_agenda_reconciliation_state (
                document_id, agenda_count, last_sequence, completed_at
            ) VALUES (%s, %s, %s, CASE WHEN %s THEN now() ELSE NULL END)
            ON CONFLICT (document_id) DO UPDATE SET
                agenda_count = EXCLUDED.agenda_count,
                last_sequence = EXCLUDED.last_sequence,
                completed_at = EXCLUDED.completed_at,
                updated_at = now()
            """,
            (document_id, agenda_count, last_sequence, complete),
        )
        return {"links_inserted": inserted, "complete": complete}

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
        existing = self.connection.execute(
            """
            SELECT document.id, document.publication_id,
                   (SELECT count(*) FROM official_transcript_utterances utterance
                    WHERE utterance.document_id = document.id) AS stored_utterances
            FROM official_transcript_documents document
            WHERE document.meeting_id = %s
              AND document.source_document_version_id = %s
            """,
            (meeting_id, version_id),
        ).fetchone()
        if existing and int(existing[2] or 0) == len(body.utterances):
            transcript_document_id, existing_publication_id, _ = existing
            self.connection.execute(
                """
                UPDATE official_transcript_documents
                SET publication_id = COALESCE(publication_id, %s),
                    extraction_status = 'EXTRACTED', publication_stage = %s,
                    authority_status = %s, status_text = %s, title = %s,
                    utterance_count = %s, parser_version = %s,
                    retrieved_at = GREATEST(retrieved_at, %s)
                WHERE id = %s
                """,
                (
                    publication_id, body.publication_stage, authority_status,
                    body.status_text, body.title, len(body.utterances),
                    source.parser_version, source.retrieved_at,
                    transcript_document_id,
                ),
            )
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
                if existing_publication_id != publication_id:
                    reconciliation = self._reconcile_exact(publication_id, transcript_document_id)
            return {
                "publication_stage": body.publication_stage,
                "utterances": len(body.utterances),
                "utterances_inserted": 0,
                "semantic_cache_hit": True,
                **reconciliation,
            }
        transcript_document_id = uuid.uuid4()
        row = self.connection.execute(
            """
            INSERT INTO official_transcript_documents (
                id, publication_id, meeting_id, source_document_version_id, conference_id,
                publication_stage, authority_status, extraction_status, status_text,
                title, utterance_count, parser_version, retrieved_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'EXTRACTED', %s, %s, %s, %s, %s)
            ON CONFLICT (meeting_id, source_document_version_id)
            DO UPDATE SET publication_id = COALESCE(
                              official_transcript_documents.publication_id,
                              EXCLUDED.publication_id
                          ),
                          extraction_status = 'EXTRACTED',
                          publication_stage = EXCLUDED.publication_stage,
                          authority_status = EXCLUDED.authority_status,
                          status_text = EXCLUDED.status_text,
                          title = EXCLUDED.title,
                          utterance_count = EXCLUDED.utterance_count,
                          parser_version = EXCLUDED.parser_version,
                          retrieved_at = GREATEST(
                              official_transcript_documents.retrieved_at,
                              EXCLUDED.retrieved_at
                          )
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
        broadcast_row = self.connection.execute(
            "SELECT broadcast_id FROM broadcast_official_publications WHERE id = %s",
            (publication_id,),
        ).fetchone()
        if broadcast_row:
            from .live_repository import LiveRepository

            LiveRepository(self.connection).refresh_official_context_stats(
                [broadcast_row[0]]
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

    def reconcile_date(
        self, meeting_date: date, checked_at: datetime,
        *, broadcast_ids: list[uuid.UUID] | None = None,
    ) -> dict[str, int]:
        broadcasts = self.connection.execute(
            """
            SELECT id, committee_name, title
            FROM live_broadcasts
            WHERE institution = 'LEGISLATURE' AND lifecycle_status = 'ENDED'
              AND committee_name = ANY(%s)
              AND (detected_at AT TIME ZONE 'Asia/Seoul')::date = %s
              AND official_status IN ('PENDING', 'NOT_PUBLISHED')
              AND (%s::uuid[] IS NULL OR id = ANY(%s::uuid[]))
            ORDER BY id
            """,
            ([*TARGET_COMMITTEES, *NATIONAL_ASSEMBLY_BODIES], meeting_date,
             broadcast_ids, broadcast_ids),
        ).fetchall()
        matched = unresolved = ambiguous = 0
        for broadcast_id, committee_name, broadcast_title in broadcasts:
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
                  AND substring(mv.meeting_order_text from '제0*([0-9]+)차')::integer
                      = substring(%s from '제0*([0-9]+)차')::integer
                ORDER BY mei.external_id, sdv.retrieved_at DESC, cme.id
                """,
                (committee_name, meeting_date, broadcast_title),
            ).fetchall()
            if len(candidates) == 1:
                meeting_id, conference_id, version_id, official_url, pdf_url = candidates[0]
                publication_row = self.connection.execute(
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
                    RETURNING id
                    """,
                    (
                        uuid.uuid4(), broadcast_id, meeting_id, conference_id,
                        version_id, official_url, pdf_url, checked_at,
                    ),
                ).fetchone()
                self.attach_preserved_documents()
                existing_document = self.connection.execute(
                    """
                    SELECT id FROM official_transcript_documents
                    WHERE meeting_id = %s AND conference_id = %s
                    ORDER BY (publication_stage = 'FINAL') DESC,
                             retrieved_at DESC, id DESC LIMIT 1
                    """,
                    (meeting_id, conference_id),
                ).fetchone()
                if existing_document:
                    self._reconcile_exact(publication_row[0], existing_document[0])
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
