from dataclasses import replace
from datetime import datetime, timedelta
import json
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import AnalysisRun, Notice
from app.services import jev_shadow
from app.services.jev_shadow import _scoped_context, evaluate_jev_shadow, jev_shadow_state, record_jev_shadow


def _settings(**updates):
    values = {
        "jev_shadow_enabled": True,
        "jev_api_key": "test-key",
        "jev_base_url": "https://www.jevai.org",
        "jev_model": "typesafe-ai/jev",
        "jev_shadow_end_date": "",
    }
    values.update(updates)
    return replace(get_settings(), **values)


def _jev_result():
    return {
        "schema_version": "poc08-jev-shadow-v2-jevai",
        "provider": "jevai",
        "model": "typesafe-ai/jev",
        "business_type": "ai_service",
        "business_type_confidence": 0.92,
        "business_type_probabilities": {
            "ai_service": 0.92,
            "ai_related_out_of_scope": 0.04,
            "non_ai_service": 0.02,
            "uncertain": 0.02,
        },
        "needs_deep_review_probability": 0.96,
        "usage": {"input_tokens": 120, "output_tokens": 12},
    }


def test_jev_request_and_response_are_normalized():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://www.jevai.org/api/v1/decisions"
        captured.update(json.loads(request.content.decode("utf-8")))
        assert request.headers["authorization"] == "Bearer test-key"
        return httpx.Response(200, json={
            "code": 0,
            "message": "ok",
            "data": {
                "model": "typesafe-ai/jev",
                "answers": {
                    "business_type": {
                        "type": "choice",
                        "choice": "ai_service",
                        "confidence": 0.92,
                        "probabilities": {
                            "ai_service": 0.92,
                            "ai_related_out_of_scope": 0.04,
                            "non_ai_service": 0.02,
                            "uncertain": 0.02,
                        },
                    },
                    "needs_deep_review": {"type": "noul", "noul": 0.96},
                },
                "usage": {"input_tokens": 120, "output_tokens": 12},
            },
        })

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = evaluate_jev_shadow("사업명: 생성형 AI 민원 서비스 구축", _settings(), client=client)

    assert captured["model"] == "typesafe-ai/jev"
    assert captured["questions"]["business_type"]["type"] == "choice"
    assert set(captured["questions"]["business_type"]["criteria"]) == {
        "ai_service", "ai_related_out_of_scope", "non_ai_service", "uncertain",
    }
    assert captured["questions"]["needs_deep_review"]["type"] == "noul"
    assert result["business_type"] == "ai_service"
    assert result["usage"] == {"input_tokens": 120, "output_tokens": 12}


def test_jev_context_redacts_unneeded_contact_details():
    context = (
        "사업명: 생성형 AI 민원 챗봇 구축\n"
        "담당자: 홍길동 / 010-1234-5678\n"
        "연락처: 02-123-4567\n"
        "추출 본문: 담당 메일 help@example.org로 연락 바랍니다."
    )
    scoped = _scoped_context(context, _settings())

    assert "생성형 AI 민원 챗봇 구축" in scoped
    assert "홍길동" not in scoped
    assert "010-1234-5678" not in scoped
    assert "02-123-4567" not in scoped
    assert "help@example.org" not in scoped


def test_shadow_result_records_comparison_without_changing_notice(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr("app.services.jev_shadow.evaluate_jev_shadow", lambda *_args, **_kwargs: _jev_result())

    with Session(engine, expire_on_commit=False) as db:
        notice = Notice(stage="prenotice", notice_no="JEV-1", agency_name="기관", title="AI 서비스 구축")
        db.add(notice)
        db.flush()

        added = record_jev_shadow(
            db,
            notice,
            "사업명: AI 서비스 구축",
            reference_business_type="ai_service",
            reference_needs_deep_review=True,
            reference_ai_relevance="high",
            settings=_settings(),
        )
        db.commit()
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.run_type == "jev_shadow"))

        assert added is True
        assert run is not None
        assert run.status == "success"
        assert run.model_name == "jevai:typesafe-ai/jev"
        assert run.cost_prompt_tokens == 120
        payload = json.loads(run.result_json)
        assert payload["record_only"] is True
        assert payload["agreement"] is True
        assert payload["deep_review_agreement"] is True


def test_shadow_failure_is_recorded_and_does_not_raise(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    def fail(*_args, **_kwargs):
        raise httpx.TimeoutException("temporary")

    monkeypatch.setattr("app.services.jev_shadow.evaluate_jev_shadow", fail)
    with Session(engine, expire_on_commit=False) as db:
        notice = Notice(stage="bid", notice_no="JEV-2", agency_name="기관", title="일반 사업")
        db.add(notice)
        db.flush()
        assert record_jev_shadow(
            db,
            notice,
            "사업명: 일반 사업",
            reference_business_type="non_ai_service",
            reference_needs_deep_review=False,
            reference_ai_relevance="low",
            settings=_settings(),
        ) is True
        db.commit()
        run = db.scalar(select(AnalysisRun).where(AnalysisRun.run_type == "jev_shadow"))
        assert run is not None
        assert run.status == "failed"
        assert "TimeoutException" in (run.error_message or "")


def test_shadow_is_safely_skipped_without_api_key():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        notice = Notice(stage="bid", notice_no="JEV-3", agency_name="기관", title="AI 사업")
        db.add(notice)
        db.flush()
        assert record_jev_shadow(
            db,
            notice,
            "사업명: AI 사업",
            reference_business_type="ai_service",
            reference_needs_deep_review=True,
            reference_ai_relevance="high",
            settings=_settings(jev_api_key=""),
        ) is False
        assert db.scalar(select(AnalysisRun.id)) is None


def test_temporary_key_stops_after_its_last_day():
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    assert jev_shadow_state(_settings(jev_shadow_end_date=today.isoformat())) in {"ready", "rate_limited"}
    assert jev_shadow_state(_settings(jev_shadow_end_date=(today - timedelta(days=1)).isoformat())) == "expired"


def test_rate_limit_cools_down_subsequent_notices(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(jev_shadow, "_retry_after_monotonic", 0.0)
    calls = []

    def rate_limited(*_args, **_kwargs):
        calls.append(1)
        response = httpx.Response(
            429,
            json={"code": -1, "message": "Too many requests"},
            request=httpx.Request("POST", "https://www.jevai.org/api/v1/decisions"),
        )
        raise httpx.HTTPStatusError("rate limited", request=response.request, response=response)

    monkeypatch.setattr(jev_shadow, "evaluate_jev_shadow", rate_limited)
    with Session(engine, expire_on_commit=False) as db:
        for number in range(2):
            notice = Notice(stage="bid", notice_no=f"RATE-{number}", agency_name="기관", title="AI 구축")
            db.add(notice)
            db.flush()
            record_jev_shadow(
                db, notice, "사업명: AI 구축",
                reference_business_type="ai_service",
                reference_needs_deep_review=True,
                reference_ai_relevance="high",
                settings=_settings(),
            )
        db.commit()
        assert calls == [1]
        assert jev_shadow_state(_settings()) == "rate_limited"
        assert len(db.scalars(select(AnalysisRun).where(AnalysisRun.run_type == "jev_shadow")).all()) == 1
