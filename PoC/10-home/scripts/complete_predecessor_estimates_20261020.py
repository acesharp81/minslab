"""Fill only missing business/approval management fields using the existing model."""
import argparse
from copy import deepcopy
from datetime import date
import json

from sqlalchemy import select, text
from backend.db import Audit, Mapping, ProgramMapping, Revision, engine_for, entity_id, now, upsert_revision
from backend.service import HomeService
from backend.api_samples import today
from backend.project_collection import collection_matrix
from backend.project_profile import progress_default, target_default
from backend.incremental_estimates import values
from backend.independent_metrics import digest

BATCH='predecessor-gaps-20261020'
ACTOR='담당자 대행 · 사용자 사업화·인허가 빈칸 추정 입력 지시'
REASON='기존 평균 소요기간·선후관계 규칙으로 누락된 사업화·인허가 관리 추정값 보완. 원천 실적과 구분'
POLICY='POL_2025_0907'
STAGES=('BUSINESS','APPROVAL')


def estimate_units(current, candidate, goal):
    if current is not None:return current
    return min(candidate,goal) if type(goal) is int and goal>=0 else candidate


def prepare(service):
    reference=today(); stamp=now().isoformat()
    projects=[p for p in service.projects(policy_id=POLICY) if p['mapping']['status']=='CONFIRMED']
    profiles={p['project_id']:p for p in service.rows('project_profile')}
    schedules={(p['project_id'],p['stage']):p for p in service.rows('execution_schedule') if p.get('status')!='RELEASED'}
    cells={r['id']:r['cells'] for r in collection_matrix(service,policy_id=POLICY)['items']}
    with service.sessions() as db:
        modelrow=db.scalar(select(Revision).where(Revision.kind=='officer_duration_model').order_by(Revision.recorded_at.desc()).limit(1))
        if not modelrow:raise ValueError('기존 담당자 평균 소요기간 모형 미확보')
        model=deepcopy(modelrow.payload['model']);model_id=modelrow.id
    work=[];not_due=[]
    for p in projects:
        pid=p['id'];profile=profiles.get(pid,{})
        missing=[]
        for stage in STAGES:
            t=target_default(cells[pid][stage],stage,schedules.get((pid,stage)))
            a=progress_default(cells[pid][stage],stage,profile.get('progress',{}).get(stage))
            if not t.get('due_date') or t.get('units') is None or not a.get('event_date') or a.get('units') is None:missing.append(stage)
        if not missing:continue
        anchors=[]
        for stage in ('BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'):
            g=schedules.get((pid,stage))
            if g and g.get('due_date'):
                anchors.append(dict(stage=stage,due_date=g['due_date'],basis='기존 담당자 목표 일정 보존·선후 추정 기준',evidence_url=g.get('evidence_url'),source_entity_id=g['id'],source_revision_id=g['source_revision_id']))
        peers=[x.get('planned_units') for x in projects if x['mapping']['program_id']==p['mapping']['program_id']]
        if not any(type(v) is int and v>0 for v in peers):peers=[x.get('planned_units') for x in projects]
        v=values(p,cells[pid],model,stamp,ACTOR,REASON,reference,anchors,peers)
        changes=dict(targets={},progress={})
        for stage in missing:
            old=schedules.get((pid,stage));effective=target_default(cells[pid][stage],stage,old)
            proposed=v['targets'][stage]
            if not effective.get('due_date') or effective.get('units') is None:
                g=deepcopy(old or {})
                g.update(due_date=effective.get('due_date') or proposed['due_date'], units=effective.get('units') if effective.get('units') is not None else proposed['units'])
                g.update(inferred=True,input_rule='OFFICER_PREDECESSOR_ESTIMATE',input_basis=REASON,calculation=proposed.get('calculation') or v.get('calculation'))
                changes['targets'][stage]=g
                effective=g
            existing=profile.get('progress',{}).get(stage,{})
            current=progress_default(cells[pid][stage],stage,existing or None)
            if current.get('event_date') and current.get('units') is not None:continue
            code=cells[pid][stage].get('progress',{}).get('code')
            candidate=v['progress'].get(stage)
            if not candidate or code in ('NOT_REACHED_REPORTED','SCHEDULE_PENDING'):
                not_due.append(dict(project_id=pid,name=p['name'],stage=stage,due_date=effective.get('due_date'),reason='미도래·원천상 미진행 또는 현재 실적 추정 기준 미충족'))
                continue
            day=current.get('event_date') or candidate.get('event_date')
            if not day or day>reference.isoformat():
                not_due.append(dict(project_id=pid,name=p['name'],stage=stage,due_date=day,reason='미래 사건을 현재 측정값으로 생성하지 않음'));continue
            r=deepcopy(existing)
            r.update(event_date=day,units=estimate_units(current.get('units'),candidate['units'],effective.get('units')),
                     input_rule='OFFICER_PREDECESSOR_ESTIMATE',input_basis=REASON,inferred=True,
                     field_provenance=dict(candidate.get('field_provenance',{})),calculation=candidate.get('calculation') or v.get('calculation'))
            r['field_provenance'].update(event_date=dict(rule='OFFICER_PREDECESSOR_ESTIMATE',value=day,basis='기존 선후 일정·원천 평균 소요기간으로 산정한 관리 추정일; 실제 사건일 확정 아님'),units=dict(rule='PROJECT_SCOPE_ESTIMATE',value=r['units'],basis='기존 사업 총량·선후 단계 범위에 따른 담당자 추정 물량'))
            changes['progress'][stage]=r
        if changes['targets'] or changes['progress']:
            work.append(dict(project_id=pid,name=p['name'],region=p['region'],source_revision_id=p['source_revision_id'],
                mapping_revision_no=p['mapping']['revision_no'],profile_revision_id=profile.get('source_revision_id'),
                program_id=p['mapping'].get('program_id'),policy_link_revision_no=p['mapping'].get('policy_link_revision_no'),
                schedule_revision_ids={stage:(schedules.get((pid,stage)) or {}).get('source_revision_id') for stage in STAGES},changes=changes))
    return dict(reference_date=reference.isoformat(),created_at=stamp,model_revision_id=model_id,projects=work,not_due=not_due,
                summary=dict(confirmed_projects=len(projects),affected_projects=len(work),targets=sum(len(p['changes']['targets']) for p in work),measurements=sum(len(p['changes']['progress']) for p in work),not_due=len(not_due)))


def apply(service,plan):
    signature=digest(plan);stamp=plan['created_at'];out=[]
    metadata=dict(actor=ACTOR,reason=REASON,origin='MANUAL',changed_at=stamp,batch_id=BATCH)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        marker=db.scalar(select(Revision).where(Revision.entity_id==entity_id('officer_completion','manual',BATCH),Revision.superseded_at.is_(None)))
        if marker:
            if marker.payload.get('plan_digest')!=signature:raise ValueError('기존 적용안과 다름')
            return dict(marker.payload,unchanged=True)
        def current(kind,pid):
            return db.scalar(select(Revision).where(Revision.entity_id==entity_id(kind,'manual_project' if kind=='project_profile' else 'officer',pid),Revision.superseded_at.is_(None)))
        for p in plan['projects']:
            if any(stage not in STAGES for changes in p['changes'].values() for stage in changes):raise ValueError('사업화·인허가 외 단계 변경 금지')
            m=db.scalar(select(Mapping).where(Mapping.project_id==p['project_id']).with_for_update())
            parent=db.get(ProgramMapping,m.program_id) if m and m.program_id else None
            effective_policy=parent.policy_id if parent and parent.status!='RELEASED' else (m.policy_id if m else None)
            raw=db.scalar(select(Revision).where(Revision.entity_id==p['project_id'],Revision.superseded_at.is_(None)))
            old=current('project_profile',p['project_id'])
            if not m or m.status!='CONFIRMED' or effective_policy!=POLICY or m.revision_no!=p['mapping_revision_no'] or not raw or raw.id!=p['source_revision_id'] or (old.id if old else None)!=p['profile_revision_id']:raise ValueError('준비 이후 사업·입력 변경: '+p['name'])
            if 'program_id' in p and (m.program_id!=p['program_id'] or parent and parent.revision_no!=p['policy_link_revision_no']):raise ValueError('준비 이후 프로그램 연결 변경: '+p['name'])
            for stage,r in p['changes']['progress'].items():
                if r['event_date']>plan['reference_date'] or not r.get('inferred'):raise ValueError('현재 추정일·추정 표시 오류')
                prior=(old.payload if old else {}).get('progress',{}).get(stage,{})
                if any(prior.get(k) not in (None,'') and prior[k]!=r[k] for k in ('event_date','units')):raise ValueError('기존 담당자 진행값 변경 금지')
            for stage in STAGES:
                g=current('execution_schedule',p['project_id']+':'+stage)
                if (g.id if g else None)!=p['schedule_revision_ids'][stage]:raise ValueError('준비 이후 목표 변경: '+p['name'])
                proposed=p['changes']['targets'].get(stage)
                if proposed and g and any(g.payload.get(k) not in (None,'') and g.payload[k]!=proposed[k] for k in ('due_date','units')):raise ValueError('기존 담당자 목표 변경 금지')
        def write(kind,sid,key,payload,action):
            eid=entity_id(kind,sid,key);old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
            before=deepcopy(old.payload) if old else {};r,outcome=upsert_revision(db,kind,sid,key,payload,BATCH)
            if outcome!='unchanged':db.add(Audit(entity_id=r.entity_id,action=action,before=before,after=payload))
            return r.entity_id
        for p in plan['projects']:
            pid=p['project_id'];old=current('project_profile',pid);profile=deepcopy(old.payload) if old else dict(project_id=pid,overrides={},progress={},approvals={})
            for stage,value in p['changes']['targets'].items():
                clean={k:v for k,v in value.items() if k not in ('id','revision_no','recorded_at','source_id','source_revision_id','source_age_days')}
                clean.update(metadata,project_id=pid,policy_id=POLICY,stage=stage,status='CONFIRMED',basis=REASON,responsible_org=ACTOR,base_date=plan['reference_date'],name=p['name'],region=p['region'])
                write('execution_schedule','officer',pid+':'+stage,clean,'EXECUTION_SCHEDULE')
            if p['changes']['progress']:
                for stage,value in p['changes']['progress'].items():
                    profile.setdefault('progress',{})[stage]=dict(value,**metadata)
                    profile.get('stage_states',{}).pop(stage,None)
                profile.update(metadata,base_date=plan['reference_date'])
                write('project_profile','manual_project',pid,profile,'PROJECT_PROFILE')
            out.append(dict(project_id=pid,name=p['name'],target_stages=list(p['changes']['targets']),measurement_stages=list(p['changes']['progress'])))
        marker=dict(plan_digest=signature,summary=plan['summary'],actor=ACTOR,reason=REASON,base_date=plan['reference_date'],results=out)
        write('officer_completion','manual',BATCH,marker,'OFFICER_PREDECESSOR_COMPLETED')
    return marker


def bound_partial_estimates(service):
    """Honor a pre-existing partial goal when the batch assumed the full capacity."""
    changed=[]
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        for old in db.scalars(select(Revision).where(Revision.kind=='project_profile',Revision.superseded_at.is_(None))):
            value=deepcopy(old.payload);edits=[]
            for stage,r in value.get('progress',{}).items():
                if stage not in STAGES or r.get('batch_id')!=BATCH or not r.get('inferred'):continue
                goal=db.scalar(select(Revision).where(Revision.entity_id==entity_id('execution_schedule','officer',value['project_id']+':'+stage),Revision.superseded_at.is_(None)))
                units=(goal.payload if goal else {}).get('units')
                if type(units) is not int or units<0 or r.get('units') is None or r['units']<=units:continue
                previous=r['units'];r['units']=units
                r.setdefault('field_provenance',{})['units']=dict(rule='EXISTING_PARTIAL_SCOPE_ESTIMATE',value=units,previous_estimate=previous,basis='기존 담당자 목표의 부분 물량을 추정 범위 상한으로 적용. 기존 목표·실제 원천 값은 변경하지 않음')
                edits.append(dict(project_id=value['project_id'],stage=stage,before=previous,after=units))
            if edits:
                value.update(changed_at=now().isoformat(),partial_scope_correction=True)
                upsert_revision(db,'project_profile','manual_project',value['project_id'],value,BATCH)
                db.add(Audit(entity_id=old.entity_id,action='OFFICER_PARTIAL_ESTIMATE_BOUND',before=old.payload,after=value));changed+=edits
    return dict(changed=changed,source_and_targets_unchanged=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');parser.add_argument('--bound-partial',action='store_true');args=parser.parse_args()
    service=HomeService(engine_for());folder=service.data_dir/BATCH;folder.mkdir(exist_ok=True)
    if args.bound_partial:
        result=bound_partial_estimates(service);(folder/('partial-scope-applied.json' if result['changed'] else 'partial-scope-idempotence.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False));raise SystemExit(0)
    planfile=folder/'plan.json'
    plan=json.loads(planfile.read_text()) if args.apply else prepare(service)
    if args.apply:
        from backend.policy_delivery import build_delivery
        from scripts.build_continuation_review_20261020 import metrics
        before=metrics(build_delivery(service,today(),include_portfolio_comparisons=False));result=apply(service,plan)
        after=metrics(build_delivery(service,today(),include_portfolio_comparisons=False));result.update(metrics_before=before,metrics_after=after)
        assert before['CONSTRUCTION']==after['CONSTRUCTION'] and before['SUPPLY']==after['SUPPLY']
        target=folder/('idempotence.json' if result.get('unchanged') else 'applied.json');target.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
    else:
        if planfile.exists():raise ValueError('기존 준비안 보존: 판본 확인 필요')
        planfile.write_text(json.dumps(plan,ensure_ascii=False,indent=2));print(json.dumps(plan['summary'],ensure_ascii=False))
