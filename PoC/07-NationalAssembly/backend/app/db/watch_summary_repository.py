from __future__ import annotations

import hashlib
import uuid
from typing import Any

from psycopg.types.json import Jsonb


class WatchSummaryRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def candidate_session(
        self, *, min_new_matches: int, debounce_seconds: int,
        max_updates: int, provider: str, model: str, prompt_version: str,
    ) -> uuid.UUID | None:
        row = self.connection.execute(
            """
            SELECT session.id
            FROM watch_sessions session
            JOIN live_broadcasts broadcast ON broadcast.id = session.broadcast_id
            JOIN watch_matches match ON match.session_id = session.id
            LEFT JOIN LATERAL (
                SELECT version.evidence_match_ids, version.created_at
                FROM watch_summary_versions version
                WHERE version.session_id = session.id AND version.status = 'READY'
                  AND version.provider = %s AND version.model = %s
                  AND version.prompt_version = %s
                ORDER BY version.created_at DESC LIMIT 1
            ) latest ON true
            WHERE session.report_summary_requested_at IS NOT NULL
              AND session.updated_at <= now() - (%s * interval '1 second')
              AND session.last_matched_at >= now() - interval '24 hours'
              AND broadcast.source_system NOT IN (
                'poc07.demo', 'poc07.test', 'poc07.replay.local', 'poc07.replay.kakao'
              )
              AND NOT EXISTS (
                SELECT 1 FROM watch_summary_versions pending
                WHERE pending.session_id = session.id AND pending.status = 'PENDING'
                  AND pending.provider = %s AND pending.model = %s
                  AND pending.prompt_version = %s
              )
              AND NOT EXISTS (
                SELECT 1 FROM watch_summary_versions delayed
                WHERE delayed.session_id = session.id
                  AND delayed.provider = %s AND delayed.model = %s
                  AND delayed.prompt_version = %s
                  AND delayed.status IN ('FAILED', 'LIMIT_REACHED')
                  AND delayed.retry_after > now()
              )
              AND (
                SELECT COUNT(*) FROM watch_summary_versions version
                WHERE version.session_id = session.id
                  AND version.provider = %s AND version.model = %s
                  AND version.prompt_version = %s
                  AND version.status IN ('READY', 'PENDING')
              ) < %s
            GROUP BY session.id, broadcast.lifecycle_status,
                     latest.evidence_match_ids, latest.created_at
            HAVING COUNT(match.id) - COALESCE(cardinality(latest.evidence_match_ids), 0) >= %s
            ORDER BY (broadcast.lifecycle_status = 'LIVE') DESC,
                     session.updated_at DESC, session.id DESC
            LIMIT 1
            """,
            (
                provider, model, prompt_version, debounce_seconds,
                provider, model, prompt_version,
                provider, model, prompt_version,
                provider, model, prompt_version, max_updates, min_new_matches,
            ),
        ).fetchone()
        return row[0] if row else None

    def clear_request(self, session_id: uuid.UUID) -> None:
        self.connection.execute(
            "UPDATE watch_sessions SET report_summary_requested_at = NULL WHERE id = %s",
            (session_id,),
        )

    def evidence(self, session_id: uuid.UUID) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT id, speaker_label, excerpt, matched_term, matched_at
            FROM watch_matches WHERE session_id = %s ORDER BY matched_at, id
            """,
            (session_id,),
        ).fetchall()
        columns = ("match_id", "speaker_label", "excerpt", "matched_term", "matched_at")
        return [dict(zip(columns, row, strict=True)) for row in rows]

    @staticmethod
    def evidence_hash(evidence: list[dict[str, Any]]) -> str:
        source = "|".join(str(item["match_id"]) for item in evidence)
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def claim(
        self, session_id: uuid.UUID, evidence: list[dict[str, Any]], *,
        provider: str, model: str, prompt_version: str,
    ) -> uuid.UUID | None:
        update_number = int(self.connection.execute(
            "SELECT COUNT(*) + 1 FROM watch_summary_versions WHERE session_id = %s",
            (session_id,),
        ).fetchone()[0])
        row = self.connection.execute(
            """
            INSERT INTO watch_summary_versions (
                id, session_id, evidence_set_hash, status, evidence_match_ids,
                provider, model, prompt_version, update_number
            ) VALUES (%s, %s, %s, 'PENDING', %s, %s, %s, %s, %s)
            ON CONFLICT (
                session_id, evidence_set_hash, provider, model, prompt_version
            ) DO UPDATE SET
                status = 'PENDING', last_error = NULL, retry_after = NULL,
                updated_at = now()
            WHERE watch_summary_versions.status IN ('FAILED', 'LIMIT_REACHED')
              AND watch_summary_versions.retry_after <= now()
            RETURNING id
            """,
            (
                uuid.uuid4(), session_id, self.evidence_hash(evidence),
                [item["match_id"] for item in evidence], provider, model,
                prompt_version, update_number,
            ),
        ).fetchone()
        return row[0] if row else None

    def complete(
        self, version_id: uuid.UUID, *, summary: str, claims: list[dict[str, Any]],
        input_tokens: int, output_tokens: int, cost_usd: float,
    ) -> None:
        self.connection.execute(
            """
            UPDATE watch_summary_versions SET status = 'READY', summary = %s,
                   claims = %s, input_tokens = %s, output_tokens = %s,
                   cost_usd = %s, last_error = NULL, retry_after = NULL,
                   updated_at = now() WHERE id = %s
            """,
            (summary, Jsonb(claims), input_tokens, output_tokens, cost_usd, version_id),
        )

    def fail(self, version_id: uuid.UUID, error: str) -> None:
        self.connection.execute(
            """
            UPDATE watch_summary_versions SET status = 'FAILED', last_error = %s,
                   retry_after = now() + interval '1 hour', updated_at = now()
            WHERE id = %s
            """,
            (error[:240], version_id),
        )

    def limit_daily(self, version_id: uuid.UUID, reason: str) -> None:
        self.connection.execute(
            """
            UPDATE watch_summary_versions SET status = 'LIMIT_REACHED',
                   last_error = %s,
                   retry_after = date_trunc('day', now()) + interval '1 day',
                   updated_at = now() WHERE id = %s
            """,
            (reason[:240], version_id),
        )

    def limit(self, version_id: uuid.UUID, reason: str) -> None:
        self.connection.execute(
            """
            UPDATE watch_summary_versions SET status = 'LIMIT_REACHED',
                   last_error = %s,
                   retry_after = date_trunc('month', now()) + interval '1 month',
                   updated_at = now() WHERE id = %s
            """,
            (reason[:240], version_id),
        )

    def monthly_cost(self) -> float:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(cost_usd), 0) FROM watch_summary_versions
            WHERE created_at >= date_trunc('month', now()) AND status = 'READY'
            """
        ).fetchone()
        return float(row[0])
