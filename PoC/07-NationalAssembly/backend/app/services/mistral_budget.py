from __future__ import annotations

from typing import Any


DEFAULT_MONTHLY_CREDIT_USD = 10.0
DEFAULT_INPUT_USD_PER_MILLION = 0.15
DEFAULT_OUTPUT_USD_PER_MILLION = 0.60


def mistral_usage_cost_usd(
    usage: dict[str, Any], *,
    input_usd_per_million: float = DEFAULT_INPUT_USD_PER_MILLION,
    output_usd_per_million: float = DEFAULT_OUTPUT_USD_PER_MILLION,
) -> float:
    input_tokens = max(0, int(usage.get("input_tokens") or 0))
    output_tokens = max(0, int(usage.get("output_tokens") or 0))
    text_cost = (
        input_tokens * float(input_usd_per_million)
        + output_tokens * float(output_usd_per_million)
    ) / 1_000_000
    return text_cost + max(0.0, float(usage.get("audio_cost_usd") or 0.0))


def mistral_budget_reached(
    usage: dict[str, Any], *,
    monthly_credit_usd: float = DEFAULT_MONTHLY_CREDIT_USD,
    input_usd_per_million: float = DEFAULT_INPUT_USD_PER_MILLION,
    output_usd_per_million: float = DEFAULT_OUTPUT_USD_PER_MILLION,
) -> bool:
    return mistral_usage_cost_usd(
        usage,
        input_usd_per_million=input_usd_per_million,
        output_usd_per_million=output_usd_per_million,
    ) >= max(0.0, float(monthly_credit_usd))


def mistral_budget_values(settings: Any) -> dict[str, float]:
    return {
        "monthly_credit_usd": float(settings.mistral_monthly_credit_usd),
        "input_usd_per_million": float(
            settings.mistral_input_usd_per_million
        ),
        "output_usd_per_million": float(
            settings.mistral_output_usd_per_million
        ),
    }
