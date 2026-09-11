from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Attachment, Notice, NoticeDecision


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    metrics = {
        "today": db.scalar(select(func.count(Notice.id)).where(Notice.created_at >= today)) or 0,
        "deep": db.scalar(select(func.count(NoticeDecision.id))) or 0,
        "priority": db.scalar(select(func.count(NoticeDecision.id)).where(NoticeDecision.recommended_action == "contact")) or 0,
        "failed": db.scalar(select(func.count(Attachment.id)).where(Attachment.parse_status.in_(["failed", "unsupported"]))) or 0,
    }
    grade_rows = db.execute(select(NoticeDecision.final_grade, func.count()).group_by(NoticeDecision.final_grade)).all()
    recent = db.execute(
        select(func.date(Notice.created_at), func.count()).where(Notice.created_at >= now - timedelta(days=7))
        .group_by(func.date(Notice.created_at)).order_by(func.date(Notice.created_at))
    ).all()
    priorities = db.scalars(
        select(Notice).join(NoticeDecision).where(NoticeDecision.recommended_action == "contact")
        .order_by(NoticeDecision.priority_score.desc()).limit(8)
    ).all()
    return request.app.state.templates.TemplateResponse(request, "dashboard.html", {
        "metrics": metrics, "grades": dict(grade_rows), "recent": recent, "priorities": priorities,
    })
