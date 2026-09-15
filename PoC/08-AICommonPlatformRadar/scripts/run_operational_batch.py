from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

import _bootstrap  # noqa: F401
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import AuditLog, PipelineRun
from app.services.collector import run_collection


KST = timezone(timedelta(hours=9))


def _stats(run: PipelineRun | None) -> dict:
    try:
        value = json.loads(run.stats_json or "{}") if run else {}
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _latest_collect_today(db) -> PipelineRun | None:
    now = datetime.now(KST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
    return db.scalar(
        select(PipelineRun)
        .where(PipelineRun.run_kind == "collect", PipelineRun.started_at >= start)
        .order_by(PipelineRun.started_at.desc())
    )


def _retry_needed(run: PipelineRun | None) -> bool:
    if run is None or run.status != "success":
        return True
    stats = _stats(run)
    return any(int(stats.get(name, 0) or 0) > 0 for name in (
        "attachment_failed", "analysis_failed", "analysis_deferred",
    ))


def _record_retry_skip(db, previous: PipelineRun) -> dict:
    stats = {"skipped": True, "reason": "primary_batch_clean", "collect_run_id": previous.id}
    now = datetime.now(timezone.utc)
    run = PipelineRun(
        run_kind="retry",
        mode=previous.mode,
        status="skipped",
        started_at=now,
        finished_at=now,
        stats_json=json.dumps(stats, ensure_ascii=False),
    )
    db.add(run)
    db.add(AuditLog(event_type="collection_retry_skipped", detail_json=json.dumps(stats, ensure_ascii=False)))
    db.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC08 새벽 운영 배치")
    parser.add_argument("--phase", choices=("primary", "retry"), default="primary")
    parser.add_argument("--lookback-days", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    init_db()
    with SessionLocal() as db:
        previous = _latest_collect_today(db)
        if args.dry_run:
            print(json.dumps({
                "ready": True,
                "phase": args.phase,
                "latest_collect_status": previous.status if previous else "missing",
                "retry_needed": _retry_needed(previous),
            }, ensure_ascii=False, indent=2))
            return
        if args.phase == "retry" and previous and not _retry_needed(previous):
            print(json.dumps(_record_retry_skip(db, previous), ensure_ascii=False, indent=2))
            return
        result = asyncio.run(run_collection(db, args.lookback_days, analyze=True))
        print(json.dumps({"phase": args.phase, **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
