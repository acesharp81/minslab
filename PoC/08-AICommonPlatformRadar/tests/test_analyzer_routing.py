from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import AnalysisRun, Attachment, Notice
from app.schemas import DeepAnalysis, Evidence, SimpleAnalysis
from app.services.analyzer import OpenAIChatClient, RoutedAnalyzer, _truncate_context, _usage, analyze_notice
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
        final_grade="B",
        ai_relevance="high",
        common_platform_fit="high",
        usage_mentioned="unclear",
        possible_common_platform_functions=["LLM API"],
        summary="공통기반 활용 여부 확인 필요",
        evidence=[Evidence(quote="생성형 AI 구축")],
        check_questions=["공통기반 API 활용을 검토했는지 확인 필요"],
        recommended_action="contact",
        priority_score=88,
        confidence=0.8,
        caveats=[],
    )


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

        result = analyze_notice(db, notice, deep=True, force=True)
        latest = db.scalar(select(AnalysisRun).where(
            AnalysisRun.notice_id == notice.id,
            AnalysisRun.run_type == "deep_ai",
        ).order_by(AnalysisRun.id.desc()))
        assert isinstance(result, DeepAnalysis)
        assert result.final_grade == "D"
        assert latest is not None
        assert latest.status == "skipped"
        assert latest.model_name == "daily-quota-guard"
