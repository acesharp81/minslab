from __future__ import annotations

import argparse
import json
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.official_integration_repository import OfficialIntegrationRepository
from ..db.speaker_repository import SpeakerRepository
from ..services.official_reconciliation import SPEAKER_MATCH_METHOD, align_live_segments
from ..services.transcript_presentation import apply_speaker_overrides


def backfill_one(broadcast_id: UUID, *, apply: bool) -> dict[str, object]:
    with connect(get_settings().database_url) as connection:
        live = LiveRepository(connection)
        context = live.broadcast_official_context(broadcast_id)
        document_id = (context or {}).get("official_document_id")
        if not document_id:
            raise ValueError("no current official document")
        material = live.broadcast_official_material(
            broadcast_id, document_id=document_id,
        )
        if not material.get("document"):
            raise ValueError("current official document has no material")
        snapshot = live.ended_transcript_snapshot(broadcast_id)
        segments = apply_speaker_overrides(
            [{**item, "broadcast_id": broadcast_id} for item in snapshot["segments"]],
            SpeakerRepository(connection).override_map([broadcast_id]),
        )
        matches = align_live_segments(
            segments, material.get("utterances") or [],
            retain_conflicted_revisions=True,
        )
        split_segments = [
            item for item in segments if int(item.get("source_part_count") or 0) > 1
        ]
        split_matches = [
            item for item in matches if int(item.get("source_part_count") or 0) > 1
        ]
        inserted = 0
        if apply:
            inserted = OfficialIntegrationRepository(connection).replace_part_matches(
                document_id, segments, matches, match_method=SPEAKER_MATCH_METHOD,
            )
        return {
            "broadcast_id": str(broadcast_id),
            "official_document_id": str(document_id),
            "split_source_parts": len(split_segments),
            "matched_source_parts": len(split_matches),
            "inserted": inserted,
            "status": "APPLIED" if apply else "PREVIEW",
            "api_requests": 0,
        }


def ready_broadcast_ids() -> list[UUID]:
    with connect(get_settings().database_url) as connection:
        rows = connection.execute(
            """
            SELECT DISTINCT integration.broadcast_id
            FROM meeting_official_integrations integration
            JOIN live_broadcasts broadcast ON broadcast.id = integration.broadcast_id
            WHERE integration.status = 'READY'
              AND broadcast.institution = 'LEGISLATURE'
            ORDER BY integration.broadcast_id
            """
        ).fetchall()
    return [row[0] for row in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill official caption piece matches")
    parser.add_argument("broadcast_id", nargs="?", type=UUID)
    parser.add_argument("--all-ready", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if bool(args.broadcast_id) == bool(args.all_ready):
        parser.error("provide a broadcast_id or --all-ready")
    ids = ready_broadcast_ids() if args.all_ready else [args.broadcast_id]
    totals = {"broadcasts": 0, "split_source_parts": 0,
              "matched_source_parts": 0, "inserted": 0, "errors": 0}
    for broadcast_id in ids:
        try:
            result = backfill_one(broadcast_id, apply=args.apply)
            totals["broadcasts"] += 1
            for key in ("split_source_parts", "matched_source_parts", "inserted"):
                totals[key] += int(result[key])
            print(json.dumps(result, ensure_ascii=False), flush=True)
        except Exception as exc:
            totals["errors"] += 1
            print(json.dumps({"broadcast_id": str(broadcast_id),
                              "status": "ERROR", "error": str(exc)},
                             ensure_ascii=False), flush=True)
    print(json.dumps({"summary": totals}, ensure_ascii=False), flush=True)
    if totals["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
