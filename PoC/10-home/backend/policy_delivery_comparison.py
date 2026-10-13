"""Comparable yearly targets and observations; missing records never mean zero."""
from collections import defaultdict
import calendar

METRICS = {'CONSTRUCTION': '착공(건설)', 'SUPPLY': '공급(분양·모집)',
           'BUSINESS': '사업화', 'APPROVAL': '인허가', 'COMPLETION': '준공', 'MOVE_IN': '입주 예정'}
REGIONS = ('서울특별시', '경기도', '인천광역시')


def comparison_index(plan, cohorts, config, statistics, reference):
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
    for pid in programs:
        members = [c for c in cohorts if c.get('program_id') == pid]
        key = 'program:' + pid
        scopes[key] = dict(name=members[0].get('program') or pid, kind='program', id=pid, cohorts=members)
        for region in {c['region'] for c in members}:
            scopes[key + '|region:' + region] = dict(name=region, kind='program_region', id=region,
                cohorts=[c for c in members if c['region'] == region])
        for city in {c.get('municipality_id') for c in members if c.get('municipality_id')}:
            local = [c for c in members if c.get('municipality_id') == city]
            scopes[key + '|city:' + city] = dict(name=local[0].get('municipality') or city,
                kind='program_city', id=city, cohorts=local)
    result = {}
    for key, scope in scopes.items():
        metrics = {}
        for metric in METRICS:
            macro = not plan.get('portfolio') and metric == 'CONSTRUCTION' and scope['kind'] in ('policy', 'region')
            plans = _official_targets(plan, scope, metric) if macro else _schedule_targets(scope['cohorts'], metric, plan['period_start'])
            actual = _regional_actual(statistics, reference, plan['period_start'],
                                      REGIONS if scope['kind'] == 'policy' else (scope['id'],)) if macro else _events(scope['cohorts'], metric, reference, plan['period_start'])
            if metric=='MOVE_IN': actual=[]
            goals = [g for g in config.get('targets', []) if g.get('origin')!='SCENARIO' and g['stage'] == metric and
                     g['scope_kind'] == scope['kind'] and (g['scope_id'] == scope['id'] or
                     scope['kind'] == 'project' and g['scope_id'] in scope['cohorts'][0]['source_ids'])]
            management = [dict(date=g['due_date'], units=g['units'], origin=g.get('origin', 'MANUAL'),
                               basis=g.get('basis'), evidence_url=g.get('evidence_url')) for g in sorted(goals, key=lambda g: g['due_date'])]
            years = []
            for year in range(reference.year - 5, reference.year + 6):
                year_end = f'{year}-12-31'
                yearly_plans = [p for p in plans if p['date'].startswith(str(year))]
                observation_end = min(year_end, reference.isoformat())
                yearly_actual = [a for a in actual if a['date'].startswith(str(year)) and a['date'] <= observation_end]
                last_actual = next((a for a in reversed(actual) if a['date'] <= observation_end), None) if year <= reference.year else None
                prior_actual = next((a for a in reversed(actual) if a['date'] < f'{year}-01-01'), None)
                target = next((p for p in reversed(plans) if p['date'] <= year_end), None)
                manual = next((p for p in reversed(management) if p['date'] <= year_end), None)
                years.append(dict(year=year, target_units=sum(p['annual_units'] for p in yearly_plans) if yearly_plans else None,
                                  target_cumulative_units=target['units'] if target else None,
                                  management_cumulative_units=manual['units'] if manual else None,
                                  actual_units=(yearly_actual[-1]['units'] - (prior_actual['units'] if prior_actual else 0)) if yearly_actual else None,
                                  actual_cumulative_units=last_actual['units'] if last_actual else None,
                                  actual_through=last_actual['date'] if last_actual else None,
                                  actual_status='FUTURE' if year > reference.year else 'PARTIAL' if yearly_actual and (not macro or yearly_actual[-1]['date'] < year_end) else 'OBSERVED' if yearly_actual else 'NOT_ACQUIRED'))
            metrics[metric] = dict(label=METRICS[metric], target_points=plans, actual_points=actual,
                                   management_points=management, annual=years,
                                   actual_basis='동일 범위 공식 지역 착공 통계' if macro else '동일 범위 단계 도달량 · 확인 필요 연결 포함 · 관측일 기준 추정은 사건일과 구분',
                                   target_basis='9·7 원문 연도별 착공 목표' if macro else '연결 사업 원천의 동일 단계 예정 물량',
                                   target_status='AVAILABLE' if plans else 'NOT_ACQUIRED',
                                   actual_status='AVAILABLE' if actual else 'NOT_ACQUIRED')
        result[key] = dict(name=scope['name'], kind=scope['kind'], metrics=metrics)
    return result


def _official_targets(plan, scope, metric):
    if metric != 'CONSTRUCTION' or scope['kind'] == 'region' and scope['id'] != '서울특별시':
        return []  # The original document gives Gyeonggi and Incheon jointly.
    cumulative = 0
    points = []
    for annual in sorted(plan['annual'], key=lambda a: a['year']):
        units = annual.get('seoul_units') if scope['kind'] == 'region' else annual['units']
        if units is None:
            continue
        cumulative += units
        points.append(dict(date=f"{annual['year']}-12-31", units=cumulative, annual_units=units,
                           origin='OFFICIAL', precision='YEAR', evidence_url=plan.get('evidence_url'),
                           basis='9·7 원문 연도별 신규 착공 목표', source_id=plan.get('source_id', 'policy_907_plan')))
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


def _events(cohorts, metric, reference, period_start):
    by_date = defaultdict(list)
    for c in cohorts:
        for e in c['events']:
            if (e['stage'] == metric and e.get('status', 'ACTUAL') == 'ACTUAL'
                    and e['event_date'] <= reference.isoformat()):
                by_date[e['event_date']].append((c, e))
    counts = {}; confirmed = {}; attributed = {}
    points = []
    for when, events in sorted(by_date.items()):
        for c, e in events:
            units = c['units'] if e.get('units') is None else e['units']
            counts[c['id']] = max(counts.get(c['id'], 0), min(c['units'], units))
            if e.get('review_status')!='REVIEW':confirmed[c['id']]=max(confirmed.get(c['id'],0),min(c['units'],units))
            if e.get('review_status')!='REVIEW' and c.get('mapping_status')=='CONFIRMED':attributed[c['id']]=max(attributed.get(c['id'],0),min(c['units'],units))
        points.append(dict(date=when, units=sum(counts.values()), confirmed_units=sum(confirmed.values()),policy_confirmed_units=sum(attributed.values()),review_units=sum(counts.values())-sum(confirmed.values()), origin='SOURCE_OR_MANUAL',
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
        points.append(dict(date=when, units=cumulative, annual_units=units, origin='SOURCE', precision='MONTH',
                           evidence_urls=sorted({s['evidence_url'] for s in schedules if s.get('evidence_url')}),
                           basis='연결 사업 원천 일정 · 중복 제외'))
    return points
