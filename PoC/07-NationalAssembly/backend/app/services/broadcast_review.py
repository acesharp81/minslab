from __future__ import annotations

from typing import Any


GENERATOR_VERSION = "keyword-review/1.0"
CLASSIFICATION_METHOD = "DETERMINISTIC_KEYWORD_RULE"
TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("재난 대응", ("재난", "호우", "복구", "피해", "안전")),
    ("재정·예산", ("예산", "재정", "재원", "결산")),
    ("법무·사법", ("법률", "법무", "법원", "검찰", "권리", "사법")),
    ("행정·지방", ("행정", "지방", "자치", "공무원", "선거")),
)
MINISTRY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("행정안전부", ("재난", "호우", "복구", "행정", "지방", "자치", "선거")),
    ("기획재정부", ("예산", "재정", "재원", "결산")),
    ("법무부", ("법률", "법무", "검찰", "권리", "사법")),
)
COMMITTEE_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("행정안전위원회", ("재난", "호우", "행정", "지방", "자치", "선거")),
    ("예산결산특별위원회", ("예산", "재정", "재원", "결산")),
    ("법제사법위원회", ("법률", "법무", "법원", "검찰", "권리", "사법")),
)


def match_labels(
    text: str, rules: tuple[tuple[str, tuple[str, ...]], ...]
) -> list[str]:
    return [name for name, keywords in rules if any(keyword in text for keyword in keywords)]


def build_broadcast_review(
    broadcast: dict[str, Any], final_segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Group final captions without inventing an abstractive summary."""
    grouped: dict[str, dict[str, Any]] = {}
    source_committee = broadcast.get("committee_name")
    for segment in final_segments:
        text = str(segment["text"]).strip()
        if not text:
            continue
        topics = match_labels(text, TOPIC_RULES) or ["기타 정책"]
        ministries = match_labels(text, MINISTRY_RULES)
        committees = match_labels(text, COMMITTEE_RULES)
        if source_committee and source_committee not in committees:
            committees.append(source_committee)
        for topic in topics:
            group = grouped.setdefault(topic, {
                "topic": topic,
                "ministries": set(),
                "committees": set(),
                "segments": [],
            })
            group["ministries"].update(ministries)
            group["committees"].update(committees)
            group["segments"].append(segment)

    result: list[dict[str, Any]] = []
    ordered = sorted(
        grouped.values(),
        key=lambda group: min(int(item["cursor"]) for item in group["segments"]),
    )
    for sort_order, group in enumerate(ordered):
        segments = sorted(group["segments"], key=lambda item: int(item["cursor"]))
        representative = max(
            segments,
            key=lambda item: (len(str(item["text"])), -int(item["cursor"])),
        )
        result.append({
            "topic": group["topic"],
            "major_quote": representative["text"],
            "speaker_label": representative.get("speaker_label"),
            "ministries": sorted(group["ministries"]),
            "committees": sorted(group["committees"]),
            "segment_count": len(segments),
            "representative_revision_id": representative["revision_id"],
            "evidence_revision_ids": [item["revision_id"] for item in segments],
            "sort_order": sort_order,
        })
    return result
