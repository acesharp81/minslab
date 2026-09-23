from __future__ import annotations

import json
import re
from pathlib import Path
from threading import Lock
from typing import Any

from pydantic import ValidationError

from ..config import get_settings
from ..models import Notice
from ..schemas import (
    DEFAULT_CONSTRUCTION_OPINION_TEMPLATE,
    DEFAULT_PLANNING_OPINION_TEMPLATE,
    OpinionSenderProfile,
)
from .attachment_policy import select_preferred_documents
from .platform_usage import has_optional_platform_usage


PROFILE_FILENAME = "opinion_sender_profile.json"
GUIDE_REFERENCE = "「공공부문 AI 도입 및 활용 가이드」(NIA 누리집 nia.or.kr > 지식정보 > 간행물 > AI.gov)"
HELP_CONTACT = "대표전화 053-230-1938 / 대표 이메일 gov-ai@nia.or.kr"
_PROFILE_LOCK = Lock()
_PLANNING_PATTERN = re.compile(
    r"(?:기본\s*계획|종합\s*계획|정보화전략계획|ISP|ISMP|BPR|마스터\s*플랜|계획\s*수립|구축\s*방안\s*연구|전략\s*수립)",
    re.IGNORECASE,
)


def _profile_path() -> Path:
    settings = get_settings()
    settings.ensure_directories()
    return settings.data_dir / PROFILE_FILENAME


def load_opinion_sender_profile() -> OpinionSenderProfile:
    path = _profile_path()
    if not path.is_file():
        return OpinionSenderProfile()
    try:
        return OpinionSenderProfile.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError):
        return OpinionSenderProfile()


def save_opinion_sender_profile(profile: OpinionSenderProfile) -> OpinionSenderProfile:
    path = _profile_path()
    temporary = path.with_suffix(".tmp")
    with _PROFILE_LOCK:
        temporary.write_text(
            json.dumps(profile.model_dump(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.chmod(0o600)
        temporary.replace(path)
    return profile


def opinion_template_type(notice: Notice) -> str:
    documents = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
    source = "\n".join([
        notice.title,
        *(item.original_filename for item in documents),
        *((item.text_excerpt or "")[:4_000] for item in documents),
    ])
    return "planning" if _PLANNING_PATTERN.search(source) else "construction"


def _overview(notice: Notice, result: dict[str, Any], template_type: str) -> str:
    title = re.sub(r"^\[[^]]+\]\s*", "", notice.title).strip()
    title = re.sub(r"\s*(?:용역|사업)\s*$", "", title).strip()
    plan_match = re.match(r"(.+?)(?:의\s*)?인공지능\s*기본\s*및\s*종합\s*계획\s*수립", title)
    if plan_match:
        subject = plan_match.group(1).strip()
        return f"{subject}의 중장기 인공지능(AI)·데이터 발전 방향 마련"
    if template_type == "planning":
        return title
    functions = result.get("possible_common_platform_functions")
    if isinstance(functions, list) and functions:
        return f"{title} — {', '.join(str(item) for item in functions[:3])}"
    return title


def _user_label(notice: Notice, result: dict[str, Any]) -> str:
    task_scope = str(result.get("task_scope") or "unclear")
    if task_scope == "government":
        local_markers = r"(?:특별시|광역시|특별자치시|특별자치도|[가-힣]+도|[가-힣]+시|[가-힣]+군|[가-힣]+구|시청|군청|구청|도청)(?:\s|$)"
        evidence = result.get("task_scope_evidence")
        quotes = " ".join(
            str(item.get("quote") or "") for item in evidence
            if isinstance(item, dict)
        ) if isinstance(evidence, list) else ""
        try:
            raw = json.loads(notice.raw_payload_json or "{}")
        except (json.JSONDecodeError, TypeError):
            raw = {}
        demand = str(raw.get("rlDminsttNm") or raw.get("dminsttNm") or "") if isinstance(raw, dict) else ""
        institution_context = f"{demand} {quotes} {notice.agency_name}"
        return "지방정부(국가사무)" if re.search(local_markers, institution_context) else "중앙정부·소속기관(국가사무)"
    return {
        "delegated_government": "공공기관(위탁 국가사무)",
        "public_institution_internal": "공공기관(기관 내부업무)",
        "non_government": "국가사무 아님",
        "unclear": "확인안됨",
    }.get(task_scope, "확인안됨")


def _network_label(value: str) -> str:
    return {
        "internal_or_connected": "내부(행정·업무)망 또는 연계망",
        "hybrid": "내·외부망 연계 환경",
        "other_closed_network": "별도 폐쇄망(행정망 연계 여부 확인 필요)",
        "external_complete": "인터넷망 완결 환경",
        "unclear": "확인안됨",
    }.get(value, "확인안됨")


def _model_label(value: str) -> str:
    return {
        "platform_llm_or_rag": "공통기반 제공 모델·RAG 적용 가능",
        "custom_model_or_full_finetuning": "독자모델·풀파인튜닝(공통기반 제공 모델 대체 여부 확인 필요)",
        "unclear": "확인안됨",
    }.get(value, "확인안됨")


def _sender_greeting(profile: OpinionSenderProfile) -> str:
    organization = profile.organization.strip()
    responsibility = profile.responsibility.strip()
    person = " ".join(part for part in (profile.name.strip(), profile.position.strip()) if part)
    phone = f" ({profile.phone.strip()})" if profile.phone.strip() else ""
    if organization and responsibility:
        subject = f"{organization} '{responsibility}'을 담당하는"
    elif organization:
        subject = organization
    elif responsibility:
        subject = f"'{responsibility}'을 담당하는"
    else:
        subject = ""
    detail = " ".join(part for part in (subject, person) if part)
    return f"안녕하세요. {detail}{phone}입니다." if detail or phone else "안녕하세요."


def _render_template(template: str, values: dict[str, str]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", value)
    return rendered.strip()


def _adapt_default_opening(message: str, notice: Notice, template_type: str) -> str:
    """Name the actual notice and use the correct procurement stage in the opening."""
    stage_label = "본공고" if notice.stage == "bid_notice" else "사전규격"
    if template_type == "planning":
        old = (
            "공개된 사전규격을 검토한 결과, 인공지능 도입·구축 방향을 수립하는 "
            "계획·ISP·연구용역으로 확인되었습니다."
        )
        new = (
            f"공개된 {stage_label} 「{notice.title}」을 검토한 결과, AI 서비스 도입·구축 "
            "방향을 수립하는 계획·ISP·연구용역으로 판단됩니다."
        )
    else:
        old = "공개된 사전규격을 검토한 결과, 인공지능 서비스를 도입·구축하는 사업으로 확인되었습니다."
        new = (
            f"공개된 {stage_label} 「{notice.title}」을 검토한 결과, AI 서비스를 "
            "도입·구축하는 사업으로 판단됩니다."
        )
    return message.replace(old, new, 1)


def _add_optional_usage_review(message: str, result: dict[str, Any]) -> str:
    if not has_optional_platform_usage(result):
        return message

    analysis_line = "- 공통기반 사용 여부: 선택적 활용 명시(실제 채택 여부 미확인)"
    request_line = (
        "- 공통기반이 다른 인프라 방안과 함께 선택적으로 제시되어 있습니다. "
        "「인공지능 및 데이터 기반 행정 활성화에 관한 법률」 제27조제2항의 취지에 따라 "
        "다른 대안을 선택하기 전에 공통기반 적용 가능성을 우선 검토하고, 적용 가능한 경우 "
        "우선 반영하며 적용이 곤란한 경우 그 사유와 대체 방안 선정 근거를 사업 문서에 "
        "명시하여 주시기 바랍니다."
    )
    marker = "[검토 요청]"
    if marker in message:
        before, after = message.split(marker, 1)
        if analysis_line not in before:
            before = before.rstrip() + "\n" + analysis_line + "\n\n"
        if request_line not in after:
            after = "\n" + request_line + after
        return before + marker + after
    return message.rstrip() + f"\n\n[검토 요청]\n{analysis_line}\n{request_line}"


def _condition_review_requests(result: dict[str, Any]) -> list[str]:
    """Turn analyzed gaps into sentences an operator can read during a call."""
    requests: list[str] = []
    model = str(result.get("model_fit") or "unclear")
    network = str(result.get("network_scope") or "unclear")
    task = str(result.get("task_scope") or "unclear")
    usage = str(result.get("platform_usage") or "not_mentioned")

    if model == "custom_model_or_full_finetuning":
        requests.append(
            "서류상 독자모델 또는 풀파인튜닝이 요구되어 있습니다. 최신 국산·공개 "
            "파운데이션 모델(예: EXAONE, Solar Open, Gemma 계열 등), 공통기반 제공 모델과 "
            "RAG 조합으로 대체할 수 있는 범위를 검토해 주시기 바랍니다."
        )
    elif model == "unclear":
        requests.append(
            "서류상 사용할 모델과 구현 방식이 명확하지 않습니다. 공통기반에서 제공하는 "
            "LLM·RAG 기능으로 구현할 수 있는지와 별도 모델 학습이 필요한 범위를 확인해 "
            "주시기 바랍니다."
        )

    if network == "unclear":
        requests.append(
            "서류상 어떤 네트워크 환경에서 사용되는지 확인되지 않습니다. 행정망·업무망에서 "
            "사용하는 서비스라면 공통기반의 모델과 RAG를 API 방식으로 호출할 수 있는지 "
            "검토해 주시기 바랍니다."
        )
    elif network == "other_closed_network":
        requests.append(
            "별도 폐쇄망 사용이 확인됩니다. 해당 망과 행정망·업무망 간 안전한 연계 또는 "
            "API 호출 방식으로 공통기반을 활용할 수 있는지 검토해 주시기 바랍니다."
        )
    elif network == "external_complete":
        requests.append(
            "인터넷망에서 완결되는 구성으로 확인됩니다. 실제 업무가 행정망·업무망에서도 "
            "수행되는지 확인하고, 해당 구간에서 공통기반을 활용할 수 있는지 검토해 주시기 바랍니다."
        )

    if task == "unclear":
        requests.append(
            "이 사업이 중앙부처·지방정부의 국가사무 또는 위임·위탁 사무에 해당하는지와 "
            "실제 업무 수행기관을 확인해 주시기 바랍니다."
        )

    if usage != "uses":
        requests.append(
            "관련 법령에 따라 범정부 인공지능 공통기반 적용 가능성을 다른 인프라 대안보다 "
            "우선 검토하고, 적용 가능한 경우 사업 범위와 시스템 구성에 반영해 주시기 바랍니다."
        )
    return list(dict.fromkeys(requests))


def _add_condition_review_requests(message: str, result: dict[str, Any]) -> str:
    lines = [f"- {item}" for item in _condition_review_requests(result)]
    if not lines:
        return message
    block = "\n".join(lines)
    marker = "[검토 요청]"
    if marker in message:
        before, after = message.split(marker, 1)
        return before.rstrip() + f"\n\n{marker}\n{block}\n" + after.lstrip()
    return message.rstrip() + f"\n\n{marker}\n{block}"


def _normalize_list_spacing(message: str) -> str:
    """Keep opinion bullets contiguous even when a saved legacy template has blank lines."""
    message = re.sub(r"(?m)^-(?=\S)", "- ", message)
    return re.sub(r"\n[ \t]*\n(?=-)", "\n", message).strip()


def build_opinion_guidance(
    notice: Notice,
    result: dict[str, Any],
    profile: OpinionSenderProfile | None = None,
) -> str:
    profile = profile or load_opinion_sender_profile()
    template_type = opinion_template_type(notice)
    template = (
        profile.planning_template or DEFAULT_PLANNING_OPINION_TEMPLATE
        if template_type == "planning"
        else profile.construction_template or DEFAULT_CONSTRUCTION_OPINION_TEMPLATE
    )
    message = _render_template(template, {
        "greeting": _sender_greeting(profile),
        "overview": _overview(notice, result, template_type),
        "user": _user_label(notice, result),
        "network": _network_label(str(result.get("network_scope") or "unclear")),
        "model": _model_label(str(result.get("model_fit") or "unclear")),
        "guide_reference": GUIDE_REFERENCE,
        "help_contact": HELP_CONTACT,
    })
    message = _adapt_default_opening(message, notice, template_type)
    message = _add_optional_usage_review(message, result)
    return _normalize_list_spacing(_add_condition_review_requests(message, result))
