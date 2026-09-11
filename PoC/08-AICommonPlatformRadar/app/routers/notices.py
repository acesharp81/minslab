from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..models import Attachment, Notice, NoticeDecision
from ..services.analyzer import analyze_notice
from ..services.parser import parse_bytes


router = APIRouter()


def _loads(value: str | None) -> list:
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except json.JSONDecodeError:
        return []


def _notice_dict(notice: Notice) -> dict:
    decision = notice.decision
    action = notice.action
    return {
        "id": notice.id, "stage": notice.stage, "notice_no": notice.notice_no,
        "title": notice.title, "agency_name": notice.agency_name, "budget_amount": notice.budget_amount,
        "posted_at": notice.posted_at, "deadline_at": notice.deadline_at, "url": notice.url,
        "decision": None if not decision else {
            "final_grade": decision.final_grade, "ai_relevance": decision.ai_relevance,
            "common_platform_fit": decision.common_platform_fit, "usage_mentioned": decision.usage_mentioned,
            "priority_score": decision.priority_score, "recommended_action": decision.recommended_action,
            "summary": decision.summary, "possible_functions": _loads(decision.possible_functions_json),
            "evidence": _loads(decision.key_evidence_json), "check_questions": _loads(decision.check_questions_json),
            "caveats": _loads(decision.caveats_json),
        },
        "action": None if not action else {"id": action.id, "status": action.status, "owner": action.owner, "memo": action.memo},
        "attachments": [{
            "id": item.id, "original_filename": item.original_filename, "file_size": item.file_size,
            "download_status": item.download_status, "parse_status": item.parse_status, "parse_error": item.parse_error,
            "text_excerpt": item.text_excerpt,
        } for item in notice.attachments],
    }


def _query(
    *, stage: str | None, agency: str | None, grade: str | None, action_status: str | None,
    keyword: str | None, date_from: date | None, date_to: date | None,
):
    statement = select(Notice).options(
        selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action)
    ).outerjoin(NoticeDecision)
    if stage:
        statement = statement.where(Notice.stage == stage)
    if agency:
        statement = statement.where(Notice.agency_name.contains(agency))
    if grade:
        statement = statement.where(NoticeDecision.final_grade == grade)
    if action_status:
        statement = statement.where(Notice.action.has(status=action_status))
    if keyword:
        statement = statement.where(or_(Notice.title.contains(keyword), Notice.agency_name.contains(keyword)))
    if date_from:
        statement = statement.where(Notice.posted_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        statement = statement.where(Notice.posted_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    return statement.order_by(NoticeDecision.priority_score.desc().nullslast(), Notice.created_at.desc())


@router.get("/notices", response_class=HTMLResponse)
def notices_page(
    request: Request, stage: str | None = None, agency: str | None = None, grade: str | None = None,
    action_status: str | None = None, keyword: str | None = None,
    date_from: date | None = None, date_to: date | None = None, db: Session = Depends(get_db),
):
    notices = db.scalars(_query(stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword, date_from=date_from, date_to=date_to).limit(500)).all()
    return request.app.state.templates.TemplateResponse(request, "notices.html", {"notices": notices})


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action), selectinload(Notice.analysis_runs)
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return request.app.state.templates.TemplateResponse(request, "notice_detail.html", {
        "notice": notice, "decision_data": _notice_dict(notice).get("decision"),
    })


@router.get("/api/notices")
def notices_api(
    stage: str | None = None, agency: str | None = None, grade: str | None = None,
    action_status: str | None = None, keyword: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
):
    rows = db.scalars(_query(stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword, date_from=date_from, date_to=date_to).limit(limit)).all()
    return {"items": [_notice_dict(row) for row in rows], "count": len(rows)}


@router.get("/api/notices/{notice_id}")
def notice_api(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action)
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return _notice_dict(notice)


@router.post("/api/notices/{notice_id}/parse")
def reparse_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(selectinload(Notice.attachments)))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    stats = {"parsed": 0, "failed": 0, "unsupported": 0}
    for attachment in notice.attachments:
        if not attachment.file_path:
            stats["failed"] += 1
            continue
        path = get_settings().project_root / attachment.file_path
        result = parse_bytes(path.read_bytes(), attachment.file_ext or "")
        attachment.parse_status, attachment.parse_error = result.status, result.error
        if result.status == "parsed":
            text_path = get_settings().parsed_dir / f"{attachment.sha256}.txt"
            text_path.write_text(result.text, encoding="utf-8")
            attachment.text_path = str(text_path.relative_to(get_settings().project_root))
            attachment.text_excerpt = result.text[:20_000]
        stats[result.status] = stats.get(result.status, 0) + 1
    db.commit()
    return stats


@router.post("/api/notices/{notice_id}/analyze/simple")
def analyze_simple(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(selectinload(Notice.attachments)))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return analyze_notice(db, notice, deep=False, force=True).model_dump()


@router.post("/api/notices/{notice_id}/analyze/deep")
def analyze_deep(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action)
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return analyze_notice(db, notice, deep=True, force=True).model_dump()

