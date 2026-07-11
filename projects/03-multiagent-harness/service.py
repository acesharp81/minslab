"""03 계층형 멀티에이전트 하네스의 홈페이지 통합 서비스."""

from __future__ import annotations

import copy
import hmac
import os
import secrets
import sys
import threading
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness_engine import AGENTS, build_demo_run, harness_config  # noqa: E402
from live_executor import LiveExecutionError, LiveHarnessExecutor, new_live_run  # noqa: E402
from model_gateway import ModelGateway, ModelGatewayError, model_options  # noqa: E402
from scheduler import HierarchicalScheduler, incident_response_work_items  # noqa: E402


class HarnessServiceError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


_RUNS: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_RUNS_LOCK = threading.Lock()
_GATEWAY: ModelGateway | None = None
_GATEWAY_LOCK = threading.Lock()
_LIVE_SLOT = threading.BoundedSemaphore(1)
_LIVE_HISTORY: deque[float] = deque()
_LIVE_HISTORY_LOCK = threading.Lock()
_LIVE_AUTH_TOKENS: dict[str, float] = {}
_LIVE_AUTH_FAILURES: deque[float] = deque()
_LIVE_AUTH_LOCK = threading.Lock()
_LIVE_TOKEN_TTL_SECONDS = 600


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
        raise HarnessServiceError("실행 기록을 찾을 수 없습니다.", 404)
    return copy.deepcopy(run)


def _apply_model_assignments(run: dict[str, Any], raw: Any) -> None:
    if not isinstance(raw, dict):
        return
    registry = model_options()
    allowed = {item["value"] for item in registry["models"]}
    assignments = {
        str(agent_id): str(model_ref)
        for agent_id, model_ref in raw.items()
        if str(model_ref) in allowed
    }
    if not assignments:
        return
    by_agent: dict[str, str] = {}
    for agent in run["agents"]:
        if agent["id"] in assignments:
            agent["model"] = assignments[agent["id"]]
        by_agent[agent["id"]] = agent["model"]
    for event in run["events"]:
        data = event.get("data") or {}
        agent_id = data.get("agent_id")
        if agent_id and event.get("type", "").startswith("inference."):
            data["provider"] = by_agent.get(agent_id, "unknown").split(":", 1)[0]
    run["assignments"] = by_agent


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _live_secret() -> str:
    return os.environ.get("MULTI_AGENT_LIVE_ENABLED_key", "").strip() or os.environ.get("MULTI_AGENT_LIVE_ENABLED_KEY", "").strip()


def _live_execution_config(*, authorized: bool = False) -> dict[str, Any]:
    options = model_options()
    has_model = any(item.get("available") for item in options["models"])
    has_secret = bool(_live_secret())
    owner_available = has_secret and has_model
    enabled = owner_available and authorized
    if not has_secret:
        reason = "서버에 MULTI_AGENT_LIVE_ENABLED_key가 설정되지 않았습니다."
    elif not has_model:
        reason = "사용 가능한 LLM 모델이 없습니다."
    elif not authorized:
        reason = "모델 설정에서 실제 LLM 실행 암호 인증이 필요합니다."
    else:
        reason = ""
    try:
        max_runs_per_hour = max(1, min(3, int(os.environ.get("MULTI_AGENT_LIVE_RUNS_PER_HOUR", "1"))))
    except ValueError:
        max_runs_per_hour = 1
    return {
        "enabled": enabled,
        "available": owner_available,
        "owner_available": owner_available,
        "personal_key_available": True,
        "credential_modes": ["owner", "personal"],
        "requires_authorization": True,
        "authorization_ttl_seconds": _LIVE_TOKEN_TTL_SECONDS,
        "endpoint": "/live",
        "authorize_endpoint": "/live/authorize",
        "reason": reason,
        "limits": {
            "max_concurrent_runs": 1,
            "max_model_calls": 8,
            "max_runs_per_hour": max_runs_per_hour,
        },
    }


def _clean_live_auth_state(now: float) -> None:
    while _LIVE_AUTH_FAILURES and now - _LIVE_AUTH_FAILURES[0] > 600:
        _LIVE_AUTH_FAILURES.popleft()
    expired = [token for token, expires_at in _LIVE_AUTH_TOKENS.items() if expires_at <= now]
    for token in expired:
        _LIVE_AUTH_TOKENS.pop(token, None)


def _authorize_live_execution(payload: dict[str, Any]) -> dict[str, Any]:
    secret = _live_secret()
    if not secret:
        raise HarnessServiceError("실제 LLM 실행 암호가 서버에 설정되지 않았습니다.", 503)
    password = str(payload.get("password") or "")
    if not password or len(password) > 256:
        raise HarnessServiceError("실제 LLM 실행 암호를 입력해 주세요.", 400)
    now = time.time()
    with _LIVE_AUTH_LOCK:
        _clean_live_auth_state(now)
        if len(_LIVE_AUTH_FAILURES) >= 5:
            raise HarnessServiceError("암호 인증 시도가 너무 많습니다. 10분 후 다시 시도해 주세요.", 429)
        if not hmac.compare_digest(password.encode("utf-8"), secret.encode("utf-8")):
            _LIVE_AUTH_FAILURES.append(now)
            raise HarnessServiceError("실제 LLM 실행 암호가 올바르지 않습니다.", 401)
        token = secrets.token_urlsafe(32)
        expires_at = now + _LIVE_TOKEN_TTL_SECONDS
        _LIVE_AUTH_TOKENS[token] = expires_at
    return {
        "ok": True,
        "authorization_token": token,
        "expires_in_seconds": _LIVE_TOKEN_TTL_SECONDS,
        "live_execution": _live_execution_config(authorized=True),
    }


def _validate_live_token(raw_token: Any, *, consume: bool) -> None:
    token = str(raw_token or "")
    if not token or len(token) > 128:
        raise HarnessServiceError("실제 LLM 실행 인증이 필요합니다.", 401)
    now = time.time()
    with _LIVE_AUTH_LOCK:
        _clean_live_auth_state(now)
        expires_at = _LIVE_AUTH_TOKENS.get(token)
        if not expires_at or expires_at <= now:
            raise HarnessServiceError("실제 LLM 실행 인증이 만료됐습니다. 다시 인증해 주세요.", 401)
        if consume:
            _LIVE_AUTH_TOKENS.pop(token, None)


def _personal_keys(payload: dict[str, Any]) -> dict[str, str]:
    raw = payload.get("personal_keys")
    if not isinstance(raw, dict):
        raise HarnessServiceError("개인 API Key를 입력해 주세요.", 400)
    keys: dict[str, str] = {}
    labels = {"openrouter": "OpenRouter", "huggingface": "Hugging Face"}
    for provider, label in labels.items():
        value = str(raw.get(provider) or "").strip()
        if not value:
            continue
        if len(value) > 512 or any(char in value for char in "\r\n\x00"):
            raise HarnessServiceError(f"{label} API Key 형식이 올바르지 않습니다.", 400)
        keys[provider] = value
    if not keys:
        raise HarnessServiceError("OpenRouter 또는 Hugging Face 개인 API Key를 입력해 주세요.", 400)
    return keys


def _append_live_event(run_id: str, event: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if run:
            run["events"].append(copy.deepcopy(event))


def _publish_live_artifact(run_id: str, artifact: dict[str, Any]) -> None:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if not run:
            return
        artifacts = run["artifacts"]
        for index, current in enumerate(artifacts):
            if current.get("id") == artifact.get("id"):
                artifacts[index] = copy.deepcopy(artifact)
                break
        else:
            artifacts.append(copy.deepcopy(artifact))


def _set_live_run_state(run_id: str, status: str, **extra: Any) -> None:
    with _RUNS_LOCK:
        run = _RUNS.get(run_id)
        if run:
            run["status"] = status
            run.update(extra)


def _execute_live_run(run_id: str, gateway: ModelGateway | None = None) -> None:
    try:
        run = _get_run(run_id)
        _set_live_run_state(run_id, "running", started_at=datetime.now(timezone.utc).isoformat())
        executor = LiveHarnessExecutor(gateway or _gateway())
        executor.execute(
            run,
            emit_event=lambda event: _append_live_event(run_id, event),
            publish_artifact=lambda artifact: _publish_live_artifact(run_id, artifact),
        )
        _set_live_run_state(run_id, "complete", finished_at=datetime.now(timezone.utc).isoformat())
    except Exception as error:
        snapshot = _get_run(run_id)
        last_ms = max([event.get("at_ms", 0) for event in snapshot.get("events", [])] or [0])
        _append_live_event(
            run_id,
            {
                "seq": len(snapshot.get("events", [])) + 1,
                "at_ms": last_ms + 1,
                "type": "run.failed",
                "data": {"message": str(error)[:500]},
            },
        )
        _set_live_run_state(run_id, "failed", error=str(error)[:500], finished_at=datetime.now(timezone.utc).isoformat())
    finally:
        _LIVE_SLOT.release()


def _start_live_run(payload: dict[str, Any]) -> dict[str, Any]:
    credential_mode = str(payload.get("credential_mode") or "owner").strip().lower()
    if credential_mode not in {"owner", "personal"}:
        raise HarnessServiceError("지원하지 않는 API Key 사용 방식입니다.", 400)
    config = _live_execution_config()
    if credential_mode == "owner":
        if not config["owner_available"]:
            raise HarnessServiceError(config["reason"] or "사이트 오너 API Key가 비활성화됐습니다.", 503)
        _validate_live_token(payload.get("authorization_token"), consume=False)
        gateway = _gateway()
    else:
        keys = _personal_keys(payload)
        gateway = ModelGateway(key_overrides=keys, allow_environment_keys=False)
    if not _LIVE_SLOT.acquire(blocking=False):
        raise HarnessServiceError("다른 실제 LLM 실행이 진행 중입니다.", 409)
    try:
        now = time.time()
        with _LIVE_HISTORY_LOCK:
            while _LIVE_HISTORY and now - _LIVE_HISTORY[0] > 3600:
                _LIVE_HISTORY.popleft()
            if len(_LIVE_HISTORY) >= config["limits"]["max_runs_per_hour"]:
                raise HarnessServiceError("시간당 실제 LLM 실행 한도를 초과했습니다.", 429)
            if credential_mode == "owner":
                _validate_live_token(payload.get("authorization_token"), consume=True)
            _LIVE_HISTORY.append(now)
        run = new_live_run(str(payload.get("prompt") or ""))
        run["credential_mode"] = credential_mode
        _apply_model_assignments(run, payload.get("assignments"))
        _store_run(run)
        threading.Thread(target=_execute_live_run, args=(run["run_id"], gateway), daemon=True, name=f"multiagent-live-{run['run_id'][:8]}").start()
        return _get_run(run["run_id"])
    except Exception:
        _LIVE_SLOT.release()
        raise


def public_health() -> dict[str, Any]:
    options = model_options()
    return {
        "ok": True,
        "service": "multiagent-harness",
        "mode": "deterministic-demo",
        "providers": options["providers"],
        "available_models": len([item for item in options["models"] if item["available"]]),
    }


def public_config() -> dict[str, Any]:
    config = harness_config()
    config["model_registry"] = model_options()
    config["workflow"] = HierarchicalScheduler(AGENTS).plan(
        incident_response_work_items()
    )
    config["live_execution"] = _live_execution_config()
    return config


def dispatch(path: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise HarnessServiceError("JSON 객체 형식이 필요합니다.")
    if path in {"", "/", "/health"} and method == "GET":
        return public_health()
    if path == "/models" and method == "GET":
        return model_options()
    if path == "/config" and method == "GET":
        return public_config()
    if path == "/gateway/status" and method == "GET":
        return {"providers": _gateway().status()}
    if path == "/demo" and method == "POST":
        run = build_demo_run(str(payload.get("prompt") or ""))
        _apply_model_assignments(run, payload.get("assignments"))
        _store_run(run)
        return run
    if path == "/live/authorize" and method == "POST":
        return _authorize_live_execution(payload)
    if path == "/live" and method == "POST":
        return _start_live_run(payload)
    if path.startswith("/runs/") and method == "GET":
        run_id = path.removeprefix("/runs/").split("/", 1)[0]
        return _get_run(run_id)
    raise HarnessServiceError(f"지원하지 않는 하네스 API입니다: {method} {path}", 404)


__all__ = ["HarnessServiceError", "ModelGatewayError", "dispatch", "public_health"]
