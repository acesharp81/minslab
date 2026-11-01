"""Fixed source examples verify accounting and approval boundaries independently of models."""
import csv,io,json,hashlib,hmac,time
from copy import deepcopy
from unittest.mock import patch
import pytest
from sqlalchemy import select,func
from test_ai_collection import env
from test_ai_agents import seed_officer,start
from backend import stage_reconciliation as sr, ai_agent_workflows as work
from backend.db import Revision,Mapping,upsert_revision,entity_id
from backend.publication_reviews import queue,save
from backend.ai_agents_inbox import export_csv

PHRASES={'BUSINESS':'지구 지정 완료','APPROVAL':'사업계획 승인 완료','CONSTRUCTION':'착공 완료','COMPLETION':'사용승인 완료','SUPPLY':'입주자 모집 공고','MOVE_IN':'입주 시작'}


def proposal(env,stage='CONSTRUCTION'):
 service,_,did,pid=env
 sentence=f'면목 주택은 2026년 10월 20일 {PHRASES[stage]}. 면목 주택 전체 100호.'
 with service.sessions.begin() as db:
  m=db.scalar(select(Mapping));m.status='CONFIRMED'
  doc=sr.current(db,'document_evidence',did)
  r,_=upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(doc.payload,text=sentence),'source')
  ref=sr.reference(r)
 p=dict(project_id=pid,project_name='면목 주택',stage=stage,url='https://www.seoul.go.kr/a',title='확인된 단계',source_ref=ref,
  identity_confirmed=True,human_hold=False,proposed=dict(event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT'),
  proof=dict(body=sentence,date_quote=sentence,units_quote=sentence,issues=[]))
 return p


def apply(service,row,**kw):
 return sr.decide(service,row['id'],row['revision_no'],row['project_revision_no'],row['profile_revision_no'],row['mapping_revision_no'],
  'APPLY','검증 담당자','공식 근거의 동일 사업 및 전체 누적 물량 확인',checked=True,**kw)

@pytest.mark.parametrize('stage',list(PHRASES))
def test_all_six_stages_replace_once_keep_goals_and_mapping(env,stage):
 service,_,_,pid=env;p=proposal(env,stage)
 with service.sessions.begin() as db:
  upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,goals={'SUPPLY':{'due_date':'2027-01-01'}},overrides={},progress={stage:dict(event_date='2026-01-01',units=100,inferred=True)}),'old')
 sr.propose(service,p);r=sr.list_items(service)[0]
 assert r['auto_eligible'] and r['delta_units']==0
 assert apply(service,r,automatic=True)['status']=='APPLIED'
 assert apply(service,r)['conflict']
 assert sr.propose(service,p)['unchanged']
 with service.sessions() as db:
  profile=sr.current(db,'project_profile',entity_id('project_profile','manual_project',pid)).payload
  assert profile['goals']['SUPPLY']['due_date']=='2027-01-01'
  assert profile['progress'][stage]['units']==100 and profile['progress'][stage]['event_date']=='2026-10-20'
  assert not profile['progress'][stage]['inferred']
  assert db.scalar(select(Mapping)).policy_id=='UNASSIGNED'

@pytest.mark.parametrize('change',['plan','future','invented_quote','people','partial','month','observation','human_hold','wrong_project_quote','different_quantity','missing_date'])
def test_unsafe_or_ambiguous_inputs_never_auto_apply(env,change):
 service,_,_,_=env;p=proposal(env)
 if change=='plan':p['proof']['date_quote']=p['proof']['body']=p['proof']['body'].replace('착공 완료','착공 예정')
 if change=='future':p['proposed']['event_date']='2099-01-01'
 if change=='invented_quote':p['proof']['date_quote']='공식 확인하였음'
 if change=='people':p['proof']['units_quote']=p['proof']['body']=p['proof']['body'].replace('100호','100명')
 if change=='partial':p['proposed']['scope']='PARTIAL'
 if change=='month':p['proposed'].update(event_date='2026-10',precision='MONTH')
 if change=='observation':p['proposed']['date_basis']='OBSERVED_BY'
 if change=='human_hold':p['human_hold']=True
 if change=='wrong_project_quote':p['project_name']='다른 사업'
 if change=='different_quantity':p['proposed']['units']=101
 if change=='missing_date':p['proposed']['event_date']=None
 sr.propose(service,p);r=sr.list_items(service)[0]
 assert not r['auto_eligible']
 with pytest.raises(ValueError):apply(service,r,automatic=True)
 assert not service.rows('project_profile')


def test_concurrent_source_change_blocks_approval_and_export_explains(env):
 service,store,did,_=env;p=proposal(env);sr.propose(service,p);r=sr.list_items(service)[0]
 with service.sessions.begin() as db:
  d=sr.current(db,'document_evidence',did);upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(d.payload,text='정정된 원문'),'changed')
 assert apply(service,r).get('conflict')
 assert sr.list_items(service)[0]['stale']
 text=export_csv(service,store,'all');assert '실적 반영' in text and '원문 또는 사업 판본 변경' in text
 assert len(list(csv.DictReader(io.StringIO(sr.export_csv(service).lstrip('\ufeff')))))==1


def test_read_only_lists_do_not_write_and_confirmed_value_needs_explicit_correction(env):
 service,_,_,pid=env;p=proposal(env)
 with service.sessions.begin() as db:
  upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,progress={'CONSTRUCTION':dict(event_date='2026-09-01',units=100,inferred=False)}),'old')
 sr.propose(service,p)
 with service.sessions() as db:before=db.scalar(select(func.count()).select_from(Revision))
 for _ in range(3):r=sr.list_items(service)[0]
 with service.sessions() as db:assert db.scalar(select(func.count()).select_from(Revision))==before
 assert not r['auto_eligible']
 with pytest.raises(ValueError,match='정정'):apply(service,r)
 assert apply(service,r,replace_confirmed=True)['status']=='APPLIED'


def test_observed_by_preserves_its_meaning_not_actual_start(env):
 service,_,_,pid=env;p=proposal(env);p['proposed']['date_basis']='OBSERVED_BY';sr.propose(service,p)
 apply(service,sr.list_items(service)[0])
 row=service.rows('project_profile')[0]['progress']['CONSTRUCTION']
 assert row['date_basis']=='OBSERVED_BY' and row['source_event_date'] is None and row['observed_on']=='2026-10-20'


def test_mapping_profile_and_project_changes_reject_stale_form(env):
 service,_,_,pid=env;p=proposal(env);sr.propose(service,p);r=sr.list_items(service)[0]
 with service.sessions.begin() as db:db.scalar(select(Mapping)).revision_no+=1
 assert apply(service,r)['conflict']
 r=sr.list_items(service)[0]
 with service.sessions.begin() as db:upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,progress={}),'change')
 assert apply(service,r)['conflict']
 r=sr.list_items(service)[0]
 with service.sessions.begin() as db:
  old=sr.current(db,'project',pid);upsert_revision(db,'project','test','p',dict(old.payload,name='다른 사업'),'change')
 assert sr.list_items(service)[0]['stale'] and apply(service,r)['conflict']


def test_approved_document_is_revisited_with_stage_evidence_without_overwriting_link(env,monkeypatch):
 monkeypatch.setenv('UPSTAGE_SECRET_KEY','offline-test')
 service,store,did,pid=env;run,result=seed_officer(service,store,did,pid,'CONSTRUCTION')
 save(service,did,1,0,'APPROVED','UNASSIGNED',[pid],[],'사람 담당자','공식 원문 사업 연결 확인',True)
 event=work.StageEvent(stage='CONSTRUCTION',event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT',date_quote='원문에 없는 착공일',units_quote='원문에 없는 물량',issues=[])
 result=work.StageDecision(**result.model_dump(),stage_events=[event]);result.stage_basis='ACTUAL'
 with patch.object(work,'invoke',return_value=(result,'test-call')):work.process(service,store,run)
 d=queue(service)['items'][0]
 assert d['status']=='APPROVED' and d['decision']['actor']=='사람 담당자'
 assert len(sr.list_items(service))==1 and not sr.list_items(service)[0]['auto_eligible']
 assert not service.rows('project_profile')


def test_api_auth_conflict_and_pending_csv(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 service,_,_,_=env;sr.propose(service,proposal(env));r=sr.list_items(service)[0]
 monkeypatch.setenv('POC10_INTERNAL_SECRET','test-secret');monkeypatch.setenv('POC10_DATA_DIR',str(service.data_dir))
 path='/poc/home/api/admin/stage-reviews/'+r['id'];stamp=str(int(time.time()))
 sig=hmac.new(b'test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
 payload={k:r[k] for k in ['revision_no','project_revision_no','profile_revision_no','mapping_revision_no']};payload.update(action='APPLY',actor='담당자',reason='검증 완료한 동일 사업 실적',checked=True)
 with TestClient(create_app(service.engine,auto_collect=False)) as c:
  assert c.get('/poc/home/api/stage-reviews').json()['pending']==1
  assert c.get('/poc/home/api/stage-reviews/export.csv').content.startswith(b'\xef\xbb\xbf')
  assert c.post(path,json=payload).status_code==401
  assert c.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code==200
  assert c.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code==409


def test_selected_permit_requires_current_source_and_refresh_is_idempotent(env):
 service,_,did,pid=env
 p=proposal(env,'APPROVAL')
 with service.sessions.begin() as db:
  doc=sr.current(db,'document_evidence',did)
  upsert_revision(db,'stage_evidence','stage_match',pid+':APPROVAL',dict(project_id=pid,stage='APPROVAL',status='REVIEW',
   selected=dict(source_entity_id=did,source_revision_no=doc.revision_no,event_date='2026-10-20',units=100,evidence_url=p['url'],method='OFFICIAL_DOCUMENT')),'match')
 first=sr.refresh(service);second=sr.refresh(service)
 assert first['proposals_changed']==1 and second['proposals_changed']==0
 row=sr.list_items(service)[0];assert row['stage']=='APPROVAL' and row['status']=='HOLD'
 with service.sessions.begin() as db:
  doc=sr.current(db,'document_evidence',did);upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(doc.payload,text='원문 정정'),'changed')
 sr.refresh(service);row=sr.list_items(service)[0]
 assert row['invalid_source'] and not row['can_apply']


def test_recent_progress_is_observation_and_partial_supply_is_not_added(env):
 service,_,_,pid=env
 with service.sessions.begin() as db:
  upsert_revision(db,'project_profile','manual_project',pid,dict(project_id=pid,base_date='2026-10-22',progress={'CONSTRUCTION':dict(units=100,event_date='2026-06-30',inferred=True)}),'old')
  upsert_revision(db,'evidence_bridge','cross_source','progress',dict(project_id=pid,name='면목',status='REVIEW',relation_type='SAME_SCOPE',units=100,evidence_url='https://www.lh.or.kr/a',facts=[dict(stage='CONSTRUCTION',kind='ACTUAL',date='2026-10-30',pct=1.7),dict(stage='SUPPLY',kind='ACTUAL',date='2026-10-30',units=10,scope_partial=True)]),'new')
 sr.refresh(service,auto_apply=True);row=sr.list_items(service)[0]
 assert len(sr.list_items(service))==1 and row['stage']=='CONSTRUCTION' and row['delta_units']==0
 assert row['proposed']['date_basis']=='OBSERVED_BY' and not row['auto_eligible']
 assert service.rows('project_profile')[0]['progress']['CONSTRUCTION']['inferred']


def test_unchanged_approved_input_does_not_spend_another_model_call(env,monkeypatch):
 monkeypatch.setenv('UPSTAGE_SECRET_KEY','offline-test')
 service,store,did,pid=env;run,result=seed_officer(service,store,did,pid)
 with patch.object(work,'invoke',return_value=(result,'test-call')):work.process(service,store,run)
 run=start(store,'officer')
 with patch.object(work,'invoke') as model:work.process(service,store,run)
 assert not model.called
