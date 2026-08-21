from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import date

from ..adapters.national_assembly.committee_minutes import CommitteeMinuteSourceRecord
from .scope import is_target_committee
from .states import AuthorityStatus, LifecycleStatus


OFFICIAL_MEETING_NAMESPACE = uuid.UUID("ca29ff17-7673-5846-a9c8-d05b60fd6748")
TITLE_IDENTITY = re.compile(r"제(?P<assembly>\d+)대\s+제(?P<session>\d+)회\s+제(?P<order>\d+)차")


@dataclass(frozen=True, slots=True)
class CanonicalCommitteeMeeting:
    conference_id: str
    meeting_uid: uuid.UUID
    meeting_source_key: str
    conference_number: str | None
    title: str | None
    class_name: str | None
    assembly_number: str | None
    committee_name: str
    conference_date: date
    session_text: str | None
    meeting_order_text: str | None
    department_code: str | None
    sections: tuple[CommitteeMinuteSourceRecord, ...]
    lifecycle_status: LifecycleStatus = LifecycleStatus.ENDED
    authority_status: AuthorityStatus = AuthorityStatus.OFFICIAL


def _strict_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid CONF_DATE: {value!r}") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"invalid CONF_DATE: {value!r}")
    return parsed


def group_target_committee_minutes(
    records: list[CommitteeMinuteSourceRecord],
) -> list[CanonicalCommitteeMeeting]:
    grouped: dict[str, list[CommitteeMinuteSourceRecord]] = {}
    for record in records:
        if is_target_committee(record.committee_name):
            grouped.setdefault(record.conference_id, []).append(record)

    meetings: list[CanonicalCommitteeMeeting] = []
    for conference_id, sections in grouped.items():
        first = sections[0]
        identity_values = {
            (item.committee_name, item.conference_date, item.title, item.conference_number)
            for item in sections
        }
        if len(identity_values) != 1:
            raise ValueError(f"conflicting meeting identity for CONF_ID {conference_id}")
        match = TITLE_IDENTITY.search(first.title or "")
        session_text = f"제{match.group('session')}회" if match else None
        meeting_order_text = f"제{match.group('order')}차" if match else None
        source_key = hashlib.sha256(
            f"committee_minutes|{conference_id}".encode("utf-8")
        ).hexdigest()
        meetings.append(CanonicalCommitteeMeeting(
            conference_id=conference_id,
            meeting_uid=uuid.uuid5(OFFICIAL_MEETING_NAMESPACE, conference_id),
            meeting_source_key=source_key,
            conference_number=first.conference_number,
            title=first.title,
            class_name=first.class_name,
            assembly_number=first.assembly_number,
            committee_name=first.committee_name,
            conference_date=_strict_date(first.conference_date),
            session_text=session_text,
            meeting_order_text=meeting_order_text,
            department_code=first.department_code,
            sections=tuple(sections),
        ))
    return sorted(meetings, key=lambda item: (item.conference_date, item.committee_name, item.conference_id))
