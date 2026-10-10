"""Same-origin boundary for the independently running HOME PoC."""
import hashlib
import hmac
import json
import os
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

PREFIX = "/poc/home"


def internal_secret():
    value = os.environ.get("POC10_INTERNAL_SECRET", "")
    if value:
        return value
    path = Path(__file__).parent / "PoC" / "10-home" / ".env"
    if path.is_file():
        for line in path.read_text().splitlines():
            if line.startswith("POC10_INTERNAL_SECRET="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return ""


async def proxy_home(scope, receive, send, upstream, is_admin=False):
    path, method = scope["path"], scope.get("method", "GET").upper()
    incoming = {k.decode("latin1").lower(): v.decode("latin1") for k, v in scope.get("headers", [])}

    async def error(status, message, extra=None):
        data = json.dumps({"detail": message}, ensure_ascii=False).encode()
        headers = [(b"content-type", b"application/json; charset=utf-8"), (b"content-length", str(len(data)).encode()), (b"cache-control", b"no-store")]
        headers.extend(extra or [])
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": b"" if method == "HEAD" else data})

    admin_write = method == "POST" and (path == PREFIX + "/api/admin/refresh" or path.startswith(PREFIX + "/api/admin/mappings/")
                                        or path.startswith(PREFIX + "/api/admin/targets/")
                                        or re.fullmatch(r"/poc/home/api/admin/programs/[^/]+/policy", path)
                                        or re.fullmatch(r"/poc/home/api/admin/projects/[^/]+/program", path))
    if method not in {"GET", "HEAD"} and not admin_write:
        return await error(405, "method not allowed", [(b"allow", b"GET, HEAD")])
    if admin_write:
        if not is_admin:
            return await error(401, "MinsLab 관리자 로그인이 필요합니다.")
        origin = urlparse(incoming.get("origin", ""))
        if origin.netloc != incoming.get("host") or origin.scheme not in {"http", "https"}:
            return await error(403, "같은 사이트에서 요청해야 합니다.")
    secret = internal_secret()
    headers = {"accept": incoming.get("accept", "*/*")}
    if incoming.get("content-type"):
        headers["content-type"] = incoming["content-type"]
    # Never forward the incoming signature or parent/other PoC cookies.
    if is_admin and secret:
        stamp = str(int(time.time()))
        signature = hmac.new(secret.encode(), f"{stamp}:{method}:{path}".encode(), hashlib.sha256).hexdigest()
        headers["x-home-admin"] = f"{stamp}:{signature}"
    if admin_write and not secret:
        return await error(503, "HOME 내부 인증 설정이 필요합니다.")
    body = bytearray()
    if admin_write:
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > (65_536 if path.startswith(PREFIX + "/api/admin/targets/") else 16_384):
                return await error(413, "request body too large")
            if not message.get("more_body"):
                break
    query = scope.get("query_string", b"").decode("ascii", errors="ignore")
    url = upstream.rstrip("/") + path + ("?" + query if query else "")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers, content=bytes(body))
        payload = b"" if method == "HEAD" else response.content
        output_headers = [(k.encode(), v.encode("latin1")) for k, v in response.headers.items()
                          if k.lower() in {"content-type", "cache-control", "location", "content-disposition", "content-security-policy", "x-frame-options", "referrer-policy"}]
        length = response.headers.get("content-length", "0") if method == "HEAD" else str(len(payload))
        output_headers.extend([(b"content-length", length.encode()), (b"x-content-type-options", b"nosniff")])
        await send({"type": "http.response.start", "status": response.status_code, "headers": output_headers})
        await send({"type": "http.response.body", "body": payload})
    except httpx.RequestError:
        await error(503, "HOME 데이터 서비스에 잠시 연결할 수 없습니다.")
