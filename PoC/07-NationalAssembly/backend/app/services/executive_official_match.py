from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo


MEETING_NUMBER = re.compile(r"제\s*(\d+)\s*회")
SEOUL = ZoneInfo("Asia/Seoul")


def meeting_number(value: Any) -> int | None:
    match = MEETING_NUMBER.search(str(value or ""))
    return int(match.group(1)) if match else None


def official_date(value: Any) -> date | None:
    digits = re.sub(r"[^0-9]", "", str(value or ""))
    if len(digits) < 8:
        return None
    try:
        return date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]))
    except ValueError:
        return None


def reconcile_executive_official_matches(
    connection: Any, official_items: list[dict[str, Any]],
) -> int:
    candidates: dict[int, list[dict[str, Any]]] = {}
    for item in official_items:
        number = item.get("meeting_number") or meeting_number(item.get("title"))
        published = official_date(item.get("published_date"))
        briefing_id = item.get("news_id")
        if not number or not briefing_id:
            continue
        candidates.setdefault(int(number), []).append({
            "number": int(number), "date": published,
            "briefing_id": str(briefing_id), "content_hash": item.get("content_hash"),
        })
    rows = connection.execute(
        """
        SELECT id, title, detected_at
        FROM live_broadcasts
        WHERE institution = 'EXECUTIVE' AND source_system = 'ktv.go.kr'
          AND lifecycle_status = 'ENDED'
        ORDER BY detected_at DESC
        """
    ).fetchall()
    matched = 0
    for broadcast_id, title, detected_at in rows:
        number = meeting_number(title)
        if not number or number not in candidates:
            continue
        meeting_date = detected_at.astimezone(SEOUL).date() if isinstance(detected_at, datetime) else None
        exact = [item for item in candidates[number] if item["date"] == meeting_date]
        if len(exact) == 1:
            selected, method = exact[0], "MEETING_NUMBER_AND_DATE"
        elif len(candidates[number]) == 1:
            selected, method = candidates[number][0], "UNIQUE_MEETING_NUMBER"
        else:
            continue
        changed = connection.execute(
            """
            INSERT INTO executive_official_matches (
                broadcast_id, official_briefing_id, meeting_number, meeting_date,
                match_method, official_content_hash
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id) DO UPDATE SET
                official_briefing_id = EXCLUDED.official_briefing_id,
                meeting_number = EXCLUDED.meeting_number,
                meeting_date = EXCLUDED.meeting_date,
                match_method = EXCLUDED.match_method,
                official_content_hash = EXCLUDED.official_content_hash,
                updated_at = now()
            WHERE (
                executive_official_matches.official_briefing_id,
                executive_official_matches.meeting_number,
                executive_official_matches.meeting_date,
                executive_official_matches.match_method,
                executive_official_matches.official_content_hash
            ) IS DISTINCT FROM (
                EXCLUDED.official_briefing_id,
                EXCLUDED.meeting_number,
                EXCLUDED.meeting_date,
                EXCLUDED.match_method,
                EXCLUDED.official_content_hash
            )
            RETURNING broadcast_id
            """,
            (
                broadcast_id, selected["briefing_id"], number, selected["date"],
                method, selected["content_hash"],
            ),
        ).fetchone()
        matched += int(changed is not None)
    return matched
