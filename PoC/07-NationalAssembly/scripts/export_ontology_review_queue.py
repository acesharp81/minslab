"""Export current policy topics without a verified ontology assignment.

Run in an API image with DATABASE_URL configured. CSV goes to stdout.
This read-only export preserves the source report and its evidence links.
"""
from __future__ import annotations

import csv
import sys

from app.config import get_settings
from app.db.connection import connect
from app.db.live_repository import LiveRepository
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.official_integration_repository import OfficialIntegrationRepository
from app.db.topic_structure_repository import TopicStructureRepository
from app.services.meeting_topic_groups import attach_meeting_topic_groups
from app.services.meeting_brief import link_tasks_to_topics
from app.services.ontology_sources import select_current_ontology_brief
from app.services.ontology_context import review_topic_context, verified_topic_spans
from app.services.meeting_topic_groups import TARGET_ONTOLOGY


FIELDS = (
    "broadcast_id", "broadcast_title", "meeting_brief_id", "official_document_id",
    "official_url", "source_status", "topic_id", "title", "summary",
    "live_evidence_ids", "official_evidence_ids", "review_reason", "review_status",
    "parent_titles", "source_quotes", "source_revision_ids",
)


def export() -> int:
    writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    rows = []
    with connect(get_settings().database_url) as connection:
        live = LiveRepository(connection)
        integrations = OfficialIntegrationRepository(connection)
        for item in MeetingBriefRepository(connection).latest_all():
            broadcast_id = item["broadcast_id"]
            context = live.broadcast_official_context(broadcast_id) or {}
            document_id = context.get("official_document_id")
            integration = integrations.latest_for_brief_document(
                item["brief_id"], document_id,
            ) if document_id else None
            brief, source = select_current_ontology_brief(
                item, integration, document_id,
            )
            structure = TopicStructureRepository(connection).ready_current(item) if source == "PROVISIONAL" else None
            if structure:
                brief = structure
            grouped = attach_meeting_topic_groups(
                link_tasks_to_topics(brief), recover_live_topics=source == "PROVISIONAL" and not structure,
            )
            topics = {str(topic.get("id")): topic
                      for topic in grouped.get("topics") or []}
            title = connection.execute(
                "SELECT title FROM live_broadcasts WHERE id=%s", (broadcast_id,),
            ).fetchone()[0]
            for group in grouped.get("topic_groups") or []:
                if group.get("assignment_method") in {"ONTOLOGY", "REPORT_ARTIFACT"}:
                    continue
                for topic_id in group.get("topic_ids") or []:
                    topic = topics[str(topic_id)]
                    official_ids = topic.get("official_evidence_ids") or []
                    source_only = bool(
                        integration
                        and (integration.get("usage_metadata") or {}).get("comparison_mode")
                            == "SOURCE_ONLY_TIMEOUT"
                    )
                    reason = (
                        review_topic_context(topic, TARGET_ONTOLOGY)["reason"]
                        if structure else
                        "SOURCE_ONLY_SUMMARY_UNVERIFIED"
                        if source_only
                        else "OFFICIAL_INTEGRATION_PENDING"
                        if source == "PROVISIONAL" and document_id
                        else "NO_VERBATIM_OFFICIAL_SOURCE"
                        if source == "PROVISIONAL"
                        else "NO_OFFICIAL_UTTERANCE_LINK"
                        if not official_ids
                        else "NO_SAFE_ONTOLOGY_TARGET"
                    )
                    rows.append({
                        "broadcast_id": str(broadcast_id),
                        "broadcast_title": title,
                        "meeting_brief_id": str(item["brief_id"]),
                        "official_document_id": str(document_id or ""),
                        "official_url": context.get("official_url") or "",
                        "source_status": source,
                        "topic_id": topic_id,
                        "title": topic.get("title") or "",
                        "summary": topic.get("summary") or "",
                        "live_evidence_ids": "|".join(
                            str(value) for value in topic.get("evidence_ids") or []
                        ),
                        "official_evidence_ids": "|".join(str(value) for value in official_ids),
                        "review_reason": reason,
                        "review_status": "PENDING_SOURCE_REVIEW",
                        "parent_titles": " | ".join(dict.fromkeys(
                            s.get("parent", "") for s in verified_topic_spans(topic))),
                        "source_quotes": " | ".join(
                            s["quote"] for s in verified_topic_spans(topic)),
                        "source_revision_ids": "|".join(dict.fromkeys(
                            str(rev) for s in verified_topic_spans(topic) for rev in s["revision_ids"])),
                    })
    for row in sorted(rows, key=lambda value: (
        value["broadcast_title"], value["topic_id"],
    )):
        writer.writerow(row)
    return len(rows)


if __name__ == "__main__":
    count = export()
    print(f"ontology_review_queue_rows={count}", file=sys.stderr)
