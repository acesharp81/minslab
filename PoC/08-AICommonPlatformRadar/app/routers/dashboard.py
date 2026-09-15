from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import Notice, PipelineRun
from ..services.attachment_policy import is_business_document, select_preferred_documents
from ..services.analyzer import is_current_deep_result
from ..services.collector import is_explicit_ai_title
from ..services.report_builder import _batch_data, _latest_reconciliation, _reconciliation_data
from ..services.workflow_view import ACTION_REQUIRED_CODES, workflow_summary
from .notices import analysis_view, deadline_label, format_datetime


router = APIRouter()
KST = timezone(timedelta(hours=9))


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today = now.astimezone(KST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    notices = db.scalars(select(Notice).options(
        selectinload(Notice.analysis_runs), selectinload(Notice.decision),
        selectinload(Notice.action), selectinload(Notice.attachments),
    )).all()
    states = {notice.id: analysis_view(notice) for notice in notices}
    workflows = {notice.id: workflow_summary(notice) for notice in notices}
    business_failures = []
    for notice in notices:
        selected = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
        business_failures.extend(
            item for item in selected
            if is_business_document(item.original_filename)
            and (item.download_status == "failed" or item.parse_status in {"failed", "unsupported"})
        )
    parse_notice_ids = {item.notice_id for item in business_failures}
    active_actions = {"new", "reviewing", "contacted", "not_reflected"}
    criteria_outdated = [notice for notice in notices if states[notice.id]["key"] == "criteria_outdated"]
    contact = [notice for notice in notices
               if workflows[notice.id]["classification_code"] in ACTION_REQUIRED_CODES
               and (not notice.action or notice.action.status in active_actions)]
    manual = [notice for notice in notices if states[notice.id]["key"] != "criteria_outdated"
              and notice.decision and notice.decision.recommended_action == "manual_review"
              and (not notice.action or notice.action.status in active_actions)]
    ai_unanalyzed = [notice for notice in notices if states[notice.id]["key"] == "unanalyzed"
                     and is_explicit_ai_title(notice.title)]
    failed_analysis = [notice for notice in notices if states[notice.id]["key"] == "failed"]
    deep_pending = [notice for notice in notices if states[notice.id]["key"] == "deep_pending"]

    workflow_tasks = [
        {"key": "criteria_outdated", "label": "기준 갱신 필요", "count": len(criteria_outdated),
         "description": "3대 기본조건으로 다시 검증할 기존 심층 결과", "href": "?analysis_status=criteria_outdated", "tone": "warning"},
        {"key": "contact", "label": "담당자 확인", "count": len(contact),
         "description": "공통기반 활용 여부를 우선 확인할 사업", "href": "?recommended_action=contact", "tone": "accent"},
        {"key": "analysis_failed", "label": "분석 재시도", "count": len(failed_analysis),
         "description": "LLM 오류 후 다음 배치를 기다리는 공고", "href": "?analysis_status=failed", "tone": "danger"},
        {"key": "ai_unanalyzed", "label": "AI 명시 미분석", "count": len(ai_unanalyzed),
         "description": "AI 키워드가 명시돼 우선 분석할 공고", "href": "?keyword=AI&analysis_status=unanalyzed", "tone": "warning"},
        {"key": "deep_pending", "label": "3차 심층 대기", "count": len(deep_pending),
         "description": "2차 통과 후 일일 심층 한도를 기다리는 공고", "href": "?analysis_status=deep_pending", "tone": "warning"},
        {"key": "manual", "label": "표본·수동 검토", "count": len(manual),
         "description": "공개자료만으로 판단이 어려운 공고", "href": "?recommended_action=manual_review", "tone": "neutral"},
        {"key": "parse", "label": "문서 재처리", "count": len(parse_notice_ids),
         "description": "사업 문서 파싱 오류 또는 미지원 공고", "href": "?parse_status=issue", "tone": "danger"},
    ]
    work_ids = ({row.id for row in criteria_outdated} | {row.id for row in contact} |
                {row.id for row in failed_analysis} |
                {row.id for row in ai_unanalyzed} | {row.id for row in deep_pending} |
                {row.id for row in manual} | parse_notice_ids)
    ranked = []
    for notice in notices:
        label = None
        rank = 99
        if notice in criteria_outdated:
            label, rank = "기준 갱신 필요", 0
        elif notice in contact:
            label, rank = "담당자 확인", 1
        elif notice in failed_analysis:
            label, rank = "분석 재시도", 2
        elif notice in ai_unanalyzed:
            label, rank = "AI 명시 미분석", 3
        elif notice in deep_pending:
            label, rank = "3차 심층 대기", 4
        elif notice in manual:
            label, rank = "수동 검토", 5
        elif notice.id in parse_notice_ids:
            label, rank = "문서 재처리", 6
        if label:
            posted = notice.posted_at.timestamp() if notice.posted_at else 0
            ranked.append((rank, -posted, notice, label))
    ranked.sort(key=lambda value: (value[0], value[1]))
    next_items = [{"notice": row[2], "label": row[3], "deadline": deadline_label(row[2].deadline_at)}
                  for row in ranked[:10]]

    metrics = {
        "today": db.scalar(select(func.count(Notice.id)).where(Notice.created_at >= today)) or 0,
        "work": len(work_ids),
        "deep": sum(states[notice.id]["key"] == "deep_completed" for notice in notices),
        "priority": len(contact),
        "failed": len(parse_notice_ids),
    }
    classifications = {
        code: sum(states[notice.id].get("classification_code") == code for notice in notices)
        for code in ("1", "2", "3", "4", "5", "6")
    }
    counts_by_day: dict[str, int] = {}
    for notice in notices:
        created_at = notice.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        day_key = created_at.astimezone(KST).date().isoformat()
        counts_by_day[day_key] = counts_by_day.get(day_key, 0) + 1
    local_day = now.astimezone(KST).date()
    recent = []
    for offset in range(6, -1, -1):
        day = local_day - timedelta(days=offset)
        recent.append({"date": day.isoformat(), "label": day.strftime("%m/%d"), "count": counts_by_day.get(day.isoformat(), 0)})
    recent_max = max((row["count"] for row in recent), default=1) or 1
    for row in recent:
        row["percent"] = max(3, round(row["count"] / recent_max * 100)) if row["count"] else 0

    def action_sort_key(notice: Notice):
        deadline = notice.deadline_at
        if deadline is None:
            deadline = datetime.max.replace(tzinfo=timezone.utc)
        elif deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return (notice.stage != "prenotice", deadline,
                -(notice.decision.priority_score if notice.decision else 0))

    priority_notices = sorted(contact, key=action_sort_key)
    priorities = [
        {"notice": notice, "analysis": states[notice.id], "workflow": workflows[notice.id],
         "deadline": deadline_label(notice.deadline_at)}
        for notice in priority_notices[:30]
    ]
    latest_batch = db.scalar(
        select(PipelineRun).where(PipelineRun.run_kind == "collect").order_by(PipelineRun.started_at.desc())
    )
    batch = _batch_data(latest_batch)
    reconciliation = _reconciliation_data(_latest_reconciliation(db, local_day))
    runs_today = [
        run for notice in notices for run in notice.analysis_runs
        if (run.created_at.replace(tzinfo=timezone.utc) if run.created_at.tzinfo is None else run.created_at) >= today
    ]
    classified_today = {
        run.notice_id for run in runs_today
        if run.run_type == "deep_ai" and is_current_deep_result(run.result_json)
        and (run.status == "success" or (run.status == "skipped" and run.model_name == "rule-gate"))
    }
    simple_today = {
        run.notice_id for run in runs_today if run.run_type == "simple_ai" and run.status == "success"
    }
    llm_needed_today = set()
    for run in runs_today:
        if run.run_type != "simple_ai" or run.status != "success":
            continue
        try:
            if json.loads(run.result_json or "{}").get("needs_deep_review"):
                llm_needed_today.add(run.notice_id)
        except (json.JSONDecodeError, TypeError):
            continue
    deep_today = {
        run.notice_id for run in runs_today
        if run.run_type == "deep_ai" and run.status == "success" and is_current_deep_result(run.result_json)
    }
    actioned_today = sum(
        bool(notice.action and notice.action.status in {"contacted", "reflected", "not_reflected", "closed"}
             and (notice.action.updated_at.replace(tzinfo=timezone.utc)
                  if notice.action.updated_at.tzinfo is None else notice.action.updated_at) >= today)
        for notice in notices
    )
    current_classified = (
        reconciliation["classified"] if reconciliation["state"] == "ready" else len(classified_today)
    )
    current_simple = (
        reconciliation["current_simple"] if reconciliation["state"] == "ready" else len(simple_today)
    )
    current_deep = (
        reconciliation["deep_candidates"] if reconciliation["state"] == "ready" else len(deep_today)
    )
    current_llm_needed = (
        reconciliation["deep_candidates"] if reconciliation["state"] == "ready" else len(llm_needed_today)
    )
    workflow_steps = [
        {"number": 1, "label": "신규 수집", "value": metrics["today"], "detail": f"배치 수신 {batch['stats'].get('received', 0)}건", "href": "?sort=newest"},
        {"number": 2, "label": "현재 유형 분류", "value": current_classified, "detail": f"비AI {classifications['6']}건", "href": ""},
        {"number": 3, "label": "2차 LLM 검증", "value": current_simple, "detail": f"심층 필요 {current_llm_needed}건", "href": "?analysis_status=simple_completed"},
        {"number": 4, "label": "3차 심층 분석", "value": current_deep, "detail": "3대 기본조건 검증 완료", "href": "?analysis_status=deep_completed"},
        {"number": 5, "label": "조치 필요", "value": len(contact), "detail": f"오늘 조치 {actioned_today}건", "href": ""},
    ]
    return request.app.state.templates.TemplateResponse(request, "dashboard.html", {
        "metrics": metrics, "classifications": classifications, "recent": recent,
        "priorities": priorities, "workflow_tasks": workflow_tasks, "next_items": next_items,
        "batch": batch, "reconciliation": reconciliation,
        "workflow_steps": workflow_steps, "actioned_today": actioned_today,
        "format_datetime": format_datetime,
    })
