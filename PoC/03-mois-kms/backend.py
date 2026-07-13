"""MoIS KMS PoC backend: Supabase admin boundary and multi-provider LLM calls."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request


LOGIN_ID_RE = re.compile(r"^[a-z0-9]{3,32}$")
POSITIONS = {"과장", "팀장", "팀원", "서무"}
BASE_PATH = "/api/poc/mois-kms"
DEFAULT_HF_MODELS = "Qwen/Qwen2.5-72B-Instruct"
DEFAULT_OPENROUTER_MODELS = "openai/gpt-4o-mini,google/gemini-2.5-flash"


class MoisKMSError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _env(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value and value.strip():
            return value.strip()
    return default


def _supabase_url() -> str:
    value = _env("VITE_MOIS_KMS_SUPABASE_URL", "MOIS_KMS_SUPABASE_URL", "SUPABASE2_URL").rstrip("/")
    if not value:
        raise MoisKMSError("MoIS KMS Supabase URL이 설정되지 않았습니다.", 503)
    return value


def _publishable_key() -> str:
    value = _env("VITE_MOIS_KMS_SUPABASE_PUBLISHABLE_KEY", "MOIS_KMS_SUPABASE_PUBLISHABLE_KEY", "SUPABASE2_PUBLISHABLE_KEY")
    if not value:
        raise MoisKMSError("MoIS KMS Supabase publishable key가 설정되지 않았습니다.", 503)
    return value


def _service_role_key() -> str:
    value = _env("MOIS_KMS_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE2_SERVICE_ROLE_KEY")
    if not value:
        raise MoisKMSError(
            "신규 회원가입과 Auth 사용자 삭제를 사용하려면 공용 .env에 SUPABASE2_SERVICE_ROLE_KEY가 필요합니다.",
            503,
        )
    return value


def _read_http_error(exc: url_error.HTTPError) -> str:
    try:
        raw = exc.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        return str(data.get("msg") or data.get("message") or data.get("error_description") or data.get("error") or raw[:300])
    except Exception:
        return str(exc.reason or exc)


def _request_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    payload: Any = None,
    timeout: int = 30,
) -> Any:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    req = url_request.Request(url, data=body, headers=request_headers, method=method)
    try:
        with url_request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except url_error.HTTPError as exc:
        raise MoisKMSError(_read_http_error(exc), exc.code) from exc
    except TimeoutError as exc:
        raise MoisKMSError("외부 서비스 응답 시간이 초과되었습니다.", 504) from exc
    except url_error.URLError as exc:
        raise MoisKMSError(f"외부 서비스 연결 실패: {exc.reason}", 503) from exc


def _service_headers(prefer: str | None = None) -> dict[str, str]:
    key = _service_role_key()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _user_headers(token: str) -> dict[str, str]:
    return {"apikey": _publishable_key(), "Authorization": f"Bearer {token}"}


def _rest_path(table: str, query: dict[str, str] | None = None) -> str:
    suffix = f"?{url_parse.urlencode(query)}" if query else ""
    return f"{_supabase_url()}/rest/v1/{table}{suffix}"


def _service_select(table: str, query: dict[str, str]) -> list[dict[str, Any]]:
    result = _request_json("GET", _rest_path(table, query), headers=_service_headers())
    return result if isinstance(result, list) else []


def _service_insert(table: str, payload: dict[str, Any]) -> None:
    _request_json("POST", _rest_path(table), headers=_service_headers("return=minimal"), payload=payload)


def _service_delete(table: str, query: dict[str, str]) -> None:
    _request_json("DELETE", _rest_path(table, query), headers=_service_headers("return=minimal"))


def _login_id(payload: dict[str, Any]) -> str:
    value = str(payload.get("login_id") or "").strip()
    if not LOGIN_ID_RE.fullmatch(value):
        raise MoisKMSError("ID는 영문 소문자와 숫자 3~32자로 입력하세요.")
    return value


def _synthetic_email(login_id: str) -> str:
    return f"{login_id}@app.local"


def signup_meta() -> dict[str, Any]:
    if not _env("MOIS_KMS_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE2_SERVICE_ROLE_KEY"):
        return {"divisions": [], "teams": [], "signup_enabled": False}
    divisions = _service_select("divisions", {"select": "id,name", "order": "name.asc"})
    teams = _service_select("teams", {"select": "id,name,division_id", "order": "name.asc"})
    return {"divisions": divisions, "teams": teams, "signup_enabled": True}


def check_login_id(payload: dict[str, Any]) -> dict[str, Any]:
    login_id = _login_id(payload)
    rows = _service_select("profiles", {"select": "id", "login_id": f"eq.{login_id}", "limit": "1"})
    return {"available": not rows, "reason": "ok" if not rows else "taken"}


def resolve_login(payload: dict[str, Any]) -> dict[str, Any]:
    login_id = _login_id(payload)
    service_key = _env("MOIS_KMS_SUPABASE_SERVICE_ROLE_KEY", "SUPABASE2_SERVICE_ROLE_KEY")
    if not service_key:
        return {"email": _synthetic_email(login_id), "status": "승인", "status_verified": False}
    rows = _service_select("profiles", {"select": "login_id,status", "login_id": f"eq.{login_id}", "limit": "1"})
    if not rows:
        raise MoisKMSError("존재하지 않는 ID입니다.", 404)
    return {"email": _synthetic_email(login_id), "status": rows[0].get("status", "가입신청"), "status_verified": True}


def signup(payload: dict[str, Any]) -> dict[str, Any]:
    login_id = _login_id(payload)
    password = str(payload.get("password") or "")
    name = str(payload.get("name") or "").strip()
    position = str(payload.get("position") or "")
    division_id = payload.get("division_id") or None
    team_id = payload.get("team_id") or None
    if not 6 <= len(password) <= 72:
        raise MoisKMSError("비밀번호는 6~72자로 입력하세요.")
    if not name or len(name) > 50:
        raise MoisKMSError("이름은 1~50자로 입력하세요.")
    if position not in POSITIONS:
        raise MoisKMSError("직급이 올바르지 않습니다.")
    if check_login_id({"login_id": login_id})["available"] is False:
        raise MoisKMSError("이미 사용 중인 ID입니다.", 409)

    key = _service_role_key()
    auth_headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    created = _request_json(
        "POST",
        f"{_supabase_url()}/auth/v1/admin/users",
        headers=auth_headers,
        payload={"email": _synthetic_email(login_id), "password": password, "email_confirm": True},
    )
    user_id = created.get("id") or (created.get("user") or {}).get("id")
    if not user_id:
        raise MoisKMSError("Supabase Auth 사용자를 생성하지 못했습니다.", 502)
    try:
        _service_insert("profiles", {
            "id": user_id,
            "login_id": login_id,
            "name": name,
            "position": position,
            "division_id": division_id,
            "team_id": None if position == "과장" else team_id,
            "status": "가입신청",
        })
    except Exception:
        try:
            _request_json("DELETE", f"{_supabase_url()}/auth/v1/admin/users/{user_id}", headers=auth_headers)
        except Exception:
            pass
        raise
    return {"ok": True}


def _verify_user(token: str, *, approved: bool = True) -> dict[str, Any]:
    if not token:
        raise MoisKMSError("로그인이 필요합니다.", 401)
    user = _request_json("GET", f"{_supabase_url()}/auth/v1/user", headers=_user_headers(token))
    user_id = user.get("id")
    if not user_id:
        raise MoisKMSError("유효하지 않은 로그인 세션입니다.", 401)
    rows = _request_json(
        "GET",
        _rest_path("profiles", {"select": "id,status", "id": f"eq.{user_id}", "limit": "1"}),
        headers=_user_headers(token),
    )
    profile = rows[0] if isinstance(rows, list) and rows else None
    if not profile:
        raise MoisKMSError("사용자 프로필을 찾을 수 없습니다.", 403)
    if approved and profile.get("status") != "승인":
        raise MoisKMSError("관리자 승인이 완료된 사용자만 이용할 수 있습니다.", 403)
    return {"id": user_id, "email": user.get("email"), "profile": profile}


def _verify_admin(token: str) -> dict[str, Any]:
    user = _verify_user(token)
    rows = _request_json(
        "GET",
        _rest_path("user_roles", {"select": "role", "user_id": f"eq.{user['id']}", "role": "eq.admin", "limit": "1"}),
        headers=_user_headers(token),
    )
    if not isinstance(rows, list) or not rows:
        raise MoisKMSError("관리자 권한이 필요합니다.", 403)
    return user


def delete_user(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    caller = _verify_admin(token)
    user_id = str(payload.get("user_id") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", user_id):
        raise MoisKMSError("사용자 ID가 올바르지 않습니다.")
    if user_id == caller["id"]:
        raise MoisKMSError("현재 로그인한 관리자 계정은 삭제할 수 없습니다.")
    key = _service_role_key()
    _service_delete("profiles", {"id": f"eq.{user_id}"})
    _request_json(
        "DELETE",
        f"{_supabase_url()}/auth/v1/admin/users/{user_id}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"},
    )
    return {"ok": True}


def _split_models(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _is_chat_model(model: dict[str, Any]) -> bool:
    name = str(model.get("name") or "").lower()
    details = model.get("details") if isinstance(model.get("details"), dict) else {}
    family = str(details.get("family") or "").lower()
    return bool(name) and "embed" not in name and "embedding" not in name and "bert" not in family


def _ollama_models() -> list[dict[str, Any]]:
    base = _env("OLLAMA_BASE_URL", default="http://127.0.0.1:11434").rstrip("/")
    try:
        result = _request_json("GET", f"{base}/api/tags", timeout=4)
    except MoisKMSError:
        return []
    return [
        {
            "value": f"ollama:{model['name']}",
            "label": f"Local LLM · {model['name']}",
            "provider": "ollama",
            "available": True,
            "details": model.get("details") or {},
        }
        for model in result.get("models", [])
        if _is_chat_model(model)
    ]


def public_config() -> dict[str, str]:
    """Return browser-safe connection values for the shared MinsLab Supabase project."""
    return {
        "supabase_url": _supabase_url(),
        "supabase_publishable_key": _publishable_key(),
    }


def model_options() -> dict[str, Any]:
    hf_key = _env("HF_API_KEY")
    openrouter_key = _env("OPENROUTER_API_KEY")
    local = _ollama_models()
    hf = [
        {"value": f"huggingface:{name}", "label": f"Hugging Face · {name}", "provider": "huggingface", "available": bool(hf_key), "details": {}}
        for name in _split_models(_env("MOIS_KMS_HF_MODELS", default=DEFAULT_HF_MODELS))
    ]
    openrouter = [
        {"value": f"openrouter:{name}", "label": f"OpenRouter · {name}", "provider": "openrouter", "available": bool(openrouter_key), "details": {}}
        for name in _split_models(_env("MOIS_KMS_OPENROUTER_MODELS", default=DEFAULT_OPENROUTER_MODELS))
    ]
    models = local + hf + openrouter
    available = [model for model in models if model["available"]]
    preferred = _env("MOIS_KMS_DEFAULT_MODEL")
    values = {model["value"] for model in available}
    default = preferred if preferred in values else (available[0]["value"] if available else "")
    return {
        "models": models,
        "default": default,
        "settings": {"temperature": 0.2, "max_tokens": 1200},
        "providers": {
            "ollama": {"configured": bool(local), "label": "Local LLM"},
            "huggingface": {"configured": bool(hf_key), "label": "Hugging Face"},
            "openrouter": {"configured": bool(openrouter_key), "label": "OpenRouter"},
        },
    }


def _clamp_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        return max(minimum, min(maximum, float(value)))
    except (TypeError, ValueError):
        return default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(value)))
    except (TypeError, ValueError):
        return default


def _extract_chat_content(result: dict[str, Any]) -> str:
    choices = result.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or message.get("reasoning_content") or "").strip()


def _remote_completion(base_url: str, key: str, model: str, messages: list[dict[str, str]], temperature: float, max_tokens: int, title: str) -> str:
    result = _request_json(
        "POST",
        f"{base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "X-Title": title},
        payload={"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=120,
    )
    content = _extract_chat_content(result)
    if not content:
        raise MoisKMSError("AI 응답 내용이 비어 있습니다.", 502)
    return content


def _ollama_completion(model: str, messages: list[dict[str, str]], temperature: float, max_tokens: int) -> str:
    base = _env("OLLAMA_BASE_URL", default="http://127.0.0.1:11434").rstrip("/")
    result = _request_json(
        "POST",
        f"{base}/api/chat",
        payload={
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": "5m",
            "options": {"temperature": temperature, "num_predict": max_tokens, "top_p": 0.9, "repeat_penalty": 1.1, "num_ctx": 8192},
        },
        timeout=180,
    )
    content = str((result.get("message") or {}).get("content") or "").strip()
    if not content:
        raise MoisKMSError("로컬 LLM 응답 내용이 비어 있습니다.", 502)
    return content


def generate_report(token: str, payload: dict[str, Any]) -> dict[str, Any]:
    _verify_user(token)
    model_choice = str(payload.get("model") or "").strip()
    system = str(payload.get("system") or "").strip()
    prompt = str(payload.get("prompt") or "").strip()
    if not model_choice or ":" not in model_choice:
        raise MoisKMSError("사용할 AI 모델을 선택하세요.")
    if not system or len(system) > 8000:
        raise MoisKMSError("시스템 프롬프트는 1~8,000자로 입력하세요.")
    if not prompt or len(prompt) > 60000:
        raise MoisKMSError("보고서 입력 내용은 1~60,000자로 입력하세요.")
    provider, model = model_choice.split(":", 1)
    advertised = {item["value"]: item for item in model_options()["models"]}
    if model_choice not in advertised:
        raise MoisKMSError("허용되지 않은 모델입니다.")
    if not advertised[model_choice]["available"]:
        raise MoisKMSError("선택한 모델 제공자의 서버 키가 설정되지 않았습니다.", 503)
    temperature = _clamp_float(payload.get("temperature"), 0.2, 0.0, 1.5)
    max_tokens = _clamp_int(payload.get("max_tokens"), 1200, 128, 4096)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
    started = time.perf_counter()
    if provider == "ollama":
        report = _ollama_completion(model, messages, temperature, max_tokens)
    elif provider == "huggingface":
        report = _remote_completion(
            _env("HF_BASE_URL", default="https://router.huggingface.co/v1"),
            _env("HF_API_KEY"), model, messages, temperature, max_tokens, "MinsLab MoIS KMS",
        )
    elif provider == "openrouter":
        report = _remote_completion(
            _env("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1"),
            _env("OPENROUTER_API_KEY"), model, messages, temperature, max_tokens, "MinsLab MoIS KMS",
        )
    else:
        raise MoisKMSError("지원하지 않는 모델 제공자입니다.")
    return {
        "report": report,
        "model": model,
        "provider": provider,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def dispatch(path: str, method: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dispatch a validated PoC API request from the host ASGI service."""
    payload = payload or {}
    routes = {
        ("/public-config", "GET"): lambda: public_config(),
        ("/models", "GET"): lambda: model_options(),
        ("/auth/signup-meta", "GET"): lambda: signup_meta(),
        ("/auth/check-login-id", "POST"): lambda: check_login_id(payload),
        ("/auth/resolve-login", "POST"): lambda: resolve_login(payload),
        ("/auth/signup", "POST"): lambda: signup(payload),
        ("/admin/delete-user", "POST"): lambda: delete_user(token, payload),
        ("/report", "POST"): lambda: generate_report(token, payload),
    }
    handler = routes.get((path, method))
    if handler is None:
        raise MoisKMSError("지원하지 않는 API 경로입니다.", 404)
    return handler()
