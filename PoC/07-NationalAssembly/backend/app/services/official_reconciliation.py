from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

from .official_brief_integration import semantic_tokens

INTEGRATION_VERSION = "official-reconciliation/1.3"
SPEAKER_MATCH_METHOD = "ORDERED_CHAR_NGRAM_9_V1"
MIN_ALIGNMENT_CONFIDENCE = 0.34
_COMPACT_PATTERN = re.compile(r"[^0-9a-zA-Z가-힣]+")
_SEMANTIC_CHARACTER_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]")


def compact_text(value: object) -> str:
    return _COMPACT_PATTERN.sub("", str(value or "").casefold())


def _ngrams(value: str, size: int = 9) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def align_live_segments(
    segments: Iterable[dict[str, Any]],
    official_utterances: Iterable[dict[str, Any]],
    *, minimum_confidence: float = MIN_ALIGNMENT_CONFIDENCE,
) -> list[dict[str, Any]]:
    """Align caption revisions to official utterances without inventing speakers.

    Character shingles tolerate caption punctuation and spacing differences. The
    official sequence order is used only as a tie-breaker so repeated procedural
    phrases do not jump across the meeting.
    """
    official = [dict(item) for item in official_utterances]
    live = [dict(item) for item in segments]
    if not official or not live:
        return []
    official_grams: list[set[str]] = []
    frequency: Counter[str] = Counter()
    for item in official:
        grams = _ngrams(compact_text(item.get("text")))
        official_grams.append(grams)
        frequency.update(grams)
    index: dict[str, list[int]] = defaultdict(list)
    for official_index, grams in enumerate(official_grams):
        for gram in grams:
            if frequency[gram] <= 8:
                index[gram].append(official_index)

    matches: list[dict[str, Any]] = []
    previous_sequence = 0
    for live_index, segment in enumerate(live):
        revision_id = segment.get("revision_id")
        normalized = compact_text(segment.get("text"))
        grams = _ngrams(normalized)
        if not revision_id or len(normalized) < 12 or len(grams) < 2:
            continue
        votes: Counter[int] = Counter()
        for gram in grams:
            for candidate in index.get(gram, ()):
                votes[candidate] += 1
        if not votes:
            continue
        expected = live_index / max(1, len(live) - 1) * max(1, len(official) - 1)
        ranked: list[tuple[float, float, int]] = []
        for candidate, overlap in votes.items():
            raw = overlap / max(1, len(grams))
            order_distance = abs(candidate - expected) / max(1, len(official))
            backwards = max(0, previous_sequence - int(
                official[candidate].get("sequence_number") or candidate + 1
            ))
            adjusted = raw - min(0.16, order_distance * 0.24) - min(0.18, backwards * 0.01)
            ranked.append((adjusted, raw, candidate))
        adjusted, raw, candidate = max(ranked)
        confidence = min(0.999, max(0.0, raw * 0.9 + max(0.0, adjusted) * 0.1))
        if raw < minimum_confidence or votes[candidate] < 2:
            continue
        official_item = official[candidate]
        sequence = int(official_item.get("sequence_number") or candidate + 1)
        previous_sequence = max(previous_sequence, sequence)
        matches.append({
            "revision_id": revision_id,
            "segment_id": segment.get("segment_id"),
            "source_speaker_label": segment.get("source_speaker_label")
                or segment.get("speaker_label"),
            "official_utterance_id": official_item.get("utterance_id"),
            "official_sequence_number": sequence,
            "official_speaker_name": official_item.get("speaker_name"),
            "official_speaker_role": official_item.get("speaker_role"),
            "confidence": round(confidence, 3),
        })
    return matches


def speaker_reconciliation_stats(matches: Iterable[dict[str, Any]]) -> dict[str, Any]:
    match_rows = list(matches)
    source_to_official: dict[str, set[str]] = defaultdict(set)
    official_to_source: dict[str, set[str]] = defaultdict(set)
    for match in match_rows:
        source = str(match.get("source_speaker_label") or "").strip()
        official = str(match.get("official_speaker_name") or "").strip()
        if not source or not official:
            continue
        source_to_official[source].add(official)
        official_to_source[official].add(source)
    return {
        "matched_segments": len(match_rows),
        "confirmed_speakers": len(official_to_source),
        "split_source_labels": sum(len(names) > 1 for names in source_to_official.values()),
        "merged_source_labels": sum(len(labels) > 1 for labels in official_to_source.values()),
    }


def _semantic_characters(value: str) -> tuple[list[str], list[int]]:
    characters: list[str] = []
    positions: list[int] = []
    for index, character in enumerate(value):
        if _SEMANTIC_CHARACTER_PATTERN.fullmatch(character):
            characters.append(character.casefold())
            positions.append(index)
    return characters, positions


def _raw_end(value: str, positions: list[int], semantic_end: int) -> int:
    if semantic_end <= 0:
        return 0
    if semantic_end >= len(positions):
        return len(value)
    return positions[semantic_end - 1] + 1


def _character_opcodes(
    before: str, after: str,
) -> tuple[list[tuple[str, int, int, int, int]], list[int], list[int]]:
    old_characters, old_positions = _semantic_characters(before)
    new_characters, new_positions = _semantic_characters(after)
    matcher = SequenceMatcher(
        None, old_characters, new_characters, autojunk=False,
    )
    return matcher.get_opcodes(), old_positions, new_positions


def minimal_patch_text(before: object, after: object) -> str:
    """Keep provisional wording and replace only official changed character runs.

    Alignment ignores spaces and punctuation.  This prevents one spacing error
    from turning the rest of a Korean sentence into a replacement.  When the
    two texts share too little wording, the provisional text remains in the
    main report and the official alternative is presented in the change report.
    """
    old = str(before or "")
    new = str(after or "")
    if not old or not new or old == new:
        return new or old
    compact_old = compact_text(old)
    compact_new = compact_text(new)
    similarity = SequenceMatcher(
        None, compact_old, compact_new, autojunk=False,
    ).ratio()
    if min(len(compact_old), len(compact_new)) >= 20 and similarity < 0.46:
        return old
    opcodes, old_positions, new_positions = _character_opcodes(old, new)
    old_cursor = 0
    new_cursor = 0
    parts: list[str] = []
    previous_opcode = ""
    for opcode, _old_start, old_end, _new_start, new_end in opcodes:
        old_raw_end = _raw_end(old, old_positions, old_end)
        new_raw_end = _raw_end(new, new_positions, new_end)
        if opcode == "equal":
            old_piece = old[old_cursor:old_raw_end]
            if previous_opcode and previous_opcode != "equal":
                new_piece = new[new_cursor:new_raw_end]
                new_prefix = re.match(
                    r"^[^0-9A-Za-z가-힣]*", new_piece,
                ).group(0)
                old_piece = new_prefix + re.sub(
                    r"^[^0-9A-Za-z가-힣]*", "", old_piece,
                )
            parts.append(old_piece)
        elif opcode in {"insert", "replace"}:
            parts.append(new[new_cursor:new_raw_end])
        old_cursor = old_raw_end
        new_cursor = new_raw_end
        previous_opcode = opcode
    patched = "".join(parts).strip()
    # A punctuation-only boundary is excluded from alignment.  When both the
    # preserved provisional sentence and the inserted official phrase carry a
    # full stop, remove only an exact double stop; keep a real "..." ellipsis.
    return re.sub(r"(?<!\.)\.\.(?!\.)", ".", patched)


def inline_diff(before: object, after: object) -> list[dict[str, str]]:
    """Build a whitespace-independent character diff with readable raw spans."""
    old = str(before or "")
    new = str(after or "")
    if old == new:
        return [{"kind": "equal", "text": new}]
    opcodes, old_positions, new_positions = _character_opcodes(old, new)
    spans: list[dict[str, str]] = []
    old_cursor = 0
    new_cursor = 0
    for opcode, _old_start, old_end, _new_start, new_end in opcodes:
        old_raw_end = _raw_end(old, old_positions, old_end)
        new_raw_end = _raw_end(new, new_positions, new_end)
        old_text = old[old_cursor:old_raw_end]
        new_text = new[new_cursor:new_raw_end]
        if opcode == "equal":
            spans.append({"kind": "equal", "text": new_text})
        elif opcode == "insert":
            spans.append({"kind": "added", "text": new_text})
        elif opcode == "delete":
            spans.append({"kind": "deleted", "text": old_text})
        else:
            if old_text:
                spans.append({"kind": "deleted", "text": old_text})
            if new_text:
                spans.append({"kind": "changed", "text": new_text, "before": old_text})
        old_cursor = old_raw_end
        new_cursor = new_raw_end
    return [span for span in spans if span.get("text")]


def _entity_map(brief: dict[str, Any], entity_type: str) -> dict[str, dict[str, Any]]:
    key = "topics" if entity_type == "topic" else "tasks"
    return {
        str(item.get("id")): item for item in brief.get(key, [])
        if isinstance(item, dict) and item.get("id")
    }


_TOPIC_FAMILY_SUFFIXES = ("권", "적", "성")


def _topic_family_tokens(*values: object) -> set[str]:
    result: set[str] = set()
    for token in semantic_tokens(*values):
        normalized = token
        for suffix in _TOPIC_FAMILY_SUFFIXES:
            if len(normalized) >= 3 and normalized.endswith(suffix):
                normalized = normalized[:-1]
                break
        if len(normalized) >= 2:
            result.add(normalized)
    return result


def _find_duplicate_topic(
    integrated: dict[str, Any], edit: dict[str, Any],
) -> dict[str, Any] | None:
    candidate_title = _topic_family_tokens(edit.get("title"), edit.get("new_text"))
    candidate_all = _topic_family_tokens(
        edit.get("title"), edit.get("new_text"), edit.get("summary"),
    )
    for topic in integrated.get("topics", []):
        existing_title = _topic_family_tokens(topic.get("title"))
        if len(candidate_title & existing_title) < 2:
            continue
        existing_all = _topic_family_tokens(topic.get("title"), topic.get("summary"))
        if len(candidate_all & existing_all) >= 3:
            return topic
    return None


def _added_task_topic_id(
    integrated: dict[str, Any], requested_topic_id: str,
    aliases: dict[str, str], title: str,
) -> str | None:
    resolved = aliases.get(requested_topic_id, requested_topic_id)
    topic = _entity_map(integrated, "topic").get(resolved)
    if not topic:
        return None
    shared = semantic_tokens(title) & semantic_tokens(
        topic.get("title"), topic.get("summary"),
    )
    return resolved if len(shared) >= 2 else None


def apply_official_edits(
    live_brief: dict[str, Any], edits: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    integrated = deepcopy(live_brief)
    accepted: list[dict[str, Any]] = []
    added_topic_aliases: dict[str, str] = {}
    suppressed_added_topics: set[str] = set()
    ordered_edits = sorted(
        (dict(item) for item in edits),
        key=lambda item: item.get("operation") == "ADD" and item.get("entity_type") != "topic",
    )
    for raw in ordered_edits:
        edit = dict(raw)
        entity_type = str(edit.get("entity_type") or "")
        operation = str(edit.get("operation") or "")
        entity_id = str(edit.get("entity_id") or "")
        field = str(edit.get("field") or "")
        target: dict[str, Any] | None
        if entity_type == "meeting":
            target = integrated
        elif entity_type in {"topic", "task"}:
            target = _entity_map(integrated, entity_type).get(entity_id)
        else:
            continue
        if operation == "ADD" and entity_type in {"topic", "task"}:
            requested_topic_id = str(edit.get("topic_id") or "")
            if entity_type == "topic":
                duplicate = _find_duplicate_topic(integrated, edit)
                if duplicate:
                    official_ids = [
                        str(value) for value in edit.get("official_utterance_ids") or []
                        if value
                    ]
                    if official_ids:
                        duplicate["official_evidence_ids"] = list(dict.fromkeys([
                            *(duplicate.get("official_evidence_ids") or []), *official_ids,
                        ]))
                    if requested_topic_id:
                        suppressed_added_topics.add(requested_topic_id)
                    continue
            resolved_topic_id = None
            if entity_type == "task":
                if requested_topic_id in suppressed_added_topics:
                    continue
                resolved_topic_id = _added_task_topic_id(
                    integrated, requested_topic_id, added_topic_aliases, str(edit.get("title") or ""))
                if not resolved_topic_id: continue
            collection = integrated.setdefault(
                "topics" if entity_type == "topic" else "tasks", [],
            )
            new_id = f"official-{entity_type}-{len(collection) + 1}"
            target = {
                "id": new_id,
                "title": str(edit.get("title") or edit.get("new_text") or "").strip(),
                "summary": str(edit.get("summary") or "").strip(),
                "ministries": list(edit.get("ministries") or []),
                "topic_id": resolved_topic_id,
                "speaker_points": [], "evidence_ids": [],
                "official_evidence_ids": list(edit.get("official_utterance_ids") or []),
                "_official_change": "added",
            }
            if not target["title"]:
                continue
            collection.append(target)
            edit["entity_id"] = new_id
            if entity_type == "topic" and requested_topic_id:
                added_topic_aliases[requested_topic_id] = new_id
            edit["after"] = target["title"]
            edit["spans"] = [{"kind": "added", "text": target["title"]}]
            accepted.append(edit)
            continue
        official_ids = [
            str(value) for value in edit.get("official_utterance_ids") or []
            if value
        ]
        if official_ids:
            target["official_evidence_ids"] = list(dict.fromkeys([
                *(target.get("official_evidence_ids") or []), *official_ids,
            ]))
        if target is None:
            continue
        if operation == "DELETE" and entity_type in {"topic", "task"}:
            target["_official_change"] = "deleted"
            edit["before"] = str(target.get("title") or "")
            edit["after"] = ""
            edit["spans"] = [{"kind": "deleted", "text": edit["before"]}]
            accepted.append(edit)
            continue
        if operation != "UPDATE" or field not in {
            "headline", "summary", "title", "ministries",
        }:
            continue
        before = target.get(field)
        official_after: Any = list(edit.get("new_values") or []) if field == "ministries" else str(
            edit.get("new_text") or ""
        ).strip()
        if not official_after or before == official_after:
            continue
        after = (
            official_after
            if field == "ministries"
            else minimal_patch_text(before, official_after)
        )
        if before == after:
            edit["presentation_status"] = "FULL_REWRITE_SUPPRESSED"
            edit["before"] = before
            edit["after"] = official_after
            edit["spans"] = [{"kind": "equal", "text": str(before or "")}]
            accepted.append(edit)
            continue
        target[field] = after
        target.setdefault("_official_diffs", {})[field] = (
            inline_diff(", ".join(before or []), ", ".join(after))
            if field == "ministries" else inline_diff(before, after)
        )
        edit["before"] = before
        edit["after"] = official_after
        edit["display_after"] = after
        edit["spans"] = target["_official_diffs"][field]
        accepted.append(edit)
    return integrated, accepted
