from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from ..config import get_settings


def set_watch_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.watch_session_cookie_name,
        token,
        max_age=30 * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="lax",
        path=settings.watch_session_cookie_path or "/",
    )


def clear_watch_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.watch_session_cookie_name,
        path=settings.watch_session_cookie_path or "/",
        httponly=True,
        secure=True,
        samesite="lax",
    )


def apply_security_headers(response: Response) -> Response:
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; media-src 'self' blob: https:; "
        "connect-src 'self' https: wss:; object-src 'none'; base-uri 'self'; "
        "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com; "
        "frame-ancestors 'self'; form-action 'self' https://kauth.kakao.com",
    )
    response.headers.setdefault(
        "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
    )
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
    )
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    return response


def install_security_middleware(app: Any) -> None:
    @app.middleware("http")
    async def secure_browser_session(request: Request, call_next: Any) -> Response:
        settings = get_settings()
        cookie_token = request.cookies.get(settings.watch_session_cookie_name)
        if cookie_token:
            request.scope["headers"] = [
                (name, value)
                for name, value in request.scope.get("headers", [])
                if name.lower() != b"x-watch-token"
            ] + [(b"x-watch-token", cookie_token.encode("utf-8"))]
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and (
            request.url.path.startswith("/api/watch")
            or request.url.path.startswith("/api/topic-reports")
        ):
            origin = request.headers.get("origin")
            public = urlsplit(settings.watch_public_base_url)
            expected = (
                f"{public.scheme}://{public.netloc}"
                if public.scheme and public.netloc else ""
            )
            if origin and expected and origin.rstrip("/") != expected.rstrip("/"):
                return apply_security_headers(JSONResponse(
                    status_code=403,
                    content={"detail": "허용되지 않은 요청 출처입니다."},
                ))
        return apply_security_headers(await call_next(request))
