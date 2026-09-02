from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from .live_topic_lineage import build_live_topic_clusters

SESSION_GAP_SECONDS = 30 * 60
SESSION_VERSION = "meeting-sessions/1.0"


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def build_meeting_sessions(
    utterances: Iterable[dict[str, Any]],
    *,
    lifecycle_by_broadcast: dict[object, str] | None = None,
    gap_seconds: int = SESSION_GAP_SECONDS,
) -> list[dict[str, Any]]:
    """Partition persisted utterances into 1..N resumable sessions.

    A session boundary is evidence-derived from a caption gap. It is a
    provisional presentation/checkpoint boundary, not an official meeting end.
    """
    if gap_seconds < 60:
        raise ValueError("gap_seconds must be at least 60")
    lifecycle = lifecycle_by_broadcast or {}
    grouped: dict[object, list[dict[str, Any]]] = defaultdict(list)
    for utterance in utterances:
        if not str(utterance.get("text") or "").strip():
            continue
        grouped[utterance.get("broadcast_id")].append(utterance)

    result: list[dict[str, Any]] = []
    for broadcast_id, items in grouped.items():
        ordered = sorted(
            items,
            key=lambda item: (
                _as_datetime(item.get("start_at") or item.get("end_at"))
                or datetime.min.replace(tzinfo=timezone.utc),
                int(item.get("first_cursor") or item.get("last_cursor") or 0),
            ),
        )
        buckets: list[list[dict[str, Any]]] = []
        previous_end: datetime | None = None
        for utterance in ordered:
            started_at = _as_datetime(utterance.get("start_at") or utterance.get("end_at"))
            if (
                buckets
                and started_at
                and previous_end
                and (started_at - previous_end).total_seconds() >= gap_seconds
            ):
                buckets.append([])
            if not buckets:
                buckets.append([])
            buckets[-1].append(utterance)
            previous_end = _as_datetime(utterance.get("end_at")) or started_at or previous_end

        live = str(lifecycle.get(broadcast_id) or "").upper() == "LIVE"
        for index, bucket in enumerate(buckets, start=1):
            session_id = f"session-{index}"
            for utterance in bucket:
                utterance["meeting_session_id"] = session_id
                utterance["meeting_session_number"] = index
            clusters, insight_count, source_title_count = build_live_topic_clusters(bucket)
            started = _as_datetime(bucket[0].get("start_at") or bucket[0].get("end_at"))
            ended = _as_datetime(bucket[-1].get("end_at") or bucket[-1].get("start_at"))
            active = live and index == len(buckets)
            result.append({
                "id": session_id,
                "broadcast_id": str(broadcast_id) if broadcast_id is not None else None,
                "number": index,
                "status": "ACTIVE" if active else "CHECKPOINTED",
                "started_at": _iso(started),
                "ended_at": None if active else _iso(ended),
                "last_activity_at": _iso(ended),
                "utterance_count": len(bucket),
                "source_insight_count": insight_count,
                "source_topic_title_count": source_title_count,
                "topic_count": len(clusters),
                "topics": [{
                    "id": cluster["id"],
                    "title": cluster["title"],
                    "utterance_count": cluster["utterance_count"],
                    "owners": cluster["owners"],
                    "tasks": cluster["tasks"],
                    "evidence_ids": cluster["utterance_ids"],
                } for cluster in clusters],
            })
    return result


def attach_meeting_sessions(
    brief: dict[str, Any],
    utterances: Iterable[dict[str, Any]],
    *,
    lifecycle_by_broadcast: dict[object, str] | None = None,
) -> dict[str, Any]:
    items = list(utterances)
    sessions = build_meeting_sessions(
        items, lifecycle_by_broadcast=lifecycle_by_broadcast,
    )
    result = deepcopy(brief)
    result["meeting_session_version"] = SESSION_VERSION
    result["meeting_session_count"] = len(sessions)
    result["meeting_sessions"] = sessions
    return result
