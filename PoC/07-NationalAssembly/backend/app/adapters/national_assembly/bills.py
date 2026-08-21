from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .base import AdapterError, SourcePayload
from .contracts import get_contract
from .json_envelope import parse_json_envelope


@dataclass(frozen=True, slots=True)
class BillDetailSourceRecord:
    source_record_key: str
    bill_id: str
    assembly_term: str
    bill_number: str | None
    bill_kind: str | None
    bill_name: str
    proposer_kind: str | None
    proposer_name: str | None
    proposal_date_text: str | None
    committee_name: str | None
    committee_process_date_text: str | None
    committee_result: str | None
    plenary_resolution_date_text: str | None
    plenary_result: str | None
    pass_classification: str | None
    process_stage_code: str | None
    official_url: str | None
    official_data: dict[str, str | None]


class BillsAdapter:
    source_key = "bills"
    parser_version = "bills/1.0.0"

    @staticmethod
    def _text(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def parse(self, payload: SourcePayload) -> list[BillDetailSourceRecord]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        contract = get_contract(self.source_key)
        envelope = parse_json_envelope(payload.content, expected_resource=contract.resource)
        records: list[BillDetailSourceRecord] = []
        for row in envelope.rows:
            official_data = {key: self._text(row, key) for key in contract.columns}
            bill_id = official_data["BILL_ID"]
            assembly_term = official_data["ERACO"]
            bill_name = official_data["BILL_NM"]
            if not bill_id or not assembly_term or not bill_name:
                raise AdapterError("bill row lacks BILL_ID, ERACO, or BILL_NM")
            source_record_key = hashlib.sha256(
                json.dumps(official_data, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()
            records.append(BillDetailSourceRecord(
                source_record_key=source_record_key,
                bill_id=bill_id,
                assembly_term=assembly_term,
                bill_number=official_data["BILL_NO"],
                bill_kind=official_data["BILL_KND"],
                bill_name=bill_name,
                proposer_kind=official_data["PPSR_KND"],
                proposer_name=official_data["PPSR_NM"],
                proposal_date_text=official_data["PPSL_DT"],
                committee_name=official_data["JRCMIT_NM"],
                committee_process_date_text=official_data["JRCMIT_PROC_DT"],
                committee_result=official_data["JRCMIT_PROC_RSLT"],
                plenary_resolution_date_text=official_data["RGS_RSLN_DT"],
                plenary_result=official_data["RGS_CONF_RSLT"],
                pass_classification=official_data["PASSGUBN"],
                process_stage_code=official_data["PROC_STAGE_CD"],
                official_url=official_data["LINK_URL"],
                official_data=official_data,
            ))
        return records
