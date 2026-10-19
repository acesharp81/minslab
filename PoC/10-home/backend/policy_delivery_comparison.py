"""Comparable yearly targets and observations; missing records never mean zero."""
from collections import defaultdict
import calendar

METRICS = {'CONSTRUCTION': '착공(건설)', 'SUPPLY': '공급(분양·모집)',
           'BUSINESS': '사업화', 'APPROVAL': '인허가', 'COMPLETION': '준공', 'MOVE_IN': '입주'}
REGIONS = ('서울특별시', '경기도', '인천광역시')


def comparison_index(plan, cohorts, config, statistics, reference, program_cohorts=None):
    """Return compact source points plus yearly pairs for every selectable scope."""
    scopes = {'policy': dict(name='수도권 전체', kind='policy', id=plan['policy_id'], cohorts=cohorts)}
    for region in REGIONS:
        scopes['region:' + region] = dict(name=region, kind='region', id=region,
                                         cohorts=[c for c in cohorts if c['region'] == region])
    for c in cohorts:
        if c.get('municipality_id'):
            key = 'city:' + c['municipality_id']
            scopes.setdefault(key, dict(name=c.get('municipality') or c['municipality_id'],
                                       kind='city', id=c['municipality_id'], cohorts=[]))['cohorts'].append(c)
        scopes['project:' + c['id']] = dict(name=c['name'], kind='project', id=c['id'], cohorts=[c])
    programs = {c.get('program_id') for c in cohorts if c.get('program_id')}
    programs.update(plan.get('program_profiles',{}))
    for pid in programs:
        members = [c for c in (program_cohorts if program_cohorts is not None else cohorts) if c.get('program_id') == pid]
        key = 'program:' + pid
        scopes[key] = dict(name=plan.get('program_profiles',{}).get(pid,{}).get('name') or (members[0].get('program') if members else pid), kind='program', id=pid, cohorts=members)
        for region in {c['region'] for c in members}:
            scopes[key + '|region:' + region] = dict(name=region, kind='program_region', id=region,program_id=pid,
                cohorts=[c for c in members if c['region'] == region])
        for city in {c.get('municipality_id') for c in members if c.get('municipality_id')}:
            local = [c for c in members if c.get('municipality_id') == city]
            scopes[key + '|city:' + city] = dict(name=local[0].get('municipality') or city,
                kind='program_city', id=city,program_id=pid, cohorts=local)
    result = {}
    for key, scope in scopes.items():
        metrics = {}
        profile=plan.get('program_profiles',{}).get(scope['id'] if scope['kind']=='program' else scope.get('program_id')) if scope['kind'].startswith('program') else None
        scope_start=profile['values']['period_start'] if profile else plan['period_start']
        scope_end=profile['values']['period_end'] if profile else plan.get('period_end','2100-12-31')
        comparable=[dict(c,events=[e for e in c['events'] if scope_start<=e['event_date']<=scope_end]) for c in scope['cohorts']] if profile else scope['cohorts']
        tracked=scope['cohorts']
        for metric in METRICS:
            macro = not plan.get('portfolio') and metric == 'CONSTRUCTION' and scope['kind'] in ('policy', 'region')
            plans = _official_targets(plan, scope, metric) if macro else _schedule_targets(scope['cohorts'], metric, scope_start)
            actual = _regional_actual(statistics, reference, plan['period_start'],
                                      REGIONS if scope['kind'] == 'policy' else (scope['id'],)) if macro else _events(comparable, metric, reference, scope_start)
            if profile:
                plans=[p for p in plans if p['date']<=scope_end]
                custom=program_target_points(profile,metric,scope['id'] if scope['kind']=='program_region' else '전체') if scope['kind']!='program_city' else []
                if custom:plans=custom
                if profile['values']['unit']!='호':plans=[];actual=[]
            goals = [g for g in config.get('targets', []) if g.get('origin')!='SCENARIO' and g['stage'] == metric and
                     g['scope_kind'] == scope['kind'] and (g['scope_id'] == scope['id'] or
                     scope['kind'] == 'project' and g['scope_id'] in scope['cohorts'][0]['source_ids'])]
            management = [dict(date=g['due_date'], units=g['units'], origin=g.get('origin', 'MANUAL'),
                               basis=g.get('basis'), evidence_url=g.get('evidence_url')) for g in sorted(goals, key=lambda g: g['due_date'])]
            profile_priority = (macro or profile is not None) and any(p.get('origin') == 'MANUAL' for p in plans)
            if profile_priority: management = plans
            years = []
            # 1900 is the inclusive ledger sentinel, not a chart's first year.
            # Keep every real event/plan year, including old starts, without
            # emitting a century of empty cells for each region/program/project.
            first_year = int(scope_start[:4])
            if first_year == 1900:
                first_year = min([reference.year - 5] +
                    [int(p['date'][:4]) for p in plans + actual + management])
            for year in range(min(reference.year - 5,first_year), max(reference.year + 5,int(scope_end[:4])) + 1):
                year_end = f'{year}-12-31'
                yearly_plans = [p for p in plans if p['date'].startswith(str(year))]
                observation_end = min(year_end, reference.isoformat())
                yearly_actual = [a for a in actual if a['date'].startswith(str(year)) and a['date'] <= observation_end]
                last_actual = next((a for a in reversed(actual) if a['date'] <= observation_end), None) if year <= reference.year else None
                prior_actual = next((a for a in reversed(actual) if a['date'] < f'{year}-01-01'), None)
                target = next((p for p in reversed(plans) if p['date'] <= year_end), None)
                manual = next((p for p in reversed(management) if p['date'] <= year_end), None)
                years.append(dict(year=year, target_units=sum(p['annual_units'] for p in yearly_plans if p.get('annual_units') is not None) if any(p.get('annual_units') is not None for p in yearly_plans) else None,
                                  target_cumulative_units=target['units'] if target else None,
                                  management_cumulative_units=manual['units'] if manual else None,
                                  actual_units=(yearly_actual[-1]['units'] - (prior_actual['units'] if prior_actual else 0)) if yearly_actual else None,
                                  actual_cumulative_units=last_actual['units'] if last_actual else None,
                                  actual_through=last_actual['date'] if last_actual else None,
                                  actual_status='FUTURE' if year > reference.year else 'PARTIAL' if yearly_actual and (not macro or yearly_actual[-1]['date'] < year_end) else 'OBSERVED' if yearly_actual else 'NOT_ACQUIRED'))
            tracking=dict(target_points=_schedule_targets(tracked,metric,'1900-01-01'),
                          actual_points=_events(tracked,metric,reference,'1900-01-01',cumulative=True),
                          project_count=len(tracked),basis='선택 범위 사업 현재+후속 단계 누적 · 담당자 입력·추정 포함 · 원천 중복 제외')
            metrics[metric] = dict(label=METRICS[metric], target_points=plans, actual_points=actual,
                                   tracking=tracking,
                                   management_points=management, annual=years,
                                   actual_basis='동일 범위 공식 지역 착공 통계' if macro else '동일 범위 단계 도달량 · 확인 필요 연결 포함 · 관측일 기준 추정은 사건일과 구분',
                                   target_basis='연도별 착공 목표 · 사용자 입력 우선 / 원천 근거 보존' if macro else '연결 사업 원천의 동일 단계 예정 물량',
                                   target_status='AVAILABLE' if plans else 'NOT_ACQUIRED',
                                   actual_status='AVAILABLE' if actual else 'NOT_ACQUIRED')
        result[key] = dict(name=scope['name'], kind=scope['kind'], metrics=metrics)
    return result


def _official_targets(plan, scope, metric):
    overrides = plan.get('profile_overrides', {})
    scope_name = scope['id'] if scope['kind'] == 'region' else '전체'
    custom = any(k.startswith('annual:' + scope_name + ':') for k in overrides)
    if metric != 'CONSTRUCTION' or scope['kind'] == 'region' and scope['id'] != '서울특별시' and not custom:
        return []  # The original document gives Gyeonggi and Incheon jointly.
    cumulative = 0
    points = []
    for annual in sorted(plan['annual'], key=lambda a: a['year']):
        units = annual.get('seoul_units') if scope['kind'] == 'region' else annual['units']
        manual = overrides.get(f"annual:{scope_name}:{annual['year']}")
        if scope['kind'] == 'region' and scope['id'] != '서울특별시': units = None
        if manual: units = manual['value']
        if units is None:
            continue
        cumulative += units
        points.append(dict(date=f"{annual['year']}-12-31", units=cumulative, annual_units=units,
                           origin='MANUAL' if manual else 'OFFICIAL', precision='YEAR', evidence_url=None if manual else plan.get('evidence_url'),
                           basis=('사용자 입력 · '+manual['actor']+' · '+manual['changed_at']) if manual else '9·7 원문 연도별 신규 착공 목표', source_id=plan.get('source_id', 'policy_907_plan')))
    return points


def _regional_actual(statistics, reference, period_start, regions):
    monthly = defaultdict(dict)
    for r in statistics:
        period = str(r.get('statistic_period', ''))
        if (r.get('statistic_metric') == '착공' and r.get('region') in regions and len(period) == 6
                and period.isdigit() and period_start[:4] <= period[:4] and period <= reference.strftime('%Y%m')
                and isinstance(r.get('units'), int) and r['units'] >= 0):
            if r['region'] in monthly[period]:
                raise ValueError('같은 지역·월 착공 통계 중복')
            monthly[period][r['region']] = r
    cumulative = 0
    points = []
    year, month = int(period_start[:4]), int(period_start[5:7])
    while f'{year}{month:02d}' <= reference.strftime('%Y%m'):
        when=f'{year}-{month:02d}-{calendar.monthrange(year, month)[1]}'
        if when>reference.isoformat():
            break
        values = monthly.get(f'{year}{month:02d}', {})
        if set(values) != set(regions):
            break  # Never join over an uncollected month or mix different regional cutoffs.
        units = sum(r['units'] for r in values.values())
        cumulative += units
        points.append(dict(date=when, units=cumulative,
                           annual_units=units, origin='SOURCE', by_region={k: r['units'] for k, r in values.items()},
                           evidence_urls=sorted({r['evidence_url'] for r in values.values() if r.get('evidence_url')})))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return points


def _events(cohorts, metric, reference, period_start, cumulative=False):
    later={'BUSINESS':{'BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
           'APPROVAL':{'APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
           'CONSTRUCTION':{'CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
           'COMPLETION':{'COMPLETION','MOVE_IN'},'SUPPLY':{'SUPPLY','MOVE_IN'},'MOVE_IN':{'MOVE_IN'}}
    accepted=later.get(metric,{metric}) if cumulative else {metric}
    by_date = defaultdict(list)
    for c in cohorts:
        for e in c['events']:
            if (e['stage'] in accepted and e.get('status', 'ACTUAL') == 'ACTUAL'
                    and e['event_date'] <= reference.isoformat()):
                by_date[e['event_date']].append((c, e))
    counts = {}; confirmed = {}; attributed = {}; manual_counts={}; inferred_counts={}
    points = []
    for when, events in sorted(by_date.items()):
        for c, e in events:
            units = c['units'] if e.get('units') is None else e['units']
            counts[c['id']] = max(counts.get(c['id'], 0), min(c['units'], units))
            if e.get('origin')=='MANUAL':manual_counts[c['id']]=max(manual_counts.get(c['id'],0),min(c['units'],units))
            if e.get('inferred'):inferred_counts[c['id']]=max(inferred_counts.get(c['id'],0),min(c['units'],units))
            if e.get('review_status')!='REVIEW':confirmed[c['id']]=max(confirmed.get(c['id'],0),min(c['units'],units))
            if e.get('review_status')!='REVIEW' and c.get('mapping_status')=='CONFIRMED':attributed[c['id']]=max(attributed.get(c['id'],0),min(c['units'],units))
        points.append(dict(date=when, units=sum(counts.values()), confirmed_units=sum(confirmed.values()),policy_confirmed_units=sum(attributed.values()),review_units=sum(counts.values())-sum(confirmed.values()), origin='SOURCE_OR_MANUAL',manual_units=sum(manual_counts.values()),inferred_units=sum(inferred_counts.values()),
                           evidence_urls=sorted({e['evidence_url'] for _, e in events if e.get('evidence_url')})))
    return points


def _schedule_targets(cohorts, metric, period_start):
    increments = defaultdict(list)
    for c in cohorts:
        source = [s for s in c['schedules'] if s['stage'] == metric and (s.get('origin') == 'SOURCE' or s.get('managed_schedule')) and s.get('units') is not None and s['due_date']>=period_start]
        managed=[s for s in source if s.get('managed_schedule')]
        if managed:source=managed
        if not source:
            continue
        # Repeated source revisions must not count the same block twice.
        latest = max(source, key=lambda s: (s.get('source_base_date') or '', s.get('source_object_id') or ''))
        source = [s for s in source if s.get('source_object_id') == latest.get('source_object_id')]
        unique = {(s['due_date'], s['units']): s for s in source}
        remaining = c['units']
        for s in sorted(unique.values(), key=lambda s: s['due_date']):
            amount = min(remaining, s['units'])
            if amount <= 0:
                continue
            increments[s['due_date']].append(dict(s, units=amount))
            remaining -= amount
    cumulative = 0
    points = []
    for when, schedules in sorted(increments.items()):
        units = sum(s['units'] for s in schedules)
        cumulative += units
        points.append(dict(date=when, units=cumulative, annual_units=units, origin='MANUAL' if any(s.get('managed_schedule') for s in schedules) else 'SOURCE', precision='DAY',
                           evidence_urls=sorted({s['evidence_url'] for s in schedules if s.get('evidence_url')}),
                           basis='연결 사업 목표 일정 · 담당자 입력 우선 · 중복 제외'))
    return points


def program_target_points(profile,metric,region='전체'):
    values=profile['values'];source=profile.get('source',{});overrides=profile.get('overrides',{})
    if values['unit']!='호' or values['metric']!=metric:return []
    points=[];total=0
    for year in range(int(values['period_start'][:4]),int(values['period_end'][:4])+1):
        key=f'annual:{region}:{year}';value=values.get(key)
        if value is None:continue
        total+=value
        points.append(dict(date=f'{year}-12-31',units=total,annual_units=value,origin='MANUAL' if key in overrides else 'OFFICIAL',precision='YEAR',basis='프로그램 연간 목표 · 입력값 우선',evidence_url=source.get('evidence_url')))
    if region=='전체' and not any(k.startswith('annual:전체:') for k in overrides):
        for m in source.get('milestones',[]):
            if m['stage']==metric and not any(p['date']==m['due_date'] for p in points):points.append(dict(date=m['due_date'],units=m['units'],annual_units=None,origin='OFFICIAL',precision=m['date_precision'],basis=m['basis'],evidence_url=source.get('evidence_url')))
    cap=values.get('target_units' if region=='전체' else 'region:'+region)
    if cap is not None and not any(p['date']==values['period_end'] for p in points):
        points.append(dict(date=values['period_end'],units=cap,annual_units=None,origin='MANUAL' if 'target_units' in overrides else 'OFFICIAL',precision='PERIOD_END',basis='프로그램 기한 내 총목표 · 미배분 연도는 추정하지 않음',evidence_url=source.get('evidence_url')))
    return sorted(points,key=lambda p:p['date'])
