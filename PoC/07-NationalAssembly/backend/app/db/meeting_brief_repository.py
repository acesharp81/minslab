from __future__ import annotations

import uuid
from typing import Any, Iterable


class MeetingBriefRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def get_cached(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, transcript_hash, source_last_event_cursor,
                   provider, model, prompt_version, authority_status, review_status,
                   brief, usage_metadata, generated_at
            FROM meeting_briefs
            WHERE broadcast_id = %s AND transcript_hash = %s
              AND provider = %s AND model = %s AND prompt_version = %s
            ORDER BY generated_at DESC LIMIT 1
            """,
            (broadcast_id, transcript_hash, provider, model, prompt_version),
        ).fetchone()
        return self._row(row)

    def latest(self, broadcast_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT id, broadcast_id, transcript_hash, source_last_event_cursor,
                   provider, model, prompt_version, authority_status, review_status,
                   brief, usage_metadata, generated_at
            FROM meeting_briefs WHERE broadcast_id = %s
            ORDER BY (provider IN ('mistral', 'openrouter')) DESC,
                     generated_at DESC, id DESC LIMIT 1
            """,
            (broadcast_id,),
        ).fetchone()
        return self._row(row)

    def latest_map(self, broadcast_ids: Iterable[Any]) -> dict[Any, dict[str, Any]]:
        ids = list(broadcast_ids)
        if not ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (broadcast_id)
                   id, broadcast_id, transcript_hash, source_last_event_cursor,
                   provider, model, prompt_version, authority_status, review_status,
                   brief, usage_metadata, generated_at
            FROM meeting_briefs
            WHERE broadcast_id = ANY(%s)
            ORDER BY broadcast_id,
                     (provider IN ('mistral', 'openrouter')) DESC,
                     generated_at DESC, id DESC
            """,
            (ids,),
        ).fetchall()
        items = [self._row(row) for row in rows]
        return {item["broadcast_id"]: item for item in items if item}

    def latest_all(self) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (broadcast_id)
                   id, broadcast_id, transcript_hash, source_last_event_cursor,
                   provider, model, prompt_version, authority_status, review_status,
                   brief, usage_metadata, generated_at
            FROM meeting_briefs
            ORDER BY broadcast_id,
                     (provider IN ('mistral', 'openrouter')) DESC,
                     generated_at DESC, id DESC
            """
        ).fetchall()
        return [item for row in rows if (item := self._row(row))]

    def latest_summary_map(
        self, broadcast_ids: Iterable[Any],
    ) -> dict[Any, dict[str, Any]]:
        """Return list-card metadata without loading full report JSON documents."""
        ids = list(broadcast_ids)
        if not ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (broadcast_id)
                   id, broadcast_id, transcript_hash, source_last_event_cursor,
                   provider, model, prompt_version, authority_status, review_status,
                   jsonb_build_object(
                       'utterance_count', brief->'utterance_count'
                   ) AS brief,
                   '{}'::jsonb AS usage_metadata, generated_at
            FROM meeting_briefs
            WHERE broadcast_id = ANY(%s)
            ORDER BY broadcast_id,
                     (provider IN ('mistral', 'openrouter')) DESC,
                     generated_at DESC, id DESC
            """,
            (ids,),
        ).fetchall()
        items = [self._row(row) for row in rows]
        return {item["broadcast_id"]: item for item in items if item}

    def get_chunk_analysis(
        self,
        broadcast_id: Any,
        chunk_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT analysis FROM meeting_brief_chunk_cache
            WHERE broadcast_id = %s AND chunk_hash = %s AND provider = %s
              AND model = %s AND prompt_version = %s
            """,
            (broadcast_id, chunk_hash, provider, model, prompt_version),
        ).fetchone()
        return dict(row[0]) if row else None

    def save_chunk_analysis(
        self,
        broadcast_id: Any,
        chunk_hash: str,
        chunk_index: int,
        analysis: dict[str, Any],
        usage_metadata: dict[str, Any],
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> None:
        from psycopg.types.json import Jsonb

        self.connection.execute(
            """
            INSERT INTO meeting_brief_chunk_cache (
                broadcast_id, chunk_hash, provider, model, prompt_version,
                chunk_index, analysis, usage_metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id, chunk_hash, provider, model, prompt_version)
            DO UPDATE SET chunk_index = EXCLUDED.chunk_index,
                          analysis = EXCLUDED.analysis,
                          usage_metadata = EXCLUDED.usage_metadata,
                          created_at = now()
            """,
            (
                broadcast_id,
                chunk_hash,
                provider,
                model,
                prompt_version,
                chunk_index,
                Jsonb(analysis),
                Jsonb(usage_metadata),
            ),
        )

    def progress(self, broadcast_id: Any) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT progress.broadcast_id, progress.transcript_hash, progress.provider,
                   progress.model, progress.prompt_version, progress.status,
                   progress.phase, progress.total_utterances, progress.processed_utterances,
                   progress.total_chunks, progress.completed_chunks,
                   progress.started_at, progress.updated_at,
                   broadcast.source_last_event_cursor
                     AS current_source_last_event_cursor
            FROM meeting_brief_progress progress
            JOIN live_broadcasts broadcast ON broadcast.id = progress.broadcast_id
            WHERE progress.broadcast_id = %s
            """,
            (broadcast_id,),
        ).fetchone()
        return self._progress_row(row)

    def progress_map(self, broadcast_ids: Iterable[Any]) -> dict[Any, dict[str, Any]]:
        ids = list(broadcast_ids)
        if not ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT progress.broadcast_id, progress.transcript_hash, progress.provider,
                   progress.model, progress.prompt_version, progress.status,
                   progress.phase, progress.total_utterances, progress.processed_utterances,
                   progress.total_chunks, progress.completed_chunks,
                   progress.started_at, progress.updated_at,
                   broadcast.source_last_event_cursor
                     AS current_source_last_event_cursor
            FROM meeting_brief_progress progress
            JOIN live_broadcasts broadcast ON broadcast.id = progress.broadcast_id
            WHERE progress.broadcast_id = ANY(%s)
            """,
            (ids,),
        ).fetchall()
        items = [self._progress_row(row) for row in rows]
        return {item["broadcast_id"]: item for item in items if item}

    def save_progress(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        status: str,
        phase: str,
        total_utterances: int,
        processed_utterances: int,
        total_chunks: int,
        completed_chunks: int,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO meeting_brief_progress (
                broadcast_id, transcript_hash, provider, model, prompt_version,
                status, phase, total_utterances, processed_utterances,
                total_chunks, completed_chunks
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id) DO UPDATE SET
                transcript_hash = EXCLUDED.transcript_hash,
                provider = EXCLUDED.provider,
                model = EXCLUDED.model,
                prompt_version = EXCLUDED.prompt_version,
                status = EXCLUDED.status,
                phase = EXCLUDED.phase,
                total_utterances = EXCLUDED.total_utterances,
                processed_utterances = EXCLUDED.processed_utterances,
                total_chunks = EXCLUDED.total_chunks,
                completed_chunks = EXCLUDED.completed_chunks,
                started_at = CASE
                    WHEN meeting_brief_progress.transcript_hash <> EXCLUDED.transcript_hash
                    THEN now() ELSE meeting_brief_progress.started_at END,
                updated_at = now()
            RETURNING broadcast_id, transcript_hash, provider, model, prompt_version,
                      status, phase, total_utterances, processed_utterances,
                      total_chunks, completed_chunks, started_at, updated_at
            """,
            (
                broadcast_id,
                transcript_hash,
                provider,
                model,
                prompt_version,
                status,
                phase,
                total_utterances,
                processed_utterances,
                total_chunks,
                completed_chunks,
            ),
        ).fetchone()
        item = self._progress_row(row)
        if item is None:
            raise RuntimeError("meeting brief progress was not saved")
        return item

    def save(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        source_last_event_cursor: int,
        brief: dict[str, Any],
        *,
        provider: str,
        model: str,
        prompt_version: str,
        usage_metadata: dict[str, Any],
    ) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        row = self.connection.execute(
            """
            INSERT INTO meeting_briefs (
                id, broadcast_id, transcript_hash, source_last_event_cursor,
                provider, model, prompt_version, brief, usage_metadata
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (broadcast_id, transcript_hash, provider, model, prompt_version)
            DO UPDATE SET usage_metadata = meeting_briefs.usage_metadata
            RETURNING id, broadcast_id, transcript_hash, source_last_event_cursor,
                      provider, model, prompt_version, authority_status, review_status,
                      brief, usage_metadata, generated_at
            """,
            (
                uuid.uuid4(),
                broadcast_id,
                transcript_hash,
                source_last_event_cursor,
                provider,
                model,
                prompt_version,
                Jsonb(brief),
                Jsonb(usage_metadata),
            ),
        ).fetchone()
        item = self._row(row)
        if item is None:
            raise RuntimeError("meeting brief was not saved")
        return item

    def update_brief(self, brief_id: Any, brief: dict[str, Any]) -> dict[str, Any]:
        from psycopg.types.json import Jsonb

        row = self.connection.execute(
            """
            UPDATE meeting_briefs SET brief = %s
            WHERE id = %s
            RETURNING id, broadcast_id, transcript_hash, source_last_event_cursor,
                      provider, model, prompt_version, authority_status, review_status,
                      brief, usage_metadata, generated_at
            """,
            (Jsonb(brief), brief_id),
        ).fetchone()
        item = self._row(row)
        if item is None:
            raise RuntimeError("meeting brief was not updated")
        return item

    def is_deferred(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> bool:
        return bool(
            self.connection.execute(
                """
            SELECT 1 FROM meeting_brief_failures
            WHERE broadcast_id = %s AND transcript_hash = %s AND provider = %s
              AND model = %s AND prompt_version = %s AND retry_after > now()
            """,
                (broadcast_id, transcript_hash, provider, model, prompt_version),
            ).fetchone()
        )

    def record_failure(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        error: str,
        retry_hours: int = 6,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO meeting_brief_failures (
                broadcast_id, transcript_hash, provider, model, prompt_version,
                attempts, last_error, retry_after
            ) VALUES (%s, %s, %s, %s, %s, 1, %s,
                      now() + (%s * interval '1 hour'))
            ON CONFLICT (broadcast_id, transcript_hash, provider, model, prompt_version)
            DO UPDATE SET attempts = meeting_brief_failures.attempts + 1,
                          last_error = EXCLUDED.last_error,
                          retry_after = EXCLUDED.retry_after, updated_at = now()
            """,
            (
                broadcast_id,
                transcript_hash,
                provider,
                model,
                prompt_version,
                error[:300],
                retry_hours,
            ),
        )

    def clear_failure(
        self,
        broadcast_id: Any,
        transcript_hash: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> None:
        self.connection.execute(
            """
            DELETE FROM meeting_brief_failures
            WHERE broadcast_id = %s AND transcript_hash = %s AND provider = %s
              AND model = %s AND prompt_version = %s
            """,
            (broadcast_id, transcript_hash, provider, model, prompt_version),
        )

    def evidence_ids(
        self,
        brief: dict[str, Any],
        entity_type: str,
        entity_id: str,
    ) -> list[str]:
        payload = brief.get("brief") or {}
        if entity_type == "topic":
            entities = payload.get("topics", [])
        elif entity_type == "task":
            entities = payload.get("tasks", [])
        elif entity_type == "live_topic_cluster":
            for cluster in (payload.get("live_topic_lineage") or {}).get(
                "clusters", []
            ):
                if cluster.get("id") == entity_id:
                    return [str(value) for value in cluster.get("utterance_ids", [])]
            return []
        elif entity_type == "speaker":
            entities = [
                point
                for topic in payload.get("topics", [])
                for point in topic.get("speaker_points", [])
            ]
        else:
            return []
        for entity in entities:
            if entity.get("id") == entity_id:
                return [str(value) for value in entity.get("evidence_ids", [])]
        return []

    @staticmethod
    def _row(row: Any) -> dict[str, Any] | None:
        if not row:
            return None
        columns = (
            "brief_id",
            "broadcast_id",
            "transcript_hash",
            "source_last_event_cursor",
            "provider",
            "model",
            "prompt_version",
            "authority_status",
            "review_status",
            "brief",
            "usage_metadata",
            "generated_at",
        )
        return dict(zip(columns, row, strict=True))

    @staticmethod
    def _progress_row(row: Any) -> dict[str, Any] | None:
        if not row:
            return None
        columns = (
            "broadcast_id",
            "transcript_hash",
            "provider",
            "model",
            "prompt_version",
            "status",
            "phase",
            "total_utterances",
            "processed_utterances",
            "total_chunks",
            "completed_chunks",
            "started_at",
            "updated_at",
        )
        if len(row) == len(columns) + 1:
            columns += ("current_source_last_event_cursor",)
        return dict(zip(columns, row, strict=True))
