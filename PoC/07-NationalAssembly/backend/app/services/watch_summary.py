from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import requests

from .openrouter_gateway_client import openrouter_headers


PROMPT_VERSION = "watch-briefing-report/3.3"
COMPATIBLE_PROMPT_VERSIONS = frozenset({
    PROMPT_VERSION, "watch-briefing-report/3.2",
})
MAX_EVIDENCE_CHARS = 18_000


def normalize_known_cjk_residue(value: str) -> str:
    normalized = re.sub(r"(?<=[가-힣])各", " 각", str(value or ""))
    normalized = re.sub(r"各\s*기관", "각 기관", normalized)
    return normalized.replace("各", "각")


class WatchSummaryQualityError(ValueError):
    def __init__(self, message: str, usage_metadata: dict[str, Any]) -> None:
        super().__init__(message)
        self.usage_metadata = usage_metadata


@dataclass(frozen=True)
class WatchSummaryResult:
    summary: str
    claims: list[dict[str, Any]]
    usage_metadata: dict[str, Any]


class MistralWatchSummaryClient:
    provider = "mistral"
    prompt_version = PROMPT_VERSION

    def __init__(
        self, api_key: str, *, model: str, base_url: str,
        timeout_seconds: float = 90.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("MISTRAL_API_KEY is required")
        self.api_key = api_key.strip()
        self.model = model.strip() or "mistral-small-2603"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _schema() -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "overview": {
                    "type": "string", "minLength": 1, "maxLength": 500,
                },
                "claims": {
                    "type": "array", "minItems": 2, "maxItems": 4,
                    "items": {
                        "type": "object", "additionalProperties": False,
                        "properties": {
                            "title": {"type": "string", "minLength": 1, "maxLength": 60},
                            "text": {"type": "string", "minLength": 1, "maxLength": 360},
                            "evidence_ids": {
                                "type": "array", "minItems": 1, "maxItems": 12,
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["title", "text", "evidence_ids"],
                    },
                },
            },
            "required": ["overview", "claims"],
        }

    def summarize(
        self, evidence: list[dict[str, Any]], *, quality_retry: bool = False,
    ) -> WatchSummaryResult:
        bounded = []
        char_count = 0
        for item in reversed(evidence):
            excerpt = str(item.get("excerpt") or "")[:1800]
            if bounded and char_count + len(excerpt) > MAX_EVIDENCE_CHARS:
                break
            bounded.append({**item, "excerpt": excerpt})
            char_count += len(excerpt)
        bounded.reverse()
        source = [{
            "id": str(item["match_id"]),
            "speaker": item.get("speaker_label") or "화자 확인 중",
            "text": item["excerpt"],
        } for item in bounded]
        quality_note = (
            "이전 출력은 한국어 보고체 또는 외국문자 혼입 품질검사를 통과하지 못했다. "
            "이번에는 입력에 있는 고유명사 외 영문·한자를 절대 사용하지 말고 모든 문장을 -습니다 체로 끝내라. "
            if quality_retry else ""
        )
        prompt = (
            quality_note
            + "아래 자료는 하나의 회의에서 사용자 관심주제와 연결된 발언 묶음이다. "
            "사용자가 담당자로부터 보고받는 것처럼 결론과 흐름이 이어지는 브리핑을 작성하라. "
            "시간순·기관별·발언별로 조각내지 말고, 겹치는 쟁점과 후속 요구를 합쳐 2~4개 큰 논점으로 구조화하라. "
            "입력이 5개 이하면 가급적 2개, 6~12개이면 2~3개 논점으로 통합하고, 실제로 독립된 쟁점일 때만 4개를 사용하라. "
            "overview는 회의에서 무엇이 확인됐고 무엇을 주목해야 하는지 2~3문장으로 종합하라. "
            "각 claim의 title은 보고서형 소제목, text는 상황·핵심 내용·확인된 요구나 조치를 자연스럽게 잇는 2~3문장 문단으로 작성하라. "
            "중요도와 논리 순서로 배열하고, 입력 하나마다 claim 하나를 만드는 방식은 금지한다. "
            "모든 문장은 개조식 명사형이 아닌 자연스러운 한국어 완결형 보고체(-습니다, -했습니다)로 작성하라. "
            "입력에 있지 않은 영문·한자 표현을 만들지 말고, 일반 개념은 반드시 한글로 표현하라. "
            "발췌문을 그대로 복사하지 말고 의미를 요약하되 수치·부정·요구·답변은 보존하라. "
            "각 claim에는 그 판단을 직접 뒷받침하는 입력 id를 evidence_ids로 반드시 넣어라. "
            "자료에 없는 사실, 인물, 기관, 결론을 만들지 말고 JSON만 출력하라.\n"
            + json.dumps({"evidence": source}, ensure_ascii=False)
        )
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json", "Accept": "application/json",
        }
        request_body = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "공식 기록을 왜곡하지 않는 한국어 회의 분석기다."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0, "stream": False, "max_tokens": 1200,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "watch_briefing_report_v3_3", "strict": True,
                        "schema": self._schema(),
                    },
                },
            }
        if self.provider == "openrouter":
            request_body.update({
                "reasoning": {"effort": "none", "exclude": True},
                "provider": {
                    "data_collection": "allow",
                    "allow_fallbacks": True, "require_parameters": True,
                },
            })
            headers = openrouter_headers(
                self.api_key, request_body, workload="watch_summary", priority=40,
            )
        response = requests.post(
            f"{self.base_url}/chat/completions", headers=headers,
            json=request_body, timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        usage_metadata = {
            "request_id": str(payload.get("id") or ""),
            "upstream_provider": str(payload.get("provider") or ""),
            "usage": payload.get("usage") or {},
            "privacy": (
                {"data_collection": "allow", "zdr": False,
                 "public_evidence_only": True}
                if self.provider == "openrouter" else {}
            ),
        }
        content = str((((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or ""))
        parsed = json.loads(content)
        allowed = {str(item["match_id"]) for item in bounded}
        claims = []
        for item in parsed.get("claims") or []:
            ids = [str(value) for value in item.get("evidence_ids") or [] if str(value) in allowed]
            title = " ".join(str(item.get("title") or "핵심 논의").split())[:60]
            text = " ".join(str(item.get("text") or "").split())[:360]
            title = normalize_known_cjk_residue(title)
            text = normalize_known_cjk_residue(text)
            if title and text and ids:
                claims.append({
                    "title": title, "text": text,
                    "evidence_ids": list(dict.fromkeys(ids)),
                })
        if not claims:
            raise WatchSummaryQualityError(
                "Watch topic report has no evidence-grounded claims", usage_metadata,
            )
        summary = " ".join(str(parsed.get("overview") or "").split())[:500]
        summary = normalize_known_cjk_residue(summary)
        if not summary:
            raise WatchSummaryQualityError(
                "Watch briefing report has no overview", usage_metadata,
            )
        source_text = " ".join(item["text"] for item in source).lower()
        generated_text = " ".join(
            [summary] + [item["title"] + " " + item["text"] for item in claims]
        )
        unknown_latin = {
            token.lower()
            for token in re.findall(r"[A-Za-z][A-Za-z0-9._-]*", generated_text)
            if token.lower() not in source_text
        }
        if unknown_latin:
            raise WatchSummaryQualityError(
                "Watch briefing report contains unsupported Latin text", usage_metadata,
            )
        unknown_cjk = {
            character
            for character in re.findall(r"[\u3400-\u4DBF\u4E00-\u9FFF]", generated_text)
            if character not in source_text
        }
        if unknown_cjk:
            raise WatchSummaryQualityError(
                "Watch briefing report contains unsupported CJK text", usage_metadata,
            )
        return WatchSummaryResult(
            summary=summary, claims=claims,
            usage_metadata=usage_metadata,
        )


class OpenRouterWatchSummaryClient(MistralWatchSummaryClient):
    provider = "openrouter"
