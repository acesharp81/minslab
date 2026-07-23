from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .config import Settings
from .storage import KST, Store


class KakaoError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class TokenCipher:
    def __init__(self, key: str):
        if not key:
            raise KakaoError("MASTER_PRESS_TOKEN_ENCRYPTION_KEY가 설정되지 않았습니다.", 503)
        try:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(key.encode("ascii"))
        except ImportError as error:
            raise KakaoError("토큰 암호화를 위해 cryptography 패키지가 필요합니다.", 503) from error
        except (ValueError, UnicodeEncodeError) as error:
            raise KakaoError("MASTER_PRESS_TOKEN_ENCRYPTION_KEY 형식이 올바르지 않습니다.", 503) from error

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(str(value).encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(str(value).encode("ascii")).decode("utf-8")


class KakaoClient:
    def __init__(self, settings: Settings, store: Store):
        self.settings = settings
        self.store = store

    @property
    def cipher(self) -> TokenCipher:
        return TokenCipher(self.settings.token_encryption_key)

    def _request(self, url: str, payload: dict | None = None, access_token: str = "", method: str = "POST") -> tuple[int, dict]:
        data = urllib.parse.urlencode(payload or {}).encode("utf-8") if payload is not None else None
        headers = {"Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded;charset=utf-8"
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                detail = json.loads(error.read().decode("utf-8"))
            except Exception:
                detail = {"message": str(error)}
            raise KakaoError(str(detail.get("msg") or detail.get("error_description") or detail.get("message") or error), error.code) from error

    def _granted_scopes(self, access_token: str, token_scope: str = "") -> list[str]:
        scopes = {value.strip() for value in str(token_scope or "").replace(",", " " ).split() if value.strip()}
        try:
            _status, data = self._request("https://kapi.kakao.com/v2/user/scopes", None, access_token, "GET")
            for item in data.get("scopes", []) if isinstance(data, dict) else []:
                if not isinstance(item, dict):
                    continue
                scope_id = str(item.get("id") or item.get("scope") or item.get("name") or "").strip()
                if scope_id and (item.get("agreed") is True or item.get("granted") is True):
                    scopes.add(scope_id)
        except KakaoError:
            if not scopes:
                raise KakaoError("카카오 메시지 전송 동의 상태를 확인하지 못했습니다. 다시 시도해 주세요.", 400)
        return sorted(scopes)

    def authorization_url(self, invite_token: str) -> str:
        if not self.store.valid_invite(invite_token):
            raise KakaoError("수신자 등록 링크가 만료되었거나 이미 사용되었습니다.", 400)
        if not (self.settings.kakao_rest_api_key and self.settings.kakao_redirect_uri):
            raise KakaoError("카카오 앱 키와 Redirect URI가 설정되지 않았습니다.", 503)
        params = urllib.parse.urlencode({
            "client_id": self.settings.kakao_rest_api_key,
            "redirect_uri": self.settings.kakao_redirect_uri,
            "response_type": "code",
            "scope": "talk_message",
            "state": invite_token,
            "prompt": "login",
        })
        return f"https://kauth.kakao.com/oauth/authorize?{params}"

    def complete_authorization(self, code: str, invite_token: str) -> dict:
        if not self.store.valid_invite(invite_token):
            raise KakaoError("수신자 등록 링크가 만료되었거나 이미 사용되었습니다.", 400)
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.settings.kakao_rest_api_key,
            "redirect_uri": self.settings.kakao_redirect_uri,
            "code": code,
        }
        if self.settings.kakao_client_secret:
            payload["client_secret"] = self.settings.kakao_client_secret
        _status, tokens = self._request("https://kauth.kakao.com/oauth/token", payload)
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        if not access_token or not refresh_token:
            raise KakaoError("카카오 토큰 응답에 필요한 값이 없습니다.")
        scopes = self._granted_scopes(access_token, str(tokens.get("scope") or ""))
        if "talk_message" not in scopes:
            raise KakaoError("카카오 로그인 후 [선택] 카카오 메시지 전송에 동의해야 실제 메시지를 받을 수 있습니다.", 400)
        _status, profile = self._request("https://kapi.kakao.com/v2/user/me", None, access_token, "GET")
        now = datetime.now(KST)
        token_data = {
            "kakao_user_id": str(profile.get("id") or ""),
            "access_token_ciphertext": self.cipher.encrypt(access_token),
            "refresh_token_ciphertext": self.cipher.encrypt(refresh_token),
            "access_token_expires_at": (now + timedelta(seconds=int(tokens.get("expires_in", 0)))).isoformat(timespec="seconds"),
            "refresh_token_expires_at": (now + timedelta(seconds=int(tokens.get("refresh_token_expires_in", 0)))).isoformat(timespec="seconds"),
            "scopes": scopes,
        }
        if not token_data["kakao_user_id"]:
            raise KakaoError("카카오 사용자 식별자를 확인하지 못했습니다.")
        recipient = self.store.consume_invite(invite_token, token_data)
        self.store.mark_signup_request_kakao_registered(invite_token, recipient["id"])
        return recipient

    def _refresh(self, recipient: dict) -> str:
        refresh_token = self.cipher.decrypt(recipient["refresh_token_ciphertext"])
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.settings.kakao_rest_api_key,
            "refresh_token": refresh_token,
        }
        if self.settings.kakao_client_secret:
            payload["client_secret"] = self.settings.kakao_client_secret
        _status, tokens = self._request("https://kauth.kakao.com/oauth/token", payload)
        access_token = tokens.get("access_token")
        if not access_token:
            raise KakaoError("카카오 액세스 토큰 갱신에 실패했습니다.")
        now = datetime.now(KST)
        updates = {
            "access_token_ciphertext": self.cipher.encrypt(access_token),
            "access_token_expires_at": (now + timedelta(seconds=int(tokens.get("expires_in", 0)))).isoformat(timespec="seconds"),
            "status": "active",
            "last_error": None,
        }
        if tokens.get("refresh_token"):
            updates["refresh_token_ciphertext"] = self.cipher.encrypt(tokens["refresh_token"])
            updates["refresh_token_expires_at"] = (now + timedelta(seconds=int(tokens.get("refresh_token_expires_in", 0)))).isoformat(timespec="seconds")
        self.store.update_recipient_tokens(recipient["id"], updates)
        return access_token

    def access_token(self, recipient_id: str) -> str:
        recipient = self.store.get_recipient(recipient_id, include_tokens=True)
        if not recipient:
            raise KakaoError("카카오 수신자를 찾지 못했습니다.", 404)
        try:
            expires_at = datetime.fromisoformat(recipient.get("access_token_expires_at") or "")
        except ValueError:
            expires_at = datetime.now(KST)
        try:
            if expires_at <= datetime.now(KST) + timedelta(minutes=5):
                return self._refresh(recipient)
            return self.cipher.decrypt(recipient["access_token_ciphertext"])
        except Exception as error:
            self.store.update_recipient_tokens(recipient_id, {"status": "reauthorize", "last_error": str(error)})
            if isinstance(error, KakaoError):
                raise
            raise KakaoError("카카오 토큰을 사용할 수 없어 재동의가 필요합니다.", 401) from error

    def connection_status(self, recipient_id: str) -> dict:
        """Refresh an expiring access token and return an operator-friendly connection result."""
        try:
            self.access_token(recipient_id)
            recipient = self.store.get_recipient(recipient_id) or {}
            if recipient.get("status") != "active" or recipient.get("last_error"):
                self.store.update_recipient_tokens(recipient_id, {"status": "active", "last_error": None})
            return {"connected": True, "label": "연결 성공", "error": ""}
        except KakaoError as error:
            return {"connected": False, "label": "연결 실패", "error": str(error)[:180]}

    @staticmethod
    def _link(original_url: str) -> dict:
        return {"web_url": original_url, "mobile_web_url": original_url}

    @staticmethod
    def _text_message(text: str, original_url: str) -> dict:
        return {
            "object_type": "text",
            "text": str(text)[:200],
            "link": KakaoClient._link(original_url),
            "button_title": "원문 보기",
        }

    @staticmethod
    def _feed_message(text: str, original_url: str, image_url: str, title: str = "", description: str = "") -> dict:
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        clean_title = str(title or "").strip() or next((line for line in lines if not line.startswith("[")), "") or "AI 언론동향 비서"
        clean_description = str(description or "").strip() or " · ".join(lines[:3]) or str(text or "")
        return {
            "object_type": "feed",
            "content": {
                "title": clean_title[:80],
                "description": clean_description[:180],
                "image_url": str(image_url).strip()[:1000],
                "link": KakaoClient._link(original_url),
            },
            "button_title": "원문 보기",
        }

    @staticmethod
    def _valid_image_url(image_url: str) -> bool:
        parsed = urllib.parse.urlsplit(str(image_url or "").strip())
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def send_to_me(self, recipient_id: str, text: str, original_url: str, image_url: str = "", title: str = "", description: str = "") -> tuple[int, dict]:
        token = self.access_token(recipient_id)
        if self._valid_image_url(image_url):
            message = self._feed_message(text, original_url, image_url, title, description)
            try:
                return self._request(
                    "https://kapi.kakao.com/v2/api/talk/memo/default/send",
                    {"template_object": json.dumps(message, ensure_ascii=False, separators=(",", ":"))},
                    token,
                )
            except KakaoError:
                pass
        message = self._text_message(text, original_url)
        return self._request(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            {"template_object": json.dumps(message, ensure_ascii=False, separators=(",", ":"))},
            token,
        )

    def disconnect(self, recipient_id: str) -> None:
        try:
            token = self.access_token(recipient_id)
            self._request("https://kapi.kakao.com/v1/user/unlink", {}, token)
        finally:
            self.store.delete_recipient(recipient_id)
