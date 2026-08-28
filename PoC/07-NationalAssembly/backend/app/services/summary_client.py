from __future__ import annotations

from typing import Any, Protocol

from .mistral_summary import (
    DEFAULT_BASE_URL as MISTRAL_BASE_URL,
    DEFAULT_MODEL as MISTRAL_MODEL,
    MistralSummaryClient,
)
from .openrouter_summary import (
    DEFAULT_MODEL as OPENROUTER_MODEL,
    OpenRouterSummaryClient,
)
from .summary_contract import PROMPT_VERSION


class SummaryClient(Protocol):
    provider: str
    prompt_version: str
    model: str

    def summarize(self, utterances: list[dict[str, Any]]) -> Any: ...


def summary_identity(settings: Any) -> tuple[str, str, str]:
    provider = str(settings.llm_provider or "disabled").strip().lower()
    defaults = {"mistral": MISTRAL_MODEL, "openrouter": OPENROUTER_MODEL}
    return provider, str(settings.llm_model or defaults.get(provider, "")), PROMPT_VERSION


def summary_daily_limit(settings: Any) -> int:
    provider = str(settings.llm_provider or "disabled").strip().lower()
    if provider == "openrouter":
        return int(settings.openrouter_daily_limit)
    return 0


def summary_monthly_credit_usd(settings: Any) -> float:
    provider = str(settings.llm_provider or "disabled").strip().lower()
    if provider == "mistral":
        return float(settings.mistral_monthly_credit_usd)
    return 0.0


def summary_mistral_prices(settings: Any) -> tuple[float, float]:
    return (
        float(settings.mistral_input_usd_per_million),
        float(settings.mistral_output_usd_per_million),
    )


def build_summary_client(settings: Any) -> SummaryClient:
    provider, model, _prompt_version = summary_identity(settings)
    if provider == "mistral":
        return MistralSummaryClient(
            settings.mistral_api_key,
            model=model,
            base_url=settings.mistral_base_url or MISTRAL_BASE_URL,
        )
    if provider == "openrouter":
        return OpenRouterSummaryClient(
            settings.openrouter_api_key,
            model=model,
            base_url=settings.openrouter_base_url,
        )
    raise ValueError(f"Unsupported LLM_PROVIDER: {provider}")
