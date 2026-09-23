from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import ActionItem, AnalysisRun, Notice, NoticeDecision
from ..schemas import CompactDeepAnalysis, DeepAnalysis, Evidence, SimpleAnalysis
from .attachment_policy import select_preferred_documents
from .filter_rules import FilterResult, evaluate_notice, evaluate_service_scope
from .jev_shadow import record_jev_shadow
from .platform_usage import (
    COMMON_PLATFORM_MENTION as _COMMON_PLATFORM_MENTION,
    COMMON_PLATFORM_NON_USE as _COMMON_PLATFORM_NON_USE,
    COMMON_PLATFORM_USAGE as _COMMON_PLATFORM_USAGE,
    OPTIONAL_USAGE_REASON,
    is_optional_platform_usage_text,
)


T = TypeVar("T", bound=BaseModel)
Usage = dict[str, int | str | bool]
KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)
CURRENT_CRITERIA_VERSION = "common-platform-v7-service-construction-scope"
CLASSIFICATION_LABELS = {
    "1": "적합·사용",
    "2": "적합·미반영",
    "3": "전환·확인검토",
    "4": "사용명시·조건확인",
    "5": "AI 서비스 부적합",
    "6": "비AI 서비스 사업",
}
LEGAL_BASIS_TEXT = (
    "「인공지능·데이터 기반 행정 활성화에 관한 법률」(약칭: 인공지능데이터행정법) "
    "제27조제2항: 공공기관의 장은 인공지능을 도입하는 경우 공통기반을 우선적으로 "
    "이용하도록 노력하여야 한다."
)
PLATFORM_ELIGIBILITY_CONDITIONS = (
    "서비스·데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계될 수 있어야 합니다.",
    "중앙부처·지방정부의 사무이거나 공공기관이 중앙부처·지방정부로부터 위탁받은 국가사무여야 합니다.",
    "공통기반 제공 LLM·공개 파운데이션 모델·RAG로 기능을 구현할 수 있어야 하며, 독자모델·풀파인튜닝은 별도 협의가 필요합니다.",
)
_GATE_CONCLUSION_PREFIXES = (
    "AI 사업으로 볼 직접 근거가 없어 비AI 사업으로 분류합니다.",
    "세 기본조건을 충족하고 범정부 인공지능 공통기반 활용 문구가 확인됩니다.",
    "공통기반 사용은 명시되어 있으나 기본조건의 불일치 또는 미확인 항목을 담당자에게 확인해야 합니다.",
    "세 기본조건은 충족하지만 공통기반 활용이 명시되지 않았거나 미사용으로 확인됩니다.",
    "비국가사무·공공기관 자체 내부업무 또는 외부망 완결 근거가 명시되어 공통기반 직접 활용 대상에서 제외합니다.",
    "v6 국가사무 기준상 비국가사무·공공기관 자체 내부업무이거나 외부망 완결 근거가 확인되어 공통기반 직접 활용 대상에서 제외합니다.",
    "공개 문서의 미확인 항목은 불충족으로 단정하지 않고 담당자 확인 대상으로 분류합니다.",
    "폐쇄망 연계 또는 독자모델·풀파인튜닝의 제공모델 대체 가능성을 담당자와 검토해야 합니다.",
    "AI 사업이지만 기본조건을 충족하지 못하거나 전환 가능성이 확인되지 않고 공통기반 사용도 확인되지 않습니다.",
    "정보화 서비스 구축 또는 이를 위한 BPR·ISP·연구용역이 아니므로 검사 비대상으로 분류합니다.",
)


def _human_guidance(model: DeepAnalysis, code: str) -> str:
    """Write a copy-ready pre-notice opinion in an ordinary public-service tone."""
    network = {
        "internal_or_connected": "서비스와 데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계되는 구조",
        "hybrid": "내부망과 외부망을 함께 사용하는 구조",
        "other_closed_network": "별도 폐쇄망에서 운영하는 구조",
        "external_complete": "인터넷망에서 서비스와 데이터 처리가 완결되는 구조",
        "unclear": "서비스 운영망과 데이터 처리 위치가 공개 문서에 명확히 제시되지 않은 상태",
    }.get(model.network_scope, "운영망 구성을 추가로 확인해야 하는 상태")
    task = {
        "government": "중앙부처 또는 지방정부의 행정사무",
        "delegated_government": "중앙부처 또는 지방정부로부터 위탁받은 국가사무",
        "public_institution_internal": "공공기관 자체 내부업무",
        "non_government": "국가사무에 해당하지 않는 업무",
        "unclear": "국가사무 또는 위탁사무인지 공개 문서만으로 확인하기 어려운 업무",
    }.get(model.task_scope, "업무 성격을 추가로 확인해야 하는 업무")
    model_state = {
        "platform_llm_or_rag": "공통기반에서 제공하는 LLM 또는 RAG로 구현할 수 있는 기능",
        "custom_model_or_full_finetuning": "독자모델 또는 풀파인튜닝을 전제로 한 기능",
        "unclear": "공통기반 제공 LLM·RAG로 구현할 수 있는지 명확하지 않은 기능",
    }.get(model.model_fit, "적용 모델을 추가로 확인해야 하는 기능")

    opening = (
        "안녕하세요. 공개된 사전규격을 검토한 결과, 이 사업은 인공지능을 도입하는 사업으로 보여 "
        "이용 조건에 맞는 경우 범정부 인공지능 공통기반 활용을 적극 검토할 필요가 있어 의견드립니다."
    )
    current = f"현재 문서상으로는 {network}이며, {task}이고, {model_state}으로 확인됩니다."

    changes: list[str] = []
    if code == "2":
        changes.append(
            "세 가지 기본조건은 충족하는 것으로 보이지만 공통기반 활용 계획은 확인되지 않습니다. "
            "본공고 제안요청서에 공통기반의 LLM·RAG를 적용할 기능, 연계 방식과 대상 데이터를 명시하면 "
            "공통기반을 활용하여 구축할 수 있습니다."
        )
    else:
        if model.network_scope == "unclear":
            changes.append(
                "서비스와 데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계되는 것으로 확인되면 "
                "공통기반을 활용할 수 있습니다."
            )
        elif model.network_scope == "other_closed_network":
            changes.append(
                "현재의 별도 폐쇄망을 행정망·업무망과 연계할 수 있도록 구성하고 데이터 처리 범위를 명확히 하면 "
                "공통기반 활용이 가능합니다."
            )
        if model.task_scope == "unclear":
            changes.append(
                "또한 이 업무가 중앙부처·지방정부의 사무이거나 해당 기관으로부터 위탁받은 국가사무임이 확인되면 "
                "이용대상 업무 조건을 충족합니다."
            )
        if model.model_fit == "unclear":
            changes.append(
                "필요한 AI 기능을 공통기반에서 제공하는 LLM 또는 공개 파운데이션 모델과 RAG로 구현할 수 있는 것으로 "
                "확인되면 공통기반에서 구축할 수 있습니다."
            )
        elif model.model_fit == "custom_model_or_full_finetuning":
            changes.append(
                "독자모델·풀파인튜닝 요구를 공통기반에서 제공하는 공개 파운데이션 모델과 RAG 방식으로 변경할 수 있다면 "
                "별도 모델 구축 없이 공통기반을 활용할 수 있습니다. 변경이 어렵다면 사전 협의가 필요합니다."
            )
        if code == "4":
            changes.append(
                "공통기반을 사용한다고 명시한 내용과 실제 망·업무·모델 조건이 일치하도록 위 사항을 본공고 전에 "
                "보완해 주시기 바랍니다."
            )

    request = (
        "위 내용을 검토하시어 공통기반 활용 가능 여부와 본공고 반영 계획을 회신해 주시기 바랍니다. "
        "공개 문서에서 확인되지 않은 사항은 현재 계획과 근거를 함께 알려주시면 감사하겠습니다."
    )
    legal = f"관련 법적 근거는 {LEGAL_BASIS_TEXT}"
    return "\n\n".join((opening, current, " ".join(changes), request, legal))


def _without_prior_gate_conclusions(summary: str) -> str:
    value = summary.strip()
    changed = True
    while changed:
        changed = False
        for prefix in _GATE_CONCLUSION_PREFIXES:
            if value.startswith(prefix):
                value = value[len(prefix):].lstrip()
                changed = True
                break
    return value


_CENTRAL_GOVERNMENT_AGENCIES = (
    "감사원", "고용노동부", "공정거래위원회", "과학기술정보통신부", "관세청",
    "교육부", "국가보훈부", "국가인권위원회", "국무조정실", "국무총리비서실",
    "국방부", "국세청", "국토교통부", "금융위원회", "기상청", "기획재정부",
    "농림축산식품부", "농촌진흥청", "대검찰청", "대통령비서실", "문화체육관광부",
    "방송통신위원회", "방위사업청", "법무부", "법제처", "병무청", "보건복지부",
    "산림청", "산업통상자원부", "새만금개발청", "소방청", "식품의약품안전처",
    "여성가족부", "외교부", "인사혁신처", "조달청", "중소벤처기업부", "질병관리청",
    "통계청", "통일부", "특허청", "해양경찰청", "해양수산부", "행정안전부",
    "행정중심복합도시건설청", "환경부", "경찰청", "기후에너지환경부",
    "산업통상부", "성평등가족부", "재정경제부", "국가데이터처", "기획예산처",
    "지식재산처", "검찰청", "국가유산청", "우주항공청", "재외동포청",
    "개인정보보호위원회", "국민권익위원회", "방송미디어통신위원회",
    "원자력안전위원회", "국가정보원", "대통령경호처",
)
_LOCAL_GOVERNMENT_ROOTS = (
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라북도", "전라남도",
    "경상북도", "경상남도", "제주특별자치도",
)
_STATUTORY_DELEGATE_AGENCIES = (
    "한국지능정보사회진흥원", "NIA", "한국지역정보개발원", "KLID",
)
_PROCUREMENT_AGENCY_PATTERN = re.compile(r"(?:^|\s)(?:조달청|[가-힣]+지방조달청)(?:\s|$)")
_DIRECT_AGENCY_LABELS = (
    "발주기관", "발주부서", "수요기관", "수요부서", "주관기관", "주관부서", "담당기관", "담당부서",
)


def _metadata_value(source_text: str, label: str) -> str:
    match = re.search(rf"(?m)^{re.escape(label)}:\s*(.+?)\s*$", source_text)
    return match.group(1).strip() if match else ""


def _is_procurement_intermediary(value: str) -> bool:
    return bool(_PROCUREMENT_AGENCY_PATTERN.search(value.strip()))


def _document_text(source_text: str) -> str:
    return source_text.split("추출 본문:", 1)[-1] if "추출 본문:" in source_text else source_text


def _labeled_document_lines(source_text: str, labels: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Extract colon and markdown-table agency labels from the business document only."""
    label_pattern = "|".join(re.escape(label) for label in labels)
    results: list[tuple[str, str, str]] = []
    for raw_line in _document_text(source_text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        colon = re.search(
            rf"(?:^|[|])\s*(?:\*\*)?({label_pattern})(?:\*\*)?\s*[:：]\s*(.+?)(?:\s*[|]|$)",
            line, re.IGNORECASE,
        )
        table = re.match(
            rf"^\|\s*(?:\*\*)?({label_pattern})(?:\*\*)?\s*\|\s*(.+?)\s*\|?$",
            line, re.IGNORECASE,
        )
        match = colon or table
        if not match:
            continue
        value = re.sub(r"(?:\*\*|<br\s*/?>).*$", "", match.group(2), flags=re.IGNORECASE).strip(" |*")
        if value:
            results.append((match.group(1), value, line[:1200]))
    return results


def _looks_like_full_agency(value: str) -> bool:
    if _is_government_buyer(value) or _contains_government_entity(value):
        return True
    compact = re.sub(r"\s+", "", value)
    return bool(re.search(
        r"(?:공사|공단|재단|진흥원|연구원|개발원|평가원|관리원|정보원|대학교|대학원|병원|협회|위원회)$",
        compact,
    ))


def _effective_buyer(source_text: str) -> tuple[str, Evidence | None, bool]:
    """Resolve the service owner; a procurement office is only an intermediary."""
    listed = _metadata_value(source_text, "기관")
    demand = _metadata_value(source_text, "수요기관")
    announcing = _metadata_value(source_text, "공고기관")
    procurement = _is_procurement_intermediary(announcing) or (
        not announcing and _is_procurement_intermediary(listed)
    )
    if not procurement:
        return listed, None, False

    document_entities = _labeled_document_lines(source_text, _DIRECT_AGENCY_LABELS)
    for label, value, line in document_entities:
        if _looks_like_full_agency(value) or (demand and _same_organization(demand, value)):
            return value, Evidence(
                quote=line, section="사업문서", interpretation=f"조달 대행기관과 구분되는 실제 {label}",
            ), True

    if demand and (not _is_procurement_intermediary(demand) or demand.strip() == "조달청"):
        return demand, Evidence(
            quote=demand, section="나라장터 수요기관", interpretation="조달 대행기관과 구분되는 실수요기관",
        ), True
    return "", None, True


def _is_government_buyer(agency: str) -> bool:
    compact = re.sub(r"\s+", "", agency)
    if any(
        compact == re.sub(r"\s+", "", name)
        or compact.startswith(re.sub(r"\s+", "", name))
        for name in _CENTRAL_GOVERNMENT_AGENCIES
    ):
        return True
    if any(agency == root or agency.startswith(f"{root} ") for root in _LOCAL_GOVERNMENT_ROOTS):
        return True
    if compact.endswith(("시청", "군청", "구청", "도청", "교육청")):
        return True
    # 나라장터 발주기관에는 청사 접미사 없이 지방자치단체명만 들어오는 경우가 있다.
    # 공사·공단·재단 등 공공기관과 혼동하지 않도록 행정구역 접미사만 허용한다.
    return bool(re.fullmatch(r"[가-힣]{2,}(?:특별시|광역시|특별자치시|특별자치도|도|시|군|구)", compact))


def _contains_government_entity(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    if any(re.sub(r"\s+", "", name) in compact for name in _CENTRAL_GOVERNMENT_AGENCIES):
        return True
    if any(re.sub(r"\s+", "", root) in compact for root in _LOCAL_GOVERNMENT_ROOTS):
        return True
    return bool(re.search(
        r"[가-힣]{2,}(?:(?:시청|군청|구청|도청|교육청)|(?:시|군|구)(?=\s+[가-힣A-Za-z0-9]+(?:과|국|실|본부|센터)))(?:\b|$)",
        text,
    ))


def _relationship_lines(source_text: str) -> list[str]:
    label = (
        r"(?:주무|소관|주관|관련|협조|협력|위탁|수탁|출연)\s*"
        r"(?:부처|부서|기관|관청|지방자치단체|지자체)?"
    )
    colon_lines = [
        line.strip() for line in _document_text(source_text).splitlines()
        if line.strip() and re.search(rf"(?:^|\s|[|]){label}\s*[:：]", line, re.IGNORECASE)
    ]
    table_labels = (
        "주무부처", "주무기관", "소관부처", "소관기관", "주관부처", "주관기관", "주관부서",
        "관련부처", "관련기관", "협조부처", "협조기관", "협력기관", "위탁기관", "수탁기관", "출연기관",
        "발주기관", "발주부서", "수요기관", "수요부서",
    )
    table_lines = [line for _label, _value, line in _labeled_document_lines(source_text, table_labels)]
    return list(dict.fromkeys([*colon_lines, *table_lines]))


def _relationship_value(line: str) -> str:
    if re.search(r"[:：]", line):
        return re.split(r"[:：]", line, maxsplit=1)[-1].strip(" |*")
    cells = [cell.strip(" *") for cell in line.strip().strip("|").split("|")]
    return cells[1] if len(cells) > 1 else ""


def _same_organization(left: str, right: str) -> bool:
    normalize = lambda value: re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()
    first, second = normalize(left), normalize(right)
    return bool(first and second and (first == second or first in second or second in first))


def _first_matching_line(
    source_text: str, patterns: tuple[str, ...], interpretation: str,
) -> Evidence | None:
    for line in (part.strip() for part in source_text.splitlines()):
        if line and any(re.search(pattern, line, re.IGNORECASE) for pattern in patterns):
            return Evidence(
                quote=line[:1200], section="공고문·사업문서", interpretation=interpretation,
            )
    return None


def enforce_public_task_policy(model: DeepAnalysis, source_text: str) -> DeepAnalysis:
    """Infer government work conservatively while preserving an explicit internal-work exclusion."""
    agency, resolved_evidence, procurement = _effective_buyer(source_text)
    if agency and _is_government_buyer(agency):
        return model.model_copy(update={
            "task_scope": "government",
            "task_scope_reason": (
                "조달 대행기관이 아닌 사업문서의 발주·주관기관 또는 나라장터 실수요기관이 "
                "중앙부처·지방정부로 확인되어 국가·지방 행정사무로 분류했습니다."
                if procurement else
                "발주기관이 중앙부처 또는 지방정부이므로 국가·지방 행정사무로 분류했습니다."
            ),
            "task_scope_evidence": [resolved_evidence or Evidence(
                quote=agency, section="발주기관", interpretation="중앙부처·지방정부 직접 발주",
            )],
        })

    relationships = _relationship_lines(source_text)
    government_relationship = next((
        line for line in relationships
        if _contains_government_entity(line) or _is_government_buyer(_relationship_value(line))
    ), None)
    is_statutory_delegate = bool(
        agency and any(name.casefold() in agency.casefold() for name in _STATUTORY_DELEGATE_AGENCIES)
    )
    # NIA·KLID 등 법정 수탁기관은 자기 기관이 주관기관으로 함께 적혀 있더라도
    # 이 사업의 중앙부처·지방정부 주무·위탁 관계가 확인되면 국가사무가 우선한다.
    if is_statutory_delegate and government_relationship:
        return model.model_copy(update={
            "task_scope": "delegated_government",
            "task_scope_reason": "법정 수탁기관 사업에서 중앙부처 또는 지방정부의 주무·위탁 관계를 확인했습니다.",
            "task_scope_evidence": [Evidence(
                quote=government_relationship[:1200], section="공고문·사업문서",
                interpretation="법정 수탁기관의 중앙부처·지방정부 주무·위탁 관계 근거",
            )],
        })

    internal_work = _first_matching_line(source_text, (
        r"사내.{0,30}(?:데이터|시스템|업무|행정|사무|직원|서비스|레거시)",
        r"기관\s*내부|내부\s*(?:업무|직원|임직원|행정|사무|시스템|레거시)",
        r"임직원|직원용|자체\s*(?:업무|인사|회계|구매|연구|교육|기관\s*운영)",
        r"사무\s*[·ㆍ]?\s*행정\s*편의",
    ), "비정부 발주기관의 자체 내부업무 근거")
    # 모델이 task_scope 코드만 government로 잘못 반환하더라도, 공개 문서가
    # 사내·임직원용 자체 업무임을 직접 밝히고 정부 주무/위탁 관계가 없으면
    # 국가사무로 승격하지 않는다.
    if agency and internal_work and not government_relationship and not is_statutory_delegate:
        return model.model_copy(update={
            "task_scope": "public_institution_internal",
            "task_scope_reason": (
                "중앙부처·지방정부가 아닌 기관이 발주했고 문서에서 사내·기관 내부업무 목적을 "
                "확인하여 공공기관 자체 업무로 분류했습니다."
            ),
            "task_scope_evidence": [internal_work],
        })

    # 그 밖의 공공기관이 명시적으로 자체 내부업무라고 밝힌 경우는
    # 기관에 일반적인 소관 부처가 있더라도 국가사무로 확대 추정하지 않는다.
    if model.task_scope in {"public_institution_internal", "non_government"} and model.task_scope_evidence:
        return model

    organizer = next((
        line for line in relationships
        if re.search(r"주관\s*(?:부처|부서|기관)?\s*[:：]", line, re.IGNORECASE)
        and _same_organization(agency, _relationship_value(line))
    ), None)
    if agency and organizer:
        return model.model_copy(update={
            "task_scope": "public_institution_internal",
            "task_scope_reason": "비정부 공공기관이 발주하고 주관기관도 해당 공공기관으로 명시되어 자체 내부업무로 분류했습니다.",
            "task_scope_evidence": [Evidence(
                quote=organizer[:1200], section="공고문·사업문서",
                interpretation="발주기관과 주관기관이 동일한 공공기관",
            )],
        })

    supervising = (
        Evidence(
            quote=government_relationship[:1200], section="공고문·사업문서",
            interpretation="중앙부처·지방정부의 주무·수탁·출연·관련·협조 관계 근거",
        )
        if government_relationship else _first_matching_line(source_text, (
            r"(?:중앙부처|중앙정부|지방정부|지방자치단체|지자체).{0,40}(?:위탁|수탁|대행|소관|주관|감독|출연|협조)",
            r"(?:위탁|수탁|대행|출연|협조).{0,40}(?:중앙부처|중앙정부|지방정부|지방자치단체|지자체)",
        ), "중앙부처·지방정부의 소관 또는 위탁 업무 근거")
    )
    if supervising:
        return model.model_copy(update={
            "task_scope": "delegated_government",
            "task_scope_reason": "사업 내용에서 중앙부처 또는 지방정부의 주무·수탁·출연·관련·협조 관계를 확인했습니다.",
            "task_scope_evidence": [supervising],
        })

    if (
        not procurement
        and model.task_scope in {"government", "delegated_government"}
        and model.task_scope_evidence
    ):
        return model
    if is_statutory_delegate:
        return model.model_copy(update={
            "task_scope": "unclear",
            "task_scope_reason": "법정 국가사무 수탁 가능 기관이지만 이 사업의 중앙부처·지방정부 주무·위탁 관계가 확인되지 않습니다.",
            "task_scope_evidence": [],
        })
    if agency:
        evidence = relationships[0] if relationships else agency
        return model.model_copy(update={
            "task_scope": "non_government",
            "task_scope_reason": "비정부 발주기관이며 주무·관련·협조기관에서 중앙부처 또는 지방정부 관계가 확인되지 않아 비국가사무로 분류했습니다.",
            "task_scope_evidence": [Evidence(
                quote=evidence[:1200], section="공고문·사업문서" if relationships else "발주기관",
                interpretation="중앙·지방정부의 주무·위탁 관계가 확인되지 않음",
            )],
        })
    return model.model_copy(update={
        "task_scope": "unclear",
        "task_scope_reason": (
            "조달 대행기관만 확인되고 사업문서의 실제 발주·주관부서 또는 실수요기관을 확인할 수 없어 "
            "국가사무 여부를 담당자에게 확인해야 합니다."
            if procurement else
            "발주기관과 공개 사업문서만으로 국가사무·위탁사무 여부를 확정할 수 없어 담당자 확인이 필요합니다."
        ),
        "task_scope_evidence": [],
    })


def enforce_closed_network_policy(model: DeepAnalysis, source_text: str) -> DeepAnalysis:
    """A generic closed network is not evidence of an administrative-network connection."""
    closed = _first_matching_line(
        source_text, (r"폐쇄망", r"폐쇄\s*네트워크"), "별도 폐쇄망 운영 근거",
    )
    if not closed:
        return model
    connected = re.search(r"행정망|업무망|내부망", source_text, re.IGNORECASE)
    if connected:
        return model
    return model.model_copy(update={
        "network_scope": "other_closed_network",
        "network_reason": "폐쇄망은 확인되지만 행정망·업무망과의 연계 여부가 확인되지 않습니다.",
        "network_evidence": [closed],
    })


def _json_object(value: str) -> dict[str, Any]:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("LLM 응답에서 JSON 객체를 찾을 수 없습니다.")
    return json.loads(cleaned[start:end + 1])


_DEEP_EVIDENCE_FIELDS = (
    "network_evidence", "task_scope_evidence", "model_fit_evidence",
    "platform_usage_evidence", "remediation_evidence", "evidence",
)


def _drop_blank_evidence(value: dict[str, Any]) -> dict[str, Any]:
    """Discard provider placeholders such as {quote: ""} before validation."""
    cleaned = dict(value)
    for field in _DEEP_EVIDENCE_FIELDS:
        items = cleaned.get(field)
        if isinstance(items, list):
            cleaned[field] = [
                item for item in items
                if isinstance(item, dict) and str(item.get("quote") or "").strip()
            ]
    return cleaned


def _downgrade_invalid_deep_gate_values(value: dict[str, Any]) -> dict[str, Any]:
    """Turn malformed provider gate enums into an auditable unknown value.

    A provider occasionally copies ai_relevance (for example high) into
    task_scope. Retrying the same prompt rarely repairs that deterministic
    mistake. Unknown is the only safe coercion: the server can still promote a
    gate later when literal source evidence or agency metadata supports it.
    """
    cleaned = dict(value)
    gates = (
        (
            "network_scope",
            {"internal_or_connected", "hybrid", "other_closed_network", "external_complete", "unclear"},
            "network_evidence",
            "network_reason",
        ),
        (
            "task_scope",
            {"government", "delegated_government", "public_institution_internal", "non_government", "unclear"},
            "task_scope_evidence",
            "task_scope_reason",
        ),
        (
            "model_fit",
            {"platform_llm_or_rag", "custom_model_or_full_finetuning", "unclear"},
            "model_fit_evidence",
            "model_fit_reason",
        ),
        (
            "platform_usage",
            {"uses", "not_used", "not_mentioned", "unclear"},
            "platform_usage_evidence",
            "platform_usage_reason",
        ),
    )
    for field, allowed, evidence_field, reason_field in gates:
        raw = cleaned.get(field)
        if raw not in allowed:
            cleaned[field] = "unclear"
            cleaned[evidence_field] = []
            reason = str(cleaned.get(reason_field) or "")
            cleaned[reason_field] = (
                f"{reason} 공급자 응답의 조건값이 유효하지 않아 확인 필요로 조정했습니다."
            ).strip()[:1500]
    remediation = cleaned.get("remediation_feasibility")
    if remediation not in {"feasible", "not_feasible", "unclear", "not_needed"}:
        cleaned["remediation_feasibility"] = "unclear"
        cleaned["remediation_targets"] = []
        cleaned["remediation_evidence"] = []
        reason = str(cleaned.get("remediation_reason") or "")
        cleaned["remediation_reason"] = (
            f"{reason} 공급자 응답의 변경 가능성 값이 유효하지 않아 확인 필요로 조정했습니다."
        ).strip()[:1500]
    return cleaned


def _ground_deep_evidence(model: DeepAnalysis, source_text: str) -> DeepAnalysis:
    """Keep literal source quotes and downgrade facts whose asserted evidence vanished."""
    updates: dict[str, Any] = {}
    grounded_by_field: dict[str, list[Evidence]] = {}
    for field in _DEEP_EVIDENCE_FIELDS:
        grounded = [
            item for item in getattr(model, field, [])
            if _evidence_is_grounded([item], source_text)
        ]
        grounded_by_field[field] = grounded
        updates[field] = grounded

    gate_fields = (
        ("network_scope", "network_evidence", "network_reason"),
        ("task_scope", "task_scope_evidence", "task_scope_reason"),
        ("model_fit", "model_fit_evidence", "model_fit_reason"),
    )
    for value_field, evidence_field, reason_field in gate_fields:
        if getattr(model, value_field) != "unclear" and not grounded_by_field[evidence_field]:
            updates[value_field] = "unclear"
            updates[reason_field] = (
                f"{getattr(model, reason_field)} 원문과 일치하는 직접 인용이 없어 불명확으로 조정했습니다."
            )[:1500]
    if model.remediation_feasibility in {"feasible", "not_feasible"} and not grounded_by_field["remediation_evidence"]:
        updates["remediation_feasibility"] = "unclear"
        updates["remediation_targets"] = []
        updates["remediation_reason"] = (
            f"{model.remediation_reason} 원문과 일치하는 직접 인용이 없어 불명확으로 조정했습니다."
        )[:1500]
    return model.model_copy(update=updates)


def _literal_evidence(quotes: list[str], source_text: str, interpretation: str) -> list[Evidence]:
    """Recover the literal source span even when the provider normalized whitespace."""
    result: list[Evidence] = []
    for raw_quote in quotes[:3]:
        quote = str(raw_quote or "").strip()
        if not quote:
            continue
        if quote in source_text:
            literal = quote
        else:
            tokens = re.findall(r"\S+", quote)
            if not tokens:
                continue
            match = re.search(r"\s+".join(re.escape(token) for token in tokens), source_text, re.I)
            if not match:
                continue
            literal = match.group(0)
        result.append(Evidence(
            quote=literal[:1200], section="추출 본문", interpretation=interpretation,
        ))
    return result


def _ground_simple_evidence(model: SimpleAnalysis, source_text: str) -> SimpleAnalysis:
    """Keep literal stage-2 quotes and recover a source line for AI candidates."""
    grounded: list[Evidence] = []
    for item in model.evidence:
        matches = _literal_evidence([item.quote], source_text, item.interpretation)
        if matches:
            matches[0].section = item.section
            grounded.extend(matches)
    if not grounded and model.ai_relevance in {"high", "medium"}:
        marker = re.compile(
            r"(?<![A-Za-z])AI(?![A-Za-z])|\bLLM\b|\bRAG\b|인공지능|생성형\s*AI|"
            r"머신러닝|딥러닝|자연어\s*처리|컴퓨터\s*비전",
            re.I,
        )
        for line in (part.strip() for part in source_text.splitlines()):
            if line and marker.search(line):
                grounded.append(Evidence(
                    quote=line[:1200],
                    section="사업명·추출 본문",
                    interpretation="AI 사업 후보를 뒷받침하는 입력 원문의 직접 문구",
                ))
                break
    return model.model_copy(update={"evidence": grounded[:10]})


def _evidence_mentions(evidence: list[Evidence], patterns: tuple[str, ...]) -> bool:
    joined = "\n".join(item.quote for item in evidence)
    return any(re.search(pattern, joined, re.I) for pattern in patterns)


def expand_compact_deep(
    facts: CompactDeepAnalysis, source_text: str, rule: FilterResult,
) -> DeepAnalysis:
    """Expand Cohere's compact fact extraction into the full auditable result."""
    network_evidence = _literal_evidence(facts.network_quotes, source_text, "망·데이터 처리 범위 근거")
    task_evidence = _literal_evidence(facts.task_scope_quotes, source_text, "국가사무 또는 기관업무 범위 근거")
    model_evidence = _literal_evidence(facts.model_fit_quotes, source_text, "요구 모델·기능 범위 근거")
    usage_evidence = _literal_evidence(facts.platform_usage_quotes, source_text, "공통기반 사용 상태 근거")
    remediation_evidence = _literal_evidence(facts.remediation_quotes, source_text, "망·모델 변경 가능성 근거")

    network_scope = facts.network_scope if facts.network_scope == "unclear" or network_evidence else "unclear"
    task_scope = facts.task_scope if facts.task_scope == "unclear" or task_evidence else "unclear"
    model_fit = facts.model_fit if facts.model_fit == "unclear" or model_evidence else "unclear"

    # A literal quote is necessary but not sufficient: the quote itself must
    # state the relevant gate. This prevents generic "AI 기반" phrases from
    # being inferred as LLM/RAG fit or an agency name from becoming a national
    # delegated task.
    if network_scope != "unclear" and not _evidence_mentions(network_evidence, (
        r"행정망", r"업무망", r"내부망", r"외부망", r"인터넷망", r"폐쇄망", r"DMZ", r"망\s*연계",
    )):
        network_scope, network_evidence = "unclear", []
    task_patterns = {
        "government": (
            r"국가\s*사무", r"행정\s*사무", r"지방\s*사무", r"법정\s*사무",
            r"중앙부처.{0,30}(?:업무|사무)", r"지방(?:자치)?정부.{0,30}(?:업무|사무)",
        ),
        "delegated_government": (
            r"국가\s*사무", r"위탁\s*사무", r"수탁\s*사무", r"법정\s*위탁",
        ),
        "public_institution_internal": (
            r"기관\s*내부", r"내부\s*업무", r"임직원", r"내부.{0,20}(?:인사|회계|구매|기관\s*운영)",
        ),
        "non_government": (r"민간\s*(?:업무|서비스)", r"학교\s*(?:업무|교육)", r"민간\s*기업"),
    }
    if task_scope != "unclear" and not _evidence_mentions(
        task_evidence, task_patterns.get(task_scope, ()),
    ):
        task_scope, task_evidence = "unclear", []
    platform_model_patterns = (
        r"\bLLM\b", r"\bRAG\b", r"거대\s*언어\s*모델", r"대규모\s*언어\s*모델",
        r"챗봇", r"질의\s*응답", r"문서\s*검색", r"검색\s*증강", r"생성형\s*AI",
        r"AI\s*에이전트",
    )
    custom_model_patterns = (
        r"풀\s*파인튜닝", r"독자\s*모델", r"자체\s*모델",
        r"전용.{0,20}(?:예측|비전|음성)\s*모델",
    )
    expected_model_patterns = (
        platform_model_patterns if model_fit == "platform_llm_or_rag" else custom_model_patterns
    )
    if model_fit != "unclear" and not _evidence_mentions(model_evidence, expected_model_patterns):
        model_fit, model_evidence = "unclear", []
    remediation = facts.remediation_feasibility
    remediation_targets = list(facts.remediation_targets)
    if remediation in {"feasible", "not_feasible"} and not remediation_evidence:
        remediation, remediation_targets = "unclear", []
    if remediation == "feasible" and not _evidence_mentions(remediation_evidence, (
        r"변경\s*가능", r"전환\s*가능", r"조정\s*가능", r"연계\s*가능", r"변경할\s*수",
        r"전환할\s*수", r"협의.{0,20}(?:변경|전환|조정)",
    )):
        remediation, remediation_targets, remediation_evidence = "unclear", [], []
    if remediation == "not_feasible" and not _evidence_mentions(remediation_evidence, (
        r"변경\s*불가", r"전환\s*불가", r"변경할\s*수\s*없", r"전환할\s*수\s*없",
    )):
        remediation, remediation_targets, remediation_evidence = "unclear", [], []

    platform_usage = facts.platform_usage
    if platform_usage in {"uses", "not_used"} and not usage_evidence:
        platform_usage = "unclear"

    evidence = [
        *network_evidence, *task_evidence, *model_evidence,
        *usage_evidence, *remediation_evidence,
    ][:20]
    return DeepAnalysis(
        classification_code="5",
        final_grade="E",
        ai_relevance=facts.ai_relevance,
        common_platform_fit="uncertain",
        usage_mentioned="yes" if platform_usage == "uses" else "no" if platform_usage == "not_used" else "unclear",
        network_scope=network_scope,
        network_reason=facts.network_reason,
        network_evidence=network_evidence,
        task_scope=task_scope,
        task_scope_reason=facts.task_scope_reason,
        task_scope_evidence=task_evidence,
        model_fit=model_fit,
        model_fit_reason=facts.model_fit_reason,
        model_fit_evidence=model_evidence,
        platform_usage=platform_usage,
        platform_usage_reason=facts.platform_usage_reason,
        platform_usage_evidence=usage_evidence,
        remediation_feasibility=remediation,
        remediation_targets=remediation_targets,
        remediation_reason=facts.remediation_reason,
        remediation_evidence=remediation_evidence,
        eligibility="uncertain",
        possible_common_platform_functions=(
            list(facts.possible_common_platform_functions) or _possible_functions(source_text)
        ),
        summary=facts.summary,
        evidence=evidence,
        check_questions=[],
        recommended_action="manual_review",
        priority_score=max(20, rule.score),
        confidence=facts.confidence,
        caveats=["공개 문서에 없는 조건은 추정하지 않았습니다."],
        guidance_message="",
    )

def is_current_deep_result(result_json: str | None) -> bool:
    try:
        value = json.loads(result_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(value, dict) and value.get("criteria_version") == CURRENT_CRITERIA_VERSION


def _evidence_is_grounded(evidence: list[Evidence], source_text: str) -> bool:
    # 공고명·기관명 같은 공개 메타데이터도 분석 입력의 직접 근거가 될 수 있다.
    compact_source = re.sub(r"\s+", " ", source_text).casefold()
    return all(re.sub(r"\s+", " ", item.quote).casefold() in compact_source for item in evidence)


def validate_grounded(model: T, source_text: str) -> T:
    evidence = list(getattr(model, "evidence", []))
    for field in (
        "network_evidence", "task_scope_evidence", "model_fit_evidence",
        "platform_usage_evidence", "remediation_evidence",
    ):
        evidence.extend(getattr(model, field, []))
    if evidence and not _evidence_is_grounded(evidence, source_text):
        raise ValueError("AI 근거 인용이 입력 원문과 일치하지 않습니다.")
    return model


def enforce_explicit_ai_scope(model: SimpleAnalysis, source_text: str) -> SimpleAnalysis:
    """AAM·첨단·자동화 등을 AI로 확대 해석한 2차 오탐을 결정론적으로 차단한다."""
    markers = (
        r"(?<![A-Za-z])AI(?![A-Za-z])",
        r"\bLLM\b",
        r"\bRAG\b",
        r"artificial intelligence",
        r"machine learning",
        r"deep learning",
        r"natural language processing",
        r"computer vision",
        r"인공지능",
        r"생성형\s*AI",
        r"머신러닝",
        r"딥러닝",
        r"자연어\s*처리",
        r"컴퓨터\s*비전",
        r"지능형\s*(?:분석|검색|상담|서비스|시스템)",
    )
    if model.ai_relevance == "low":
        model.needs_deep_review = False
        return model
    if any(re.search(marker, source_text, re.I) for marker in markers):
        return model
    return SimpleAnalysis(
        ai_relevance="low",
        needs_deep_review=False,
        reason="입력에서 직접적인 AI 기능 근거를 확인하지 못해 심층검토 대상에서 제외했습니다.",
        evidence=[],
        confidence=min(model.confidence, 0.8),
    )


def preserve_deep_ai_scope(model: DeepAnalysis, simple: SimpleAnalysis) -> DeepAnalysis:
    """Do not let stage 3 erase a stage-2-confirmed AI education/event project."""
    if (
        simple.needs_deep_review
        and simple.ai_relevance in {"high", "medium"}
        and model.ai_relevance == "low"
    ):
        return model.model_copy(update={
            "ai_relevance": simple.ai_relevance,
            "summary": (
                "2차에서 AI가 사업명 또는 핵심 주제로 확인되어 AI 사업 범위를 유지합니다. "
                f"{model.summary}"
            )[:3000],
        })
    return model


def merge_simple_and_gate_evidence(model: DeepAnalysis, simple: SimpleAnalysis) -> DeepAnalysis:
    """Keep the stage-2 AI basis together with every confirmed gate quote.

    Stage 2 answers why this is an AI project, while stage 3 answers whether
    the mandatory common-platform conditions are met. Both must remain visible
    in the final audited result.
    """
    combined = [
        *simple.evidence,
        *model.evidence,
        *model.network_evidence,
        *model.task_scope_evidence,
        *model.model_fit_evidence,
        *model.platform_usage_evidence,
        *model.remediation_evidence,
    ]
    unique: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for item in combined:
        key = (re.sub(r"\s+", " ", item.quote).strip(), item.interpretation.strip())
        if not key[0] or key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return model.model_copy(update={"evidence": unique[:20]})


def _first_evidence(text: str, keywords: list[str]) -> Evidence | None:
    document_text = text.split("추출 본문:\n", 1)[-1]
    for line in (part.strip() for part in re.split(r"[\n。]", document_text)):
        if line and any(keyword.casefold() in line.casefold() for keyword in keywords):
            return Evidence(quote=line[:1000], section="추출 본문", interpretation="AI 기능 또는 공통기반 관련 명시")
    return None


def _possible_functions(text: str) -> list[str]:
    mapping = {
        "LLM API": ["llm", "거대언어모델", "생성형 ai", "챗봇"],
        "RAG/공통 참조데이터": ["rag", "검색증강", "벡터db", "지식검색", "질의응답"],
        "GPU inference": ["gpu", "추론 서버", "모델 서빙"],
        "Agent builder": ["ai 에이전트", "업무 에이전트", "에이전트 빌더"],
    }
    folded = text.casefold()
    return [name for name, keywords in mapping.items() if any(key in folded for key in keywords)]


def enforce_common_platform_gates(model: DeepAnalysis, source_text: str) -> DeepAnalysis:
    """Derive the final grade from the three mandatory eligibility gates.

    The model extracts structured facts and evidence; this deterministic layer
    prevents generic AI/RAG requirements from being promoted to A/B without
    eligible network and public-task evidence.
    """
    scope_status, scope_reason = evaluate_service_scope(
        _metadata_value(source_text, "사업명"), source_text,
    )
    if scope_status == "non_target":
        conclusion = "정보화 서비스 구축 또는 이를 위한 BPR·ISP·연구용역이 아니므로 검사 비대상으로 분류합니다."
        return model.model_copy(update={
            "service_scope": "non_target",
            "service_scope_reason": scope_reason,
            "classification_code": "6",
            "final_grade": "E",
            "common_platform_fit": "low",
            "eligibility": "ineligible",
            "summary": f"{conclusion} {scope_reason}",
            "check_questions": [],
            "recommended_action": "no_action",
            "priority_score": 0,
            "remediation_feasibility": "not_needed",
            "remediation_targets": [],
            "remediation_reason": "검사 범위 밖의 용역이므로 공통기반 전환 검토를 수행하지 않습니다.",
            "caveats": list(dict.fromkeys([*model.caveats, scope_reason])),
            "guidance_message": "",
        })

    model = model.model_copy(update={
        "service_scope": scope_status,
        "service_scope_reason": scope_reason,
    })
    model = enforce_public_task_policy(model, source_text)
    model = enforce_closed_network_policy(model, source_text)
    explicit_non_use = bool(_COMMON_PLATFORM_NON_USE.search(source_text))
    explicit_usage = not explicit_non_use and bool(_COMMON_PLATFORM_USAGE.search(source_text))
    optional_usage = (
        not explicit_non_use
        and not explicit_usage
        and is_optional_platform_usage_text(source_text)
    )
    if model.network_scope == "external_complete" or model.task_scope in {
        "public_institution_internal", "non_government",
    }:
        eligibility = "ineligible"
    elif model.network_scope == "unclear" or model.task_scope == "unclear" or model.model_fit == "unclear":
        eligibility = "uncertain"
    elif model.model_fit == "custom_model_or_full_finetuning":
        eligibility = "consultation_required"
    elif (
        model.network_scope in {"internal_or_connected", "hybrid"}
        and model.task_scope in {"government", "delegated_government"}
        and model.model_fit == "platform_llm_or_rag"
    ):
        eligibility = "eligible"
    else:
        eligibility = "uncertain"

    if explicit_usage:
        platform_usage = "uses"
    elif explicit_non_use:
        platform_usage = "not_used"
    elif optional_usage or _COMMON_PLATFORM_MENTION.search(source_text):
        platform_usage = "unclear"
    else:
        platform_usage = "not_mentioned"
    platform_usage_evidence = list(model.platform_usage_evidence)
    if (platform_usage in {"uses", "not_used"} or optional_usage) and not platform_usage_evidence:
        usage_evidence = _first_evidence(source_text, [
            "범정부 인공지능 공통기반", "범정부 AI 공통기반", "AI 공통기반",
            "범정부 인공지능 플랫폼", "범정부 AI 플랫폼",
        ])
        if usage_evidence:
            platform_usage_evidence = [usage_evidence]
    platform_usage_reason = {
        "uses": "원문에서 범정부 인공지능 공통기반의 사용·연계 계획을 확인했습니다.",
        "not_used": "원문에서 범정부 인공지능 공통기반을 사용하지 않는다는 문구를 확인했습니다.",
        "unclear": OPTIONAL_USAGE_REASON if optional_usage else "공통기반이 언급됐지만 실제 사용 또는 미사용 여부는 명확하지 않습니다.",
        "not_mentioned": "공통기반 사용 또는 미사용 문구가 확인되지 않습니다.",
    }[platform_usage]
    ai_relevance = "medium" if explicit_usage and model.ai_relevance == "low" else model.ai_relevance
    explicit_exclusion = (
        model.network_scope == "external_complete"
        or model.task_scope in {"public_institution_internal", "non_government"}
    )
    has_unknown_gate = (
        model.network_scope == "unclear"
        or model.task_scope == "unclear"
        or model.model_fit == "unclear"
    )
    if ai_relevance == "low":
        code, grade, fit, action = "6", "E", "low", "no_action"
        score = 0
        conclusion = "AI 사업으로 볼 직접 근거가 없어 비AI 사업으로 분류합니다."
    elif platform_usage == "uses" and eligibility == "eligible":
        code, grade, fit, action = "1", "A", "high", "watch"
        score = max(85, model.priority_score)
        conclusion = "세 기본조건을 충족하고 범정부 인공지능 공통기반 활용 문구가 확인됩니다."
    elif platform_usage == "uses":
        code, grade, fit, action = "4", "D", "uncertain", "contact"
        score = max(85, model.priority_score)
        conclusion = "공통기반 사용은 명시되어 있으나 기본조건의 불일치 또는 미확인 항목을 담당자에게 확인해야 합니다."
    elif eligibility == "eligible":
        code, grade, fit, action = "2", "B", "high", "contact"
        score = max(70, min(94, model.priority_score))
        conclusion = (
            "세 기본조건을 충족하지만 공통기반이 선택적 대안으로만 제시되어 "
            "다른 방안보다 우선 검토하고 실제 채택 여부를 확인하도록 하는 장치가 부족합니다."
            if optional_usage else
            "세 기본조건은 충족하지만 공통기반 활용이 명시되지 않았거나 미사용으로 확인됩니다."
        )
    elif explicit_exclusion:
        code, grade, fit, action = "5", "E", "low", "no_action"
        score = min(39, model.priority_score)
        conclusion = "v6 국가사무 기준상 비국가사무·공공기관 자체 내부업무이거나 외부망 완결 근거가 확인되어 공통기반 직접 활용 대상에서 제외합니다."
    else:
        code = "3"
        grade = "D" if has_unknown_gate else "C"
        fit = "uncertain" if has_unknown_gate else "partial"
        action = "contact"
        score = max(65, min(89, model.priority_score))
        conclusion = (
            "공개 문서의 미확인 항목은 불충족으로 단정하지 않고 담당자 확인 대상으로 분류합니다."
            if has_unknown_gate else
            "폐쇄망 연계 또는 독자모델·풀파인튜닝의 제공모델 대체 가능성을 담당자와 검토해야 합니다."
        )

    # 질문은 최종 게이트 상태에서 다시 구성한다. 모델이 만든 일반 질문을
    # 유지하면 이미 발주기관 근거로 확정한 국가사무까지 재확인하게 된다.
    questions: list[str] = []
    if code == "2":
        questions.append(
            "다른 인프라 대안을 선택하기 전에 범정부 인공지능 공통기반 적용 가능성을 "
            "우선 검토했는지와 실제 채택 여부를 확인 필요"
            if optional_usage else
            "범정부 인공지능 공통기반의 LLM API 또는 RAG를 적용·연계할 계획인지 확인 필요"
        )
    if model.network_scope == "unclear":
        questions.append("서비스와 데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계되는지 확인 필요")
    if model.network_scope == "other_closed_network":
        questions.append("명시된 폐쇄망이 행정망·업무망과 연결 가능한지, 연결 시 데이터 처리 범위와 보안 경계를 확인 필요")
    if model.task_scope == "unclear":
        questions.append("해당 업무의 주무부처·지방정부와 국가사무 또는 위탁사무 근거를 담당자에게 확인 필요")
    if model.model_fit == "unclear":
        questions.append("공통기반 제공 LLM·RAG로 처리 가능한 기능 범위와 별도 모델 필요 여부를 확인 필요")
    if model.model_fit == "custom_model_or_full_finetuning":
        questions.append("독자모델·풀파인튜닝 요구를 공통기반의 공개 파운데이션 모델·RAG로 대체할 수 있는지 확인 필요")
    if code == "3":
        questions.append("확인 결과에 따라 운영망 연계 또는 제공모델 전환을 본공고 전에 반영할 수 있는지 확인 필요")
    if code == "4":
        questions.append("공통기반 사용 계획과 실제 망·국가사무·모델 기본조건이 일치하는지 본공고 전에 확인 필요")
    questions = list(dict.fromkeys(questions))

    caveats = list(dict.fromkeys([
        *model.caveats,
        "중앙부처·지방정부 직접 발주는 국가사무로, 비정부 공공기관은 주관기관 동일 여부와 정부 주무·수탁·출연·관련·협조 관계로 구분했습니다.",
        "온프레미스라는 표현만으로 행정망·업무망 연계 여부를 확정하지 않았습니다.",
    ]))
    evidence = list(model.evidence)
    if grade in {"A", "B", "C"} and not evidence:
        evidence = [
            *model.network_evidence,
            *model.task_scope_evidence,
            *model.model_fit_evidence,
        ]
    usage = "yes" if platform_usage == "uses" else ("no" if platform_usage == "not_used" else "unclear")
    guidance = ""
    if code in {"2", "3", "4"}:
        guidance = _human_guidance(model, code)
    if model.task_scope == "public_institution_internal":
        detail_summary = " ".join(filter(None, (
            model.task_scope_reason,
            model.network_reason,
            model.model_fit_reason,
            platform_usage_reason,
        )))
    else:
        detail_summary = _without_prior_gate_conclusions(model.summary)
    return DeepAnalysis.model_validate({**model.model_dump(), **{
        "classification_code": code,
        "final_grade": grade,
        "ai_relevance": ai_relevance,
        "common_platform_fit": fit,
        "usage_mentioned": usage,
        "platform_usage": platform_usage,
        "platform_usage_reason": platform_usage_reason,
        "platform_usage_evidence": platform_usage_evidence,
        "eligibility": eligibility,
        "summary": " ".join(filter(None, (conclusion, detail_summary))),
        "evidence": evidence,
        "check_questions": questions,
        "recommended_action": action,
        "priority_score": score,
        "caveats": caveats,
        "guidance_message": guidance,
    }})


def _truncate_context(context: str, maximum: int) -> str:
    if len(context) <= maximum:
        return context
    marker = "추출 본문:\n"
    if marker not in context:
        return context[:maximum]
    metadata, document = context.split(marker, 1)
    available = max(0, maximum - len(metadata) - len(marker))
    return f"{metadata}{marker}{document[:available]}"


def _usage(model: str, provider: str, prompt: int = 0, completion: int = 0, *, fallback: bool = False) -> Usage:
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "model_name": model,
        "provider": provider,
        "fallback_used": fallback,
    }


class Analyzer(Protocol):
    simple_model_name: str
    deep_model_name: str
    cache_fingerprint: str
    simple_cache_fingerprint: str
    deep_cache_fingerprint: str

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]: ...
    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]: ...


class MockAnalyzer:
    simple_model_name = "mock-deterministic-v1"
    deep_model_name = "mock-deterministic-v1"
    cache_fingerprint = "mock-deterministic-v1"
    simple_cache_fingerprint = "mock-simple-deterministic-v2"
    deep_cache_fingerprint = "mock-deep-verification-v3"

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]:
        relevance = "high" if rule.score >= 55 else "medium" if rule.score >= 20 else "low"
        evidence = _first_evidence(context, rule.matched_include_keywords) if rule.matched_include_keywords else None
        result = SimpleAnalysis(
            ai_relevance=relevance,
            needs_deep_review=not rule.skip and (relevance != "low" or rule.needs_sample_review),
            reason=rule.reason,
            evidence=[evidence] if evidence else [],
            confidence=0.88 if rule.matched_include_keywords else 0.55,
        )
        return result, _usage(self.simple_model_name, "mock")

    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]:
        folded = context.casefold()
        usage_mentioned = bool(_COMMON_PLATFORM_USAGE.search(context))
        functions = _possible_functions(context)
        evidence_item = _first_evidence(context, rule.matched_include_keywords + ["인공지능", "생성형", "자연어", "머신러닝"])

        internal_terms = ["행정망", "업무망", "내부망", "폐쇄망"]
        external_terms = ["인터넷망", "외부망"]
        external_complete_terms = ["외부망에서 완결", "인터넷망에서 완결", "내부망 연계 없음"]
        if any(term in folded for term in external_complete_terms):
            network_scope = "external_complete"
            network_words = external_complete_terms
        elif any(term in folded for term in internal_terms) and any(term in folded for term in external_terms):
            network_scope = "hybrid"
            network_words = internal_terms + external_terms
        elif any(term in folded for term in internal_terms):
            network_scope = "internal_or_connected"
            network_words = internal_terms
        else:
            network_scope = "unclear"
            network_words = []
        network_evidence = _first_evidence(context, network_words) if network_words else None

        delegated_terms = ["국가사무 위탁", "위탁받은 국가사무", "법정 위탁사무", "정부 위탁사무"]
        government_terms = ["국가사무", "지방행정", "행정사무"]
        internal_task_terms = ["기관 내부업무", "임직원 내부업무", "교직원 내부업무"]
        if any(term in folded for term in delegated_terms):
            task_scope = "delegated_government"
            task_words = delegated_terms
        elif any(term in folded for term in internal_task_terms):
            task_scope = "public_institution_internal"
            task_words = internal_task_terms
        elif any(term in folded for term in government_terms):
            task_scope = "government"
            task_words = government_terms
        else:
            task_scope = "unclear"
            task_words = []
        task_evidence = _first_evidence(context, task_words) if task_words else None

        custom_terms = ["풀파인튜닝", "풀 파인튜닝", "독자 모델", "자체 모델"]
        direct_terms = ["챗봇", "질의응답", "요약", "분류", "생성형 ai", "llm", "rag", "문서검색"]
        if any(term in folded for term in custom_terms):
            model_fit = "custom_model_or_full_finetuning"
            model_words = custom_terms
        elif any(term in folded for term in direct_terms):
            model_fit = "platform_llm_or_rag"
            model_words = direct_terms
        else:
            model_fit = "unclear"
            model_words = []
        model_evidence = _first_evidence(context, model_words) if model_words else None
        usage_evidence = _first_evidence(context, ["범정부 인공지능 공통기반", "범정부 AI 공통기반", "AI 공통기반"]) if usage_mentioned else None
        no_change_needed = network_scope in {"internal_or_connected", "hybrid"} and model_fit == "platform_llm_or_rag"

        result = DeepAnalysis(
            classification_code="5",
            final_grade="D",
            ai_relevance=simple.ai_relevance,
            common_platform_fit="uncertain",
            usage_mentioned="yes" if usage_mentioned else "unclear",
            network_scope=network_scope,
            network_reason="문서에서 망·데이터 처리 조건을 분류했습니다." if network_evidence else "망·데이터 처리 조건이 불명확합니다.",
            network_evidence=[network_evidence] if network_evidence else [],
            task_scope=task_scope,
            task_scope_reason="문서에서 국가사무 범위 근거를 확인했습니다." if task_evidence else "국가사무 또는 위탁사무 여부가 불명확합니다.",
            task_scope_evidence=[task_evidence] if task_evidence else [],
            model_fit=model_fit,
            model_fit_reason="문서의 모델·기능 요구를 분류했습니다." if model_evidence else "필요한 모델·학습 방식이 불명확합니다.",
            model_fit_evidence=[model_evidence] if model_evidence else [],
            platform_usage="uses" if usage_mentioned else "not_mentioned",
            platform_usage_reason="공통기반 활용 문구를 확인했습니다." if usage_mentioned else "공통기반 사용 또는 미사용 문구가 없습니다.",
            platform_usage_evidence=[usage_evidence] if usage_evidence else [],
            remediation_feasibility="not_needed" if no_change_needed else "unclear",
            remediation_targets=[],
            remediation_reason="현재 망과 모델 조건이 충족됩니다." if no_change_needed else "망·모델 변경 가능성을 확인할 근거가 없습니다.",
            remediation_evidence=[],
            eligibility="uncertain",
            possible_common_platform_functions=functions,
            summary="AI 기능을 확인했으며 세 가지 공통기반 기본조건을 종합 검토했습니다.",
            evidence=[evidence_item] if evidence_item else [],
            check_questions=["세 가지 공통기반 기본조건의 미확인 사항을 담당자에게 확인할 필요"],
            recommended_action="manual_review",
            priority_score=max(20, rule.score),
            confidence=0.84 if evidence_item else 0.5,
            caveats=["공개 문서에 없는 망·위탁사무 조건은 추정하지 않았습니다."],
            guidance_message="",
        )
        return result, _usage(self.deep_model_name, "mock")


@dataclass(frozen=True)
class ChatEndpoint:
    provider: str
    base_url: str
    api_key: str
    model: str
    timeout_seconds: int
    reasoning_effort: str = ""
    min_interval_seconds: float = 0.0


class LLMRateLimitExceeded(RuntimeError):
    pass


class OpenAIChatClient:
    """Gemini/OpenAI/NVIDIA의 OpenAI 호환 Chat Completions 최소 공통 어댑터."""

    _pace_lock = Lock()
    _next_request_at: dict[tuple[str, str, str], float] = {}
    _rate_limited_until: dict[tuple[str, str, str], float] = {}

    def __init__(self, endpoint: ChatEndpoint):
        self.endpoint = endpoint

    def _pace(self) -> None:
        interval = max(0.0, self.endpoint.min_interval_seconds)
        if interval == 0:
            return
        key = (self.endpoint.provider, self.endpoint.base_url, self.endpoint.model)
        with self._pace_lock:
            wait = self._next_request_at.get(key, 0.0) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._next_request_at[key] = time.monotonic() + interval

    @staticmethod
    def _is_daily_quota(response: httpx.Response) -> bool:
        body = response.text.casefold()
        return any(marker in body for marker in (
            "perday", "per_day", "requestsperday", "daily quota", "quota/day",
        ))

    def _check_rate_limit_circuit(self) -> None:
        key = (self.endpoint.provider, self.endpoint.base_url, self.endpoint.model)
        with self._pace_lock:
            remaining = self._rate_limited_until.get(key, 0.0) - time.monotonic()
        if remaining > 0:
            raise LLMRateLimitExceeded(
                f"{self.endpoint.provider} 호출 한도 회로 차단 중({int(remaining)}초 남음)"
            )

    def _open_rate_limit_circuit(self, *, daily: bool) -> None:
        key = (self.endpoint.provider, self.endpoint.base_url, self.endpoint.model)
        if daily:
            now = datetime.now(KST)
            tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=5, second=0, microsecond=0)
            seconds = max(300.0, (tomorrow - now).total_seconds())
        else:
            seconds = 900.0
        with self._pace_lock:
            self._rate_limited_until[key] = time.monotonic() + seconds

    @staticmethod
    def _retry_delay(exc: Exception, attempt: int) -> float:
        if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
            retry_after = exc.response.headers.get("retry-after", "")
            try:
                return max(float(retry_after), 20.0 * (attempt + 1))
            except ValueError:
                return 20.0 * (attempt + 1)
        return 0.5 * (2**attempt)

    def call(self, system: str, context: str, schema: type[T]) -> tuple[T, Usage]:
        endpoint = self.endpoint
        output_tokens = 900 if schema is SimpleAnalysis else 8_000
        if endpoint.provider == "cohere" and schema is not SimpleAnalysis:
            output_tokens = 3_000
        payload: dict[str, Any] = {
            "model": endpoint.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": context},
            ],
        }
        if endpoint.provider == "nvidia":
            payload.update({"temperature": 1.0, "top_p": 0.95, "max_tokens": output_tokens})
            if endpoint.model == "nvidia/nemotron-3-super-120b-a12b":
                # PoC 4에서 검증한 설정: 사고 토큰 대신 완결된 판정 JSON에
                # 출력 예산을 집중해 응답 누락과 스키마 실패를 줄인다.
                payload["chat_template_kwargs"] = {"enable_thinking": False}
        elif endpoint.provider == "openai":
            payload.update({
                "response_format": {"type": "json_object"},
                "reasoning_effort": endpoint.reasoning_effort or "medium",
                "max_completion_tokens": output_tokens,
            })
        elif endpoint.provider == "cohere":
            payload.update({
                # Use Cohere's native V2 JSON mode. The OpenAI compatibility
                # layer intermittently converts this extraction into a tool
                # generation and returns INVALID_TOOL_GENERATION.
                "thinking": {"type": "disabled"},
                "temperature": 0,
                "max_tokens": output_tokens,
            })
        else:
            payload.update({"response_format": {"type": "json_object"}, "temperature": 0, "max_tokens": output_tokens})

        headers = {"Authorization": f"Bearer {endpoint.api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        with httpx.Client(timeout=endpoint.timeout_seconds) as client:
            for attempt in range(3):
                try:
                    self._check_rate_limit_circuit()
                    self._pace()
                    request_url = (
                        "https://api.cohere.ai/v2/chat"
                        if endpoint.provider == "cohere"
                        else f"{endpoint.base_url}/chat/completions"
                    )
                    response = client.post(request_url, headers=headers, json=payload)
                    response.raise_for_status()
                    raw = response.json()
                    if endpoint.provider == "cohere":
                        content = next((
                            block["text"] for block in raw["message"]["content"]
                            if block.get("type") == "text" and block.get("text")
                        ), "")
                        finish_reason = raw.get("finish_reason", "unknown")
                    else:
                        choice = raw["choices"][0]
                        content = choice["message"]["content"]
                        finish_reason = choice.get("finish_reason", "unknown")
                    if not isinstance(content, str) or not content.strip():
                        raise ValueError(
                            "LLM 응답 content가 비어 있습니다. "
                            f"finish_reason={finish_reason}"
                        )
                    raw_model = _json_object(content)
                    if schema is DeepAnalysis:
                        raw_model = _downgrade_invalid_deep_gate_values(
                            _drop_blank_evidence(raw_model)
                        )
                    model = schema.model_validate(raw_model)
                    if isinstance(model, DeepAnalysis):
                        model = _ground_deep_evidence(model, context)
                    elif isinstance(model, SimpleAnalysis):
                        model = _ground_simple_evidence(model, context)
                    validate_grounded(model, context)
                    tokens = raw.get("usage", {})
                    if endpoint.provider == "cohere":
                        tokens = tokens.get("tokens", tokens)
                    return model, _usage(
                        str(raw.get("model") or endpoint.model),
                        endpoint.provider,
                        int(tokens.get("prompt_tokens", tokens.get("input_tokens", 0))),
                        int(tokens.get("completion_tokens", tokens.get("output_tokens", 0))),
                    )
                except (httpx.HTTPError, ValidationError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
                    last_error = exc
                    if (
                        isinstance(exc, httpx.HTTPStatusError)
                        and exc.response.status_code == 429
                        and self._is_daily_quota(exc.response)
                    ):
                        self._open_rate_limit_circuit(daily=True)
                        break
                    if attempt < 2:
                        time.sleep(self._retry_delay(exc, attempt))
                except LLMRateLimitExceeded as exc:
                    last_error = exc
                    break
        detail = type(last_error).__name__
        if isinstance(last_error, httpx.HTTPStatusError):
            response_detail = re.sub(r"\s+", " ", last_error.response.text).strip()[:300]
            detail = f"HTTP {last_error.response.status_code}"
            detail += f": {response_detail}" if response_detail else ""
            if last_error.response.status_code == 429:
                self._open_rate_limit_circuit(daily=self._is_daily_quota(last_error.response))
                raise LLMRateLimitExceeded(f"{endpoint.provider} 호출 한도 초과: {detail}") from last_error
        elif isinstance(last_error, LLMRateLimitExceeded):
            raise last_error
        elif last_error is not None:
            detail = f"{type(last_error).__name__}: {str(last_error)[:300]}"
        raise RuntimeError(f"{endpoint.provider} LLM 분석 3회 실패: {detail}") from last_error


class RoutedAnalyzer:
    _semaphores: dict[int, BoundedSemaphore] = {}
    _semaphores_lock = Lock()

    def __init__(self, settings: Settings):
        self.settings = settings
        prompt_root = Path(__file__).resolve().parent.parent / "prompts"
        self.simple_prompt = (prompt_root / "simple_review.md").read_text(encoding="utf-8")
        self.deep_prompt = (prompt_root / "deep_review.md").read_text(encoding="utf-8")
        self.cohere_deep_prompt = (prompt_root / "cohere_deep_review.md").read_text(encoding="utf-8")
        self.mock = MockAnalyzer()
        self.simple_endpoint = ChatEndpoint(
            settings.stage2_provider,
            settings.stage2_base_url,
            settings.stage2_api_key,
            settings.stage2_model,
            settings.stage2_timeout_seconds,
            min_interval_seconds=settings.stage2_min_interval_seconds,
        )
        self.simple_fallback_endpoint = ChatEndpoint(
            settings.stage2_fallback_provider,
            settings.stage2_fallback_base_url,
            settings.stage2_fallback_api_key,
            settings.stage2_fallback_model,
            settings.stage2_timeout_seconds,
            min_interval_seconds=settings.stage2_fallback_min_interval_seconds,
        )
        self.primary_endpoint = ChatEndpoint(
            settings.stage3_primary_provider,
            settings.stage3_primary_base_url,
            settings.stage3_primary_api_key,
            settings.stage3_primary_model,
            settings.stage3_timeout_seconds,
            settings.stage3_primary_reasoning_effort,
        )
        self.fallback_endpoint = ChatEndpoint(
            settings.stage3_fallback_provider,
            settings.stage3_fallback_base_url,
            settings.stage3_fallback_api_key,
            settings.stage3_fallback_model,
            settings.stage3_timeout_seconds,
        )
        self.simple_model_name = f"{self.simple_endpoint.provider}:{self.simple_endpoint.model}"
        self.deep_model_name = f"{self.primary_endpoint.provider}:{self.primary_endpoint.model}"
        self.simple_cache_fingerprint = hashlib.sha256(
            "|".join((
                self.simple_model_name,
                f"{self.simple_fallback_endpoint.provider}:{self.simple_fallback_endpoint.model}",
                self.simple_prompt,
            )).encode("utf-8")
        ).hexdigest()
        self.deep_cache_fingerprint = hashlib.sha256(
            "|".join((
                self.deep_model_name,
                f"{self.fallback_endpoint.provider}:{self.fallback_endpoint.model}",
                self.deep_prompt,
                self.cohere_deep_prompt,
            )).encode("utf-8")
        ).hexdigest()
        self.cache_fingerprint = hashlib.sha256(
            f"{self.simple_cache_fingerprint}|{self.deep_cache_fingerprint}".encode("utf-8")
        ).hexdigest()
        with self._semaphores_lock:
            self.deep_semaphore = self._semaphores.setdefault(
                settings.stage3_max_concurrency,
                BoundedSemaphore(settings.stage3_max_concurrency),
            )

    def simple(self, context: str, rule: FilterResult) -> tuple[SimpleAnalysis, Usage]:
        scoped = _truncate_context(context, self.settings.stage2_max_input_chars)
        if self.simple_endpoint.provider == "mock":
            return self.mock.simple(scoped, rule)
        try:
            return OpenAIChatClient(self.simple_endpoint).call(
                self.simple_prompt, scoped, SimpleAnalysis,
            )
        except RuntimeError as primary_error:
            fallback = self.simple_fallback_endpoint
            if fallback.provider == "mock" or not fallback.api_key:
                raise primary_error
            logger.warning("2차 주 공급자 실패로 fallback을 사용합니다: %s", primary_error)
            result, usage = OpenAIChatClient(fallback).call(
                self.simple_prompt, scoped, SimpleAnalysis,
            )
            usage["fallback_used"] = True
            usage["primary_error"] = str(primary_error)[:500]
            return result, usage

    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]:
        scoped = _truncate_context(context, self.settings.stage3_max_input_chars)
        primary, fallback = self._deep_endpoints(scoped)
        acquired = self.deep_semaphore.acquire(timeout=self.settings.stage3_timeout_seconds)
        if not acquired:
            raise RuntimeError("3차 분석 동시성 대기시간을 초과했습니다.")
        try:
            if primary.provider == "mock":
                return self.mock.deep(scoped, simple, rule)
            try:
                return self._call_deep_endpoint(primary, scoped, rule)
            except RuntimeError as primary_error:
                if fallback.provider == "mock" or not fallback.api_key:
                    raise primary_error
                logger.warning("3차 주 공급자 실패로 fallback을 사용합니다: %s", primary_error)
                result, usage = self._call_deep_endpoint(fallback, scoped, rule)
                usage["fallback_used"] = True
                usage["primary_error"] = str(primary_error)[:500]
                return result, usage
        finally:
            self.deep_semaphore.release()

    def _deep_endpoints(self, scoped: str) -> tuple[ChatEndpoint, ChatEndpoint]:
        """Choose a stable 50:50 route while retaining reciprocal failover."""
        if (
            self.settings.stage3_routing_mode == "balanced"
            and self.primary_endpoint.provider != "mock"
            and self.fallback_endpoint.provider != "mock"
            and self.primary_endpoint.api_key
            and self.fallback_endpoint.api_key
            and int(hashlib.sha256(scoped.encode("utf-8")).hexdigest()[:8], 16) % 2
        ):
            return self.fallback_endpoint, self.primary_endpoint
        return self.primary_endpoint, self.fallback_endpoint

    def _call_deep_endpoint(
        self, endpoint: ChatEndpoint, scoped: str, rule: FilterResult,
    ) -> tuple[DeepAnalysis, Usage]:
        if endpoint.provider == "cohere":
            facts, usage = OpenAIChatClient(endpoint).call(
                self.cohere_deep_prompt, scoped, CompactDeepAnalysis,
            )
            return expand_compact_deep(facts, scoped, rule), usage
        return OpenAIChatClient(endpoint).call(self.deep_prompt, scoped, DeepAnalysis)


def get_analyzer(settings: Settings | None = None) -> Analyzer:
    return RoutedAnalyzer(settings or get_settings())


def notice_context(notice: Notice) -> str:
    attachments = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
    text = "\n\n".join(attachment.text_excerpt or "" for attachment in attachments)
    filenames = ", ".join(attachment.original_filename for attachment in attachments)
    try:
        raw = json.loads(notice.raw_payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    demand_agency = str(raw.get("rlDminsttNm") or raw.get("dminsttNm") or notice.agency_name or "").strip()
    announcing_agency = str(raw.get("orderInsttNm") or raw.get("ntceInsttNm") or notice.agency_name or "").strip()
    return (
        f"사업명: {notice.title}\n기관: {demand_agency}\n수요기관: {demand_agency}\n"
        f"공고기관: {announcing_agency}\n예산: {notice.budget_amount or '미상'}\n첨부: {filenames}"
        f"\n\n추출 본문:\n{text}"
    )


def _input_hash(context: str, run_type: str, fingerprint: str) -> str:
    return hashlib.sha256(f"{run_type}|{fingerprint}|{context}".encode("utf-8")).hexdigest()


def _stage3_used_today(db: Session) -> int:
    now = datetime.now(timezone.utc)
    local_start = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    utc_start = local_start.astimezone(timezone.utc)
    return int(db.scalar(select(func.count(AnalysisRun.id)).where(
        AnalysisRun.run_type == "deep_ai",
        AnalysisRun.status == "success",
        AnalysisRun.created_at >= utc_start,
    )) or 0)


def _quota_result(simple: SimpleAnalysis, rule: FilterResult) -> DeepAnalysis:
    return DeepAnalysis(
        classification_code="5",
        final_grade="D",
        ai_relevance=simple.ai_relevance,
        common_platform_fit="uncertain",
        usage_mentioned="unclear",
        network_scope="unclear",
        network_reason="일일 심층검증 한도로 망 조건을 분석하지 못했습니다.",
        network_evidence=[],
        task_scope="unclear",
        task_scope_reason="일일 심층검증 한도로 국가사무 범위를 분석하지 못했습니다.",
        task_scope_evidence=[],
        model_fit="unclear",
        model_fit_reason="일일 심층검증 한도로 모델 적합성을 분석하지 못했습니다.",
        model_fit_evidence=[],
        platform_usage="unclear",
        platform_usage_reason="일일 심층검증 한도로 사용 여부를 분석하지 못했습니다.",
        platform_usage_evidence=[],
        remediation_feasibility="unclear",
        remediation_targets=[],
        remediation_reason="일일 심층검증 한도로 변경 가능성을 분석하지 못했습니다.",
        remediation_evidence=[],
        eligibility="uncertain",
        summary="오늘의 자동 심층검증 한도에 도달하여 다음 실행 또는 수동 검토가 필요합니다.",
        evidence=[],
        check_questions=["3차 분석 일일 한도 초기화 후 심층검증을 다시 실행할 필요"],
        recommended_action="manual_review",
        priority_score=max(20, rule.score),
        confidence=min(simple.confidence, 0.5),
        caveats=["비용 보호를 위해 3차 LLM 호출을 수행하지 않았습니다."],
        guidance_message="",
    )


def update_decision_projection(db: Session, notice: Notice, result: DeepAnalysis) -> None:
    """Synchronize the mutable current-view projection from an audited result."""
    decision = notice.decision or db.scalar(select(NoticeDecision).where(
        NoticeDecision.notice_id == notice.id
    )) or NoticeDecision(notice_id=notice.id)
    decision.final_grade = result.final_grade
    decision.ai_relevance = result.ai_relevance
    decision.common_platform_fit = result.common_platform_fit
    decision.usage_mentioned = result.usage_mentioned
    decision.priority_score = result.priority_score
    decision.recommended_action = result.recommended_action
    decision.summary = result.summary
    decision.possible_functions_json = json.dumps(result.possible_common_platform_functions, ensure_ascii=False)
    decision.key_evidence_json = json.dumps([item.model_dump() for item in result.evidence], ensure_ascii=False)
    decision.check_questions_json = json.dumps(result.check_questions, ensure_ascii=False)
    decision.caveats_json = json.dumps(result.caveats, ensure_ascii=False)
    if notice.decision is None:
        db.add(decision)
    action_exists = notice.action or db.scalar(select(ActionItem).where(ActionItem.notice_id == notice.id))
    if action_exists is None:
        db.add(ActionItem(notice_id=notice.id))


def _rule_screen_result(rule: FilterResult) -> DeepAnalysis:
    scope_excluded = rule.scope_status == "non_target"
    return DeepAnalysis(
        service_scope="non_target" if scope_excluded else rule.scope_status,
        service_scope_reason=rule.scope_reason,
        classification_code="6",
        final_grade="E",
        ai_relevance="medium" if scope_excluded and rule.matched_include_keywords else "low",
        common_platform_fit="low",
        usage_mentioned="unclear",
        network_scope="unclear",
        network_reason="검사 범위 비대상으로 망 조건을 심층검증하지 않았습니다." if scope_excluded else "비AI 규칙 분류로 망 조건 심층검증 대상이 아닙니다.",
        network_evidence=[],
        task_scope="unclear",
        task_scope_reason="검사 범위 비대상으로 국가사무 조건을 심층검증하지 않았습니다." if scope_excluded else "비AI 규칙 분류로 국가사무 조건 심층검증 대상이 아닙니다.",
        task_scope_evidence=[],
        model_fit="unclear",
        model_fit_reason="구축 대상 AI 모델 검증을 수행하지 않았습니다." if scope_excluded else "AI 모델 요구가 확인되지 않았습니다.",
        model_fit_evidence=[],
        platform_usage="not_mentioned",
        platform_usage_reason="공통기반 사용 여부는 검사하지 않았습니다." if scope_excluded else "공통기반 사용 문구가 확인되지 않았습니다.",
        platform_usage_evidence=[],
        remediation_feasibility="not_needed" if scope_excluded else "unclear",
        remediation_targets=[],
        remediation_reason="검사 범위 밖의 용역이므로 공통기반 전환 검토 대상이 아닙니다." if scope_excluded else "비AI 사업으로 망·모델 전환 검토 대상이 아닙니다.",
        remediation_evidence=[],
        eligibility="ineligible" if scope_excluded else "uncertain",
        possible_common_platform_functions=[],
        summary=rule.scope_reason if scope_excluded else "제목과 사업 문서에서 직접적인 AI 구축·개선 근거를 찾지 못해 비AI 사업으로 분류했습니다.",
        evidence=[],
        check_questions=[],
        recommended_action="no_action",
        priority_score=0,
        confidence=0.95 if scope_excluded else 0.8,
        caveats=[
            "사업 범위가 정보화 서비스 구축 또는 이를 위한 BPR·ISP·연구용역으로 변경되면 재검토합니다."
            if scope_excluded else
            "규칙 기반 분류이며 AI 기능이 문서에 누락된 경우 수동 재검토할 수 있습니다."
        ],
        guidance_message="",
    )


def record_non_ai_screen(db: Session, notice: Notice, rule: FilterResult) -> bool:
    """Persist an inexpensive category-6 non-AI-service result."""
    context = notice_context(notice)
    gate_hash = _input_hash(context, "deep_ai", CURRENT_CRITERIA_VERSION)
    result = _rule_screen_result(rule)
    shadow_added = record_jev_shadow(
        db,
        notice,
        context,
        reference_business_type=(
            "ai_related_out_of_scope" if rule.scope_status == "non_target" else "non_ai_service"
        ),
        reference_needs_deep_review=False,
        reference_ai_relevance=result.ai_relevance,
    )
    existing = next((
        run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        if run.run_type == "deep_ai" and run.status == "skipped"
        and run.model_name == "rule-gate" and run.input_hash == gate_hash
        and is_current_deep_result(run.result_json)
    ), None)
    if existing:
        if shadow_added:
            db.commit()
        return False
    db.add(AnalysisRun(
        notice_id=notice.id,
        run_type="deep_ai",
        model_name="rule-gate",
        input_hash=gate_hash,
        status="skipped",
        result_json=result.model_dump_json(),
        confidence=result.confidence,
        cost_prompt_tokens=0,
        cost_completion_tokens=0,
    ))
    update_decision_projection(db, notice, result)
    db.commit()
    return True


def analyze_notice(db: Session, notice: Notice, *, deep: bool = True, force: bool = False) -> DeepAnalysis | SimpleAnalysis:
    settings = get_settings()
    context = notice_context(notice)
    rule = evaluate_notice(
        title=notice.title,
        agency=notice.agency_name,
        budget_amount=notice.budget_amount,
        attachment_names=[item.original_filename for item in notice.attachments],
        text_excerpt=context,
    )
    if deep and rule.scope_status == "non_target":
        result = _rule_screen_result(rule)
        record_non_ai_screen(db, notice, rule)
        return result
    analyzer = get_analyzer(settings)
    simple_hash = _input_hash(context, "simple_ai", analyzer.simple_cache_fingerprint)
    deep_hash = _input_hash(context, "deep_ai", analyzer.deep_cache_fingerprint)
    requested_type = "deep_ai" if deep else "simple_ai"

    if not force:
        cached = db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == requested_type,
            AnalysisRun.input_hash == (deep_hash if deep else simple_hash),
            AnalysisRun.status == "success",
        ).order_by(AnalysisRun.id.desc()))
        if cached:
            cached_result = (DeepAnalysis if deep else SimpleAnalysis).model_validate_json(cached.result_json)
            if isinstance(cached_result, DeepAnalysis):
                reference_business_type = (
                    "ai_related_out_of_scope" if cached_result.service_scope == "non_target"
                    else "non_ai_service" if cached_result.classification_code == "6" or cached_result.ai_relevance == "low"
                    else "ai_service" if cached_result.service_scope == "target"
                    else "uncertain"
                )
                reference_needs_deep_review = (
                    cached_result.service_scope != "non_target"
                    and cached_result.classification_code != "6"
                )
            else:
                reference_business_type = (
                    "ai_service" if cached_result.ai_relevance in {"high", "medium"} else "non_ai_service"
                )
                reference_needs_deep_review = cached_result.needs_deep_review
            if record_jev_shadow(
                db,
                notice,
                context,
                reference_business_type=reference_business_type,
                reference_needs_deep_review=reference_needs_deep_review,
                reference_ai_relevance=cached_result.ai_relevance,
                settings=settings,
            ):
                db.commit()
            return cached_result

    active_run_type = "simple_ai"
    try:
        # 수동 심층 재검사(force)는 3차만 새로 수행한다. 2차 수동검사에서만
        # Gemini를 강제 재호출하며, 불필요한 무료 쿼터 소모를 막는다.
        force_simple = force and not deep
        simple_cached = None if force_simple else db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == "simple_ai",
            AnalysisRun.input_hash == simple_hash,
            AnalysisRun.status == "success",
        ).order_by(AnalysisRun.id.desc()))
        if simple_cached is None and deep and not force_simple:
            latest_deep_terminal = db.scalar(select(AnalysisRun).where(
                AnalysisRun.notice_id == notice.id,
                AnalysisRun.run_type == "deep_ai",
                (
                    (AnalysisRun.status == "success")
                    | ((AnalysisRun.status == "skipped") & (AnalysisRun.model_name == "rule-gate"))
                ),
            ).order_by(AnalysisRun.id.desc()))
            if latest_deep_terminal and not is_current_deep_result(latest_deep_terminal.result_json):
                # Criteria migrations do not change AI relevance. Reuse the
                # latest successful stage-2 result even when the legacy deep
                # terminal was a skipped rule-gate.
                simple_cached = db.scalar(select(AnalysisRun).where(
                    AnalysisRun.notice_id == notice.id,
                    AnalysisRun.run_type == "simple_ai",
                    AnalysisRun.status == "success",
                ).order_by(AnalysisRun.id.desc()))
        if simple_cached:
            simple = SimpleAnalysis.model_validate_json(simple_cached.result_json)
        else:
            simple, simple_usage = analyzer.simple(context, rule)
            simple = enforce_explicit_ai_scope(simple, context)
            db.add(AnalysisRun(
                notice_id=notice.id,
                run_type="simple_ai",
                model_name=str(simple_usage["model_name"]),
                input_hash=simple_hash,
                status="success",
                result_json=simple.model_dump_json(),
                confidence=simple.confidence,
                cost_prompt_tokens=int(simple_usage["prompt_tokens"]),
                cost_completion_tokens=int(simple_usage["completion_tokens"]),
            ))
        record_jev_shadow(
            db,
            notice,
            context,
            reference_business_type=(
                "ai_service" if simple.ai_relevance in {"high", "medium"} else "non_ai_service"
            ),
            reference_needs_deep_review=simple.needs_deep_review,
            reference_ai_relevance=simple.ai_relevance,
            settings=settings,
        )
        if not deep:
            db.commit()
            return simple
        # Cached results also pass through the current explicit-AI guard.
        simple = enforce_explicit_ai_scope(simple, context)

        active_run_type = "deep_ai"
        if not simple.needs_deep_review:
            result = DeepAnalysis(
                classification_code="6" if simple.ai_relevance == "low" else "5",
                final_grade="E",
                ai_relevance=simple.ai_relevance,
                common_platform_fit="uncertain",
                usage_mentioned="unclear",
                network_scope="unclear",
                network_reason="2차 규칙 제외로 망 조건을 심층분석하지 않았습니다.",
                network_evidence=[],
                task_scope="unclear",
                task_scope_reason="2차 규칙 제외로 국가사무 범위를 심층분석하지 않았습니다.",
                task_scope_evidence=[],
                model_fit="unclear",
                model_fit_reason="2차 규칙 제외로 모델 적합성을 심층분석하지 않았습니다.",
                model_fit_evidence=[],
                platform_usage="not_mentioned",
                platform_usage_reason="공통기반 사용 문구를 확인하지 못했습니다.",
                platform_usage_evidence=[],
                remediation_feasibility="unclear",
                remediation_targets=[],
                remediation_reason="망·모델 변경 가능성을 분석하지 않았습니다.",
                remediation_evidence=[],
                eligibility="uncertain",
                summary="AI 직접 근거가 없어 비AI 사업으로 규칙 분류했습니다." if simple.ai_relevance == "low" else "규칙상 우선 심층검토 대상은 아니며 표본 검토가 필요합니다.",
                evidence=[],
                check_questions=["AI 기능 포함 여부를 담당자가 표본 확인할 필요"],
                recommended_action="no_action" if simple.ai_relevance == "low" else "manual_review",
                priority_score=rule.score,
                confidence=simple.confidence,
                caveats=["자동 제외가 아닌 낮은 우선순위 후보입니다."],
                guidance_message="",
            )
            deep_usage = _usage("rule-gate", "local")
            deep_status = "skipped"
        elif (
            not force and settings.stage3_daily_limit > 0
            and _stage3_used_today(db) >= settings.stage3_daily_limit
        ):
            result = _quota_result(simple, rule)
            deep_usage = _usage("daily-quota-guard", "local")
            deep_status = "skipped"
        else:
            result, deep_usage = analyzer.deep(context, simple, rule)
            result = preserve_deep_ai_scope(result, simple)
            result = enforce_common_platform_gates(result, context)
            deep_status = "success"

        result = merge_simple_and_gate_evidence(result, simple)

        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type="deep_ai",
            model_name=str(deep_usage["model_name"]),
            input_hash=deep_hash,
            status=deep_status,
            result_json=result.model_dump_json(),
            confidence=result.confidence,
            cost_prompt_tokens=int(deep_usage["prompt_tokens"]),
            cost_completion_tokens=int(deep_usage["completion_tokens"]),
            error_message=(
                f"primary provider failed; fallback used: {deep_usage.get('primary_error', '')}"[:1000]
                if deep_usage.get("fallback_used") else None
            ),
        ))
        update_decision_projection(db, notice, result)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        db.add(AnalysisRun(
            notice_id=notice.id,
            run_type=active_run_type,
            model_name=analyzer.deep_model_name if active_run_type == "deep_ai" else analyzer.simple_model_name,
            input_hash=deep_hash if active_run_type == "deep_ai" else simple_hash,
            status="failed",
            error_message=f"{type(exc).__name__}: {str(exc)[:1000]}",
        ))
        db.commit()
        raise
