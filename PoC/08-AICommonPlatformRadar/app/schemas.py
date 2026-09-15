from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Evidence(BaseModel):
    quote: str = Field(min_length=1, max_length=1200)
    section: str = Field(default="위치 미확인", max_length=300)
    interpretation: str = Field(default="AI 기능 관련 근거", max_length=1000)


class SimpleAnalysis(BaseModel):
    ai_relevance: Literal["high", "medium", "low"]
    needs_deep_review: bool
    reason: str = Field(min_length=1, max_length=1500)
    evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    confidence: float = Field(ge=0, le=1)

    @field_validator("evidence", mode="before")
    @classmethod
    def trim_excess_evidence(cls, value):
        # 공급자가 프롬프트의 최대 개수를 넘겨도 유효한 상위 근거는 보존한다.
        return value[:10] if isinstance(value, list) else value



class CompactDeepAnalysis(BaseModel):
    """Provider-friendly facts; the server expands these into the full audit schema."""

    ai_relevance: Literal["high", "medium", "low"]
    network_scope: Literal["internal_or_connected", "hybrid", "external_complete", "unclear"]
    network_reason: str = Field(min_length=1, max_length=1000)
    network_quotes: list[str] = Field(max_length=3)
    task_scope: Literal[
        "government", "delegated_government", "public_institution_internal", "non_government", "unclear"
    ]
    task_scope_reason: str = Field(min_length=1, max_length=1000)
    task_scope_quotes: list[str] = Field(max_length=3)
    model_fit: Literal["platform_llm_or_rag", "custom_model_or_full_finetuning", "unclear"]
    model_fit_reason: str = Field(min_length=1, max_length=1000)
    model_fit_quotes: list[str] = Field(max_length=3)
    platform_usage: Literal["uses", "not_used", "not_mentioned", "unclear"]
    platform_usage_reason: str = Field(min_length=1, max_length=1000)
    platform_usage_quotes: list[str] = Field(max_length=3)
    remediation_feasibility: Literal["feasible", "not_feasible", "unclear", "not_needed"]
    remediation_targets: list[Literal["network", "model"]] = Field(max_length=2)
    remediation_reason: str = Field(min_length=1, max_length=1000)
    remediation_quotes: list[str] = Field(max_length=3)
    possible_common_platform_functions: list[str] = Field(max_length=10)
    summary: str = Field(min_length=1, max_length=2000)
    confidence: float = Field(ge=0, le=1)

    @field_validator(
        "network_quotes", "task_scope_quotes", "model_fit_quotes",
        "platform_usage_quotes", "remediation_quotes", mode="before",
    )
    @classmethod
    def trim_quotes(cls, value):
        return value[:3] if isinstance(value, list) else value

    @field_validator("remediation_targets", mode="before")
    @classmethod
    def trim_targets(cls, value):
        return value[:2] if isinstance(value, list) else value

    @field_validator("possible_common_platform_functions", mode="before")
    @classmethod
    def trim_functions(cls, value):
        return value[:10] if isinstance(value, list) else value


class DeepAnalysis(BaseModel):
    criteria_version: Literal["common-platform-v3-six-categories"] = "common-platform-v3-six-categories"
    classification_code: Literal["1", "2", "3", "4", "5", "6"]
    final_grade: Literal["A", "B", "C", "D", "E"]
    ai_relevance: Literal["high", "medium", "low"]
    common_platform_fit: Literal["high", "partial", "uncertain", "low"]
    usage_mentioned: Literal["yes", "no", "unclear"]
    network_scope: Literal["internal_or_connected", "hybrid", "external_complete", "unclear"]
    network_reason: str = Field(min_length=1, max_length=1500)
    network_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    task_scope: Literal[
        "government", "delegated_government", "public_institution_internal", "non_government", "unclear"
    ]
    task_scope_reason: str = Field(min_length=1, max_length=1500)
    task_scope_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    model_fit: Literal["platform_llm_or_rag", "custom_model_or_full_finetuning", "unclear"]
    model_fit_reason: str = Field(min_length=1, max_length=1500)
    model_fit_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    platform_usage: Literal["uses", "not_used", "not_mentioned", "unclear"]
    platform_usage_reason: str = Field(min_length=1, max_length=1500)
    platform_usage_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    remediation_feasibility: Literal["feasible", "not_feasible", "unclear", "not_needed"]
    remediation_targets: list[Literal["network", "model"]] = Field(default_factory=list, max_length=2)
    remediation_reason: str = Field(min_length=1, max_length=1500)
    remediation_evidence: list[Evidence] = Field(default_factory=list, max_length=10)
    eligibility: Literal["eligible", "consultation_required", "ineligible", "uncertain"]
    possible_common_platform_functions: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    check_questions: list[str] = Field(default_factory=list, max_length=20)
    recommended_action: Literal["contact", "watch", "no_action", "manual_review"]
    priority_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    caveats: list[str] = Field(default_factory=list, max_length=20)
    guidance_message: str = Field(default="", max_length=4000)

    @field_validator("classification_code", mode="before")
    @classmethod
    def normalize_classification_code(cls, value):
        # LLM은 JSON 열거값을 문자열 또는 숫자로 반환할 수 있다.
        return str(value) if isinstance(value, int) and not isinstance(value, bool) else value

    @field_validator(
        "network_evidence", "task_scope_evidence", "model_fit_evidence",
        "platform_usage_evidence", "remediation_evidence",
        "possible_common_platform_functions", "evidence", "check_questions", "caveats",
        mode="before",
    )
    @classmethod
    def trim_excess_lists(cls, value, info):
        if not isinstance(value, list):
            return value
        maximum = 10 if info.field_name.endswith("_evidence") else 20
        return value[:maximum]

    @field_validator("evidence")
    @classmethod
    def evidence_required_for_actionable_grades(cls, value: list[Evidence], info):
        grade = info.data.get("final_grade")
        if grade in {"A", "B", "C"} and not value:
            raise ValueError("A/B/C 등급은 원문 근거가 필요합니다.")
        return value

    @field_validator("check_questions")
    @classmethod
    def questions_required_for_uncertain_grades(cls, value: list[str], info):
        grade = info.data.get("final_grade")
        if grade in {"B", "C", "D"} and not value:
            raise ValueError("B/C/D 등급은 확인 질문이 필요합니다.")
        return value

    @model_validator(mode="after")
    def definite_gate_values_require_grounded_evidence(self):
        checks = (
            (self.network_scope, self.network_evidence, "망 구성"),
            (self.task_scope, self.task_scope_evidence, "업무 범위"),
            (self.model_fit, self.model_fit_evidence, "모델 적합성"),
            (self.platform_usage, self.platform_usage_evidence, "공통기반 사용 여부"),
        )
        for value, evidence, label in checks:
            if value not in {"unclear", "not_mentioned"} and not evidence:
                raise ValueError(f"{label}을 확정하려면 원문 근거가 필요합니다.")
        if self.remediation_feasibility in {"feasible", "not_feasible"} and not self.remediation_evidence:
            raise ValueError("망·모델 변경 가능성을 확정하려면 원문 근거가 필요합니다.")
        if self.remediation_feasibility == "feasible" and not self.remediation_targets:
            raise ValueError("변경 가능 판정에는 network 또는 model 대상이 필요합니다.")
        return self


class ActionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["new", "reviewing", "contacted", "reflected", "not_reflected", "closed"] | None = None
    owner: str | None = Field(default=None, max_length=200)
    agency_response: str | None = Field(default=None, max_length=10000)
    saving_estimate: int | None = Field(default=None, ge=0)
    security_effect_note: str | None = Field(default=None, max_length=10000)
    memo: str | None = Field(default=None, max_length=10000)


class ReportRequest(BaseModel):
    report_date: date | None = None
