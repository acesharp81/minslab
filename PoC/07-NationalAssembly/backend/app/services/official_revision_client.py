from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable

import requests

from .official_edit_validation import filter_supported_official_edits


PROMPT_VERSION = "official-brief-delta/1.2"
MAX_OFFICIAL_EVIDENCE = 64
MAX_EVIDENCE_CHARS = 480


@dataclass(frozen=True)
class OfficialRevisionResult:
    edits: list[dict[str, Any]]
    usage_metadata: dict[str, Any]


def revision_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "edits": {
                "type": "array", "maxItems": 30,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "properties": {
                        "entity_type": {
                            "type": "string", "enum": ["meeting", "topic", "task"],
                        },
                        "entity_id": {"type": "string", "maxLength": 80},
                        "operation": {
                            "type": "string", "enum": ["UPDATE", "ADD", "DELETE"],
                        },
                        "field": {
                            "type": "string",
                            "enum": ["headline", "summary", "title", "ministries", "entity"],
                        },
                        "new_text": {"type": "string", "maxLength": 600},
                        "new_values": {
                            "type": "array", "maxItems": 8,
                            "items": {"type": "string", "maxLength": 80},
                        },
                        "title": {"type": "string", "maxLength": 220},
                        "summary": {"type": "string", "maxLength": 500},
                        "topic_id": {"type": "string", "maxLength": 80},
                        "ministries": {
                            "type": "array", "maxItems": 8,
                            "items": {"type": "string", "maxLength": 80},
                        },
                        "official_utterance_ids": {
                            "type": "array", "minItems": 1, "maxItems": 8,
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "entity_type", "entity_id", "operation", "field",
                        "new_text", "new_values", "title", "summary",
                        "topic_id", "ministries", "official_utterance_ids",
                    ],
                },
            },
        },
        "required": ["edits"],
    }


def _live_packet(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": brief.get("headline"),
        "summary": brief.get("summary"),
        "topics": [
            {"id": item.get("id"), "title": item.get("title"), "summary": item.get("summary")}
            for item in brief.get("topics", [])
        ],
        "tasks": [
            {
                "id": item.get("id"), "title": item.get("title"),
                "topic_id": item.get("topic_id"),
                "ministries": item.get("ministries") or [],
            }
            for item in brief.get("tasks", [])
        ],
    }


def build_revision_prompt(
    live_brief: dict[str, Any], official_rows: Iterable[dict[str, Any]],
) -> tuple[str, set[str]]:
    rows = [dict(row) for row in official_rows]
    policy = [row for row in rows if row.get("utterance_kind") == "POLICY"] or rows
    if len(policy) > MAX_OFFICIAL_EVIDENCE:
        policy = [
            policy[round(index * (len(policy) - 1) / (MAX_OFFICIAL_EVIDENCE - 1))]
            for index in range(MAX_OFFICIAL_EVIDENCE)
        ]
    evidence = []
    valid_ids: set[str] = set()
    for row in policy[:MAX_OFFICIAL_EVIDENCE]:
        utterance_id = str(row.get("utterance_id") or "")
        text = " ".join(str(row.get("text") or "").split())[:MAX_EVIDENCE_CHARS]
        if not utterance_id or not text:
            continue
        valid_ids.add(utterance_id)
        evidence.append({
            "id": utterance_id,
            "sequence": row.get("sequence_number"),
            "speaker": row.get("speaker_name"),
            "role": row.get("speaker_role"),
            "text": text,
            "topics": row.get("topics") or [],
            "ministries": row.get("ministries") or [],
        })
    prompt = (
        "LIVE 자막에서 만든 잠정 회의 결과와 공식 회의록 발언을 대조한다.\n"
        "문체 개선만을 위한 수정은 만들지 말고, 공식 발언이 기존 내용과 명확히 다를 때만 수정한다.\n"
        "공식 자료에 없다는 이유만으로 기존 항목을 삭제하지 않는다. 삭제는 공식 내용이 기존 판단을 명백히 부정할 때만 허용한다.\n"
        "개조식을 서술식으로 풀거나 문장 종결·어순만 바꾸는 UPDATE는 금지한다. 기존 의미에 설명을 "
        "덧붙이는 대신 새로운 사실·결정·조치는 별도의 주제나 과제로 추가한다.\n"
        "추가는 공식 발언에 분명한 주요 주제나 후속 과제가 있고 기존 항목에 포함되지 않았을 때만 허용한다.\n"
        "새 과제가 기존 주제와 직접 관련되지 않으면 무관한 주제에 붙이지 말고 ADD topic과 ADD task를 함께 반환한다.\n"
        "함께 추가하는 topic과 task는 topic_id에 같은 new-topic-N 임시 키를 넣는다.\n"
        "UPDATE는 기존 entity_id를 보존한다. ADD는 entity_id를 빈 문자열로 둔다. ADD topic은 summary도 채운다.\n"
        "모든 변경은 반드시 아래 official utterance id를 근거로 포함한다. 화자명은 수정하지 않는다.\n\n"
        f"[잠정 결과]\n{json.dumps(_live_packet(live_brief), ensure_ascii=False)}\n\n"
        f"[공식 근거 발언]\n{json.dumps(evidence, ensure_ascii=False)}"
    )
    return prompt, valid_ids


def validate_revision_edits(
    payload: dict[str, Any], live_brief: dict[str, Any], valid_official_ids: set[str],
) -> list[dict[str, Any]]:
    valid_entities = {
        "topic": {str(item.get("id")) for item in live_brief.get("topics", [])},
        "task": {str(item.get("id")) for item in live_brief.get("tasks", [])},
    }
    result = []
    for raw in payload.get("edits", []) if isinstance(payload.get("edits"), list) else []:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        entity_type = str(item.get("entity_type") or "")
        operation = str(item.get("operation") or "")
        entity_id = str(item.get("entity_id") or "")
        evidence_ids = [
            str(value) for value in item.get("official_utterance_ids") or []
            if str(value) in valid_official_ids
        ]
        if not evidence_ids:
            continue
        if entity_type in {"topic", "task"} and operation != "ADD":
            if entity_id not in valid_entities[entity_type]:
                continue
        if entity_type == "meeting" and operation != "UPDATE":
            continue
        item["official_utterance_ids"] = evidence_ids
        result.append(item)
    return result


class MistralOfficialRevisionClient:
    def __init__(
        self, api_key: str, *, model: str, base_url: str,
        timeout_seconds: float = 120.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("MISTRAL_API_KEY is required")
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def compare(
        self, live_brief: dict[str, Any], official_rows: Iterable[dict[str, Any]],
    ) -> OfficialRevisionResult:
        rows = list(official_rows)
        prompt, valid_ids = build_revision_prompt(live_brief, rows)
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json", "Accept": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "공식 근거에만 기반해 잠정 국회 회의 결과의 변경점만 반환한다."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False, "temperature": 0.0, "random_seed": 19,
                "max_tokens": 8000, "reasoning_effort": "none",
                "safe_prompt": False, "service_tier": "standard_only",
                "prompt_cache_key": f"poc07-{PROMPT_VERSION}",
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "official_brief_delta", "strict": True,
                        "schema": revision_response_schema(),
                    },
                },
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise requests.HTTPError(
                f"Mistral {response.status_code}: upstream error", response=response,
            )
        response.raise_for_status()
        payload = response.json()
        content = str(
            (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "")
        )
        data = json.loads(content)
        edits = filter_supported_official_edits(
            data, live_brief,
            [row for row in rows if str(row.get("utterance_id")) in valid_ids],
        )
        return OfficialRevisionResult(
            edits=edits,
            usage_metadata={
                "request_id": str(payload.get("id") or ""),
                "usage": payload.get("usage") or {},
            },
        )
