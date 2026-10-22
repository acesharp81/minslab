"""Explicit officer-requested completion. Source revisions are never overwritten.

Prepare a version-pinned plan, then atomically append manual overlays and audit every
change. Inferred milestones remain identifiable as officer assumptions.
"""
from copy import deepcopy
from calendar import monthrange
from datetime import date, timedelta
from collections import Counter
from statistics import median
import hashlib
import json
from sqlalchemy import select, text
from .db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, now
from .api_samples import today
from .project_profile import STAGES, target_default, progress_default, linked_progress
from .policy_profile import source_fields, validate as validate_policy
from .program_profile import BASE, profiles, validate as validate_program

POLICY='POL_2025_0907'
BATCH='officer-kimmin-20261014-v1'
ACTOR='김민'
REASON='자동매칭 확인 완료'
# Supply may precede construction/completion. It only proves business/approval.
SUCCESSORS={'BUSINESS':['APPROVAL','CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN'],
 'APPROVAL':['CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN'],
 'CONSTRUCTION':['COMPLETION','MOVE_IN'],'COMPLETION':['MOVE_IN'],'SUPPLY':['MOVE_IN'],'MOVE_IN':[]}

def normalized(value):
    if not value:return ''
    try:
        if len(value)==4:value+='-12-31'
        if len(value)==7:value+=f'-{monthrange(int(value[:4]),int(value[5:]))[1]:02d}'
        return date.fromisoformat(value).isoformat()
    except (ValueError,TypeError):return ''

def meta(stamp,rule,basis,inferred=False):
    return dict(origin='MANUAL',actor=ACTOR,reason=REASON,changed_at=stamp,batch_id=BATCH,
                input_rule=rule,input_basis=basis,inferred=inferred,authentication='ADMIN',actor_basis='사용자 지정 담당자 이름')

def project_values(p,cells,stamp,parent=None,previous=None):
    """Collected measurements take priority; missing fields use goals only with independent event evidence."""
    previous=previous or {};cap=p.get('planned_units');issues=[];progress={};targets={}
    overrides=deepcopy(previous.get('overrides',{}))
    if type(cap) is int:overrides['planned_units']=dict(meta(stamp,'SOURCE_ACCEPTED','현재 수집된 사업 총 목표 공급량 채택'),value=cap)
    linked=linked_progress(cells['CONSTRUCTION'])
    pct=p.get('progress_pct') if p.get('progress_pct') is not None else (linked or {}).get('pct')
    pctdate=p.get('progress_date') or (linked or {}).get('date') or p.get('base_date')
    if pct is not None and normalized(pctdate) and normalized(pctdate)<=today().isoformat():
        for k,v in [('progress_pct',pct),('progress_date',normalized(pctdate))]:
            overrides[k]=dict(meta(stamp,'SOURCE_ACCEPTED','수집 공정률 및 관측일 채택'),value=v)
    for stage in STAGES:
        c=cells['CONSTRUCTION' if stage=='COMPLETION' else stage]
        measured=progress_default(c,stage,previous.get('progress',{}).get(stage))
        planned=target_default(c,stage)
        when=normalized(measured.get('event_date'));units=measured.get('units')
        if when and when>today().isoformat():when=''
        if units is not None and cap is not None and units>cap:
            issues.append(dict(stage=stage,code='SCOPE_CONFLICT',field='measurement.units',reason='원천 확인량이 사업 총량을 초과해 합산하지 않음'));units=None
        if when or units is not None:
            progress[stage]=dict(meta(stamp,'SOURCE_ACCEPTED','같은 사업·단계의 수집 측정값 채택'),event_date=when,units=units)
        if planned.get('due_date'):
            u=planned.get('units');u=u if u is None or cap is None or u<=cap else None
            targets[stage]=dict(meta(stamp,'SOURCE_ACCEPTED','같은 사업·단계의 수집 예정값 채택'),due_date=planned['due_date'],units=u)
        if '상충' in measured.get('display_note','') or '서로 다른' in planned.get('display_note',''):
            issues.append(dict(stage=stage,code='SOURCE_CONFLICT',reason='서로 다른 원천 날짜·수량은 상세 근거에서 비교 필요'))
    for stage in STAGES:
        actual=progress.get(stage,{})
        goal=targets.get(stage,{})
        if not goal and actual.get('event_date'):
            goal=dict(meta(stamp,'MEASUREMENT_TO_TARGET','목표 미확보: 담당자가 현재 확인값을 목표 기준선으로 채택',actual.get('inferred',False)),due_date=actual['event_date'],units=None)
        if goal and goal.get('units') is None:
            goal['units']=actual.get('units') if actual.get('units') is not None else cap
            goal.setdefault('field_provenance',{})['units']=dict(rule='MEASUREMENT_TO_TARGET' if actual.get('units') is not None else 'PROJECT_CAPACITY_TARGET',basis='확인 물량 채택' if actual.get('units') is not None else '사업 총 목표 공급량을 단계 목표로 채택')
        if goal:targets[stage]=goal
    # Earlier goals can share the later goal's date as an explicitly adopted deadline.
    for stage in reversed(list(STAGES)):
        if stage in targets:continue
        options=[(s,targets[s]) for s in SUCCESSORS[stage] if s in targets]
        if not options:continue
        s,t=min(options,key=lambda x:x[1]['due_date'])
        # Never manufacture a zero-length construction period.
        if stage=='CONSTRUCTION':continue
        targets[stage]=dict(meta(stamp,'PREDECESSOR_TARGET','후속 '+STAGES[s]+' 목표일을 선행 완료 상한 목표일로 채택',True),due_date=t['due_date'],units=t.get('units') if t.get('units') is not None else cap)
    # An explicit source-unavailable decision is required for model-only estimates.
    # No such decision is inferred from a missing API field or a future date.
    for stage in STAGES:
        c=cells['CONSTRUCTION' if stage=='COMPLETION' else stage]
        assessment=c.get('assessment') or {}
        if stage not in targets and assessment.get('status')=='COLLECTION_UNAVAILABLE':
            end=normalized((parent or {}).get('period_end'))
            if end:targets[stage]=dict(meta(stamp,'UNAVAILABLE_POLICY_ESTIMATE','수집 불가 담당자 판정에 따라 프로그램 종료일을 잠정 목표로 채택',True),due_date=end,units=cap)
    if targets.get('CONSTRUCTION',{}).get('due_date') and targets.get('COMPLETION',{}).get('due_date') and targets['CONSTRUCTION']['due_date']>=targets['COMPLETION']['due_date']:
        issues.append(dict(stage='CONSTRUCTION',code='SCHEDULE_CONFLICT',reason='착공·준공 목표의 선후관계 충돌: 추정 착공 목표를 적용하지 않음'))
        if targets['CONSTRUCTION'].get('inferred'):targets.pop('CONSTRUCTION')
        elif targets['COMPLETION'].get('inferred'):targets.pop('COMPLETION')
        else:targets.pop('CONSTRUCTION')
    from .measurement_estimates import reconcile
    progress=reconcile(progress,targets,cells,today(),scope_limit=cap)['progress']
    for record in progress.values():
        for key,metadata_value in meta(stamp,record['input_rule'],record['input_basis'],record['inferred']).items():record.setdefault(key,metadata_value)
    for stage in STAGES:
        c=cells['CONSTRUCTION' if stage=='COMPLETION' else stage];a=progress.get(stage,{});t=targets.get(stage,{})
        for field,v in [('target.date',t.get('due_date')),('target.units',t.get('units')),('measurement.date',a.get('event_date')),('measurement.units',a.get('units'))]:
            if v not in (None,''):continue
            code=c.get('progress',{}).get('code')
            future=field.startswith('measurement') and (code in ('UPCOMING','NOT_REACHED_REPORTED','SCHEDULE_PENDING') or t.get('due_date','')>today().isoformat())
            issues.append(dict(stage=stage,field=field,code='UPCOMING' if future else 'UNRESOLVED',reason='시기 미도래·단계 미진행 또는 일정 미정' if future else '수집 불가 확정 근거 없음 · 추가 확인 필요'))
    return dict(overrides=overrides,progress=progress,targets=targets,remaining=issues)


def prepare(service):
    from .project_collection import collection_matrix
    from .projection_cache import projection_version
    version=projection_version(service)
    projects=service.projects(policy_id=POLICY);matrix=collection_matrix(service,policy_id=POLICY)
    cells={p['id']:p['cells'] for p in matrix['items']};parents=service.program_links();parent_by={p['id']:p for p in parents}
    previous={p['project_id']:p for p in service.rows('project_profile')}
    stamp=now().isoformat();work=[]
    observed_sizes=[p['planned_units'] for p in projects if type(p.get('planned_units')) is int and p['planned_units']>0]
    durations=[]
    for p in projects:
        start=normalized(p.get('start_actual_date') or p.get('start_plan_date'));end=normalized(p.get('completion_actual_date') or p.get('completion_plan_date'))
        if start and end:
            days=(date.fromisoformat(end)-date.fromisoformat(start)).days
            if 180<=days<=3650:durations.append(days)
    duration=int(median(durations)) if durations else 1095
    for p in projects:
        if p['mapping']['status'] in ('RELEASED','REJECTED'):continue
        original_cap=p.get('planned_units');cap_basis=''
        if type(original_cap) is not int or original_cap<=0:
            facts=[r for c in cells[p['id']].values() for r in c.get('sources',[]) if type(r.get('units')) is int and r['units']>0 and not r.get('scope_partial')]
            if facts:
                chosen=max(facts,key=lambda r:(r.get('review_status')=='CONFIRMED',r.get('source_revision_no') or 0,r.get('date') or ''))
                cap=chosen['units'];cap_basis='연결된 동일 사업 범위 원천의 확인량/목표량 채택'
            else:
                siblings=[r['planned_units'] for r in projects if r['mapping']['program_id']==p['mapping']['program_id'] and type(r.get('planned_units')) is int and r['planned_units']>0]
                cap=int(median(siblings or observed_sizes));cap_basis='동일 프로그램 등록 사업 규모 중앙값' if siblings else '정책 등록 사업 규모 중앙값'
            p=dict(p,planned_units=cap)
        parent=parent_by.get(p['mapping']['program_id'],{}).get('profile')
        values=complete_values(p,cells[p['id']],project_values(p,cells[p['id']],stamp,parent,previous.get(p['id'])),stamp,duration,parent)
        if cap_basis:values['overrides']['planned_units']=dict(meta(stamp,'PROJECT_CAPACITY_ESTIMATE',cap_basis,True),value=p['planned_units'])
        work.append(dict(id=p['id'],name=p['name'],region=p['region'],program_id=p['mapping']['program_id'],evidence_url=p.get('evidence_url'),**values))
    if version!=projection_version(service):raise ValueError('데이터 변경 감지: 다시 준비하세요')
    return dict(batch_id=BATCH,actor=ACTOR,reason=REASON,stamp=stamp,version=[str(v) for v in version],projects=work,
                summary=dict(projects=len(work),programs=sum(p['policy_id']==POLICY and p['status'] not in ('RELEASED','REJECTED') for p in parents),
                construction_duration_days=duration,targets=sum(len(p['targets']) for p in work),measurements=sum(len(p['progress']) for p in work),
                inferred_measurements=sum(bool(r.get('inferred')) for p in work for r in p['progress'].values()),
                not_due_measurements=sum(6-len(p['progress']) for p in work),remaining=dict(Counter(r['code'] for p in work for r in p['remaining']))))


def apply(service,plan):
    from .projection_cache import projection_version
    if plan['batch_id']!=BATCH:raise ValueError('배치 식별자 오류')
    existing=service.rows('officer_completion')
    if any(r.get('batch_id')==BATCH for r in existing):return dict(already_applied=True)
    stamp=plan['stamp'];stampmeta=meta(stamp,'OFFICER_BATCH','사용자 요청에 따른 일괄 입력')
    pids={p['id'] for p in plan['projects']}
    storedprograms=profiles(service)
    policyplan=next(p for p in service.rows('policy_delivery_plan') if p['policy_id']==POLICY)
    counts=Counter()
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':
            for lock in (9072026,1019081):db.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
        if [str(v) for v in projection_version(service)]!=plan['version']:raise ValueError('준비 이후 데이터 변경: 다시 준비하세요')
        def current(kind,sid,key):return db.scalar(select(Revision).where(Revision.entity_id==entity_id(kind,sid,key),Revision.superseded_at.is_(None)))
        def write(kind,sid,key,payload,action):
            old=current(kind,sid,key);before=deepcopy(old.payload) if old else {}
            payload=dict(payload,base_date=today().isoformat(),actor=ACTOR,reason=REASON,batch_id=BATCH)
            r,_=upsert_revision(db,kind,sid,key,payload,BATCH)
            db.add(Audit(entity_id=r.entity_id if kind not in ('policy_profile','program_profile') else key,action=action,before=before,after=payload));counts[kind]+=1
            return r
        programupdates=[]
        for row in db.scalars(select(ProgramMapping).where(ProgramMapping.policy_id==POLICY).with_for_update()):
            if row.status in ('RELEASED','REJECTED'):continue
            before={k:getattr(row,k) for k in ('policy_id','status','basis','evidence_url','revision_no')}
            row.status='CONFIRMED';row.basis='사용자 입력 · '+ACTOR+' · '+REASON;row.reviewed_at=now();row.revision_no+=1
            after=dict({k:getattr(row,k) for k in before},**stampmeta)
            db.add(Audit(entity_id=row.id,action='PROGRAM_POLICY_REVIEW',before=before,after=after));counts['program_mapping']+=1
            programupdates.append(dict(id=row.id,name=row.name,before=before,after=after))
            stored=storedprograms.get(row.id,{})
            source=stored.get('source',{}).get('fields',{});values=dict(BASE,**source);values.update(stored.get('values',{}));values['name']=values['name'] or row.name
            overrides=deepcopy(stored.get('overrides',{}))
            for k,v in values.items():
                if v is not None and (k in ('target_units','period_start','period_end') or k.startswith(('annual:','region:'))):
                    overrides[k]=dict(meta(stamp,'SOURCE_ACCEPTED','현재 프로그램 목표·기간 채택'),value=v)
            # Missing independent total: use the registered projects as a stated provisional target.
            members=[p for p in plan['projects'] if p['program_id']==row.id]
            if values.get('target_units') is None and values.get('unit')=='호' and members and all(p['overrides'].get('planned_units') for p in members):
                amount=sum(p['overrides']['planned_units']['value'] for p in members)
                overrides['target_units']=dict(meta(stamp,'REGISTERED_PROJECT_TARGET','등록 사업 총 목표 공급량 합계를 담당자 잠정 목표로 채택 · 공식 독립 목표 아님',True),value=amount)
            effective=dict(values,**{k:v['value'] for k,v in overrides.items()})
            weights={region:sum(p['overrides']['planned_units']['value'] for p in members if p['region']==region) for region in ('서울특별시','경기도','인천광역시')}
            if not sum(weights.values()):
                geography=stored.get('source',{}).get('geography',[])
                weights={r:1 if not geography or r in geography else 0 for r in weights}
            complete_goal_grid(effective,overrides,stamp,weights);validate_program(effective,overrides)
            write('program_profile','manual_program',row.id,dict(program_id=row.id,overrides=overrides,changed_at=stamp,program_changes=[]),'PROGRAM_PROFILE_UPDATED')
        old=current('policy_profile','manual_policy',POLICY);policyvalue=deepcopy(old.payload) if old else dict(policy_id=POLICY,overrides={})
        fields=source_fields(policyplan);fields.update({k:v['value'] for k,v in policyvalue['overrides'].items()})
        for k,v in fields.items():
            if v is not None and (k in ('target_units','period_start','period_end') or k.startswith(('annual:','region:'))):policyvalue['overrides'][k]=dict(meta(stamp,'SOURCE_ACCEPTED','수집 정책 목표·기간 채택'),value=v)
        policyweights={region:sum(p['overrides']['planned_units']['value'] for p in plan['projects'] if p['region']==region) for region in ('서울특별시','경기도','인천광역시')}
        complete_goal_grid(fields,policyvalue['overrides'],stamp,policyweights)
        validate_policy(policyplan,policyvalue['overrides']);policyvalue.update(program_changes=programupdates,changed_at=stamp)
        write('policy_profile','manual_policy',POLICY,policyvalue,'POLICY_PROFILE_UPDATED')
        for p in plan['projects']:
            row=db.scalar(select(Mapping).where(Mapping.project_id==p['id']).with_for_update())
            before={k:getattr(row,k) for k in ('policy_id','program_id','status','basis','evidence_url','revision_no')}
            row.status='CONFIRMED';row.basis='사용자 입력 · '+ACTOR+' · '+REASON;row.reviewed_at=now();row.revision_no+=1
            after=dict({k:getattr(row,k) for k in before},**stampmeta)
            db.add(Audit(entity_id=p['id'],action='PROJECT_PROGRAM_REVIEW',before=before,after=after));counts['project_mapping']+=1
            old=current('project_profile','manual_project',p['id']);value=deepcopy(old.payload) if old else dict(project_id=p['id'],approvals={})
            value.update(overrides=p['overrides'],progress=p['progress'],remaining=p['remaining'],completion_decisions=p.get('decisions',[]),last_changes=dict(mapping=dict(before=before,after=after),fields={k:v['value'] for k,v in p['overrides'].items()},progress=p['progress']))
            write('project_profile','manual_project',p['id'],value,'PROJECT_PROFILE_UPDATED')
            for stage,t in p['targets'].items():
                old=current('execution_schedule','officer',p['id']+':'+stage)
                if old and old.payload.get('status')!='RELEASED':continue
                goal=dict(t,project_id=p['id'],policy_id=POLICY,stage=stage,status='CONFIRMED',basis=REASON,responsible_org=ACTOR,evidence_url=p['evidence_url'],name=p['name'],region=p['region'],shift_days=0)
                goal['baseline']=dict(due_date=t['due_date'],units=t['units'],basis=REASON,accepted_on=today().isoformat(),label='담당자 채택 기준선 · 최초 원천계획과 구분')
                write('execution_schedule','officer',p['id']+':'+stage,goal,'EXECUTION_SCHEDULE')
        # Confirm only already selected/proposed links; do not select a new candidate.
        for old in list(db.scalars(select(Revision).where(Revision.kind.in_(['stage_evidence','evidence_bridge','collection_link']),Revision.superseded_at.is_(None)))):
            v=deepcopy(old.payload)
            if v.get('project_id') not in pids or v.get('status') in ('RELEASED','REJECTED'):continue
            if old.kind=='stage_evidence' and not v.get('selected'):continue
            if old.kind=='collection_link' and not v.get('links'):continue
            v.update(status='CONFIRMED',reviewed=True,review_basis=REASON,reviewed_on=today().isoformat(),**stampmeta)
            if old.kind=='stage_evidence':
                v['selected']=dict(v['selected'],original_method=v['selected'].get('method'),method='OFFICER_CONFIRMATION',basis='담당자 확인 · '+ACTOR+' · '+REASON+' · '+(v['selected'].get('basis') or ''))
            for link in v.get('links',[]):link.update(review_status='CONFIRMED',**stampmeta)
            key=v['project_id']+':'+(v['source_entity_id'] if old.kind=='evidence_bridge' else v['stage'])
            write(old.kind,old.source_id,key,v,'EVIDENCE_BRIDGE_REVIEW' if old.kind=='evidence_bridge' else 'OFFICER_LINK_CONFIRMED')
        write('officer_completion','manual',BATCH,dict(summary=plan['summary'],counts=dict(counts),changed_at=stamp,project_ids=sorted(pids)),'OFFICER_BATCH_COMPLETED')
    return dict(applied=True,counts=dict(counts),summary=plan['summary'])


def distribute(total,weights):
    """Integer apportionment without losing households through rounding."""
    total=max(0,int(total));weights={k:max(0,float(v or 0)) for k,v in weights.items()}
    denom=sum(weights.values())
    if not denom:weights={k:1 for k in weights};denom=len(weights)
    if not denom:return {}
    raw={k:total*v/denom for k,v in weights.items()};out={k:int(v) for k,v in raw.items()}
    for k in sorted(weights,key=lambda k:raw[k]-out[k],reverse=True)[:total-sum(out.values())]:out[k]+=1
    return out


def complete_values(p,cells,value,stamp,duration=1095,parent=None):
    """Explicit user-authorized completion; every assumption carries its derivation.

    Missing measurement fields equal their own due targets, explicitly marked as
    estimates. Collected measurements, including zero, are preserved.
    """
    cap=p['planned_units'];parent=parent or {};progress=value['progress'];targets=value['targets']
    decisions=deepcopy(value['remaining'])
    # Resolve conflicting/partial original values by exact project scope first,
    # dated official evidence second, and latest event last. Preserve all originals.
    for stage in STAGES:
        c=cells['CONSTRUCTION' if stage=='COMPLETION' else stage]
        candidates=[r for r in c.get('sources',[]) if r.get('kind')=='ACTUAL' and r.get('pct') is None
                    and (r.get('milestone')==stage or not r.get('milestone') and stage!='COMPLETION')
                    and normalized(r.get('date')) and normalized(r['date'])<=today().isoformat()]
        if stage not in progress and candidates:
            r=max(candidates,key=lambda r:(not r.get('scope_partial'),r.get('units')==cap,r.get('review_status')=='CONFIRMED',r.get('source_revision_no') or 0,r['date']))
            units=r.get('units');units=min(cap,units) if type(units) is int and units>=0 else cap
            progress[stage]=dict(meta(stamp,'BEST_SOURCE_SELECTED','동일 사업 범위·확정 연결·최신 판본 우선 선택; 원천 간 상충값은 상세 근거 보존',True),event_date=normalized(r['date']),units=units,evidence_url=r.get('evidence_url'))
        if stage in progress and progress[stage].get('units') is None:
            progress[stage].update(units=cap,inferred=True)
            progress[stage].setdefault('field_provenance',{})['units']=dict(rule='SCOPE_RECONCILIATION',basis='사업 총 목표량을 초과하는 타 범위 원천 대신 현재 사업 총량을 채택',value=cap)
    def shift(d,days):return (date.fromisoformat(d)+timedelta(days=days)).isoformat()
    def known(stage):return targets.get(stage,{}).get('due_date') or progress.get(stage,{}).get('event_date')
    start=known('CONSTRUCTION')
    if not start:
        completion=known('COMPLETION') or (shift(known('MOVE_IN'),-90) if known('MOVE_IN') else None)
        start=shift(completion,-duration) if completion else known('SUPPLY') or parent.get('period_end') or '2030-12-31'
    default={'BUSINESS':shift(start,-730),'APPROVAL':shift(start,-365),'CONSTRUCTION':start,'COMPLETION':shift(start,duration),'SUPPLY':shift(start,180),'MOVE_IN':shift(start,duration+90)}
    for stage in STAGES:
        if stage not in targets:
            day=progress.get(stage,{}).get('event_date') or default[stage]
            targets[stage]=dict(meta(stamp,'OFFICER_SCHEDULE_ESTIMATE',f'확인 일정·프로그램 종료일 기준 역산/순산. 비교 사업 공사기간 중앙값 {duration}일, 착공 전 사업화 730일·인허가 365일, 공급 착공 후 180일, 준공 후 입주 90일 가정',True),due_date=day,units=cap)
        if targets[stage].get('units') is None:targets[stage]['units']=cap
    def adjust(stage,day,why):
        original=targets[stage]['due_date'];targets[stage].update(due_date=day,inferred=True)
        targets[stage].setdefault('field_provenance',{})['due_date']=dict(rule='SEQUENCE_RECONCILIATION',previous_value=original,value=day,basis=why)
    # Preserve measured chronology; reconcile only adopted target dates.
    if targets['COMPLETION']['due_date']<=targets['CONSTRUCTION']['due_date']:adjust('COMPLETION',shift(targets['CONSTRUCTION']['due_date'],duration),'착공 이후 준공: 비교 사업 공사기간으로 목표 정합성 조정')
    if targets['MOVE_IN']['due_date']<targets['COMPLETION']['due_date']:adjust('MOVE_IN',shift(targets['COMPLETION']['due_date'],90),'준공 이후 입주: 90일 준비기간 적용')
    if targets['SUPPLY']['due_date']>targets['MOVE_IN']['due_date']:adjust('SUPPLY',targets['MOVE_IN']['due_date'],'공급 목표는 입주 목표 이내')
    bound=min(targets['CONSTRUCTION']['due_date'],targets['SUPPLY']['due_date'])
    if targets['APPROVAL']['due_date']>bound:adjust('APPROVAL',bound,'인허가 목표는 착공·공급 이전')
    if targets['BUSINESS']['due_date']>targets['APPROVAL']['due_date']:adjust('BUSINESS',targets['APPROVAL']['due_date'],'사업화 목표는 인허가 이전')
    from .measurement_estimates import reconcile
    progress=reconcile(progress,targets,cells,today(),scope_limit=cap)['progress']
    for record in progress.values():
        for key,metadata_value in meta(stamp,record['input_rule'],record['input_basis'],record['inferred']).items():record.setdefault(key,metadata_value)
    value['progress']=progress
    if not value['overrides'].get('progress_pct') and progress.get('CONSTRUCTION',{}).get('event_date'):
        start=date.fromisoformat(progress['CONSTRUCTION']['event_date']);end=date.fromisoformat(targets['COMPLETION']['due_date'])
        pct=100 if 'COMPLETION' in progress else min(99,max(0,round(100*(today()-start).days/max(1,(end-start).days),1)))
        for key,v in [('progress_pct',pct),('progress_date',today().isoformat())]:value['overrides'][key]=dict(meta(stamp,'TIME_PROGRESS_ESTIMATE','착공 확인/채택일과 준공 목표 사이 경과일 비율 · 담당자 추정 공정률',True),value=v)
    value['decisions']=decisions;value['remaining']=[]
    return value


def complete_goal_grid(values,overrides,stamp,weights):
    """Fill region/year goals without changing known numbers or exceeding totals."""
    regions=('서울특별시','경기도','인천광역시');years=list(range(int(values['period_start'][:4]),int(values['period_end'][:4])+1));cap=values['target_units']
    def put(k,v,basis):
        values[k]=v;overrides[k]=dict(meta(stamp,'GOAL_ALLOCATION_ESTIMATE',basis,True),value=v)
    missing=[r for r in regions if values.get('region:'+r) is None]
    remainder=cap-sum(values.get('region:'+r) or 0 for r in regions)
    for r,v in distribute(remainder,{r:weights.get(r,0) for r in missing}).items():put('region:'+r,v,'기존 지역 목표를 보존하고 잔여 목표를 등록 사업 규모 비율로 배분')
    missingyears=[y for y in years if values.get(f'annual:전체:{y}') is None]
    remainder=cap-sum(values.get(f'annual:전체:{y}') or 0 for y in years)
    for y,v in distribute(remainder,{y:1 for y in missingyears}).items():put(f'annual:전체:{y}',v,'연도별 목표 미확보분을 사업기간 내 균등 배분')
    available={r:values['region:'+r]-sum(values.get(f'annual:{r}:{y}') or 0 for y in years) for r in regions}
    for y in years:
        missing=[r for r in regions if values.get(f'annual:{r}:{y}') is None]
        amount=values[f'annual:전체:{y}']-sum(values.get(f'annual:{r}:{y}') or 0 for r in regions)
        allocations=distribute(amount,{r:available[r] for r in missing})
        for r,v in allocations.items():
            v=min(v,max(0,available[r]));put(f'annual:{r}:{y}',v,'해당 연도 전체 목표와 지역 잔여 총량에 비례 배분');available[r]-=v
    return values
