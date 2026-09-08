from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import re
from typing import Any

from .official_brief_integration import semantic_tokens


GENERATOR_VERSION = "specific-policy-issues/1.1"
_PROCEDURAL_TITLE = re.compile(
    r"간사\s*선임|소위원장\s*선출|일괄\s*상정|개의|산회|회의\s*진행|보고\s*순서"
    r"|신임\s*위원장\s*인사|위원장\s*인사"
)
_GENERIC_AGENDA_TITLE = re.compile(
    r"^\d{4}회계연도.+(?:결산|예비비).+(?:보고|심사|승인\s*건?)$"
    r"|등\s*\d+건(?:의)?\s*법률안"
)
_NON_PRODUCTION_MEETING = re.compile(r"^\s*\[(?:테스트|test|demo)\]", re.IGNORECASE)
_DECISION_WORDS = re.compile(
    r"가결(?:되|됐|했|함|$)|의결(?:되|됐|했|함|$)|통과(?:되|됐|했|함|$)"
    r"|시행(?:$|되|됐|한|했|중|예정|개시)"
)
_FORMALIZATION_WORDS = re.compile(
    r"개정안|제정안|개편안|법률안|법안|시행령|시행세칙"
)
_GENERIC_TOPIC_WORDS = {
    "관련", "정책", "문제", "문제점", "요구", "개선", "지원", "추진",
    "방안", "논의", "제도", "운영", "예산", "강화", "검토",
}


def _as_iso_date(value: object) -> str | None:
    parsed = _as_date(value)
    return parsed.isoformat() if parsed else None


def _bill_matches_occurrences(
    bill: dict[str, Any], occurrences: list[dict[str, Any]],
) -> bool:
    """Reject agenda links that are structurally exact but topically unrelated.

    Assembly minutes occasionally retain a stale ``itemN`` CSS class while a
    speaker explicitly moves to another agenda item.  A direct bill claim is
    therefore exposed only when a distinctive term (4+ characters) from the
    stored report topic is also present in the official agenda/bill title.
    """
    bill_tokens = semantic_tokens(bill.get("bill_name"), bill.get("agenda_name"))
    if not bill_tokens:
        return False
    for occurrence in occurrences:
        topic_tokens = semantic_tokens(occurrence.get("title"), occurrence.get("summary"))
        for topic_token in topic_tokens:
            if len(topic_token) < 4:
                continue
            if any(
                topic_token == bill_token
                or topic_token in bill_token
                or bill_token in topic_token
                for bill_token in bill_tokens if len(bill_token) >= 4
            ):
                return True
    return False


def _bill_process(bill: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    steps: list[dict[str, Any]] = []
    proposal_date = _as_iso_date(bill.get("proposal_date"))
    committee_date = _as_iso_date(bill.get("committee_process_date"))
    plenary_date = _as_iso_date(bill.get("plenary_resolution_date"))
    proposal_step = ({
            "key": "PROPOSED", "label": "의안 발의", "date": proposal_date,
            "detail": str(bill.get("proposer_name") or bill.get("proposer_kind") or "발의자 확인"),
            "status": "DONE",
        } if proposal_date else None)
    committee_result = str(bill.get("committee_result") or "").strip()
    committee_step = ({
            "key": "COMMITTEE", "label": "소관위원회 심사", "date": committee_date,
            "detail": " · ".join(value for value in (
                str(bill.get("committee_name") or "").strip(), committee_result,
            ) if value),
            "status": "DONE" if committee_result else "CURRENT",
        } if committee_date or committee_result else None)
    committee_alternative = (
        proposal_step is not None and committee_step is not None
        and committee_date is not None and proposal_date is not None
        and committee_date < proposal_date
        and "위원장" in str(bill.get("proposer_kind") or bill.get("proposer_name") or "")
    )
    if committee_alternative:
        committee_step["label"] = "소관위원회 대안 의결"
        proposal_step["label"] = "위원장 대안 제출"
        steps.extend((committee_step, proposal_step))
    else:
        if proposal_step:
            steps.append(proposal_step)
        if committee_step:
            steps.append(committee_step)
    plenary_result = str(bill.get("plenary_result") or "").strip()
    if plenary_date or plenary_result:
        steps.append({
            "key": "PLENARY", "label": "본회의", "date": plenary_date,
            "detail": plenary_result or "처리 결과 확인 중",
            "status": "DONE" if plenary_result else "CURRENT",
        })
    current_status = (
        str(bill.get("pass_classification") or "").strip()
        or plenary_result
        or committee_result
        or str(bill.get("process_stage_code") or "").strip()
        or "의안 정보 확인 · 처리 단계 수집 중"
    )
    if not steps:
        steps.append({
            "key": "LINKED", "label": "상정 의안 확인", "date": None,
            "detail": current_status, "status": "CURRENT",
        })
    elif not any(step["status"] == "CURRENT" for step in steps):
        steps[-1]["status"] = "CURRENT"
    return steps, current_status


def _as_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _topic_key(value: object) -> str:
    return re.sub(r"[^0-9a-zA-Z가-힣]+", "", str(value or "").casefold())


def _similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    if left["key"] == right["key"]:
        return 1.0
    shared = left["title_tokens"] & right["title_tokens"]
    if len(shared) < 2:
        return 0.0
    title_score = len(shared) / max(1, min(
        len(left["title_tokens"]), len(right["title_tokens"]),
    ))
    context_shared = left["tokens"] & right["tokens"]
    context_score = len(context_shared) / max(1, min(
        len(left["tokens"]), len(right["tokens"]), 12,
    ))
    score = title_score * 0.75 + context_score * 0.25
    specific_shared = shared - _GENERIC_TOPIC_WORDS
    if title_score >= 0.6 and specific_shared:
        score = max(score, 0.62)
    return score


def _occurrences(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    occurrences: list[dict[str, Any]] = []
    for record in records:
        if _NON_PRODUCTION_MEETING.search(str(record.get("meeting_title") or "")):
            continue
        brief = record.get("brief") or {}
        tasks = [task for task in brief.get("tasks") or [] if isinstance(task, dict)]
        for topic in brief.get("topics") or []:
            if not isinstance(topic, dict):
                continue
            title = " ".join(str(topic.get("title") or "").split())
            summary = " ".join(str(topic.get("summary") or "").split())
            if (
                len(title) < 8
                or _PROCEDURAL_TITLE.search(title)
                or _GENERIC_AGENDA_TITLE.search(title)
            ):
                continue
            topic_id = str(topic.get("id") or "")
            linked_tasks = [
                task for task in tasks
                if str(task.get("topic_id") or "") == topic_id
                or (not task.get("topic_id") and task.get("topic_title") == title)
            ]
            ministries = sorted({
                str(ministry) for task in linked_tasks
                for ministry in task.get("ministries") or [] if ministry
            })
            evidence_ids = {
                str(value) for value in (
                    list(topic.get("evidence_ids") or [])
                    + list(topic.get("official_evidence_ids") or [])
                ) if value
            }
            for point in topic.get("speaker_points") or []:
                evidence_ids.update(str(value) for value in point.get("evidence_ids") or [] if value)
                evidence_ids.update(str(value) for value in point.get("official_evidence_ids") or [] if value)
            occurrence = {
                "broadcast_id": str(record.get("broadcast_id") or ""),
                "meeting_title": str(record.get("meeting_title") or ""),
                "meeting_date": _as_date(record.get("meeting_date")),
                "committee_name": str(record.get("committee_name") or ""),
                "institution": str(record.get("institution") or ""),
                "authority_status": str(record.get("authority_status") or "PROVISIONAL"),
                "topic_id": topic_id,
                "title": title,
                "summary": summary,
                "key": _topic_key(title),
                "title_tokens": semantic_tokens(title),
                "tokens": semantic_tokens(title, summary),
                "ministries": ministries,
                "tasks": [str(task.get("title") or "") for task in linked_tasks if task.get("title")],
                "evidence_ids": evidence_ids,
                "official_evidence_ids": {
                    str(value) for value in topic.get("official_evidence_ids") or [] if value
                },
            }
            occurrences.append(occurrence)
    return occurrences


def build_specific_policy_issues(
    records: list[dict[str, Any]], bill_links: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    for occurrence in sorted(
        _occurrences(records), key=lambda item: item["meeting_date"] or date.min,
    ):
        candidates = [
            (_similarity(occurrence, group["representative"]), group)
            for group in groups
        ]
        score, group = max(candidates, default=(0.0, None), key=lambda item: item[0])
        if group is None or score < 0.58:
            group = {"representative": occurrence, "occurrences": []}
            groups.append(group)
        group["occurrences"].append(occurrence)
        if (occurrence["meeting_date"] or date.min) >= (
            group["representative"]["meeting_date"] or date.min
        ):
            group["representative"] = occurrence

    latest_date = max(
        (item["meeting_date"] for group in groups for item in group["occurrences"] if item["meeting_date"]),
        default=date.today(),
    )
    current_start = latest_date - timedelta(days=13)
    previous_start = current_start - timedelta(days=14)
    previous_end = current_start - timedelta(days=1)
    items: list[dict[str, Any]] = []
    for group in groups:
        occurrences = group["occurrences"]
        representative = group["representative"]
        meetings = {item["broadcast_id"] for item in occurrences}
        evidence_ids = set().union(*(item["evidence_ids"] for item in occurrences))
        official_evidence_ids = set().union(*(
            item["official_evidence_ids"] for item in occurrences
        ))
        candidate_bills: dict[str, dict[str, Any]] = {}
        for evidence_id in official_evidence_ids:
            for bill in bill_links.get(evidence_id, []):
                candidate_bills[str(bill.get("bill_id") or bill.get("bill_number"))] = bill
        bills: dict[str, dict[str, Any]] = {}
        for key, candidate in candidate_bills.items():
            if not _bill_matches_occurrences(candidate, occurrences):
                continue
            verified = dict(candidate)
            process_steps, current_status = _bill_process(verified)
            verified["verification_status"] = "TOPIC_TITLE_VERIFIED"
            verified["process_steps"] = process_steps
            verified["current_status"] = current_status
            verified["status_as_of"] = _as_iso_date(verified.get("status_as_of"))
            bills[key] = verified
        timeline_meetings: dict[str, set[str]] = {}
        for occurrence in occurrences:
            if not occurrence["meeting_date"]:
                continue
            day = occurrence["meeting_date"].isoformat()
            timeline_meetings.setdefault(day, set()).add(occurrence["broadcast_id"])
        current = len({
            item["broadcast_id"] for item in occurrences
            if item["meeting_date"] and current_start <= item["meeting_date"] <= latest_date
        })
        previous = len({
            item["broadcast_id"] for item in occurrences
            if item["meeting_date"] and previous_start <= item["meeting_date"] <= previous_end
        })
        if current == 0 and previous:
            trend_status = "최근 미관측"
        elif previous >= 1 and current >= 3 and current >= previous * 2:
            trend_status = "급증"
        elif current and previous:
            trend_status = "지속"
        elif current:
            trend_status = "신규 관측"
        else:
            trend_status = "관측 부족"
        tasks = list(dict.fromkeys(
            task for item in reversed(occurrences) for task in item["tasks"]
        ))
        legislative_occurrences = [
            item for item in occurrences
            if item["institution"] in {"LEGISLATURE", "NATIONAL_ASSEMBLY"}
        ]
        latest_legislative = max(
            legislative_occurrences,
            key=lambda item: item["meeting_date"] or date.min,
            default=None,
        )
        discussion_events = []
        seen_discussions: set[tuple[str, str]] = set()
        for occurrence in sorted(
            occurrences, key=lambda item: item["meeting_date"] or date.min,
        ):
            discussion_key = (occurrence["broadcast_id"], occurrence["topic_id"])
            if discussion_key in seen_discussions:
                continue
            seen_discussions.add(discussion_key)
            discussion_events.append({
                "broadcast_id": occurrence["broadcast_id"],
                "meeting_title": occurrence["meeting_title"],
                "date": _as_iso_date(occurrence["meeting_date"]),
                "committee_name": occurrence["committee_name"],
                "institution": occurrence["institution"],
                "topic": occurrence["title"],
                "summary": occurrence["summary"],
                "authority_status": occurrence["authority_status"],
                "evidence_count": len(occurrence["evidence_ids"]),
            })
        if bills:
            transition_stage = "BILL_LINKED"
            transition_label = "공식 의안 직접 연결"
        elif _DECISION_WORDS.search(representative["title"] + " " + representative["summary"]):
            transition_stage = "DECISION_MENTIONED"
            transition_label = "보고서상 의결·시행"
        elif _FORMALIZATION_WORDS.search(
            representative["title"] + " " + representative["summary"]
        ):
            transition_stage = "FORMALIZATION_MENTIONED"
            transition_label = "보고서상 법안·제도개편"
        elif tasks:
            transition_stage = "FOLLOW_UP_TASK"
            transition_label = "후속 과제 도출"
        else:
            transition_stage = "DISCUSSION"
            transition_label = "논의 관측"
        stable_key = min(item["key"] for item in occurrences)
        items.append({
            "id": "issue-" + hashlib.sha256(stable_key.encode("utf-8")).hexdigest()[:12],
            "topic": representative["title"],
            "summary": representative["summary"],
            "trend_status": trend_status,
            "current_meeting_count": current,
            "previous_meeting_count": previous,
            "meeting_count": len(meetings),
            "mention_count": len(evidence_ids),
            "timeline": [
                {"date": key, "meeting_count": len(broadcast_ids)}
                for key, broadcast_ids in sorted(timeline_meetings.items())
            ],
            "discussion_events": discussion_events,
            "latest_meeting": {
                "broadcast_id": representative["broadcast_id"],
                "title": representative["meeting_title"],
                "date": representative["meeting_date"].isoformat()
                    if representative["meeting_date"] else None,
                "committee_name": representative["committee_name"],
                "institution": representative["institution"],
                "authority_status": representative["authority_status"],
            },
            "latest_legislative_meeting": ({
                "broadcast_id": latest_legislative["broadcast_id"],
                "title": latest_legislative["meeting_title"],
                "date": latest_legislative["meeting_date"].isoformat()
                    if latest_legislative["meeting_date"] else None,
                "committee_name": latest_legislative["committee_name"],
                "summary": latest_legislative["summary"],
                "authority_status": latest_legislative["authority_status"],
            } if latest_legislative else None),
            "institutions": sorted({
                item["institution"] for item in occurrences if item["institution"]
            }),
            "ministries": sorted({
                ministry for item in occurrences for ministry in item["ministries"]
            }),
            "tasks": tasks[:4],
            "bills": sorted(bills.values(), key=lambda item: str(item.get("bill_number") or "")),
            "rejected_bill_link_count": len(candidate_bills) - len(bills),
            "transition_stage": transition_stage,
            "transition_label": transition_label,
        })
    priority = {"급증": 4, "지속": 3, "신규 관측": 2, "최근 미관측": 1, "관측 부족": 0}
    items.sort(key=lambda item: (
        priority[item["trend_status"]], item["current_meeting_count"],
        item["mention_count"], item["topic"],
    ), reverse=True)
    return {
        "items": items,
        "count": len(items),
        "latest_observed_date": latest_date.isoformat(),
        "generator_version": GENERATOR_VERSION,
        "authority_status": "PROVISIONAL",
        "source_status": "STORED_MEETING_REPORT_TOPICS",
        "additional_llm_calls": 0,
    }
