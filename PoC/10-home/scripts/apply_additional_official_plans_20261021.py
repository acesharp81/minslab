"""Pin five official plan confirmations; update only their MOVE_IN plans.

Run inside the HOME API container with its existing DB configuration. No
actual event, housing quantity, policy assignment, or completion plan is edited.
The plan and pinned files must be reviewed before --apply is used.
"""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from bs4 import BeautifulSoup
from sqlalchemy import select,text
from backend.db import Audit,Mapping,Revision,entity_id,now,upsert_revision
from backend.service import HomeService
from backend.db import engine_for

BATCH='official-extra-plans-20261021'
ACTOR='담당자 대행 · 10.16 신규 검증 공식 입주계획 대조'

def protected(db):
    result={}
    for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None),
            Revision.kind.in_(['project','project_profile','execution_schedule']))):
        if r.kind=='project':result[r.entity_id]=r.payload_hash
        elif r.kind=='project_profile':result[r.entity_id]=r.payload
        elif r.payload.get('stage')!='MOVE_IN':result[r.entity_id]=r.payload_hash
    result['policy_mappings']=[(r.project_id,r.policy_id,r.program_id,r.status,r.revision_no)
                               for r in db.scalars(select(Mapping).order_by(Mapping.project_id))]
    return result

def apply(service,folder,plan):
    # Verify contents before opening the write transaction.
    for s in plan:
        raw=(folder/s['file']).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==s['sha256'],s['key']
        if s['file'].endswith('.hwpx'):
            from backend.lh_public_history import movein_rows
            rs,_=movein_rows(raw)
            exact=[r for r in rs if '인천계양' in r[0] and r[1].replace('-','').replace(' ','')=='A2']
            assert sum(int(r[4].replace(',','')) for r in exact)==747
            assert all(r[5]=='2026-12' for r in exact)
        else:
            content=re.sub(r'\s+','',BeautifulSoup(raw,'html.parser').get_text())
            assert all(re.sub(r'\s+','',term) in content for term in s['checks']),s['key']
    results=[]
    with service.sessions.begin() as db:
        db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        before=protected(db)
        def current(eid):
            return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        def put(kind,source,key,payload,action):
            old=current(entity_id(kind,source,key));prior=deepcopy(old.payload) if old else {}
            row,outcome=upsert_revision(db,kind,source,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=row.entity_id,action=action,before=prior,after=payload))
            return row,outcome
        for s in plan:
            pid=s['project_id'];p=current(pid)
            link=db.scalar(select(Mapping).where(Mapping.project_id==pid).with_for_update())
            assert p and link and link.status=='CONFIRMED' and link.policy_id=='POL_2025_0907'
            assert p.payload['planned_units']==s['units'],pid
            label='담당자 확인 완료 - 공식 자료: '+s['source_name']
            fact=dict(stage='MOVE_IN',kind='PLAN',date=s['month'],date_label=s['month'],precision='MONTH',
                units=s['units'],milestone='MOVE_IN',basis=label+' · 실제 입주 완료 아님',
                evidence_url=s['url'],source_type='OFFICIAL',review_label=label)
            value=dict(name=p.payload['name']+' · '+label,source_object_id=BATCH+':'+s['key'],
                sample_kind='document_evidence',base_date='2026-10-21',source_date=s.get('published_at'),
                original_as_of=s.get('original_as_of'),source_publication_date=s.get('published_at'),
                official_briefing_date='2026-10-16',checked_at=s['checked_at'],date_precision='DAY' if s.get('published_at') else 'YEAR',
                evidence_url=s['url'],original_sha256=s['sha256'],original_file=BATCH+'/'+s['file'],
                checked_source_type='OFFICIAL',review_label=label,review_actor=ACTOR,status='CONFIRMED',
                reviewed=True,verification_status='SOURCE_CONTENT_CHECKED',matched_project_ids=[pid],
                planned_units=s['units'],facts=[fact],basis=s['basis'],comparison_check_id=s['check_id'],
                unit_basis='해당 블록 전체 입주 예정계획 · 실제 입주량 및 신규 정책 호수 합산 금지')
            doc,doc_out=put('document_evidence','official_document',value['source_object_id'],value,'OFFICIAL_PLAN_RECHECKED')
            bridge=dict(project_id=pid,source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,
                source_id='official_document',evidence_source_id='official_document',source_name=label,
                evidence_url=s['url'],facts=[fact],units=None,status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                review_label=label,checked_source_type='OFFICIAL',officer_review_status='CONFIRMED',
                relation_type='OFFICER_VERIFIED_PLAN_SCOPE',basis=s['basis'],base_date='2026-10-21')
            b,b_out=put('evidence_bridge','cross_source',pid+':'+doc.entity_id,bridge,'OFFICIAL_PLAN_LINKED')
            key=pid+':MOVE_IN';old=current(entity_id('execution_schedule','officer',key))
            assert old, 'existing schedule required'
            prior=deepcopy(old.payload)
            if prior.get('batch_id')==BATCH:
                assert prior['due_date']==s['due_date'];schedule_out='unchanged'
            else:
                assert prior.get('due_date')==s['expected_previous_due_date'], 'schedule changed since review'
                value=dict(prior,due_date=s['due_date'],units=s['units'],status='CONFIRMED',
                    basis=s['basis'],reason=s['basis'],actor=ACTOR,responsible_org=ACTOR,origin='MANUAL',
                    evidence_url=s['url'],batch_id=BATCH,base_date='2026-10-21',source_precision='MONTH',
                    source_date_label=s['month'],date_conversion='MONTH_END',
                    source_type='OFFICIAL',review_label=label,input_rule='OFFICER_VERIFIED_PLAN',inferred=False,
                    source_entity_id=doc.entity_id,source_revision_no=doc.revision_no,
                    previous_schedule=prior,changed_at=now().isoformat())
                if value.get('baseline',{}).get('due_date'):
                    value['shift_days']=(date.fromisoformat(s['due_date'])-date.fromisoformat(value['baseline']['due_date'])).days
                _,schedule_out=put('execution_schedule','officer',key,value,'OFFICIAL_MOVE_IN_PLAN')
            results.append(dict(project_id=pid,document_id=doc.entity_id,bridge_id=b.entity_id,
                document_outcome=doc_out,bridge_outcome=b_out,schedule_outcome=schedule_out,
                previous_due_date=s['expected_previous_due_date'],due_date=s['due_date'],units=s['units'],
                date_changed=s['expected_previous_due_date']!=s['due_date'],source_type='OFFICIAL'))
        assert protected(db)==before,'protected quantities/events/mappings modified'
    return dict(results=results,new_policy_assignments=0,unofficial_adoptions=0,
        date_changes=sum(r['date_changed'] for r in results),protected_values_unchanged=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    service=HomeService(engine_for());folder=service.data_dir/BATCH;plan=json.loads((folder/'plan.json').read_text())
    if not args.apply:print(json.dumps(plan,ensure_ascii=False,indent=2))
    else:
        result=apply(service,folder,plan);name='applied.json' if any(r['document_outcome']!='unchanged' for r in result['results']) else 'idempotence.json'
        (folder/name).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
