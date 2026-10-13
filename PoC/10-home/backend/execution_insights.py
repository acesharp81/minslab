"""Evidence-based schedule review. Missing observations never mean zero output."""
from collections import Counter, defaultdict
from datetime import date
from .schedule_period import schedule_period
from .api_samples import today

STAGES = ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN')
LABELS = dict(BUSINESS='사업화',APPROVAL='인허가',CONSTRUCTION='착공',SUPPLY='분양·모집',COMPLETION='준공',MOVE_IN='입주 시작')


def milestone(e, stage):
    if stage not in ('CONSTRUCTION','COMPLETION'):return True
    kind = e.get('milestone') or e.get('event_type')
    if stage=='COMPLETION':return kind in ('COMPLETION','COMPLETE','USE_APPROVAL')
    return kind in ('CONSTRUCTION','START','STARTED','CONSTRUCTION_START')


def confirmed_observation(cell, stage, reference, capacity):
    rows=[]
    for e in cell.get('sources',[]):
        if e.get('kind')!='ACTUAL' or e.get('scope_partial') or e.get('review_status') in ('REVIEW','RELEASED'):continue
        if e.get('method') in ('PREREQUISITE','STAGE_INFERENCE') or not milestone(e,stage):continue
        stamp=e.get('date')
        if not stamp or len(stamp)!=10:continue
        try:d=date.fromisoformat(stamp)
        except ValueError:continue
        if d>reference:continue
        rows.append(e)
    if not rows:return dict(date=None,units=None,evidence_url=None)
    # Complete stage milestones describe the whole project. Supply quantities
    # must be explicit; a recruitment record is not whole-project completion.
    amounts=[e.get('units') for e in rows if e.get('units') is not None]
    amount=max(amounts) if amounts else capacity if stage not in ('SUPPLY',) else None
    if capacity is not None and amount is not None:amount=min(capacity,amount)
    qualifying=[e for e in rows if amount is None or (e.get('units') if e.get('units') is not None else capacity) is not None and (e.get('units') if e.get('units') is not None else capacity)>=amount]
    dated=min(qualifying or rows,key=lambda e:e['date'])
    return dict(date=dated['date'],units=amount,evidence_url=dated.get('evidence_url'))


def summarize(rows, key):
    groups=defaultdict(list)
    for row in rows:groups[row.get(key) or '미확인'].append(row)
    result=[]
    for name,items in sorted(groups.items()):
        quantities={}
        for r in items:
            if r['status'] in ('DELAYED','PLAN_DELAY','VERIFY') and r.get('planned_units') is not None:
                quantities[r['project_id']]=max(quantities.get(r['project_id'],0),r['planned_units'])
        result.append(dict(name=name,total=len(items),statuses=dict(Counter(r['status'] for r in items)),
            affected_known_units=sum(quantities.values()),unknown_units=sum(r.get('planned_units') is None for r in items)))
    return result


def build(service, matrix, reference=None):
    reference=reference or today()
    projects={p['id']:p for p in service.projects(policy_id='POL_2025_0907',as_of=reference)}
    schedules={(r['project_id'],r['stage']):r for r in service.rows('execution_schedule',reference) if r.get('status')!='RELEASED'}
    assignments={(r['project_id'],r['stage']):r for r in service.rows('execution_agency',reference) if r.get('status')!='RELEASED'}
    rows=[];agency_comparisons=[]
    for p in matrix['items']:
        raw=projects.get(p['id'],{});capacity=raw.get('planned_units')
        for stage in STAGES:
            cell=p['cells'].get('CONSTRUCTION' if stage=='COMPLETION' else stage,{})
            schedule=schedules.get((p['id'],stage),{})
            assignment=assignments.get((p['id'],stage),{})
            plans=[]
            for t in cell.get('targets',[]):
                if t.get('scope_partial') or t.get('reference_only') or not milestone(t,stage):continue
                period=schedule_period(t.get('date') or t.get('date_label'))
                if period:plans.append(dict(t,period=period))
            selected=min(plans,key=lambda t:t['period']['due_date'],default={})
            period=schedule_period(schedule.get('due_date')) if schedule else selected.get('period')
            original=schedule.get('baseline')
            baseline=original.get('due_date') if original else None
            due=period['due_date'] if period else None
            actual=confirmed_observation(cell,stage,reference,capacity)
            # Native source milestones have explicit event meanings.
            field={'CONSTRUCTION':'start_actual_date','COMPLETION':'completion_actual_date','MOVE_IN':'move_in_actual_date'}.get(stage)
            native=raw.get(field) if field else None
            if native and len(native)==10 and native<=reference.isoformat() and not actual['date']:
                actual=dict(date=native,units=capacity,evidence_url=raw.get('completion_evidence_url') if stage=='COMPLETION' else raw.get('evidence_url'))
            if not (due or baseline or actual['date'] or assignment):continue
            target=schedule.get('units') if schedule.get('units') is not None else selected.get('units') if selected.get('units') is not None else capacity
            fully_observed=actual['date'] and (target is None or actual['units'] is not None and actual['units']>=target)
            shift=(date.fromisoformat(due)-date.fromisoformat(baseline)).days if due and baseline else None
            delay=(date.fromisoformat(actual['date'])-date.fromisoformat(baseline)).days if baseline and fully_observed else None
            if delay is not None:status='DELAYED' if delay>0 else 'ON_TIME'
            elif shift is not None and shift>0:status='PLAN_DELAY'
            elif due and due<reference.isoformat() and not fully_observed:status='VERIFY'
            elif fully_observed:status='OBSERVED'
            elif due:status='UPCOMING'
            else:status='NO_BASELINE'
            row=dict(project_id=p['id'],name=p['name'],region=p['region'],municipality=p.get('municipality'),stage=stage,
                responsible_org=assignment.get('responsible_org') or schedule.get('responsible_org') or raw.get('developer') or '미확인',
                cooperating_orgs=assignment.get('cooperating_orgs',[]),baseline_date=baseline,current_date=due,
                actual_date=actual['date'],actual_units=actual['units'],planned_units=target,capacity=capacity,
                status=status,shift_days=shift,delay_days=delay,elapsed_days=max(0,(reference-date.fromisoformat(due)).days) if due else None,
                precision=period.get('precision') if period else None,original_date=period.get('original') if period else None,
                plan_conflict=len({t['period']['due_date'] for t in plans})>1,
                basis=schedule.get('basis') or selected.get('basis'),evidence_url=actual.get('evidence_url') or schedule.get('evidence_url') or selected.get('evidence_url'),
                candidate_evidence_count=sum(e.get('kind')=='ACTUAL' and e.get('review_status')=='REVIEW' for e in cell.get('sources',[])))
            rows.append(row)
            if assignment:
                amount=assignment['units']; observed=actual['units']
                comparison=dict(assignment,actual_date=actual['date'],observed_units=observed,
                    gap_units=max(0,amount-observed) if observed is not None else None,
                    achievement_percent=round(observed/amount*100,1) if observed is not None and amount else None,
                    comparison_status='REVIEW' if assignment['status']!='CONFIRMED' else 'VERIFY' if observed is None or observed<amount and assignment['due_date']<reference.isoformat() else 'REACHED' if observed>=amount else 'UPCOMING')
                agency_comparisons.append(comparison)
    agency_groups=defaultdict(list)
    for r in agency_comparisons:
        if r['status']=='CONFIRMED':agency_groups[(r['responsible_org'],r['stage'],r['due_date'][:4])].append(r)
    agency_totals=[]
    for (org,stage,year),group in sorted(agency_groups.items()):
        target=sum(r['units'] for r in group);known=sum(r['observed_units'] for r in group if r['observed_units'] is not None)
        missing=sum(r['observed_units'] is None for r in group)
        agency_totals.append(dict(responsible_org=org,stage=stage,year=year,project_count=len(group),target_units=target,
            known_observed_units=known,unknown_projects=missing,observed_units=None if missing else known,
            gap_units=None if missing else max(0,target-known),achievement_percent=round(known/target*100,1) if target and not missing else None))
    rows.sort(key=lambda r:({'DELAYED':0,'PLAN_DELAY':1,'VERIFY':2,'NO_BASELINE':3}.get(r['status'],4),r['current_date'] or '9999',r['name'],r['stage']))
    return dict(as_of_date=reference.isoformat(),items=rows,assignments=agency_comparisons,agency_totals=agency_totals,
        groups={key:summarize(rows,key) for key in ('region','responsible_org','stage')},
        summary=dict(project_count=len(projects),milestone_count=len(rows),statuses=dict(Counter(r['status'] for r in rows)),
                     approved_baselines=sum(bool(r['baseline_date']) for r in rows),assignment_count=len(agency_comparisons)),
        note='9·7 연결 사업 기록 기준. 승인 기준선 없는 예정기한 경과는 이행 확인 필요입니다. 검토 후보·추정·공정률을 완료일로 사용하지 않으며 입주는 실거주 호수가 아닌 시작 대상 물량입니다. 사업 기록 간 중복 가능성이 있어 그룹 물량은 공식 정책 실적이 아닙니다.')
