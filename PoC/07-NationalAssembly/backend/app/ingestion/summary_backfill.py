from __future__ import annotations

import argparse
import json
from uuid import UUID

from ..config import get_settings
from ..db.connection import connect
from ..db.migrate import apply_migrations
from ..db.live_repository import LiveRepository
from ..services.summary_client import (
    build_summary_client,
    summary_daily_limit,
    summary_mistral_prices,
    summary_monthly_credit_usd,
)
from ..services.summary_cache import cache_missing_summaries
from ..services.transcript_presentation import (
    apply_speaker_overrides,
    group_transcript_segments,
)


def backfill_one(broadcast_id: UUID) -> dict[str, object]:
    settings = get_settings()
    client = build_summary_client(settings)
    with connect(settings.database_url) as connection:
        broadcast = connection.execute(
            """
            SELECT id, title FROM live_broadcasts
            WHERE id = %s AND source_system = 'assembly.webcast.go.kr'
              AND lifecycle_status = 'ENDED'
            """,
            (broadcast_id,),
        ).fetchone()
        if not broadcast:
            raise ValueError("eligible ended broadcast not found")
        segments = LiveRepository(connection).ended_transcript_snapshot(
            broadcast_id
        )["segments"]
    presented = apply_speaker_overrides(
        [{**segment, "broadcast_id": broadcast_id} for segment in segments],
        {},
    )
    utterances = group_transcript_segments(presented)
    input_price, output_price = summary_mistral_prices(settings)
    with connect(settings.database_url) as connection:
        stats = cache_missing_summaries(
            connection, broadcast_id, utterances, client,
            daily_limit=summary_daily_limit(settings),
            monthly_credit_usd=summary_monthly_credit_usd(settings),
            input_usd_per_million=input_price,
            output_usd_per_million=output_price,
        )
    return {
        "broadcast_id": str(broadcast_id),
        "title": broadcast[1],
        "utterances": len(utterances),
        **stats,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cache LLM summaries for one ended broadcast"
    )
    parser.add_argument("--broadcast-id", type=UUID, required=True)
    args = parser.parse_args()
    apply_migrations(get_settings().database_url)
    print(json.dumps(backfill_one(args.broadcast_id), ensure_ascii=False))


if __name__ == "__main__":
    main()
