from officer_fixtures import officer_response
"""Workflow regressions from November audit: precheck != analysis != business approval."""
from unittest.mock import patch
import pytest
from sqlalchemy import select
from test_ai_agents import env,seed_officer,start,config,keys
from test_ai_collection import isolate_shared_budget,run_for
from backend import ai_agent_workflows as work,ai_agents_store as agents
from backend.ai_officer_review import candidate_projects,effective_analysis,ACTOR,official_search as real_official_search
from backend.publication_reviews import queue,save
from backend.db import Revision,upsert_revision

@pytest.fixture(autouse=True)
def offline_search():
 with patch('backend.ai_officer_review.official_search',return_value=[]) as search:yield search

def test_alias_candidates_are_retrieved_but_do_not_grant_identity():
 p=dict(id='P',name='고덕강일지구 3단지',address='서울 강동구 고덕동 12',revision_no=1)
 assert candidate_projects([p],'고덕강일 3단지 토지임대부 모집',{})==[p]
 assert not work.strong_identity(p,'고덕강일 3단지 토지임대부 모집')

def test_current_raw_source_recovers_missing_and_stale_analysis():
 doc=dict(id='D',source_revision_no=2)
 body='서울 면목 행복주택 사업은 서울 면목동 123에 위치합니다. 전체 공급 계획과 주택 건설 공사 일정을 확인합니다.'
 a=effective_analysis(doc,dict(source_revision_no=1,body_text='다른 판본'),{},dict(text=body))
 assert a['body_text']==body and a['body_origin']=='SOURCE' and a['source_revision_no']==2

def test_unmatched_body_is_analyzed_and_business_hold_saved_once(env,offline_search):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 with service.sessions.begin() as db:
  p=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
  upsert_revision(db,'project','test','p',dict(p.payload,name='전혀 다른 단지',address='다른 주소'),'no-match')
 result.action='HOLD';result.project_id='';result.reason='단지 블록과 사업번호가 없어 기존 사업 식별이 필요합니다'
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')) as call:work.process(service,store,r)
 assert call.call_count==1 and call.call_args.args[5]['candidates']==[]
 doc=queue(service)['items'][0];assert doc['status']=='HOLD' and doc['decision']['actor']==ACTOR
 assert offline_search.call_count==1
 progress=store.status()['runs'][0]['progress'];assert progress['business_outcomes']['model_analyzed']==1
 assert progress['business_outcomes']['holds_saved']==1 and progress['business_outcomes']['documents_linked']==0
 r=start(store,'officer')
 with patch.object(work,'invoke') as call:work.process(service,store,r)
 assert not call.called and queue(service)['items'][0]['review_revision_no']==doc['review_revision_no']

def test_ai_and_prior_human_holds_can_resolve_under_user_delegation(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 save(service,did,1,0,'HOLD','UNASSIGNED',[],[],ACTOR,'원문 보완 이전 자동 보류',False)
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')):work.process(service,store,r)
 assert queue(service)['items'][0]['status']=='APPROVED'
 assert store.status()['runs'][0]['progress']['business_outcomes']['documents_linked']==1
 doc=queue(service)['items'][0]
 save(service,did,1,doc['review_revision_no'],'HOLD','UNASSIGNED',[],[],'김민','담당자 판단으로 범위 확인 필요',True)
 r=start(store,'officer')
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')):work.process(service,store,r)
 assert queue(service)['items'][0]['status']=='APPROVED'
 assert store.status()['runs'][0]['progress']['business_outcomes']['documents_linked']==1

def test_registration_wait_is_resolved_when_existing_project_identified(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 save(service,did,1,0,'REGISTRATION_REQUIRED','UNASSIGNED',[],['서울 면목 행복주택'],'담당자','사업 등록 대기 판정',True)
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')) as call:work.process(service,store,r)
 assert call.call_count==2 and queue(service)['items'][0]['status']=='APPROVED'
 assert agents.latest(store,'officer')[did]['verdict']=='YES'

def test_unofficial_body_is_analyzed_but_never_auto_approved(env,offline_search):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 with service.sessions.begin() as db:
  d=db.scalar(select(Revision).where(Revision.entity_id==did,Revision.superseded_at.is_(None)))
  d.payload=dict(d.payload,evidence_url='https://example.com/news')
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')) as call:work.process(service,store,r)
 assert call.call_count==1 and offline_search.call_count==1
 assert queue(service)['items'][0]['status']=='HOLD'

def test_batch_completion_keeps_unprocessed_backlog_visible(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 r['config']['max_documents']=1
 with service.sessions.begin() as db:
  upsert_revision(db,'document_evidence','seoul_press_watch','second',dict(name='추가 공고',evidence_url='https://www.seoul.go.kr/b',source_date='2026-10-28',facts=[],units=None),'seed')
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')):work.process(service,store,r)
 run=store.status()['runs'][0];p=run['progress']
 assert p['queue_total']==2 and p['queue_remaining']==1 and p['percent']==100
 assert run['status']=='PARTIAL'

def test_unrelated_without_exact_source_quote_stays_hold(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 result.action='UNRELATED';result.evidence=['원문에 없는 인용'];result.reason='관련 여부에 추가 확인이 필요합니다'
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')):work.process(service,store,r)
 assert queue(service)['items'][0]['status']=='HOLD'

def test_official_search_registers_only_official_candidates_not_snippet_evidence(env):
 official_search=real_official_search
 service,store,did,_=env;run=run_for(store)
 rows=[dict(name='면목 주택 공급',evidence_url='https://example.com/news',source_date='2026-11-05'),dict(name='면목 주택 공급',evidence_url='https://www.seoul.go.kr/housing',source_date='2026-11-05')]
 with patch('backend.ai_collection_fetch.Fetcher.get',return_value=b'<rss/>'),patch('backend.ai_collection.search_rows',return_value=rows):
  found=official_search(service,store,run,dict(id=did,title='면목 주택 공급'))
 assert len(found)==1 and found[0]['verified'] is False
 docs=queue(service)['items'];new=next(d for d in docs if d['id']==found[0]['document_id'])
 assert new['status']=='REVIEW' and new['decision'] is None

def test_narrow_nonhousing_rule_plus_actual_quote_can_exclude(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 with service.sessions.begin() as db:
  d=db.scalar(select(Revision).where(Revision.entity_id==did,Revision.superseded_at.is_(None)))
  d.payload=dict(d.payload,name='희망돌보미 채용 공고')
  a=db.scalar(select(Revision).where(Revision.kind=='ai_publication_analysis',Revision.superseded_at.is_(None)))
  a.payload=dict(a.payload,body_text=a.payload['body_text']+' 희망돌보미 채용 공고입니다. 직원 채용 접수를 안내합니다.')
 result.action='UNRELATED';result.reason='직원 채용 공고로 주택사업 사건에 해당하지 않습니다'
 with patch.object(work,'invoke',side_effect=officer_response(result,'call')):work.process(service,store,r)
 assert queue(service)['items'][0]['status']=='EXCLUDED'
 assert store.status()['runs'][0]['progress']['business_outcomes']['documents_excluded']==1

def test_recovery_preserves_attachment_provenance_and_rejects_unofficial_redirect(env):
 from backend.ai_officer_evidence import recover
 service,store,did,pid=env
 doc=queue(service)['items'][0]
 body='서울 면목 행복주택의 건설 계획을 확인하는 공식 원문입니다. 사업별 공급 일정과 블록을 명시합니다. '*5
 meta=dict(url=doc['evidence_url'],sha256='a'*64,attachments=[dict(name='공고.pdf',url='https://www.seoul.go.kr/a.pdf',sha256='b'*64,file_state='PRESENT')])
 class Fetch:
  last=meta
  def get(self,*a,**kw):return b'<article/>'
 with patch('backend.ai_officer_evidence.Fetcher',return_value=Fetch()),patch('backend.publication_capture.capture',return_value=(('title',body,False),meta)):
  recover(service,doc)
 with service.sessions() as db:
  r=db.scalar(select(Revision).where(Revision.kind=='publication_supplement',Revision.superseded_at.is_(None)))
  assert r.payload['attachments'][0]['sha256']=='b'*64
 bad=dict(meta,url='https://example.com/pdf')
 with patch('backend.ai_officer_evidence.Fetcher',return_value=Fetch()),patch('backend.publication_capture.capture',return_value=(('title',body,False),bad)):
  with pytest.raises(ValueError,match='공식 출처'):recover(service,doc)

def test_invalid_model_output_is_a_failure_not_an_input_skip(env):
 service,store,did,pid=env;r,result=seed_officer(service,store,did,pid)
 with patch.object(work,'invoke',side_effect=ValueError('모델 응답 형식 오류')):work.process(service,store,r)
 outcome=store.status()['runs'][0]['progress']['business_outcomes']
 assert outcome['analysis_failed']==1 and outcome['input_held']==0 and outcome['model_analyzed']==0
 assert agents.latest(store,'officer')[did]['stage']=='ANALYSIS_ERROR'
 assert queue(service)['items'][0]['status']=='HOLD'

@pytest.mark.parametrize('condition',['night','day','manual','budget','failure','cap'])
def test_nightly_continuation_respects_window_failures_and_batch_cap(env,condition):
 from datetime import datetime
 from zoneinfo import ZoneInfo
 from backend.ai_agents_store import continue_officer
 service,store,did,pid=env;config(store,'officer',enabled=True,hour_kst=3)
 day='officer:2026-11-05'
 key=None if condition=='manual' else day+':batch:5' if condition=='cap' else day
 agents.enqueue(store,'officer',key);run=store.claim()
 store.checkpoint(run['id'],documents_done=20,queue_remaining=100,business_outcomes=dict(analysis_failed=1 if condition=='failure' else 0))
 store.finish(run['id'],'BUDGET_PAUSED' if condition=='budget' else 'PARTIAL')
 result=continue_officer(store,datetime(2026,11,5,8 if condition=='day' else 4,tzinfo=ZoneInfo('Asia/Seoul')))
 if condition=='night':
  assert result and not result['already_running']
  assert store.claim()['schedule_day']==day+':batch:2'
 else:assert result is None
