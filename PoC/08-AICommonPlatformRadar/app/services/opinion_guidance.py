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
    return _add_optional_usage_review(message, result)
