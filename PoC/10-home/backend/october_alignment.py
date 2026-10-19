"""Keep the October announcement's named scopes attached to the complete ledger.

An old source date is a reconciliation issue, never a rule to drop a named
project. Official area totals stay on the area row; they are not replicated
onto every block or used to rewrite accepted project quantities.
"""
import json
from pathlib import Path
from .integrity_diagnostics import belongs

ANNOUNCED='2026-10-16'
BENCHMARK=Path(__file__).with_name('data')/'official_benchmark_20261016.json'
LATER={'CONSTRUCTION':{'CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
       'SUPPLY':{'SUPPLY','MOVE_IN'},'MOVE_IN':{'MOVE_IN'}}


def reached(c, stage, day):
    values=[c['units'] if e.get('units') is None else e['units'] for e in c['events']
        if e['stage'] in LATER[stage] and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=day]
    return min(c['units'],max(values)) if values else None


def build(cohorts, source_projects, reference):
    day=reference.isoformat()
    if day<ANNOUNCED:return None
    benchmark=json.loads(BENCHMARK.read_text())
    cases=[]
    for row in benchmark['rows']+benchmark.get('supplemental_site_rows',[]):
        if not row['id'].startswith('S'):continue
        stage='CONSTRUCTION' if row['stage']=='착공' else 'MOVE_IN' if row['id'] in ('S14','S15','S16') else 'SUPPLY'
        matched=[c for c in cohorts if belongs(c['name'],row['name'])]
        sources=[p for p in source_projects if belongs(p['name'],row['name'])]
        members=[]
        for c in matched:
            events=[e for e in c['events'] if e['stage']==stage and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=day]
            old=[e for e in events if e['event_date']<'2026-01-01'] if stage=='CONSTRUCTION' else []
            future=[s for s in c['schedules'] if s['stage']==stage and s['due_date']>day]
            states=[]
            if old:states.append('START_YEAR_CONFLICT')
            if stage=='CONSTRUCTION' and not events:
                states.append('ANNOUNCED_START_NOT_REFLECTED')
            members.append(dict(id=c['id'],name=c['name'],program_id=c.get('program_id'),region=c['region'],
                municipality_id=c.get('municipality_id'),units=c['units'],current_units=reached(c,stage,day),
                source_ids=c['source_ids'],source_event_dates=sorted({e['event_date'] for e in events if e.get('date_basis')!='OBSERVED_BY'}),
                observed_by_dates=sorted({e['event_date'] for e in events if e.get('date_basis')=='OBSERVED_BY'}),
                future_plan_dates=sorted({s['due_date'] for s in future}),issues=states,
                inclusion_basis='기존 승인 정책 연결 · 공식 발표 사업명 대조',
                evidence_url=c.get('evidence_url')))
        cases.append(dict(id=row['id'],name=row['name'],stage=stage,announced_stage=row['stage'],
            announced_at=ANNOUNCED,official_units=row['official_value'],official_period=row['official_period'],
            evidence_url=row['official_url'],source_correction_note=row.get('source_correction_note'),prior_source_value=row.get('prior_source_value'),official_quantity_qualifier='APPROXIMATE' if row['official_value'] is not None else 'NOT_STATED',
            matched_source_count=len(sources),source_project_ids=[p['id'] for p in sources],
            members=members,included_project_ids=[c['id'] for c in matched],
            managed_capacity=sum(c['units'] for c in matched) if matched else None,
            scope_status='BLOCK_SCOPE_REVIEW' if len(matched)>1 else 'NAMED_PROJECT_LINKED' if matched else 'PROJECT_LINK_REQUIRED',
            comparison_eligible=False,
            note='공식 수치는 발표 범위에 한 번만 보관. 지구 전체 보유량과 발표의 일부 블록 물량을 바로 차감하지 않음. 과거 착공일은 제외 사유로 사용하지 않음.'))
    prior={m['id'] for c in cases for m in c['members'] if 'START_YEAR_CONFLICT' in m['issues']}
    missing={m['id'] for c in cases for m in c['members'] if 'ANNOUNCED_START_NOT_REFLECTED' in m['issues']}
    return dict(version='OCTOBER-NAMED-SCOPE-2',announced_at=ANNOUNCED,as_of_date=day,
        scope='수도권 통합 공급대책의 10월 발표 · 현재 정책에 연결된 사업과 대조',
        official_start_units_lower_bound=99000,official_start_period='부문별 2026년 8월·9월·10월 2주 기준 혼합',
        official_period_basis='서면 3~4쪽: 민간정비 9월, 기타주택 8월, 발표 명목 10월 2주. 과거 착공 전부가 올해 실적에 포함된다는 뜻은 아님.',
        start_components=benchmark.get('start_components',[]),component_reconciliation=benchmark.get('component_reconciliation'),appendix_url=benchmark.get('appendix_url'),
        default_management_scope='PORTFOLIO',exclude_by_start_year=False,write_approved_values=False,
        named_prior_start_ids=sorted(prior),announced_start_not_reflected_ids=sorted(missing),cases=cases)
