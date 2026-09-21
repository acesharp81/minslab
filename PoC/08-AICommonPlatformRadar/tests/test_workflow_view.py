import json

from app.models import ActionItem, AnalysisRun, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.workflow_view import (
    current_classification_run, finding_details, g2b_opinion_url, g2b_registration_no, guidance_sections,
    notice_contact, opinion_tracking, workflow_summary,
)


def _result(code="2"):
    return {
        "criteria_version": CURRENT_CRITERIA_VERSION,
        "classification_code": code,
        "network_scope": "internal_or_connected",
        "task_scope": "government",
        "model_fit": "platform_llm_or_rag",
        "platform_usage": "not_mentioned",
        "remediation_feasibility": "not_needed",
        "guidance_message": "공통기반 활용 범위와 연계 방식을 반영해 주시기 바랍니다.",
    }


def test_prenotice_opinion_flow_uses_search_route_and_exposes_registration_number():
    notice = Notice(
        stage="prenotice", notice_no="fallback", agency_name="기관", title="AI 사업",
        raw_payload_json=json.dumps({"bfSpecRgstNo": "R26BD00123456"}),
    )

    assert g2b_opinion_url(notice) == "https://www.g2b.go.kr/"
    assert g2b_registration_no(notice) == "R26BD00123456"


def test_guidance_message_is_split_into_visual_sections():
    sections = guidance_sections(
        "[법적 근거]\n- 제27조제2항\n\n[확인 사항]\n- 업무망 연계 여부\n- 모델 적용 범위"
    )

    assert sections == [
        {"title": "법적 근거", "entries": ["제27조제2항"]},
        {"title": "확인 사항", "entries": ["업무망 연계 여부", "모델 적용 범위"]},
    ]


def test_human_guidance_message_is_split_by_purpose():
    sections = guidance_sections(
        "안녕하세요. 의견드립니다.\n\n현재 문서상으로는 업무망입니다.\n\n"
        "공통기반으로 변경하면 활용할 수 있습니다.\n\n검토 후 회신 바랍니다.\n\n관련 법적 근거입니다."
    )

    assert [section["title"] for section in sections] == [
        "의견 요지", "현재 확인된 내용", "보완·확인 시 활용 가능", "검토 요청", "관련 법적 근거",
    ]


def test_bid_notice_contact_comes_from_public_raw_payload():
    notice = Notice(
        stage="bid_notice", notice_no="1", agency_name="기관", title="AI 사업",
        raw_payload_json=json.dumps({"ntceInsttOfclNm": "홍길동", "ntceInsttOfclTelNo": "02-123-4567"}),
    )

    assert notice_contact(notice) == {
        "name": "홍길동", "phone": "02-123-4567", "tel_url": "tel:021234567", "available": True,
    }


def test_contacted_prenotice_without_cache_needs_reply_check():
    notice = Notice(stage="prenotice", notice_no="1", agency_name="기관", title="AI 사업")
    notice.action = ActionItem(status="contacted")

    assert opinion_tracking(notice)["status"] == "not_checked"


def test_category_two_exposes_problem_and_required_action():
    findings = finding_details(_result("2"))

    assert any(item["gate"] == "공통기반 활용" for item in findings)
    assert any("사전규격" in item["action"] for item in findings)


def test_optional_usage_finding_requests_priority_review_instead_of_missing_use():
    result = _result("2")
    result["platform_usage_evidence"] = [{
        "quote": "기존 유휴장비 활용, 범정부 AI 플랫폼 활용, 경량화 모델 활용 등 인프라 구성 방안을 제시",
        "section": "요구사항", "interpretation": "선택 가능한 방안",
    }]

    findings = finding_details(result)
    usage = next(item for item in findings if item["gate"] == "공통기반 활용")

    assert "여러 인프라 대안 중 하나" in usage["problem"]
    assert "우선 검토" in usage["problem"]
    assert "미채택 사유" in usage["action"]


def test_valid_classification_survives_later_failed_retry():
    notice = Notice(stage="bid", notice_no="1", agency_name="기관", title="AI 사업")
    success = AnalysisRun(
        id=10, run_type="deep_ai", model_name="model", input_hash="a" * 64,
        status="success", result_json=json.dumps(_result("2"), ensure_ascii=False),
    )
    failure = AnalysisRun(
        id=11, run_type="deep_ai", model_name="retry", input_hash="b" * 64,
        status="failed", result_json="{}", error_message="temporary",
    )
    notice.analysis_runs.extend([success, failure])

    assert current_classification_run(notice) is success
    summary = workflow_summary(notice)
    assert summary["classification_code"] == "2"
    assert summary["action_required"] is True


def test_newer_successful_simple_result_invalidates_old_classification():
    notice = Notice(stage="bid", notice_no="2", agency_name="기관", title="AI 교육 사업")
    old = AnalysisRun(
        id=20, run_type="deep_ai", model_name="rule-gate", input_hash="a" * 64,
        status="skipped", result_json=json.dumps(_result("6"), ensure_ascii=False),
    )
    simple = AnalysisRun(
        id=21, run_type="simple_ai", model_name="command-a-plus-05-2026",
        input_hash="b" * 64, status="success",
        result_json=json.dumps({"ai_relevance": "medium", "needs_deep_review": True}),
    )
    notice.analysis_runs.extend([old, simple])

    assert current_classification_run(notice) is None
