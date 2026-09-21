from __future__ import annotations

import argparse
import hashlib
import json

import _bootstrap  # noqa: F401
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import AnalysisRun, Notice
from app.schemas import DeepAnalysis
from app.services.analyzer import (
    CURRENT_CRITERIA_VERSION,
    enforce_common_platform_gates,
    is_current_deep_result,
    notice_context,
    update_decision_projection,
)
from app.services.supabase_store import get_supabase_store


def _criteria(result_json: str | None) -> str:
    try:
        value = json.loads(result_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return ""
    return str(value.get("criteria_version") or "") if isinstance(value, dict) else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="현재 기준 결과도 최신 결정 로직으로 다시 투영합니다.",
    )
    args = parser.parse_args()
    init_db()
    stats = {
        "regraded": 0,
        "already_current": 0,
        "no_reusable_result": 0,
        "validation_failed": 0,
        "classification_distribution": {},
    }
    changed: list[object] = []
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments),
            selectinload(Notice.analysis_runs),
            selectinload(Notice.decision),
            selectinload(Notice.action),
        )).all()
        for notice in notices:
            ordered = sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
            current = next((
                row for row in ordered
                if row.run_type == "deep_ai"
                and (
                    row.status == "success"
                    or (row.status == "skipped" and row.model_name == "rule-gate")
                )
                and is_current_deep_result(row.result_json)
            ), None)
            if current and not args.force:
                try:
                    current_result = DeepAnalysis.model_validate_json(current.result_json)
                except ValidationError:
                    stats["validation_failed"] += 1
                    continue
                update_decision_projection(db, notice, current_result)
                changed.append(current)
                if notice.decision:
                    changed.append(notice.decision)
                stats["already_current"] += 1
                continue
            source = current if args.force and current else next((
                row for row in ordered
                if row.run_type == "deep_ai"
                and (
                    row.status == "success"
                    or (row.status == "skipped" and row.model_name == "rule-gate")
                )
                and bool(_criteria(row.result_json))
                and _criteria(row.result_json) != CURRENT_CRITERIA_VERSION
            ), None)
            if source is None:
                stats["no_reusable_result"] += 1
                continue
            try:
                payload = json.loads(source.result_json)
                payload["criteria_version"] = CURRENT_CRITERIA_VERSION
                previous = DeepAnalysis.model_validate(payload)
                result = enforce_common_platform_gates(previous, notice_context(notice))
            except (json.JSONDecodeError, ValidationError, ValueError):
                stats["validation_failed"] += 1
                continue

            fingerprint = hashlib.sha256(
                f"{CURRENT_CRITERIA_VERSION}|{source.id}|{source.result_json}".encode()
            ).hexdigest()
            status = "skipped" if source.model_name == "rule-gate" else "success"
            model_name = "rule-gate" if status == "skipped" else f"policy-regrade-v6:{source.model_name}"
            new_run = AnalysisRun(
                notice_id=notice.id,
                run_type="deep_ai",
                model_name=model_name,
                input_hash=fingerprint,
                status=status,
                result_json=result.model_dump_json(),
                confidence=result.confidence,
                cost_prompt_tokens=0,
                cost_completion_tokens=0,
            )
            db.add(new_run)
            update_decision_projection(db, notice, result)
            changed.append(new_run)
            if notice.decision:
                changed.append(notice.decision)
            stats["regraded"] += 1
            distribution = stats["classification_distribution"]
            distribution[result.classification_code] = distribution.get(result.classification_code, 0) + 1

        db.commit()
        db.info.pop("suppress_supabase_sync", None)
        store = get_supabase_store()
        stats["supabase_synced"] = store.push_changes(changed, []) if changed else store.enabled

    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
