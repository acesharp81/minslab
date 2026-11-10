"""End-to-end worklist tests; verify real business tables, never model-only totals."""
import csv,io,json
from unittest.mock import patch
import pytest
from sqlalchemy import select
from test_ai_agents import env,seed_officer,config,keys
from test_ai_collection import isolate_shared_budget
from officer_fixtures import officer_response
from backend import officer_campaign as campaign, ai_agent_workflows as work, ai_agents_store as agents
from backend.db import Revision,upsert_revision
from backend.publication_reviews import queue,save
from backend.ai_officer_decisions import hold_payload
from backend.stage_reconciliation import propose
from test_stage_reconciliation import proposal


def ready(env,extra=0):
 s,store,did,pid=env;run,response=seed_officer(s,store,did,pid);store.finish(run['id'],'CANCELLED')
 store.configure(dict(store.settings(),max_documents=1,search_enabled=False))
 for i in range(extra):
  with s.sessions.begin() as db:
   d=db.scalar(select(Revision).where(Revision.entity_id==did,Revision.superseded_at.is_(None)))
   upsert_revision(db,'document_evidence','seoul_press_watch','extra'+str(i),dict(d.payload,name='서울 면목 행복주택 추가 자료 '+str(i)),'test')
 return s,store,did,pid,response


def record_hold(store,run,did):
 agents.record(store,'officer',did,'fp',run['id'],'HOLD',**{k:v for k,v in hold_payload('개별 사업번호가 원문에 없어 추가 공식 증거 확보 필요').items() if k!='state'})


def test_manual_drains_more_than_five_batches_and_reports_real_holds(env):
 s,store,did,pid,_=ready(env,extra=6);c=campaign.start(s,store)
 assert c['documents']==7
 seen=[]
 for i in range(7):
  run=store.claim();assert run and run['config']['force_officer_review']
  ids=run['config']['target_document_ids'];assert len(ids)==1;seen+=ids
  record_hold(store,run,ids[0]);store.finish(run['id'],'PARTIAL');campaign.advance(s,store)
 final=campaign.latest(store)
 assert len(set(seen))==7 and final['batches']==7 and final['status']=='COMPLETED_WITH_HOLDS'
 assert final['hold']==7 and final['remaining']==0 and final['percent']==100
 rows=list(csv.DictReader(io.StringIO(campaign.export_csv(store).lstrip('\ufeff'))));assert len(rows)==7
 assert all(r['최종결정']=='HOLD' and json.loads(r['필요근거_JSON']) for r in rows)


def test_real_yes_is_checked_against_actual_saved_link(env):
 s,store,did,pid,response=ready(env);campaign.start(s,store);run=store.claim()
 with patch.object(work,'invoke',side_effect=officer_response(response,'call')):work.process(s,store,run)
 campaign.advance(s,store);final=campaign.latest(store)
 assert final['status']=='COMPLETED' and final['yes']==1 and final['effects']['DOCUMENT']==1
 assert queue(s)['items'][0]['decision']['project_ids']==[pid]


def test_model_yes_without_db_effect_is_not_completion(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);run=store.claim()
 agents.record(store,'officer',did,'fp',run['id'],'DONE',verdict='YES',stage='DECISION_YES',effects=[dict(kind='DOCUMENT',document_id=did,status='APPROVED',project_ids=[pid])])
 store.finish(run['id'],'COMPLETED');campaign.advance(s,store)
 assert campaign.latest(store)['status']=='PAUSED_ERRORS' and campaign.latest(store)['remaining']==1
 assert campaign.latest(store)['yes']==0


def test_budget_pause_resumes_only_unvisited_not_verified_items(env):
 s,store,did,pid,_=ready(env,extra=2);campaign.start(s,store)
 r=store.claim();record_hold(store,r,r['config']['target_document_ids'][0]);first=r['config']['target_document_ids'][0]
 store.finish(r['id'],'PARTIAL');campaign.advance(s,store)
 r=store.claim();store.finish(r['id'],'BUDGET_PAUSED','공통 예산 부족');campaign.advance(s,store)
 assert campaign.latest(store)['status']=='PAUSED_BUDGET' and campaign.latest(store)['hold']==1
 campaign.advance(s,store);assert store.claim() is None
 campaign.start(s,store);r=store.claim();assert first not in r['config']['target_document_ids']


def test_stop_between_batches_never_auto_restarts_and_resume_consumes_cancelled_run(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store)
 campaign.stop(store);assert campaign.latest(store)['status']=='PAUSED_USER'
 campaign.advance(s,store);assert store.claim() is None
 campaign.start(s,store);campaign.advance(s,store)
 r=store.claim();assert r and r['config']['target_document_ids']==[did]


def test_unchanged_hold_is_reviewed_once_when_explicitly_requested(env):
 s,store,did,pid,response=ready(env);response.action='HOLD';response.project_id='';response.reason='사업번호가 없어 추가 원문 확인이 필요합니다'
 with patch.object(work,'invoke',side_effect=officer_response(response,'call')) as invoke:
  for i in range(2):
   campaign.start(s,store);r=store.claim();work.process(s,store,r);campaign.advance(s,store)
   assert campaign.latest(store)['status']=='COMPLETED_WITH_HOLDS'
 assert invoke.call_count==4


def test_stage_holds_are_included_and_never_applied_by_completion_check(env):
 s,store,did,pid,_=ready(env);p=proposal(env);p['human_hold']=True;propose(s,p)
 campaign.start(s,store);r=store.claim();record_hold(store,r,did);store.finish(r['id'],'PARTIAL');campaign.advance(s,store)
 final=campaign.latest(store);assert final['total']==2 and final['hold']==1 and final['status']=='RUNNING'
 research_run=store.claim();assert research_run['config']['target_stage_ids']
 sid=research_run['config']['target_stage_ids'][0]
 agents.record(store,'officer',sid,'research',research_run['id'],'HOLD',researched=True,**{k:v for k,v in hold_payload('공식 원문 재조사 후에도 전체 물량과 사건일 근거 부족').items() if k!='state'})
 store.finish(research_run['id'],'COMPLETED');campaign.advance(s,store)
 final=campaign.latest(store);assert final['hold']==2 and final['status']=='COMPLETED_WITH_HOLDS'
 assert not s.rows('project_profile')


def test_missing_record_and_incomplete_hold_fields_are_errors(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);r=store.claim();store.finish(r['id'],'COMPLETED');campaign.advance(s,store)
 assert campaign.latest(store)['errors']==1 and campaign.latest(store)['hold']==0
 campaign.start(s,store);r=store.claim()
 agents.record(store,'officer',did,'fp',r['id'],'HOLD',verdict='HOLD',reason='모름',missing_evidence=[])
 store.finish(r['id'],'PARTIAL');campaign.advance(s,store)
 assert campaign.latest(store)['errors']==1 and campaign.latest(store)['hold']==0


def test_later_change_invalidates_earlier_yes_in_final_verification(env):
 s,store,did,pid,response=ready(env);campaign.start(s,store);r=store.claim()
 with patch.object(work,'invoke',side_effect=officer_response(response,'call')):work.process(s,store,r)
 d=queue(s)['items'][0];save(s,did,d['source_revision_no'],d['review_revision_no'],'HOLD','UNASSIGNED',[],[],'담당자','새 근거가 상충하여 원장 변경',False)
 campaign.advance(s,store);assert campaign.latest(store)['yes']==0 and campaign.latest(store)['status']=='PAUSED_ERRORS'


def test_scheduled_batches_wait_for_next_night_and_manual_can_continue(env):
 from datetime import datetime
 from zoneinfo import ZoneInfo
 s,store,did,pid,_=ready(env,extra=1)
 campaign.start(s,store,'officer:2026-11-09')
 day=datetime(2026,11,9,12,tzinfo=ZoneInfo('Asia/Seoul'));night=datetime(2026,11,10,1,tzinfo=ZoneInfo('Asia/Seoul'))
 campaign.advance(s,store,day)
 assert campaign.latest(store)['status']=='WAITING_NIGHT' and store.claim(allow_scheduled=False) is None
 campaign.advance(s,store,night);r=store.claim()
 record_hold(store,r,r['config']['target_document_ids'][0]);store.finish(r['id'],'PARTIAL')
 campaign.advance(s,store,night);campaign.advance(s,store,night)
 assert store.claim() is not None and campaign.latest(store)['batches']==2


def test_verified_yes_later_invalidated_across_batches_blocks_final_completion(env):
 s,store,did,pid,response=ready(env)
 campaign.start(s,store);r=store.claim()
 with patch.object(work,'invoke',side_effect=officer_response(response,'call')):work.process(s,store,r)
 with patch('backend.officer_campaign.verify_stages',side_effect=RuntimeError('test')):campaign.advance(s,store)
 assert campaign.latest(store)['status']=='PAUSED_ERRORS'
 assert campaign.latest(store)['status']!='COMPLETED'


def test_completion_routes_require_admin_and_start_returns_worklist(env):
 from fastapi import FastAPI
 from fastapi.testclient import TestClient
 from backend.ai_agents_api import install
 s,store,did,pid,_=ready(env);store.heartbeat();app=FastAPI()
 install(app,s,lambda req:req.headers.get('x-admin')=='yes','/poc/home')
 with patch('backend.ai_agents_api.budget',return_value=dict(models=[])),TestClient(app) as client:
  path='/poc/home/api/admin/ai-agents/officer'
  assert client.get(path+'/completion.csv').status_code==401
  assert client.post(path+'/completion/stop').status_code==401
  assert client.post(path+'/runs').status_code==401
  response=client.post(path+'/runs',headers={'x-admin':'yes'});assert response.status_code==200
  assert response.json()['documents']==1 and response.json()['status']=='RUNNING'
  assert client.get('/poc/home/api/ai-agents').json()['officer_completion']['id']==response.json()['id']
  assert client.get(path+'/completion.csv',headers={'x-admin':'yes'}).status_code==200
  assert client.post(path+'/completion/stop',headers={'x-admin':'yes'}).json()['status']=='PAUSED_USER'


def test_real_no_saved_by_decision_engine_is_verified(env):
 from backend.ai_officer_decisions import Decision,normalize_result
 s,store,did,pid,response=ready(env);campaign.start(s,store);r=store.claim()
 value=normalize_result(response,queue(s)['items'][0]);value.update(verdict='NO',project_ids=[],no_basis='NOT_PROJECT_DATA',reason='교육 홍보 내용으로 개별 주택공급 사업 자료가 아닙니다');value=Decision.model_validate(value)
 with patch.object(work,'invoke',side_effect=officer_response(value,'no')):work.process(s,store,r)
 campaign.advance(s,store)
 assert campaign.latest(store)['no']==1 and campaign.latest(store)['status']=='COMPLETED'
 assert queue(s)['items'][0]['status']=='EXCLUDED'


def test_concurrent_human_exclusion_is_respected_without_ai_credit(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);r=store.claim()
 d=queue(s)['items'][0]
 save(s,did,d['source_revision_no'],d['review_revision_no'],'EXCLUDED','UNASSIGNED',[],[],'담당자','공식 자료 확인 결과 대상 외 공고',True)
 store.finish(r['id'],'COMPLETED');campaign.advance(s,store)
 assert campaign.latest(store)['no']==1 and campaign.latest(store)['effects']=={}


def test_actual_stage_profile_must_match_to_count_yes(env):
 s,store,did,pid,_=ready(env);propose(s,proposal(env));campaign.start(s,store)
 r=store.claim();record_hold(store,r,did);store.finish(r['id'],'PARTIAL');campaign.advance(s,store)
 from backend import stage_reconciliation as sr
 from test_stage_reconciliation import apply
 row=sr.list_items(s)[0];assert apply(s,row,automatic=True)['status']=='APPLIED'
 stage_run=store.claim();store.finish(stage_run['id'],'COMPLETED');campaign.advance(s,store)
 final=campaign.latest(store);assert final['yes']==1 and final['effects']['STAGE']==1
 p=campaign.latest(store,True)
 with s.sessions.begin() as db:
  profile=db.scalar(select(Revision).where(Revision.kind=='project_profile',Revision.superseded_at.is_(None)))
  from copy import deepcopy
  payload=deepcopy(profile.payload);payload['progress']['CONSTRUCTION']['units']=999;profile.payload=payload
 campaign.verify_stages(s,p)
 assert any(result['verdict']=='ERROR' for result in p['results'].values())


def test_manual_resume_of_queued_night_work_can_claim_during_day(env):
 from datetime import datetime
 from zoneinfo import ZoneInfo
 s,store,did,pid,_=ready(env);campaign.start(s,store,'officer:2026-11-09')
 campaign.advance(s,store,datetime(2026,11,9,12,tzinfo=ZoneInfo('Asia/Seoul')))
 campaign.start(s,store)
 assert store.claim(allow_scheduled=False) is not None


def test_stale_worker_cannot_undo_stop_or_enqueue_more(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);p=campaign.latest(store,True)
 campaign.stop(store)
 with store.db(True) as db:
  campaign.enqueue_batch(db,p);campaign.persist(db,p)
 assert campaign.latest(store)['status']=='PAUSED_USER'
 assert store.claim() is None


def test_stage_application_stops_when_user_pauses(env):
 from backend import stage_reconciliation as sr
 s,store,did,pid,_=ready(env);propose(s,proposal(env))
 sr.refresh(s,auto_apply=True,can_continue=lambda:False)
 assert not s.rows('project_profile')


def test_direct_official_reference_already_committed_needs_no_second_model_run(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);run=store.claim()
 with s.sessions.begin() as db:
  doc=db.scalar(select(Revision).where(Revision.kind=='document_evidence',Revision.entity_id==did,Revision.superseded_at.is_(None)))
  ref,_=upsert_revision(db,'document_evidence','seoul_press_watch','new-proof',dict(doc.payload,name='새 공식 대조자료'),'source');new_id=ref.entity_id
 effects=[]
 for doc in queue(s)['items']:
  save(s,doc['id'],doc['source_revision_no'],doc['review_revision_no'],'APPROVED','UNASSIGNED',[pid],[],'업무담당자 AI','원문과 사업번호 대조 완료',True)
  effects.append(dict(kind='DOCUMENT',document_id=doc['id'],status='APPROVED',project_ids=[pid]))
 agents.record(store,'officer',did,'fp',run['id'],'DONE',verdict='YES',reason='공식 근거 대조 후 저장',effects=effects,official_search=[dict(document_id=new_id)])
 store.finish(run['id'],'COMPLETED');campaign.advance(s,store)
 final=campaign.latest(store)
 assert final['documents']==2 and final['yes']==2 and final['batches']==1
 assert final['effects']['DOCUMENT']==2 and store.claim() is None


def test_worklist_survives_store_restart(env):
 from backend.ai_collection_store import Store
 s,store,did,pid,_=ready(env,extra=1);campaign.start(s,store)
 run=store.claim();record_hold(store,run,run['config']['target_document_ids'][0]);store.finish(run['id'],'PARTIAL')
 restored=Store(s.data_dir);campaign.advance(s,restored)
 assert campaign.latest(restored)['hold']==1 and campaign.latest(restored)['batches']==2
 assert restored.claim() is not None


def test_existing_exclusion_without_source_checkbox_is_completed_but_stale_is_not(env):
 s,store,did,pid,_=ready(env);campaign.start(s,store);run=store.claim();d=queue(s)['items'][0]
 save(s,did,d['source_revision_no'],d['review_revision_no'],'EXCLUDED','UNASSIGNED',[],[],'위임 업무담당자','개별 주택공급 사업과 무관한 주거급여 행정 자료',False)
 work.process(s,store,run);campaign.advance(s,store)
 assert campaign.latest(store)['no']==1 and campaign.latest(store)['errors']==0
 assert campaign.latest(store)['effects']=={}
 doc=queue(s)['items'][0];doc['source_changed']=True
 assert campaign.verify_document(s,did,None,{did:doc})['verdict']=='ERROR'
 doc['source_changed']=False;doc['decision']['source_revision_no']-=1
 assert campaign.verify_document(s,did,None,{did:doc})['verdict']=='ERROR'
