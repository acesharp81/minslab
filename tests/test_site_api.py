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
        self.assertIn("서버 리소스 · 최근 3일".encode("utf-8"), body)
        self.assertIn(b'id="cpuChart"', body)
        self.assertIn(b'id="memoryChart"', body)

    async def test_admin_analytics_requires_session(self):
        start, body = await call_app("/api/admin/analytics")
        self.assertEqual(start["status"], 401)
        self.assertIn("관리자 로그인이 필요합니다".encode("utf-8"), body)

    async def test_admin_analytics_includes_system_metrics(self):
        history = {
            "hours": 72,
            "range_started_at": "2026-07-13T00:00:00+00:00",
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
        self.assertEqual(payload["system_metrics"]["hours"], 72)
        self.assertEqual(
            payload["system_metrics_interval_seconds"],
            main.SYSTEM_METRICS_INTERVAL_SECONDS,
        )

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
