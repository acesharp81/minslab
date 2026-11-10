import json
import httpx
import pytest
from app.store import Store
from app.vision import Vision, DailyBudgetExhausted, token_cost


def vision(tmp_path):
    return Vision(Store(tmp_path),{'key':'synthetic','url':'https://example.test/v1','gateway':'https://meter.test','meter_token':'synthetic'})


def test_daily_denial_switches_once_and_reuses_cached_result(tmp_path, monkeypatch):
    v=vision(tmp_path);events=[];sent=[]
    def gateway(path,body=None):
        events.append((path,body))
        if path=='budget/reserve' and body['model']=='gpt-5.4':raise DailyBudgetExhausted('daily')
        return {}
    monkeypatch.setattr(v,'gateway',gateway)
    def post(url,**kw):
        sent.append(kw['json'])
        return httpx.Response(200,json={'status':'completed','usage':{'input_tokens':1000,'output_tokens':200},'output':[{'content':[{'type':'output_text','text':'완료 5건 / 미완료 1건'}]}]})
    monkeypatch.setattr('app.vision.httpx.post',post)
    picture={'data':b'synthetic','sha':'synthetic'}
    a=v.transcribe(picture);b=v.transcribe(picture)
    assert a['model']=='gpt-6.1-terra' and a['budget_source']=='monthly-shared-credit' and b['cached']
    assert len(sent)==1 and sent[0]['model']=='gpt-6.1-terra'
    assert [x[1]['model'] for x in events if x[0]=='budget/reserve']==['gpt-5.4','gpt-6.1-terra']
    settle=next(b for p,b in events if p=='budget/settle');assert settle['cost_usd']==pytest.approx(.002)
    event=next(b for p,b in events if p=='usage-events');assert event['project']=='poc13-handover' and event['model']=='gpt-6.1-terra'
    assert v.store.one('SELECT synced FROM vision_calls')['synced']==1


@pytest.mark.parametrize('reason',['monthly-exhausted','gateway-offline','unknown-reservation'])
def test_monthly_or_connection_failure_never_calls_provider(tmp_path,monkeypatch,reason):
    v=vision(tmp_path);sent=[];reserved=[]
    def gateway(path,body=None):
        reserved.append(body['model'])
        if body['model']=='gpt-5.4' and reason=='monthly-exhausted':raise DailyBudgetExhausted('daily')
        raise ValueError(reason)
    monkeypatch.setattr(v,'gateway',gateway)
    monkeypatch.setattr('app.vision.httpx.post',lambda *a,**kw:sent.append(kw))
    with pytest.raises(ValueError):v.transcribe({'data':b'x','sha':'x'})
    assert not sent and not v.store.rows('SELECT * FROM vision_calls')
    assert len(reserved)==(2 if reason=='monthly-exhausted' else 1)


@pytest.mark.parametrize('status,message,daily',[(409,'OpenAI UTC daily token limit reached',True),(409,'공통 일일 토큰 배정 없음',True),(409,'제공사 공통 호출 대기 상태',False),(503,'shared_budget_unavailable',False),(403,'meter_token_required',False)])
def test_gateway_only_classifies_explicit_daily_denial(tmp_path,monkeypatch,status,message,daily):
    v=vision(tmp_path)
    monkeypatch.setattr('app.vision.httpx.post',lambda *a,**kw:httpx.Response(status,json={'error':{'message':message}}))
    with pytest.raises(ValueError) as e:v.gateway('budget/reserve',{})
    assert isinstance(e.value,DailyBudgetExhausted)==daily


def test_shared_monthly_snapshot_and_conservative_cost(tmp_path,monkeypatch):
    v=vision(tmp_path)
    card={'id':'gpt-5.4','remaining':100,'limit':1000000,'used':999900}
    credit={'id':'openai-shared','remaining':74.5,'limit':100,'used':25,'reserved':.5,'unknown':0,'status':'AVAILABLE'}
    monkeypatch.setattr(v,'gateway',lambda *a,**kw:{'models':[card,credit],'checked_at':'2026-11-09T16:00:00Z'})
    b=v.budget();assert b['monthly_credit']==credit and b['next_model']=='gpt-6.1-terra'
    assert token_cost('gpt-6-luna',{}) is None
    assert token_cost('gpt-6-luna',{'input_tokens':1000,'output_tokens':200,'input_tokens_details':{'cache_write_tokens':100}})==pytest.approx(.000225)
