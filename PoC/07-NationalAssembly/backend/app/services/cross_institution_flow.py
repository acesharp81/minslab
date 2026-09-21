from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Any

from .official_brief_integration import semantic_tokens
from .official_transcript_insights import classify_official_utterance


MATCH_METHOD = "EXACT_SHARED_TOPIC_AND_KEYWORD_V3"
SPECIFIC_MATCH_METHOD = "SPECIFIC_REPORT_TOPIC_TOKEN_V1"
_GENERIC_CROSS_WORDS = {
    "관련", "정책", "문제", "문제점", "요구", "개선", "지원", "추진",
    "방안", "논의", "제도", "운영", "계획", "보고", "검토", "정부",
    "국회", "기관", "사업", "강화", "마련", "법률", "법안", "개정안",
    "시행령", "수사", "예산", "예산안", "재정", "관한", "위한",
    "기본법", "특별법", "보호", "대책", "관리", "규정", "법적",
    "대통령", "추가", "과정", "설정", "개정", "시행", "필요한",
    "또한", "통해", "위해", "있도록", "이에", "일부",
}
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


def _normalized_ministries(values: Any) -> set[str]:
    if not isinstance(values, list):
        return set()
    return {
        "".join(str(value).split()).replace("소관", "")
        for value in values if value
    }


@lru_cache(maxsize=16384)
def _cached_semantic_tokens(title: str, summary: str = "") -> frozenset[str]:
    return frozenset(semantic_tokens(title, summary))


def _specific_match(
    agenda: dict[str, Any], issue: dict[str, Any],
) -> tuple[float, list[str], list[str]] | None:
    agenda_topic = str(agenda.get("topic") or "")
    agenda_summary = str(agenda.get("summary") or "")
    issue_topic = str(issue.get("topic") or "")
    issue_summary = str(issue.get("summary") or "")
    agenda_title = _cached_semantic_tokens(agenda_topic)
    agenda_all = _cached_semantic_tokens(agenda_topic, agenda_summary)
    issue_title = _cached_semantic_tokens(issue_topic)
    issue_all = _cached_semantic_tokens(issue_topic, issue_summary)
    title_shared = agenda_title & issue_title
    all_shared = agenda_all & issue_all
    specific_shared = all_shared - _GENERIC_CROSS_WORDS
    title_specific = title_shared - _GENERIC_CROSS_WORDS
    ministry_shared = (
        _normalized_ministries(agenda.get("ministries"))
        & _normalized_ministries(issue.get("ministries"))
    )
    has_distinctive_title = any(
        len(token) >= 5
        and not token.isdigit()
        and not (
            len(token) in {5, 6}
            and token[:4].isdigit()
            and token[4:] in {"년", "년도"}
        )
        for token in title_specific
    )
    has_multi_specific_title = (
        len(title_specific) >= 2
        and any(len(token) >= 4 for token in title_specific)
    )
    if not (has_distinctive_title or has_multi_specific_title):
        return None
    score = (
        len(title_specific) * 5
        + len(specific_shared) * 2
        + len(ministry_shared) * 2
        + (4 if has_distinctive_title else 0)
    )
    return float(score), sorted(specific_shared), sorted(ministry_shared)


def build_specific_cross_institution_flow(
    executive_items: list[dict[str, Any]],
    specific_issues: dict[str, Any],
) -> dict[str, Any]:
    """Link official executive agendas only to matching concrete Assembly topics."""
    matches: dict[str, dict[str, Any]] = {}
    issues = [
        issue for issue in specific_issues.get("items", [])
        if issue.get("latest_legislative_meeting")
    ]
    for meeting in executive_items:
        for agenda in meeting.get("agendas", []):
            candidates = []
            for issue in issues:
                match = _specific_match(agenda, issue)
                if match:
                    candidates.append((match[0], issue, match[1], match[2]))
            if not candidates:
                continue
            candidates.sort(key=lambda candidate: candidate[0], reverse=True)
            score, issue, shared_words, shared_ministries = candidates[0]
            if len(candidates) > 1 and score - candidates[1][0] < 4:
                continue
            evidence = {
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
                "shared_evidence_keywords": shared_words,
                "shared_ministries": shared_ministries,
                "match_score": score,
            }
            key = str(issue.get("id") or issue.get("topic"))
            current = matches.get(key)
            if current is None:
                matches[key] = {
                    "issue": issue,
                    "executive_evidence": [evidence],
                    "best_score": score,
                }
            else:
                current["executive_evidence"].append(evidence)
                current["best_score"] = max(current["best_score"], score)
    items = []
    for match in matches.values():
        issue = match["issue"]
        executive_evidence = max(
            match["executive_evidence"],
            key=lambda evidence: evidence["match_score"],
        )
        legislative = issue["latest_legislative_meeting"]
        temporal_relation, temporal_label = _temporal_relation(
            executive_evidence.get("published_date"), legislative.get("date")
        )
        items.append({
            "topic": issue.get("topic"),
            "executive_agenda_count": len(match["executive_evidence"]),
            "legislative_statement_count": issue.get("mention_count", 0),
            "executive_evidence": executive_evidence,
            "legislative_evidence": {
                "broadcast_id": legislative.get("broadcast_id"),
                "committee_name": legislative.get("committee_name"),
                "conference_date": legislative.get("date"),
                "text": legislative.get("summary") or issue.get("summary"),
                "authority_status": legislative.get("authority_status"),
                "topic_evidence_keywords": executive_evidence[
                    "shared_evidence_keywords"
                ],
            },
            "committees": [{
                "label": legislative.get("committee_name"),
                "count": issue.get("meeting_count", 0),
            }],
            "ministries": [
                {"label": ministry, "relation": "REPORT_TOPIC"}
                for ministry in issue.get("ministries", [])
            ],
            "bills": issue.get("bills", []),
            "shared_evidence_keywords": executive_evidence[
                "shared_evidence_keywords"
            ],
            "shared_ministries": executive_evidence["shared_ministries"],
            "temporal_relation": temporal_relation,
            "temporal_label": temporal_label,
            "link_scope": "SPECIFIC_TOPIC_SIGNAL_ONLY",
            "match_method": SPECIFIC_MATCH_METHOD,
            "match_score": match["best_score"],
            "review_status": "DRAFT",
            "authority_status": "PROVISIONAL",
        })
    items.sort(
        key=lambda item: (item["match_score"], item["topic"]), reverse=True
    )
    return {
        "items": items,
        "count": len(items),
        "match_method": SPECIFIC_MATCH_METHOD,
        "review_status": "DRAFT",
        "authority_status": "PROVISIONAL",
        "additional_llm_calls": 0,
    }
