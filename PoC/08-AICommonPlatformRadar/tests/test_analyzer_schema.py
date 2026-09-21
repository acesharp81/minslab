import httpx
import pytest
from pydantic import ValidationError

from app.schemas import DeepAnalysis, Evidence, SimpleAnalysis
from app.services.analyzer import (
    OpenAIChatClient,
    _downgrade_invalid_deep_gate_values,
    _ground_simple_evidence,
    enforce_common_platform_gates,
    enforce_explicit_ai_scope,
    merge_simple_and_gate_evidence,
    validate_grounded,
)


def test_stage2_normalized_quote_is_replaced_with_literal_source_line():
    model = SimpleAnalysis(
        ai_relevance="high",
        needs_deep_review=True,
        reason="AI 사업",
        evidence=[Evidence(quote="생성형 AI 기반 상담 서비스", section="과업", interpretation="AI 기능")],
        confidence=0.9,
    )
    source = "사업명: 생성형  AI 기반 상담 서비스\n추출 본문:\n세부 과업"

    grounded = _ground_simple_evidence(model, source)

    assert grounded.evidence
    assert grounded.evidence[0].quote in source
    assert validate_grounded(grounded, source) == grounded


def test_invalid_deep_gate_enum_is_downgraded_to_unclear():
    payload = valid_payload()
    payload.update({
        "task_scope": "high",
        "task_scope_reason": "국가사무라고 판단",
        "task_scope_evidence": [{"quote": "행정안전부", "section": "기관", "interpretation": "발주기관"}],
    })

    cleaned = _downgrade_invalid_deep_gate_values(payload)

    assert cleaned["task_scope"] == "unclear"
    assert cleaned["task_scope_evidence"] == []
    assert "확인 필요" in cleaned["task_scope_reason"]


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


def test_final_evidence_keeps_stage2_ai_basis_and_stage3_gate_quotes():
    simple = SimpleAnalysis(
        ai_relevance="high", needs_deep_review=True, reason="AI 사업",
        evidence=[Evidence(quote="AI 민원 상담 서비스를 구축한다", section="사업 개요", interpretation="AI 사업 판단")],
        confidence=0.9,
    )
    payload = valid_payload()
    payload.update({
        "network_scope": "internal_or_connected",
        "network_evidence": [{"quote": "행정망에서 서비스를 운영한다", "section": "시스템 구성", "interpretation": "망 조건"}],
    })
    deep = DeepAnalysis.model_validate(payload)

    enriched = merge_simple_and_gate_evidence(deep, simple)
    quotes = [item.quote for item in enriched.evidence]

    assert "AI 민원 상담 서비스를 구축한다" in quotes
    assert "행정망에서 서비스를 운영한다" in quotes


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
    assert guarded.classification_code == "3"
    assert guarded.recommended_action == "contact"
    assert "불충족으로 단정하지 않고" in guarded.summary
    assert guarded.eligibility == "uncertain"
    assert any("국가사무" in question for question in guarded.check_questions)

    rerun = enforce_common_platform_gates(guarded, source)
    assert rerun.summary.count("공개 문서의 미확인 항목은") == 1


@pytest.mark.parametrize("agency", [
    "행정안전부",
    "문화체육관광부 국립민속박물관",
    "서울특별시",
    "경기도 수원시",
    "수원시",
    "강남구",
    "부산광역시교육청",
])
def test_central_or_local_government_buyer_is_government_work(agency):
    source = f"기관: {agency}\n\n추출 본문:\n업무망에서 질의응답 서비스를 구축한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "government"
    assert guarded.classification_code == "2"
    assert guarded.task_scope_evidence[0].section == "발주기관"
    assert not any("국가사무" in question for question in guarded.check_questions)


def test_procurement_office_uses_document_governing_agency():
    source = (
        "기관: 조달청 서울지방조달청\n"
        "수요기관: 경기도 안양시\n공고기관: 조달청 서울지방조달청\n\n추출 본문:\n"
        "| 주관기관 | 경기도 안양시 AI정책과 |\n"
        "업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "government"
    assert guarded.classification_code == "2"
    assert guarded.task_scope_evidence[0].section == "사업문서"
    assert "조달 대행기관" in guarded.task_scope_reason


def test_procurement_office_without_real_buyer_is_not_government_evidence():
    source = (
        "기관: 조달청 서울지방조달청\n공고기관: 조달청 서울지방조달청\n\n추출 본문:\n"
        "업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    ).model_copy(update={
        "task_scope_evidence": [Evidence(
            quote="조달청 서울지방조달청", section="공고기관", interpretation="정부기관으로 오인한 근거",
        )],
    })

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "unclear"
    assert guarded.classification_code == "3"
    assert "실제 발주·주관부서" in guarded.task_scope_reason


def test_public_institution_with_supervising_ministry_is_delegated_government_work():
    source = (
        "기관: 한국공공서비스원\n\n추출 본문:\n"
        "주무부처: 보건복지부\n업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "delegated_government"
    assert guarded.classification_code == "2"


def test_other_public_institution_without_government_relationship_is_non_government():
    source = "기관: 한국공공서비스원\n\n추출 본문:\n업무망에서 질의응답 서비스를 구축한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "non_government"
    assert guarded.eligibility == "ineligible"
    assert guarded.classification_code == "5"
    assert guarded.recommended_action == "no_action"


def test_public_institution_self_sponsored_work_is_internal_work():
    source = (
        "기관: 한국공공서비스원\n\n추출 본문:\n"
        "주관기관: 한국공공서비스원\n업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "public_institution_internal"
    assert guarded.classification_code == "5"
    assert "발주기관과 주관기관이 동일" in guarded.task_scope_evidence[0].interpretation


def test_public_institution_internal_evidence_overrides_wrong_government_enum():
    source = (
        "사업명: 한난형 AI 기반 Agent 및 인프라 고도화 용역\n"
        "기관: 한국지역난방공사\n\n추출 본문:\n"
        "한난형 AI는 사무·행정 편의성 향상에 기여했다.\n"
        "사내 데이터베이스 검색(RAG), 내부 레거시 시스템 연동(MCP)을 구축한다.\n"
        "업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="government",
        model_fit="platform_llm_or_rag",
    ).model_copy(update={
        "task_scope_reason": "공공기관 자체 업무용 시스템으로 기관 운영 업무임",
        "task_scope_evidence": [
            Evidence(quote="사내 데이터베이스 검색(RAG)", section="추진 배경", interpretation="기관 내부 업무"),
        ],
    })

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "public_institution_internal"
    assert guarded.eligibility == "ineligible"
    assert guarded.classification_code == "5"
    assert guarded.common_platform_fit == "low"
    assert guarded.recommended_action == "no_action"
    assert "공통기반 적합 사업" not in guarded.summary
    assert "2번(적합·미반영)" not in guarded.summary


@pytest.mark.parametrize("agency", ["한국지능정보사회진흥원(NIA)", "한국지역정보개발원(KLID)"])
def test_statutory_delegate_with_central_ministry_is_delegated_government(agency):
    source = (
        f"기관: {agency}\n\n추출 본문:\n"
        "주무부처: 행정안전부\n업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "delegated_government"
    assert guarded.classification_code == "2"


@pytest.mark.parametrize("agency", ["한국지능정보사회진흥원(NIA)", "한국지역정보개발원(KLID)"])
def test_statutory_delegate_government_relation_overrides_self_sponsor(agency):
    source = (
        f"기관: {agency}\n\n추출 본문:\n"
        f"주관기관: {agency}\n주무부처: 행정안전부\n"
        "업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="public_institution_internal",
        model_fit="platform_llm_or_rag",
    ).model_copy(update={
        "task_scope_evidence": [Evidence(
            quote=f"주관기관: {agency}", section="주관기관",
            interpretation="발주기관과 주관기관 동일",
        )],
    })

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "delegated_government"
    assert guarded.classification_code == "2"
    assert "법정 수탁기관" in guarded.task_scope_reason


def test_statutory_delegate_without_ministry_relationship_remains_unclear():
    source = (
        "기관: 한국지능정보사회진흥원(NIA)\n\n추출 본문:\n"
        "업무망에서 질의응답 서비스를 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.task_scope == "unclear"
    assert guarded.classification_code == "3"
    assert any("국가사무" in question for question in guarded.check_questions)


def test_unconnected_closed_network_is_contact_for_admin_network_linkage():
    source = "기관: 행정안전부\n\n추출 본문:\n별도 폐쇄망에서 질의응답 서비스를 구축한다"
    model = _gated_payload(
        source, network="unclear", task="unclear", model_fit="platform_llm_or_rag",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.network_scope == "other_closed_network"
    assert guarded.classification_code == "3"
    assert any("폐쇄망" in question and "행정망" in question for question in guarded.check_questions)


def test_full_finetuning_is_contact_for_public_model_substitution():
    source = (
        "기관: 행정안전부\n\n추출 본문:\n"
        "업무망 질의응답 기능을 풀파인튜닝 독자 모델로 구축한다"
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="unclear",
        model_fit="custom_model_or_full_finetuning",
    )

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.classification_code == "3"
    assert guarded.recommended_action == "contact"
    assert any("공개 파운데이션 모델" in question for question in guarded.check_questions)


def test_all_gates_without_usage_maps_to_b():
    source = "업무망에서 행정사무 질의응답 서비스를 제공한다"
    model = _gated_payload(
        source, network="internal_or_connected", task="government", model_fit="platform_llm_or_rag",
    )
    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)
    assert guarded.final_grade == "B"
    assert guarded.classification_code == "2"
    assert guarded.guidance_message
    assert "인공지능데이터행정법" in guarded.guidance_message
    assert "제27조제2항" in guarded.guidance_message
    assert "현재 문서상으로는" in guarded.guidance_message
    assert "공통기반 활용 계획은 확인되지 않습니다" in guarded.guidance_message
    assert "검토하시어" in guarded.guidance_message
    assert "회신해 주시기 바랍니다" in guarded.guidance_message
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


def test_optional_government_ai_platform_stays_category_two_with_priority_review():
    source = (
        "업무망에서 행정사무 질의응답을 제공한다. "
        "기존 유휴장비 활용, 범정부 AI 플랫폼 활용, 경량화 모델 활용 등 "
        "실현 가능한 인프라 구성 방안을 제시한다."
    )
    model = _gated_payload(
        source, network="internal_or_connected", task="government",
        model_fit="platform_llm_or_rag",
    ).model_copy(update={
        "platform_usage_evidence": [Evidence(
            quote="기존 유휴장비 활용, 범정부 AI 플랫폼 활용, 경량화 모델 활용 등 실현 가능한 인프라 구성 방안을 제시한다.",
            section="요구사항", interpretation="공통기반이 선택 대안으로 제시됨",
        )],
    })

    guarded = enforce_common_platform_gates(validate_grounded(model, source), source)

    assert guarded.classification_code == "2"
    assert guarded.platform_usage == "unclear"
    assert "선택적으로 제시" in guarded.platform_usage_reason
    assert "우선 검토" in guarded.summary
    assert any("다른 인프라 대안" in question for question in guarded.check_questions)


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
