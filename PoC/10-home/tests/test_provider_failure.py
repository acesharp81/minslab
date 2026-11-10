"""Provider suspension is not a business HOLD or a document repair prompt."""
import json
from unittest.mock import patch
import httpx
import pytest
from test_ai_agents import env,keys,config
from test_ai_collection import isolate_shared_budget,run_for,Source
from test_officer_campaign import ready,record_hold
from test_officer_research_v2 import prepare_stage
from backend import ai_collection as collection,ai_agent_workflows as work
from backend import officer_campaign as campaign,officer_stage_work as stages
from backend.ai_collection_models import invoke,ModelProviderError
from backend.publication_reviews import queue


@pytest.mark.parametrize('status',[400,401,403,404,422,429,503])
def test_upstream_rejection_is_safe_diagnostic_and_usage_is_not_reserved(env,status):
    _,store,_,_=env;run=run_for(store,profile='SOLAR')
    response=httpx.MockTransport(lambda _:httpx.Response(status,json={'error':{
        'code':'api_key_is_not_allowed','message':'API key suspended due to insufficient credit. secret-value-do-not-log'}}))
    with pytest.raises(ModelProviderError) as exc:
        invoke(store,run,'solar-pro4',{},'public body',None,response)
    assert f'HTTP {status}' in str(exc.value) and '크레딧 부족' in str(exc.value)
    assert 'secret-value' not in str(exc.value)
    with store.db() as db:
        row=db.execute('SELECT * FROM calls').fetchone()
        if status!=503:
            assert row['status']=='REJECTED' and row['cost_usd']==row['input_tokens']==row['output_tokens']==0
        else:assert row['status']=='UNKNOWN_COST' and row['cost_usd'] is None
        assert 'secret-value' not in str([dict(r) for r in db.execute('SELECT * FROM events')])


def test_officer_provider_failure_stops_batch_without_business_hold(env):
    s,store,did,pid,_=ready(env,extra=2)
    store.configure(dict(store.settings(),max_documents=20))
    campaign.start(s,store);run=store.claim()
    before={d['id']:d['status'] for d in queue(s)['items']}
    with patch.object(work,'invoke',side_effect=ModelProviderError('SOLAR · HTTP 403 · 크레딧 부족')) as call:
        work.process(s,store,run)
    assert call.call_count==1
    assert {d['id']:d['status'] for d in queue(s)['items']}==before
    campaign.advance(s,store);summary=campaign.latest(store)
    assert summary['status']=='PAUSED_ERRORS' and summary['remaining']==3 and summary['hold']==0
    assert 'HTTP 403' in summary['reason'] and store.claim() is None


def test_resume_changes_model_and_does_not_replay_verified_records(env):
    s,store,_,_,_=ready(env,extra=2);campaign.start(s,store)
    run=store.claim();done=run['config']['target_document_ids'][0]
    record_hold(store,run,done);store.finish(run['id'],'PARTIAL');campaign.advance(s,store)
    run=store.claim();store.finish(run['id'],'FAILED','SOLAR · HTTP 403');campaign.advance(s,store)
    config(store,'officer','gpt-5.4');campaign.start(s,store)
    resumed=store.claim()
    assert resumed['config']['selected_model']=='gpt-5.4' and resumed['config']['profile']=='OPENAI'
    assert done not in resumed['config']['target_document_ids'] and campaign.latest(store)['hold']==1


def test_stage_provider_failure_does_not_try_three_schema_repairs(env):
    s,store,run,sid,_,evidence,_=prepare_stage(env)
    run['config']['target_stage_ids']=[sid]
    with patch.object(stages,'inputs',return_value=(evidence,[])),patch('backend.ai_collection_models.invoke',side_effect=ModelProviderError('SOLAR · HTTP 403')) as call:
        stages.process(s,store,run,call)
    assert call.call_count==1 and not s.rows('project_profile')
    latest=store.status()['runs'][0]
    assert latest['status']=='FAILED' and 'HTTP 403' in latest['error']


def test_collection_preserves_source_and_stops_on_provider_failure(env):
    s,store,did,_=env;run=run_for(store)
    with patch('backend.ai_collection_models.invoke',side_effect=ModelProviderError('SOLAR · HTTP 403')) as call:
        collection.process_run(s,store,run,Source(),discover=lambda *a:None)
    assert call.call_count==1 and store.status()['runs'][0]['status']=='FAILED'
    assert collection.annotations(s,[did])[did]['body_text']
    assert queue(s)['items'][0]['status']=='REVIEW'
