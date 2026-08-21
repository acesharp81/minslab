from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from ..adapters.national_assembly.base import SourcePayload
from ..adapters.national_assembly.schedule import ScheduleAdapter
from ..config import PROJECT_DIR, get_settings
from ..db.connection import connect
from ..db.schedule_repository import ScheduleRepository, SourceVersionInput
from ..domain.schedule import normalize_schedule


def latest_manifest(raw_root: Path) -> Path:
    manifests = list((raw_root / "assembly_schedule").rglob("*.manifest.json"))
    if not manifests:
        raise FileNotFoundError("저장된 assembly_schedule manifest가 없습니다.")
    return max(manifests, key=lambda path: path.stat().st_mtime)


def ingest_manifest(manifest_path: Path, database_url: str) -> dict[str, object]:
    manifest_path = manifest_path.resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content_hash = str(manifest["content_hash"])
    detected_format = str(manifest["detected_format"])
    content_path = manifest_path.with_name(f"{content_hash}.{detected_format}")
    content = content_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != content_hash:
        raise ValueError(f"raw content hash mismatch: {content_path}")

    payload = SourcePayload(
        source_key=str(manifest["source_type"]),
        source_url=str(manifest["source_url"]),
        retrieved_at=datetime.fromisoformat(str(manifest["retrieved_at"])),
        content=content,
        content_type=str(manifest["content_type"]),
        http_status=int(manifest["http_status"]),
    )
    adapter = ScheduleAdapter()
    entries = [normalize_schedule(record) for record in adapter.parse(payload)]
    try:
        raw_path = content_path.relative_to(PROJECT_DIR)
    except ValueError:
        raw_path = content_path
    source = SourceVersionInput(
        source_type=payload.source_key,
        source_url=payload.source_url,
        content_hash=content_hash,
        raw_path=raw_path,
        retrieved_at=payload.retrieved_at,
        parser_version=adapter.parser_version,
        content_type=payload.content_type,
        metadata={
            "http_status": payload.http_status,
            "detected_format": detected_format,
        },
    )
    with connect(database_url) as connection:
        result = ScheduleRepository(connection).ingest(source, entries)
    return {
        "source_document_version_id": str(result.source_document_version_id),
        "records_seen": result.records_seen,
        "schedule_entries_inserted": result.schedule_entries_inserted,
        "meetings_inserted": result.meetings_inserted,
        "meeting_versions_inserted": result.meeting_versions_inserted,
    }


if __name__ == "__main__":
    settings = get_settings()
    parser = argparse.ArgumentParser(description="보존된 국회일정을 PostgreSQL에 정규화합니다.")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    path = args.manifest or latest_manifest(settings.raw_data_dir)
    print(json.dumps(ingest_manifest(path, settings.database_url), ensure_ascii=False))
