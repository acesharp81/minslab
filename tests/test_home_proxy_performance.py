import gzip
import unittest
from unittest.mock import patch
import httpx
from poc10_proxy import proxy_home

class HomeProxyPerformanceTests(unittest.IsolatedAsyncioTestCase):
    async def call(self, response, headers=(), method='GET'):
        seen=[];sent=[]
        async def handler(request):
            seen.append(request)
            return response
        client=httpx.AsyncClient
        async def receive():return {'type':'http.request','body':b''}
        async def send(message):sent.append(message)
        with patch('poc10_proxy.httpx.AsyncClient',side_effect=lambda **kw:client(transport=httpx.MockTransport(handler),**kw)):
            await proxy_home({'path':'/poc/home/api/project-collection','method':method,'headers':headers,'query_string':b''},receive,send,'http://home')
        return seen[0],sent[0],sent[1]['body']

    async def test_gzip_wire_bytes_and_no_auth_forwarding(self):
        payload=gzip.compress(b'{"items":[]}'*1000)
        req,head,body=await self.call(httpx.Response(200,headers={'content-encoding':'gzip','vary':'Accept-Encoding','content-type':'application/json'},stream=httpx.ByteStream(payload)),[(b'accept-encoding',b'gzip'),(b'cookie',b'private=secret'),(b'x-home-admin',b'forged')])
        self.assertEqual(body,payload)
        self.assertEqual(dict(head['headers'])[b'content-encoding'],b'gzip')
        self.assertEqual(int(dict(head['headers'])[b'content-length']),len(payload))
        self.assertEqual(req.headers['accept-encoding'],'gzip')
        self.assertNotIn('cookie',req.headers);self.assertNotIn('x-home-admin',req.headers)

    async def test_conditional_static_revalidation(self):
        req,head,body=await self.call(httpx.Response(304,headers={'etag':'"version1"'},stream=httpx.ByteStream(b'')),[(b'if-none-match',b'"version1"')])
        self.assertEqual(req.headers['if-none-match'],'"version1"')
        self.assertEqual(head['status'],304);self.assertEqual(body,b'')
        self.assertEqual(dict(head['headers'])[b'etag'],b'"version1"')

    async def test_identity_and_head(self):
        req,head,body=await self.call(httpx.Response(200,headers={'content-length':'42'},stream=httpx.ByteStream(b'')),method='HEAD')
        self.assertEqual(req.headers['accept-encoding'],'identity')
        self.assertEqual(body,b'');self.assertEqual(dict(head['headers'])[b'content-length'],b'42')
