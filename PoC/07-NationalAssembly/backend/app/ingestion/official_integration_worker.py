from __future__ import annotations

import argparse
import json
import time

import requests
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
from ..services.official_speaker_context import resolve_brief_speaker_context
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
    unambiguous_revision_matches,
)
from ..services.official_revision_client import (
    MistralOfficialRevisionClient,
    OpenRouterOfficialRevisionClient,
)
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
    first_seen_at = document.get("semantic_first_seen_at") or document.get("retrieved_at")
    if not isinstance(first_seen_at, datetime):
        return False
    current = now or datetime.now(timezone.utc)
    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
    return current - first_seen_at >= TEMPORARY_STABILITY_WINDOW


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
    official_document_id: UUID | None = None,
    meeting_brief_id: UUID | None = None,
    source_only_due_to_prior_failure: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        live_repository = LiveRepository(connection)
        brief_repository = MeetingBriefRepository(connection)
        brief_record = (
            brief_repository.get_by_id(broadcast_id, meeting_brief_id)
            if meeting_brief_id is not None
            else brief_repository.latest(broadcast_id)
        )
        material = live_repository.broadcast_official_material(
            broadcast_id, document_id=official_document_id,
        )
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
        reviewed_decisions = repository.reviewed_speaker_decisions(
            brief_record["brief_id"], document["document_id"],
        )
        semantic_hash = official_material_hash(official_rows)
        part_matches = align_live_segments(
            segments, official_rows, retain_conflicted_revisions=True,
        )
        repository.replace_part_matches(
            document["document_id"], segments, part_matches,
            match_method=SPEAKER_MATCH_METHOD,
        )
        matches = unambiguous_revision_matches(part_matches)
        repository.replace_segment_matches(
            matches, match_method=SPEAKER_MATCH_METHOD,
            document_id=document["document_id"],
            revision_ids=[item["revision_id"] for item in segments],
        )
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
            integrated_brief, _ = resolve_brief_speaker_context(
                integrated_brief, segments, official_rows,
                reviewed_decisions=reviewed_decisions,
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
            remapped_brief = remap_official_references(
                reusable.get("integrated_brief") or {}, identifier_map,
            )
            remapped_brief, _ = resolve_brief_speaker_context(
                remapped_brief, segments, official_rows,
                reviewed_decisions=reviewed_decisions,
            )
            saved = repository.save(
                broadcast_id=broadcast_id,
                meeting_brief_id=brief_record["brief_id"],
                official_document_id=document["document_id"],
                integration_version=INTEGRATION_VERSION,
                status="READY",
                integrated_brief=remapped_brief,
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
            integrated_brief, _ = resolve_brief_speaker_context(
                integrated_brief, segments, official_rows,
                reviewed_decisions=reviewed_decisions,
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
    if source_only_due_to_prior_failure:
        usage_metadata.update({
            "comparison_mode": "SOURCE_ONLY_TIMEOUT",
            "comparison_error": "PREVIOUS_GATEWAY_FAILURE",
        })
    elif settings.ai_enrichment_enabled and settings.llm_provider in {"mistral", "openrouter"}:
        if settings.llm_provider == "mistral":
            with connect(settings.database_url) as connection:
                usage = SummaryRepository(connection).monthly_token_usage(
                    "mistral", settings.llm_model,
                )
                if mistral_budget_reached(
                    usage, **mistral_budget_values(settings),
                ):
                    raise RuntimeError("Mistral monthly credit limit reached")
            client = MistralOfficialRevisionClient(
                settings.mistral_api_key, model=settings.llm_model,
                base_url=settings.mistral_base_url,
            )
        else:
            client = OpenRouterOfficialRevisionClient(
                settings.openrouter_api_key, model=settings.llm_model,
                base_url=settings.openrouter_base_url,
            )
        result = None
        try:
            result = client.compare(live_brief, official_rows)
        except (requests.Timeout, requests.exceptions.JSONDecodeError, json.JSONDecodeError) as exc:
            # The official source and exact speaker links are already stored.
            # Keep them available after a slow model request while clearly
            # retaining LIVE summaries as unreviewed provisional content.
            edits = []
            usage_metadata = {
                "api_requests": 1,
                "official_semantic_hash": semantic_hash,
                "publication_stage": document.get("publication_stage"),
                "comparison_mode": "SOURCE_ONLY_TIMEOUT",
                "comparison_error": type(exc).__name__,
            }
        else:
            edits = result.edits
            usage_metadata = {
                "api_requests": 1,
                "official_semantic_hash": semantic_hash,
                "publication_stage": document.get("publication_stage"),
                **result.usage_metadata,
            }
        if settings.llm_provider == "mistral" and result is not None:
            with connect(settings.database_url) as connection:
                SummaryRepository(connection).record_monthly_token_usage(
                    "mistral", settings.llm_model, result.usage_metadata,
                )

    integrated_brief, changes = apply_official_edits(live_brief, edits)
    integrated_brief = apply_official_speakers_to_brief(
        integrated_brief, segments, matches,
    )
    integrated_brief, _ = resolve_brief_speaker_context(
        integrated_brief, segments, official_rows,
        reviewed_decisions=reviewed_decisions,
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
                official_document_id=job["official_document_id"],
                meeting_brief_id=job["meeting_brief_id"],
                source_only_due_to_prior_failure=str(job.get("last_error") or "").startswith(
                    ("ReadTimeout:", "Timeout:", "JSONDecodeError:")
                ),
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
