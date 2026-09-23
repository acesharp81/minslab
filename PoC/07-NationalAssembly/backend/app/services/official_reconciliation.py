from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

from .official_brief_integration import semantic_tokens

INTEGRATION_VERSION = "official-reconciliation/1.6"
SPEAKER_MATCH_METHOD = "ORDERED_BIDIRECTIONAL_CHAR_NGRAM_9_V2"
MIN_ALIGNMENT_CONFIDENCE = 0.34
MIN_INLINE_PATCH_SIMILARITY = 0.58
_COMPACT_PATTERN = re.compile(r"[^0-9a-zA-Z가-힣]+")
_SEMANTIC_CHARACTER_PATTERN = re.compile(r"[0-9a-zA-Z가-힣]")
_NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)?")
_POLARITY_MARKERS = (
    "아니", "않", "없", "안", "못", "부인", "취소", "철회", "반대",
)
_ACTION_MARKERS = (
    "검토", "추진", "확정", "의결", "지시", "요청", "제출",
    "시행", "집행", "편성", "보류", "중단", "폐지", "신설", "확대",
    "축소", "증액", "감액", "찬성", "반대", "보고", "발표",
)
_STYLE_TOKEN_SUFFIXES = (
    "하겠습니다", "했습니다", "하였습니다", "하겠다고", "하였다고",
    "한다고", "했다고", "합니다", "하였다", "했다", "한다", "하며",
    "하고", "하여", "하기", "됩니다", "되었습니다", "됐습니다",
    "되었다", "됐다고", "된다", "으로써", "로써", "입니다", "이었다",
    "였다",
)


def compact_text(value: object) -> str:
    return _COMPACT_PATTERN.sub("", str(value or "").casefold())


def _comparison_tokens(value: object) -> set[str]:
    result: set[str] = set()
    for source in semantic_tokens(value):
        token = source
        for suffix in _STYLE_TOKEN_SUFFIXES:
            if len(token) >= len(suffix) + 2 and token.endswith(suffix):
                token = token[:-len(suffix)]
                break
        if token and token not in _ACTION_MARKERS:
            result.add(token)
    return result


def _marker_counts(value: object, candidates: Iterable[str]) -> Counter[str]:
    text = compact_text(value)
    return Counter({marker: text.count(marker) for marker in candidates if marker in text})


def _semantic_units(value: object) -> Counter[tuple[object, ...]]:
    """Bind institutions/content to their nearby action before ignoring order."""
    text = " ".join(str(value or "").split())
    action_pattern = "|".join(map(re.escape, _ACTION_MARKERS))
    connector = re.compile(
        rf"(?P<action>{action_pattern})(?:하고|했으며|하며|하여)\s*",
    )
    units: list[str] = []
    for sentence in re.split(r"(?<=[.!?。;])\s+", text):
        cursor = 0
        for match in connector.finditer(sentence):
            units.append(sentence[cursor:match.end("action")])
            cursor = match.end()
        units.append(sentence[cursor:])
    signatures: Counter[tuple[object, ...]] = Counter()
    for unit in units:
        tokens = tuple(sorted(_comparison_tokens(unit)))
        actions = tuple(sorted(_marker_counts(unit, _ACTION_MARKERS).items()))
        polarities = tuple(sorted(_marker_counts(unit, _POLARITY_MARKERS).items()))
        numbers = tuple(sorted(Counter(_NUMBER_PATTERN.findall(unit)).items()))
        if tokens or actions or polarities or numbers:
            signatures[(tokens, actions, polarities, numbers)] += 1
    return signatures


def style_only_equivalent(before: object, after: object) -> bool:
    """Return true only when formatting/order changed without a factual signal.

    Whitespace and punctuation are ignored first.  For bullet/prose or clause
    reordering, order-independent normalized content tokens are compared while
    numbers, polarity, and decision/action markers must remain identical.  The
    conservative exact-token rule prevents a new ministry, amount, decision,
    or action from being hidden as a style edit.
    """
    old = " ".join(str(before or "").split())
    new = " ".join(str(after or "").split())
    if not old or not new:
        return old == new
    compact_old = compact_text(old)
    compact_new = compact_text(new)
    if compact_old == compact_new:
        return True
    if Counter(_NUMBER_PATTERN.findall(old)) != Counter(_NUMBER_PATTERN.findall(new)):
        return False
    if _marker_counts(old, _POLARITY_MARKERS) != _marker_counts(
        new, _POLARITY_MARKERS,
    ):
        return False
    if _marker_counts(old, _ACTION_MARKERS) != _marker_counts(new, _ACTION_MARKERS):
        return False
    old_tokens = _comparison_tokens(old)
    new_tokens = _comparison_tokens(new)
    if len(old_tokens) < 2 or old_tokens != new_tokens:
        return False
    if _semantic_units(old) != _semantic_units(new):
        return False
    length_ratio = min(len(compact_old), len(compact_new)) / max(
        len(compact_old), len(compact_new), 1,
    )
    return length_ratio >= 0.55


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
            official_sequence = int(
                official[candidate].get("sequence_number") or candidate + 1
            )
            # A caption may be a fragment of one official utterance, but a
            # generic fragment must not win merely because all of its shingles
            # occur in a much longer official speech. Balance both directions.
            live_coverage = overlap / max(1, len(grams))
            official_coverage = overlap / max(1, len(official_grams[candidate]))
            dice = (2 * overlap) / max(
                1, len(grams) + len(official_grams[candidate]),
            )
            containment = min(live_coverage, official_coverage)
            semantic_score = dice * 0.72 + containment * 0.28
            order_distance = abs(candidate - expected) / max(1, len(official))
            backwards = max(0, previous_sequence - official_sequence)
            if backwards > 1:
                continue
            adjusted = (
                semantic_score
                - min(0.16, order_distance * 0.24)
                - min(0.18, backwards * 0.04)
            )
            ranked.append((adjusted, semantic_score, candidate))
        if not ranked:
            continue
        ranked.sort(reverse=True)
        adjusted, semantic_score, candidate = ranked[0]
        confidence = min(
            0.999,
            max(0.0, semantic_score * 0.9 + max(0.0, adjusted) * 0.1),
        )
        runner_up = ranked[1][0] if len(ranked) > 1 else -1.0
        runner_up_semantic = ranked[1][1] if len(ranked) > 1 else -1.0
        ambiguous_containment = bool(
            len(ranked) > 1
            and votes[candidate] / max(1, len(grams)) >= 0.80
            and votes[ranked[1][2]] / max(1, len(grams)) >= 0.80
            and confidence < 0.85
        )
        if (
            semantic_score < minimum_confidence
            or votes[candidate] < 2
            or ambiguous_containment
            or (adjusted - runner_up < 0.035 and confidence < 0.72)
            or (
                semantic_score - runner_up_semantic < 0.025
                and confidence < 0.80
            )
        ):
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


def _preserve_official_sentence_boundaries(
    provisional_piece: str, official_piece: str,
) -> str:
    """Keep provisional spacing but restore official sentence punctuation."""
    old_characters, old_positions = _semantic_characters(provisional_piece)
    new_characters, new_positions = _semantic_characters(official_piece)
    if old_characters != new_characters or not old_positions:
        return provisional_piece
    strong = re.compile(r"[.!?。;:]")

    def merged_gap(old_gap: str, new_gap: str) -> str:
        if strong.search(old_gap) or not strong.search(new_gap):
            return old_gap
        marks = "".join(strong.findall(new_gap))
        whitespace = " " if any(char.isspace() for char in old_gap + new_gap) else ""
        return marks + whitespace

    # A leading separator belongs to the preceding opcode/chunk. Restoring it
    # here can prepend a moved sentence with an orphan full stop.
    parts = [provisional_piece[:old_positions[0]]]
    for index, old_position in enumerate(old_positions):
        parts.append(provisional_piece[old_position])
        old_end = old_positions[index + 1] if index + 1 < len(old_positions) else len(
            provisional_piece,
        )
        new_end = new_positions[index + 1] if index + 1 < len(new_positions) else len(
            official_piece,
        )
        parts.append(merged_gap(
            provisional_piece[old_position + 1:old_end],
            official_piece[new_positions[index] + 1:new_end],
        ))
    return "".join(parts)


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
    if style_only_equivalent(old, new):
        return old
    compact_old = compact_text(old)
    compact_new = compact_text(new)
    similarity = SequenceMatcher(
        None, compact_old, compact_new, autojunk=False,
    ).ratio()
    moved_patch = _minimal_patch_with_moves(old, new)
    if moved_patch is not None:
        return moved_patch
    if (
        min(len(compact_old), len(compact_new)) >= 20
        and similarity < MIN_INLINE_PATCH_SIMILARITY
    ):
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
            new_piece = new[new_cursor:new_raw_end]
            old_piece = _preserve_official_sentence_boundaries(
                old_piece, new_piece,
            )
            if previous_opcode and previous_opcode != "equal":
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


def _raw_diff_chunks(before: str, after: str) -> list[dict[str, str]]:
    opcodes, old_positions, new_positions = _character_opcodes(before, after)
    chunks: list[dict[str, str]] = []
    old_cursor = 0
    new_cursor = 0
    for opcode, _old_start, old_end, _new_start, new_end in opcodes:
        old_raw_end = _raw_end(before, old_positions, old_end)
        new_raw_end = _raw_end(after, new_positions, new_end)
        chunks.append({
            "opcode": opcode,
            "old_text": before[old_cursor:old_raw_end],
            "new_text": after[new_cursor:new_raw_end],
        })
        old_cursor = old_raw_end
        new_cursor = new_raw_end
    return chunks


def _basic_inline_diff(before: str, after: str) -> list[dict[str, str]]:
    if style_only_equivalent(before, after):
        return [{"kind": "equal", "text": after}]
    spans: list[dict[str, str]] = []
    for chunk in _raw_diff_chunks(before, after):
        opcode = chunk["opcode"]
        old_text = chunk["old_text"]
        new_text = chunk["new_text"]
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
    return spans


def _move_similarity(before: str, after: str) -> float:
    old = compact_text(before)
    new = compact_text(after)
    if min(len(old), len(new)) < 6:
        return 0.0
    matcher = SequenceMatcher(None, old, new, autojunk=False)
    ratio = matcher.ratio()
    longest = matcher.find_longest_match().size / max(1, min(len(old), len(new)))
    if ratio < 0.52 or longest < 0.5:
        return 0.0
    return (ratio + longest) / 2


def _pair_moved_chunks(
    chunks: list[dict[str, str]],
) -> tuple[dict[int, int], dict[int, int]]:
    candidates: list[tuple[float, int, int]] = []
    for old_index, deleted in enumerate(chunks):
        if deleted["opcode"] != "delete":
            continue
        for new_index, inserted in enumerate(chunks):
            if inserted["opcode"] != "insert":
                continue
            score = _move_similarity(deleted["old_text"], inserted["new_text"])
            if score:
                candidates.append((score, old_index, new_index))
    paired_delete: dict[int, int] = {}
    paired_insert: dict[int, int] = {}
    for _score, old_index, new_index in sorted(candidates, reverse=True):
        if old_index in paired_delete or new_index in paired_insert:
            continue
        paired_delete[old_index] = new_index
        paired_insert[new_index] = old_index
    return paired_delete, paired_insert


def _minimal_patch_with_moves(before: str, after: str) -> str | None:
    """Patch a moved clause at its provisional location, not its new position."""
    chunks = _raw_diff_chunks(before, after)
    paired_delete, paired_insert = _pair_moved_chunks(chunks)
    if not paired_delete:
        return None
    parts: list[str] = []
    for index, chunk in enumerate(chunks):
        opcode = chunk["opcode"]
        if index in paired_delete:
            moved = chunks[paired_delete[index]]
            parts.append(minimal_patch_text(chunk["old_text"], moved["new_text"]))
        elif index in paired_insert:
            continue
        elif opcode == "equal":
            parts.append(chunk["old_text"])
        elif opcode == "replace":
            parts.append(minimal_patch_text(chunk["old_text"], chunk["new_text"]))
        elif opcode == "delete":
            # A low-confidence unpaired deletion must not erase provisional copy.
            parts.append(chunk["old_text"])
        elif opcode == "insert":
            parts.append(chunk["new_text"])
    patched = "".join(parts).strip()
    return re.sub(r"(?<!\.)\.\.(?!\.)", ".", patched) if patched else before


def _merge_inline_spans(spans: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    for source in spans:
        span = dict(source)
        if not span.get("text"):
            continue
        if (
            merged
            and merged[-1].get("kind") == span.get("kind")
            and (
                span.get("kind") != "changed"
                or merged[-1].get("before") == span.get("before")
            )
        ):
            merged[-1]["text"] += span["text"]
            continue
        merged.append(span)
    return merged


def inline_diff(before: object, after: object) -> list[dict[str, str]]:
    """Build a spacing-independent, move-aware character diff.

    SequenceMatcher normally reports a moved clause as one deletion and one
    insertion.  Similar delete/insert chunks are paired and compared locally,
    so unchanged moved wording is rendered once and only the real edit inside
    the moved clause is highlighted.
    """
    old = str(before or "")
    new = str(after or "")
    if old == new:
        return [{"kind": "equal", "text": new}]
    if style_only_equivalent(old, new):
        return [{"kind": "equal", "text": new}]
    chunks = _raw_diff_chunks(old, new)
    paired_delete, paired_insert = _pair_moved_chunks(chunks)

    spans: list[dict[str, str]] = []
    for index, chunk in enumerate(chunks):
        if index in paired_delete:
            continue
        if index in paired_insert:
            deleted = chunks[paired_insert[index]]
            spans.extend(_basic_inline_diff(deleted["old_text"], chunk["new_text"]))
            continue
        spans.extend(_basic_inline_diff(chunk["old_text"], chunk["new_text"]))
    return _merge_inline_spans(spans)


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
        if field != "ministries" and style_only_equivalent(before, official_after):
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
