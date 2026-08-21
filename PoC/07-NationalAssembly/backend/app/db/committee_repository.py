from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Iterable

from ..services.official_transcript_insights import GENERATOR_VERSION as INSIGHT_VERSION

from ..adapters.national_assembly.meeting_agendas import MeetingAgendaSourceRecord
from ..domain.committee_bundle import CanonicalCommitteeMeeting
from .schedule_repository import SourceVersionInput


def _topic_link_keywords(links: Any, topic: str) -> set[str]:
    if not isinstance(links, list):
        return set()
    for link in links:
        if isinstance(link, dict) and link.get("label") == topic:
            return {str(keyword) for keyword in link.get("keywords", []) if keyword}
    return set()


@dataclass(frozen=True, slots=True)
class MinutesIngestionResult:
    source_document_version_id: uuid.UUID
    meetings_seen: int
    meetings_inserted: int
    meeting_versions_inserted: int
    minute_entries_inserted: int


@dataclass(frozen=True, slots=True)
class AgendasIngestionResult:
    source_document_version_id: uuid.UUID
    records_seen: int
    agenda_items_inserted: int
    bills_inserted: int
    unresolved_records: int


class CommitteeRepository:
    source_system = "open.assembly.go.kr"

    def __init__(self, connection: Any):
        self.connection = connection

    def ingest_minutes(
        self,
        source: SourceVersionInput,
        meetings: Iterable[CanonicalCommitteeMeeting],
    ) -> MinutesIngestionResult:
        from psycopg.types.json import Jsonb

        document_id = self._upsert_document(source)
        version_id = self._upsert_source_version(document_id, source)
        seen = meetings_inserted = versions_inserted = entries_inserted = 0
        for meeting in meetings:
            seen += 1
            meeting_id, inserted, match_method = self._resolve_meeting(meeting)
            meetings_inserted += int(inserted)
            self.connection.execute(
                """
                INSERT INTO meeting_external_ids (
                    id, meeting_id, source_system, id_type, external_id
                ) VALUES (%s, %s, %s, 'CONF_ID', %s)
                ON CONFLICT (source_system, id_type, external_id) DO NOTHING
                """,
                (uuid.uuid4(), meeting_id, self.source_system, meeting.conference_id),
            )
            self.connection.execute(
                """
                INSERT INTO meeting_sources (
                    id, meeting_id, source_document_version_id, source_record_key,
                    reconciliation_status, match_method, match_confidence
                ) VALUES (%s, %s, %s, %s, 'MATCHED', %s, 1.0)
                ON CONFLICT (source_document_version_id, source_record_key) DO NOTHING
                """,
                (uuid.uuid4(), meeting_id, version_id, meeting.meeting_source_key, match_method),
            )
            row = self.connection.execute(
                """
                INSERT INTO meeting_versions (
                    id, meeting_id, source_document_version_id, source_record_key,
                    lifecycle_status, authority_status, title, meeting_type,
                    committee_name, scheduled_date, session_text, meeting_order_text,
                    official_data
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (meeting_id, source_document_version_id, source_record_key)
                DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), meeting_id, version_id, meeting.meeting_source_key,
                    meeting.lifecycle_status.value, meeting.authority_status.value,
                    meeting.title, meeting.class_name, meeting.committee_name,
                    meeting.conference_date, meeting.session_text,
                    meeting.meeting_order_text,
                    Jsonb({
                        "conference_id": meeting.conference_id,
                        "conference_number": meeting.conference_number,
                        "assembly_number": meeting.assembly_number,
                        "department_code": meeting.department_code,
                    }),
                ),
            ).fetchone()
            versions_inserted += int(row is not None)
            for section in meeting.sections:
                row = self.connection.execute(
                    """
                    INSERT INTO committee_minute_entries (
                        id, meeting_id, source_document_version_id, source_record_key,
                        conference_id, conference_number, subject_name, minutes_url,
                        pdf_url, pdf_file_id, vod_url, department_code,
                        authority_status, official_data
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        'OFFICIAL', %s
                    )
                    ON CONFLICT (source_document_version_id, source_record_key)
                    DO NOTHING RETURNING id
                    """,
                    (
                        uuid.uuid4(), meeting_id, version_id, section.source_record_key,
                        section.conference_id, section.conference_number,
                        section.subject_name, section.minutes_url, section.pdf_url,
                        section.pdf_file_id, section.vod_url, section.department_code,
                        Jsonb({"title": section.title, "class_name": section.class_name}),
                    ),
                ).fetchone()
                entries_inserted += int(row is not None)
        return MinutesIngestionResult(
            version_id, seen, meetings_inserted, versions_inserted, entries_inserted
        )

    def ingest_agendas(
        self,
        source: SourceVersionInput,
        records: Iterable[MeetingAgendaSourceRecord],
    ) -> AgendasIngestionResult:
        from psycopg.types.json import Jsonb

        document_id = self._upsert_document(source)
        version_id = self._upsert_source_version(document_id, source)
        seen = inserted_count = bills_inserted = unresolved = 0
        for record in records:
            seen += 1
            found = self.connection.execute(
                """
                SELECT meeting_id FROM meeting_external_ids
                WHERE source_system = %s AND id_type = 'CONF_ID' AND external_id = %s
                """,
                (self.source_system, record.conference_id),
            ).fetchone()
            if not found:
                unresolved += 1
                continue
            meeting_id = found[0]
            internal_bill_id: uuid.UUID | None = None
            if record.bill_id:
                candidate_id = uuid.uuid4()
                row = self.connection.execute(
                    """
                    INSERT INTO bills (id, bill_id, bill_name, official_url)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (bill_id) DO UPDATE SET
                        bill_name = EXCLUDED.bill_name,
                        official_url = COALESCE(EXCLUDED.official_url, bills.official_url),
                        updated_at = now()
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    (candidate_id, record.bill_id, record.bill_name, record.official_url),
                ).fetchone()
                internal_bill_id = row[0]
                bills_inserted += int(row[1])
            row = self.connection.execute(
                """
                INSERT INTO agenda_items (
                    id, meeting_id, bill_id, source_document_version_id,
                    source_record_key, conference_id, assembly_term, session_text,
                    meeting_order_text, agenda_name, official_url,
                    authority_status, official_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'OFFICIAL', %s
                )
                ON CONFLICT (source_document_version_id, source_record_key)
                DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), meeting_id, internal_bill_id, version_id,
                    record.source_record_key, record.conference_id,
                    record.assembly_term, record.session_text,
                    record.meeting_order_text, record.bill_name,
                    record.official_url, Jsonb({"bill_id": record.bill_id}),
                ),
            ).fetchone()
            inserted_count += int(row is not None)
        return AgendasIngestionResult(
            version_id, seen, inserted_count, bills_inserted, unresolved
        )

    def _resolve_meeting(
        self, meeting: CanonicalCommitteeMeeting
    ) -> tuple[uuid.UUID, bool, str]:
        existing = self.connection.execute(
            """
            SELECT meeting_id FROM meeting_external_ids
            WHERE source_system = %s AND id_type = 'CONF_ID' AND external_id = %s
            """,
            (self.source_system, meeting.conference_id),
        ).fetchone()
        if existing:
            return existing[0], False, "OFFICIAL_CONF_ID"

        candidates: list[Any] = []
        if meeting.session_text and meeting.meeting_order_text:
            candidates = self.connection.execute(
                """
                SELECT DISTINCT meeting_id FROM meeting_versions
                WHERE committee_name = %s AND scheduled_date = %s
                  AND session_text LIKE %s AND meeting_order_text = %s
                """,
                (
                    meeting.committee_name,
                    meeting.conference_date,
                    f"{meeting.session_text}%",
                    meeting.meeting_order_text,
                ),
            ).fetchall()
        if len(candidates) == 1:
            return candidates[0][0], False, "EXACT_COMMITTEE_DATE_SESSION_ORDER"

        row = self.connection.execute(
            """
            INSERT INTO meetings (id, meeting_uid) VALUES (%s, %s)
            ON CONFLICT (meeting_uid) DO NOTHING RETURNING id
            """,
            (uuid.uuid4(), meeting.meeting_uid),
        ).fetchone()
        if row:
            return row[0], True, "OFFICIAL_CONF_ID"
        existing = self.connection.execute(
            "SELECT id FROM meetings WHERE meeting_uid = %s", (meeting.meeting_uid,)
        ).fetchone()
        return existing[0], False, "OFFICIAL_CONF_ID"

    def _upsert_document(self, source: SourceVersionInput) -> uuid.UUID:
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
                uuid.uuid4(), self.source_system, source.source_type, external_id,
                source.source_url, source.retrieved_at,
            ),
        ).fetchone()
        return row[0]

    def _upsert_source_version(
        self, document_id: uuid.UUID, source: SourceVersionInput
    ) -> uuid.UUID:
        from psycopg.types.json import Jsonb

        row = self.connection.execute(
            """
            INSERT INTO source_document_versions (
                id, source_document_id, content_hash, source_url, raw_path,
                retrieved_at, parser_version, content_type, authority_status, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'OFFICIAL', %s)
            ON CONFLICT (source_document_id, content_hash)
            DO UPDATE SET parser_version = EXCLUDED.parser_version RETURNING id
            """,
            (
                uuid.uuid4(), document_id, source.content_hash, source.source_url,
                str(source.raw_path), source.retrieved_at, source.parser_version,
                source.content_type, Jsonb(source.metadata),
            ),
        ).fetchone()
        return row[0]

    def list_target_meetings(self, *, limit: int = 50) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT mei.external_id, mv.title, mv.committee_name, mv.scheduled_date,
                   mv.session_text, mv.meeting_order_text, mv.authority_status,
                   count(DISTINCT cme.id) AS minute_sections,
                   count(DISTINCT ai.id) AS agenda_items,
                   (SELECT document.publication_stage
                    FROM official_transcript_documents document
                    WHERE document.meeting_id = mei.meeting_id
                    ORDER BY document.retrieved_at DESC, document.id DESC LIMIT 1),
                   (SELECT document.utterance_count
                    FROM official_transcript_documents document
                    WHERE document.meeting_id = mei.meeting_id
                    ORDER BY document.retrieved_at DESC, document.id DESC LIMIT 1)
            FROM meeting_external_ids mei
            JOIN meeting_versions mv ON mv.meeting_id = mei.meeting_id
            LEFT JOIN committee_minute_entries cme ON cme.meeting_id = mei.meeting_id
            LEFT JOIN agenda_items ai ON ai.meeting_id = mei.meeting_id
            WHERE mei.source_system = %s AND mei.id_type = 'CONF_ID'
            GROUP BY mei.meeting_id, mei.external_id, mv.title, mv.committee_name, mv.scheduled_date,
                     mv.session_text, mv.meeting_order_text, mv.authority_status
            ORDER BY mv.scheduled_date DESC, mv.committee_name
            LIMIT %s
            """,
            (self.source_system, limit),
        ).fetchall()
        columns = (
            "conference_id", "title", "committee_name", "conference_date",
            "session_text", "meeting_order_text", "authority_status",
            "minute_sections", "agenda_items",
            "official_transcript_stage", "official_utterance_count",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        if not items:
            return items
        summaries = self.connection.execute(
            """
            WITH labels AS (
                SELECT external.external_id AS conference_id, 'TOPIC' AS kind,
                       label, count(*) AS label_count
                FROM meeting_external_ids external
                JOIN official_transcript_documents document
                  ON document.meeting_id = external.meeting_id
                JOIN official_transcript_utterances utterance
                  ON utterance.document_id = document.id
                JOIN official_utterance_annotations annotation
                  ON annotation.utterance_id = utterance.id
                CROSS JOIN LATERAL unnest(annotation.topics) label
                WHERE external.external_id = ANY(%s)
                  AND annotation.generator_version = %s
                  AND annotation.utterance_kind = 'POLICY'
                  AND label <> '절차·의결'
                GROUP BY external.external_id, label
                UNION ALL
                SELECT external.external_id, 'MINISTRY', label, count(*)
                FROM meeting_external_ids external
                JOIN official_transcript_documents document
                  ON document.meeting_id = external.meeting_id
                JOIN official_transcript_utterances utterance
                  ON utterance.document_id = document.id
                JOIN official_utterance_annotations annotation
                  ON annotation.utterance_id = utterance.id
                CROSS JOIN LATERAL unnest(annotation.ministries) label
                WHERE external.external_id = ANY(%s)
                  AND annotation.generator_version = %s
                  AND annotation.utterance_kind = 'POLICY'
                GROUP BY external.external_id, label
            ), ranked AS (
                SELECT *, row_number() OVER (
                    PARTITION BY conference_id, kind ORDER BY label_count DESC, label
                ) AS rank
                FROM labels
            )
            SELECT conference_id, kind, label, label_count FROM ranked WHERE rank = 1
            """,
            (
                [item["conference_id"] for item in items], INSIGHT_VERSION,
                [item["conference_id"] for item in items], INSIGHT_VERSION,
            ),
        ).fetchall()
        by_id = {item["conference_id"]: item for item in items}
        for item in items:
            item["top_policy_topic"] = None
            item["top_policy_topic_count"] = 0
            item["top_related_ministry"] = None
            item["top_related_ministry_count"] = 0
            item["insight_status"] = "PROVISIONAL_DRAFT"
        for conference_id, kind, label, count in summaries:
            target = by_id[conference_id]
            if kind == "TOPIC":
                target["top_policy_topic"] = label
                target["top_policy_topic_count"] = count
            else:
                target["top_related_ministry"] = label
                target["top_related_ministry_count"] = count
        return items

    def list_official_transcript(
        self, conference_id: str, *, offset: int = 0, limit: int = 100,
        topic: str | None = None, ministry: str | None = None,
    ) -> dict[str, Any] | None:
        document = self.connection.execute(
            """
            SELECT document.id, version.committee_name, version.scheduled_date,
                   version.session_text, version.meeting_order_text,
                   document.publication_stage, document.authority_status,
                   document.status_text, document.title, document.utterance_count,
                   source.source_url, document.retrieved_at
            FROM meeting_external_ids external
            JOIN meeting_versions version ON version.meeting_id = external.meeting_id
            JOIN official_transcript_documents document
              ON document.meeting_id = external.meeting_id
            JOIN source_document_versions source
              ON source.id = document.source_document_version_id
            WHERE external.source_system = %s AND external.id_type = 'CONF_ID'
              AND external.external_id = %s
              AND version.committee_name IN (
                    '행정안전위원회', '예산결산특별위원회', '법제사법위원회'
                  )
            ORDER BY document.retrieved_at DESC, document.id DESC LIMIT 1
            """,
            (self.source_system, conference_id),
        ).fetchone()
        if document is None:
            return None
        columns = (
            "document_id", "committee_name", "conference_date", "session_text",
            "meeting_order_text", "publication_stage", "authority_status",
            "status_text", "title", "utterance_count", "source_url", "retrieved_at",
        )
        result = dict(zip(columns, document, strict=True))
        rows = self.connection.execute(
            """
            SELECT utterance.sequence_number, utterance.source_speaker_id,
                   utterance.source_span_id, utterance.agenda_item_ref,
                   utterance.speaker_name, utterance.speaker_role, utterance.text,
                   COALESCE(annotation.topics, '{}'), COALESCE(annotation.ministries, '{}'),
                   annotation.review_status, annotation.classification_method,
                   annotation.utterance_kind, annotation.evidence_keywords,
                   annotation.topic_links, annotation.ministry_links
            FROM official_transcript_utterances utterance
            LEFT JOIN official_utterance_annotations annotation
              ON annotation.utterance_id = utterance.id
             AND annotation.generator_version = %s
            WHERE utterance.document_id = %s
              AND (%s::text IS NULL OR %s = ANY(COALESCE(annotation.topics, '{}')))
              AND (%s::text IS NULL OR %s = ANY(COALESCE(annotation.ministries, '{}')))
            ORDER BY utterance.sequence_number OFFSET %s LIMIT %s
            """,
            (INSIGHT_VERSION, result["document_id"], topic, topic, ministry, ministry, offset, limit),
        ).fetchall()
        item_columns = (
            "sequence_number", "source_speaker_id", "source_span_id",
            "agenda_item_ref", "speaker_name", "speaker_role", "text",
            "topics", "ministries", "annotation_review_status", "classification_method",
            "utterance_kind", "evidence_keywords", "topic_links", "ministry_links",
        )
        result["items"] = [dict(zip(item_columns, row, strict=True)) for row in rows]
        result["conference_id"] = conference_id
        result["offset"] = offset
        result["limit"] = limit
        result["topic_filter"] = topic
        result["ministry_filter"] = ministry
        result["insights"] = self._official_transcript_insights(result["document_id"])
        return result

    def policy_flow(self, committee_name: str | None = None) -> dict[str, Any]:
        rows = self.connection.execute(
            """
            WITH latest_documents AS (
                SELECT DISTINCT ON (meeting_id) id, meeting_id, source_document_version_id
                FROM official_transcript_documents
                ORDER BY meeting_id, retrieved_at DESC, id DESC
            )
            SELECT external.external_id, version.committee_name,
                   version.scheduled_date, utterance.sequence_number,
                   utterance.source_span_id, utterance.speaker_name,
                   utterance.speaker_role, utterance.text,
                   annotation.topics, annotation.ministries, annotation.topic_links,
                   source.source_url, bill.bill_id, agenda.agenda_name,
                   bill_version.bill_number, bill_version.bill_name,
                   bill_version.process_stage_code, bill_version.committee_result,
                   bill_version.plenary_result,
                   COALESCE(bill_version.official_url, bill.official_url)
            FROM latest_documents document
            JOIN meeting_external_ids external ON external.meeting_id = document.meeting_id
              AND external.source_system = %s AND external.id_type = 'CONF_ID'
            JOIN LATERAL (
                SELECT committee_name, scheduled_date
                FROM meeting_versions
                WHERE meeting_id = document.meeting_id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) version ON true
            JOIN official_transcript_utterances utterance
              ON utterance.document_id = document.id
            JOIN official_utterance_annotations annotation
              ON annotation.utterance_id = utterance.id
             AND annotation.generator_version = %s
             AND annotation.utterance_kind = 'POLICY'
            JOIN source_document_versions source
              ON source.id = document.source_document_version_id
            LEFT JOIN official_utterance_agenda_links agenda_link
              ON agenda_link.utterance_id = utterance.id
             AND agenda_link.reconciliation_status = 'MATCHED'
             AND agenda_link.match_method = 'EXACT_ITEM_REF_AGENDA_PREFIX'
            LEFT JOIN agenda_items agenda ON agenda.id = agenda_link.agenda_item_id
            LEFT JOIN bills bill ON bill.id = agenda.bill_id
            LEFT JOIN LATERAL (
                SELECT bill_number, bill_name, process_stage_code,
                       committee_result, plenary_result, official_url
                FROM bill_versions
                WHERE bill_id = bill.id
                ORDER BY created_at DESC, id DESC LIMIT 1
            ) bill_version ON true
            WHERE (%s::text IS NULL OR version.committee_name = %s)
            ORDER BY version.scheduled_date DESC, external.external_id,
                     utterance.sequence_number
            """,
            (self.source_system, INSIGHT_VERSION, committee_name, committee_name),
        ).fetchall()
        topics: dict[str, dict[str, Any]] = {}
        ministry_totals: dict[str, int] = {}
        committees: set[str] = set()
        for (
            conference_id, committee, meeting_date, sequence, span_id,
            speaker_name, speaker_role, text, topic_labels, ministries, topic_links, source_url,
            bill_id, agenda_name, bill_number, bill_name, process_stage,
            committee_result, plenary_result, bill_official_url,
        ) in rows:
            committees.add(committee)
            for ministry in ministries:
                ministry_totals[ministry] = ministry_totals.get(ministry, 0) + 1
            for topic in topic_labels:
                if topic == "절차·의결":
                    continue
                group = topics.setdefault(topic, {
                    "topic": topic, "statement_count": 0,
                    "committees": {}, "ministries": {}, "bills": {}, "evidence": None,
                })
                group["statement_count"] += 1
                group["committees"][committee] = group["committees"].get(committee, 0) + 1
                for ministry in ministries:
                    group["ministries"][ministry] = group["ministries"].get(ministry, 0) + 1
                candidate = {
                    "conference_id": conference_id,
                    "committee_name": committee,
                    "conference_date": meeting_date,
                    "sequence_number": sequence,
                    "source_span_id": span_id,
                    "speaker_name": speaker_name,
                    "speaker_role": speaker_role,
                    "text": text,
                    "source_url": source_url,
                    "topic_evidence_keywords": sorted(_topic_link_keywords(topic_links, topic)),
                }
                current = group["evidence"]
                if current is None or len(text) > len(current["text"]):
                    group["evidence"] = candidate
                if bill_id:
                    group["bills"][bill_id] = {
                        "bill_id": bill_id,
                        "agenda_name": agenda_name,
                        "bill_number": bill_number,
                        "bill_name": bill_name,
                        "process_stage_code": process_stage,
                        "committee_result": committee_result,
                        "plenary_result": plenary_result,
                        "official_url": bill_official_url,
                        "match_method": "EXACT_ITEM_REF_AGENDA_PREFIX",
                        "match_confidence": 1.0,
                    }
        items = []
        for group in topics.values():
            group["committees"] = [
                {"label": label, "count": count}
                for label, count in sorted(group["committees"].items(), key=lambda item: (-item[1], item[0]))
            ]
            group["ministries"] = [
                {"label": label, "count": count, "relation": "RELATED"}
                for label, count in sorted(group["ministries"].items(), key=lambda item: (-item[1], item[0]))
            ]
            group["bills"] = sorted(
                group["bills"].values(),
                key=lambda bill: (bill.get("bill_number") or "", bill["bill_id"]),
                reverse=True,
            )
            group["evidence_keywords"] = (
                group["evidence"].get("topic_evidence_keywords", [])
                if group["evidence"] else []
            )
            items.append(group)
        items.sort(key=lambda item: (-item["statement_count"], item["topic"]))
        return {
            "items": items,
            "policy_statement_count": len(rows),
            "topic_count": len(items),
            "committee_count": len(committees),
            "linked_bill_count": len({
                bill["bill_id"] for item in items for bill in item["bills"]
            }),
            "ministries": [
                {"label": label, "count": count, "relation": "RELATED"}
                for label, count in sorted(ministry_totals.items(), key=lambda item: (-item[1], item[0]))
            ],
            "committee_filter": committee_name,
            "generator_version": INSIGHT_VERSION,
            "authority_status": "PROVISIONAL",
            "review_status": "DRAFT",
        }

    def _official_transcript_insights(self, document_id: uuid.UUID) -> dict[str, Any]:
        topics = self.connection.execute(
            """
            SELECT label, count(*) FROM official_transcript_utterances utterance
            JOIN official_utterance_annotations annotation ON annotation.utterance_id = utterance.id
            CROSS JOIN LATERAL unnest(annotation.topics) label
            WHERE utterance.document_id = %s AND annotation.generator_version = %s
              AND annotation.utterance_kind = 'POLICY' AND label <> '절차·의결'
            GROUP BY label ORDER BY count(*) DESC, label
            """,
            (document_id, INSIGHT_VERSION),
        ).fetchall()
        ministries = self.connection.execute(
            """
            SELECT label, count(*) FROM official_transcript_utterances utterance
            JOIN official_utterance_annotations annotation ON annotation.utterance_id = utterance.id
            CROSS JOIN LATERAL unnest(annotation.ministries) label
            WHERE utterance.document_id = %s AND annotation.generator_version = %s
              AND annotation.utterance_kind = 'POLICY'
            GROUP BY label ORDER BY count(*) DESC, label
            """,
            (document_id, INSIGHT_VERSION),
        ).fetchall()
        return {
            "generator_version": INSIGHT_VERSION,
            "authority_status": "PROVISIONAL",
            "review_status": "DRAFT",
            "scope": "POLICY_ONLY",
            "topics": [{"label": label, "count": count} for label, count in topics],
            "ministries": [{"label": label, "count": count} for label, count in ministries],
        }
