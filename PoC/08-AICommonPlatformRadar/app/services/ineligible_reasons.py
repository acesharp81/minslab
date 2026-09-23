from __future__ import annotations

import json
import re
from typing import Any

from ..models import Notice


INELIGIBLE_REASON_META = (
    ("national_task", "국가사무 범위 외", "#bd625b"),
    ("network_data", "망·데이터", "#d89a3d"),
    ("specialized_model", "모델 요구 미지원", "#7278b8"),
)
INELIGIBLE_DETAIL_META = (
    {
        "key": "non_government_task", "group": "national_task", "label": "국가사무 아님",
        "priority": "공통기반 적용 대상 정책과 국가사무 판단 기준을 명확히 안내", "color": "#a9504b",
    },
    {
        "key": "public_internal_task", "group": "national_task", "label": "공공기관 고유 내부업무",
        "priority": "위임·위탁 국가사무 여부와 적용 대상 확대 필요성을 검토", "color": "#c36b63",
    },
    {
        "key": "task_basis_unknown", "group": "national_task", "label": "국가사무 근거 미확인",
        "priority": "발주 문서에 수행 사무와 법적 근거를 명시하도록 표준 문구 제공", "color": "#dc8b82",
    },
    {
        "key": "internet_only_service", "group": "network_data", "label": "인터넷망 완결 서비스",
        "priority": "인터넷망 서비스 수용 범위 또는 안전한 중계 구조를 우선 검토", "color": "#c47d22",
    },
    {
        "key": "isolated_network_no_link", "group": "network_data", "label": "분리망·폐쇄망 연계 불가",
        "priority": "망간 연계 게이트웨이와 보안승인 표준 모델을 우선 마련", "color": "#d59337",
    },
    {
        "key": "data_transfer_restricted", "group": "network_data", "label": "데이터 반입·반출 제한",
        "priority": "비식별화·데이터 반입 절차와 보안 데이터 처리 기능을 우선 검토", "color": "#e4ad5a",
    },
    {
        "key": "closed_network_integration", "group": "network_data", "label": "폐쇄망 연계 방식 미지원",
        "priority": "기관별 폐쇄망 연결 방식과 공통 연계 규격을 우선 검토", "color": "#edc27b",
    },
    {
        "key": "network_requirements_unknown", "group": "network_data", "label": "망·데이터 조건 미확인",
        "priority": "망 구성과 데이터 이동 가능 여부를 받는 사전 진단표를 보급", "color": "#f1d39b",
    },
    {
        "key": "model_training_required", "group": "specialized_model", "label": "모델 학습·풀파인튜닝 목적",
        "priority": "안전한 추가학습·튜닝 기능과 학습 데이터 반입 체계를 우선 검토", "color": "#575fa8",
    },
    {
        "key": "domain_specialized_model", "group": "specialized_model", "label": "업무 특화모델 필요",
        "priority": "수요가 많은 분야부터 특화모델 카탈로그와 반입·검증 절차를 확대", "color": "#7278b8",
    },
    {
        "key": "unsupported_service_capability", "group": "specialized_model", "label": "미지원 서비스·기능",
        "priority": "반복 수요 기능을 제품 로드맵에 반영하고 외부 서비스 연계 기준을 마련", "color": "#8d91c8",
    },
    {
        "key": "custom_model_required", "group": "specialized_model", "label": "독자·자체모델 요구",
        "priority": "제공 모델 대체 가능성 및 외부 모델 반입·운영 기준을 우선 검토", "color": "#a7aad7",
    },
    {
        "key": "model_requirements_unknown", "group": "specialized_model", "label": "모델 요구사항 미확인",
        "priority": "필요 모델·학습 방식·성능 기준을 받는 표준 요구사항을 보급", "color": "#c4c6e5",
    },
    {
        "key": "service_scope_outside_target", "group": "service_scope", "label": "공통기반 적용 서비스 아님",
        "priority": "확대 과제가 아니라 적용범위 밖 사업으로 별도 관리", "color": "#8d9892",
    },
)
INELIGIBLE_DETAIL_BY_KEY = {item["key"]: item for item in INELIGIBLE_DETAIL_META}
INELIGIBLE_IMPROVEMENT_META = {
    "internet_only_service": {
        "potential": "조건부", "analysis": "인터넷망 수요를 공통기반과 연결할 중계·인증 구조가 확보될 때 개선 가능",
    },
    "isolated_network_no_link": {
        "potential": "중간", "analysis": "기관 보안승인과 망간 연계 표준을 함께 마련해야 적용 가능",
    },
    "data_transfer_restricted": {
        "potential": "중간", "analysis": "비식별화와 승인된 반입·반출 절차를 제공하면 일부 수요를 수용 가능",
    },
    "closed_network_integration": {
        "potential": "높음", "analysis": "반복되는 폐쇄망 연결 방식을 공통 규격으로 만들면 다수 사업에 재사용 가능",
    },
    "model_training_required": {
        "potential": "조건부", "analysis": "학습 데이터 보안과 추가학습 운영 기능을 갖춘 범위에서 지원 가능",
    },
    "domain_specialized_model": {
        "potential": "높음", "analysis": "반복 수요 분야를 선별해 검증된 특화모델로 제공하면 확대 효과가 큼",
    },
    "unsupported_service_capability": {
        "potential": "중간", "analysis": "반복 요청 기능을 제품 로드맵이나 외부 서비스 연계로 수용할 수 있는지 검토 가능",
    },
    "custom_model_required": {
        "potential": "조건부", "analysis": "기존 제공 모델의 대체 가능성과 외부 모델 반입 요건을 먼저 검증해야 함",
    },
}
INELIGIBLE_UNKNOWN_KEYS = {
    "task_basis_unknown", "network_requirements_unknown", "model_requirements_unknown",
}
INELIGIBLE_REASON_KEYS = (
    {key for key, _label, _color in INELIGIBLE_REASON_META}
    | set(INELIGIBLE_DETAIL_BY_KEY)
    | {"non_ai"}
)
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


def _detail_text(result: dict[str, Any]) -> str:
    evidence = []
    for key in ("network_evidence", "model_fit_evidence", "remediation_evidence", "evidence"):
        for item in result.get(key) or []:
            if isinstance(item, dict):
                evidence.extend((str(item.get("quote") or ""), str(item.get("interpretation") or "")))
    return " ".join([
        str(result.get("network_reason") or ""),
        str(result.get("service_scope_reason") or ""),
        str(result.get("model_fit_reason") or ""),
        str(result.get("remediation_reason") or ""),
        str(result.get("summary") or ""),
        " ".join(str(item) for item in result.get("possible_common_platform_functions") or []),
        *evidence,
    ])


def ineligible_detail_key(notice: Notice, result: dict[str, Any]) -> str:
    """Classify the concrete blocker that should drive platform expansion priorities."""
    manual = manual_ineligible_reason(notice)
    if manual in INELIGIBLE_DETAIL_BY_KEY:
        return manual

    task_scope = str(result.get("task_scope") or "")
    network_scope = str(result.get("network_scope") or "")
    text = _detail_text(result)
    compact = re.sub(r"\s+", "", text).casefold()

    # The original three-way metric is the stable parent category. Detail
    # classification may subdivide that parent, but must never move a notice
    # to a different parent and rewrite the historical percentage.
    if manual in {"national_task", "network_data", "specialized_model", "service_scope"}:
        group = manual
    elif task_scope in {"public_institution_internal", "non_government"}:
        group = "national_task"
    elif network_scope in {"external_complete", "other_closed_network"}:
        group = "network_data"
    elif str(result.get("service_scope") or "") == "non_target":
        group = "service_scope"
    else:
        group = "specialized_model"

    if group == "national_task":
        if task_scope == "non_government":
            return "non_government_task"
        if task_scope == "public_institution_internal":
            return "public_internal_task"
        return "task_basis_unknown"

    if group == "network_data":
        if network_scope == "external_complete":
            return "internet_only_service"
        if re.search(r"(데이터|자료|개인정보|민감정보).{0,18}(반입|반출|이동|전송).{0,10}(불가|금지|제한)", compact):
            return "data_transfer_restricted"
        if re.search(r"(망분리|물리적분리|폐쇄망|분리망).{0,20}(연계불가|연결불가|차단|금지)", compact):
            return "isolated_network_no_link"
        if network_scope == "other_closed_network":
            return "closed_network_integration"
        return "network_requirements_unknown"

    if group == "service_scope":
        return "service_scope_outside_target"

    if re.search(r"(풀파인튜닝|full.?fine.?tun|추가학습|재학습|모델학습|학습데이터)", compact):
        return "model_training_required"
    if re.search(r"(특화모델|전문모델|도메인모델|업무전용모델)", compact):
        return "domain_specialized_model"
    if re.search(r"(미지원|지원하지못|제공하지않|구현불가|처리불가|기능부족)", compact):
        return "unsupported_service_capability"
    if re.search(r"(독자모델|자체모델|전용모델)", compact):
        return "custom_model_required"
    if str(result.get("model_fit") or "") == "custom_model_or_full_finetuning":
        return "custom_model_required"
    return "model_requirements_unknown"


def ineligible_reason_key(notice: Notice, result: dict[str, Any]) -> str:
    """Return the original stable three-way group used by historical metrics."""
    manual = manual_ineligible_reason(notice)
    if manual in {"national_task", "network_data", "specialized_model", "service_scope"}:
        return manual
    if manual in INELIGIBLE_DETAIL_BY_KEY:
        return str(INELIGIBLE_DETAIL_BY_KEY[manual]["group"])
    if result.get("task_scope") in {"public_institution_internal", "non_government"}:
        return "national_task"
    if result.get("network_scope") in {"external_complete", "other_closed_network"}:
        return "network_data"
    if result.get("service_scope") == "non_target":
        return "service_scope"
    return "specialized_model"
