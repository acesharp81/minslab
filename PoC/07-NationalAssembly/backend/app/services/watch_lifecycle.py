"""Pure topic completion and message presentation; no model/network calls."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .live_topic_lineage import build_live_topic_clusters

TOPIC_GRACE = timedelta(minutes=5)


def closed_for_summary(
    utterances: list[dict[str, Any]], *, lifecycle: str,
    now: datetime, boundary: bool = False,
) -> list[dict[str, Any]]:
    candidates = utterances[:-1] if lifecycle == "LIVE" and not boundary else utterances
    return [u for u in candidates if boundary or lifecycle == "ENDED"
            or u.get("is_final") or now - u["end_at"] >= TOPIC_GRACE]


def declaration_kind(text: str, speaker: str) -> str | None:
    # Require the presiding role and a declaration, never a proposal/quotation.
    if not re.search(r"위원장|의장|의장대리", speaker):
        return None
    compact = re.sub(r"\s+", "", text).strip(" .。")
    if re.fullmatch(
        r"(?:그러면|이상으로|지금부터)?(?:잠시)?정회를선포합니다[.!。]*", compact
    ):
        return "RECESS"
    if re.fullmatch(r"(?:그러면|이상으로)?산회를선포합니다[.!。]*", compact):
        return "ENDED"
    return None


def topic_projection(
    utterances: list[dict[str, Any]], detected_segments: set[str]
) -> list[dict[str, Any]]:
    clusters, _, _ = build_live_topic_clusters(utterances)
    by_id = {str(u["utterance_id"]): u for u in utterances}
    topics = []
    for cluster in clusters:
        members = [by_id[key] for key in cluster["utterance_ids"]]
        if not any(
            detected_segments.intersection(
                str(s).split(":")[0] for s in u["segment_ids"]
            )
            for u in members
        ):
            continue
        topics.append(
            {
                "title": cluster["title"],
                "utterance_count": len(members),
                "speaker_count": len({u.get("speaker_label") for u in members}),
                "last_at": max(u["end_at"] for u in members).isoformat(),
                "points": [
                    {
                        "speaker": u.get("speaker_label") or "화자 확인 중",
                        "summary": u["summary"],
                        "utterance_id": str(u["utterance_id"]),
                        "segment_ids": [str(s).split(":")[0] for s in u["segment_ids"]],
                        "revision_ids": [str(s) for s in u["revision_ids"]],
                        "text": u["text"],
                    }
                    for u in members
                ],
            }
        )
    return topics


def completion_ready(
    utterances: list[dict[str, Any]],
    detected_segments: set[str],
    *,
    now: datetime,
    boundary: bool = False,
) -> bool:
    if not utterances or not detected_segments:
        return False
    # Unknown/unprocessed statements may be answers without the keyword.
    # Never interpret a summary failure or an unfinished turn as a transition.
    pending = [u for u in utterances if not u.get("ready")]
    if boundary and pending:
        return False
    topics = topic_projection(utterances, detected_segments)
    if not topics:
        return False
    if boundary:
        return True
    related = {p["utterance_id"] for t in topics for p in t["points"]}
    last_related = max(
        i for i, u in enumerate(utterances) if str(u["utterance_id"]) in related
    )
    following = utterances[last_related + 1 :]
    if not following or not following[0].get("ready"):
        return False
    deadline = following[0]["end_at"] + TOPIC_GRACE
    if now < deadline:
        return False
    # An unknown turn inside the grace period could return to this topic.
    # New unprocessed turns after the complete window must not starve older topics.
    return not any(u.get("start_at", u["end_at"]) <= deadline for u in pending)


def rank_topics(topics: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    # Union overlapping evidence across rules, without duplicating the same answer.
    merged: list[dict[str, Any]] = []
    for topic in topics:
        candidate = {**topic, "points": list(topic["points"])}
        ids = {p["utterance_id"] for p in candidate["points"]}
        for other in list(merged):
            if ids.intersection(p["utterance_id"] for p in other["points"]):
                candidate["points"] = list(
                    {
                        p["utterance_id"]: p
                        for p in other["points"] + candidate["points"]
                    }.values()
                )
                candidate["last_at"] = max(candidate["last_at"], other["last_at"])
                ids.update(p["utterance_id"] for p in other["points"])
                merged.remove(other)
        candidate["utterance_count"] = len(candidate["points"])
        candidate["speaker_count"] = len({p["speaker"] for p in candidate["points"]})
        merged.append(candidate)
    return sorted(
        merged,
        key=lambda t: (
            -t["utterance_count"],
            -t["speaker_count"],
            -datetime.fromisoformat(t["last_at"]).timestamp(),
            t["title"],
        ),
    )[:limit]


def compact_message(title: str, body: str) -> str:
    text = f"{title}\n{body}"
    if len(text) <= 200:
        return text
    return text[:182].rstrip() + "…\n전체 요약은 링크에서 확인"
