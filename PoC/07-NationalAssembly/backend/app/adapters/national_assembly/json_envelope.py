from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .base import AdapterError


@dataclass(frozen=True, slots=True)
class JsonEnvelope:
    resource: str
    result_code: str
    result_message: str
    total_count: int
    rows: tuple[dict[str, Any], ...]

    @property
    def ok(self) -> bool:
        return self.result_code == "INFO-000"

    @property
    def empty(self) -> bool:
        return self.result_code == "INFO-200" or self.total_count == 0


def parse_json_envelope(content: bytes, *, expected_resource: str) -> JsonEnvelope:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AdapterError(f"malformed JSON: {error}") from error

    if not isinstance(payload, dict) or not payload:
        raise AdapterError("response must be a non-empty JSON object")

    if "RESULT" in payload:
        result = payload["RESULT"]
        if not isinstance(result, dict):
            raise AdapterError("invalid RESULT envelope")
        code = str(result.get("CODE") or "")
        message = str(result.get("MESSAGE") or "")
        if code == "INFO-200":
            return JsonEnvelope(expected_resource, code, message, 0, ())
        raise AdapterError(f"source error {code}: {message}")

    if expected_resource not in payload:
        raise AdapterError(f"unexpected response resource: {sorted(payload)}")

    blocks = payload[expected_resource]
    if not isinstance(blocks, list) or not blocks:
        raise AdapterError("resource envelope must be a non-empty list")

    head = blocks[0].get("head") if isinstance(blocks[0], dict) else None
    if not isinstance(head, list):
        raise AdapterError("response head is missing")

    total_count = next(
        (item.get("list_total_count") for item in head if isinstance(item, dict) and "list_total_count" in item),
        0,
    )
    result = next(
        (item.get("RESULT") for item in head if isinstance(item, dict) and isinstance(item.get("RESULT"), dict)),
        {},
    )
    code = str(result.get("CODE") or "")
    message = str(result.get("MESSAGE") or "")
    if code not in {"INFO-000", "INFO-200"}:
        raise AdapterError(f"source error {code}: {message}")

    rows: list[dict[str, Any]] = []
    if len(blocks) > 1 and isinstance(blocks[1], dict):
        candidate_rows = blocks[1].get("row") or []
        if not isinstance(candidate_rows, list) or not all(isinstance(row, dict) for row in candidate_rows):
            raise AdapterError("response rows must be a list of objects")
        rows = candidate_rows

    try:
        normalized_total = int(total_count)
    except (TypeError, ValueError) as error:
        raise AdapterError(f"invalid total count: {total_count!r}") from error

    return JsonEnvelope(expected_resource, code, message, normalized_total, tuple(rows))
