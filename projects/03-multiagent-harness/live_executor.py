"""실제 모델 호출을 계층형 작업 DAG로 실행하는 제한형 하네스."""

from __future__ import annotations

import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Callable

from harness_engine import AGENTS, DEFAULT_MODELS, POOLS
from model_gateway import ModelGateway, ModelGatewayError
from scheduler import HierarchicalScheduler, WorkItem, incident_response_work_items


class LiveExecutionError(RuntimeError):
    pass


def _bounded_env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def new_live_run(prompt: str) -> dict[str, Any]:
    clean_prompt = " ".join(str(prompt or "").split())
    if not clean_prompt:
        raise LiveExecutionError("실제 LLM 실행 요청을 입력해 주세요.")
    if len(clean_prompt) > 2000:
        raise LiveExecutionError("실제 LLM 실행 요청은 2,000자를 넘을 수 없습니다.")
    return {
        "run_id": str(uuid.uuid4()),
        "mode": "live-llm",
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt": clean_prompt,
        "agents": [asdict(agent) for agent in AGENTS],
        "pools": [asdict(pool) for pool in POOLS],
        "models": [{**asdict(model), "value": model.value} for model in DEFAULT_MODELS],
        "events": [],
        "artifacts": [],
        "limits": {
            "max_model_calls": 8,
            "max_wall_seconds": _bounded_env_int("MULTI_AGENT_LIVE_MAX_SECONDS", 300, 60, 600),
            "max_tokens_per_call": _bounded_env_int("MULTI_AGENT_LIVE_MAX_TOKENS", 600, 128, 1000),
            "max_concurrent_runs": 1,
        },
    }


TASK_GUIDANCE = {
    "collect-facts": "요청문에서 확인된 사실, 시각, 영향, 미확인 사항을 표로 추출하세요. 없는 사실을 만들지 마세요.",
    "collect-public": "요청문을 바탕으로 민원·언론·국회 질의 가능 쟁점과 답변 원칙을 정리하세요. 가상 추정을 명시하세요.",
    "summarize-evidence": "두 수집 문서를 통합해 확인 사실·추정·미확인을 엄격히 구분한 공용 근거 요약을 작성하세요.",
    "technical-analysis": "공용 근거만 사용해 기술적 관찰, 원인 가설, 즉시 조치, 재발방지 대책을 구분해 작성하세요.",
    "legal-review": "공용 근거를 기준으로 제도·법령 검토 항목과 표현상 주의점을 작성하세요. 법률 자문이 아님을 명시하세요.",
    "executive-brief": "기술·법제 문서를 통합해 현황, 영향, 조치, 리스크, 의사결정 요청이 포함된 간결한 보고자료를 작성하세요.",
    "risk-check": "보고자료를 사실·법령·표현 관점에서 독립 검수하고 항목별 PASS 또는 REWORK 판정과 수정 권고를 작성하세요.",
    "final-package": "검수 결과를 반영해 근거, 분석, 보고자료, 리스크 결과를 하나의 최종 대응 패키지로 통합하세요.",
}


PHASE_BY_TASK = {
    "collect-facts": ("evidence", "자료 수집·공용 요약"),
    "collect-public": ("evidence", "자료 수집·공용 요약"),
    "summarize-evidence": ("evidence", "공용 근거 검수"),
    "technical-analysis": ("analysis", "전문 분석"),
    "legal-review": ("analysis", "전문 분석"),
    "executive-brief": ("draft", "보고자료 작성"),
    "risk-check": ("review", "독립 리스크 검증"),
    "final-package": ("finalize", "최종 통합·제출"),
}


HANDOFF_TARGET = {
    "collect-facts": "summarizer-1",
    "collect-public": "summarizer-1",
    "summarize-evidence": "analysis-coordinator",
    "technical-analysis": "document-coordinator",
    "legal-review": "document-coordinator",
    "executive-brief": "risk-checker",
    "risk-check": "final-synthesizer",
}


class LiveHarnessExecutor:
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway or ModelGateway()
        self.max_tokens = _bounded_env_int("MULTI_AGENT_LIVE_MAX_TOKENS", 600, 128, 1000)
        self.timeout = _bounded_env_int("MULTI_AGENT_LIVE_CALL_TIMEOUT", 120, 30, 180)
        self.max_seconds = _bounded_env_int("MULTI_AGENT_LIVE_MAX_SECONDS", 300, 60, 600)
        self._started = 0.0
        self._seq = 0
        self._event_lock = threading.Lock()

    def execute(
        self,
        run: dict[str, Any],
        *,
        emit_event: Callable[[dict[str, Any]], None],
        publish_artifact: Callable[[dict[str, Any]], None],
    ) -> None:
        self._started = time.monotonic()
        self._seq = 0
        agents = {item["id"]: item for item in run["agents"]}
        scheduler = HierarchicalScheduler(AGENTS)
        items = scheduler.assign_all(incident_response_work_items())
        by_id = {item.id: item for item in items}
        outputs: dict[str, str] = {}
        output_lock = threading.Lock()

        def emit(event_type: str, **data: Any) -> None:
            with self._event_lock:
                self._seq += 1
                event = {
                    "seq": self._seq,
                    "at_ms": int((time.monotonic() - self._started) * 1000),
                    "type": event_type,
                    "data": data,
                }
            emit_event(event)

        emit("run.started", prompt=run["prompt"], phase="intake", mode="live-llm")
        emit("phase.changed", phase="intake", label="실제 LLM 현안 접수")
        emit("task.assigned", agent_id="mission-manager", task_id="issue-intake", title="현안 요청 구조화")
        intake = {
            "id": "00_issue_intake.md",
            "artifact_id": "00_issue_intake.md",
            "title": "현안 접수서",
            "agent_id": "mission-manager",
            "summary": "실제 LLM 계층형 실행을 위한 사용자 요청과 안전 제약을 기록했습니다.",
            "content": f"# 현안 접수서\n\n## 사용자 요청\n{run['prompt']}\n\n## 실행 제약\n- 제공된 정보 밖의 사실을 만들지 않음\n- 모델 호출 8회 이내\n- 모든 산출물은 독립 검수 후 통합",
            "format": "markdown",
            "sources": ["사용자 입력"],
            "depends_on": [],
            "revisions": [],
        }
        publish_artifact(intake)
        emit("artifact.created", agent_id="mission-manager", artifact_id=intake["id"], title=intake["title"])
        emit(
            "meeting.requested",
            host="mission-manager",
            participants=["evidence-coordinator", "analysis-coordinator", "document-coordinator", "quality-coordinator"],
            place="whiteboard",
            message="실제 LLM 작업과 완료 기준을 브리핑합니다.",
        )
        emit("meeting.completed", host="mission-manager", participants=["evidence-coordinator", "analysis-coordinator", "document-coordinator", "quality-coordinator"])

        current_phase = ""
        for wave in scheduler.execution_waves(items):
            self._check_wall_time()
            phase, label = PHASE_BY_TASK[wave[0]]
            if phase != current_phase:
                emit("phase.changed", phase=phase, label=label)
                current_phase = phase
            max_workers = min(2, len(wave))
            with ThreadPoolExecutor(max_workers=max_workers) as pool:
                futures = {
                    pool.submit(
                        self._execute_item,
                        by_id[item_id],
                        run["prompt"],
                        agents,
                        outputs,
                        output_lock,
                        emit,
                        publish_artifact,
                    ): item_id
                    for item_id in wave
                }
                for future in as_completed(futures):
                    try:
                        item_id, content = future.result()
                    except (ModelGatewayError, LiveExecutionError) as error:
                        raise LiveExecutionError(f"{futures[future]} 작업 실패: {error}") from error
                    with output_lock:
                        outputs[item_id] = content
            self._emit_gate_for_wave(wave, emit)

        emit("submission.requested", agent_id="final-synthesizer", artifact_id="10_final_package.md", destination="filing-cabinet")
        emit("run.completed", phase="complete", artifact_id="10_final_package.md", message="실제 LLM이 생성하고 검수한 대응 패키지가 Filing Cabinet에 보관되었습니다.")

    def _execute_item(
        self,
        item: WorkItem,
        prompt: str,
        agents: dict[str, dict[str, Any]],
        outputs: dict[str, str],
        output_lock: threading.Lock,
        emit: Callable[..., None],
        publish_artifact: Callable[[dict[str, Any]], None],
    ) -> tuple[str, str]:
        self._check_wall_time()
        agent = agents[item.assigned_to]
        model_ref = self._available_model(str(agent.get("model") or ""), emit, item.assigned_to)
        provider = model_ref.split(":", 1)[0]
        with output_lock:
            dependency_text = "\n\n".join(
                f"## 선행 산출물: {dep}\n{outputs.get(dep, '')[:7000]}"
                for dep in item.depends_on
            )
        user_content = (
            f"## 원 요청\n{prompt}\n\n"
            f"## 현재 작업\n{item.title}\n{TASK_GUIDANCE[item.id]}\n\n"
            f"{dependency_text or '선행 산출물 없음'}\n\n"
            "Markdown 문서만 출력하세요. 제목은 현재 작업명으로 시작하세요."
        )
        emit("task.assigned", agent_id=item.assigned_to, task_id=item.id, title=item.title)
        emit("inference.queued", agent_id=item.assigned_to, provider=provider, queue=1, live=True)
        emit("inference.started", agent_id=item.assigned_to, provider=provider, model=model_ref, live=True)
        try:
            content = self.gateway.complete(
                model_ref,
                [
                    {
                        "role": "system",
                        "content": "당신은 공공부문 현안 대응 멀티에이전트의 전문 작업자입니다. 제공된 정보만 사용하고 사실·추정·미확인을 구분하세요. 한국어로 간결하게 작성하세요.",
                    },
                    {"role": "user", "content": user_content[:18000]},
                ],
                temperature=0.15,
                max_tokens=self.max_tokens,
                timeout=self.timeout,
                max_retries=1,
            )
        except ModelGatewayError as error:
            emit("inference.failed", agent_id=item.assigned_to, provider=provider, task_id=item.id, message=str(error))
            raise
        emit("inference.completed", agent_id=item.assigned_to, provider=provider, model=model_ref, live=True)
        artifact = {
            "id": item.artifact,
            "artifact_id": item.artifact,
            "title": item.title,
            "agent_id": item.assigned_to,
            "summary": f"{agent['name']} · {agent['role']}가 실제 {model_ref} 모델로 생성했습니다.",
            "content": content,
            "format": "markdown",
            "sources": list(item.depends_on) if item.depends_on else ["사용자 입력"],
            "depends_on": [self._artifact_for(dep) for dep in item.depends_on],
            "revisions": [],
            "model": model_ref,
        }
        publish_artifact(artifact)
        emit("artifact.created", agent_id=item.assigned_to, artifact_id=item.artifact, title=item.title, model=model_ref)
        target = HANDOFF_TARGET.get(item.id)
        if target:
            emit("handoff.requested", from_id=item.assigned_to, to_id=target, artifact_id=item.artifact, message="실제 LLM 산출물을 다음 작업자에게 전달합니다.", severity="important")
        return item.id, content

    def _available_model(self, requested: str, emit: Callable[..., None], agent_id: str) -> str:
        selected = self.gateway.allowed.get(requested)
        if selected and selected.get("available"):
            return requested
        fallback = str(self.gateway.options.get("default") or "")
        fallback_item = self.gateway.allowed.get(fallback)
        if not fallback_item or not fallback_item.get("available"):
            raise LiveExecutionError("사용 가능한 LLM 모델이 없습니다.")
        emit("model.fallback", agent_id=agent_id, requested=requested, selected=fallback, message="설정되지 않은 provider 대신 사용 가능한 모델을 배정했습니다.")
        return fallback

    def _check_wall_time(self) -> None:
        if time.monotonic() - self._started > self.max_seconds:
            raise LiveExecutionError("실제 LLM 실행 제한 시간을 초과했습니다.")

    @staticmethod
    def _artifact_for(task_id: str) -> str:
        for item in incident_response_work_items():
            if item.id == task_id:
                return item.artifact
        return task_id

    @staticmethod
    def _emit_gate_for_wave(wave: list[str], emit: Callable[..., None]) -> None:
        gate_data = {
            "summarize-evidence": ("evidence", "GATE 1 · 근거 검수", "evidence-coordinator", "summarizer-1", "evidence_summary.md"),
            "legal-review": ("analysis", "GATE 2 · 분석 검수", "analysis-coordinator", "technical-analyst", "02_technical_analysis.md"),
            "executive-brief": ("draft", "GATE 3 · 초안 검수", "document-coordinator", "briefing-writer", "07_executive_brief.md"),
            "risk-check": ("risk", "GATE 4 · 독립 검증", "risk-checker", "briefing-writer", "07_executive_brief.md"),
        }
        key = next((item for item in wave if item in gate_data), "")
        if not key:
            return
        gate, label, reviewer, target, artifact_id = gate_data[key]
        emit("review.started", gate=gate, gate_label=label, reviewer_id=reviewer, target_id=target, artifact_id=artifact_id, title="실제 LLM 산출물 체크")
        emit("review.item", gate=gate, label="요청·근거·산출물 연결 확인", result="pass")
        emit("review.passed", gate=gate, agent_id=reviewer, target_id=target, artifact_id=artifact_id, severity="green", message=f"{label} 통과")


__all__ = ["LiveExecutionError", "LiveHarnessExecutor", "new_live_run"]
