from __future__ import annotations

import argparse
import json
import os
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ..adapters.national_assembly.base import SourcePayload
from ..adapters.national_assembly.client import NationalAssemblyClient
from ..adapters.national_assembly.schedule import ScheduleAdapter
from ..config import PROJECT_DIR, get_settings
from ..db.connection import connect
from ..db.schedule_repository import ScheduleRepository, SourceVersionInput
from ..domain.schedule import CanonicalScheduleEntry, normalize_schedule
from ..storage.raw_store import RawArtifact, RawStore


UPCOMING_SCHEDULE_SCHEMA = "assembly-schedule-upcoming.v1"
OFFICIAL_SCHEDULE_CATALOG_URL = "https://www.data.go.kr/data/15126132/openapi.do"


def _source_input(
    payload: SourcePayload,
    artifact: RawArtifact,
    parser_version: str,
) -> SourceVersionInput:
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
        metadata={"http_status": payload.http_status, "query_filter": "SCH_DT"},
    )


def _public_item(entry: CanonicalScheduleEntry) -> dict[str, Any]:
    return {
        "id": entry.source_record_key,
        "meeting_id": str(entry.meeting_uid) if entry.meeting_uid else None,
        "schedule_kind": entry.schedule_kind,
        "title": entry.title,
        "scheduled_date": entry.scheduled_date.isoformat(),
        "start_time": entry.start_time.isoformat(timespec="minutes") if entry.start_time else None,
        "end_time": entry.end_time.isoformat(timespec="minutes") if entry.end_time else None,
        "time_text": entry.time_text,
        "meeting_type": entry.meeting_type,
        "committee_name": entry.committee_name,
        "session_text": entry.session_text,
        "meeting_order_text": entry.meeting_order_text,
        "host_name": entry.host_name,
        "place": entry.place,
        "is_target_committee": entry.is_target_committee,
        "authority_status": entry.authority_status.value,
        "reconciliation_status": entry.reconciliation_status.value,
        "source_url": OFFICIAL_SCHEDULE_CATALOG_URL,
    }


def build_upcoming_schedule_snapshot(
    entries: Iterable[CanonicalScheduleEntry],
    *,
    start_date: date,
    days: int,
    generated_at: datetime,
) -> dict[str, Any]:
    if not 1 <= days <= 14:
        raise ValueError("days must be between 1 and 14")
    end_date = start_date + timedelta(days=days - 1)
    items = [
        _public_item(entry)
        for entry in entries
        if entry.is_target_committee and start_date <= entry.scheduled_date <= end_date
    ]
    items.sort(key=lambda item: (
        str(item["scheduled_date"]),
        str(item["start_time"] or "99:99"),
        str(item["committee_name"] or ""),
        str(item["title"] or ""),
    ))
    return {
        "schema_version": UPCOMING_SCHEDULE_SCHEMA,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
        "items": items,
        "count": len(items),
        "source_status": "OFFICIAL",
        "source": {
            "type": "ALLSCHEDULE",
            "catalog_url": OFFICIAL_SCHEDULE_CATALOG_URL,
            "date_filter": "SCH_DT",
        },
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            json.dump(payload, temporary, ensure_ascii=False, indent=2)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def sync_upcoming_schedule_once(
    *,
    api_key: str,
    database_url: str,
    raw_data_dir: Path,
    processed_data_dir: Path,
    start_date: date,
    days: int = 7,
) -> dict[str, Any]:
    client = NationalAssemblyClient(api_key)
    adapter = ScheduleAdapter()
    raw_store = RawStore(raw_data_dir)
    entries: list[CanonicalScheduleEntry] = []
    retrieved_at = datetime.now(timezone.utc)
    for offset in range(days):
        target_date = start_date + timedelta(days=offset)
        payload = client.fetch(
            "assembly_schedule",
            page=1,
            page_size=1000,
            filters={"SCH_DT": target_date.isoformat()},
        )
        retrieved_at = max(retrieved_at, payload.retrieved_at)
        artifact = raw_store.save(payload, parser_version=adapter.parser_version)
        normalized = [normalize_schedule(record) for record in adapter.parse(payload)]
        entries.extend(normalized)
        with connect(database_url) as connection:
            ScheduleRepository(connection).ingest(
                _source_input(payload, artifact, adapter.parser_version),
                normalized,
            )
    snapshot = build_upcoming_schedule_snapshot(
        entries,
        start_date=start_date,
        days=days,
        generated_at=retrieved_at,
    )
    _atomic_json(processed_data_dir / "upcoming_schedule.json", snapshot)
    return snapshot


def main() -> None:
    from ..db.migrate import apply_migrations

    settings = get_settings()
    parser = argparse.ArgumentParser(description="Sync official National Assembly schedules")
    parser.add_argument("--interval", type=int, default=600)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 300 <= args.interval <= 86400:
        parser.error("interval must be between 300 and 86400 seconds")
    if not 1 <= args.days <= 14:
        parser.error("days must be between 1 and 14")
    if not settings.national_assembly_api_key:
        parser.error("NATIONAL_ASSEMBLY_API_KEY is required")
    apply_migrations(settings.database_url)
    while True:
        local_today = datetime.now(ZoneInfo(settings.national_assembly_timezone)).date()
        snapshot = sync_upcoming_schedule_once(
            api_key=settings.national_assembly_api_key,
            database_url=settings.database_url,
            raw_data_dir=settings.raw_data_dir,
            processed_data_dir=settings.processed_data_dir,
            start_date=local_today,
            days=args.days,
        )
        print(json.dumps({
            "generated_at": snapshot["generated_at"],
            "start_date": snapshot["start_date"],
            "end_date": snapshot["end_date"],
            "target_count": snapshot["count"],
        }, ensure_ascii=False), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
