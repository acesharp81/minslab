from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

from ..adapters.national_assembly.bills import BillDetailSourceRecord
from .schedule_repository import SourceVersionInput


@dataclass(frozen=True, slots=True)
class BillDetailsIngestionResult:
    source_document_version_id: uuid.UUID
    records_seen: int
    versions_inserted: int
    unresolved_records: int


def _date_or_none(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid official date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"invalid official date: {value!r}")
    return parsed


class BillRepository:
    source_system = "open.assembly.go.kr"

    def __init__(self, connection: Any):
        self.connection = connection

    def target_bill_external_ids(self) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT b.bill_id
            FROM bills b
            JOIN agenda_items ai ON ai.bill_id = b.id
            ORDER BY b.bill_id
            """
        ).fetchall()
        return [row[0] for row in rows]

    def pending_official_documents(self, limit: int = 10) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (bill_id) bill_id, bill_name, official_url, official_data
                FROM bill_versions ORDER BY bill_id, created_at DESC
            )
            SELECT b.id, b.bill_id, latest.bill_name, latest.official_url,
                   latest.official_data->>'PDF_URL1'
            FROM bills b JOIN latest ON latest.bill_id = b.id
            WHERE NULLIF(latest.official_data->>'PDF_URL1', '') IS NOT NULL
            ORDER BY b.bill_id LIMIT %s
            """,
            (limit,),
        ).fetchall()
        columns = ("bill_uuid", "bill_id", "bill_name", "official_url", "pdf_urls")
        return [dict(zip(columns, row, strict=True)) for row in rows]

    def ingest_official_document(
        self, *, bill_uuid: uuid.UUID, source: SourceVersionInput,
        document_index: int, title: str | None, pages: list[str],
        sections: list[dict[str, Any]],
    ) -> dict[str, Any]:
        semantic_hash = hashlib.md5("\f".join(pages).encode("utf-8"), usedforsecurity=False).hexdigest()
        existing = self.connection.execute(
            "SELECT id FROM bill_official_documents WHERE bill_id = %s AND semantic_hash = %s LIMIT 1",
            (bill_uuid, semantic_hash),
        ).fetchone()
        if existing:
            return {"document_id": str(existing[0]), "sections_inserted": 0, "semantic_duplicate": True}
        document_source_id = self._upsert_document(source)
        version_id = self._upsert_source_version(document_source_id, source)
        row = self.connection.execute(
            """
            INSERT INTO bill_official_documents (
                id, bill_id, source_document_version_id, document_kind,
                document_index, title, page_count, extracted_text,
                parser_version, authority_status, semantic_hash
            ) VALUES (%s, %s, %s, 'OFFICIAL_PDF', %s, %s, %s, %s, %s, 'OFFICIAL', %s)
            ON CONFLICT (bill_id, source_document_version_id, document_index)
            DO UPDATE SET extracted_text = EXCLUDED.extracted_text,
                          parser_version = EXCLUDED.parser_version
            RETURNING id
            """,
            (
                uuid.uuid4(), bill_uuid, version_id, document_index, title,
                len(pages), "\f".join(pages), source.parser_version, semantic_hash,
            ),
        ).fetchone()
        document_id = row[0]
        inserted = 0
        for section in sections:
            saved = self.connection.execute(
                """
                INSERT INTO bill_official_document_sections (
                    id, document_id, section_kind, heading, source_span_id,
                    page_start, page_end, text
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (document_id, section_kind, source_span_id) DO NOTHING
                RETURNING id
                """,
                (
                    uuid.uuid4(), document_id, section["section_kind"],
                    section["heading"], section["source_span_id"],
                    section["page_start"], section["page_end"], section["text"],
                ),
            ).fetchone()
            inserted += int(saved is not None)
        return {"document_id": str(document_id), "sections_inserted": inserted, "semantic_duplicate": False}

    def ingest_details(
        self,
        source: SourceVersionInput,
        records: Iterable[BillDetailSourceRecord],
    ) -> BillDetailsIngestionResult:
        from psycopg.types.json import Jsonb

        document_id = self._upsert_document(source)
        version_id = self._upsert_source_version(document_id, source)
        seen = inserted = unresolved = 0
        for record in records:
            seen += 1
            bill = self.connection.execute(
                "SELECT id FROM bills WHERE bill_id = %s", (record.bill_id,)
            ).fetchone()
            if not bill:
                unresolved += 1
                continue
            self.connection.execute(
                """
                UPDATE bills SET bill_name = %s,
                    official_url = COALESCE(%s, official_url), updated_at = now()
                WHERE id = %s
                """,
                (record.bill_name, record.official_url, bill[0]),
            )
            row = self.connection.execute(
                """
                INSERT INTO bill_versions (
                    id, bill_id, source_document_version_id, source_record_key,
                    assembly_term, bill_number, bill_kind, bill_name,
                    proposer_kind, proposer_name, proposal_date, committee_name,
                    committee_process_date, committee_result,
                    plenary_resolution_date, plenary_result, pass_classification,
                    process_stage_code, official_url, authority_status, official_data
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, 'OFFICIAL', %s
                )
                ON CONFLICT (bill_id, source_document_version_id, source_record_key)
                DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), bill[0], version_id, record.source_record_key,
                    record.assembly_term, record.bill_number, record.bill_kind,
                    record.bill_name, record.proposer_kind, record.proposer_name,
                    _date_or_none(record.proposal_date_text), record.committee_name,
                    _date_or_none(record.committee_process_date_text),
                    record.committee_result,
                    _date_or_none(record.plenary_resolution_date_text),
                    record.plenary_result, record.pass_classification,
                    record.process_stage_code, record.official_url,
                    Jsonb(record.official_data),
                ),
            ).fetchone()
            inserted += int(row is not None)
        return BillDetailsIngestionResult(version_id, seen, inserted, unresolved)

    def search_target_bills(
        self,
        *,
        query: str | None = None,
        committee_name: str | None = None,
        process_stage: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        where = ["1 = 1"]
        parameters: list[Any] = []
        if query:
            where.append(
                "(latest.bill_name ILIKE %s OR latest.proposer_name ILIKE %s "
                "OR latest.bill_number ILIKE %s)"
            )
            pattern = f"%{query}%"
            parameters.extend((pattern, pattern, pattern))
        if committee_name:
            where.append("mv.committee_name = %s")
            parameters.append(committee_name)
        if process_stage:
            where.append("latest.process_stage_code = %s")
            parameters.append(process_stage)
        parameters.append(limit)
        rows = self.connection.execute(
            f"""
            WITH latest AS (
                SELECT DISTINCT ON (bv.bill_id)
                    bv.*, sdv.source_url, sdv.retrieved_at, sdv.content_hash,
                    sdv.parser_version
                FROM bill_versions bv
                JOIN source_document_versions sdv
                  ON sdv.id = bv.source_document_version_id
                ORDER BY bv.bill_id, bv.created_at DESC
            )
            SELECT b.bill_id, latest.bill_number, latest.bill_name,
                   latest.bill_kind, latest.proposer_kind, latest.proposer_name,
                   latest.proposal_date, latest.committee_name,
                   latest.committee_process_date, latest.committee_result,
                   latest.plenary_resolution_date, latest.plenary_result,
                   latest.pass_classification, latest.process_stage_code,
                   latest.official_url, latest.authority_status,
                   array_agg(DISTINCT mv.committee_name ORDER BY mv.committee_name),
                   latest.source_url, latest.retrieved_at, latest.content_hash,
                   latest.parser_version
            FROM bills b
            JOIN latest ON latest.bill_id = b.id
            JOIN agenda_items ai ON ai.bill_id = b.id
            JOIN meeting_versions mv ON mv.meeting_id = ai.meeting_id
            WHERE {' AND '.join(where)}
            GROUP BY b.bill_id, latest.bill_number, latest.bill_name,
                     latest.bill_kind, latest.proposer_kind, latest.proposer_name,
                     latest.proposal_date, latest.committee_name,
                     latest.committee_process_date, latest.committee_result,
                     latest.plenary_resolution_date, latest.plenary_result,
                     latest.pass_classification, latest.process_stage_code,
                     latest.official_url, latest.authority_status,
                     latest.source_url, latest.retrieved_at, latest.content_hash,
                     latest.parser_version
            ORDER BY latest.proposal_date DESC NULLS LAST, latest.bill_number DESC
            LIMIT %s
            """,
            tuple(parameters),
        ).fetchall()
        columns = (
            "bill_id", "bill_number", "bill_name", "bill_kind",
            "proposer_kind", "proposer_name", "proposal_date",
            "committee_name", "committee_process_date", "committee_result",
            "plenary_resolution_date", "plenary_result", "pass_classification",
            "process_stage_code", "official_url", "authority_status",
            "target_meeting_committees", "source_url", "retrieved_at",
            "content_hash", "parser_version",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        if not items:
            return items
        document_rows = self.connection.execute(
            """
            SELECT DISTINCT ON (b.bill_id) b.bill_id, source.source_url,
                   source.content_hash, document.page_count,
                   document.parser_version,
                   COALESCE((
                       SELECT jsonb_agg(jsonb_build_object(
                           'section_kind', section.section_kind,
                           'heading', section.heading,
                           'source_span_id', section.source_span_id,
                           'page_start', section.page_start,
                           'page_end', section.page_end,
                           'text', left(section.text, 1200),
                           'is_excerpt', length(section.text) > 1200
                       ) ORDER BY section.page_start, section.id)
                       FROM bill_official_document_sections section
                       WHERE section.document_id = document.id
                   ), '[]'::jsonb)
            FROM bills b
            JOIN bill_official_documents document ON document.bill_id = b.id
            JOIN source_document_versions source
              ON source.id = document.source_document_version_id
            WHERE b.bill_id = ANY(%s)
            ORDER BY b.bill_id, document.created_at DESC, document.id DESC
            """,
            ([item["bill_id"] for item in items],),
        ).fetchall()
        documents = {
            row[0]: {
                "source_url": row[1], "content_hash": row[2],
                "page_count": row[3], "parser_version": row[4],
                "sections": row[5], "authority_status": "OFFICIAL",
            }
            for row in document_rows
        }
        for item in items:
            item["official_document"] = documents.get(item["bill_id"])
        return items

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

    def _upsert_source_version(self, document_id: uuid.UUID, source: SourceVersionInput) -> uuid.UUID:
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
