"""Offline independent checks for boundaries, routing and human hand-off."""
import csv,io,json,time,hashlib,hmac
from unittest.mock import patch
import httpx,pytest
from sqlalchemy import select
from test_ai_collection import env,run_for,RESULT,BODY,Source,analyze,isolate_shared_budget
from backend import ai_agents_store as agents,ai_agent_workflows as work,ai_agents_inbox as inbox
from backend import ai_collection as collection
from backend.ai_collection_models import evaluate,invoke,Analysis
from backend.ai_collection_store import Store,BudgetExceeded
from backend.ai_agent_catalog import NEMO
from backend.publication_reviews import save,queue
from backend.db import Revision,upsert_revision

@pytest.fixture(autouse=True)
def keys(monkeypatch):
 for k in ('OPENAI_API_KEY','UPSTAGE_SECRET_KEY','USAGE_METER_TOKEN'):monkeypatch.setenv(k,'offline-test')
 monkeypatch.setenv('USAGE_GATEWAY_URL','http://test-gateway')
 monkeypatch.setenv('POC10_SHARED_BUDGET_REQUIRED','false')

def config(store,role,model='solar-pro4',**kw):
 c=agents.settings(store)[role];c.pop('role');c.update(model=model,**kw);return agents.configure(store,role,c)

def start(store,role):agents.enqueue(store,role);return store.claim()

def test_role_models_and_optional_review_are_bounded(env):
 _,s,_,_=env
 assert list(agents.settings(s))==['algorithm','collection','officer']
 for role in ('algorithm','officer'):
  with pytest.raises(ValueError):config(s,role,'gpt-5.4-mini')
  with pytest.raises(ValueError):config(s,role,review_model='gpt-5.4')
 with pytest.raises(ValueError):config(s,'collection','solar-pro4',review_model='gpt-5.4')
 with pytest.raises(ValueError):config(s,'collection','gpt-5.4-mini',review_model='solar-pro4')
 config(s,'collection','gpt-5.4-mini',review_model='gpt-5.4')
 first=start(s,'collection');second=agents.enqueue(s,'officer')
 assert second['already_running'] and first['config']['review_model']=='gpt-5.4'
 c=agents.settings(s)['collection'];c.pop('role');agents.configure(s,'collection',c)
 with pytest.raises(ValueError):agents.configure(s,'collection',c)
 assert len(s.status()['runs'])==1

def test_solar_unlimited_usage_never_consumes_openai_local_cap(env,monkeypatch):
 _,s,_,_=env;monkeypatch.setenv('SHARED_SOLAR_UNLIMITED','true');r=run_for(s)
 c=s.reserve(r['id'],'SOLAR','solar-pro4','large',999999999,999,r['config']);s.settle(c,100,100,999)
 s.reserve(r['id'],'OPENAI','gpt-5.4-mini','mini',200,.001,r['config'])
 assert s.status()['usage'][0]['tokens']>0
 monkeypatch.setenv('SHARED_SOLAR_UNLIMITED','false')
 with pytest.raises(BudgetExceeded):s.reserve(r['id'],'SOLAR','solar-pro4','large',100,.1,r['config'])

def test_nemotron_uses_shared_gateway_and_no_second_reservation(env):
 _,s,did,_=env;config(s,'collection',NEMO);run=start(s,'collection');seen=[]
 def respond(req):
  seen.append(req);return httpx.Response(200,json={'usage':{'prompt_tokens':50,'completion_tokens':30},'choices':[{'finish_reason':'stop','message':{'content':json.dumps(RESULT)}}]})
 with patch('backend.ai_collection_models.shared_budget.reserve') as reserve:
  result,_=invoke(s,run,NEMO,{'id':did},BODY,None,httpx.MockTransport(respond))
 assert not reserve.called and result.summary==RESULT['summary']
 assert seen[0].headers['x-minslab-project']=='poc10' and seen[0].headers['x-minslab-workload']=='home_collection'
 assert 'authorization' not in seen[0].headers
 assert json.loads(seen[0].content)['model']==NEMO
 assert s.status()['usage'][0]['cost_usd']==0

def test_single_model_and_conditional_review(env):
 _,s,did,_=env;config(s,'collection','gpt-5.4-mini');r=start(s,'collection')
 with patch('backend.ai_collection_models.invoke',return_value=(Analysis.model_validate(RESULT),'test')) as call:
  result=evaluate(s,r,{'id':did,'name':'공고'},BODY)
 assert call.call_count==1 and not result['escalated']
 s.finish(r['id'],'COMPLETED');config(s,'collection','gpt-5.4-mini',review_model='gpt-5.4');r=start(s,'collection')
 with patch('backend.ai_collection_models.invoke',return_value=(Analysis.model_validate(RESULT),'test')) as call:
  result=evaluate(s,r,{'id':did,'name':'공고'},BODY)
 assert call.call_count==2 and result['escalated']

def seed_officer(service,s,did,pid,stage='UNKNOWN'):
 with service.sessions.begin() as db:
  p=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
  upsert_revision(db,'project','test','p',dict(p.payload,name='서울 면목 행복주택',address='서울 면목동 123'), 'seed-identity')
 body='서울 면목 행복주택 사업은 서울 면목동 123에 위치합니다. 공급 계획을 확인합니다.'
 r=run_for(s);doc=collection.candidates(service)[0]
 collection.save_analysis(service,doc,body,{},dict(result=RESULT,passes=[],checks=[],approved=False,actual_units_added=0),r)
 s.finish(r['id'],'COMPLETED');config(s,'officer');r=start(s,'officer')
 result=work.Decision(action='LINK',project_id=pid,reason='사업명과 주소가 공고 본문에 직접 일치합니다',evidence=['서울 면목동 123'],stage=stage,stage_basis='PLAN',issues=[])
 return r,result

def test_officer_strong_identity_links_only_document_and_keeps_stage_hold(env):
 service,s,did,pid=env;r,result=seed_officer(service,s,did,pid,'SUPPLY')
 with patch.object(work,'invoke',return_value=(result,'test-call')):work.process(service,s,r)
 assert s.status()['runs'][0]['status']=='PARTIAL'
 d=queue(service)['items'][0];assert d['status']=='APPROVED'
 assert d['decision']['actor'].startswith('업무담당자 AI')
 assert inbox.items(service,s,'officer')[0]['stage']=='STAGE_HOLD'
 with service.sessions() as db:
  p=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
  assert p.payload['planned_units']==100
  bridge=db.scalar(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))
  assert bridge.payload.get('facts',[])==[]
 assert '단계 SUPPLY' in inbox.export_csv(service,s,'officer')

@pytest.mark.parametrize('change',['empty_quote','changed_project','human_decision'])
def test_officer_does_not_accept_missing_evidence_or_concurrent_changes(env,change):
 service,s,did,pid=env;r,result=seed_officer(service,s,did,pid)
 def respond(*args,**kw):
  if change=='empty_quote':result.evidence=['']
  elif change=='changed_project':
   with service.sessions.begin() as db:
    p=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.superseded_at.is_(None)))
    upsert_revision(db,'project','test','p',dict(p.payload,address='다른 지역 456'),'concurrent')
  else:save(service,did,1,0,'HOLD','UNASSIGNED',[],[],'사람 담당자','동명이인 사업인지 확인 필요',False)
  return result,'call'
 with patch.object(work,'invoke',side_effect=respond):work.process(service,s,r)
 assert queue(service)['items'][0]['status']!='APPROVED'
 assert inbox.items(service,s,'officer')[0]['state']=='HOLD'

def test_collection_unchanged_retains_flags_and_old_approval_cannot_hide_new_failure(env):
 service,s,did,pid=env
 save(service,did,1,0,'APPROVED','UNASSIGNED',[pid],[],'담당자','기존에 확인한 연결 근거입니다',True)
 r=run_for(s);s.event(r['id'],'DOCUMENT_ERROR',document_id=did,message='새 원문 오류');s.finish(r['id'],'PARTIAL')
 assert inbox.items(service,s,'collection')[0]['state']=='HOLD'
 r=run_for(s);doc=collection.candidates(service)[0]
 collection.save_analysis(service,doc,BODY,{},dict(result=RESULT,passes=[],checks=['미달 근거 확인'],approved=False,actual_units_added=0),r)
 s.event(r['id'],'UNCHANGED',document_id=did);s.finish(r['id'],'COMPLETED')
 assert '미달 근거 확인' in inbox.items(service,s,'collection')[0]['reason']

def test_combined_csv_equals_union_and_quotes_formula(env):
 service,s,did,pid=env;r=run_for(s);s.event(r['id'],'DOCUMENT_ERROR',document_id=did,message='=HYPERLINK("bad")');s.finish(r['id'],'PARTIAL')
 agents.record(s,'officer',did,'fp',r['id'],'HOLD',title='검토',reason='근거 부족',source_revision_no=1)
 def rows(role):return list(csv.reader(io.StringIO(inbox.export_csv(service,s,role).lstrip('\ufeff'))))[1:]
 assert rows('all')==rows('collection')+rows('officer')
 assert rows('collection')[0][5].startswith("'=")
 assert inbox.export_csv(service,s).startswith('\ufeff')

def test_algorithm_proposes_without_executing_input(env):
 service,s,did,_=env;r=run_for(s);s.event(r['id'],'DOCUMENT_ERROR',document_id=did,message='원문 읽기 실패');s.finish(r['id'],'PARTIAL')
 config(s,'algorithm');r=start(s,'algorithm')
 result=work.RuleProposal(diagnosis='본문 선택자 확인',change_type='BODY_SELECTOR',selector='article',reason='첨부 범위 확인이 필요합니다',regression_cases=['과거 정상 공고'])
 with patch.object(work,'invoke',return_value=(result,'call')):work.process(service,s,r)
 out=inbox.items(service,s,'algorithm')[0]
 assert out['stage']=='RULE_VALIDATION_REQUIRED' and out['state']=='HOLD'
 assert queue(service)['items'][0]['status']=='REVIEW'

def test_api_auth_allowlist_and_csv(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 from backend import ai_agents_api
 service,s,_,_=env
 monkeypatch.setenv('POC10_INTERNAL_SECRET','test-secret');monkeypatch.setenv('POC10_DATA_DIR',str(service.data_dir))
 monkeypatch.setattr(ai_agents_api,'budget',lambda:dict(models=[]))
 def headers(path):
  stamp=str(int(time.time()));sig=hmac.new(b'test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest();return {'x-home-admin':stamp+':'+sig}
 with TestClient(create_app(service.engine,auto_collect=False)) as client:
  data=client.get('/poc/home/api/ai-agents').json();assert len(data['models'])==5
  assert 'offline-test' not in json.dumps(data)
  p='/poc/home/api/admin/ai-agents/collection/settings';v=data['agents']['collection'];v.pop('role')
  assert client.post(p,json=v).status_code==401
  assert client.post(p,json=v,headers=headers(p)).status_code==200
  assert client.post(p,json=dict(v,model='arbitrary-model'),headers=headers(p)).status_code==422
  assert client.get('/poc/home/api/ai-agents/holds.csv').content.startswith(b'\xef\xbb\xbf')
  assert client.get('/poc/home/api/ai-agents/holds.csv?role=algorithm').status_code==422


def test_clear_mini_result_does_not_trigger_paid_sample(env):
 _,s,_,_=env;config(s,'collection','gpt-5.4-mini',review_model='gpt-5.4');r=start(s,'collection')
 simple=dict(RESULT,project_names=['면목'],quantities=[],evidence_quotes=['공고 본문'],issues=[])
 with patch('backend.ai_collection_models.invoke',return_value=(Analysis.model_validate(simple),'call')) as call:
  result=evaluate(s,r,{'id':'DOC_000000','name':'공고'},'공고 본문')
 assert call.call_count==1 and not result['escalated']


def test_scheduler_runs_three_roles_in_order_without_overlap(env,monkeypatch):
 from backend import ai_collection_worker as worker
 from datetime import datetime
 from zoneinfo import ZoneInfo
 _,s,_,_=env
 for role in ('algorithm','collection','officer'):config(s,role,enabled=True,hour_kst=1)
 class Night(datetime):
  @classmethod
  def now(cls,tz=None):return datetime(2026,10,31,4,tzinfo=ZoneInfo('Asia/Seoul'))
 monkeypatch.setattr(worker,'datetime',Night)
 seen=[]
 def finish(service,store,run):seen.append(run['config']['agent_role']);store.finish(run['id'],'COMPLETED')
 monkeypatch.setattr(worker,'process_run',finish);monkeypatch.setattr(work,'process',finish)
 for _ in range(5):worker.tick(env[0],s)
 assert seen==['algorithm','collection','officer']


def test_manual_recovery_is_available_in_officer_and_hold_csv(env):
 from backend.publication_supplements import save as supplement
 service,s,did,pid=env
 r,result=seed_officer(service,s,did,pid)
 # Recover an independent full body; the previous AI extraction is deliberately empty.
 with service.sessions.begin() as db:
  for row in db.scalars(select(Revision).where(Revision.kind=='ai_publication_analysis',Revision.superseded_at.is_(None))):
   row.payload=dict(row.payload,body_text='')
 body='서울 면목 행복주택 사업은 서울 면목동 123에 위치합니다. 공급 계획을 확인합니다.'
 supplement(service,did,1,body,'공식 원문 복구',[],'담당자',hashlib.sha256(body.encode()).hexdigest())
 with patch.object(work,'invoke',return_value=(result,'test-call')) as call:work.process(service,s,r)
 assert queue(service)['items'][0]['status']=='APPROVED' and call.called
 assert call.call_args.args[4]==body
 r=run_for(s);s.event(r['id'],'DOCUMENT_ERROR',document_id=did,message='새 수집 오류');s.finish(r['id'],'PARTIAL')
 item=inbox.items(service,s,'collection')[0]
 assert item['state']=='HOLD' and item['business_status']=='APPROVED'
 assert item['body_text']==body and item['body_origin']=='담당자 원문 복구'
 exported=list(csv.DictReader(io.StringIO(inbox.export_csv(service,s,'collection').lstrip('\ufeff'))))[0]
 assert exported['수집본문']==body and exported['현재업무상태']=='자료 연결 승인'


def test_later_human_hold_replaces_stale_missing_body_message(env):
 service,s,did,pid=env;r=run_for(s)
 agents.record(s,'officer',did,'fp',r['id'],'HOLD',title='검토',reason='본문 미확보',source_revision_no=1)
 save(service,did,1,0,'HOLD',None,[],[],'담당자','본문 복구 완료. 단지별 자산 목록 필요',True)
 item=inbox.items(service,s,'officer')[0]
 assert item['state']=='HOLD' and item['stage']=='HUMAN_HOLD' and '자산 목록' in item['reason']
