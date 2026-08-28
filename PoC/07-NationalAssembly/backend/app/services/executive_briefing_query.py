from __future__ import annotations

from typing import Any


def build_executive_content_groups(
    meeting: dict[str, Any], agendas: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected = agendas if agendas is not None else list(meeting.get("agendas") or [])
    reports = [
        agenda for agenda in selected if agenda.get("agenda_type") == "REPORT"
    ]
    deliberations = [
        agenda for agenda in selected if agenda.get("agenda_type") != "REPORT"
    ]
    presidential = meeting.get("presidential_briefing")
    spokesperson_items = []
    if presidential:
        spokesperson_items.append({
            "content_type": "SPOKESPERSON_BRIEFING",
            **presidential,
        })
    return [
        {
            "key": "ministry_reports",
            "label": "부처보고",
            "description": "국무회의에서 관계 부처가 보고한 정책·현안",
            "count": len(reports),
            "items": reports,
        },
        {
            "key": "deliberated_agendas",
            "label": "심의안건",
            "description": "국무회의가 심의·의결한 법률안·대통령령안 등",
            "count": len(deliberations),
            "items": deliberations,
        },
        {
            "key": "spokesperson_briefing",
            "label": "대변인 브리핑",
            "description": "같은 회차·날짜로 확인된 대통령실 공식 설명",
            "count": len(spokesperson_items),
            "items": spokesperson_items,
        },
    ]


def build_government_source_flow(
    meeting: dict[str, Any], agendas: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Expose verified government-source relationships without inventing docs."""
    selected_agendas = agendas if agendas is not None else list(meeting.get("agendas") or [])
    meeting_id = str(meeting.get("news_id") or meeting.get("meeting_number") or "meeting")
    council_id = f"state-council:{meeting_id}"
    nodes: list[dict[str, Any]] = [{
        "id": council_id,
        "source_type": "STATE_COUNCIL",
        "institution_label": "국무회의",
        "title": meeting.get("title") or "국무회의 공식 결과",
        "source_url": meeting.get("source_url"),
        "authority_status": "OFFICIAL",
    }]
    links: list[dict[str, Any]] = []

    presidential = meeting.get("presidential_briefing") or {}
    if presidential:
        presidential_id = f"presidential:{presidential.get('briefing_id') or meeting_id}"
        nodes.append({
            "id": presidential_id,
            "source_type": "PRESIDENTIAL_OFFICE",
            "institution_label": "대통령실",
            "title": presidential.get("title") or "대통령실 공식 브리핑",
            "source_url": presidential.get("source_url"),
            "authority_status": "OFFICIAL",
        })
        links.append({
            "from": council_id,
            "to": presidential_id,
            "relation_type": "SAME_MEETING_NUMBER_AND_DATE",
            "label": "같은 회차·날짜의 후속 설명",
            "authority_status": "OFFICIAL_MATCH",
        })

    ministry_agendas: dict[str, dict[str, list[str]]] = {}
    for agenda in selected_agendas:
        for ministry in agenda.get("ministries") or []:
            grouped = ministry_agendas.setdefault(
                str(ministry), {"reports": [], "deliberations": []},
            )
            key = "reports" if agenda.get("agenda_type") == "REPORT" else "deliberations"
            grouped[key].append(str(agenda.get("topic") or "공식 안건"))
    for ministry in sorted(ministry_agendas):
        reports = ministry_agendas[ministry]["reports"]
        deliberations = ministry_agendas[ministry]["deliberations"]
        ministry_id = f"ministry:{ministry}"
        if reports and deliberations:
            ministry_title = f"보고 {len(reports)}건 · 심의안건 {len(deliberations)}건"
        elif reports:
            ministry_title = f"{len(reports)}개 보고 안건"
        else:
            ministry_title = f"{len(deliberations)}개 심의 안건 소관"
        relation_type = (
            "OFFICIAL_REPORTING_MINISTRY" if reports
            else "OFFICIAL_AGENDA_OWNER"
        )
        nodes.append({
            "id": ministry_id,
            "source_type": "MINISTRY",
            "institution_label": ministry,
            "title": ministry_title,
            "agenda_titles": reports + deliberations,
            "authority_status": relation_type,
        })
        links.append({
            "from": council_id,
            "to": ministry_id,
            "relation_type": relation_type,
            "label": (
                "국무회의 원문에 명시된 보고 부처" if reports
                else "공식 안건에 명시된 소관 부처"
            ),
            "authority_status": "OFFICIAL",
        })
    for agenda in selected_agendas:
        for briefing in agenda.get("related_ministry_briefings") or []:
            briefing_id = f"ministry-briefing:{briefing.get('briefing_id')}"
            nodes.append({
                "id": briefing_id,
                "source_type": "MINISTRY_BRIEFING",
                "institution_label": briefing.get("ministry") or "부처",
                "title": briefing.get("title") or "부처 공식 브리핑",
                "source_url": briefing.get("source_url"),
                "authority_status": "OFFICIAL",
            })
            relation = briefing.get("relation") or {}
            links.append({
                "from": council_id,
                "to": briefing_id,
                "relation_type": relation.get("relation_type")
                or "SAME_DAY_MINISTRY_REPORT_BRIEFING",
                "label": relation.get("label")
                or "같은 날·동일 부처·동일 주제의 공식 브리핑",
                "authority_status": relation.get("authority_status") or "VERIFIED",
                "evidence": relation.get("evidence"),
            })
    return {"nodes": nodes, "links": links, "node_count": len(nodes)}


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
            related_titles = " ".join(
                str(row.get("title") or "")
                for row in agenda.get("related_ministry_briefings") or []
            )
            searchable = (
                f"{agenda.get('topic', '')} {agenda.get('summary', '')} {related_titles}"
            ).casefold()
            if query_filter and query_filter not in searchable:
                continue
            agendas.append(agenda)
        if agendas:
            filtered.append({
                **meeting,
                "agendas": agendas,
                "agenda_count": len(agendas),
                "content_groups": build_executive_content_groups(meeting, agendas),
                "government_flow": build_government_source_flow(meeting, agendas),
            })

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
