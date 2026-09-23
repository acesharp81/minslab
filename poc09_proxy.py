"""Same-origin ASGI proxy for the isolated PoC9 Next.js service."""
import json
import sys
from http.cookies import SimpleCookie

import httpx


async def proxy_poc09(scope, receive, send, upstream):
    path = scope.get('path', '')
    method = scope.get('method', 'GET').upper()
    if method not in {'GET', 'HEAD', 'POST', 'PATCH', 'DELETE'}:
        payload = b'{"detail":"method not allowed"}'
        await send({'type': 'http.response.start', 'status': 405, 'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(payload)).encode()), (b'allow', b'GET, HEAD, POST, PATCH, DELETE')]})
        await send({'type': 'http.response.body', 'body': payload})
        return
    if path == '/poc/mwomeokji':
        await send({'type': 'http.response.start', 'status': 307, 'headers': [(b'location', b'/poc/mwomeokji/'), (b'content-length', b'0'), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': b''})
        return
    incoming = {key.decode('latin-1').lower(): value.decode('latin-1') for key, value in scope.get('headers', [])}
    headers = {'accept': incoming.get('accept', '*/*'), 'x-forwarded-proto': incoming.get('x-forwarded-proto', 'https'), 'x-forwarded-host': incoming.get('host', ''), 'x-forwarded-prefix': '/poc/mwomeokji', 'x-forwarded-for': scope.get('client', ('127.0.0.1', 0))[0]}
    for name in ('content-type', 'user-agent', 'if-none-match', 'if-modified-since', 'origin', 'referer'):
        if incoming.get(name):
            headers[name] = incoming[name]
    cookies = SimpleCookie()
    try:
        cookies.load(incoming.get('cookie', ''))
    except Exception:
        pass
    mmj_cookies = [f'{name}={cookies[name].value}' for name in ('poc09_guest', 'poc09_merchant') if name in cookies]
    if mmj_cookies:
        headers['cookie'] = '; '.join(mmj_cookies)
    body = bytearray()
    if method in {'POST', 'PATCH', 'DELETE'}:
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            body.extend(message.get('body', b''))
            if len(body) > 6_000_000:
                payload = b'{"detail":"request body too large"}'
                await send({'type': 'http.response.start', 'status': 413, 'headers': [(b'content-type', b'application/json'), (b'content-length', str(len(payload)).encode())]})
                await send({'type': 'http.response.body', 'body': payload})
                return
            if not message.get('more_body', False):
                break
    query = scope.get('query_string', b'').decode('ascii', errors='ignore')
    url = f'{upstream}{path}' + (f'?{query}' if query else '')
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.request(method, url, headers=headers, content=bytes(body))
        payload = b'' if method == 'HEAD' else response.content
        output_headers = [(name.lower().encode('ascii'), value.encode('latin-1')) for name, value in response.headers.multi_items() if name.lower() in {'content-type', 'cache-control', 'location', 'etag', 'last-modified', 'set-cookie', 'vary'}]
        output_headers += [(b'content-length', str(len(payload)).encode('ascii')), (b'x-content-type-options', b'nosniff'), (b'x-robots-tag', b'noindex, nofollow')]
        await send({'type': 'http.response.start', 'status': response.status_code, 'headers': output_headers})
        await send({'type': 'http.response.body', 'body': payload})
    except httpx.RequestError as error:
        print(f'PoC9 upstream unavailable: {error}', file=sys.stderr)
        payload = json.dumps({'detail': '뭐먹지? 서비스에 잠시 연결할 수 없습니다.'}, ensure_ascii=False).encode()
        await send({'type': 'http.response.start', 'status': 503, 'headers': [(b'content-type', b'application/json; charset=utf-8'), (b'content-length', str(len(payload)).encode()), (b'cache-control', b'no-store')]})
        await send({'type': 'http.response.body', 'body': b'' if method == 'HEAD' else payload})
