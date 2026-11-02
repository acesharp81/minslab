from __future__ import annotations

import urllib.parse
from datetime import datetime, timezone

import requests

from ..adapters.national_assembly.base import AdapterError, SourcePayload


ROOT_URL = "https://record.assembly.go.kr/"


def body_view_url(official_url: str) -> str:
    parsed = urllib.parse.urlsplit(official_url)
    if parsed.scheme != "https" or parsed.hostname != "record.assembly.go.kr":
        raise AdapterError("unsupported official minutes host")
    query = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    if not query.get("id", [""])[0].isdigit():
        raise AdapterError("official minutes URL has no numeric id")
    query["type"] = ["view"]
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query, doseq=True), ""))


def fetch_official_minutes_body(
    official_url: str, timeout_seconds: float = 20.0,
    *, source_key: str = "committee_minutes_body",
) -> SourcePayload:
    if source_key not in {"committee_minutes_body", "plenary_minutes_body"}:
        raise AdapterError("unsupported official minutes body source")
    view_url = body_view_url(official_url)
    headers = {"User-Agent": "PoC07-NationalAssembly/1.0 (+official-source-collector)"}
    with requests.Session() as session:
        warmup = session.get(ROOT_URL, headers=headers, timeout=timeout_seconds)
        warmup.raise_for_status()
        retrieved_at = datetime.now(timezone.utc)
        response = session.get(view_url, headers={**headers, "Referer": official_url}, timeout=timeout_seconds)
        response.raise_for_status()
        content = response.content
        status = response.status_code
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        final_url = response.url
    if status != 200:
        raise AdapterError(f"official minutes body returned HTTP {status}")
    return SourcePayload(
        source_key=source_key, content=content, content_type=content_type,
        retrieved_at=retrieved_at, source_url=final_url, http_status=status,
    )
