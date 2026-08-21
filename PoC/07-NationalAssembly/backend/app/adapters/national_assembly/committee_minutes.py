from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .base import AdapterError, SourcePayload
from .contracts import get_contract
from .json_envelope import parse_json_envelope


@dataclass(frozen=True, slots=True)
class CommitteeMinuteSourceRecord:
    source_record_key: str
    conference_id: str
    conference_number: str | None
    title: str | None
    class_name: str | None
    assembly_number: str | None
    committee_name: str
    conference_date: str
    subject_name: str | None
    vod_url: str | None
    minutes_url: str | None
    pdf_url: str | None
    pdf_file_id: str | None
    department_code: str | None


class CommitteeMinutesAdapter:
    source_key = "committee_minutes"
    parser_version = "committee-minutes/1.0.0"

    @staticmethod
    def _text(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def parse(self, payload: SourcePayload) -> list[CommitteeMinuteSourceRecord]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        envelope = parse_json_envelope(
            payload.content,
            expected_resource=get_contract(self.source_key).resource,
        )
        records: list[CommitteeMinuteSourceRecord] = []
        for row in envelope.rows:
            conference_id = self._text(row, "CONF_ID")
            committee_name = self._text(row, "COMM_NAME")
            conference_date = self._text(row, "CONF_DATE")
            if not conference_id or not committee_name or not conference_date:
                raise AdapterError("committee minute row lacks CONF_ID, COMM_NAME, or CONF_DATE")
            identity = {
                key: self._text(row, key)
                for key in get_contract(self.source_key).columns
            }
            source_record_key = hashlib.sha256(
                json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            records.append(CommitteeMinuteSourceRecord(
                source_record_key=source_record_key,
                conference_id=conference_id,
                conference_number=self._text(row, "CONFER_NUM"),
                title=self._text(row, "TITLE"),
                class_name=self._text(row, "CLASS_NAME"),
                assembly_number=self._text(row, "DAE_NUM"),
                committee_name=committee_name,
                conference_date=conference_date,
                subject_name=self._text(row, "SUB_NAME"),
                vod_url=self._text(row, "VOD_LINK_URL"),
                minutes_url=self._text(row, "CONF_LINK_URL"),
                pdf_url=self._text(row, "PDF_LINK_URL"),
                pdf_file_id=self._text(row, "PDF_FILE_ID"),
                department_code=self._text(row, "DEPT_CD"),
            ))
        return records
