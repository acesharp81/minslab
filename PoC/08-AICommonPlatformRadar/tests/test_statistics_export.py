from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import ActionItem, AnalysisRun, AuditLog, Notice
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from app.services.statistics_export import COLUMNS, build_statistics_csv


def _rows(payload: bytes) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(payload.decode("utf-8-sig"))))


def test_csv_includes_current_collections_and_old_notices_processed_in_period():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    now = datetime(2026, 9, 28, 3, 0, tzinfo=timezone.utc)
    recent = Notice(
        stage="bid_notice", notice_no="BID-NEW", agency_name="현재기관",
        title="=HYPERLINK(\"bad\")", created_at=now - timedelta(days=2),
    )
    old_opinion = Notice(
        stage="prenotice", notice_no="PRE-OLD", agency_name="과거기관",
        title="기관 답변 사례", created_at=now - timedelta(days=80),
        raw_payload_json=json.dumps({"_poc08_opinion_tracking": {
            "status": "replied", "status_label": "답변 등록 1건",
            "submitted_at": (now - timedelta(days=3)).isoformat(),
            "submitted_content": "공통기반 사용을 요청합니다.",
            "latest_reply_content": "연계망 제약으로 이용할 수 없습니다.",
            "latest_reply_at": "20260927143000",
        }}, ensure_ascii=False),
    )
    old_opinion.action = ActionItem(
        status="completed_ineligible", agency_response="연계망 제약으로 이용할 수 없습니다.",
        memo="담당자와 후속 협의", owner="홍길동", updated_at=now - timedelta(days=1),
    )
    old_opinion.analysis_runs.append(AnalysisRun(
        run_type="deep_ai", status="success", model_name="test", input_hash="a" * 64,
        result_json=json.dumps({
            "criteria_version": CURRENT_CRITERIA_VERSION, "classification_code": "5",
            "summary": "망 연계 검토 필요", "network_scope": "other_closed_network",
            "network_reason": "망 미연계", "service_scope": "target_build",
        }, ensure_ascii=False),
    ))
    old_action = Notice(
        stage="prenotice", notice_no="PRE-ACTION", agency_name="기존기관",
        title="기간 내 조치 진행", created_at=now - timedelta(days=80),
    )
    old_action.action = ActionItem(status="in_progress", updated_at=now - timedelta(days=1))
    untouched = Notice(
        stage="bid_notice", notice_no="BID-OLD", agency_name="과거기관",
        title="기간 외", created_at=now - timedelta(days=80),
    )
    with Session(engine) as db:
        db.add_all([recent, old_opinion, old_action, untouched])
        db.flush()
        db.add(AuditLog(
            event_type="action_updated", entity_type="action_item", entity_id=str(old_opinion.action.id),
            detail_json=json.dumps({"status": "completed_ineligible"}), created_at=now - timedelta(days=1),
        ))
        db.commit()
        payload = build_statistics_csv(db, period="30d", now=now)

    assert payload.startswith(b"\xef\xbb\xbf")
    assert list(_rows(payload)[0]) == list(COLUMNS)
    rows = {row["공고번호"]: row for row in _rows(payload)}
    assert set(rows) == {"BID-NEW", "PRE-OLD", "PRE-ACTION"}
    assert rows["PRE-ACTION"]["집계 포함 기준"] == "조치 기록"
    assert rows["BID-NEW"]["사업명"].startswith("'=HYPERLINK")
    assert rows["BID-NEW"]["집계 포함 기준"] == "수집"
    assert rows["PRE-OLD"]["집계 포함 기준"] == "조치 완료·의견 등록"
    assert rows["PRE-OLD"]["의견 결과"] == "부적합"
    assert rows["PRE-OLD"]["기관 회신 기록"] == "연계망 제약으로 이용할 수 없습니다."
    assert rows["PRE-OLD"]["의견 등록 내용"] == "공통기반 사용을 요청합니다."
    assert rows["PRE-OLD"]["조치 메모"] == "담당자와 후속 협의"
    assert rows["PRE-OLD"]["기간 내 조치 완료일"]
    assert "completed_ineligible" in rows["PRE-OLD"]["조치 변경 이력(JSON)"]
    assert set(row["공고번호"] for row in _rows(build_statistics_csv(Session(engine), "all", now))) == {
        "BID-NEW", "PRE-OLD", "PRE-ACTION", "BID-OLD",
    }


def test_csv_route_requires_admin_and_keeps_selected_period_and_proxy_prefix(monkeypatch):
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            page = client.get("/reports/daily?period=year", headers={"x-forwarded-prefix": "/poc/ai-common-platform-radar"})
            denied = client.get("/reports/daily/statistics.csv?period=year")
            monkeypatch.setattr(
                "app.routers.settings.verify_admin_session",
                lambda token: token == "valid-admin-session",
            )
            client.cookies.set("poc08_admin_session", "valid-admin-session")
            allowed = client.get("/reports/daily/statistics.csv?period=year")
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert page.status_code == 200
    assert 'href="/poc/ai-common-platform-radar/reports/daily/statistics.csv?period=year"' in page.text
    assert "통계자료 받기" in page.text
    assert denied.status_code == 401
    assert allowed.status_code == 200
    assert allowed.headers["content-disposition"].startswith('attachment; filename="poc08-statistics-year-')
    assert allowed.headers["content-type"].startswith("text/csv")
    assert allowed.headers["cache-control"] == "no-store"
    assert allowed.content.startswith(b"\xef\xbb\xbf")
