from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..db import get_db
from ..models import AnalysisRun, Attachment, Notice, NoticeDecision
from ..services.analyzer import (
    CLASSIFICATION_LABELS,
    CURRENT_CRITERIA_VERSION,
    analyze_notice,
)
from ..services.attachment_policy import select_preferred_documents
from ..services.collector import parse_preferred_attachments
from ..services.opinion_tracker import refresh_notice_opinions
from ..services.platform_usage import with_usage_presentation
from ..services.ineligible_reasons import INELIGIBLE_REASON_META, manual_ineligible_reason
from ..services.workflow_view import (
    current_classification_run,
    current_deep_success,
    workflow_summary,
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
        "ineligible": "명시적 기본조건 부적합", "uncertain": "확인 필요",
    },
    "network": {
        "internal_or_connected": "내부·업무망 또는 연계", "hybrid": "내·외부망 혼합",
        "other_closed_network": "별도 폐쇄망·행정망 연계 확인", "external_complete": "외부망 완결", "unclear": "망 구성 미확인",
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


_AI_EVIDENCE_MARKER = re.compile(
    r"(?<![A-Za-z])AI(?![A-Za-z])|\bLLM\b|\bRAG\b|인공지능|생성형\s*AI|"
    r"머신러닝|딥러닝|자연어\s*처리|컴퓨터\s*비전|지능형\s*(?:분석|검색|상담|서비스|시스템)",
    re.I,
)
_GATE_EVIDENCE_FIELDS = (
    ("망·데이터", "network_evidence"),
    ("국가사무", "task_scope_evidence"),
    ("모델·기능", "model_fit_evidence"),
    ("공통기반 사용 여부", "platform_usage_evidence"),
    ("망·모델 보완 가능성", "remediation_evidence"),
)


def _evidence_items(value) -> list[dict]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if not isinstance(item, dict) or not str(item.get("quote") or "").strip():
            continue
        result.append({
            "quote": str(item.get("quote") or "").strip(),
            "section": str(item.get("section") or "원문").strip(),
            "interpretation": str(item.get("interpretation") or "직접 확인된 문구").strip(),
        })
    return result


def analysis_source_evidence(
    notice: Notice, result: dict, decision_data: dict | None = None,
) -> dict:
    """Build an operator view from the audited stage-2 and stage-3 evidence."""
    ordered = sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
    simple_run = next((
        row for row in ordered if row.run_type == "simple_ai" and row.status == "success"
    ), None)
    simple = _result(simple_run.result_json) if simple_run else {}
    ai_evidence = _evidence_items(simple.get("evidence"))

    if not ai_evidence:
        candidates = [("사업명", notice.title or "")]
        for attachment in notice.attachments:
            excerpt = str(attachment.text_excerpt or "")
            candidates.extend(
                (attachment.original_filename or "사업 문서", part.strip())
                for part in re.split(r"[\n。]+", excerpt)
                if part.strip()
            )
        for section, text in candidates:
            if _AI_EVIDENCE_MARKER.search(text):
                ai_evidence.append({
                    "quote": text[:1200], "section": section,
                    "interpretation": "AI 도입·구축·활용 사업으로 판단한 직접 문구",
                })
            if len(ai_evidence) >= 3:
                break

    gate_evidence: list[dict] = []
    for gate, field in _GATE_EVIDENCE_FIELDS:
        for item in _evidence_items(result.get(field)):
            gate_evidence.append({**item, "gate": gate})

    questions = []
    for value in (
        list(result.get("check_questions") or [])
        + list((decision_data or {}).get("check_questions") or [])
    ):
        text = str(value or "").strip()
        if text and text not in questions:
            questions.append(text)

    def add_question(text: str, *covered_by: str) -> None:
        if covered_by and any(
            any(marker.casefold() in existing.casefold() for marker in covered_by)
            for existing in questions
        ):
            return
        if text not in questions:
            questions.append(text)

    code = str(result.get("classification_code") or "")
    ai_relevance = str(result.get("ai_relevance") or "")
    if ai_relevance in {"high", "medium"} and not ai_evidence:
        add_question("AI를 실제 도입·구축·활용하는 사업인지와 적용할 AI 기능을 담당자에게 확인 필요", "AI 기능", "인공지능 기능")
    if result.get("network_scope") == "unclear":
        add_question("서비스와 데이터가 행정망·업무망·내부망에서 처리되거나 해당 망과 연계되는지 확인 필요", "행정망", "업무망", "내부망")
    elif result.get("network_scope") == "other_closed_network":
        add_question("해당 폐쇄망이 행정망·업무망과 연계 가능한지와 데이터 처리 경계를 확인 필요", "폐쇄망")
    if result.get("task_scope") == "unclear":
        add_question("주무부처·지방정부 및 국가사무·위탁사무 근거를 담당자에게 확인 필요", "국가사무", "위탁사무", "주무부처")
    if result.get("model_fit") == "unclear":
        add_question("공통기반 제공 LLM·RAG로 처리 가능한 기능과 별도 모델 필요 여부를 확인 필요", "별도 모델", "LLM·RAG", "풀파인튜닝")
    elif result.get("model_fit") == "custom_model_or_full_finetuning":
        add_question("독자모델·풀파인튜닝을 공개 파운데이션 모델 또는 RAG로 대체할 수 있는지 확인 필요", "독자모델", "풀파인튜닝")
    if code in {"2", "3", "4"} and result.get("platform_usage") in {"unclear", "not_mentioned", None}:
        add_question("범정부 인공지능 공통기반을 실제 적용·연계할 계획인지 확인 필요", "실제 적용", "활용할 계획", "연계할 계획")
    questions = list(dict.fromkeys(questions))
    return {
        "ai_evidence": ai_evidence[:5],
        "gate_evidence": gate_evidence[:20],
        "questions": questions[:20],
    }


def _json_string_value(column, key: str, value: str):
    """Match JSON text written with either compact or default separators."""
    return or_(
        column.contains(f'"{key}":"{value}"'),
        column.contains(f'"{key}": "{value}"'),
    )


def current_classification_condition(codes: set[str]):
    """Match only the latest current classification without loading run history."""
    latest = aliased(AnalysisRun)
    latest_is_terminal = and_(
        latest.run_type == "deep_ai",
        or_(
            latest.status == "success",
            and_(latest.status == "skipped", latest.model_name == "rule-gate"),
        ),
        _json_string_value(
            latest.result_json, "criteria_version", CURRENT_CRITERIA_VERSION,
        ),
    )
    latest_id = (
        select(func.max(latest.id))
        .where(latest.notice_id == Notice.id, latest_is_terminal)
        .correlate(Notice)
        .scalar_subquery()
    )
    code_match = or_(*(
        _json_string_value(AnalysisRun.result_json, "classification_code", code)
        for code in sorted(codes)
    ))
    has_latest_code = Notice.analysis_runs.any(and_(
        AnalysisRun.id == latest_id,
        code_match,
    ))
    has_later_simple = Notice.analysis_runs.any(and_(
        AnalysisRun.run_type == "simple_ai",
        AnalysisRun.status == "success",
        AnalysisRun.id > latest_id,
    ))
    return and_(has_latest_code, ~has_later_simple)


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
    result = with_usage_presentation(_result(run.result_json)) if run else {}
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
    action_required: bool | None = None,
):
    def json_string_value(key: str, value: str):
        return _json_string_value(AnalysisRun.result_json, key, value)

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
        statement = statement.where(current_classification_condition({classification_code}))
    if action_required:
        statement = statement.where(current_classification_condition({"2", "3", "4"}))
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
    action_required: bool | None = None, page: int = Query(1, ge=1),
    db: Session = Depends(get_db),
):
    query = _query(
        stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword,
        date_from=date_from, date_to=date_to, analysis_status=analysis_status,
        ai_relevance=ai_relevance, deadline_status=deadline_status,
        recommended_action=recommended_action, parse_status=parse_status, sort=sort,
        classification_code=classification_code, action_required=action_required,
    )
    page_size = 10
    total = int(db.scalar(
        select(func.count()).select_from(query.order_by(None).subquery())
    ) or 0)
    total_pages = max(1, math.ceil(total / page_size))
    current_page = min(page, total_pages)
    notices = db.scalars(
        query.offset((current_page - 1) * page_size).limit(page_size)
    ).all()

    def page_url(target_page: int) -> str:
        params = dict(request.query_params)
        params["page"] = str(target_page)
        return f"{request.url_for('notices_page').path}?{urlencode(params)}"

    first_page = max(1, current_page - 2)
    last_page = min(total_pages, first_page + 4)
    first_page = max(1, last_page - 4)
    return request.app.state.templates.TemplateResponse(request, "notices.html", {
        "notice_rows": [
            {"notice": row, "analysis": analysis_view(row), "workflow": workflow_summary(row)}
            for row in notices
        ],
        "format_datetime": format_datetime, "deadline_label": deadline_label,
        "pagination": {
            "page": current_page, "page_size": page_size, "total": total,
            "total_pages": total_pages, "pages": range(first_page, last_page + 1),
            "previous_url": page_url(current_page - 1) if current_page > 1 else None,
            "next_url": page_url(current_page + 1) if current_page < total_pages else None,
            "page_url": page_url,
        },
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
    analysis = analysis_view(notice)
    decision_data = _notice_dict(notice).get("decision")
    return request.app.state.templates.TemplateResponse(request, "notice_detail.html", {
        "notice": notice,
        "business_attachments": select_preferred_documents(notice.attachments, name=lambda row: row.original_filename),
        "decision_data": decision_data,
        "source_evidence": analysis_source_evidence(notice, analysis.get("result") or {}, decision_data),
        "analysis": analysis, "format_datetime": format_datetime,
        "deadline_label": deadline_label, "gate_labels": GATE_LABELS,
        "workflow": workflow,
        "ineligible_reason_options": INELIGIBLE_REASON_META,
        "manual_ineligible_reason": manual_ineligible_reason(notice),
    })


@router.get("/api/notices")
def notices_api(
    stage: str | None = None, agency: str | None = None, grade: str | None = None,
    action_status: str | None = None, keyword: str | None = None,
    date_from: date | None = None, date_to: date | None = None,
    analysis_status: str | None = None, ai_relevance: str | None = None,
    deadline_status: str | None = None, recommended_action: str | None = None,
    parse_status: str | None = None, sort: str | None = None, classification_code: str | None = None,
    action_required: bool | None = None,
    limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
):
    query = _query(
        stage=stage, agency=agency, grade=grade, action_status=action_status, keyword=keyword,
        date_from=date_from, date_to=date_to, analysis_status=analysis_status,
        ai_relevance=ai_relevance, deadline_status=deadline_status,
        recommended_action=recommended_action, parse_status=parse_status, sort=sort,
        classification_code=classification_code, action_required=action_required,
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


@router.post("/api/notices/{notice_id}/opinions/refresh")
async def refresh_opinions(notice_id: int, db: Session = Depends(get_db)):
    notice = db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.action), selectinload(Notice.analysis_runs),
    ))
    if not notice:
        raise HTTPException(404, "공고를 찾을 수 없습니다.")
    if notice.stage != "prenotice":
        raise HTTPException(400, "사전규격 공고만 의견 답변을 확인할 수 있습니다.")
    try:
        return await refresh_notice_opinions(db, notice)
    except Exception as exc:
        db.rollback()
        raise HTTPException(502, f"나라장터 의견 답변 확인에 실패했습니다: {type(exc).__name__}") from None
