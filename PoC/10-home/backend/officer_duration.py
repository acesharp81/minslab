"""Audited refinement of missing target dates using collected stage intervals.

This never creates measured events. Existing collected schedules have priority.
Large districts use explicitly assumed concurrent complexes, not serial 80-year builds.
"""
from collections import Counter
from copy import deepcopy
from datetime import date,timedelta
from math import ceil
from statistics import mean
from sqlalchemy import select,text
from .api_samples import today
from .db import Revision,Audit,entity_id,upsert_revision,now
from .officer_completion import POLICY,ACTOR,REASON,normalized
from .project_profile import STAGES,target_default,progress_default
from .projection_cache import projection_version

BATCH='officer-kimmin-duration-20261014-v2'
PAIRS=[('BUSINESS','APPROVAL'),('APPROVAL','CONSTRUCTION'),('CONSTRUCTION','COMPLETION'),('COMPLETION','MOVE_IN'),('CONSTRUCTION','SUPPLY')]

def duration_model(service):
    from .project_collection import collection_matrix
    from .supply_dashboard import block_key
    matrix=collection_matrix(service,policy_id=POLICY);cells={p['id']:p['cells'] for p in matrix['items']}
    samples={a+'_'+b:[] for a,b in PAIRS};seen=set()
    for p in sorted(service.projects(policy_id=POLICY),key=lambda p:p.get('base_date',''),reverse=True):
        key=block_key(p) or p['id']
        if key in seen:continue
        seen.add(key);dates={}
        cap=p.get('source_values',{}).get('planned_units',p.get('planned_units'))
        if type(cap) is not int or cap<=0:continue
        for stage in STAGES:
            c=cells[p['id']]['CONSTRUCTION' if stage=='COMPLETION' else stage]
            raw=dict(c,sources=[r for r in c['sources'] if r.get('source_id')!='officer'],targets=[r for r in c['targets'] if r.get('source_id')!='officer'])
            dates[stage]=normalized(progress_default(raw,stage).get('event_date') or target_default(raw,stage).get('due_date'))
        for a,b in PAIRS:
            if not dates[a] or not dates[b]:continue
            days=(date.fromisoformat(dates[b])-date.fromisoformat(dates[a])).days
            low=-730 if b=='SUPPLY' else 180 if b=='COMPLETION' else 1
            high=3650 if b=='COMPLETION' else 1825
            if low<=days<=high:samples[a+'_'+b].append(dict(project_id=p['id'],name=p['name'],days=days,units=cap,from_date=dates[a],to_date=dates[b]))
    defaults={'BUSINESS_APPROVAL':365,'APPROVAL_CONSTRUCTION':365,'CONSTRUCTION_COMPLETION':1095,'COMPLETION_MOVE_IN':61,'CONSTRUCTION_SUPPLY':180}
    result={k:dict(sample_count=len(rows),mean_days=round(mean(r['days'] for r in rows)) if rows else defaults[k],samples=rows,origin='COLLECTED_INTERVAL_MEAN' if rows else 'OFFICER_REFERENCE_ASSUMPTION') for k,rows in samples.items()}
    construction=result['CONSTRUCTION_COMPLETION'];rows=construction['samples']
    construction.update(days_per_unit=sum(r['days'] for r in rows)/sum(r['units'] for r in rows) if rows else 1.5,
                        typical_units=mean(r['units'] for r in rows) if rows else 730)
    return result


def construction_days(project,model):
    m=model['CONSTRUCTION_COMPLETION'];cap=project['planned_units']
    large=cap>3000 or (not project.get('block') and cap>2*m['typical_units'])
    groups=max(1,ceil(cap/m['typical_units'])) if large else 1
    raw=cap*m['days_per_unit']
    return dict(days=max(1,round(raw/groups)),raw_days=round(raw),parallel_groups=groups,units=cap,
        days_per_unit=m['days_per_unit'],typical_units=m['typical_units'],sample_count=m['sample_count'],
        formula='round(목표 호수 × 호당 평균 공사일수 ÷ 병행 공구 수)',
        parallel_basis='대규모 지구·다단지 사업: 평균 단지 규모로 나눈 공구 수를 동시 추진한다고 가정' if groups>1 else '단일 공구 기준')


def refine_project(project,schedules,profile,model):
    goals=deepcopy(schedules);calculation=construction_days(project,model)
    def shift(day,days):return (date.fromisoformat(day)+timedelta(days=days)).isoformat()
    # A measured DATE remains an anchor even if its quantity was inferred.
    def observed(stage):
        p=profile.get('progress',{}).get(stage,{})
        return p.get('event_date') if p.get('input_rule') in ('SOURCE_ACCEPTED','BEST_SOURCE_SELECTED') and 'event_date' not in p.get('field_provenance',{}) else None
    def fixed(stage):
        g=goals[stage]
        official_plan=(g.get('input_rule') in ('SOURCE_ACCEPTED','OFFICER_VERIFIED_PLAN','OFFICIAL_PLAN_ACCEPTED')
                       or g.get('source_type')=='OFFICIAL')
        return g['due_date'] if official_plan and not g.get('inferred') else observed(stage)
    anchors={s:fixed(s) for s in STAGES}
    move_gap=model['COMPLETION_MOVE_IN']['mean_days']
    start=anchors['CONSTRUCTION']
    completion=anchors['COMPLETION'] or (shift(anchors['MOVE_IN'],-move_gap) if anchors['MOVE_IN'] else None)
    if not start:start=shift(completion,-calculation['days']) if completion else goals['CONSTRUCTION']['due_date']
    if not completion:completion=shift(start,calculation['days'])
    approval=anchors['APPROVAL'] or shift(start,-model['APPROVAL_CONSTRUCTION']['mean_days'])
    days={'CONSTRUCTION':start,'COMPLETION':completion,'APPROVAL':approval,
          'BUSINESS':anchors['BUSINESS'] or shift(approval,-model['BUSINESS_APPROVAL']['mean_days']),
          'SUPPLY':anchors['SUPPLY'] or shift(start,model['CONSTRUCTION_SUPPLY']['mean_days']),
          'MOVE_IN':anchors['MOVE_IN'] or shift(completion,move_gap)}
    # Correct inferred goals only; collected conflicting dates remain documented.
    constraints=[('BUSINESS','APPROVAL',0),('APPROVAL','CONSTRUCTION',0),('APPROVAL','SUPPLY',0),('CONSTRUCTION','COMPLETION',1),('COMPLETION','MOVE_IN',0),('SUPPLY','MOVE_IN',0)]
    for _ in range(3):
        for a,b,gap in constraints:
            if days[a]<days[b] or not gap and days[a]==days[b]:continue
            if not anchors[b]:days[b]=shift(days[a],calculation['days'] if b=='COMPLETION' else move_gap if b=='MOVE_IN' else gap)
            elif not anchors[a]:days[a]=shift(days[b],-calculation['days'] if a=='CONSTRUCTION' else -gap)
    calculation['applied_days']=(date.fromisoformat(days['COMPLETION'])-date.fromisoformat(days['CONSTRUCTION'])).days
    calculation['collected_schedule_priority']=calculation['applied_days']!=calculation['days']
    changes={}
    for stage in STAGES:
        if anchors[stage] and goals[stage]['due_date']==days[stage]:continue
        if not 1900<=int(days[stage][:4])<=2100:raise ValueError('산정 목표가 관리 가능한 연도 범위를 벗어납니다: '+project['name'])
        g=deepcopy(goals[stage]);g.update(due_date=days[stage],units=g.get('units') if g.get('units') is not None else project['planned_units'],inferred=not bool(anchors[stage]))
        g['calculation']=dict(construction=calculation,intervals={k:dict(sample_count=v['sample_count'],mean_days=v['mean_days'],origin=v['origin']) for k,v in model.items()},anchors=anchors)
        g.update(input_rule='OFFICER_AVERAGE_DURATION',input_basis='수집 일정 우선. 사업화→인허가·인허가→착공·준공→입주는 원천 일정 평균 간격, 건설은 호당 평균일수×목표호수/병행공구로 산정. 표본에는 예정 일정이 포함되며 실제 평균 공기와 구분.')
        if g['due_date']!=goals[stage]['due_date'] or goals[stage].get('input_rule') not in ('SOURCE_ACCEPTED','MEASUREMENT_TO_TARGET'):
            changes[stage]=g
    return changes,calculation


def prepare(service):
    version=[str(v) for v in projection_version(service)];model=duration_model(service)
    projects=service.projects(policy_id=POLICY);profiles={r['project_id']:r for r in service.rows('project_profile')}
    goals={}
    for r in service.rows('execution_schedule'):
        if r.get('status')!='RELEASED':goals.setdefault(r['project_id'],{})[r['stage']]=r
    work=[]
    for p in projects:
        if p['id'] not in profiles or len(goals.get(p['id'],{}))!=6:raise ValueError('6개 단계 담당자 목표 입력을 먼저 완료하세요')
        changes,calculation=refine_project(p,goals[p['id']],profiles[p['id']],model)
        effective=dict(goals[p['id']],**changes)
        # A past deadline was previously used as a current estimate. If the new
        # model places it in the future, retract that estimate, preserving history.
        remove=[stage for stage,r in profiles[p['id']].get('progress',{}).items() if r.get('input_rule')=='OFFICER_CURRENT_ESTIMATE' and effective[stage]['due_date']>today().isoformat()]
        work.append(dict(id=p['id'],name=p['name'],changes=changes,remove_progress=remove,construction=calculation))
    if version!=[str(v) for v in projection_version(service)]:raise ValueError('산정 중 자료 변경: 다시 준비하세요')
    return dict(batch_id=BATCH,version=version,model=model,projects=work,summary=dict(projects=len(work),target_updates=sum(len(p['changes']) for p in work),parallel_projects=sum(p['construction']['parallel_groups']>1 for p in work),retracted_past_estimates=sum(len(p['remove_progress']) for p in work)))


def apply(service,plan):
    if any(r.get('batch_id')==BATCH for r in service.rows('officer_completion')):return dict(already_applied=True)
    stamp=now().isoformat();meta=dict(origin='MANUAL',actor=ACTOR,reason=REASON,changed_at=stamp,batch_id=BATCH)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        if plan['version']!=[str(v) for v in projection_version(service)]:raise ValueError('준비 이후 DB 변경: 다시 산정하세요')
        def write(kind,sid,key,value,action):
            old=db.scalar(select(Revision).where(Revision.entity_id==entity_id(kind,sid,key),Revision.superseded_at.is_(None)))
            before=deepcopy(old.payload) if old else {}
            # service.rows includes read-only projection metadata; don't persist it.
            value={k:v for k,v in value.items() if k not in ('id','revision_no','recorded_at','source_id','superseded_at','payload_hash')}
            value.update(meta,base_date=today().isoformat())
            r,_=upsert_revision(db,kind,sid,key,value,BATCH)
            db.add(Audit(entity_id=r.entity_id,action=action,before=before,after=value))
        for p in plan['projects']:
            for stage,g in p['changes'].items():
                base=g.get('baseline',{}).get('due_date') or g['due_date']
                g=dict(g,shift_days=(date.fromisoformat(g['due_date'])-date.fromisoformat(base)).days,change_reason='평균 소요기간·호당 공사기간·병행 공구 보정으로 목표 재산정')
                write('execution_schedule','officer',p['id']+':'+stage,g,'EXECUTION_SCHEDULE')
            old=db.scalar(select(Revision).where(Revision.entity_id==entity_id('project_profile','manual_project',p['id']),Revision.superseded_at.is_(None)))
            value=deepcopy(old.payload)
            for stage in p['remove_progress']:value['progress'].pop(stage)
            value['target_calculation']=p['construction']
            value['last_changes']=dict(schedules={s:dict(due_date=g['due_date'],units=g['units'],calculation=g['calculation']) for s,g in p['changes'].items()},retracted_progress=p['remove_progress'],reason='평균 소요기간 기준 목표 재산정 · 미도래 측정값 생성 안 함')
            # Explicit states represent absent observations; no fake zero or event date.
            value['stage_states']={s:dict(status='NOT_OBSERVED',actor=ACTOR,reason=REASON,basis='목표만 산정 · 미도래/미진행 단계 측정값 생성 안 함',changed_at=stamp) for s in STAGES if s not in value['progress']}
            write('project_profile','manual_project',p['id'],value,'PROJECT_PROFILE_UPDATED')
        write('officer_duration_model','manual',BATCH,dict(model=plan['model'],summary=plan['summary']),'OFFICER_DURATION_MODEL')
        write('officer_completion','manual',BATCH,dict(summary=plan['summary']),'OFFICER_BATCH_COMPLETED')
    return dict(applied=True,summary=plan['summary'])
