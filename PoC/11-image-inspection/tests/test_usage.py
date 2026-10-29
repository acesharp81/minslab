import json
import httpx
import pytest
from app.config import Settings
from app.storage import Store
from app.usage import Usage,BudgetError

def setup(tmp_path,**values):
    s=Settings({'DATA_DIR':str(tmp_path),'USAGE_GATEWAY_URL':'https://meter.example','USAGE_METER_TOKEN':'meter-test',
                'SHARED_BUDGET_DATABASE_URL':'','OPENROUTER_GATEWAY_URL':'','OPENROUTER_API_KEY':'','SHARED_CREDIT_GRANT_ID':'grant1','SHARED_CREDIT_EXPIRES_AT':'2099-01-01T00:00:00+00:00',
                'SHARED_CREDIT_BUDGET_USD':'8','SHARED_CREDIT_MONTH_END_RENEWAL':'false',**values})
    return Usage(s,Store(tmp_path/'test.sqlite3'))

def event():return dict(event_id='poc11-test-event',project='poc11-image-inspection',workload='text-analysis',provider='upstage',model='solar-pro4',status='COMPLETED',http_status=200,input_tokens=10,output_tokens=4,cost_usd=.01)

def test_failed_delivery_retained_and_retried_same_id(tmp_path,monkeypatch):
    u=setup(tmp_path);sent=[]
    def failed(*a,**kw):raise httpx.ConnectError('down')
    monkeypatch.setattr('app.usage.httpx.post',failed);u.record(event(),None)
    with u.store.connect() as c:assert c.execute('SELECT synced FROM usage_events').fetchone()[0]==0
    def delivered(url,**kw):sent.append(kw['json']);return httpx.Response(201,request=httpx.Request('POST',url))
    monkeypatch.setattr('app.usage.httpx.post',delivered)
    assert u.flush()==1 and u.flush()==0
    assert sent[0]['event_id']==event()['event_id']
    assert 'reservation' not in sent[0]

def test_shared_budget_required_and_expiry(tmp_path):
    u=setup(tmp_path)
    with pytest.raises(BudgetError):u.reserve('id','gpt-6-astra',100,100)
    u.s.values['SHARED_CREDIT_EXPIRES_AT']='2000-01-01T00:00:00+00:00'
    with pytest.raises(BudgetError):u.period()
    u.s.values.update(SHARED_CREDIT_MONTH_END_RENEWAL='true',SHARED_CREDIT_MONTHLY_BUDGET_USD='20')
    grant,cap=u.period();assert grant.startswith('grant1:renew:') and cap==20

def test_unknown_model_not_charged(tmp_path):
    with pytest.raises(BudgetError):setup(tmp_path).reserve('id','unknown',100,100)

def test_remaining_models_share_one_budget_and_solar_stays_unknown(tmp_path,monkeypatch):
    u=setup(tmp_path)
    monkeypatch.setattr(u,'budget_snapshot',lambda:{'budget':{'remaining_usd':6.25,'limit_usd':8,'expires_at':'2099-01-01T00:00:00+00:00'}})
    daily,mini,shared,solar,router,naver=u.remaining()['models']
    assert naver['limit']==100 and naver['period']=='month'
    assert mini['id']=='gpt-5.4-mini' and mini['scope']=='POC7_SHARED_OPENAI_MINI_TOKENS'
    assert daily['id']=='gpt-5.4' and daily['unit']=='tokens'
    assert shared['remaining']==6.25
    assert shared['scope']=='POC7_SHARED_OPENAI_CREDIT'
    assert router['remaining'] is None
    assert solar['remaining'] is None and solar['limit'] is None and solar['status']=='UNCONFIRMED'
    monkeypatch.setattr(u,'budget_snapshot',lambda:{'budget':{'remaining_usd':0,'limit_usd':8,'expires_at':None}})
    assert next(m for m in u.remaining()['models'] if m['id']=='openai-shared')['remaining']==0


def test_unavailable_budget_is_not_zero_or_unlimited(tmp_path,monkeypatch):
    u=setup(tmp_path)
    monkeypatch.setattr(u,'budget_snapshot',lambda:{'budget':None,'budget_error':'연결 오류'})
    for m in u.remaining()['models'][:1]:
        assert m['remaining'] is None and m['limit'] is None and m['status']=='UNAVAILABLE'


def test_openrouter_remaining_uses_provider_counter_not_credit_or_guess(tmp_path,monkeypatch):
    u=setup(tmp_path,OPENROUTER_API_KEY='test')
    def response(url,**kwargs):return httpx.Response(200,json={'data':{'limit_remaining':100,'free_model_daily_requests':{'remaining':37,'limit':50}}},request=httpx.Request('GET',url))
    monkeypatch.setattr('app.usage.httpx.get',response)
    assert u.openrouter_remaining()['remaining']==37 and u.openrouter_remaining()['unit']=='requests'
    monkeypatch.setattr('app.usage.httpx.get',lambda url,**kw:httpx.Response(200,json={'data':{'limit_remaining':100}},request=httpx.Request('GET',url)))
    assert u.openrouter_remaining()['remaining'] is None
    assert u.reserve('free','nvidia/nemotron-3.5-super-vl:free',100,100) is None


def test_shared_openrouter_remaining_takes_minimum_and_fails_closed(tmp_path,monkeypatch):
    u=setup(tmp_path,OPENROUTER_API_KEY='test',OPENROUTER_GATEWAY_URL='http://shared:8071')
    def respond(url,**kw):
        body={'data':{'free_model_daily_requests':{'remaining':910,'limit':1000}}} if url.endswith('/key') else {'remaining':876,'operational_limit':950,'safety_reserve':50}
        return httpx.Response(200,json=body,request=httpx.Request('GET',url))
    monkeypatch.setattr('app.usage.httpx.get',respond)
    card=u.openrouter_remaining();assert card['remaining']==876 and card['official_remaining']==910
    assert card['scope']=='POC7_SHARED_OPENROUTER_REQUESTS'


@pytest.mark.parametrize('instant,start,end',[
 ('2026-10-30T14:59:59+00:00',None,'2026-10-31T00:00:00+09:00'),
 ('2026-10-30T15:00:00+00:00','2026-10-31','2026-11-30T00:00:00+09:00'),
 ('2026-11-29T15:00:00+00:00','2026-11-30','2026-12-31T00:00:00+09:00'),
 ('2026-12-30T15:00:00+00:00','2026-12-31','2027-01-31T00:00:00+09:00'),
 ('2027-02-27T15:00:00+00:00','2027-02-28','2027-03-31T00:00:00+09:00'),
 ('2028-02-28T15:00:00+00:00','2028-02-29','2028-03-31T00:00:00+09:00'),
])
def test_month_end_credit_boundary_preserves_initial_allowance(tmp_path,monkeypatch,instant,start,end):
    from datetime import datetime
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime.fromisoformat(instant).astimezone(tz)
    monkeypatch.setattr('app.usage.datetime',Clock)
    u=setup(tmp_path,SHARED_CREDIT_EXPIRES_AT='2026-10-31T00:00:00+09:00',SHARED_CREDIT_MONTH_END_RENEWAL='true',SHARED_CREDIT_MONTHLY_BUDGET_USD='100')
    grant,amount,expiry=u.period_details()
    assert grant==('grant1:renew:'+start if start else 'grant1')
    assert amount==(100 if start else 8) and expiry==end


def test_monthly_gauge_denominator_does_not_increase_current_allowance(tmp_path,monkeypatch):
    u=setup(tmp_path)
    monkeypatch.setattr(u,'budget_snapshot',lambda:{'budget':{'limit_usd':8,'monthly_limit_usd':100,'remaining_usd':6.82,'expires_at':'2026-10-31T00:00:00+09:00','renewal':'KST_MONTH_LAST_DAY_00:00'}})
    card=next(m for m in u.remaining()['models'] if m['id']=='openai-shared')
    assert card['limit']==100 and card['remaining']==6.82 and card['current_period_allowance']==8
    assert '말일' in card['note']
