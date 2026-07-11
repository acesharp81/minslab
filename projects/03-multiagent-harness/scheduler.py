"""계층형 업무 DAG와 공용 에이전트 풀의 결정적 라우터."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from harness_engine import AgentDefinition


class SchedulerError(ValueError):
    pass


@dataclass
class WorkItem:
    id: str
    title: str
    capability: str
    coordinator_id: str
    depends_on: tuple[str, ...] = ()
    artifact: str = ""
    assigned_to: str = ""
    status: str = "todo"
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RunBudget:
    max_remote_calls: int = 12
    max_rework_rounds: int = 1
    max_wall_seconds: int = 600
    max_estimated_cost_usd: float = 1.0


class CapabilityRouter:
    """역할이 아니라 capability를 기준으로 가장 덜 배정된 에이전트를 선택한다."""

    def __init__(self, agents: Iterable[AgentDefinition]) -> None:
        self.agents = list(agents)
        self.assignment_counts = {agent.id: 0 for agent in self.agents}

    def assign(self, item: WorkItem) -> str:
        candidates = [agent for agent in self.agents if agent.capability == item.capability]
        if not candidates:
            raise SchedulerError(f"capability '{item.capability}'를 처리할 에이전트가 없습니다.")
        selected = min(candidates, key=lambda agent: (self.assignment_counts[agent.id], agent.id))
        self.assignment_counts[selected.id] += 1
        item.assigned_to = selected.id
        return selected.id


class HierarchicalScheduler:
    def __init__(self, agents: Iterable[AgentDefinition], budget: RunBudget | None = None) -> None:
        self.agents = list(agents)
        self.router = CapabilityRouter(self.agents)
        self.budget = budget or RunBudget()

    @staticmethod
    def validate(items: Iterable[WorkItem]) -> None:
        work = list(items)
        ids = [item.id for item in work]
        if len(ids) != len(set(ids)):
            raise SchedulerError("작업 ID가 중복됐습니다.")
        known = set(ids)
        for item in work:
            unknown = [dep for dep in item.depends_on if dep not in known]
            if unknown:
                raise SchedulerError(f"작업 '{item.id}'의 알 수 없는 의존성: {unknown}")
        remaining = {item.id: set(item.depends_on) for item in work}
        while remaining:
            ready = [item_id for item_id, deps in remaining.items() if not deps]
            if not ready:
                raise SchedulerError("작업 의존성에 순환이 있습니다.")
            for item_id in ready:
                remaining.pop(item_id)
            for deps in remaining.values():
                deps.difference_update(ready)

    def assign_all(self, items: list[WorkItem]) -> list[WorkItem]:
        self.validate(items)
        for item in items:
            if not item.assigned_to:
                self.router.assign(item)
        return items

    @staticmethod
    def execution_waves(items: Iterable[WorkItem]) -> list[list[str]]:
        work = list(items)
        HierarchicalScheduler.validate(work)
        remaining = {item.id: set(item.depends_on) for item in work}
        completed: set[str] = set()
        waves: list[list[str]] = []
        while remaining:
            ready = sorted(item_id for item_id, deps in remaining.items() if deps.issubset(completed))
            waves.append(ready)
            for item_id in ready:
                remaining.pop(item_id)
                completed.add(item_id)
        return waves

    def plan(self, items: list[WorkItem]) -> dict:
        assigned = self.assign_all(items)
        return {
            "items": [asdict(item) for item in assigned],
            "waves": self.execution_waves(assigned),
            "budget": asdict(self.budget),
            "assignment_counts": dict(self.router.assignment_counts),
        }


def incident_response_work_items() -> list[WorkItem]:
    return [
        WorkItem("collect-facts", "장애 사실관계 수집", "collect", "evidence-coordinator", artifact="01_fact_timeline.md"),
        WorkItem("collect-public", "민원·언론 쟁점 수집", "collect", "evidence-coordinator", artifact="04_public_sentiment.md"),
        WorkItem("summarize-evidence", "공용 근거 요약", "summarize", "evidence-coordinator", depends_on=("collect-facts", "collect-public"), artifact="evidence_summary.md"),
        WorkItem("technical-analysis", "기술 원인·조치 분석", "technical_analysis", "analysis-coordinator", depends_on=("summarize-evidence",), artifact="02_technical_analysis.md"),
        WorkItem("legal-review", "법령·제도 검토", "legal_review", "analysis-coordinator", depends_on=("summarize-evidence",), artifact="03_legal_policy_review.md"),
        WorkItem("executive-brief", "실장급 보고자료 작성", "write_briefing", "document-coordinator", depends_on=("technical-analysis", "legal-review"), artifact="07_executive_brief.md"),
        WorkItem("risk-check", "사실·법령·표현 교차검증", "risk_check", "quality-coordinator", depends_on=("executive-brief",), artifact="09_risk_check.md"),
        WorkItem("final-package", "현안 대응 패키지 통합", "synthesize", "quality-coordinator", depends_on=("risk-check",), artifact="10_final_package.md"),
    ]
