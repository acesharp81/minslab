from __future__ import annotations

import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import ActionItem, AnalysisRun, AuditLog, Notice
from app.routers import actions
from app.schemas import ActionPatch, ClassificationErrorRequest
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.ineligible_reasons import INELIGIBLE_REASON_META
from app.services.statistics_builder import final_status_key
from app.services.workflow_view import current_classification_run


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _notice(code: str = "2") -> Notice:
    notice = Notice(stage="prenotice", notice_no="R26TEST0001", agency_name="테스트기관", title="AI 구축 사업")
    notice.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="test", input_hash="a" * 64, status="success",
        result_json=json.dumps({
            "criteria_version": CURRENT_CRITERIA_VERSION,
            "classification_code": code,
            "network_scope": "internal_or_connected",
            "task_scope": "government",
            "service_scope": "target_build",
            "model_fit": "platform_llm_or_rag",
            "platform_usage": "not_mentioned",
            "remediation_feasibility": "not_needed",
            "guidance_message": "공통기반 이용을 검토해 주시기 바랍니다.",
        }, ensure_ascii=False),
    ))
    return notice


def test_non_ai_is_a_standalone_action_status_not_an_ineligible_reason():
    assert ActionPatch(status="completed_non_ai").status == "completed_non_ai"
    assert "non_ai" not in {item[0] for item in INELIGIBLE_REASON_META}


def test_completion_transition_does_not_send_notification(db: Session, monkeypatch):
    notice = _notice()
    notice.action = ActionItem(status="new")
    db.add(notice)
    db.commit()
    sent = []
    monkeypatch.setattr(actions, "send_opinion_submitted_notification", lambda *args: sent.append(args) or {"sent": True})

    result = actions.update_action(notice.action.id, ActionPatch(status="completed_uses"), db)

    assert result["status"] == "completed_uses"
    classified = json.loads(current_classification_run(notice).result_json)
    assert result["classification_code"] == "1"
    assert classified["classification_code"] == "1"
    assert classified["platform_usage"] == "uses"
    assert classified["manual_final_classification_reason"] == "action_confirmed_uses"
    assert result["notification"] is None
    assert sent == []
    assert db.query(AuditLog).filter(AuditLog.event_type.like("%email%")).count() == 0


def test_ineligible_completion_requires_and_records_reason(db: Session):
    notice = _notice("3")
    notice.action = ActionItem(status="reviewing")
    db.add(notice)
    db.commit()

    with pytest.raises(Exception) as exc_info:
        actions.update_action(notice.action.id, ActionPatch(status="completed_ineligible"), db)

    assert getattr(exc_info.value, "status_code", None) == 422
    result = actions.update_action(
        notice.action.id,
        ActionPatch(status="completed_ineligible", ineligible_reason="network_data"),
        db,
    )

    assert result["status"] == "completed_ineligible"
    assert json.loads(notice.raw_payload_json)["_poc08_manual_ineligible_reason"] == "network_data"
    log = db.query(AuditLog).filter_by(event_type="action_updated").one()
    assert json.loads(log.detail_json)["ineligible_reason"] == "network_data"


def test_leaving_ineligible_completion_clears_manual_reason(db: Session):
    notice = _notice("3")
    notice.raw_payload_json = json.dumps({"_poc08_manual_ineligible_reason": "national_task"})
    notice.action = ActionItem(status="completed_ineligible")
    db.add(notice)
    db.commit()

    actions.update_action(notice.action.id, ActionPatch(status="completed_not_used"), db)

    assert "_poc08_manual_ineligible_reason" not in json.loads(notice.raw_payload_json)


def test_non_ai_feedback_reclassifies_notice_and_can_restore_previous_result(db: Session):
    notice = _notice("3")
    notice.action = ActionItem(status="reviewing")
    db.add(notice)
    db.commit()

    result = actions.update_action(
        notice.action.id,
        ActionPatch(
            status="completed_non_ai",
            agency_response="사업담당자가 AI를 도입하는 사업이 아니라고 회신했습니다.",
        ),
        db,
    )

    classified = json.loads(current_classification_run(notice).result_json)
    payload = json.loads(notice.raw_payload_json)
    assert result["classification_code"] == "6"
    assert classified["classification_code"] == "6"
    assert classified["ai_relevance"] == "low"
    assert classified["manual_final_classification_reason"] == "non_ai"
    assert payload["_poc08_manual_ineligible_reason"] == "non_ai"
    assert "_poc08_manual_classification_backup" in payload
    assert notice.action.status == "completed_non_ai"
    assert final_status_key(notice) == "non_ai"

    actions.update_action(notice.action.id, ActionPatch(status="reviewing"), db)

    restored = json.loads(current_classification_run(notice).result_json)
    restored_payload = json.loads(notice.raw_payload_json)
    assert restored["classification_code"] == "3"
    assert "_poc08_manual_ineligible_reason" not in restored_payload
    assert "_poc08_manual_classification_backup" not in restored_payload


def test_opinion_submission_sends_notification_only_once(db: Session, monkeypatch):
    notice = _notice()
    notice.action = ActionItem(status="new")
    db.add(notice)
    db.commit()
    sent = []
    monkeypatch.setattr(
        actions, "send_opinion_submitted_notification",
        lambda notice, action, content: sent.append((notice.id, action.status, content)) or {"sent": True},
    )

    first = actions.mark_opinion_submitted(notice.action.id, db)
    second = actions.mark_opinion_submitted(notice.action.id, db)

    assert first["status"] == "in_progress"
    assert first["notification"] == {"sent": True}
    assert second["notification"] == {"sent": False, "reason": "already_sent"}
    assert len(sent) == 1
    tracking = json.loads(notice.raw_payload_json)["_poc08_opinion_tracking"]
    assert tracking["status"] == "not_checked"
    assert "공통기반" in tracking["submitted_content"]
    assert "[분석 내용]" in tracking["submitted_content"]
    assert db.query(AuditLog).filter_by(event_type="opinion_submitted").count() == 1
    assert db.query(AuditLog).filter_by(event_type="opinion_submitted_email_sent").count() == 1


def test_extension_fallback_creates_action_and_marks_in_progress(db: Session, monkeypatch):
    notice = _notice()
    db.add(notice)
    db.commit()
    monkeypatch.setattr(actions, "send_opinion_submitted_notification", lambda *_args: {"sent": True})

    result = actions.mark_notice_opinion_submitted(notice.id, db)

    assert result["status"] == "in_progress"
    assert notice.action.status == "in_progress"
    assert notice.action.contacted_at is not None
    assert result["notification"] == {"sent": True}
    assert db.query(AuditLog).filter_by(event_type="opinion_submitted").count() == 1


@pytest.mark.parametrize(
    ("stage", "notice_no"),
    [("bid_notice", "R26TEST0002-00"), ("prenotice", "SAMPLE-PRE-001")],
)
def test_opinion_submission_rejects_bid_and_sample_notices(
    db: Session, monkeypatch, stage: str, notice_no: str,
):
    notice = _notice()
    notice.stage = stage
    notice.notice_no = notice_no
    notice.action = ActionItem(status="new")
    db.add(notice)
    db.commit()
    sent = []
    monkeypatch.setattr(
        actions, "send_opinion_submitted_notification",
        lambda *args: sent.append(args) or {"sent": True},
    )

    with pytest.raises(Exception) as exc_info:
        actions.mark_opinion_submitted(notice.action.id, db)

    assert getattr(exc_info.value, "status_code", None) == 409
    assert notice.action.status == "new"
    assert sent == []
    assert db.query(AuditLog).filter_by(event_type="opinion_submitted").count() == 0


def test_classification_error_is_recorded_and_completed_as_ineligible(db: Session, monkeypatch):
    notice = _notice("3")
    notice.action = ActionItem(status="reviewing")
    db.add(notice)
    db.commit()
    sent = []
    monkeypatch.setattr(actions, "send_opinion_submitted_notification", lambda *args: sent.append(args) or {"sent": True})

    result = actions.report_classification_error(
        notice.id,
        ClassificationErrorRequest(reason="공개 문서에서 인터넷망 완결 서비스임을 확인했습니다."),
        db,
    )

    assert result["classification_code"] == "5"
    assert notice.action.status == "completed_ineligible"
    assert db.query(AuditLog).filter_by(event_type="classification_error_report").count() == 1
    assert sent == []
    latest = sorted(notice.analysis_runs, key=lambda row: row.id, reverse=True)[0]
    assert json.loads(latest.result_json)["manual_override"] is True
