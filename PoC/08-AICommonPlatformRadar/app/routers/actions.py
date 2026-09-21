from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActionItem, AnalysisRun, AuditLog, Notice
from ..schemas import ActionPatch, ClassificationErrorRequest
from ..services.analyzer import CURRENT_CRITERIA_VERSION
from ..services.email_notifier import send_opinion_submitted_notification
from ..services.ineligible_reasons import manual_ineligible_reason, set_manual_ineligible_reason
from ..services.workflow_view import current_classification_run, workflow_summary


router = APIRouter()
COMPLETED_STATES = {"completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai"}
MANUAL_CLASSIFICATION_BACKUP_KEY = "_poc08_manual_classification_backup"


def _ensure_real_prenotice(notice: Notice) -> None:
    """Opinion submission is valid only for a real G2B prior specification."""
    if notice.stage != "prenotice":
        raise HTTPException(409, "사전규격 공고만 의견 등록 상태로 전환할 수 있습니다.")
    if (notice.notice_no or "").upper().startswith("SAMPLE-"):
        raise HTTPException(409, "샘플 공고는 의견 등록 상태로 전환하거나 메일을 발송할 수 없습니다.")


def _json_object(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _sync_decision(notice: Notice, result: dict) -> None:
    if not notice.decision:
        return
    notice.decision.final_grade = str(result.get("final_grade") or "E")
    notice.decision.ai_relevance = str(result.get("ai_relevance") or "low")
    notice.decision.common_platform_fit = str(result.get("common_platform_fit") or "low")
    notice.decision.priority_score = int(result.get("priority_score") or 0)
    notice.decision.recommended_action = str(result.get("recommended_action") or "no_action")
    notice.decision.summary = str(result.get("summary") or "최종 피드백을 반영했습니다.")


def _append_manual_classification(
    notice: Notice, *, reason: str, feedback: str = "",
) -> str:
    """Persist an operator-confirmed final classification as the newest result."""
    current_run = current_classification_run(notice)
    current = _json_object(current_run.result_json if current_run else None)
    payload = _json_object(notice.raw_payload_json)
    if MANUAL_CLASSIFICATION_BACKUP_KEY not in payload and current:
        payload[MANUAL_CLASSIFICATION_BACKUP_KEY] = current
    base = payload.get(MANUAL_CLASSIFICATION_BACKUP_KEY)
    base = dict(base) if isinstance(base, dict) else dict(current)
    code = "6" if reason == "non_ai" else "5"
    if (
        str(current.get("classification_code") or "") == code
        and current.get("manual_final_classification_reason") == reason
    ):
        notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)
        return code

    label = "비AI 사업" if reason == "non_ai" else "공통기반 이용 부적합"
    summary = f"사업담당자 피드백을 반영하여 {label}으로 최종 분류했습니다."
    if feedback.strip():
        summary = f"{summary} {feedback.strip()}"
    corrected = dict(base)
    corrected.update({
        "criteria_version": CURRENT_CRITERIA_VERSION,
        "classification_code": code,
        "final_grade": "E",
        "ai_relevance": "low" if reason == "non_ai" else str(base.get("ai_relevance") or "high"),
        "common_platform_fit": "low",
        "eligibility": "uncertain" if reason == "non_ai" else "ineligible",
        "recommended_action": "no_action",
        "priority_score": 0,
        "guidance_message": "",
        "manual_override": True,
        "manual_override_reason": feedback.strip() or label,
        "manual_final_classification_reason": reason,
        "summary": summary,
    })
    if reason == "non_ai":
        corrected["service_scope"] = "non_target"
    digest = hashlib.sha256(
        f"manual-final:{notice.id}:{datetime.now(timezone.utc).isoformat()}:{reason}:{feedback}".encode("utf-8")
    ).hexdigest()
    notice.analysis_runs.append(AnalysisRun(
        notice_id=notice.id, run_type="deep_ai", model_name="manual-feedback",
        input_hash=digest, status="success",
        result_json=json.dumps(corrected, ensure_ascii=False), confidence=1.0,
    ))
    notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    _sync_decision(notice, corrected)
    return code


def _restore_classification_before_manual_feedback(notice: Notice) -> None:
    payload = _json_object(notice.raw_payload_json)
    backup = payload.pop(MANUAL_CLASSIFICATION_BACKUP_KEY, None)
    notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    if not isinstance(backup, dict) or not backup.get("classification_code"):
        return
    restored = dict(backup)
    digest = hashlib.sha256(
        f"manual-restore:{notice.id}:{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
    ).hexdigest()
    notice.analysis_runs.append(AnalysisRun(
        notice_id=notice.id, run_type="deep_ai", model_name="manual-feedback-restore",
        input_hash=digest, status="success",
        result_json=json.dumps(restored, ensure_ascii=False), confidence=1.0,
    ))
    _sync_decision(notice, restored)


@router.patch("/api/actions/{action_id}")
def update_action(action_id: int, patch: ActionPatch, db: Session = Depends(get_db)):
    action = db.get(ActionItem, action_id)
    if not action:
        raise HTTPException(404, "조치 항목을 찾을 수 없습니다.")
    previous_status = action.status
    changes = patch.model_dump(exclude_unset=True)
    ineligible_reason = changes.pop("ineligible_reason", None)
    previous_reason = manual_ineligible_reason(action.notice)
    resulting_status = changes.get("status", action.status)
    resolved_reason = ""
    if resulting_status == "completed_ineligible":
        resolved_reason = ineligible_reason or previous_reason
        if not resolved_reason or resolved_reason == "non_ai":
            raise HTTPException(422, "부적합 유형을 선택해 주세요.")
        set_manual_ineligible_reason(action.notice, resolved_reason)
    elif resulting_status == "completed_non_ai":
        resolved_reason = "non_ai"
        set_manual_ineligible_reason(action.notice, resolved_reason)
    elif "status" in changes:
        set_manual_ineligible_reason(action.notice, None)
    for key, value in changes.items():
        setattr(action, key, value)
    final_code = ""
    if resulting_status in {"completed_ineligible", "completed_non_ai"}:
        feedback = str(changes.get("agency_response") or action.agency_response or changes.get("memo") or action.memo or "")
        final_code = _append_manual_classification(
            action.notice, reason=resolved_reason, feedback=feedback,
        )
    elif "status" in changes and previous_reason:
        _restore_classification_before_manual_feedback(action.notice)
    if changes.get("status") in {"contacted", "in_progress"} and not action.contacted_at:
        action.contacted_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        event_type="action_updated", entity_type="action_item", entity_id=str(action_id), actor="admin",
        detail_json=json.dumps({
            "notice_id": action.notice_id, "previous_status": previous_status,
            **changes, "ineligible_reason": ineligible_reason or previous_reason or "",
            "classification_code": final_code,
        }, ensure_ascii=False),
    ))
    db.commit()
    return {
        "id": action.id, "status": action.status, "owner": action.owner,
        "updated_at": action.updated_at, "classification_code": final_code or None,
        "notification": None,
    }


def _opinion_email_was_sent(db: Session, action_id: int) -> bool:
    return db.scalar(select(AuditLog.id).where(
        AuditLog.event_type == "opinion_submitted_email_sent",
        AuditLog.entity_type == "action_item",
        AuditLog.entity_id == str(action_id),
    ).limit(1)) is not None


def _record_opinion_submission(db: Session, action: ActionItem, *, fallback: bool = False) -> dict:
    opinion_content = workflow_summary(action.notice).get("guidance_message", "")
    try:
        notice_payload = json.loads(action.notice.raw_payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        notice_payload = {}
    if not isinstance(notice_payload, dict):
        notice_payload = {}
    tracking = notice_payload.get("_poc08_opinion_tracking")
    tracking = tracking if isinstance(tracking, dict) else {}
    tracking.update({
        "status": "not_checked",
        "status_label": "답변 확인 전",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "submitted_content": opinion_content,
    })
    notice_payload["_poc08_opinion_tracking"] = tracking
    action.notice.raw_payload_json = json.dumps(notice_payload, ensure_ascii=False, default=str)
    already_recorded = db.scalar(select(AuditLog.id).where(
        AuditLog.event_type == "opinion_submitted",
        AuditLog.entity_type == "action_item",
        AuditLog.entity_id == str(action.id),
    ).limit(1)) is not None
    if action.status not in COMPLETED_STATES:
        action.status = "in_progress"
    action.contacted_at = action.contacted_at or datetime.now(timezone.utc)
    if not already_recorded:
        db.add(AuditLog(
            event_type="opinion_submitted", entity_type="action_item", entity_id=str(action.id), actor="extension",
            detail_json=json.dumps({
                "notice_id": action.notice_id, "fallback": fallback,
                "opinion_content": opinion_content,
            }, ensure_ascii=False),
        ))
    db.commit()

    if _opinion_email_was_sent(db, action.id):
        return {"sent": False, "reason": "already_sent"}
    try:
        notification = send_opinion_submitted_notification(
            action.notice, action, opinion_content,
        )
        event_type = "opinion_submitted_email_sent" if notification.get("sent") else "opinion_submitted_email_skipped"
    except Exception as exc:
        notification = {"sent": False, "reason": type(exc).__name__}
        event_type = "opinion_submitted_email_failed"
    db.add(AuditLog(
        event_type=event_type, entity_type="action_item", entity_id=str(action.id), actor="system",
        detail_json=json.dumps(notification, ensure_ascii=False),
    ))
    db.commit()
    return notification


@router.post("/api/actions/{action_id}/opinion-submitted")
def mark_opinion_submitted(action_id: int, db: Session = Depends(get_db)):
    action = db.get(ActionItem, action_id)
    if not action:
        raise HTTPException(404, "조치 항목을 찾을 수 없습니다.")
    _ensure_real_prenotice(action.notice)
    notification = _record_opinion_submission(db, action)
    return {"id": action.id, "status": action.status, "notification": notification}


@router.post("/api/notices/{notice_id}/opinion-submitted")
def mark_notice_opinion_submitted(notice_id: int, db: Session = Depends(get_db)):
    """Extension fallback for an actionable notice whose ActionItem was not materialized yet."""
    notice = db.get(Notice, notice_id)
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    _ensure_real_prenotice(notice)
    action = notice.action or ActionItem(status="new")
    if notice.action is None:
        notice.action = action
        db.flush()
    notification = _record_opinion_submission(db, action, fallback=True)
    return {"id": action.id, "status": action.status, "notification": notification}


@router.post("/api/notices/{notice_id}/classification-error")
def report_classification_error(
    notice_id: int, payload: ClassificationErrorRequest, db: Session = Depends(get_db),
):
    notice = db.get(Notice, notice_id)
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    run = current_classification_run(notice)
    if not run:
        raise HTTPException(409, "현재 유효한 판정이 없습니다.")
    try:
        original = json.loads(run.result_json or "{}")
    except json.JSONDecodeError:
        original = {}
    original_code = str(original.get("classification_code") or "")
    if original_code not in {"2", "3", "4"}:
        raise HTTPException(409, "미이용 또는 검토 필요 판정만 오류 신고로 부적합 전환할 수 있습니다.")
    corrected = dict(original)
    corrected.update({
        "classification_code": "5",
        "final_grade": "E",
        "common_platform_fit": "low",
        "eligibility": "ineligible",
        "recommended_action": "no_action",
        "priority_score": 0,
        "guidance_message": "",
        "manual_override": True,
        "manual_override_reason": payload.reason,
        "summary": f"사용자 판정오류 신고로 공통기반 부적합으로 정정했습니다. {payload.reason}",
    })
    digest = hashlib.sha256(
        f"manual:{notice.id}:{datetime.now(timezone.utc).isoformat()}:{payload.reason}".encode("utf-8")
    ).hexdigest()
    notice.analysis_runs.append(AnalysisRun(
        notice_id=notice.id, run_type="deep_ai", model_name="manual-override",
        input_hash=digest, status="success", result_json=json.dumps(corrected, ensure_ascii=False), confidence=1.0,
    ))
    if notice.decision:
        notice.decision.final_grade = "E"
        notice.decision.common_platform_fit = "low"
        notice.decision.priority_score = 0
        notice.decision.recommended_action = "no_action"
        notice.decision.summary = corrected["summary"]
    action = notice.action or ActionItem()
    action.status = "completed_ineligible"
    action.memo = "\n".join(filter(None, [action.memo, f"판정오류 신고: {payload.reason}"]))
    if notice.action is None:
        notice.action = action
    db.add(AuditLog(
        event_type="classification_error_report", entity_type="notice", entity_id=str(notice.id), actor="admin",
        detail_json=json.dumps({
            "notice_id": notice.id, "title": notice.title, "agency_name": notice.agency_name,
            "notice_url": notice.url, "original_code": original_code, "corrected_code": "5",
            "reason": payload.reason,
        }, ensure_ascii=False),
    ))
    db.commit()
    return {
        "notice_id": notice.id, "original_code": original_code,
        "classification_code": "5", "notification": None,
    }
