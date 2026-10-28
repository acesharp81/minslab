"""Conserved policy target ledger. Raw records, forecasts and actuals stay distinct."""
from collections import defaultdict
from datetime import date
from calendar import monthrange
from .construction_plan import construction_plan
import hashlib

from sqlalchemy import select
from .db import Revision, Audit, entity_id, upsert_revision
from .supply_dashboard import inventory, block_key, linked_notices
from .roadmap import source_events
from .policy_geo import schematic_view, region_outlines
from .api_samples import today
from .policy_delivery_comparison import comparison_index
from .stage_evidence import linked_events
from .occupancy_targets import occupancy_schedules
from .occupancy_monitor import build_occupancy_monitor

POLICY_ID='POL_2025_0907'
STAGES={'POLICY':'정책','BUSINESS':'사업화','APPROVAL':'인허가','CONSTRUCTION':'건설','SUPPLY':'공급','MOVE_IN':'입주'}
REGIONS=['서울특별시','경기도','인천광역시']

def settings(service,as_of=None):
    rows=service.rows('delivery_setting',as_of)
    return next((r for r in rows if r.get('policy_id')==POLICY_ID),dict(policy_id=POLICY_ID,revision_no=0,targets=[],events=[]))

def save_settings(service,revision_no,targets,events,occupancy_observations=None):
    allowed=set(STAGES)|{'COMPLETION'}
    seen=set();previous=defaultdict(list)
    projects={r['id']:r for r in service.projects(policy_id=POLICY_ID)}
    project_ids=set(projects)
    program_ids={r.get('mapping',{}).get('program_id') for r in projects.values()}
    if hasattr(service,'program_links'):program_ids.update(p['id'] for p in service.program_links() if p['policy_id']==POLICY_ID and p['status']!='RELEASED')
    program_ids.update(p['id'] for row in service.rows('policy_delivery_plan') for p in row.get('programs',[]))
    for target in targets:
        if target.get('origin')=='SCENARIO':raise ValueError('시나리오는 일정·병목 관리의 별도 시나리오에서 입력하세요')
        if target['scope_kind']=='project' and target['scope_id'] in projects:
            capacity=projects[target['scope_id']].get('planned_units')
            if capacity is not None and target['units']>capacity:raise ValueError('목표 물량이 사업 계획물량을 초과합니다')
        key=(target['scope_kind'],target['scope_id'],target['stage'],target['due_date'])
        if key in seen:raise ValueError('같은 범위·단계·목표일이 중복됩니다')
        seen.add(key)
        if target.get('origin')=='SOURCE_REVIEW' and not str(target.get('evidence_url') or '').startswith('https://'):raise ValueError('자료 기반 임시 목표에는 HTTPS 근거가 필요합니다')
        if target['stage'] not in allowed or target['stage']=='POLICY':raise ValueError('지원하지 않는 목표 단계')
        if target['scope_kind']=='project' and target['scope_id'] not in project_ids:raise ValueError('9·7 연결 사업을 선택하세요')
        if target['scope_kind']=='policy' and target['scope_id']!=POLICY_ID:raise ValueError('정책 범위 불일치')
        if target['scope_kind']=='region' and target['scope_id'] not in REGIONS:raise ValueError('수도권 시도 범위 불일치')
        if target['scope_kind']=='program' and target['scope_id'] not in program_ids:raise ValueError('9·7 연결 프로그램을 선택하세요')
        if not 0<=target['units']<=1350000:raise ValueError('목표 물량은 0~135만 호 범위입니다')
        previous[key[:3]].append((target['due_date'],target['units']))
    for points in previous.values():
        points.sort()
        if any(a[1]>b[1] for a,b in zip(points,points[1:])):raise ValueError('누적 목표는 시간에 따라 감소할 수 없습니다')
    event_keys=set()
    for event in events:
        key=(event['project_id'],event['stage'],event['event_date'])
        if key in event_keys:raise ValueError('동일 사업·단계·실적일 중복')
        event_keys.add(key)
        if event['project_id'] not in project_ids:raise ValueError('실제 사건은 9·7 연결 사업에 입력하세요')
        capacity=projects[event['project_id']].get('planned_units')
        if event.get('units') is not None and capacity is not None and event['units']>capacity:raise ValueError('실적 물량이 사업 계획물량을 초과합니다')
        if event['stage']=='MOVE_IN' and event.get('units') is not None:raise ValueError('입주는 실제 시작일만 입력합니다. 호수는 공란으로 두세요')
        if event['stage']!='SUPPLY' and event.get('units') not in (None,capacity):raise ValueError('부분 단계 도달은 공급묶음을 나눈 뒤 입력하세요. 전체 사업은 호수를 공란으로 둡니다')
        if event['event_date']>today().isoformat():raise ValueError('실제 사건에 미래 날짜를 입력할 수 없습니다')
        if not event.get('evidence_url','').startswith('https://'):raise ValueError('실제 사건의 HTTPS 근거가 필요합니다')
    if occupancy_observations is not None:
        seen_observations=set()
        for r in occupancy_observations:
            key=(r['region'],r['year'],r['as_of_date'])
            if key in seen_observations:raise ValueError('동일 지역·연도·기준일 입주량 중복')
            seen_observations.add(key)
            if not str(r['evidence_url']).startswith('https://'):raise ValueError('입주량의 HTTPS 근거가 필요합니다')
            if r['as_of_date']>today().isoformat() or r['as_of_date'][:4]<str(r['year']):raise ValueError('입주 실적 기준일을 확인하세요')
    with service.sessions.begin() as session:
        if service.engine.dialect.name=='postgresql':
            from sqlalchemy import text
            session.execute(text('SELECT pg_advisory_xact_lock(1019077)'))
        eid=entity_id('delivery_setting','manual_delivery',POLICY_ID)
        old=session.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)).with_for_update())
        current=old.revision_no if old else 0
        if revision_no!=current:return dict(conflict=True,revision_no=current)
        payload=dict(policy_id=POLICY_ID,targets=targets,events=events,base_date=today().isoformat(),origin='MANUAL',
            occupancy_observations=occupancy_observations if occupancy_observations is not None else (old.payload.get('occupancy_observations',[]) if old else []))
        row,outcome=upsert_revision(session,'delivery_setting','manual_delivery',POLICY_ID,payload,'manual')
        if outcome!='unchanged':session.add(Audit(entity_id=POLICY_ID,action='DELIVERY_TARGETS_UPDATED',before=old.payload if old else {},after=payload))
        return dict(payload,revision_no=row.revision_no,outcome=outcome)

def build_delivery(service,reference,include_portfolio_comparisons=True,indicators_only=False,comparison_scopes=None):
    from .read_scope import projection_reads
    with projection_reads():
        return _build_delivery(service,reference,include_portfolio_comparisons,indicators_only,comparison_scopes)


def _build_delivery(service,reference,include_portfolio_comparisons=True,indicators_only=False,comparison_scopes=None):
    plans=service.rows('policy_delivery_plan',reference)
    plan=next((r for r in plans if r.get('policy_id')==POLICY_ID),None)
    if not plan:return dict(policy_id=POLICY_ID,status='PLAN_NOT_COLLECTED',target_units=1350000,
                             notice='9·7 공식 원문 목표표 수집이 필요합니다')
    from .policy_profile import apply_profile, profile
    plan=apply_profile(plan,profile(service,reference))
    raw=service.projects(as_of=reference,policy_id=POLICY_ID)
    aliases={'lh_incheon_sale':'lh_sale','lh_incheon_rent':'lh_rent','lh_incheon_construction':'lh_construction'}
    rows=[dict(r,source_id=aliases.get(r['source_id'],r['source_id']),origin_source_id=r['source_id']) for r in raw]
    from .program_profile import profiles
    program_details=profiles(service,reference)
    linked_programs=service.program_links(reference,projects=raw) if hasattr(service,'program_links') else []
    plan['program_profiles']={p['id']:dict(program_details[p['id']],name=p['name']) for p in linked_programs if p['id'] in program_details and p['policy_id']==POLICY_ID and p['status']!='RELEASED'}
    from .supply_type import assess as assess_supply_type
    chosen,excluded=inventory(rows)
    all_by_key=defaultdict(list)
    for row in rows:all_by_key[block_key(row) or ('ID',row['id'])].append(row)
    notices=linked_notices(chosen,service.rows('notice',reference),reference)
    from .evidence_bridge import supply_notices
    eligible={r['id']:r for r in chosen}
    for pid,notice in supply_notices(service,reference).items():
        if pid in eligible and notice['units']<=(eligible[pid].get('planned_units') or 0):
            notices[pid]=notice
    stored_config=settings(service,reference)
    from .delivery_operations import schedule_goals
    approved_schedules=schedule_goals(service,reference)
    managed_keys={(g['scope_id'],g['stage']) for g in approved_schedules}
    config=dict(stored_config,targets=[g for g in stored_config.get('targets',[]) if g.get('origin')!='SCENARIO' and (g['scope_id'],g['stage']) not in managed_keys]+approved_schedules)
    stage_links=linked_events(service,reference)
    from .evidence_bridge import by_project
    bridge_links=by_project(service,reference)
    occupancy=occupancy_schedules(service,rows,reference)
    from .project_profile import progress_events
    managed_progress=defaultdict(list)
    for event in progress_events(service,reference):managed_progress[event['project_id']].append(event)
    manual=defaultdict(list)
    for event in config.get('events',[]):manual[event['project_id']].append(event)
    dashboard=service.supply_dashboard(as_of=reference,horizon=5,measure='SUPPLY',
        **({'policy_id':POLICY_ID} if comparison_scopes is not None else {}))
    extra=service.rows('policy_municipality',reference)
    places=list({p['id']:p for p in extra+dashboard['municipalities']}.values())
    shape=schematic_view(dict(dashboard,municipalities=places))
    if not indicators_only:
        shape['region_shapes']=region_outlines(places,getattr(service,'engine',None))
    place_lookup={(p['region'],p['name']):p for p in places}
    city_of={pid:city['id'] for city in dashboard['municipalities'] for pid in city['project_ids']}
    blocks={pid:block for block in dashboard['blocks'] for pid in block['project_ids']}
    cohorts=[];portfolio=[];historical=[];missing=[]
    selected_ids={r['id'] for r in chosen}
    for row in chosen:
        group=all_by_key[block_key(row) or ('ID',row['id'])]
        # Distinct rental tenures at one block are disjoint inventories. Do not
        # copy a sibling's or the whole-block contract's dates/quantities into
        # both tenures. Each retains its own approved observations and plans.
        if sum(m['id'] in selected_ids for m in group)>1:
            group=[m for m in group if m['id']==row['id']]
        planned_cap=row.get('planned_units');cap=planned_cap
        if cap is None or cap<=0:
            missing.append(row['id']);cap=(notices.get(row['id']) or {}).get('units')
            if not cap:continue
        # An officer-verified event for this exact cohort supersedes an older
        # whole-contract estimate on sibling source records at the same block.
        verified_stages={e['stage'] for e in managed_progress.get(row['id'],[])
                         if not e.get('inferred',True) and e.get('input_rule')=='OFFICER_VERIFIED_SOURCE'}
        scoped_overrides=[e for m in group for e in managed_progress.get(m['id'],[])
                          if m['id']==row['id'] or e['stage'] not in verified_stages]
        events=[];schedules=[];progress=[]
        for member in group:
            if member.get('start_actual_date'):
                events.append(dict(stage='CONSTRUCTION',event_date=member['start_actual_date'],units=cap,
                                   evidence_url=member['evidence_url'],origin='SOURCE',source_id=member['origin_source_id']))
            for event in source_events(member,reference):
                schedules.append(dict(stage=event['stage'],due_date=event.get('due_date') or event['month']+'-01',
                    precision=event.get('precision','MONTH'),units=event.get('units'),evidence_url=event['evidence_url'],origin='SOURCE',
                    basis=event.get('basis'),source_id=member['origin_source_id'],source_object_id=member['id'],
                    source_base_date=member['base_date']))
            if member.get('progress_pct') is not None:
                override=member.get('manual_fields',{}).get('progress_pct',{})
                progress.append(dict(pct=member['progress_pct'],as_of_date=member.get('progress_date') or member['base_date'],evidence_url=member['evidence_url'],inferred=bool(override.get('inferred')),origin='MANUAL' if override else 'SOURCE'))
            events.extend(dict(e,origin='MANUAL') for e in manual.get(member['id'],[]))
            events.extend(stage_links.get(member['id'],[]))
            # Collection diagrams and policy charts consume the same pinned evidence.
            for bridge in bridge_links.get(member['id'],[]):
                if bridge.get('status') not in ('REVIEW','CONFIRMED'):continue
                for fact in bridge.get('facts',[]):
                    if fact.get('scope_partial') or fact.get('reference_only'):continue
                    stage='COMPLETION' if fact.get('stage')=='CONSTRUCTION' and fact.get('milestone')=='COMPLETION' else fact.get('stage')
                    if stage not in set(STAGES)|{'COMPLETION'}:continue
                    when=fact.get('date') or fact.get('date_label')
                    if fact.get('kind')=='ACTUAL' and when and len(when)==10 and when<=reference.isoformat():
                        events.append(dict(stage=stage,event_date=when,units=fact.get('units'),status='ACTUAL',
                            review_status=bridge['status'],origin='LINKED_EVIDENCE',source_id=bridge['source_id'],
                            evidence_url=bridge.get('evidence_url'),basis=fact.get('basis'),
                            date_basis=fact.get('date_basis','EVENT'),
                            source_event_date=when if fact.get('date_basis','EVENT')=='EVENT' else fact.get('source_event_date'),
                            observed_on=fact.get('observed_on'),method=fact.get('method')))
                    elif fact.get('kind')=='PLAN':
                        from .schedule_period import schedule_period
                        period=schedule_period(when)
                        if period:
                            schedules.append(dict(stage=stage,due_date=period['due_date'],precision=period['precision'],
                                source_date_label=period['original'],date_conversion=period['conversion'],
                                units=fact.get('units') or cap,origin='SOURCE',source_id=bridge['source_id'],
                                source_object_id=bridge['source_entity_id'],review_status=bridge['status'],
                                evidence_url=bridge.get('evidence_url'),basis=fact.get('basis')))

            schedules.extend(occupancy.get(member['id'],[]))
            managed_stages={t['stage'] for t in approved_schedules if t['scope_id']==member['id']}
            schedules=[s for s in schedules if not (s.get('source_object_id')==member['id'] and s['stage'] in managed_stages)]
            schedules.extend(dict(t,precision=t.get('precision','DAY')) for t in config.get('targets',[])
                             if t['scope_kind']=='project' and t['scope_id']==member['id'])
        overrides=scoped_overrides
        if overrides:
            stages={e['stage'] for e in overrides}
            events=[e for e in events if e['stage'] not in stages]+overrides
        starts=[e['event_date'] for e in events if e['stage']=='CONSTRUCTION' and e.get('status','ACTUAL')=='ACTUAL']
        before_period=bool(starts and min(starts)<plan['period_start'])
        if before_period:
            historical.append(dict(id=row['id'],name=row['name'],units=cap,start_date=min(starts),region=row['region']))
        notice=notices.get(row['id'])
        if notice:
            events.append(dict(stage='SUPPLY',event_date=notice['source_date'],units=notice['units'],
                evidence_url=notice['evidence_url'],origin='SOURCE',source_id=notice['source_id']))
        if notice and notice.get('move_in_plan_month'):
            month=notice['move_in_plan_month'].replace('-','')
            if len(month)==6 and month.isdigit():
                schedules.append(dict(stage='MOVE_IN',due_date=month[:4]+'-'+month[4:]+'-01',precision='MONTH',
                    units=notice['units'],origin='SOURCE',source_id=notice['source_id'],source_object_id=notice['id'],
                    source_base_date=notice['source_date'],basis='본 모집공고 입주 예정 물량 · 실입주 아님',evidence_url=notice['evidence_url']))
        city_id=city_of.get(row['id']);city_name=next((p['name'] for p in places if p['id']==city_id),row.get('municipality'))
        if row['region']=='인천광역시':
            # Use the dated administrative label resolved from the source, not
            # a substring of a station name (제물포역 is in 미추홀구).
            inferred=next((p for p in extra if p['name']==row.get('municipality')),None)
            if inferred:city_id=inferred['id'];city_name=inferred['name']
        block=next((blocks[m['id']] for m in group if m['id'] in blocks),None)
        p=max(progress,key=lambda x:x['as_of_date']) if progress else None
        if p and p['pct']==100 and not p.get('inferred'):
            events.append(dict(stage='COMPLETION',event_date=p['as_of_date'],units=cap,
                               evidence_url=p['evidence_url'],origin=p.get('origin','SOURCE'),basis='담당자 확인 공정률 100% 확인일' if p.get('origin')=='MANUAL' else '원천 공정률 100% 확인일'))
        overrides=scoped_overrides
        if overrides:
            stages={e['stage'] for e in overrides}
            events=[e for e in events if e['stage'] not in stages]+overrides
        portfolio.append(dict(id=row['id'],source_ids=[m['id'] for m in group],name=row['name'],units=cap,
            planned_units=planned_cap,quantity_basis='PLAN' if planned_cap else 'NOTICE_ONLY',region=row['region'],municipality=city_name,municipality_id=city_id,program_id=row.get('mapping',{}).get('program_id'),
            program=row.get('mapping',{}).get('program_name') or row.get('program'),block=row.get('block'),
            developer=next((m.get('developer') for m in group if m.get('developer')),None),
            longitude=(block or {}).get('longitude'),latitude=(block or {}).get('latitude'),
            coordinate_basis=(block or {}).get('coordinate_basis'),events=events,schedules=schedules,
            construction_plan=next((value for m in sorted(group,key=lambda m:m.get('base_date',''),reverse=True) if (value:=construction_plan(m,reference))),None),
            progress=p,move_in_start=row.get('move_in_start'),mapping_status=row.get('mapping',{}).get('status'),
            eligibility_status='PRE_POLICY_START' if before_period else 'START_IN_POLICY_PERIOD' if starts else 'PERIOD_MEMBERSHIP_REVIEW',
            evidence_url=row['evidence_url'],
            report_metadata=dict(
                supply_type=assess_supply_type(row), tenure=row.get('tenure'),
                unit=row.get('unit') or ('실' if '오피스텔' in (row.get('name') or '') else '호'),
                mapping=row.get('mapping', {}),
                source_revisions=[{k:m.get(k) for k in ('id','source_id','source_revision_id',
                    'revision_no','source_payload_hash','recorded_at','last_collection_at','base_date','evidence_url')}
                    for m in group])))
        if not before_period and planned_cap:cohorts.append(portfolio[-1])
    target=plan['target_units'];allocated=sum(c['units'] for c in cohorts)
    if allocated>target:raise ValueError('연결 사업 물량이 정책 목표 초과: 배분 검토 필요')
    reserve=target-allocated
    if indicators_only:
        # Regional indicators consume these same reviewed cohorts, events and
        # plans. They do not use monthly policy animation, program comparison
        # matrices, province dissolves or full-source diagnostic payloads.
        return dict(status='READY',policy_id=POLICY_ID,name=plan['name'],plan=plan,
            target_units=target,cohorts=cohorts,portfolio_cohorts=portfolio,geometry=shape)
    def cohort_state(cutoff,forecast=False):
        totals={k:0 for k in STAGES};totals['UNKNOWN']=0;details=[]
        for c in cohorts:
            active=[e for e in c['events'] if e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=min(cutoff,reference.isoformat())]
            if forecast:
                active+= [dict(stage=s['stage'],event_date=s['due_date'],units=s['units'],origin='PLANNED')
                          for s in c['schedules'] if s['units'] is not None and reference.isoformat()<s['due_date']<=cutoff and s['stage']!='MOVE_IN']
            supplied=min(c['units'],max((e['units'] if e.get('units') is not None else c['units'] for e in active if e['stage']=='SUPPLY'),default=0))
            entry_units=min(c['units'],max((e['units'] if e.get('units') is not None else c['units'] for e in active if e['stage']=='MOVE_IN' and e.get('origin')!='PLANNED'),default=0))
            entry=entry_units>0
            supplied=max(supplied,entry_units)
            parts={'MOVE_IN':entry_units,'SUPPLY':supplied-entry_units};assigned=supplied
            for stage in ('CONSTRUCTION','APPROVAL','BUSINESS'):
                reached=min(c['units'],max((e['units'] if e.get('units') is not None else c['units'] for e in active if e['stage']==stage),default=0))
                parts[stage]=max(0,reached-assigned);assigned+=parts[stage]
            parts['UNKNOWN']=c['units']-assigned
            full=next((s for s in ('CONSTRUCTION','APPROVAL','BUSINESS') if parts[s]),'UNKNOWN')
            for k,v in parts.items():totals[k]+=v
            details.append(dict(id=c['id'],parts=parts,representative_stage='MOVE_IN' if entry and supplied else 'SUPPLY' if supplied else full))
        totals['POLICY']=reserve
        if forecast:
            # The original document plans starts for an unenumerated target pool.
            # Transfer that planned pool only; never present it as observed output.
            year=int(cutoff[:4]);month=int(cutoff[5:7])
            planned=sum((a['units'] or 0) for a in plan['annual'] if a['year']<year)
            planned+=round(sum((a['units'] or 0) for a in plan['annual'] if a['year']==year)*month/12)
            known=sum(c['units'] for c in cohorts if any(e['stage']=='CONSTRUCTION' and e['event_date']<=cutoff for e in c['events']))
            transfer=min(totals['POLICY'],max(0,planned-known))
            totals['POLICY']-=transfer;totals['CONSTRUCTION']+=transfer
            for goal in sorted(config.get('targets',[]),key=lambda g:g['due_date']):
                if goal['scope_kind']!='policy' or goal['stage'] not in STAGES or not reference.isoformat()<goal['due_date']<=cutoff:continue
                later=list(STAGES)[list(STAGES).index(goal['stage']):]
                reached=sum(totals[k] for k in later)
                deficit=max(0,goal['units']-reached)
                for pool in ('POLICY','UNKNOWN'):
                    shift=min(totals[pool],deficit)
                    totals[pool]-=shift;totals[goal['stage']]+=shift;deficit-=shift
        return dict(date=cutoff,month=cutoff[:7],totals=totals,total_units=sum(totals.values()),forecast=forecast,cohorts=details)
    snapshots=[]
    dates=[d for c in portfolio for d in [*(e['event_date'] for e in c['events']),*(s['due_date'] for s in c['schedules'])] if d]
    dates.extend(d for p in plan.get('program_profiles',{}).values() for d in (p['values']['period_start'],p['values']['period_end']))
    first_year=min([reference.year-5,int(plan['period_start'][:4])]+[int(d[:4]) for d in dates]);last_year=max([reference.year+5,int(plan['period_end'][:4])]+[int(d[:4]) for d in dates])
    for year in range(first_year,last_year+1):
        for month in range(1,13):
            cutoff=f'{year}-{month:02d}-{monthrange(year,month)[1]:02d}'
            if cutoff[:7]==reference.strftime('%Y-%m'):cutoff=reference.isoformat()
            state=cohort_state(cutoff,cutoff>reference.isoformat())
            snapshots.append({k:v for k,v in state.items() if k!='cohorts'})
    current=cohort_state(reference.isoformat())
    current_index={c['id']:c for c in current['cohorts']}
    for c in portfolio:
        c.update(current_index.get(c['id'],dict(representative_stage='UNKNOWN')))
    issues=[]
    for c in portfolio:
        goals=[s for s in c['schedules'] if s['stage'] in ('SUPPLY','CONSTRUCTION','COMPLETION')]
        goals+= [dict(t,precision=t.get('precision','DAY')) for t in config.get('targets',[]) if t['scope_kind']=='project' and t['scope_id'] in c['source_ids']]
        for goal in sorted(goals,key=lambda x:x['due_date']):
            if goal['due_date']>=reference.strftime('%Y-%m')+'-01':continue
            actual=[e for e in c['events'] if e.get('status','ACTUAL')=='ACTUAL' and e['stage']==goal['stage'] and e['event_date']<=reference.isoformat()]
            amount=max((e['units'] if e.get('units') is not None else c['units'] for e in actual),default=0)
            gap=max(0,(goal.get('units') or c['units'])-amount)
            if not gap:continue
            pct=c.get('progress')
            confirmed=goal['stage']=='COMPLETION' and pct and not pct.get('inferred') and pct['as_of_date']>goal['due_date'] and pct['pct']<100
            confirmed=confirmed or any(e.get('status')=='DELAYED' for e in manual.get(c['id'],[]) if e['stage']==goal['stage'])
            issues.append(dict(project_id=c['id'],name=c['name'],region=c['region'],municipality_id=c['municipality_id'],
                stage=goal['stage'],units=min(c['units'],gap),due_date=goal['due_date'],status='DELAYED' if confirmed else 'VERIFY',
                evidence_url=(pct or {}).get('evidence_url') if confirmed and pct else goal.get('evidence_url')))
            break # Each cohort contributes once to the combined problem subtotal.
    statistics=(service.policy_start_statistics(reference) if hasattr(service,'policy_start_statistics')
                else service.rows('statistic',reference))
    yearly_comparisons=comparison_index(plan,cohorts,config,statistics,reference,program_cohorts=portfolio,
        scope_keys=None if comparison_scopes is None else set(comparison_scopes)|{'policy'})
    macro_points=yearly_comparisons['policy']['metrics']['CONSTRUCTION']['actual_points']
    regional_months=[dict(month=p['date'][:7],units=p['annual_units'],cumulative_units=p['units'],by_region=p['by_region']) for p in macro_points]
    annual=[]
    for a in plan['annual']:
        by_region={}
        for region in REGIONS:
            obs=[p for p in macro_points if p['date'].startswith(str(a['year']))]
            by_region[region]=sum(p['by_region'][region] for p in obs) if obs else None
        annual.append(dict(a,actual_start_by_region=by_region))
    source_ids={'policy_907_plan','policy_907_incheon_geometry','incheon_statistics','lh_incheon_sale','lh_incheon_rent','lh_incheon_construction','ih_supply'}
    # screen_view drops source diagnostics; don't scan batch manifests to build
    # data which will be discarded. Full diagnostics/export retains this field.
    sources=([dict(id=s['id'],name=s['name'],status=s['status'],last_success=s.get('last_success'),record_count=s.get('record_count')) for s in service.sources() if s['id'] in source_ids]
             if comparison_scopes is None else [])
    comparisons=[]
    for goal in config.get('targets',[]) if comparison_scopes is None else []:
        scope=[c for c in cohorts if goal['scope_kind']=='policy' or
               (goal['scope_kind']=='region' and c['region']==goal['scope_id']) or
               (goal['scope_kind']=='project' and goal['scope_id'] in c['source_ids']) or
               (goal['scope_kind']=='program' and c['program_id']==goal['scope_id'])]
        found=[]
        for c in scope:
            observations=[e for e in c['events'] if e['stage']==goal['stage'] and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=reference.isoformat()]
            if observations:found.append(min(c['units'],max(e['units'] if e.get('units') is not None else c['units'] for e in observations)))
        actual=sum(found) if found else None;due=goal['due_date']<=reference.isoformat()
        comparisons.append(dict(goal,observed_units=actual,gap_units=max(0,goal['units']-actual) if actual is not None else None,
            comparison_status='VERIFY' if actual is None or due and actual<goal['units'] else 'OBSERVED_GOAL_REACHED' if actual>=goal['units'] else 'UPCOMING'))
    from .program_management import assessment
    program_assessments={pid:assessment(pid,p['values'],p['source'],dict(portfolio_cohorts=portfolio),raw) for pid,p in plan.get('program_profiles',{}).items()}
    from .october_alignment import build as october_alignment
    official_alignment=october_alignment(portfolio,raw,reference)
    return dict(**({'_comparison_inputs':dict(config=config,statistics=[s for s in statistics if s.get('statistic_metric')=='착공'])} if comparison_scopes is not None else {}),
        official_alignment=official_alignment,policy_id=POLICY_ID,status='READY',name=plan['name'],as_of_date=reference.isoformat(),
        measurement_contract=dict(version='2026-10-12.1',target_metric='CONSTRUCTION',supply_metric='SUPPLY',
            scope='9·7 수도권 2026–2030 신규 착공',partition='EXCLUSIVE',map_measure='CUMULATIVE_REACHED',
            reserve_status='PROJECT_NOT_IDENTIFIED',unknown_status='STAGE_NOT_VERIFIED',
            identification_pct=round(allocated/target*100,4),legacy_scenario_targets_excluded=sum(g.get('origin')=='SCENARIO' for g in stored_config.get('targets',[])),
            conservation_ok=current['total_units']==target,rounding_reserve=plan.get('rounding_unallocated_units'),
            mapping_review_included=True),
        target_units=target,plan=plan,annual=annual,program_assessments=program_assessments,stages=STAGES,current=current,snapshots=snapshots,cohorts=cohorts,
        allocated_units=allocated,reserve_units=reserve,historical=historical,excluded_source_ids=excluded,missing_quantity_ids=missing,
        issues=issues,settings=stored_config,geometry=shape,sources=sources,goal_comparisons=comparisons,regional_start_months=regional_months,
        management_projects=[dict(id=r['id'],name=r['name'],units=r.get('planned_units'),program_id=r.get('mapping',{}).get('program_id'),program=r.get('program')) for r in raw],
        occupancy_monitor=build_occupancy_monitor(plan,config,reference),yearly_comparisons=yearly_comparisons,portfolio_cohorts=portfolio,
        portfolio_comparisons=comparison_index(dict(plan,period_start='1900-01-01',portfolio=True),portfolio,config,[],reference,scope_keys=comparison_scopes) if include_portfolio_comparisons else {},
        map_reconciliation=dict(default_scope='PORTFOLIO',default_stage='SUPPLY',
            linked_units=sum(c['planned_units'] or 0 for c in portfolio),policy_period_units=allocated,
            prior_start_units=sum(c['units'] for c in portfolio if c['eligibility_status']=='PRE_POLICY_START'),
            rule='공급현황과 동일한 지구·블록 중복 제외. 연결사업 전체에는 정책기간 이전 착공 포함. 135만 목표 원장에서는 별도 제외.'),
        stage_note='공급은 본 모집·분양 기준. 입주는 실제 시작 확인일만 관리. 대표 단계와 실제 공정률은 별도. 미확인 물량은 회색으로 표시.')
