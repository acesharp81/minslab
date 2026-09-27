from dataclasses import replace
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import AnalysisRun, Attachment, Notice
from app.services import collector
from app.services.analyzer import LLMRateLimitExceeded, record_non_ai_screen
from app.services.collector import _needs_backlog_analysis, _notice_priority, _store_attachment, _upsert_notice
from app.services.g2b_client import G2BAttachment, G2BNotice, _items


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def sample(no="N-1", text="생성형 AI 챗봇 구축"):
    return G2BNotice(
        stage="prenotice", notice_no=no, bid_no=None, agency_name="테스트기관", agency_code=None,
        title="AI 서비스", budget_amount=100_000_000, posted_at=datetime.now(timezone.utc),
        deadline_at=None, url=None, attachments=[G2BAttachment("rfp.txt", f"sample://{no}")],
        raw={"text": text},
    )


def test_explicit_ai_title_gets_analysis_priority():
    general = replace(sample("GENERAL"), title="통합 정보시스템 구축")
    explicit = replace(sample("AI"), title="생성형 AI 행정서비스 구축")
    assert collector._collection_priority(explicit) > collector._collection_priority(general)


def test_legacy_result_gets_backlog_priority(db):
    stale, _ = _upsert_notice(db, replace(sample("STALE"), title="AI 기존 결과"))
    fresh, _ = _upsert_notice(db, replace(sample("FRESH"), title="AI 신규 후보"))
    stale.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", model_name="old", input_hash="o" * 64,
        status="success", result_json='{"criteria_version":"common-platform-v2"}',
    ))
    db.commit()
    assert _notice_priority(stale) > _notice_priority(fresh)


def test_rule_non_ai_is_persisted_as_category_6(db):
    notice, _ = _upsert_notice(db, replace(sample("NON-AI"), title="청사 청소 용역", attachments=[]))
    db.commit()
    rule = collector.evaluate_notice(title=notice.title)
    assert rule.score == 0
    assert record_non_ai_screen(db, notice, rule) is True
    db.refresh(notice)
    assert '"classification_code":"6"' in notice.analysis_runs[-1].result_json
    assert _needs_backlog_analysis(notice) is False


def test_rule_non_construction_ai_service_is_persisted_as_category_6(db):
    notice, _ = _upsert_notice(db, replace(
        sample("AI-AUDIT"), title="생성형 AI 플랫폼 구축사업 감리용역", attachments=[],
    ))
    db.commit()
    rule = collector.evaluate_notice(title=notice.title)
    assert rule.scope_status == "non_target"
    assert record_non_ai_screen(db, notice, rule) is True
    db.refresh(notice)
    result = __import__("json").loads(notice.analysis_runs[-1].result_json)
    assert result["classification_code"] == "6"
    assert result["ai_relevance"] == "medium"
    assert result["service_scope"] == "non_target"
    assert _needs_backlog_analysis(notice) is False


def test_notice_upsert_does_not_duplicate(db):
    first, created = _upsert_notice(db, sample())
    db.commit()
    second, created_again = _upsert_notice(db, sample())
    db.commit()
    assert created is True
    assert created_again is False
    assert first.id == second.id
    assert db.scalar(select(func.count(Notice.id))) == 1


def test_sha_duplicate_reuses_file(tmp_path, db, monkeypatch):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data", raw_dir=tmp_path / "data/raw",
        parsed_dir=tmp_path / "data/parsed", reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    monkeypatch.setattr(collector, "get_settings", lambda: settings)
    one, _ = _upsert_notice(db, sample("N-1", "동일한 내용"))
    two, _ = _upsert_notice(db, sample("N-2", "동일한 내용"))
    db.flush()
    _store_attachment(db, one, sample("N-1", "동일한 내용"), 1, "sample://N-1", "one.txt")
    db.flush()
    _store_attachment(db, two, sample("N-2", "동일한 내용"), 1, "sample://N-2", "two.txt")
    db.commit()
    paths = {row.file_path for row in db.scalars(select(Attachment)).all()}
    assert len(paths) == 1
    assert len(list(settings.raw_dir.glob("*.txt"))) == 1


@pytest.mark.asyncio
async def test_notice_failure_is_isolated(db, monkeypatch, tmp_path):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data", raw_dir=tmp_path / "data/raw",
        parsed_dir=tmp_path / "data/parsed", reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    monkeypatch.setattr(collector, "get_settings", lambda: settings)

    async def fake_collect(self, _days):
        return [sample("FAIL"), sample("OK")]

    monkeypatch.setattr(collector.G2BClient, "collect", fake_collect)
    original = collector._upsert_notice

    def sometimes_fails(session, item):
        if item.notice_no == "FAIL":
            raise ValueError("broken payload")
        return original(session, item)

    monkeypatch.setattr(collector, "_upsert_notice", sometimes_fails)
    result = await collector.run_collection(db, analyze=False)
    assert result["received"] == 2
    assert db.scalar(select(func.count(Notice.id))) == 1


@pytest.mark.asyncio
async def test_rate_limit_defers_remaining_candidates(db, monkeypatch, tmp_path):
    settings = replace(
        get_settings(), project_root=tmp_path, data_dir=tmp_path / "data", raw_dir=tmp_path / "data/raw",
        parsed_dir=tmp_path / "data/parsed", reports_dir=tmp_path / "data/reports", logs_dir=tmp_path / "data/logs",
    )
    settings.ensure_directories()
    monkeypatch.setattr(collector, "get_settings", lambda: settings)

    async def fake_collect(self, _days):
        return [sample(f"RATE-{index}") for index in range(3)]

    calls = []

    def rate_limited(_db, notice, **_kwargs):
        calls.append(notice.id)
        raise LLMRateLimitExceeded("HTTP 429")

    monkeypatch.setattr(collector.G2BClient, "collect", fake_collect)
    monkeypatch.setattr(collector, "analyze_notice", rate_limited)
    result = await collector.run_collection(db, analyze=True)
    assert result["rule_candidates"] == 3
    assert result["analysis_failed"] == 1
    assert result["analysis_deferred"] == 2
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_g2b_encoded_key_is_decoded_once(monkeypatch):
    settings = replace(get_settings(), g2b_service_key="abc%2Fdef%2Bghi%3D")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": {"header": {"resultCode": "00"}, "body": {"items": {"item": []}}}}

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, params):
            captured.update(params)
            return Response()

    monkeypatch.setattr("app.services.g2b_client.httpx.AsyncClient", Client)
    await collector.G2BClient(settings)._request("https://example.com", "operation", {})
    assert captured["serviceKey"] == "abc/def+ghi="


@pytest.mark.asyncio
async def test_g2b_rate_limit_is_not_retried_immediately(monkeypatch):
    settings = replace(get_settings(), g2b_service_key="test-key")
    calls = []

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, params):
            calls.append(url)
            return httpx.Response(429, request=httpx.Request("GET", url))

    monkeypatch.setattr("app.services.g2b_client.httpx.AsyncClient", Client)
    with pytest.raises(RuntimeError, match="HTTP 429"):
        await collector.G2BClient(settings)._request("https://example.com", "operation", {})
    assert len(calls) == 1


def test_g2b_current_items_array_shape_is_supported():
    payload = {
        "response": {
            "header": {"resultCode": "00"},
            "body": {"items": [{"bidNtceNo": "A"}, {"bidNtceNo": "B"}]},
        }
    }
    assert [row["bidNtceNo"] for row in _items(payload)] == ["A", "B"]


def test_bid_maps_all_ten_specification_files():
    settings = replace(get_settings(), g2b_mode="live")
    item = {
        "bidNtceNo": "BID-1",
        "bidNtceOrd": "00",
        "bidNtceNm": "AI 사업",
        **{f"ntceSpecDocUrl{index}": f"https://example.com/{index}.pdf" for index in range(1, 11)},
        **{f"ntceSpecFileNm{index}": f"문서-{index}.pdf" for index in range(1, 11)},
    }
    notice = collector.G2BClient(settings)._map_bid(item)
    assert len(notice.attachments) == 10
    assert notice.attachments[-1].name == "문서-10.pdf"


def test_prenotice_prefers_real_demand_institution_over_procurement_office():
    settings = replace(get_settings(), g2b_mode="live")
    notice = collector.G2BClient(settings)._map_prenotice({
        "bfSpecRgstNo": "PRE-1",
        "prdctNm": "AI 사업",
        "orderInsttNm": "조달청 서울지방조달청",
        "orderInsttCd": "PROCUREMENT",
        "rlDminsttNm": "경기도 안양시",
        "rlDminsttCd": "ANYANG",
    })

    assert notice.agency_name == "경기도 안양시"
    assert notice.agency_code == "ANYANG"
