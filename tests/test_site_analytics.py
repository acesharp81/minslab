from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timedelta, timezone
from pathlib import Path

from admin_auth import AdminAuth, configured_admin_password
from analytics_store import AnalyticsStore, normalize_page_path
from runtime_monitor import drain_http_window, observe_http_request
from system_metrics import (
    calculate_cpu_percent,
    read_memory_details,
    read_memory_percent,
    read_memory_pressure_avg10,
    read_oom_kills,
    read_filesystem_usage,
    read_service_memory_bytes,
)


class AnalyticsStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = AnalyticsStore(Path(self.temp_dir.name) / "analytics.sqlite3", retention_days=90)
        self.instant = datetime(2026, 7, 10, 15, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_records_rollups_visitors_and_deduplicates(self):
        first = self.store.record_visit(
            visitor_id="browser-a",
            ip_address="203.0.113.10",
            path="/portfolio?project=demo",
            page_title="Demo",
            user_agent="Test Browser",
            visited_at=self.instant,
        )
        duplicate = self.store.record_visit(
            visitor_id="browser-a",
            ip_address="203.0.113.10",
            path="/portfolio?project=demo",
            visited_at=self.instant + timedelta(seconds=1),
        )
        second_page = self.store.record_visit(
            visitor_id="browser-a",
            ip_address="203.0.113.10",
            path="/poc",
            visited_at=self.instant + timedelta(seconds=3),
        )
        second_visitor = self.store.record_visit(
            visitor_id="browser-b",
            ip_address="198.51.100.20",
            path="/",
            visited_at=self.instant + timedelta(seconds=4),
        )

        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertTrue(second_page)
        self.assertTrue(second_visitor)
        summary = self.store.get_summary("2026-07-11")
        self.assertEqual(summary["total_views"], 3)
        self.assertEqual(summary["today_views"], 3)
        self.assertEqual(summary["today_visitors"], 2)
        self.assertEqual(summary["total_visitors"], 2)
        self.assertEqual(len(summary["trend"]["cumulative_views"]), 7)
        self.assertEqual(summary["trend"]["cumulative_views"][-1], 3)
        self.assertTrue(all(
            left <= right
            for left, right in zip(
                summary["trend"]["cumulative_views"],
                summary["trend"]["cumulative_views"][1:],
            )
        ))
        self.assertEqual(len(summary["trend"]["page_views"]), 7)
        self.assertEqual(summary["trend"]["page_views"][-1], 3)
        self.assertEqual(summary["trend"]["visitors"][-1], 2)

    def test_cumulative_view_trend_includes_pre_window_total(self):
        self.store.record_visit(
            visitor_id="older-browser",
            ip_address="203.0.113.50",
            path="/",
            visited_at=self.instant - timedelta(days=10),
        )
        self.store.record_visit(
            visitor_id="current-browser",
            ip_address="203.0.113.51",
            path="/poc",
            visited_at=self.instant,
        )

        summary = self.store.get_summary("2026-07-11")
        cumulative = summary["trend"]["cumulative_views"]
        self.assertEqual(cumulative[0], 1)
        self.assertEqual(cumulative[-1], summary["total_views"])
        self.assertTrue(all(left <= right for left, right in zip(cumulative, cumulative[1:])))



    def test_local_llm_counter_is_persistent(self):
        self.assertEqual(self.store.increment_metric("local_llm_calls"), 1)
        self.assertEqual(self.store.increment_metric("local_llm_calls", 2), 3)
        summary = self.store.get_summary("2026-07-11")
        self.assertEqual(summary["local_llm_calls"], 3)

    def test_system_metrics_returns_only_requested_history(self):
        now = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        self.store.record_system_metrics(80, 20, now - timedelta(hours=80))
        self.store.record_system_metrics(25, 40, now - timedelta(hours=71))
        self.store.record_system_metrics(150, 50, now)

        metrics = self.store.get_system_metrics(72, now)
        self.assertEqual(len(metrics["points"]), 2)
        self.assertEqual(metrics["cpu"]["current"], 100)
        self.assertEqual(metrics["cpu"]["average"], 62.5)
        self.assertEqual(metrics["memory"]["maximum"], 50)

    def test_operational_memory_metrics_detect_oom_risk(self):
        now = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        details = {
            "memory_total_bytes": 16 * 1024**3,
            "memory_available_bytes": 12 * 1024**3,
            "swap_percent": 0.0,
            "memory_pressure_avg10": 0.0,
            "service_memory_bytes": 180 * 1024**2,
            "service_memory_percent": 1.1,
        }
        self.store.record_system_metrics(
            10, 25, now - timedelta(minutes=1), oom_kills=2, **details
        )
        self.store.record_system_metrics(12, 25, now, oom_kills=3, **details)

        metrics = self.store.get_system_metrics(48, now)
        self.assertEqual(metrics["latest"]["oom_delta"], 1)
        self.assertEqual(metrics["health"]["level"], "critical")
        self.assertAlmostEqual(metrics["service_memory"]["current"], 180)
        self.assertEqual(metrics["latest"]["available_percent"], 75)

    def test_service_probe_and_disk_http_risk_are_reported(self):
        now = datetime(2026, 7, 16, 1, 0, tzinfo=timezone.utc)
        self.store.record_system_metrics(
            20,
            40,
            now,
            memory_total_bytes=16 * 1024**3,
            memory_available_bytes=10 * 1024**3,
            disk_total_bytes=100 * 1024**3,
            disk_available_bytes=4 * 1024**3,
            disk_used_percent=96,
            inode_used_percent=20,
            io_pressure_avg10=0,
            http_requests=10,
            http_errors=3,
            http_p95_ms=6000,
        )
        self.store.record_service_probe(
            probe_ok=False,
            latency_ms=10,
            status_code=None,
            error="connection refused",
            service_active=False,
            restart_count=3,
            exit_status=1,
            sampled_at=now,
        )

        metrics = self.store.get_system_metrics(48, now)
        self.assertEqual(metrics["health"]["level"], "critical")
        self.assertFalse(metrics["availability"]["current_ok"])
        self.assertEqual(metrics["http"]["error_rate_15m"], 30)
        self.assertEqual(metrics["latest"]["disk_used_percent"], 96)

    def test_admin_list_filters_and_retention_keeps_rollup(self):
        old = self.instant - timedelta(days=100)
        self.store.record_visit(
            visitor_id="old-browser",
            ip_address="203.0.113.30",
            path="/",
            visited_at=old,
        )
        self.store.record_visit(
            visitor_id="current-browser",
            ip_address="203.0.113.40",
            path="/poc?project=safe",
            visited_at=self.instant,
        )
        result = self.store.list_visits(
            local_date="2026-07-11",
            ip_filter="113.40",
            path_filter="project=safe",
        )
        self.assertEqual(result["pagination"]["total"], 1)
        self.assertEqual(result["items"][0]["ip_address"], "203.0.113.40")
        self.assertEqual(self.store.purge_old_events(now=self.instant), 1)
        self.assertEqual(self.store.get_summary("2026-07-11")["total_views"], 2)

    def test_rejects_external_or_private_routes(self):
        for path in ("https://example.com/", "/api/health", "/admin", "/static/app.js"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                normalize_page_path(path)


class AdminAuthTests(unittest.TestCase):
    def test_signed_session_and_expiration(self):
        auth = AdminAuth(password="correct-password", secret="test-secret", session_seconds=300)
        token = auth.authenticate("correct-password", "203.0.113.5", now=1_000)
        self.assertIsNotNone(auth.verify_session(token, now=1_100))
        self.assertIsNone(auth.verify_session(token, now=1_301))
        self.assertIsNone(auth.verify_session(f"{token}changed", now=1_100))

    def test_literal_key_name_resolves_shared_live_password(self):
        with mock.patch.dict(
            os.environ,
            {"MINSLAB_ADMIN_PASSWORD": "MULTI_AGENT_LIVE_ENABLED_key",
             "MULTI_AGENT_LIVE_ENABLED_key": "shared-secret"},
            clear=True,
        ):
            self.assertEqual(configured_admin_password(), "shared-secret")

    def test_failure_limit(self):
        auth = AdminAuth(
            password="correct-password",
            secret="test-secret",
            max_failures=2,
            failure_window_seconds=60,
        )
        with self.assertRaises(ValueError):
            auth.authenticate("wrong", "203.0.113.5", now=1_000)
        with self.assertRaises(ValueError):
            auth.authenticate("wrong", "203.0.113.5", now=1_001)
        with self.assertRaises(PermissionError):
            auth.authenticate("correct-password", "203.0.113.5", now=1_002)


class SystemMetricsTests(unittest.TestCase):
    def test_cpu_percent_uses_snapshot_delta(self):
        self.assertEqual(calculate_cpu_percent((100, 40), (200, 60)), 80)

    def test_memory_percent_uses_available_memory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            meminfo = Path(temp_dir) / "meminfo"
            meminfo.write_text(
                "MemTotal:       1000 kB\nMemAvailable:    350 kB\n",
                encoding="utf-8",
            )
            self.assertEqual(read_memory_percent(meminfo), 65)

    def test_operational_linux_memory_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meminfo = root / "meminfo"
            pressure = root / "pressure"
            vmstat = root / "vmstat"
            cgroup = root / "cgroup"
            status = root / "status"
            cgroup_root = root / "sys-fs-cgroup"
            service_group = cgroup_root / "system.slice" / "myservice.service"
            service_group.mkdir(parents=True)
            meminfo.write_text(
                "MemTotal:       1000 kB\n"
                "MemAvailable:    350 kB\n"
                "SwapTotal:       500 kB\n"
                "SwapFree:        400 kB\n",
                encoding="utf-8",
            )
            pressure.write_text(
                "some avg10=1.25 avg60=0.50 avg300=0.10 total=10\n",
                encoding="utf-8",
            )
            vmstat.write_text("pgfault 10\noom_kill 3\n", encoding="utf-8")
            cgroup.write_text(
                "0::/system.slice/myservice.service\n", encoding="utf-8"
            )
            status.write_text("VmRSS: 10 kB\n", encoding="utf-8")
            (service_group / "memory.current").write_text(
                str(180 * 1024**2), encoding="utf-8"
            )

            details = read_memory_details(meminfo)
            self.assertEqual(details["memory_percent"], 65)
            self.assertEqual(details["swap_percent"], 20)
            self.assertEqual(read_memory_pressure_avg10(pressure), 1.25)
            self.assertEqual(read_oom_kills(vmstat), 3)
            self.assertEqual(
                read_service_memory_bytes(cgroup, cgroup_root, status),
                180 * 1024**2,
            )

    def test_filesystem_and_http_window_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            filesystem = read_filesystem_usage(Path(temp_dir))
        self.assertGreater(filesystem["disk_total_bytes"], 0)
        self.assertGreaterEqual(filesystem["disk_used_percent"], 0)
        self.assertGreaterEqual(filesystem["inode_used_percent"], 0)

        drain_http_window()
        observe_http_request("/", 200, 100)
        observe_http_request("/api/chat", 503, 500)
        observe_http_request("/api/health", 500, 900)
        window = drain_http_window()
        self.assertEqual(window["http_requests"], 2)
        self.assertEqual(window["http_errors"], 1)
        self.assertEqual(window["http_p95_ms"], 500)


if __name__ == "__main__":
    unittest.main()
