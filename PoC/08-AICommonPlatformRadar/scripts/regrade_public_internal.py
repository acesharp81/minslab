from __future__ import annotations

import hashlib
import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import AnalysisRun, Notice
from app.schemas import DeepAnalysis
from app.services.analyzer import (
    enforce_common_platform_gates,
    is_current_deep_result,
    notice_context,
    update_decision_projection,
)


POLICY_VERSION = "public-internal-v1"


def main() -> None:
    init_db()
    checked = 0
    changed = 0
    changes: list[dict[str, object]] = []
    with SessionLocal() as db:
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments),
            selectinload(Notice.analysis_runs),
            selectinload(Notice.decision),
            selectinload(Notice.action),
        )).all()
        for notice in notices:
            latest = next((
                run for run in sorted(
                    notice.analysis_runs, key=lambda row: row.id or 0, reverse=True,
                )
                if run.run_type == "deep_ai"
                and run.status == "success"
                and is_current_deep_result(run.result_json)
            ), None)
            if latest is None:
                continue
            checked += 1
            try:
                previous = DeepAnalysis.model_validate_json(latest.result_json)
            except Exception:
                continue
            revised = enforce_common_platform_gates(previous, notice_context(notice))
            if not (
                revised.task_scope == "public_institution_internal"
                and previous.model_dump() != revised.model_dump()
            ):
                continue
            digest = hashlib.sha256(
                f"{POLICY_VERSION}|{notice.id}|{latest.id}".encode("utf-8")
            ).hexdigest()
            db.add(AnalysisRun(
                notice_id=notice.id,
                run_type="deep_ai",
                model_name=f"policy-regrade:{POLICY_VERSION}",
                input_hash=digest,
                status="success",
                result_json=revised.model_dump_json(),
                confidence=revised.confidence,
                cost_prompt_tokens=0,
                cost_completion_tokens=0,
            ))
            update_decision_projection(db, notice, revised)
            db.commit()
            changed += 1
            changes.append({
                "notice_id": notice.id,
                "title": notice.title,
                "from": previous.classification_code,
                "to": revised.classification_code,
            })
    print(json.dumps({
        "checked": checked,
        "changed": changed,
        "changes": changes,
    }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
