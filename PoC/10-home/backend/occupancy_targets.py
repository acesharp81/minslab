"""Planned occupancy quantities are targets, never observed move-in counts."""
from collections import defaultdict
from .supply_dashboard import block_key
from .roadmap import month as schedule_month

def occupancy_schedules(service,projects,reference):
    owners=defaultdict(list)
    for p in projects:
        key=block_key(p)
        if key:owners[key].append(p)
    groups=defaultdict(list)
    for r in service.rows('lh_movein_plan',reference):
        key=block_key(dict(r,district=r.get('district_name')))
        if key in owners and r.get('units') is not None and r.get('move_in_plan_month'):
            groups[key].append(r)
    result={}
    # Current supply plans retain occupancy quantities in their original tenure/area rows.
    # Date-only move_in_start remains untouched; these are planned quantities only.
    for p in projects:
        dimensions=defaultdict(list)
        for r in p.get('rows',[]):
            when=schedule_month(r.get('move_in_month'))
            if when and isinstance(r.get('units'),int):dimensions[when].append(r['units'])
        if dimensions:
            remaining=p.get('planned_units') or sum(sum(v) for v in dimensions.values())
            schedules=[]
            for when,values in sorted(dimensions.items()):
                units=min(remaining,sum(values));remaining-=units
                if units<=0:continue
                schedules.append(dict(stage='MOVE_IN',due_date=when+'-01',units=units,precision='MONTH',origin='SOURCE',
                    source_id=p['source_id'],source_object_id=p['id'],source_base_date=p['base_date'],
                    basis='원천 면적·유형별 입주 예정 물량 · 실입주 아님',evidence_url=p['evidence_url']))
            result[p['id']]=schedules
    for key,rows in groups.items():
        # Latest published edition per block. Sum non-overlapping tenure/area rows.
        version=max(str(r.get('dataset_version','')) for r in rows)
        latest={r['id']:r for r in rows if str(r.get('dataset_version',''))==version}
        by_month=defaultdict(list)
        for r in latest.values():by_month[r['move_in_plan_month']].append(r)
        for p in owners[key]:
            schedules=[];remaining=p.get('planned_units') or 0
            for month,rs in sorted(by_month.items()):
                units=min(remaining,sum(r['units'] for r in rs));remaining-=units
                if units<=0:continue
                schedules.append(dict(stage='MOVE_IN',due_date=month+'-01',units=units,precision='MONTH',origin='SOURCE',
                    source_id=rs[0]['source_id'],source_object_id='occupancy:'+str(key),source_base_date=version,
                    basis='LH 공식 연간 입주계획 · 동일 지구·블록 연결 검토 · 실입주 아님',evidence_url=rs[0]['evidence_url'],review_status='REVIEW'))
            result.setdefault(p['id'],[]).extend(schedules)
    return result
