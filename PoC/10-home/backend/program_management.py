"""Program target versus enumerated delivery plans, never convert missing data to zero."""
from datetime import date
from .policy_delivery_comparison import _schedule_targets

KINDS={'TARGET':'공식 목표','APPROXIMATE':'약량 목표','LOWER_BOUND':'최소 목표 + 추가분 미정','EFFECT':'사업 촉진·제도지원 효과'}

def members(model,pid):
    return [c for c in model.get('portfolio_cohorts',model.get('cohorts',[])) if c.get('program_id')==pid]

def assessment(pid,values,source,model,projects=None):
    selected=[p for p in (projects or []) if p.get('mapping',{}).get('program_id')==pid and p['mapping'].get('status')!='RELEASED']
    cs=members(model,pid);metric=values['metric'];start=values['period_start'];end=values['period_end'];unit=values['unit'];kind=source.get('target_kind','TARGET')
    rows=[];points=[]
    for c in cs:
        cap=c.get('planned_units',c.get('units'))
        capacity_only=metric=='CAPACITY' and unit=='호'
        plans=_schedule_targets([dict(c,schedules=c.get('schedules',[]))],metric,start) if not capacity_only and unit=='호' else []
        inside=[p for p in plans if start<=p['date']<=end]
        amount=cap if capacity_only else inside[-1]['units'] if inside and unit=='호' else None
        status='AVAILABLE' if amount is not None else 'OUTSIDE_PERIOD' if plans else 'SCHEDULE_NOT_ACQUIRED'
        rows.append(dict(id=c.get('id'),name=c['name'],region=c['region'],capacity=cap,period_plan_units=amount,status=status,mapping_status=c.get('mapping_status','REVIEW'),evidence_url=c.get('evidence_url'),schedule_points=inside))
        points.extend(inside)
    known_caps=[r['capacity'] for r in rows if r['capacity'] is not None]
    available=[r for r in rows if r['period_plan_units'] is not None]
    # An empty program means an unenumerated inventory, never a zero-house target.
    total=sum(r['period_plan_units'] for r in available) if available else None
    excluded=max(0,len(selected)-len({sid for c in cs for sid in c.get('source_ids',[c.get('id')])}))
    missing=sum(r['status']=='SCHEDULE_NOT_ACQUIRED' for r in rows)
    complete=bool(rows) and len(available)==len(rows) and not excluded and all(p.get('planned_units') is not None for p in selected)
    comparable=unit=='호' and kind!='EFFECT'
    cap_total=sum(known_caps) if known_caps and unit=='호' else None
    target=values.get('target_units')
    gap=target-total if comparable and target is not None and total is not None else None
    capacity_gap=target-cap_total if comparable and target is not None and cap_total is not None else None
    allowed=comparable and complete and total is not None and total>0
    basis=source.get('management',{})
    return dict(target_mode=values.get('target_mode','INDEPENDENT'),target_kind=kind,target_kind_label=KINDS.get(kind,kind) if source.get('fields',{}).get('target_units') is not None else '목표 미확보' if target is None else '담당자 목표',
        management_target=target,unit=unit,metric=metric,period_start=start,period_end=end,
        capacity_units=cap_total,capacity_gap_units=capacity_gap,period_plan_units=total,plan_gap_units=gap,
        subtotal_status='COMPLETE' if complete else 'PARTIAL' if total is not None else 'NOT_ACQUIRED',
        selected_source_count=len(selected),counted_project_count=len(rows),known_plan_count=len(available),
        review_project_count=sum(r['mapping_status']!='CONFIRMED' for r in rows),missing_quantity_count=sum(p.get('planned_units') is None for p in selected),
        missing_schedule_count=missing,outside_period_count=sum(r['status']=='OUTSIDE_PERIOD' for r in rows),unresolved_source_count=excluded,
        aggregate_allowed=allowed,case=basis.get('case','목표·사업계획 대조'),
        guidance=basis.get('guidance','관리목표를 유지하고 연결 사업의 같은 단계·기간 계획을 참고값으로 비교합니다.'),
        required_data=basis.get('required_data',[]),api_ids=basis.get('api_ids',[]),rows=rows,
        notice='사업 계획 차이는 지연 실적이 아닙니다. 검토 중 귀속 포함·누락 및 일정 미확보는 0으로 환산하지 않습니다. 프로그램 간 목표는 단순 합산하지 않습니다.')

def current_parts(cohorts,reference):
    totals={k:0 for k in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN','UNKNOWN')}
    for c in cohorts:
        if 'parts' in c:
            for k in totals:totals[k]+=c['parts'].get(k,0)
            continue
        active=[e for e in c.get('events',[]) if e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=reference]
        units=c['units'];supply=min(units,max((units if e.get('units') is None else e['units'] for e in active if e['stage']=='SUPPLY'),default=0))
        entry=any(e['stage']=='MOVE_IN' for e in active)
        if entry:supply=units
        totals['MOVE_IN' if entry else 'SUPPLY']+=supply;assigned=supply
        for stage in ('CONSTRUCTION','APPROVAL','BUSINESS'):
            reached=min(units,max((units if e.get('units') is None else e['units'] for e in active if e['stage']==stage),default=0))
            amount=max(0,reached-assigned);totals[stage]+=amount;assigned+=amount
        totals['UNKNOWN']+=units-assigned
    return totals

def scoped_model(service,program,model):
    """Use pinned source facts for programs outside the dedicated 9.7 policy ledger."""
    if not model.get('policy_id') or program['policy_id']==model['policy_id']:return model
    from collections import defaultdict
    from .supply_dashboard import inventory,block_key
    from .roadmap import source_events
    from .stage_evidence import linked_events
    from .evidence_bridge import by_project
    from .schedule_period import schedule_period
    reference=date.fromisoformat(model['as_of_date'])
    rows=[p for p in service.projects(as_of=reference) if p['mapping'].get('program_id')==program['id'] and p['mapping']['status']!='RELEASED']
    aliases={'lh_incheon_sale':'lh_sale','lh_incheon_rent':'lh_rent','lh_incheon_construction':'lh_construction'}
    rows=[dict(p,source_id=aliases.get(p['source_id'],p['source_id'])) for p in rows]
    selected,_=inventory(rows);groups=defaultdict(list)
    for p in rows:groups[block_key(p) or ('ID',p['id'])].append(p)
    links=linked_events(service,reference);bridges=by_project(service,reference)
    manual=[e for r in service.rows('delivery_setting',reference) for e in r.get('events',[])]
    portfolio=[]
    for p in selected:
        units=p.get('planned_units')
        if units is None or units<=0:continue
        group=groups[block_key(p) or ('ID',p['id'])];events=[];schedules=[]
        for row in group:
            for field,stage in (('start_actual_date','CONSTRUCTION'),('completion_actual_date','COMPLETION'),('move_in_actual_date','MOVE_IN')):
                if row.get(field) and row[field]<=reference.isoformat():events.append(dict(stage=stage,event_date=row[field],units=units,origin='SOURCE',evidence_url=row.get('evidence_url')))
            events.extend(links.get(row['id'],[]));events.extend(dict(e,origin='MANUAL') for e in manual if e['project_id']==row['id'])
            schedules.extend(dict(stage=e['stage'],due_date=e['due_date'],units=e['units'],origin='SOURCE',source_object_id=row['id'],source_base_date=row['base_date'],basis=e['basis'],evidence_url=e['evidence_url']) for e in source_events(row,reference))
            for bridge in bridges.get(row['id'],[]):
                for fact in bridge.get('facts',[]):
                    if fact.get('scope_partial'):continue
                    stage='COMPLETION' if fact.get('stage')=='CONSTRUCTION' and fact.get('milestone')=='COMPLETION' else fact.get('stage')
                    period=schedule_period(fact.get('date') or fact.get('date_label'))
                    if not period:continue
                    amount=fact.get('units') if fact.get('units') is not None else units
                    if fact.get('kind')=='ACTUAL' and fact.get('date') and fact['date']<=reference.isoformat():events.append(dict(stage=stage,event_date=fact['date'],units=amount,origin='LINKED_EVIDENCE',evidence_url=bridge.get('evidence_url')))
                    elif fact.get('kind')=='PLAN':schedules.append(dict(stage=stage,due_date=period['due_date'],units=amount,origin='SOURCE',source_object_id=bridge['source_entity_id'],source_base_date=row['base_date'],evidence_url=bridge.get('evidence_url'),basis=fact.get('basis')))
        portfolio.append(dict(id=p['id'],source_ids=[r['id'] for r in group],name=p['name'],region=p['region'],units=units,planned_units=units,program_id=program['id'],mapping_status=p['mapping']['status'],events=events,schedules=schedules,evidence_url=p.get('evidence_url')))
    return dict(model,policy_id=program['policy_id'],portfolio_cohorts=portfolio,cohorts=portfolio)
