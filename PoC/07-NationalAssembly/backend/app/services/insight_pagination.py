"""Page the full insight projection after selecting its display category."""
from typing import Any
import unicodedata

from ..domain.ministry import normalize_ministry_mentions


_SEARCH_FIELDS = frozenset({
    "topic", "summary", "text", "title", "label", "ministries", "shared_ministries",
    "tasks", "bills", "bill_name", "bill_number", "agenda_name", "agenda_topic",
    "meeting_title", "committee_name", "committees", "latest_meeting",
    "latest_legislative_meeting", "discussion_events", "executive_evidence",
    "legislative_evidence", "trend_status", "transition_label", "temporal_label",
})


def _search_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return " ".join(_search_text(item) for item in value)
    if isinstance(value, dict):
        return " ".join(_search_text(item) for key, item in value.items() if key in _SEARCH_FIELDS)
    return ""


def _normalize(value: str) -> str:
    return unicodedata.normalize("NFKC", normalize_ministry_mentions(value)).casefold()


def insight_page(result: dict[str, Any], limit: int | None, offset: int = 0,
                 category: str = "all", q: str = "") -> dict[str, Any]:
    items = list(result.get("items") or [])
    if category == "institution":
        order = {"BILL_LINKED": 4, "DECISION_MENTIONED": 3,
                 "FORMALIZATION_MENTIONED": 2, "FOLLOW_UP_TASK": 1}
        items = [item for item in items if item.get("transition_stage") in order]
        items.sort(key=lambda item: (-order[item["transition_stage"]],
                                    -int(item.get("current_meeting_count") or 0)))
    unfiltered_total = len(items)
    terms = _normalize(q.strip()).split()
    if terms:
        items = [item for item in items
                 if all(term in _normalize(_search_text(item)) for term in terms)]
    total = len(items)
    page = items[offset:offset + limit] if limit is not None else items[offset:]
    next_offset = offset + len(page)
    return {**result, "items": page, "count": len(page), "total_count": total,
            "query": q.strip(), "unfiltered_total_count": unfiltered_total,
            "offset": offset, "has_more": next_offset < total,
            "next_offset": next_offset if next_offset < total else None}
