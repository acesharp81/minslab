from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import ActionItem, AnalysisRun, Notice, NoticeDecision
from ..services.statistics_builder import build_final_status_snapshot
from ..services.workflow_view import workflow_summary
from .notices import current_classification_notice_ids, deadline_label, format_datetime

router = APIRouter()
KST = timezone(timedelta(hours=9))
ACTION_CODES = {"2", "3", "4"}
PENDING_ACTION_STATES = {"new", "reviewing"}
OPINION_IN_PROGRESS_STATES = {"in_progress", "contacted", "not_reflected"}
IN_PROGRESS_STATES = {"in_progress", "contacted", "reviewing"}
COMPLETED_STATES = {
    "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai", "reflected", "closed",
}


def collection_window(now: datetime) -> dict[str, datetime | str]:
    """Return the latest closed daily cycle containing the morning jobs."""
    local_now = now.astimezone(KST)
    # 06:00 closes the cycle after the 03:10 primary collection and 04:35
    # conditional retry (which is hard-stopped by 05:50).
    end_local = local_now.replace(hour=6, minute=0, second=0, microsecond=0)
    if local_now < end_local:
        end_local -= timedelta(days=1)
    start_local = end_local - timedelta(days=1)

    def label(value: datetime) -> str:
        return f"{value.year % 100}.{value.month}.{value.day}. {value:%H:%M}"

    return {
        "start": start_local.astimezone(timezone.utc),
        "end": end_local.astimezone(timezone.utc),
        "label": f"{label(start_local)} ~ {label(end_local)}",
    }


def _count(db: Session, *conditions) -> int:
    return int(db.scalar(select(func.count(Notice.id)).where(*conditions)) or 0)


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    page: int = Query(1, ge=1),
    progress_page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    """Render a compact operator dashboard from bounded, server-side queries."""
    now = datetime.now(timezone.utc)
    today = now.astimezone(KST).replace(
        hour=0, minute=0, second=0, microsecond=0,
    ).astimezone(timezone.utc)
    window = collection_window(now)
    window_notices = db.scalars(
        select(Notice)
        .options(
            selectinload(Notice.analysis_runs).load_only(
                AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
                AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.error_message,
            ),
            selectinload(Notice.action),
        )
        .where(Notice.created_at >= window["start"], Notice.created_at < window["end"])
    ).all()
    summary_flow = build_final_status_snapshot(window_notices)
    classification_ids = current_classification_notice_ids(db)

    pending_action = or_(
        ~Notice.action.has(),
        Notice.action.has(ActionItem.status.in_(PENDING_ACTION_STATES)),
    )
    action_ids = set().union(*(classification_ids.get(code, ()) for code in ACTION_CODES))
    action_condition = Notice.id.in_(action_ids)
    action_total = _count(db, action_condition, pending_action)
    page_size = 10
    total_pages = max(1, math.ceil(action_total / page_size))
    current_page = min(page, total_pages)
    action_notices = db.scalars(
        select(Notice)
        .options(
            selectinload(Notice.analysis_runs).load_only(
                AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
                AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.error_message,
            ),
            selectinload(Notice.action),
        )
        .outerjoin(NoticeDecision)
        .where(action_condition, pending_action)
        .order_by(
            (Notice.stage != "prenotice").asc(),
            Notice.deadline_at.asc().nullslast(),
            NoticeDecision.priority_score.desc().nullslast(),
        )
        .offset((current_page - 1) * page_size)
        .limit(page_size)
    ).all()
    priorities = [
        {
            "notice": notice,
            "workflow": workflow_summary(notice),
            "deadline": deadline_label(notice.deadline_at),
        }
        for notice in action_notices
    ]


    def stage_priorities(stage: str) -> list[dict]:
        rows = db.scalars(
            select(Notice)
            .options(
                selectinload(Notice.analysis_runs).load_only(
                    AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
                    AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.error_message,
                ),
                selectinload(Notice.action),
            )
            .outerjoin(NoticeDecision)
            .where(action_condition, pending_action, Notice.stage == stage)
            .order_by(
                Notice.deadline_at.asc().nullslast(),
                NoticeDecision.priority_score.desc().nullslast(),
            )
            .limit(page_size)
        ).all()
        return [
            {
                "notice": notice,
                "workflow": workflow_summary(notice),
                "deadline": deadline_label(notice.deadline_at),
            }
            for notice in rows
        ]

    prenotice_action_total = _count(
        db, action_condition, pending_action, Notice.stage == "prenotice",
    )
    bid_action_total = _count(
        db, action_condition, pending_action, Notice.stage == "bid_notice",
    )
    prenotice_priorities = stage_priorities("prenotice")
    bid_priorities = stage_priorities("bid_notice")

    progress_condition = (
        Notice.stage == "prenotice",
        Notice.action.has(ActionItem.status.in_(OPINION_IN_PROGRESS_STATES)),
    )
    progress_total = _count(db, *progress_condition)
    progress_total_pages = max(1, math.ceil(progress_total / page_size))
    current_progress_page = min(progress_page, progress_total_pages)
    progress_notices = db.scalars(
        select(Notice)
        .options(
            selectinload(Notice.analysis_runs).load_only(
                AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
                AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.error_message,
            ),
            selectinload(Notice.action),
        )
        .join(ActionItem)
        .where(*progress_condition)
        .order_by(
            ActionItem.updated_at.desc(),
            Notice.deadline_at.asc().nullslast(),
        )
        .offset((current_progress_page - 1) * page_size)
        .limit(page_size)
    ).all()
    in_progress = [
        {
            "notice": notice,
            "workflow": workflow_summary(notice),
            "deadline": deadline_label(notice.deadline_at),
        }
        for notice in progress_notices
    ]
    actioned_today = int(db.scalar(
        select(func.count(ActionItem.id)).where(
            ActionItem.status.in_(tuple(IN_PROGRESS_STATES | COMPLETED_STATES)),
            ActionItem.updated_at >= today,
        )
    ) or 0)

    confirmed_use_notices = db.scalars(
        select(Notice)
        .options(
            selectinload(Notice.action),
            selectinload(Notice.analysis_runs).load_only(
                AnalysisRun.id, AnalysisRun.run_type, AnalysisRun.model_name,
                AnalysisRun.status, AnalysisRun.result_json, AnalysisRun.error_message,
            ),
        )
        .where(or_(
            Notice.id.in_(classification_ids.get("1", ())),
            Notice.action.has(ActionItem.status == "completed_uses"),
        ))
        .order_by(Notice.updated_at.desc())
        .limit(10)
    ).all()

    def page_url(target_page: int) -> str:
        params = dict(request.query_params)
        params["page"] = str(target_page)
        return f"{request.url_for('dashboard').path}?{urlencode(params)}#action-required"

    def progress_page_url(target_page: int) -> str:
        params = dict(request.query_params)
        params["progress_page"] = str(target_page)
        return f"{request.url_for('dashboard').path}?{urlencode(params)}#actions-in-progress"

    first_page = max(1, current_page - 2)
    last_page = min(total_pages, first_page + 4)
    first_page = max(1, last_page - 4)
    progress_first_page = max(1, current_progress_page - 2)
    progress_last_page = min(progress_total_pages, progress_first_page + 4)
    progress_first_page = max(1, progress_last_page - 4)

    return request.app.state.templates.TemplateResponse(request, "dashboard.html", {
        "priorities": priorities,
        "prenotice_priorities": prenotice_priorities,
        "bid_priorities": bid_priorities,
        "prenotice_action_total": prenotice_action_total,
        "bid_action_total": bid_action_total,
        "in_progress": in_progress,
        "action_total": action_total,
        "progress_total": progress_total,
        "actioned_today": actioned_today,
        "collection_window": window,
        "summary_flow": summary_flow,
        "confirmed_use_notices": confirmed_use_notices,
        "format_datetime": format_datetime,
        "pagination": {
            "page": current_page,
            "page_size": page_size,
            "total": action_total,
            "total_pages": total_pages,
            "pages": range(first_page, last_page + 1),
            "previous_url": page_url(current_page - 1) if current_page > 1 else None,
            "next_url": page_url(current_page + 1) if current_page < total_pages else None,
            "page_url": page_url,
        },
        "progress_pagination": {
            "page": current_progress_page,
            "page_size": page_size,
            "total": progress_total,
            "total_pages": progress_total_pages,
            "pages": range(progress_first_page, progress_last_page + 1),
            "previous_url": progress_page_url(current_progress_page - 1) if current_progress_page > 1 else None,
            "next_url": progress_page_url(current_progress_page + 1) if current_progress_page < progress_total_pages else None,
            "page_url": progress_page_url,
        },
    })
