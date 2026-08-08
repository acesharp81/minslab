from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import main
import presentation_loader


async def call_app(path: str, method: str = "GET", payload: dict | None = None):
    sent = []
    raw_body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else b""
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": raw_body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(raw_body)).encode("ascii"))],
        "client": ("203.0.113.10", 12345),
        "server": ("testserver", 443),
    }
    await main.app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start, body


class PresentationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.directory_patch = mock.patch.object(
            presentation_loader, "PRESENTATIONS_DIR", Path(self.temp_dir.name)
        )
        self.directory_patch.start()
        self.addCleanup(self.directory_patch.stop)

    async def test_admin_upload_requires_session(self):
        start, body = await call_app("/api/admin/presentations", "POST", {"title": "자료", "html": "<html></html>"})
        self.assertEqual(start["status"], 401)
        self.assertIn("관리자 로그인이 필요합니다".encode("utf-8"), body)

    async def test_upload_lists_and_serves_sandboxed_html(self):
        payload = {"title": "AI 추진계획", "filename": "slides.html", "html": "<!doctype html><html><body>발표 화면</body></html>"}
        with mock.patch.object(main, "admin_session", return_value={"exp": 1}):
            start, body = await call_app("/api/admin/presentations", "POST", payload)
        self.assertEqual(start["status"], 201)
        created = json.loads(body)["created"]
        self.assertEqual(created["title"], "AI 추진계획")

        page_start, page_body = await call_app(created["url"])
        headers = dict(page_start["headers"])
        self.assertEqual(page_start["status"], 200)
        self.assertIn(b"sandbox allow-scripts", headers[b"content-security-policy"])
        self.assertIn("발표 화면".encode("utf-8"), page_body)

        home_start, home_body = await call_app("/presentations")
        self.assertEqual(home_start["status"], 200)
        self.assertIn("설명자료".encode("utf-8"), home_body)
        self.assertIn("AI 추진계획".encode("utf-8"), home_body)

    async def test_admin_page_contains_upload_controls(self):
        start, body = await call_app("/admin")
        self.assertEqual(start["status"], 200)
        self.assertIn(b'id="presentationForm"', body)
        self.assertIn("왼쪽 트리 타이틀".encode("utf-8"), body)
        self.assertIn(b'id="presentationCancel"', body)
        self.assertIn("수정 저장".encode("utf-8"), body)

    async def test_update_preserves_url_and_optionally_replaces_html(self):
        created = presentation_loader.save_presentation(
            "기존 제목", "<!doctype html><html><body>기존 화면</body></html>", "old.html"
        )
        with mock.patch.object(main, "admin_session", return_value={"exp": 1}):
            start, body = await call_app(
                "/api/admin/presentations",
                "PUT",
                {"id": created["id"], "title": "수정 제목"},
            )
        self.assertEqual(start["status"], 200)
        updated = json.loads(body)["updated"]
        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(updated["url"], created["url"])
        self.assertEqual(updated["title"], "수정 제목")
        self.assertIn("기존 화면", presentation_loader.presentation_file(created["id"]).read_text())

        with mock.patch.object(main, "admin_session", return_value={"exp": 1}):
            replace_start, _ = await call_app(
                "/api/admin/presentations",
                "PUT",
                {
                    "id": created["id"],
                    "title": "최종 제목",
                    "filename": "new.html",
                    "html": "<!doctype html><html><body>교체 화면</body></html>",
                },
            )
        self.assertEqual(replace_start["status"], 200)
        self.assertIn("교체 화면", presentation_loader.presentation_file(created["id"]).read_text())


if __name__ == "__main__":
    unittest.main()
