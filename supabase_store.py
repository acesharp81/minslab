"""Supabase REST API and local fallback chat history store."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, parse, request

from env_utils import env_first, load_project_env


load_project_env()

APP_DIR = Path(__file__).resolve().parent
LOCAL_HISTORY_PATH = APP_DIR / "data" / "chat_history.json"
_LOCAL_LOCK = threading.Lock()


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


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


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


def _read_local_records() -> list[dict]:
    if not LOCAL_HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(LOCAL_HISTORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else []


def _write_local_records(records: list[dict]) -> None:
    LOCAL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_HISTORY_PATH.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _owner_matches(record: dict, client_id: str, account_id: str | None = None) -> bool:
    if account_id:
        return record.get("account_id") == account_id
    return record.get("client_id") == client_id and not record.get("account_id")


def _local_list_history(client_id: str, account_id: str | None = None) -> list[dict]:
    with _LOCAL_LOCK:
        records = [item for item in _read_local_records() if _owner_matches(item, client_id, account_id)]
    records.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or "", reverse=True)
    return [
        {
            "id": item.get("id"),
            "title": item.get("title") or "새로운 대화",
            "model": item.get("model") or "",
            "messages": item.get("messages") or [],
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "storage": "local",
            "scope_type": item.get("scope_type") or ("account" if item.get("account_id") else "device"),
        }
        for item in records[:50]
    ]


def _local_save_history(record: dict) -> list[dict]:
    now = _now_iso()
    item = {
        "id": record["id"],
        "client_id": record["client_id"],
        "account_id": record.get("account_id") or None,
        "scope_type": record.get("scope_type") or ("account" if record.get("account_id") else "device"),
        "title": record.get("title") or "새로운 대화",
        "model": record.get("model") or "",
        "messages": record.get("messages") or [],
        "updated_at": now,
    }
    with _LOCAL_LOCK:
        records = _read_local_records()
        existing = next((entry for entry in records if entry.get("id") == item["id"]), None)
        if existing:
            created_at = existing.get("created_at") or now
            existing.clear()
            existing.update({**item, "created_at": created_at})
            saved = existing
        else:
            saved = {**item, "created_at": now}
            records.append(saved)
        _write_local_records(records)
    return [saved]


def _remote_list_history(client_id: str) -> list[dict]:
    query = parse.urlencode({
        "client_id": f"eq.{client_id}",
        "select": "id,title,model,messages,created_at,updated_at",
        "order": "updated_at.desc",
        "limit": "50",
    })
    rows = _request("GET", f"chat_history?{query}") or []
    for row in rows:
        row["storage"] = "supabase"
        row["scope_type"] = "device"
    return rows


def _remote_save_history(record: dict):
    payload = {
        "id": record["id"],
        "client_id": record["client_id"],
        "title": record.get("title") or "새로운 대화",
        "model": record.get("model") or "",
        "messages": record.get("messages") or [],
        "updated_at": _now_iso(),
    }
    return _request(
        "POST",
        "chat_history?on_conflict=id",
        [payload],
        prefer="resolution=merge-duplicates,return=representation",
    )


def list_history(client_id: str, account_id: str | None = None) -> tuple[list[dict], str, str | None]:
    if account_id:
        return _local_list_history(client_id, account_id), "local", None
    try:
        return _remote_list_history(client_id), "supabase", None
    except RuntimeError as exc:
        return _local_list_history(client_id), "local", str(exc)


def save_history(record: dict) -> tuple[list[dict], str, str | None]:
    if record.get("account_id"):
        return _local_save_history(record), "local", None
    try:
        return _remote_save_history(record), "supabase", None
    except RuntimeError as exc:
        return _local_save_history(record), "local", str(exc)


def delete_history(history_id, client_id, account_id: str | None = None):
    if account_id:
        with _LOCAL_LOCK:
            records = [item for item in _read_local_records() if not (item.get("id") == history_id and _owner_matches(item, client_id, account_id))]
            _write_local_records(records)
        return
    query = parse.urlencode({"id": f"eq.{history_id}", "client_id": f"eq.{client_id}"})
    _request("DELETE", f"chat_history?{query}", prefer="return=minimal")
