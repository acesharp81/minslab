import httpx
import pytest
from pydantic import ValidationError

from app.schemas import DeepAnalysis, SimpleAnalysis
from app.services.analyzer import (
    OpenAIChatClient,
    enforce_common_platform_gates,
    enforce_explicit_ai_scope,
    validate_grounded,
)


def valid_payload():
    return {
        "classification_code": "5",
        "final_grade": "B", "ai_relevance": "high", "common_platform_fit": "high",
        "usage_mentioned": "unclear", "possible_common_platform_functions": ["LLM API"],
        "network_scope": "unclear", "network_reason": "망 구성 확인 필요", "network_evidence": [],
        "task_scope": "unclear", "task_scope_reason": "국가사무 확인 필요", "task_scope_evidence": [],
        "model_fit": "unclear", "model_fit_reason": "모델 확인 필요", "model_fit_evidence": [],
        "platform_usage": "not_mentioned", "platform_usage_reason": "사용 문구 없음",
        "platform_usage_evidence": [],
        "remediation_feasibility": "unclear", "remediation_targets": [],
        "remediation_reason": "변경 가능성 확인 필요", "remediation_evidence": [],
        "eligibility": "uncertain",
        "summary": "활용 여부 확인 필요", "evidence": [{"quote": "생성형 AI 구축", "section": "3장", "interpretation": "AI 사업"}],
        "check_questions": ["공통기반 검토 여부 확인 필요"], "recommended_action": "contact",
        "priority_score": 88, "confidence": 0.8, "caveats": [],
    }


def test_valid_deep_schema_and_grounding():
    model = DeepAnalysis.model_validate(valid_payload())
    assert validate_grounded(model, "과업은 생성형 AI 구축을 포함한다") == model


def test_llm_numeric_classification_code_is_normalized():
    payload = valid_payload()
    payload["classification_code"] = 5
    assert DeepAnalysis.model_validate(payload).classification_code == "5"


def test_llm_excess_evidence_is_trimmed_to_schema_limit():
    quote = {"quote": "생성형 AI 구축", "section": "과업", "interpretation": "AI 기능"}
    simple = SimpleAnalysis.model_validate({
        "ai_relevance": "high", "needs_deep_review": True, "reason": "AI 사업",
        "evidence": [quote] * 21, "confidence": 0.9,
    })
    payload = valid_payload()
    payload["network_evidence"] = [quote] * 21
    deep = DeepAnalysis.model_validate(payload)

    assert len(simple.evidence) == 10
    assert len(deep.network_evidence) == 10


def test_actionable_grade_requires_evidence():
    payload = valid_payload()
    payload["evidence"] = []
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_uncertain_grade_requires_questions():
    payload = valid_payload()
    payload["check_questions"] = []
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_priority_range():
    payload = valid_payload()
    payload["priority_score"] = 101
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_fabricated_quote_is_rejected():
    model = DeepAnalysis.model_validate(valid_payload())
    with pytest.raises(ValueError):
        validate_grounded(model, "전혀 다른 원문")


def test_public_notice_metadata_is_valid_grounding_source():
    payload = valid_payload()
    payload["evidence"] = [{"quote": "생성형 AI 구축", "section": "사업명", "interpretation": "AI 사업"}]
    model = DeepAnalysis.model_validate(payload)
    assert validate_grounded(model, "사업명: 생성형 AI 구축\n추출 본문:\n세부 과업 확인") == model


def _gated_payload(source: str, *, network: str, task: str, model_fit: str):
    payload = valid_payload()
    payload.update({
        "evidence": [
            {"quote": "질의응답", "section": "기능", "interpretation": "AI 기능"}
        ],
        "network_scope": network,
        "network_reason": "망 조건 판정",
        "network_evidence": [] if network == "unclear" else [
            {"quote": "업무망", "section": "구성", "interpretation": "업무망에서 처리"}
        ],
        "task_scope": task,
        "task_scope_reason": "업무 범위 판정",
        "task_scope_evidence": [] if task == "unclear" else [
            {"quote": "행정사무", "section": "목적", "interpretation": "정부 행정사무"}
        ],
        "model_fit": model_fit,
        "model_fit_reason": "모델 적합성 판정",
        "model_fit_evidence": [] if model_fit == "unclear" else [
            {"quote": "질의응답", "section": "기능", "interpretation": "공통 LLM 기능"}
        ],
    })
    return DeepAnalysis.model_validate(payload)


def test_generic_rag_cannot_be_b_when_public_task_is_unclear():
    source = "업무망에서 질의응답 서비스를 제공한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.classification_code == "5"
    assert guarded.eligibility == "uncertain"
    assert any("국가사무" in question for question in guarded.check_questions)


def test_all_gates_without_usage_maps_to_b():
    source = "업무망에서 행정사무 질의응답 서비스를 제공한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.final_grade == "B"
    assert guarded.classification_code == "2"
    assert guarded.guidance_message
    assert guarded.eligibility == "eligible"
    assert guarded.usage_mentioned != "yes"


def test_rule_regrade_to_actionable_grade_promotes_gate_evidence():
    source = "업무망에서 행정사무 질의응답 서비스를 제공한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    ).model_copy(update={"final_grade": "E", "evidence": []})
    guarded = enforce_common_platform_gates(model, source)
    assert guarded.final_grade == "B"
    assert guarded.evidence


def test_all_gates_with_explicit_usage_maps_to_a():
    source = "업무망에서 행정사무 질의응답을 위해 범정부 인공지능 공통기반을 활용한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.final_grade == "A"
    assert guarded.classification_code == "1"
    assert guarded.usage_mentioned == "yes"


def test_usage_review_phrase_is_not_treated_as_actual_use():
    source = "업무망 행정사무 질의응답에서 범정부 인공지능 공통기반 활용 여부를 검토한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.classification_code == "2"
    assert guarded.platform_usage == "unclear"


def test_explicit_non_use_is_distinct_from_missing_phrase():
    source = "업무망 행정사무 질의응답에서 범정부 인공지능 공통기반을 사용하지 않는다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.classification_code == "2"
    assert guarded.platform_usage == "not_used"
    assert guarded.usage_mentioned == "no"


def test_public_institution_internal_work_maps_to_e():
    source = "업무망에서 공공기관 내부 행정사무 질의응답 서비스를 제공한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="public_institution_internal",
        model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.final_grade == "E"
    assert guarded.classification_code == "5"
    assert guarded.eligibility == "ineligible"


def test_custom_model_with_proven_switchability_maps_to_category_3():
    source = "업무망의 행정사무 질의응답에 독자 모델을 적용하되 제공 모델로 교체할 수 있다"
    base = _gated_payload(
        source, network="internal_or_connected", task="government",
        model_fit="custom_model_or_full_finetuning",
    )
    model = DeepAnalysis.model_validate({**base.model_dump(), **{
        "remediation_feasibility": "feasible",
        "remediation_targets": ["model"],
        "remediation_reason": "제공 모델 전환 가능",
        "remediation_evidence": [{"quote": "제공 모델로 교체할 수 있다", "section": "모델", "interpretation": "모델 변경 가능"}],
    }})
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.final_grade == "C"
    assert guarded.classification_code == "3"
    assert guarded.guidance_message


def test_explicit_usage_with_failed_public_task_maps_to_category_4():
    source = "업무망에서 공공기관 내부 행정사무 질의응답에 범정부 인공지능 공통기반을 활용한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="public_institution_internal",
        model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.classification_code == "4"
    assert guarded.recommended_action == "contact"
    assert guarded.guidance_message


def test_non_ai_maps_to_category_6():
    source = "업무망에서 행정사무 정보시스템을 구축한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="unclear",
    ).model_copy(update={"ai_relevance": "low", "final_grade": "E", "evidence": []})
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.classification_code == "6"
    assert guarded.priority_score == 0


def test_aam_without_explicit_ai_is_downgraded():
    model = SimpleAnalysis(
        ai_relevance="high",
        needs_deep_review=True,
        reason="AAM 첨단 사업",
        evidence=[{"quote": "AAM 리프트프롭", "section": "사업명", "interpretation": "첨단 기술"}],
        confidence=0.95,
    )
    guarded = enforce_explicit_ai_scope(model, "사업명: AAM 리프트프롭 풍동시험치구 제작")
    assert guarded.ai_relevance == "low"
    assert guarded.needs_deep_review is False
    assert guarded.evidence == []


def test_low_relevance_sample_without_ai_marker_is_not_sent_to_deep_review():
    model = SimpleAnalysis(
        ai_relevance="low",
        needs_deep_review=True,
        reason="고예산 정보화 용역 표본 검토",
        evidence=[],
        confidence=0.55,
    )
    guarded = enforce_explicit_ai_scope(model, "사업명: 노후 가상화 서버 교체 사업")
    assert guarded.ai_relevance == "low"
    assert guarded.needs_deep_review is False


def test_explicit_rag_evidence_keeps_ai_candidate():
    model = SimpleAnalysis(
        ai_relevance="high",
        needs_deep_review=True,
        reason="RAG 구축",
        evidence=[{"quote": "RAG 기반 검색", "section": "과업", "interpretation": "AI 기능"}],
        confidence=0.9,
    )
    assert enforce_explicit_ai_scope(model, "과업: RAG 기반 검색") == model


def test_rate_limit_retry_uses_long_backoff_without_header():
    response = httpx.Response(429, request=httpx.Request("POST", "https://example.test"))
    error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)
    assert OpenAIChatClient._retry_delay(error, 0) == 20.0
    assert OpenAIChatClient._retry_delay(error, 1) == 40.0


def test_rate_limit_retry_honors_retry_after_header():
    response = httpx.Response(
        429, headers={"retry-after": "75"}, request=httpx.Request("POST", "https://example.test")
    )
    error = httpx.HTTPStatusError("rate limited", request=response.request, response=response)
    assert OpenAIChatClient._retry_delay(error, 0) == 75.0
