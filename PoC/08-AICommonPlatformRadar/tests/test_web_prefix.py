from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone

from app.db import Base, get_db
from app.main import app, format_number
from app.models import ActionItem, AnalysisRun, Notice
from app.routers.dashboard import collection_window
from app.services.analyzer import CURRENT_CRITERIA_VERSION
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def test_statistics_number_format_uses_thousands_separator():
    assert format_number(1581) == "1,581"
    assert format_number(99.8) == "99.8"


def test_collection_window_uses_latest_closed_05_kst_operating_cycle():
    window = collection_window(datetime(2026, 9, 16, 2, 0, tzinfo=timezone.utc))

    assert window["label"] == "26.9.15. 05:00 ~ 26.9.16. 05:00"


def test_dashboard_keeps_forwarded_homepage_prefix():
    prefix = "/poc/ai-common-platform-radar"
    with TestClient(app) as client:
        response = client.get("/", headers={"x-forwarded-prefix": prefix})

    assert response.status_code == 200
    assert f'data-base-path="{prefix}"' in response.text
    assert f'href="{prefix}/notices"' in response.text
    assert f'href="{prefix}/reports/daily"' in response.text
    assert f'href="{prefix}/settings"' in response.text
    assert f'href="{prefix}/extension/install"' in response.text
    assert "성과 통계" in response.text
    assert "설정" in response.text
    assert "확장프로그램 설치" in response.text
    assert f'href="{prefix}/static/app.css"' in response.text
    assert f'src="{prefix}/static/app.js"' in response.text
    assert "지금 조치·확인할 사업" in response.text
    assert "조달체크" in response.text
    assert "나라장터 AI 사업, 자동으로 찾고 공통기반 활용까지 체크." in response.text
    assert "일일 처리 주기" in response.text
    assert "공통기반 적합" in response.text
    assert 'class="daily-status-map"' in response.text
    assert "AI 사업" in response.text and "비AI 사업" in response.text
    assert "부적합" in response.text
    assert 'class="ineligible-reason-chart compact"' in response.text
    assert "이용" in response.text and "미이용" in response.text
    assert "검토 필요" in response.text
    assert "공통기반 이용 확인 공고" in response.text
    assert "전체 대상" in response.text
    assert "누적 유형 분류" not in response.text
    assert 'class="admin-link"' not in response.text
    assert "ADMIN 로그인" not in response.text
    assert response.text.index(f'class="nav-item nav-install" href="{prefix}/extension/install"') < response.text.index(f'class="nav-item" href="{prefix}/"')
    assert 'class="nav-icon"' in response.text


def test_dashboard_stays_standalone_without_forwarded_prefix():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'data-base-path=""' in response.text
    assert 'href="/notices"' in response.text
    assert 'href="/static/app.css"' in response.text
    assert 'class="admin-link"' not in response.text


def test_dashboard_separates_registered_prenotices_into_paginated_in_progress_section():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)

    def add_notice(db: Session, index: int, status: str):
        notice = Notice(
            stage="prenotice", notice_no=f"R26DASH{index:04d}",
            agency_name="테스트기관", title=f"대시보드 분리 사업 {index:02d}",
        )
        notice.analysis_runs.append(AnalysisRun(
            run_type="deep_ai", model_name="test", input_hash=f"{index:064d}"[-64:], status="success",
            result_json=json.dumps({
                "criteria_version": CURRENT_CRITERIA_VERSION,
                "classification_code": "2",
            }),
        ))
        notice.action = ActionItem(status=status)
        db.add(notice)

    with Session(engine) as db:
        add_notice(db, 0, "new")
        for index in range(1, 13):
            add_notice(db, index, "in_progress")
        db.commit()

    def override_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            first = client.get("/")
            second = client.get("/?progress_page=2")
    finally:
        app.dependency_overrides.pop(get_db, None)

    required = first.text.split('id="action-required"', 1)[1].split('id="actions-in-progress"', 1)[0]
    progress = first.text.split('id="actions-in-progress"', 1)[1].split('confirmed-use-panel', 1)[0]
    progress_second = second.text.split('id="actions-in-progress"', 1)[1].split('confirmed-use-panel', 1)[0]
    assert "대시보드 분리 사업 00" in required
    assert "대시보드 분리 사업 01" not in required
    assert "대시보드 분리 사업 00" not in progress
    assert progress.count('class="action-row progress-action-row"') == 10
    assert "전체 12건" in progress
    assert progress_second.count('class="action-row progress-action-row"') == 2
    assert "progress_page=2#actions-in-progress" in first.text


def test_statistics_shows_ineligible_pie_and_removes_stacked_status_bar():
    with TestClient(app) as client:
        response = client.get("/reports/daily")

    assert response.status_code == 200
    assert 'class="ineligible-reason-chart"' in response.text
    assert "국가사무" in response.text
    assert "망·데이터" in response.text
    assert "특화모델(학습 필요)" in response.text
    assert "status-stacked-bar" not in response.text
    assert "status-legend" not in response.text


def test_admin_link_is_not_exposed_for_an_unrelated_deployment_prefix():
    with TestClient(app) as client:
        response = client.get("/", headers={"x-forwarded-prefix": "/standalone-radar"})

    assert response.status_code == 200
    assert 'class="admin-link"' not in response.text


def test_static_assets_remain_routable_with_forwarded_prefix():
    with TestClient(app) as client:
        response = client.get(
            "/static/app.css",
            headers={"x-forwarded-prefix": "/poc/ai-common-platform-radar"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")


def test_extension_install_page_and_archive_are_available():
    with TestClient(app) as client:
        page = client.get("/extension/install")
        archive = client.get("/extension/download")

    assert page.status_code == 200
    assert "나라장터 의견 도우미 설치" in page.text
    assert "v0.1.7" in page.text
    assert "나라장터 등록 의견 확인" in page.text
    assert "최종 저장" in page.text
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"
    assert archive.content.startswith(b"PK")
    with zipfile.ZipFile(io.BytesIO(archive.content)) as package:
        manifest = json.loads(package.read("browser-extension/manifest.json"))
        bridge = package.read("browser-extension/poc_bridge.js").decode("utf-8")
        assistant = package.read("browser-extension/g2b_assistant.js").decode("utf-8")
    assert manifest["version"] == "0.1.7"
    assert "data-extension-opinion-view" in bridge
    assert "view_opened" in assistant
