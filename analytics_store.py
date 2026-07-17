"""SQLite-backed page-view analytics for the MinsLab site."""

from __future__ import annotations

import hashlib
import ipaddress
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from env_utils import env_first, load_project_env


load_project_env()

APP_DIR = Path(__file__).resolve().parent
SEOUL = ZoneInfo("Asia/Seoul")
UTC = timezone.utc


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return _utc_now()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clean_text(value, limit: int) -> str:
    text = str(value or "").replace("\x00", "").strip()
    return text[:limit]


def normalize_page_path(value: str) -> str:
    """Accept only local public-site paths and retain a small query string."""
    text = _clean_text(value, 600)
    parsed = urlsplit(text)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        raise ValueError("방문 경로가 올바르지 않습니다.")
    allowed = (
        parsed.path == "/"
        or parsed.path == "/portfolio"
        or parsed.path.startswith("/portfolio/")
        or parsed.path == "/poc"
        or parsed.path.startswith("/poc/")
    )
    if not allowed:
        raise ValueError("기록할 수 없는 방문 경로입니다.")
    query = f"?{parsed.query[:300]}" if parsed.query else ""
    return f"{parsed.path[:300]}{query}"


def normalize_ip(value: str) -> str:
    text = _clean_text(value, 80)
    try:
        return ipaddress.ip_address(text).compressed
    except ValueError:
        return "unknown"


class AnalyticsStore:
    """Persist raw visits and durable daily rollups in one SQLite file."""

    def __init__(self, db_path: str | Path, retention_days: int = 90):
        self.db_path = Path(db_path)
        self.retention_days = max(1, int(retention_days))
        self._init_lock = threading.Lock()
        self._initialized = False

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=10000")
        return connection

    def initialize(self) -> None:
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            with self._connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS visit_events (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        visited_at TEXT NOT NULL,
                        local_date TEXT NOT NULL,
                        visitor_key TEXT NOT NULL,
                        ip_address TEXT NOT NULL,
                        path TEXT NOT NULL,
                        page_title TEXT NOT NULL DEFAULT '',
                        referrer TEXT NOT NULL DEFAULT '',
                        user_agent TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS visit_events_date_idx
                        ON visit_events (local_date, visited_at DESC);
                    CREATE INDEX IF NOT EXISTS visit_events_ip_idx
                        ON visit_events (ip_address, visited_at DESC);
                    CREATE INDEX IF NOT EXISTS visit_events_path_idx
                        ON visit_events (path, visited_at DESC);

                    CREATE TABLE IF NOT EXISTS daily_stats (
                        local_date TEXT PRIMARY KEY,
                        page_views INTEGER NOT NULL DEFAULT 0
                    );

                    CREATE TABLE IF NOT EXISTS daily_visitors (
                        local_date TEXT NOT NULL,
                        visitor_key TEXT NOT NULL,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        view_count INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (local_date, visitor_key)
                    );
                    CREATE INDEX IF NOT EXISTS daily_visitors_key_idx
                        ON daily_visitors (visitor_key);

                    CREATE TABLE IF NOT EXISTS metric_counters (
                        metric_key TEXT PRIMARY KEY,
                        metric_value INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS system_metric_samples (
                        sampled_at TEXT PRIMARY KEY,
                        cpu_percent REAL NOT NULL,
                        memory_percent REAL NOT NULL,
                        memory_total_bytes INTEGER,
                        memory_available_bytes INTEGER,
                        swap_percent REAL,
                        memory_pressure_avg10 REAL,
                        oom_kills INTEGER,
                        service_memory_bytes INTEGER,
                        service_memory_percent REAL,
                        disk_total_bytes INTEGER,
                        disk_available_bytes INTEGER,
                        disk_used_percent REAL,
                        inode_used_percent REAL,
                        io_pressure_avg10 REAL,
                        http_requests INTEGER,
                        http_errors INTEGER,
                        http_p95_ms REAL,
                        http_max_ms REAL
                    );
                    CREATE INDEX IF NOT EXISTS system_metric_samples_time_idx
                        ON system_metric_samples (sampled_at);

                    CREATE TABLE IF NOT EXISTS service_probe_samples (
                        sampled_at TEXT PRIMARY KEY,
                        probe_ok INTEGER NOT NULL,
                        latency_ms REAL,
                        status_code INTEGER,
                        error TEXT NOT NULL DEFAULT '',
                        service_active INTEGER,
                        restart_count INTEGER,
                        exit_status INTEGER
                    );
                    CREATE INDEX IF NOT EXISTS service_probe_samples_time_idx
                        ON service_probe_samples (sampled_at);
                    """
                )
                metric_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(system_metric_samples)"
                    ).fetchall()
                }
                migrations = {
                    "memory_total_bytes": "INTEGER",
                    "memory_available_bytes": "INTEGER",
                    "swap_percent": "REAL",
                    "memory_pressure_avg10": "REAL",
                    "oom_kills": "INTEGER",
                    "service_memory_bytes": "INTEGER",
                    "service_memory_percent": "REAL",
                    "disk_total_bytes": "INTEGER",
                    "disk_available_bytes": "INTEGER",
                    "disk_used_percent": "REAL",
                    "inode_used_percent": "REAL",
                    "io_pressure_avg10": "REAL",
                    "http_requests": "INTEGER",
                    "http_errors": "INTEGER",
                    "http_p95_ms": "REAL",
                    "http_max_ms": "REAL",
                }
                for column, column_type in migrations.items():
                    if column not in metric_columns:
                        connection.execute(
                            f"ALTER TABLE system_metric_samples ADD COLUMN {column} {column_type}"
                        )
            self._initialized = True

    def _visitor_key(self, visitor_id: str, ip_address: str, user_agent: str) -> str:
        stable_id = _clean_text(visitor_id, 160)
        if stable_id:
            source = f"browser:{stable_id}"
        else:
            source = f"fallback:{ip_address}:{_clean_text(user_agent, 300)}"
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    def record_visit(
        self,
        *,
        visitor_id: str,
        ip_address: str,
        path: str,
        page_title: str = "",
        referrer: str = "",
        user_agent: str = "",
        visited_at: datetime | None = None,
        dedupe_seconds: int = 2,
    ) -> bool:
        self.initialize()
        instant = _as_utc(visited_at)
        local_date = instant.astimezone(SEOUL).date().isoformat()
        normalized_ip = normalize_ip(ip_address)
        normalized_path = normalize_page_path(path)
        clean_agent = _clean_text(user_agent, 600)
        visitor_key = self._visitor_key(visitor_id, normalized_ip, clean_agent)
        timestamp = instant.isoformat(timespec="microseconds")
        cutoff = (instant - timedelta(seconds=max(0, dedupe_seconds))).isoformat(timespec="microseconds")

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                """
                SELECT 1 FROM visit_events
                WHERE visitor_key = ? AND path = ? AND visited_at >= ?
                LIMIT 1
                """,
                (visitor_key, normalized_path, cutoff),
            ).fetchone()
            if duplicate:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO visit_events
                    (visited_at, local_date, visitor_key, ip_address, path, page_title, referrer, user_agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    local_date,
                    visitor_key,
                    normalized_ip,
                    normalized_path,
                    _clean_text(page_title, 200),
                    _clean_text(referrer, 500),
                    clean_agent,
                ),
            )
            connection.execute(
                """
                INSERT INTO daily_stats (local_date, page_views) VALUES (?, 1)
                ON CONFLICT(local_date) DO UPDATE SET page_views = page_views + 1
                """,
                (local_date,),
            )
            connection.execute(
                """
                INSERT INTO daily_visitors
                    (local_date, visitor_key, first_seen, last_seen, view_count)
                VALUES (?, ?, ?, ?, 1)
                ON CONFLICT(local_date, visitor_key) DO UPDATE SET
                    last_seen = excluded.last_seen,
                    view_count = view_count + 1
                """,
                (local_date, visitor_key, timestamp, timestamp),
            )
            connection.commit()
        return True

    def increment_metric(self, metric_key: str, amount: int = 1) -> int:
        self.initialize()
        key = _clean_text(metric_key, 80)
        if not key or any(not (char.isalnum() or char == "_") for char in key):
            raise ValueError("통계 지표 이름이 올바르지 않습니다.")
        increment = max(1, int(amount))
        updated_at = _utc_now().isoformat(timespec="microseconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO metric_counters (metric_key, metric_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(metric_key) DO UPDATE SET
                    metric_value = metric_value + excluded.metric_value,
                    updated_at = excluded.updated_at
                """,
                (key, increment, updated_at),
            )
            value = connection.execute(
                "SELECT metric_value FROM metric_counters WHERE metric_key = ?", (key,)
            ).fetchone()[0]
        return int(value)

    def record_system_metrics(
        self,
        cpu_percent: float,
        memory_percent: float,
        sampled_at: datetime | None = None,
        *,
        memory_total_bytes: int | None = None,
        memory_available_bytes: int | None = None,
        swap_percent: float | None = None,
        memory_pressure_avg10: float | None = None,
        oom_kills: int | None = None,
        service_memory_bytes: int | None = None,
        service_memory_percent: float | None = None,
        disk_total_bytes: int | None = None,
        disk_available_bytes: int | None = None,
        disk_used_percent: float | None = None,
        inode_used_percent: float | None = None,
        io_pressure_avg10: float | None = None,
        http_requests: int | None = None,
        http_errors: int | None = None,
        http_p95_ms: float | None = None,
        http_max_ms: float | None = None,
    ) -> None:
        self.initialize()
        instant = _as_utc(sampled_at)
        timestamp = instant.isoformat(timespec="microseconds")
        cpu = round(max(0.0, min(100.0, float(cpu_percent))), 2)
        memory = round(max(0.0, min(100.0, float(memory_percent))), 2)
        cutoff = (instant - timedelta(days=7)).isoformat(timespec="microseconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO system_metric_samples
                    (
                        sampled_at, cpu_percent, memory_percent,
                        memory_total_bytes, memory_available_bytes, swap_percent,
                        memory_pressure_avg10, oom_kills,
                        service_memory_bytes, service_memory_percent,
                        disk_total_bytes, disk_available_bytes,
                        disk_used_percent, inode_used_percent, io_pressure_avg10,
                        http_requests, http_errors, http_p95_ms, http_max_ms
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    cpu,
                    memory,
                    max(0, int(memory_total_bytes)) if memory_total_bytes is not None else None,
                    max(0, int(memory_available_bytes)) if memory_available_bytes is not None else None,
                    round(max(0.0, min(100.0, float(swap_percent))), 2)
                    if swap_percent is not None else None,
                    round(max(0.0, float(memory_pressure_avg10)), 2)
                    if memory_pressure_avg10 is not None else None,
                    max(0, int(oom_kills)) if oom_kills is not None else None,
                    max(0, int(service_memory_bytes)) if service_memory_bytes is not None else None,
                    round(max(0.0, min(100.0, float(service_memory_percent))), 3)
                    if service_memory_percent is not None else None,
                    max(0, int(disk_total_bytes)) if disk_total_bytes is not None else None,
                    max(0, int(disk_available_bytes)) if disk_available_bytes is not None else None,
                    round(max(0.0, min(100.0, float(disk_used_percent))), 2)
                    if disk_used_percent is not None else None,
                    round(max(0.0, min(100.0, float(inode_used_percent))), 2)
                    if inode_used_percent is not None else None,
                    round(max(0.0, float(io_pressure_avg10)), 2)
                    if io_pressure_avg10 is not None else None,
                    max(0, int(http_requests)) if http_requests is not None else None,
                    max(0, int(http_errors)) if http_errors is not None else None,
                    round(max(0.0, float(http_p95_ms)), 2)
                    if http_p95_ms is not None else None,
                    round(max(0.0, float(http_max_ms)), 2)
                    if http_max_ms is not None else None,
                ),
            )
            connection.execute(
                "DELETE FROM system_metric_samples WHERE sampled_at < ?",
                (cutoff,),
            )

    def record_service_probe(
        self,
        *,
        probe_ok: bool,
        latency_ms: float | None,
        status_code: int | None,
        error: str = "",
        service_active: bool | None = None,
        restart_count: int | None = None,
        exit_status: int | None = None,
        sampled_at: datetime | None = None,
    ) -> None:
        self.initialize()
        instant = _as_utc(sampled_at)
        timestamp = instant.isoformat(timespec="microseconds")
        cutoff = (instant - timedelta(days=7)).isoformat(timespec="microseconds")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO service_probe_samples (
                    sampled_at, probe_ok, latency_ms, status_code, error,
                    service_active, restart_count, exit_status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    int(bool(probe_ok)),
                    round(max(0.0, float(latency_ms)), 2)
                    if latency_ms is not None else None,
                    int(status_code) if status_code is not None else None,
                    _clean_text(error, 300),
                    int(bool(service_active)) if service_active is not None else None,
                    max(0, int(restart_count)) if restart_count is not None else None,
                    int(exit_status) if exit_status is not None else None,
                ),
            )
            connection.execute(
                "DELETE FROM service_probe_samples WHERE sampled_at < ?",
                (cutoff,),
            )

    def get_system_metrics(
        self,
        hours: int = 72,
        now: datetime | None = None,
    ) -> dict:
        self.initialize()
        range_end = _as_utc(now)
        range_hours = min(168, max(1, int(hours)))
        range_start = range_end - timedelta(hours=range_hours)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    sampled_at, cpu_percent, memory_percent,
                    memory_total_bytes, memory_available_bytes, swap_percent,
                    memory_pressure_avg10, oom_kills,
                    service_memory_bytes, service_memory_percent,
                    disk_total_bytes, disk_available_bytes,
                    disk_used_percent, inode_used_percent, io_pressure_avg10,
                    http_requests, http_errors, http_p95_ms, http_max_ms
                FROM system_metric_samples
                WHERE sampled_at BETWEEN ? AND ?
                ORDER BY sampled_at ASC
                """,
                (
                    range_start.isoformat(timespec="microseconds"),
                    range_end.isoformat(timespec="microseconds"),
                ),
            ).fetchall()
            probe_rows = connection.execute(
                """
                SELECT
                    sampled_at, probe_ok, latency_ms, status_code, error,
                    service_active, restart_count, exit_status
                FROM service_probe_samples
                WHERE sampled_at BETWEEN ? AND ?
                ORDER BY sampled_at ASC
                """,
                (
                    range_start.isoformat(timespec="microseconds"),
                    range_end.isoformat(timespec="microseconds"),
                ),
            ).fetchall()
        points = []
        for row in rows:
            service_bytes = (
                int(row["service_memory_bytes"])
                if row["service_memory_bytes"] is not None
                else None
            )
            points.append({
                "sampled_at": row["sampled_at"],
                "cpu_percent": round(float(row["cpu_percent"]), 2),
                "memory_percent": round(float(row["memory_percent"]), 2),
                "memory_total_bytes": (
                    int(row["memory_total_bytes"])
                    if row["memory_total_bytes"] is not None else None
                ),
                "memory_available_bytes": (
                    int(row["memory_available_bytes"])
                    if row["memory_available_bytes"] is not None else None
                ),
                "swap_percent": (
                    round(float(row["swap_percent"]), 2)
                    if row["swap_percent"] is not None else None
                ),
                "memory_pressure_avg10": (
                    round(float(row["memory_pressure_avg10"]), 2)
                    if row["memory_pressure_avg10"] is not None else None
                ),
                "oom_kills": (
                    int(row["oom_kills"]) if row["oom_kills"] is not None else None
                ),
                "service_memory_bytes": service_bytes,
                "service_memory_mb": (
                    round(service_bytes / (1024 * 1024), 2)
                    if service_bytes is not None else None
                ),
                "service_memory_percent": (
                    round(float(row["service_memory_percent"]), 3)
                    if row["service_memory_percent"] is not None else None
                ),
                "disk_total_bytes": (
                    int(row["disk_total_bytes"])
                    if row["disk_total_bytes"] is not None else None
                ),
                "disk_available_bytes": (
                    int(row["disk_available_bytes"])
                    if row["disk_available_bytes"] is not None else None
                ),
                "disk_used_percent": (
                    round(float(row["disk_used_percent"]), 2)
                    if row["disk_used_percent"] is not None else None
                ),
                "inode_used_percent": (
                    round(float(row["inode_used_percent"]), 2)
                    if row["inode_used_percent"] is not None else None
                ),
                "io_pressure_avg10": (
                    round(float(row["io_pressure_avg10"]), 2)
                    if row["io_pressure_avg10"] is not None else None
                ),
                "http_requests": (
                    int(row["http_requests"]) if row["http_requests"] is not None else None
                ),
                "http_errors": (
                    int(row["http_errors"]) if row["http_errors"] is not None else None
                ),
                "http_p95_ms": (
                    round(float(row["http_p95_ms"]), 2)
                    if row["http_p95_ms"] is not None else None
                ),
                "http_max_ms": (
                    round(float(row["http_max_ms"]), 2)
                    if row["http_max_ms"] is not None else None
                ),
            })

        def aggregate(key: str) -> dict:
            values = [
                float(point[key])
                for point in points
                if point.get(key) is not None
            ]
            return {
                "current": round(values[-1], 2) if values else None,
                "average": round(sum(values) / len(values), 2) if values else None,
                "maximum": round(max(values), 2) if values else None,
            }

        service = aggregate("service_memory_mb")
        recent_service = [
            point for point in points
            if point.get("service_memory_mb") is not None
            and datetime.fromisoformat(point["sampled_at"]) >= range_end - timedelta(hours=6)
        ]
        service["growth_6h_mb"] = round(
            recent_service[-1]["service_memory_mb"] - recent_service[0]["service_memory_mb"],
            2,
        ) if len(recent_service) >= 2 else None

        recent_http = [
            point for point in points
            if datetime.fromisoformat(point["sampled_at"]) >= range_end - timedelta(minutes=15)
        ]
        http_requests = sum(int(point.get("http_requests") or 0) for point in recent_http)
        http_errors = sum(int(point.get("http_errors") or 0) for point in recent_http)
        http_p95_values = [
            float(point["http_p95_ms"])
            for point in recent_http
            if point.get("http_p95_ms") is not None
        ]
        http = {
            "requests_15m": http_requests,
            "errors_15m": http_errors,
            "error_rate_15m": round(http_errors / http_requests * 100.0, 2)
            if http_requests else 0.0,
            "p95_window_max_ms": round(max(http_p95_values), 2)
            if http_p95_values else None,
        }

        probes = [
            {
                "sampled_at": row["sampled_at"],
                "ok": bool(row["probe_ok"]),
                "latency_ms": round(float(row["latency_ms"]), 2)
                if row["latency_ms"] is not None else None,
                "status_code": int(row["status_code"])
                if row["status_code"] is not None else None,
                "error": row["error"],
                "service_active": bool(row["service_active"])
                if row["service_active"] is not None else None,
                "restart_count": int(row["restart_count"])
                if row["restart_count"] is not None else None,
                "exit_status": int(row["exit_status"])
                if row["exit_status"] is not None else None,
            }
            for row in probe_rows
        ]
        latest_probe = probes[-1] if probes else {}
        successful_probes = sum(1 for probe in probes if probe["ok"])
        recent_probes = [
            probe for probe in probes
            if datetime.fromisoformat(probe["sampled_at"]) >= range_end - timedelta(minutes=15)
        ]
        restart_values = [
            int(probe["restart_count"])
            for probe in recent_probes
            if probe.get("restart_count") is not None
        ]
        availability = {
            "current_ok": latest_probe.get("ok"),
            "latest_latency_ms": latest_probe.get("latency_ms"),
            "latest_status_code": latest_probe.get("status_code"),
            "latest_error": latest_probe.get("error") or "",
            "success_rate": round(successful_probes / len(probes) * 100.0, 2)
            if probes else None,
            "failures_15m": sum(1 for probe in recent_probes if not probe["ok"]),
            "restart_count": latest_probe.get("restart_count"),
            "restarts_15m": max(0, restart_values[-1] - restart_values[0])
            if len(restart_values) >= 2 else 0,
            "service_active": latest_probe.get("service_active"),
            "exit_status": latest_probe.get("exit_status"),
            "points": probes,
        }

        latest = points[-1] if points else {}
        available_percent = (
            round(100.0 - float(latest["memory_percent"]), 2)
            if latest.get("memory_percent") is not None else None
        )
        oom_values = [
            int(point["oom_kills"])
            for point in points
            if point.get("oom_kills") is not None
        ]
        oom_delta = max(0, oom_values[-1] - oom_values[0]) if len(oom_values) >= 2 else 0
        pressure = float(latest.get("memory_pressure_avg10") or 0)
        swap = float(latest.get("swap_percent") or 0)
        service_percent = float(latest.get("service_memory_percent") or 0)
        growth = float(service.get("growth_6h_mb") or 0)
        disk_used = float(latest.get("disk_used_percent") or 0)
        inode_used = float(latest.get("inode_used_percent") or 0)
        disk_available = int(latest.get("disk_available_bytes") or 0)
        io_pressure = float(latest.get("io_pressure_avg10") or 0)
        critical_reasons = []
        warning_reasons = []
        if available_percent is not None and available_percent <= 5:
            critical_reasons.append("가용 메모리 5% 이하")
        if pressure >= 10:
            critical_reasons.append("메모리 압력 PSI 10 이상")
        if oom_delta > 0:
            critical_reasons.append(f"최근 OOM 종료 {oom_delta}회")
        if availability["current_ok"] is False:
            critical_reasons.append("외부 HTTPS 프로브 실패")
        if availability["restarts_15m"] >= 3:
            critical_reasons.append("15분 내 서비스 3회 이상 재시작")
        if disk_used >= 95 or (disk_available and disk_available < 5 * 1024**3):
            critical_reasons.append("디스크 가용 공간 위험")
        if inode_used >= 95:
            critical_reasons.append("inode 가용량 5% 이하")
        if io_pressure >= 10:
            critical_reasons.append("I/O 압력 PSI 10 이상")
        if http["requests_15m"] >= 5 and http["error_rate_15m"] >= 20:
            critical_reasons.append("최근 HTTP 5xx 비율 20% 이상")
        if (http["p95_window_max_ms"] or 0) >= 5000:
            critical_reasons.append("최근 HTTP p95 지연 5초 이상")
        if available_percent is not None and 5 < available_percent <= 15:
            warning_reasons.append("가용 메모리 15% 이하")
        if 1 <= pressure < 10:
            warning_reasons.append("메모리 압력 감지")
        if swap >= 25:
            warning_reasons.append("Swap 사용률 25% 이상")
        if service_percent >= 50:
            warning_reasons.append("웹 서비스가 물리 메모리 50% 이상 사용")
        if growth >= 512:
            warning_reasons.append("웹 서비스 메모리가 6시간 동안 512MB 이상 증가")
        if availability["failures_15m"] > 0 and availability["current_ok"] is not False:
            warning_reasons.append("최근 15분 외부 프로브 실패 이력")
        if 90 <= disk_used < 95 or (
            disk_available and 5 * 1024**3 <= disk_available < 10 * 1024**3
        ):
            warning_reasons.append("디스크 가용 공간 10% 또는 10GB 이하")
        if 90 <= inode_used < 95:
            warning_reasons.append("inode 가용량 10% 이하")
        if 1 <= io_pressure < 10:
            warning_reasons.append("I/O 압력 감지")
        if (
            http["requests_15m"] >= 5
            and 5 <= http["error_rate_15m"] < 20
        ):
            warning_reasons.append("최근 HTTP 5xx 비율 5% 이상")
        if 2000 <= (http["p95_window_max_ms"] or 0) < 5000:
            warning_reasons.append("최근 HTTP p95 지연 2초 이상")
        if critical_reasons:
            health = {
                "level": "critical",
                "label": "위험",
                "summary": "서버 다운 가능성이 높은 운영 징후가 있습니다.",
                "reasons": critical_reasons,
            }
        elif warning_reasons:
            health = {
                "level": "warning",
                "label": "주의",
                "summary": "서버 운영 상태를 관찰해야 합니다.",
                "reasons": warning_reasons,
            }
        elif points and latest.get("memory_available_bytes") is not None:
            health = {
                "level": "normal",
                "label": "정상",
                "summary": "현재 서버 다운 징후가 없습니다.",
                "reasons": [],
            }
        else:
            health = {
                "level": "unknown",
                "label": "수집 중",
                "summary": "운영 지표가 아직 충분하지 않습니다.",
                "reasons": [],
            }

        return {
            "hours": range_hours,
            "range_started_at": range_start.isoformat(timespec="seconds"),
            "range_ended_at": range_end.isoformat(timespec="seconds"),
            "points": points,
            "cpu": aggregate("cpu_percent"),
            "memory": aggregate("memory_percent"),
            "service_memory": service,
            "http": http,
            "availability": availability,
            "latest": {
                "memory_total_bytes": latest.get("memory_total_bytes"),
                "memory_available_bytes": latest.get("memory_available_bytes"),
                "available_percent": available_percent,
                "swap_percent": latest.get("swap_percent"),
                "memory_pressure_avg10": latest.get("memory_pressure_avg10"),
                "oom_kills": latest.get("oom_kills"),
                "oom_delta": oom_delta,
                "service_memory_bytes": latest.get("service_memory_bytes"),
                "service_memory_percent": latest.get("service_memory_percent"),
                "disk_total_bytes": latest.get("disk_total_bytes"),
                "disk_available_bytes": latest.get("disk_available_bytes"),
                "disk_used_percent": latest.get("disk_used_percent"),
                "inode_used_percent": latest.get("inode_used_percent"),
                "io_pressure_avg10": latest.get("io_pressure_avg10"),
            },
            "health": health,
        }


    def get_summary(self, local_date: str | None = None) -> dict:
        self.initialize()
        target_date = local_date or datetime.now(SEOUL).date().isoformat()
        target_day = datetime.strptime(target_date, "%Y-%m-%d").date()
        trend_dates = [(target_day - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
        with self._connect() as connection:
            total_views = connection.execute(
                "SELECT COALESCE(SUM(page_views), 0) FROM daily_stats"
            ).fetchone()[0]
            today_views = connection.execute(
                "SELECT COALESCE(page_views, 0) FROM daily_stats WHERE local_date = ?",
                (target_date,),
            ).fetchone()
            today_visitors = connection.execute(
                "SELECT COUNT(*) FROM daily_visitors WHERE local_date = ?",
                (target_date,),
            ).fetchone()[0]
            total_visitors = connection.execute(
                "SELECT COUNT(DISTINCT visitor_key) FROM daily_visitors"
            ).fetchone()[0]
            local_llm_calls = connection.execute(
                "SELECT COALESCE(metric_value, 0) FROM metric_counters WHERE metric_key = ?",
                ("local_llm_calls",),
            ).fetchone()
            baseline_views = connection.execute(
                "SELECT COALESCE(SUM(page_views), 0) FROM daily_stats WHERE local_date < ?",
                (trend_dates[0],),
            ).fetchone()[0]
            view_rows = connection.execute(
                """
                SELECT local_date, page_views FROM daily_stats
                WHERE local_date BETWEEN ? AND ?
                """,
                (trend_dates[0], trend_dates[-1]),
            ).fetchall()
            visitor_rows = connection.execute(
                """
                SELECT local_date, COUNT(*) AS visitors FROM daily_visitors
                WHERE local_date BETWEEN ? AND ?
                GROUP BY local_date
                """,
                (trend_dates[0], trend_dates[-1]),
            ).fetchall()
        views_by_date = {row["local_date"]: int(row["page_views"]) for row in view_rows}
        visitors_by_date = {row["local_date"]: int(row["visitors"]) for row in visitor_rows}
        cumulative_views = []
        running_views = int(baseline_views or 0)
        for value in trend_dates:
            running_views += views_by_date.get(value, 0)
            cumulative_views.append(running_views)
        return {
            "date": target_date,
            "total_views": int(total_views or 0),
            "today_views": int(today_views[0] if today_views else 0),
            "today_visitors": int(today_visitors or 0),
            "total_visitors": int(total_visitors or 0),
            "local_llm_calls": int(local_llm_calls[0] if local_llm_calls else 0),
            "trend": {
                "labels": [value[5:] for value in trend_dates],
                "cumulative_views": cumulative_views,
                "page_views": [views_by_date.get(value, 0) for value in trend_dates],
                "visitors": [visitors_by_date.get(value, 0) for value in trend_dates],
            },
        }

    def list_visits(
        self,
        *,
        local_date: str | None = None,
        page: int = 1,
        page_size: int = 50,
        ip_filter: str = "",
        path_filter: str = "",
    ) -> dict:
        self.initialize()
        target_date = local_date or datetime.now(SEOUL).date().isoformat()
        page = max(1, int(page))
        page_size = min(100, max(1, int(page_size)))
        clauses = ["local_date = ?"]
        params: list[object] = [target_date]
        if ip_filter.strip():
            clauses.append("ip_address LIKE ?")
            params.append(f"%{_clean_text(ip_filter, 80)}%")
        if path_filter.strip():
            clauses.append("path LIKE ?")
            params.append(f"%{_clean_text(path_filter, 200)}%")
        where = " AND ".join(clauses)

        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM visit_events WHERE {where}", params
            ).fetchone()[0]
            rows = connection.execute(
                f"""
                SELECT id, visited_at, local_date, ip_address, path, page_title, referrer, user_agent
                FROM visit_events
                WHERE {where}
                ORDER BY visited_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, (page - 1) * page_size],
            ).fetchall()
            path_rows = connection.execute(
                """
                SELECT path, COUNT(*) AS views, COUNT(DISTINCT visitor_key) AS visitors
                FROM visit_events
                WHERE local_date = ?
                GROUP BY path
                ORDER BY views DESC, path ASC
                LIMIT 20
                """,
                (target_date,),
            ).fetchall()

        return {
            "date": target_date,
            "items": [dict(row) for row in rows],
            "paths": [dict(row) for row in path_rows],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": int(total),
                "pages": max(1, (int(total) + page_size - 1) // page_size),
            },
        }

    def purge_old_events(self, now: datetime | None = None) -> int:
        self.initialize()
        cutoff = _as_utc(now) - timedelta(days=self.retention_days)
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM visit_events WHERE visited_at < ?",
                (cutoff.isoformat(timespec="microseconds"),),
            )
            return int(cursor.rowcount or 0)

    def status(self) -> dict:
        self.initialize()
        with self._connect() as connection:
            connection.execute("SELECT 1").fetchone()
        return {"ok": True, "path": str(self.db_path), "retention_days": self.retention_days}


def _default_db_path() -> Path:
    configured = env_first("MINSLAB_ANALYTICS_DB")
    return Path(configured).expanduser() if configured else APP_DIR / "data" / "analytics.sqlite3"


DEFAULT_STORE = AnalyticsStore(
    _default_db_path(),
    retention_days=int(env_first("MINSLAB_ANALYTICS_RETENTION_DAYS", default="90")),
)


def record_visit(**kwargs) -> bool:
    return DEFAULT_STORE.record_visit(**kwargs)


def get_analytics_summary(local_date: str | None = None) -> dict:
    return DEFAULT_STORE.get_summary(local_date)

def increment_local_llm_calls(amount: int = 1) -> int:
    return DEFAULT_STORE.increment_metric("local_llm_calls", amount)


def record_system_metrics(
    cpu_percent: float,
    memory_percent: float,
    **details,
) -> None:
    DEFAULT_STORE.record_system_metrics(cpu_percent, memory_percent, **details)


def get_system_metric_history(hours: int = 72) -> dict:
    return DEFAULT_STORE.get_system_metrics(hours)


def record_service_probe(**kwargs) -> None:
    DEFAULT_STORE.record_service_probe(**kwargs)



def list_analytics_visits(**kwargs) -> dict:
    return DEFAULT_STORE.list_visits(**kwargs)


def analytics_status() -> dict:
    return DEFAULT_STORE.status()


def purge_old_analytics_events() -> int:
    return DEFAULT_STORE.purge_old_events()
