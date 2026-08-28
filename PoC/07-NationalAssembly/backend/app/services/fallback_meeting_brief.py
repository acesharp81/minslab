from __future__ import annotations

from typing import Any

from .transcript_presentation import summarize_utterance


PROVIDER = "deterministic"
MODEL = "broadcast-review-v1"
PROMPT_VERSION = "fallback-result-v2"


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_fallback_meeting_brief(
    meeting: dict[str, Any],
    utterances: list[dict[str, Any]],
    review_topics: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build an evidence-only result view while abstractive AI is unavailable."""
    utterance_by_id = {
        str(item["utterance_id"]): item for item in utterances
        if item.get("utterance_id") is not None
    }
    revision_to_utterance: dict[str, str] = {}
    for item in utterances:
        utterance_id = str(item.get("utterance_id") or "")
        for revision_id in item.get("revision_ids", []):
            revision_to_utterance[str(revision_id)] = utterance_id

    topics: list[dict[str, Any]] = []
    for index, source in enumerate(review_topics[:8], start=1):
        revision_ids = [
            source.get("representative_revision_id"),
            *source.get("evidence_revision_ids", []),
        ]
        evidence_ids = _unique([
            revision_to_utterance.get(str(revision_id), "")
            for revision_id in revision_ids if revision_id is not None
        ])[:3]
        if not evidence_ids:
            continue
        evidence = utterance_by_id[evidence_ids[0]]
        summary = summarize_utterance(
            str(source.get("major_quote") or evidence.get("text") or "")
        )
        topics.append({
            "id": f"fallback-topic-{index}",
            "title": str(source.get("topic") or "주요 논의"),
            "summary": summary,
            "speaker_points": [{
                "id": f"fallback-speaker-{index}-1",
                "speaker_label": evidence.get("speaker_label") or "화자 미확인",
                "summary": summary,
                "evidence_ids": evidence_ids,
            }],
            "evidence_ids": evidence_ids,
        })

    topic_titles = {item["title"] for item in topics}
    default_topic = topics[0]["title"] if topics else "주요 논의"
    tasks: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()
    for utterance in utterances:
        for hint in utterance.get("insight_hints", []):
            if not isinstance(hint, dict):
                continue
            task_text = str(hint.get("task") or "").strip()
            if (
                not task_text
                or hint.get("task_status") != "OPEN"
                or hint.get("resolution") is True
            ):
                continue
            title = summarize_utterance(task_text, max_chars=120)
            if title in seen_tasks:
                continue
            seen_tasks.add(title)
            hinted_topic = str(hint.get("topic") or "")
            topic_title = hinted_topic if hinted_topic in topic_titles else default_topic
            ministries = [
                str(value) for value in hint.get("ministries", [])
                if str(value).strip()
            ]
            tasks.append({
                "id": f"fallback-task-{len(tasks) + 1}",
                "title": title,
                "topic_title": topic_title,
                "status": "OPEN",
                "ministries": ministries,
                "owner_basis": "EXPLICIT" if ministries else "UNASSIGNED",
                "evidence_ids": [str(utterance["utterance_id"])],
            })
            if len(tasks) >= 12:
                break
        if len(tasks) >= 12:
            break

    title = str(meeting.get("title") or meeting.get("committee_name") or "종료 회의")
    committee = str(meeting.get("committee_name") or "위원회")
    return {
        "headline": f"{title} 주요 논의 결과",
        "summary": (
            f"{committee} LIVE 저장본에서 확인된 주요 논의를 근거 발언별로 정리했습니다. "
            "AI 통합 요약은 생성 대기 중이며 저장된 발언 원문은 바로 확인할 수 있습니다."
        ),
        "topics": topics,
        "tasks": tasks,
        "utterance_count": len(utterances),
        "result_kind": "DETERMINISTIC_FALLBACK",
    }
