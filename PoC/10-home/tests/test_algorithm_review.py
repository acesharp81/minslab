"""Independent HTML fixtures exercise human decisions and production extraction."""
import hashlib,hmac,time,json
from unittest.mock import patch
import pytest
from sqlalchemy import select
from test_ai_collection import env,run_for
from test_ai_agents import config,start
from backend import algorithm_review as ar,ai_agents_store as agents,ai_agents_inbox as inbox,ai_agent_workflows as work
from backend.db import Revision,upsert_revision
from backend.publication_reviews import save,queue

QUOTE='면목 주택의 총 공급 호수는 100호이며 공고 본문의 상세 일정을 확인합니다.'
BODY=QUOTE+' 신청 자격과 제출 서류, 사업 위치 및 공급 범위는 원문에 기재된 기준을 따릅니다.'
RAW=('<html><title>주택 모집</title><article>'+('관련 뉴스와 공통 안내입니다. '*8)+'</article><div id="notice">'+BODY+'</div></html>').encode()


def seed(env,state='HOLD',kind='BODY_SELECTOR'):
 service,store,did,pid=env
 agents.record(store,'algorithm',did,'input-fingerprint','test-run',state,title='면목 주택 공고',url='https://www.seoul.go.kr/a',source_revision_no=1,
  stage='DIAGNOSED' if state=='DONE' else 'RULE_VALIDATION_REQUIRED',reason='본문이 다른 영역에서 추출됨',body_text=BODY,result=dict(change_type=kind,selector='#notice',diagnosis='본문 영역 변경',reason='별도 공고 영역이 존재',regression_cases=['과거 본문 보존']))
 return ar.detail(service,store,did)

class Fetch:
 def __init__(self,store):self.store=store;self.last={}
 def get(self,url):
  sha=hashlib.sha256(RAW).hexdigest();folder=self.store.path.parent.parent/'raw'/'ai_publication';folder.mkdir(parents=True,exist_ok=True);(folder/(sha+'.raw')).write_bytes(RAW)
  self.last=dict(url=url,sha256=sha);return RAW


def validate(env,detail,scope='URL'):
 service,store,did,_=env
 return ar.validate(service,store,did,detail['result_id'],'#notice',scope,QUOTE,Fetch(store))


def decide(env,d,action,**kw):
 service,store,did,_=env
 return ar.decide(service,store,did,d['result_id'],d['review']['version'],action,'유지관리 담당자','원문과 대상 범위를 대조한 검토 결과',**kw)


def test_approval_reaches_real_extractor_and_disable_reverts(env):
 service,store,did,pid=env;d=seed(env);v=validate(env,d)
 assert v['passed'] and v['before']!=v['after']
 r=decide(env,d,'APPLY',validation_id=v['id'],checked=True)
 text,rule=ar.extract_approved(store,d['source']['url'],RAW)
 assert text[1]==BODY and rule['applied'] and r['action']=='APPLY'
 assert ar.extract_approved(store,d['source']['url']+'?other=1',RAW)[1] is None
 other,rule=ar.extract_approved(store,'https://www.seoul.go.kr/different',RAW)
 assert rule is None and other[1]!=BODY
 with pytest.raises(ar.Conflict):decide(env,d,'APPLY',validation_id=v['id'],checked=True)
 d=ar.detail(service,store,did);decide(env,d,'DISABLE')
 text,rule=ar.extract_approved(store,d['source']['url'],RAW);assert rule is None and text[1]!=BODY
 with service.sessions() as db:assert db.scalar(select(Revision).where(Revision.kind=='project',Revision.entity_id==pid)).payload['planned_units']==100
 assert queue(service)['items'][0]['status']=='REVIEW'

@pytest.mark.parametrize('selector',['변경이 필요합니다','# 본문을 검토하세요','article:has(*)','script()','div;alert(1)',''])
def test_prose_or_executable_or_expensive_selectors_are_rejected(selector):
 with pytest.raises(ValueError):ar.selector_ok(selector)


def test_approval_requires_passed_test_and_explicit_confirmation(env):
 d=seed(env)
 with pytest.raises(ValueError):decide(env,d,'APPLY',checked=False)
 with pytest.raises(ar.Conflict):decide(env,d,'APPLY',checked=True)
 v=validate(env,d,'PATH');assert not v['passed']
 with pytest.raises(ar.Conflict):decide(env,d,'APPLY',validation_id=v['id'],checked=True)


def test_path_rule_requires_two_independent_prior_bodies(env):
 service,store,did,_=env;d=seed(env)
 fetch=Fetch(store);fetch.get(d['source']['url'])
 with service.sessions.begin() as db:
  for i in range(2):
   upsert_revision(db,'ai_publication_analysis','ai_publication',str(i),dict(document_id='past-'+str(i),raw=dict(url='https://www.seoul.go.kr/a?page='+str(i),sha256=fetch.last['sha256']),body_text=BODY,checks=[],result={'issues':[]}),'old-golden')
 v=validate(env,d,'PATH');assert v['passed'] and len(v['cases'])==2
 decide(env,d,'APPLY',validation_id=v['id'],checked=True)
 body,rule=ar.extract_approved(store,'https://www.seoul.go.kr/a?page=new',RAW)
 assert body[1]==BODY and rule['applied']
 assert ar.extract_approved(store,'https://another.go.kr/a?page=new',RAW)[1] is None


def test_path_rule_blocks_regression_on_prior_success(env):
 service,store,did,_=env;d=seed(env);f=Fetch(store);f.get(d['source']['url'])
 with service.sessions.begin() as db:
  for i in range(2):upsert_revision(db,'ai_publication_analysis','ai_publication',str(i),dict(document_id='past-'+str(i),raw=f.last,body_text='과거 정상 본문의 필수 문장입니다. '*8,checks=[],result={'issues':[]}),'golden')
 assert not validate(env,d,'PATH')['passed']

@pytest.mark.parametrize('change',['source','result','review','raw'])
def test_stale_approval_rejected(env,change):
 service,store,did,_=env;d=seed(env);v=validate(env,d)
 if change=='source':
  with service.sessions.begin() as db:
   old=db.scalar(select(Revision).where(Revision.entity_id==did));upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(old.payload,name='원문 정정'),'changed')
 if change=='result':seed(env)
 if change=='review':decide(env,d,'IGNORE')
 if change=='raw':(store.path.parent.parent/'raw'/'ai_publication'/(v['sha256']+'.raw')).write_bytes(b'changed')
 with pytest.raises(ValueError):decide(env,d,'APPLY',validation_id=v['id'],checked=True)


def test_changed_html_falls_back_instead_of_corrupting_rule_output(env):
 _,store,_,_=env;d=seed(env);v=validate(env,d);decide(env,d,'APPLY',validation_id=v['id'],checked=True)
 raw=RAW.replace(b'id="notice"',b'id="changed"');text,rule=ar.extract_approved(store,d['source']['url'],raw)
 assert not rule['applied'] and '기존' not in rule.get('scope_key','') and text[1]!=BODY


def test_business_hold_does_not_reopen_completed_algorithm(env):
 service,store,did,_=env;seed(env,state='DONE',kind='NO_CHANGE')
 save(service,did,1,0,'HOLD',None,[],[],'업무 담당자','사업 자산 범위 확인 필요',True)
 r=inbox.items(service,store,'algorithm')[0]
 assert r['state']=='DONE' and r['business_status']=='HOLD'


def test_ignore_and_retry_preserve_business_and_are_audited(env):
 service,store,did,_=env;d=seed(env);decide(env,d,'IGNORE')
 assert inbox.items(service,store,'algorithm')[0]['state']=='DONE'
 d=ar.detail(service,store,did);assert len(d['history'])==1
 decide(env,d,'RETRY');d=ar.detail(service,store,did)
 assert len(d['history'])==2 and inbox.items(service,store,'algorithm')[0]['stage']=='REANALYSIS_REQUESTED'
 assert queue(service)['items'][0]['status']=='REVIEW'


def test_retry_is_processed_even_when_collection_is_not_pending(env,monkeypatch):
 monkeypatch.setenv('UPSTAGE_SECRET_KEY','offline-test')
 service,store,did,_=env;d=seed(env);decide(env,d,'RETRY');config(store,'algorithm');run=start(store,'algorithm')
 response=work.RuleProposal(diagnosis='규칙 정상 확인',change_type='NO_CHANGE',selector='',reason='원문 검증 결과 변경 불필요',regression_cases=['고정 원문 대조'])
 with patch.object(work,'invoke',return_value=(response,'call')) as invoke:work.process(service,store,run)
 assert invoke.called and '원문과 대상 범위' in invoke.call_args.args[4]
 assert inbox.items(service,store,'algorithm')[0]['state']=='DONE'


def test_authenticated_api_and_no_secret_in_detail(env,monkeypatch):
 from fastapi.testclient import TestClient
 from backend.app import create_app
 service,store,did,_=env;d=seed(env)
 monkeypatch.setenv('POC10_INTERNAL_SECRET','test-secret');monkeypatch.setenv('POC10_DATA_DIR',str(service.data_dir))
 path='/poc/home/api/admin/algorithm-review/'+did+'/decision'
 payload=dict(result_id=d['result_id'],version=0,action='IGNORE',actor='담당자',reason='이번 수집의 일시 오류로 확인')
 stamp=str(int(time.time()));sig=hmac.new(b'test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
 with TestClient(create_app(service.engine,auto_collect=False)) as c:
  assert c.get('/poc/home/api/algorithm-review/'+did).json()['result_id']==d['result_id']
  assert c.post(path,json=payload).status_code==401
  assert c.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code==200
  assert c.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code==409


def test_existing_completed_fingerprint_is_preserved_without_manual_retry():
 doc={'source_revision_no':3,'review_revision_no':2};analysis={'body_sha256':'abc','failure_context':None,'candidate_versions':[('project',1)]};models=['solar-pro4',None]
 expected=hashlib.sha256(json.dumps([3,2,'abc',None,[('project',1)],models,'agents-stage-2'],sort_keys=True).encode()).hexdigest()
 assert work.fingerprint(doc,analysis,models)==expected
 assert work.fingerprint(doc,dict(analysis,human_retry=1),models)!=expected


def test_officer_evidence_changes_do_not_invalidate_algorithm_diagnoses():
 doc={'source_revision_no':3,'review_revision_no':2};analysis={'body_sha256':'abc','candidate_versions':[('project',1)]};models=['solar-pro4',None]
 first=dict(analysis,evidence_epoch='before');second=dict(analysis,evidence_epoch='after')
 assert work.fingerprint(doc,first,models)==work.fingerprint(doc,second,models)
 assert work.fingerprint(doc,first,models,role='officer')!=work.fingerprint(doc,second,models,role='officer')
 assert work.fingerprint(doc,first,models)!=work.fingerprint(doc,first,models,role='officer')


def test_duplicate_prior_document_does_not_count_twice(env):
 service,store,did,_=env;d=seed(env);f=Fetch(store);f.get(d['source']['url'])
 with service.sessions.begin() as db:
  for i in range(2):upsert_revision(db,'ai_publication_analysis','ai_publication',str(i),dict(document_id='same-past-document',raw=f.last,body_text=BODY,checks=[],result={'issues':[]}),'old-golden')
 v=validate(env,d,'PATH');assert not v['passed'] and len(v['cases'])==1


def test_expired_validation_cannot_activate_rule(env):
 _,store,_,_=env;d=seed(env);v=validate(env,d)
 with store.db(True) as c:
  v['created']=time.time()-86401;c.execute('UPDATE algorithm_validations SET payload=? WHERE id=?',(json.dumps(v),v['id']))
 with pytest.raises(ar.Conflict):decide(env,d,'APPLY',validation_id=v['id'],checked=True)


def test_fresh_store_without_algorithm_result_returns_validation_error(env):
 service,store,did,_=env
 with pytest.raises(ValueError,match='진단 결과'):ar.detail(service,store,did)
