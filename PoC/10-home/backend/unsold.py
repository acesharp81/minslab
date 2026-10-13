"""Official municipal unsold inventory; completed inventory is a subset, not extra."""
from collections import defaultdict
from datetime import date
from .api_samples import key_for, response_json, today
from .collectors import integer
from .additional_apis import STAT_URL, STAT_PERIOD_URL

REGIONS={'서울':'서울특별시','경기':'경기도','인천':'인천광역시'}
SERIES=(('2082','128','TOTAL','미분양현황'),('5328','1','COMPLETED','호'))


def parse(data, source, form, style, metric, field, period):
    if data.get('result_status',{}).get('status_code')!='INFO-000':raise ValueError('미분양 통계 원천 응답 오류')
    body=data.get('result_data',{});rows=body.get('formList')
    if body.get('unitName')!='호' or not isinstance(rows,list) or not rows or len(rows)>10000:raise ValueError('미분양 통계 단위·행 구조 확인 필요')
    items=[];seen=set();totals={};details=defaultdict(int)
    for row in rows:
        region=REGIONS.get(row.get('구분'))
        if not region:continue
        if metric=='COMPLETED' and (row.get('부문')!='계' or row.get('규모')!='계'):continue
        if str(row.get('date'))!=period:raise ValueError('미분양 통계 기준월 불일치')
        area=str(row.get('시군구') or '').strip();units=integer(row.get(field))
        if not area or units is None:raise ValueError('미분양 통계 지역·호수 미확인')
        municipality=None if area in ('계','합계') else area
        key=(region,municipality)
        if key in seen:raise ValueError('미분양 통계 동일 지역 중복')
        seen.add(key)
        if municipality:details[region]+=units
        else:totals[region]=units
        identity=f'{period}:{region}:{municipality or "ALL"}:{metric}'
        items.append(('unsold',identity,dict(source_object_id=identity,source_id=source['id'],name=f'{region} {municipality or "전체"} {period} '+('준공 후 미분양' if metric=='COMPLETED' else '전체 미분양'),
            region=region,municipality=municipality,period=period[:4]+'-'+period[4:],metric=metric,units=units,
            source_date=period[:4]+'-'+period[4:],source_date_label='통계 기준월 · 공표일과 구분',base_date=today().isoformat(),
            form_id=form,style_num=style,evidence_url=f'https://stat.molit.go.kr/portal/cate/viewChk.do?hFormId={form}&hRsId=32',
            policy_mapping_status='REGIONAL_REFERENCE',unit_basis='월말 미분양 재고 · 정책 신규 공급 실적 아님',
            completion_subset=metric=='COMPLETED')))
    if set(totals)!=set(REGIONS.values()):raise ValueError('미분양 통계 수도권 지역 총계 누락')
    if any(details[r]!=n for r,n in totals.items()):raise ValueError('미분양 통계 시군구 합계와 시도 총계 불일치')
    return items


def collect(source,fetcher,service):
    metadata=response_json(fetcher.get(STAT_PERIOD_URL,'json',params={'form_id':'2082','style_num':'128'}))
    periods=sorted(str(p.get('MNG_DIV_VL')) for p in metadata.get('periodList',[]) if len(str(p.get('MNG_DIV_VL','')))==6 and str(p.get('MNG_DIV_VL')).isdigit() and str(p.get('MNG_DIV_VL'))<=today().strftime('%Y%m'))
    if not periods:raise ValueError('미분양 통계 공개 기준월 미확인')
    latest=periods[-1];ordinal=int(latest[:4])*12+int(latest[4:])-1
    window=[f'{(ordinal-i)//12:04}{(ordinal-i)%12+1:02}' for i in range(12,-1,-1)]
    existing=service.rows('unsold');complete_months={r['period'].replace('-','') for r in existing}
    selected=window if any(p not in complete_months for p in window) else window[-3:]
    records=[]
    for period in selected:
        pair=[]
        for form,style,metric,field in SERIES:
            data=response_json(fetcher.get(STAT_URL,'json',params={'key':key_for(source),'form_id':form,'style_num':style,'start_dt':period,'end_dt':period}))
            pair+=parse(data,source,form,style,metric,field,period)
        quantities=defaultdict(dict)
        for _,_,r in pair:quantities[(r['region'],r['municipality'])][r['metric']]=r['units']
        if any(set(v)!= {'TOTAL','COMPLETED'} or v['COMPLETED']>v['TOTAL'] for v in quantities.values()):raise ValueError('미분양 전체/준공 후 범위 또는 수량 충돌')
        records+=pair
    return records,dict(latest_period=periods[-1],periods=selected,regions=list(REGIONS.values()),record_count=len(records),
        collection_mode='OFFICIAL_REGIONAL_REFERENCE',complete_population=False,
        scope_note='서울·경기·인천 시도 및 원천 시군구 월말 재고. 최신 13개월 최초 확보 후 최근 3개월 갱신. 시도 총계·시군구 합계·준공 후 포함관계 검증. 고유 사업 실적이 아님.')


def context(service,region,municipality=None,as_of=None):
    reference=as_of or today();cutoff=reference.strftime('%Y-%m')
    allrows=[r for r in service.rows('unsold') if r.get('region')==region and r.get('period','9999')<=cutoff]
    rows=[r for r in allrows if r.get('municipality')==municipality]
    fallback=bool(municipality and not rows)
    if fallback:rows=[r for r in allrows if r.get('municipality') is None]
    periods=defaultdict(dict)
    for row in rows:periods[row['period']][row['metric']]=row
    history=[]
    for month,metrics in sorted(periods.items()):
        if not all(k in metrics for k in ('TOTAL','COMPLETED')):continue
        total,finished=metrics['TOTAL']['units'],metrics['COMPLETED']['units']
        history.append(dict(period=month,total=total,completed=finished,pre_completion=total-finished,
            completed_share_pct=round(finished/total*100,1) if total else None,evidence_url=metrics['TOTAL']['evidence_url'],completed_evidence_url=metrics['COMPLETED']['evidence_url'],collected_at=max(r['recorded_at'] for r in metrics.values())))
    current=history[-1].copy() if history else None
    if current:
        ordinal=int(current['period'][:4])*12+int(current['period'][5:])-1
        def earlier(months):
            y,m=divmod(ordinal-months,12);stamp=f'{y:04}-{m+1:02}'
            return next((r for r in history if r['period']==stamp),None)
        for offset,prefix in ((1,'mom'),(3,'three_month'),(12,'yoy')):
            old=earlier(offset)
            for metric in ('total','completed'):
                delta=current[metric]-old[metric] if old else None
                current[prefix+'_'+metric+'_change']=delta
                current[prefix+'_'+metric+'_pct']=round(delta/old[metric]*100,1) if old and old[metric] else None
        before=[earlier(i) for i in range(1,4)]
        rising=all(before) and current['completed']>before[0]['completed']>before[1]['completed']>before[2]['completed']
        current['signal']='준공 후 미분양 3개월 연속 증가 · 추세 점검' if rising else '월별 규모·비중과 변화 함께 확인'
    return dict(region=region,municipality=None if fallback else municipality,requested_municipality=municipality,
        level='REGION' if fallback or not municipality else 'MUNICIPALITY',fallback=fallback,current=current,history=history,
        definition='준공 후 미분양(통상 악성 미분양)은 사용검사 후에도 분양되지 않은 주택이며 전체 미분양에 포함됩니다. 분양 후 미입주·빈집·임대 공가와 다릅니다.',
        method='사업 입지의 시군구 시장 참고 지표입니다. 정확한 지역이 없으면 시도 참고로 명시합니다. 미분양·준공 후 규모, 준공 후 비중, 전월·3개월·전년 동월 증감으로 점검하며 가격·수요·향후 공급·입지와 함께 판단합니다.')
