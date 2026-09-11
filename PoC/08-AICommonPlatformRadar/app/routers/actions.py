from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ActionItem, AuditLog
from ..schemas import ActionPatch


router = APIRouter()


@router.patch("/api/actions/{action_id}")
def update_action(action_id: int, patch: ActionPatch, db: Session = Depends(get_db)):
    action = db.get(ActionItem, action_id)
    if not action:
        raise HTTPException(404, "조치 항목을 찾을 수 없습니다.")
    changes = patch.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(action, key, value)
    if changes.get("status") == "contacted" and not action.contacted_at:
        action.contacted_at = datetime.now(timezone.utc)
    db.add(AuditLog(
        event_type="action_updated", entity_type="action_item", entity_id=str(action_id), actor="admin",
        detail_json=json.dumps(changes, ensure_ascii=False),
    ))
    db.commit()
    return {"id": action.id, "status": action.status, "owner": action.owner, "updated_at": action.updated_at}

