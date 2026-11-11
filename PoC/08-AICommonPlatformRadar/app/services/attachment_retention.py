from __future__ import annotations

import json
from datetime import timezone
from pathlib import Path

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..models import ActionItem, AnalysisRun, Attachment, AuditLog, PipelineRun
from .analyzer import is_current_deep_result


PRESERVED_ACTION_STATES = {
    "completed_uses", "completed_not_used", "reflected", "closed",
}
PURGED_ACTION_STATES = {"completed_ineligible", "completed_non_ai"}


def _current_codes(db: Session) -> dict[int, str | None]:
    """Build the current classification without loading notices or attachments."""
    rows = db.execute(select(
        AnalysisRun.id,
        AnalysisRun.notice_id,
        AnalysisRun.run_type,
        AnalysisRun.status,
        AnalysisRun.model_name,
        AnalysisRun.result_json,
    ).where(or_(
        AnalysisRun.run_type == "deep_ai",
        (AnalysisRun.run_type == "simple_ai") & (AnalysisRun.status == "success"),
    )).order_by(AnalysisRun.id)).all()

    current: dict[int, str | None] = {}
    for _run_id, notice_id, run_type, status, model_name, result_json in rows:
        if run_type == "simple_ai":
            current[notice_id] = None
            continue
        if status not in {"success", "skipped"}:
            continue
        if status == "skipped" and model_name != "rule-gate":
            continue
        if not is_current_deep_result(result_json):
            continue
        try:
            result = json.loads(result_json or "{}")
        except (json.JSONDecodeError, TypeError):
            continue
        code = "6" if result.get("service_scope") == "non_target" else str(
            result.get("classification_code") or ""
        )
        current[notice_id] = code or None
    return current


def _managed_path(value: str | None, settings: Settings) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = settings.project_root / path
    try:
        resolved = path.resolve()
        resolved.relative_to(settings.data_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def purge_attachments_by_policy(
    db: Session,
    *,
    settings: Settings | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Remove stored files for terminal low-value classifications.

    Codes 1/2 (confirmed use / eligible but unused) and review codes 3/4 are
    intentionally retained. Code 6 and out-of-scope records are purged as soon
    as the scheduled cleanup sees them; code 5 and manually confirmed
    ineligible records are purged by the same daily pass. Metadata and analysis
    history stay in the database so statistics and audit trails remain intact.
    """
    settings = settings or get_settings()
    codes = _current_codes(db)
    action_rows = db.execute(select(
        ActionItem.notice_id, ActionItem.status,
    )).all()
    preserved_ids = {
        notice_id for notice_id, status in action_rows if status in PRESERVED_ACTION_STATES
    }
    reasons = {
        notice_id: "non_ai" if code == "6" else "ineligible"
        for notice_id, code in codes.items()
        if code in {"5", "6"} and notice_id not in preserved_ids
    }
    for notice_id, status in action_rows:
        if notice_id in preserved_ids:
            continue
        if status == "completed_non_ai":
            reasons[notice_id] = "non_ai"
        elif status == "completed_ineligible":
            reasons[notice_id] = "ineligible"

    stats = {
        "notices_selected": len(reasons),
        "non_ai_notices": sum(reason == "non_ai" for reason in reasons.values()),
        "ineligible_notices": sum(reason == "ineligible" for reason in reasons.values()),
        "attachments_purged": 0,
        "raw_files_deleted": 0,
        "parsed_files_deleted": 0,
        "shared_files_preserved": 0,
        "delete_failed": 0,
        "batch_failures_resolved": 0,
    }
    if not reasons:
        return stats

    candidates = db.scalars(select(Attachment).where(
        Attachment.notice_id.in_(tuple(reasons)),
        or_(
            Attachment.file_path.is_not(None),
            Attachment.text_path.is_not(None),
            Attachment.text_excerpt.is_not(None),
        ),
    )).all()
    if not candidates:
        return stats

    latest_collect = db.scalar(select(PipelineRun).where(
        PipelineRun.run_kind == "collect",
    ).order_by(PipelineRun.started_at.desc()))
    latest_started = latest_collect.started_at if latest_collect else None
    if latest_started and latest_started.tzinfo is None:
        latest_started = latest_started.replace(tzinfo=timezone.utc)
    for attachment in candidates:
        updated_at = attachment.updated_at
        if updated_at and updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if (
            attachment.parse_status == "failed"
            and latest_started
            and updated_at
            and updated_at >= latest_started
        ):
            stats["batch_failures_resolved"] += 1

    candidate_ids = set(reasons)
    protected_paths: set[Path] = set()
    for file_path, text_path in db.execute(select(
        Attachment.file_path, Attachment.text_path,
    ).where(~Attachment.notice_id.in_(tuple(candidate_ids)))):
        for value in (file_path, text_path):
            if path := _managed_path(value, settings):
                protected_paths.add(path)

    raw_paths: set[Path] = set()
    parsed_paths: set[Path] = set()
    for attachment in candidates:
        if path := _managed_path(attachment.file_path, settings):
            raw_paths.add(path)
        if path := _managed_path(attachment.text_path, settings):
            parsed_paths.add(path)
    stats["attachments_purged"] = len(candidates)
    stats["shared_files_preserved"] = len((raw_paths | parsed_paths) & protected_paths)
    if dry_run:
        stats["raw_files_deleted"] = len(raw_paths - protected_paths)
        stats["parsed_files_deleted"] = len(parsed_paths - protected_paths)
        return stats

    for attachment in candidates:
        reason_label = "비AI·적용범위 외" if reasons[attachment.notice_id] == "non_ai" else "공통기반 부적합"
        attachment.file_path = None
        attachment.text_path = None
        attachment.text_excerpt = None
        attachment.download_status = "purged"
        attachment.parse_status = "purged"
        attachment.parse_error = f"보존 정책에 따라 {reason_label} 첨부 원문·파싱 파일 삭제"
    db.flush()

    if latest_collect and stats["batch_failures_resolved"]:
        try:
            batch_stats = json.loads(latest_collect.stats_json or "{}")
        except (json.JSONDecodeError, TypeError):
            batch_stats = {}
        unresolved = int(batch_stats.get("attachment_failed", 0) or 0)
        recovered = min(unresolved, stats["batch_failures_resolved"])
        batch_stats["attachment_failed"] = unresolved - recovered
        batch_stats["attachment_recovered"] = int(
            batch_stats.get("attachment_recovered", 0) or 0
        ) + recovered
        latest_collect.stats_json = json.dumps(batch_stats, ensure_ascii=False)
        stats["batch_failures_resolved"] = recovered

    for kind, paths in (("raw", raw_paths), ("parsed", parsed_paths)):
        for path in paths - protected_paths:
            try:
                if path.is_file():
                    path.unlink()
                    stats[f"{kind}_files_deleted"] += 1
            except OSError:
                stats["delete_failed"] += 1

    db.add(AuditLog(
        event_type="attachment_retention_cleanup",
        entity_type="attachment",
        detail_json=json.dumps(stats, ensure_ascii=False),
    ))
    db.commit()
    return stats
