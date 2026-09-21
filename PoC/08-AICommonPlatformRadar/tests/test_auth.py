from __future__ import annotations

import base64
from dataclasses import replace

from fastapi.testclient import TestClient

import app.main as main_module
import app.routers.settings as settings_router


def test_public_reads_remain_available_when_admin_auth_is_enabled(monkeypatch):
    secured = replace(
        main_module.settings,
        admin_username="radar-admin",
        admin_password="test-password",
        admin_token="",
    )
    monkeypatch.setattr(main_module, "settings", secured)

    with TestClient(main_module.app) as client:
        dashboard = client.get("/")
        health = client.get("/health")

    assert dashboard.status_code == 200
    assert health.status_code == 200


def test_mutations_require_admin_auth(monkeypatch):
    secured = replace(
        main_module.settings,
        admin_username="radar-admin",
        admin_password="test-password",
        admin_token="",
    )
    monkeypatch.setattr(main_module, "settings", secured)

    credentials = base64.b64encode(b"radar-admin:test-password").decode("ascii")
    with TestClient(main_module.app) as client:
        denied = client.post("/__auth_boundary_test__")
        authorized = client.post(
            "/__auth_boundary_test__",
            headers={"Authorization": f"Basic {credentials}"},
        )

    assert denied.status_code == 401
    assert denied.headers["www-authenticate"].startswith("Basic ")
    assert authorized.status_code == 404


def test_signed_parent_proxy_token_authorizes_mutation(monkeypatch):
    secured = replace(
        main_module.settings,
        admin_username="radar-admin",
        admin_password="test-password",
        admin_token="",
        proxy_token="derived-internal-token",
    )
    monkeypatch.setattr(main_module, "settings", secured)

    with TestClient(main_module.app) as client:
        denied = client.post(
            "/__auth_boundary_test__",
            headers={"X-PoC08-Proxy-Token": "forged-token"},
        )
        authorized = client.post(
            "/__auth_boundary_test__",
            headers={"X-PoC08-Proxy-Token": "derived-internal-token"},
        )

    assert denied.status_code == 401
    assert authorized.status_code == 404


def test_settings_login_is_the_only_public_post_entry(monkeypatch):
    secured = replace(
        main_module.settings,
        admin_username="radar-admin",
        admin_password="test-password",
        admin_token="",
    )
    monkeypatch.setattr(main_module, "settings", secured)
    monkeypatch.setattr(settings_router, "verify_admin_password", lambda username, password: (username, password) == ("radar-admin", "test-password"))
    monkeypatch.setattr(settings_router, "create_admin_session", lambda _username: "signed-session")

    with TestClient(main_module.app) as client:
        response = client.post(
            "/settings/login",
            data={"username": "radar-admin", "password": "test-password"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"].endswith("/settings")
    assert "poc08_admin_session=signed-session" in response.headers["set-cookie"]


def test_opinion_sender_profile_requires_settings_authorization(monkeypatch):
    secured = replace(main_module.settings, proxy_token="derived-internal-token")
    monkeypatch.setattr(settings_router, "get_settings", lambda: secured)

    with TestClient(main_module.app) as client:
        denied = client.get("/api/settings/opinion-sender")
        authorized = client.get(
            "/api/settings/opinion-sender",
            headers={"X-PoC08-Proxy-Token": "derived-internal-token"},
        )

    assert denied.status_code == 401
    assert authorized.status_code == 200
    assert "opinion_password" in authorized.json()
