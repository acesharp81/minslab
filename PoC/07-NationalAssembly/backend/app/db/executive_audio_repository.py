from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


class ExecutiveAudioRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def next_chunk_number(self, broadcast_id: uuid.UUID) -> int:
        row = self.connection.execute(
            "SELECT COALESCE(MAX(chunk_number), -1) + 1 FROM executive_audio_chunks WHERE broadcast_id = %s",
            (broadcast_id,),
        ).fetchone()
        return int(row[0])

    def save_captured(
        self, broadcast_id: uuid.UUID, chunk_number: int, *,
        content_hash: str, raw_path: Path, captured_at: datetime, duration_ms: int,
    ) -> uuid.UUID:
        row = self.connection.execute(
            """
            INSERT INTO executive_audio_chunks (
                id, broadcast_id, chunk_number, content_hash, raw_path,
                captured_at, duration_ms
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id, content_hash) DO UPDATE
            SET raw_path = EXCLUDED.raw_path, updated_at = now()
            RETURNING id
            """,
            (
                uuid.uuid4(), broadcast_id, chunk_number, content_hash,
                str(raw_path), captured_at, duration_ms,
            ),
        ).fetchone()
        return row[0]

    def claim_pending(self, broadcast_id: uuid.UUID) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            WITH candidate AS (
                SELECT chunk.id,
                       COALESCE((
                           SELECT SUM(previous.duration_ms)
                           FROM executive_audio_chunks previous
                           WHERE previous.broadcast_id = chunk.broadcast_id
                             AND previous.chunk_number < chunk.chunk_number
                       ), 0) AS start_offset_ms
                FROM executive_audio_chunks chunk
                WHERE chunk.broadcast_id = %s
                  AND chunk.transcription_status IN ('CAPTURED', 'FAILED', 'PROCESSING')
                  AND chunk.attempts < 4
                ORDER BY chunk.chunk_number
                FOR UPDATE SKIP LOCKED LIMIT 1
            )
            UPDATE executive_audio_chunks chunk
            SET transcription_status = 'PROCESSING', attempts = attempts + 1,
                error_type = NULL, updated_at = now()
            FROM candidate WHERE chunk.id = candidate.id
            RETURNING chunk.id, chunk.broadcast_id, chunk.chunk_number,
                      chunk.content_hash, chunk.raw_path, chunk.captured_at,
                      chunk.duration_ms, candidate.start_offset_ms
            """,
            (broadcast_id,),
        ).fetchone()
        if not row:
            return None
        return dict(zip(
            (
                "chunk_id", "broadcast_id", "chunk_number", "content_hash",
                "raw_path", "captured_at", "duration_ms", "start_offset_ms",
            ),
            row,
            strict=True,
        ))

    def complete(
        self, chunk_id: uuid.UUID, *, provider: str, model: str,
        transcript_payload: dict[str, Any], usage_metadata: dict[str, Any],
    ) -> None:
        from psycopg.types.json import Jsonb

        self.connection.execute(
            """
            UPDATE executive_audio_chunks
            SET transcription_status = 'TRANSCRIBED', provider = %s, model = %s,
                transcript_payload = %s, usage_metadata = %s,
                error_type = NULL, updated_at = now()
            WHERE id = %s
            """,
            (provider, model, Jsonb(transcript_payload), Jsonb(usage_metadata), chunk_id),
        )

    def fail(self, chunk_id: uuid.UUID, error_type: str) -> None:
        self.connection.execute(
            """
            UPDATE executive_audio_chunks
            SET transcription_status = 'FAILED', error_type = %s, updated_at = now()
            WHERE id = %s
            """,
            (error_type[:120], chunk_id),
        )

    def record_usage(
        self, *, provider: str, request_id: str, model: str,
        audio_seconds: float, cost_usd: float,
    ) -> bool:
        row = self.connection.execute(
            """
            INSERT INTO audio_usage_events (
                provider, request_id, model, usage_month, audio_seconds, cost_usd
            ) VALUES (%s, %s, %s, date_trunc('month', now())::date, %s, %s)
            ON CONFLICT (provider, request_id) DO NOTHING
            RETURNING request_id
            """,
            (provider, request_id, model, audio_seconds, cost_usd),
        ).fetchone()
        return row is not None

    def monthly_usage(self, provider: str = "mistral") -> dict[str, float | int]:
        row = self.connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(audio_seconds), 0), COALESCE(SUM(cost_usd), 0)
            FROM audio_usage_events
            WHERE provider = %s
              AND usage_month = date_trunc('month', now())::date
            """,
            (provider,),
        ).fetchone()
        return {
            "request_count": int(row[0]),
            "audio_seconds": float(row[1]),
            "cost_usd": float(row[2]),
        }
