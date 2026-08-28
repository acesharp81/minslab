from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from typing import Any

from .transcript_presentation import (
    group_transcript_segments,
    utterance_evidence_aliases,
)
from .official_reconciliation import inline_diff


def apply_official_speakers_to_brief(
    brief: dict[str, Any], segments: Iterable[dict[str, Any]],
    matches: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Correct labels without replacing abstractive summaries with excerpts."""
    integrated = deepcopy(brief)
    segment_rows = [dict(item) for item in segments]
    match_map = {
        str(item.get("segment_id")): dict(item)
        for item in matches if item.get("segment_id") and item.get("official_speaker_name")
    }
    utterance_map: dict[str, dict[str, Any]] = {}
    for utterance in group_transcript_segments(segment_rows):
        aliases = set(utterance_evidence_aliases(utterance.get("utterance_id")))
        aliases.update(str(value) for value in utterance.get("segment_ids") or [])
        for alias in aliases:
            utterance_map[alias] = utterance

    def official_matches(evidence_ids: Iterable[object]) -> tuple[list[str], list[str]]:
        names: list[str] = []
        official_ids: list[str] = []
        for evidence_id in evidence_ids:
            utterance = utterance_map.get(str(evidence_id))
            if not utterance:
                continue
            for segment_id in utterance.get("segment_ids", []):
                match = match_map.get(str(segment_id))
                if not match:
                    continue
                name = str(match.get("official_speaker_name") or "").strip()
                official_id = str(match.get("official_utterance_id") or "").strip()
                if name and name not in names:
                    names.append(name)
                if official_id and official_id not in official_ids:
                    official_ids.append(official_id)
        return names, official_ids

    for topic in integrated.get("topics", []):
        corrected_points = []
        for point in topic.get("speaker_points", []):
            evidence_ids = [str(value) for value in point.get("evidence_ids") or []]
            names, official_ids = official_matches(evidence_ids)
            if not names:
                corrected_points.append(point)
                continue
            corrected_points.append({
                **point,
                "speaker_label": " · ".join(names[:4]),
                "speaker_official": True,
                "official_evidence_ids": official_ids,
            })
        _, direct_topic_ids = official_matches(topic.get("evidence_ids") or [])
        topic_official_ids = list(dict.fromkeys([
            *direct_topic_ids,
            *(
            official_id
            for point in corrected_points
            for official_id in point.get("official_evidence_ids") or []
            ),
        ]))
        if topic_official_ids:
            topic["official_evidence_ids"] = topic_official_ids
        topic["speaker_points"] = corrected_points

    for task in integrated.get("tasks", []):
        _, official_ids = official_matches(task.get("evidence_ids") or [])
        if official_ids:
            task["official_evidence_ids"] = official_ids
    return integrated

_NAME_CHAIN_PATTERN = re.compile(r"[가-힣]{3}(?:·[가-힣]{3})+")
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+")


def remove_unsupported_official_claims(
    brief: dict[str, Any], official_rows: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Drop sentences whose joined proper names are absent from official evidence."""
    integrated = deepcopy(brief)
    official_text_by_id = {
        str(row.get("utterance_id")): str(row.get("text") or "")
        for row in official_rows
        if row.get("utterance_id")
    }
    repairs: list[dict[str, Any]] = []
    for topic in integrated.get("topics", []):
        before = str(topic.get("summary") or "").strip()
        evidence_ids = [str(value) for value in topic.get("official_evidence_ids") or []]
        evidence = " ".join(
            official_text_by_id.get(value, "") for value in evidence_ids
        )
        if not before or not evidence:
            continue
        kept: list[str] = []
        removed = False
        for sentence in _SENTENCE_BOUNDARY.split(before):
            chains = _NAME_CHAIN_PATTERN.findall(sentence)
            unsupported = any(
                any(part not in evidence for part in chain.split("·"))
                for chain in chains
            )
            if unsupported:
                removed = True
            else:
                kept.append(sentence.strip())
        after = " ".join(kept).strip()
        if not removed or not after or after == before:
            continue
        spans = inline_diff(before, after)
        topic["summary"] = after
        topic.setdefault("_official_diffs", {})["summary"] = spans
        repairs.append({
            "entity_type": "topic", "entity_id": str(topic.get("id") or ""),
            "validation_rule": "UNSUPPORTED_JOINED_PERSON_NAMES",
            "operation": "UPDATE", "field": "summary", "title": topic.get("title"),
            "before": before, "after": after, "new_text": after, "spans": spans,
            "official_utterance_ids": evidence_ids,
        })
    return integrated, repairs


def merge_validation_repairs(
    changes: Iterable[dict[str, Any]], repairs: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    repair_items = [dict(item) for item in repairs]
    repaired_keys = {
        (item.get("entity_type"), item.get("entity_id"), item.get("field"))
        for item in repair_items
    }
    kept = [
        dict(change) for change in changes
        if (change.get("entity_type"), change.get("entity_id"), change.get("field"))
        not in repaired_keys
    ]
    return [*kept, *repair_items]
