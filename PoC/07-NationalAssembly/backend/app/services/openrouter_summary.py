from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Iterable

import requests

from .openrouter_gateway_client import openrouter_headers
from .summary_contract import (
    PROMPT_VERSION as COMMON_PROMPT_VERSION,
)
from .summary_contract import (
    build_summary_prompt,
    summary_response_schema,
    validated_summary_items,
)

PROVIDER = "openrouter"
PROMPT_VERSION = COMMON_PROMPT_VERSION
DEFAULT_MODEL = "nvidia/nemotron-3.5-super-vl:free"
MAX_BATCH_ITEMS = 8
MAX_BATCH_CHARS = 12_000
CONTEXT_BEFORE_ITEMS = 4
CONTEXT_AFTER_ITEMS = 2
MAX_CONTEXT_CHARS = 12_000
MAX_ATTEMPTS = 1
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class OpenRouterSummaryResult:
    items: list[dict[str, Any]]
    usage_metadata: dict[str, Any]


def parse_summary_items(text: str) -> list[Any]:
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("summaries")
    except json.JSONDecodeError:
        parsed = []
        decoder = json.JSONDecoder()
        marker = text.find("\"summaries\"")
        cursor = text.find("[", marker) + 1 if marker >= 0 else 0
        while cursor > 0:
            object_start = text.find("{", cursor)
            if object_start < 0:
                break
            try:
                item, cursor = decoder.raw_decode(text, object_start)
            except json.JSONDecodeError:
                break
            parsed.append(item)
        if not parsed:
            raise
    if not isinstance(parsed, list):
        raise ValueError("OpenRouter summary response must contain a summaries array")
    return parsed


def mixes_immediate_reply_task(item: dict[str, Any], source: str) -> bool:
    """Reject ambiguous oral-answer tasks for Mini to reprocess, not silently erase them."""
    task = str((item.get("live_insight") or {}).get("task") or "")
    if not re.search(r"설명|답변|응답", task):
        return False
    for clause in re.split(r"[.!?。！？]", source):
        # Written/future answers may be genuine follow-up tasks.
        if re.search(r"서면|답변서|추후|다음|내일|모레|까지|추가로|후에", clause):
            continue
        if re.search(r"(?:설명|답변|답|응답)\s*(?:해|하여)\s*(?:주십|주시|주세요|달라)", clause):
            return True
    return False


class OpenRouterSummaryClient:
    provider = PROVIDER
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_MODEL,
        base_url: str = "https://openrouter.ai/api/v1",
        timeout_seconds: float = 210.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OPENROUTER_API_KEY is required")
        self.api_key = api_key.strip()
        self.model = model.strip() or DEFAULT_MODEL
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def summarize(self, utterances: list[dict[str, Any]]) -> OpenRouterSummaryResult:
        prompt = build_summary_prompt(utterances)
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "공식 기록을 왜곡하지 않는 한국어 요약기다."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 12000,
            "response_format": {"type": "json_schema", "json_schema": {"name": "assembly_summaries", "strict": True, "schema": summary_response_schema()}},
            # Some endpoints require reasoning. Exclude its text without disabling it.
            "reasoning": {"effort": "low", "exclude": True},
            "provider": {
                "data_collection": "allow",
                "allow_fallbacks": True, "require_parameters": True,
            },
        }
        # Pin the evaluated model; provider fallback must not change its identity.
        body["models"] = [self.model]
        if self.model == "nvidia/nemotron-3.5-super-vl:free":
            # Validated for short Korean extraction; hidden reasoning still costs latency.
            body["reasoning"] = {"enabled": False, "exclude": True}
            body["messages"][0]["content"] += (
                " 한 발언에 후속 조치 요구와 즉석 질문이 섞이면 summary에는 둘 다 남기되, "
                "task에는 후속 조치만 남겨라. 현장에서 설명해 달라거나 답해 달라는 부분은 "
                "자료 제출·개선 계획 과제와 합치지 마라. task_evidence_quote 역시 "
                "그 후속 조치의 직접 요구 구간만 인용하라."
            )
            # Keep room for production batches larger than the two-item pilot.
            body["max_tokens"] = 8192
        if self.model == "dots-studio/dots-3-note-preview:free":
            body["reasoning"] = {"enabled": False, "exclude": True}
            body["max_tokens"] = 8192
        response = None
        for attempt in range(MAX_ATTEMPTS):
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=openrouter_headers(
                    self.api_key, body, workload="utterance_summary", priority=10,
                ),
                json=body,
                timeout=self.timeout_seconds,
            )
            status_code = getattr(response, "status_code", 200)
            if status_code not in RETRYABLE_STATUS_CODES or status_code == 429:
                break
            if attempt + 1 < MAX_ATTEMPTS:
                time.sleep(min(2 ** attempt, 4))
        assert response is not None
        if getattr(response, "status_code", 200) >= 400:
            try:
                error_data = response.json().get("error") or {}
                error_metadata = error_data.get("metadata") if isinstance(error_data, dict) else {}
                error_metadata = error_metadata if isinstance(error_metadata, dict) else {}
                error_message = str(error_metadata.get("raw") or error_data.get("message") or "upstream error")[:300]
            except Exception:
                error_message = "upstream error"
            raise requests.HTTPError(f"OpenRouter {response.status_code}: {error_message}", response=response)
        response.raise_for_status()
        payload = response.json()
        message = ((payload.get("choices") or [{}])[0].get("message") or {})
        parsed = parse_summary_items(str(message.get("content") or ""))
        items = validated_summary_items(parsed, utterances)
        quality_rejections: dict[str, str] = {}
        if self.model == DEFAULT_MODEL:
            sources = {u["content_hash"]: str(u.get("text") or "") for u in utterances}
            quality_rejections = {
                item["content_hash"]: "IMMEDIATE_REPLY_MIXED_IN_FOLLOW_UP"
                for item in items
                if mixes_immediate_reply_task(item, sources.get(item["content_hash"], ""))
            }
            items = [item for item in items if item["content_hash"] not in quality_rejections]
        return OpenRouterSummaryResult(
            items=items,
            usage_metadata={
                "request_id": str(payload.get("id") or ""),
                "upstream_provider": str(payload.get("provider") or ""),
                "response_model": str(payload.get("model") or ""),
                "raw_response": str(message.get("content") or ""),
                "quality_rejections": quality_rejections,
                "rejected_ids": [str(row.get('id')) for row in parsed if isinstance(row, dict)
                    and row.get('id') in {u['content_hash'] for u in utterances}
                    and row.get('id') not in {i['content_hash'] for i in items}],
                "usage": payload.get("usage") or {},
                "privacy": {"data_collection": "allow", "zdr": False,
                            "public_evidence_only": True},
            },
        )


def add_conversation_context(
    utterances: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach nearby complete speaker turns while keeping each target cacheable."""
    contextualized: list[dict[str, Any]] = []
    for target_index, target in enumerate(utterances):
        target_text = str(target.get("text") or "")
        selected_indexes = [target_index]
        context_chars = len(target_text)
        nearby = list(range(
            target_index - 1,
            max(-1, target_index - CONTEXT_BEFORE_ITEMS - 1),
            -1,
        ))
        nearby += list(range(
            target_index + 1,
            min(len(utterances), target_index + CONTEXT_AFTER_ITEMS + 1),
        ))
        for context_index in nearby:
            context_text = str(utterances[context_index].get("text") or "")
            if context_chars + len(context_text) > MAX_CONTEXT_CHARS:
                continue
            selected_indexes.append(context_index)
            context_chars += len(context_text)
        conversation = []
        for context_index in sorted(selected_indexes):
            item = utterances[context_index]
            conversation.append({
                "position": "target" if context_index == target_index else (
                    "before" if context_index < target_index else "after"
                ),
                "speaker": item.get("speaker_label") or "화자 미확인",
                "text": str(item.get("text") or ""),
            })
        contextualized.append({
            **target,
            "conversation_context": conversation,
        })
    return contextualized


def iter_summary_batches(
    utterances: Iterable[dict[str, Any]],
) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    char_count = 0
    for utterance in utterances:
        item_chars = len(str(utterance.get("text") or ""))
        if batch and (
            len(batch) >= MAX_BATCH_ITEMS
            or char_count + item_chars > MAX_BATCH_CHARS
        ):
            yield batch
            batch = []
            char_count = 0
        batch.append(utterance)
        char_count += item_chars
    if batch:
        yield batch
