from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import AdapterError, SourcePayload
from .contracts import get_contract
from .json_envelope import parse_json_envelope


@dataclass(frozen=True, slots=True)
class MemberSourceRecord:
    member_code: str
    name: str
    parties: tuple[str, ...]
    elected_terms: tuple[str, ...]
    election_types: tuple[str, ...]
    gender: str | None
    duty_name: str | None
    committee_name: str | None


class MemberAdapter:
    source_key = "members"
    parser_version = "assembly-members/1.0.0"

    def parse(self, payload: SourcePayload) -> tuple[list[MemberSourceRecord], int]:
        if payload.source_key != self.source_key:
            raise AdapterError(f"unexpected source key: {payload.source_key}")
        contract = get_contract(self.source_key)
        envelope = parse_json_envelope(
            payload.content, expected_resource=contract.resource,
        )
        return [self._normalize(row) for row in envelope.rows], envelope.total_count

    @staticmethod
    def _text(row: dict[str, Any], key: str) -> str | None:
        value = row.get(key)
        if value is None:
            return None
        text = " ".join(str(value).split())
        return text or None

    @staticmethod
    def _sequence(value: str | None, separator: str) -> tuple[str, ...]:
        return tuple(
            item.strip() for item in str(value or "").split(separator)
            if item.strip()
        )

    def _normalize(self, row: dict[str, Any]) -> MemberSourceRecord:
        member_code = self._text(row, "NAAS_CD")
        name = self._text(row, "NAAS_NM")
        if not member_code or not name:
            raise AdapterError("member row lacks NAAS_CD or NAAS_NM")
        return MemberSourceRecord(
            member_code=member_code,
            name=name,
            parties=self._sequence(self._text(row, "PLPT_NM"), "/"),
            elected_terms=self._sequence(self._text(row, "GTELT_ERACO"), ","),
            election_types=self._sequence(self._text(row, "ELECD_DIV_NM"), "/"),
            gender=self._text(row, "NTR_DIV"),
            duty_name=self._text(row, "DTY_NM"),
            committee_name=self._text(row, "CMIT_NM"),
        )


def value_for_term(
    values: tuple[str, ...], terms: tuple[str, ...], current_term: str,
) -> str | None:
    try:
        index = terms.index(current_term)
    except ValueError:
        return None
    if index < len(values):
        return values[index]
    return values[-1] if values else None
