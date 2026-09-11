import pytest

from app.services.filter_rules import evaluate_notice


@pytest.mark.parametrize("title", [
    "AI 상담 서비스 구축", "인공지능 학습 플랫폼", "생성형 업무지원", "LLM 기반 검색",
    "RAG 지식관리", "지능형 관제", "빅데이터 분석", "GPU 인프라", "챗봇 고도화",
])
def test_include_candidates(title):
    result = evaluate_notice(title=title)
    assert not result.skip
    assert result.score > 0


@pytest.mark.parametrize("title", ["청사 청소 용역", "회계감사 용역", "인쇄 제작", "시설관리 위탁", "행사 운영"])
def test_clear_exclusions(title):
    result = evaluate_notice(title=title, budget_amount=10_000_000)
    assert result.skip


def test_exclusion_never_overrides_ai_evidence():
    result = evaluate_notice(title="AI 시스템 감리 및 챗봇 개선", text_excerpt="생성형 AI 기능을 개선한다")
    assert not result.skip
    assert result.matched_exclude_keywords


def test_high_budget_is_sampled():
    result = evaluate_notice(title="정보시스템 유지관리", budget_amount=500_000_000)
    assert not result.skip
    assert result.needs_sample_review

