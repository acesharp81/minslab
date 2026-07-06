"""Supabase REST API를 이용한 대화 이력 저장소."""

import json
from datetime import datetime, timezone
from urllib import error, parse, request

from env_utils import env_first, load_project_env


load_project_env()


def is_configured():
    return bool(_base_url() and _api_key())


def _base_url():
    return env_first("SUPABASE2_URL", "SUPABASE_URL")


def _api_key():
    return env_first(
        "SUPABASE2_SERVICE_ROLE_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_ANON_KEY",
    )


def _request(method, path, payload=None, prefer=None):
    if not is_configured():
        raise RuntimeError("Supabase 환경변수가 설정되지 않았습니다.")
    headers = {
        "apikey": _api_key(),
        "Authorization": f"Bearer {_api_key()}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    base_url = _base_url().rstrip("/")
    rest_url = base_url if base_url.endswith("/rest/v1") else f"{base_url}/rest/v1"
    req = request.Request(
        f"{rest_url}/{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(req, timeout=10) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else None
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase {exc.code}: {detail}") from exc


def list_history(client_id):
    query = parse.urlencode({
        "client_id": f"eq.{client_id}",
        "select": "id,title,model,messages,created_at,updated_at",
        "order": "updated_at.desc",
        "limit": "50",
    })
    return _request("GET", f"chat_history?{query}") or []


def save_history(record):
    record = {**record, "updated_at": datetime.now(timezone.utc).isoformat()}
    return _request(
        "POST",
        "chat_history?on_conflict=id",
        [record],
        prefer="resolution=merge-duplicates,return=representation",
    )


def delete_history(history_id, client_id):
    query = parse.urlencode({"id": f"eq.{history_id}", "client_id": f"eq.{client_id}"})
    _request("DELETE", f"chat_history?{query}", prefer="return=minimal")
