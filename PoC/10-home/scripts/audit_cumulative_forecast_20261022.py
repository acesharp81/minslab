"""Reproduce cumulative membership and year-end forecast checks from API snapshots."""
import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path

from backend.policy_delivery_comparison import comparison_index, _schedule_targets, METRICS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/analysis/cumulative_forecast_review_20261022'
DAY = '2026-10-22'
END = '2026-12-31'
LATER = {
    'BUSINESS': {'BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
    'APPROVAL': {'APPROVAL','CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
    'CONSTRUCTION': {'CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'},
    'COMPLETION': {'COMPLETION','MOVE_IN'}, 'SUPPLY': {'SUPPLY','MOVE_IN'}, 'MOVE_IN': {'MOVE_IN'},
}


def last(points, cutoff=END):
    return next((p['units'] for p in reversed(points) if p['date'] <= cutoff), None)


def write_csv(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def normalized(value):
    # SQL rows with equal event dates have no guaranteed tie order after restart.
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    if isinstance(value,list):return sorted((normalized(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    return value


def main():
    before=json.loads((OUT/'before.json').read_text())
    after=json.loads((OUT/'after.json').read_text())
    cs=after['portfolio_cohorts']
    assert normalized(cs)==normalized(before['portfolio_cohorts']), '원천 사업/사건/계획 변경'
    assert after['official_alignment']==before['official_alignment'], '공식 대조 변경'
    assert after['regional_start_months']==before['regional_start_months']
    for name in ('portfolio_comparisons','yearly_comparisons'):
        for key,scope in before[name].items():
            actual=json.loads(json.dumps(after[name][key]))
            for metric in actual['metrics'].values():metric['tracking'].pop('forecast_points',None)
            assert normalized(actual)==normalized(scope), (name,key,'기존 목표/관측/판정 변경')

    rows=[];by_id={}
    for c in cs:
        for metric in METRICS:
            events=[e for e in c['events'] if e['stage'] in LATER[metric]
                    and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<=DAY]
            observed=min(c['units'],max((e.get('units') if e.get('units') is not None else c['units'] for e in events),default=0)) if events else None
            planned=last(_schedule_targets([c],metric,'1900-01-01'))
            expected=max(observed or 0,planned or 0) if observed is not None or planned is not None else None
            row=dict(project_id=c['id'],project_name=c['name'],program_id=c.get('program_id'),region=c['region'],
                     metric=metric,current_units=observed,saved_plan_units=planned,expected_units=expected,
                     remaining_plan_units=expected-(observed or 0) if expected is not None else None,
                     restored_to_forecast_units=(expected or 0)-(planned or 0),
                     prior_start=c['eligibility_status']=='PRE_POLICY_START',
                     event_dates=';'.join(sorted({e['event_date'] for e in events})),evidence_url=c['evidence_url'])
            rows.append(row);by_id[(c['id'],metric)]=row

    full=comparison_index(dict(after['plan'],period_start='1900-01-01',portfolio=True),cs,
                          after['settings'],[],date.fromisoformat(DAY))
    checks=0
    for key,scope in full.items():
        # Independently select the members of every policy/program/region/city/project scope.
        members=cs
        for part in key.split('|'):
            if part=='policy':continue
            kind,ident=part.split(':',1)
            field={'program':'program_id','region':'region','city':'municipality_id','project':'id'}[kind]
            members=[c for c in members if c.get(field)==ident]
        for metric,value in scope['metrics'].items():
            values=[by_id[(c['id'],metric)] for c in members]
            for field,series in [('current_units','actual_points'),('expected_units','forecast_points')]:
                known=[r[field] for r in values if r[field] is not None]
                independent=sum(known) if known else None
                assert last(value['tracking'][series])==independent,(key,metric,field)
            current=last(value['tracking']['actual_points'])
            expected=last(value['tracking']['forecast_points'])
            assert current is None or expected>=current,(key,metric)
            checks+=1

    summary=[]
    for metric,label in METRICS.items():
        values=[r for r in rows if r['metric']==metric]
        t=after['portfolio_comparisons']['policy']['metrics'][metric]['tracking']
        summary.append(dict(stage=metric,label=label,current_units=last(t['actual_points']),
            previous_year_end_units=last(t['target_points']),year_end_units=last(t['forecast_points']),
            additional_plan_units=sum(r['remaining_plan_units'] or 0 for r in values),
            restored_forecast_units=sum(r['restored_to_forecast_units'] for r in values),
            forecast_missing_projects=sum(r['expected_units'] is None for r in values)))
    old=[]
    for c in cs:
        starts=[e for e in c['events'] if e['stage']=='CONSTRUCTION' and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<='2025-12-31']
        if starts:
            row=by_id[(c['id'],'CONSTRUCTION')]
            old.append(dict(project_id=c['id'],project_name=c['name'],program_id=c.get('program_id'),
                start_dates=';'.join(sorted({e['event_date'] for e in starts})),
                cumulative_construction_units=row['current_units'],date_basis=';'.join(sorted({e.get('date_basis') or ('ESTIMATED' if e.get('inferred') else 'EVENT_OR_UNSPECIFIED') for e in starts})),
                evidence_urls=';'.join(sorted({e.get('evidence_url') for e in starts if e.get('evidence_url')}))))
    assert len(old)==len(after['historical'])
    write_csv('project_stage_forecast.csv',rows)
    write_csv('prior_year_start_included.csv',old)
    write_csv('stage_summary.csv',summary)
    result=dict(as_of=DAY,projects=len(cs),old_csv_projects=len(before['cohorts']),
        prior_year_start_projects=len(old),prior_year_start_cumulative_units=sum(r['cumulative_construction_units'] for r in old),
        scopes=len(full),scope_stage_checks=checks,official_comparison_unchanged=True,
        source_events_and_plans_unchanged=True,summary=summary)
    (OUT/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
