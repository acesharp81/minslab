from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Iterable


def apply_official_speakers(
    segments: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Use the current official speaker as the presentation grouping key.

    The provisional label is retained only on the in-memory read model. Adjacent
    segments with the same official speaker merge naturally, while a caption
    block spanning multiple official speakers splits at its existing segment
    boundaries.
    """
    result: list[dict[str, Any]] = []
    for source in segments:
        item = dict(source)
        reconciliation = item.get("official_reconciliation")
        official_name = str(
            reconciliation.get("official_speaker_name") or ""
        ).strip() if isinstance(reconciliation, dict) else ""
        if reconciliation and reconciliation.get("status") == "MATCHED" and official_name:
            item["provisional_speaker_label"] = item.get("speaker_label")
            item["speaker_label"] = official_name
            item["source_speaker_label"] = f"official:{official_name}"
            item["speaker_official"] = True
        result.append(item)
    return result


def overlay_confirmed_brief_speakers(
    provisional_brief: dict[str, Any], official_brief: dict[str, Any],
) -> dict[str, Any]:
    """Present evidenced official names without changing the stored LIVE brief."""
    confirmed: dict[tuple[str, str], dict[str, Any]] = {}
    for topic in official_brief.get("topics") or []:
        topic_id = str(topic.get("id") or "")
        for point in topic.get("speaker_points") or []:
            point_id = str(point.get("id") or "")
            label = str(point.get("speaker_label") or "").strip()
            if (
                topic_id and point_id and point.get("speaker_official") is True
                and point.get("official_evidence_ids") and label
                and not label.startswith("화자")
            ):
                confirmed[(topic_id, point_id)] = point

    presented = deepcopy(provisional_brief)
    for topic in presented.get("topics") or []:
        topic_id = str(topic.get("id") or "")
        for point in topic.get("speaker_points") or []:
            source = confirmed.get((topic_id, str(point.get("id") or "")))
            if source is None:
                label = str(point.get("speaker_label") or "").strip()
                if label and not label.startswith("화자"):
                    point["provisional_speaker_label"] = label
                    point["speaker_label"] = "화자 미확인"
                continue
            point["provisional_speaker_label"] = point.get("speaker_label")
            point["speaker_label"] = source["speaker_label"]
            point["speaker_official"] = True
            point["official_evidence_ids"] = list(source["official_evidence_ids"])
    return presented


_SPEAKER_REFERENCE = re.compile(r"화자\s*(\d+)(은|는|이|가|을|를|과|와)?")


def _reference_particle(label: str, particle: str | None) -> str:
    if not particle:
        return ""
    last = label[-1]
    if not ("가" <= last <= "힣"):
        return particle
    has_final = (ord(last) - ord("가")) % 28 != 0
    pairs = {"은": ("은", "는"), "는": ("은", "는"),
             "이": ("이", "가"), "가": ("이", "가"),
             "을": ("을", "를"), "를": ("을", "를"),
             "과": ("과", "와"), "와": ("과", "와")}
    before, after = pairs[particle]
    return before if has_final else after


def present_brief_speaker_references(
    brief: dict[str, Any], provisional_brief: dict[str, Any] | None = None,
    *, neutralize_topic_summaries: bool = False,
) -> dict[str, Any]:
    """Replace numeric speaker codes in prose using only unambiguous topic evidence.

    LIVE speaker codes can be reused for different people. Their meaning is
    therefore local to a topic, and any conflicting or missing attribution is
    rendered as a neutral participant reference instead of a guessed name.
    """
    presented = deepcopy(brief)
    original_topics = {
        str(topic.get("id") or ""): topic
        for topic in (provisional_brief or {}).get("topics") or []
    }

    def replacement(value: Any, names: dict[str, str]) -> Any:
        if not isinstance(value, str):
            return value
        def substitute(match: re.Match[str]) -> str:
            label = names.get(match.group(1)) or (
                "한 참석자" if match.group(1) == "0" else
                "다른 참석자" if match.group(1) == "1" else "또 다른 참석자"
            )
            return label + _reference_particle(label, match.group(2))

        return _SPEAKER_REFERENCE.sub(substitute, value)

    def replace_field(item: dict[str, Any], field: str, names: dict[str, str]) -> None:
        before = item.get(field)
        after = replacement(before, names)
        if after == before:
            return
        item[field] = after
        diffs = item.get("_official_diffs")
        if isinstance(diffs, dict):
            diffs.pop(field, None)

    for field in ("headline", "summary"):
        replace_field(presented, field, {})
    for topic in presented.get("topics") or []:
        original = original_topics.get(str(topic.get("id") or "")) or topic
        original_points = {
            str(point.get("id") or ""): point
            for point in original.get("speaker_points") or []
        }
        by_code: dict[str, list[str | None]] = {}
        for point in topic.get("speaker_points") or []:
            original_point = original_points.get(str(point.get("id") or "")) or point
            original_label = str(original_point.get("speaker_label") or "")
            match = _SPEAKER_REFERENCE.search(original_label)
            if not match:
                continue
            label = str(point.get("speaker_label") or "").strip()
            verified = bool(
                point.get("speaker_official") is True
                and point.get("official_evidence_ids")
                and label and not label.startswith("화자") and " · " not in label
            )
            by_code.setdefault(match.group(1), []).append(label if verified else None)
        names = {
            code: values[0]
            for code, values in by_code.items()
            if values and all(value == values[0] and value for value in values)
        }
        replace_field(topic, "title", names)
        summary_before = topic.get("summary")
        replace_field(topic, "summary", {} if neutralize_topic_summaries else names)
        if neutralize_topic_summaries and topic.get("summary") != summary_before:
            topic["provisional_summary"] = summary_before
            topic["summary_verification"] = "PROVISIONAL_ATTRIBUTION_REMOVED"
        for point in topic.get("speaker_points") or []:
            replace_field(point, "summary", names)
            label = str(point.get("speaker_label") or "").strip()
            if _SPEAKER_REFERENCE.match(label) and not (
                point.get("speaker_official") is True
                and point.get("official_evidence_ids")
            ):
                point.setdefault("provisional_speaker_label", label)
                point["speaker_label"] = "화자 미확인"
    for group in presented.get("topic_groups") or []:
        for field in ("title", "summary"):
            replace_field(group, field, {})
    for task in presented.get("tasks") or []:
        for field in ("title", "description", "summary"):
            replace_field(task, field, {})
    return presented
