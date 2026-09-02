from __future__ import annotations

import argparse
import json
import math
from collections import Counter
import os
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ..adapters.national_assembly.base import SourcePayload
from ..adapters.national_assembly.client import NationalAssemblyClient
from ..adapters.national_assembly.members import MemberAdapter, MemberSourceRecord, value_for_term
from ..adapters.national_assembly.schedule import ScheduleAdapter
from ..config import PROJECT_DIR, get_settings
from ..db.connection import connect
from ..db.schedule_repository import ScheduleRepository, SourceVersionInput
from ..domain.schedule import CanonicalScheduleEntry, normalize_schedule
from ..storage.raw_store import RawArtifact, RawStore


UPCOMING_SCHEDULE_SCHEMA = "assembly-schedule-upcoming.v1"
ASSEMBLY_REFERENCE_SCHEMA = "assembly-reference.v1"
OFFICIAL_SCHEDULE_CATALOG_URL = "https://www.data.go.kr/data/15126132/openapi.do"
OFFICIAL_MEMBER_CATALOG_URL = "https://www.data.go.kr/data/15126133/openapi.do"


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



def build_assembly_reference_snapshot(
    members: Iterable[MemberSourceRecord], *, current_term: str,
    generated_at: datetime, source_versions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    active = [
        member for member in members
        if current_term in member.elected_terms and member.duty_name
    ]
    party_counts: Counter[str] = Counter()
    election_counts: Counter[str] = Counter()
    gender_counts: Counter[str] = Counter()
    committees: set[str] = set()
    for member in active:
        party_counts[value_for_term(
            member.parties, member.elected_terms, current_term,
        ) or "미확인"] += 1
        election_counts[value_for_term(
            member.election_types, member.elected_terms, current_term,
        ) or "미확인"] += 1
        gender_counts[member.gender or "미확인"] += 1
        if member.committee_name:
            committees.update(
                value.strip() for value in member.committee_name.split(",")
                if value.strip()
            )

    def ranked(counter: Counter[str]) -> list[dict[str, object]]:
        return [
            {"label": label, "count": count}
            for label, count in sorted(
                counter.items(), key=lambda item: (-item[1], item[0]),
            )
        ]

    return {
        "schema_version": ASSEMBLY_REFERENCE_SCHEMA,
        "generated_at": generated_at.astimezone(timezone.utc).isoformat(),
        "assembly_term": current_term,
        "seat_count": len(active),
        "party_seats": ranked(party_counts),
        "election_type_seats": ranked(election_counts),
        "gender_seats": ranked(gender_counts),
        "committee_count": len(committees),
        "source_status": "OFFICIAL",
        "source": {
            "type": "ALLNAMEMBER",
            "catalog_url": OFFICIAL_MEMBER_CATALOG_URL,
            "active_rule": f"{current_term} elected term and non-empty DTY_NM",
            "party_rule": "PLPT_NM value aligned to the current elected term",
            "versions": source_versions or [],
        },
    }


def _reference_snapshot_fresh(
    path: Path, *, now: datetime, max_age: timedelta = timedelta(hours=24),
) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != ASSEMBLY_REFERENCE_SCHEMA:
            return False
        generated_at = datetime.fromisoformat(
            str(payload["generated_at"]).replace("Z", "+00:00")
        )
    except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
        return False
    return now.astimezone(timezone.utc) - generated_at.astimezone(timezone.utc) < max_age


def sync_assembly_reference_once(
    *, api_key: str, raw_data_dir: Path, processed_data_dir: Path,
    current_term: str = "제22대",
) -> dict[str, Any]:
    client = NationalAssemblyClient(api_key)
    adapter = MemberAdapter()
    raw_store = RawStore(raw_data_dir)
    records: list[MemberSourceRecord] = []
    versions: list[dict[str, Any]] = []
    total_count = 0
    generated_at = datetime.now(timezone.utc)
    page = 1
    while page == 1 or len(records) < total_count:
        payload = client.fetch("members", page=page, page_size=1000)
        artifact = raw_store.save(payload, parser_version=adapter.parser_version)
        page_records, total_count = adapter.parse(payload)
        records.extend(page_records)
        generated_at = max(generated_at, payload.retrieved_at)
        versions.append({
            "content_hash": artifact.content_hash,
            "retrieved_at": payload.retrieved_at.isoformat(),
            "parser_version": adapter.parser_version,
            "page": page,
        })
        if not page_records or page >= math.ceil(max(1, total_count) / 1000):
            break
        page += 1
    snapshot = build_assembly_reference_snapshot(
        records, current_term=current_term, generated_at=generated_at,
        source_versions=versions,
    )
    _atomic_json(processed_data_dir / "assembly_reference.json", snapshot)
    return snapshot

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
    parser.add_argument("--term", default="제22대")
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
        reference_path = settings.processed_data_dir / "assembly_reference.json"
        reference = None
        if not _reference_snapshot_fresh(
            reference_path, now=datetime.now(timezone.utc),
        ):
            try:
                reference = sync_assembly_reference_once(
                    api_key=settings.national_assembly_api_key,
                    raw_data_dir=settings.raw_data_dir,
                    processed_data_dir=settings.processed_data_dir,
                    current_term=args.term.strip() or "제22대",
                )
            except Exception as exc:
                print(json.dumps({
                    "assembly_reference_error": type(exc).__name__,
                    "fallback": "last_snapshot",
                }, ensure_ascii=False), flush=True)
        print(json.dumps({
            "generated_at": snapshot["generated_at"],
            "start_date": snapshot["start_date"],
            "end_date": snapshot["end_date"],
            "target_count": snapshot["count"],
            "assembly_seat_count": (
                reference.get("seat_count") if reference else None
            ),
        }, ensure_ascii=False), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
