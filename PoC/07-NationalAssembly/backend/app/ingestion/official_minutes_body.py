from __future__ import annotations

import http.cookiejar
import urllib.parse
import urllib.request
from datetime import datetime, timezone

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


def fetch_official_minutes_body(official_url: str, timeout_seconds: float = 20.0) -> SourcePayload:
    view_url = body_view_url(official_url)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    headers = {"User-Agent": "PoC07-NationalAssembly/1.0 (+official-source-collector)"}
    with opener.open(urllib.request.Request(ROOT_URL, headers=headers), timeout=timeout_seconds):
        pass
    request = urllib.request.Request(view_url, headers={**headers, "Referer": official_url})
    retrieved_at = datetime.now(timezone.utc)
    with opener.open(request, timeout=timeout_seconds) as response:
        content = response.read()
        status = int(getattr(response, "status", 200))
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        final_url = response.geturl()
    if status != 200:
        raise AdapterError(f"official minutes body returned HTTP {status}")
    return SourcePayload(
        source_key="committee_minutes_body", content=content, content_type=content_type,
        retrieved_at=retrieved_at, source_url=final_url, http_status=status,
    )
