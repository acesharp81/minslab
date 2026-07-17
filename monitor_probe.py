"""Out-of-process availability probe for the MinsLab web service."""

from __future__ import annotations

import json
import subprocess
import time
from urllib import error as url_error
from urllib import request as url_request

from analytics_store import record_service_probe
from env_utils import env_first, load_project_env


def probe_endpoint(url: str, timeout: float = 10.0) -> dict:
    started = time.perf_counter()
    status_code = None
    try:
        request = url_request.Request(
            url,
            headers={"User-Agent": "MinsLab-External-Monitor/1.0"},
        )
        with url_request.urlopen(request, timeout=timeout) as response:
            status_code = int(response.status)
            payload = json.loads(response.read(4096).decode("utf-8"))
        ok = status_code == 200 and payload.get("status") == "healthy"
        error = "" if ok else "헬스 응답 내용이 정상 상태가 아닙니다."
    except (
        OSError,
        TimeoutError,
        ValueError,
        json.JSONDecodeError,
        url_error.URLError,
    ) as exc:
        ok = False
        error = str(exc)
    return {
        "probe_ok": ok,
        "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
        "status_code": status_code,
        "error": error,
    }


def read_service_state(unit: str = "myservice") -> dict:
    try:
        result = subprocess.run(
            [
                "systemctl",
                "show",
                unit,
                "--property=ActiveState",
                "--property=NRestarts",
                "--property=ExecMainStatus",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        values = dict(
            line.split("=", 1)
            for line in result.stdout.splitlines()
            if "=" in line
        )
        return {
            "service_active": values.get("ActiveState") == "active",
            "restart_count": int(values.get("NRestarts", 0)),
            "exit_status": int(values.get("ExecMainStatus", 0)),
        }
    except (OSError, ValueError, subprocess.SubprocessError):
        return {
            "service_active": None,
            "restart_count": None,
            "exit_status": None,
        }


def main() -> int:
    load_project_env()
    url = env_first("MINSLAB_MONITOR_URL", default="https://www.minslab.kr/health")
    result = probe_endpoint(url)
    result.update(read_service_state())
    record_service_probe(**result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
