from __future__ import annotations

from collections import Counter
import re
from typing import Any, Iterable


INTEGRATION_VERSION = "official-live-integration/1.0"
MATCH_METHOD = "DETERMINISTIC_TERM_MINISTRY_OVERLAP"

_TOKEN_PATTERN = re.compile(r"[가-힣a-zA-Z0-9]{2,}")
_STOP_WORDS = {
    "관련", "대한", "위한", "통한", "등의", "문제", "논의", "필요", "필요성",
    "검토", "추진", "요청", "방안", "개선", "마련", "진행", "현안", "내용",
    "위원회", "회의", "국회", "국민", "정부", "업무", "보고", "결과", "계획",
    "지적", "강조", "질의", "답변", "발언", "기관", "제도", "정책",
}
_SUFFIXES = (
    "에서는", "으로부터", "이라고", "이라는", "하도록", "하기로", "에서도",
    "으로", "에서", "에게", "까지", "부터", "보다", "처럼", "관련", "대한",
    "에는", "으로", "하고", "하며", "되고", "하는", "하기", "위해",
    "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도",
)


def _token(value: str) -> str:
    token = value.casefold()
    for suffix in _SUFFIXES:
        if len(token) >= len(suffix) + 2 and token.endswith(suffix):
            token = token[:-len(suffix)]
            break
    return token


def semantic_tokens(*values: object) -> set[str]:
    result: set[str] = set()
    for value in values:
        for raw in _TOKEN_PATTERN.findall(str(value or "")):
            token = _token(raw)
            if len(token) >= 2 and token not in _STOP_WORDS:
                result.add(token)
    return result


def _best_excerpt(text: str, query_tokens: set[str], limit: int = 300) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。])\s+|(?<=다\.)\s*", normalized)
        if sentence.strip()
    ]
    if not sentences:
        return normalized[:limit].rstrip() + "…"
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            len(semantic_tokens(item[1]) & query_tokens),
            min(len(item[1]), limit),
            -item[0],
        ),
        reverse=True,
    )
    excerpt = ranked[0][1]
    if len(excerpt) > limit:
        excerpt = excerpt[:limit].rstrip() + "…"
    return excerpt


def _prepare_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        topics = [str(value) for value in row.get("topics") or []]
        ministries = [str(value) for value in row.get("ministries") or []]
        row["topics"] = topics
        row["ministries"] = ministries
        row["agenda_titles"] = [
            str(value) for value in row.get("agenda_titles") or [] if value
        ]
        row["_tokens"] = semantic_tokens(
            row.get("text"), *topics, *ministries, *row["agenda_titles"],
        )
        prepared.append(row)
    return prepared


def _row_score(
    query_tokens: set[str],
    query_ministries: set[str],
    row: dict[str, Any],
) -> tuple[float, set[str]]:
    shared = query_tokens & row["_tokens"]
    ministry_tokens = semantic_tokens(*query_ministries)
    content_shared = shared - ministry_tokens
    ministry_overlap = query_ministries & set(row["ministries"])
    if len(shared) < 2 or not content_shared:
        return 0.0, shared
    if len(content_shared) < 2 and not (
        ministry_overlap and any(len(token) >= 5 for token in content_shared)
    ):
        return 0.0, shared
    coverage = len(shared) / max(2, min(len(query_tokens), 10))
    ministry_bonus = min(0.2, len(ministry_overlap) * 0.1)
    long_token_bonus = 0.08 if any(len(token) >= 5 for token in shared) else 0.0
    return min(1.0, coverage + ministry_bonus + long_token_bonus), shared


def _match_entity(
    entity: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    ministries: Iterable[str] = (),
    minimum_score: float,
    limit: int,
) -> list[dict[str, Any]]:
    query_ministries = {str(value) for value in ministries if value}
    query_tokens = semantic_tokens(
        entity.get("title"), entity.get("summary"), *query_ministries,
    )
    if len(query_tokens) < 2:
        return []
    candidates: list[tuple[float, int, dict[str, Any], set[str]]] = []
    for row in rows:
        if row.get("utterance_kind") not in {None, "POLICY"}:
            continue
        score, shared = _row_score(query_tokens, query_ministries, row)
        if score < minimum_score:
            continue
        candidates.append((
            score,
            -int(row.get("sequence_number") or 0),
            row,
            shared,
        ))
    candidates.sort(key=lambda value: (value[0], value[1]), reverse=True)
    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, _, row, shared in candidates:
        utterance_id = str(row.get("utterance_id") or "")
        if not utterance_id or utterance_id in seen:
            continue
        seen.add(utterance_id)
        evidence.append({
            "utterance_id": utterance_id,
            "sequence_number": int(row.get("sequence_number") or 0),
            "speaker_name": row.get("speaker_name") or "공식 발언자",
            "speaker_role": row.get("speaker_role"),
            "excerpt": _best_excerpt(str(row.get("text") or ""), query_tokens),
            "topics": row["topics"],
            "ministries": row["ministries"],
            "agenda_titles": row["agenda_titles"],
            "shared_terms": sorted(shared, key=lambda value: (-len(value), value))[:8],
            "score": round(score, 3),
            "match_method": MATCH_METHOD,
            "source_locator": row.get("source_locator"),
        })
        if len(evidence) >= limit:
            break
    return evidence


def _official_categories(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    topic_counts: Counter[str] = Counter()
    ministry_counts: dict[str, Counter[str]] = {}
    for row in rows:
        if row.get("utterance_kind") != "POLICY":
            continue
        for topic in row["topics"]:
            if topic in {"기타 발언", "절차·의결"}:
                continue
            topic_counts[topic] += 1
            ministry_counts.setdefault(topic, Counter()).update(row["ministries"])
    return [
        {
            "title": topic,
            "official_utterance_count": count,
            "ministries": [
                ministry for ministry, _ in ministry_counts.get(topic, Counter()).most_common(4)
            ],
        }
        for topic, count in topic_counts.most_common()
    ]


def build_official_brief_integration(
    live_brief: dict[str, Any] | None,
    official_rows: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    payload = (live_brief or {}).get("brief") or live_brief or {}
    rows = _prepare_rows(official_rows)
    live_topics = list(payload.get("topics") or [])
    live_tasks = list(payload.get("tasks") or [])
    topic_ministries: dict[str, set[str]] = {}
    for task in live_tasks:
        topic_ministries.setdefault(str(task.get("topic_title") or ""), set()).update(
            str(value) for value in task.get("ministries") or [] if value
        )

    topics: list[dict[str, Any]] = []
    for topic in live_topics:
        evidence = _match_entity(
            topic,
            rows,
            ministries=topic_ministries.get(str(topic.get("title") or ""), set()),
            minimum_score=0.28,
            limit=3,
        )
        topics.append({
            "id": topic.get("id"),
            "title": topic.get("title"),
            "status": "OFFICIAL_RELATED" if evidence else "NOT_LINKED",
            "official_evidence": evidence,
        })

    tasks: list[dict[str, Any]] = []
    for task in live_tasks:
        evidence = _match_entity(
            task,
            rows,
            ministries=task.get("ministries") or [],
            minimum_score=0.34,
            limit=2,
        )
        tasks.append({
            "id": task.get("id"),
            "title": task.get("title"),
            "topic_title": task.get("topic_title"),
            "ministries": list(task.get("ministries") or []),
            "status": "OFFICIAL_RELATED" if evidence else "NOT_LINKED",
            "official_evidence": evidence,
        })

    related_topics = sum(item["status"] == "OFFICIAL_RELATED" for item in topics)
    related_tasks = sum(item["status"] == "OFFICIAL_RELATED" for item in tasks)
    return {
        "integration_version": INTEGRATION_VERSION,
        "match_method": MATCH_METHOD,
        "interpretation": (
            "관련 공식 발언은 LIVE 분석의 확정·승인을 뜻하지 않으며, "
            "공식 회의록에서 같은 핵심어와 소관 부처가 확인된 근거입니다."
        ),
        "summary": {
            "official_policy_utterances": sum(
                row.get("utterance_kind") == "POLICY" for row in rows
            ),
            "live_topic_count": len(topics),
            "related_topic_count": related_topics,
            "live_task_count": len(tasks),
            "related_task_count": related_tasks,
        },
        "official_categories": _official_categories(rows),
        "topics": topics,
        "tasks": tasks,
    }
