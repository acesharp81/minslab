"""Read-only same-origin bridge for the independent PoC 12 Next.js app."""

import json

import httpx

PREFIX = "/poc/housing-board"
REQUEST_HEADERS = (
    "accept", "user-agent", "if-none-match", "if-modified-since",
    "rsc", "next-router-state-tree", "next-router-prefetch", "next-url", "purpose",
)
RESPONSE_HEADERS = {
    "content-type", "cache-control", "location", "etag", "last-modified", "vary",
    "content-security-policy", "x-frame-options", "referrer-policy", "x-nextjs-stale-time",
}


async def proxy_poc12(scope, receive, send, upstream):
    path = scope.get("path", "")
    method = scope.get("method", "GET").upper()
    if method not in {"GET", "HEAD"}:
        body = b'{"detail":"method not allowed"}'
        await send({"type": "http.response.start", "status": 405, "headers": [
            (b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
            (b"allow", b"GET, HEAD"), (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": body})
        return
    incoming = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
    headers = {name: incoming[name] for name in REQUEST_HEADERS if incoming.get(name)}
    headers["accept-encoding"] = "identity"
    headers["x-forwarded-proto"] = incoming.get("x-forwarded-proto", "https")
    headers["x-forwarded-host"] = incoming.get("host", "")
    headers["x-forwarded-prefix"] = PREFIX
    query = scope.get("query_string", b"").decode("ascii", errors="ignore")
    url = upstream.rstrip("/") + path + ("?" + query if query else "")
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers)
    except httpx.RequestError:
        body = json.dumps({"detail": "PoC 12 서비스에 잠시 연결할 수 없습니다."}, ensure_ascii=False).encode()
        await send({"type": "http.response.start", "status": 503, "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode()), (b"cache-control", b"no-store"),
        ]})
        await send({"type": "http.response.body", "body": b"" if method == "HEAD" else body})
        return
    body = b"" if method == "HEAD" else response.content
    outgoing = [(name.lower().encode("ascii"), value.encode("latin-1"))
                for name, value in response.headers.multi_items() if name.lower() in RESPONSE_HEADERS]
    length = response.headers.get("content-length", "0") if method == "HEAD" else str(len(body))
    outgoing.extend([(b"content-length", length.encode()), (b"x-content-type-options", b"nosniff"),
                     (b"x-robots-tag", b"noindex, nofollow")])
    await send({"type": "http.response.start", "status": response.status_code, "headers": outgoing})
    await send({"type": "http.response.body", "body": body})
