from __future__ import annotations

from datetime import date, datetime
from typing import Any

from .official_transcript_insights import classify_official_utterance


MATCH_METHOD = "EXACT_SHARED_TOPIC_AND_KEYWORD_V3"
STRONG_EVIDENCE: dict[str, set[str]] = {
    "법무·사법": {"법무", "법원", "검찰", "수사", "사법", "특별검사"},
    "재난·안전": {"재난", "호우", "복구", "안전", "소방"},
}
WEAK_SHARED_ONLY: dict[str, set[str]] = {
    "지방·행정": {"지방", "행정", "공무원"},
    "법무·사법": {"법률", "법무", "사법"},
    "재난·안전": {"안전"},
}


def _topic_keywords(links: Any, topic: str) -> set[str]:
    if not isinstance(links, list):
        return set()
    for link in links:
        if isinstance(link, dict) and link.get("label") == topic:
            return {str(keyword) for keyword in link.get("keywords", []) if keyword}
    return set()


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    normalized = str(value).strip().rstrip(".").replace(".", "-")
    try:
        return date.fromisoformat(normalized)
    except ValueError:
        return None


def _temporal_relation(executive_date: Any, legislative_date: Any) -> tuple[str, str]:
    executive = _as_date(executive_date)
    legislative = _as_date(legislative_date)
    if not executive or not legislative:
        return "UNKNOWN", "날짜 순서 확인 필요"
    if executive < legislative:
        return "EXECUTIVE_BEFORE_LEGISLATURE", "국무회의 후 국회 논의"
    if executive > legislative:
        return "LEGISLATURE_BEFORE_EXECUTIVE", "국회 논의 후 국무회의"
    return "SAME_DATE", "같은 날 논의"


def build_cross_institution_flow(
    executive_items: list[dict[str, Any]],
    legislative_flow: dict[str, Any],
) -> dict[str, Any]:
    legislative_by_topic = {
        item["topic"]: item for item in legislative_flow.get("items", [])
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for meeting in executive_items:
        for agenda in meeting.get("agendas", []):
            insight = classify_official_utterance(
                f"{agenda.get('topic', '')} {agenda.get('summary', '')}"
            )
            if insight["utterance_kind"] != "POLICY":
                continue
            for topic in insight["topics"]:
                if topic not in legislative_by_topic:
                    continue
                keywords = _topic_keywords(insight["topic_links"], topic)
                required = STRONG_EVIDENCE.get(topic)
                if required and not required.intersection(keywords):
                    continue
                legislative = legislative_by_topic[topic]
                legislative_keywords = set(legislative.get("evidence_keywords", []))
                shared_keywords = sorted(keywords.intersection(legislative_keywords))
                if not shared_keywords:
                    continue
                weak_only = WEAK_SHARED_ONLY.get(topic)
                if weak_only and set(shared_keywords).issubset(weak_only):
                    continue
                grouped.setdefault(topic, []).append({
                    "meeting_number": meeting.get("meeting_number"),
                    "meeting_title": meeting.get("title"),
                    "published_date": meeting.get("published_date"),
                    "agenda_topic": agenda.get("topic"),
                    "summary": agenda.get("summary"),
                    "ministries": agenda.get("ministries", []),
                    "source_span_id": agenda.get("source_span_id"),
                    "source_url": meeting.get("source_url"),
                    "source_content_hash": meeting.get("content_hash"),
                    "source_parser_version": meeting.get("parser_version"),
                    "evidence_keywords": sorted(keywords),
                    "shared_evidence_keywords": shared_keywords,
                })
    items = []
    for topic, executive_evidence in grouped.items():
        legislative = legislative_by_topic[topic]
        temporal_relation, temporal_label = _temporal_relation(
            executive_evidence[0].get("published_date"),
            (legislative.get("evidence") or {}).get("conference_date"),
        )
        items.append({
            "topic": topic,
            "executive_agenda_count": len(executive_evidence),
            "legislative_statement_count": legislative["statement_count"],
            "executive_evidence": executive_evidence[0],
            "legislative_evidence": legislative.get("evidence"),
            "committees": legislative.get("committees", []),
            "ministries": legislative.get("ministries", []),
            "bills": legislative.get("bills", []),
            "shared_evidence_keywords": executive_evidence[0]["shared_evidence_keywords"],
            "temporal_relation": temporal_relation,
            "temporal_label": temporal_label,
            "link_scope": "COMMON_TOPIC_SIGNAL_ONLY",
            "match_method": MATCH_METHOD,
            "review_status": "DRAFT",
            "authority_status": "PROVISIONAL",
        })
    items.sort(
        key=lambda item: (
            item["executive_agenda_count"] + item["legislative_statement_count"],
            item["topic"],
        ),
        reverse=True,
    )
    return {
        "items": items,
        "count": len(items),
        "match_method": MATCH_METHOD,
        "review_status": "DRAFT",
        "authority_status": "PROVISIONAL",
    }
