from __future__ import annotations

import json
import logging
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..models import Attachment, AuditLog, Notice, PipelineRun
from .analyzer import LLMRateLimitExceeded, analyze_notice, is_current_deep_result, record_non_ai_screen
from .attachment_policy import (
    business_document_key,
    is_business_document,
    is_opaque_attachment_name,
    select_preferred_documents,
)
from .batch_lock import exclusive_collection_lock
from .downloader import DownloadResult, download_attachment
from .filename import build_stored_filename, extension_from_name, safe_original_name, sha256_bytes
from .filter_rules import evaluate_notice
from .g2b_client import G2BClient, G2BNotice
from .parser import parse_bytes
from .supabase_store import get_supabase_store


logger = logging.getLogger(__name__)

_EXPLICIT_AI = re.compile(
    r"(?<![A-Za-z])AI(?![A-Za-z])|인공지능|생성형|(?<![A-Za-z])LLM(?![A-Za-z])|"
    r"(?<![A-Za-z])RAG(?![A-Za-z])|머신러닝|딥러닝|챗봇",
    re.IGNORECASE,
)


def is_explicit_ai_title(title: str) -> bool:
    return bool(_EXPLICIT_AI.search(title or ""))


def can_rule_screen_non_ai(notice: Notice, rule) -> bool:
    """Only close as non-AI when an exclusion is explicit or parsed business text is available."""
    if rule.score > 0 or rule.needs_sample_review:
        return False
    documents = select_preferred_documents(notice.attachments, name=lambda row: row.original_filename)
    parsed_documents = [row for row in documents if row.parse_status == "parsed" and (row.text_excerpt or "").strip()]
    return bool(rule.skip or parsed_documents)


def _collection_priority(item: G2BNotice) -> tuple[int, int, float]:
    """한도가 짧은 2차 분석을 명시적 AI 공고부터 사용한다."""
    rule = evaluate_notice(
        title=item.title,
        agency=item.agency_name,
        budget_amount=item.budget_amount,
        attachment_names=[row.name for row in item.attachments],
    )
    posted = item.posted_at.timestamp() if item.posted_at else 0.0
    return (1 if is_explicit_ai_title(item.title) else 0, rule.score, posted)


def _notice_priority(notice: Notice) -> tuple[int, int, int, int, float]:
    rule = evaluate_notice(
        title=notice.title,
        agency=notice.agency_name,
        budget_amount=notice.budget_amount,
        attachment_names=[row.original_filename for row in notice.attachments],
        text_excerpt="\n".join(row.text_excerpt or "" for row in notice.attachments),
    )
    posted = notice.posted_at.timestamp() if notice.posted_at else 0.0
    runs = sorted(notice.analysis_runs, key=lambda row: row.id or 0)
    has_current = any(
        row.run_type == "deep_ai" and row.status == "success" and is_current_deep_result(row.result_json)
        for row in runs
    )
    has_legacy = any(row.run_type == "deep_ai" and row.status == "success" for row in runs) and not has_current
    latest = runs[-1] if runs else None
    return (
        1 if has_legacy else 0,
        1 if is_explicit_ai_title(notice.title) else 0,
        1 if latest and latest.status == "failed" else 0,
        rule.score,
        posted,
    )


def _needs_backlog_analysis(notice: Notice) -> bool:
    runs = sorted(notice.analysis_runs, key=lambda row: row.id or 0)
    if any(
        row.run_type == "deep_ai" and row.status == "success" and is_current_deep_result(row.result_json)
        for row in runs
    ):
        return False
    latest_deep = next((row for row in reversed(runs) if row.run_type == "deep_ai"), None)
    if latest_deep and latest_deep.status == "skipped" and latest_deep.model_name == "rule-gate":
        return not is_current_deep_result(latest_deep.result_json)
    simple_success = next((
        row for row in reversed(runs) if row.run_type == "simple_ai" and row.status == "success"
    ), None)
    if simple_success:
        try:
            return bool(json.loads(simple_success.result_json).get("needs_deep_review"))
        except (json.JSONDecodeError, AttributeError, TypeError):
            return True
    return True


def _relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(get_settings().project_root))
    except ValueError:
        # DATA_DIR를 프로젝트 밖의 볼륨으로 지정한 경우 절대경로를 보존한다.
        return str(resolved)


def _sample_download(item: G2BNotice) -> DownloadResult:
    content = str(item.raw.get("text") or "").encode("utf-8")
    name = safe_original_name(f"{item.notice_no}_제안요청서.txt")
    return DownloadResult("downloaded", content, name, "txt", sha256_bytes(content))


def _upsert_notice(db: Session, item: G2BNotice) -> tuple[Notice, bool]:
    notice = db.scalar(select(Notice).where(
        Notice.source == "g2b", Notice.stage == item.stage, Notice.notice_no == item.notice_no,
    ))
    created = notice is None
    if notice is None:
        notice = Notice(source="g2b", stage=item.stage, notice_no=item.notice_no, title=item.title)
        db.add(notice)
    notice.bid_no = item.bid_no
    notice.agency_name = item.agency_name
    notice.agency_code = item.agency_code
    notice.title = item.title
    notice.budget_amount = item.budget_amount
    notice.posted_at = item.posted_at
    notice.deadline_at = item.deadline_at
    notice.url = item.url
    notice.business_type = "service"
    notice.raw_payload_json = json.dumps(item.raw, ensure_ascii=False, default=str)
    notice.collect_status = "collected"
    db.flush()
    return notice, created


def _store_attachment(db: Session, notice: Notice, item: G2BNotice, sequence: int, source_url: str, name_hint: str) -> str:
    existing = db.scalar(select(Attachment).where(Attachment.notice_id == notice.id, Attachment.source_url == source_url))
    if existing and existing.parse_status in {"parsed", "skipped", "skipped_duplicate"}:
        return "cached" if existing.parse_status == "parsed" else existing.parse_status
    if existing and existing.parse_status == "unsupported" and not extension_from_name(existing.original_filename):
        return "unsupported"
    attachment = existing or Attachment(notice_id=notice.id, source_url=source_url, original_filename=safe_original_name(name_hint))
    if not existing:
        db.add(attachment)
    result = _sample_download(item) if source_url.startswith("sample://") else download_attachment(source_url)
    attachment.download_status = result.status
    attachment.download_error = result.error
    attachment.original_filename = result.original_filename or attachment.original_filename
    if result.original_filename and not is_business_document(attachment.original_filename):
        attachment.file_ext = result.extension or None
        attachment.file_size = len(result.content) if result.content else None
        attachment.sha256 = result.sha256 or None
        attachment.parse_status = "skipped"
        attachment.parse_error = "사업 내용 문서가 아니어서 파싱 대상에서 제외"
        attachment.text_path = None
        attachment.text_excerpt = None
        return "skipped"
    if result.status != "downloaded":
        attachment.parse_status = "unsupported" if result.status == "unsupported" else "failed"
        attachment.parse_error = result.error or "다운로드 실패로 파싱하지 않음"
        return result.status
    duplicate = db.scalar(select(Attachment).where(Attachment.sha256 == result.sha256, Attachment.file_path.is_not(None)).limit(1))
    posted = (item.posted_at or datetime.now(timezone.utc)).strftime("%Y%m%d")
    stored_name = build_stored_filename(
        source="g2b", stage=item.stage, notice_no=item.notice_no, agency=item.agency_name,
        posted_yyyymmdd=posted, title=item.title, sequence=sequence,
        sha256=result.sha256, extension=result.extension,
    )
    path = get_settings().raw_dir / stored_name
    if duplicate and duplicate.file_path and (get_settings().project_root / duplicate.file_path).is_file():
        path = get_settings().project_root / duplicate.file_path
    elif not path.exists():
        path.write_bytes(result.content)
    attachment.original_filename = result.original_filename or safe_original_name(name_hint)
    attachment.stored_filename = path.name
    attachment.file_path = _relative(path)
    attachment.file_ext = result.extension
    attachment.file_size = len(result.content)
    attachment.sha256 = result.sha256
    attachment.parse_status = "pending"
    attachment.parse_error = None
    attachment.text_path = None
    attachment.text_excerpt = None
    return "pending"


def parse_preferred_attachments(db: Session, notice: Notice, *, force: bool = False) -> dict[str, str]:
    attachments = list(db.scalars(select(Attachment).where(Attachment.notice_id == notice.id)).all())
    preferred = select_preferred_documents(attachments, name=lambda row: row.original_filename)
    preferred_ids = {row.id for row in preferred}
    preferred_by_key = {
        business_document_key(row.original_filename): row
        for row in preferred
        if is_business_document(row.original_filename)
    }

    for attachment in attachments:
        if not is_business_document(attachment.original_filename):
            if not is_opaque_attachment_name(attachment.original_filename):
                attachment.parse_status = "skipped"
                attachment.parse_error = "사업 내용 문서가 아니어서 파싱 대상에서 제외"
                attachment.text_path = None
                attachment.text_excerpt = None
            continue
        if attachment.id not in preferred_ids and attachment.file_path:
            winner = preferred_by_key.get(business_document_key(attachment.original_filename))
            attachment.parse_status = "skipped_duplicate"
            attachment.parse_error = (
                f"동일 제목의 {winner.file_ext or '다른'} 형식을 우선 파싱"
                if winner else "동일 제목의 파서 우선 형식을 선택"
            )
            attachment.text_path = None
            attachment.text_excerpt = None

    for attachment in preferred:
        if not attachment.file_path:
            continue
        if attachment.parse_status == "parsed" and not force:
            continue
        path = Path(attachment.file_path)
        if not path.is_absolute():
            path = get_settings().project_root / path
        try:
            parsed = parse_bytes(path.read_bytes(), attachment.file_ext or "")
            attachment.parse_status = parsed.status
            attachment.parse_error = parsed.error
            attachment.text_path = None
            attachment.text_excerpt = None
            if parsed.status == "parsed":
                text_path = get_settings().parsed_dir / f"{attachment.sha256}.txt"
                if not text_path.exists():
                    text_path.write_text(parsed.text, encoding="utf-8")
                attachment.text_path = _relative(text_path)
                attachment.text_excerpt = parsed.text[:20_000]
        except Exception as exc:
            attachment.parse_status = "failed"
            attachment.parse_error = f"{type(exc).__name__}: {str(exc)[:500]}"
    db.flush()
    return {row.source_url: row.parse_status for row in attachments}


async def run_collection(db: Session, lookback_days: int | None = None, *, analyze: bool = True) -> dict[str, int | str]:
    settings = get_settings()
    with exclusive_collection_lock(settings.data_dir):
        return await _run_collection(db, lookback_days, analyze=analyze, settings=settings)


async def _run_collection(
    db: Session,
    lookback_days: int | None = None,
    *,
    analyze: bool = True,
    settings=None,
) -> dict[str, int | str]:
    settings = settings or get_settings()
    settings.ensure_directories()
    problems = settings.validate_runtime()
    if problems:
        raise RuntimeError(" ".join(problems))
    bulk_supabase_sync = settings.supabase_enabled
    if bulk_supabase_sync:
        db.info["suppress_supabase_sync"] = True
    run = PipelineRun(run_kind="collect", mode=settings.g2b_mode, status="running")
    db.add(run)
    db.commit()
    stats: dict[str, int | str] = {
        "received": 0, "created": 0, "updated": 0, "attachments": 0,
        "parsed": 0, "attachment_unsupported": 0, "attachment_failed": 0, "attachment_skipped": 0,
        "rule_candidates": 0, "analyzed": 0, "analysis_failed": 0, "analysis_deferred": 0,
        "screened_non_ai": 0,
    }
    try:
        client = G2BClient(settings)
        items = await client.collect(lookback_days or settings.collect_lookback_days)
        items = sorted(items, key=_collection_priority, reverse=True)
        stats["received"] = len(items)
        for position, item in enumerate(items, start=1):
            try:
                policy_attachments = select_preferred_documents(item.attachments, name=lambda row: row.name)
                metadata_rule = evaluate_notice(
                    title=item.title, agency=item.agency_name, budget_amount=item.budget_amount,
                    attachment_names=[row.name for row in policy_attachments],
                )
                if item.stage == "bid_notice" and item.bid_no and not policy_attachments and metadata_rule.score > 0:
                    order = item.notice_no.rsplit("-", 1)[-1]
                    item = replace(item, attachments=await client.bid_attachments(item.bid_no, order))
                notice, created = _upsert_notice(db, item)
                stats["created" if created else "updated"] += 1
                candidate_attachments = [] if metadata_rule.skip else select_preferred_documents(
                    item.attachments, name=lambda row: row.name
                )
                touched_urls: set[str] = set()
                for sequence, attachment in enumerate(candidate_attachments[:settings.max_files_per_notice], start=1):
                    _store_attachment(db, notice, item, sequence, attachment.url, attachment.name)
                    touched_urls.add(attachment.url)
                    stats["attachments"] += 1
                db.flush()
                attachment_statuses = parse_preferred_attachments(db, notice)
                for source_url in touched_urls:
                    status = attachment_statuses.get(source_url, "failed")
                    if status == "parsed":
                        stats["parsed"] += 1
                    elif status == "unsupported":
                        stats["attachment_unsupported"] += 1
                    elif status in {"skipped", "skipped_duplicate"}:
                        stats["attachment_skipped"] += 1
                    elif status in {"failed", "download_failed", "pending"}:
                        stats["attachment_failed"] += 1
                db.commit()
                business_attachments = select_preferred_documents(
                    notice.attachments, name=lambda row: row.original_filename
                )
                rule = evaluate_notice(
                    title=notice.title, agency=notice.agency_name, budget_amount=notice.budget_amount,
                    attachment_names=[row.original_filename for row in business_attachments],
                    text_excerpt="\n".join(row.text_excerpt or "" for row in business_attachments),
                )
                db.add(AuditLog(
                    event_type="rule_filter", entity_type="notice", entity_id=str(notice.id),
                    detail_json=json.dumps(rule.as_dict(), ensure_ascii=False),
                ))
                db.commit()
                if rule.score > 0:
                    stats["rule_candidates"] += 1
            except Exception as exc:
                db.rollback()
                logger.exception("공고 단위 처리 실패: %s", item.notice_no)
                stats["attachment_failed"] += 1
                db.add(AuditLog(
                    event_type="notice_pipeline_failed", entity_type="notice", entity_id=item.notice_no,
                    detail_json=json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:500]}"}, ensure_ascii=False),
                ))
                db.commit()
            if position % 10 == 0:
                run.stats_json = json.dumps({**stats, "processed": position}, ensure_ascii=False)
                db.commit()
        if analyze:
            all_notices = db.scalars(select(Notice).options(
                selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
                selectinload(Notice.decision), selectinload(Notice.action),
            )).all()
            backlog = []
            for notice in all_notices:
                if not _needs_backlog_analysis(notice):
                    continue
                rule = evaluate_notice(
                    title=notice.title,
                    agency=notice.agency_name,
                    budget_amount=notice.budget_amount,
                    attachment_names=[row.original_filename for row in notice.attachments],
                    text_excerpt="\n".join(row.text_excerpt or "" for row in notice.attachments),
                )
                if rule.score > 0:
                    backlog.append(notice)
                elif can_rule_screen_non_ai(notice, rule) and record_non_ai_screen(db, notice, rule):
                    stats["screened_non_ai"] += 1
            backlog.sort(key=_notice_priority, reverse=True)
            for index, notice in enumerate(backlog):
                try:
                    analyze_notice(db, notice, deep=True)
                    stats["analyzed"] += 1
                except LLMRateLimitExceeded:
                    logger.warning("2차 LLM 호출 한도로 나머지 후보 분석을 다음 배치로 보류합니다.")
                    stats["analysis_failed"] += 1
                    stats["analysis_deferred"] += len(backlog) - index - 1
                    break
                except Exception:
                    logger.exception("공고 %s 분석 실패", notice.id)
                    stats["analysis_failed"] += 1
        run.status = "success"
        run.stats_json = json.dumps(stats, ensure_ascii=False)
        run.finished_at = datetime.now(timezone.utc)
        db.add(AuditLog(event_type="collection_finished", entity_type="pipeline_run", entity_id=str(run.id), detail_json=run.stats_json))
        db.commit()
        return stats
    except Exception as exc:
        db.rollback()
        run = db.get(PipelineRun, run.id)
        if run:
            run.status = "failed"
            run.error_message = f"{type(exc).__name__}: {str(exc)[:1000]}"
            run.finished_at = datetime.now(timezone.utc)
            run.stats_json = json.dumps(stats, ensure_ascii=False)
            db.commit()
        raise
    finally:
        if bulk_supabase_sync:
            db.info.pop("suppress_supabase_sync", None)
            get_supabase_store().push_all(db)


def reparse_failed(db: Session) -> dict[str, int]:
    settings = get_settings()
    stats = {"retried": 0, "parsed": 0, "failed": 0}
    rows = db.scalars(select(Attachment).where(
        Attachment.file_path.is_not(None),
        or_(
            Attachment.parse_status == "failed",
            and_(Attachment.parse_status == "unsupported", Attachment.file_ext.in_(("hwp", "hwpx"))),
        ),
    )).all()
    bulk_supabase_sync = settings.supabase_enabled
    if bulk_supabase_sync:
        db.info["suppress_supabase_sync"] = True
    try:
        for attachment in rows:
            stats["retried"] += 1
            path = Path(str(attachment.file_path))
            if not path.is_absolute():
                path = settings.project_root / path
            try:
                result = parse_bytes(path.read_bytes(), attachment.file_ext or "")
                attachment.parse_status = result.status
                attachment.parse_error = result.error
                attachment.text_path = None
                attachment.text_excerpt = None
                if result.status == "parsed":
                    text_path = settings.parsed_dir / f"{attachment.sha256}.txt"
                    text_path.write_text(result.text, encoding="utf-8")
                    attachment.text_path = _relative(text_path)
                    attachment.text_excerpt = result.text[:20_000]
                    stats["parsed"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                attachment.parse_status = "failed"
                attachment.parse_error = f"{type(exc).__name__}: {str(exc)[:500]}"
                stats["failed"] += 1
            if stats["retried"] % 25 == 0:
                db.commit()
        db.add(AuditLog(event_type="reparse_finished", detail_json=json.dumps(stats, ensure_ascii=False)))
        db.commit()
    finally:
        if bulk_supabase_sync:
            db.info.pop("suppress_supabase_sync", None)
            get_supabase_store().push_all(db)
    return stats
