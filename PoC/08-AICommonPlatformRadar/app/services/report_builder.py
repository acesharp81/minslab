from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Notice, PipelineRun
from .workflow_view import (
    ACTION_REQUIRED_CODES, current_classification_run, current_deep_success, workflow_summary,
)
from .attachment_policy import is_business_document, select_preferred_documents
from .analyzer import CLASSIFICATION_LABELS, CURRENT_CRITERIA_VERSION, is_current_deep_result
from .collector import is_explicit_ai_title


KST = timezone(timedelta(hours=9))
ACTIVE_ACTIONS = {"new", "reviewing", "in_progress", "contacted", "not_reflected"}
ELIGIBILITY_LABELS = {
    "eligible": "직접 이용 가능",
    "consultation_required": "별도 협의 필요",
    "ineligible": "명시적 기본조건 부적합",
    "uncertain": "확인 필요",
}
NETWORK_LABELS = {
    "internal_or_connected": "내부·업무망 또는 연계",
    "hybrid": "내·외부망 혼합",
    "other_closed_network": "별도 폐쇄망·행정망 연계 확인",
    "external_complete": "외부망 완결",
    "unclear": "망 구성 미확인",
}
TASK_LABELS = {
    "government": "정부 행정사무",
    "delegated_government": "위탁 국가사무",
    "public_institution_internal": "공공기관 자체 내부업무",
    "non_government": "비국가사무",
    "unclear": "국가사무 여부 미확인",
}
MODEL_LABELS = {
    "platform_llm_or_rag": "공통 LLM·RAG로 처리 가능",
    "custom_model_or_full_finetuning": "독자모델·풀파인튜닝 협의",
    "unclear": "모델 요구 미확인",
}


@dataclass(frozen=True)
class ReportArtifact:
    report_date: date
    generated_at: str
    status: str
    finalized: bool
    markdown_path: str
    html_path: str
    json_path: str
    summary: dict
    data: dict

    def as_dict(self, *, include_markdown: bool = False) -> dict:
        result = {
            "date": self.report_date.isoformat(), "generated_at": self.generated_at,
            "status": self.status, "finalized": self.finalized,
            "criteria_version": self.data["criteria_version"], "summary": self.summary,
            "batch": self.data["batch"], "processing": self.data["processing"],
            "workflow": self.data["workflow"], "action_outcomes": self.data["action_outcomes"],
            "monthly": self.data["monthly"], "recent": self.data["recent"],
            "priority_items": self.data["priority_items"],
            "uncertain_items": self.data["uncertain_items"], "failures": self.data["failures"],
            "pipeline_failures": self.data["pipeline_failures"],
            "artifacts": {"markdown": self.markdown_path, "html": self.html_path, "json": self.json_path},
        }
        if include_markdown:
            result["markdown"] = Path(self.markdown_path).read_text(encoding="utf-8")
        return result


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=KST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _month_bounds(day: date) -> tuple[datetime, datetime]:
    start_day = day.replace(day=1)
    next_day = (start_day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return _day_bounds(start_day)[0], _day_bounds(next_day)[0]


def _json_value(value: str | None, fallback):
    try:
        parsed = json.loads(value or "")
        return parsed if isinstance(parsed, type(fallback)) else fallback
    except (json.JSONDecodeError, TypeError):
        return fallback


def _kst_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).isoformat(timespec="seconds")


def _in_range(value: datetime | None, start: datetime, end: datetime) -> bool:
    if value is None:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return start <= value < end


def _kst_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST).date()


def _latest_batch(db: Session, day: date) -> PipelineRun | None:
    start, end = _day_bounds(day)
    base = select(PipelineRun).where(
        PipelineRun.run_kind == "collect", PipelineRun.started_at >= start, PipelineRun.started_at < end,
    )
    successful = db.scalar(base.where(PipelineRun.status == "success").order_by(PipelineRun.started_at.desc()))
    return successful or db.scalar(base.order_by(PipelineRun.started_at.desc()))


def _latest_reconciliation(db: Session, day: date) -> PipelineRun | None:
    start, end = _day_bounds(day)
    return db.scalar(select(PipelineRun).where(
        PipelineRun.run_kind == "analysis_reconcile",
        PipelineRun.status == "success",
        PipelineRun.started_at >= start,
        PipelineRun.started_at < end,
    ).order_by(PipelineRun.started_at.desc()))


def _reconciliation_data(run: PipelineRun | None) -> dict:
    stats = _json_value(run.stats_json, {}) if run else {}
    total = int(stats.get("total", 0) or 0)
    classified = int(stats.get("classified_total", 0) or 0)
    unresolved = int(stats.get("unresolved", total - classified) or 0)
    return {
        "id": run.id if run else None,
        "state": "ready" if run and total > 0 and unresolved == 0 and classified == total else "missing",
        "label": "현재 기준 전량 분석 완료" if run and unresolved == 0 and classified == total else "분석 정산 기록 없음",
        "total": total, "classified": classified, "unresolved": unresolved,
        "current_simple": int(stats.get("current_simple", 0) or 0),
        "deep_candidates": int(stats.get("deep_candidates", 0) or 0),
        "categories": stats.get("classification_distribution", {}),
        "finished_at": _kst_text(run.finished_at) if run else None,
    }


def _batch_data(run: PipelineRun | None) -> dict:
    if run is None:
        return {"id": None, "state": "missing", "label": "수집 배치 미실행", "mode": None,
                "started_at": None, "finished_at": None, "stats": {}, "error": None}
    stats = _json_value(run.stats_json, {})
    partial = any(int(stats.get(name, 0) or 0) > 0 for name in (
        "attachment_failed", "analysis_failed", "analysis_deferred",
    ))
    if run.status == "success":
        state, label = ("partial", "일부 실패 포함") if partial else ("ready", "수집·분석 완료")
    elif run.status == "running":
        state, label = "running", "배치 실행 중"
    else:
        state, label = "failed", "배치 실패"
    return {"id": run.id, "state": state, "label": label, "mode": run.mode,
            "started_at": _kst_text(run.started_at), "finished_at": _kst_text(run.finished_at),
            "stats": stats, "error": run.error_message}


def _notice_item(notice: Notice) -> dict:
    decision = notice.decision
    workflow = workflow_summary(notice)
    deep_run = current_deep_success(notice)
    deep_result = _json_value(deep_run.result_json if deep_run else None, {})
    eligibility = deep_result.get("eligibility", "uncertain")
    network_scope = deep_result.get("network_scope", "unclear")
    task_scope = deep_result.get("task_scope", "unclear")
    model_fit = deep_result.get("model_fit", "unclear")
    classification_code = workflow["classification_code"] or deep_result.get("classification_code", "5")
    return {
        "id": notice.id, "title": notice.title, "agency_name": notice.agency_name, "stage": notice.stage,
        "stage_label": "사전규격" if notice.stage == "prenotice" else "본공고",
        "notice_no": notice.notice_no, "posted_at": _kst_text(notice.posted_at),
        "deadline_at": _kst_text(notice.deadline_at), "budget_amount": notice.budget_amount or 0,
        "grade": decision.final_grade if decision else "–",
        "priority_score": decision.priority_score if decision else 0,
        "recommended_action": decision.recommended_action if decision else "manual_review",
        "summary": decision.summary if decision else deep_result.get("summary", "판정 결과를 확인해야 합니다."),
        "functions": _json_value(decision.possible_functions_json, []) if decision else [],
        "evidence": _json_value(decision.key_evidence_json, []) if decision else [],
        "questions": _json_value(decision.check_questions_json, []) if decision else [],
        "caveats": _json_value(decision.caveats_json, []) if decision else [],
        "criteria_version": deep_result.get("criteria_version"),
        "eligibility": eligibility, "eligibility_label": ELIGIBILITY_LABELS.get(eligibility, "확인 필요"),
        "network_scope": network_scope, "network_label": NETWORK_LABELS.get(network_scope, "망 구성 미확인"),
        "task_scope": task_scope, "task_label": TASK_LABELS.get(task_scope, "국가사무 여부 미확인"),
        "model_fit": model_fit, "model_label": MODEL_LABELS.get(model_fit, "모델 요구 미확인"),
        "classification_code": classification_code,
        "classification_label": CLASSIFICATION_LABELS.get(classification_code, "미분류"),
        "guidance_message": workflow["guidance_message"],
        "guidance_sections": workflow["guidance_sections"],
        "action_status": notice.action.status if notice.action else "new",
        "findings": workflow["findings"], "issue_labels": workflow["issue_labels"],
        "opinion_url": workflow["opinion_url"], "action_required": workflow["action_required"],
    }


def _analysis_state(notice: Notice) -> str:
    runs = sorted(notice.analysis_runs, key=lambda row: row.id or 0)
    latest_simple = next((row for row in reversed(runs) if row.run_type == "simple_ai"), None)
    latest_deep = next((row for row in reversed(runs) if row.run_type == "deep_ai"), None)
    classification = current_classification_run(notice)
    if classification:
        return "deep_completed" if current_deep_success(notice) else "screened_out"
    if latest_deep and latest_deep.status == "skipped" and latest_deep.model_name == "daily-quota-guard":
        return "deep_pending"
    if latest_deep and (
        latest_deep.status == "success"
        or (latest_deep.status == "skipped" and latest_deep.model_name == "rule-gate")
    ):
        return "criteria_outdated"
    if (latest_deep or latest_simple) and (latest_deep or latest_simple).status == "failed":
        return "failed"
    if latest_simple and latest_simple.status == "success":
        return "simple_completed"
    return "unanalyzed"


def _markdown(data: dict) -> str:
    workflow = data["workflow"]
    outcomes = data["action_outcomes"]
    summary = data["summary"]
    lines = [
        f"# {data['date']} 공통기반 활용 가능 사업 레이더", "",
        f"> 보고서 상태: **{data['batch']['label']}** · 생성: {data['generated_at']}",
        (
            f"> 현재 분석 정산: **{data['reconciliation']['label']}** · "
            f"분류 {data['reconciliation']['classified']}/{data['reconciliation']['total']}건 · "
            f"미해결 {data['reconciliation']['unresolved']}건"
        ),
        f"> {data['disclaimer']}", "",
        "## 금일 판정 흐름", "",
        (
            f"**신규 수집 {workflow['collected']}건 → 유형 분류 {workflow['classified']}건 "
            f"→ 2차 LLM {workflow['llm_reviewed']}건 → 심층분석 {workflow['deep_completed']}건 "
            f"→ 조치 필요 {workflow['action_needed']}건 → 오늘 조치 {workflow['acted']}건**"
        ), "",
        f"- 규칙 분류 중 비AI 사업: {workflow['non_ai']}건",
        f"- 2차 검토 중 심층분석 필요 판정: {workflow['llm_needed']}건",
        f"- 의견·연락 완료: {outcomes['contacted_today']}건 / 반영 확인: {outcomes['reflected_today']}건",
        f"- 미종결 조치 대상: {outcomes['unresolved']}건", "",
        "## 현재 전체 6개 유형 분류", "",
    ]
    for code, label in CLASSIFICATION_LABELS.items():
        lines.append(f"- {code} · {label}: {summary['classification_distribution'].get(code, 0)}건")

    lines.extend(["", "## 조치 필요 사업", ""])
    if not data["priority_items"]:
        lines.append("미종결 2·3·4유형 조치 대상이 없습니다.")
    for item in data["priority_items"]:
        lines.extend([
            f"### {item['classification_code']}유형 · {item['classification_label']} · {item['title']}", "",
            f"- 기관/단계: {item['agency_name']} / {item['stage_label']}",
            f"- 기간: {item['posted_at'] or '미상'} ~ {item['deadline_at'] or '미상'}",
            f"- 조치 상태: {item['action_status']}",
        ])
        for finding in item["findings"]:
            lines.append(f"- 발견 [{finding['gate']}]: {finding['problem']}")
            lines.append(f"  - 필요 조치: {finding['action']}")
        if item["guidance_message"]:
            lines.append(f"- 의견 문안: {item['guidance_message']}")
        if item["opinion_url"]:
            lines.append(f"- 나라장터/원문: {item['opinion_url']}")
        lines.append("")

    processing = data["processing"]
    lines.extend([
        "## 후속 처리 대기", "",
        f"- 전체 큐(중복 제외): {processing['total']}건",
        f"- 기준 갱신: {processing['criteria_outdated']}건 / 분석 재시도: {processing['analysis_failed']}건",
        f"- AI 명시 미분석: {processing['ai_unanalyzed']}건 / 심층 대기: {processing['deep_pending']}건",
        f"- 문서 재처리: {processing['parse_issues']}건", "",
        "## 오류 및 재처리", "",
    ])
    if not data["failures"] and not data["pipeline_failures"]:
        lines.append("오류 또는 미지원 사업 문서와 배치 오류가 없습니다.")
    for item in data["failures"]:
        lines.append(f"- 첨부 #{item['id']} \\u0060{item['filename']}\\u0060: {item['reason']}")
    for item in data["pipeline_failures"]:
        lines.append(f"- 배치 #{item['id']} \\u0060{item['kind']}\\u0060: {item['error']}")

    monthly = data["monthly"]
    lines.extend([
        "", f"## {data['date'][:7]} 누적", "",
        f"- 수집 {monthly['collected']}건 / 2차 검증 {monthly['simple_verified']}건 / 3차 검증 {monthly['deep_verified']}건",
        f"- 담당자 안내 {monthly['contacted']}건 / 반영 확인 {monthly['reflected']}건",
    ])
    return "\n".join(lines) + "\n"


def _render_html(data: dict) -> str:
    settings = get_settings()
    environment = Environment(loader=FileSystemLoader(str(settings.project_root / "app" / "templates")),
                              autoescape=select_autoescape(("html", "xml")))
    return environment.get_template("daily_report_export.html").render(report=data)


def _artifact_paths(day: date) -> tuple[Path, Path, Path]:
    base = get_settings().reports_dir / f"{day.isoformat()}_daily_report"
    return Path(f"{base}.md"), Path(f"{base}.html"), Path(f"{base}.json")


def load_finalized_report(report_date: date) -> ReportArtifact | None:
    markdown_path, html_path, json_path = _artifact_paths(report_date)
    if not (markdown_path.is_file() and html_path.is_file() and json_path.is_file()):
        return None
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or not data.get("finalized"):
        return None
    required = {
        "workflow", "action_outcomes", "processing", "monthly", "recent",
        "pipeline_failures", "reconciliation",
    }
    if not required.issubset(data) or data.get("criteria_version") != CURRENT_CRITERIA_VERSION:
        return None
    return ReportArtifact(
        report_date=report_date, generated_at=str(data.get("generated_at", "")),
        status=str(data.get("status", "ready")), finalized=True,
        markdown_path=str(markdown_path), html_path=str(html_path), json_path=str(json_path),
        summary=data.get("summary", {}), data=data,
    )


def build_daily_report(db: Session, report_date: date | None = None, *, finalized: bool = False,
                       require_successful_batch: bool = False) -> ReportArtifact:
    settings = get_settings()
    settings.ensure_directories()
    day = report_date or datetime.now(KST).date()
    start, end = _day_bounds(day)
    month_start, month_end = _month_bounds(day)
    batch = _batch_data(_latest_batch(db, day))
    reconciliation = _reconciliation_data(_latest_reconciliation(db, day))
    if require_successful_batch and batch["state"] not in {"ready", "partial"}:
        raise RuntimeError(f"{day.isoformat()} 수집 배치가 완료되지 않아 최종 보고서를 생성하지 않습니다: {batch['label']}")

    notices = db.scalars(select(Notice).options(
        selectinload(Notice.attachments), selectinload(Notice.decision),
        selectinload(Notice.action), selectinload(Notice.analysis_runs),
    )).all()
    new_notices = [notice for notice in notices if _in_range(notice.created_at, start, end)]
    selected = {notice.id: select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
                for notice in new_notices}
    attachments = [item for values in selected.values() for item in values]
    attachments_acquired = sum(item.download_status == "downloaded" for item in attachments)
    parsed_count = sum(item.parse_status == "parsed" for item in attachments)
    all_runs = [run for notice in notices for run in notice.analysis_runs]
    runs_today = [run for run in all_runs if _in_range(run.created_at, start, end)]
    simple_success = [run for run in runs_today if run.run_type == "simple_ai" and run.status == "success"]
    deep_success = [
        run for run in runs_today
        if run.run_type == "deep_ai" and run.status == "success" and is_current_deep_result(run.result_json)
    ]
    classified_runs = [
        run for run in runs_today
        if run.run_type == "deep_ai" and is_current_deep_result(run.result_json)
        and (run.status == "success" or (run.status == "skipped" and run.model_name == "rule-gate"))
    ]
    deep_candidate_ids = set()
    for run in simple_success:
        if _json_value(run.result_json, {}).get("needs_deep_review"):
            deep_candidate_ids.add(run.notice_id)

    states = {notice.id: _analysis_state(notice) for notice in notices}
    workflows = {notice.id: workflow_summary(notice) for notice in notices}
    active_contact = [notice for notice in notices
                      if workflows[notice.id]["classification_code"] in ACTION_REQUIRED_CODES
                      and (not notice.action or notice.action.status in ACTIVE_ACTIONS)]
    active_manual = [notice for notice in notices if states[notice.id] != "criteria_outdated" and notice.decision
                     and notice.decision.recommended_action == "manual_review"
                     and (not notice.action or notice.action.status in ACTIVE_ACTIONS)]
    active_contact.sort(key=lambda row: row.decision.priority_score, reverse=True)
    active_manual.sort(key=lambda row: row.decision.priority_score, reverse=True)
    priority_items = [_notice_item(notice) for notice in active_contact]
    uncertain_items = [_notice_item(notice) for notice in active_manual[:100]]

    failure_attachments = []
    for notice in notices:
        for item in select_preferred_documents(notice.attachments, name=lambda row: row.original_filename):
            if not is_business_document(item.original_filename):
                continue
            if item.download_status not in {"downloaded", "pending"} or item.parse_status in {"failed", "unsupported"}:
                failure_attachments.append(item)
    parse_notice_ids = {item.notice_id for item in failure_attachments}
    failed_ids = {notice.id for notice in notices if states[notice.id] == "failed"}
    ai_unanalyzed_ids = {notice.id for notice in notices if states[notice.id] == "unanalyzed"
                         and is_explicit_ai_title(notice.title)}
    deep_pending_ids = {notice.id for notice in notices if states[notice.id] == "deep_pending"}
    criteria_outdated_ids = {notice.id for notice in notices if states[notice.id] == "criteria_outdated"}
    manual_ids = {notice.id for notice in active_manual}
    contact_ids = {notice.id for notice in active_contact}
    processing_ids = (
        failed_ids | ai_unanalyzed_ids | deep_pending_ids | criteria_outdated_ids |
        manual_ids | contact_ids | parse_notice_ids
    )
    processing = {
        "total": len(processing_ids), "priority_contact": len(contact_ids),
        "analysis_failed": len(failed_ids), "ai_unanalyzed": len(ai_unanalyzed_ids),
        "deep_pending": len(deep_pending_ids), "manual_review": len(manual_ids),
        "criteria_outdated": len(criteria_outdated_ids),
        "parse_issues": len(parse_notice_ids),
    }

    pipeline_failures = []
    pipeline_runs = db.scalars(select(PipelineRun).where(
        PipelineRun.started_at >= start, PipelineRun.started_at < end,
    ).order_by(PipelineRun.started_at.desc())).all()
    for run in pipeline_runs:
        if run.status == "failed" or run.error_message:
            pipeline_failures.append({
                "id": run.id, "kind": run.run_kind, "status": run.status,
                "error": run.error_message or "배치 실패", "started_at": _kst_text(run.started_at),
            })

    month_notices = {notice.id for notice in notices if _in_range(notice.created_at, month_start, month_end)}
    month_simple = {run.notice_id for run in all_runs if run.run_type == "simple_ai" and run.status == "success"
                    and _in_range(run.created_at, month_start, month_end)}
    month_deep = {run.notice_id for run in all_runs if run.run_type == "deep_ai" and run.status == "success"
                  and is_current_deep_result(run.result_json)
                  and _in_range(run.created_at, month_start, month_end)}
    contacted = sum(bool(notice.action and _in_range(notice.action.contacted_at, month_start, month_end)) for notice in notices)
    reflected = sum(bool(notice.action and notice.action.status in {"completed_uses", "reflected"}
                         and _in_range(notice.action.updated_at, month_start, month_end)) for notice in notices)
    monthly = {"collected": len(month_notices), "simple_verified": len(month_simple),
               "deep_verified": len(month_deep), "contacted": contacted, "reflected": reflected}

    created_counts: dict[date, int] = {}
    for notice in notices:
        created_day = _kst_date(notice.created_at)
        if created_day is not None:
            created_counts[created_day] = created_counts.get(created_day, 0) + 1
    recent = []
    for offset in range(6, -1, -1):
        recent_day = day - timedelta(days=offset)
        recent.append({
            "date": recent_day.isoformat(), "label": recent_day.strftime("%m/%d"),
            "count": created_counts.get(recent_day, 0),
        })

    grades_today_ids = {run.notice_id for run in deep_success}
    grade_notices = [notice for notice in notices if notice.id in grades_today_ids and notice.decision]
    grades = {grade: sum(notice.decision.final_grade == grade for notice in grade_notices) for grade in "ABCDE"}
    latest_classification_by_notice = {}
    for run in classified_runs:
        if run.notice_id not in latest_classification_by_notice or run.id > latest_classification_by_notice[run.notice_id].id:
            latest_classification_by_notice[run.notice_id] = run
    classification_distribution = {code: 0 for code in CLASSIFICATION_LABELS}
    for run in latest_classification_by_notice.values():
        code = str(_json_value(run.result_json, {}).get("classification_code") or "")
        if code in classification_distribution:
            classification_distribution[code] += 1

    actioned_statuses = {
        "in_progress", "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai",
        "contacted", "reflected", "not_reflected", "closed",
    }
    started_today = [
        notice for notice in notices if notice.action and notice.action.status != "new"
        and _in_range(notice.action.updated_at, start, end)
    ]
    actioned_today = [
        notice for notice in started_today if notice.action.status in actioned_statuses
    ]
    action_outcomes = {
        "started_today": len(started_today),
        "acted_today": len(actioned_today),
        "contacted_today": sum(
            bool(notice.action and _in_range(notice.action.contacted_at, start, end))
            for notice in notices
        ),
        "reflected_today": sum(
            bool(notice.action and notice.action.status in {"completed_uses", "reflected"}
                 and _in_range(notice.action.updated_at, start, end))
            for notice in notices
        ),
        "unresolved": len(active_contact),
    }
    workflow = {
        "collected": len(new_notices),
        "classified": len(latest_classification_by_notice),
        "non_ai": classification_distribution.get("6", 0),
        "llm_reviewed": len({run.notice_id for run in simple_success}),
        "llm_needed": len(deep_candidate_ids),
        "deep_completed": len({run.notice_id for run in deep_success}),
        "action_needed": len(active_contact),
        "acted": len(actioned_today),
    }
    summary = {
        "new_notices": len(new_notices), "attachments": len(attachments),
        "attachments_acquired": attachments_acquired,
        "parse_rate": round(parsed_count / len(attachments) * 100, 1) if attachments else 0,
        "simple_review": len({run.notice_id for run in simple_success}),
        "actions_completed": action_outcomes["acted_today"],
        "deep_candidates": len(deep_candidate_ids),
        "deep_review": len({run.notice_id for run in deep_success}),
        "priority_actions": len(priority_items), "failures": len(failure_attachments),
        "grade_distribution": grades,
        "classification_distribution": classification_distribution,
    }
    if reconciliation["state"] == "ready":
        reconciled_distribution = {code: 0 for code in CLASSIFICATION_LABELS}
        reconciled_distribution.update({
            str(code): int(count) for code, count in reconciliation["categories"].items()
            if str(code) in CLASSIFICATION_LABELS
        })
        workflow.update({
            "classified": reconciliation["classified"],
            "non_ai": reconciled_distribution["6"],
            "llm_reviewed": reconciliation["current_simple"],
            "llm_needed": reconciliation["deep_candidates"],
            "deep_completed": reconciliation["deep_candidates"],
        })
        summary.update({
            "simple_review": reconciliation["current_simple"],
            "deep_candidates": reconciliation["deep_candidates"],
            "deep_review": reconciliation["deep_candidates"],
            "classification_distribution": reconciled_distribution,
        })
    generated_at = datetime.now(KST).isoformat(timespec="seconds")
    data = {
        "date": day.isoformat(), "generated_at": generated_at, "status": batch["state"],
        "criteria_version": CURRENT_CRITERIA_VERSION,
        "finalized": bool(finalized and batch["state"] in {"ready", "partial"}),
        "workflow": workflow, "action_outcomes": action_outcomes,
        "disclaimer": "공개자료 기반 후보 선별 결과이며 최종 행정판단이 아닙니다.",
        "batch": batch, "reconciliation": reconciliation,
        "summary": summary, "processing": processing, "monthly": monthly,
        "recent": recent,
        "priority_items": priority_items, "uncertain_items": uncertain_items,
        "failures": [{"id": item.id, "notice_id": item.notice_id, "filename": item.original_filename,
                      "status": item.parse_status, "reason": item.parse_error or item.download_error or item.parse_status}
                     for item in failure_attachments[:100]],
        "pipeline_failures": pipeline_failures[:100],
    }
    markdown_path, html_path, json_path = _artifact_paths(day)
    markdown_path.write_text(_markdown(data), encoding="utf-8")
    html_path.write_text(_render_html(data), encoding="utf-8")
    json_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return ReportArtifact(day, generated_at, batch["state"], data["finalized"], str(markdown_path),
                          str(html_path), str(json_path), summary, data)


def get_daily_report(db: Session, report_date: date | None = None) -> ReportArtifact:
    day = report_date or datetime.now(KST).date()
    return load_finalized_report(day) or build_daily_report(db, day)
