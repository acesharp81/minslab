from __future__ import annotations

import json
from typing import Any

from ..models import Notice


INELIGIBLE_REASON_META = (
    ("national_task", "국가사무", "#bd625b"),
    ("network_data", "망·데이터", "#d89a3d"),
    ("specialized_model", "특화모델(학습 필요)", "#7278b8"),
)
INELIGIBLE_REASON_KEYS = {key for key, _label, _color in INELIGIBLE_REASON_META} | {"non_ai"}
MANUAL_REASON_KEY = "_poc08_manual_ineligible_reason"


def _payload(notice: Notice) -> dict[str, Any]:
    try:
        value = json.loads(notice.raw_payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        value = {}
    return value if isinstance(value, dict) else {}


def manual_ineligible_reason(notice: Notice) -> str:
    value = str(_payload(notice).get(MANUAL_REASON_KEY) or "")
    return value if value in INELIGIBLE_REASON_KEYS else ""


def set_manual_ineligible_reason(notice: Notice, reason: str | None) -> None:
    payload = _payload(notice)
    if reason:
        if reason not in INELIGIBLE_REASON_KEYS:
            raise ValueError("지원하지 않는 부적합 유형입니다.")
        payload[MANUAL_REASON_KEY] = reason
    else:
        payload.pop(MANUAL_REASON_KEY, None)
    notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)


def ineligible_reason_key(notice: Notice, result: dict[str, Any]) -> str:
    """Prefer the operator's final reason and otherwise infer a primary reason."""
    manual = manual_ineligible_reason(notice)
    if manual:
        return manual
    if result.get("task_scope") in {"public_institution_internal", "non_government"}:
        return "national_task"
    if result.get("network_scope") in {"external_complete", "other_closed_network"}:
        return "network_data"
    return "specialized_model"
