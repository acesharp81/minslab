"""Project editor: immutable source values, manual priority and atomic review history."""
from copy import deepcopy
from datetime import date
from calendar import monthrange
import hashlib
import json
import math
from sqlalchemy import select, text
from .db import Revision, Mapping, ProgramMapping, Audit, entity_id, upsert_revision, now
from .api_samples import today

POLICY = 'POL_2025_0907'
FIELDS = dict(name='사업명', overview='사업 개요', developer='시행사', contractor='시공사', address='위치·주소',
              planned_units='총 목표량 (호)', progress_pct='확인 공정률 (%)', progress_date='공정률 기준일')
STAGES = dict(BUSINESS='사업화', APPROVAL='인허가', CONSTRUCTION='착공', COMPLETION='준공', SUPPLY='공급·모집', MOVE_IN='입주 시작')

def profile(service, pid, as_of=None):
    return next((r for r in service.rows('project_profile', as_of) if r['project_id']==pid), {})

def overlay(service, rows, as_of=None):
    saved={r['project_id']:r for r in service.rows('project_profile',as_of)}
    schedules={}
    for r in service.rows('execution_schedule',as_of):
        if r.get('status')!='RELEASED':schedules.setdefault(r['project_id'],{})[r['stage']]=r
    for p in rows:
        p['managed_schedules']=schedules.get(p['id'],{})
        overrides=saved.get(p['id'],{}).get('overrides',{})
        if p.get('progress_pct') is not None and not p.get('progress_date'):p['progress_date']=p.get('base_date')
        p['source_values']={k:p.get(k) for k in FIELDS}
        p['manual_fields']=overrides
        p.update({k:v['value'] for k,v in overrides.items()})
    return rows

def fingerprint(cell):
    return hashlib.sha256(json.dumps(sorted(cell.get('sources',[]),key=lambda r:json.dumps(r,ensure_ascii=False,sort_keys=True)),ensure_ascii=False,sort_keys=True).encode()).hexdigest()

from .input_status import input_status,input_label

def target_default(cell, stage, saved=None):
    """Date input normalisation only; source precision and conflicting scopes survive."""
    if saved and saved.get('status')!='RELEASED':
        return dict(saved,precision='DAY',input_status=input_status(saved,cell.get('assessment'),True),display_note='입력값 · '+input_label(saved,cell.get('assessment'),True)+' · '+saved.get('actor','담당자'))
    choices=[]
    for t in cell.get('targets',[]):
        if t.get('reference_only') or t.get('scope_partial'):continue
        milestone=t.get('milestone')
        if milestone!=stage and (milestone or stage=='COMPLETION'):continue
        raw=t.get('date') or ''
        try:
            if len(raw)==7:
                year,month=map(int,raw.split('-'));normalized=f'{raw}-{monthrange(year,month)[1]:02d}';precision='MONTH'
            elif len(raw)==4:
                normalized=raw+'-12-31';precision='YEAR'
            elif len(raw)==10:normalized=date.fromisoformat(raw).isoformat();precision='DAY'
            else:continue
            date.fromisoformat(normalized)
        except (ValueError,TypeError):continue
        choices.append(dict(due_date=normalized,source_date=raw,precision=precision,units=t.get('units'),evidence_url=t.get('evidence_url')))
    if not choices:return dict(due_date='',units=None,display_note='원천 목표 일정 미확보 · 필요 시 입력')
    if len({c['due_date'] for c in choices})>1:return dict(due_date='',units=None,display_note='서로 다른 원천 일정 · 아래 근거 비교 후 입력')
    selected=choices[0]
    quantities={c['units'] for c in choices}
    selected['units']=next(iter(quantities)) if len(quantities)==1 else None
    selected['display_note']='원천 '+selected['source_date']+({'MONTH':' · 월 단위 → 월말 기준','YEAR':' · 연도 단위 → 연말 기준','DAY':' · 일 단위'}[selected['precision']])
    return selected

def stage_sources(cell,stage):
    return [r for r in cell.get('sources',[]) if (r.get('milestone')=='COMPLETION' if stage=='COMPLETION' else r.get('milestone')!='COMPLETION' if stage=='CONSTRUCTION' else True)]

def missing_progress_note(cell,stage):
    rows=stage_sources(cell,stage)
    if any(r.get('kind')=='STATE' for r in rows):return '상태 근거 확보 · 실적일·물량 미확인'
    if any(r.get('kind')=='DOCUMENT' for r in rows):return '문서 확보 · 실적일·물량 미확인'
    if any(r.get('kind')=='PLAN' for r in rows):return '예정 정보 확보 · 실제 이행 미확인'
    status=next((r.get('schedule_status') for r in rows if r.get('kind')=='PLAN_STATUS'),None)
    if status=='NOT_PROVIDED':return '원천 항목 미제공 · 추가 수집 필요'
    if status=='EMPTY':return '원천 공란 · 미정 여부 미확인'
    return '진행값 미확보'

def linked_progress(cell):
    candidates=[r for r in cell.get('sources',[]) if r.get('kind')=='ACTUAL' and not r.get('scope_partial')
                and type(r.get('pct')) in (int,float) and math.isfinite(r['pct']) and 0<=r['pct']<=100
                and len(r.get('date') or '')==10 and not r.get('manual_priority') and r.get('source_id')!='officer']
    latest=max((r['date'] for r in candidates),default=None)
    current=[r for r in candidates if r['date']==latest]
    if not current or len({r['pct'] for r in current})!=1:return None
    return current[0]

def progress_default(cell,stage,manual=None):
    if manual:return dict(manual,manual=True,input_status=input_status(manual,cell.get('assessment'),True),display_note='입력값 · '+input_label(manual,cell.get('assessment'),True)+' · '+manual['actor'])
    facts=[r for r in cell.get('sources',[]) if r.get('kind')=='ACTUAL'
           and r.get('pct') is None and not r.get('scope_partial') and (r.get('milestone')==stage or (not r.get('milestone') and stage!='COMPLETION'))]
    dates={r['date'] for r in facts if r.get('date') and len(r['date'])==10}
    units={r['units'] for r in facts if r.get('units') is not None}
    return dict(event_date=next(iter(dates)) if len(dates)==1 else '',units=next(iter(units)) if len(units)==1 else None,
                manual=False,display_note='원천 상충 · 근거 확인' if len(dates)>1 or len(units)>1 else
                '수집 실적 · 연결 검토 중' if any(r.get('review_status')=='REVIEW' for r in facts) else
                '수집 실적' if facts else missing_progress_note(cell,stage),has_evidence=bool(cell.get('sources')))

def progress_events(service,as_of=None):
    return [dict(v,project_id=r['project_id'],stage=stage,status='ACTUAL',review_status='CONFIRMED',basis=v['reason'])
            for r in service.rows('project_profile',as_of) for stage,v in r.get('progress',{}).items()
            if v.get('event_date') and v.get('units') is not None]


def view(service,pid,matrix,locations=None):
    projects=service.projects()
    current=next((p for p in projects if p['id']==pid),None)
    p=dict(deepcopy(current),history=service.history(pid),mapping_history=service.mapping_history(pid)) if current else None
    if not p:raise ValueError('사업을 찾을 수 없습니다')
    saved=profile(service,pid)
    cellrow=next((r for r in matrix['items'] if r['id']==pid),None)
    if cellrow is None:raise ValueError('선택 정책에 포함된 사업이 아닙니다')
    from .project_locations import resolve_anchor
    location=resolve_anchor(p,locations,next((r for r in service.rows('project_location') if r['project_id']==pid and r.get('status')!='RELEASED'),None))
    fields={}
    source_catalog=service.sources()
    source_meta=next((r for r in source_catalog if r['id']==p.get('source_id')), {})
    for k,label in FIELDS.items():
        source=dict(origin='SOURCE',value=p.get('source_values',{}).get(k),basis=p.get('unit_basis') if k=='planned_units' else p.get('schedule_basis') or '수집 원천의 해당 항목',evidence_url=(p.get('progress_evidence_url') or p.get('evidence_url')) if k in ('progress_pct','progress_date') else p.get('evidence_url'),base_date=p.get('base_date'),name=source_meta.get('name') or p.get('source_id'),collection_method='공개 API 조회' if source_meta.get('key_env') else '공식 원천 수집·항목 추출')
        manual=saved.get('overrides',{}).get(k)
        fields[k]=dict(label=label,value=p.get(k),manual=bool(manual),input_label=input_label(manual) if manual else None,evidence=([manual] if manual else [])+[source])
    if location:
        if not p.get('address') and location.get('address'):
            fields['address'].update(value=location['address'],linked=True,review_required=location['approximate'])
            fields['address']['evidence'].insert(0,dict(origin='LINKED_SOURCE',value=location['address'],basis=location['label'],name='대표 위치 원천 주소',collection_method='위치 원천의 원문 주소 연결',evidence_url=location.get('evidence_url'),review_status='REVIEW' if location['approximate'] else 'CONFIRMED'))
            p['address']=location['address']
        fields['address']['location']=location
        fields['address']['evidence'].append(dict(origin='LOCATION',value=(location.get('address') or location['label'])+f" · {location['latitude']:.6f}, {location['longitude']:.6f}",basis=location['label'],name='대표 위치 원천',collection_method='저장된 위치 근거·좌표 연결',evidence_url=location.get('evidence_url')))
    cells=deepcopy(cellrow['cells'])
    sources={r['id']:r for r in source_catalog}
    for cell in cells.values():
        for r in cell.get('sources',[]):
            source=sources.get(r.get('source_id'),{})
            mode=source.get('collection_mode','')
            r['collection_method']='담당자 입력' if r.get('source_id')=='officer' else ('공개 API 조회' if source.get('key_env') else '공식 파일·문서 수집' if mode in ('PUBLIC_FILE','HISTORY','LEGAL_PLAN_PILOT','PUBLIC_DOCUMENT') else '공식 웹 원천 수집')+' · 사업명·지역·블록 및 단계 근거 대조'
    linked=linked_progress(cells['CONSTRUCTION'])
    if linked and p.get('source_values',{}).get('progress_pct') is None:
        for key,rawkey in [('progress_pct','pct'),('progress_date','date')]:
            manual=saved.get('overrides',{}).get(key)
            evidence=dict(linked,origin='LINKED_SOURCE',value=linked[rawkey],base_date=linked['date'])
            # Preserve the absent original field as well as the linked source and manual override.
            fields[key]['evidence'].insert(1 if manual else 0,evidence)
            if not manual and (p.get(key) is None or key=='progress_pct'):
                fields[key].update(value=linked[rawkey],linked=True,review_required=linked.get('review_status')=='REVIEW')
                p[key]=linked[rawkey]
    for stage,c in cells.items():
        approved=saved.get('approvals',{}).get(stage)
        c['fingerprint']=fingerprint(cellrow['cells'][stage])
        c['review']=approved
        c['review_current']=bool(approved and approved['fingerprint']==c['fingerprint'])
    schedules={r['stage']:r for r in service.rows('execution_schedule') if r['project_id']==pid}
    programs=service.program_links(projects=projects)
    progress={stage:progress_default(cells['CONSTRUCTION' if stage=='COMPLETION' else stage],stage,saved.get('progress',{}).get(stage)) for stage in STAGES}
    defaults={stage:target_default(cells['CONSTRUCTION' if stage=='COMPLETION' else stage],stage,schedules.get(stage)) for stage in STAGES}
    for stage,v in progress.items():
        if not v.get('event_date') and v.get('units') is None and ((defaults[stage].get('due_date') or '')>today().isoformat() or cells['CONSTRUCTION' if stage=='COMPLETION' else stage].get('progress',{}).get('code') in ('NOT_REACHED_REPORTED','SCHEDULE_PENDING')):
            v.update(not_due=True,display_note='미도래·미진행 · 측정값 해당 없음')
        elif not v.get('event_date') and v.get('units') is None and saved.get('stage_states',{}).get(stage,{}).get('status')=='NOT_OBSERVED':
            v.update(not_observed=True,display_note='미측정 · 실적 근거 없음')
    raw_cells={stage:dict(c,targets=[r for r in c.get('targets',[]) if r.get('source_id')!='officer'],sources=[r for r in c.get('sources',[]) if not r.get('manual_priority')]) for stage,c in cells.items()}
    source_defaults={stage:dict(target=target_default(raw_cells['CONSTRUCTION' if stage=='COMPLETION' else stage],stage),progress=progress_default(raw_cells['CONSTRUCTION' if stage=='COMPLETION' else stage],stage)) for stage in STAGES}
    parent=next((r for r in programs if r['id']==p['mapping'].get('program_id')),None)
    from .supply_conditions import conditions
    supply_conditions=conditions(service,p,location,projects=projects)
    return dict(supply_conditions=supply_conditions,project=p,location=location,fields=fields,cells=cells,target_defaults=defaults,progress_defaults=progress,source_defaults=source_defaults,stages=matrix['stages'],schedule_stages=STAGES,schedules=schedules,
                programs=[r for r in programs if r['policy_id']==POLICY and r['status'] not in ('RELEASED','REJECTED')],
                parent=parent,revision_no=saved.get('revision_no',0),mapping_revision_no=p['mapping']['revision_no'],
                history=service.history(entity_id('project_profile','manual_project',pid)),as_of_date=today().isoformat())

def save(service,pid,revision_no,mapping_revision_no,changes,actor,reason,mapping=None,schedules=None,approvals=None,progress=None):
    if not actor.strip() or not reason.strip():raise ValueError('변경자와 사유를 입력하세요')
    if not any((changes,mapping,schedules,approvals,progress)):raise ValueError('변경 내용이 없습니다')
    p=next((p for p in service.projects() if p['id']==pid),None)
    if not p:raise ValueError('사업을 찾을 수 없습니다')
    from .projection_cache import projection_version
    observed_version=projection_version(service)
    checked={}
    if approvals:
        from .project_collection import collection_matrix
        matrix=collection_matrix(service,policy_id=POLICY)
        row=next((r for r in matrix['items'] if r['id']==pid),None)
        if not row:raise ValueError('정책 범위를 확인하세요')
        for stage,token in approvals.items():
            if stage not in row['cells']:raise ValueError('수집 단계 오류')
            if token is None:continue
            cell=row['cells'][stage]
            if not cell['sources']:raise ValueError('수집 근거가 없는 단계는 승인할 수 없습니다')
            if token!=fingerprint(cell):return dict(conflict=True)
            checked[stage]=token
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        if approvals and observed_version!=projection_version(service):return dict(conflict=True)
        link=db.scalar(select(Mapping).where(Mapping.project_id==pid).with_for_update())
        if link is None:raise ValueError('사업 연결 정보가 없습니다')
        if link.revision_no!=mapping_revision_no:return dict(conflict=True)
        old=db.scalar(select(Revision).where(Revision.entity_id==entity_id('project_profile','manual_project',pid),Revision.superseded_at.is_(None)).with_for_update())
        if revision_no!=(old.revision_no if old else 0):return dict(conflict=True)
        before=deepcopy(old.payload) if old else {}
        value=deepcopy(before) or dict(project_id=pid,overrides={},approvals={})
        stamp=now().isoformat();meta=dict(origin='MANUAL',actor=actor.strip(),reason=reason.strip(),changed_at=stamp)
        for k,v in changes.items():
            if k not in FIELDS:raise ValueError('수정할 수 없는 사업 항목입니다')
            if v is None:value['overrides'].pop(k,None);continue
            if k=='planned_units':
                if type(v) is not int or not 0<=v<=100000000:raise ValueError('목표량은 0~1억 사이 정수입니다')
            elif k=='progress_pct':
                if type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100:raise ValueError('공정률은 0~100입니다')
            elif k=='progress_date':
                if date.fromisoformat(v)>today():raise ValueError('공정률 기준일은 미래일 수 없습니다')
            elif not isinstance(v,str) or not v.strip() or len(v)>(4000 if k=='overview' else 500):raise ValueError('명칭·설명을 확인하세요')
            value['overrides'][k]=dict(meta,value=v)
        effective=dict(p.get('source_values',{}));effective.update({k:v['value'] for k,v in value['overrides'].items()})
        if 'progress_pct' in value['overrides'] and not effective.get('progress_date'):raise ValueError('입력 공정률의 기준일이 필요합니다')
        value.setdefault('progress',{})
        for stage,v in (progress or {}).items():
            if stage not in STAGES:raise ValueError('진행 단계 오류')
            if v is None:value['progress'].pop(stage,None);continue
            when=v.get('event_date') or '';units=v.get('units')
            if not when and units is None:raise ValueError('진행일 또는 진행량을 입력하세요')
            if when and not date(1900,1,1)<=date.fromisoformat(when)<=today():raise ValueError('진행일은 실제 확인한 과거·현재 일자입니다')
            if units is not None and (type(units) is not int or not 0<=units<=(effective.get('planned_units') if effective.get('planned_units') is not None else 100000000)):raise ValueError('진행량은 사업 목표량 이내 정수입니다')
            cap=effective.get('planned_units')
            value['progress'][stage]=dict(meta,event_date=when,units=units)
        cap=effective.get('planned_units')
        if cap is not None and any(v.get('units') is not None and v['units']>cap for v in value['progress'].values()):raise ValueError('기존 진행량보다 총 목표량을 줄일 수 없습니다')
        parent=db.get(ProgramMapping,link.program_id) if link.program_id else None
        if not parent or parent.policy_id!=POLICY or parent.status in ('RELEASED','REJECTED'):raise ValueError('9.7 정책 소속 사업만 편집할 수 있습니다')
        mapping_before=None
        if mapping:
            target=db.get(ProgramMapping,mapping.get('program_id'))
            if not target or target.policy_id!=POLICY or target.status in ('RELEASED','REJECTED'):raise ValueError('9.7 소속 프로그램을 선택하세요')
            if mapping.get('program_revision_no')!=target.revision_no:return dict(conflict=True)
            if mapping.get('status') not in ('CONFIRMED','REVIEW'):raise ValueError('연결 검토 상태를 확인하세요')
            mapping_before={k:getattr(link,k) for k in ('program_id','policy_id','status','revision_no','basis','evidence_url')}
            link.program_id=target.id;link.policy_id=POLICY;link.status=mapping['status'];link.revision_no+=1
            link.basis='사용자 입력 · '+actor.strip()+' · '+reason.strip();link.reviewed_at=now()
            mapping_after={k:getattr(link,k) for k in mapping_before}
        pending=[]
        for stage,s in (schedules or {}).items():
            if stage not in STAGES:raise ValueError('목표 단계 오류')
            key=pid+':'+stage;eid=entity_id('execution_schedule','officer',key)
            previous=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
            if s.get('revision_no')!=(previous.revision_no if previous else 0):raise ValueError('단계별 목표가 변경됐습니다. 다시 조회하세요')
            if s.get('reset'):
                if previous:pending.append((key,dict(previous.payload,status='RELEASED',base_date=today().isoformat(),**meta),previous.payload))
                continue
            due=date.fromisoformat(s.get('due_date','')).isoformat();units=s.get('units')
            if not 1900<=int(due[:4])<=2100:raise ValueError('목표 연도 범위를 확인하세요')
            if units is not None and (type(units) is not int or units<0 or units> (effective.get('planned_units') if effective.get('planned_units') is not None else 100000000)):raise ValueError('단계 목표량은 사업 목표량 이내여야 합니다')
            baseline=previous.payload.get('baseline') if previous else None
            schedule=dict(project_id=pid,policy_id=POLICY,stage=stage,due_date=due,units=units,status='CONFIRMED',basis=reason.strip(),responsible_org=actor.strip(),origin='MANUAL',evidence_url=p.get('evidence_url'),base_date=today().isoformat(),name=effective.get('name'),region=p['region'],**{k:v for k,v in meta.items() if k!='origin'})
            schedule['baseline']=baseline or dict(due_date=due,units=units,basis=reason.strip(),accepted_on=today().isoformat(),label='사업정보 담당자 승인 기준선')
            schedule['shift_days']=(date.fromisoformat(due)-date.fromisoformat(schedule['baseline']['due_date'])).days
            pending.append((key,schedule,previous.payload if previous else {}))
        active={r.payload['stage']:r.payload for r in db.scalars(select(Revision).where(Revision.kind=='execution_schedule',Revision.superseded_at.is_(None))) if r.payload.get('project_id')==pid and r.payload.get('status')!='RELEASED'}
        for _,schedule,_ in pending:
            if schedule['status']=='RELEASED':active.pop(schedule['stage'],None)
            else:active[schedule['stage']]=schedule
        cap=effective.get('planned_units')
        if cap is not None and any(r.get('units') is not None and r['units']>cap for r in active.values()):raise ValueError('기존 단계 목표량보다 총 목표량을 줄일 수 없습니다. 단계 목표도 함께 조정하세요')
        if 'CONSTRUCTION' in active and 'COMPLETION' in active and active['CONSTRUCTION']['due_date']>=active['COMPLETION']['due_date']:raise ValueError('준공 목표일은 착공 목표일 이후여야 합니다')
        for stage,token in (approvals or {}).items():
            if token is None:value['approvals'].pop(stage,None)
            else:value['approvals'][stage]=dict(meta,fingerprint=checked[stage])
        value['last_changes']=dict(fields=changes,mapping=dict(before=mapping_before,after=mapping_after) if mapping_before else None,schedules=[dict(before=prior,after=schedule) for _,schedule,prior in pending],approvals=approvals or {},progress=progress or {})
        value.update(base_date=today().isoformat(),actor=actor.strip(),reason=reason.strip())
        record,_=upsert_revision(db,'project_profile','manual_project',pid,value,'manual')
        db.add(Audit(entity_id=record.entity_id,action='PROJECT_PROFILE_UPDATED',before=before,after=value))
        if mapping_before:db.add(Audit(entity_id=pid,action='PROJECT_PROGRAM_REVIEW',before=mapping_before,after=mapping_after))
        for key,schedule,prior in pending:
            r,_=upsert_revision(db,'execution_schedule','officer',key,schedule,'manual')
            db.add(Audit(entity_id=r.entity_id,action='EXECUTION_SCHEDULE',before=prior,after=schedule))
        return dict(project_id=pid,revision_no=record.revision_no)
