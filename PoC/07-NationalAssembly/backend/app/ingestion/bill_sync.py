from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..adapters.national_assembly.bills import BillsAdapter
from ..adapters.national_assembly.client import NationalAssemblyClient
from ..config import PROJECT_DIR, get_settings
from ..db.bill_repository import BillRepository
from ..db.connection import connect
from ..db.schedule_repository import SourceVersionInput
from ..storage.raw_store import RawArtifact, RawStore


def _source_input(payload: Any, artifact: RawArtifact, parser_version: str) -> SourceVersionInput:
    try:
        raw_path = artifact.content_path.relative_to(PROJECT_DIR)
    except ValueError:
        raw_path = artifact.content_path
    return SourceVersionInput(
        source_type=payload.source_key, source_url=payload.source_url,
        content_hash=artifact.content_hash, raw_path=raw_path,
        retrieved_at=payload.retrieved_at, parser_version=parser_version,
        content_type=payload.content_type, metadata={"http_status": payload.http_status},
    )


def sync_target_bill_details(
    *, assembly_term: str, api_key: str, database_url: str, raw_data_dir: Path,
) -> dict[str, Any]:
    with connect(database_url) as connection:
        bill_ids = BillRepository(connection).target_bill_external_ids()
    client = NationalAssemblyClient(api_key)
    adapter = BillsAdapter()
    raw_store = RawStore(raw_data_dir)
    summary: dict[str, Any] = {
        "assembly_term": assembly_term, "bills_requested": len(bill_ids),
        "details_seen": 0, "versions_inserted": 0,
        "missing_details": [], "unresolved_records": 0,
    }
    for bill_id in bill_ids:
        payload = client.fetch(
            "bills", page_size=10,
            filters={"ERACO": assembly_term, "BILL_ID": bill_id},
        )
        artifact = raw_store.save(payload, parser_version=adapter.parser_version)
        records = adapter.parse(payload)
        if not records:
            summary["missing_details"].append(bill_id)
        if any(record.bill_id != bill_id for record in records):
            raise ValueError(f"bill filter returned an unexpected BILL_ID for {bill_id}")
        with connect(database_url) as connection:
            result = BillRepository(connection).ingest_details(
                _source_input(payload, artifact, adapter.parser_version), records,
            )
        summary["details_seen"] += result.records_seen
        summary["versions_inserted"] += result.versions_inserted
        summary["unresolved_records"] += result.unresolved_records
    return summary


if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser(description="대상 회의에 연결된 의안의 공식 상세정보를 동기화합니다.")
    parser.add_argument("--assembly-term", default="제22대")
    args = parser.parse_args()
    print(json.dumps(sync_target_bill_details(
        assembly_term=args.assembly_term,
        api_key=settings.national_assembly_api_key,
        database_url=settings.database_url,
        raw_data_dir=settings.raw_data_dir,
    ), ensure_ascii=False))
