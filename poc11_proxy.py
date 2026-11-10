"""Same-origin proxy for the independent image inspection service."""
import hashlib
import hmac
import json
import time
from pathlib import Path
import httpx
from admin_auth import AdminAuth

PREFIX='/poc/image-inspection'

def secret():
    path=Path(__file__).parent/'PoC/11-image-inspection/.env'
    if not path.exists():return ''
    for line in path.read_text().splitlines():
        if line.startswith('SESSION_SECRET='):return line.split('=',1)[1].strip().strip("\"'")
    return ''

async def proxy_inspection(scope,receive,send,upstream,is_admin=False):
    method=scope.get('method','GET').upper();path=scope['path']
    incoming={k.decode().lower():v.decode('latin1') for k,v in scope.get('headers',[])}
    async def error(code,message):
        body=json.dumps({'detail':message},ensure_ascii=False).encode()
        await send({'type':'http.response.start','status':code,'headers':[(b'content-type',b'application/json; charset=utf-8'),(b'cache-control',b'no-store')]})
        await send({'type':'http.response.body','body':body})
    headers={k:incoming[k] for k in ('content-type','accept','origin','host','if-none-match','if-modified-since') if k in incoming}
    # Never negotiate a coding that the browser did not request. Keep the wire
    # bytes compressed; httpx.request().content otherwise silently decodes them.
    headers['accept-encoding']=incoming.get('accept-encoding','identity')
    # Forward only PoC11's own cookie; never forward arbitrary auth headers.
    from http.cookies import SimpleCookie
    cookies=SimpleCookie()
    try:cookies.load(incoming.get('cookie',''))
    except Exception:pass
    if 'poc11_session' in cookies:headers['cookie']='poc11_session='+cookies['poc11_session'].value
    if is_admin and secret():
        stamp=str(int(time.time()));digest=hmac.new(secret().encode(),f'{stamp}:{method}:{path}'.encode(),hashlib.sha256).hexdigest();headers['x-inspection-admin']=f'{stamp}:{digest}'
    body=bytearray()
    while True:
        msg=await receive()
        if msg['type']=='http.disconnect':return
        body.extend(msg.get('body',b''))
        if len(body)>21*1024*1024:return await error(413,'이미지는 최대 20MB까지 등록할 수 있습니다.')
        if not msg.get('more_body'):break
    query=scope.get('query_string',b'').decode('ascii','ignore')
    try:
        async with httpx.AsyncClient(timeout=40,follow_redirects=False,trust_env=False) as client:
            async with client.stream(method,upstream.rstrip('/')+path+('?' +query if query else ''),headers=headers,content=bytes(body)) as r:
                payload=b''.join([chunk async for chunk in r.aiter_raw()])
        out=[(k.encode(),v.encode('latin1')) for k,v in r.headers.multi_items() if k.lower() in ('content-type','content-disposition','content-encoding','etag','last-modified','vary','set-cookie','location','cache-control','content-security-policy','x-frame-options','referrer-policy','x-content-type-options')]
        # The signed site session otherwise immediately logs the user back in.
        # Only a successful local logout ends the browser's shared site session.
        if method=='POST' and path==PREFIX+'/api/logout' and 200<=r.status_code<300:
            out.append((b'set-cookie',AdminAuth.clear_cookie_header().encode('latin1')))
        no_body=method=='HEAD' or r.status_code in (204,304)
        if not no_body:out.append((b'content-length',str(len(payload)).encode()))
        elif method=='HEAD' and 'content-length' in r.headers:out.append((b'content-length',r.headers['content-length'].encode()))
        await send({'type':'http.response.start','status':r.status_code,'headers':out});await send({'type':'http.response.body','body':b'' if no_body else payload})
    except httpx.HTTPError:await error(503,'이미지 검수 서비스에 연결할 수 없습니다.')
