"""Compact target/measurement presentation shared by matrix and project detail."""
from .project_profile import target_default,progress_default,STAGES
from .input_status import input_status
from .collection_tags import tag
from .stage_chronology import field_tag,propagate_upcoming

FIELDS={'target.date':'목표일','target.units':'목표량','measurement.date':'측정일','measurement.units':'측정량'}

def annotate(cells,project,profile,goals,reference,policy=None):
    for stage,c in cells.items():
        c['officer_confirmed']=any(r.get('officer_confirmed') or r.get('source_id')=='officer' for r in c['sources'])
        for r in c['sources']:
            r['input_status']=input_status(r,c.get('assessment'));r['collection_tag']=tag(r)
        c['management']=dict(target=[],measurement=[],remaining=[])
        if stage=='POLICY':
            c['management']['target']=[dict(milestone='POLICY',date=(policy or {}).get('announced_at') or (policy or {}).get('base_date'),units=project.get('planned_units'),manual=bool(project.get('manual_fields',{}).get('planned_units')),inferred=bool(project.get('manual_fields',{}).get('planned_units',{}).get('inferred')),input_status=input_status(project.get('manual_fields',{}).get('planned_units',{})))]
            r=c['management']['target'][0]
            r['collection_tag']=tag(dict(r,evidence_url=(policy or {}).get('evidence_url') or project.get('mapping',{}).get('evidence_url')),missing=not(r['date'] or r['units'] is not None))
            continue
        for milestone in (('CONSTRUCTION','COMPLETION') if stage=='CONSTRUCTION' else (stage,)):
            target=target_default(c,milestone,goals.get(milestone))
            measured=progress_default(c,milestone,profile.get('progress',{}).get(milestone))
            for kind,v,key in [('target',target,'due_date'),('measurement',measured,'event_date')]:
                manual=v.get('origin')=='MANUAL' or v.get('manual',False)
                c['management'][kind].append(dict(milestone=milestone,label=STAGES[milestone],date=v.get(key),units=v.get('units'),manual=manual,inferred=bool(v.get('inferred')),actor=v.get('actor'),reason=v.get('reason'),input_basis=v.get('input_basis'),field_provenance=v.get('field_provenance',{}),input_rule=v.get('input_rule'),changed_at=v.get('changed_at'),input_status=input_status(v,c.get('assessment'),manual or (kind=='measurement' and c['officer_confirmed']))))
                row=c['management'][kind][-1]
                # Retain the provenance of the actual selected event, not any other stage's approval.
                candidates=[r for r in c['sources'] if r.get('kind')==('PLAN' if kind=='target' else 'ACTUAL') and (r.get('milestone')==milestone or not r.get('milestone') and milestone!='COMPLETION') and (not row['date'] or r.get('date')==row['date']) and (row['units'] is None or r.get('units')==row['units'])]
                source=next((r for r in candidates if not input_status(r).startswith('ESTIMATED')),candidates[0] if candidates else {})
                provenance=dict(source,**v)
                if not manual and source.get('inferred'):
                    row['inferred']=True;row['input_status']=input_status(source)
                future=kind=='measurement' and (target.get('due_date') or '')>reference.isoformat()
                row['collection_tag']=tag(provenance,upcoming=future,missing=not(row['date'] or row['units'] is not None))
                row['field_tags']={}
                for field,value in [('date',row['date']),('units',row['units'])]:
                    exact=[r for r in c['sources'] if r.get('kind')==('PLAN' if kind=='target' else 'ACTUAL') and r.get('pct') is None and not r.get('scope_partial') and (r.get('milestone')==milestone or not r.get('milestone') and milestone!='COMPLETION') and r.get(field)==value and value not in (None,'')]
                    own=next((r for r in exact if not input_status(r).startswith('ESTIMATED')),exact[0] if exact else source)
                    row['field_tags'][field]=field_tag(v,own,field,missing=value in (None,''),upcoming=future)
                for field,value in [('date',v.get(key)),('units',v.get('units'))]:
                    if value not in (None,''):continue
                    code=c.get('progress',{}).get('code')
                    observed_state=profile.get('stage_states',{}).get(milestone,{}).get('status')=='NOT_OBSERVED'
                    future=kind=='measurement' and (target.get('due_date') or '')>reference.isoformat()
                    unavailable=(c.get('assessment') or {}).get('status')=='COLLECTION_UNAVAILABLE'
                    label='일정 미정' if code=='SCHEDULE_PENDING' and kind=='measurement' else '시기 미도래·미진행' if future else '미측정 · 실적 근거 없음' if observed_state else '수집 불가 확정' if unavailable else '추가 확인 필요'
                    c['management']['remaining'].append(dict(milestone=milestone,field=kind+'.'+field,label=label.replace('시期','시기'),code='UPCOMING' if future else 'NOT_OBSERVED' if observed_state else 'COLLECTION_UNAVAILABLE' if unavailable else 'UNRESOLVED'))
        pct=next((r for r in c['sources'] if r.get('pct') is not None and r.get('source_id')=='officer'),None) or next((r for r in c['sources'] if r.get('pct') is not None),None)
        if pct:c['management']['progress_pct']=dict(date=pct.get('date'),pct=pct['pct'],manual=pct.get('source_id')=='officer',input_status=pct.get('input_status'),collection_tag=tag(pct))

    propagate_upcoming(cells,reference.isoformat())
