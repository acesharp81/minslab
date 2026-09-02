from __future__ import annotations

import argparse
import logging
import time

from ..config import get_settings
from ..db.connection import connect
from ..db.summary_repository import SummaryRepository, token_usage_from_metadata
from ..db.watch_summary_repository import WatchSummaryRepository
from ..services.mistral_budget import mistral_usage_cost_usd
from ..services.openrouter_summary import DEFAULT_MODEL as OPENROUTER_DEFAULT_MODEL
from ..services.watch_summary import (
    MistralWatchSummaryClient, OpenRouterWatchSummaryClient, PROMPT_VERSION,
    WatchSummaryQualityError,
)


LOGGER = logging.getLogger(__name__)


def run_once(database_url: str) -> dict[str, int | float | str]:
    settings = get_settings()
    if not settings.watch_llm_enabled:
        return {"status": "DISABLED", "generated": 0, "cost_usd": 0.0}
    provider = settings.watch_llm_provider.strip().lower()
    if provider == "openrouter":
        model = settings.watch_llm_model.strip() or OPENROUTER_DEFAULT_MODEL
        if not settings.openrouter_api_key:
            return {"status": "CONFIG_REQUIRED", "generated": 0, "cost_usd": 0.0}
    elif provider == "mistral":
        model = settings.watch_llm_model.strip() or settings.llm_model
        if not settings.mistral_api_key:
            return {"status": "CONFIG_REQUIRED", "generated": 0, "cost_usd": 0.0}
    else:
        return {"status": "UNSUPPORTED_PROVIDER", "generated": 0, "cost_usd": 0.0}

    with connect(database_url) as connection:
        repository = WatchSummaryRepository(connection)
        watch_cost = repository.monthly_cost()
        summary_repository = SummaryRepository(connection)
        global_cost = 0.0
        if provider == "mistral":
            global_usage = summary_repository.monthly_token_usage(provider, model)
            global_cost = mistral_usage_cost_usd(
                global_usage,
                input_usd_per_million=settings.mistral_input_usd_per_million,
                output_usd_per_million=settings.mistral_output_usd_per_million,
            ) + float(global_usage.get("audio_cost_usd") or 0)
        session_id = repository.candidate_session(
            min_new_matches=settings.watch_llm_min_new_matches,
            debounce_seconds=settings.watch_llm_debounce_seconds,
            max_updates=settings.watch_llm_max_updates_per_session,
            provider=provider, model=model, prompt_version=PROMPT_VERSION,
        )
        if session_id is None:
            return {"status": "IDLE", "generated": 0, "cost_usd": watch_cost}
        evidence = repository.evidence(session_id)
        version_id = repository.claim(
            session_id, evidence, provider=provider, model=model,
            prompt_version=PROMPT_VERSION,
        )
        if version_id is None:
            repository.clear_request(session_id)
            return {"status": "CACHED", "generated": 0, "cost_usd": watch_cost}
        if watch_cost >= settings.watch_llm_monthly_budget_usd:
            repository.limit(version_id, "WATCH_MONTHLY_SOFT_CAP")
            return {"status": "LIMIT_REACHED", "generated": 0, "cost_usd": watch_cost}
        if provider == "mistral" and global_cost >= settings.mistral_monthly_credit_usd:
            repository.limit(version_id, "MISTRAL_GLOBAL_MONTHLY_CAP")
            return {"status": "GLOBAL_LIMIT_REACHED", "generated": 0, "cost_usd": watch_cost}
        if provider == "openrouter":
            daily_limit = max(1, min(int(settings.openrouter_daily_limit), 500))
            reserved = summary_repository.reserve_daily_request("openrouter", daily_limit)
            if reserved is None:
                repository.limit_daily(version_id, "OPENROUTER_DAILY_LIMIT")
                return {"status": "DAILY_LIMIT_REACHED", "generated": 0, "cost_usd": watch_cost}
            client = OpenRouterWatchSummaryClient(
                settings.openrouter_api_key, model=model, base_url=settings.openrouter_base_url,
            )
        else:
            client = MistralWatchSummaryClient(
                settings.mistral_api_key, model=model, base_url=settings.mistral_base_url,
            )
        prior_input_tokens = 0
        prior_output_tokens = 0
        prior_cost = 0.0
        try:
            for attempt in range(2):
                try:
                    result = client.summarize(evidence, quality_retry=attempt > 0)
                    break
                except WatchSummaryQualityError as quality_error:
                    failed_usage = token_usage_from_metadata(quality_error.usage_metadata)
                    summary_repository.record_monthly_token_usage(
                        provider, model, quality_error.usage_metadata,
                    )
                    prior_input_tokens += failed_usage["input_tokens"]
                    prior_output_tokens += failed_usage["output_tokens"]
                    if provider == "openrouter":
                        prior_cost += float(
                            (quality_error.usage_metadata.get("usage") or {}).get("cost") or 0
                        )
                    else:
                        prior_cost += mistral_usage_cost_usd(
                            failed_usage,
                            input_usd_per_million=settings.mistral_input_usd_per_million,
                            output_usd_per_million=settings.mistral_output_usd_per_million,
                        )
                    if attempt > 0:
                        raise
                    if provider == "openrouter":
                        retry_reserved = summary_repository.reserve_daily_request(
                            "openrouter", daily_limit,
                        )
                        if retry_reserved is None:
                            repository.limit_daily(version_id, "OPENROUTER_DAILY_LIMIT")
                            return {
                                "status": "DAILY_LIMIT_REACHED", "generated": 0,
                                "cost_usd": watch_cost + prior_cost,
                            }
            usage = token_usage_from_metadata(result.usage_metadata)
            if provider == "openrouter":
                cost = float((result.usage_metadata.get("usage") or {}).get("cost") or 0)
            else:
                cost = mistral_usage_cost_usd(
                    usage,
                    input_usd_per_million=settings.mistral_input_usd_per_million,
                    output_usd_per_million=settings.mistral_output_usd_per_million,
                )
            summary_repository.record_monthly_token_usage(
                provider, model, result.usage_metadata,
            )
            total_cost = prior_cost + cost
            repository.complete(
                version_id, summary=result.summary, claims=result.claims,
                input_tokens=prior_input_tokens + usage["input_tokens"],
                output_tokens=prior_output_tokens + usage["output_tokens"],
                cost_usd=total_cost,
            )
            repository.clear_request(session_id)
            return {
                "status": "READY", "generated": 1,
                "cost_usd": watch_cost + total_cost,
            }
        except Exception as exc:
            safe_error = (
                str(exc) if isinstance(exc, WatchSummaryQualityError)
                else type(exc).__name__
            )
            repository.fail(version_id, safe_error)
            if isinstance(exc, WatchSummaryQualityError):
                repository.clear_request(session_id)
            LOGGER.warning("watch summary failed without evidence payload: %s", safe_error)
            return {
                "status": "FAILED", "generated": 0,
                "cost_usd": watch_cost + prior_cost,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description="선택형 관심주제 통합 요약 worker")
    parser.add_argument("--interval", type=float, default=10.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    logging.basicConfig(level=settings.national_assembly_log_level)
    while True:
        try:
            result = run_once(settings.database_url)
            if result.get("generated") or result.get("status") == "FAILED":
                LOGGER.info("watch summary worker processed %s", result)
        except Exception:  # noqa: BLE001 - persistent worker retries
            LOGGER.exception("watch summary worker iteration failed")
        if args.once:
            return
        time.sleep(max(2.0, args.interval))


if __name__ == "__main__":
    main()
