from __future__ import annotations

from typing import Any


def filter_executive_briefings(
    items: list[dict[str, Any]],
    *,
    ministry: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    ministry_filter = (ministry or "").strip()
    query_filter = (query or "").strip().casefold()
    ministry_counts: dict[str, int] = {}
    for meeting in items:
        for agenda in meeting.get("agendas", []):
            for label in agenda.get("ministries", []):
                ministry_counts[label] = ministry_counts.get(label, 0) + 1

    filtered = []
    for meeting in items:
        agendas = []
        for agenda in meeting.get("agendas", []):
            if ministry_filter and ministry_filter not in agenda.get("ministries", []):
                continue
            searchable = f"{agenda.get('topic', '')} {agenda.get('summary', '')}".casefold()
            if query_filter and query_filter not in searchable:
                continue
            agendas.append(agenda)
        if agendas:
            filtered.append({**meeting, "agendas": agendas, "agenda_count": len(agendas)})

    return {
        "items": filtered,
        "meeting_count": len(filtered),
        "agenda_count": sum(len(item["agendas"]) for item in filtered),
        "filters": {"ministry": ministry_filter or None, "q": query_filter or None},
        "facets": {
            "ministries": [
                {"label": label, "count": count}
                for label, count in sorted(
                    ministry_counts.items(), key=lambda item: (-item[1], item[0])
                )
            ],
        },
    }
