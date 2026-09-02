from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from typing import Any

SUMMARY_MAX_CHARS = 180
TURN_CONTINUATION_GAP_SECONDS = 5 * 60


def executive_meeting_content_segments(
    segments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Exclude KTV pre-show material once the formal meeting opening is observed."""
    source = [dict(item) for item in segments]
    ordered = sorted(
        source,
        key=lambda value: (
            int(value.get("cursor") or 0),
            str(value.get("received_at") or ""),
        ),
    )
    for index, item in enumerate(ordered):
        normalized = re.sub(r"[\s,·]+", "", str(item.get("text") or ""))
        if "국무회의를시작하겠습니다" in normalized:
            return ordered[index:]
    return source


def default_speaker_name(source_label: str | None) -> str:
    """Return a readable label without pretending that a source code is a name."""
    label = str(source_label or "").strip()
    if not label or label == "-1":
        return "화자 미확인"
    if label.lstrip("-").isdigit():
        return f"화자 {label} · 이름 미확인"
    if label.startswith("chunk-") and ":speaker" in label:
        return "화자 미확인"
    return label


def expand_source_speaker_segments(
    segments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Split one Assembly caption revision into its source-provided speaker pieces."""
    result: list[dict[str, Any]] = []
    for source in segments:
        item = dict(source)
        raw_parts = item.pop("source_speaker_segments", None)
        parts = [
            {
                "speaker": str(part.get("speaker") or "").strip(),
                "text": str(part.get("text") or "").strip(),
            }
            for part in raw_parts or []
            if isinstance(part, dict) and str(part.get("text") or "").strip()
        ]
        if not parts:
            result.append(item)
            continue
        parent_segment_id = str(item.get("segment_id") or "")
        parent_source_id = str(item.get("source_segment_id") or parent_segment_id)
        for index, part in enumerate(parts):
            derived = dict(item)
            derived["source_parent_segment_id"] = parent_segment_id
            derived["segment_id"] = f"{parent_segment_id}:{index}"
            derived["source_segment_id"] = f"{parent_source_id}:{index}"
            derived["speaker_label"] = part["speaker"] or None
            derived["text"] = part["text"]
            if index:
                derived["insight_hint"] = None
                derived["official_reconciliation"] = None
            result.append(derived)
    return result


def apply_speaker_overrides(
    segments: Iterable[dict[str, Any]],
    overrides: dict[tuple[Any, str], str],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in expand_source_speaker_segments(segments):
        item = dict(source)
        source_label = str(item.get("speaker_label") or "").strip()
        override = overrides.get((item.get("broadcast_id"), source_label))
        item["source_speaker_label"] = source_label or None
        item["speaker_label"] = override or default_speaker_name(source_label)
        item["speaker_overridden"] = bool(override)
        result.append(item)
    return result


def _joined_text(parts: list[str]) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip()).strip()


def summarize_utterance(text: str, *, max_chars: int = SUMMARY_MAX_CHARS) -> str:
    normalized = _joined_text([text])
    if len(normalized) <= max_chars:
        return normalized
    clipped = normalized[: max_chars + 1]
    boundary = clipped.rfind(" ")
    if boundary >= max_chars // 2:
        clipped = clipped[:boundary]
    else:
        clipped = clipped[:max_chars]
    return f"{clipped.rstrip()}…"


def utterance_content_hash(text: str) -> str:
    normalized = _joined_text([text])
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utterance_evidence_aliases(utterance_id: Any) -> set[str]:
    """Keep saved brief evidence valid after source speaker-piece expansion."""
    value = str(utterance_id or "")
    parent = value.split(":", 1)[0]
    return {alias for alias in (value, parent) if alias}



def group_transcript_segments(
    segments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a presentation read model while preserving every source segment id."""
    ordered = sorted(
        (dict(item) for item in segments if str(item.get("text") or "").strip()),
        key=lambda item: (
            item.get("received_at") or datetime.min,
            int(item.get("cursor") or 0),
        ),
    )
    groups: list[dict[str, Any]] = []
    for item in ordered:
        text = str(item.get("text") or "").strip()
        source_label = item.get("source_speaker_label")
        previous = groups[-1] if groups else None
        transient_unknown = (
            str(source_label or "").strip() in {"", "-1"}
            and item.get("is_final") is not True
            and previous is not None
            and previous["broadcast_id"] == item.get("broadcast_id")
        )
        if transient_unknown:
            source_label = previous.get("source_speaker_label")
            item["speaker_label"] = previous.get("speaker_label")
            item["speaker_overridden"] = previous.get("speaker_overridden", False)
        current_at = item.get("received_at")
        previous_at = previous.get("end_at") if previous else None
        within_turn_gap = not (
            isinstance(current_at, datetime) and isinstance(previous_at, datetime)
        ) or (current_at - previous_at).total_seconds() <= TURN_CONTINUATION_GAP_SECONDS
        same_turn = bool(
            previous
            and previous["broadcast_id"] == item.get("broadcast_id")
            and previous.get("source_speaker_label") == source_label
            and within_turn_gap
        )
        if not same_turn:
            groups.append({
                "utterance_id": str(item.get("segment_id")),
                "broadcast_id": item.get("broadcast_id"),
                "speaker_label": item.get("speaker_label"),
                "source_speaker_label": source_label,
                "speaker_overridden": bool(item.get("speaker_overridden")),
                "text": text,
                "summary": summarize_utterance(text),
                "content_hash": utterance_content_hash(text),
                "summary_kind": "EXTRACTIVE_FALLBACK",
                "start_at": item.get("received_at"),
                "end_at": item.get("received_at"),
                "first_cursor": item.get("cursor"),
                "last_cursor": item.get("cursor"),
                "segment_count": 1,
                "segment_ids": [item.get("segment_id")],
                "revision_ids": [item.get("revision_id")],
                "is_final": item.get("is_final") is True,
                "insight_hints": [item["insight_hint"]] if item.get("insight_hint") else [],
                "official_reconciliations": [item["official_reconciliation"]]
                if item.get("official_reconciliation") else [],
            })
            continue
        previous["text"] = _joined_text([previous["text"], text])
        previous["summary"] = summarize_utterance(previous["text"])
        previous["content_hash"] = utterance_content_hash(previous["text"])
        previous["end_at"] = item.get("received_at")
        previous["last_cursor"] = item.get("cursor")
        previous["segment_count"] += 1
        previous["segment_ids"].append(item.get("segment_id"))
        previous["revision_ids"].append(item.get("revision_id"))
        previous["is_final"] = previous["is_final"] and item.get("is_final") is True
        if item.get("insight_hint"):
            previous["insight_hints"].append(item["insight_hint"])
        if item.get("official_reconciliation"):
            previous["official_reconciliations"].append(item["official_reconciliation"])
    return groups
