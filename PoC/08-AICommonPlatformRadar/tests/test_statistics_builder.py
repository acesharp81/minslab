from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ActionItem, AnalysisRun, Attachment, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.ineligible_reasons import ineligible_detail_key, ineligible_reason_key
from app.services.statistics_builder import build_statistics


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _analysis(code: str, *, ai: str = "high", usage: str = "not_mentioned", **fields):
    result = {
        "criteria_version": CURRENT_CRITERIA_VERSION,
        "classification_code": code,
        "ai_relevance": ai,
        "network_scope": "internal_or_connected",
        "task_scope": "government",
        "service_scope": "target_build",
        "model_fit": "platform_llm_or_rag",
        "platform_usage": usage,
        "evidence": [{"quote": "AI 서비스"}] if ai != "low" else [],
        **fields,
    }
    return AnalysisRun(
        run_type="deep_ai", model_name="test", input_hash=(code * 64)[:64],
        status="success", result_json=json.dumps(result, ensure_ascii=False),
    )


def test_statistics_tracks_detection_action_and_verified_conversion(db: Session):
    now = datetime.now(timezone.utc)
    pre = Notice(
        stage="prenotice", notice_no="PRE-1", agency_name="행정안전부", title="AI 사전규격",
        posted_at=now - timedelta(days=3),
    )
    pre.analysis_runs.append(_analysis("2"))
    pre.action = ActionItem(status="completed_uses", contacted_at=now - timedelta(days=2))
    pre.attachments.append(Attachment(
        original_filename="제안요청서.pdf", source_url="sample://pre", parse_status="parsed",
    ))

    bid = Notice(
        stage="bid_notice", notice_no="BID-1", agency_name="행정안전부", title="AI 본공고",
        posted_at=now - timedelta(days=1), raw_payload_json=json.dumps({"bfSpecRgstNo": "PRE-1"}),
    )
    bid.analysis_runs.append(_analysis("1", usage="uses"))

    excluded = Notice(
        stage="bid_notice", notice_no="BID-2", agency_name="공공기관", title="AI 연수 운영",
        posted_at=now, raw_payload_json="{}",
    )
    excluded.analysis_runs.append(_analysis(
        "5", network_scope="external_complete", service_scope="target_build",
    ))

    non_ai = Notice(
        stage="bid_notice", notice_no="BID-3", agency_name="공공기관", title="청소 용역",
        posted_at=now, raw_payload_json="{}",
    )
    non_ai.analysis_runs.append(_analysis("6", ai="low"))
    db.add_all([pre, bid, excluded, non_ai])
    db.commit()

    stats = build_statistics(db)

    assert stats["overview"] == {
        "collected": 4, "analyzed": 4, "coverage_rate": 100.0,
        "ai": 3, "non_ai": 1, "non_ai_direct": 1, "out_of_scope": 0,
        "ai_rate": 75.0,
    }
    assert stats["platform"]["eligible_uses"] == 1
    assert stats["platform"]["eligible_not_used"] == 1
    assert stats["status"]["collected"] == 4
    assert stats["status"]["non_ai"] == 1
    assert stats["status"]["ai"] == 3
    assert stats["status"]["eligible"] == 2
    assert stats["status"]["eligible_uses"] == 2
    assert stats["status"]["ineligible"] == 1
    ineligible_reasons = stats["status"]["ineligible_reasons"]
    assert ineligible_reasons["total"] == 1
    assert {item["key"]: item["count"] for item in ineligible_reasons["items"]} == {
        "national_task": 0, "network_data": 1, "specialized_model": 0,
    }
    assert sum(item["percent"] for item in ineligible_reasons["items"]) == 100.0
    assert stats["status"]["collected"] == stats["status"]["non_ai"] + stats["status"]["ai"] + stats["status"]["pending"]
    assert stats["status"]["ai"] == stats["status"]["eligible"] + stats["status"]["review"] + stats["status"]["ineligible"]
    assert stats["achievements"]["unused_to_used"] == 1
    assert stats["actions"]["detected"] == 1
    assert stats["actions"]["reclassified_excluded"] == 0
    assert stats["actions"]["current_detected"] == 1
    assert stats["actions"]["contacted"] == 1
    assert stats["actions"]["completed"] == 1
    assert stats["actions"]["completed_uses"] == 1
    assert stats["actions"]["in_progress"] == 0
    assert stats["actions"]["converted"] == 1
    assert stats["actions"]["converted_eligible"] == 1
    assert stats["conversions"][0]["prenotice_no"] == "PRE-1"
    assert stats["conversions"][0]["bid_notice_no"] == "BID-1"
    reasons = {item["key"]: item["count"] for item in stats["reason_groups"]}
    assert stats["action_use_cases"][0]["title"] == "AI 사전규격"
    assert stats["action_use_cases"][0]["source_label"] == "조치 결과 이용 확인"
    details = {
        item["key"]: item["count"] for item in stats["status"]["ineligible_details"]["items"]
    }
    assert details["internet_only_service"] == 1
    assert stats["status"]["ineligible_details"]["items"][0]["priority_rank"] == 1
    assert reasons["network"] == 1
    assert reasons["service"] == 0


def test_conversion_before_recorded_contact_is_not_counted(db: Session):
    now = datetime.now(timezone.utc)
    pre = Notice(stage="prenotice", notice_no="PRE-OLD", agency_name="기관", title="AI 사전규격")
    pre.analysis_runs.append(_analysis("3"))
    pre.action = ActionItem(status="contacted", contacted_at=now)
    bid = Notice(
        stage="bid_notice", notice_no="BID-OLD", agency_name="기관", title="기존 AI 본공고",
        posted_at=now - timedelta(days=1), raw_payload_json=json.dumps({"bfSpecRgstNo": "PRE-OLD"}),
    )
    bid.analysis_runs.append(_analysis("1", usage="uses"))
    db.add_all([pre, bid])
    db.commit()

    assert build_statistics(db)["actions"]["converted"] == 0


def test_manual_ineligible_reason_overrides_analysis_reason(db: Session):
    notice = Notice(
        stage="bid_notice", notice_no="MANUAL-1", agency_name="기관", title="AI 사업",
        raw_payload_json=json.dumps({"_poc08_manual_ineligible_reason": "national_task"}),
    )
    notice.analysis_runs.append(_analysis("3", network_scope="external_complete"))
    notice.action = ActionItem(status="completed_ineligible")
    db.add(notice)
    db.commit()

    items = build_statistics(db)["status"]["ineligible_reasons"]["items"]

    assert {item["key"]: item["count"] for item in items} == {
        "national_task": 1, "network_data": 0, "specialized_model": 0,
    }


def test_non_ai_feedback_is_excluded_from_all_ineligible_statistics(db: Session):
    notice = Notice(
        stage="prenotice", notice_no="NON-AI-FEEDBACK", agency_name="기관", title="AI 여부 확인 사업",
        raw_payload_json=json.dumps({"_poc08_manual_ineligible_reason": "non_ai"}),
    )
    notice.analysis_runs.extend([_analysis("3"), _analysis("6", ai="low")])
    notice.action = ActionItem(status="completed_non_ai")
    db.add(notice)
    db.commit()

    stats = build_statistics(db)

    assert stats["status"]["non_ai"] == 1
    assert stats["status"]["ineligible"] == 0
    assert stats["status"]["ineligible_reasons"]["total"] == 0
    assert stats["achievements"]["review_to_ineligible"] == 0
    assert stats["actions"]["completed_non_ai"] == 1
    assert stats["actions"]["completed_ineligible"] == 0


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"model_fit_reason": "업무 데이터로 풀파인튜닝 모델 학습 필요"}, "model_training_required"),
        ({"model_fit_reason": "법률 분야 업무 특화모델 필요"}, "domain_specialized_model"),
        ({"service_scope_reason": "영상 분석 기능은 현재 지원하지 못함"}, "unsupported_service_capability"),
        ({"network_scope": "other_closed_network", "network_reason": "망분리 환경이라 연계 불가"}, "isolated_network_no_link"),
        ({"network_scope": "other_closed_network", "network_reason": "민감정보 데이터 반출 제한"}, "data_transfer_restricted"),
    ],
)
def test_ineligible_detail_taxonomy_distinguishes_expansion_priorities(fields, expected):
    notice = Notice(stage="bid_notice", notice_no=f"DETAIL-{expected}", title="AI 사업")
    result = {
        "task_scope": "government",
        "network_scope": "internal_or_connected",
        "model_fit": "custom_model_or_full_finetuning",
        **fields,
    }

    assert ineligible_detail_key(notice, result) == expected


def test_detail_taxonomy_does_not_rewrite_legacy_parent_metric():
    notice = Notice(stage="bid_notice", notice_no="DETAIL-STABLE", title="AI 사업")
    result = {
        "task_scope": "unclear",
        "network_scope": "internal_or_connected",
        "model_fit": "custom_model_or_full_finetuning",
        "model_fit_reason": "업무 데이터로 풀파인튜닝 모델 학습 필요",
    }

    assert ineligible_reason_key(notice, result) == "specialized_model"
    assert ineligible_detail_key(notice, result) == "model_training_required"


def test_non_target_service_is_not_counted_as_a_model_problem():
    notice = Notice(stage="bid_notice", notice_no="SERVICE-SCOPE", title="일반 감리 용역")
    result = {
        "task_scope": "unclear", "network_scope": "unclear",
        "service_scope": "non_target", "model_fit": "unclear",
    }

    assert ineligible_reason_key(notice, result) == "service_scope"
    assert ineligible_detail_key(notice, result) == "service_scope_outside_target"


def test_non_target_service_is_counted_under_non_ai_service_not_ai_ineligible(db: Session):
    notice = Notice(stage="bid_notice", notice_no="SCOPE-OUT", title="생성형 AI 교육 운영")
    notice.analysis_runs.append(_analysis(
        "5", ai="medium", service_scope="non_target", network_scope="unclear",
    ))
    db.add(notice)
    db.commit()

    stats = build_statistics(db)

    assert stats["status"]["non_ai_service"] == 1
    assert stats["status"]["out_of_scope"] == 1
    assert stats["status"]["ai"] == 0
    assert stats["status"]["ineligible"] == 0


def test_review_notices_count_each_unresolved_reason(db: Session):
    cases = [
        ("MULTI", {"network_scope": "unclear", "task_scope": "unclear", "model_fit": "unclear"}),
        ("NETWORK", {"network_scope": "unclear"}),
        ("TASK", {"task_scope": "unclear"}),
        ("MODEL", {"model_fit": "custom_model_or_full_finetuning"}),
        ("USAGE", {}),
    ]
    for no, fields in cases:
        notice = Notice(stage="prenotice", notice_no=f"REVIEW-{no}", title=f"검토 {no}")
        notice.analysis_runs.append(_analysis("3", **fields))
        db.add(notice)
    db.commit()

    reasons = build_statistics(db)["status"]["review_reasons"]

    assert reasons["total"] == 6
    assert reasons["notice_total"] == 5
    assert {item["key"]: item["count"] for item in reasons["items"]} == {
        "network_data": 2, "national_task": 2, "model": 2,
    }
    assert sum(item["percent"] for item in reasons["items"]) == 100.0


def test_reason_percent_rounding_never_assigns_percent_to_zero_count(db: Session):
    for index in range(35):
        notice = Notice(stage="prenotice", notice_no=f"ROUND-{index}", title="검토 반올림")
        fields = {"network_scope": "unclear"} if index < 29 else {
            "model_fit": "custom_model_or_full_finetuning",
        }
        notice.analysis_runs.append(_analysis("3", **fields))
        db.add(notice)
    db.commit()

    items = build_statistics(db)["status"]["review_reasons"]["items"]

    assert sum(item["percent"] for item in items) == 100.0
    assert all(item["percent"] == 0 for item in items if item["count"] == 0)


def test_review_nine_notices_show_seventeen_overlapping_reasons(db: Session):
    for index in range(9):
        notice = Notice(stage="prenotice", notice_no=f"OVERLAP-{index}", title="검토")
        if index < 7:
            fields = {"network_scope": "unclear", "model_fit": "unclear"}
            if index == 0:
                fields["task_scope"] = "unclear"
        elif index == 7:
            fields = {"network_scope": "unclear"}
        else:
            fields = {"task_scope": "unclear"}
        notice.analysis_runs.append(_analysis("3", **fields))
        db.add(notice)
    db.commit()

    status = build_statistics(db)["status"]
    assert status["review"] == 9
    assert status["review_reasons"]["notice_total"] == 9
    assert status["review_reasons"]["total"] == 17
    assert {item["key"]: item["count"] for item in status["review_reasons"]["items"]} == {
        "network_data": 8, "national_task": 2, "model": 7,
    }


def test_review_without_platform_use_then_completed_use_counts_both_achievements(db: Session):
    now = datetime.now(timezone.utc)
    notice = Notice(
        stage="prenotice", notice_no="ANYANG-CASE", agency_name="안양시",
        title="안양시 AI 서비스", created_at=now - timedelta(days=2),
    )
    notice.analysis_runs.append(_analysis("3", usage="not_mentioned"))
    notice.action = ActionItem(status="completed_uses", updated_at=now)
    db.add(notice)
    db.commit()

    stats = build_statistics(db, period="all", now=now + timedelta(seconds=1))

    assert stats["achievements"]["review_to_eligible"] == 1
    assert stats["achievements"]["unused_to_used"] == 1
    assert stats["action_use_cases"][0]["achievement_labels"] == [
        "검토 후 적합", "미적용 → 적용",
    ]


def test_previous_criteria_review_history_still_counts_both_anyang_achievements(db: Session):
    now = datetime.now(timezone.utc)
    notice = Notice(
        stage="prenotice", notice_no="ANYANG-VERSIONED", agency_name="경기도 안양시",
        title="안양시 인공지능 기본 및 종합계획 수립 용역",
        created_at=now - timedelta(days=2),
    )
    before = _analysis("3", usage="not_mentioned")
    payload = json.loads(before.result_json)
    payload["criteria_version"] = "common-platform-v7-service-construction-scope"
    before.result_json = json.dumps(payload, ensure_ascii=False)
    notice.analysis_runs.extend([before, _analysis("1", usage="uses")])
    notice.action = ActionItem(status="completed_uses", updated_at=now)
    db.add(notice)
    db.commit()

    stats = build_statistics(db, period="all", now=now + timedelta(seconds=1))

    assert stats["status"]["eligible_uses"] == 1
    assert stats["achievements"]["review_to_eligible"] == 1
    assert stats["achievements"]["unused_to_used"] == 1
    assert stats["action_use_cases"][0]["achievement_labels"] == [
        "검토 후 적합", "미적용 → 적용",
    ]


def test_review_resolution_and_period_filter_are_reflected_in_final_status(db: Session):
    now = datetime.now(timezone.utc)
    resolved = Notice(
        stage="prenotice", notice_no="REVIEW-1", agency_name="기관", title="AI 검토 사업",
        created_at=now - timedelta(days=2),
    )
    resolved.analysis_runs.append(_analysis("3"))
    resolved.action = ActionItem(
        status="completed_not_used", contacted_at=now - timedelta(days=1), updated_at=now,
    )
    old = Notice(
        stage="bid_notice", notice_no="OLD-1", agency_name="기관", title="오래된 비AI 사업",
        created_at=now - timedelta(days=90),
    )
    old.analysis_runs.append(_analysis("6", ai="low"))
    db.add_all([resolved, old])
    db.commit()

    stats = build_statistics(db, period="30d", now=now + timedelta(seconds=1))

    assert stats["status"]["collected"] == 1
    assert stats["status"]["eligible_not_used"] == 1
    assert stats["status"]["review"] == 0
    assert stats["achievements"]["review_to_eligible"] == 1
