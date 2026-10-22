"""Preview/apply revision-pinned corrections: sequence-validated target estimates."""
import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from sqlalchemy import select, text
from backend.api_samples import today
from backend.db import Revision, Audit, engine_for, entity_id, upsert_revision, now
from backend.service import HomeService
from backend.project_collection import collection_matrix
from backend.measurement_estimates import reconcile, goals_from_cells, RULE, BASIS, STAGES

BATCH='measure-sequence-validated-20261022'
ACTOR='시스템 · 사용자 요청 기준 정정'


def prepare(service):
    reference=today().isoformat();stamp=now().isoformat()
    matrix=collection_matrix(service,include_link_history=False)
    profiles={r['project_id']:r for r in service.rows('project_profile')}
    projects={r['id']:r for r in service.projects()}
    schedules={(r['project_id'],r['stage']):r for r in service.rows('execution_schedule') if r.get('status')!='RELEASED'}
    updates=[];conflicts=[];counts=Counter()
    with service.sessions() as db:
        for p in matrix['items']:
            pid=p['id'];stored=profiles.get(pid)
            if not stored and p.get('mapping_status')!='CONFIRMED':
                counts['unadopted_projects_skipped']+=1;continue
            before=deepcopy(db.get(Revision,stored['source_revision_id']).payload) if stored else {}
            goals=goals_from_cells(p['cells'])
            for stage,g in goals.items():g['source_revision_id']=schedules.get((pid,stage),{}).get('source_revision_id')
            result=reconcile(before.get('progress',{}),goals,p['cells'],reference,scope_limit=projects.get(pid,{}).get('planned_units'))
            conflicts.extend(dict(project_id=pid,name=p['name'],**c) for c in result['conflicts'])
            if not result['changes'] or (not stored and not any(r.get('inferred') for r in result['progress'].values())):continue
            after=deepcopy(before) if stored else dict(project_id=pid,overrides={},approvals={},progress={})
            after['progress']={k:v for k,v in after.get('progress',{}).items() if k not in STAGES}
            for stage,r in result['progress'].items():
                r=deepcopy(r)
                if any(c['stage']==stage for c in result['changes']):r.update(actor=ACTOR,reason=BASIS,origin='MANUAL',changed_at=stamp,batch_id=BATCH)
                after['progress'][stage]=r;after.setdefault('stage_states',{}).pop(stage,None)
            for stage in STAGES:
                if stage not in result['progress'] and stage in before.get('progress',{}):
                    after.setdefault('stage_states',{})[stage]=dict(status='NOT_OBSERVED',actor=ACTOR,reason=BASIS,basis='확인 사건·선후관계·물량 근거 부족 또는 미도래·미진행: 현재 추정값 없음')
            after.update(actor=ACTOR,reason=BASIS,changed_at=stamp,batch_id=BATCH,base_date=reference,
                measurement_estimate_rule=dict(rule=RULE,reference_date=reference,version=2))
            for c in result['changes']:
                if c['before']!=c['after']:counts['revised_stages']+=1
                for field in ('event_date','units'):
                    if c['before'].get(field)!=c['after'].get(field):counts['revised_'+field]+=1
            updates.append(dict(project_id=pid,name=p['name'],expected_revision_id=(stored or {}).get('source_revision_id'),
                expected_goal_revisions={stage:schedules.get((pid,stage),{}).get('source_revision_id') for stage in STAGES},before=before,after=after,changes=result['changes']))
    return dict(rule=RULE,basis=BASIS,reference_date=reference,created_at=stamp,updates=updates,conflicts=conflicts,
        summary=dict(checked_projects=len(matrix['items']),affected_projects=len(updates),source_conflicts=len(conflicts),**counts))


def apply(service,plan):
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':
            for lock in (9072026,9701022):db.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
        for u in plan['updates']:
            eid=entity_id('project_profile','manual_project',u['project_id'])
            current=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
            if (current.id if current else None)!=u['expected_revision_id']:raise ValueError('검토 이후 담당자 입력 변경: '+u['name'])
            for stage,rid in u['expected_goal_revisions'].items():
                goal=db.scalar(select(Revision).where(Revision.entity_id==entity_id('execution_schedule','officer',u['project_id']+':'+stage),Revision.superseded_at.is_(None)))
                if (goal.id if goal and goal.payload.get('status')!='RELEASED' else None)!=rid:raise ValueError('검토 이후 목표 변경: '+u['name'])
        written=[]
        for u in plan['updates']:
            r,_=upsert_revision(db,'project_profile','manual_project',u['project_id'],u['after'],BATCH)
            db.add(Audit(entity_id=r.entity_id,action='MEASURE_SEQUENCE_VALIDATION',before=u['before'],after=dict(revision_id=r.id,rule=RULE,actor=ACTOR,changes=u['changes'])))
            written.append(dict(project_id=u['project_id'],name=u['name'],revision_id=r.id))
    return dict(summary=plan['summary'],written=written,raw_sources_and_targets_unchanged=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--plan',type=Path,required=True);args=parser.parse_args()
    service=HomeService(engine_for());args.plan.parent.mkdir(parents=True,exist_ok=True)
    if args.apply:
        result=apply(service,json.loads(args.plan.read_text()));args.plan.with_name(args.plan.stem+'-applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
        print(json.dumps(result['summary'],ensure_ascii=False))
    else:
        if args.plan.exists():raise ValueError('기존 검토안 보존: 다른 파일명을 사용하세요')
        plan=prepare(service);args.plan.write_text(json.dumps(plan,ensure_ascii=False,indent=2));print(json.dumps(plan['summary'],ensure_ascii=False))
if __name__=='__main__':main()
