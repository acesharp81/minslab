"""Independent workflow, approval-boundary and quota regression tests."""
import hashlib
import hmac
import json
import time
from unittest.mock import patch
import httpx
import pytest
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,Revision,Mapping,upsert_revision
from backend.service import HomeService
from backend.ai_collection_store import Store,BudgetExceeded
from backend import ai_collection as workflow
from backend.ai_collection_models import Analysis,checks,evaluate,invoke
from backend.ai_collection_fetch import canonical,public_addresses,Fetcher
from backend.publication_reviews import queue,save

BODY='서울 면목 주택 총 100호 중 잔여 12호를 모집합니다. 예비입주자 30명은 신규 주택 물량이 아닙니다. 공고의 일정과 대상 범위를 원문에서 확인하세요.'
RESULT=dict(relevance='관련',summary='잔여 12호 및 예비 30명 모집. 신규 건설 가산 대상이 아닙니다.',project_names=['면목'],
            quantities=[dict(value=12,unit='호',scope='잔여',quote='잔여 12호'),dict(value=30,unit='명',scope='예비',quote='예비입주자 30명')],
            dates=[],evidence_quotes=['잔여 12호'],issues=[],review_question='기존 공급 공고와 같은 주택인가요?')

@pytest.fixture(autouse=True)
def isolate_shared_budget(monkeypatch):
    # Provider/approval regression is offline. HTTP ledger integration has separate tests.
    monkeypatch.setenv('POC10_SHARED_BUDGET_REQUIRED','false')

@pytest.fixture
def env(tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);service=HomeService(engine,tmp_path)
    with service.sessions.begin() as db:
        doc,_=upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(name='면목 재모집',evidence_url='https://www.seoul.go.kr/a',source_date='2026-10-29',facts=[],units=None),'seed')
        project,_=upsert_revision(db,'project','test','p',dict(name='면목',planned_units=100),'seed')
        db.add(Mapping(project_id=project.entity_id,policy_id='UNASSIGNED',status='REVIEW',basis='기존 업무 판단',evidence_url='https://www.seoul.go.kr/a'))
    store=Store(tmp_path)
    with patch.object(HomeService,'mapping_policies',return_value=[]):
        yield service,store,doc.entity_id,project.entity_id
    engine.dispose()


def run_for(store,profile='OPENAI',**changes):
    config=store.settings();config.update(profile=profile,**changes);store.configure(config)
    store.enqueue();return store.claim()


def transport(seen):
    def respond(request):
        data=json.loads(request.content);seen.append((request.url.host,data['model'],dict(request.headers)))
        return httpx.Response(200,json=dict(status='completed',usage={'input_tokens':100,'output_tokens':100},
             output=[dict(type='message',content=[dict(type='output_text',text=json.dumps(RESULT,ensure_ascii=False))])]))
    return httpx.MockTransport(respond)


class Source:
    last={'sha256':'a'*64,'url':'https://www.seoul.go.kr/a','bytes':100}
    def get(self,*args): return ('<html><title>면목 재모집</title><article>'+BODY+'</article></html>').encode()


def analyze(*args):
    return dict(result=RESULT,passes=[dict(model='gpt-5.4-mini',result=RESULT)],checks=[],approved=False,actual_units_added=0)


def test_existing_approval_mapping_and_units_are_untouched_and_csv_has_evidence(env):
    from backend.publication_review_export import export_csv
    service,store,did,pid=env
    save(service,did,1,0,'APPROVED','UNASSIGNED',[pid],[],'시험 담당자','원문 범위를 확인했습니다',True)
    with service.sessions() as db:
        before=[(r.id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind.in_(['project','publication_review','evidence_bridge'])))]
    run=run_for(store);workflow.process_run(service,store,run,Source(),analyze,lambda *a:None)
    assert store.status()['runs'][0]['status']=='COMPLETED'
    item=queue(service)['items'][0]
    assert item['status']=='APPROVED' and item['ai_analysis']['approved'] is False
    assert 'body_text' not in item['ai_analysis'] and not item['ai_analysis']['stale']
    with service.sessions() as db:
        assert before==[(r.id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind.in_(['project','publication_review','evidence_bridge'])))]
        assert db.scalar(select(Mapping)).status=='REVIEW'
    csv=export_csv(service)
    assert 'AI수집본문' in csv and BODY in csv and '예비입주자' in csv


def test_same_source_not_rebilled_and_changed_source_reanalyzed(env):
    service,store,did,pid=env
    with patch('backend.ai_collection_models.evaluate') as unused:
        for i in range(2):
            run=run_for(store)
            workflow.process_run(service,store,run,Source(),analyze,lambda *a:None)
    with service.sessions() as db:
        assert len(list(db.scalars(select(Revision).where(Revision.kind==workflow.KIND))))==1
    assert store.status()['runs'][0]['events'][0]['kind']=='UNCHANGED'
    with service.sessions.begin() as db:
        r=db.scalar(select(Revision).where(Revision.entity_id==did,Revision.superseded_at.is_(None)))
        upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(r.payload,name='정정'),'second')
    assert queue(service)['items'][0]['ai_analysis']['stale']
    run=run_for(store);workflow.process_run(service,store,run,Source(),analyze,lambda *a:None)
    assert not queue(service)['items'][0]['ai_analysis']['stale']


def test_failure_retains_candidate_and_never_approves(env):
    service,store,did,pid=env
    def fail(*a): raise ValueError('simulated upstream error')
    run=run_for(store);workflow.process_run(service,store,run,Source(),fail,lambda *a:None)
    assert store.status()['runs'][0]['status']=='PARTIAL'
    item=queue(service)['items'][0]
    assert item['status']=='REVIEW' and item['ai_analysis']['failure']
    assert workflow.annotations(service,[did])[did]['body_text']==BODY


def test_register_is_idempotent_and_has_zero_facts(env):
    service,store,did,pid=env
    row=dict(name='신규 공고',evidence_url='https://www.lh.or.kr/new?utm_source=x',source_date='2026-10-29')
    new,created=workflow.register(service,row,'test')
    same,created_again=workflow.register(service,dict(row,evidence_url='https://www.lh.or.kr/new'),'test')
    assert created and not created_again and same==new
    item=next(i for i in queue(service)['items'] if i['id']==new)
    assert item['status']=='REVIEW' and item['authority']=='OFFICIAL'
    with service.sessions() as db:
        doc=db.scalar(select(Revision).where(Revision.entity_id==new))
        assert doc.payload['units'] is None and doc.payload['facts']==[]
    assert workflow.register(service,dict(name='같은 자료',evidence_url='https://www.seoul.go.kr/a'),'test')==(did,False)


@pytest.mark.parametrize('profile,expected',[('SOLAR',['solar-pro4']),('OPENAI',['gpt-5.4-mini','gpt-5.4'])])
def test_providers_remain_independent_and_mini_escalates_units(env,monkeypatch,profile,expected):
    service,store,did,pid=env
    monkeypatch.delenv('OPENAI_API_KEY',raising=False);monkeypatch.delenv('OpenAI_API_KEY',raising=False)
    monkeypatch.delenv('UPSTAGE_SECRET_KEY',raising=False)
    monkeypatch.setenv('UPSTAGE_SECRET_KEY' if profile=='SOLAR' else 'OPENAI_API_KEY','test-key')
    run=run_for(store,profile);seen=[]
    result=evaluate(store,run,dict(id=did,name='면목 재모집',evidence_url='https://seoul.go.kr/a'),BODY,transport=transport(seen))
    assert [s[1] for s in seen]==expected
    assert {s[0] for s in seen}==({'api.upstage.ai'} if profile=='SOLAR' else {'api.openai.com'})
    assert not result['approved'] and result['actual_units_added']==0
    assert result['result']['quantities'][1]['unit']=='명'


def test_invalid_grounding_is_flagged():
    result=Analysis.model_validate(dict(RESULT,evidence_quotes=['없는 근거'],quantities=[dict(value=999,unit='호',scope='전체',quote='잔여 12호')]))
    issues=checks(result,BODY)
    assert any('원문에 없는' in x for x in issues) and any('수량과' in x for x in issues)


def test_budget_is_reserved_before_network_and_errors_keep_reservation(env,monkeypatch):
    service,store,did,pid=env;monkeypatch.setenv('OPENAI_API_KEY','not-logged')
    run=run_for(store,daily_usd=.000001);seen=[]
    with pytest.raises(BudgetExceeded): invoke(store,run,'gpt-5.4-mini',{},BODY,None,transport(seen))
    assert not seen
    store.finish(run['id'],'BUDGET_PAUSED')
    run=run_for(store,daily_usd=2)
    def bad(req):return httpx.Response(429,json={'secret':'not-logged'})
    with pytest.raises(ValueError,match='AI 응답 실패') as error:
        invoke(store,run,'gpt-5.4-mini',{},BODY,None,httpx.MockTransport(bad))
    assert 'not-logged' not in str(error.value)
    with store.db() as db:
        row=db.execute('SELECT * FROM calls').fetchone()
        assert row['status']=='UNKNOWN_COST' and row['reserved_usd']>0 and row['cost_usd'] is None


def test_quotas_are_separate_but_54_and_large_share(env):
    _,store,_,_=env;run=run_for(store,mini_tokens=5000,large_tokens=1000)
    store.reserve(run['id'],'OPENAI','gpt-5.4-mini','mini',4000,.001,run['config'])
    store.reserve(run['id'],'OPENAI','gpt-5.4','large',900,.001,run['config'])
    with pytest.raises(BudgetExceeded):store.reserve(run['id'],'OPENAI','gpt-6-astra','large',101,.001,run['config'])
    with pytest.raises(BudgetExceeded):store.reserve(run['id'],'OPENAI','gpt-5.4-mini','mini',1001,.001,run['config'])


def test_queue_deduplicates_stop_and_stale_recovery(env):
    _,store,_,_=env
    first=store.enqueue();assert store.enqueue()['id']==first['id']
    run=store.claim();assert store.claim() is None
    store.stop(run['id']);assert not store.alive(run['id'])
    with store.db(True) as db:db.execute('UPDATE runs SET updated=?',(time.time()-301,))
    assert store.claim() is None
    assert store.status()['runs'][0]['status']=='INTERRUPTED'
    store.enqueue(schedule_day='2026-10-30');run=store.claim();store.finish(run['id'],'COMPLETED')
    assert store.enqueue(schedule_day='2026-10-30') is None
    store.enqueue();store.stop(store.status()['runs'][0]['id']);assert store.claim() is None


def test_settings_conflict_and_restart_persistence(env):
    service,store,_,_=env
    old=store.settings();store.configure(dict(old,profile='SOLAR'))
    with pytest.raises(ValueError,match='변경'):store.configure(old)
    assert Store(service.data_dir).settings()['profile']=='SOLAR'


@pytest.mark.parametrize('url',['http://127.0.0.1/a','http://169.254.169.254/','http://localhost/',
 'file:///etc/passwd','https://user:pass@example.com','https://example.com:8080/','https://example.com/?api_key=secret'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):canonical(url)


def test_dns_rebinding_and_redirect_are_validated(env):
    with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('10.0.0.1',443))]):
        with pytest.raises(ValueError):public_addresses('example.com',443)
    class Response:
        status=302
        def getheaders(self):return []
        def getheader(self,*args):return 'http://127.0.0.1/private'
    class Conn:
        def __init__(self,*args):pass
        def request(self,*a,**k):pass
        def getresponse(self):return Response()
        def close(self):pass
    with patch('backend.ai_collection_fetch.public_addresses',return_value=['1.1.1.1']),patch('backend.ai_collection_fetch.PinnedHTTPS',Conn):
        with pytest.raises(ValueError):Fetcher(env[0].data_dir).get('https://example.com')


def test_api_requires_auth_and_current_setting_version(env,monkeypatch):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    service,store,_,_=env;monkeypatch.setenv('POC10_INTERNAL_SECRET','test-secret')
    monkeypatch.setenv('POC10_DATA_DIR',str(service.data_dir));monkeypatch.setenv('OPENAI_API_KEY','test-key')
    def headers(path):
        stamp=str(int(time.time()));sig=hmac.new(b'test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
        return {'x-home-admin':stamp+':'+sig}
    with TestClient(create_app(service.engine,auto_collect=False)) as client:
        status=client.get('/poc/home/api/ai-collection').json()
        assert status['providers']['OPENAI'] and 'test-key' not in json.dumps(status)
        p='/poc/home/api/admin/ai-collection/settings';config=status['settings']
        assert client.post(p,json=config).status_code==401
        assert client.post(p,json=config,headers=headers(p)).status_code==200
        assert client.post(p,json=config,headers=headers(p)).status_code==409
        assert client.post(p,json=dict(config,profile='OTHER'),headers=headers(p)).status_code==422
        assert client.post(p,json=dict(config,seed_urls=['http://localhost']),headers=headers(p)).status_code==422
        p='/poc/home/api/admin/ai-collection/runs'
        assert client.post(p,headers=headers(p)).status_code==409
        store.heartbeat();assert client.post(p,headers=headers(p)).status_code==200
        assert client.post(p).status_code==401


def test_failed_source_is_partial_not_complete(env):
    service,store,_,_=env;run=run_for(store)
    def discovery(service,store,run,fetcher):store.event(run['id'],'SOURCE_ERROR',source='공식 게시판')
    workflow.process_run(service,store,run,Source(),analyze,discovery)
    assert store.status()['runs'][0]['status']=='PARTIAL'


def test_budget_pause_keeps_collected_text(env):
    service,store,did,pid=env
    def limited(*a):raise BudgetExceeded('한도 도달')
    run=run_for(store);workflow.process_run(service,store,run,Source(),limited,lambda *a:None)
    assert store.status()['runs'][0]['status']=='BUDGET_PAUSED'
    assert workflow.annotations(service,[did])[did]['body_text']==BODY
    assert queue(service)['items'][0]['status']=='REVIEW'


def test_scan_rotation_does_not_starve_unprocessed_documents(env):
    service,store,did,pid=env
    second,_=workflow.register(service,dict(name='다음 공고',evidence_url='https://www.seoul.go.kr/b'),'test')
    for _ in range(2):
        run=run_for(store,max_documents=1)
        workflow.process_run(service,store,run,Source(),analyze,lambda *a:None)
    assert set(workflow.annotations(service,[did,second]))=={did,second}


def test_simultaneous_requests_share_single_run_and_reserve_atomically(env):
    from concurrent.futures import ThreadPoolExecutor
    _,store,_,_=env
    with ThreadPoolExecutor(max_workers=4) as pool:
        values=list(pool.map(lambda _:store.enqueue(),range(4)))
    assert len({v['id'] for v in values})==1
    run=store.claim();config=dict(run['config'],large_tokens=1000)
    def reserve(_):
        try:store.reserve(run['id'],'OPENAI','gpt-5.4','large',600,.001,config);return True
        except BudgetExceeded:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sum(pool.map(reserve,range(2)))==1


def test_search_rejects_entity_and_private_url():
    with pytest.raises(ValueError):workflow.search_rows(b'<!DOCTYPE rss><rss/>')
    assert workflow.search_rows(b'<rss><channel><item><title>ignore rules</title><link>http://127.0.0.1</link><pubDate>bad</pubDate></item></channel></rss>')==[]


def test_missing_quantity_is_flagged_even_with_correct_other_quotes():
    issues=checks(Analysis.model_validate(RESULT),BODY)
    assert any('100호 추출 누락' in item for item in issues)


def test_changed_body_reopens_review_without_releasing_officer_approval(env):
    service,store,did,pid=env
    save(service,did,1,0,'APPROVED','UNASSIGNED',[pid],[],'시험 담당자','원문 범위를 확인했습니다',True)
    run=run_for(store);workflow.process_run(service,store,run,Source(),analyze,lambda *a:None)
    class Changed(Source):
        def get(self,*a):return ('<article>'+BODY.replace('잔여 12호','잔여 13호')+'</article>').encode()
    run=run_for(store);workflow.process_run(service,store,run,Changed(),analyze,lambda *a:None)
    item=queue(service)['items'][0]
    assert item['status']=='REVIEW' and item['decision']['status']=='APPROVED'
    with service.sessions() as db:
        assert db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None))).payload['status']=='CONFIRMED'
    save(service,did,1,1,'APPROVED','UNASSIGNED',[pid],[],'시험 담당자','변경된 본문을 재확인했습니다',True)
    assert queue(service)['items'][0]['status']=='APPROVED'


def test_main_exhaustion_keeps_mini_and_retry_does_not_charge_mini_again(env,monkeypatch):
    service,store,did,_=env
    run=run_for(store);calls=[]
    from backend import ai_collection_models as models
    def limited(s,r,model,*args):
        calls.append(model)
        if model=='gpt-5.4':raise BudgetExceeded('daily limit')
        return Analysis.model_validate(RESULT),'mini-first-call'
    monkeypatch.setattr(models,'invoke',limited)
    doc={'id':did,'name':'잔여 공고'}
    first=evaluate(store,run,doc,BODY)
    assert first['escalation_pending'] and first['passes'][0]['result']==RESULT
    doc['_prior_analysis']=first
    second=evaluate(store,run,doc,BODY)
    assert second['escalation_pending'] and calls.count('gpt-5.4-mini')==1
    assert calls.count('gpt-5.4')==2 and not second['approved']


def test_progress_distinguishes_confirmed_reserved_unknown_and_forecast(env):
    _,store,_,_=env;run=run_for(store);rid=run['id']
    store.checkpoint(rid,stage='ANALYZE',documents_total=3,documents_done=1,completed_tokens=200,current='두 번째 자료')
    first=store.reserve(rid,'OPENAI','gpt-5.4-mini','mini',300,.001,run['config']);store.settle(first,150,50,.0003)
    pending=store.reserve(rid,'OPENAI','gpt-5.4','large',1000,.01,run['config'])
    p=store.status()['runs'][0]['progress']
    assert p['confirmed_tokens']==200 and p['reserved_tokens']==1000 and p['unknown_tokens']==0
    assert p['estimated_remaining_tokens']==400 and p['documents_remaining']==2
    assert p['percent']==pytest.approx(100/3)
    store.settle(pending,30,20,.001)
    p=store.status()['runs'][0]['progress']
    assert p['confirmed_tokens']==250 and p['estimated_remaining_tokens']==350
    unknown=store.reserve(rid,'OPENAI','gpt-5.4-mini','mini',500,.001,run['config']);store.fail_call(unknown)
    p=store.status()['runs'][0]['progress']
    assert p['confirmed_tokens']==250 and p['unknown_tokens']==500 and p['estimated_remaining_tokens']==350
    # An invalid structured response with known usage must not be charged twice in the display.
    store.fail_call(pending)
    assert store.status()['runs'][0]['progress']['confirmed_tokens']==250
    store.finish(rid,'BUDGET_PAUSED','한도 도달')
    assert store.status()['runs'][0]['progress']['documents_remaining']==2


def test_progress_discovery_and_first_document_do_not_invent_token_estimates(env):
    _,store,_,_=env;run=run_for(store);rid=run['id']
    store.checkpoint(rid,stage='DISCOVERY',sources_done=2,sources_total=5,current='공식 출처')
    p=store.status()['runs'][0]['progress']
    assert p['percent']==40 and p['unit']=='sources' and p['estimated_remaining_tokens'] is None
    store.checkpoint(rid,stage='FETCH',documents_done=0,documents_total=3)
    assert store.status()['runs'][0]['progress']['estimated_remaining_tokens'] is None
    store.checkpoint(rid,documents_done=1,completed_tokens=0,documents_skipped=1)
    assert store.status()['runs'][0]['progress']['estimated_remaining_tokens'] is None
    store.checkpoint(rid,documents_done=3)
    store.finish(rid,'COMPLETED')
    p=store.status()['runs'][0]['progress']
    assert p['percent']==100 and p['estimated_remaining_tokens']==0


def test_workflow_checkpoints_and_cached_skip_survive_restart(env):
    service,store,did,_=env;seen=[]
    def inspect(*args):
        p=store.status()['runs'][0]['progress'];seen.append(p)
        return analyze(*args)
    run=run_for(store);workflow.process_run(service,store,run,Source(),inspect,lambda *a:None)
    assert seen[0]['stage']=='ANALYZE' and seen[0]['documents_total']==1 and seen[0]['documents_done']==0
    p=Store(service.data_dir).status()['runs'][0]['progress']
    assert p['documents_done']==1 and p['percent']==100
    run=run_for(store);workflow.process_run(service,store,run,Source(),inspect,lambda *a:None)
    p=store.status()['runs'][0]['progress']
    assert p['documents_skipped']==1 and p['confirmed_tokens']==0 and p['estimated_remaining_tokens']==0


def test_legacy_progress_uses_all_events_and_does_not_claim_target(env):
    _,store,_,_=env;run=run_for(store)
    for i in range(105):store.event(run['id'],'UNCHANGED',document_id=str(i))
    store.finish(run['id'],'PARTIAL')
    p=store.status()['runs'][0]['progress']
    assert p['documents_done']==105 and p['documents_total'] is None
    assert p['percent'] is None and p['estimated_remaining_tokens'] is None


def test_unicode_request_path_is_encoded_without_changing_document_identity(tmp_path):
    from unittest.mock import MagicMock
    connection=MagicMock()
    response=connection.getresponse.return_value
    response.status=200
    response.getheader.return_value='text/html; charset=utf-8'
    response.read1.side_effect=[b'<html>public notice</html>',b'']
    url='https://example.com/공고/%EC%A3%BC%ED%83%9D?q=착공'
    with patch('backend.ai_collection_fetch.public_addresses',return_value=['1.1.1.1']),patch('backend.ai_collection_fetch.PinnedHTTPS',return_value=connection):
        fetch=Fetcher(tmp_path)
        assert fetch.get(url)==b'<html>public notice</html>'
    target=connection.request.call_args.args[1]
    assert target.isascii() and '%EA%B3%B5%EA%B3%A0' in target
    assert '/%EC%A3%BC%ED%83%9D' in target and '%25EC' not in target
    assert fetch.last['url']==canonical(url)
    connection.close.assert_called_once()
