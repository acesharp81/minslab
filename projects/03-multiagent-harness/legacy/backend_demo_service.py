"""초기 demo-only API 경계 보관본. 현재 홈페이지 실행 경계는 ../service.py이다."""

from __future__ import annotations

import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from harness_engine import build_demo_run, harness_config  # noqa: E402
from model_gateway import ModelGateway, ModelGatewayError, model_options  # noqa: E402


class HarnessAPIError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_RUNS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_RUNS_LOCK = threading.Lock()
_GATEWAY: ModelGateway | None = None
_GATEWAY_LOCK = threading.Lock()


def _gateway() -> ModelGateway:
    global _GATEWAY
    with _GATEWAY_LOCK:
        if _GATEWAY is None:
            _GATEWAY = ModelGateway()
        return _GATEWAY


def _store_run(run: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        _RUNS[run["run_id"]] = run
        while len(_RUNS) > 12:
            _RUNS.popitem(last=False)


def _get_run(run_id: str) -> dict[str, Any]:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
    if not run:
        raise HarnessAPIError("실행 기록을 찾을 수 없습니다.", 404)
    return run


def public_health() -> dict[str, Any]:
    options = model_options()
    return {
        "ok": True,
        "service": "multiagent-harness",
        "mode": "deterministic-demo",
        "providers": options["providers"],
        "available_models": len([item for item in options["models"] if item["available"]]),
    }


def dispatch(path: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise HarnessAPIError("JSON 객체 형식이 필요합니다.")

    if path in {"", "/", "/health"} and method == "GET":
        return public_health()
    if path == "/models" and method == "GET":
        return model_options()
    if path == "/config" and method == "GET":
        config = harness_config()
        config["model_registry"] = model_options()
        return config
    if path == "/gateway/status" and method == "GET":
        return {"providers": _gateway().status()}
    if path == "/demo" and method == "POST":
        run = build_demo_run(str(payload.get("prompt") or ""))
        _store_run(run)
        return run
    if path.startswith("/runs/") and method == "GET":
        run_id = path.removeprefix("/runs/").split("/", 1)[0]
        return _get_run(run_id)
    raise HarnessAPIError(f"지원하지 않는 하네스 API입니다: {method} {path}", 404)


__all__ = [
    "HarnessAPIError",
    "ModelGatewayError",
    "dispatch",
    "public_health",
]
