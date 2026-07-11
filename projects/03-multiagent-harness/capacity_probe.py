#!/usr/bin/env python3
"""Provider 단일 키 동시 호출 용량을 관리자 CLI에서 제한적으로 검증한다."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Any

from model_gateway import ModelGateway, ModelGatewayError, model_options


@dataclass(frozen=True)
class ProbePlan:
    model: str
    provider: str
    concurrency: int
    requests: int
    max_tokens: int
    confirmed: bool


def build_probe_plan(
    model_ref: str,
    *,
    concurrency: int,
    requests: int,
    max_tokens: int,
    confirmed: bool,
) -> ProbePlan:
    if ":" not in model_ref:
        raise ValueError("모델은 provider:model 형식이어야 합니다.")
    provider = model_ref.split(":", 1)[0]
    if provider not in {"ollama", "huggingface", "openrouter"}:
        raise ValueError("지원하지 않는 provider입니다.")
    concurrency = max(1, min(4, int(concurrency)))
    requests = max(1, min(4, int(requests)))
    if concurrency > requests:
        concurrency = requests
    max_tokens = max(8, min(32, int(max_tokens)))
    return ProbePlan(model_ref, provider, concurrency, requests, max_tokens, confirmed)


def preflight() -> dict[str, Any]:
    options = model_options()
    return {
        "mode": "preflight",
        "providers": options["providers"],
        "models": [
            {
                "value": item["value"],
                "provider": item["provider"],
                "available": item["available"],
            }
            for item in options["models"]
        ],
        "notice": "외부 모델 호출은 실행하지 않았습니다.",
    }


def run_probe(plan: ProbePlan) -> dict[str, Any]:
    if not plan.confirmed:
        raise ValueError("실제 호출에는 --confirm-live가 필요합니다.")
    gateway = ModelGateway()
    allowed = gateway.allowed.get(plan.model)
    if not allowed:
        raise ValueError("모델 레지스트리에 없는 모델입니다.")
    if not allowed["available"]:
        raise ValueError("선택한 provider가 설정되지 않았습니다.")

    def invoke(index: int) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            gateway.complete(
                plan.model,
                [
                    {"role": "system", "content": "You are a capacity probe. Reply only with OK."},
                    {"role": "user", "content": f"Probe {index}: reply only OK."},
                ],
                temperature=0,
                max_tokens=plan.max_tokens,
                timeout=120,
                max_retries=0,
            )
            return {"index": index, "ok": True, "elapsed_seconds": round(time.perf_counter() - started, 3)}
        except ModelGatewayError as error:
            return {
                "index": index,
                "ok": False,
                "status": error.status,
                "retryable": error.retryable,
                "error": str(error),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }

    started = time.perf_counter()
    results = []
    with ThreadPoolExecutor(max_workers=plan.concurrency) as executor:
        futures = [executor.submit(invoke, index + 1) for index in range(plan.requests)]
        for future in as_completed(futures):
            results.append(future.result())
    results.sort(key=lambda item: item["index"])
    success = sum(1 for item in results if item["ok"])
    return {
        "mode": "live-capacity-probe",
        "plan": asdict(plan),
        "success": success,
        "failed": len(results) - success,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "results": results,
        "gateway": gateway.status(),
        "recommendation": {
            "safe_concurrency": plan.concurrency if success == len(results) else max(1, plan.concurrency - 1),
            "apply_automatically": False,
        },
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="멀티에이전트 provider 용량을 안전하게 점검합니다.")
    value.add_argument("--model", default="", help="provider:model 형식")
    value.add_argument("--concurrency", type=int, default=1, help="1~4")
    value.add_argument("--requests", type=int, default=1, help="총 1~4회")
    value.add_argument("--max-tokens", type=int, default=16, help="8~32")
    value.add_argument("--confirm-live", action="store_true", help="실제 모델 호출에 명시적으로 동의")
    return value


def main() -> int:
    args = parser().parse_args()
    if not args.model:
        print(json.dumps(preflight(), ensure_ascii=False, indent=2))
        return 0
    try:
        plan = build_probe_plan(
            args.model,
            concurrency=args.concurrency,
            requests=args.requests,
            max_tokens=args.max_tokens,
            confirmed=args.confirm_live,
        )
        if not plan.confirmed:
            raise ValueError("비용이 발생할 수 있습니다. 확인 후 --confirm-live를 추가하세요.")
        print(json.dumps(run_probe(plan), ensure_ascii=False, indent=2))
        return 0
    except (ValueError, ModelGatewayError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
