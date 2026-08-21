from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from ..adapters.national_assembly.base import SourcePayload
from ..adapters.national_assembly.client import NationalAssemblyClient
from ..adapters.national_assembly.committee_minutes import CommitteeMinutesAdapter
from ..adapters.national_assembly.contracts import get_contract
from ..adapters.national_assembly.json_envelope import parse_json_envelope
from ..adapters.national_assembly.meeting_agendas import MeetingAgendasAdapter
from ..config import PROJECT_DIR, get_settings
from ..db.committee_repository import CommitteeRepository
from ..db.connection import connect
from ..db.schedule_repository import SourceVersionInput
from ..domain.committee_bundle import group_target_committee_minutes
from ..storage.raw_store import RawArtifact, RawStore


def _source_input(payload: SourcePayload, artifact: RawArtifact, parser_version: str) -> SourceVersionInput:
    try:
        raw_path = artifact.content_path.relative_to(PROJECT_DIR)
    except ValueError:
        raw_path = artifact.content_path
    return SourceVersionInput(
        source_type=payload.source_key,
        source_url=payload.source_url,
        content_hash=artifact.content_hash,
        raw_path=raw_path,
        retrieved_at=payload.retrieved_at,
        parser_version=parser_version,
        content_type=payload.content_type,
        metadata={"http_status": payload.http_status},
    )


def _fetch_pages(client: NationalAssemblyClient, source_key: str, filters: dict[str, str], page_size: int) -> list[SourcePayload]:
    contract = get_contract(source_key)
    first = client.fetch(source_key, page=1, page_size=page_size, filters=filters)
    envelope = parse_json_envelope(first.content, expected_resource=contract.resource)
    pages = max(1, math.ceil(envelope.total_count / page_size))
    return [first] + [
        client.fetch(source_key, page=page, page_size=page_size, filters=filters)
        for page in range(2, pages + 1)
    ]


def sync_committee_bundle(
    *, conference_date: str, assembly_number: str, page_size: int,
    api_key: str, database_url: str, raw_data_dir: Path,
) -> dict[str, Any]:
    client = NationalAssemblyClient(api_key)
    raw_store = RawStore(raw_data_dir)
    minutes_adapter = CommitteeMinutesAdapter()
    agendas_adapter = MeetingAgendasAdapter()
    minute_pages = _fetch_pages(
        client, "committee_minutes",
        {"DAE_NUM": assembly_number, "CONF_DATE": conference_date}, page_size,
    )
    conference_ids: set[str] = set()
    summary: dict[str, Any] = {
        "conference_date": conference_date, "assembly_number": assembly_number,
        "minute_pages": len(minute_pages), "minute_rows_seen": 0,
        "target_meetings_seen": 0, "minute_entries_inserted": 0,
        "agenda_pages": 0, "agenda_rows_seen": 0,
        "agenda_items_inserted": 0, "bills_inserted": 0,
        "unresolved_agenda_rows": 0, "conference_ids": [],
    }
    for payload in minute_pages:
        artifact = raw_store.save(payload, parser_version=minutes_adapter.parser_version)
        records = minutes_adapter.parse(payload)
        meetings = group_target_committee_minutes(records)
        summary["minute_rows_seen"] += len(records)
        summary["target_meetings_seen"] += len(meetings)
        conference_ids.update(item.conference_id for item in meetings)
        with connect(database_url) as connection:
            result = CommitteeRepository(connection).ingest_minutes(
                _source_input(payload, artifact, minutes_adapter.parser_version), meetings,
            )
        summary["minute_entries_inserted"] += result.minute_entries_inserted

    for conference_id in sorted(conference_ids):
        agenda_pages = _fetch_pages(
            client, "meeting_agendas", {"CONF_ID": conference_id}, page_size,
        )
        summary["agenda_pages"] += len(agenda_pages)
        for payload in agenda_pages:
            artifact = raw_store.save(payload, parser_version=agendas_adapter.parser_version)
            records = agendas_adapter.parse(payload)
            summary["agenda_rows_seen"] += len(records)
            with connect(database_url) as connection:
                result = CommitteeRepository(connection).ingest_agendas(
                    _source_input(payload, artifact, agendas_adapter.parser_version), records,
                )
            summary["agenda_items_inserted"] += result.agenda_items_inserted
            summary["bills_inserted"] += result.bills_inserted
            summary["unresolved_agenda_rows"] += result.unresolved_records
    summary["conference_ids"] = sorted(conference_ids)
    return summary


if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser(description="대상 위원회의 회의록과 회의별 의안을 raw 보존 후 정규화합니다.")
    parser.add_argument("--date", required=True, help="회의일 YYYY-MM-DD")
    parser.add_argument("--assembly-number", default="22")
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args()
    result = sync_committee_bundle(
        conference_date=args.date, assembly_number=args.assembly_number,
        page_size=args.page_size, api_key=settings.national_assembly_api_key,
        database_url=settings.database_url, raw_data_dir=settings.raw_data_dir,
    )
    print(json.dumps(result, ensure_ascii=False))
