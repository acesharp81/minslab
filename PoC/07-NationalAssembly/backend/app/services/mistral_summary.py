from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from .summary_contract import (
    PROMPT_VERSION,
    build_summary_prompt,
    parse_summary_items,
    summary_response_schema,
    validated_summary_items,
)


PROVIDER = "mistral"
DEFAULT_MODEL = "mistral-small-2603"
DEFAULT_BASE_URL = "https://api.mistral.ai/v1"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class MistralSummaryResult:
    items: list[dict[str, Any]]
    usage_metadata: dict[str, Any]


class MistralSummaryClient:
    provider = PROVIDER
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 90.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("MISTRAL_API_KEY is required")
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def summarize(self, utterances: list[dict[str, Any]]) -> MistralSummaryResult:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "공식 기록을 왜곡하지 않는 한국어 요약기다."},
                {"role": "user", "content": build_summary_prompt(utterances)},
            ],
            "stream": False,
            "temperature": 0.0,
            "random_seed": 7,
            "max_tokens": 1024,
            "reasoning_effort": "none",
            "safe_prompt": False,
            "service_tier": "standard_only",
            "prompt_cache_key": f"poc07-{PROMPT_VERSION}",
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "assembly_summaries",
                    "strict": True,
                    "schema": summary_response_schema(),
                },
            },
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=body,
            timeout=self.timeout_seconds,
        )
        if getattr(response, "status_code", 200) >= 400:
            try:
                payload = response.json()
                message = str(payload.get("message") or payload.get("detail") or "upstream error")[:300]
            except Exception:
                message = "upstream error"
            raise requests.HTTPError(
                f"Mistral {response.status_code}: {message}", response=response,
            )
        response.raise_for_status()
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        parsed = parse_summary_items(str(message.get("content") or ""))
        return MistralSummaryResult(
            items=validated_summary_items(parsed, utterances),
            usage_metadata={
                "request_id": str(payload.get("id") or ""),
                "usage": payload.get("usage") or {},
            },
        )
