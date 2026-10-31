from __future__ import annotations

import json
import unittest
from unittest import mock

import main
import poc10_proxy
import httpx


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
            "/mmj": "/poc/mwomeokji/",
            "/home": "/poc/home/",
            "/imgscan": "/poc/image-inspection/",
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

    async def test_home_page_and_api_proxy_to_independent_service(self):
        expected = main.HOME_PAGE.read_bytes()
        observed = []
        def upstream(request):
            observed.append(str(request.url))
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8", "cache-control": "no-cache", "content-length": str(len(expected))}, content=expected)
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream)
        for path in ("/poc/home", "/poc/home/", "/poc/home/api/overview"):
            for method in ("GET", "HEAD"):
                with self.subTest(path=path, method=method), mock.patch.object(poc10_proxy.httpx, "AsyncClient", side_effect=lambda **kw: original_client(transport=transport, **kw)):
                    start, body = await call_app(path, method=method)
                    headers = dict(start["headers"])
                    self.assertEqual(start["status"], 200)
                    self.assertEqual(headers[b"content-type"], b"text/html; charset=utf-8")
                    self.assertEqual(headers[b"content-length"], str(len(expected)).encode("ascii"))
                    self.assertEqual(headers[b"cache-control"], b"no-cache")
                    self.assertEqual(body, b"" if method == "HEAD" else expected)
                    self.assertIn(b"/poc/home/assets/app.js", expected)
        self.assertTrue(all(url.startswith(main.HOME_UPSTREAM + "/poc/home") for url in observed))

    async def test_home_admin_refresh_rejects_anonymous_and_forged_headers(self):
        start, _ = await call_app("/poc/home/api/admin/refresh", method="POST", headers=[
            (b"x-home-admin", b"forged"), (b"origin", b"https://www.minslab.kr"), (b"host", b"www.minslab.kr")])
        self.assertEqual(start["status"], 401)

    async def test_home_target_write_requires_admin_same_origin_and_internal_signature(self):
        path='/poc/home/api/admin/targets/PRO_TEST'
        start,_=await call_app(path,method='POST')
        self.assertEqual(start['status'],401)
        observed=[]
        def upstream(request):
            observed.append(request)
            return httpx.Response(200,json={'revision_no':1})
        original_client=httpx.AsyncClient
        with mock.patch.object(main,'admin_session',return_value={'subject':'admin'}), \
             mock.patch.object(poc10_proxy,'internal_secret',return_value='home-goal-test-secret'), \
             mock.patch.object(poc10_proxy.httpx,'AsyncClient',side_effect=lambda **kw:original_client(transport=httpx.MockTransport(upstream),**kw)):
            start,_=await call_app(path,method='POST',headers=[(b'host',b'www.minslab.kr'),(b'origin',b'https://untrusted.example')])
            self.assertEqual(start['status'],403)
            self.assertFalse(observed)
            start,_=await call_app(path,method='POST',headers=[(b'host',b'www.minslab.kr'),(b'origin',b'https://www.minslab.kr'),(b'x-home-admin',b'forged')])
            self.assertEqual(start['status'],200)
            self.assertNotEqual(observed[0].headers.get('x-home-admin'),'forged')
            self.assertIn('x-home-admin',observed[0].headers)

    async def test_home_two_stage_mapping_writes_use_existing_admin_boundary(self):
        paths = ['/poc/home/api/admin/programs/PRG_TEST/policy',
                 '/poc/home/api/admin/projects/PRO_TEST/program']
        observed = []
        def upstream(request):
            observed.append(request)
            return httpx.Response(200, json={'revision_no': 2})
        original_client = httpx.AsyncClient
        for path in paths:
            start, _ = await call_app(path, method='POST')
            self.assertEqual(start['status'], 401)
            with mock.patch.object(main, 'admin_session', return_value={'subject': 'admin'}), \
                 mock.patch.object(poc10_proxy, 'internal_secret', return_value='home-hierarchy-test-secret'), \
                 mock.patch.object(poc10_proxy.httpx, 'AsyncClient', side_effect=lambda **kw: original_client(transport=httpx.MockTransport(upstream), **kw)):
                start, _ = await call_app(path, method='POST', headers=[(b'host', b'www.minslab.kr'),
                    (b'origin', b'https://untrusted.example')])
                self.assertEqual(start['status'], 403)
                start, _ = await call_app(path, method='POST', headers=[(b'host', b'www.minslab.kr'),
                    (b'origin', b'https://www.minslab.kr'), (b'x-home-admin', b'forged')])
                self.assertEqual(start['status'], 200)
                self.assertNotEqual(observed[-1].headers.get('x-home-admin'), 'forged')

    async def test_home_proxy_does_not_forward_cookies_or_incoming_signature(self):
        observed = {}
        def upstream(request):
            observed.update(dict(request.headers))
            return httpx.Response(200, json={"ok": True})
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream)
        with mock.patch.object(poc10_proxy.httpx, "AsyncClient", side_effect=lambda **kw: original_client(transport=transport, **kw)):
            start, _ = await call_app("/poc/home/api/sources", headers=[(b"cookie", b"other_poc=hidden"), (b"x-home-admin", b"forged")])
        self.assertEqual(start["status"], 200)
        self.assertNotIn("cookie", observed)
        self.assertNotIn("x-home-admin", observed)

    async def test_home_admin_writes_require_same_origin_and_server_signature(self):
        observed = []
        def upstream(request):
            observed.append(request)
            return httpx.Response(202, json={"status":"ACCEPTED"})
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(upstream)
        with mock.patch.object(main,"admin_session",return_value={"subject":"admin"}), \
             mock.patch.object(poc10_proxy,"internal_secret",return_value="home-proxy-test-secret"), \
             mock.patch.object(poc10_proxy.httpx,"AsyncClient",side_effect=lambda **kw:original_client(transport=transport,**kw)):
            start,_ = await call_app('/poc/home/api/admin/refresh',method='POST',headers=[
                (b'host',b'www.minslab.kr'),(b'origin',b'https://untrusted.example')])
            self.assertEqual(start['status'],403)
            self.assertFalse(observed)
            start,_ = await call_app('/poc/home/api/admin/refresh',method='POST',headers=[
                (b'host',b'www.minslab.kr'),(b'origin',b'https://www.minslab.kr'),(b'x-home-admin',b'forged')])
            self.assertEqual(start['status'],202)
            self.assertIn('x-home-admin',observed[0].headers)
            self.assertNotEqual(observed[0].headers['x-home-admin'],'forged')

    async def test_home_paths_reject_write_methods(self):
        for path in ("/home", "/home/", "/poc/home", "/poc/home/"):
            with self.subTest(path=path):
                start, body = await call_app(path, method="POST")
                self.assertEqual(start["status"], 405)
                self.assertEqual(dict(start["headers"])[b"allow"], b"GET, HEAD")
                self.assertIn(b"method not allowed", body)





    async def test_poc_shortcuts_reject_write_methods(self):
        start, body = await call_app("/kjon", method="POST")
        headers = dict(start["headers"])

        self.assertEqual(start["status"], 405)
        self.assertEqual(headers[b"allow"], b"GET, HEAD")
        self.assertIn(b"method not allowed", body)



    async def test_ai_common_radar_put_is_supported_and_requires_admin(self):
        with mock.patch.object(main, "admin_session", return_value=None):
            start, body = await call_app(
                "/poc/ai-common-platform-radar/api/settings/opinion-sender",
                method="PUT",
                headers=[(b"content-type", b"application/json")],
            )

        self.assertEqual(start["status"], 401)
        self.assertIn("홈페이지 관리자 로그인이 필요합니다".encode("utf-8"), body)

    async def test_ai_common_radar_put_forwards_internal_signed_token(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "application/json",
            "location": None,
        }.get(name, default)
        upstream_headers.get_all.return_value = []
        upstream = mock.MagicMock()
        upstream.status = 200
        upstream.headers = upstream_headers
        upstream.read.return_value = b'{"saved":true}'
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with (
            mock.patch.object(main, "admin_session", return_value={"exp": 1}),
            mock.patch.object(main, "AI_COMMON_RADAR_PROXY_TOKEN", "derived-internal-token"),
            mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened,
        ):
            start, body = await call_app(
                "/poc/ai-common-platform-radar/api/settings/opinion-sender",
                method="PUT",
                headers=[(b"content-type", b"application/json")],
            )

        request = opened.call_args.args[0]
        forwarded_headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(forwarded_headers["x-poc08-proxy-token"], "derived-internal-token")
        self.assertEqual(start["status"], 200)
        self.assertEqual(body, b'{"saved":true}')

    async def test_ai_common_radar_admin_get_forwards_internal_signed_token(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "text/html; charset=utf-8",
            "location": None,
        }.get(name, default)
        upstream_headers.get_all.return_value = []
        upstream = mock.MagicMock()
        upstream.status = 200
        upstream.headers = upstream_headers
        upstream.read.return_value = b"settings"
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with (
            mock.patch.object(main, "admin_session", return_value={"exp": 1}),
            mock.patch.object(main, "AI_COMMON_RADAR_PROXY_TOKEN", "derived-internal-token"),
            mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened,
        ):
            start, body = await call_app("/poc/ai-common-platform-radar/settings")

        request = opened.call_args.args[0]
        forwarded_headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(start["status"], 200)
        self.assertEqual(body, b"settings")
        self.assertEqual(forwarded_headers["x-poc08-proxy-token"], "derived-internal-token")

    async def test_ai_common_radar_settings_login_is_forwarded_without_parent_session(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "text/html; charset=utf-8",
            "location": None,
        }.get(name, default)
        upstream_headers.get_all.return_value = []
        upstream = mock.MagicMock()
        upstream.status = 401
        upstream.headers = upstream_headers
        upstream.read.return_value = b"login handled by poc08"
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with (
            mock.patch.object(main, "admin_session", return_value=None),
            mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened,
        ):
            start, body = await call_app(
                "/poc/ai-common-platform-radar/settings/login",
                method="POST",
                headers=[(b"content-type", b"application/x-www-form-urlencoded")],
            )

        request = opened.call_args.args[0]
        forwarded_headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(start["status"], 401)
        self.assertEqual(body, b"login handled by poc08")
        self.assertNotIn("x-poc08-proxy-token", forwarded_headers)

    async def test_ai_common_radar_signed_backend_session_cookie_is_forwarded(self):
        upstream_headers = mock.MagicMock()
        upstream_headers.get.side_effect = lambda name, default=None: {
            "content-type": "application/json",
            "location": None,
        }.get(name, default)
        upstream_headers.get_all.return_value = []
        upstream = mock.MagicMock()
        upstream.status = 200
        upstream.headers = upstream_headers
        upstream.read.return_value = b'{"saved":true}'
        upstream.__enter__.return_value = upstream
        upstream.__exit__.return_value = False
        with (
            mock.patch.object(main, "admin_session", return_value=None),
            mock.patch.object(main.url_request, "urlopen", return_value=upstream) as opened,
        ):
            start, body = await call_app(
                "/poc/ai-common-platform-radar/api/settings/opinion-sender",
                method="PUT",
                headers=[
                    (b"content-type", b"application/json"),
                    (b"cookie", b"unrelated=value; poc08_admin_session=signed.backend.token"),
                ],
            )

        request = opened.call_args.args[0]
        forwarded_headers = {name.lower(): value for name, value in request.header_items()}
        self.assertEqual(start["status"], 200)
        self.assertEqual(body, b'{"saved":true}')
        self.assertEqual(forwarded_headers["cookie"], "poc08_admin_session=signed.backend.token")
        self.assertNotIn("x-poc08-proxy-token", forwarded_headers)

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


class RetirementTests(unittest.IsolatedAsyncioTestCase):
    async def test_retired_routes_never_load_or_forward(self):
        for path in ['/poc/mois-kms/', '/api/poc/mois-kms/tasks',
                     '/poc/north-korea-night-lights/map', '/poc/mwomeokji/api/health']:
            for method in ['GET', 'POST', 'HEAD']:
                start, body = await call_app(path, method=method)
                self.assertEqual(start['status'], 410, (path, method))
                if method == 'HEAD': self.assertEqual(body, b'')


class PausedProjectTests(unittest.IsolatedAsyncioTestCase):
    async def test_poc04_retains_code_but_blocks_runtime_when_paused(self):
        with mock.patch.object(main,'MASTER_PRESS_PAUSED',True), mock.patch.object(main,'load_master_press_module',side_effect=AssertionError('must stay paused')):
            start,body=await call_app('/api/poc/master-press/collect',method='POST')
            self.assertEqual(start['status'],503)
            start,body=await call_app('/poc/master-press/')
            self.assertEqual(start['status'],200)
