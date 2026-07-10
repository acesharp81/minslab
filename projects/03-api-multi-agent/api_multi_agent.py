#!/usr/bin/env python3
"""OpenAI 호환 API로 실행하는 독립형 멀티에이전트 CLI.

외부 패키지와 상위 프로젝트 모듈을 사용하지 않는다. 조정자가 계획을 세운 뒤
분석가와 검토자를 병렬 호출하고, 종합자가 두 결과를 하나의 답변으로 합친다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[1]
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


class AgentError(RuntimeError):
    """에이전트 설정 또는 API 실행에 실패했을 때 발생한다."""


def load_env(path: Path) -> None:
    """간단한 KEY=VALUE 형식의 설정을 읽되 기존 환경변수는 덮어쓰지 않는다."""
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and not value.startswith("YOUR_"):
            os.environ.setdefault(key, value)


def first_env(*names: str, default: str = "") -> str:
    """여러 환경변수 중 처음 설정된 값을 반환한다."""
    return next((os.environ[name] for name in names if os.environ.get(name)), default)


@dataclass(frozen=True)
class Agent:
    """한 에이전트의 이름과 책임, 시스템 지시사항."""

    name: str
    role: str
    system_prompt: str


@dataclass
class AgentResult:
    """에이전트 한 명의 실행 결과."""

    agent: str
    role: str
    content: str
    elapsed_seconds: float


@dataclass
class WorkflowResult:
    """전체 멀티에이전트 실행 결과."""

    request: str
    model: str
    final_answer: str
    stages: list[AgentResult]
    elapsed_seconds: float


class ChatCompletionsClient:
    """표준 라이브러리만 사용하는 OpenAI 호환 Chat Completions 클라이언트."""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float) -> None:
        if not api_key:
            raise AgentError(
                "API 키가 없습니다. 저장소 공용 .env에 "
                "OPENROUTER_API_KEY를 설정하세요."
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:500]
            raise AgentError(f"API HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise AgentError(f"API 연결 실패: {error}") from error

        try:
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise AgentError(f"API 응답 형식을 해석하지 못했습니다: {body[:300]}") from error

        if isinstance(content, list):
            content = "\n".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise AgentError("API가 빈 답변을 반환했습니다.")
        return content.strip()


class DemoClient:
    """네트워크 없이 오케스트레이션을 확인하는 결정적 데모 클라이언트."""

    model = "demo/offline"

    def complete(self, system_prompt: str, user_prompt: str) -> str:
        if "팀의 조정자" in system_prompt:
            return (
                "1. 요청의 목표와 완료 조건을 정의합니다.\n"
                "2. 필요한 정보와 제약조건을 분리합니다.\n"
                "3. 실행안과 위험요소를 각각 검토합니다.\n"
                "4. 우선순위와 다음 행동을 포함한 답변으로 종합합니다."
            )
        if "해결안을 설계" in system_prompt:
            return (
                "핵심 목표를 작은 작업 단위로 나누고 담당자, 산출물, 완료 기준을 "
                "명시합니다. 가장 불확실한 가정은 짧은 검증 실험으로 먼저 확인하고, "
                "측정 가능한 지표를 두어 결과를 비교합니다."
            )
        if "위험과 허점" in system_prompt:
            return (
                "요구사항 누락, 외부 API 실패, 비용 증가, 보안 정보 노출 가능성을 "
                "점검해야 합니다. 각 위험에는 타임아웃, 예산 한도, 비밀정보 분리, "
                "사람의 최종 검토 같은 대응책이 필요합니다."
            )
        return (
            "요청을 실행 가능한 단계로 나누고 가장 불확실한 부분부터 검증하세요. "
            "담당자와 완료 기준을 정한 뒤 작은 실험을 실행하고, API 실패·비용·보안 "
            "위험을 함께 관리하세요. 마지막에는 측정 결과를 바탕으로 다음 단계를 결정합니다."
        )


class MultiAgentWorkflow:
    """조정 → 병렬 분석/검토 → 종합 순서로 에이전트를 실행한다."""

    coordinator = Agent(
        name="coordinator",
        role="조정자",
        system_prompt=(
            "당신은 멀티에이전트 팀의 조정자입니다. 사용자 요청을 분석해 구체적인 "
            "실행 계획을 작성하세요. 목표, 제약조건, 필요한 판단, 완료 기준을 포함하고 "
            "아직 확인하지 않은 사실은 사실처럼 단정하지 마세요."
        ),
    )
    analyst = Agent(
        name="analyst",
        role="분석가",
        system_prompt=(
            "당신은 실행 가능한 해결안을 설계하는 분석가입니다. 요청과 조정자의 계획을 "
            "바탕으로 선택지, 권장안, 구체적인 실행 단계를 제시하세요. 근거가 없는 수치나 "
            "외부 사실을 만들지 마세요."
        ),
    )
    reviewer = Agent(
        name="reviewer",
        role="검토자",
        system_prompt=(
            "당신은 계획의 위험과 허점을 찾는 독립 검토자입니다. 누락된 요구사항, "
            "실패 조건, 보안·비용·운영 위험, 검증 방법을 지적하고 현실적인 보완책을 "
            "제안하세요. 비판만 하지 말고 우선순위를 정하세요."
        ),
    )
    synthesizer = Agent(
        name="synthesizer",
        role="종합자",
        system_prompt=(
            "당신은 멀티에이전트 팀의 최종 종합자입니다. 사용자 요청, 실행 계획, 분석, "
            "검토 결과를 비교해 중복과 모순을 제거하세요. 가장 중요한 결론부터 한국어로 "
            "명료하게 답하고, 실행 단계와 주의사항을 필요한 만큼만 포함하세요."
        ),
    )

    def __init__(self, complete: Callable[[str, str], str], model: str) -> None:
        self.complete = complete
        self.model = model

    def _run_agent(self, agent: Agent, prompt: str) -> AgentResult:
        started = time.perf_counter()
        content = self.complete(agent.system_prompt, prompt)
        return AgentResult(
            agent=agent.name,
            role=agent.role,
            content=content,
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )

    def run(self, user_request: str) -> WorkflowResult:
        started = time.perf_counter()
        plan = self._run_agent(self.coordinator, user_request)
        shared_prompt = (
            f"[사용자 요청]\n{user_request}\n\n"
            f"[조정자의 실행 계획]\n{plan.content}"
        )

        parallel_results: dict[str, AgentResult] = {}
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._run_agent, agent, shared_prompt): agent.name
                for agent in (self.analyst, self.reviewer)
            }
            for future in as_completed(futures):
                parallel_results[futures[future]] = future.result()

        analysis = parallel_results[self.analyst.name]
        review = parallel_results[self.reviewer.name]
        final_prompt = (
            f"{shared_prompt}\n\n"
            f"[분석가 결과]\n{analysis.content}\n\n"
            f"[검토자 결과]\n{review.content}"
        )
        final = self._run_agent(self.synthesizer, final_prompt)
        return WorkflowResult(
            request=user_request,
            model=self.model,
            final_answer=final.content,
            stages=[plan, analysis, review, final],
            elapsed_seconds=round(time.perf_counter() - started, 3),
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="API 기반 멀티에이전트 협업을 독립 실행합니다."
    )
    parser.add_argument("request", nargs="+", help="에이전트 팀이 처리할 요청")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="API를 호출하지 않고 예제 응답으로 협업 흐름을 확인합니다.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="최종 답변과 함께 모든 에이전트의 중간 결과를 출력합니다.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="실행 결과를 JSON으로 출력합니다.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=PROJECT_ROOT / ".env",
        help="환경설정 파일 경로(기본값: 저장소 루트의 공용 .env)",
    )
    return parser


def create_workflow(args: argparse.Namespace) -> MultiAgentWorkflow:
    if args.demo:
        client = DemoClient()
        return MultiAgentWorkflow(client.complete, client.model)

    load_env(args.env_file.expanduser().resolve())
    api_key = first_env("OPENROUTER_API_KEY", "MULTI_AGENT_API_KEY")
    base_url = first_env(
        "OPENROUTER_BASE_URL", "MULTI_AGENT_BASE_URL", default=DEFAULT_BASE_URL
    )
    model = first_env("MULTI_AGENT_MODEL", "OPENROUTER_MODEL", default=DEFAULT_MODEL)
    timeout_text = first_env("MULTI_AGENT_TIMEOUT", default="60")
    try:
        timeout = float(timeout_text)
        if timeout <= 0:
            raise ValueError
    except ValueError as error:
        raise AgentError("MULTI_AGENT_TIMEOUT은 0보다 큰 숫자여야 합니다.") from error

    client = ChatCompletionsClient(api_key, base_url, model, timeout)
    return MultiAgentWorkflow(client.complete, model)


def print_result(result: WorkflowResult, verbose: bool) -> None:
    if verbose:
        for stage in result.stages:
            print(f"\n[{stage.role} · {stage.agent} · {stage.elapsed_seconds:.3f}s]")
            print(stage.content)
    else:
        print(result.final_answer)
    print(f"\n모델: {result.model} · 전체 소요: {result.elapsed_seconds:.3f}s")


def main() -> int:
    args = build_parser().parse_args()
    user_request = " ".join(args.request).strip()
    try:
        workflow = create_workflow(args)
        result = workflow.run(user_request)
    except AgentError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n실행을 취소했습니다.", file=sys.stderr)
        return 130

    if args.json:
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    else:
        print_result(result, args.verbose)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
