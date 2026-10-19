"""Re-evaluate the external benchmark from current, frozen HOME evidence.

Benchmark values are isolated in this module; they never create source events.
Whole-population agreement requires a verified population, not a similar sum.
"""
from collections import Counter
from pathlib import Path
import json
import re
from .subject_identity import taxonomy
from .independent_metrics import digest

BENCHMARK = Path(__file__).parent/'data/official_benchmark_20261016.json'
ACTUAL_METRICS = {'M04','M07','M08','M09','M10','M11','M14','M15','M16','M19','M30','M31'}
TARGETS = {'M01','M02','M03','M06','M35','M36'}
PLANS = {'M05','M17','M18','M20','M21','M22'}
MODES = ('NEW_BUILD','REDEVELOPMENT','NEW_PURCHASE_AGREEMENT','EXISTING_PURCHASE','LEASE_SUPPORT')


def belongs(name, area):
    normalize=lambda v:re.sub(r'[^가-힣A-Z0-9]','',str(v).upper())
    name,area=normalize(name),normalize(area)
    if area=='남양주왕숙':return area in name and '남양주왕숙2' not in name
    if area=='흑석11구역':return bool(re.search(r'흑석11(?!\d)',name))
    if area=='신림2구역':return bool(re.search(r'신림2(?:재정비|구역)',name))
    return area in name


def evaluate(snapshot, projects, delivery, annual, source_counts, identity_counts, ih_stats=None, reference_rows=()):
    benchmark=json.loads(BENCHMARK.read_text())
    from .report_reproducibility import evaluate as assess_report
    report=assess_report(benchmark,snapshot,projects,delivery,annual,source_counts,reference_rows)
    report_rows={r['id']:r for r in report['rows']}
    result=snapshot['result'];events=result['selected_events'];rows=[]
    active=[p for p in projects if p.get('mapping',{}).get('status') not in ('RELEASED','REJECTED')]
    by_region=Counter(p.get('region') for p in active)
    by_mode=Counter((p.get('region'),taxonomy(p)['acquisition_mode']) for p in active)
    for original in benchmark['rows']:
        r=dict(original,actual_value=None,actual_scope=None,evidence_ids=[],event_ids=[],
               state='pending',eligible=False,independent_match=False,metric_origin=None,
               checked_at=snapshot['context']['known_at'],next_action='대상 명부·원천 사건·기간 정의를 확보하고 재집계')
        key=r['id']
        if not r['numeric']:
            r.update(state='excluded',status='QUALITATIVE',explanation='수치가 없는 정성 과제·입주 진행 설명. 수치 일치율 분모에서 제외.',next_action='과제·진행 상태의 원문과 시점을 별도로 검증')
        elif key=='M01':
            value=delivery.get('plan',{}).get('target_units')
            r.update(actual_value=value,actual_scope='2026~2030 · 등록된 9·7 최초 목표',metric_origin='POLICY_TARGET',
                status='MATCH_EXACT' if value==r['official_value'] else 'VERSION_DIFFERENCE',
                explanation='현재 등록된 최초 목표 판본을 대조. 실제 공급 사건의 독립 산출 능력과 별도.',next_action='후속 통합 목표의 포함관계·변경 판본 관리')
            if value==r['official_value']:r.update(state='matched',eligible=True)
        elif key=='M03':
            value=next((a['units'] for a in delivery.get('plan',{}).get('annual',[]) if a['year']==2026),None)
            r.update(actual_value=value,actual_scope='2026 · 등록된 9·7 목표',metric_origin='POLICY_TARGET',status='VERSION_DIFFERENCE',
                explanation='최초 목표와 후속 발표의 변경 근거·동일 버전 여부 미확인.',next_action='목표 변경의 원문·시행시점·포함 사업 판본 확인')
        elif key=='M31':
            cell=next((a['metrics']['착공'] for a in annual.get('rows',[]) if a['year']==2026 and a.get('region')=='서울특별시'),{})
            value=cell.get('units');period=cell.get('period_label','');months=cell.get('months',[])
            # Only the explicitly identified January–August statistical series.
            period_ok=cell.get('periods')==8 and cell.get('through_period')=='202608'
            period=period or str(cell.get('through_period') or '')
            r.update(actual_value=value,actual_scope='2026 서울 · '+str(period or cell.get('coverage','기간 확인 필요')),
                metric_origin='OFFICIAL_STAT',status='PERIOD_UNVERIFIED',
                explanation='월별 공식 통계 참조값. 사업 사건 직접 합산과 분리.',next_action='동일 기간의 사업별 착공 사건을 확보하여 독립 합계 검증')
            if value is not None and period_ok:
                r['status']='MATCH_ROUNDED' if abs(value-r['official_value'])<500 else 'VALUE_DIFFERENCE'
                if r['status']=='MATCH_ROUNDED':r.update(state='matched',eligible=True)
        elif key.startswith('S'):
            candidates=[p for p in active if belongs(p['name'],r['name'])]
            ids={p['id'] for p in candidates};r['evidence_ids']=sorted(ids)
            r['managed_name_found']=bool(candidates)
            event_type='CONSTRUCTION_STARTED' if r['stage']=='착공' else 'RECRUITMENT_PUBLISHED'
            subset=[e for e in events if e['project_id'] in ids and e['event_type']==event_type]
            r.update(event_ids=[e['event_id'] for e in subset],metric_origin='INDEPENDENT_EVENT_AGGREGATE',
                actual_value=sum(e['quantity'] for e in subset) if subset else None,
                actual_scope='등록 사업 중 직접 원천·날짜·물량이 확인된 부분 범위',
                status='PARTIAL_SCOPE' if subset else 'EVENT_EVIDENCE_MISSING',
                explanation=f'관리 후보 {len(candidates)}건, 직접 인정 사건 {len(subset)}건. 지구 전수·발표 마감시점·유형 구획 미검증.',
                next_action='구성 블록·유형 명부와 실제 사건일·물량의 직접 원문 확보')
            if r['stage']!='착공':
                r.update(actual_value=None,event_ids=[],status='PLAN_SCOPE_GAP',
                    explanation=f'관리 후보 {len(candidates)}건. Q4 예정과 이미 발생한 모집을 분리하여 계획 판본·회차·구획 검증 필요.')
            legacy=[c for c in delivery.get('portfolio_cohorts',[]) if belongs(c['name'],r['name'])]
            r['management_actuals']=[dict(project_id=c['id'],name=c['name'],date=e.get('event_date'),units=e.get('units'),inferred=bool(e.get('inferred')))
                for c in legacy for e in c.get('events',[]) if e.get('status')=='ACTUAL' and e.get('stage')=='CONSTRUCTION']
            if key=='S01' and any(e['inferred'] for e in r['management_actuals']):
                r['explanation']+=' 추정 표식이 있는 관리 입력과 직접 원천 사건을 분리했다. 현재 직접 합계는 별도 원문으로 검증된 사건만 포함.'
        elif key in ACTUAL_METRICS:
            capability=report_rows[key]
            r.update(status='PARTIAL_SCOPE' if capability['own_value'] is not None else capability['status'],metric_origin='INDEPENDENT_EVENT_AGGREGATE',
                partial_registered_value=capability['own_value'],event_ids=capability['event_ids'],evidence_ids=capability['project_ids'],
                actual_scope=capability.get('own_scope'),explanation=capability['blocker'],next_action=capability['next_action'])
            if key=='M04':
                latest=delivery.get('regional_start_months',[])[-1:]
                r['statistical_reference']=latest[0] if latest else None
                r['explanation']+=' 보유 월별 통계와 10월 둘째 주 발표는 기간이 달라 수치 오차를 계산하지 않음.'
        elif key in TARGETS:
            r.update(status='VERSION_MISSING',explanation='같은 대상·단위·기간의 목표 판본 미확보.',next_action='정책 목표 원문과 최초·변경 판본 확인; 실제 사건 합산과 구분')
        elif key in PLANS:
            r.update(status='PLAN_SCOPE_GAP',explanation='전체 대상 사업의 동일 기간 계획·전망 구성과 판본 미검증.',next_action='개별 사업 원천 계획을 같은 기간·범위로 합산하고 변경 이력 보존')
        else:
            r.update(status='SOURCE_NOT_ACQUIRED',explanation='과제·접수·지수 등 해당 지표의 원천 명부·시계열 미확보.',next_action='주택 사건과 별개인 원천 데이터 계약·단위·기간 확보')
        rows.append(r)
    numeric=[r for r in rows if r['numeric']];matched=[r for r in numeric if r['state']=='matched']
    actual=[r for r in numeric if r['id'] in ACTUAL_METRICS or r['id'].startswith('S') and r['stage']=='착공']
    agreement=dict(total_rows=len(rows),numeric_rows=len(numeric),confirmed_matches=len(matched),
        pending=len(numeric)-len(matched),excluded=len(rows)-len(numeric),comparable=len(matched),
        exact=sum(r['status']=='MATCH_EXACT' for r in matched),overall_confirmed_percent=round(100*len(matched)/len(numeric),2),
        comparable_match_percent=100 if matched else None,rows=rows,
        evaluated_at=snapshot['context']['known_at'],evaluation_version='CURRENT-PRIMARY-EVIDENCE-2',
        independent_actual_matches=sum(r['independent_match'] for r in actual),independent_actual_rows=len(actual),
        definition_change='최초 대조에서 포함했던 추정 담당자 실적은 직접 원천 일치에서 제외. 목표·공식 통계 참조 일치는 별도 출처로 표시.',
        managed_site_rows=sum(bool(r.get('managed_name_found')) for r in rows if r['id'].startswith('S')))
    reasons=Counter(reason for e in result['exclusions'] for reason in e['validation_reasons'])
    population=dict(status='UNVERIFIED',expected_projects=None,managed_source_records=len(active),
        region_counts=dict(by_region),source_counts=source_counts,identity_counts=identity_counts,
        cells=[dict(region=region,acquisition_mode=mode,managed_source_records=by_mode[region,mode],expected_projects=None,status='DENOMINATOR_UNVERIFIED')
            for region in ('서울특별시','경기도','인천광역시') for mode in MODES],
        note='원천 행 수·관리 후보 수는 실사업 전수 분모가 아님. 중복 원천·부분 유형은 별개 사업으로 합산하지 않음.')
    diagnostics=dict(known_at=snapshot['context']['known_at'],snapshot_id=snapshot['id'],agreement=agreement,
        population=population,event_blockers=dict(reasons),conflicts=result['conflicts'],ih_collection=ih_stats or {},
        missing_actual_metrics=[m['metric_code'] for m in result['metrics'] if m['value'] is None],
        benchmark_sha256=digest(benchmark),benchmark_use='EXTERNAL_VALIDATION_ONLY',report_reproducibility=report)
    return diagnostics
