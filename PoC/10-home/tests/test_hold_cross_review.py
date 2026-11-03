import csv,io,json,hashlib
from copy import deepcopy
import pytest
from test_ai_collection import env
from test_stage_reconciliation import proposal,apply
from backend import hold_review as hr,stage_reconciliation as sr,ai_agents_store as agents
from backend.ai_agents_inbox import export_csv,enrich,items
from backend.db import upsert_revision

def test_cross_review_is_version_pinned_idempotent_and_not_approval(env):
 s,_,did,_=env
 with s.sessions() as db:doc=sr.current(db,'document_evidence',did)
 payload=dict(subject=did,report_id='test',report_sha256='a'*64,actor='독립 검토',findings=['본문 부족'],refs=[sr.reference(doc)],outcome='보류 유지')
 hr.save(s,payload);assert hr.save(s,payload)['unchanged']
 assert hr.load(s,[did])[did]['current']
 assert not s.rows('project_profile') and not s.rows('publication_review')
 with s.sessions.begin() as db:upsert_revision(db,'document_evidence','seoul_press_watch','test',dict(doc.payload,name='정정 원문'),'changed')
 assert not hr.load(s,[did])[did]['current']
 with pytest.raises(ValueError):hr.save(s,payload)

def test_full_proof_only_on_explicit_export(env):
 s,store,_,_=env;p=proposal(env);sr.propose(s,p)
 assert 'evidence_package' not in sr.list_items(s)[0]
 assert all(isinstance(r['evidence'],list) for r in items(s,store,'officer'))
 exported=sr.list_items(s,include_proof=True)[0]['evidence_package']
 assert exported['body']==p['proof']['body']
 assert exported['exported_body_sha256']==hashlib.sha256(exported['body'].encode()).hexdigest()
 assert all(exported['quote_checks'].values())
 row=next(r for r in csv.DictReader(io.StringIO(export_csv(s,store).lstrip('\ufeff'))) if r['대상유형']=='STAGE')
 assert row['수집본문']==p['proof']['body'] and row['증빙상태']=='PINNED_TEXT'

def test_duplicate_group_and_conflicting_candidates_stop_auto_apply(env):
 s,_,_,_=env;p=proposal(env);sr.propose(s,p)
 def another(key,when):
  with s.sessions.begin() as db:
   doc=sr.current(db,'document_evidence',p['source_ref']['id']);row,_=upsert_revision(db,'document_evidence','seoul_press_watch',key,dict(doc.payload,name=key),'source')
  cp=deepcopy(p);cp['source_ref']=sr.reference(row);cp['proposed']['event_date']=when;sr.propose(s,cp)
 another('same-event','2026-10-20');rows=sr.list_items(s)
 assert all(len(r['duplicate_ids'])==1 for r in rows)
 another('different-event','2026-10-21');rows=sr.list_items(s)
 assert all(r['different_value_ids'] and not r['auto_eligible'] for r in rows)
 with pytest.raises(ValueError,match='상이한 후보'):apply(s,next(r for r in rows if r['proposed']['event_date']=='2026-10-20'),automatic=True)
 assert not s.rows('project_profile')

def test_unique_export_keeps_each_agents_assessment(env):
 s,store,did,_=env;run=store.enqueue(actor='test');store.event(run['id'],'DOCUMENT_ERROR',document_id=did,message='본문 미확보')
 agents.record(store,'officer',did,'fp',run['id'],'HOLD',reason='사업 식별 보류',stage='INPUT_HOLD',source_revision_no=1)
 regular=list(csv.DictReader(io.StringIO(export_csv(s,store).lstrip('\ufeff'))));unique=list(csv.DictReader(io.StringIO(export_csv(s,store,unique=True).lstrip('\ufeff'))))
 assert len(regular)==2 and len(unique)==1 and unique[0]['합쳐진기록수']=='2'
 records=json.loads(unique[0]['에이전트별기록_JSON']);assert {r['role'] for r in records}=={'collection','officer'}
 assert {r['reason'] for r in records}=={'본문 미확보','사업 식별 보류'}

def test_manual_recovery_marks_retry_without_closing_business_hold():
 r=dict(role='collection',stage='DOCUMENT_ERROR',state='HOLD',created=0)
 doc=dict(status='HOLD',status_label='보류',source_revision_no=1,decision={'reason':'사업ID 확인 필요'})
 out=enrich(r,doc,dict(source_revision_no=1,body_text='복구된 원문'*30),{})
 assert out['reanalysis_required'] and out['state']=='HOLD' and out['business_status']=='HOLD'
