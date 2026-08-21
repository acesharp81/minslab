from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .base import AdapterError, SourcePayload
from .contracts import get_contract
from .json_envelope import parse_json_envelope


@dataclass(frozen=True, slots=True)
class MeetingAgendaSourceRecord:
    source_record_key: str
    conference_id: str
    assembly_term: str | None
    session_text: str | None
    meeting_order_text: str | None
    bill_id: str | None
    bill_name: str
    official_url: str | None


class MeetingAgendasAdapter:
    source_key = "meeting_agendas"
    parser_version = "meeting-agendas/1.0.0"

    @staticmethod
    def _text(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def parse(self, payload: SourcePayload) -> list[MeetingAgendaSourceRecord]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        envelope = parse_json_envelope(
            payload.content,
            expected_resource=get_contract(self.source_key).resource,
        )
        records: list[MeetingAgendaSourceRecord] = []
        for row in envelope.rows:
            conference_id = self._text(row, "CONF_ID")
            bill_name = self._text(row, "BILL_NM")
            if not conference_id or not bill_name:
                raise AdapterError("meeting agenda row lacks CONF_ID or BILL_NM")
            identity = {
                key: self._text(row, key)
                for key in get_contract(self.source_key).columns
            }
            source_record_key = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            records.append(MeetingAgendaSourceRecord(
                source_record_key=source_record_key,
                conference_id=conference_id,
                assembly_term=self._text(row, "ERACO"),
                session_text=self._text(row, "SESS"),
                meeting_order_text=self._text(row, "DGR"),
                bill_id=self._text(row, "BILL_ID"),
                bill_name=bill_name,
                official_url=self._text(row, "LINK_URL"),
            ))
        return records
