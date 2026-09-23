from __future__ import annotations

from app.models import Notice
from app.schemas import OpinionSenderProfile
from app.services.opinion_guidance import build_opinion_guidance, opinion_template_type
from app.services.workflow_view import guidance_sections


def _profile():
    return OpinionSenderProfile(
        organization="행정안전부",
        responsibility="범정부 인공지능공통기반",
        name="홍길동",
        position="사무관",
        phone="044-123-4567",
    )


def test_anyang_plan_uses_planning_template_and_structured_facts():
    notice = Notice(
        stage="prenotice", notice_no="R26BD00275090", agency_name="경기도 안양시",
        title="안양시 인공지능 기본 및 종합계획 수립 용역",
    )
    result = {
        "task_scope": "government", "network_scope": "unclear", "model_fit": "unclear",
        "possible_common_platform_functions": [],
    }

    message = build_opinion_guidance(notice, result, _profile())

    assert opinion_template_type(notice) == "planning"
    assert message.startswith(
        "안녕하세요. 행정안전부 '범정부 인공지능공통기반'을 담당하는 홍길동 사무관 (044-123-4567)입니다."
    )
    assert "AI 서비스 도입·구축 방향을 수립하는 계획·ISP·연구용역" in message
    assert "- AI 서비스 개요: 안양시의 중장기 인공지능(AI)·데이터 발전 방향 마련" in message
    assert "- 사용자: 지방정부(국가사무)" in message
    assert "- 사용환경: 확인안됨" in message
    assert "- 사용모델: 확인안됨" in message
    assert "적정성이 확인되면 향후 사업이 '범정부 인공지능 공통기반'을 활용할 수 있도록 계획에 반영" in message
    assert "[분석 내용]\n- AI 서비스" in message
    assert "판단\n- 적정성이" in message
    assert "\n\n-" not in message
    assert "053-230-1938" in message and "gov-ai@nia.or.kr" in message
    assert [section["title"] for section in guidance_sections(message)] == [
        "인사·의견 요지", "분석 내용", "검토 요청",
    ]


def test_actual_build_uses_construction_template():
    notice = Notice(
        stage="prenotice", notice_no="BUILD-1", agency_name="행정안전부",
        title="생성형 AI 업무지원 서비스 구축 사업",
    )
    result = {
        "task_scope": "government", "network_scope": "internal_or_connected",
        "model_fit": "platform_llm_or_rag", "possible_common_platform_functions": ["RAG", "질의응답"],
    }

    message = build_opinion_guidance(notice, result, _profile())

    assert opinion_template_type(notice) == "construction"
    assert "AI 서비스를 도입·구축하는 사업" in message
    assert "- 사용자: 중앙정부·소속기관(국가사무)" in message
    assert "- 사용환경: 내부(행정·업무)망 또는 연계망" in message
    assert "- 사용모델: 공통기반 제공 모델·RAG 적용 가능" in message
    assert "시스템 구성, 적용 기능 및 제안요청서 반영 방향 검토" in message


def test_review_request_adds_condition_specific_sentences_for_operator_call():
    notice = Notice(
        stage="bid_notice", notice_no="BID-CALL-1", agency_name="행정안전부",
        title="생성형 AI 업무지원 서비스 구축 사업",
    )
    result = {
        "task_scope": "government", "network_scope": "unclear",
        "model_fit": "custom_model_or_full_finetuning", "platform_usage": "not_mentioned",
    }

    message = build_opinion_guidance(notice, result, _profile())

    assert "공개된 본공고 「생성형 AI 업무지원 서비스 구축 사업」" in message
    assert "AI 서비스를 도입·구축하는 사업으로 판단됩니다" in message
    assert "공개된 사전규격" not in message
    assert "서류상 독자모델 또는 풀파인튜닝이 요구" in message
    assert "EXAONE, Solar Open, Gemma 계열" in message
    assert "서류상 어떤 네트워크 환경에서 사용되는지 확인되지 않습니다" in message
    assert "API 방식으로 호출할 수 있는지" in message
    assert "다른 인프라 대안보다 우선 검토" in message
    assert message.count("[검토 요청]") == 1


def test_optional_platform_usage_adds_priority_review_to_existing_template():
    notice = Notice(
        stage="prenotice", notice_no="R26BD00276148", agency_name="우정정보관리원",
        title="우체국금융시스템 프로그램 유지·운영관리 용역",
    )
    result = {
        "task_scope": "government", "network_scope": "internal_or_connected",
        "model_fit": "platform_llm_or_rag", "platform_usage": "not_mentioned",
        "platform_usage_evidence": [{
            "quote": "기존 유휴장비 활용, 범정부 AI 플랫폼 활용, 경량화 모델 활용 등 실현 가능한 인프라 구성 방안을 제시",
            "section": "DE-MGR-007", "interpretation": "선택 가능한 인프라 방안",
        }],
    }

    message = build_opinion_guidance(notice, result, _profile())

    assert "공통기반 사용 여부: 선택적 활용 명시" in message
    assert "다른 대안을 선택하기 전에 공통기반 적용 가능성을 우선 검토" in message
    assert "적용이 곤란한 경우 그 사유와 대체 방안 선정 근거" in message
    assert message.count("[검토 요청]") == 1


def test_procurement_notice_uses_real_local_demand_in_user_label():
    notice = Notice(
        stage="prenotice", notice_no="PROCUREMENT-1", agency_name="조달청 서울지방조달청",
        title="AI 업무지원 서비스 구축 사업",
        raw_payload_json='{"orderInsttNm":"조달청 서울지방조달청","rlDminsttNm":"경기도 안양시"}',
    )
    message = build_opinion_guidance(notice, {
        "task_scope": "government", "network_scope": "unclear", "model_fit": "unclear",
        "task_scope_evidence": [],
    }, _profile())

    assert "- 사용자: 지방정부(국가사무)" in message


def test_custom_planning_template_replaces_only_supported_tokens():
    notice = Notice(
        stage="prenotice", notice_no="CUSTOM-1", agency_name="경기도 안양시",
        title="안양시 인공지능 기본 및 종합계획 수립 용역",
    )
    profile = _profile().model_copy(update={
        "planning_template": "{greeting}\n{overview}|{user}|{network}|{model}",
    })

    message = build_opinion_guidance(notice, {
        "task_scope": "government", "network_scope": "unclear", "model_fit": "unclear",
    }, profile)

    assert "홍길동 사무관" in message
    assert "안양시의 중장기 인공지능(AI)·데이터 발전 방향 마련" in message
    assert "지방정부(국가사무)|확인안됨|확인안됨" in message
