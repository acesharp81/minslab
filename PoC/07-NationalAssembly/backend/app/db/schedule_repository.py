from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from ..domain.schedule import CanonicalScheduleEntry


@dataclass(frozen=True, slots=True)
class SourceVersionInput:
    source_type: str
    source_url: str
    content_hash: str
    raw_path: Path
    retrieved_at: datetime
    parser_version: str
    content_type: str
    metadata: dict[str, Any]


@dataclass(frozen=True, slots=True)
class IngestionResult:
    source_document_version_id: uuid.UUID
    records_seen: int
    schedule_entries_inserted: int
    meetings_inserted: int
    meeting_versions_inserted: int


class ScheduleRepository:
    source_system = "open.assembly.go.kr"

    def __init__(self, connection: Any):
        self.connection = connection

    def ingest(
        self,
        source: SourceVersionInput,
        entries: Iterable[CanonicalScheduleEntry],
    ) -> IngestionResult:
        from psycopg.types.json import Jsonb

        document_id = self._upsert_document(source)
        version_id = self._upsert_source_version(document_id, source)
        records_seen = schedule_count = meeting_count = meeting_version_count = 0

        for entry in entries:
            records_seen += 1
            meeting_id: uuid.UUID | None = None
            if entry.meeting_uid is not None:
                meeting_id, meeting_inserted = self._upsert_meeting(entry.meeting_uid)
                meeting_count += int(meeting_inserted)
                self.connection.execute(
                    """
                    INSERT INTO meeting_sources (
                        id, meeting_id, source_document_version_id, source_record_key,
                        reconciliation_status, match_method, match_confidence
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (source_document_version_id, source_record_key) DO NOTHING
                    """,
                    (
                        uuid.uuid4(), meeting_id, version_id, entry.source_record_key,
                        entry.reconciliation_status.value, "OFFICIAL_SCHEDULE_IDENTITY", 1.0,
                    ),
                )
                inserted = self.connection.execute(
                    """
                    INSERT INTO meeting_versions (
                        id, meeting_id, source_document_version_id, source_record_key,
                        lifecycle_status, authority_status, title, meeting_type,
                        committee_name, scheduled_date, start_time, end_time, time_text,
                        session_text, meeting_order_text, place, official_data
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    ON CONFLICT (meeting_id, source_document_version_id, source_record_key)
                    DO NOTHING RETURNING id
                    """,
                    (
                        uuid.uuid4(), meeting_id, version_id, entry.source_record_key,
                        entry.lifecycle_status.value, entry.authority_status.value,
                        entry.title, entry.meeting_type, entry.committee_name,
                        entry.scheduled_date, entry.start_time, entry.end_time,
                        entry.time_text, entry.session_text, entry.meeting_order_text,
                        entry.place, Jsonb(entry.official_data()),
                    ),
                ).fetchone()
                meeting_version_count += int(inserted is not None)

            inserted = self.connection.execute(
                """
                INSERT INTO schedule_entries (
                    id, source_document_version_id, source_record_key, meeting_id,
                    schedule_kind, title, scheduled_date, start_time, end_time, time_text,
                    meeting_type, committee_name, session_text, meeting_order_text,
                    host_name, place, is_target_committee, authority_status,
                    reconciliation_status, official_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (source_document_version_id, source_record_key)
                DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), version_id, entry.source_record_key, meeting_id,
                    entry.schedule_kind, entry.title, entry.scheduled_date,
                    entry.start_time, entry.end_time, entry.time_text, entry.meeting_type,
                    entry.committee_name, entry.session_text, entry.meeting_order_text,
                    entry.host_name, entry.place, entry.is_target_committee,
                    entry.authority_status.value,
                    entry.reconciliation_status.value, Jsonb(entry.official_data()),
                ),
            ).fetchone()
            schedule_count += int(inserted is not None)

        return IngestionResult(
            source_document_version_id=version_id,
            records_seen=records_seen,
            schedule_entries_inserted=schedule_count,
            meetings_inserted=meeting_count,
            meeting_versions_inserted=meeting_version_count,
        )

    def _upsert_document(self, source: SourceVersionInput) -> uuid.UUID:
        external_id = hashlib.sha256(source.source_url.encode("utf-8")).hexdigest()
        row = self.connection.execute(
            """
            INSERT INTO source_documents (
                id, source_system, source_type, external_id, canonical_url, first_seen_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_system, source_type, external_id)
            DO UPDATE SET canonical_url = EXCLUDED.canonical_url
            RETURNING id
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
            DO UPDATE SET parser_version = EXCLUDED.parser_version
            RETURNING id
            """,
            (
                uuid.uuid4(), document_id, source.content_hash, source.source_url,
                str(source.raw_path), source.retrieved_at, source.parser_version,
                source.content_type, Jsonb(source.metadata),
            ),
        ).fetchone()
        return row[0]

    def _upsert_meeting(self, meeting_uid: uuid.UUID) -> tuple[uuid.UUID, bool]:
        row = self.connection.execute(
            """
            INSERT INTO meetings (id, meeting_uid) VALUES (%s, %s)
            ON CONFLICT (meeting_uid) DO NOTHING RETURNING id
            """,
            (uuid.uuid4(), meeting_uid),
        ).fetchone()
        if row:
            return row[0], True
        existing = self.connection.execute(
            "SELECT id FROM meetings WHERE meeting_uid = %s", (meeting_uid,)
        ).fetchone()
        return existing[0], False

    def list_schedule_for_date(self, scheduled_date: Any) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT se.id, se.meeting_id, se.schedule_kind, se.title,
                   se.scheduled_date, se.start_time, se.end_time, se.time_text,
                   se.meeting_type, se.committee_name, se.session_text,
                   se.meeting_order_text, se.host_name, se.place,
                   se.is_target_committee, se.authority_status, se.reconciliation_status,
                   sdv.source_url, sdv.retrieved_at, sdv.content_hash,
                   sdv.parser_version
            FROM schedule_entries se
            JOIN source_document_versions sdv ON sdv.id = se.source_document_version_id
            WHERE se.scheduled_date = %s
            ORDER BY se.start_time NULLS LAST, se.title
            """,
            (scheduled_date,),
        ).fetchall()
        columns = (
            "id", "meeting_id", "schedule_kind", "title", "scheduled_date",
            "start_time", "end_time", "time_text", "meeting_type",
            "committee_name", "session_text", "meeting_order_text", "host_name",
            "place", "is_target_committee", "authority_status", "reconciliation_status", "source_url",
            "retrieved_at", "content_hash", "parser_version",
        )
        return [dict(zip(columns, row, strict=True)) for row in rows]
