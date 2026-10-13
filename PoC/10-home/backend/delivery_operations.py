"""Officer schedule baselines, action cases and isolated, reproducible scenarios.

Records use the existing immutable Revision/Audit store. No source payload is
mutated; an approved schedule baseline survives all later revisions.
"""
from collections import Counter, defaultdict
from datetime import date
import calendar
import hashlib
import json
from sqlalchemy import select
from .db import Revision, Audit, entity_id, upsert_revision
from .api_samples import today

POLICY = 'POL_2025_0907'
STAGES = ('BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'SUPPLY', 'COMPLETION', 'MOVE_IN')
KINDS = {'schedule': 'execution_schedule', 'case': 'execution_case', 'scenario': 'execution_scenario', 'agency': 'execution_agency'}

def _day(value):
    return date.fromisoformat(value)

def _validate_project(service, project_id):
    project = next((p for p in service.projects(policy_id=POLICY) if p['id'] == project_id), None)
    if not project:
        raise ValueError('9·7에 연결된 사업을 선택하세요')
    return project

def save(service, kind, key, revision_no, values):
    if kind not in KINDS:
        raise ValueError('지원하지 않는 관리 유형')
    if not key or len(key) > 140:
        raise ValueError('관리 식별자를 확인하세요')
    p = _validate_project(service, values['project_id']) if kind != 'scenario' else None
    value = dict(values, policy_id=POLICY, base_date=today().isoformat())
    if p:
        value.update(name=p['name'], region=p['region'])
        if values['stage'] not in STAGES:
            raise ValueError('단계를 확인하세요')
        if values.get('units') is not None:
            if values['units'] < 0 or values['units'] > (p.get('planned_units') or 1350000):
                raise ValueError('물량은 해당 사업 계획량 이내여야 합니다')
    if kind == 'agency':
        if key != values['project_id'] + ':' + values['stage']:
            raise ValueError('기관 목표는 사업·단계별 하나의 변경 이력으로 관리합니다')
        _day(values['due_date'])
        if values.get('units') is None or not values.get('responsible_org','').strip() or not values.get('basis','').strip():
            raise ValueError('기관 배정 목표·주관기관·근거를 입력하세요')
        if values['status']=='CONFIRMED' and not (values.get('evidence_url') or '').startswith('https://'):
            raise ValueError('기관 배정 목표 승인에는 HTTPS 근거가 필요합니다')
    if kind == 'schedule':
        if key != values['project_id'] + ':' + values['stage']:
            raise ValueError('사업·단계별 일정은 하나의 변경 이력으로 관리합니다')
        _day(values['due_date'])
        if not values.get('basis', '').strip() or not values.get('responsible_org', '').strip():
            raise ValueError('일정 근거와 입력 책임기관을 입력하세요')
        if values.get('origin') == 'SOURCE_REVIEW' and not (values.get('evidence_url') or '').startswith('https://'):
            raise ValueError('자료 추출 일정에는 HTTPS 원문이 필요합니다')
    if kind == 'case':
        _day(values['due_date'])
        if not all(str(values.get(k) or '').strip() for k in ('cause', 'responsible_org', 'action', 'basis')):
            raise ValueError('원인·담당기관·조치·근거를 입력하세요')
        if values['status'] == 'RESOLVED' and not values.get('resolution', '').strip():
            raise ValueError('해결 결과를 입력하세요')
    if kind == 'scenario':
        projects = {p['id']: p for p in service.projects(policy_id=POLICY)}
        if not values.get('name', '').strip() or not values.get('basis', '').strip():
            raise ValueError('시나리오명과 가정을 입력하세요')
        seen = set()
        for a in values.get('adjustments', []):
            if a['project_id'] not in projects or a['stage'] not in STAGES:
                raise ValueError('시나리오 사업·단계를 확인하세요')
            if not -60 <= a['months'] <= 120:
                raise ValueError('일정 조정은 -60~120개월입니다')
            token = (a['project_id'], a['stage'])
            if token in seen:
                raise ValueError('동일 사업·단계 조정 중복')
            seen.add(token)
    # Build outside the write transaction; only scenarios carry a frozen model.
    baseline = None
    if kind == 'scenario' and revision_no == 0:
        from .policy_delivery import build_delivery
        model = build_delivery(service, today())
        baseline = dict(as_of_date=model['as_of_date'], cohorts=model.get('cohorts', []),
                        target_units=model['target_units'], plan_revision=model.get('plan', {}).get('revision_no'))
        baseline['fingerprint'] = hashlib.sha256(json.dumps(baseline, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    eid = entity_id(KINDS[kind], 'officer', key)
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            from sqlalchemy import text
            db.execute(text('SELECT pg_advisory_xact_lock(1019079)'))
        old = db.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)).with_for_update())
        if (old.revision_no if old else 0) != revision_no:
            return dict(conflict=True)
        if old and kind != 'scenario' and (old.payload['project_id'], old.payload['stage']) != (value['project_id'], value['stage']):
            raise ValueError('기존 기록의 사업·단계는 변경할 수 없습니다')
        if kind == 'schedule':
            original = old.payload.get('baseline') if old else None
            if old and old.payload['due_date'] != value['due_date'] and not value.get('change_reason', '').strip():
                raise ValueError('일정 변경 사유를 입력하세요')
            if not original and value['status'] == 'CONFIRMED':
                original = {k: value.get(k) for k in ('due_date', 'units', 'basis', 'evidence_url', 'responsible_org', 'origin')}
                original.update(accepted_on=today().isoformat(), label='담당자 승인 기준선 · 최초 공식 약속 여부는 근거 참조')
            value['baseline'] = original
            value['shift_days'] = (_day(value['due_date']) - _day(original['due_date'])).days if original else None
        if kind == 'agency':
            if old and any(old.payload.get(k)!=value.get(k) for k in ('units','due_date','responsible_org')) and not value.get('change_reason','').strip():
                raise ValueError('기관·목표·기한 변경 사유를 입력하세요')
            value['baseline']=old.payload.get('baseline') if old else None
            if not value['baseline'] and value['status']=='CONFIRMED':
                value['baseline']={k:value.get(k) for k in ('units','due_date','responsible_org','basis','evidence_url')}
        if kind == 'case':
            value['opened_on'] = old.payload['opened_on'] if old else today().isoformat()
            value['resolved_on'] = today().isoformat() if value['status'] == 'RESOLVED' else None
        if kind == 'scenario':
            value['baseline'] = old.payload['baseline'] if old else baseline
        value['key'] = key
        row, outcome = upsert_revision(db, KINDS[kind], 'officer', key, value, 'manual')
        if outcome != 'unchanged':
            db.add(Audit(entity_id=eid, action='EXECUTION_' + kind.upper(), before=old.payload if old else {}, after=value))
        return dict(value, id=eid, revision_no=row.revision_no)

def records(service, as_of=None):
    day = as_of or today()
    schedules = service.rows(KINDS['schedule'], day)
    cases = service.rows(KINDS['case'], day)
    scenarios = service.rows(KINDS['scenario'], day)
    for c in cases:
        c['overdue'] = c['status'] != 'RESOLVED' and c['due_date'] < day.isoformat()
        c['age_days'] = max(0, (day - _day(c['opened_on'])).days)
    # Cases for one project may describe the same homes. Use max, never sum.
    affected = defaultdict(int)
    for c in cases:
        if c['status'] != 'RESOLVED' and c.get('units') is not None:
            affected[c['project_id']] = max(affected[c['project_id']], c['units'])
    agencies={}
    for c in cases:
        org=c['responsible_org']; a=agencies.setdefault(org,dict(name=org,open_cases=0,overdue_cases=0,projects={}))
        if c['status']!='RESOLVED':
            a['open_cases']+=1;a['overdue_cases']+=int(c['overdue'])
            if c.get('units') is not None:a['projects'][c['project_id']]=max(a['projects'].get(c['project_id'],0),c['units'])
    agency_rows=[dict(name=a['name'],open_cases=a['open_cases'],overdue_cases=a['overdue_cases'],affected_known_units=sum(a['projects'].values())) for a in agencies.values()]
    return dict(schedules=schedules, cases=cases,agencies=agency_rows, assignments=service.rows(KINDS['agency'],day),
                scenarios=[{k:v for k,v in r.items() if k != 'baseline'} | {'baseline_date':r['baseline']['as_of_date'], 'baseline_fingerprint':r['baseline']['fingerprint']} for r in scenarios],
                summary=dict(schedule_count=len(schedules), approved_baselines=sum(bool(s.get('baseline')) for s in schedules),
                    open_cases=sum(c['status'] != 'RESOLVED' for c in cases), overdue_cases=sum(c['overdue'] for c in cases),
                    affected_known_units=sum(affected.values()), affected_unknown_cases=sum(c.get('units') is None and c['status'] != 'RESOLVED' for c in cases)))

def history(service, kind, key):
    if kind not in KINDS:
        raise ValueError('관리 유형 오류')
    with service.sessions() as db:
        rows = db.scalars(select(Revision).where(Revision.entity_id == entity_id(KINDS[kind], 'officer', key)).order_by(Revision.revision_no.desc()).limit(100))
        return [dict(revision_no=r.revision_no, recorded_at=r.recorded_at.isoformat(), value={k:v for k,v in r.payload.items() if k != 'baseline'} | ({'baseline':r.payload.get('baseline')} if kind == 'schedule' else {})) for r in rows]

def schedule_goals(service, reference):
    return [dict(scope_kind='project', scope_id=r['project_id'], stage=r['stage'], due_date=r['due_date'],
                 units=r['units'], origin='SOURCE_REVIEW' if r['status'] == 'REVIEW' else 'MANUAL',
                 basis=r['basis'], evidence_url=r.get('evidence_url'), precision='DAY',
                 baseline=r.get('baseline'), managed_schedule=True)
            for r in service.rows(KINDS['schedule'], reference) if r['status'] != 'RELEASED' and r.get('units') is not None]

def shift_months(day, months):
    d = _day(day); count = d.year * 12 + d.month - 1 + months
    year, month = count // 12, count % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1])).isoformat()

def scenario_comparison(service, key):
    row = next((r for r in service.rows(KINDS['scenario']) if r['key'] == key), None)
    if row is None:
        raise ValueError('시나리오를 찾을 수 없습니다')
    baseline = row['baseline']; adjustments = {(a['project_id'], a['stage']):a['months'] for a in row['adjustments']}
    from .policy_delivery_comparison import _schedule_targets
    original = baseline['cohorts']; changed = json.loads(json.dumps(original))
    for c in changed:
        for s in c['schedules']:
            if s['due_date'] <= baseline['as_of_date']:
                continue # Observed/past periods never move.
            months = next((adjustments[(pid, s['stage'])] for pid in c['source_ids'] if (pid, s['stage']) in adjustments), 0)
            shifted = shift_months(s['due_date'], months)
            if months and shifted <= baseline['as_of_date']:
                raise ValueError('시나리오로 미래 일정을 기준일 이전 실적으로 이동할 수 없습니다')
            s['due_date'] = shifted
    stages = {}
    for stage in STAGES:
        a = _schedule_targets(original, stage, '1900-01-01'); b = _schedule_targets(changed, stage, '1900-01-01')
        years = sorted({int(p['date'][:4]) for p in a + b})
        stages[stage] = [dict(year=y, baseline=sum(p['annual_units'] for p in a if p['date'][:4] == str(y)),
                             scenario=sum(p['annual_units'] for p in b if p['date'][:4] == str(y))) for y in years]
    return dict(name=row['name'], basis=row['basis'], baseline_date=baseline['as_of_date'], baseline_fingerprint=baseline['fingerprint'],
                stages=stages, note='별도 분석. 선택 단계의 미래 일정만 이동하며 공식 목표·실적·다른 단계는 변경하지 않습니다.')

def collection_actions(service):
    items = []
    for s in service.sources():
        status = s.get('status'); last = s.get('last_success'); n = s.get('record_count')
        category = 'FAILED' if status == 'FAILED' else 'NOT_STARTED' if not last else 'ACQUIRED'
        if s['id'] == 'building_hub_details' and category == 'FAILED':
            action = '실패 원본 필드 검증·파서 복구 후 마지막 성공 법정동부터 이어받기'
        elif s['id'] == 'ih_supply' and category == 'FAILED':
            action = '접속·HTTP·활용승인 상태 재검증. 응답 전에는 원천 0건으로 판정하지 않음'
        elif category == 'NOT_STARTED':
            action = '서비스 구현·권한·조회조건 확인 후 최초 수집'
        elif category == 'FAILED':
            action = '마지막 성공 자료 보존·오류 원인 수정 후 재시도'
        else:
            action = '수집 범위·갱신 기준일 확인 및 미조회 범위 이어받기'
        coverage=service.latest_collection_stats(s['id']) if s['id'] in ('building_hub','building_register','building_hub_details','building_hub_incheon') else {}
        remaining=coverage.get('scope_remaining_dongs')
        if category=='ACQUIRED' and remaining:category='PARTIAL'
        items.append(dict(remaining_dongs=remaining,completed_dongs=coverage.get('scope_completed_dongs'),id=s['id'], name=s['name'], status=category, collector_status=status,
                          last_success=last, record_count=n, next_action=action))
    return dict(items=items, counts=dict(Counter(i['status'] for i in items)),
                note='0건만으로 원천 0을 판정하지 않습니다. 조회조건 전체 페이지 확인은 Coverage에서 별도 검증합니다.')
