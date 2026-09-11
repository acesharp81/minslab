from dataclasses import replace
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base
from app.models import Attachment, Notice
from app.services import collector
from app.services.collector import _store_attachment, _upsert_notice
from app.services.g2b_client import G2BAttachment, G2BNotice


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
