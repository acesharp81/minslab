import gzip
import hashlib
import hmac
import unittest
from unittest.mock import patch
import httpx
from poc11_proxy import proxy_inspection

class InspectionProxyTests(unittest.IsolatedAsyncioTestCase):
    async def invoke(self,admin=False,body=b''):
        seen=[];sent=[]
        async def receive():return {'type':'http.request','body':body,'more_body':False}
        async def send(message):sent.append(message)
        async def handler(request):
            seen.append(request)
            return httpx.Response(200,headers={'set-cookie':'poc11_session=abc; HttpOnly; Path=/poc/image-inspection','content-type':'application/json'},content=b'{"ok":true}')
        client=httpx.AsyncClient
        with patch('poc11_proxy.secret',return_value='test-secret'),patch('poc11_proxy.httpx.AsyncClient',side_effect=lambda **kw:client(transport=httpx.MockTransport(handler),**kw)):
            await proxy_inspection({'path':'/poc/image-inspection/api/jobs','method':'POST','query_string':b'',
               'headers':[(b'cookie',b'admin=private; poc11_session=own; other=secret'),(b'x-inspection-admin',b'forged'),(b'host',b'minslab.kr'),(b'origin',b'https://minslab.kr'),(b'content-type',b'application/json')]},receive,send,'http://inspection',is_admin=admin)
        return seen,sent
    async def test_cookie_isolation_and_no_forged_auth(self):
        seen,sent=await self.invoke(body=b'{}')
        self.assertEqual(seen[0].headers['cookie'],'poc11_session=own')
        self.assertNotIn('x-inspection-admin',seen[0].headers)
        self.assertIn(b'set-cookie',dict(sent[0]['headers']))
        self.assertEqual(seen[0].content,b'{}')
    async def test_admin_signs_method_path(self):
        seen,_=await self.invoke(admin=True)
        stamp,digest=seen[0].headers['x-inspection-admin'].split(':')
        self.assertEqual(digest,hmac.new(b'test-secret',f'{stamp}:POST:/poc/image-inspection/api/jobs'.encode(),hashlib.sha256).hexdigest())
    async def test_oversize_body_never_reaches_upstream(self):
        seen,sent=await self.invoke(body=b'x'*(21*1024*1024+1))
        self.assertFalse(seen);self.assertEqual(sent[0]['status'],413)
