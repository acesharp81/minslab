from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.schemas import DeepAnalysis, SimpleAnalysis
from app.services.analyzer import ChatEndpoint, OpenAIChatClient


SAMPLE_CONTEXT = """사업명: 생성형 AI 민원지원 서비스 구축
기관: 연계 점검용 가상기관
예산: 300000000
첨부: 공개 제안요청서.txt

추출 본문:
생성형 AI 기반 질의응답 서비스를 구축하고 LLM API와 RAG 기반 지식검색 기능을 연계한다.
범정부 AI 공통기반 활용 여부는 제안 단계에서 확인한다.
"""


def endpoints():
    settings = get_settings()
    return {
        "stage2": (
            ChatEndpoint(
                settings.stage2_provider,
                settings.stage2_base_url,
                settings.stage2_api_key,
                settings.stage2_model,
                settings.stage2_timeout_seconds,
            ),
            "simple_review.md",
            SimpleAnalysis,
        ),
        "stage3-primary": (
            ChatEndpoint(
                settings.stage3_primary_provider,
                settings.stage3_primary_base_url,
                settings.stage3_primary_api_key,
                settings.stage3_primary_model,
                settings.stage3_timeout_seconds,
                settings.stage3_primary_reasoning_effort,
            ),
            "deep_review.md",
            DeepAnalysis,
        ),
        "stage3-fallback": (
            ChatEndpoint(
                settings.stage3_fallback_provider,
                settings.stage3_fallback_base_url,
                settings.stage3_fallback_api_key,
                settings.stage3_fallback_model,
                settings.stage3_timeout_seconds,
            ),
            "deep_review.md",
            DeepAnalysis,
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="키를 노출하지 않고 단계별 LLM 연결을 1회 점검합니다.")
    parser.add_argument("--target", choices=["stage2", "stage3-primary", "stage3-fallback", "all"], default="all")
    args = parser.parse_args()
    prompt_root = Path(__file__).resolve().parent.parent / "app" / "prompts"
    selected = endpoints()
    if args.target != "all":
        selected = {args.target: selected[args.target]}

    results: dict[str, dict[str, object]] = {}
    failed = False
    for name, (endpoint, prompt_name, schema) in selected.items():
        if endpoint.provider == "mock":
            results[name] = {"status": "skipped", "reason": "provider=mock", "model": endpoint.model}
            continue
        if not endpoint.api_key:
            results[name] = {"status": "failed", "reason": "API key missing", "provider": endpoint.provider, "model": endpoint.model}
            failed = True
            continue
        try:
            prompt = (prompt_root / prompt_name).read_text(encoding="utf-8")
            model, usage = OpenAIChatClient(endpoint).call(prompt, SAMPLE_CONTEXT, schema)
            results[name] = {
                "status": "ok",
                "provider": endpoint.provider,
                "model": usage["model_name"],
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "result_type": type(model).__name__,
            }
        except Exception as exc:
            results[name] = {
                "status": "failed",
                "provider": endpoint.provider,
                "model": endpoint.model,
                "error": f"{type(exc).__name__}: {str(exc)[:300]}",
            }
            failed = True
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
