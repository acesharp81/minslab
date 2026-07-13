from __future__ import annotations

import unittest

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

    async def test_admin_analytics_requires_session(self):
        start, body = await call_app("/api/admin/analytics")
        self.assertEqual(start["status"], 401)
        self.assertIn("관리자 로그인이 필요합니다".encode("utf-8"), body)

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
