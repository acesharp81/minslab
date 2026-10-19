"""Delegated officer review of official plans; exact scope and quantity only.

Dry-run by default. --apply confirms evidence links, preserving approved schedules,
quantities, policy assignments and actual events. --allow-list pins reviewed proposals.
"""
import argparse, hashlib, json
from collections import defaultdict, Counter
from pathlib import Path
from datetime import date
from sqlalchemy import select
from backend.db import engine_for, Revision, Mapping, Audit, upsert_revision, entity_id
from backend.service import HomeService, latest_batches
from backend.plan_review_matching import scope_key
from backend.schedule_period import schedule_period
from backend.subject_identity import normalized_tenure
from backend.evidence_bridge import facts as source_facts

ACTOR='담당자 대행 · 사용자 연결 검토 지시 2026-10-19'

def protected(service):
    with service.sessions() as db:
        values=[(r.entity_id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind.in_(['execution_schedule','project_profile']),Revision.superseded_at.is_(None)))]
        values += [(m.project_id,m.policy_id,m.program_id,m.status,m.revision_no) for m in db.scalars(select(Mapping))]
    return hashlib.sha256(json.dumps(sorted(values),ensure_ascii=False).encode()).hexdigest()

def main(apply=False, allow_list=None):
    service=HomeService(engine_for());before=protected(service)
    projects={p['id']:p for p in service.projects()}
    delivery=json.loads((service.data_dir/'plan-audit-delivery-20261019.json').read_text())
    owners={sid:c['id'] for c in delivery['portfolio_cohorts'] for sid in c['source_ids']}
    index=defaultdict(dict)
    for p in projects.values():
        if p['mapping']['status']!='CONFIRMED' or p['mapping'].get('policy_id') in (None,'UNASSIGNED'):continue
        if any(w in p.get('warnings',[]) for w in ['MULTI_SITE_CONTRACT','MULTI_BLOCK_NAME_NOT_LOCATED']):continue
        key=scope_key(p);owner=owners.get(p['id'],p['id'])
        target=projects.get(owner,p)
        if key and target.get('planned_units'):index[key][owner]=target
    sources=[r for kind in ['agency_plan','lh_movein_plan','lh_completion_plan'] for r in service.rows(kind)]
    with service.sessions() as db:
        batches=latest_batches(db,'SUCCESS',source_ids={r['source_id'] for r in sources})
    members={b.source_id:set(b.stats.get('entity_ids',[])) for b in batches}
    sources=[r for r in sources if r['id'] in members.get(r['source_id'],set())]
    existing=service.rows('evidence_bridge')
    connected={(b['project_id'],b['source_entity_id']):b for b in existing if b.get('status')=='CONFIRMED'}
    grouped=defaultdict(list);skipped=Counter()
    for r in sources:
        key=scope_key(r)
        if not key:skipped['물리적 지구·블록 키 없음']+=1;continue
        if any(w in r.get('warnings',[]) for w in ['AMBIGUOUS_PLAN_DIMENSION','SOURCE_TOTAL_MISMATCH']) and r['source_id']!='lh_movein_history':skipped['원천 세부 행 범위·합계 검토']+=1;continue
        if not isinstance(r.get('units'),int) or r['units']<=0:skipped['호수 미확인']+=1;continue
        if r['source_id']=='lh_movein_history':
            period=schedule_period(r.get('move_in_plan_month'));fs=[dict(stage='MOVE_IN',kind='PLAN',date=period['due_date'],precision=period['precision'],date_label=r['move_in_plan_month'],units=r['units'],basis='LH 연간 입주계획 원문 동일 블록·주택유형·면적별 계획') ] if period else []
        else:fs=source_facts(r,date(2026,10,19))
        r=dict(r,review_facts=fs)
        grouped[(r['source_id'],str(r.get('dataset_version','')),key,r.get('tenure') or r.get('housing_type'),tuple((f.get('stage'),f.get('milestone'),f.get('date')) for f in fs))].append(r)
    proposed=[];held=[]
    allowed=set(json.loads(Path(allow_list).read_text())) if allow_list else None
    for (sid,version,key,tenure,dates),rs in sorted(grouped.items(),key=str):
        units=sum(r['units'] for r in rs);candidates=list(index.get(key,{}).values())
        exact=[p for p in candidates if p['planned_units']==units]
        if len(exact)!=1 or not dates:
            held.append(dict(source_id=sid,key=key,tenure=tenure,units=units,source_ids=[r['id'] for r in rs],candidates=[dict(id=p['id'],name=p['name'],units=p['planned_units']) for p in candidates],reason='동일 물리적 범위·동일 호수의 단일 승인 사업 또는 계획일 미확보'));continue
        target=exact[0];rs=sorted(rs,key=lambda r:r['id']);first=rs[0]
        source_tenure=normalized_tenure(dict(first,tenure=tenure));target_tenure=normalized_tenure(target)
        conflict=(source_tenure and target_tenure and source_tenure!=target_tenure) or (source_tenure and any(normalized_tenure(p)==source_tenure and p['planned_units']!=units for p in candidates))
        if conflict:
            held.append(dict(source_id=sid,key=key,source_ids=[r['id'] for r in rs],units=units,reason='같은 블록의 주택유형별 물량과 전체 블록 물량 범위 충돌'));continue
        if all((target['id'],r['id']) in connected for r in rs):
            skipped['기존 담당자 확인 연결 유지']+=len(rs);continue
        # Every group must have distinct source rows; aggregate only the displayed dimensions.
        assert len(rs)==len({r['id'] for r in rs})
        fs=[dict(f,units=units,kind='PLAN') for f in first['review_facts']]
        key_id=target['id']+':plan:'+hashlib.sha256('|'.join(r['id'] for r in rs).encode()).hexdigest()[:24]
        eid=entity_id('evidence_bridge','cross_source',key_id)
        basis=f"{ACTOR}. 시도 {key[0]}, 지구 {key[1]}, 블록 {key[2]}, 공식 계획 {units}호 = 기존 승인 사업 {target['planned_units']}호. 원천 유형 {tenure or '미표기'}; 원천 {len(rs)}행의 동일 예정시기 세부 물량 대조. 승인 정책·사업 범위 유지, 계획 근거만 연결."
        entry=dict(id=eid,target_id=target['id'],target_name=target['name'],source_id=sid,source_name=first['name'],source_ids=[r['id'] for r in rs],source_revision_nos=[r['revision_no'] for r in rs],units=units,scope_key=key,tenure=tenure,facts=fs,basis=basis,evidence_url=first['evidence_url'],result='proposed')
        if apply:
            if allowed is None or eid not in allowed:entry['result']='not_in_reviewed_allow_list';proposed.append(entry);continue
            with service.sessions.begin() as db:
                old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
                if old:
                    entry['result']='existing_preserved';proposed.append(entry);continue
                for r in rs:
                    current=db.scalar(select(Revision).where(Revision.entity_id==r['id'],Revision.superseded_at.is_(None)))
                    if not current or current.revision_no!=r['revision_no']:raise ValueError('검토 중 원천 판본 변경')
                payload=dict(project_id=target['id'],name=target['name'],region=key[0],source_entity_id=first['id'],source_revision_no=first['revision_no'],
                    source_name=first['name'],evidence_source_id=sid,source_id=sid,source_rows=[dict(id=r['id'],revision_no=r['revision_no'],units=r['units']) for r in rs],
                    evidence_url=first['evidence_url'],units=units,facts=fs,status='CONFIRMED',reviewed=True,reviewed_on='2026-10-19',review_actor=ACTOR,
                    relation_type='SAME_PLAN_QUANTITY_SCOPE',matching_version='DELEGATED_EXACT_PLAN_REVIEW_20261019',basis=basis,review_basis=basis,base_date='2026-10-19')
                row,_=upsert_revision(db,'evidence_bridge','cross_source',key_id,payload,'plan-review-20261019')
                db.add(Audit(entity_id=row.entity_id,action='DELEGATED_PLAN_LINK_CONFIRMED',before={},after=payload))
                entry['result']='confirmed'
        proposed.append(entry)
    after=protected(service)
    if before!=after:raise ValueError('승인 관리값이 검토 중 변경됨: 결과 재진단 필요')
    result=dict(applied=apply,actor=ACTOR,protected_before=before,protected_after=after,proposed=proposed,held=held,skipped=dict(skipped))
    path=service.data_dir/('plan-links-applied-20261019.json' if apply else 'plan-links-review-20261019.json');path.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'file':str(path),'results':dict(Counter(p['result'] for p in proposed)),'held_groups':len(held),'skipped':dict(skipped),'protected_unchanged':before==after},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--allow-list');a=p.parse_args();main(a.apply,a.allow_list)
