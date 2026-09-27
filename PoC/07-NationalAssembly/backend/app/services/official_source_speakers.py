from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
from typing import Any, Iterable


_SPEAKER_PARTICLES = {"은": "는", "는": "는", "이": "가", "가": "가",
                      "을": "를", "를": "를", "과": "와", "와": "와"}


def _neutralize_numeric_speakers(value: str) -> str:
    return re.sub(
        r"화자\s*\d+(은|는|이|가|을|를|과|와)?",
        lambda match: "발언자" + _SPEAKER_PARTICLES.get(match.group(1), ""),
        value,
    )


def source_first_speaker_points(
    brief: dict[str, Any], official_items: Iterable[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, int]]:
    """Present official speech under its recorded speaker, preserving draft claims.

    A LIVE summary may contradict or combine different official speeches. The
    official view therefore quotes the selected official source directly. Items
    without a current-document source stay in a separate draft-only collection.
    """
    by_id = {
        str(item["utterance_id"]): item for item in official_items
        if item.get("utterance_id") and str(item.get("speaker_label") or "").strip()
        and str(item.get("text") or "").strip()
    }
    result = deepcopy(brief)
    stats = {"official_source_points": 0, "draft_only_points": 0,
             "split_speaker_points": 0, "missing_source_ids": 0,
             "neutralized_topic_summaries": 0}
    for topic in result.get("topics") or []:
        # The topic synopsis is an AI paraphrase of LIVE captions. Its numeric
        # speaker IDs cannot safely be turned into official names, even when
        # individual points are sourced. Preserve the original for comparison.
        summary = str(topic.get("summary") or "")
        neutral_summary = _neutralize_numeric_speakers(summary)
        if neutral_summary != summary:
            topic["provisional_summary"] = summary
            topic["summary"] = neutral_summary
            topic["summary_verification"] = "PROVISIONAL_ATTRIBUTION_REMOVED"
            # Inline diff spans contain the old sentence and would otherwise
            # put the numeric speaker back on the official view.
            if isinstance(topic.get("_official_diffs"), dict):
                topic["_official_diffs"].pop("summary", None)
        if topic.get("summary_verification") == "PROVISIONAL_ATTRIBUTION_REMOVED":
            stats["neutralized_topic_summaries"] += 1
        official_points = []
        draft_only = []
        for point in topic.get("speaker_points") or []:
            source_ids = list(dict.fromkeys(
                str(value) for value in point.get("official_evidence_ids") or [] if value
            ))
            sources = [by_id[value] for value in source_ids if value in by_id]
            stats["missing_source_ids"] += len(source_ids) - len(sources)
            if not sources:
                draft_point = deepcopy(point)
                draft_point["summary_verification"] = "OFFICIAL_UNVERIFIED"
                draft_point["provisional_speaker_label"] = point.get("speaker_label")
                draft_point["speaker_label"] = "화자 미확인"
                draft_point["speaker_official"] = False
                draft_point.pop("official_evidence_ids", None)
                draft_only.append(draft_point)
                stats["draft_only_points"] += 1
                continue
            by_speaker: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for source in sources:
                by_speaker[str(source["speaker_label"]).strip()].append(source)
            if len(by_speaker) > 1:
                stats["split_speaker_points"] += 1
            for index, (speaker, rows) in enumerate(by_speaker.items(), start=1):
                presented = deepcopy(point)
                if len(by_speaker) > 1:
                    presented["id"] = f"{point.get('id')}:official:{index}"
                presented["provisional_summary"] = point.get("summary")
                presented["summary"] = "\n\n".join(str(row["text"]).strip() for row in rows)
                presented["summary_verification"] = "OFFICIAL_SOURCE_EXCERPT"
                presented["speaker_label"] = speaker
                presented["speaker_official"] = True
                presented["official_evidence_ids"] = [
                    str(row["utterance_id"]) for row in rows
                ]
                official_points.append(presented)
                stats["official_source_points"] += 1
        topic["speaker_points"] = official_points
        topic["draft_only_speaker_points"] = draft_only
    for session in result.get("meeting_sessions") or []:
        for topic in session.get("topics") or []:
            title = str(topic.get("title") or "")
            neutral_title = _neutralize_numeric_speakers(title)
            if neutral_title != title:
                topic["provisional_title"] = title
                topic["title"] = neutral_title
    for cluster in (result.get("live_topic_lineage") or {}).get("clusters") or []:
        title = str(cluster.get("title") or "")
        neutral_title = _neutralize_numeric_speakers(title)
        if neutral_title != title:
            cluster["provisional_title"] = title
            cluster["title"] = neutral_title
        aliases = cluster.get("aliases") or []
        neutral_aliases = [_neutralize_numeric_speakers(str(alias)) for alias in aliases]
        if neutral_aliases != aliases:
            cluster["provisional_aliases"] = aliases
            cluster["aliases"] = neutral_aliases
    return result, stats
