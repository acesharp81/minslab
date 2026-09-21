from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from pathlib import Path

from ..config import get_settings


def _path() -> Path:
    return get_settings().data_dir / "runtime_settings.json"


def _defaults() -> dict:
    return {
        "admin": {"password_hash": "", "session_secret": secrets.token_urlsafe(32)},
        "notifications": {
            "enabled": False,
            "recipients": [],
            "smtp_host": "smtp.gmail.com",
            "smtp_port": 587,
            "smtp_username": "",
            "smtp_password": "",
            "from_email": "",
            "use_tls": True,
        },
    }


def load_runtime_settings() -> dict:
    path = _path()
    data = _defaults()
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            for section in ("admin", "notifications"):
                if isinstance(loaded.get(section), dict):
                    data[section].update(loaded[section])
        except (OSError, json.JSONDecodeError):
            pass
    if not data["notifications"].get("smtp_host"):
        data["notifications"]["smtp_host"] = "smtp.gmail.com"
    if not path.is_file() or not data["admin"].get("session_secret"):
        save_runtime_settings(data)
    return data


def save_runtime_settings(data: dict) -> dict:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="runtime-settings-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.chmod(temp_name, 0o600)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return data


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 210_000)
    return f"{base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(derived).decode()}"


def verify_admin_password(username: str, password: str) -> bool:
    settings = get_settings()
    expected_user = settings.admin_username or "admin"
    if not hmac.compare_digest(username, expected_user):
        return False
    stored = load_runtime_settings()["admin"].get("password_hash", "")
    if not stored:
        return bool(settings.admin_password) and hmac.compare_digest(password, settings.admin_password)
    try:
        salt_text, digest_text = stored.split("$", 1)
        actual = _password_hash(password, base64.urlsafe_b64decode(salt_text.encode())).split("$", 1)[1]
        return hmac.compare_digest(actual, digest_text)
    except (ValueError, TypeError):
        return False


def change_admin_password(password: str) -> None:
    data = load_runtime_settings()
    data["admin"]["password_hash"] = _password_hash(password)
    save_runtime_settings(data)


def create_admin_session(username: str) -> str:
    data = load_runtime_settings()
    payload = f"{username}:{int(time.time())}"
    encoded = base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")
    signature = hmac.new(data["admin"]["session_secret"].encode(), encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def verify_admin_session(token: str, max_age_seconds: int = 12 * 60 * 60) -> bool:
    if not token or "." not in token:
        return False
    encoded, signature = token.rsplit(".", 1)
    data = load_runtime_settings()
    expected = hmac.new(data["admin"]["session_secret"].encode(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        username, timestamp = base64.urlsafe_b64decode(padded.encode()).decode().rsplit(":", 1)
        return username == (get_settings().admin_username or "admin") and time.time() - int(timestamp) <= max_age_seconds
    except (ValueError, UnicodeDecodeError):
        return False


def public_notification_settings() -> dict:
    values = dict(load_runtime_settings()["notifications"])
    if not values.get("from_email") and values.get("smtp_username"):
        values["from_email"] = values["smtp_username"]
    values["smtp_password_configured"] = bool(values.pop("smtp_password", ""))
    return values


def update_notification_settings(values: dict) -> dict:
    data = load_runtime_settings()
    password = values.pop("smtp_password", "")
    values["smtp_host"] = values.get("smtp_host") or "smtp.gmail.com"
    if not values.get("from_email") and values.get("smtp_username"):
        values["from_email"] = values["smtp_username"]
    data["notifications"].update(values)
    if password:
        data["notifications"]["smtp_password"] = password
    save_runtime_settings(data)
    return public_notification_settings()
