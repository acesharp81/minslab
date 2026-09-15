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
from .filter_rules import FilterResult, evaluate_notice


T = TypeVar("T", bound=BaseModel)
Usage = dict[str, int | str | bool]
KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)
CURRENT_CRITERIA_VERSION = "common-platform-v3-six-categories"
CLASSIFICATION_LABELS = {
    "1": "적합·사용",
    "2": "적합·미반영",
    "3": "전환검토·미반영",
    "4": "사용명시·조건점검",
    "5": "조건불충족·미사용",
    "6": "비AI 사업",
}


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


_COMMON_PLATFORM_TERM = r"(?:범정부\s*)?(?:인공지능|AI)\s*공통기반"
_COMMON_PLATFORM_MENTION = re.compile(_COMMON_PLATFORM_TERM, re.IGNORECASE)
_COMMON_PLATFORM_USAGE = re.compile(
    _COMMON_PLATFORM_TERM
    + r".{0,40}(?:활용(?:한다|하여|할\s*예정|\s*계획)|사용(?:한다|하여|할\s*예정|\s*계획)|연계(?:한다|하여|할\s*예정)|적용(?:한다|하여|할\s*예정)|이용(?:한다|하여|할\s*예정))",
    re.IGNORECASE,
)
_COMMON_PLATFORM_NON_USE = re.compile(
    rf"(?:{_COMMON_PLATFORM_TERM}.{{0,40}}(?:사용|활용|연계|적용)하지\s*않|{_COMMON_PLATFORM_TERM}.{{0,30}}미사용|미사용.{{0,30}}{_COMMON_PLATFORM_TERM})",
    re.IGNORECASE,
)


def enforce_common_platform_gates(model: DeepAnalysis, source_text: str) -> DeepAnalysis:
    """Derive the final grade from the three mandatory eligibility gates.

    The model extracts structured facts and evidence; this deterministic layer
    prevents generic AI/RAG requirements from being promoted to A/B without
    eligible network and public-task evidence.
    """
    explicit_non_use = bool(_COMMON_PLATFORM_NON_USE.search(source_text))
    explicit_usage = not explicit_non_use and bool(_COMMON_PLATFORM_USAGE.search(source_text))
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
    elif _COMMON_PLATFORM_MENTION.search(source_text):
        platform_usage = "unclear"
    else:
        platform_usage = "not_mentioned"
    platform_usage_evidence = list(model.platform_usage_evidence)
    if platform_usage in {"uses", "not_used"} and not platform_usage_evidence:
        usage_evidence = _first_evidence(source_text, ["범정부 인공지능 공통기반", "범정부 AI 공통기반", "AI 공통기반"])
        if usage_evidence:
            platform_usage_evidence = [usage_evidence]
    platform_usage_reason = {
        "uses": "원문에서 범정부 인공지능 공통기반의 사용·연계 계획을 확인했습니다.",
        "not_used": "원문에서 범정부 인공지능 공통기반을 사용하지 않는다는 문구를 확인했습니다.",
        "unclear": "공통기반이 언급됐지만 실제 사용 또는 미사용 여부는 명확하지 않습니다.",
        "not_mentioned": "공통기반 사용 또는 미사용 문구가 확인되지 않습니다.",
    }[platform_usage]
    ai_relevance = "medium" if explicit_usage and model.ai_relevance == "low" else model.ai_relevance
    remediation_blockers = []
    if model.network_scope not in {"internal_or_connected", "hybrid"}:
        remediation_blockers.append("network")
    if model.model_fit != "platform_llm_or_rag":
        remediation_blockers.append("model")
    remediation_covers_all = bool(remediation_blockers) and set(remediation_blockers).issubset(
        set(model.remediation_targets)
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
        conclusion = "공통기반 사용은 명시되어 있으나 기본조건 중 불충족 또는 미확인 항목이 있습니다."
    elif eligibility == "eligible":
        code, grade, fit, action = "2", "B", "high", "contact"
        score = max(70, min(94, model.priority_score))
        conclusion = "세 기본조건은 충족하지만 공통기반 활용이 명시되지 않았거나 미사용으로 확인됩니다."
    elif (
        model.task_scope in {"government", "delegated_government"}
        and model.remediation_feasibility == "feasible"
        and remediation_covers_all
    ):
        code, grade, fit, action = "3", "C", "partial", "contact"
        score = max(65, min(89, model.priority_score))
        conclusion = "국가사무 조건을 충족하며 망 또는 모델 변경으로 공통기반 전환을 검토할 수 있습니다."
    else:
        code, grade, fit, action = "5", "E", "low", "no_action"
        score = min(39, model.priority_score)
        conclusion = "AI 사업이지만 기본조건을 충족하지 못하거나 전환 가능성이 확인되지 않고 공통기반 사용도 확인되지 않습니다."

    questions = list(model.check_questions)
    if code == "2":
        questions.append("범정부 인공지능 공통기반의 LLM API 또는 RAG를 적용·연계할 계획인지 확인 필요")
    if model.network_scope == "unclear":
        questions.append("서비스와 데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계되는지 확인 필요")
    if model.task_scope == "unclear":
        questions.append("해당 업무가 중앙·지방정부의 행정사무 또는 공공기관이 위탁받은 국가사무인지 확인 필요")
    if model.model_fit == "unclear":
        questions.append("공통기반 제공 LLM·RAG로 처리 가능한지, 독자 모델 또는 풀파인튜닝이 필요한지 확인 필요")
    if model.model_fit == "custom_model_or_full_finetuning":
        questions.append("독자 모델·풀파인튜닝 필요 범위와 공통기반 별도 협의 절차를 확인 필요")
    if code == "3":
        questions.append("운영망 연계 또는 공통기반 제공모델 전환을 본공고 전에 반영할 수 있는지 확인 필요")
    if code == "4":
        questions.append("공통기반 사용 계획과 실제 망·국가사무·모델 기본조건이 일치하는지 본공고 전에 확인 필요")
    questions = list(dict.fromkeys(questions))

    caveats = list(dict.fromkeys([
        *model.caveats,
        "기관 유형만으로 국가사무 또는 위탁 국가사무 여부를 추정하지 않았습니다.",
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
    issue_labels = []
    if model.network_scope not in {"internal_or_connected", "hybrid"}:
        issue_labels.append("운영망·데이터 연계")
    if model.task_scope not in {"government", "delegated_government"}:
        issue_labels.append("국가사무 범위")
    if model.model_fit != "platform_llm_or_rag":
        issue_labels.append("제공모델·RAG 적용")
    issue_text = "·".join(issue_labels) or "세 기본조건"
    guidance = ""
    if code == "2":
        guidance = (
            "본 사업은 공통기반 기본조건을 충족할 가능성이 확인되나 활용 계획이 문서에 반영되지 않았습니다. "
            "본공고 제안요청서에 범정부 인공지능 공통기반의 LLM·RAG 활용 범위, 연계 방식과 대상 데이터·업무를 명시해 주시기 바랍니다."
        )
    elif code == "3":
        guidance = (
            f"본 사업은 국가사무에 해당하나 현재 {issue_text} 조건의 조정이 필요합니다. "
            "본공고 전에 운영망 연계 또는 제공모델 전환 가능성을 검토하고, 가능한 경우 공통기반 활용 범위와 별도 협의사항을 제안요청서에 반영해 주시기 바랍니다."
        )
    elif code == "4":
        guidance = (
            f"공통기반 활용이 명시되어 있으나 {issue_text} 조건이 이용요건과 맞지 않거나 확인되지 않습니다. "
            "본공고 전에 이용대상 업무, 망·데이터 처리 구조와 제공모델 적용 범위를 재확인하고 충족 근거 또는 별도 협의사항을 명시해 주시기 바랍니다."
        )
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
        "summary": f"{conclusion} {model.summary}",
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
    deep_cache_fingerprint = "mock-deep-eligibility-v2"

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
                        raw_model = _drop_blank_evidence(raw_model)
                    model = schema.model_validate(raw_model)
                    if isinstance(model, DeepAnalysis):
                        model = _ground_deep_evidence(model, context)
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
            f"{self.simple_model_name}|{self.simple_prompt}".encode("utf-8")
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
            return OpenAIChatClient(self.simple_endpoint).call(self.simple_prompt, scoped, SimpleAnalysis)
        except (LLMRateLimitExceeded, RuntimeError) as exc:
            # 무료 2차 모델의 일시 한도가 전체 새벽 배치를 중단시키지 않게 한다.
            # 이미 규칙 후보인 건은 낮은 점수여도 심층 대기 대상으로 보수적으로 유지한다.
            logger.warning("2차 LLM 실패로 보수적 규칙 판정을 사용합니다: %s", exc)
            result, _usage_ignored = self.mock.simple(scoped, rule)
            if rule.score > 0 and not rule.skip:
                result = result.model_copy(update={
                    "ai_relevance": "high" if rule.score >= 55 else "medium",
                    "needs_deep_review": True,
                    "reason": f"2차 LLM 한도·장애로 보수적 규칙 판정 적용: {rule.reason}",
                    "confidence": min(result.confidence, 0.6),
                })
            return result, _usage("rule-fallback-after-stage2-error", "local", fallback=True)

    def deep(self, context: str, simple: SimpleAnalysis, rule: FilterResult) -> tuple[DeepAnalysis, Usage]:
        scoped = _truncate_context(context, self.settings.stage3_max_input_chars)
        acquired = self.deep_semaphore.acquire(timeout=self.settings.stage3_timeout_seconds)
        if not acquired:
            raise RuntimeError("3차 분석 동시성 대기시간을 초과했습니다.")
        try:
            if self.primary_endpoint.provider == "mock":
                return self.mock.deep(scoped, simple, rule)
            try:
                return self._call_deep_endpoint(self.primary_endpoint, scoped, rule)
            except RuntimeError as primary_error:
                if self.fallback_endpoint.provider == "mock":
                    raise primary_error
                logger.warning("3차 주 공급자 실패로 fallback을 사용합니다: %s", primary_error)
                result, usage = self._call_deep_endpoint(self.fallback_endpoint, scoped, rule)
                usage["fallback_used"] = True
                usage["primary_error"] = str(primary_error)[:500]
                return result, usage
        finally:
            self.deep_semaphore.release()

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
    return f"사업명: {notice.title}\n기관: {notice.agency_name}\n예산: {notice.budget_amount or '미상'}\n첨부: {filenames}\n\n추출 본문:\n{text}"


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


def record_non_ai_screen(db: Session, notice: Notice, rule: FilterResult) -> bool:
    """Persist an inexpensive category-6 result for clear rule-level non-AI notices."""
    context = notice_context(notice)
    gate_hash = _input_hash(context, "deep_ai", CURRENT_CRITERIA_VERSION)
    existing = next((
        run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
        if run.run_type == "deep_ai" and run.status == "skipped"
        and run.model_name == "rule-gate" and run.input_hash == gate_hash
        and is_current_deep_result(run.result_json)
    ), None)
    if existing:
        return False
    result = DeepAnalysis(
        classification_code="6",
        final_grade="E",
        ai_relevance="low",
        common_platform_fit="low",
        usage_mentioned="unclear",
        network_scope="unclear",
        network_reason="비AI 규칙 분류로 망 조건 심층검증 대상이 아닙니다.",
        network_evidence=[],
        task_scope="unclear",
        task_scope_reason="비AI 규칙 분류로 국가사무 조건 심층검증 대상이 아닙니다.",
        task_scope_evidence=[],
        model_fit="unclear",
        model_fit_reason="AI 모델 요구가 확인되지 않았습니다.",
        model_fit_evidence=[],
        platform_usage="not_mentioned",
        platform_usage_reason="공통기반 사용 문구가 확인되지 않았습니다.",
        platform_usage_evidence=[],
        remediation_feasibility="unclear",
        remediation_targets=[],
        remediation_reason="비AI 사업으로 망·모델 전환 검토 대상이 아닙니다.",
        remediation_evidence=[],
        eligibility="uncertain",
        possible_common_platform_functions=[],
        summary="제목과 사업 문서에서 직접적인 AI 구축·개선 근거를 찾지 못해 비AI 사업으로 분류했습니다.",
        evidence=[],
        check_questions=[],
        recommended_action="no_action",
        priority_score=0,
        confidence=0.8,
        caveats=["규칙 기반 분류이며 AI 기능이 문서에 누락된 경우 수동 재검토할 수 있습니다."],
        guidance_message="",
    )
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
            return (DeepAnalysis if deep else SimpleAnalysis).model_validate_json(cached.result_json)

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
        elif not force and _stage3_used_today(db) >= settings.stage3_daily_limit:
            result = _quota_result(simple, rule)
            deep_usage = _usage("daily-quota-guard", "local")
            deep_status = "skipped"
        else:
            result, deep_usage = analyzer.deep(context, simple, rule)
            result = preserve_deep_ai_scope(result, simple)
            result = enforce_common_platform_gates(result, context)
            deep_status = "success"

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
