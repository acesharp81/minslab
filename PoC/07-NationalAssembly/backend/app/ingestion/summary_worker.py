from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime
from typing import Any

from ..domain.scope import NATIONAL_ASSEMBLY_BODIES, TARGET_COMMITTEES
from ..services.summary_cache import (
    DailyRequestLimitReached,
    MonthlyTokenLimitReached,
    cache_missing_summaries,
)
from ..services.summary_client import (
    SummaryClient,
    build_summary_client,
    summary_daily_limit,
    summary_mistral_prices,
    summary_monthly_credit_usd,
)
from ..services.transcript_presentation import (
    apply_speaker_overrides,
    group_transcript_segments,
)


def closed_utterances(
    segments: list[dict[str, Any]], *, lifecycle_status: str,
    include_stable_partial: bool = False, now: datetime | None = None,
) -> list[dict[str, Any]]:
    utterances = group_transcript_segments(apply_speaker_overrides(segments, {}))
    if include_stable_partial:
        from ..services.watch_lifecycle import closed_for_summary
        return closed_for_summary(utterances, lifecycle=lifecycle_status, now=now or datetime.now(UTC))
    if lifecycle_status == "LIVE":
        return [item for item in utterances[:-1] if item.get("is_final") is True]
    return utterances


def watch_summary_scope(utterances: list[dict[str, Any]], start_cursor: int) -> list[dict[str, Any]]:
    from ..services.summary_contract import CONTEXT_BEFORE_ITEMS

    first = next((i for i, u in enumerate(utterances)
                  if int(u["last_cursor"]) >= start_cursor), len(utterances))
    return utterances[max(0, first - CONTEXT_BEFORE_ITEMS):] if first < len(utterances) else []


def process_available(
    database_url: str,
    client: SummaryClient,
    *,
    daily_limit: int = 950,
    shared_pool: bool = False,
    monthly_credit_usd: float = 10.0,
    input_usd_per_million: float = 0.15,
    output_usd_per_million: float = 0.60,
) -> dict[str, int | float]:
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT id, lifecycle_status, EXISTS (
                SELECT 1 FROM watch_topic_episodes e JOIN watch_sessions s ON s.id=e.session_id
                WHERE s.broadcast_id=live_broadcasts.id AND e.status IN ('OPEN','WAITING')
            ) AS watched
            FROM live_broadcasts
            WHERE (
                    (institution = 'LEGISLATURE' AND source_system = 'assembly.webcast.go.kr')
                    OR (institution = 'EXECUTIVE' AND source_system = 'ktv.go.kr')
                  )
              AND (
                    lifecycle_status = 'LIVE'
                    OR (lifecycle_status = 'ENDED'
                        AND (ended_at >= now() - interval '1 hour' OR EXISTS (
                            SELECT 1 FROM watch_topic_episodes episode
                            JOIN watch_sessions session ON session.id=episode.session_id
                            WHERE session.broadcast_id=live_broadcasts.id
                              AND episode.status='WAITING'
                        )))
              )
              AND (
                    institution <> 'LEGISLATURE'
                    OR committee_name = ANY(%s)
                  )
            ORDER BY watched DESC, detected_at DESC
            """,
            ([*TARGET_COMMITTEES, *NATIONAL_ASSEMBLY_BODIES],),
        ).fetchall()
    totals = {"broadcasts": 0, "eligible": 0, "cached": 0,
              "requested": 0, "saved": 0, "api_requests": 0, "failed": 0, "deferred": 0,
              "daily_limit": (
                  min(int(daily_limit), 950)
                  if client.provider == "openrouter" else 0
              ),
              "daily_usage": 0,
              "monthly_credit_usd": (
                  float(monthly_credit_usd)
                  if client.provider == "mistral" else 0.0
              ),
              "monthly_cost_usd": 0.0,
              "monthly_tokens": 0}
    for broadcast_id, lifecycle_status, watched in rows:
        with connect(database_url) as connection:
            segments = LiveRepository(connection).broadcast_transcript_snapshot(
                broadcast_id, lifecycle_status=lifecycle_status,
            )["segments"]
        prepared = [
            {**segment, "broadcast_id": broadcast_id}
            for segment in segments
        ]
        utterances = closed_utterances(prepared, lifecycle_status=lifecycle_status,
                                      include_stable_partial=watched)
        with connect(database_url) as connection:
            # A recess closes the current turn even before another speaker appears.
            # Cache these boundary snapshots through the existing summary pipeline.
            from ..db.watch_lifecycle_repository import WatchLifecycleRepository
            boundaries = connection.execute(
                """SELECT DISTINCT b.cutoff_cursor FROM watch_meeting_boundaries b
                   JOIN watch_topic_episodes e ON e.boundary_id=b.id
                   WHERE b.broadcast_id=%s AND e.status='WAITING'""", (broadcast_id,),
            ).fetchall()
            for (cutoff,) in boundaries:
                utterances.extend(WatchLifecycleRepository(connection).utterances(broadcast_id, lifecycle_status, cutoff=cutoff))
            utterances = list({u['content_hash']: u for u in utterances}.values())
            if watched:
                first_detection = connection.execute(
                    """SELECT MIN(e.started_cursor) FROM watch_topic_episodes e
                       JOIN watch_sessions s ON s.id=e.session_id
                       JOIN watch_rules r ON r.id=s.rule_id
                       WHERE s.broadcast_id=%s AND e.status<>'CANCELED'
                         AND r.enabled AND e.rule_revision=r.current_revision""", (broadcast_id,),
                ).fetchone()[0]
                if first_detection is not None:
                    utterances = watch_summary_scope(utterances, int(first_detection))
            from ..db.summary_repository import SummaryRepository
            review_hashes = SummaryRepository(connection).task_review_hashes(
                broadcast_id, [u['content_hash'] for u in utterances])
            stats = cache_missing_summaries(
                connection, broadcast_id, utterances, client,
                include_short=watched, batch_items=2 if shared_pool else (8 if watched else 2),
                shared_pool=shared_pool,
                review_hashes=review_hashes,
                daily_limit=daily_limit,
                monthly_credit_usd=monthly_credit_usd,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            )
        totals["broadcasts"] += 1
        for key in ("eligible", "cached", "requested", "saved", "api_requests", "failed", "deferred"):
            totals[key] += stats[key]
        totals["daily_usage"] = stats["daily_usage"]
        totals["monthly_tokens"] = stats["monthly_tokens"]
        totals["monthly_cost_usd"] = stats["monthly_cost_usd"]
    return totals


OPENROUTER_HEAD_START_SECONDS = 1.0


def next_pool_tick(origin: float, interval: float, phase: float, now: float) -> float:
    """Next shared poll slot; skip missed slots rather than issuing catch-up calls."""
    first = origin + phase
    if now < first:
        return first
    return first + (math.floor((now - first) / interval) + 1) * interval


def run_pool_lane(settings, args, client, *, origin: float, phase: float) -> None:
    next_run = origin + phase
    while True:
        delay = next_run - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        failed = False
        try:
            result = process_available(settings.database_url, client,
                daily_limit=settings.openrouter_daily_limit, shared_pool=True)
            if result['api_requests'] or result['failed']:
                print(json.dumps({'event':'summary.pool','provider':client.provider,**result}),flush=True)
        except Exception as exc:
            failed = True
            print(json.dumps({'event':'summary.pool_deferred','provider':client.provider,
                              'error':type(exc).__name__}),flush=True)
        if args.once:
            return
        # A slow or unavailable provider never holds the other lane behind a barrier.
        # Keep the existing error cooldown and align the next poll to the shared grid.
        earliest = time.monotonic() + (60.0 if failed else 0.0)
        next_run = next_pool_tick(origin, args.interval, phase, earliest)


def run_grouped_pool(settings, args):
    """Independent lanes with OpenRouter one second ahead on every shared poll cycle."""
    from concurrent.futures import ThreadPoolExecutor
    from ..db.migrate import apply_migrations
    from ..services.openai_summary import OpenAISummaryClient
    from ..services.openrouter_summary import OpenRouterSummaryClient
    apply_migrations(settings.database_url)
    lanes = []
    if settings.openrouter_api_key:
        lanes.append((OpenRouterSummaryClient(settings.openrouter_api_key,
            model=settings.llm_model, base_url=settings.openrouter_base_url), 0.0))
    if settings.openai_api_key:
        phase = OPENROUTER_HEAD_START_SECONDS if settings.openrouter_api_key else 0.0
        lanes.append((OpenAISummaryClient(settings), phase))
    if not lanes:
        raise RuntimeError('No realtime model configured')
    origin = time.monotonic()
    print(json.dumps({'event':'summary.pool_schedule','interval_seconds':args.interval,
        'lanes':[{'provider':c.provider,'phase_seconds':p} for c,p in lanes]}),flush=True)
    with ThreadPoolExecutor(max_workers=len(lanes)) as executor:
        futures = [executor.submit(run_pool_lane, settings, args, c, origin=origin, phase=p)
                   for c,p in lanes]
        for future in futures:
            future.result()


def main() -> None:
    from ..config import get_settings
    from ..db.migrate import apply_migrations

    parser = argparse.ArgumentParser(
        description="Cache LLM summaries after each live speaker transition"
    )
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    if not 2 <= args.interval <= 300:
        parser.error("interval must be between 2 and 300 seconds")
    settings = get_settings()
    if not settings.ai_enrichment_enabled:
        raise RuntimeError("Summary generation is not enabled")
    client = build_summary_client(settings)
    if settings.model_workload_groups_enabled:
        run_grouped_pool(settings, args)
        return
    daily_limit = summary_daily_limit(settings)
    monthly_credit_usd = summary_monthly_credit_usd(settings)
    input_price, output_price = summary_mistral_prices(settings)
    apply_migrations(settings.database_url)
    last_report_at = 0.0
    while True:
        try:
            result = process_available(
                settings.database_url, client,
                daily_limit=daily_limit,
                monthly_credit_usd=monthly_credit_usd,
                input_usd_per_million=input_price,
                output_usd_per_million=output_price,
            )
            if (result["saved"] or result["api_requests"] or result["failed"]
                    or (result["deferred"] and time.monotonic() - last_report_at >= 300)):
                print(json.dumps({"event": "summary.cached", **result}), flush=True)
                last_report_at = time.monotonic()
        except DailyRequestLimitReached:
            print(json.dumps({
                "event": "summary.daily_limit", "limit": min(daily_limit, 950),
                "budget_source": "gateway" if settings.openrouter_gateway_status_url else "local",
            }), flush=True)
            if args.once:
                return
            # Recheck after central-state recovery; do not sleep for an hour
            # based on a stale or corrected budget decision.
            time.sleep(60)
            continue
        except MonthlyTokenLimitReached:
            print(json.dumps({
                "event": "summary.monthly_credit_limit",
                "limit_usd": monthly_credit_usd,
            }), flush=True)
            if args.once:
                return
            time.sleep(3600)
            continue
        except Exception as exc:
            print(json.dumps({
                "event": "summary.error", "error": type(exc).__name__
            }), flush=True)
            if args.once:
                return
            time.sleep(300)
            continue
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
