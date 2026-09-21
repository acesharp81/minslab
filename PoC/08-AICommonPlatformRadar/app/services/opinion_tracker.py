from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..models import ActionItem, AuditLog, Notice
from .g2b_client import G2BClient, KST
from .workflow_view import current_classification_run, json_object


TRACKING_KEY = "_poc08_opinion_tracking"
TRACKED_ACTION_STATES = {
    "in_progress", "contacted", "reflected", "not_reflected",
    "completed_uses", "completed_not_used", "completed_ineligible", "completed_non_ai",
}


def cached_opinion_tracking(notice: Notice) -> dict[str, Any]:
    cached = json_object(notice.raw_payload_json).get(TRACKING_KEY)
    return cached if isinstance(cached, dict) else {}


def _compact(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", str(value or "")).casefold()


def _input_datetime(value: Any) -> datetime | None:
    raw = re.sub(r"[^0-9]", "", str(value or ""))
    for fmt, size in (("%Y%m%d%H%M%S", 14), ("%Y%m%d%H%M", 12), ("%Y%m%d", 8)):
        if len(raw) < size:
            continue
        try:
            return datetime.strptime(raw[:size], fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


def _guidance(notice: Notice) -> str:
    run = current_classification_run(notice)
    return str(json_object(run.result_json if run else None).get("guidance_message") or "")


def _match_root(notice: Notice, roots: list[dict[str, Any]]) -> dict[str, Any] | None:
    expected = _compact(_guidance(notice))
    contacted_at = notice.action.contacted_at if notice.action else None
    if contacted_at and contacted_at.tzinfo is None:
        contacted_at = contacted_at.replace(tzinfo=timezone.utc)

    ranked: list[tuple[float, dict[str, Any]]] = []
    for row in roots:
        actual = _compact(row.get("opninCntnts"))
        similarity = SequenceMatcher(None, expected, actual).ratio() if expected and actual else 0.0
        # 기존 형식의 문안을 제출한 뒤 안내문이 개정된 경우에도 법적 근거와 핵심 용어로 식별한다.
        shared_basis = all(token in actual for token in ("공통기반", "제27조제2항"))
        entered = _input_datetime(row.get("inptDt"))
        near_contact = bool(
            contacted_at and entered
            and contacted_at - timedelta(days=1) <= entered.astimezone(timezone.utc) <= contacted_at + timedelta(days=3)
        )
        score = similarity + (0.35 if shared_basis else 0.0) + (0.2 if near_contact else 0.0)
        ranked.append((score, row))
    if not ranked:
        return None
    score, best = max(ranked, key=lambda item: item[0])
    return best if score >= 0.52 else None


def _tracking_result(notice: Notice, rows: list[dict[str, Any]]) -> dict[str, Any]:
    roots = [row for row in rows if str(row.get("rplyNo") or "0") == "0"]
    match = _match_root(notice, roots)
    now = datetime.now(timezone.utc).isoformat()
    result: dict[str, Any] = {
        "checked_at": now,
        "opinion_count": len(roots),
        "reply_count": sum(str(row.get("rplyNo") or "0") != "0" for row in rows),
    }
    if not notice.action or notice.action.status not in TRACKED_ACTION_STATES:
        result.update(status="not_submitted", status_label="의견 등록 전")
        return result
    if not match:
        result.update(
            status="unmatched",
            status_label="등록 의견 식별 필요",
            detail="나라장터 의견은 조회되지만 이 서비스에서 관리 중인 의견을 자동 식별하지 못했습니다.",
        )
        return result

    opinion_no = str(match.get("opninNo") or "")
    replies = [
        row for row in rows
        if str(row.get("opninNo") or "") == opinion_no and str(row.get("rplyNo") or "0") != "0"
    ]
    replies.sort(key=lambda row: str(row.get("inptDt") or ""))
    result.update({
        "status": "replied" if replies else "submitted_waiting",
        "status_label": f"답변 등록 {len(replies)}건" if replies else "의견 등록 · 답변 대기",
        "matched_opinion_no": opinion_no,
        "matched_title": str(match.get("opninTitl") or ""),
        "matched_at": str(match.get("inptDt") or ""),
        "matched_reply_count": len(replies),
        "submitted_content": str(match.get("opninCntnts") or ""),
    })
    if replies:
        latest = replies[-1]
        result.update(
            latest_reply_content=str(latest.get("opninCntnts") or ""),
            latest_reply_at=str(latest.get("inptDt") or ""),
        )
    return result


async def refresh_notice_opinions(
    db: Session, notice: Notice, *, client: G2BClient | None = None,
) -> dict[str, Any]:
    if notice.stage != "prenotice":
        raise ValueError("사전규격 공고만 의견 답변을 확인할 수 있습니다.")
    payload = json_object(notice.raw_payload_json)
    registration_no = str(payload.get("bfSpecRgstNo") or notice.notice_no or "").strip()
    rows = await (client or G2BClient()).prenotice_opinions(registration_no)
    tracking = _tracking_result(notice, rows)
    payload[TRACKING_KEY] = tracking
    notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)
    db.add(AuditLog(
        event_type="prenotice_opinion_checked", entity_type="notice", entity_id=str(notice.id),
        detail_json=json.dumps(tracking, ensure_ascii=False),
    ))
    db.commit()
    return tracking


async def refresh_tracked_opinions(db: Session) -> dict[str, int]:
    notices = db.scalars(
        select(Notice)
        .join(ActionItem)
        .where(Notice.stage == "prenotice", ActionItem.status.in_(TRACKED_ACTION_STATES))
        .options(selectinload(Notice.action), selectinload(Notice.analysis_runs))
    ).all()
    client = G2BClient()
    stats = {"checked": 0, "replied": 0, "failed": 0}
    for notice in notices:
        try:
            tracking = await refresh_notice_opinions(db, notice, client=client)
            stats["checked"] += 1
            stats["replied"] += int(tracking.get("status") == "replied")
        except Exception as exc:
            db.rollback()
            stats["failed"] += 1
            payload = json_object(notice.raw_payload_json)
            payload[TRACKING_KEY] = {
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "status": "error",
                "status_label": "답변 확인 실패",
                "detail": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            notice.raw_payload_json = json.dumps(payload, ensure_ascii=False, default=str)
            db.commit()
    return stats
