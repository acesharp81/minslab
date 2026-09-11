from __future__ import annotations

import time
from typing import Any

import requests

from ..db.summary_repository import SummaryRepository
from .mistral_budget import (
    DEFAULT_INPUT_USD_PER_MILLION,
    DEFAULT_MONTHLY_CREDIT_USD,
    DEFAULT_OUTPUT_USD_PER_MILLION,
    mistral_budget_reached,
    mistral_usage_cost_usd,
)
from .summary_contract import (
    MAX_SUMMARY_CHARS,
    add_conversation_context,
    iter_summary_batches,
)
from .summary_client import SummaryClient

HARD_DAILY_REQUEST_LIMIT = 950
MIN_REQUEST_INTERVAL_SECONDS = 3.5
MAX_QUOTA_COUNTED_ATTEMPTS = 3
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class DailyRequestLimitReached(RuntimeError):
    pass


class MonthlyTokenLimitReached(RuntimeError):
    pass


def _summarize_with_reserved_attempts(connection: Any, repository: SummaryRepository,
        client: SummaryClient, batch: list[dict[str, Any]], daily_limit: int,
        monthly_credit_usd: float, input_usd_per_million: float,
        output_usd_per_million: float) -> tuple[Any, int]:
    attempts = 0
    for attempt in range(MAX_QUOTA_COUNTED_ATTEMPTS):
        if client.provider == "openrouter":
            reserved = repository.reserve_daily_request(
                client.provider, daily_limit,
            )
            if reserved is None:
                raise DailyRequestLimitReached(
                    "provider_daily_request_limit_reached"
                )
            connection.commit()
        elif client.provider == "mistral":
            usage = repository.monthly_token_usage(
                client.provider, client.model,
            )
            if mistral_budget_reached(
                usage, monthly_credit_usd=monthly_credit_usd,
                input_usd_per_million=input_usd_per_million,
                output_usd_per_million=output_usd_per_million,
            ):
                raise MonthlyTokenLimitReached(
                    "provider_monthly_credit_limit_reached"
                )
        attempts += 1
        try:
            result = client.summarize(batch)
            if client.provider == "mistral":
                repository.record_monthly_token_usage(
                    client.provider, client.model, result.usage_metadata,
                )
                connection.commit()
            return result, attempts
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if status_code not in RETRYABLE_STATUS_CODES or attempt + 1 >= MAX_QUOTA_COUNTED_ATTEMPTS:
                raise
            time.sleep(10 * (attempt + 1))
    raise RuntimeError("unreachable summary provider retry state")


def cache_missing_summaries(connection: Any, broadcast_id: Any,
        utterances: list[dict[str, Any]], client: SummaryClient, *,
        daily_limit: int = HARD_DAILY_REQUEST_LIMIT,
        monthly_credit_usd: float = DEFAULT_MONTHLY_CREDIT_USD,
        input_usd_per_million: float = DEFAULT_INPUT_USD_PER_MILLION,
        output_usd_per_million: float = DEFAULT_OUTPUT_USD_PER_MILLION,
        ) -> dict[str, int | float]:
    repository = SummaryRepository(connection)
    contextualized = add_conversation_context(utterances)
    candidates = [
        item for item in contextualized
        if len(str(item.get("text") or "")) > MAX_SUMMARY_CHARS
    ]
    hashes = [item["content_hash"] for item in candidates]
    existing = repository.existing_hashes(
        broadcast_id, hashes, provider=client.provider, model=client.model,
        prompt_version=client.prompt_version,
    )
    deferred = repository.deferred_hashes(
        broadcast_id, hashes, provider=client.provider, model=client.model,
        prompt_version=client.prompt_version,
    )
    missing = [item for item in candidates if item["content_hash"] not in existing | deferred]
    saved = 0
    failed = 0
    attempted = False
    effective_daily_limit = (
        max(1, min(int(daily_limit), HARD_DAILY_REQUEST_LIMIT))
        if client.provider == "openrouter" else 0
    )
    effective_monthly_credit = (
        max(0.0, float(monthly_credit_usd))
        if client.provider == "mistral" else 0.0
    )
    monthly_usage_before = (
        repository.monthly_token_usage(client.provider, client.model)
        if client.provider == "mistral"
        else {
            "request_count": 0, "input_tokens": 0,
            "output_tokens": 0, "total_tokens": 0,
        }
    )
    api_requests = 0
    for batch in iter_summary_batches(missing):
        if attempted:
            time.sleep(MIN_REQUEST_INTERVAL_SECONDS)
        attempted = True
        try:
            result, attempts = _summarize_with_reserved_attempts(
                connection, repository, client, batch,
                effective_daily_limit, effective_monthly_credit,
                input_usd_per_million, output_usd_per_million,
            )
            api_requests += attempts
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else 0
            if status_code != 400:
                raise
            for item in batch:
                repository.record_failure(
                    broadcast_id, item["content_hash"], provider=client.provider,
                    model=client.model, prompt_version=client.prompt_version,
                    error=str(exc),
                )
            connection.commit()
            failed += len(batch)
            continue
        except (ValueError, KeyError) as exc:
            for item in batch:
                repository.record_failure(
                    broadcast_id, item["content_hash"], provider=client.provider,
                    model=client.model, prompt_version=client.prompt_version,
                    error=type(exc).__name__,
                )
            connection.commit()
            failed += len(batch)
            continue
        source_by_hash = {item["content_hash"]: item for item in batch}
        rows = []
        for generated in result.items:
            source = source_by_hash[generated["content_hash"]]
            rows.append({**generated,
                "source_speaker_label": str(source.get("source_speaker_label") or ""),
                "original_char_count": len(source["text"]),
                "segment_count": int(source.get("segment_count") or 1)})
        saved += repository.save_many(
            broadcast_id, rows, provider=client.provider, model=client.model,
            prompt_version=client.prompt_version, usage_metadata=result.usage_metadata,
        )
        connection.commit()
    daily_usage_after = (
        repository.daily_usage(client.provider)
        if client.provider == "openrouter" else 0
    )
    monthly_usage_after = (
        repository.monthly_token_usage(client.provider, client.model)
        if client.provider == "mistral" else monthly_usage_before
    )
    monthly_cost = mistral_usage_cost_usd(
        monthly_usage_after,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
    ) if client.provider == "mistral" else 0.0
    return {"eligible": len(candidates), "cached": len(existing),
        "deferred": len(deferred), "requested": len(missing), "saved": saved,
        "failed": failed, "api_requests": api_requests,
        "daily_limit": effective_daily_limit,
        "daily_usage": daily_usage_after,
        "monthly_credit_usd": effective_monthly_credit,
        "monthly_cost_usd": monthly_cost,
        "monthly_tokens": monthly_usage_after["total_tokens"]}
