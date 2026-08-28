from __future__ import annotations

import argparse
import json
import time
from typing import Any
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.live_repository import LiveRepository
from ..db.meeting_brief_repository import MeetingBriefRepository
from ..db.migrate import apply_migrations
from ..db.speaker_repository import SpeakerRepository
from ..db.summary_repository import SummaryRepository
from ..services.mistral_budget import (
    mistral_budget_reached,
    mistral_budget_values,
)
from ..services.broadcast_review_v2 import build_broadcast_review
from ..services.fallback_meeting_brief import (
    MODEL as FALLBACK_MODEL,
    PROMPT_VERSION as FALLBACK_PROMPT_VERSION,
    PROVIDER as FALLBACK_PROVIDER,
    build_fallback_meeting_brief,
)
from ..services.meeting_brief import (
    MistralMeetingBriefClient,
    PROMPT_VERSION,
    meeting_transcript_hash,
)
from ..services.summary_cache import MonthlyTokenLimitReached
from ..services.summary_client import summary_identity
from ..services.transcript_presentation import (
    apply_speaker_overrides,
    group_transcript_segments,
)


def prepare_brief_utterances(
    connection: Any, broadcast_id: Any, segments: list[dict[str, Any]],
    *, provider: str, model: str, summary_prompt_version: str,
) -> list[dict[str, Any]]:
    overrides = SpeakerRepository(connection).override_map([broadcast_id])
    presented = apply_speaker_overrides(
        [{**item, "broadcast_id": broadcast_id} for item in segments], overrides,
    )
    utterances = group_transcript_segments(presented)
    cached = SummaryRepository(connection).summary_map(
        [broadcast_id], provider=provider, model=model,
        prompt_version=summary_prompt_version,
    )
    for utterance in utterances:
        item = cached.get((broadcast_id, utterance["content_hash"]))
        if item:
            utterance["summary"] = item["summary"]
            utterance["summary_kind"] = "AI_CACHED"
    return utterances


def generate_one(
    broadcast_id: UUID, *, force: bool = False,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ai_enrichment_enabled or settings.llm_provider != "mistral":
        raise RuntimeError("Mistral AI enrichment is not enabled")
    summary_provider, summary_model, summary_prompt_version = summary_identity(settings)
    with connect(settings.database_url) as connection:
        row = connection.execute(
            """
            SELECT id, title, committee_name, detected_at, ended_at, institution
            FROM live_broadcasts
            WHERE id = %s
              AND (
                    (institution = 'LEGISLATURE' AND source_system = 'assembly.webcast.go.kr')
                    OR (institution = 'EXECUTIVE' AND source_system = 'ktv.go.kr')
                  )
              AND lifecycle_status = 'ENDED'
            """,
            (broadcast_id,),
        ).fetchone()
        if not row:
            raise ValueError("eligible ended broadcast not found")
        meeting = dict(zip(
            ("broadcast_id", "title", "committee_name", "detected_at", "ended_at", "institution"),
            row, strict=True,
        ))
        snapshot = LiveRepository(connection).ended_transcript_snapshot(broadcast_id)
        utterances = prepare_brief_utterances(
            connection, broadcast_id, snapshot["segments"],
            provider=summary_provider, model=summary_model,
            summary_prompt_version=summary_prompt_version,
        )
        transcript_hash = meeting_transcript_hash(utterances)
        repository = MeetingBriefRepository(connection)
        cached = repository.get_cached(
            broadcast_id, transcript_hash, provider="mistral",
            model=settings.llm_model, prompt_version=PROMPT_VERSION,
        )
        if cached and not force:
            return {
                "broadcast_id": str(broadcast_id), "status": "CACHED",
                "transcript_hash": transcript_hash,
                "topic_count": len(cached["brief"].get("topics", [])),
                "task_count": len(cached["brief"].get("tasks", [])),
                "api_requests": 0,
            }
        review_topics = build_broadcast_review(
            meeting,
            [item for item in snapshot["segments"] if item.get("is_final") is True],
        )
        fallback = build_fallback_meeting_brief(
            meeting, utterances, review_topics,
        )
        repository.save(
            broadcast_id,
            transcript_hash,
            int(snapshot.get("cursor") or 0),
            fallback,
            provider=FALLBACK_PROVIDER,
            model=FALLBACK_MODEL,
            prompt_version=FALLBACK_PROMPT_VERSION,
            usage_metadata={
                "api_requests": 0,
                "source": "DETERMINISTIC_BROADCAST_REVIEW",
            },
        )
        repository.save_progress(
            broadcast_id, transcript_hash, provider="mistral",
            model=settings.llm_model, prompt_version=PROMPT_VERSION,
            status="PROCESSING", phase="ANALYZING",
            total_utterances=len(utterances), processed_utterances=0,
            total_chunks=0, completed_chunks=0,
        )
        if repository.is_deferred(
            broadcast_id, transcript_hash, provider="mistral",
            model=settings.llm_model, prompt_version=PROMPT_VERSION,
        ) and not force:
            repository.save_progress(
                broadcast_id, transcript_hash, provider="mistral",
                model=settings.llm_model, prompt_version=PROMPT_VERSION,
                status="DEFERRED", phase="RETRY_WAIT",
                total_utterances=len(utterances), processed_utterances=0,
                total_chunks=0, completed_chunks=0,
            )
            return {
                "broadcast_id": str(broadcast_id), "status": "DEFERRED",
                "transcript_hash": transcript_hash, "api_requests": 0,
            }

    client = MistralMeetingBriefClient(
        settings.mistral_api_key, model=settings.llm_model,
        base_url=settings.mistral_base_url,
    )

    def check_monthly_budget() -> None:
        with connect(settings.database_url) as quota_connection:
            usage = SummaryRepository(quota_connection).monthly_token_usage(
                "mistral", settings.llm_model,
            )
            if mistral_budget_reached(
                usage, **mistral_budget_values(settings),
            ):
                raise MonthlyTokenLimitReached(
                    "Mistral monthly credit limit reached"
                )

    def record_token_usage(metadata: dict[str, Any]) -> None:
        with connect(settings.database_url) as quota_connection:
            SummaryRepository(quota_connection).record_monthly_token_usage(
                "mistral", settings.llm_model, metadata,
            )


    last_progress = {
        "status": "PROCESSING", "phase": "ANALYZING",
        "total_utterances": len(utterances), "processed_utterances": 0,
        "total_chunks": 0, "completed_chunks": 0,
    }

    def record_progress(progress: dict[str, Any]) -> None:
        nonlocal last_progress
        last_progress = dict(progress)
        with connect(settings.database_url) as progress_connection:
            MeetingBriefRepository(progress_connection).save_progress(
                broadcast_id, transcript_hash, provider="mistral",
                model=settings.llm_model, prompt_version=PROMPT_VERSION,
                **last_progress,
            )
    try:
        result = client.generate(
            meeting, utterances,
            before_request=check_monthly_budget,
            after_request=record_token_usage,
            on_progress=record_progress,
        )
    except MonthlyTokenLimitReached:
        record_progress({**last_progress, "status": "DEFERRED", "phase": "TOKEN_LIMIT"})
        raise
    except Exception as exc:
        record_progress({**last_progress, "status": "FAILED", "phase": "RETRY_WAIT"})
        with connect(settings.database_url) as connection:
            MeetingBriefRepository(connection).record_failure(
                broadcast_id, transcript_hash, provider="mistral",
                model=settings.llm_model, prompt_version=PROMPT_VERSION,
                error=type(exc).__name__,
            )
        raise
    with connect(settings.database_url) as connection:
        repository = MeetingBriefRepository(connection)
        saved = repository.save(
            broadcast_id, transcript_hash, int(snapshot.get("cursor") or 0),
            result.brief, provider="mistral", model=settings.llm_model,
            prompt_version=PROMPT_VERSION, usage_metadata=result.usage_metadata,
        )
        repository.clear_failure(
            broadcast_id, transcript_hash, provider="mistral",
            model=settings.llm_model, prompt_version=PROMPT_VERSION,
        )
    return {
        "broadcast_id": str(broadcast_id), "status": "GENERATED",
        "transcript_hash": transcript_hash,
        "headline": saved["brief"].get("headline"),
        "topic_count": len(saved["brief"].get("topics", [])),
        "task_count": len(saved["brief"].get("tasks", [])),
        "api_requests": result.api_requests,
    }


def eligible_broadcast_ids(limit: int = 5) -> list[UUID]:
    settings = get_settings()
    with connect(settings.database_url) as connection:
        rows = connection.execute(
            """
            SELECT broadcast.id FROM live_broadcasts broadcast
            WHERE (
                    (broadcast.institution = 'LEGISLATURE' AND broadcast.source_system = 'assembly.webcast.go.kr')
                    OR (broadcast.institution = 'EXECUTIVE' AND broadcast.source_system = 'ktv.go.kr')
                  )
              AND lifecycle_status = 'ENDED'
              AND ended_at >= now() - interval '30 days'
              AND EXISTS (
                  SELECT 1 FROM transcript_segments segment
                  WHERE segment.broadcast_id = broadcast.id AND segment.is_final = true
              )
              AND NOT EXISTS (
                  SELECT 1 FROM executive_audio_chunks audio
                  WHERE audio.broadcast_id = broadcast.id
                    AND audio.transcription_status <> 'TRANSCRIBED'
              )
              AND (
                  broadcast.institution <> 'EXECUTIVE'
                  OR (broadcast.capture_status = 'COMPLETED'
                      AND broadcast.ended_at <= now() - interval '2 minutes')
              )
            ORDER BY ended_at DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [row[0] for row in rows]


def process_available(limit: int = 5) -> list[dict[str, Any]]:
    results = []
    for broadcast_id in eligible_broadcast_ids(limit):
        try:
            results.append(generate_one(broadcast_id))
        except MonthlyTokenLimitReached:
            results.append({
                "broadcast_id": str(broadcast_id),
                "status": "MONTHLY_TOKEN_LIMIT",
            })
            break
        except Exception as exc:
            results.append({
                "broadcast_id": str(broadcast_id), "status": "FAILED",
                "error": type(exc).__name__,
            })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate evidence-backed meeting briefs for ended broadcasts"
    )
    parser.add_argument("--broadcast-id", type=UUID)
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--interval", type=float, default=60.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.limit <= 20:
        parser.error("limit must be between 1 and 20")
    if not 10 <= args.interval <= 3600:
        parser.error("interval must be between 10 and 3600 seconds")
    apply_migrations(get_settings().database_url)
    while True:
        output = [generate_one(args.broadcast_id, force=args.force)] if args.broadcast_id else process_available(args.limit)
        print(json.dumps({"event": "meeting_brief.run", "items": output}, ensure_ascii=False), flush=True)
        if args.once or args.broadcast_id:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
