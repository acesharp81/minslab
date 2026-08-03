from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import unittest
from unittest import mock
from pathlib import Path


TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["MASTER_PRESS_DATA_DIR"] = TEMP_DIR.name
os.environ["SUPABASE2_URL"] = ""
os.environ["SUPABASE2_SERVICE_ROLE_KEY"] = ""

import main
from admin_auth import SESSION_COOKIE


def case_payload(index: int = 1) -> dict:
    return {
        "name": f"케이스 {index}",
        "topic_description": "인공지능 행정 서비스 정책",
        "include_terms": ["인공지능", "행정"],
        "required_terms": [],
        "exclude_terms": ["광고"],
        "urgent_terms": ["긴급"],
        "synonym_terms": {},
        "include_publishers": [],
        "exclude_publishers": [],
        "rss_urls": [],
        "collection_mode": "interval",
        "collection_interval_minutes": 10,
        "collection_times": [],
        "delivery_mode": "immediate",
        "delivery_times": [],
        "send_relevant_immediately": True,
        "relevance_threshold": 70,
        "hold_threshold": 55,
        "keyword_weight": 0,
        "semantic_weight": 0.25,
        "llm_weight": 0.75,
        "max_articles_per_message": 2,
        "is_active": True,
    }


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
        self.assertEqual(body.count(b'<script src="/poc/master-press/app.js?v='), 1)
        self.assertIn(b'<script src="/poc/master-press/app.js?v=', body)
        self.assertIn(b'id="signupView"', body)
        self.assertIn("매뉴얼".encode("utf-8"), body)
        self.assertLess(body.index("구독 및 케이스 신청".encode("utf-8")), body.index("매거진".encode("utf-8")))
        self.assertLess(body.index("매거진".encode("utf-8")), body.index("대시보드".encode("utf-8")))
        self.assertIn(b'id="magazineView"', body)
        self.assertIn(b'id="magazineAdminActions"', body)
        self.assertIn(b'id="republishMagazine"', body)
        self.assertIn(b'id="resendMagazine"', body)
        self.assertIn(b'id="analysisThresholdStatus"', body)
        self.assertIn(b'href="/poc/master-press/manual.pdf"', body)
        self.assertIn(b'id="manualView"', body)
        self.assertIn("시간당 30건 이상 메시지".encode("utf-8"), body)

        self.assertIn("카카오 메시지 동의 확인 전".encode("utf-8"), body)
        self.assertIn("유사 기사 묶음 기준".encode("utf-8"), body)
        self.assertIn("오류·전환 분석 로그".encode("utf-8"), body)
        self.assertIn(b'id="operationLogList"', body)
        self.assertNotIn("저유사도 개선 자료".encode("utf-8"), body)
        self.assertIn(b'id="startKakaoSignup"', body)
        self.assertIn(b'id="startKakaoUnsubscribe"', body)
        self.assertIn("메시지는 '나와의 채팅'으로 발송됩니다.".encode("utf-8"), body)
        self.assertIn(b'id="submitSignupRequest"', body)
        self.assertIn("구독 신청".encode("utf-8"), body)
        self.assertIn(b'id="articleSearch"', body)
        self.assertNotIn(b'id="activeFilterLabel"', body)
        self.assertEqual(body.count(b'data-article-delivery-filter='), 3)
        self.assertIn("전체 목록".encode("utf-8"), body)
        self.assertIn(b'id="pressSearch"', body)
        self.assertIn(b'id="pressMatchThreshold"', body)
        self.assertIn(b'id="bodyBackfillSummary"', body)
        self.assertIn("발송목록".encode("utf-8"), body)
        self.assertIn("미발송목록".encode("utf-8"), body)
        self.assertIn('"id": "master-press"', homepage)
        renderer_order = re.search(
            r"function renderMoisKmsLab\(p\)\{.*?\n    \}\n\n    function renderMasterPressLab\(p\)\{.*?"
            r"\n    \}\n\n    function renderMultiAgentHarnessLab\(p\)\{",
            homepage,
            re.S,
        )
        self.assertIsNotNone(renderer_order, "AI 언론동향 비서 렌더러가 다른 렌더러 안에 중첩됐습니다.")

    def test_unsubscribe_oauth_callback_returns_to_signup(self):
        module = type("Module", (), {
            "complete_kakao_authorization": staticmethod(
                lambda code, state: {"_oauth_action": "unsubscribe", "deleted": True}
            ),
        })()
        with mock.patch.object(main, "load_master_press_module", return_value=module):
            status, headers, _body = asyncio.run(call_app(
                "/poc/master-press/oauth/kakao/callback?code=test-code&state=test-state"
            ))
        self.assertEqual(status, 302)
        self.assertEqual(headers[b"location"], b"/poc/master-press/?view=signup&unsubscribed=1")

    def test_public_unsubscribe_starts_short_lived_kakao_login(self):
        status, _headers, body = asyncio.run(call_app(
            "/api/poc/master-press/signup/kakao-unsubscribe", "POST", {}
        ))
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertIn("/poc/master-press/connect?invite=", data["registration"]["registration_url"])

    def test_master_press_manual_pdf_download(self):
        status, headers, body = asyncio.run(call_app("/poc/master-press/manual.pdf"))
        self.assertEqual(status, 200)
        self.assertEqual(headers.get(b"content-type"), b"application/pdf")
        self.assertIn(b"manual.pdf", headers.get(b"content-disposition", b""))
        self.assertTrue(body.startswith(b"%PDF"))

    def test_public_api_and_admin_protection(self):
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/dashboard"))
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data["project"]["id"], "master-press")
        self.assertIn("organizations", data)
        self.assertLessEqual(len(data["dashboard"]["articles"]), 20)
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/signup/bootstrap"))
        self.assertEqual(status, 200)
        self.assertIn("requests", json.loads(body))
        status, _headers, body = asyncio.run(call_app("/api/poc/master-press/admin/bootstrap"))
        self.assertEqual(status, 401)
        self.assertIn("관리자", json.loads(body)["error"])

    def test_public_dashboard_coalesces_same_filter_requests(self):
        module = main.load_master_press_module()
        module._PUBLIC_DASHBOARD_CACHE.clear()
        module._PUBLIC_DASHBOARD_LOCKS.clear()
        expected = {"project": {"id": "master-press"}, "dashboard": {"articles": []}}
        with mock.patch.object(module, "_build_public_dashboard", return_value=expected) as build:
            first = module.public_dashboard(organization_id="organization-1", limit=30)
            first["dashboard"]["articles"].append({"id": "mutated"})
            second = module.public_dashboard(organization_id="organization-1", limit=30)
        self.assertEqual(build.call_count, 1)
        self.assertEqual(second, expected)

    def test_analysis_threshold_save_is_returned_by_fresh_admin_bootstrap(self):
        token = main.ADMIN_AUTH.issue_session()
        cookie = f"{SESSION_COOKIE}={token}"
        payload = {
            "batch_size": 10,
            "semantic_candidate_threshold": 50,
            "press_release_match_threshold": 70,
            "similar_article_threshold": 70,
            "magazine_similarity_threshold": 82,
            "openai_shadow_enabled": False,
            "openai_shadow_daily_limit": 150,
        }
        status, _headers, body = asyncio.run(call_app(
            "/api/poc/master-press/admin/settings/analysis-thresholds", "PUT", payload, cookie
        ))
        self.assertEqual(status, 200, body.decode("utf-8"))
        self.assertEqual(json.loads(body)["magazine_similarity_threshold"], 82)

        status, _headers, body = asyncio.run(call_app(
            "/api/poc/master-press/admin/bootstrap", "GET", None, cookie
        ))
        self.assertEqual(status, 200, body.decode("utf-8"))
        settings = json.loads(body)["settings"]
        self.assertEqual(settings["magazine_similarity_threshold"], 82)
        self.assertFalse(settings["openai_shadow_enabled"])

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

    def test_admin_analysis_feedback_route_stores_and_reports_feedback(self):
        module = main.load_master_press_module()
        service = module.get_service()
        case = service.store.save_case(case_payload())
        article, _created = service.store.upsert_article({
            "canonical_url": "https://example.com/admin-feedback",
            "original_url": "https://example.com/admin-feedback",
            "title": "관리자 피드백 기사",
            "publisher": "example.com",
            "published_at": None,
            "snippet": "관리자 피드백 API 테스트",
            "source_type": "test",
        })
        token = main.ADMIN_AUTH.issue_session()
        cookie = f"{SESSION_COOKIE}={token}"
        status, _headers, body = asyncio.run(call_app(
            f"/api/poc/master-press/admin/analysis/{article['id']}/{case['id']}/feedback",
            "POST",
            {"reasons": ["negative_signal_missing"], "comment": "부정 신호가 부족합니다."},
            cookie,
        ))
        self.assertEqual(status, 200, body.decode("utf-8"))
        response = json.loads(body)
        self.assertEqual(response["saved"], 1)
        self.assertEqual(response["feedback"]["total"], 1)
        self.assertEqual(response["feedback"]["breakdown"][0]["reason"], "negative_signal_missing")

        status, _headers, body = asyncio.run(call_app(
            f"/api/poc/master-press/admin/analysis/{article['id']}/{case['id']}/report",
            "GET",
            None,
            cookie,
        ))
        self.assertEqual(status, 200)
        report = json.loads(body)
        self.assertEqual(report["feedback"]["total"], 1)
        self.assertEqual(report["feedback"]["breakdown"][0]["reason"], "negative_signal_missing")

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
