"""MinsLab 공용 모델 규칙을 따르는 멀티 provider 실행 브로커."""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable
from urllib import error as url_error
from urllib import request as url_request

from project_env import load_project_env


load_project_env()

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_HF_BASE_URL = "https://router.huggingface.co/v1"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class ModelGatewayError(RuntimeError):
    def __init__(self, message: str, status: int = 502, retryable: bool = False):
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _bounded_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _bounded_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout: float = 60,
) -> tuple[dict[str, Any], dict[str, str]]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        request_headers["Content-Type"] = "application/json"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = url_request.Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )
    try:
        with url_request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
    except url_error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:500]
        retryable = error.code in {408, 429, 500, 502, 503, 504}
        exc = ModelGatewayError(
            f"모델 API HTTP {error.code}: {detail or error.reason}",
            status=error.code,
            retryable=retryable,
        )
        setattr(exc, "retry_after", error.headers.get("Retry-After", ""))
        raise exc from error
    except (url_error.URLError, TimeoutError, OSError) as error:
        raise ModelGatewayError(f"모델 API 연결 실패: {error}", retryable=True) from error

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ModelGatewayError(f"모델 API JSON 응답을 해석하지 못했습니다: {raw[:300]}") from error
    if not isinstance(parsed, dict):
        raise ModelGatewayError("모델 API가 JSON 객체를 반환하지 않았습니다.")
    return parsed, response_headers


def _is_chat_model(model: dict[str, Any]) -> bool:
    name = str(model.get("name") or "").lower()
    details = model.get("details") if isinstance(model.get("details"), dict) else {}
    family = str(details.get("family") or "").lower()
    families = [str(item).lower() for item in details.get("families", []) if item]
    return bool(name) and "embed" not in name and "embedding" not in name and "bert" not in family and not any("bert" in item for item in families)


def _ollama_models() -> list[dict[str, Any]]:
    base_url = _env("OLLAMA_BASE_URL", default=DEFAULT_OLLAMA_BASE_URL).rstrip("/")
    try:
        result, _ = _request_json("GET", f"{base_url}/api/tags", timeout=3)
    except ModelGatewayError:
        return []
    return [
        {
            "value": f"ollama:{model['name']}",
            "label": f"Local LLM · {model['name']}",
            "provider": "ollama",
            "name": model["name"],
            "available": True,
            "details": model.get("details") or {},
        }
        for model in result.get("models", [])
        if isinstance(model, dict) and _is_chat_model(model)
    ]


def model_options(
    key_overrides: dict[str, str] | None = None,
    *,
    allow_environment_keys: bool = True,
) -> dict[str, Any]:
    overrides = key_overrides or {}
    local = _ollama_models()
    hf_key = str(overrides.get("huggingface") or "")
    openrouter_key = str(overrides.get("openrouter") or "")
    if allow_environment_keys:
        hf_key = hf_key or _env("HF_API_KEY", "HF_TOKEN")
        openrouter_key = openrouter_key or _env("OPENROUTER_API_KEY")
    hf_names = _split_models(
        _env(
            "MULTI_AGENT_HF_MODELS",
            default="Qwen/Qwen2.5-72B-Instruct",
        )
    )
    openrouter_names = _split_models(
        _env(
            "MULTI_AGENT_OPENROUTER_MODELS",
            default="openai/gpt-4o-mini,google/gemini-2.5-flash",
        )
    )
    hf = [
        {
            "value": f"huggingface:{name}",
            "label": f"Hugging Face · {name}",
            "provider": "huggingface",
            "name": name,
            "available": bool(hf_key),
            "details": {},
        }
        for name in hf_names
    ]
    openrouter = [
        {
            "value": f"openrouter:{name}",
            "label": f"OpenRouter · {name}",
            "provider": "openrouter",
            "name": name,
            "available": bool(openrouter_key),
            "details": {},
        }
        for name in openrouter_names
    ]
    models = local + hf + openrouter
    available = [model for model in models if model["available"]]
    preferred = _env("MULTI_AGENT_DEFAULT_MODEL", default="ollama:qwen2.5:1.5b")
    values = {model["value"] for model in available}
    default = preferred if preferred in values else (available[0]["value"] if available else "")
    slots = {
        "ollama": _bounded_int(_env("MULTI_AGENT_OLLAMA_CONCURRENCY", default="1"), 1, 1, 2),
        "huggingface": _bounded_int(_env("MULTI_AGENT_HF_CONCURRENCY", default="1"), 1, 1, 4),
        "openrouter": _bounded_int(_env("MULTI_AGENT_OPENROUTER_CONCURRENCY", default="2"), 2, 1, 8),
    }
    return {
        "models": models,
        "default": default,
        "settings": {
            "temperature": 0.2,
            "max_tokens": 800,
            "timeout_seconds": 120,
        },
        "providers": {
            "ollama": {"configured": bool(local), "label": "Local LLM", "max_in_flight": slots["ollama"]},
            "huggingface": {"configured": bool(hf_key), "label": "Hugging Face", "max_in_flight": slots["huggingface"]},
            "openrouter": {"configured": bool(openrouter_key), "label": "OpenRouter", "max_in_flight": slots["openrouter"]},
        },
    }


@dataclass
class ProviderState:
    provider: str
    max_in_flight: int
    active: int = 0
    queued: int = 0
    completed: int = 0
    failed: int = 0


class ProviderLane:
    def __init__(self, provider: str, max_in_flight: int) -> None:
        self.state = ProviderState(provider, max_in_flight)
        self._semaphore = threading.BoundedSemaphore(max_in_flight)
        self._lock = threading.Lock()

    def execute(self, callback: Callable[[], str]) -> str:
        with self._lock:
            self.state.queued += 1
        acquired = self._semaphore.acquire(timeout=300)
        if not acquired:
            with self._lock:
                self.state.queued -= 1
                self.state.failed += 1
            raise ModelGatewayError(f"{self.state.provider} 실행 슬롯 대기 시간이 초과됐습니다.", status=503)
        with self._lock:
            self.state.queued -= 1
            self.state.active += 1
        try:
            result = callback()
            with self._lock:
                self.state.completed += 1
            return result
        except Exception:
            with self._lock:
                self.state.failed += 1
            raise
        finally:
            with self._lock:
                self.state.active -= 1
            self._semaphore.release()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "provider": self.state.provider,
                "max_in_flight": self.state.max_in_flight,
                "active": self.state.active,
                "queued": self.state.queued,
                "completed": self.state.completed,
                "failed": self.state.failed,
            }


class ModelGateway:
    def __init__(
        self,
        key_overrides: dict[str, str] | None = None,
        *,
        allow_environment_keys: bool = True,
    ) -> None:
        overrides = key_overrides or {}
        self._keys = {
            provider: str(overrides.get(provider) or "").strip()
            for provider in ("huggingface", "openrouter")
        }
        self._allow_environment_keys = allow_environment_keys
        options = model_options(
            self._keys,
            allow_environment_keys=allow_environment_keys,
        )
        self.options = options
        self.allowed = {item["value"]: item for item in options["models"]}
        self.lanes = {
            provider: ProviderLane(provider, int(info["max_in_flight"]))
            for provider, info in options["providers"].items()
        }

    def status(self) -> dict[str, Any]:
        return {provider: lane.snapshot() for provider, lane in self.lanes.items()}

    def complete(
        self,
        model_ref: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 800,
        timeout: int = 120,
        max_retries: int = 2,
    ) -> str:
        selected = self.allowed.get(model_ref)
        if not selected:
            raise ModelGatewayError("허용되지 않은 모델입니다.", status=400)
        if not selected["available"]:
            raise ModelGatewayError("선택한 모델 provider가 설정되지 않았습니다.", status=503)
        provider, model = model_ref.split(":", 1)
        clean_messages = []
        for item in messages:
            role = str(item.get("role") or "user")
            content = str(item.get("content") or "").strip()
            if content:
                clean_messages.append({"role": role, "content": content})
        if not clean_messages:
            raise ModelGatewayError("모델에 전달할 메시지가 없습니다.", status=400)

        settings = {
            "temperature": _bounded_float(temperature, 0.2, 0.0, 1.5),
            "max_tokens": _bounded_int(max_tokens, 800, 16, 4096),
            "timeout": _bounded_int(timeout, 120, 5, 300),
        }

        def invoke() -> str:
            return self._complete_with_retry(
                provider,
                model,
                clean_messages,
                settings,
                max_retries=_bounded_int(max_retries, 2, 0, 3),
            )

        return self.lanes[provider].execute(invoke)

    def _complete_with_retry(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        settings: dict[str, Any],
        *,
        max_retries: int,
    ) -> str:
        attempt = 0
        while True:
            try:
                return self._complete_once(provider, model, messages, settings)
            except ModelGatewayError as error:
                if not error.retryable or attempt >= max_retries:
                    raise
                retry_after = getattr(error, "retry_after", "")
                try:
                    delay = max(0.2, min(10.0, float(retry_after)))
                except (TypeError, ValueError):
                    delay = min(5.0, 0.6 * (2**attempt))
                time.sleep(delay + (0.1 * attempt))
                attempt += 1

    def _complete_once(
        self,
        provider: str,
        model: str,
        messages: list[dict[str, str]],
        settings: dict[str, Any],
    ) -> str:
        if provider == "ollama":
            try:
                from analytics_store import increment_local_llm_calls
                increment_local_llm_calls()
            except Exception:
                pass
            base = _env("OLLAMA_BASE_URL", default=DEFAULT_OLLAMA_BASE_URL).rstrip("/")
            result, _ = _request_json(
                "POST",
                f"{base}/api/chat",
                payload={
                    "model": model,
                    "messages": messages,
                    "stream": False,
                    "keep_alive": "5m",
                    "options": {
                        "temperature": settings["temperature"],
                        "num_predict": settings["max_tokens"],
                        "num_ctx": 4096,
                    },
                },
                timeout=settings["timeout"],
            )
            content = str((result.get("message") or {}).get("content") or "").strip()
        else:
            if provider == "huggingface":
                base = _env("HF_BASE_URL", default=DEFAULT_HF_BASE_URL)
                key = self._keys.get("huggingface") or (
                    _env("HF_API_KEY", "HF_TOKEN") if self._allow_environment_keys else ""
                )
                title = "MinsLab Multi-Agent Harness"
            elif provider == "openrouter":
                base = _env("OPENROUTER_BASE_URL", default=DEFAULT_OPENROUTER_BASE_URL)
                key = self._keys.get("openrouter") or (
                    _env("OPENROUTER_API_KEY") if self._allow_environment_keys else ""
                )
                title = "MinsLab Multi-Agent Harness"
            else:
                raise ModelGatewayError(f"지원하지 않는 provider입니다: {provider}", status=400)
            result, _ = _request_json(
                "POST",
                f"{base.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "X-Title": title},
                payload={
                    "model": model,
                    "messages": messages,
                    "temperature": settings["temperature"],
                    "max_tokens": settings["max_tokens"],
                },
                timeout=settings["timeout"],
            )
            choices = result.get("choices") or []
            message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
            content = str((message or {}).get("content") or (message or {}).get("reasoning_content") or "").strip()
        if not content:
            raise ModelGatewayError("모델이 빈 응답을 반환했습니다.")
        return content
