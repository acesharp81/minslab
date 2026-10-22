"""Adopt six already-collected 2027 supply plans after identity/reason review.

No project is created, no policy assignment or measured event is changed.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from sqlalchemy import select,text
from backend.db import Audit,Revision,Mapping,entity_id,engine_for,now,upsert_revision
from backend.service import HomeService
BATCH='supply-plan-review-20261022'
ACTOR='담당자 대행 · 사용자 2027년 이후 수집·연결 점검 지시'
OUT=Path('data/remediation/future-plan-review-20261022')
CASES={
 '남양주왕숙 A25':('PRO_f345f2ad0c4ce9f333d7e80d','기존 동일 지구·블록·1298호 연결. 공식 2027년 하반기 계획이 수집됐으나 평균기간 추정 2026-11-15 목표 보존 규칙으로 미반영'),
 '의정부우정 A3':('PRO_9bb2aea471cca4dfe1473b62','기존 동일 지구·블록·640호 연결. 공식 2027년 하반기 계획이 수집됐으나 평균기간 추정 2026-05-16 목표 보존 규칙으로 미반영'),
 '양주옥정 A22':('PRO_46a39b2e958153bd4b912fb3','경기도·양주옥정·A22/A-22BL·1126호 일치. 계약명 접두어 때문에 이전 연결 누락. 평균기간 추정 2025-11-08 대신 공식 2027년 하반기 계획 채택'),
 '안산장상 A10':('PRO_d4e72ea1dc0cec414a81a5bf','경기도·안산장상·A10·320호 일치. 계획표 수집 이후 추가된 원장과 연결 재검토가 실행되지 않아 누락'),
 '수원당수2 C1':('PRO_99ee1fc085ac97b36b95b01b','기존 채택 사유 재사용: 국토부 제2025-807호 C1과 LH B5는 23922㎡·364호·용적률170% 일치. 명칭 전환으로 누락된 공식 공급계획 연결'),
 '수원당수2 C4':('PRO_046e3fb9776e2536afbe2b6b','기존 채택 사유 재사용: 국토부 제2025-807호 C4와 LH B7은 42841㎡·880호·용적률230% 일치. 과거 C4+C5 통합계획과 구분하여 공식 공급계획 연결'),
}


def pinned(db,eid):
    return db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))


def prepare(s):
    plans={p['name']:p for p in s.rows('agency_plan') if p.get('source_object_id','').startswith('0813-2027:')}
    projects={p['id']:p for p in s.projects(policy_id='POL_2025_0907')}
    # Historical alias names are verified against the retained mapping decisions.
    for name,(pid,why) in list(CASES.items()):
        if name=='수원당수2 C4':
            hits=[p for p in projects.values() if p['name']=='수원당수2 B7']
            assert len(hits)==1;CASES[name]=(hits[0]['id'],why)
    items=[]
    with s.sessions() as db:
        for name,(pid,why) in CASES.items():
            a=plans[name];p=projects[pid]
            assert p['mapping']['status']=='CONFIRMED' and p['planned_units']==a['units']
            assert a['plan_year']==2027 and a['plan_half']=='H2'
            raw=Path('data')/a['original_file'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==a['original_sha256']
            if name.endswith(' C1'):assert all(t in p['mapping']['basis'] for t in ['C1','B5','23,922','364'])
            if name.endswith(' C4'):assert all(t in p['mapping']['basis'] for t in ['C4','B7','42,841','880'])
            sched=pinned(db,entity_id('execution_schedule','officer',pid+':SUPPLY'))
            if sched:assert sched.payload.get('inferred') and sched.payload.get('input_rule')=='OFFICER_AVERAGE_DURATION'
            bridge=pinned(db,entity_id('evidence_bridge','cross_source',pid+':'+a['id']))
            profile=pinned(db,entity_id('project_profile','manual_project',pid))
            assert not (profile.payload.get('progress',{}).get('SUPPLY',{}).get('event_date') if profile else None)
            items.append(dict(project_id=pid,name=p['name'],source_name=name,source_id=a['id'],source_revision_id=a['source_revision_id'],source_revision_no=a['revision_no'],
                project_revision_id=p['source_revision_id'],profile_revision_id=profile.id if profile else None,
                mapping_revision_no=p['mapping']['revision_no'],units=a['units'],url=a['evidence_url'],due_date='2027-12-31',
                expected_schedule_revision_id=sched.id if sched else None,before_schedule=deepcopy(sched.payload) if sched else None,
                expected_bridge_revision_id=bridge.id if bridge else None,before_bridge=deepcopy(bridge.payload) if bridge else None,
                reason=why+' · 공식 PDF 15쪽 표 재확인. 반기 일정은 기간 말일로 표시; 실제 공급·착공 실적 아님',source_fact=a['facts'][0]))
    return dict(batch_id=BATCH,items=items,summary=dict(reviewed_plans=6,new_links=sum(not r['before_bridge'] for r in items),new_schedules=sum(not r['before_schedule'] for r in items),updated_estimated_schedules=sum(bool(r['before_schedule']) for r in items),plan_units=sum(r['units'] for r in items)))


def apply(s,plan):
    receipt=[]
    with s.sessions.begin() as db:
        if s.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        for r in plan['items']:
            for eid,rid in [(r['source_id'],r['source_revision_id']),(r['project_id'],r['project_revision_id']),
                (entity_id('project_profile','manual_project',r['project_id']),r['profile_revision_id']),
                (entity_id('execution_schedule','officer',r['project_id']+':SUPPLY'),r['expected_schedule_revision_id']),
                (entity_id('evidence_bridge','cross_source',r['project_id']+':'+r['source_id']),r['expected_bridge_revision_id'])]:
                cur=pinned(db,eid);assert (cur.id if cur else None)==rid,'検討後変更 '+r['name']
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==r['project_id']).with_for_update())
            assert mapping.status=='CONFIRMED' and mapping.revision_no==r['mapping_revision_no']
        for r in plan['items']:
            fact=dict(r['source_fact'],date='2027-12',date_label='2027년 하반기',precision='HALF_YEAR',basis=r['reason'])
            b=dict(r['before_bridge'] or {},project_id=r['project_id'],name=r['name'],source_entity_id=r['source_id'],source_revision_no=r['source_revision_no'],
                source_id='official_document',evidence_source_id='official_document',source_name=r['source_name'],evidence_url=r['url'],units=r['units'],
                facts=[fact],reference_facts=[],approved_schedule_preserved=False,status='CONFIRMED',reviewed=True,review_actor=ACTOR,
                relation_type='REVIEWED_SUPPLY_PLAN',basis=r['reason'],base_date='2026-10-22',batch_id=BATCH)
            goal=dict(r['before_schedule'] or {},project_id=r['project_id'],policy_id='POL_2025_0907',stage='SUPPLY',name=r['name'],
                due_date=r['due_date'],units=r['units'],origin='MANUAL',status='CONFIRMED',input_rule='SOURCE_ACCEPTED',inferred=False,
                input_basis=r['reason'],basis=r['reason'],reason=r['reason'],actor=ACTOR,responsible_org=ACTOR,
                evidence_url=r['url'],source_entity_id=r['source_id'],source_revision_no=r['source_revision_no'],source_precision='HALF_YEAR',source_date_label='2027년 하반기',
                source_date='2026-08-13',base_date='2026-10-22',changed_at=now().isoformat(),batch_id=BATCH,
                field_provenance={f:dict(rule='SOURCE_ACCEPTED',value=v,source_entity_id=r['source_id'],source_revision_no=r['source_revision_no'],basis=r['reason']) for f,v in [('due_date',r['due_date']),('units',r['units'])]})
            if r['before_schedule']:goal['previous_schedule']=r['before_schedule']
            for kind,src,key,payload,before in [('evidence_bridge','cross_source',r['project_id']+':'+r['source_id'],b,r['before_bridge']),('execution_schedule','officer',r['project_id']+':SUPPLY',goal,r['before_schedule'])]:
                row,_=upsert_revision(db,kind,src,key,payload,BATCH)
                db.add(Audit(entity_id=row.entity_id,action='OFFICIAL_2027_PLAN_REPAIR',before=before or {},after=dict(payload,revision_id=row.id)))
                receipt.append(dict(kind=kind,entity_id=row.entity_id,revision_id=row.id))
    return dict(summary=plan['summary'],written=receipt,new_projects=0,actual_events_added=0,mapping_changes=0)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args();s=HomeService(engine_for());OUT.mkdir(parents=True,exist_ok=True);path=OUT/'plan.json'
    if args.apply:
        result=apply(s,json.loads(path.read_text()));(OUT/'applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        assert not path.exists(),'기존 검토안 보존';result=prepare(s);path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['summary'],ensure_ascii=False))
