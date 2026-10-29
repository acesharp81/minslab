from __future__ import annotations

from datetime import date
from typing import Any

from .summary_repository import token_usage_from_metadata


from .openai_daily_budget import DailyTokenLimitReached


class OpenAIGroupBudget:
    def __init__(self, connection: Any, group: str) -> None:
        if group not in {"mini", "main"}:
            raise ValueError("Unknown OpenAI budget group")
        self.group = group
        self.connection = connection

    def reserve(self, estimated_tokens: int, limit: int) -> date:
        if estimated_tokens < 1 or limit < 1:
            raise ValueError("token reservation and limit must be positive")
        row = self.connection.execute(
            """
            INSERT INTO openai_group_daily_usage (budget_group, usage_date, reserved_tokens)
            SELECT %s, timezone('UTC', now())::date, %s
            WHERE %s <= %s
            ON CONFLICT (budget_group, usage_date) DO UPDATE
            SET reserved_tokens = openai_group_daily_usage.reserved_tokens + %s,
                updated_at = now()
            WHERE openai_group_daily_usage.total_tokens
                + openai_group_daily_usage.unknown_tokens
                + openai_group_daily_usage.reserved_tokens + %s <= %s
            RETURNING usage_date
            """,
            (
                self.group, estimated_tokens, estimated_tokens, limit,
                estimated_tokens, estimated_tokens, limit,
            ),
        ).fetchone()
        if row is None:
            raise DailyTokenLimitReached("OpenAI UTC daily token limit reached")
        return row[0]

    def settle(
        self,
        usage_date: date,
        reserved_tokens: int,
        usage_metadata: dict[str, Any] | None,
    ) -> None:
        usage = token_usage_from_metadata(usage_metadata)
        known = bool(usage_metadata and (usage["total_tokens"] > 0 or usage_metadata.get("request_rejected")))
        updated = self.connection.execute(
            """
            UPDATE openai_group_daily_usage
            SET request_count = request_count + 1,
                input_tokens = input_tokens + %s,
                output_tokens = output_tokens + %s,
                total_tokens = total_tokens + %s,
                unknown_tokens = unknown_tokens + %s,
                reserved_tokens = reserved_tokens - %s,
                updated_at = now()
            WHERE budget_group = %s AND usage_date = %s AND reserved_tokens >= %s
            """,
            (
                usage["input_tokens"] if known else 0,
                usage["output_tokens"] if known else 0,
                usage["total_tokens"] if known else 0,
                0 if known else reserved_tokens,
                reserved_tokens, self.group, usage_date, reserved_tokens,
            ),
        )
        if updated.rowcount != 1:
            raise RuntimeError("OpenAI token reservation could not be settled")

    def today(self) -> dict[str, int]:
        row = self.connection.execute(
            """
            SELECT request_count, input_tokens, output_tokens, total_tokens,
                   unknown_tokens, reserved_tokens
            FROM openai_group_daily_usage
            WHERE budget_group = %s AND usage_date = timezone('UTC', now())::date
            """, (self.group,),
        ).fetchone()
        values = row or (0, 0, 0, 0, 0, 0)
        return dict(zip(
            ("request_count", "input_tokens", "output_tokens", "total_tokens",
             "unknown_tokens", "reserved_tokens"),
            (int(value) for value in values), strict=True,
        ))
