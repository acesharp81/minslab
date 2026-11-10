"""Fixed failure cases from the Nov 9 run; no provider calls or business-data mutation."""
import json
from unittest.mock import patch
import pytest
from pydantic import ValidationError
from sqlalchemy import select
from test_ai_agents import env,keys,seed_officer
from test_ai_collection import isolate_shared_budget,run_for
from test_ai_officer_decisions import setup,officer_response
from backend import ai_officer_decisions as dec,ai_agent_workflows as work,ai_agents_store as agents
from backend.ai_collection import search_rows
from backend.ai_collection_models import ModelResponseError
from backend.ai_officer_review import official_search,relevant_search_result,publisher_fallback
from backend.publication_reviews import queue
from backend.db import Revision,upsert_revision
from backend import stage_reconciliation as sr,officer_stage_work as stage_work,officer_campaign as campaign


def rss(date='수, 04 11월 2026 23:19:00 GMT',title='면목 행복주택 착공 공고'):
 return f'<rss><channel><item><title>{title}</title><link>https://www.seoul.go.kr/notice/view.do?id=123</link><pubDate>{date}</pubDate></item></channel></rss>'.encode()


def test_korean_rss_date_is_not_silently_dropped():
 stats={};rows=search_rows(rss(),max_age_days=None,allow_undated=True,diagnostics=stats)
 assert len(rows)==1 and rows[0]['source_date']=='2026-11-04'
 assert stats['raw_items']==stats['parsed_rows']==1 and stats['invalid_date']==0


def test_unrecognized_rss_date_is_failure_not_empty_success():
 stats={}
 with pytest.raises(ValueError,match='날짜 해석 실패'):search_rows(rss('unknown-date'),max_age_days=None,allow_undated=True,diagnostics=stats)
 assert stats['invalid_date']==1


def test_search_accepts_detail_but_rejects_homepage_and_portal(env):
 service,store,did,_=env;run=run_for(store)
 with patch('backend.ai_collection_fetch.Fetcher.get',return_value=rss()),patch('backend.ai_officer_evidence.recover',return_value={}):
  rows=official_search(service,store,run,dict(id=did,title='면목 행복주택 착공 공고'))
 assert len(rows)==1 and rows[0]['body_recovered']
 assert not relevant_search_result(dict(name='면목 행복주택 안내',evidence_url='https://www.seoul.go.kr/main/index.jsp'),dict(title='면목 행복주택'))
 assert not relevant_search_result(dict(name='전세임대포털',evidence_url='https://jeonse.lh.or.kr/view.do'),dict(title='면목 전세임대 주택'))


def test_search_failure_is_logged_and_not_disguised_as_no_candidates(env):
 service,store,did,_=env;run=run_for(store)
 with patch('backend.ai_collection_fetch.Fetcher.get',return_value=rss('unknown-date')),patch('backend.ai_officer_review.publisher_fallback',return_value=([],[])):
  with pytest.raises(ValueError,match='검색 실패'):official_search(service,store,run,dict(id=did,title='면목 행복주택 착공'))
 event=next(e for e in store.status()['runs'][0]['events'] if e['kind']=='OFFICER_SEARCH')
 assert event['outcome']=='SEARCH_ERROR' and len(event['attempts'])==3


def test_official_publisher_fallback_is_bounded_and_cached():
 from types import SimpleNamespace
 row=dict(name='면목 행복주택 착공 공고',evidence_url='https://www.seoul.go.kr/view.do?id=123')
 run={};fetcher=SimpleNamespace(last={'sha256':'fixed'})
 with patch('backend.publication_watch.collect',return_value=([('document_evidence','123',row)],{'provided':1})) as collect:
  rows,attempts=publisher_fallback(fetcher,run,dict(title='면목 행복주택 착공'),lambda:True)
  repeated,again=publisher_fallback(fetcher,run,dict(title='면목 행복주택 착공'),lambda:True)
 assert rows==repeated==[row] and collect.call_count==1 and again[0]['cached']
 assert len(collect.call_args.args[0]['feed_urls'])==1


def test_source_and_project_ids_are_schema_choices(env):
 s,store,d,a,body,projects,v,run=setup(env);schema=dec.decision_schema([d['id']],[p['id'] for p in projects])
 assert schema.model_validate(v).evidence_document_id==d['id']
 with pytest.raises(ValidationError):schema.model_validate(dict(v,evidence_document_id=d['evidence_url']))
 with pytest.raises(ValidationError):schema.model_validate(dict(v,project_ids=['NEW_001']))


def test_unnecessary_hold_is_reviewed_and_core_link_completed(env):
 s,store,d,a,body,projects,v,run=setup(env)
 held=dict(v,verdict='HOLD',project_ids=[],missing_evidence=[dec.pending('실적 호수 없음')],reason='실적 호수가 없어 동일 사업 연결도 보류합니다')
 responses=iter([(dec.Decision.model_validate(held),'first'),(dec.Check(accept=False,reason='실적과 별개로 사업명·주소가 일치하여 자료 연결 가능',issues=['연결과 실적 혼동']),'audit'),(dec.Decision.model_validate(v),'fixed'),(dec.Check(accept=True,reason='원문에 사업명과 주소가 직접 존재합니다',issues=[]),'check')])
 _,result=dec.execute(s,store,run,d,body,a,projects,projects,lambda *a,**kw:next(responses))
 assert result['verdict']=='YES' and queue(s)['items'][0]['status']=='APPROVED'
 assert any('보류 필요성' in x['task'] for x in result['passes'])


def test_bad_optional_event_cannot_erase_valid_document_link(env):
 s,store,d,a,body,projects,v,run=setup(env)
 event=dict(project_key=projects[0]['id'],stage='CONSTRUCTION',event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT',date_quote='원문에 없는 착공일',units_quote='원문에 없는 물량',issues=[])
 value=dec.Decision.model_validate(dict(v,stage_events=[event]))
 _,result=dec.execute(s,store,run,d,body,a,projects,projects,officer_response(value))
 assert result['verdict']=='YES' and queue(s)['items'][0]['status']=='APPROVED'
 assert result['deferred_actions'][0]['kind']=='STAGE' and result['deferred_actions'][0]['status']=='HOLD'
 assert not s.rows('project_profile')


def test_optional_model_failure_keeps_core_effect_but_reports_error(env):
 s,store,d,a,body,projects,v,run=setup(env)
 # A failure during the core review is an execution error, never a HOLD.
 responses=iter([(dec.Decision.model_validate(v),'first')])
 def respond(*args,**kw):
  if kw['schema']==dec.Check:raise ModelResponseError('SCHEMA · invalid')
  return next(responses)
 with pytest.raises(ModelResponseError):dec.execute(s,store,run,d,body,a,projects,projects,respond)
 assert queue(s)['items'][0]['status']!='APPROVED'


@pytest.mark.parametrize('failure',[InterruptedError,ModelResponseError])
def test_optional_interruption_preserves_committed_link_and_retry_work(env,failure):
 s,store,d,a,body,projects,v,run=setup(env)
 event=dict(project_key=projects[0]['id'],stage='CONSTRUCTION',event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT',date_quote=body,units_quote=body,issues=[])
 value=dec.Decision.model_validate(dict(v,stage_events=[event]));checks=0
 def respond(*args,**kw):
  nonlocal checks
  if kw['schema']==dec.Check:
   checks+=1
   if checks==2:raise failure('test interruption')
   return dec.Check(accept=True,reason='자료 연결 근거 확인',issues=[]),'check'
  return value,'decision'
 if failure is InterruptedError:
  with pytest.raises(InterruptedError):dec.execute(s,store,run,d,body,a,projects,projects,respond)
  result=agents.latest(store,'officer')[d['id']]
 else:
  _,result=dec.execute(s,store,run,d,body,a,projects,projects,respond)
 assert queue(s)['items'][0]['status']=='APPROVED'
 assert result['verdict']=='YES' and result['deferred_actions'][0]['status']=='ERROR'
 assert not s.rows('project_profile')


def prepare_stage(env,planned=False):
 s,store,did,pid=env;run,_=seed_officer(s,store,did,pid)
 sentence='서울 면목 행복주택은 서울 면목동 123에 위치하며 2026년 10월 20일 착공 '+('예정' if planned else '완료')+'. 서울 면목 행복주택 전체 100호.'
 with s.sessions.begin() as db:
  d=sr.current(db,'document_evidence',did)
  source,_=upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(d.payload,text=sentence),'fixed-case')
  pr=sr.current(db,'project',pid);project=dict(pr.payload,id=pid,revision_no=pr.revision_no)
 payload=dict(project_id=pid,project_name=project['name'],stage='CONSTRUCTION',url='https://www.seoul.go.kr/a',title='면목 행복주택 착공',document_id=did,
  source_ref=sr.reference(source),identity_confirmed=True,human_hold=True,proposed=dict(event_date='2026-10-20',units=100,date_basis='EVENT',precision='DAY',scope='WHOLE_PROJECT'),proof=dict(body='',date_quote='',units_quote='',issues=[]))
 sid=sr.propose(s,payload)['id'];doc=queue(s)['items'][0]
 evidence=[dict(doc=doc,body=sentence,analysis=dict(body_origin='SOURCE',source_revision_no=doc['source_revision_no']))]
 event=dec.Event(project_key=pid,stage='CONSTRUCTION',**payload['proposed'],date_quote=sentence,units_quote=sentence,issues=[])
 return s,store,run,sid,doc,evidence,event


def test_stage_candidate_is_researched_and_actual_profile_written(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 answer=stage_work.Research(verdict='YES',evidence_document_id=doc['id'],reason='공식 원문에서 동일 사업의 실제 착공일과 전체 물량 확인',evidence_quote=evidence[0]['body'],event=event,missing_evidence=[])
 with patch.object(stage_work,'inputs',return_value=(evidence,[])):
  result=stage_work.research(s,store,run,sid,officer_response(answer))
 assert result['verdict']=='YES' and result['researched']
 assert s.rows('project_profile')[0]['progress']['CONSTRUCTION']['units']==100


def test_stage_plan_never_becomes_actual_even_if_model_says_yes(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env,planned=True)
 answer=stage_work.Research(verdict='YES',evidence_document_id=doc['id'],reason='모델의 잘못된 실제 착공 판단입니다',evidence_quote=evidence[0]['body'],event=event,missing_evidence=[])
 with patch.object(stage_work,'inputs',return_value=(evidence,[])):
  with pytest.raises(dec.Pending,match='계획'):stage_work.research(s,store,run,sid,officer_response(answer))
 assert not s.rows('project_profile')


def test_stage_no_requires_original_source_and_records_dismissal(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env,planned=True)
 answer=stage_work.Research(verdict='NO',evidence_document_id=doc['id'],reason='기존 원문 자체가 착공 예정이며 실제 착공 제안은 제외',evidence_quote=evidence[0]['body'],event=None,missing_evidence=[])
 with patch.object(stage_work,'inputs',return_value=(evidence,[])):result=stage_work.research(s,store,run,sid,officer_response(answer))
 assert result['verdict']=='NO' and sr.list_items(s)[0]['status']=='DISMISSED'
 assert not s.rows('project_profile')


def test_stage_hold_requires_research_not_just_old_rule_flags(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 row=sr.list_items(s)[0]
 assert campaign.verify_stage_record(s,row,None)['verdict']=='ERROR'
 with patch.object(stage_work,'inputs',return_value=([],[])):result=stage_work.research(s,store,run,sid,lambda *a,**kw:pytest.fail('no source: no fabricated model input'))
 assert campaign.verify_stage_record(s,row,result)['verdict']=='HOLD'


@pytest.mark.parametrize('recover_body',[False,True])
def test_stage_reuses_existing_official_document_outside_discovery_inbox(env,recover_body):
 from backend.publication_supplements import save as supplement
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 body=evidence[0]['body'];run['config']['search_enabled']=False
 with s.sessions.begin() as db:
  source=sr.current(db,'document_evidence',doc['id']);source.source_id='official_document'
  if recover_body:source.payload=dict(source.payload,text='')
 assert doc['id'] not in [d['id'] for d in queue(s)['items']]
 def recover(service,d,**kw):
  assert kw['allow_existing']
  return supplement(service,d['id'],d['source_revision_no'],body,'기존 공식 원문 복구',[],'시험','a'*64,allow_existing=True)
 answer=stage_work.Research(verdict='YES',evidence_document_id=doc['id'],reason='기존 공식 자료의 동일 사업 착공 근거 확인',evidence_quote=body,event=event,missing_evidence=[])
 with patch('backend.ai_officer_evidence.recover',side_effect=recover):
  result=stage_work.research(s,store,run,sid,officer_response(answer))
 assert result['verdict']=='YES',result
 assert s.rows('project_profile')[0]['progress']['CONSTRUCTION']['units']==100
 with s.sessions() as db:
  assert len(list(db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.superseded_at.is_(None)))))==1
 assert doc['id'] not in [d['id'] for d in queue(s)['items']]

@pytest.mark.parametrize('fault',['project','stage','quote','missing_event','schema'])
def test_stage_repairs_invalid_response_before_independent_check_or_write(env,fault):
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 good=stage_work.Research(verdict='YES',evidence_document_id=doc['id'],reason='공식 원문의 동일 사업 실제 착공 근거 확인',evidence_quote=evidence[0]['body'],event=event,missing_evidence=[])
 bad=good.model_copy(deep=True)
 if fault=='project':bad.event.project_key='wrong-project'
 if fault=='stage':bad.event.stage='SUPPLY'
 if fault=='quote':bad.evidence_quote='원문에 없는 임의의 요약 문장'
 if fault=='missing_event':bad.event=None
 requests=[]
 def respond(*args,**kw):
  if kw['schema']==dec.Check:return dec.Check(accept=True,reason='원문 대조 완료',issues=[]),'check'
  requests.append(args[5])
  assert not s.rows('project_profile')
  if len(requests)==1:
   if fault=='schema':raise ModelResponseError('SCHEMA')
   return bad,'bad'
  assert args[5]['validation_error']
  assert kw['output_tokens']==5000
  return kw['schema'].model_validate_json(good.model_dump_json()),'fixed'
 with patch.object(stage_work,'inputs',return_value=(evidence,[])):
  result=stage_work.research(s,store,run,sid,respond)
 assert result['verdict']=='YES' and len(requests)==2
 assert s.rows('project_profile')[0]['progress']['CONSTRUCTION']['units']==100


def test_stage_correction_is_bounded_and_never_marks_invalid_quote_as_hold(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 bad=stage_work.Research(verdict='YES',evidence_document_id=doc['id'],reason='잘못된 응답 테스트',evidence_quote='없는 인용',event=event,missing_evidence=[])
 calls=[]
 def respond(*a,**kw):calls.append(1);return bad,'invalid'
 with patch.object(stage_work,'inputs',return_value=(evidence,[])),pytest.raises(ValueError,match='보정 3회 실패') as error:
  stage_work.research(s,store,run,sid,respond)
 assert len(calls)==3 and not s.rows('project_profile')
 assert len([p for p in error.value.diagnostics['passes'] if p['task']=='코드 검증·재작성'])==3


def test_empty_hold_is_corrected_with_specific_missing_evidence(env):
 s,store,run,sid,doc,evidence,event=prepare_stage(env)
 bad=stage_work.Research(verdict='HOLD',evidence_document_id=doc['id'],reason='현재 근거로는 판단하기 어렵습니다',evidence_quote='',event=None,missing_evidence=[])
 good=bad.model_copy(update={'missing_evidence':[dec.Missing(field='units',needed='사업 전체 누적 실적 물량',source='공식 착공 확인 자료',retry_when='전체 누적 물량 확인 시 재판단')]})
 calls=[]
 def respond(*a,**kw):
  if kw['schema']==dec.Check:return dec.Check(accept=True,reason='자료 확보 전 보류 타당',issues=[]),'check'
  if kw['schema']==stage_work.HoldRequirements:
   calls.append(1);return stage_work.HoldRequirements(missing_evidence=good.missing_evidence),'requirements'
  calls.append(1);return bad,'result'
 with patch.object(stage_work,'inputs',return_value=(evidence,[])):result=stage_work.research(s,store,run,sid,respond)
 assert len(calls)==2 and result['verdict']=='HOLD' and result['missing_evidence'] and not s.rows('project_profile')


def test_quote_options_are_exact_bounded_source_windows():
 body='사업 안내 '*100+'서울 면목 행복주택 2026년 착공 전체 100호 '+ '공식 원문 '*500
 rows=[dict(doc={'id':'d1'},body=body),dict(doc={'id':'d2'},body='다른 사업 안내')]
 options=stage_work.quote_options(rows,dict(name='서울 면목 행복주택'))
 assert len(options)<=20
 originals={r['doc']['id']:r['body'] for r in rows}
 assert all(x['quote'] in originals[x['document_id']] for x in options)
 assert any('전체 100호' in x['quote'] for x in options)
