"""Small in-process HTTP window used by the operations dashboard."""

from __future__ import annotations

import math
import threading


_lock = threading.Lock()
_durations_ms: list[float] = []
_request_count = 0
_error_count = 0

_EXCLUDED_PATHS = {
    "/admin",
    "/api/admin/analytics",
    "/api/admin/session",
    "/api/health",
    "/health",
}


def observe_http_request(path: str, status: int, duration_ms: float) -> None:
    if path in _EXCLUDED_PATHS or path.startswith("/static/"):
        return
    global _request_count, _error_count
    with _lock:
        _request_count += 1
        if int(status) >= 500:
            _error_count += 1
        _durations_ms.append(max(0.0, float(duration_ms)))


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * percentile) - 1)
    return round(ordered[index], 2)


def drain_http_window() -> dict:
    global _request_count, _error_count, _durations_ms
    with _lock:
        requests = _request_count
        errors = _error_count
        durations = _durations_ms
        _request_count = 0
        _error_count = 0
        _durations_ms = []
    return {
        "http_requests": requests,
        "http_errors": errors,
        "http_p95_ms": _percentile(durations, 0.95),
        "http_max_ms": round(max(durations), 2) if durations else None,
    }
