from __future__ import annotations

import json
import logging
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Attachment, AuditLog, Notice, PipelineRun
from .analyzer import analyze_notice
from .downloader import DownloadResult, download_attachment
from .filename import build_stored_filename, safe_original_name, sha256_bytes
from .filter_rules import evaluate_notice
from .g2b_client import G2BClient, G2BNotice
from .parser import parse_bytes


logger = logging.getLogger(__name__)


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
    if existing and existing.parse_status == "parsed":
        return "cached"
    attachment = existing or Attachment(notice_id=notice.id, source_url=source_url, original_filename=safe_original_name(name_hint))
    if not existing:
        db.add(attachment)
    result = _sample_download(item) if source_url.startswith("sample://") else download_attachment(source_url)
    attachment.download_status = result.status
    attachment.download_error = result.error
    if result.status != "downloaded":
        attachment.parse_status = "failed"
        attachment.parse_error = "다운로드 실패로 파싱하지 않음"
        return "download_failed"
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
    parsed = parse_bytes(result.content, result.extension)
    attachment.parse_status = parsed.status
    attachment.parse_error = parsed.error
    if parsed.status == "parsed":
        text_path = get_settings().parsed_dir / f"{result.sha256}.txt"
        if not text_path.exists():
            text_path.write_text(parsed.text, encoding="utf-8")
        attachment.text_path = _relative(text_path)
        attachment.text_excerpt = parsed.text[:20_000]
    return parsed.status


async def run_collection(db: Session, lookback_days: int | None = None, *, analyze: bool = True) -> dict[str, int | str]:
    settings = get_settings()
    settings.ensure_directories()
    problems = settings.validate_runtime()
    if problems:
        raise RuntimeError(" ".join(problems))
    run = PipelineRun(run_kind="collect", mode=settings.g2b_mode, status="running")
    db.add(run)
    db.commit()
    stats: dict[str, int | str] = {
        "received": 0, "created": 0, "updated": 0, "attachments": 0,
        "parsed": 0, "attachment_failed": 0, "analyzed": 0, "analysis_failed": 0,
    }
    try:
        client = G2BClient(settings)
        items = await client.collect(lookback_days or settings.collect_lookback_days)
        stats["received"] = len(items)
        for item in items:
            try:
                metadata_rule = evaluate_notice(
                    title=item.title, agency=item.agency_name, budget_amount=item.budget_amount,
                    attachment_names=[row.name for row in item.attachments],
                )
                if item.stage == "bid_notice" and item.bid_no and not item.attachments and not metadata_rule.skip:
                    order = item.notice_no.rsplit("-", 1)[-1]
                    item = replace(item, attachments=await client.bid_attachments(item.bid_no, order))
                notice, created = _upsert_notice(db, item)
                stats["created" if created else "updated"] += 1
                for sequence, attachment in enumerate(item.attachments[:settings.max_files_per_notice], start=1):
                    status = _store_attachment(db, notice, item, sequence, attachment.url, attachment.name)
                    stats["attachments"] += 1
                    if status == "parsed" or status == "cached":
                        stats["parsed"] += 1
                    elif status in {"failed", "download_failed"}:
                        stats["attachment_failed"] += 1
                db.commit()
                rule = evaluate_notice(
                    title=notice.title, agency=notice.agency_name, budget_amount=notice.budget_amount,
                    attachment_names=[row.original_filename for row in notice.attachments],
                    text_excerpt="\n".join(row.text_excerpt or "" for row in notice.attachments),
                )
                db.add(AuditLog(
                    event_type="rule_filter", entity_type="notice", entity_id=str(notice.id),
                    detail_json=json.dumps(rule.as_dict(), ensure_ascii=False),
                ))
                db.commit()
                if analyze:
                    try:
                        analyze_notice(db, notice, deep=True)
                        stats["analyzed"] += 1
                    except Exception:
                        logger.exception("공고 %s 분석 실패", notice.id)
                        stats["analysis_failed"] += 1
            except Exception as exc:
                db.rollback()
                logger.exception("공고 단위 처리 실패: %s", item.notice_no)
                stats["attachment_failed"] += 1
                db.add(AuditLog(
                    event_type="notice_pipeline_failed", entity_type="notice", entity_id=item.notice_no,
                    detail_json=json.dumps({"error": f"{type(exc).__name__}: {str(exc)[:500]}"}, ensure_ascii=False),
                ))
                db.commit()
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


def reparse_failed(db: Session) -> dict[str, int]:
    settings = get_settings()
    stats = {"retried": 0, "parsed": 0, "failed": 0}
    rows = db.scalars(select(Attachment).where(Attachment.parse_status == "failed", Attachment.file_path.is_not(None))).all()
    for attachment in rows:
        stats["retried"] += 1
        path = settings.project_root / str(attachment.file_path)
        try:
            result = parse_bytes(path.read_bytes(), attachment.file_ext or "")
            attachment.parse_status = result.status
            attachment.parse_error = result.error
            if result.status == "parsed":
                text_path = settings.parsed_dir / f"{attachment.sha256}.txt"
                text_path.write_text(result.text, encoding="utf-8")
                attachment.text_path = _relative(text_path)
                attachment.text_excerpt = result.text[:20_000]
                stats["parsed"] += 1
            else:
                stats["failed"] += 1
        except Exception as exc:
            attachment.parse_error = f"{type(exc).__name__}: {str(exc)[:500]}"
            stats["failed"] += 1
        db.commit()
    db.add(AuditLog(event_type="reparse_finished", detail_json=json.dumps(stats, ensure_ascii=False)))
    db.commit()
    return stats
