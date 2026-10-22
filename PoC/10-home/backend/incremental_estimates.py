"""Incremental officer estimates for newly connected projects, never raw events."""
from copy import deepcopy
from datetime import date, timedelta
from statistics import median
import re

from sqlalchemy import select, text
from .db import Audit, Mapping, Revision, entity_id, now, upsert_revision
from .independent_metrics import digest
from .officer_completion import project_values, complete_values, normalized, POLICY
from .officer_duration import refine_project
from .project_profile import STAGES
from .schedule_period import schedule_period


def ih_inputs(project):
    """Read explicit stored source fields. A business schedule is always a plan."""
    fields = project.get('source_fields') or {}
    amount = fields.get('공급규모', '')
    match = re.fullmatch(r'([\d,]+)\s*세대\s*(?:\([^()]*\))?', amount)
    units = int(match[1].replace(',', '')) if match else None
    plans = []
    for m in re.finditer(r'(착공|준공)\s*(?:\(예정\))?\s*((?:20)?\d{2}년\s*(?:[상하]반기|\d{1,2}월))', fields.get('사업일정', '')):
        label = re.sub(r'^(\d{2})년', r'20\1년', m[2])
        period = schedule_period(label)
        if period:
            plans.append(dict(stage='CONSTRUCTION' if m[1]=='착공' else 'COMPLETION',
                due_date=period['due_date'], precision=period['precision'], original_schedule=m[2],
                date_conversion=period['conversion'], basis='저장된 iH 사업일정 원문 · 실제 사건과 구분',
                source_entity_id=project['id'], source_revision_id=project['source_revision_id'],
                evidence_url=project.get('evidence_url'), review_status='SOURCE'))
    return units, plans


def values(project, cells, model, stamp, actor, reason, reference, anchors=(), peer_units=()):
    """Reuse the existing completion/duration models for one new project only."""
    p=deepcopy(project); c=deepcopy(cells); cap=p.get('planned_units'); cap_proof=None
    own_plans=[]
    if p.get('source_id')=='ih_notice':
        explicit,own_plans=ih_inputs(p)
        if cap is None and explicit is not None:
            cap=explicit;cap_proof=dict(rule='STORED_EXPLICIT_CAPACITY',field='공급규모',
                basis='동일 iH 원문에 명시된 총 공급규모 채택',inferred=False)
    if cap is None:
        known=[v for v in peer_units if type(v) is int and v>0]
        if not known:raise ValueError('규모 추정 비교 표본이 없습니다: '+p['name'])
        cap=int(median(known));cap_proof=dict(rule='PROJECT_CAPACITY_ESTIMATE',
            basis='동일 프로그램 또는 정책의 원천 사업규모 중앙값',inferred=True,sample_units=known)
    p['planned_units']=cap
    all_anchors=own_plans+list(anchors)
    for f in p.get('facts',[]):
        stage=f.get('milestone') or f.get('stage')
        if f.get('kind')=='PLAN' and stage in STAGES and normalized(f.get('date')):
            all_anchors.append(dict(stage=stage,due_date=normalized(f['date']),
                precision=f.get('date_precision','DAY'),original_schedule=f.get('original_schedule') or f['date'],
                date_conversion='PERIOD_END',basis=f['basis'],source_entity_id=p['id'],
                source_revision_id=p['source_revision_id'],evidence_url=p.get('evidence_url'),review_status='SOURCE'))
    # Keep one source date per stage; conflicting dates remain explicit blockers.
    accepted={};conflicts=[]
    for stage in STAGES:
        choices=[a for a in all_anchors if a['stage']==stage]
        days={a['due_date'] for a in choices}
        if len(days)>1:
            conflicts.append(dict(stage=stage,dates=sorted(days),basis='저장 원천 일정 상충 · 앵커 채택 보류'))
        elif choices:
            accepted[stage]=choices[0]
            cell=c['CONSTRUCTION' if stage=='COMPLETION' else stage]
            if stage in ('CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'):
                cell['targets']=[t for t in cell.get('targets',[]) if (t.get('milestone') or stage)!=stage]
                cell['targets'].append(dict(date=choices[0]['due_date'],units=cap,
                    milestone=stage,evidence_url=choices[0].get('evidence_url')))
            else:
                # Candidate event dates are estimation anchors, not new raw events.
                cell['sources'].append(dict(kind='ACTUAL',date=choices[0]['due_date'],units=cap,
                    milestone=stage,evidence_url=choices[0].get('evidence_url'),estimation_anchor=True))
    base=project_values(p,c,stamp)
    if not any(s in accepted for s in ('CONSTRUCTION','COMPLETION')) and 'CONSTRUCTION' not in base['targets']:
        approval=base['progress'].get('APPROVAL',{}).get('event_date') or base['targets'].get('APPROVAL',{}).get('due_date')
        if approval:
            due=(date.fromisoformat(approval)+timedelta(days=model['APPROVAL_CONSTRUCTION']['mean_days'])).isoformat()
            base['targets']['CONSTRUCTION']=dict(due_date=due,units=cap,inferred=True,
                input_rule='OFFICER_AVERAGE_DURATION',input_basis='저장 인허가일 + 수집 표본의 인허가→착공 평균 소요기간',
                field_provenance={'due_date':dict(rule='APPROVAL_TO_CONSTRUCTION',from_date=approval,
                    days=model['APPROVAL_CONSTRUCTION']['mean_days'])})
    result=complete_values(p,c,base,stamp,model['CONSTRUCTION_COMPLETION']['mean_days'])
    # complete_values can resolve several approval amendments to a dated source
    # after project_values found them conflicting. Use that date before falling
    # back to a generic 2030 deadline.
    approval=result['progress'].get('APPROVAL',{}).get('event_date')
    if approval and not any(s in accepted for s in ('CONSTRUCTION','COMPLETION')):
        result['targets']['CONSTRUCTION'].update(
            due_date=(date.fromisoformat(approval)+timedelta(days=model['APPROVAL_CONSTRUCTION']['mean_days'])).isoformat(),
            inferred=True,input_rule='OFFICER_AVERAGE_DURATION',
            input_basis='저장 인허가일 + 수집 표본의 인허가→착공 평균 소요기간')
    # Existing duration refinement respects explicit source dates; other dates
    # follow the same collected interval averages as the original 197 projects.
    changes,calculation=refine_project(p,result['targets'],dict(progress=result['progress']),model)
    result['targets'].update(changes)
    for stage,t in result['targets'].items():
        a=accepted.get(stage)
        if a:
            t.update(due_date=a['due_date'],input_rule='SOURCE_ACCEPTED',inferred=False,
                source_anchor=a,evidence_url=a.get('evidence_url'),date_precision=a.get('precision','DAY'),
                source_date_label=a.get('original_schedule') or a['due_date'],
                input_basis=a.get('basis','저장 원천 일정 채택')+' · 원문 '+str(a.get('original_schedule') or a['due_date'])+' · 범위 일정은 마지막 날을 관리 기준으로 사용')
    from .stage_chronology import constrain_estimated_dates
    result['sequence_date_corrections']=constrain_estimated_dates(result['targets'],'due_date')
    from .measurement_estimates import reconcile
    result['progress']=reconcile(result['progress'],result['targets'],c,reference,scope_limit=cap)['progress']
    progress=result['progress']
    for field in ('progress_pct','progress_date'):result['overrides'].pop(field,None)
    if 'CONSTRUCTION' in progress:
        start=date.fromisoformat(progress['CONSTRUCTION']['event_date']);end=date.fromisoformat(result['targets']['COMPLETION']['due_date'])
        pct=100 if 'COMPLETION' in progress else min(99,max(0,round(100*(reference-start).days/max(1,(end-start).days),1)))
        for field,value in [('progress_pct',pct),('progress_date',reference.isoformat())]:
            result['overrides'][field]=dict(value=value,inferred=True,input_rule='TIME_PROGRESS_ESTIMATE',
                input_basis='추정 착공일~준공 목표 사이의 경과일 비율 · 실제 공정률 아님')
    if cap_proof:
        result['overrides']['planned_units']=dict(value=cap,inferred=cap_proof['inferred'],
            input_rule=cap_proof['rule'],input_basis=cap_proof['basis'],field_provenance={'value':dict(cap_proof,value=cap,
                rule='SOURCE_ACCEPTED' if not cap_proof['inferred'] else cap_proof['rule'],derivation_rule=cap_proof['rule'])})
    for records in (result['overrides'],result['targets'],result['progress']):
        for record in records.values():record.update(origin='MANUAL',actor=actor,reason=reason,changed_at=stamp)
    result.update(project_id=p['id'],name=p['name'],region=p['region'],policy_id=POLICY,
        planned_units=cap,source_anchors=accepted,anchor_conflicts=conflicts,calculation=calculation,
        model={k:{f:v[f] for f in ('sample_count','mean_days','origin')} for k,v in model.items()},
        stage_states={s:dict(status='NOT_OBSERVED',actor=actor,reason=reason,
            basis='미도래 또는 관측 근거 미확보 · 목표만 산정') for s in STAGES if s not in progress})
    return result


def apply(service, plan, batch_id, actor, reason):
    """Atomically append only declared missing overlays; never re-review mappings."""
    if not actor.strip() or not reason.strip() or not plan['projects']:raise ValueError('적용 대상과 담당자·사유가 필요합니다')
    signature=digest(dict(plan=plan,actor=actor,reason=reason))
    marker=entity_id('officer_completion','manual',batch_id)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':
            for lock in (9072026,1019081):db.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
        old=db.scalar(select(Revision).where(Revision.entity_id==marker,Revision.superseded_at.is_(None)))
        if old:
            if old.payload.get('plan_digest')!=signature:raise ValueError('기존 적용안과 다릅니다')
            return dict(old.payload,unchanged=True)
        if len({p['project_id'] for p in plan['projects']})!=len(plan['projects']):raise ValueError('중복 대상')
        for p in plan['projects']:
            mapping=db.scalar(select(Mapping).where(Mapping.project_id==p['project_id']).with_for_update())
            if not mapping or mapping.status!='CONFIRMED' or mapping.policy_id!=p.get('policy_id',POLICY) or mapping.revision_no!=p['mapping_revision_no']:
                raise ValueError('사업 연결이 변경됐습니다: '+p['name'])
            for ref in p['pinned_inputs']:
                query=select(Revision).where(Revision.entity_id==ref['entity_id'])
                query=query.where(Revision.id==ref['revision_id'],Revision.kind=='officer_duration_model') if ref.get('historical_model') else query.where(Revision.superseded_at.is_(None))
                r=db.scalar(query)
                if not r or r.id!=ref['revision_id']:raise ValueError('추정 근거 판본이 변경됐습니다: '+p['name'])
            keys=[entity_id('project_profile','manual_project',p['project_id'])]+[entity_id('execution_schedule','officer',p['project_id']+':'+s) for s in STAGES]
            if db.scalar(select(Revision.id).where(Revision.entity_id.in_(keys),Revision.superseded_at.is_(None)).limit(1)):
                raise ValueError('기존 입력을 덮어쓸 수 없습니다: '+p['name'])
        counts={'project_profile':0,'execution_schedule':0}
        def write(kind,sid,key,payload,action):
            payload=dict(payload,actor=actor,reason=reason,batch_id=batch_id,base_date=plan['reference_date'])
            r,_=upsert_revision(db,kind,sid,key,payload,batch_id)
            db.add(Audit(entity_id=r.entity_id,action=action,before={},after=payload))
            if kind in counts:counts[kind]+=1
        for p in plan['projects']:
            value=deepcopy({k:p[k] for k in ('project_id','overrides','progress','stage_states','source_anchors','anchor_conflicts','calculation','model')})
            value.update(approvals={},remaining=[],last_changes=dict(scope='추가 연결 사업의 누락된 추정값 보완',
                fields={k:v['value'] for k,v in p['overrides'].items()},progress=p['progress']),
                source_input_manifest=p['pinned_inputs'])
            for records in (value['overrides'],value['progress']):
                for r in records.values():r['batch_id']=batch_id
            write('project_profile','manual_project',p['project_id'],value,'PROJECT_PROFILE_UPDATED')
            for stage,t in p['targets'].items():
                goal=dict(t,project_id=p['project_id'],policy_id=p.get('policy_id',POLICY),stage=stage,status='CONFIRMED',
                    responsible_org=actor,basis=reason,name=p['name'],region=p['region'],
                    evidence_url=t.get('evidence_url') or p['evidence_url'],shift_days=0,
                    baseline=dict(due_date=t['due_date'],units=t['units'],basis=reason,
                        accepted_on=plan['reference_date'],label='추가 사업 담당자 채택 기준선'))
                write('execution_schedule','officer',p['project_id']+':'+stage,goal,'EXECUTION_SCHEDULE')
        payload=dict(plan_digest=signature,project_ids=sorted(p['project_id'] for p in plan['projects']),
            counts=counts,summary=plan['summary'],actual_events_created=0,actor=actor,reason=reason)
        write('officer_completion','manual',batch_id,payload,'OFFICER_BATCH_COMPLETED')
    return payload
