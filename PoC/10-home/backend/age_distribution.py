"""Registered-resident age shares, with the source geography and denominator kept."""
from collections import defaultdict
from .api_samples import today
from .area_stats import kosis_rows,kosis_key,count,GYEONGGI

TABLE='DT_1B04005N'
URL='https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId='+TABLE
REGIONS={'11':'서울특별시','28':'인천광역시','41':'경기도'}
BANDS={'0-14':'0~14세','15-34':'15~34세','35-64':'35~64세','65+':'65세 이상'}


def place(row):
    code=str(row.get('C1',''));region=REGIONS.get(code[:2]);name=str(row.get('C1_NM',''))
    if not region:return None
    if len(code)==2:return region,None
    if len(code)!=5:return None
    if region=='경기도' and name not in GYEONGGI:return None
    if region!='경기도' and not name.endswith(('구','군')):return None
    return region,name


def parse(rows,period):
    groups=defaultdict(dict);names={}
    for row in rows:
        target=place(row)
        if not target or row.get('ITM_ID')!='T2':continue
        if row.get('PRD_DE')!=period or row.get('UNIT_NM')!='명':raise ValueError('연령 통계 기준월·단위 불일치')
        age=str(row.get('C2',''));value=count(row.get('DT'))
        if age not in {'0',*[str(i) for i in range(5,106,5)]} or value is None:raise ValueError('연령 분류·값 확인 필요')
        if age in groups[target]:raise ValueError('연령 지역·분류 중복')
        groups[target][age]=value;names[target]=str(row['C1'])
    result={}
    for target,values in groups.items():
        if set(values)!={'0',*[str(i) for i in range(5,106,5)]}:raise ValueError('연령 분류 누락')
        if sum(v for k,v in values.items() if k!='0')!=values['0']:raise ValueError('연령 합계와 총인구 불일치')
        bands={key:0 for key in BANDS}
        for age,value in values.items():
            if age=='0':continue
            lower=int(age)-5;band='0-14' if lower<15 else '15-34' if lower<35 else '35-64' if lower<65 else '65+'
            bands[band]+=value
        result[target]=dict(total=values['0'],bands=bands,region_code=names[target],age_classes=values)
    for region,expected in [('서울특별시',25),('경기도',31),('인천광역시',None)]:
        district=[v for (r,m),v in result.items() if r==region and m]
        if (region,None) not in result or expected is not None and len(district)!=expected or region=='인천광역시' and len(district) not in (10,11):raise ValueError('연령 통계 수도권 시군구 범위 누락')
        if sum(v['total'] for v in district)!=result[(region,None)]['total']:raise ValueError('연령 지역 총계·시군구 합계 불일치')
    return result


def parse_sexes(rows,period):
    total=parse(rows,period)
    sexes={key:parse([dict(r,ITM_ID='T2') for r in rows if r.get('ITM_ID')==item],period)
           for key,item in [('male','T3'),('female','T4')]}
    for target,v in total.items():
        for age,count_ in v['age_classes'].items():
            if sum(sexes[key][target]['age_classes'][age] for key in sexes)!=count_:
                raise ValueError('남녀 연령 합계와 총인구 불일치')
        v['sex_age_classes']={key:sexes[key][target]['age_classes'] for key in sexes}
    return total


def collect(source,fetcher):
    key=kosis_key();now=today();ordinal=now.year*12+now.month-2
    period=None;metadata=None
    for offset in range(3):
        y,m=divmod(ordinal-offset,12);candidate=f'{y:04}{m+1:02}'
        rows=kosis_rows(fetcher,key,TABLE,'M','T2',candidate,candidate,allow_missing=True,objL2='0')
        if rows:period=candidate;metadata=rows;break
    if not period:raise ValueError('연령 통계 최신 공개월 미확인')
    codes=sorted({str(r['C1']) for r in metadata if place(r)})
    rows=kosis_rows(fetcher,key,TABLE,'M','T2+T3+T4',period,period,objL1='+'.join(codes),objL2='ALL')
    places=parse_sexes(rows,period);records=[]
    for (region,municipality),v in sorted(places.items(),key=lambda t:(t[0][0],t[0][1] or '')):
        payload=dict(name=municipality or region,region=region,municipality=municipality,metric_group='kosis_age',
                     year=int(period[:4]),period=period[:4]+'-'+period[4:],base_date=today().isoformat(),
                     source_date=max((r.get('LST_CHN_DE','') for r in rows),default=''),
                     table_id=TABLE,evidence_url=URL,population_total=v['total'],age_bands=v['bands'],age_labels=BANDS,
                     age_classes=v['age_classes'],sex_age_classes=v['sex_age_classes'],region_code=v['region_code'],
                     definition='주민등록인구 총인구(T2)의 연령 분포. 일반가구·인구총조사 인구와 분모가 다르며 외국인 포함 여부 등 원천 정의 유지')
        records.append(('area_stat',f'{region}|{municipality or "ALL"}|{period}',payload))
    return records,dict(period=period,covered_places=len(places),table_id=TABLE,complete_query=True,
                        scope_note='서울·경기·인천 시도/시군구 원천 명부, 21개 5세 연령 구간과 총계 검증. 과거 경계를 현재 경계에 재배분하지 않음')


def context(service,region,municipality,year):
    rows=[r for r in service.rows('area_stat') if r.get('metric_group')=='kosis_age' and r.get('region')==region and r.get('year',9999)<=year]
    selected=[r for r in rows if r.get('municipality')==municipality]
    fallback=bool(municipality and not selected)
    if fallback:selected=[r for r in rows if r.get('municipality') is None]
    latest=max(selected,key=lambda r:r.get('period',''),default=None)
    if not latest:return dict(current=None,fallback=False,requested_municipality=municipality)
    total=latest['population_total']
    return dict(current=dict(period=latest['period'],total=total,bands=[dict(id=k,label=BANDS[k],count=latest['age_bands'][k],percent=round(latest['age_bands'][k]/total*100,1) if total else None) for k in BANDS],
                             sex_age_classes=latest.get('sex_age_classes'),age_classes=latest.get('age_classes'),source_date=latest.get('source_date'),evidence_url=latest['evidence_url'],definition=latest['definition']),
                fallback=fallback,requested_municipality=municipality,municipality=None if fallback else municipality)
