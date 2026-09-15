from __future__ import annotations

import argparse
import json
from collections import Counter
import time

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import Notice
from app.services.analyzer import _input_hash, analyze_notice, get_analyzer, notice_context
from app.services.supabase_store import get_supabase_store
from app.services.workflow_view import current_classification_run


def _json(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _notice_ids(db) -> list[int]:
    notices = db.scalars(select(Notice).options(selectinload(Notice.analysis_runs))).all()
    return [notice.id for notice in notices if current_classification_run(notice) is None]


def _candidate_ids(db, analyzer) -> list[int]:
    notices = db.scalars(select(Notice).options(
        selectinload(Notice.analysis_runs), selectinload(Notice.attachments),
    )).all()
    result = []
    for notice in notices:
        expected_simple_hash = _input_hash(
            notice_context(notice), "simple_ai", analyzer.simple_cache_fingerprint,
        )
        simple = next((
            run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
            if run.run_type == "simple_ai" and run.status == "success"
            and run.input_hash == expected_simple_hash
        ), None)
        if simple is None:
            # The prepare phase owns notices without a current stage-2 result.
            continue
        if not _json(simple.result_json).get("needs_deep_review"):
            continue
        expected_hash = _input_hash(
            notice_context(notice), "deep_ai", analyzer.deep_cache_fingerprint,
        )
        current = current_classification_run(notice)
        if current is None or current.input_hash != expected_hash:
            result.append(notice.id)
    return result


def _load_notice(db, notice_id: int) -> Notice:
    return db.scalar(select(Notice).where(Notice.id == notice_id).options(
        selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
        selectinload(Notice.decision), selectinload(Notice.action),
    ))


def _run(
    db, ids: list[int], *, force: bool, limit: int | None,
    interval_seconds: float = 0.0, skip_classified: bool = True,
) -> dict:
    stats = {"requested": len(ids), "processed": 0, "classified": 0, "failed": 0}
    errors = []
    for position, notice_id in enumerate(ids[:limit] if limit else ids, start=1):
        if position > 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
        notice = _load_notice(db, notice_id)
        if notice is None or (skip_classified and current_classification_run(notice)):
            continue
        try:
            analyze_notice(db, notice, deep=True, force=force)
            db.expire_all()
            refreshed = _load_notice(db, notice_id)
            stats["classified"] += int(bool(refreshed and current_classification_run(refreshed)))
        except Exception as exc:
            db.rollback()
            stats["failed"] += 1
            errors.append({"notice_id": notice_id, "error": f"{type(exc).__name__}: {str(exc)[:300]}"})
        stats["processed"] += 1
        if position % 25 == 0 or position == len(ids):
            print(json.dumps({"progress": position, **stats}, ensure_ascii=False), flush=True)
    stats["errors"] = errors[:100]
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="현재 기준 미분류 공고 전량 재처리")
    parser.add_argument("--interval-seconds", type=float, default=0.0)
    parser.add_argument("--phase", choices=("prepare", "deep", "all"), default="all")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument("--no-sync", action="store_true")
    args = parser.parse_args()
    if args.shard_count < 1 or not 0 <= args.shard_index < args.shard_count:
        parser.error("--shard-index는 0 이상 --shard-count 미만이어야 합니다.")

    init_db()
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        analyzer = get_analyzer()
        result = {}
        if args.phase in {"prepare", "all"}:
            result["prepare"] = _run(db, _notice_ids(db), force=False, limit=args.limit, interval_seconds=args.interval_seconds)
        if args.phase in {"deep", "all"}:
            deep_ids = _candidate_ids(db, analyzer)
            deep_ids = [
                notice_id for notice_id in deep_ids
                if notice_id % args.shard_count == args.shard_index
            ]
            result["deep"] = _run(
                db, deep_ids, force=True, limit=args.limit,
                interval_seconds=args.interval_seconds, skip_classified=False,
            )

        notices = db.scalars(select(Notice).options(selectinload(Notice.analysis_runs))).all()
        codes = Counter()
        unresolved = 0
        for notice in notices:
            run = current_classification_run(notice)
            if run is None:
                unresolved += 1
                continue
            code = str(_json(run.result_json).get("classification_code") or "")
            codes[code] += 1
        result["final"] = {
            "total": len(notices), "classified": len(notices) - unresolved,
            "unresolved": unresolved, "categories": dict(sorted(codes.items())),
        }
        db.info.pop("suppress_supabase_sync", None)
        if not args.no_sync:
            get_supabase_store().push_all(db)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
