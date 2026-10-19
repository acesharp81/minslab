"""Map selections use the same deduplicated stage ledger as policy progress."""
from datetime import date
from .policy_delivery_comparison import METRICS, _events, _schedule_targets


def build_progress(model, project_ids, region=None, program_id=None, level='block'):
    ids=set(project_ids)
    cohorts=[c for c in model.get('portfolio_cohorts', []) if ids.intersection(c['source_ids']) or c['id'] in ids]
    if program_id:
        cohorts=[c for c in cohorts if c.get('program_id')==program_id or c.get('program')==program_id]
    if region:
        cohorts=[c for c in cohorts if c.get('region')==region]
    ref=date.fromisoformat(model['as_of_date'])
    metrics={stage:dict(label=METRICS[stage],target_points=_schedule_targets(cohorts,stage,'1900-01-01'),
                       actual_points=_events(cohorts,stage,ref,'1900-01-01',cumulative=True),
                       display_actual_points=_events(cohorts,stage,ref,'1900-01-01'),
                       actual_period=confirmed_period(cohorts,stage,ref))
             for stage in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
    target=sum(c['units'] for c in cohorts)
    if level=='region':
        programs={c.get('program_id') for c in cohorts}
        profile_id=next(iter(programs)) if len(programs)==1 else program_id
        profile=model.get('plan',{}).get('program_profiles',{}).get(profile_id,{}).get('values',{})
        selected=profile.get('region:'+region) if program_id and region else profile.get('target_units') if program_id else (model.get('plan',{}).get('region_allocations',{}).get(region) if region else model.get('target_units',model.get('plan',{}).get('target_units')))
        if selected is not None:target=selected
    matched={pid for c in cohorts for pid in c['source_ids']} | {c['id'] for c in cohorts}
    return dict(as_of_date=model['as_of_date'],stages=model['stages'],comparisons=metrics,policy_target=target,
                project_count=len(cohorts),source_record_count=len(ids&matched),unmatched_count=len(ids-matched),
                delays=[r for r in model.get('issues',[]) if r.get('status')=='DELAYED' and r['project_id'] in matched])


def confirmed_period(cohorts, stage, reference):
    """Only dated actual records of this stage; never borrow later stages or goals."""
    dates=sorted({e['event_date'] for c in cohorts for e in c.get('events',[])
                  if e.get('stage')==stage and e.get('status','ACTUAL')=='ACTUAL'
                  and not e.get('inferred') and e.get('date_basis')!='OBSERVED_BY' and e.get('event_date') and e['event_date']<=reference.isoformat()})
    return dict(start=dates[0] if dates else None,end=dates[-1] if len(dates)>1 else None)
