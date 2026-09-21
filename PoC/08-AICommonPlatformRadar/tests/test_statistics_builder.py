from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ActionItem, AnalysisRun, Attachment, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
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
        "5", network_scope="external_complete", service_scope="non_target",
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
        "ai": 3, "non_ai": 1, "ai_rate": 75.0,
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
    assert reasons["network"] == 1
    assert reasons["service"] == 1


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
