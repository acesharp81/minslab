"""Nine source-labelled housing indicators below the existing progress reports."""
import json
import re
from collections import defaultdict
from datetime import date
from calendar import monthrange
from pathlib import Path
from .policy_delivery_comparison import _events, _schedule_targets
from .annual_supply import SOURCES as SUPPLY_SOURCES
from .api_samples import today

CAPITAL=('서울특별시','경기도','인천광역시')
REFERENCE=json.loads((Path(__file__).parent/'data/housing_indicator_reference.json').read_text())
STAGES=('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')


def known(v):return isinstance(v,(int,float)) and not isinstance(v,bool)


def month_before(period,count=1):
    y,m=map(int,period.split('-'));i=y*12+m-1-count
    return f'{i//12:04}-{i%12+1:02}'


def price_series(rows,region,municipality,reference):
    chosen=sorted([r for r in rows if r.get('region')==region and r.get('municipality')==municipality and r['period']<=reference.strftime('%Y-%m')],key=lambda r:r['period'])
    index={r['period']:r for r in chosen};result=[]
    for row in chosen:
        old=index.get(month_before(row['period']))
        rate=(row['index']/old['index']-1)*100 if old and old['index']>0 and old.get('source_vintage')==row.get('source_vintage') and old.get('index_basis')==row.get('index_basis') else None
        result.append(dict(period=row['period'],index=row['index'],change_pct=round(rate,3) if rate is not None else None,index_basis=row.get('index_basis'),source_url=row.get('evidence_url')))
    return result


def annual_series(statistics,regions,reference):
    cells=defaultdict(dict)
    for r in statistics:
        metric=r.get('statistic_metric');period=str(r.get('statistic_period',''))
        if r.get('region') not in regions or metric not in ('인허가','착공','준공') or not known(r.get('units')) or not re.fullmatch(r'\d{4}(\d{2})?',period):continue
        if metric=='인허가' and len(period)!=4:continue
        if metric!='인허가' and len(period)!=6:continue
        year=int(period[:4])
        if year>reference.year or len(period)==6 and period>reference.strftime('%Y%m'):continue
        key=(metric,r['region'],year);slot=period[4:] or 'YEAR'
        if slot in cells[key]:raise ValueError('지역 공급 통계 기간 중복')
        cells[key][slot]=r['units']
    years=sorted({k[2] for k in cells});result=[]
    for y in years:
        metrics={}
        for metric in ('인허가','착공','준공'):
            items=[cells.get((metric,r,y),{}) for r in regions];expected=['YEAR'] if metric=='인허가' else [f'{m:02}' for m in range(1,13)]
            common=set.intersection(*(set(v) for v in items)) if items else set()
            complete=all(set(v)==set(expected) for v in items)
            metrics[metric]=dict(units=sum(v[p] for v in items for p in common) if common else None,complete=complete,periods=len(common),through_period=max(common) if common else None)
        result.append(dict(year=y,metrics=metrics))
    return result


def monthly_starts(statistics,regions,year,reference,cohorts):
    lookup={}
    for r in statistics:
        p=str(r.get('statistic_period',''))
        if r.get('region') in regions and r.get('statistic_metric')=='착공' and len(p)==6 and p.isdigit() and known(r.get('units')):lookup[(r['region'],p)]=r['units']
    events=_events(cohorts,'CONSTRUCTION',reference,'1900-01-01')
    confirmed=[dict(c,events=[e for e in c.get('events',[]) if not e.get('inferred') and e.get('review_status')!='REVIEW']) for c in cohorts if c.get('mapping_status')=='CONFIRMED']
    accepted=_events(confirmed,'CONSTRUCTION',reference,'1900-01-01');result=[];running=0;last_running=0;open_current=True;open_prior=True
    at=lambda when:next((p['units'] for p in reversed(events) if p['date']<=when),None)
    # Same-day January records belong to this year, not the prior-year stock.
    before=at(f'{year-1}-12-31')
    for m in range(1,13):
        stamp=f'{year}{m:02}';prior=f'{year-1}{m:02}';current=[lookup.get((r,stamp)) for r in regions];previous=[lookup.get((r,prior)) for r in regions]
        value=sum(current) if all(known(v) for v in current) and stamp<=reference.strftime('%Y%m') else None
        old=sum(previous) if all(known(v) for v in previous) else None
        if value is None:open_current=False
        else:running+=value
        if old is None:open_prior=False
        else:last_running+=old
        cutoff=min(f'{year}-{m:02}-{monthrange(year,m)[1]:02}',reference.isoformat()) if year<=reference.year else reference.isoformat()
        point=at(cutoff) if stamp<=reference.strftime('%Y%m') else None
        policy=point-(before or 0) if point is not None else None
        accepted_at=lambda when:next((p['units'] for p in reversed(accepted) if p['date']<=when),None)
        accepted_point=accepted_at(cutoff) if stamp<=reference.strftime('%Y%m') else None
        policy_confirmed=accepted_point-(accepted_at(f'{year-1}-12-31') or 0) if accepted_point is not None else None
        result.append(dict(month=m,period=f'{year}-{m:02}',regional=value,prior_regional=old,cumulative=running if open_current else None,prior_cumulative=last_running if open_prior else None,
            policy_cumulative=policy,confirmed_policy_cumulative=policy_confirmed,yoy_pct=round((running/last_running-1)*100,1) if open_current and open_prior and last_running>0 else None))
    return result


def housing_series(rows,region,municipality,reference):
    selected=[r for r in rows if r.get('metric_group')=='kosis_housing' and r.get('region')==region and r.get('municipality')==municipality and r.get('year',9999)<=reference.year and (not r.get('source_date') or r['source_date']<=reference.isoformat())]
    return [dict(year=r['year'],housing_units=r.get('housing_units'),households=r.get('households'),population=r.get('population'),official_ratio=r.get('official_ratio'),
        calculated_ratio=round(100*r['housing_units']/r['households'],1) if known(r.get('housing_units')) and known(r.get('households')) and r['households']>0 else None,
        published_at=r.get('source_date'),source_url=r.get('evidence_url')) for r in sorted(selected,key=lambda r:r['year'])]


def assessed_delay(cohort,reference):
    greatest=0;status='NORMAL';stage=None
    for k in STAGES:
        goals=[p for p in _schedule_targets([cohort],k,'1900-01-01') if p['date']<=reference.isoformat()]
        actual=_events([cohort],k,reference,'1900-01-01',cumulative=True)
        if not goals or not actual or goals[-1]['units']<=0:continue
        gap=max(0,goals[-1]['units']-actual[-1]['units']);rate=gap/goals[-1]['units']*100
        current_rank={'NORMAL':0,'WARNING':1,'DELAYED':2}[status];rank=2 if rate>=2 else 1 if gap>0 else 0
        if rank>current_rank or rank==current_rank and gap>greatest:
            greatest=gap;stage=k;status='DELAYED' if rank==2 else 'WARNING' if rank==1 else 'NORMAL'
    return dict(status=status,gap_units=greatest,stage=stage)


def future_schedules(cohorts,reference):
    points=[];missing=0;overdue=0
    for c in cohorts:
        for stage in ('CONSTRUCTION','COMPLETION','MOVE_IN'):
            plans=[s for s in c.get('schedules',[]) if s.get('stage')==stage and s.get('due_date') and known(s.get('units'))]
            if any(p.get('managed_schedule') for p in plans):plans=[p for p in plans if p.get('managed_schedule')]
            if not plans:
                if stage=='MOVE_IN':missing+=1
                continue
            unique={}
            for p in plans:unique[p['due_date']]=max(unique.get(p['due_date'],0),p['units'])
            cap=c['units'];actual=_events([c],stage,reference,'1900-01-01');reached=actual[-1]['units'] if actual else None;prior=0
            for when,units in sorted(unique.items()):
                amount=min(max(0,cap-prior),units);prior+=amount
                if when<=reference.isoformat():
                    if stage=='MOVE_IN' and reached is not None:overdue+=max(0,min(prior,cap)-reached)-max(0,min(prior-amount,cap)-reached)
                    continue
                if amount>0:points.append(dict(stage=stage,date=when,year=int(when[:4]),units=amount,project_id=c['id'],name=c['name'],region=c['region'],municipality=c.get('municipality'),source_ids=c['source_ids'],status=assessed_delay(c,reference)['status']))
    return dict(points=points,missing_move_in_schedule_count=missing,overdue_move_in_units=overdue,schedule_scope='선택 원장에 확보된 향후 일정 · 지역 전체 전망과 구분')


def unsold_series(rows,regions,municipality,reference):
    chosen=[r for r in rows if r.get('region') in regions and r.get('municipality')==municipality and r.get('period','9999')<=reference.strftime('%Y-%m')]
    cells=defaultdict(dict)
    for r in chosen:cells[(r['period'],r['metric'])][r['region']]=r['units']
    result=[]
    for p in sorted({p for p,m in cells}):
        total,completed=cells[(p,'TOTAL')],cells[(p,'COMPLETED')]
        if set(total)!=set(regions) or set(completed)!=set(regions):continue
        a,b=sum(total.values()),sum(completed.values())
        if b>a:raise ValueError('준공 후 미분양 포함관계 오류')
        result.append(dict(period=p,total=a,completed=b,pre_completion=a-b,completed_share_pct=round(b/a*100,1) if a>0 else None))
    if result:
        latest=result[-1];prev=next((p for p in result if p['period']==month_before(latest['period'])),None)
        latest.update(total_change=latest['total']-prev['total'] if prev else None,completed_change=latest['completed']-prev['completed'] if prev else None)
    return result


def classification(cohorts,project_rows=()):
    sectors=defaultdict(int);types=defaultdict(int);source_index={p['id']:p for p in project_rows}
    for c in cohorts:
        members=[source_index[pid] for pid in c['source_ids'] if pid in source_index]
        developer=' '.join([c.get('developer') or '']+[p.get('developer') or '' for p in members]);names=[c['name']]+[p.get('name') or '' for p in members]
        sector='공공 시행기관' if re.search(r'한국토지주택|서울주택|경기주택|인천도시|\bLH\b|\bSH\b|\bGH\b|\biH\b',developer) else '민간 시행기관' if re.search(r'주식회사|㈜|\(주\)',developer) else '시행기관 미분류'
        apartment=any('아파트' in name for name in names);non_apartment=any(re.search(r'오피스텔|연립|다세대|단독주택',name) for name in names)
        kind='아파트' if apartment and not non_apartment else '비아파트' if non_apartment and not apartment else '주택유형 미분류'
        sectors[sector]+=c['units'];types[kind]+=c['units']
    return dict(sectors=[dict(label=k,units=v) for k,v in sectors.items()],housing_types=[dict(label=k,units=v) for k,v in types.items()],
        basis='공공/민간은 원천 시행기관 표기, 아파트/비아파트는 저장된 동일 사업 연결 ID의 원문 사업명에 명시된 유형만 분류. 연결 원천 간 유형 상충은 미분류. 공공주택 법적 분류 및 지역 전체 유형별 착공과 별도')


def build_indicators(model,statistics,areas,unsold,prices,kind,scope_id,reference,region=None,municipality_id=None,year=None,baseline_years=3,portfolio=False,project_rows=()):
    if model.get('status')!='READY':return dict(status='NOT_ACQUIRED',notice='단계 원장 미확보')
    all_cohorts=model.get('portfolio_cohorts',[]) if portfolio else model.get('cohorts',[])
    if kind=='program':
        profile=model.get('plan',{}).get('program_profiles',{}).get(scope_id)
        if not profile:raise ValueError('연결된 프로그램을 찾을 수 없습니다')
        cohorts=[c for c in all_cohorts if c.get('program_id')==scope_id];name=profile['name']
    elif kind=='project':
        cohorts=[c for c in model.get('portfolio_cohorts',[]) if scope_id in c.get('source_ids',[]) or scope_id==c['id']]
        if not cohorts:raise ValueError('연결된 사업을 찾을 수 없습니다')
        name=cohorts[0]['name'];profile=None
    else:
        if scope_id!=model.get('policy_id'):raise ValueError('정책 연결을 확인하세요')
        cohorts=all_cohorts;name=model['name'];profile=None
    shapes=model.get('geometry',{}).get('shapes',[]);municipality=None
    if municipality_id:
        shape=next((s for s in shapes if s['id']==municipality_id),None)
        if not shape or region and region!=shape['region']:raise ValueError('선택 시군구 연결 확인 필요')
        region=shape['region'];municipality=shape['name'];cohorts=[c for c in cohorts if c.get('municipality_id')==municipality_id]
    if region:cohorts=[c for c in cohorts if c['region']==region]
    regions=[region] if region else list(CAPITAL) if kind=='policy' else sorted({c['region'] for c in cohorts if c['region'] in CAPITAL}) or list(CAPITAL)
    year=year or reference.year;annual=annual_series(statistics,regions,reference)
    futures=future_schedules(cohorts,reference)
    places=[]
    location_list=[dict(id=r,name=r,region=r,municipality=None) for r in regions]+[dict(id=s['id'],name=s['name'],region=s['region'],municipality=s['name'],rings=s['rings'],longitude=s.get('longitude'),latitude=s.get('latitude')) for s in shapes if s['region'] in regions]
    for loc in location_list:
        cs=[c for c in cohorts if c['region']==loc['region'] and (not loc['municipality'] or c.get('municipality_id')==loc['id'])]
        history=housing_series(areas,loc['region'],loc['municipality'],reference);official=next((r for r in reversed(history) if r['official_ratio'] is not None),None)
        ps=price_series(prices,loc['region'],loc['municipality'],reference);latest=ps[-1] if ps else None
        delay=[assessed_delay(c,reference) for c in cs];known_plans=[c.get('planned_units') for c in cs if known(c.get('planned_units'))]
        places.append(dict(**loc,housing=history,official_housing=official,price=ps,target_units=sum(known_plans) if known_plans else None,project_count=len(cs),
            delayed_count=sum(d['status']=='DELAYED' for d in delay),warning_count=sum(d['status']=='WARNING' for d in delay),gap_units=sum(d['gap_units'] for d in delay),
            construction_planned=sum(p['units'] for p in futures['points'] if p['stage']=='CONSTRUCTION' and p['year']==year and p['project_id'] in {c['id'] for c in cs}),
            move_in_planned=sum(p['units'] for p in futures['points'] if p['stage']=='MOVE_IN' and p['year']==year and p['project_id'] in {c['id'] for c in cs})))
    starts=monthly_starts(statistics,regions,year,reference,cohorts)
    averages={}
    for metric in ('인허가','착공','준공'):
        expected=list(range(reference.year-baseline_years,reference.year));available=[r for r in annual if r['year'] in expected and r['metrics'][metric]['complete']]
        average=sum(r['metrics'][metric]['units'] for r in available)/baseline_years if len(available)==baseline_years else None
        averages[metric]=dict(value=average,start_year=expected[0],end_year=expected[-1],acquired_years=len(available),required_years=baseline_years)
    market_scope='수도권' if set(regions)==set(CAPITAL) else '서울특별시' if regions==['서울특별시'] else None
    target=None;target_metric='CONSTRUCTION';target_unit='호';goal_kind='정책 연간 착공 목표';total_goal=model.get('target_units') if kind=='policy' else profile['values'].get('target_units') if kind=='program' else cohorts[0].get('planned_units')
    if kind=='policy':
        if not municipality_id:
            p=next((p for p in model['plan'].get('annual',[]) if p['year']==year),None)
            target=p.get('seoul_units') if p and regions==['서울특별시'] else p.get('units') if p and set(regions)==set(CAPITAL) else None
    elif kind=='program':
        values=profile['values'];target_metric=values.get('metric');target_unit=values.get('unit');goal_kind='프로그램 연간 목표'
        target=values.get(f'annual:{region or "전체"}:{year}')
    else:
        goal_kind='사업 착공 예정';plans=[p for p in futures['points'] if p['stage']=='CONSTRUCTION' and p['year']==year]
        target=sum(p['units'] for p in plans) if plans else None
    scale_base=averages.get('착공',{}).get('value');comparable=kind=='policy' and not municipality_id and target_metric=='CONSTRUCTION' and target_unit=='호'
    forecasts=[]
    for y in range(reference.year,reference.year+11):
        items=[next((r for r in areas if r.get('metric_group')=='kosis_household_forecast' and r.get('region')==reg and r.get('year')==y and not r.get('municipality')),None) for reg in regions]
        if all(items):forecasts.append(dict(year=y,households=sum(r['forecast_households'] for r in items),published_at=max(r.get('source_date','') for r in items)))
    unsold_rows=unsold_series(unsold,regions,municipality,reference);fallback=False
    if municipality and not unsold_rows:unsold_rows=unsold_series(unsold,regions,None,reference);fallback=True
    return dict(status='READY',as_of_date=reference.isoformat(),scope=dict(kind=kind,id=scope_id,name=name,regions=regions,municipality_id=municipality_id,municipality=municipality,year=year,portfolio=portfolio,project_count=len(cohorts)),
        places=places,annual=annual,averages=averages,monthly_starts=starts,goal=dict(value=target,metric=target_metric,unit=target_unit,label=goal_kind,total_value=total_goal,total_scope={'policy':'정책 전체','program':'프로그램 전체','project':'사업 전체'}[kind],scope_comparable=comparable),
        goal_scale=dict(baseline=scale_base if comparable else None,increment=target-scale_base if comparable and target is not None and scale_base is not None else None,multiplier=target/scale_base if comparable and target is not None and scale_base and scale_base>0 else None),
        classification=classification(cohorts,project_rows),future=futures,unsold=dict(history=unsold_rows,fallback=fallback),household_forecast=forecasts,
        reference=dict(**REFERENCE,selected_market_scope=market_scope),sources=dict(price='https://www.reb.or.kr/r-one/portal/stat/easyStatPage/A_2024_00045.do',housing='https://kosis.kr/statHtml/statHtml.do?orgId=116&tblId=DT_MLTM_2100',supply=SUPPLY_SOURCES,unsold='https://stat.molit.go.kr/portal/cate/statMetaView.do?hRsId=32'),
        regional_comparison_scope='지역 전체 통계 · 정책 인정 실적과 별도',coverage=dict(price_places=sum(bool(p['price']) for p in places),housing_places=sum(bool(p['housing']) for p in places),cohorts=len(cohorts)))


def housing_indicators(service,model,**params):
    ref=params['reference']
    return build_indicators(model,service.rows('statistic',ref),service.rows('area_stat',ref),service.rows('unsold',ref),service.rows('market_price',ref),project_rows=service.rows('project',ref),**params)
