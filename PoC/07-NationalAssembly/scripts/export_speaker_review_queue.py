"""Export current official-report speaker points that still need source review.

Run in an API image with DATABASE_URL configured. CSV goes to stdout. This
read-only export never promotes a draft speaker name to an official identity.
"""
from __future__ import annotations

import csv
import sys

from app.config import get_settings
from app.db.connection import connect
from app.db.live_repository import LiveRepository
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.official_integration_repository import OfficialIntegrationRepository
from app.services.official_source_speakers import source_first_speaker_points
from app.services.ontology_sources import select_current_ontology_brief


FIELDS = (
    "broadcast_id", "broadcast_title", "meeting_brief_id", "official_document_id",
    "official_url", "comparison_mode", "topic_id", "topic_title", "point_id", "draft_summary",
    "live_evidence_ids", "review_reason", "review_status",
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
            if not document_id:
                continue
            integration = integrations.latest_for_brief_document(
                item["brief_id"], document_id,
            )
            brief, source = select_current_ontology_brief(
                item, integration, document_id,
            )
            source_only = bool(
                integration and integration.get("status") == "READY"
                and (integration.get("usage_metadata") or {}).get("comparison_mode")
                    == "SOURCE_ONLY_TIMEOUT"
                and integration.get("meeting_brief_id") == item["brief_id"]
                and integration.get("official_document_id") == document_id
            )
            if source != "OFFICIAL_INTEGRATED" and not source_only:
                continue
            if source_only:
                brief = integration.get("integrated_brief") or item.get("brief") or {}
            material = live.broadcast_official_material(
                broadcast_id, document_id=document_id,
            )
            utterances = [
                {**utterance, "speaker_label": utterance.get("speaker_name")}
                for utterance in material.get("utterances") or []
            ]
            presented, _ = source_first_speaker_points(brief, utterances)
            title = connection.execute(
                "SELECT title FROM live_broadcasts WHERE id=%s", (broadcast_id,),
            ).fetchone()[0]
            for topic in presented.get("topics") or []:
                for point in topic.get("draft_only_speaker_points") or []:
                    rows.append({
                        "broadcast_id": str(broadcast_id),
                        "broadcast_title": title,
                        "meeting_brief_id": str(item["brief_id"]),
                        "official_document_id": str(document_id),
                        "official_url": context.get("official_url") or "",
                        "comparison_mode": "SOURCE_ONLY_TIMEOUT" if source_only else "MODEL_REVIEWED",
                        "topic_id": topic.get("id") or "",
                        "topic_title": topic.get("title") or "",
                        "point_id": point.get("id") or "",
                        "draft_summary": point.get("summary") or "",
                        "live_evidence_ids": "|".join(
                            str(value) for value in point.get("evidence_ids") or []
                        ),
                        "review_reason": "NO_CURRENT_OFFICIAL_UTTERANCE_LINK",
                        "review_status": "PENDING_SOURCE_REVIEW",
                    })
    for row in sorted(rows, key=lambda value: (
        value["broadcast_title"], value["topic_id"], value["point_id"],
    )):
        writer.writerow(row)
    return len(rows)


if __name__ == "__main__":
    count = export()
    print(f"speaker_review_queue_rows={count}", file=sys.stderr)
