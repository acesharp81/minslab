"""Forecast-adopted occupancy management targets, on a distinct market population."""
def build_occupancy_monitor(plan, config, reference):
    outlook=plan.get('occupancy_outlook') or {}
    records=config.get('occupancy_observations',[])
    result=[]
    for region in ('수도권','서울특별시'):
        target_total=0;actual_total=0;complete=True;years=[]
        for entry in outlook.get('annual',[]):
            if entry['year']<outlook.get('baseline_year',2025):continue
            year=entry['year'];goal=entry['units'] if region=='수도권' else entry['seoul_units']
            target_total+=goal
            observations=[r for r in records if r['region']==region and r['year']==year and r['as_of_date']<=reference.isoformat()]
            obs=max(observations,key=lambda r:r['as_of_date']) if observations else None
            actual=obs['units'] if obs else None
            due=f'{year}-12-31';closed=bool(obs and obs['as_of_date']>=due)
            if closed:actual_total+=actual
            else:complete=False
            gap=max(0,goal-actual) if actual is not None else None
            status='DELAYED' if gap and closed else 'ACHIEVED' if actual is not None and actual>=goal else 'VERIFY' if due<=reference.isoformat() else 'UPCOMING'
            years.append(dict(year=year,target_units=goal,target_cumulative_units=target_total,actual_units=actual,
                actual_cumulative_units=actual_total if complete else None,gap_units=gap,
                status=status,due_date=due,observation=obs,coverage='FULL_YEAR' if closed else 'PARTIAL' if obs else 'NOT_ACQUIRED'))
        result.append(dict(region=region,annual=years))
    return dict(source=outlook,scopes=result,notice='수도권 아파트 전체 전망을 채택한 입주 관리목표. 135만 신규 착공 원장과 모집단이 달라 합산하지 않습니다. 실적 미확보는 0호가 아니며 지연 판정을 대기합니다.')
