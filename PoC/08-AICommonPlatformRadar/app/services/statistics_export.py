"""Downloadable, notice-level data behind the performance statistics page."""
from __future__ import annotations

import csv
import io
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import ActionItem, AnalysisRun, Attachment, AuditLog, Notice
from .analyzer import CLASSIFICATION_LABELS
from .ineligible_reasons import INELIGIBLE_DETAIL_BY_KEY, ineligible_detail_key, manual_ineligible_reason
from .opinion_tracker import cached_opinion_tracking
from .statistics_builder import (
    KST, OPINION_INELIGIBLE_GROUPS, _current_result, _in_window, _opinion_ineligible_group,
    _opinion_outcome_key, _opinion_submission_dates, _period_window,
    _resolution_events, final_status_key,
)
from .workflow_view import ACTION_STATUS_LABELS, current_classification_run, json_object


COLUMNS = (
    "집계 기간", "집계 포함 기준", "공고 ID", "공고 구분", "공고번호", "입찰공고번호",
    "기관명", "사업명", "공고일", "마감일", "수집일", "공고 원문 URL",
    "최종 상태", "판정 코드", "판정명", "판정 시각", "AI 관련성", "공통기반 적합성",
    "공통기반 이용 여부", "우선순위", "분석 요약", "망 조건", "망 판단 근거",
    "업무 조건", "업무 판단 근거", "모델 조건", "모델 판단 근거", "적용 범위",
    "부적합 세부 사유", "조치 상태", "조치 담당자", "연락일", "조치 수정일",
    "기간 내 조치 완료일", "기관 회신 기록", "조치 메모", "의견 등록일", "의견 결과",
    "의견 등록 내용", "나라장터 답변 상태", "나라장터 답변일", "나라장터 답변 내용",
    "첨부파일명", "최신 판정 전체(JSON)", "조치 변경 이력(JSON)", "의견 등록 이력(JSON)",
)

FINAL_STATUS_LABELS = {
    "eligible_uses": "적합·이용", "eligible_not_used": "적합·미이용",
    "review": "검토 필요", "ineligible": "부적합", "non_ai": "비AI 서비스 사업",
    "out_of_scope": "적용범위 외", "pending": "최종판정 대기",
}
OPINION_OUTCOME_LABELS = {
    "not_submitted": "미등록", "waiting": "답변 대기", "accepted": "수용",
    "not_used": "미사용", "ineligible": "부적합", "non_ai": "비AI 서비스 사업",
    "unclassified": "답변 확인·결과 미분류",
}


def _date(value: datetime | None) -> str:
    if not value:
        return ""
    return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(KST).strftime("%Y-%m-%d %H:%M")


def _safe(value: Any) -> Any:
    """Keep spreadsheet programs from evaluating untrusted notice text as formulas."""
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value if value is not None else ""


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def build_statistics_csv(db: Session, period: str = "30d", now: datetime | None = None) -> bytes:
    """Export notices collected or acted on in the selected period."""
    window = _period_window(period, now)
    all_notices = db.scalars(select(Notice).options(
        selectinload(Notice.attachments).load_only(Attachment.id, Attachment.original_filename),
        selectinload(Notice.analysis_runs).load_only(
            AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
            AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.created_at,
        ),
        selectinload(Notice.decision),
        selectinload(Notice.action),
    ).order_by(Notice.id)).all()
    submissions = _opinion_submission_dates(db, all_notices)
    resolution_events = _resolution_events(db, all_notices)
    resolution_dates: dict[int, list[datetime]] = defaultdict(list)
    for event in resolution_events:
        if _in_window(event["at"], window["start"], window["end"]):
            resolution_dates[event["notice"].id].append(event["at"])

    by_action = {notice.action.id: notice.id for notice in all_notices if notice.action and notice.action.id}
    histories: dict[str, dict[int, list[dict[str, Any]]]] = {
        "action_updated": defaultdict(list), "opinion_submitted": defaultdict(list),
    }
    action_activity_ids = {
        notice.id for notice in all_notices
        if notice.action and _in_window(notice.action.updated_at, window["start"], window["end"])
    }
    for log in db.scalars(select(AuditLog).where(
        AuditLog.event_type.in_(histories)
    ).order_by(AuditLog.id)).all():
        try:
            notice_id = by_action.get(int(log.entity_id or 0))
        except ValueError:
            continue
        if notice_id:
            if log.event_type == "action_updated" and _in_window(
                log.created_at, window["start"], window["end"]
            ):
                action_activity_ids.add(notice_id)
            histories[log.event_type][notice_id].append({
                "at": _date(log.created_at), "detail": json_object(log.detail_json),
            })

    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    for notice in all_notices:
        basis = []
        if _in_window(notice.created_at, window["start"], window["end"]):
            basis.append("수집")
        if resolution_dates.get(notice.id):
            basis.append("조치 완료")
        elif notice.id in action_activity_ids:
            basis.append("조치 기록")
        if _in_window(submissions.get(notice.id), window["start"], window["end"]):
            basis.append("의견 등록")
        if not basis:
            continue

        result = _current_result(notice)
        run = current_classification_run(notice)
        action: ActionItem | None = notice.action
        tracking = cached_opinion_tracking(notice)
        code = str(result.get("classification_code") or "")
        state = final_status_key(notice, result)
        detail_key = (
            manual_ineligible_reason(notice) or ineligible_detail_key(notice, result)
            if state == "ineligible" else ""
        )
        detail_label = INELIGIBLE_DETAIL_BY_KEY.get(detail_key, {}).get("label", detail_key)
        outcome = _opinion_outcome_key(notice, submissions.get(notice.id))
        if outcome == "ineligible":
            group = _opinion_ineligible_group(manual_ineligible_reason(notice))
            group_label = dict(OPINION_INELIGIBLE_GROUPS).get(group, group)
            detail_label = f"{group_label} · {detail_label}" if detail_label else group_label
        row = (
            window["label"], "·".join(basis), notice.id,
            "사전규격" if notice.stage == "prenotice" else "본공고" if notice.stage == "bid_notice" else notice.stage,
            notice.notice_no, notice.bid_no, notice.agency_name, notice.title,
            _date(notice.posted_at), _date(notice.deadline_at), _date(notice.created_at), notice.url,
            FINAL_STATUS_LABELS.get(state, state), code, CLASSIFICATION_LABELS.get(code, ""),
            _date(run.created_at if run else None), result.get("ai_relevance") or (notice.decision.ai_relevance if notice.decision else ""),
            notice.decision.common_platform_fit if notice.decision else "",
            result.get("platform_usage") or (notice.decision.usage_mentioned if notice.decision else ""),
            notice.decision.priority_score if notice.decision else "",
            result.get("summary") or (notice.decision.summary if notice.decision else ""),
            result.get("network_scope"), result.get("network_reason"),
            result.get("task_scope"), result.get("task_scope_reason"),
            result.get("model_fit"), result.get("model_fit_reason"), result.get("service_scope"),
            detail_label, ACTION_STATUS_LABELS.get(action.status, action.status) if action else "",
            action.owner if action else "", _date(action.contacted_at if action else None),
            _date(action.updated_at if action else None),
            _date(max(resolution_dates[notice.id])) if resolution_dates.get(notice.id) else "",
            action.agency_response if action else "", action.memo if action else "",
            _date(submissions.get(notice.id)), OPINION_OUTCOME_LABELS[outcome],
            tracking.get("submitted_content"), tracking.get("status_label"),
            tracking.get("latest_reply_at"), tracking.get("latest_reply_content"),
            " | ".join(attachment.original_filename for attachment in notice.attachments),
            _json(result) if result else "",
            _json(histories["action_updated"][notice.id]) if histories["action_updated"].get(notice.id) else "",
            _json(histories["opinion_submitted"][notice.id]) if histories["opinion_submitted"].get(notice.id) else "",
        )
        writer.writerow([_safe(value) for value in row])
    return ("\ufeff" + output.getvalue()).encode("utf-8")
