"""Availability indicators for the registered 9.7 scope, not national completeness."""
from .api_samples import today

STAGES = ('BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'SUPPLY', 'MOVE_IN')


def indicator(label, count, total, note):
    return dict(label=label, count=count, total=total, percent=round(count / total * 100, 1) if total else None, note=note)


def build_status(service, matrix):
    projects = matrix['items']; ids = {p['id'] for p in projects}; n = len(projects)
    raw = {p['id']: p for p in service.projects(policy_id='POL_2025_0907') if p['id'] in ids}
    cells = [p['cells'][s] for p in projects for s in STAGES]
    schedules = [s for s in service.rows('execution_schedule') if s['project_id'] in ids and s.get('status') != 'RELEASED']
    cases = [c for c in service.rows('execution_case') if c['project_id'] in ids]
    scenarios = service.rows('execution_scenario')
    assignments=[r for r in service.rows('execution_agency') if r['project_id'] in ids and r.get('status')=='CONFIRMED']
    baseline_keys = {(s['project_id'], 'CONSTRUCTION' if s['stage'] == 'COMPLETION' else s['stage']) for s in schedules if s.get('baseline')}
    pairs = sum(bool(c.get('dated_plan_available') and c.get('actual_available')) for c in cells)
    def rate(label, count, total=n, note=''): return indicator(label, count, total, note)
    metrics = {
        'F-01': rate('지도 위치 근거가 있는 사업 기록', sum(bool(p.get('lineage', {}).get('keys', {}).get('coordinates')) for p in projects), note='대표·근사 위치 포함. 전국 사업 모집단 확보율이 아닙니다.'),
        'F-02': rate('일정 목표와 실적 근거를 함께 확보한 셀', pairs, len(cells), '사업화~입주 5단계 기준. 목표·실적의 최종 물량 범위 검토는 별도입니다.'),
        'F-03': rate('실적·진척 근거를 확보한 셀', sum(bool(c.get('actual_available')) for c in cells), len(cells), '5단계 사업 기록 기준. 실제 입주 세대수 확보율과 다릅니다.'),
        'F-04': rate('사업명·지역·계획량을 확보한 기록', sum(bool(p.get('name') and p.get('region') and p.get('planned_units') is not None) for p in raw.values()), note='상세정보 전체 항목 완성률이 아닌 세 가지 기본 필드 지표입니다.'),
        'F-05': rate('날짜가 있는 단계 계획을 확보한 사업', sum(any(p['cells'][s].get('dated_plan_available') for s in STAGES) for p in projects), note='최소 한 단계 기준. 모든 연도·단계 계획의 완비를 의미하지 않습니다.'),
        'F-06': rate('담당자 승인 최초 기준선 등록 셀', len(baseline_keys), len(cells), '최초 약속 대비 지연 판정에 필요한 기준선입니다. 현재 예정일과 구분합니다.'),
        'F-07': rate('원인·기관·조치·기한이 채워진 병목 기록', sum(all(c.get(k) for k in ('cause', 'responsible_org', 'action', 'due_date')) for c in cases), len(cases), '등록된 병목만 분모로 사용합니다. 미등록 병목의 존재 여부는 알 수 없습니다.'),
        'F-08': rate('승인 기관 배정 목표를 등록한 사업',len({r['project_id'] for r in assignments}),note='기관 역할·누적 목표·기한·HTTPS 근거를 승인한 사업 기록입니다. 입력 기능 완비와 공식 배정자료 확보는 구분합니다.'),
        'F-09': rate('공급 또는 입주 예정일이 있는 사업', sum(any(p['cells'][s].get('dated_plan_available') for s in ('SUPPLY', 'MOVE_IN')) for p in projects), note='원천 예정 일정 기준이며 실제 입주 확인과 구분합니다.'),
        'F-10': rate('원천 링크와 기준일이 있는 사업', sum(bool(p.get('evidence_url') and p.get('base_date')) for p in raw.values()), note='메타데이터 존재율입니다. 원천 내용의 정확도·최신성·전수 수집을 보증하지 않습니다.'),
        'F-11': rate('목표·실적 동시 확보 셀', pairs, len(cells), '종합 판단에 필요한 자료의 일부 지표입니다. 시차·공급범위 검토가 추가로 필요합니다.'),
        'F-12': rate('가정·기준 원장을 저장한 시나리오', sum(bool(s.get('basis') and s.get('baseline')) for s in scenarios), len(scenarios), '등록된 분석 시나리오 기준. 예측 정확도나 공식 전망 충족률이 아닙니다.'),
    }
    return dict(as_of_date=matrix.get('as_of_date') or today().isoformat(), policy_id='POL_2025_0907',
                project_count=n, metrics=metrics, notice='등록된 9·7 사업 기록의 데이터 확보 지표입니다. 원천 중복 기록을 포함할 수 있으며 고유 실사업·전국 모집단 확보율이 아닙니다.')
