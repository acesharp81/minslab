import json

from app.models import AnalysisRun, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.workflow_view import (
    current_classification_run, finding_details, g2b_opinion_url, workflow_summary,
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


def test_prenotice_opinion_url_uses_public_registration_number():
    notice = Notice(
        stage="prenotice", notice_no="fallback", agency_name="기관", title="AI 사업",
        raw_payload_json=json.dumps({"bfSpecRgstNo": "R26BD00123456"}),
    )

    assert g2b_opinion_url(notice) == (
        "https://www.g2b.go.kr/link/PNPE027_01/single/?bfSpecRgstNo=R26BD00123456"
    )


def test_category_two_exposes_problem_and_required_action():
    findings = finding_details(_result("2"))

    assert any(item["gate"] == "공통기반 활용" for item in findings)
    assert any("사전규격" in item["action"] for item in findings)


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
