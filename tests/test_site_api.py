from __future__ import annotations

import json
import unittest
from unittest import mock

import main


async def call_app(path: str, method: str = "GET", headers: list[tuple[bytes, bytes]] | None = None):
    sent = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
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
        "headers": headers or [],
        "client": ("203.0.113.10", 12345),
        "server": ("testserver", 443),
    }
    await main.app(scope, receive, send)
    start = next(message for message in sent if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in sent
        if message["type"] == "http.response.body"
    )
    return start, body


class SiteApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_poc_shortcuts_redirect_with_or_without_trailing_slash(self):
        shortcuts = {
            "/press": "/poc/master-press/",
            "/kjon": "/poc/national-assembly/",
            "/airador": "/poc/ai-common-platform-radar/",
        }
        for shortcut, target in shortcuts.items():
            for path in (shortcut, f"{shortcut}/"):
                with self.subTest(path=path):
                    start, body = await call_app(path)
                    headers = dict(start["headers"])
                    self.assertEqual(start["status"], 307)
                    self.assertEqual(headers[b"location"], target.encode("ascii"))
                    self.assertEqual(headers[b"cache-control"], b"no-store")
                    self.assertEqual(headers[b"content-length"], b"0")
                    self.assertEqual(body, b"")

    async def test_poc_shortcut_head_redirect_has_no_body(self):
        start, body = await call_app("/press", method="HEAD")

        self.assertEqual(start["status"], 307)
        self.assertEqual(dict(start["headers"])[b"location"], b"/poc/master-press/")
        self.assertEqual(body, b"")

    async def test_poc_shortcuts_reject_write_methods(self):
        start, body = await call_app("/kjon", method="POST")
        headers = dict(start["headers"])

        self.assertEqual(start["status"], 405)
        self.assertEqual(headers[b"allow"], b"GET, HEAD")
        self.assertIn(b"method not allowed", body)

    async def test_admin_page_is_html_and_not_cacheable(self):
        start, body = await call_app("/admin")
        headers = dict(start["headers"])
        self.assertEqual(start["status"], 200)
        self.assertEqual(headers[b"content-type"], b"text/html; charset=utf-8")
        self.assertEqual(headers[b"cache-control"], b"no-store")
        self.assertEqual(headers[b"x-frame-options"], b"DENY")
        self.assertIn("관리자 로그인".encode("utf-8"), body)
        self.assertIn("Local LLM 호출".encode("utf-8"), body)
        self.assertIn("가동 시간".encode("utf-8"), body)
        self.assertIn("서버 운영 모니터 · 최근 2일".encode("utf-8"), body)
        self.assertIn(b'id="cpuChart"', body)
        self.assertIn(b'id="memoryChart"', body)
        self.assertIn(b'id="serviceMemoryChart"', body)
        self.assertIn(b'HOST MEMORY', body)
        self.assertIn(b'WEB SERVICE', body)
        self.assertIn(b'HTTP LATENCY', body)
        self.assertIn(b'DISK USAGE', body)
        self.assertIn("외부 HTTPS".encode("utf-8"), body)
        self.assertIn("서비스 재시작".encode("utf-8"), body)

    async def test_admin_analytics_requires_session(self):
        start, body = await call_app("/api/admin/analytics")
        self.assertEqual(start["status"], 401)
        self.assertIn("관리자 로그인이 필요합니다".encode("utf-8"), body)

    async def test_admin_analytics_includes_system_metrics(self):
        history = {
            "hours": 48,
            "range_started_at": "2026-07-14T00:00:00+00:00",
            "range_ended_at": "2026-07-16T00:00:00+00:00",
            "points": [],
            "cpu": {"current": None, "average": None, "maximum": None},
            "memory": {"current": None, "average": None, "maximum": None},
        }
        visits = {
            "date": "2026-07-16",
            "items": [],
            "paths": [],
            "pagination": {"page": 1, "pages": 1, "page_size": 50, "total": 0},
        }
        with (
            mock.patch.object(main, "admin_session", return_value={"exp": 1}),
            mock.patch.object(main, "list_analytics_visits", return_value=visits),
            mock.patch.object(main, "get_analytics_summary", return_value={}),
            mock.patch.object(main, "get_system_metric_history", return_value=history),
        ):
            start, body = await call_app("/api/admin/analytics")

        self.assertEqual(start["status"], 200)
        payload = json.loads(body)
        self.assertEqual(payload["system_metrics"]["hours"], 48)
        self.assertEqual(
            payload["system_metrics_interval_seconds"],
            main.SYSTEM_METRICS_INTERVAL_SECONDS,
        )

    async def test_national_assembly_speaker_write_requires_admin(self):
        path = (
            "/poc/national-assembly/api/live/broadcasts/"
            "00000000-0000-4000-8000-000000000001/speakers/1"
        )
        with mock.patch.object(main, "admin_session", return_value=None):
            start, body = await call_app(path, method="PUT")

        self.assertEqual(start["status"], 401)
        self.assertIn("관리자 로그인이 필요합니다".encode("utf-8"), body)

    async def test_national_assembly_topic_report_proxy_forwards_only_poc7_session(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "application/json",
            "location": None,
        }.get(name, default)
        upstream_headers.get_all.side_effect = lambda name, default=None: {
            "set-cookie": [
                "gukjeongbomi_session=new-token; HttpOnly; Secure; SameSite=lax; Path=/poc/national-assembly"
            ],
            "x-llm-calls": ["0"],
        }.get(name, default or [])
        upstream = mock.MagicMock()
        upstream.status = 200
        upstream.headers = upstream_headers
        upstream.read.return_value = b"{\"items\":[],\"count\":0,\"llm_calls\":0}"
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened:
            start, body = await call_app(
                "/poc/national-assembly/api/topic-reports/search",
                method="POST",
                headers=[
                    (b"content-type", b"application/json"),
                    (b"origin", b"https://www.minslab.kr"),
                    (b"cookie", b"parent_admin=do-not-forward; gukjeongbomi_session=browser-token"),
                ],
            )

        request = opened.call_args.args[0]
        self.assertEqual(request.get_header("Cookie"), "gukjeongbomi_session=browser-token")
        self.assertEqual(request.get_header("Origin"), "https://www.minslab.kr")
        headers = dict(start["headers"])
        self.assertEqual(start["status"], 200)
        self.assertEqual(headers[b"x-llm-calls"], b"0")
        self.assertIn(b"HttpOnly", headers[b"set-cookie"])
        self.assertIn(b"default-src 'self'", headers[b"content-security-policy"])
        self.assertIn(b"max-age=31536000", headers[b"strict-transport-security"])
        self.assertIn(b"\"llm_calls\":0", body)

    async def test_national_assembly_admin_session_injects_internal_poc7_token(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "application/json", "location": None,
        }.get(name, default)
        upstream_headers.get_all.return_value = []
        upstream = mock.MagicMock()
        upstream.status = 200
        upstream.headers = upstream_headers
        upstream.read.return_value = b'{"authenticated":true}'
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with (
            mock.patch.object(main, "admin_session", return_value={"exp": 1}),
            mock.patch.object(main, "NATIONAL_ASSEMBLY_ADMIN_TOKEN", "internal-poc07-token"),
            mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened,
        ):
            start, _ = await call_app(
                "/poc/national-assembly/api/watch/admin/session",
            )

        request = opened.call_args.args[0]
        self.assertEqual(request.get_header("X-watch-admin-token"), "internal-poc07-token")
        self.assertEqual(start["status"], 200)

    async def test_national_assembly_other_write_paths_are_not_proxied(self):
        start, _ = await call_app(
            "/poc/national-assembly/api/live/overview", method="DELETE",
        )
        self.assertEqual(start["status"], 404)

    async def test_existing_health_route_remains_available(self):
        start, body = await call_app("/health")
        self.assertEqual(start["status"], 200)
        self.assertIn(b'"status": "healthy"', body)

    async def test_footer_keeps_admin_and_removes_service_health_link(self):
        start, body = await call_app("/")
        self.assertEqual(start["status"], 200)
        self.assertIn(b'href="/admin"', body)
        self.assertNotIn(b'SERVICE HEALTH', body)
        self.assertIn(b'healthSparkline', body)


    def test_linux_host_uptime_is_available(self):
        uptime = main.host_uptime_seconds()
        self.assertIsInstance(uptime, int)
        self.assertGreater(uptime, 0)

if __name__ == "__main__":
    unittest.main()
