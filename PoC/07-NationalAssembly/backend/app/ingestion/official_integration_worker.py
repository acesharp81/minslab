from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.official_integration_job_repository import OfficialIntegrationJobRepository
from ..db.official_integration_repository import OfficialIntegrationRepository
from ..db.speaker_repository import SpeakerRepository
from ..db.summary_repository import SummaryRepository
from ..services.meeting_brief import link_tasks_to_topics
from ..services.mistral_budget import (
    mistral_budget_reached,
    mistral_budget_values,
)
from ..services.official_brief_speakers import (
    apply_official_speakers_to_brief,
    merge_validation_repairs,
    remove_unsupported_official_claims,
)
from ..services.official_edit_validation import filter_supported_official_edits
from ..services.official_evidence_presentation import (
    official_material_hash,
    remap_official_references,
)
from ..services.official_reconciliation import (
    INTEGRATION_VERSION,
    SPEAKER_MATCH_METHOD,
    align_live_segments,
    apply_official_edits,
    speaker_reconciliation_stats,
)
from ..services.official_revision_client import MistralOfficialRevisionClient
from ..services.transcript_presentation import apply_speaker_overrides

TEMPORARY_STABILITY_WINDOW = timedelta(minutes=30)


def normalized_cached_edits(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Restore a reusable edit payload from a previously accepted change list."""
    result: list[dict[str, Any]] = []
    for source in changes:
        edit = dict(source)
        operation = str(edit.get("operation") or "")
        field = str(edit.get("field") or "")
        if operation == "UPDATE":
            if field == "ministries":
                if not edit.get("new_values") and isinstance(edit.get("after"), list):
                    edit["new_values"] = list(edit["after"])
            elif not str(edit.get("new_text") or "").strip():
                edit["new_text"] = str(edit.get("after") or "")
        elif operation == "ADD" and not str(edit.get("title") or "").strip():
            edit["title"] = str(edit.get("after") or "")
        result.append(edit)
    return result


def temporary_document_stable(
    document: dict[str, Any], *, now: datetime | None = None,
) -> bool:
    if document.get("publication_stage") != "TEMPORARY":
        return True
    retrieved_at = document.get("retrieved_at")
    if not isinstance(retrieved_at, datetime):
        return False
    current = now or datetime.now(timezone.utc)
    if retrieved_at.tzinfo is None:
        retrieved_at = retrieved_at.replace(tzinfo=timezone.utc)
    return current - retrieved_at >= TEMPORARY_STABILITY_WINDOW


def cached_ready_status(
    cached: dict[str, Any] | None, *, temporary_stable: bool, force: bool,
) -> str | None:
    if not cached or cached.get("status") != "READY" or force:
        return None
    deferred = (
        (cached.get("usage_metadata") or {}).get("reuse_reason")
        == "TEMPORARY_UPDATE_DEFERRED"
    )
    if deferred:
        return None if temporary_stable else "DEFERRED"
    return "CACHED"


def generate_one(
    broadcast_id: UUID, *, force: bool = False, deterministic_only: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        live_repository = LiveRepository(connection)
        brief_record = MeetingBriefRepository(connection).latest(broadcast_id)
        material = live_repository.broadcast_official_material(broadcast_id)
        document = material.get("document")
        if not brief_record or not document:
            raise ValueError("LIVE brief and official document are required")
        repository = OfficialIntegrationRepository(connection)
        cached = repository.get_cached(
            brief_record["brief_id"], document["document_id"], INTEGRATION_VERSION,
        )
        temporary_stable = temporary_document_stable(document)
        cached_deferred = bool(
            cached
            and cached.get("usage_metadata", {}).get("reuse_reason")
            == "TEMPORARY_UPDATE_DEFERRED"
        )
        cached_status = cached_ready_status(
            cached, temporary_stable=temporary_stable, force=force,
        )
        if cached_status:
            return {
                "broadcast_id": str(broadcast_id), "status": cached_status,
                "changes": len(cached.get("changes") or []), "api_requests": 0,
                **(
                    {"reuse_reason": "TEMPORARY_UPDATE_DEFERRED"}
                    if cached_status == "DEFERRED" else {}
                ),
            }
        snapshot = live_repository.ended_transcript_snapshot(broadcast_id)
        overrides = SpeakerRepository(connection).override_map([broadcast_id])
        segments = apply_speaker_overrides(
            [{**item, "broadcast_id": broadcast_id} for item in snapshot["segments"]],
            overrides,
        )
        official_rows = list(material.get("utterances") or [])
        semantic_hash = official_material_hash(official_rows)
        matches = align_live_segments(segments, official_rows)
        repository.replace_segment_matches(matches, match_method=SPEAKER_MATCH_METHOD)
        speaker_stats = speaker_reconciliation_stats(matches)
        live_brief = link_tasks_to_topics(brief_record.get("brief") or {})
        reusable = repository.latest_for_brief(
            brief_record["brief_id"],
        ) if not force else None
        same_semantic_content = bool(
            reusable
            and reusable.get("usage_metadata", {}).get("official_semantic_hash")
            == semantic_hash
        )
        deferred_analysis_due = bool(
            reusable
            and reusable.get("official_document_id") == document["document_id"]
            and reusable.get("usage_metadata", {}).get("reuse_reason")
            == "TEMPORARY_UPDATE_DEFERRED"
            and temporary_stable
        )
        reuse_temporary = bool(
            reusable
            and document.get("publication_stage") == "TEMPORARY"
            and not temporary_stable
            and reusable.get("official_document_id") != document["document_id"]
        )
        deterministic_upgrade = bool(
            reusable
            and reusable.get("status") == "READY"
            and same_semantic_content
            and reusable.get("integration_version") != INTEGRATION_VERSION
        )
        if deterministic_upgrade:
            identifier_map = repository.official_utterance_id_map(
                reusable["official_document_id"], document["document_id"],
            )
            cached_changes = remap_official_references(
                reusable.get("changes") or [], identifier_map,
            )
            supported_edits = filter_supported_official_edits(
                {"edits": normalized_cached_edits(cached_changes)},
                live_brief,
                official_rows,
            )
            integrated_brief, changes = apply_official_edits(
                live_brief, supported_edits,
            )
            integrated_brief = apply_official_speakers_to_brief(
                integrated_brief, segments, matches,
            )
            integrated_brief, claim_repairs = remove_unsupported_official_claims(
                integrated_brief, official_rows,
            )
            changes = merge_validation_repairs(changes, claim_repairs)
            usage_metadata = {
                "api_requests": 0,
                "official_semantic_hash": semantic_hash,
                "publication_stage": document.get("publication_stage"),
                "reused_integration_id": str(reusable["integration_id"]),
                "reuse_reason": "DETERMINISTIC_COMPARISON_UPGRADE",
            }
            saved = repository.save(
                broadcast_id=broadcast_id,
                meeting_brief_id=brief_record["brief_id"],
                official_document_id=document["document_id"],
                integration_version=INTEGRATION_VERSION,
                status="READY",
                integrated_brief=integrated_brief,
                changes=changes,
                speaker_stats=speaker_stats,
                usage_metadata=usage_metadata,
            )
            return {
                "broadcast_id": str(broadcast_id),
                "status": "UPGRADED",
                "changes": len(saved.get("changes") or []),
                "matched_segments": speaker_stats["matched_segments"],
                "api_requests": 0,
                "reuse_reason": usage_metadata["reuse_reason"],
            }
        if reusable and reusable.get("status") == "READY" and (
            (same_semantic_content and not deferred_analysis_due)
            or reuse_temporary
        ):
            identifier_map = repository.official_utterance_id_map(
                reusable["official_document_id"], document["document_id"],
            )
            usage_metadata = {
                "api_requests": 0,
                "official_semantic_hash": semantic_hash,
                "publication_stage": document.get("publication_stage"),
                "reused_integration_id": str(reusable["integration_id"]),
                "reuse_reason": (
                    "SEMANTICALLY_IDENTICAL"
                    if same_semantic_content else "TEMPORARY_UPDATE_DEFERRED"
                ),
            }
            saved = repository.save(
                broadcast_id=broadcast_id,
                meeting_brief_id=brief_record["brief_id"],
                official_document_id=document["document_id"],
                integration_version=INTEGRATION_VERSION,
                status="READY",
                integrated_brief=remap_official_references(
                    reusable.get("integrated_brief") or {}, identifier_map,
                ),
                changes=remap_official_references(
                    reusable.get("changes") or [], identifier_map,
                ),
                speaker_stats=speaker_stats,
                usage_metadata=usage_metadata,
            )
            return {
                "broadcast_id": str(broadcast_id),
                "status": "REUSED",
                "changes": len(saved.get("changes") or []),
                "matched_segments": speaker_stats["matched_segments"],
                "api_requests": 0,
                "reuse_reason": usage_metadata["reuse_reason"],
            }
        if (
            document.get("publication_stage") == "TEMPORARY"
            and not temporary_stable and not reusable
        ):
            integrated_brief = apply_official_speakers_to_brief(
                live_brief, segments, matches,
            )
            usage_metadata = {
                "api_requests": 0,
                "official_semantic_hash": semantic_hash,
                "publication_stage": "TEMPORARY",
                "reuse_reason": "TEMPORARY_UPDATE_DEFERRED",
            }
            repository.save(
                broadcast_id=broadcast_id,
                meeting_brief_id=brief_record["brief_id"],
                official_document_id=document["document_id"],
                integration_version=INTEGRATION_VERSION,
                status="READY",
                integrated_brief=integrated_brief,
                changes=[],
                speaker_stats=speaker_stats,
                usage_metadata=usage_metadata,
            )
            return {
                "broadcast_id": str(broadcast_id),
                "status": "DEFERRED",
                "changes": 0,
                "matched_segments": speaker_stats["matched_segments"],
                "api_requests": 0,
                "reuse_reason": usage_metadata["reuse_reason"],
            }

        if deterministic_only:
            return {
                "broadcast_id": str(broadcast_id),
                "status": "SKIPPED_LLM_REQUIRED",
                "changes": len(reusable.get("changes") or []) if reusable else 0,
                "api_requests": 0,
            }

    usage_metadata: dict[str, Any] = {
        "api_requests": 0,
        "official_semantic_hash": semantic_hash,
        "publication_stage": document.get("publication_stage"),
    }
    edits: list[dict[str, Any]] = []
    if settings.ai_enrichment_enabled and settings.llm_provider == "mistral":
        with connect(settings.database_url) as connection:
            usage = SummaryRepository(connection).monthly_token_usage(
                "mistral", settings.llm_model,
            )
            if mistral_budget_reached(
                usage, **mistral_budget_values(settings),
            ):
                raise RuntimeError("Mistral monthly credit limit reached")
        result = MistralOfficialRevisionClient(
            settings.mistral_api_key, model=settings.llm_model,
            base_url=settings.mistral_base_url,
        ).compare(live_brief, official_rows)
        edits = result.edits
        usage_metadata = {
            "api_requests": 1,
            "official_semantic_hash": semantic_hash,
            "publication_stage": document.get("publication_stage"),
            **result.usage_metadata,
        }
        with connect(settings.database_url) as connection:
            SummaryRepository(connection).record_monthly_token_usage(
                "mistral", settings.llm_model, result.usage_metadata,
            )

    integrated_brief, changes = apply_official_edits(live_brief, edits)
    integrated_brief = apply_official_speakers_to_brief(
        integrated_brief, segments, matches,
    )
    integrated_brief, claim_repairs = remove_unsupported_official_claims(
        integrated_brief, official_rows,
    )
    changes = merge_validation_repairs(changes, claim_repairs)
    with connect(settings.database_url) as connection:
        saved = OfficialIntegrationRepository(connection).save(
            broadcast_id=broadcast_id,
            meeting_brief_id=brief_record["brief_id"],
            official_document_id=document["document_id"],
            integration_version=INTEGRATION_VERSION,
            status="READY", integrated_brief=integrated_brief,
            changes=changes, speaker_stats=speaker_stats,
            usage_metadata=usage_metadata,
        )
    return {
        "broadcast_id": str(broadcast_id), "status": saved["status"],
        "changes": len(changes), "matched_segments": speaker_stats["matched_segments"],
        "api_requests": int(usage_metadata.get("api_requests") or 0),
    }


def eligible_broadcast_ids(limit: int = 5) -> list[UUID]:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        repository = OfficialIntegrationJobRepository(connection)
        repository.sync_pending(INTEGRATION_VERSION)
        rows = connection.execute(
            """
            SELECT DISTINCT ON (job.broadcast_id) job.broadcast_id
            FROM meeting_official_integration_jobs job
            WHERE job.status = 'PENDING'
               OR (job.status = 'RETRY_WAIT' AND job.next_attempt_at <= now())
               OR (job.status = 'PROCESSING' AND job.lease_expires_at < now())
            ORDER BY job.broadcast_id, job.created_at, job.id
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [row[0] for row in rows]


def process_available(
    limit: int = 5, *, deterministic_only: bool = False,
) -> list[dict[str, Any]]:
    settings = get_settings()
    worker_id = f"official-integration-{uuid4()}"
    with connect(settings.database_url) as connection:
        queued = OfficialIntegrationJobRepository(connection).sync_pending(
            INTEGRATION_VERSION,
        )
    results: list[dict[str, Any]] = []
    for _ in range(limit):
        with connect(settings.database_url) as connection:
            job = OfficialIntegrationJobRepository(connection).claim(worker_id)
        if not job:
            break
        broadcast_id = job["broadcast_id"]
        try:
            result = generate_one(
                broadcast_id, deterministic_only=deterministic_only,
            )
            if result.get("status") in {
                "DEFERRED", "SKIPPED_LLM_REQUIRED",
            }:
                with connect(settings.database_url) as connection:
                    OfficialIntegrationJobRepository(connection).retry(
                        job["job_id"],
                        (
                            "TEMPORARY_STABILITY_WINDOW"
                            if result.get("status") == "DEFERRED"
                            else "LLM_REQUIRED"
                        ),
                    )
            else:
                with connect(settings.database_url) as connection:
                    OfficialIntegrationJobRepository(connection).complete(job["job_id"])
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - isolate one meeting failure
            error = f"{type(exc).__name__}: {str(exc)[:120]}"
            with connect(settings.database_url) as connection:
                OfficialIntegrationJobRepository(connection).retry(job["job_id"], error)
            results.append({
                "broadcast_id": str(broadcast_id), "status": "RETRY_WAIT",
                "error": type(exc).__name__, "attempt": job["attempt_count"],
            })
    if queued and not results:
        results.append({"status": "QUEUED", "jobs": queued})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile LIVE briefs with official minutes")
    parser.add_argument("--broadcast-id", type=UUID)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--interval", type=float, default=15.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--deterministic-only", action="store_true",
        help="Reuse cached verified changes only; never call an external LLM",
    )
    args = parser.parse_args()
    if args.broadcast_id:
        result: Any = generate_one(
            args.broadcast_id, force=args.force,
            deterministic_only=args.deterministic_only,
        )
        print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        return
    if not 2 <= args.interval <= 3600:
        parser.error("interval must be between 2 and 3600 seconds")
    while True:
        result = process_available(
            args.limit, deterministic_only=args.deterministic_only,
        )
        if result:
            print(json.dumps(result, ensure_ascii=False, default=str), flush=True)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
