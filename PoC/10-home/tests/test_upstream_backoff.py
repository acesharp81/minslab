import httpx
import pytest
from backend.collectors import Fetcher


def test_rate_limit_retries_same_page_and_honors_retry_after(tmp_path,monkeypatch):
    calls=[];sleeps=[]
    def respond(request):
        calls.append(str(request.url))
        return httpx.Response(429,headers={'Retry-After':'42'}) if len(calls)==1 else httpx.Response(200,json={'rows':[1]})
    monkeypatch.setattr('backend.collectors.time.sleep',sleeps.append)
    f=Fetcher('test',tmp_path);f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(respond))
    try:
        body=f.get('https://apis.data.go.kr/example','json',params={'serviceKey':'private-test-token','pageNo':7})
        assert b'rows' in body and calls[0]==calls[1]
        assert sleeps==[42]
        assert 'private-test-token' not in str(f.manifest)
    finally:f.close()


def test_exhausted_overload_is_not_empty_success_and_hides_key(tmp_path,monkeypatch):
    calls=[]
    def respond(request):calls.append(request);return httpx.Response(503)
    monkeypatch.setenv('POC10_FETCH_ATTEMPTS','4')
    monkeypatch.setattr('backend.collectors.time.sleep',lambda _:None)
    f=Fetcher('test',tmp_path);f.client.close();f.client=httpx.Client(transport=httpx.MockTransport(respond))
    try:
        with pytest.raises(RuntimeError,match=r'^공식 원천 연결 실패 \(HTTP 503\)$'):
            f.get('https://apis.data.go.kr/example','json',params={'serviceKey':'private-test-token'})
        assert len(calls)==4 and f.manifest==[]
    finally:f.close()
