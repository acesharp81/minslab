from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


class KakaoProviderError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise KakaoProviderError("Kakao 토큰 암호화 키가 설정되지 않았습니다.", 503)
        try:
            from cryptography.fernet import Fernet

            self._fernet = Fernet(key.encode("ascii"))
        except ImportError as exc:
            raise KakaoProviderError("토큰 암호화 패키지가 설치되지 않았습니다.", 503) from exc
        except (ValueError, UnicodeEncodeError) as exc:
            raise KakaoProviderError("Kakao 토큰 암호화 키 형식이 올바르지 않습니다.", 503) from exc

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except Exception as exc:
            raise KakaoProviderError("Kakao 토큰을 복호화할 수 없어 재동의가 필요합니다.", 401) from exc


class KakaoNotificationProvider:
    name = "KAKAO"

    def __init__(self, settings: Any, *, timeout_seconds: float = 15.0):
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    @property
    def cipher(self) -> TokenCipher:
        return TokenCipher(self.settings.watch_kakao_token_encryption_key)

    def configured(self) -> bool:
        return bool(
            self.settings.watch_kakao_enabled
            and self.settings.watch_kakao_rest_api_key
            and self.settings.watch_kakao_redirect_uri
            and self.settings.watch_kakao_token_encryption_key
            and self.settings.watch_public_base_url
        )

    def configuration(self) -> dict[str, Any]:
        missing = []
        for name, value in (
            ("WATCH_KAKAO_REST_API_KEY", self.settings.watch_kakao_rest_api_key),
            ("WATCH_KAKAO_REDIRECT_URI", self.settings.watch_kakao_redirect_uri),
            ("WATCH_KAKAO_TOKEN_ENCRYPTION_KEY", self.settings.watch_kakao_token_encryption_key),
            ("WATCH_PUBLIC_BASE_URL", self.settings.watch_public_base_url),
        ):
            if not value:
                missing.append(name)
        if not self.settings.watch_kakao_enabled:
            missing.insert(0, "WATCH_KAKAO_ENABLED")
        return {"configured": not missing, "missing": missing}

    def _request(
        self,
        url: str,
        payload: dict[str, Any] | None = None,
        *,
        access_token: str = "",
        method: str = "POST",
    ) -> dict[str, Any]:
        data = urllib.parse.urlencode(payload or {}).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
            except Exception:
                detail = {}
            message = str(
                detail.get("msg") or detail.get("error_description")
                or detail.get("message") or "Kakao provider error"
            )[:240]
            raise KakaoProviderError(message, exc.code) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise KakaoProviderError("Kakao 연결 시간이 초과되었습니다.", 503) from exc

    def _granted_scopes(self, access_token: str, token_scope: str = "") -> list[str]:
        scopes = {
            value.strip()
            for value in str(token_scope or "").replace(",", " ").split()
            if value.strip()
        }
        try:
            data = self._request(
                "https://kapi.kakao.com/v2/user/scopes", None,
                access_token=access_token, method="GET",
            )
            for item in data.get("scopes", []) if isinstance(data, dict) else []:
                if not isinstance(item, dict):
                    continue
                scope_id = str(
                    item.get("id") or item.get("scope") or item.get("name") or ""
                ).strip()
                if scope_id and (item.get("agreed") is True or item.get("granted") is True):
                    scopes.add(scope_id)
        except KakaoProviderError:
            if not scopes:
                raise KakaoProviderError(
                    "카카오 메시지 전송 동의 상태를 확인하지 못했습니다. 다시 연결해 주세요.",
                    400,
                )
        if "talk_message" not in scopes:
            raise KakaoProviderError(
                "카카오 로그인 후 [선택] 카카오 메시지 전송에 동의해야 "
                "나와의 채팅으로 알림을 받을 수 있습니다.",
                400,
            )
        return sorted(scopes)

    def authorization_url(self, state: str) -> str:
        if not self.configured():
            raise KakaoProviderError("Kakao 연결 설정이 완료되지 않았습니다.", 503)
        params = urllib.parse.urlencode({
            "client_id": self.settings.watch_kakao_rest_api_key,
            "redirect_uri": self.settings.watch_kakao_redirect_uri,
            "response_type": "code",
            "state": state,
            "scope": "talk_message",
            "prompt": "login",
        })
        return f"https://kauth.kakao.com/oauth/authorize?{params}"

    def exchange_code(self, code: str) -> dict[str, Any]:
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.settings.watch_kakao_rest_api_key,
            "redirect_uri": self.settings.watch_kakao_redirect_uri,
            "code": code,
        }
        if self.settings.watch_kakao_client_secret:
            payload["client_secret"] = self.settings.watch_kakao_client_secret
        tokens = self._request("https://kauth.kakao.com/oauth/token", payload)
        access_token = str(tokens.get("access_token") or "")
        refresh_token = str(tokens.get("refresh_token") or "")
        if not access_token or not refresh_token:
            raise KakaoProviderError("Kakao 토큰 응답이 완전하지 않습니다.")
        scopes = self._granted_scopes(access_token, str(tokens.get("scope") or ""))
        profile = self._request(
            "https://kapi.kakao.com/v2/user/me", None,
            access_token=access_token, method="GET",
        )
        kakao_user_id = str(profile.get("id") or "")
        if not kakao_user_id:
            raise KakaoProviderError("Kakao 사용자 식별자를 확인하지 못했습니다.")
        now = datetime.now(timezone.utc)
        return {
            "kakao_user_id": kakao_user_id,
            "access_token_ciphertext": self.cipher.encrypt(access_token),
            "refresh_token_ciphertext": self.cipher.encrypt(refresh_token),
            "access_token_expires_at": now + timedelta(seconds=int(tokens.get("expires_in") or 0)),
            "refresh_token_expires_at": now + timedelta(
                seconds=int(tokens.get("refresh_token_expires_in") or 0)
            ) if tokens.get("refresh_token_expires_in") else None,
            "scopes": sorted(scopes),
        }

    def _refresh(self, account: dict[str, Any], repository: Any) -> str:
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.settings.watch_kakao_rest_api_key,
            "refresh_token": self.cipher.decrypt(account["refresh_token_ciphertext"]),
        }
        if self.settings.watch_kakao_client_secret:
            payload["client_secret"] = self.settings.watch_kakao_client_secret
        tokens = self._request("https://kauth.kakao.com/oauth/token", payload)
        access_token = str(tokens.get("access_token") or "")
        if not access_token:
            raise KakaoProviderError("Kakao 토큰 갱신에 실패했습니다.", 401)
        now = datetime.now(timezone.utc)
        repository.update_account_tokens(
            account["account_id"],
            access_token_ciphertext=self.cipher.encrypt(access_token),
            access_token_expires_at=now + timedelta(seconds=int(tokens.get("expires_in") or 0)),
            refresh_token_ciphertext=(
                self.cipher.encrypt(str(tokens["refresh_token"]))
                if tokens.get("refresh_token") else None
            ),
            refresh_token_expires_at=(
                now + timedelta(seconds=int(tokens.get("refresh_token_expires_in") or 0))
                if tokens.get("refresh_token_expires_in") else None
            ),
        )
        return access_token

    def access_token(self, account: dict[str, Any], repository: Any) -> str:
        expires_at = account.get("access_token_expires_at")
        if not isinstance(expires_at, datetime) or expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5):
            return self._refresh(account, repository)
        return self.cipher.decrypt(account["access_token_ciphertext"])

    def send(self, delivery: dict[str, Any], repository: Any) -> None:
        account = delivery["account"]
        token = self.access_token(account, repository)
        deep_link = (
            f"{self.settings.watch_public_base_url.rstrip('/')}"
            f"?watch_session={delivery['session_id']}"
        )
        message = {
            "object_type": "text",
            "text": f"{delivery['title']}\n{delivery['body']}"[:200],
            "link": {"web_url": deep_link, "mobile_web_url": deep_link},
            "button_title": "근거 발언 보기",
        }
        response = self._request(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            {"template_object": json.dumps(message, ensure_ascii=False, separators=(",", ":"))},
            access_token=token,
        )
        try:
            result_code = int(response.get("result_code", -1))
        except (TypeError, ValueError):
            result_code = -1
        if result_code != 0:
            raise KakaoProviderError("Kakao가 메시지를 접수하지 않았습니다.", 502)
