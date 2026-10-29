from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import httpx
import pytest
from app.config import Settings
from app.storage import Store
from app import naver_ocr as n


def setup(tmp_path,limit=100):
    return Settings({'DATA_DIR':str(tmp_path),'NAVER_OCR_API_KEY':'private-test','NAVER_OCR_API_URL':'https://test.apigw.ntruss.com/infer','NAVER_OCR_MONTHLY_LIMIT':str(limit)}),Store(tmp_path/'test.sqlite3')


def test_concurrent_calls_cannot_exceed_month_cap(tmp_path):
    s,st=setup(tmp_path,3)
    def reserve(_):
        try:return n.reserve(s,st)
        except RuntimeError:return None
    with ThreadPoolExecutor(max_workers=8) as pool:ids=list(pool.map(reserve,range(16)))
    assert sum(x is not None for x in ids)==3
    assert n.snapshot(s,st)['remaining']==0 and n.snapshot(s,st)['reserved']==3


def test_month_reset_is_kst_first_day_not_credit_last_day():
    assert n.month_period(datetime(2026,10,31,14,59,tzinfo=timezone.utc))[0]=='2026-10'
    assert n.month_period(datetime(2026,10,31,15,0,tzinfo=timezone.utc))[0]=='2026-11'


def test_key_rotation_does_not_reset_monthly_calls(tmp_path):
    s,st=setup(tmp_path,1)
    n.reserve(s,st)
    s.values['NAVER_OCR_API_KEY']='rotated-test-key'
    assert n.snapshot(s,st)['remaining']==0
    with pytest.raises(RuntimeError,match='한도 소진'):n.reserve(s,st)


def test_error_code_is_safe_but_provider_body_is_not_exposed(tmp_path,monkeypatch):
    s,st=setup(tmp_path);real=httpx.Client
    monkeypatch.setattr(n.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(
        lambda req:httpx.Response(400,json={'code':'0001','message':'private-test secret URL'}))))
    with pytest.raises(RuntimeError,match='0001 호출 URL 오류'):n.call(s,st,b'png')
    assert 'private-test' not in json.dumps(n.history(st))


def test_timeout_is_counted_and_never_automatically_retried(tmp_path,monkeypatch):
    s,st=setup(tmp_path,1);real=httpx.Client;calls=[]
    def fail(req):calls.append(req);raise httpx.ReadTimeout('secret endpoint',request=req)
    monkeypatch.setattr(n.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(fail)))
    with pytest.raises(RuntimeError,match='예약 유지'):n.call(s,st,b'png')
    with pytest.raises(RuntimeError,match='한도 소진'):n.call(s,st,b'png')
    assert len(calls)==1 and n.snapshot(s,st)['unknown']==1
    assert 'secret' not in json.dumps(n.history(st))


def test_response_positions_and_key_never_enter_public_meter(tmp_path,monkeypatch):
    s,st=setup(tmp_path);real=httpx.Client
    def respond(req):
        assert req.headers['x-ocr-secret']=='private-test'
        payload=json.loads(req.content);assert len(payload['images'])==1 and payload['version']=='V2'
        return httpx.Response(200,json={'images':[{'inferResult':'SUCCESS','fields':[{'inferText':'김처찌개','inferConfidence':.8,'boundingPoly':{'vertices':[{'x':1,'y':2},{'x':30,'y':2},{'x':30,'y':20},{'x':1,'y':20}]}}]}]})
    monkeypatch.setattr(n.httpx,'Client',lambda **kw:real(transport=httpx.MockTransport(respond)))
    r=n.call(s,st,b'png');assert r['fields'][0]['rect_px']==[1,2,30,20]
    assert n.snapshot(s,st)['remaining']==99
    assert 'private-test' not in json.dumps(n.history(st))
