from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import unittest
from pathlib import Path


TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["MASTER_PRESS_DATA_DIR"] = TEMP_DIR.name
os.environ["SUPABASE2_URL"] = ""
os.environ["SUPABASE2_SERVICE_ROLE_KEY"] = ""

import main
from admin_auth import SESSION_COOKIE


async def call_app(path: str, method: str = "GET", payload: dict | None = None, cookie: str = ""):
    query_string = b""
    if "?" in path:
        path, query = path.split("?", 1)
        query_string = query.encode("utf-8")
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else b""
    messages = [{"type": "http.request", "body": body, "more_body": False}]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    headers = [(b"host", b"testserver"), (b"x-forwarded-proto", b"https")]
    if cookie:
        headers.append((b"cookie", cookie.encode("latin-1")))
    await main.app({
        "type": "http", "http_version": "1.1", "method": method, "scheme": "https",
        "path": path, "query_string": query_string, "headers": headers,
        "client": ("127.0.0.1", 12345),
    }, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    response_body = b"".join(message.get("body", b"") for message in sent if message["type"] == "http.response.body")
    return start["status"], dict(start["headers"]), response_body


class MainIntegrationTests(unittest.TestCase):
    def test_static_dashboard_and_project_registration(self):
        status, _headers, body = asyncio.run(call_app("/poc/master-press/"))
        self.assertEqual(status, 200)
        self.assertIn("AI 언론동향 비서".encode("utf-8"), body)
        self.assertIn("AI읽고 AI로 분류하다".encode("utf-8"), body)
        homepage = main.build_html()
        self.assertEqual(body.count(b'id="organizationDialog"'), 1)
        self.assertEqual(body.count(b'id="inviteDialog"'), 1)
        self.assertIn(b'id="commonPending"', body)
        self.assertIn(b'id="casePending"', body)
        self.assertIn(b'id="organizationFilter"', body)
        self.assertIn(b'id="categoryStats"', body)
        self.assertIn(b'id="recentSent"', body)
        self.assertEqual(body.count(b'<script src="/poc/master-press/app.js?v=20260720-3"></script>'), 1)
        self.assertIn('"id": "master-press"', homepage)
        renderer_order = re.search(
            r"function renderMoisKmsLab\(p\)\{.*?\n    \}\n\n    function renderMasterPressLab\(p\)\{.*?"
            r"\n    \}\n\n    function renderMultiAgentHarnessLab\(p\)\{",
            homepage,
            re.S,
        )
        self.assertIsNotNone(renderer_order, "AI 언론동향 비서 렌더러가 다른 렌더러 안에 중첩됐습니다.")

    def test_public_api_and_admin_protection(self):
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/dashboard"))
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["project"]["id"], "master-press")
        self.assertIn("organizations", data)
        self.assertLessEqual(len(data["dashboard"]["articles"]), 20)
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/admin/bootstrap"))
        self.assertEqual(status, 401)
        self.assertIn("관리자", json.loads(body)["error"])

    def test_article_link_redirects_to_saved_original(self):
        module = main.load_master_press_module()
        article, _created = module.get_service().store.upsert_article({
            "canonical_url": "https://news.example/article/redirect-test",
            "original_url": "https://news.example/article/redirect-test?from=masterpress",
            "title": "원문 연결 시험",
            "publisher": "news.example",
            "published_at": None,
            "snippet": "",
            "source_type": "test",
        })
        status, headers, _body = asyncio.run(call_app(
            f"/poc/master-press/article/{article['id']}"
        ))
        self.assertEqual(status, 302)
        self.assertEqual(
            headers[b"location"],
            b"https://news.example/article/redirect-test?from=masterpress",
        )

    def test_shared_admin_cookie_creates_case(self):
        token = main.ADMIN_AUTH.issue_session()
        cookie = f"{SESSION_COOKIE}={token}"
        payload = {
            "name": "통합 시험", "topic_description": "공공 인공지능 정책",
            "include_terms": ["인공지능"], "required_terms": [], "exclude_terms": [],
            "urgent_terms": [], "synonym_terms": {}, "include_publishers": [],
            "exclude_publishers": [], "rss_urls": [], "collection_mode": "interval",
            "collection_interval_minutes": 30, "collection_times": [],
            "delivery_mode": "immediate", "delivery_times": [],
            "relevance_threshold": 75, "hold_threshold": 55,
            "keyword_weight": 0.3, "semantic_weight": 0.4, "llm_weight": 0.3,
            "max_articles_per_message": 2, "is_active": True, "recipient_ids": [],
        }
        status, _headers, body = asyncio.run(call_app(
            "/api/poc/master-press/admin/cases", "POST", payload, cookie
        ))
        self.assertEqual(status, 200, body.decode("utf-8"))
        created = json.loads(body)["case"]
        self.assertEqual(created["name"], "통합 시험")
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/dashboard"))
        self.assertEqual(status, 200)
        self.assertTrue(any(item["id"] == created["id"] for item in json.loads(body)["cases"]))


if __name__ == "__main__":
    unittest.main()
