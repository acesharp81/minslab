from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable

from .official_brief_integration import semantic_tokens
from .official_reconciliation import compact_text
from .transcript_presentation import (
    group_transcript_segments,
    utterance_content_hash,
    utterance_evidence_aliases,
)


def _reviewed_candidate(
    point_id: str, source: str, rows: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> tuple[dict[str, Any], str | None] | None:
    """Apply a stored review only to the exact draft point and source text."""
    if not point_id or not source:
        return None
    source_hash = utterance_content_hash(source)
    for decision in decisions:
        if (
            str(decision.get("point_id") or "") != point_id
            or str(decision.get("source_text_hash") or "") != source_hash
        ):
            continue
        target_id = str(decision.get("official_utterance_id") or "")
        target = next((row for row in rows if row["id"] == target_id), None)
        if target is not None:
            return (
                {**target, "score": 1.0,
                 "method": "REVIEWED_OFFICIAL_SOURCE_V2"},
                str(decision.get("replacement_summary") or "").strip() or None,
            )
    return None


def _grams(text: str, size: int = 5) -> set[str]:
    return {text[index:index + size] for index in range(max(0, len(text) - size + 1))}


def _official_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared = []
    for row in rows:
        name = str(row.get("speaker_name") or "").strip()
        utterance_id = str(row.get("utterance_id") or "").strip()
        if not name or not utterance_id:
            continue
        normalized = compact_text(row.get("text"))
        prepared.append({
            "id": utterance_id,
            "name": name,
            "compact": normalized,
            "grams": _grams(normalized),
            "tokens": semantic_tokens(row.get("text")),
            "length": len(normalized),
        })
    return prepared


def _summary_candidate(
    source: str, summary: str, rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    summary_tokens = semantic_tokens(summary)
    if len(summary_tokens) < 3:
        return None
    source_grams = _grams(compact_text(source))
    summary_grams = _grams(compact_text(summary))
    if not source_grams:
        return None
    source_tokens = semantic_tokens(source)
    summary_source_coverage = len(summary_tokens & source_tokens) / len(summary_tokens)
    by_name: dict[str, tuple[float, float, float, dict[str, Any]]] = {}
    for row in rows:
        official_grams = row["grams"]
        shared = len(source_grams & official_grams)
        if shared < 3:
            continue
        source_coverage = shared / max(1, min(len(source_grams), len(official_grams)))
        summary_coverage = len(summary_tokens & row["tokens"]) / len(summary_tokens)
        summary_character_coverage = (
            len(summary_grams & official_grams) / max(1, len(summary_grams))
        )
        score = (
            source_coverage * 0.5 + summary_coverage * 0.35
            + summary_character_coverage * 0.15
        )
        previous = by_name.get(row["name"])
        if previous is None or score > previous[0]:
            by_name[row["name"]] = (score, summary_coverage, source_coverage, row)
    ranked = sorted(by_name.values(), key=lambda entry: entry[0], reverse=True)
    if not ranked:
        return None
    score, summary_coverage, source_coverage, row = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    strong = score >= 0.5 and summary_coverage >= 0.2 and score - runner_up >= 0.12
    contextual = (
        score >= 0.48 and source_coverage >= 0.6 and row["length"] >= 50
        and summary_coverage >= 0.09 and summary_source_coverage >= 0.3
        and score - runner_up >= 0.08
    )
    if not strong and not contextual:
        return None
    return {**row, "score": round(score, 3), "method": "SUMMARY_SOURCE_V1"}


def _exact_fragment_candidate(
    source: str, summary: str, rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Use a short fragment only when the report repeats it and one name owns it."""
    normalized = compact_text(source)
    if not 8 <= len(normalized) <= 23 or normalized not in compact_text(summary):
        return None
    matches = [row for row in rows if normalized in row["compact"]]
    if len({row["name"] for row in matches}) != 1:
        return None
    row = min(matches, key=lambda candidate: candidate["length"])
    return {**row, "score": 1.0, "method": "UNIQUE_EXACT_FRAGMENT_V1"}


def _group_candidate(
    group: dict[str, Any], rows: list[dict[str, Any]],
) -> tuple[float, float, dict[str, Any]] | None:
    text = compact_text(group.get("text"))
    source_grams = _grams(text)
    if len(text) < 12 or not source_grams:
        return None
    by_name: dict[str, tuple[float, dict[str, Any]]] = {}
    for row in rows:
        shared = len(source_grams & row["grams"])
        if shared < 2:
            continue
        recall = shared / len(source_grams)
        previous = by_name.get(row["name"])
        if previous is None or recall > previous[0]:
            by_name[row["name"]] = (recall, row)
    ranked = sorted(by_name.values(), key=lambda entry: entry[0], reverse=True)
    if not ranked:
        return None
    recall, row = ranked[0]
    runner_up = ranked[1][0] if len(ranked) > 1 else 0.0
    if recall < 0.6 or recall - runner_up < 0.2:
        return None
    return recall, runner_up, row


def _consistent_group_candidate(
    groups: list[dict[str, Any]], summary: str,
    rows: list[dict[str, Any]], cache: dict[str, tuple[float, float, dict[str, Any]] | None],
) -> dict[str, Any] | None:
    summary_tokens = semantic_tokens(summary)
    if len(summary_tokens) < 3 or not groups:
        return None
    picks = []
    for group in groups:
        key = str(group.get("utterance_id") or "")
        if key not in cache:
            cache[key] = _group_candidate(group, rows)
        choice = cache[key]
        if choice is None:
            return None
        picks.append(choice)
    if len({choice[2]["name"] for choice in picks}) != 1:
        return None
    combined_tokens = set().union(*(choice[2]["tokens"] for choice in picks))
    combined_grams = set().union(*(choice[2]["grams"] for choice in picks))
    summary_grams = _grams(compact_text(summary))
    token_coverage = len(summary_tokens & combined_tokens) / len(summary_tokens)
    character_coverage = len(summary_grams & combined_grams) / max(1, len(summary_grams))
    if token_coverage < 0.12 and character_coverage < 0.08:
        return None
    row = max(
        (choice[2] for choice in picks),
        key=lambda candidate: (
            len(summary_tokens & candidate["tokens"]) / len(summary_tokens),
            len(summary_grams & candidate["grams"]),
        ),
    )
    return {**row, "score": round(min(choice[0] for choice in picks), 3),
            "method": "GROUP_CONTENT_V1"}


def resolve_brief_speaker_context(
    brief: dict[str, Any], segments: Iterable[dict[str, Any]],
    official_utterances: Iterable[dict[str, Any]],
    *, reviewed_decisions: Iterable[dict[str, Any]] = (),
) -> tuple[dict[str, Any], dict[str, int]]:
    """Attribute report points only when source text and official speech agree.

    Caption speaker codes are not stable identities. A grouped LIVE utterance can
    contain another person's greeting or short reply. Match the point's summary
    as well as its source text before replacing an existing name. Keep every
    earlier stored version intact; this returns a new presentation projection.
    """
    rows = _official_rows(official_utterances)
    segment_rows = [dict(segment) for segment in segments]
    decisions = [dict(item) for item in reviewed_decisions]
    groups = group_transcript_segments(segment_rows)
    by_evidence: dict[str, dict[str, Any]] = {}
    for group in groups:
        for alias in utterance_evidence_aliases(group.get("utterance_id")):
            by_evidence[alias] = group
        for segment_id in group.get("segment_ids") or []:
            by_evidence[str(segment_id)] = group
    group_cache: dict[str, tuple[float, float, dict[str, Any]] | None] = {}
    projected = deepcopy(brief)
    stats: Counter[str] = Counter()
    for topic in projected.get("topics") or []:
        for point in topic.get("speaker_points") or []:
            original_label = str(point.get("speaker_label") or "").strip()
            evidence_ids = [str(value) for value in point.get("evidence_ids") or []]
            related = {
                str(by_evidence[value].get("utterance_id")): by_evidence[value]
                for value in evidence_ids if value in by_evidence
            }
            source = " ".join(str(group.get("text") or "") for group in related.values())
            summary = str(point.get("summary") or "")
            reviewed = _reviewed_candidate(
                str(point.get("id") or ""), source, rows, decisions,
            )
            selected = reviewed[0] if reviewed else _summary_candidate(source, summary, rows)
            if reviewed and reviewed[1]:
                point["provisional_summary"] = summary
                point["summary"] = reviewed[1]
                point["speaker_summary_reviewed"] = True
                stats["reviewed_summary_repaired"] += 1
            if selected is None:
                selected = _exact_fragment_candidate(source, summary, rows)
            if selected is None:
                selected = _consistent_group_candidate(
                    list(related.values()), summary, rows, group_cache,
                )
            if selected is not None:
                point["speaker_label"] = selected["name"]
                point["speaker_official"] = True
                point["official_evidence_ids"] = [selected["id"]]
                point["speaker_match_method"] = selected["method"]
                point["speaker_match_score"] = selected["score"]
                stats["context_attributed"] += 1
                if original_label != selected["name"]:
                    stats["labels_changed"] += 1
                continue
            if point.get("speaker_official") is True and point.get("official_evidence_ids"):
                summary_tokens = semantic_tokens(summary)
                source_tokens = semantic_tokens(source)
                summary_source_coverage = (
                    len(summary_tokens & source_tokens) / len(summary_tokens)
                    if summary_tokens else 0.0
                )
                if not (
                    " · " in original_label and len(summary_tokens) >= 5
                    and summary_source_coverage < 0.2
                ):
                    stats["existing_evidence_preserved"] += 1
                    continue
                stats["ambiguous_group_labels_removed"] += 1
            if original_label and not original_label.startswith("화자"):
                point["provisional_speaker_label"] = original_label
                point["speaker_label"] = "화자 미확인"
                stats["unsupported_labels_removed"] += 1
            point["speaker_official"] = False
            point.pop("official_evidence_ids", None)
            point["speaker_match_method"] = "UNRESOLVED"
            stats["unresolved"] += 1
    return projected, dict(stats)
