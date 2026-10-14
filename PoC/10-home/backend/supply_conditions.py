"""Display-only supply conditions; preserve source scopes, never infer prices."""
from .supply_dashboard import block_key
from .facility_plans import nearby_plans
from .infrastructure import distance_metres


def condition_key(row):
    # Use explicit district/block identifiers across the notice and Incheon sources.
    return block_key(dict(row,source_id='lh_sale'))


def conditions(service, project, location):
    key=condition_key(project)
    peers=[r for r in service.projects() if key and condition_key(r)==key and r['id']!=project['id']]
    records=[project,*peers]
    plans=[r for r in records if r.get('rows') or r.get('source_id') in ('lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent','gh_supply_plan')]
    groups=[]
    for r in plans or [project]:
        tenure=r.get('tenure') or '유형 미확보'
        area_rows=r.get('rows') or []
        groups.append(dict(name=tenure,units=r.get('planned_units'),project_id=r['id'],source_url=r.get('evidence_url'),
                           source_date=r.get('base_date'),areas=[dict(area=x.get('area'),units=x.get('units'),month=x.get('supply_month')) for x in area_rows],
                           area_total=sum(x['units'] for x in area_rows) if area_rows and all(x.get('units') is not None for x in area_rows) else None))
    contractors=list(dict.fromkeys(r['contractor'] for r in records if r.get('contractor')))
    departments=list(dict.fromkeys(x['org'] for r in plans for x in r.get('rows',[]) if x.get('org')))
    prices=[dict(value=r['sale_price'],source_url=r.get('evidence_url'),source_date=r.get('base_date')) for r in records if r.get('sale_price')]
    notices=[r for r in service.rows('supply_conditions') if key and condition_key(r)==key and r.get('notice_status')!='CANCELLED' and r.get('notice_round')!='ADDITIONAL']
    latest=max(notices,key=lambda r:(r.get('source_date') or '',r['id']),default=None)
    if latest:
        if not plans:
            terms=latest.get('terms',[])
            groups=[dict(name=latest.get('tenure') or '공공분양',units=project.get('planned_units'),project_id=project['id'],source_url=latest.get('evidence_url'),source_date=latest.get('source_date'),areas=[dict(area=t['area'],units=t.get('units')) for t in terms],area_total=sum(t['units'] for t in terms) if terms and all(t.get('units') is not None for t in terms) else None)]
        prices=[dict(area=t['area'],value=f"{t['average_price_won']:,}원",source_url=latest.get('evidence_url'),source_date=latest.get('source_date'),basis=t['price_basis']) for t in latest.get('terms',[])]
    facilities,coverage=[], '공식 개교·개원 계획 확인분만 연결합니다. 미수집은 예정 시설이 없음을 의미하지 않습니다.'
    if location and location.get('latitude') is not None and location.get('longitude') is not None:
        facilities,coverage=nearby_plans(location['latitude'],location['longitude'],distance_metres,district_key=key[1] if key else None)
    return dict(groups=groups,developer=project.get('developer'),departments=departments,contractors=contractors,prices=prices,
                source_url=project.get('evidence_url'),facility_plans=facilities,plan_coverage_note=coverage)
