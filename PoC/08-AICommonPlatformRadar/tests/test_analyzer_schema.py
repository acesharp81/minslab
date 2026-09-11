import pytest
from pydantic import ValidationError

from app.schemas import DeepAnalysis
from app.services.analyzer import validate_grounded


def valid_payload():
    return {
        "final_grade": "B", "ai_relevance": "high", "common_platform_fit": "high",
        "usage_mentioned": "unclear", "possible_common_platform_functions": ["LLM API"],
        "summary": "활용 여부 확인 필요", "evidence": [{"quote": "생성형 AI 구축", "section": "3장", "interpretation": "AI 사업"}],
        "check_questions": ["공통기반 검토 여부 확인 필요"], "recommended_action": "contact",
        "priority_score": 88, "confidence": 0.8, "caveats": [],
    }


def test_valid_deep_schema_and_grounding():
    model = DeepAnalysis.model_validate(valid_payload())
    assert validate_grounded(model, "과업은 생성형 AI 구축을 포함한다") == model


def test_actionable_grade_requires_evidence():
    payload = valid_payload()
    payload["evidence"] = []
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_uncertain_grade_requires_questions():
    payload = valid_payload()
    payload["check_questions"] = []
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_priority_range():
    payload = valid_payload()
    payload["priority_score"] = 101
    with pytest.raises(ValidationError):
        DeepAnalysis.model_validate(payload)


def test_fabricated_quote_is_rejected():
    model = DeepAnalysis.model_validate(valid_payload())
    with pytest.raises(ValueError):
        validate_grounded(model, "전혀 다른 원문")


def test_public_notice_metadata_is_valid_grounding_source():
    payload = valid_payload()
    payload["evidence"] = [{"quote": "생성형 AI 구축", "section": "사업명", "interpretation": "AI 사업"}]
    model = DeepAnalysis.model_validate(payload)
    assert validate_grounded(model, "사업명: 생성형 AI 구축\n추출 본문:\n세부 과업 확인") == model
