from __future__ import annotations

import argparse
import json
from typing import Any
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.official_integration_repository import OfficialIntegrationRepository
from ..db.speaker_repository import SpeakerRepository
from ..services.meeting_brief import link_tasks_to_topics
from ..services.official_brief_speakers import (
    apply_official_speakers_to_brief,
    merge_validation_repairs,
    remove_unsupported_official_claims,
)
from ..services.official_edit_validation import filter_supported_official_edits
from ..services.official_speaker_context import resolve_brief_speaker_context
from ..services.official_reconciliation import (
    SPEAKER_MATCH_METHOD,
    align_live_segments,
    apply_official_edits,
    speaker_reconciliation_stats,
)
from ..services.transcript_presentation import apply_speaker_overrides


def revalidate_one(broadcast_id: UUID) -> dict[str, Any]:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        repository = OfficialIntegrationRepository(connection)
        brief_record = MeetingBriefRepository(connection).latest(broadcast_id)
        live_repository = LiveRepository(connection)
        context = live_repository.broadcast_official_context(broadcast_id)
        document_id = (context or {}).get("official_document_id")
        integration = (
            repository.latest_for_brief_document(brief_record["brief_id"], document_id)
            if brief_record and document_id else None
        )
        material = live_repository.broadcast_official_material(
            broadcast_id, document_id=document_id,
        ) if document_id else {"document": None, "utterances": []}
        if not integration or not brief_record or not material.get("document"):
            raise ValueError("saved integration, brief, and official document are required")
        live_brief = link_tasks_to_topics(brief_record.get("brief") or {})
        filtered = filter_supported_official_edits(
            {"edits": [
                item for item in integration.get("changes") or []
                if not item.get("validation_rule")
            ]}, live_brief,
            material.get("utterances") or [],
        )
        integrated_brief, changes = apply_official_edits(live_brief, filtered)
        snapshot = LiveRepository(connection).ended_transcript_snapshot(broadcast_id)
        overrides = SpeakerRepository(connection).override_map([broadcast_id])
        segments = apply_speaker_overrides(
            [{**item, "broadcast_id": broadcast_id} for item in snapshot["segments"]],
            overrides,
        )
        matches = align_live_segments(segments, material.get("utterances") or [])
        repository.replace_segment_matches(
            matches, match_method=SPEAKER_MATCH_METHOD,
            document_id=material["document"]["document_id"],
            revision_ids=[item["revision_id"] for item in segments],
        )
        speaker_stats = speaker_reconciliation_stats(matches)
        integrated_brief = apply_official_speakers_to_brief(
            integrated_brief, segments, matches,
        )
        integrated_brief, _ = resolve_brief_speaker_context(
            integrated_brief, segments, material.get("utterances") or [],
            reviewed_decisions=repository.reviewed_speaker_decisions(
                brief_record["brief_id"], material["document"]["document_id"],
            ),
        )
        integrated_brief, claim_repairs = remove_unsupported_official_claims(
            integrated_brief, material.get("utterances") or [],
        )
        changes = merge_validation_repairs(changes, claim_repairs)
        saved = repository.save(
            broadcast_id=broadcast_id,
            meeting_brief_id=brief_record["brief_id"],
            official_document_id=material["document"]["document_id"],
            integration_version=integration["integration_version"],
            status="READY", integrated_brief=integrated_brief,
            changes=changes,
            speaker_stats=speaker_stats,
            usage_metadata={
                **(integration.get("usage_metadata") or {}),
                "revalidated_without_llm": True,
            },
        )
    return {
        "broadcast_id": str(broadcast_id), "status": saved["status"],
        "before_changes": len(integration.get("changes") or []),
        "after_changes": len(changes), "api_requests": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Revalidate a cached official integration")
    parser.add_argument("broadcast_id", type=UUID)
    args = parser.parse_args()
    print(json.dumps(revalidate_one(args.broadcast_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
