from __future__ import annotations

import argparse
import json
import time
from typing import Any

from ..services.summary_client import (
    SummaryClient,
    build_summary_client,
    summary_daily_limit,
    summary_mistral_prices,
    summary_monthly_credit_usd,
)
from ..services.summary_cache import (
    DailyRequestLimitReached,
    MonthlyTokenLimitReached,
    cache_missing_summaries,
)
from ..services.transcript_presentation import (
    apply_speaker_overrides,
    group_transcript_segments,
)


def closed_utterances(
    segments: list[dict[str, Any]], *, lifecycle_status: str
) -> list[dict[str, Any]]:
    utterances = group_transcript_segments(apply_speaker_overrides(segments, {}))
    if lifecycle_status == "LIVE":
        return [item for item in utterances[:-1] if item.get("is_final") is True]
    return utterances


def process_available(
    database_url: str,
    client: SummaryClient,
    *,
    daily_limit: int = 500,
    monthly_credit_usd: float = 10.0,
    input_usd_per_million: float = 0.15,
    output_usd_per_million: float = 0.60,
) -> dict[str, int | float]:
    from ..db.connection import connect
    from ..db.live_repository import LiveRepository

    with connect(database_url) as connection:
        rows = connection.execute(
            """
            SELECT id, lifecycle_status
            FROM live_broadcasts
            WHERE (
                    (institution = 'LEGISLATURE' AND source_system = 'assembly.webcast.go.kr')
                    OR (institution = 'EXECUTIVE' AND source_system = 'ktv.go.kr')
                  )
              AND (
                    lifecycle_status = 'LIVE'
                    OR (lifecycle_status = 'ENDED'
                        AND ended_at >= now() - interval '1 hour')
              )
            ORDER BY detected_at
            """
        ).fetchall()
    totals = {"broadcasts": 0, "eligible": 0, "cached": 0,
              "requested": 0, "saved": 0, "api_requests": 0,
              "daily_limit": (
                  min(int(daily_limit), 500)
                  if client.provider == "openrouter" else 0
              ),
              "daily_usage": 0,
              "monthly_credit_usd": (
                  float(monthly_credit_usd)
                  if client.provider == "mistral" else 0.0
              ),
              "monthly_cost_usd": 0.0,
              "monthly_tokens": 0}
    for broadcast_id, lifecycle_status in rows:
        with connect(database_url) as connection:
            segments = LiveRepository(connection).broadcast_transcript_snapshot(
                broadcast_id, lifecycle_status=lifecycle_status,
            )["segments"]
        prepared = [
            {**segment, "broadcast_id": broadcast_id}
            for segment in segments
        ]
        utterances = closed_utterances(prepared, lifecycle_status=lifecycle_status)
        with connect(database_url) as connection:
            stats = cache_missing_summaries(
                connection, broadcast_id, utterances, client,
                daily_limit=daily_limit,
                monthly_credit_usd=monthly_credit_usd,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            )
        totals["broadcasts"] += 1
        for key in ("eligible", "cached", "requested", "saved", "api_requests"):
            totals[key] += stats[key]
        totals["daily_usage"] = stats["daily_usage"]
        totals["monthly_tokens"] = stats["monthly_tokens"]
        totals["monthly_cost_usd"] = stats["monthly_cost_usd"]
    return totals


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
    daily_limit = summary_daily_limit(settings)
    monthly_credit_usd = summary_monthly_credit_usd(settings)
    input_price, output_price = summary_mistral_prices(settings)
    apply_migrations(settings.database_url)
    while True:
        try:
            result = process_available(
                settings.database_url, client,
                daily_limit=daily_limit,
                monthly_credit_usd=monthly_credit_usd,
                input_usd_per_million=input_price,
                output_usd_per_million=output_price,
            )
            if result["saved"] or result["api_requests"]:
                print(json.dumps({"event": "summary.cached", **result}), flush=True)
        except DailyRequestLimitReached:
            print(json.dumps({
                "event": "summary.daily_limit", "limit": min(daily_limit, 500),
            }), flush=True)
            if args.once:
                return
            time.sleep(3600)
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
