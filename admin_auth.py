"""Small signed-cookie authentication helper for the site administrator."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time

from env_utils import env_first, load_project_env


load_project_env()

SESSION_COOKIE = "minslab_admin_session"


def configured_admin_password() -> str:
    configured = env_first("MINSLAB_ADMIN_PASSWORD") or ""
    shared_live_password = env_first("MULTI_AGENT_LIVE_ENABLED_key") or ""
    if configured == "MULTI_AGENT_LIVE_ENABLED_key":
        return shared_live_password or configured
    return configured or shared_live_password



def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


class AdminAuth:
    def __init__(
        self,
        password: str | None = None,
        secret: str | bytes | None = None,
        session_seconds: int = 8 * 60 * 60,
        max_failures: int = 5,
        failure_window_seconds: int = 10 * 60,
    ):
        self.password = password if password is not None else configured_admin_password()
        configured_secret = secret if secret is not None else env_first("MINSLAB_ADMIN_SESSION_SECRET")
        if isinstance(configured_secret, str):
            configured_secret = configured_secret.encode("utf-8")
        self.secret = configured_secret or secrets.token_bytes(48)
        self.session_seconds = max(300, int(session_seconds))
        self.max_failures = max(1, int(max_failures))
        self.failure_window_seconds = max(60, int(failure_window_seconds))
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    @property
    def configured(self) -> bool:
        return bool(self.password)

    def _recent_failures(self, ip_address: str, now: float) -> list[float]:
        cutoff = now - self.failure_window_seconds
        return [stamp for stamp in self._failures.get(ip_address, []) if stamp >= cutoff]

    def retry_after(self, ip_address: str, now: float | None = None) -> int:
        current = float(now if now is not None else time.time())
        with self._lock:
            failures = self._recent_failures(ip_address, current)
            self._failures[ip_address] = failures
            if len(failures) < self.max_failures:
                return 0
            return max(1, int(failures[0] + self.failure_window_seconds - current))

    def authenticate(self, candidate: str, ip_address: str, now: float | None = None) -> str:
        current = float(now if now is not None else time.time())
        if not self.configured:
            raise RuntimeError("관리자 암호가 설정되지 않았습니다.")
        if self.retry_after(ip_address, current):
            raise PermissionError("로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.")
        if not hmac.compare_digest(str(candidate or ""), self.password):
            with self._lock:
                failures = self._recent_failures(ip_address, current)
                failures.append(current)
                self._failures[ip_address] = failures
            raise ValueError("암호가 올바르지 않습니다.")
        with self._lock:
            self._failures.pop(ip_address, None)
        return self.issue_session(current)

    def issue_session(self, now: float | None = None) -> str:
        current = int(now if now is not None else time.time())
        payload = {
            "iat": current,
            "exp": current + self.session_seconds,
            "nonce": secrets.token_urlsafe(16),
        }
        encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = _b64encode(hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest())
        return f"{encoded}.{signature}"

    def verify_session(self, token: str, now: float | None = None) -> dict | None:
        try:
            encoded, supplied_signature = str(token or "").split(".", 1)
            expected_signature = _b64encode(
                hmac.new(self.secret, encoded.encode("ascii"), hashlib.sha256).digest()
            )
            if not hmac.compare_digest(supplied_signature, expected_signature):
                return None
            payload = json.loads(_b64decode(encoded).decode("utf-8"))
            current = int(now if now is not None else time.time())
            if int(payload.get("exp", 0)) <= current or int(payload.get("iat", 0)) > current + 60:
                return None
            return payload
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError):
            return None

    def cookie_header(self, token: str) -> str:
        return (
            f"{SESSION_COOKIE}={token}; Path=/; Max-Age={self.session_seconds}; "
            "HttpOnly; Secure; SameSite=Strict"
        )

    @staticmethod
    def clear_cookie_header() -> str:
        return f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; Secure; SameSite=Strict"


ADMIN_AUTH = AdminAuth()
