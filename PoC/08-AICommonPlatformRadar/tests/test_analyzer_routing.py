from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import AnalysisRun, Attachment, Notice
from app.schemas import CompactDeepAnalysis, DeepAnalysis, Evidence, SimpleAnalysis
from app.services.analyzer import (
    ChatEndpoint,
    LLMRateLimitExceeded,
    OpenAIChatClient,
    RoutedAnalyzer,
    _truncate_context,
    _usage,
    analyze_notice,
    enforce_common_platform_gates,
    expand_compact_deep,
    preserve_deep_ai_scope,
)
from app.services.filter_rules import FilterResult


def _rule() -> FilterResult:
    return FilterResult(False, "AI 후보", 80, ["생성형 AI"], [], False)


def _simple() -> SimpleAnalysis:
    return SimpleAnalysis(
        ai_relevance="high",
        needs_deep_review=True,
        reason="생성형 AI 기능 확인",
        evidence=[Evidence(quote="생성형 AI 구축")],
        confidence=0.9,
    )


def _deep() -> DeepAnalysis:
    return DeepAnalysis(
        classification_code="5",
        final_grade="B",
        ai_relevance="high",
        common_platform_fit="high",
        usage_mentioned="unclear",
        network_scope="unclear",
        network_reason="망 구성 확인 필요",
        network_evidence=[],
        task_scope="unclear",
        task_scope_reason="국가사무 확인 필요",
        task_scope_evidence=[],
        model_fit="unclear",
        model_fit_reason="모델 확인 필요",
        model_fit_evidence=[],
        platform_usage="not_mentioned",
        platform_usage_reason="사용 문구 없음",
        platform_usage_evidence=[],
        remediation_feasibility="unclear",
        remediation_targets=[],
        remediation_reason="변경 가능성 확인 필요",
        remediation_evidence=[],
        eligibility="uncertain",
        possible_common_platform_functions=["LLM API"],
        summary="공통기반 활용 여부 확인 필요",
        evidence=[Evidence(quote="생성형 AI 구축")],
        check_questions=["공통기반 API 활용을 검토했는지 확인 필요"],
        recommended_action="contact",
        priority_score=88,
        confidence=0.8,
        caveats=[],
    )


def _compact(**updates) -> CompactDeepAnalysis:
    payload = {
        "ai_relevance": "high",
        "network_scope": "unclear",
        "network_reason": "망 근거 없음",
        "network_quotes": [],
        "task_scope": "unclear",
        "task_scope_reason": "업무 근거 없음",
        "task_scope_quotes": [],
        "model_fit": "unclear",
        "model_fit_reason": "모델 근거 없음",
        "model_fit_quotes": [],
        "platform_usage": "not_mentioned",
        "platform_usage_reason": "공통기반 언급 없음",
        "platform_usage_quotes": [],
        "remediation_feasibility": "unclear",
        "remediation_targets": [],
        "remediation_reason": "변경 근거 없음",
        "remediation_quotes": [],
        "possible_common_platform_functions": [],
        "summary": "공개 문서 근거 분석",
        "confidence": 0.8,
    }
    payload.update(updates)
    return CompactDeepAnalysis.model_validate(payload)


def test_compact_deep_downgrades_generic_ai_quotes():
    source = "추출 본문:\nAI 기반 자료 제작 및 해외봉사단 파견 규정"
    facts = _compact(
        task_scope="delegated_government",
        task_scope_reason="규정명이 있어 국가 위탁사무로 추정",
        task_scope_quotes=["해외봉사단 파견 규정"],
        model_fit="platform_llm_or_rag",
        model_fit_reason="AI 기반 자료이므로 LLM으로 추정",
        model_fit_quotes=["AI 기반 자료 제작"],
    )

    result = expand_compact_deep(facts, source, _rule())

    assert result.task_scope == "unclear"
    assert result.task_scope_evidence == []
    assert result.model_fit == "unclear"
    assert result.model_fit_evidence == []


def test_compact_deep_preserves_direct_gate_evidence_and_classifies():
    source = (
        "추출 본문:\n국가사무를 업무망에서 처리한다. "
        "생성형 AI 챗봇과 RAG 문서검색을 구축한다."
    )
    facts = _compact(
        network_scope="internal_or_connected",
        network_reason="업무망 처리 명시",
        network_quotes=["업무망에서 처리한다"],
        task_scope="government",
        task_scope_reason="국가사무 명시",
        task_scope_quotes=["국가사무"],
        model_fit="platform_llm_or_rag",
        model_fit_reason="챗봇과 RAG 명시",
        model_fit_quotes=["생성형 AI 챗봇과 RAG 문서검색"],
        remediation_feasibility="not_needed",
        remediation_reason="기본조건 충족",
    )

    result = enforce_common_platform_gates(expand_compact_deep(facts, source, _rule()), source)

    assert result.classification_code == "2"
    assert result.network_scope == "internal_or_connected"
    assert result.task_scope == "government"
    assert result.model_fit == "platform_llm_or_rag"


def test_deep_cannot_downgrade_confirmed_ai_education_to_non_ai():
    deep = _deep().model_copy(update={"ai_relevance": "low"})
    simple = _simple().model_copy(update={"ai_relevance": "medium"})

    result = preserve_deep_ai_scope(deep, simple)

    assert result.ai_relevance == "medium"
    assert result.summary.startswith("2차에서 AI가 사업명 또는 핵심 주제로 확인")


def test_stage_context_limits_preserve_metadata():
    context = "사업명: 테스트\n\n추출 본문:\n" + ("가" * 100)
    scoped = _truncate_context(context, 45)
    assert scoped.startswith("사업명: 테스트")
    assert len(scoped) == 45


def test_deep_falls_back_to_nvidia(monkeypatch):
    settings = replace(
        get_settings(),
        stage3_primary_provider="openai",
        stage3_primary_api_key="openai-test",
        stage3_primary_model="gpt-5.4-mini",
        stage3_fallback_provider="nvidia",
        stage3_fallback_api_key="nvidia-test",
        stage3_fallback_model="nvidia/nemotron-3-super-120b-a12b",
    )
    analyzer = RoutedAnalyzer(settings)
    calls: list[str] = []

    def fake_call(self, _system, _context, _schema):
        calls.append(self.endpoint.provider)
        if self.endpoint.provider == "openai":
            raise RuntimeError("temporary upstream failure")
        return _deep(), _usage(self.endpoint.model, self.endpoint.provider)

    monkeypatch.setattr(OpenAIChatClient, "call", fake_call)
    result, usage = analyzer.deep("추출 본문:\n생성형 AI 구축", _simple(), _rule())
    assert result.final_grade == "B"
    assert calls == ["openai", "nvidia"]
    assert usage["provider"] == "nvidia"
    assert usage["fallback_used"] is True
    assert "temporary upstream failure" in usage["primary_error"]


def test_stage2_rate_limit_uses_conservative_rule_fallback(monkeypatch):
    settings = replace(
        get_settings(), stage2_provider="gemini", stage2_api_key="gemini-test",
    )
    analyzer = RoutedAnalyzer(settings)
    rule = FilterResult(False, "AI 후보", 12, ["생성형 AI"], [], False)

    def rate_limited(*_args, **_kwargs):
        raise LLMRateLimitExceeded("Gemini daily quota")

    monkeypatch.setattr(OpenAIChatClient, "call", rate_limited)
    result, usage = analyzer.simple("추출 본문:\n생성형 AI 구축", rule)

    assert result.ai_relevance == "medium"
    assert result.needs_deep_review is True
    assert usage["model_name"] == "rule-fallback-after-stage2-error"
    assert usage["fallback_used"] is True


def test_daily_quota_opens_shared_rate_limit_circuit():
    endpoint = ChatEndpoint("gemini", "https://example.test", "key", "model", 30)
    client = OpenAIChatClient(endpoint)
    key = (endpoint.provider, endpoint.base_url, endpoint.model)
    response = httpx.Response(
        429,
        json={"error": {"details": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}]}},
        request=httpx.Request("POST", "https://example.test/chat/completions"),
    )

    assert client._is_daily_quota(response) is True
    OpenAIChatClient._rate_limited_until.pop(key, None)
    client._open_rate_limit_circuit(daily=True)
    with pytest.raises(LLMRateLimitExceeded, match="회로 차단"):
        client._check_rate_limit_circuit()
    OpenAIChatClient._rate_limited_until.pop(key, None)


@pytest.mark.parametrize("legacy_status,legacy_model", [
    ("success", "openai:old"),
    ("skipped", "rule-gate"),
])
def test_legacy_deep_reanalysis_reuses_previous_simple_result(monkeypatch, legacy_status, legacy_model):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls = {"simple": 0, "deep": 0}

    class Analyzer:
        simple_model_name = "gemini:new"
        deep_model_name = "openai:new"
        simple_cache_fingerprint = "new-simple-prompt"
        deep_cache_fingerprint = "new-deep-prompt"
        cache_fingerprint = "new"

        def simple(self, _context, _rule):
            calls["simple"] += 1
            raise AssertionError("legacy deep migration must reuse the prior simple result")

        def deep(self, _context, _simple_result, _rule):
            calls["deep"] += 1
            return _deep(), _usage("gpt-5.4-mini", "openai")

    monkeypatch.setattr("app.services.analyzer.get_analyzer", lambda _settings: Analyzer())
    with Session(engine, expire_on_commit=False) as db:
        notice = Notice(stage="bid", notice_no="LEGACY-1", agency_name="기관", title="생성형 AI 구축")
        db.add(notice)
        db.flush()
        notice.attachments.append(Attachment(
            source_url="sample://legacy", original_filename="제안요청서.txt",
            text_excerpt="생성형 AI 구축", parse_status="parsed",
        ))
        db.add(AnalysisRun(
            notice_id=notice.id, run_type="simple_ai", model_name="gemini:old",
            input_hash="s" * 64, status="success", result_json=_simple().model_dump_json(),
        ))
        db.add(AnalysisRun(
            notice_id=notice.id, run_type="deep_ai", model_name=legacy_model,
            input_hash="d" * 64, status=legacy_status, result_json='{"final_grade":"B"}',
        ))
        db.commit()

        result = analyze_notice(db, notice, deep=True, force=False)

        assert isinstance(result, DeepAnalysis)
        assert calls == {"simple": 0, "deep": 1}


def test_daily_deep_limit_skips_paid_call(tmp_path, monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = replace(get_settings(), stage3_daily_limit=10)
    monkeypatch.setattr("app.services.analyzer.get_settings", lambda: settings)

    with Session(engine, expire_on_commit=False) as db:
        notice = Notice(stage="prenotice", notice_no="LIMIT-1", agency_name="기관", title="생성형 AI 챗봇 구축")
        db.add(notice)
        db.flush()
        notice.attachments.append(Attachment(
            source_url="sample://limit",
            original_filename="rfp.txt",
            text_excerpt="생성형 AI 구축 및 LLM API 연계",
            parse_status="parsed",
        ))
        for index in range(10):
            db.add(AnalysisRun(
                notice_id=notice.id,
                run_type="deep_ai",
                model_name="openai:gpt-5.4-mini",
                input_hash=f"{index:064d}",
                status="success",
                result_json="{}",
                created_at=datetime.now(timezone.utc),
            ))
        db.commit()

        result = analyze_notice(db, notice, deep=True, force=False)
        latest = db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == "deep_ai",
        ).order_by(AnalysisRun.id.desc()))
        assert isinstance(result, DeepAnalysis)
        assert result.final_grade == "D"
        assert latest is not None
        assert latest.status == "skipped"
        assert latest.model_name == "daily-quota-guard"

        manual_result = analyze_notice(db, notice, deep=True, force=True)
        manual_run = db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == "deep_ai",
        ).order_by(AnalysisRun.id.desc()))
        assert isinstance(manual_result, DeepAnalysis)
        assert manual_run is not None
        assert manual_run.status == "success"
