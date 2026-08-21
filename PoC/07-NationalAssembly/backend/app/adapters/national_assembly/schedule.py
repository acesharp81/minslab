from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .base import AdapterError, SourcePayload
from .contracts import get_contract
from .json_envelope import parse_json_envelope


@dataclass(frozen=True, slots=True)
class ScheduleSourceRecord:
    source_record_key: str
    schedule_kind: str | None
    content: str | None
    date_text: str | None
    time_text: str | None
    meeting_type: str | None
    committee_name: str | None
    session_text: str | None
    meeting_order_text: str | None
    host_name: str | None
    place: str | None


class ScheduleAdapter:
    source_key = "assembly_schedule"
    parser_version = "assembly-schedule/1.0.0"

    def parse(self, payload: SourcePayload) -> list[ScheduleSourceRecord]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        contract = get_contract(self.source_key)
        envelope = parse_json_envelope(payload.content, expected_resource=contract.resource)
        return [self._normalize(row) for row in envelope.rows]

    @staticmethod
    def _text(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _normalize(self, row: dict[str, Any]) -> ScheduleSourceRecord:
        identity_fields = {
            key: self._text(row, key)
            for key in ("SCH_KIND", "SCH_CN", "SCH_DT", "SCH_TM", "CONF_DIV", "CMIT_NM", "CONF_SESS", "CONF_DGR")
        }
        source_record_key = hashlib.sha256(
            json.dumps(identity_fields, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return ScheduleSourceRecord(
            source_record_key=source_record_key,
            schedule_kind=self._text(row, "SCH_KIND"),
            content=self._text(row, "SCH_CN"),
            date_text=self._text(row, "SCH_DT"),
            time_text=self._text(row, "SCH_TM"),
            meeting_type=self._text(row, "CONF_DIV"),
            committee_name=self._text(row, "CMIT_NM"),
            session_text=self._text(row, "CONF_SESS"),
            meeting_order_text=self._text(row, "CONF_DGR"),
            host_name=self._text(row, "EV_INST_NM"),
            place=self._text(row, "EV_PLC"),
        )
