from __future__ import annotations

from typing import Any

from .broadcast_review import (
    COMMITTEE_RULES,
    MINISTRY_RULES,
    TOPIC_RULES,
    match_labels,
)
from .transcript_presentation import summarize_utterance


GENERATOR_VERSION = "keyword-review/1.2"
CLASSIFICATION_METHOD = "DETERMINISTIC_KEYWORD_RULE_WITH_SPEAKER_TURNS"


def merge_speaker_turns(final_segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for segment in sorted(final_segments, key=lambda item: int(item["cursor"])):
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        previous = turns[-1] if turns else None
        if (
            previous
            and previous.get("speaker_label") == segment.get("speaker_label")
        ):
            previous["text"] = f'{previous["text"]} {text}'
            previous["last_cursor"] = segment["cursor"]
            previous["evidence_revision_ids"].append(segment["revision_id"])
            previous["segment_count"] += 1
            if len(text) > len(previous["representative_text"]):
                previous["representative_text"] = text
                previous["representative_revision_id"] = segment["revision_id"]
            continue
        turns.append({
            "text": text,
            "speaker_label": segment.get("speaker_label"),
            "first_cursor": segment["cursor"],
            "last_cursor": segment["cursor"],
            "segment_count": 1,
            "evidence_revision_ids": [segment["revision_id"]],
            "representative_text": text,
            "representative_revision_id": segment["revision_id"],
        })
    return turns


def build_broadcast_review(
    broadcast: dict[str, Any], final_segments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Classify readable speaker turns while retaining every revision as evidence."""
    grouped: dict[str, dict[str, Any]] = {}
    source_committee = broadcast.get("committee_name")
    for turn in merge_speaker_turns(final_segments):
        topics = match_labels(turn["text"], TOPIC_RULES) or ["기타 정책"]
        ministries = match_labels(turn["text"], MINISTRY_RULES)
        committees = match_labels(turn["text"], COMMITTEE_RULES)
        if source_committee and source_committee not in committees:
            committees.append(source_committee)
        for topic in topics:
            group = grouped.setdefault(topic, {
                "topic": topic,
                "ministries": set(),
                "committees": set(),
                "turns": [],
            })
            group["ministries"].update(ministries)
            group["committees"].update(committees)
            group["turns"].append(turn)

    result: list[dict[str, Any]] = []
    ordered = sorted(
        grouped.values(),
        key=lambda group: min(int(item["first_cursor"]) for item in group["turns"]),
    )
    for sort_order, group in enumerate(ordered):
        turns = sorted(group["turns"], key=lambda item: int(item["first_cursor"]))
        representative = max(
            turns,
            key=lambda item: (len(item["text"]), -int(item["first_cursor"])),
        )
        result.append({
            "topic": group["topic"],
            "major_quote": summarize_utterance(representative["text"]),
            "speaker_label": representative.get("speaker_label"),
            "ministries": sorted(group["ministries"]),
            "committees": sorted(group["committees"]),
            "segment_count": sum(item["segment_count"] for item in turns),
            "representative_revision_id": representative["representative_revision_id"],
            "evidence_revision_ids": [
                revision_id
                for item in turns
                for revision_id in item["evidence_revision_ids"]
            ],
            "sort_order": sort_order,
        })
    return result
