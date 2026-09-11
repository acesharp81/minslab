from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import create_engine, select

from app.config import get_settings
from app.db import Base, RadarSession
from app.models import Notice
from app.services import supabase_store
from app.services.supabase_store import SupabaseRestStore, deserialize_row, serialize_model


def enabled_settings():
    return replace(
        get_settings(),
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="server-only-test-key",
    )


def test_json_and_datetime_round_trip():
    created_at = datetime(2026, 9, 11, 1, 2, 3, tzinfo=timezone.utc)
    notice = Notice(
        id=7,
        stage="bid",
        notice_no="TEST-7",
        title="AI 플랫폼 구축",
        raw_payload_json='{"nested": [1, 2]}',
        created_at=created_at,
        updated_at=created_at,
    )

    wire = serialize_model(notice)
    assert wire["raw_payload_json"] == {"nested": [1, 2]}
    assert wire["created_at"] == created_at.isoformat()

    local = deserialize_row(Notice, wire)
    assert json.loads(local["raw_payload_json"]) == {"nested": [1, 2]}
    assert local["created_at"] == created_at


def test_commit_pushes_only_to_poc08_table(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    calls: list[tuple[list[object], list[object]]] = []

    class FakeStore:
        def push_changes(self, upserts, deletes):
            calls.append((list(upserts), list(deletes)))
            return True

    monkeypatch.setattr(supabase_store, "get_supabase_store", lambda: FakeStore())
    with RadarSession(bind=engine, expire_on_commit=False) as db:
        notice = Notice(stage="bid", notice_no="COMMIT-1", title="커밋 동기화")
        db.add(notice)
        db.commit()

    assert len(calls) == 1
    assert calls[0][0][0].notice_no == "COMMIT-1"
    assert calls[0][1] == []
    assert supabase_store.model_tables()[Notice] == "poc08_notices"


def test_reconcile_pulls_remote_then_pushes_local(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    store = SupabaseRestStore(enabled_settings())
    pushed: dict[str, list[dict]] = {}
    remote_notice = {
        "id": 11,
        "source": "g2b",
        "stage": "prenotice",
        "notice_no": "REMOTE-11",
        "title": "원격 공고",
        "raw_payload_json": {"origin": "supabase"},
        "created_at": "2026-09-11T00:00:00+00:00",
        "updated_at": "2026-09-11T00:00:00+00:00",
    }

    monkeypatch.setattr(
        store,
        "fetch_all",
        lambda table: [remote_notice] if table == "poc08_notices" else [],
    )
    monkeypatch.setattr(store, "upsert", lambda table, rows: pushed.setdefault(table, rows))

    with RadarSession(bind=engine, expire_on_commit=False) as db:
        assert store.reconcile(db)
        notice = db.scalar(select(Notice).where(Notice.id == 11))
        assert notice is not None
        assert json.loads(notice.raw_payload_json) == {"origin": "supabase"}

    assert pushed["poc08_notices"][0]["notice_no"] == "REMOTE-11"


def test_fetch_all_pages_past_supabase_default_row_limit(monkeypatch):
    store = SupabaseRestStore(enabled_settings())
    ranges: list[str] = []

    def fake_request(_method, _path, **kwargs):
        current = kwargs["extra_headers"]["Range"]
        ranges.append(current)
        return [{"id": index} for index in range(1_000)] if current == "0-999" else [{"id": 1001}]

    monkeypatch.setattr(store, "request", fake_request)
    rows = store.fetch_all("poc08_notices")

    assert len(rows) == 1_001
    assert ranges == ["0-999", "1000-1999"]


def test_rest_error_never_contains_key_or_url(monkeypatch):
    class FakeResponse:
        status_code = 404
        content = b'{"code":"PGRST205","message":"missing table"}'
        reason_phrase = "Not Found"

        @staticmethod
        def json():
            return {"code": "PGRST205", "message": "missing table"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        @staticmethod
        def request(*_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(supabase_store.httpx, "Client", FakeClient)
    store = SupabaseRestStore(enabled_settings())
    try:
        store.request("GET", "poc08_notices?limit=1")
    except supabase_store.SupabaseStoreError as exc:
        message = str(exc)
    else:
        raise AssertionError("오류 응답이어야 합니다.")

    assert "server-only-test-key" not in message
    assert "example.supabase.co" not in message
    assert "PGRST205" in message
