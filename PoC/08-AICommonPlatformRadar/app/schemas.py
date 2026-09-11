from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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


class DeepAnalysis(BaseModel):
    final_grade: Literal["A", "B", "C", "D", "E"]
    ai_relevance: Literal["high", "medium", "low"]
    common_platform_fit: Literal["high", "partial", "uncertain", "low"]
    usage_mentioned: Literal["yes", "no", "unclear"]
    possible_common_platform_functions: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=4000)
    evidence: list[Evidence] = Field(default_factory=list, max_length=20)
    check_questions: list[str] = Field(default_factory=list, max_length=20)
    recommended_action: Literal["contact", "watch", "no_action", "manual_review"]
    priority_score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    caveats: list[str] = Field(default_factory=list, max_length=20)

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
