from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_keeps_forwarded_homepage_prefix():
    prefix = "/poc/ai-common-platform-radar"
    with TestClient(app) as client:
        response = client.get("/", headers={"x-forwarded-prefix": prefix})

    assert response.status_code == 200
    assert f'data-base-path="{prefix}"' in response.text
    assert f'href="{prefix}/notices"' in response.text
    assert f'href="{prefix}/reports/daily"' in response.text
    assert f'href="{prefix}/static/app.css"' in response.text
    assert f'src="{prefix}/static/app.js"' in response.text
    assert "지금 처리해야 할 항목" in response.text
    assert "문서 오류 재처리" in response.text
    assert "오늘의 공통기반 검토" in response.text
    assert "지금 조치할 사업" in response.text
    assert "누적 유형 분류" in response.text
    assert 'class="admin-link" href="/admin" target="_top"' in response.text
    assert "ADMIN 로그인" in response.text


def test_dashboard_stays_standalone_without_forwarded_prefix():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert 'data-base-path=""' in response.text
    assert 'href="/notices"' in response.text
    assert 'href="/static/app.css"' in response.text
    assert 'class="admin-link"' not in response.text


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
