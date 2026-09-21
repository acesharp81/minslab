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
    network_scope: Literal["internal_or_connected", "hybrid", "other_closed_network", "external_complete", "unclear"]
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
    criteria_version: Literal["common-platform-v7-service-construction-scope"] = "common-platform-v7-service-construction-scope"
    service_scope: Literal["target", "non_target", "unclear"] = "unclear"
    service_scope_reason: str = Field(default="", max_length=1500)
    classification_code: Literal["1", "2", "3", "4", "5", "6"]
    final_grade: Literal["A", "B", "C", "D", "E"]
    ai_relevance: Literal["high", "medium", "low"]
    common_platform_fit: Literal["high", "partial", "uncertain", "low"]
    usage_mentioned: Literal["yes", "no", "unclear"]
    network_scope: Literal["internal_or_connected", "hybrid", "other_closed_network", "external_complete", "unclear"]
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
    status: Literal[
        "new", "reviewing", "completed_non_ai", "in_progress", "completed_uses", "completed_not_used", "completed_ineligible",
        "contacted", "reflected", "not_reflected", "closed",
    ] | None = None
    owner: str | None = Field(default=None, max_length=200)
    agency_response: str | None = Field(default=None, max_length=10000)
    saving_estimate: int | None = Field(default=None, ge=0)
    security_effect_note: str | None = Field(default=None, max_length=10000)
    memo: str | None = Field(default=None, max_length=10000)
    ineligible_reason: Literal["national_task", "network_data", "specialized_model"] | None = None


class ReportRequest(BaseModel):
    report_date: date | None = None


DEFAULT_PLANNING_OPINION_TEMPLATE = """{greeting}

공개된 사전규격을 검토한 결과, 인공지능 도입·구축 방향을 수립하는 계획·ISP·연구용역으로 확인되었습니다. 향후 개별 구축사업이 관련 법(「인공지능데이터행정법」 제27조제2항)에 따라 범정부 인공지능 공통기반을 우선 검토할 수 있도록 계획 단계에서 반영할 필요가 있어 의견드립니다.

[분석 내용]

- AI 서비스 개요: {overview}
- 사용자: {user}
- 사용환경: {network}
- 사용모델: {model}

[검토 요청]
-「공공부문 AI 도입 및 활용 가이드」(NIA 누리집 nia.or.kr > 지식정보 > 간행물 > AI.gov)를 참조하여 공통기반 활용이 적정한지 판단

- 적정성이 확인되면 향후 사업이 '범정부 인공지능 공통기반'을 활용할 수 있도록 계획에 반영
  ※ 범정부 AI 공통기반은 내부(행정)망 또는 이와 연계된 망에서 모델과 RAG를 제공할 수 있으며, 자세한 서비스 내용은 대표전화 053-230-1938 / 대표 이메일 gov-ai@nia.or.kr로 연락 바랍니다."""


DEFAULT_CONSTRUCTION_OPINION_TEMPLATE = """{greeting}

공개된 사전규격을 검토한 결과, 인공지능 서비스를 도입·구축하는 사업으로 확인되었습니다. 관련 법(「인공지능데이터행정법」 제27조제2항)에 따라 범정부 인공지능 공통기반 활용을 적극 검토할 필요가 있어 의견드립니다.

[분석 내용]

- AI 서비스 개요: {overview}
- 사용자: {user}
- 사용환경: {network}
- 사용모델: {model}

[검토 요청]
-「공공부문 AI 도입 및 활용 가이드」(NIA 누리집 nia.or.kr > 지식정보 > 간행물 > AI.gov)를 참조하여 공통기반 활용이 적정한지 판단

- 적정성이 확인되면 '범정부 인공지능 공통기반'을 활용하여 서비스를 구축할 수 있도록 시스템 구성, 적용 기능 및 제안요청서 반영 방향 검토
  ※ 범정부 AI 공통기반은 내부(행정)망 또는 이와 연계된 망에서 모델과 RAG를 제공할 수 있으며, 자세한 서비스 내용은 대표전화 053-230-1938 / 대표 이메일 gov-ai@nia.or.kr로 연락 바랍니다."""


class OpinionSenderProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    organization: str = Field(default="행정안전부", min_length=1, max_length=120)
    responsibility: str = Field(default="범정부 인공지능공통기반", min_length=1, max_length=160)
    name: str = Field(default="", max_length=80)
    position: str = Field(default="", max_length=80)
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=160)
    opinion_type: str = Field(default="기타", max_length=80)
    other_opinion: str = Field(default="사업 계획", max_length=160)
    opinion_password: str = Field(default="", max_length=100)
    planning_template: str = Field(default=DEFAULT_PLANNING_OPINION_TEMPLATE, max_length=12000)
    construction_template: str = Field(default=DEFAULT_CONSTRUCTION_OPINION_TEMPLATE, max_length=12000)


class ClassificationErrorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=4000)


class NotificationSettingsPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    enabled: bool = False
    recipients: list[str] = Field(default_factory=list, max_length=100)
    smtp_host: str = Field(default="smtp.gmail.com", max_length=300)
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str = Field(default="", max_length=300)
    smtp_password: str = Field(default="", max_length=500)
    from_email: str = Field(default="", max_length=300)
    use_tls: bool = True


class AdminPasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=300)
    new_password: str = Field(min_length=8, max_length=300)
