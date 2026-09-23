from __future__ import annotations

import uuid
from typing import Any, Iterable


def token_usage_from_metadata(metadata: dict[str, Any] | None) -> dict[str, int]:
    usage = (metadata or {}).get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = max(0, int(
        usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    ))
    output_tokens = max(0, int(
        usage.get("completion_tokens") or usage.get("output_tokens") or 0
    ))
    total_tokens = max(0, int(
        usage.get("total_tokens") or input_tokens + output_tokens
    ))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


class SummaryRepository:
    def __init__(self, connection: Any):
        self.connection = connection

    def summary_map(
        self,
        broadcast_ids: Iterable[Any],
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> dict[tuple[Any, str], dict[str, Any]]:
        ids = list(broadcast_ids)
        if not ids:
            return {}
        rows = self.connection.execute(
            """
            SELECT DISTINCT ON (broadcast_id, content_hash)
                   broadcast_id, content_hash, summary, provider, model,
                   prompt_version, live_insight, created_at
            FROM transcript_utterance_summaries
            WHERE broadcast_id = ANY(%s)
            ORDER BY broadcast_id, content_hash,
                     (prompt_version = %s) DESC,
                     (provider = %s AND model = %s) DESC, created_at DESC
            """,
            (ids, prompt_version, provider, model),
        ).fetchall()
        columns = (
            "broadcast_id", "content_hash", "summary", "provider", "model",
            "prompt_version", "live_insight", "created_at",
        )
        items = [dict(zip(columns, row, strict=True)) for row in rows]
        return {(item["broadcast_id"], item["content_hash"]): item for item in items}

    def existing_hashes(
        self,
        broadcast_id: Any,
        content_hashes: Iterable[str],
        *,
        provider: str,
        model: str,
        prompt_version: str,
    ) -> set[str]:
        del provider, model, prompt_version
        hashes = list(content_hashes)
        if not hashes:
            return set()
        rows = self.connection.execute(
            """
            SELECT DISTINCT content_hash FROM transcript_utterance_summaries
            WHERE broadcast_id = %s AND content_hash = ANY(%s)
            """,
            (broadcast_id, hashes),
        ).fetchall()
        return {row[0] for row in rows}

    def reserve_daily_request(self, provider: str, limit: int) -> int | None:
        if provider != "openrouter":
            raise ValueError(
                "daily request quota is reserved for OpenRouter only"
            )
        row = self.connection.execute(
            """
            INSERT INTO llm_provider_daily_usage (
                provider, usage_date, request_count
            ) VALUES (%s, timezone('UTC', now())::date, 1)
            ON CONFLICT (provider, usage_date) DO UPDATE
            SET request_count = llm_provider_daily_usage.request_count + 1,
                updated_at = now()
            WHERE llm_provider_daily_usage.request_count < %s
            RETURNING request_count
            """,
            (provider, limit),
        ).fetchone()
        return int(row[0]) if row else None

    def daily_usage(self, provider: str) -> int:
        row = self.connection.execute(
            """
            SELECT request_count FROM llm_provider_daily_usage
            WHERE provider = %s AND usage_date = timezone('UTC', now())::date
            """,
            (provider,),
        ).fetchone()
        return int(row[0]) if row else 0

    def monthly_token_usage(self, provider: str, model: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT request_count, input_tokens, output_tokens, total_tokens
            FROM llm_provider_monthly_token_usage
            WHERE provider = %s AND model = %s
              AND usage_month = date_trunc(
                  'month', timezone('UTC', now())
              )::date
            """,
            (provider, model),
        ).fetchone()
        values = row or (0, 0, 0, 0)
        result = dict(zip(
            ("request_count", "input_tokens", "output_tokens", "total_tokens"),
            (int(value) for value in values),
            strict=True,
        ))
        audio = self.connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(audio_seconds), 0), COALESCE(SUM(cost_usd), 0)
            FROM audio_usage_events
            WHERE provider = %s
              AND usage_month = date_trunc('month', now())::date
            """,
            (provider,),
        ).fetchone()
        result.update({
            "audio_request_count": int(audio[0]),
            "audio_seconds": float(audio[1]),
            "audio_cost_usd": float(audio[2]),
        })
        return result

    def monthly_provider_usage(self, provider: str) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT COALESCE(SUM(request_count), 0),
                   COALESCE(SUM(input_tokens), 0),
                   COALESCE(SUM(output_tokens), 0),
                   COALESCE(SUM(total_tokens), 0)
            FROM llm_provider_monthly_token_usage
            WHERE provider = %s
              AND usage_month = date_trunc('month', timezone('UTC', now()))::date
            """,
            (provider,),
        ).fetchone()
        result = dict(zip(
            ("request_count", "input_tokens", "output_tokens", "total_tokens"),
            (int(value) for value in (row or (0, 0, 0, 0))), strict=True,
        ))
        audio = self.connection.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(audio_seconds), 0), COALESCE(SUM(cost_usd), 0)
            FROM audio_usage_events
            WHERE provider = %s
              AND usage_month = date_trunc('month', now())::date
            """,
            (provider,),
        ).fetchone()
        result.update({
            "audio_request_count": int(audio[0]),
            "audio_seconds": float(audio[1]),
            "audio_cost_usd": float(audio[2]),
        })
        return result

    def monthly_model_usage(self) -> list[dict[str, Any]]:
        usage: dict[tuple[str, str], dict[str, Any]] = {}
        token_rows = self.connection.execute(
            """
            SELECT provider, model, request_count,
                   input_tokens, output_tokens, total_tokens
            FROM llm_provider_monthly_token_usage
            WHERE usage_month = date_trunc(
                'month', timezone('UTC', now())
            )::date
            """
        ).fetchall()
        for row in token_rows:
            key = (str(row[0]), str(row[1]))
            usage[key] = {
                "provider": key[0],
                "model": key[1],
                "request_count": int(row[2]),
                "input_tokens": int(row[3]),
                "output_tokens": int(row[4]),
                "total_tokens": int(row[5]),
                "audio_request_count": 0,
                "audio_seconds": 0.0,
                "audio_cost_usd": 0.0,
            }
        audio_rows = self.connection.execute(
            """
            SELECT provider, model, COUNT(*),
                   COALESCE(SUM(audio_seconds), 0),
                   COALESCE(SUM(cost_usd), 0)
            FROM audio_usage_events
            WHERE usage_month = date_trunc('month', now())::date
            GROUP BY provider, model
            """
        ).fetchall()
        for row in audio_rows:
            key = (str(row[0]), str(row[1]))
            item = usage.setdefault(key, {
                "provider": key[0],
                "model": key[1],
                "request_count": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "audio_request_count": 0,
                "audio_seconds": 0.0,
                "audio_cost_usd": 0.0,
            })
            item["audio_request_count"] = int(row[2])
            item["audio_seconds"] = float(row[3])
            item["audio_cost_usd"] = float(row[4])
        return sorted(
            usage.values(),
            key=lambda item: (
                str(item["provider"]),
                -int(item["request_count"])
                - int(item["audio_request_count"]),
                str(item["model"]),
            ),
        )

    def record_monthly_token_usage(
        self, provider: str, model: str,
        usage_metadata: dict[str, Any] | None,
    ) -> dict[str, int]:
        usage = token_usage_from_metadata(usage_metadata)
        request_id = str((usage_metadata or {}).get("request_id") or "").strip()
        if not request_id:
            raise ValueError("provider usage metadata is missing request_id")
        event = self.connection.execute(
            """
            INSERT INTO llm_provider_token_usage_events (
                provider, request_id, model, usage_month,
                input_tokens, output_tokens, total_tokens
            ) VALUES (
                %s, %s, %s,
                date_trunc('month', timezone('UTC', now()))::date,
                %s, %s, %s
            )
            ON CONFLICT (provider, request_id) DO NOTHING
            RETURNING request_id
            """,
            (
                provider, request_id, model, usage["input_tokens"],
                usage["output_tokens"], usage["total_tokens"],
            ),
        ).fetchone()
        if event is None:
            return self.monthly_token_usage(provider, model)
        row = self.connection.execute(
            """
            INSERT INTO llm_provider_monthly_token_usage (
                provider, model, usage_month, request_count,
                input_tokens, output_tokens, total_tokens
            ) VALUES (
                %s, %s,
                date_trunc('month', timezone('UTC', now()))::date,
                1, %s, %s, %s
            )
            ON CONFLICT (provider, model, usage_month) DO UPDATE
            SET request_count =
                    llm_provider_monthly_token_usage.request_count + 1,
                input_tokens =
                    llm_provider_monthly_token_usage.input_tokens
                    + EXCLUDED.input_tokens,
                output_tokens =
                    llm_provider_monthly_token_usage.output_tokens
                    + EXCLUDED.output_tokens,
                total_tokens =
                    llm_provider_monthly_token_usage.total_tokens
                    + EXCLUDED.total_tokens,
                updated_at = now()
            RETURNING request_count, input_tokens, output_tokens, total_tokens
            """,
            (
                provider, model, usage["input_tokens"],
                usage["output_tokens"], usage["total_tokens"],
            ),
        ).fetchone()
        return dict(zip(
            ("request_count", "input_tokens", "output_tokens", "total_tokens"),
            (int(value) for value in row),
            strict=True,
        ))

    def deferred_hashes(self, broadcast_id: Any, content_hashes: Iterable[str], *, provider: str, model: str, prompt_version: str) -> set[str]:
        hashes = list(content_hashes)
        if not hashes:
            return set()
        rows = self.connection.execute(
            """SELECT content_hash FROM transcript_utterance_summary_failures
               WHERE broadcast_id = %s AND content_hash = ANY(%s)
                 AND provider = %s AND model = %s AND prompt_version = %s
                 AND retry_after > now()""",
            (broadcast_id, hashes, provider, model, prompt_version),
        ).fetchall()
        return {row[0] for row in rows}

    def record_failure(self, broadcast_id: Any, content_hash: str, *, provider: str, model: str, prompt_version: str, error: str, retry_hours: int = 24) -> None:
        self.connection.execute(
            """INSERT INTO transcript_utterance_summary_failures (
                   broadcast_id, content_hash, provider, model, prompt_version,
                   attempts, last_error, retry_after)
               VALUES (%s, %s, %s, %s, %s, 1, %s,
                       now() + (%s * interval '1 hour'))
               ON CONFLICT (broadcast_id, content_hash, provider, model, prompt_version)
               DO UPDATE SET attempts = transcript_utterance_summary_failures.attempts + 1,
                   last_error = EXCLUDED.last_error, retry_after = EXCLUDED.retry_after,
                   updated_at = now()""",
            (broadcast_id, content_hash, provider, model, prompt_version, error[:300], retry_hours),
        )

    def save_many(
        self,
        broadcast_id: Any,
        items: Iterable[dict[str, Any]],
        *,
        provider: str,
        model: str,
        prompt_version: str,
        usage_metadata: dict[str, Any] | None = None,
    ) -> int:
        from psycopg.types.json import Jsonb

        saved = 0
        for item in items:
            row = self.connection.execute(
                """
                INSERT INTO transcript_utterance_summaries (
                    id, broadcast_id, source_speaker_label, content_hash, summary,
                    provider, model, prompt_version, original_char_count,
                    segment_count, usage_metadata, live_insight
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (broadcast_id, content_hash, provider, model, prompt_version)
                DO NOTHING RETURNING id
                """,
                (
                    uuid.uuid4(), broadcast_id, item["source_speaker_label"],
                    item["content_hash"], item["summary"], provider, model,
                    prompt_version, item["original_char_count"],
                    item["segment_count"], Jsonb(usage_metadata or {}),
                    Jsonb(item.get("live_insight") or {}),
                ),
            ).fetchone()
            saved += int(row is not None)
        return saved

    def count_for_broadcast(self, broadcast_id: Any) -> int:
        return int(self.connection.execute(
            "SELECT COUNT(*) FROM transcript_utterance_summaries WHERE broadcast_id = %s",
            (broadcast_id,),
        ).fetchone()[0])
