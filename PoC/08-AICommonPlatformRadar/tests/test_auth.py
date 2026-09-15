from __future__ import annotations

import base64
from dataclasses import replace

from fastapi.testclient import TestClient

import app.main as main_module


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
