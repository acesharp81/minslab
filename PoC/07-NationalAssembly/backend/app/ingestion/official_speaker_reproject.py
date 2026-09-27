from __future__ import annotations

import argparse
import json
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.official_integration_repository import OfficialIntegrationRepository
from ..db.speaker_repository import SpeakerRepository
from ..services.official_brief_speakers import apply_official_speakers_to_brief
from ..services.official_speaker_context import resolve_brief_speaker_context
from ..services.official_reconciliation import (
    INTEGRATION_VERSION,
    SPEAKER_MATCH_METHOD,
    align_live_segments,
    speaker_reconciliation_stats,
)
from ..services.transcript_presentation import apply_speaker_overrides


PROJECTION_VERSION = f"{INTEGRATION_VERSION}-speaker-context/4"


def _is_unknown(point: dict) -> bool:
    return not bool(
        point.get("speaker_official") is True and point.get("official_evidence_ids")
    )


def _unknown_points(brief: dict) -> int:
    return sum(
        _is_unknown(point)
        for topic in brief.get("topics") or []
        for point in topic.get("speaker_points") or []
    )


def reproject(broadcast_id: UUID, *, apply: bool = False) -> dict[str, object]:
    with connect(get_settings().database_url) as connection:
        live = LiveRepository(connection)
        integrations = OfficialIntegrationRepository(connection)
        brief = MeetingBriefRepository(connection).latest(broadcast_id)
        if not brief:
            raise ValueError("no LIVE brief for broadcast")
        context = live.broadcast_official_context(broadcast_id)
        current_document_id = (context or {}).get("official_document_id")
        if not current_document_id:
            raise ValueError("no current official document for broadcast")
        material = live.broadcast_official_material(
            broadcast_id, document_id=current_document_id,
        )
        document = material.get("document")
        if not document or document.get("publication_stage") not in ("TEMPORARY", "FINAL"):
            raise ValueError("no official minutes document for broadcast")
        base = integrations.get_cached(
            brief["brief_id"], document["document_id"], INTEGRATION_VERSION,
        )
        if not base or base.get("status") != "READY":
            raise ValueError("no ready official integration for selected brief and document")
        existing = integrations.get_cached(
            brief["brief_id"], document["document_id"], PROJECTION_VERSION,
        )
        if existing and existing.get("status") == "READY":
            return {"status": "ALREADY_READY", "broadcast_id": str(broadcast_id),
                    "projection_version": PROJECTION_VERSION}
        snapshot = live.ended_transcript_snapshot(broadcast_id)
        overrides = SpeakerRepository(connection).override_map([broadcast_id])
        segments = apply_speaker_overrides(snapshot["segments"], overrides)
        matches = align_live_segments(segments, material.get("utterances") or [])
        original = base.get("integrated_brief") or {}
        attributed = apply_official_speakers_to_brief(
            original, segments, matches,
        )
        reviewed_decisions = integrations.reviewed_speaker_decisions(
            brief["brief_id"], document["document_id"],
        )
        updated, context_stats = resolve_brief_speaker_context(
            attributed, segments, material.get("utterances") or [],
            reviewed_decisions=reviewed_decisions,
        )
        result: dict[str, object] = {
            "status": "PREVIEW" if not apply else "READY",
            "broadcast_id": str(broadcast_id),
            "projection_version": PROJECTION_VERSION,
            "matched_segments": len(matches),
            "publication_stage": document["publication_stage"],
            "unknown_points_before": _unknown_points(original),
            "unknown_points_after": _unknown_points(updated),
            "speaker_resolution": context_stats,
            "api_requests": 0,
        }
        if apply:
            original_usage = base.get("usage_metadata") or {}
            integrations.save(
                broadcast_id=broadcast_id,
                meeting_brief_id=brief["brief_id"],
                official_document_id=document["document_id"],
                integration_version=PROJECTION_VERSION,
                status="READY", integrated_brief=updated,
                changes=base.get("changes") or [],
                speaker_stats=speaker_reconciliation_stats(matches),
                usage_metadata={
                    "api_requests": 0,
                    "publication_stage": document["publication_stage"],
                    "official_semantic_hash": original_usage.get("official_semantic_hash"),
                    "reuse_reason": "DETERMINISTIC_SPEAKER_REPROJECTION",
                    "reused_integration_id": str(base["integration_id"]),
                    "speaker_match_method": SPEAKER_MATCH_METHOD,
                    "speaker_resolution": context_stats,
                },
            )
        return result


def _ready_broadcast_ids() -> list[UUID]:
    with connect(get_settings().database_url) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT integration.broadcast_id
            FROM meeting_official_integrations integration
            JOIN live_broadcasts broadcast ON broadcast.id = integration.broadcast_id
            WHERE integration.integration_version = %s
              AND integration.status = 'READY'
              AND broadcast.institution = 'LEGISLATURE'
            ORDER BY integration.broadcast_id
            """,
            (INTEGRATION_VERSION,),
        ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Reproject official speaker names")
    parser.add_argument("broadcast_id", nargs="?", type=UUID)
    parser.add_argument("--all-ready", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if bool(args.broadcast_id) == bool(args.all_ready):
        parser.error("provide a broadcast_id or --all-ready")
    broadcast_ids = _ready_broadcast_ids() if args.all_ready else [args.broadcast_id]
    totals = {"broadcasts": 0, "ready": 0, "newly_named_points": 0, "errors": 0}
    for broadcast_id in broadcast_ids:
        try:
            result = reproject(broadcast_id, apply=args.apply)
            totals["broadcasts"] += 1
            totals["ready"] += int(result.get("status") == "READY")
            totals["newly_named_points"] += max(
                0,
                int(result.get("unknown_points_before") or 0)
                - int(result.get("unknown_points_after") or 0),
            )
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except ValueError as exc:
            if args.all_ready and str(exc) == "no ready official integration for selected brief and document":
                print(json.dumps({"broadcast_id": str(broadcast_id),
                                  "status": "SKIPPED_CURRENT_DOCUMENT_PENDING"},
                                 ensure_ascii=False), flush=True)
                continue
            totals["errors"] += 1
            print(json.dumps({"broadcast_id": str(broadcast_id),
                              "status": "ERROR", "error": str(exc)},
                             ensure_ascii=False), flush=True)
        except Exception as exc:
            totals["errors"] += 1
            print(json.dumps({"broadcast_id": str(broadcast_id),
                              "status": "ERROR", "error": str(exc)},
                             ensure_ascii=False), flush=True)
    if args.all_ready:
        print(json.dumps({"summary": totals}, ensure_ascii=False))
    if totals["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
