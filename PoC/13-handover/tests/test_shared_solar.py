import json
from unittest.mock import patch
import httpx
import pytest
from app.store import Store
from app.billing import Meter,completion_request
from app.shared_solar import SharedSolar
from app.streaming import completion_stream

def setup(tmp_path):
    store=Store(tmp_path);config=dict(url='https://api.upstage.ai/v1',key='test-only',model='solar-pro4')
    shared=SharedSolar(store,'http://gateway.invalid','test-token',config)
    config['_meter']=Meter(store,shared=shared)
    return store,config,shared

def test_denied_admission_never_sends_model_request(tmp_path):
    store,config,shared=setup(tmp_path)
    with patch.object(shared,'request',side_effect=ValueError('공유 한도 부족')) as reserve,patch('httpx.Client') as model:
        with pytest.raises(ValueError):completion_request(config,{'max_tokens':10},1,'question')
    assert reserve.call_count==1 and not model.called
    assert store.one('SELECT count(*) n FROM llm_costs')['n']==0

def test_both_usage_and_rejected_content_settle_and_no_key_is_exported(tmp_path):
    store,config,shared=setup(tmp_path)
    with patch.object(shared,'request',return_value={}) as gateway:
        event=config['_meter'].start(config,'question',{'max_tokens':2400})
        config['_meter'].finish(event,config,httpx.Response(200,json={'model':'solar-pro4-260806','usage':{'prompt_tokens':100,'completion_tokens':10},'content':'invalid'}))
        shared.flush()
    assert [x.args[0] for x in gateway.call_args_list]==['reserve','settle']
    reservation=gateway.call_args_list[0].args[1];assert reservation['project']=='poc13' and reservation['solar_pool']=='key2'
    value=gateway.call_args_list[1].args[1];assert value['cost_usd']==pytest.approx(.000042)
    assert 'test-only' not in str(gateway.call_args_list)

def test_missing_usage_uses_unknown_reservation_and_http_rejection_zero(tmp_path):
    store,config,shared=setup(tmp_path)
    with patch.object(shared,'request',return_value={}) as gateway:
        event=config['_meter'].start(config,'question',{'max_tokens':2400})
        config['_meter'].finish(event,config,None)
        assert gateway.call_args.args[1]['cost_usd'] is None
        event=config['_meter'].start(config,'question',{'max_tokens':2400})
        config['_meter'].finish(event,config,httpx.Response(403,json={}))
        assert gateway.call_args.args[1]['rejected'] and gateway.call_args.args[1]['cost_usd']==0

def test_settlement_failure_persists_and_prevents_next_paid_call(tmp_path):
    store,config,shared=setup(tmp_path)
    with patch.object(shared,'request',return_value={}):event=config['_meter'].start(config,'question',{'max_tokens':10})
    with patch.object(shared,'request',side_effect=ValueError('offline')),patch('httpx.Client') as model:
        config['_meter'].finish(event,config,None)
        with pytest.raises(ValueError):completion_request(config,{'max_tokens':10},1,'question')
        assert not model.called
    assert store.one('SELECT synced,settlement FROM solar_shared_calls')['settlement']
    with patch.object(shared,'request',return_value={}):shared.flush()
    assert store.one('SELECT synced FROM solar_shared_calls')['synced']==1

def test_snapshot_is_shared_cached_and_key_scoped(tmp_path):
    store,config,shared=setup(tmp_path)
    value={'models':[dict(id='solar-pro4',limit=100,used=1,reserved=2,unknown=3,remaining=94,scope='PoC10 · PoC13 공통 원장')]}
    with patch.object(shared,'request',return_value=value) as request:
        first=config['_meter'].summary(config);second=config['_meter'].summary(config)
    assert request.call_count==1 and first['remaining_usd']==second['remaining_usd']==94
    assert first['own_used_usd']==0 and first['used_usd']==1
    assert not shared.enabled(dict(config,key='different-key'))

def test_stream_interruption_still_settles_unknown_bound(tmp_path):
    store,config,shared=setup(tmp_path)
    with patch.object(shared,'request',return_value={}) as gateway,patch('httpx.Client',side_effect=httpx.ConnectError('offline')):
        with pytest.raises(httpx.ConnectError):completion_stream(config,{'max_tokens':10},1,'question',lambda _:None)
    assert [x.args[0] for x in gateway.call_args_list]==['reserve','settle']
    assert gateway.call_args.args[1]['cost_usd'] is None


def test_budget_api_does_not_overwrite_shared_remaining(tmp_path,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import create_app
    monkeypatch.setenv('HANDOVER_SOLAR_SHARED_POOL','key2')
    monkeypatch.setenv('HANDOVER_USAGE_GATEWAY_URL','http://test-gateway')
    monkeypatch.setenv('HANDOVER_USAGE_METER_TOKEN','test-token')
    result=dict(shared=True,budget_known=True,budget_usd=100,used_usd=1,remaining_usd=94,reserved_usd=2,unknown_usd=3)
    with patch.object(SharedSolar,'summary',return_value=result):
        with TestClient(create_app(tmp_path,dict(url='https://api.upstage.ai/v1',key='test-only',model='solar-pro4'))) as client:
            data=client.get('/api/budget').json()
    assert data['remaining_usd']==94 and data['shared']


def test_history_import_is_idempotent_and_does_not_reset_old_usage(tmp_path):
    store,config,shared=setup(tmp_path)
    local=Meter(store)
    known=local.start(config,'question')
    local.finish(known,config,httpx.Response(200,json={'usage':{'prompt_tokens':100,'completion_tokens':10},'model':'solar-pro4'}))
    unknown=local.start(config,'question')
    with patch.object(shared,'request',return_value={}) as gateway:
        assert shared.import_history(config)['imported']==2
        assert shared.import_history(config)['imported']==0
    assert gateway.call_count==4
    assert gateway.call_args.args[1]['cost_usd'] is None
    unknown_reserve=gateway.call_args_list[-2].args[1]
    assert unknown_reserve['input_bound']==2000000 and unknown_reserve['output_bound']==100000
    assert local.summary(config)['used_usd']==pytest.approx(.000042)
    assert local.summary(config)['unknown_calls']==1
