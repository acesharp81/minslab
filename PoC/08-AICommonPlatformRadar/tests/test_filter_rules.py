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


def test_it_audit_is_out_of_scope_even_when_ai_is_mentioned():
    result = evaluate_notice(title="AI 시스템 감리 및 챗봇 개선", text_excerpt="생성형 AI 기능을 개선한다")
    assert result.skip
    assert result.scope_status == "non_target"
    assert result.matched_exclude_keywords


def test_maintenance_only_is_out_of_scope_even_when_high_budget():
    result = evaluate_notice(title="정보시스템 유지관리", budget_amount=500_000_000)
    assert result.skip
    assert result.scope_status == "non_target"


@pytest.mark.parametrize("title", [
    "AI 기반 행정서비스 구축",
    "생성형 AI 업무지원 챗봇 개발 및 고도화",
    "NPU 기반 범정부 AI 서비스 구현",
    "차세대 정보시스템 구축 BPR/ISP 수립",
    "AI 행정서비스 구축방안 연구용역",
])
def test_construction_and_construction_planning_are_in_scope(title):
    result = evaluate_notice(title=title)
    assert not result.skip
    assert result.scope_status == "target"


@pytest.mark.parametrize("title", [
    "생성형 AI 정보시스템 감리 용역",
    "AI 대응서비스 구축 및 실증 위탁감리(통합)",
    "공공부문 AI 활용지표 발굴 용역",
    "생성형 AI 역량강화 연수 운영",
    "AI 교육훈련 과정 운영 용역",
    "공공기관 AI 활용 컨설팅",
    "지능형기술 분야 조직분석 기준 연구용역",
    "관광 AI 거버넌스 및 민관 협력체계 구축 방안 연구용역",
])
def test_non_construction_ai_services_are_out_of_scope(title):
    result = evaluate_notice(title=title)
    assert result.skip
    assert result.score == 0
    assert result.scope_status == "non_target"
