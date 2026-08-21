from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import date, time

from ..adapters.national_assembly.schedule import ScheduleSourceRecord
from .scope import is_target_committee
from .states import AuthorityStatus, LifecycleStatus, ReconciliationStatus

MEETING_NAMESPACE = uuid.UUID("dcfbe97c-2c47-5eb2-b2b4-28b4bc490f02")


@dataclass(frozen=True, slots=True)
class CanonicalScheduleEntry:
    source_record_key: str
    schedule_kind: str | None
    title: str | None
    scheduled_date: date
    start_time: time | None
    end_time: time | None
    time_text: str | None
    meeting_type: str | None
    committee_name: str | None
    session_text: str | None
    meeting_order_text: str | None
    host_name: str | None
    place: str | None
    meeting_uid: uuid.UUID | None
    lifecycle_status: LifecycleStatus
    authority_status: AuthorityStatus
    is_target_committee: bool
    reconciliation_status: ReconciliationStatus

    def official_data(self) -> dict[str, str | None]:
        data = asdict(self)
        for key in (
            "scheduled_date",
            "start_time",
            "end_time",
            "meeting_uid",
            "lifecycle_status",
            "authority_status",
            "reconciliation_status",
        ):
            data.pop(key)
        data.pop("is_target_committee")
        return data


def _parse_date(value: str | None) -> date:
    if value is None:
        raise ValueError("SCH_DT is required")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid SCH_DT: {value!r}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"invalid SCH_DT: {value!r}")
    return parsed


def _parse_time(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid SCH_TM component: {value!r}") from exc


def _parse_time_range(value: str | None) -> tuple[time | None, time | None]:
    if value is None:
        return None, None
    parts = [part.strip() for part in value.split("~", 1)]
    start = _parse_time(parts[0])
    end = _parse_time(parts[1]) if len(parts) == 2 and parts[1] else None
    return start, end


def _meeting_uid(record: ScheduleSourceRecord, scheduled_date: date) -> uuid.UUID | None:
    is_committee_meeting = (
        record.schedule_kind == "위원회"
        and record.meeting_type is not None
        and record.committee_name is not None
    )
    if not is_committee_meeting:
        return None
    identity = "|".join(
        value or ""
        for value in (
            scheduled_date.isoformat(),
            record.committee_name,
            record.meeting_type,
            record.session_text,
            record.meeting_order_text,
        )
    )
    return uuid.uuid5(MEETING_NAMESPACE, identity)


def normalize_schedule(record: ScheduleSourceRecord) -> CanonicalScheduleEntry:
    scheduled_date = _parse_date(record.date_text)
    start_time, end_time = _parse_time_range(record.time_text)
    meeting_uid = _meeting_uid(record, scheduled_date)
    return CanonicalScheduleEntry(
        source_record_key=record.source_record_key,
        schedule_kind=record.schedule_kind,
        title=record.content,
        scheduled_date=scheduled_date,
        start_time=start_time,
        end_time=end_time,
        time_text=record.time_text,
        meeting_type=record.meeting_type,
        committee_name=record.committee_name,
        session_text=record.session_text,
        meeting_order_text=record.meeting_order_text,
        host_name=record.host_name,
        is_target_committee=is_target_committee(record.committee_name),
        place=record.place,
        meeting_uid=meeting_uid,
        lifecycle_status=LifecycleStatus.SCHEDULED,
        authority_status=AuthorityStatus.OFFICIAL,
        reconciliation_status=(
            ReconciliationStatus.MATCHED
            if meeting_uid is not None
            else ReconciliationStatus.UNRESOLVED
        ),
    )
