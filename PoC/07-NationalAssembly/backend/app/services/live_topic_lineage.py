from __future__ import annotations

import re
from collections.abc import Iterable
from copy import deepcopy
from difflib import SequenceMatcher
from typing import Any

LINEAGE_VERSION = "live-topic-lineage/1.0"
_TOKEN_PATTERN = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_STOP_WORDS = {
    "관련",
    "대한",
    "위한",
    "논의",
    "문제",
    "방안",
    "마련",
    "요구",
    "정책",
    "제도",
    "개선",
    "검토",
    "추진",
    "평가",
    "강화",
    "요청",
    "현황",
    "필요",
    "발언",
    "답변",
    "주장",
}
_SUFFIXES = (
    "으로부터",
    "에서는",
    "이라고",
    "이라는",
    "하도록",
    "에서도",
    "으로",
    "에서",
    "에게",
    "까지",
    "부터",
    "보다",
    "에는",
    "하고",
    "하며",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "의",
    "에",
    "와",
    "과",
    "도",
)


def _clean(value: object, limit: int = 300) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _tokens(*values: object) -> set[str]:
    result: set[str] = set()
    for value in values:
        for raw in _TOKEN_PATTERN.findall(str(value or "").casefold()):
            token = raw
            for suffix in _SUFFIXES:
                if len(token) >= len(suffix) + 2 and token.endswith(suffix):
                    token = token[: -len(suffix)]
                    break
            if len(token) >= 2 and token not in _STOP_WORDS:
                result.add(token)
    return result


def _owner_tokens(values: object) -> set[str]:
    source = values if isinstance(values, list) else [values]
    result: set[str] = set()
    for value in source:
        normalized = re.sub(r"[^0-9a-z가-힣]+", "", str(value or "").casefold())
        if not normalized:
            continue
        result.add(normalized)
        stem = re.sub(r"(위원회|위원장|본부|부처|실|청|처|부|원)$", "", normalized)
        if len(stem) >= 2:
            result.add(stem)
    return result


def _related(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 2 and shorter in longer


def _overlap(left: set[str], right: set[str]) -> int:
    return sum(
        1 for token in left if any(_related(token, candidate) for candidate in right)
    )


def _sets_overlap(left: set[str], right: set[str]) -> bool:
    return any(_related(a, b) for a in left for b in right)


def _normalized_key(value: object) -> str:
    return re.sub(r"[^0-9a-z가-힣]+", "-", str(value or "").casefold()).strip("-")


def build_live_topic_clusters(
    utterances: Iterable[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    groups: list[dict[str, Any]] = []
    by_key: dict[str, dict[str, Any]] = {}
    source_insight_count = 0
    source_titles: set[str] = set()

    for sequence, utterance in enumerate(utterances):
        insight = utterance.get("live_insight")
        if not isinstance(insight, dict):
            continue
        topic = _clean(insight.get("topic"), 180)
        topic_key = _clean(insight.get("topic_key"), 180)
        utterance_id = _clean(utterance.get("utterance_id"), 100)
        if not topic or not utterance_id:
            continue
        source_insight_count += 1
        source_titles.add(topic)
        key = _normalized_key(topic_key or topic)
        hint_tokens = _tokens(topic_key, topic)
        hint_owners = _owner_tokens(insight.get("owners") or [])
        group = by_key.get(key)

        if group is None and hint_tokens:
            best: dict[str, Any] | None = None
            best_rank = 0.0
            for candidate in groups:
                overlap = _overlap(hint_tokens, candidate["_tokens"])
                denominator = min(len(hint_tokens), len(candidate["_tokens"])) or 1
                coverage = overlap / denominator
                owner_match = _sets_overlap(hint_owners, candidate["_owners"])
                recent = sequence - int(candidate["_last_seen"]) <= 8
                qualifies = (overlap >= 2 and coverage >= 0.42) or (
                    owner_match and recent and overlap >= 2 and coverage >= 0.4
                )
                rank = (
                    coverage + (0.2 if owner_match else 0.0) + (0.05 if recent else 0.0)
                )
                if qualifies and rank > best_rank:
                    best = candidate
                    best_rank = rank
            group = best

        if group is None:
            group = {
                "id": "",
                "title": topic,
                "aliases": [],
                "topic_keys": [],
                "utterance_ids": [],
                "owners": [],
                "tasks": [],
                "first_sequence": sequence,
                "last_sequence": sequence,
                "_tokens": set(),
                "_owners": set(),
                "_last_seen": sequence,
            }
            groups.append(group)

        if key:
            by_key[key] = group
        if topic not in group["aliases"]:
            group["aliases"].append(topic)
        if topic_key and topic_key not in group["topic_keys"]:
            group["topic_keys"].append(topic_key)
        if utterance_id not in group["utterance_ids"]:
            group["utterance_ids"].append(utterance_id)
        for owner in insight.get("owners") or []:
            cleaned = _clean(owner, 80)
            if cleaned and cleaned not in group["owners"]:
                group["owners"].append(cleaned)
        task = _clean(insight.get("task"), 240)
        if task and task not in group["tasks"]:
            group["tasks"].append(task)
        group["_tokens"].update(hint_tokens)
        group["_owners"].update(hint_owners)
        group["_last_seen"] = sequence
        group["last_sequence"] = sequence

    for index, group in enumerate(groups, start=1):
        group["id"] = f"live-topic-{index}"
        group["utterance_count"] = len(group["utterance_ids"])
        group["aliases"] = group["aliases"][:12]
        group["topic_keys"] = group["topic_keys"][:12]
        group["owners"] = group["owners"][:12]
        group["tasks"] = group["tasks"][:12]
    return groups, source_insight_count, len(source_titles)


def _topic_evidence(topic: dict[str, Any], tasks: list[dict[str, Any]]) -> set[str]:
    evidence = {str(value) for value in topic.get("evidence_ids") or []}
    for point in topic.get("speaker_points") or []:
        evidence.update(str(value) for value in point.get("evidence_ids") or [])
    for task in tasks:
        if task.get("topic_id") == topic.get("id"):
            evidence.update(str(value) for value in task.get("evidence_ids") or [])
    return evidence


def _topic_corpus(
    topic: dict[str, Any], tasks: list[dict[str, Any]]
) -> tuple[set[str], str]:
    values: list[object] = [topic.get("title"), topic.get("summary")]
    values.extend(point.get("summary") for point in topic.get("speaker_points") or [])
    values.extend(
        task.get("title") for task in tasks if task.get("topic_id") == topic.get("id")
    )
    return _tokens(*values), _clean(topic.get("title"), 180).casefold()


def attach_live_topic_lineage(
    brief: dict[str, Any],
    utterances: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    result = deepcopy(brief)
    topics = [topic for topic in result.get("topics") or [] if isinstance(topic, dict)]
    tasks = [task for task in result.get("tasks") or [] if isinstance(task, dict)]
    clusters, source_count, source_title_count = build_live_topic_clusters(utterances)
    topic_data = {
        str(topic.get("id")): {
            "topic": topic,
            "evidence": _topic_evidence(topic, tasks),
            "corpus": _topic_corpus(topic, tasks),
        }
        for topic in topics
        if topic.get("id")
    }
    assignment = result.get("live_topic_assignment") or {}
    synthesis_ids: dict[str, list[str]] = {}
    if assignment:
        for topic in topics:
            for cluster_id in topic.get("live_topic_cluster_ids") or []:
                synthesis_ids.setdefault(str(cluster_id), []).append(
                    str(topic.get("id"))
                )
    fallback_ids = {
        str(value) for value in assignment.get("fallback_cluster_ids") or []
    }
    semantic_ids = {
        str(value)
        for value in assignment.get("semantic_assigned_cluster_ids") or []
    }
    session_by_utterance = {
        str(item.get("utterance_id")): str(item.get("meeting_session_id") or "")
        for item in utterances
        if item.get("utterance_id")
    }
    mapped = ambiguous = unmapped = 0

    for cluster in clusters:
        cluster_evidence = set(cluster["utterance_ids"])
        direct_ids = [
            topic_id
            for topic_id, data in topic_data.items()
            if cluster_evidence & data["evidence"]
        ]
        status = "UNMAPPED"
        final_topic_ids: list[str] = []
        score = 0.0

        assigned_ids = synthesis_ids.get(str(cluster.get("id") or ""), [])
        if assigned_ids:
            final_topic_ids = assigned_ids
            cluster_id = str(cluster.get("id") or "")
            if cluster_id in fallback_ids:
                status = "DETERMINISTIC_FALLBACK"
            elif cluster_id in semantic_ids:
                status = "SEMANTIC_ASSIGNED"
            else:
                status = "SYNTHESIS_ASSIGNED"
            score = 1.0
        elif len(direct_ids) == 1:
            status = "DIRECT_EVIDENCE"
            final_topic_ids = direct_ids
            score = 1.0
        elif len(direct_ids) > 1:
            status = "MULTIPLE_FINAL_TOPICS"
            final_topic_ids = []
            score = 1.0
        else:
            cluster_tokens = set(cluster["_tokens"])
            cluster_title = _clean(cluster.get("title"), 180).casefold()
            candidates: list[tuple[float, int, str]] = []
            for topic_id, data in topic_data.items():
                topic_tokens, topic_title = data["corpus"]
                overlap = _overlap(cluster_tokens, topic_tokens)
                denominator = min(len(cluster_tokens), len(topic_tokens)) or 1
                coverage = overlap / denominator
                title_ratio = SequenceMatcher(None, cluster_title, topic_title).ratio()
                candidate_score = coverage * 0.8 + title_ratio * 0.2
                candidates.append((candidate_score, overlap, topic_id))
            candidates.sort(reverse=True)
            if candidates:
                best_score, best_overlap, best_id = candidates[0]
                second_score = candidates[1][0] if len(candidates) > 1 else 0.0
                qualifies = (best_overlap >= 2 and best_score >= 0.48) or (
                    best_overlap >= 3 and best_score >= 0.4
                )
                if qualifies and best_score - second_score >= 0.08:
                    status = "LEXICAL_CANDIDATE"
                    final_topic_ids = []
                    score = best_score
                elif qualifies:
                    status = "AMBIGUOUS"
                    final_topic_ids = []
                    score = best_score

        cluster["session_ids"] = list(
            dict.fromkeys(
                session_by_utterance.get(str(value), "")
                for value in cluster["utterance_ids"]
                if session_by_utterance.get(str(value), "")
            )
        )
        if status in {
            "DIRECT_EVIDENCE",
            "SYNTHESIS_ASSIGNED",
            "DETERMINISTIC_FALLBACK",
            "SEMANTIC_ASSIGNED",
        }:
            mapped += 1
        elif status in {"AMBIGUOUS", "MULTIPLE_FINAL_TOPICS", "LEXICAL_CANDIDATE"}:
            ambiguous += 1
        else:
            unmapped += 1
        cluster["mapping_status"] = status
        cluster["final_topic_ids"] = final_topic_ids
        cluster["match_score"] = round(score, 4)
        cluster.pop("_tokens", None)
        cluster.pop("_owners", None)
        cluster.pop("_last_seen", None)

    for topic in topics:
        topic_id = str(topic.get("id") or "")
        topic["live_topic_cluster_ids"] = [
            cluster["id"]
            for cluster in clusters
            if topic_id in cluster["final_topic_ids"]
        ]

    result["live_topic_lineage"] = {
        "version": LINEAGE_VERSION,
        "method": "EVIDENCE_WITH_LEXICAL_CANDIDATES",
        "additional_llm_calls": int(assignment.get("additional_llm_calls") or 0),
        "source_insight_count": source_count,
        "source_topic_title_count": source_title_count,
        "cluster_count": len(clusters),
        "mapped_cluster_count": mapped,
        "ambiguous_cluster_count": ambiguous,
        "unmapped_cluster_count": unmapped,
        "coverage_status": "COMPLETE"
        if unmapped == 0 and ambiguous == 0
        else "PARTIAL",
        "clusters": clusters,
    }
    return result
