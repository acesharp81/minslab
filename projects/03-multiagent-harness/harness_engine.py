"""계층형 멀티에이전트 하네스의 도메인 모델과 결정적 데모 실행기."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from artifact_catalog import build_artifact_catalog


@dataclass(frozen=True)
class ModelPolicy:
    provider: str
    model: str
    max_in_flight: int
    label: str

    @property
    def value(self) -> str:
        return f"{self.provider}:{self.model}"


@dataclass(frozen=True)
class AgentDefinition:
    id: str
    name: str
    role: str
    layer: str
    team: str
    capability: str
    model: str
    home: tuple[int, int]
    color: str
    pool: str = ""


@dataclass(frozen=True)
class PoolDefinition:
    id: str
    label: str
    capability: str
    replicas: int
    agent_ids: tuple[str, ...]


@dataclass(frozen=True)
class HarnessEvent:
    seq: int
    at_ms: int
    type: str
    data: dict[str, Any] = field(default_factory=dict)


DEFAULT_MODELS = (
    ModelPolicy("ollama", "qwen2.5:1.5b", 1, "Local LLM · qwen2.5:1.5b"),
    ModelPolicy(
        "huggingface",
        "Qwen/Qwen2.5-72B-Instruct",
        1,
        "Hugging Face · Qwen2.5-72B-Instruct",
    ),
    ModelPolicy(
        "openrouter",
        "openai/gpt-4o-mini",
        2,
        "OpenRouter · gpt-4o-mini",
    ),
)


AGENTS = (
    AgentDefinition("mission-manager", "한결", "Mission Manager", "manager", "command", "orchestrate", "openrouter:openai/gpt-4o-mini", (780, 112), "#ffd166"),
    AgentDefinition("evidence-coordinator", "서린", "Evidence Coordinator", "coordinator", "evidence", "coordinate_evidence", "openrouter:openai/gpt-4o-mini", (145, 155), "#69d2e7"),
    AgentDefinition("analysis-coordinator", "도윤", "Analysis Coordinator", "coordinator", "analysis", "coordinate_analysis", "openrouter:openai/gpt-4o-mini", (370, 155), "#7bd389"),
    AgentDefinition("document-coordinator", "나래", "Document Coordinator", "coordinator", "document", "coordinate_document", "openrouter:openai/gpt-4o-mini", (560, 330), "#cdb4db"),
    AgentDefinition("quality-coordinator", "태오", "Quality Coordinator", "coordinator", "quality", "coordinate_quality", "openrouter:openai/gpt-4o-mini", (760, 330), "#ff8fab"),
    AgentDefinition("collector-1", "수집A", "Fact Collector", "worker", "shared", "collect", "openrouter:openai/gpt-4o-mini", (115, 285), "#4cc9f0", "collector-pool"),
    AgentDefinition("collector-2", "수집B", "Fact Collector", "worker", "shared", "collect", "huggingface:Qwen/Qwen2.5-72B-Instruct", (225, 285), "#4895ef", "collector-pool"),
    AgentDefinition("summarizer-1", "요약A", "Shared Summarizer", "worker", "shared", "summarize", "ollama:qwen2.5:1.5b", (285, 420), "#4361ee", "summarizer-pool"),
    AgentDefinition("technical-analyst", "기술", "Technical Analyst", "worker", "analysis", "technical_analysis", "huggingface:Qwen/Qwen2.5-72B-Instruct", (390, 285), "#80ed99"),
    AgentDefinition("legal-reviewer", "법제", "Legal Policy Reviewer", "worker", "analysis", "legal_review", "openrouter:openai/gpt-4o-mini", (490, 285), "#57cc99"),
    AgentDefinition("briefing-writer", "보고", "Briefing Writer", "worker", "document", "write_briefing", "openrouter:openai/gpt-4o-mini", (560, 445), "#b8c0ff"),
    AgentDefinition("risk-checker", "검증", "Risk Checker", "worker", "quality", "risk_check", "openrouter:openai/gpt-4o-mini", (680, 445), "#ff7096"),
    AgentDefinition("final-synthesizer", "통합", "Final Synthesizer", "worker", "quality", "synthesize", "openrouter:openai/gpt-4o-mini", (790, 445), "#f15bb5"),
)


POOLS = (
    PoolDefinition("collector-pool", "Collector Pool", "collect", 2, ("collector-1", "collector-2")),
    PoolDefinition("summarizer-pool", "Summarizer Pool", "summarize", 1, ("summarizer-1",)),
)


class DemoTimeline:
    def __init__(self) -> None:
        self.events: list[HarnessEvent] = []

    def emit(self, at_ms: int, event_type: str, **data: Any) -> None:
        self.events.append(
            HarnessEvent(
                seq=len(self.events) + 1,
                at_ms=at_ms,
                type=event_type,
                data=data,
            )
        )

    def build(self) -> list[dict[str, Any]]:
        self.events.sort(key=lambda item: (item.at_ms, item.seq))
        return [asdict(event) for event in self.events]


def _build_events(prompt: str) -> list[dict[str, Any]]:
    timeline = DemoTimeline()
    emit = timeline.emit

    emit(0, "run.started", prompt=prompt, phase="intake")
    emit(250, "phase.changed", phase="intake", label="현안 접수")
    emit(550, "task.assigned", agent_id="mission-manager", task_id="issue-intake", title="현안 요청 구조화")
    emit(900, "agent.status", agent_id="mission-manager", status="working", message="현안의 목표·제약·산출물을 정리합니다.")
    emit(1450, "artifact.created", agent_id="mission-manager", artifact_id="00_issue_intake.md", title="현안 접수서")
    emit(1750, "phase.changed", phase="decompose", label="계층형 업무 분해")
    emit(2050, "meeting.requested", host="mission-manager", participants=["evidence-coordinator", "analysis-coordinator", "document-coordinator", "quality-coordinator"], place="whiteboard", message="팀별 임무와 완료 기준을 브리핑합니다.")
    emit(3600, "meeting.completed", host="mission-manager", participants=["evidence-coordinator", "analysis-coordinator", "document-coordinator", "quality-coordinator"])

    emit(3900, "phase.changed", phase="evidence", label="자료 수집·공용 요약")
    emit(4100, "task.assigned", agent_id="collector-1", task_id="collect-timeline", title="장애 타임라인 수집")
    emit(4200, "task.assigned", agent_id="collector-2", task_id="collect-impact", title="영향·민원 쟁점 수집")
    emit(4400, "inference.queued", agent_id="collector-1", provider="openrouter", queue=1)
    emit(4500, "inference.queued", agent_id="collector-2", provider="huggingface", queue=1)
    emit(4800, "inference.started", agent_id="collector-1", provider="openrouter", slot=1)
    emit(4900, "inference.started", agent_id="collector-2", provider="huggingface", slot=1)
    emit(6200, "inference.completed", agent_id="collector-1", provider="openrouter")
    emit(6300, "artifact.created", agent_id="collector-1", artifact_id="01_fact_timeline.md", title="사실관계·타임라인")
    emit(6500, "inference.completed", agent_id="collector-2", provider="huggingface")
    emit(6600, "artifact.created", agent_id="collector-2", artifact_id="04_public_sentiment.md", title="민원·언론 쟁점")
    emit(6800, "handoff.requested", from_id="collector-1", to_id="summarizer-1", artifact_id="01_fact_timeline.md", message="확인 사실과 미확인 사항을 요약해 주세요.", severity="important")
    emit(7000, "handoff.requested", from_id="collector-2", to_id="summarizer-1", artifact_id="04_public_sentiment.md", message="대외 쟁점을 공용 브리프로 합쳐 주세요.", severity="important")
    emit(9200, "inference.queued", agent_id="summarizer-1", provider="ollama", queue=1)
    emit(9500, "inference.started", agent_id="summarizer-1", provider="ollama", slot=1)
    emit(11100, "inference.completed", agent_id="summarizer-1", provider="ollama")
    emit(11200, "artifact.created", agent_id="summarizer-1", artifact_id="evidence_summary.md", title="공용 근거 요약")
    emit(11400, "handoff.requested", from_id="summarizer-1", to_id="analysis-coordinator", artifact_id="evidence_summary.md", message="분석팀 공용 근거 요약을 전달합니다.", severity="important")
    emit(11800, "review.started", gate="evidence", gate_label="GATE 1 · 근거 검수", reviewer_id="evidence-coordinator", target_id="summarizer-1", artifact_id="evidence_summary.md", title="근거 완전성 체크")
    emit(12100, "review.item", gate="evidence", label="출처와 확인 시각 표기", result="pass")
    emit(12400, "review.item", gate="evidence", label="사실·추정·미확인 분리", result="pass")
    emit(12800, "review.passed", gate="evidence", agent_id="evidence-coordinator", target_id="summarizer-1", artifact_id="evidence_summary.md", severity="green", message="근거 요약이 분석 단계 진입 기준을 충족했습니다.")

    emit(13700, "phase.changed", phase="analysis", label="전문 분석")
    emit(13900, "task.assigned", agent_id="technical-analyst", task_id="technical-analysis", title="기술 원인·조치 분석")
    emit(14000, "task.assigned", agent_id="legal-reviewer", task_id="legal-review", title="법령·제도 검토")
    emit(14300, "inference.queued", agent_id="technical-analyst", provider="huggingface", queue=1)
    emit(14400, "inference.queued", agent_id="legal-reviewer", provider="openrouter", queue=1)
    emit(14700, "inference.started", agent_id="technical-analyst", provider="huggingface", slot=1)
    emit(14800, "inference.started", agent_id="legal-reviewer", provider="openrouter", slot=1)
    emit(16700, "inference.completed", agent_id="technical-analyst", provider="huggingface")
    emit(16800, "artifact.created", agent_id="technical-analyst", artifact_id="02_technical_analysis.md", title="기술 분석")
    emit(17100, "inference.completed", agent_id="legal-reviewer", provider="openrouter")
    emit(17200, "artifact.created", agent_id="legal-reviewer", artifact_id="03_legal_policy_review.md", title="법령·제도 검토")
    emit(17400, "review.started", gate="analysis", gate_label="GATE 2 · 분석 검수", reviewer_id="analysis-coordinator", target_id="technical-analyst", artifact_id="02_technical_analysis.md", title="교차 분석 체크")
    emit(17700, "review.item", gate="analysis", label="기술 근거와 조치 연결", result="pass")
    emit(18000, "review.item", gate="analysis", label="법령 해석 한계 고지", result="pass")
    emit(18400, "review.passed", gate="analysis", agent_id="analysis-coordinator", target_id="technical-analyst", artifact_id="02_technical_analysis.md", severity="green", message="기술·법제 분석의 교차검수를 통과했습니다.")
    emit(18700, "handoff.requested", from_id="technical-analyst", to_id="document-coordinator", artifact_id="02_technical_analysis.md", message="원인 단정 없이 기술 분석을 전달합니다.", severity="important")
    emit(19000, "handoff.requested", from_id="legal-reviewer", to_id="document-coordinator", artifact_id="03_legal_policy_review.md", message="법률 자문이 아닌 검토 초안을 전달합니다.", severity="important")

    emit(20400, "phase.changed", phase="draft", label="보고자료 작성")
    emit(20600, "task.assigned", agent_id="briefing-writer", task_id="executive-brief", title="실장급 보고자료 작성")
    emit(20900, "inference.queued", agent_id="briefing-writer", provider="openrouter", queue=1)
    emit(21200, "inference.started", agent_id="briefing-writer", provider="openrouter", slot=1)
    emit(23200, "inference.completed", agent_id="briefing-writer", provider="openrouter")
    emit(23300, "artifact.created", agent_id="briefing-writer", artifact_id="07_executive_brief.md", title="실장급 보고자료")
    emit(23500, "review.started", gate="draft", gate_label="GATE 3 · 초안 검수", reviewer_id="document-coordinator", target_id="briefing-writer", artifact_id="07_executive_brief.md", title="보고자료 품질 체크")
    emit(23800, "review.item", gate="draft", label="핵심 메시지와 근거 링크", result="pass")
    emit(24100, "review.item", gate="draft", label="의사결정 요청사항 명료성", result="pass")
    emit(24500, "review.passed", gate="draft", agent_id="document-coordinator", target_id="briefing-writer", artifact_id="07_executive_brief.md", severity="green", message="초안 검수를 통과해 독립 리스크 검증으로 이동합니다.")
    emit(24800, "handoff.requested", from_id="briefing-writer", to_id="risk-checker", artifact_id="07_executive_brief.md", message="중간 검수를 통과한 초안의 사실·표현 리스크를 검토해 주세요.", severity="important")

    emit(26000, "phase.changed", phase="review", label="리스크 검증")
    emit(26200, "task.assigned", agent_id="risk-checker", task_id="risk-check", title="사실·법령·표현 교차검증")
    emit(26500, "inference.queued", agent_id="risk-checker", provider="openrouter", queue=1)
    emit(26800, "inference.started", agent_id="risk-checker", provider="openrouter", slot=1)
    emit(27100, "review.started", gate="risk", gate_label="GATE 4 · 독립 검증", reviewer_id="risk-checker", target_id="briefing-writer", artifact_id="07_executive_brief.md", title="사실·법령·표현 교차검증")
    emit(27500, "review.item", gate="risk", label="수치·시각·출처 일치", result="pass")
    emit(27900, "review.item", gate="risk", label="법령 인용과 면책 문구", result="pass")
    emit(28200, "review.item", gate="risk", label="확정되지 않은 원인 단정", result="fail")
    emit(28400, "inference.completed", agent_id="risk-checker", provider="openrouter")
    emit(28600, "review.failed", gate="risk", agent_id="risk-checker", target_id="briefing-writer", artifact_id="07_executive_brief.md", severity="red", message="확정되지 않은 장애 원인 표현 1건을 수정해야 합니다.")
    emit(28800, "handoff.requested", from_id="risk-checker", to_id="briefing-writer", artifact_id="07_executive_brief.md", message="필수 수정 1건을 반송합니다.", severity="red")
    emit(31400, "task.rework", agent_id="briefing-writer", task_id="executive-brief", title="원인 표현 수정")
    emit(31800, "inference.started", agent_id="briefing-writer", provider="openrouter", slot=1)
    emit(33100, "inference.completed", agent_id="briefing-writer", provider="openrouter")
    emit(33300, "artifact.revised", agent_id="briefing-writer", artifact_id="07_executive_brief.md", revision=2)
    emit(33500, "handoff.requested", from_id="briefing-writer", to_id="risk-checker", artifact_id="07_executive_brief.md", message="단정 표현을 수정해 재검토를 요청합니다.", severity="important")
    emit(34100, "review.started", gate="risk", gate_label="GATE 4 · 재검수", reviewer_id="risk-checker", target_id="briefing-writer", artifact_id="07_executive_brief.md", title="수정사항 재검수")
    emit(34800, "review.item", gate="risk", label="원인 표현을 조사 중으로 수정", result="pass")
    emit(35400, "review.item", gate="risk", label="필수 수정 이력 추적", result="pass")
    emit(36000, "review.passed", gate="risk", agent_id="risk-checker", target_id="briefing-writer", artifact_id="07_executive_brief.md", severity="green", message="필수 수정 반영을 확인했습니다.")
    emit(36200, "artifact.created", agent_id="risk-checker", artifact_id="09_risk_check.md", title="리스크 검토 결과")
    emit(36500, "handoff.requested", from_id="risk-checker", to_id="final-synthesizer", artifact_id="09_risk_check.md", message="검증 통과 산출물을 최종 통합해 주세요.", severity="important")

    emit(39200, "phase.changed", phase="finalize", label="최종 통합·제출")
    emit(39400, "task.assigned", agent_id="final-synthesizer", task_id="final-package", title="현안 대응 패키지 통합")
    emit(39700, "inference.queued", agent_id="final-synthesizer", provider="openrouter", queue=1)
    emit(40000, "inference.started", agent_id="final-synthesizer", provider="openrouter", slot=1)
    emit(42000, "inference.completed", agent_id="final-synthesizer", provider="openrouter")
    emit(42200, "artifact.created", agent_id="final-synthesizer", artifact_id="10_final_package.md", title="현안 대응 패키지")
    emit(42500, "submission.requested", agent_id="final-synthesizer", artifact_id="10_final_package.md", destination="filing-cabinet")
    emit(45200, "run.completed", phase="complete", artifact_id="10_final_package.md", message="검증된 현안 대응 패키지가 Filing Cabinet에 보관되었습니다.")
    return timeline.build()


def build_demo_run(prompt: str) -> dict[str, Any]:
    clean_prompt = " ".join(str(prompt or "").split())
    if not clean_prompt:
        clean_prompt = "가상 공공서비스 예약시스템 장애 현안 대응 패키지를 생성해 주세요."
    if len(clean_prompt) > 4000:
        raise ValueError("데모 요청은 4,000자를 넘을 수 없습니다.")

    return {
        "run_id": str(uuid.uuid4()),
        "mode": "deterministic-demo",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "prompt": clean_prompt,
        "agents": [asdict(agent) for agent in AGENTS],
        "pools": [asdict(pool) for pool in POOLS],
        "models": [
            {**asdict(model), "value": model.value}
            for model in DEFAULT_MODELS
        ],
        "events": _build_events(clean_prompt),
        "artifacts": build_artifact_catalog(clean_prompt),
        "limits": {
            "max_concurrent_runs": 1,
            "provider_slots": {model.provider: model.max_in_flight for model in DEFAULT_MODELS},
            "max_rework_rounds": 1,
        },
    }


def harness_config() -> dict[str, Any]:
    return {
        "agents": [asdict(agent) for agent in AGENTS],
        "pools": [asdict(pool) for pool in POOLS],
        "models": [{**asdict(model), "value": model.value} for model in DEFAULT_MODELS],
        "phases": [
            {"id": "intake", "label": "현안 접수"},
            {"id": "decompose", "label": "업무 분해"},
            {"id": "evidence", "label": "자료 수집·요약"},
            {"id": "analysis", "label": "전문 분석"},
            {"id": "draft", "label": "보고자료 작성"},
            {"id": "review", "label": "리스크 검증"},
            {"id": "finalize", "label": "최종 통합"},
        ],
    }
