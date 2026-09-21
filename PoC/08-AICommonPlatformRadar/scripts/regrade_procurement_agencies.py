from __future__ import annotations

import hashlib
import json

import _bootstrap  # noqa: F401
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db import SessionLocal, init_db
from app.models import AnalysisRun, AuditLog, Notice
from app.schemas import DeepAnalysis
from app.services.analyzer import (
    enforce_common_platform_gates,
    is_current_deep_result,
    notice_context,
    update_decision_projection,
)
from app.services.supabase_store import get_supabase_store


POLICY_VERSION = "procurement-demand-agency-v1"


def _agency_values(notice: Notice) -> tuple[str, str, str | None]:
    try:
        raw = json.loads(notice.raw_payload_json or "{}")
    except (json.JSONDecodeError, TypeError):
        raw = {}
    if not isinstance(raw, dict):
        return "", "", None
    announcing = str(raw.get("orderInsttNm") or raw.get("ntceInsttNm") or "").strip()
    demand = str(raw.get("rlDminsttNm") or raw.get("dminsttNm") or "").strip()
    demand_code = str(raw.get("rlDminsttCd") or raw.get("dminsttCd") or "").strip() or None
    return announcing, demand, demand_code


def main() -> None:
    init_db()
    stats = {"checked": 0, "agency_changed": 0, "analysis_changed": 0}
    transitions: dict[str, int] = {}
    sync_rows: list[object] = []
    with SessionLocal() as db:
        db.info["suppress_supabase_sync"] = True
        notices = db.scalars(select(Notice).options(
            selectinload(Notice.attachments),
            selectinload(Notice.analysis_runs),
            selectinload(Notice.decision),
            selectinload(Notice.action),
        )).all()
        for notice in notices:
            announcing, demand, demand_code = _agency_values(notice)
            if "조달청" not in announcing or not demand or demand == announcing:
                continue
            stats["checked"] += 1
            if notice.agency_name != demand or (demand_code and notice.agency_code != demand_code):
                notice.agency_name = demand
                if demand_code:
                    notice.agency_code = demand_code
                stats["agency_changed"] += 1
                sync_rows.append(notice)

            latest = next((
                run for run in sorted(notice.analysis_runs, key=lambda row: row.id or 0, reverse=True)
                if run.run_type == "deep_ai" and run.status == "success"
                and is_current_deep_result(run.result_json)
            ), None)
            if latest is None or latest.model_name == f"policy-regrade:{POLICY_VERSION}":
                continue
            try:
                previous = DeepAnalysis.model_validate_json(latest.result_json)
            except Exception:
                continue
            revised = enforce_common_platform_gates(previous, notice_context(notice))
            if previous.model_dump() == revised.model_dump():
                continue
            digest = hashlib.sha256(
                f"{POLICY_VERSION}|{notice.id}|{latest.id}".encode("utf-8")
            ).hexdigest()
            run = AnalysisRun(
                notice_id=notice.id,
                run_type="deep_ai",
                model_name=f"policy-regrade:{POLICY_VERSION}",
                input_hash=digest,
                status="success",
                result_json=revised.model_dump_json(),
                confidence=revised.confidence,
                cost_prompt_tokens=0,
                cost_completion_tokens=0,
            )
            db.add(run)
            update_decision_projection(db, notice, revised)
            db.flush()
            sync_rows.extend([run, notice.decision])
            stats["analysis_changed"] += 1
            transition = f"{previous.classification_code}->{revised.classification_code}"
            transitions[transition] = transitions.get(transition, 0) + 1

        audit = AuditLog(
            event_type="procurement_agency_regrade",
            entity_type="policy",
            entity_id=POLICY_VERSION,
            actor="system",
            detail_json=json.dumps({**stats, "transitions": transitions}, ensure_ascii=False),
        )
        db.add(audit)
        db.commit()
        sync_rows.append(audit)
        synced = get_supabase_store().push_changes(sync_rows, [])
        db.info.pop("suppress_supabase_sync", None)
    print(json.dumps({**stats, "transitions": transitions, "supabase_synced": synced}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
