"""Shared ledger regression: isolated schema, no live usage rows or paid requests."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest
import psycopg
from psycopg import sql
from app.config import Settings
from app.services import shared_budget as b
from app.db.openai_group_budget import OpenAIGroupBudget
from app.db.openai_daily_budget import DailyTokenLimitReached


@pytest.fixture
def ledger():
    dsn=os.environ.get('SHARED_TEST_DATABASE_URL')
    if not dsn:pytest.skip('Explicit isolated PostgreSQL test connection required')
    schema='test_shared_'+uuid.uuid4().hex
    with psycopg.connect(dsn,autocommit=True) as c:
        c.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    def connect():return psycopg.connect(dsn,options=f'-c search_path={schema},public')
    try:
        with connect() as c:
            for table in ('openai_group_daily_usage','openai_credit_grant_usage','model_provider_cooldowns'):
                c.execute(sql.SQL('CREATE TABLE {} (LIKE public.{} INCLUDING ALL)').format(sql.Identifier(table),sql.Identifier(table)))
            c.execute((Path(__file__).parents[1]/'migrations/0061_shared_model_budgets.sql').read_text())
        yield connect,Settings(_env_file=None,openai_mini_daily_token_limit=10000000,openai_daily_token_limit=1000000,
            openai_credit_grant_id='test',openai_credit_budget_usd=8,openai_credit_expires_at='2099-01-01T00:00:00Z')
    finally:
        with psycopg.connect(dsn,autocommit=True) as c:
            c.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def card(c,s,id):return next(x for x in b.snapshot(c,s)['models'] if x['id']==id)


def test_native7_and_http10_11_admit_atomically_and_idempotently(ledger):
    connect,s=ledger
    with connect() as c:
        day=OpenAIGroupBudget(c,'main').reserve(999900,1000000)
    def attempt(project):
        try:
            with connect() as c:return b.reserve(c,s,'event-'+project,project,'gpt-5.4',50,10)
        except DailyTokenLimitReached:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(attempt,['poc10','poc11']))
    assert sum(x is not None for x in results)==1
    event=next(x['event_id'] for x in results if x)
    with connect() as c:
        assert card(c,s,'gpt-5.4')['remaining']==40
        b.reserve(c,s,event,event[6:],'gpt-5.4',50,10)
        assert card(c,s,'gpt-5.4')['remaining']==40
        b.settle(c,event,20,5,.01);b.settle(c,event,20,5,.01)
        assert card(c,s,'gpt-5.4')['remaining']==75
        OpenAIGroupBudget(c,'main').settle(day,999900,{'request_rejected':True})
        assert card(c,s,'gpt-5.4')['remaining']==999975
        assert card(c,s,'gpt-5.4-mini')['remaining']==10000000
        with pytest.raises(b.BudgetUnavailable):b.reserve(c,s,event,event[6:],'gpt-5.4',50,10)


def test_unknown_and_previous_day_reservation_never_freed_on_reset(ledger):
    connect,s=ledger
    with connect() as c:
        b.reserve(c,s,'unknown-main','poc10','gpt-5.4',400,100)
        b.settle(c,'unknown-main',None,None,None)
        v=card(c,s,'gpt-5.4');assert v['unknown']==500 and v['remaining']==999500
        b.reserve(c,s,'past-day-event','poc11','gpt-5.4-mini',100,10)
        past=(datetime.now(timezone.utc)-timedelta(days=1)).date()
        c.execute("UPDATE shared_model_reservations SET period_key=%s WHERE event_id='past-day-event'",(str(past),))
        c.execute("UPDATE openai_group_daily_usage SET usage_date=%s WHERE budget_group='mini'",(past,))
        b.settle(c,'past-day-event',20,5,.01)
        assert card(c,s,'gpt-5.4-mini')['remaining']==10000000
        assert c.execute("SELECT total_tokens FROM openai_group_daily_usage WHERE usage_date=%s AND budget_group='mini'",(past,)).fetchone()[0]==25
        assert datetime.fromisoformat(v['expires_at']).hour==0


def test_solar_history_duplicates_cross_project_and_unknown(ledger):
    connect,s=ledger
    rows=[dict(event_id='legacy-solar',project='poc11',model='solar-pro4',input_tokens=1,output_tokens=1,cost_usd=109.9)]
    with connect() as c:
        b.import_solar_history(c,s,rows);b.import_solar_history(c,s,rows)
        b.reserve(c,s,'solar-new-10','poc10','solar-pro4',1000,100)
        b.settle(c,'solar-new-10',100,20,.01)
        assert card(c,s,'solar-pro4')['remaining']==pytest.approx(.09)
        with pytest.raises(b.BudgetUnavailable):b.reserve(c,s,'solar-too-large','poc11','solar-pro4',300000,100000)
        b.reserve(c,s,'solar-unknown','poc11','solar-pro4',1000,100)
        b.settle(c,'solar-unknown',None,None,None)
        v=card(c,s,'solar-pro4');assert v['unknown']>0 and v['expires_at'] is None


def test_credit_and_request_rejection(ledger):
    connect,s=ledger
    with connect() as c:
        b.reserve(c,s,'paid-request','poc11','gpt-6-astra',1000,100)
        b.settle(c,'paid-request',None,None,0,rejected=True)
        assert card(c,s,'openai-shared')['remaining']==8
        b.reserve(c,s,'paid-request-2','poc10','gpt-6.1-sol',1000,100)
        b.settle(c,'paid-request-2',None,None,None)
        assert card(c,s,'openai-shared')['unknown']>0
        with pytest.raises(b.BudgetUnavailable):b.settle(c,'paid-request-2',1,1,float('nan'))


def test_gateway_requires_auth_and_validates_without_provider_calls(monkeypatch,tmp_path):
    from fastapi.testclient import TestClient
    from app import openrouter_gateway as g
    monkeypatch.setattr(g,'METER_TOKEN','test-token')
    client=TestClient(g.app)
    assert client.get('/internal/budget/status').status_code==403
    assert client.post('/internal/budget/reserve',json={}).status_code==403
    assert client.post('/internal/budget/reserve',headers={'x-minslab-meter-token':'test-token'},json={'project':'poc10'}).status_code==422
    monkeypatch.setattr(g,'_shared_snapshot',lambda:{'models':[],'scope':b.SCOPE})
    assert client.get('/internal/budget/status',headers={'x-minslab-meter-token':'test-token'}).json()['scope']==b.SCOPE


def test_solar_unlimited_tracks_all_projects_without_dollar_cap(ledger):
    connect,s=ledger
    s=s.model_copy(update={'shared_solar_unlimited':True})
    with connect() as c:
        b.import_solar_history(c,s,[dict(event_id='old-solar-usage',project='poc11',model='solar-pro4',input_tokens=100,output_tokens=20,cost_usd=120)])
        b.reserve(c,s,'unlimited-poc10','poc10','solar-pro4',10000,1000)
        b.settle(c,'unlimited-poc10',400,40,.001)
        v=card(c,s,'solar-pro4')
        assert v['status']=='UNLIMITED' and v['limit'] is None and v['remaining'] is None
        assert v['input_tokens']==500 and v['output_tokens']==60 and v['used']>120
        assert card(c,s,'gpt-5.4-mini')['remaining']==10000000
    limited=s.model_copy(update={'shared_solar_unlimited':False})
    with connect() as c:
        with pytest.raises(b.BudgetUnavailable):b.reserve(c,limited,'paid-again-poc10','poc10','solar-pro4',10,10)


def test_home_gateway_requires_auth_and_pins_approved_free_model(monkeypatch):
    from fastapi.testclient import TestClient
    from app import openrouter_gateway as g
    monkeypatch.setattr(g,'API_KEY','test-provider-key');monkeypatch.setattr(g,'METER_TOKEN','test-meter')
    monkeypatch.setattr(g,'FREE_MODELS',('nvidia/nemotron-3.5-super-vl:free',))
    client=TestClient(g.app)
    headers={'x-minslab-project':'poc10','x-minslab-workload':'home_collection','x-minslab-data-class':'public_web_news'}
    assert client.post('/api/v1/chat/completions',headers=headers,json={}).status_code==403
    headers['x-minslab-meter-token']='test-meter'
    for model in ['nvidia/nemotron-3-super-120b-a12b:free','nvidia/nemotron-3.5-super-vl','gpt-5.4']:
        assert client.post('/api/v1/chat/completions',headers=headers,json={'model':model}).status_code==400
    # Cache intercept is after the gateway pins the exact approved model, before provider I/O.
    monkeypatch.setattr(g,'_cached',lambda *a,**kw:(200,b'{"cached":true}'))
    response=client.post('/api/v1/chat/completions',headers=headers,json={'model':'nvidia/nemotron-3.5-super-vl:free'})
    assert response.status_code==200 and response.json()['cached']
