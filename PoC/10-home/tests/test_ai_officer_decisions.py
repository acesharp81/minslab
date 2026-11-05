"""Delegated business outcomes, not just model output or a completed progress bar."""
from unittest.mock import patch
import pytest
from sqlalchemy import select
from test_ai_agents import env,keys,seed_officer
from test_ai_collection import isolate_shared_budget
from backend.ai_officer_decisions import apply,preflight,normalize_result,Pending,Check,Decision,ACTOR
from backend import ai_agent_workflows as work,ai_agents_store as agents
from backend.ai_collection import annotations
from backend.publication_reviews import queue,save
from backend.db import Revision,Mapping,upsert_revision

def officer_response(result,cid='offline'):
 def respond(*args,**kwargs):
  return (Check(accept=True,reason='독립 검증 자료와 동일 사업·범위·인용을 확인했습니다',issues=[]),cid+'-check') if kwargs.get('schema')==Check else (result,cid)
 return respond

def setup(env):
 service,store,did,pid=env;run,result=seed_officer(service,store,did,pid)
 doc=queue(service)['items'][0];a=annotations(service,[did])[did];body=a['body_text']
 with service.sessions() as db:projects=[dict(r.payload,id=r.entity_id,revision_no=r.revision_no) for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))]
 return service,store,doc,a,body,projects,normalize_result(result,doc),run

def set_body(service,did,body):
 with service.sessions.begin() as db:
  a=db.scalar(select(Revision).where(Revision.kind=='ai_publication_analysis',Revision.superseded_at.is_(None)))
  a.payload=dict(a.payload,body_text=body)
 return annotations(service,[did])[did]

@pytest.mark.parametrize('old_status',['HOLD','REGISTRATION_REQUIRED'])
def test_delegated_officer_finishes_prior_human_wait_without_requesting_approval(env,old_status):
 s,store,d,a,body,projects,value,run=setup(env)
 save(s,d['id'],1,0,old_status,'UNASSIGNED',[],['서울 면목 행복주택'] if old_status=='REGISTRATION_REQUIRED' else [],'김민','당시 근거 보완 대기',True)
 d=queue(s)['items'][0]
 updated,effects=apply(s,d,body,a,value,projects,[])
 assert updated['status']=='APPROVED' and updated['decision']['actor']==ACTOR
 assert effects[0]['kind']=='DOCUMENT' and effects[0]['verdict']=='YES'
 with s.sessions() as db:assert db.scalar(select(Mapping)).policy_id=='UNASSIGNED'


def test_plan_reference_yes_completes_without_inventing_actual_stage(env):
 s,store,d,a,body,projects,value,run=setup(env)
 with patch.object(work,'invoke',side_effect=officer_response(Decision.model_validate(value))):work.process(s,store,run)
 r=agents.latest(store,'officer')[d['id']]
 assert r['verdict']=='YES' and r['state']=='DONE' and r['effects'][0]['status']=='APPROVED'
 with s.sessions() as db:assert db.scalar(select(Revision).where(Revision.kind=='project_profile')) is None


def test_no_is_saved_not_just_exclusion_advice(env):
 s,store,d,a,body,projects,v,run=setup(env)
 v.update(verdict='NO',project_ids=[],no_basis='NOT_PROJECT_DATA',reason='교육 홍보 내용으로 개별 주택공급 사업 자료가 아닙니다')
 updated,effects=apply(s,d,body,a,v,projects,[])
 assert updated['status']=='EXCLUDED' and effects[0]['verdict']=='NO'


def registration_value(v):
 name='서울 청량리 신규주택';address='서울특별시 동대문구 청량리동 999'
 quote=f'{name} 사업은 {address}에 위치하며 전체 120세대를 건설할 계획입니다.'
 p=dict(key='NEW1',name=name,address=address,region='서울특별시',developer='',official_id='',planned_units=120,identity_quote=quote,units_quote=quote)
 return dict(v,evidence=[quote],project_ids=[],new_projects=[p]),quote


def test_registration_yes_creates_project_and_document_link_atomically(env):
 s,store,d,a,body,projects,v,run=setup(env);v,body=registration_value(v);a=set_body(s,d['id'],body)
 updated,effects=apply(s,d,body,a,v,projects,[])
 assert updated['status']=='APPROVED' and any(e['kind']=='REGISTER' and e['created'] for e in effects)
 with s.sessions() as db:
  p=db.scalar(select(Revision).where(Revision.kind=='project',Revision.source_id=='ai_officer_registry',Revision.superseded_at.is_(None)))
  assert p.payload['planned_units']==120 and p.payload['policy_candidate_only']
  assert db.scalar(select(Mapping).where(Mapping.project_id==p.entity_id)).policy_id=='UNASSIGNED'
 assert any(p['name']=='서울 청량리 신규주택' for p in s.rows('project'))


def test_duplicate_registration_is_held_without_side_effects(env):
 s,store,d,a,body,projects,v,run=setup(env);v,body=registration_value(v)
 v['new_projects'][0]['name']=projects[0]['name'];a=set_body(s,d['id'],body)
 with pytest.raises(Pending):apply(s,d,body,a,v,projects,[])
 assert queue(s)['items'][0]['status']=='REVIEW'


def test_registration_rolls_back_if_requested_stage_cannot_be_applied(env):
 s,store,d,a,body,projects,v,run=setup(env);v,body=registration_value(v)
 q='서울 청량리 신규주택은 2099년 1월 1일 착공했습니다. 서울 청량리 신규주택 전체 120세대입니다.'
 body+=q;a=set_body(s,d['id'],body)
 v['stage_events']=[dict(project_key='NEW1',stage='CONSTRUCTION',event_date='2099-01-01',units=120,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT',date_quote=q,units_quote=q,issues=[])]
 with pytest.raises(ValueError):apply(s,d,body,a,v,projects,[])
 with s.sessions() as db:
  assert db.scalar(select(Revision).where(Revision.source_id=='ai_officer_registry')) is None
  assert db.scalar(select(Revision).where(Revision.kind=='publication_review')) is None
  assert len(list(db.scalars(select(Mapping))))==1


def test_actual_fact_can_be_recorded_before_policy_membership(env):
 s,store,d,a,body,projects,v,run=setup(env);pid=projects[0]['id']
 q='서울 면목 행복주택은 2026년 10월 20일 착공했습니다. 서울 면목 행복주택 전체 100세대입니다.'
 body+=q;a=set_body(s,d['id'],body)
 v['stage_events']=[dict(project_key=pid,stage='CONSTRUCTION',event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT',date_quote=q,units_quote=q,issues=[])]
 updated,effects=apply(s,d,body,a,v,projects,[])
 assert any(e['kind']=='STAGE' for e in effects)
 with s.sessions() as db:
  profile=db.scalar(select(Revision).where(Revision.kind=='project_profile',Revision.superseded_at.is_(None)))
  assert profile.payload['progress']['CONSTRUCTION']['units']==100
  assert db.scalar(select(Mapping)).policy_id=='UNASSIGNED'


def test_concurrent_review_change_never_overwritten(env):
 s,store,d,a,body,projects,v,run=setup(env)
 save(s,d['id'],1,0,'HOLD','UNASSIGNED',[],[],'새 담당자','분석 중 새 판단 추가',False)
 with pytest.raises(Pending,match='변경'):apply(s,d,body,a,v,projects,[])
 assert queue(s)['items'][0]['decision']['actor']=='새 담당자'


def test_policy_link_requires_individual_policy_quote_and_is_saved(env):
 s,store,d,a,body,projects,v,run=setup(env);pid=projects[0]['id'];policy=dict(policy_id='POL_TEST',name='검증 주택공급 방안',monitor_kind='POLICY')
 q='서울 면목 행복주택은 검증 주택공급 방안의 추진 대상에 포함되었습니다.';body+=q;a=set_body(s,d['id'],body)
 v['policy_links']=[dict(project_key=pid,policy_id='POL_TEST',quote=q)]
 with patch.object(s,'mapping_policies',return_value=[policy]):
  updated,effects=apply(s,d,body,a,v,projects,[policy])
 assert any(e['kind']=='POLICY' for e in effects)
 with s.sessions() as db:assert db.scalar(select(Mapping)).policy_id=='POL_TEST'
 v['policy_links'][0]['quote']='공급 확대 방안입니다'
 with pytest.raises(Pending):preflight(v,d,body,projects,[policy])


def test_hold_contains_specific_retrieval_and_retry_conditions(env):
 s,store,d,a,body,projects,v,run=setup(env)
 v.update(verdict='HOLD',missing_evidence=[dict(field='주소',needed='해당 단지 지번 주소',source='공식 입주자 모집공고 첨부',retry_when='지번을 포함한 첨부가 수집되면')])
 with patch.object(work,'invoke',side_effect=officer_response(Decision.model_validate(v))):work.process(s,store,run)
 r=agents.latest(store,'officer')[d['id']]
 assert r['verdict']=='HOLD' and r['missing_evidence'][0]['field']=='주소' and r['retry_after']
 assert queue(s)['items'][0]['status']=='HOLD'

def test_official_corroboration_closes_unofficial_hold_and_pins_both_documents(env):
 from backend.ai_officer_decisions import execute
 s,store,d,a,body,projects,v,run=setup(env)
 with s.sessions.begin() as db:
  row=db.scalar(select(Revision).where(Revision.entity_id==d['id'],Revision.superseded_at.is_(None)))
  row.payload=dict(row.payload,evidence_url='https://example.com/news')
  other,_=upsert_revision(db,'document_evidence','seoul_press_watch','official-corroboration',dict(name='서울 면목 행복주택 공식 안내',evidence_url='https://www.seoul.go.kr/official',text=body*5,source_date='2026-11-05',facts=[],units=None),'seed');oid=other.entity_id;source=dict(other.payload)
 docs={x['id']:x for x in queue(s)['items']};d=docs[d['id']];v['evidence_document_id']=oid
 updated,out=execute(s,store,run,d,body,a,projects,projects,officer_response(Decision.model_validate(v)),docs,annotations(s,list(docs)),{}, {oid:source})
 assert out['verdict']=='YES' and updated['id']==d['id']
 assert all(x['status']=='APPROVED' for x in queue(s)['items'])
 assert len([x for x in out['effects'] if x['kind']=='DOCUMENT'])==2


def test_unverified_yes_or_no_never_executes(env):
 from backend.ai_officer_decisions import execute
 s,store,d,a,body,projects,v,run=setup(env)
 def reject(*args,**kw):
  if kw['schema']==Check:return Check(accept=False,reason='원문과 연결 범위가 일치하지 않습니다',issues=['다른 사업 범위']), 'check'
  return Decision.model_validate(v),'decision'
 updated,out=execute(s,store,run,d,body,a,projects,projects,reject)
 assert out['verdict']=='HOLD' and not out['effects'] and queue(s)['items'][0]['status']=='REVIEW'

def test_officer_evidence_search_keeps_old_and_undated_sources_without_weakening_daily_collector():
 from backend.ai_collection import search_rows
 rss=b'<rss><channel><item><title>old</title><link>https://www.seoul.go.kr/old</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item><item><title>undated</title><link>https://www.lh.or.kr/undated</link></item></channel></rss>'
 assert search_rows(rss)==[]
 rows=search_rows(rss,max_age_days=None,allow_undated=True)
 assert len(rows)==2 and rows[0]['source_date']=='2024-01-01' and rows[1]['source_date'] is None


def test_three_verdict_csv_contains_effects_and_missing_evidence(env):
 import csv,io,json
 from backend.ai_agents_inbox import export_csv
 s,store,_,_=env
 rows=[dict(role='officer',subject='DOC_'+v,state='HOLD' if v=='HOLD' else 'DONE',verdict=v,title=v,result={},effects=[dict(kind='DOCUMENT',verdict=v)] if v!='HOLD' else [],missing_evidence=[dict(field='주소',needed='공식 지번',source='공식 공고',retry_when='공고 확보 시')] if v=='HOLD' else []) for v in ('YES','NO','HOLD')]
 with patch('backend.ai_agents_inbox.items',return_value=rows):
  all_rows=list(csv.DictReader(io.StringIO(export_csv(s,store,'officer',verdict='ALL').lstrip('\ufeff'))))
  assert len(all_rows)==3 and '판단사유' in all_rows[0]
  assert {json.loads(r['분석결과_JSON'])['verdict'] for r in all_rows}=={'YES','NO','HOLD'}
  assert json.loads(all_rows[0]['분석결과_JSON'])['effects'][0]['kind']=='DOCUMENT'
  assert json.loads(all_rows[2]['분석결과_JSON'])['missing_evidence'][0]['source']=='공식 공고'
  assert len(list(csv.DictReader(io.StringIO(export_csv(s,store,'officer',verdict='YES').lstrip('\ufeff')))))==1
  assert len(list(csv.DictReader(io.StringIO(export_csv(s,store,'officer').lstrip('\ufeff')))))==1


def test_invalid_quote_gets_one_repair_then_independent_check(env):
 from backend.ai_officer_decisions import execute
 s,store,d,a,body,projects,v,run=setup(env)
 bad=dict(v,evidence=['원문에 없는 요약'])
 responses=iter([(Decision.model_validate(bad),'first'),(Decision.model_validate(v),'repair'),(Check(accept=True,reason='원문 인용과 사업 동일성을 확인했습니다',issues=[]),'check')])
 with patch.object(work,'invoke',side_effect=lambda *args,**kw:next(responses)) as invoke:
  updated,out=execute(s,store,run,d,body,a,projects,projects,invoke)
 assert out['verdict']=='YES' and updated['status']=='APPROVED' and len(out['passes'])==3
 assert out['passes'][1]['validation_error']=='최종 판단을 뒷받침하는 정확한 원문 인용 필요'


def test_repeat_invalid_quotes_never_bypass_gate_or_loop(env):
 from backend.ai_officer_decisions import execute
 s,store,d,a,body,projects,v,run=setup(env);v['evidence']=['원문에 없는 요약']
 with patch.object(work,'invoke',return_value=(Decision.model_validate(v),'invalid')) as invoke:
  updated,out=execute(s,store,run,d,body,a,projects,projects,invoke)
 assert invoke.call_count==2 and out['verdict']=='HOLD' and out['evidence']==[] and not out['effects']
 assert queue(s)['items'][0]['status']=='REVIEW'


def test_pdf_whitespace_is_restored_to_exact_source_without_altering_numbers(env):
 from backend.ai_officer_decisions import restore_quotes
 s,store,d,a,body,projects,v,run=setup(env)
 v['evidence']=['주택 총 100호 공급', '주택 총 101호 공급']
 restored,changes=restore_quotes(v,'주택총100호\n공급')
 assert restored['evidence']==['주택총100호\n공급','주택 총 101호 공급']
 assert len(changes)==1 and changes[0]['method']=='WHITESPACE_ONLY'


def test_district_and_short_block_are_exact_identifiers_not_similar_numbers():
 from backend.ai_officer_decisions import identity
 p=dict(id='PRO_TEST',name='시흥거모 S1',block='S1')
 d=dict(authority='OFFICIAL',status='HOLD')
 assert identity(p,'시흥거모 공공주택지구 공공분양 S-1블록 300호 모집',d)
 assert not identity(p,'시흥거모 S-10블록 300호 모집',d)
 assert not identity(p,'시흥거모의 지구 개발. 다른 지구인 고양창릉 S-1블록',d)
 assert not identity(p,'고양창릉 S-1블록 300호 모집',d)


def test_contradictory_check_reasks_once_without_ignoring_issues(env):
 from backend.ai_officer_decisions import execute
 s,store,d,a,body,projects,v,run=setup(env)
 for accepted in (False,True):
  responses=iter([(Decision.model_validate(v),'first'),(Check(accept=True,reason='인용 및 동일 사업을 확인했습니다',issues=['주의: 계획 자료이므로 실적 가산 없음']),'contradiction'),(Check(accept=accepted,reason='제안 작업을 원문과 다시 대조했습니다',issues=[] if accepted else ['실제 동일성 미확인']),'clarified')])
  updated,out=execute(s,store,run,d,body,a,projects,projects,lambda *args,**kw:next(responses))
  assert out['verdict']==('YES' if accepted else 'HOLD') and len(out['passes'])==3
