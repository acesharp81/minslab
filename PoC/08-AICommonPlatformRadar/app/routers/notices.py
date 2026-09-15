from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import AnalysisRun, Attachment, Notice, NoticeDecision
from ..services.analyzer import (
    CLASSIFICATION_LABELS, CURRENT_CRITERIA_VERSION, analyze_notice, is_current_deep_result,
)
from ..services.attachment_policy import select_preferred_documents
from ..services.collector import parse_preferred_attachments
from ..services.workflow_view import (
    analysis_trace, current_classification_run, current_deep_success, workflow_summary,
)


router = APIRouter()
KST = timezone(timedelta(hours=9))
ANALYSIS_LABELS = {
    "deep_completed": "3차 심층 완료",
    "criteria_outdated": "기준 갱신 필요",
    "deep_pending": "3차 심층 대기",
    "simple_completed": "2차 검토 완료",
    "screened_out": "규칙 제외",
    "failed": "분석 실패",
    "unanalyzed": "미분석",
}
GATE_LABELS = {
    "eligibility": {
        "eligible": "직접 이용 가능", "consultation_required": "별도 협의 필요",
        "ineligible": "기본조건 부적합", "uncertain": "확인 필요",
    },
    "network": {
        "internal_or_connected": "내부·업무망 또는 연계", "hybrid": "내·외부망 혼합",
        "external_complete": "외부망 완결", "unclear": "망 구성 미확인",
    },
    "task": {
        "government": "정부 행정사무", "delegated_government": "위탁 국가사무",
        "public_institution_internal": "공공기관 자체 내부업무",
        "non_government": "비국가사무", "unclear": "국가사무 여부 미확인",
    },
    "model": {
        "platform_llm_or_rag": "공통 LLM·RAG로 처리 가능",
        "custom_model_or_full_finetuning": "독자모델·풀파인튜닝 협의",
        "unclear": "모델 요구 미확인",
    },
    "usage": {
        "uses": "공통기반 사용 명시", "not_used": "미사용 명시",
        "not_mentioned": "사용 문구 없음", "unclear": "사용 여부 미확인",
    },
    "remediation": {
        "feasible": "망·모델 변경 가능", "not_feasible": "변경 곤란",
        "unclear": "변경 가능성 미확인", "not_needed": "변경 불필요",
    },
}


def _loads(value: str | None) -> list:
    try:
        result = json.loads(value or "[]")
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


def _result(value: str | None) -> dict:
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def format_datetime(value: datetime | None) -> str:
    if not value:
        return "미상"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).strftime("%Y-%m-%d %H:%M")


def deadline_label(value: datetime | None) -> str:
    if not value:
        return "마감 미상"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    seconds = (value - datetime.now(timezone.utc)).total_seconds()
    if seconds < 0:
        return "마감"
    days = int(seconds // 86400)
    return "D-Day" if days == 0 else f"D-{days}"


def analysis_view(notice: Notice) -> dict:
    runs = sorted(notice.analysis_runs, key=lambda row: row.id or 0)
    latest_simple = next((row for row in reversed(runs) if row.run_type == "simple_ai"), None)
    latest_deep = next((row for row in reversed(runs) if row.run_type == "deep_ai"), None)
    classification_run = current_classification_run(notice)
    deep_success = current_deep_success(notice)
    run = classification_run or latest_deep or latest_simple
    key = "unanalyzed"
    if classification_run:
        key = "deep_completed" if deep_success else "screened_out"
    elif latest_deep and latest_deep.status == "skipped" and latest_deep.model_name == "daily-quota-guard":
        key = "deep_pending"
    elif latest_deep and (
        latest_deep.status == "success"
        or (latest_deep.status == "skipped" and latest_deep.model_name == "rule-gate")
    ):
        key = "criteria_outdated"
    elif run and run.status == "failed":
        key = "failed"
    elif latest_simple and latest_simple.status == "success":
        key = "simple_completed"
        run = latest_simple
    result = _result(run.result_json) if run else {}
    classification_ready = bool(classification_run)
    classification_code = result.get("classification_code") if classification_ready else None
    retry_error = None
    if classification_run and latest_deep and (latest_deep.id or 0) > (classification_run.id or 0) and latest_deep.status == "failed":
        retry_error = latest_deep.error_message
    return {
        "key": key,
        "label": ANALYSIS_LABELS[key],
        "model_name": run.model_name if run else None,
        "created_at": run.created_at if run else None,
        "confidence": run.confidence if run else None,
        "result": result,
        "classification_code": classification_code,
        "classification_label": CLASSIFICATION_LABELS.get(classification_code, "미분류"),
        "error": retry_error or (run.error_message if run and run.status == "failed" else None),
    }


def _notice_dict(notice: Notice, *, include_text: bool = True) -> dict:
    decision = notice.decision
    action = notice.action
    business_attachments = select_preferred_documents(
        notice.attachments, name=lambda row: row.original_filename
    )
    return {
        "id": notice.id, "stage": notice.stage, "notice_no": notice.notice_no,
        "title": notice.title, "agency_name": notice.agency_name, "budget_amount": notice.budget_amount,
        "posted_at": notice.posted_at, "deadline_at": notice.deadline_at, "url": notice.url,
        "analysis": analysis_view(notice),
        "decision": None if not decision else {
            "final_grade": decision.final_grade, "ai_relevance": decision.ai_relevance,
            "common_platform_fit": decision.common_platform_fit, "usage_mentioned": decision.usage_mentioned,
            "priority_score": decision.priority_score, "recommended_action": decision.recommended_action,
            "summary": decision.summary, "possible_functions": _loads(decision.possible_functions_json),
            "evidence": _loads(decision.key_evidence_json), "check_questions": _loads(decision.check_questions_json),
            "caveats": _loads(decision.caveats_json),
        },
        "action": None if not action else {"id": action.id, "status": action.status, "owner": action.owner, "memo": action.memo},
        "attachments": [
            {
                "id": item.id,
                "original_filename": item.original_filename,
                "file_size": item.file_size,
                "download_status": item.download_status,
                "parse_status": item.parse_status,
                "parse_error": item.parse_error,
                **({"text_excerpt": item.text_excerpt} if include_text else {}),
            }
            for item in business_attachments
        ],
    }


def _query(
    *, stage: str | None, agency: str | None, grade: str | None, action_status: str | None,
    keyword: str | None, date_from: date | None, date_to: date | None,
    analysis_status: str | None = None, ai_relevance: str | None = None,
    deadline_status: str | None = None, recommended_action: str | None = None,
    parse_status: str | None = None, sort: str | None = None, classification_code: str | None = None,
):
    def json_string_value(key: str, value: str):
        # result_json은 JSON Text 컬럼이다. json.dumps 기본 공백 형식과
        # compact 형식(기존/테스트 데이터)을 모두 지원한다.
        return or_(
            AnalysisRun.result_json.contains(f'"{key}":"{value}"'),
            AnalysisRun.result_json.contains(f'"{key}": "{value}"'),
        )

    current_result = json_string_value("criteria_version", CURRENT_CRITERIA_VERSION)
    current_rule_gate = and_(
        AnalysisRun.run_type == "deep_ai", AnalysisRun.status == "skipped",
        AnalysisRun.model_name == "rule-gate", current_result,
    )
    current_terminal = or_(
        and_(AnalysisRun.run_type == "deep_ai", AnalysisRun.status == "success", current_result),
        current_rule_gate,
    )
    statement = select(Notice).options(
        selectinload(Notice.attachments), selectinload(Notice.decision),
        selectinload(Notice.action), selectinload(Notice.analysis_runs),
    ).outerjoin(NoticeDecision)
    if stage:
        statement = statement.where(Notice.stage == stage)
    if agency:
        statement = statement.where(Notice.agency_name.contains(agency))
    if grade:
        statement = statement.where(NoticeDecision.final_grade == grade)
    if ai_relevance:
        statement = statement.where(NoticeDecision.ai_relevance == ai_relevance)
    if recommended_action:
        statement = statement.where(NoticeDecision.recommended_action == recommended_action)
    if classification_code:
        statement = statement.where(Notice.analysis_runs.any(and_(
            AnalysisRun.run_type == "deep_ai",
            or_(AnalysisRun.status == "success", and_(
                AnalysisRun.status == "skipped", AnalysisRun.model_name == "rule-gate",
            )),
            current_result,
            json_string_value("classification_code", classification_code),
        )))
    if action_status:
        statement = statement.where(Notice.action.has(status=action_status))
    if keyword:
        statement = statement.where(or_(
            Notice.title.contains(keyword), Notice.agency_name.contains(keyword), Notice.notice_no.contains(keyword),
        ))
    if date_from:
        statement = statement.where(Notice.posted_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to:
        statement = statement.where(Notice.posted_at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc))
    now = datetime.now(timezone.utc)
    if deadline_status == "open":
        statement = statement.where(Notice.deadline_at >= now)
    elif deadline_status == "closed":
        statement = statement.where(Notice.deadline_at < now)
    elif deadline_status == "unknown":
        statement = statement.where(Notice.deadline_at.is_(None))
    if parse_status == "issue":
        statement = statement.where(Notice.attachments.any(
            (Attachment.parse_status.in_(("failed", "unsupported"))) |
            (Attachment.download_status == "failed")
        ))
    elif parse_status:
        statement = statement.where(Notice.attachments.any(Attachment.parse_status == parse_status))

    deep_success = and_(
        AnalysisRun.run_type == "deep_ai", AnalysisRun.status == "success",
        current_result,
    )
    legacy_deep_terminal = and_(
        AnalysisRun.run_type == "deep_ai",
        or_(
            AnalysisRun.status == "success",
            and_(AnalysisRun.status == "skipped", AnalysisRun.model_name == "rule-gate"),
        ),
        ~current_result,
    )
    simple_success = and_(AnalysisRun.run_type == "simple_ai", AnalysisRun.status == "success")
    if analysis_status == "deep_completed":
        statement = statement.where(Notice.analysis_runs.any(deep_success))
    elif analysis_status == "criteria_outdated":
        statement = statement.where(
            Notice.analysis_runs.any(legacy_deep_terminal),
            ~Notice.analysis_runs.any(current_terminal),
        )
    elif analysis_status == "deep_pending":
        statement = statement.where(Notice.analysis_runs.any(and_(
            AnalysisRun.run_type == "deep_ai", AnalysisRun.status == "skipped",
            AnalysisRun.model_name == "daily-quota-guard",
        )))
    elif analysis_status == "simple_completed":
        statement = statement.where(Notice.analysis_runs.any(simple_success), ~Notice.analysis_runs.any(current_terminal))
    elif analysis_status == "screened_out":
        statement = statement.where(Notice.analysis_runs.any(current_rule_gate))
    elif analysis_status == "failed":
        statement = statement.where(Notice.analysis_runs.any(AnalysisRun.status == "failed"))
    elif analysis_status == "unanalyzed":
        statement = statement.where(~Notice.analysis_runs.any(simple_success))

    if sort == "deadline":
        return statement.order_by(Notice.deadline_at.asc().nullslast(), Notice.created_at.desc())
    if sort == "budget":
        return statement.order_by(Notice.budget_amount.desc().nullslast(), Notice.created_at.desc())
    if sort == "newest":
        return statement.order_by(Notice.posted_at.desc().nullslast(), Notice.created_at.desc())
    return statement.order_by(NoticeDecision.priority_score.desc().nullslast(), Notice.posted_at.desc().nullslast())


@router.get("/notices", response_class=HTMLResponse)
def notices_page(
    request: Request, stage: str | None = None, agency: str | None = None, grade: str | None = None,
    action_status: str | None = None, keyword: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    analysis_status: str | None = None, ai_relevance: str | None = None,
    deadline_status: str | None = None, recommended_action: str | None = None,
    parse_status: str | None = None, sort: str | None = None, classification_code: str | None = None,
    db: Session = Depends(get_db),
):
    query = _query(
        stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword,
        date_from=date_from, date_to=date_to, analysis_status=analysis_status,
        ai_relevance=ai_relevance, deadline_status=deadline_status,
        recommended_action=recommended_action, parse_status=parse_status, sort=sort,
        classification_code=classification_code,
    )
    notices = db.scalars(query.limit(500)).all()
    return request.app.state.templates.TemplateResponse(request, "notices.html", {
        "notice_rows": [{"notice": row, "analysis": analysis_view(row)} for row in notices],
        "format_datetime": format_datetime, "deadline_label": deadline_label,
    })


@router.get("/notices/{notice_id}", response_class=HTMLResponse)
def notice_detail(request: Request, notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision),
        selectinload(Notice.action), selectinload(Notice.analysis_runs),
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    workflow = workflow_summary(notice)
    return request.app.state.templates.TemplateResponse(request, "notice_detail.html", {
        "notice": notice,
        "business_attachments": select_preferred_documents(notice.attachments, name=lambda row: row.original_filename),
        "decision_data": _notice_dict(notice).get("decision"),
        "analysis": analysis_view(notice), "format_datetime": format_datetime,
        "deadline_label": deadline_label, "gate_labels": GATE_LABELS,
        "workflow": workflow, "analysis_trace": analysis_trace(notice),
    })


@router.get("/api/notices")
def notices_api(
    stage: str | None = None, agency: str | None = None, grade: str | None = None,
    action_status: str | None = None, keyword: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    analysis_status: str | None = None, ai_relevance: str | None = None,
    deadline_status: str | None = None, recommended_action: str | None = None,
    parse_status: str | None = None, sort: str | None = None, classification_code: str | None = None,
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
):
    query = _query(
        stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword,
        date_from=date_from, date_to=date_to, analysis_status=analysis_status,
        ai_relevance=ai_relevance, deadline_status=deadline_status,
        recommended_action=recommended_action, parse_status=parse_status, sort=sort,
        classification_code=classification_code,
    )
    rows = db.scalars(query.limit(limit)).all()
    return {"items": [_notice_dict(row, include_text=False) for row in rows], "count": len(rows)}


@router.get("/api/notices/{notice_id}")
def notice_api(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision),
        selectinload(Notice.action), selectinload(Notice.analysis_runs),
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return _notice_dict(notice)


@router.post("/api/notices/{notice_id}/parse")
def reparse_notice(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(selectinload(Notice.attachments)))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    statuses = parse_preferred_attachments(db, notice, force=True)
    db.commit()
    return {
        status: sum(value == status for value in statuses.values())
        for status in ("parsed", "failed", "unsupported", "skipped", "skipped_duplicate")
    }


@router.post("/api/notices/{notice_id}/analyze/simple")
def analyze_simple(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(selectinload(Notice.attachments)))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return analyze_notice(db, notice, deep=False, force=True).model_dump()


@router.post("/api/notices/{notice_id}/analyze/deep")
def analyze_deep(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action),
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    return analyze_notice(db, notice, deep=True, force=True).model_dump()
