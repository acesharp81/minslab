from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from ..config import Settings, get_settings
from .filename import extension_from_name, safe_original_name, sha256_bytes


@dataclass(frozen=True)
class DownloadResult:
    status: str
    content: bytes = b""
    original_filename: str = ""
    extension: str = ""
    sha256: str = ""
    error: str | None = None


def validate_download_url(url: str, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("첨부파일은 HTTPS URL만 허용합니다.")
    host = (parsed.hostname or "").lower()
    if not any(host == allowed or host.endswith(f".{allowed}") for allowed in settings.download_allowed_hosts):
        raise ValueError("허용된 조달 도메인이 아닙니다.")
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("사용자정보 또는 비표준 포트가 포함된 URL은 허용하지 않습니다.")


def _filename_from_response(url: str, response: httpx.Response) -> str:
    disposition = response.headers.get("content-disposition", "")
    marker = "filename="
    if marker in disposition.lower():
        raw = disposition[disposition.lower().index(marker) + len(marker):].strip().strip('"')
        return safe_original_name(unquote(raw))
    return safe_original_name(unquote(Path(urlparse(url).path).name))


def _extension(name: str, content_type: str) -> str:
    ext = extension_from_name(name)
    if ext:
        return ext
    guessed = mimetypes.guess_extension(content_type.split(";", 1)[0].strip()) or ""
    return extension_from_name(f"file{guessed}")


def download_attachment(url: str, settings: Settings | None = None) -> DownloadResult:
    settings = settings or get_settings()
    try:
        validate_download_url(url, settings)
        limit = settings.max_file_size_mb * 1024 * 1024
        chunks: list[bytes] = []
        size = 0
        with httpx.stream("GET", url, timeout=settings.g2b_timeout_seconds, follow_redirects=False) as response:
            response.raise_for_status()
            declared = int(response.headers.get("content-length", "0") or 0)
            if declared > limit:
                raise ValueError("파일 크기 제한 초과")
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError("파일 크기 제한 초과")
                chunks.append(chunk)
            content = b"".join(chunks)
            name = _filename_from_response(url, response)
            ext = _extension(name, response.headers.get("content-type", ""))
        if not content:
            raise ValueError("0바이트 파일")
        if not ext:
            raise ValueError("허용 확장자를 확인할 수 없음")
        return DownloadResult("downloaded", content, name, ext, sha256_bytes(content))
    except Exception as exc:
        return DownloadResult("download_failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")

