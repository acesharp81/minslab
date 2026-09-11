from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Attachment, Notice, NoticeDecision


KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class ReportArtifact:
    report_date: date
    markdown_path: str
    html_path: str
    summary: dict


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=KST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _json_list(value: str | None) -> list:
    try:
        parsed = json.loads(value or "[]")
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def build_daily_report(db: Session, report_date: date | None = None) -> ReportArtifact:
    settings = get_settings()
    settings.ensure_directories()
    day = report_date or datetime.now(KST).date()
    start, end = _day_bounds(day)
    notices = db.scalars(
        select(Notice).where(Notice.created_at >= start, Notice.created_at < end)
        .options(selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action))
        .order_by(Notice.created_at.desc())
    ).all()
    # 샘플 DB를 다음 날 열어도 유용하도록 당일 신규가 없으면 최근 누적 후보를 보여준다.
    candidates = [notice for notice in notices if notice.decision]
    if not candidates:
        candidates = db.scalars(
            select(Notice).join(NoticeDecision).options(
                selectinload(Notice.attachments), selectinload(Notice.decision), selectinload(Notice.action)
            ).order_by(NoticeDecision.priority_score.desc()).limit(50)
        ).all()
    attachments = [item for notice in notices for item in notice.attachments]
    parsed_count = sum(item.parse_status == "parsed" for item in attachments)
    priority = [notice for notice in candidates if notice.decision and notice.decision.recommended_action == "contact"]
    uncertain = [notice for notice in candidates if notice.decision and notice.decision.final_grade == "D"]
    failures = db.scalars(select(Attachment).where(Attachment.parse_status.in_(["failed", "unsupported"]))).all()
    grade_rows = db.execute(select(NoticeDecision.final_grade, func.count()).group_by(NoticeDecision.final_grade)).all()
    summary = {
        "new_notices": len(notices), "attachments": len(attachments),
        "parse_rate": round(parsed_count / len(attachments) * 100, 1) if attachments else 0,
        "deep_review": len(candidates), "priority_actions": len(priority),
        "failures": len(failures), "grade_distribution": dict(grade_rows),
    }

    lines = [
        f"# {day.isoformat()} 공통기반 활용 가능 사업 레이더", "",
        "> 본 리포트는 공개자료 기반 후보 선별 결과이며 최종 행정판단이 아닙니다.", "",
        "## 금일 요약", "",
        f"- 신규 수집: {summary['new_notices']}건",
        f"- 첨부 확보: {summary['attachments']}건 / 파싱 성공률: {summary['parse_rate']}%",
        f"- 심층검토 후보: {summary['deep_review']}건 / 우선 조치: {summary['priority_actions']}건",
        f"- 오류·미지원: {summary['failures']}건", "", "## 우선 조치 대상", "",
    ]
    if not priority:
        lines.append("우선 조치 대상이 없습니다.")
    for notice in priority:
        decision = notice.decision
        evidence = _json_list(decision.key_evidence_json)
        functions = _json_list(decision.possible_functions_json)
        lines.extend([
            f"### {decision.final_grade} · {notice.title}", "",
            f"- 기관/단계: {notice.agency_name} / {notice.stage}",
            f"- 예산: {notice.budget_amount or 0:,}원",
            f"- 우선순위: {decision.priority_score}점",
            f"- 활용 가능 기능: {', '.join(functions) or '확인 필요'}",
            f"- 판단: {decision.summary}",
        ])
        if evidence:
            lines.append(f"- 근거: “{evidence[0].get('quote', '')}”")
        lines.append("")
    lines.extend(["## 확인 필요 대상", ""])
    if not uncertain:
        lines.append("확인 필요 대상이 없습니다.")
    for notice in uncertain:
        questions = _json_list(notice.decision.check_questions_json)
        lines.append(f"- **{notice.title}** — {' / '.join(questions) or '담당자 확인 필요'}")
    lines.extend(["", "## 오류 및 재처리 대상", ""])
    if not failures:
        lines.append("오류 또는 미지원 첨부가 없습니다.")
    for item in failures[:100]:
        lines.append(f"- 첨부 #{item.id} `{item.original_filename}`: {item.parse_error or item.parse_status}")
    lines.extend(["", "## 누적 등급 분포", ""])
    for grade in "ABCDE":
        lines.append(f"- {grade}: {summary['grade_distribution'].get(grade, 0)}건")
    markdown = "\n".join(lines) + "\n"
    markdown_path = settings.reports_dir / f"{day.isoformat()}_daily_report.md"
    html_path = settings.reports_dir / f"{day.isoformat()}_daily_report.html"
    markdown_path.write_text(markdown, encoding="utf-8")
    escaped = html.escape(markdown)
    html_path.write_text(
        "<!doctype html><html lang='ko'><meta charset='utf-8'><title>공통기반 사업 레이더</title>"
        "<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:40px auto;padding:0 24px;line-height:1.7;color:#17231d}"
        "pre{white-space:pre-wrap;font:inherit} </style><body><pre>" + escaped + "</pre></body></html>",
        encoding="utf-8",
    )
    return ReportArtifact(day, str(markdown_path), str(html_path), summary)

