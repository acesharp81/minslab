from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import AuditLog, Notice, PipelineRun
from app.services.workflow_view import current_classification_run


def _json(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def main() -> None:
    init_db()
    with SessionLocal() as db:
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments), selectinload(Notice.analysis_runs),
        )).all()
        categories = Counter()
        current_simple = 0
        deep_candidates = 0
        unresolved = []
        for notice in notices:
            simple = next((
                run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
                if run.run_type == "simple_ai" and run.status == "success"
            ), None)
            if simple:
                current_simple += 1
            current = current_classification_run(notice)
            if current is None:
                unresolved.append(notice.id)
            else:
                deep_candidates += int(current.status == "success")
                categories[str(_json(current.result_json).get("classification_code") or "")] += 1

        if unresolved:
            raise RuntimeError(
                f"정산 불가: total={len(notices)}, unresolved={len(unresolved)}"
            )
        source = db.scalar(select(PipelineRun).where(
            PipelineRun.run_kind == "collect",
        ).order_by(PipelineRun.started_at.desc()))
        if source is None:
            raise RuntimeError("정산할 수집 배치가 없습니다.")
        now = datetime.now(timezone.utc)
        detail = {
            "source_collect_run_id": source.id,
            "total": len(notices),
            "current_simple": current_simple,
            "deep_candidates": deep_candidates,
            "rule_or_simple_screened": len(notices) - deep_candidates,
            "classified_total": len(notices),
            "unresolved": 0,
            "analysis_failed": 0,
            "analysis_deferred": 0,
            "screened_non_ai": int(categories.get("6", 0)),
            "classification_distribution": dict(sorted(categories.items())),
        }
        reconciliation = PipelineRun(
            run_kind="analysis_reconcile", mode="external-command-a",
            status="success", started_at=now, finished_at=now,
            stats_json=json.dumps(detail, ensure_ascii=False),
        )
        db.add(reconciliation)
        db.flush()
        db.add(AuditLog(
            event_type="analysis_backlog_reconciled", entity_type="pipeline_run",
            entity_id=str(reconciliation.id), actor="system",
            detail_json=json.dumps(detail, ensure_ascii=False),
        ))
        db.commit()
        print(json.dumps(detail, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
