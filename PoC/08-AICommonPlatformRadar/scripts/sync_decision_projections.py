from __future__ import annotations

import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import AuditLog, Notice
from app.schemas import DeepAnalysis
from app.services.analyzer import update_decision_projection
from app.services.workflow_view import current_classification_run


def main() -> None:
    init_db()
    synced = 0
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.analysis_runs), selectinload(Notice.decision),
            selectinload(Notice.action),
        )).all()
        for notice in notices:
            current = current_classification_run(notice)
            if current is None:
                continue
            result = DeepAnalysis.model_validate_json(current.result_json)
            update_decision_projection(db, notice, result)
            synced += 1
        db.add(AuditLog(
            event_type="decision_projections_synchronized", actor="system",
            detail_json=json.dumps({"synced": synced}, ensure_ascii=False),
        ))
        db.commit()
    print(json.dumps({"synced": synced}, ensure_ascii=False))


if __name__ == "__main__":
    main()
