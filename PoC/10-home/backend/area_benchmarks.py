"""National shares matched to the displayed local period and source classification."""
from collections import defaultdict
from .api_samples import today
from .area_stats import kosis_rows,kosis_key,count,HOUSEHOLD_SIZE_ITEMS,sgis_token,sgis_data,SGIS_DOC

AGE_TABLE='DT_1B04005N'
HOUSE_TABLE='DT_1JC1516'
def kosis_url(table):return 'https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId='+table

def national_age(rows,period):
    sexes=defaultdict(dict);items={'T2':'total','T3':'male','T4':'female'}
    expected={'0',*[str(i) for i in range(5,106,5)]}
    for r in rows:
        if r.get('C1')!='00' or r.get('C1_NM')!='전국' or r.get('ITM_ID') not in items:raise ValueError('전국 연령 지역·항목 확인 필요')
        if r.get('PRD_DE')!=period or r.get('UNIT_NM')!='명':raise ValueError('전국 연령 기준월·단위 불일치')
        key=items[r['ITM_ID']];age=r.get('C2');value=count(r.get('DT'))
        if age not in expected or value is None or age in sexes[key]:raise ValueError('전국 연령 분류 누락·중복·값 오류')
        sexes[key][age]=value
    if set(sexes)!=set(items.values()) or any(set(v)!=expected for v in sexes.values()):raise ValueError('전국 연령 분류 누락')
    if any(sum(v[k] for k in expected-{'0'})!=v['0'] for v in sexes.values()):raise ValueError('전국 연령 합계 불일치')
    if any(sexes['male'][k]+sexes['female'][k]!=sexes['total'][k] for k in expected):raise ValueError('전국 남녀 합계 불일치')
    return dict(period=period[:4]+'-'+period[4:],total=sexes['total']['0'],sex_age_classes={k:sexes[k] for k in ('male','female')},evidence_url=kosis_url(AGE_TABLE),table_id=AGE_TABLE)

def national_household(rows,year):
    values={}
    for r in rows:
        if r.get('C1')!='00' or r.get('C1_NM')!='전국' or r.get('C2')!='00' or str(r.get('PRD_DE'))!=str(year):raise ValueError('전국 가구 지역·연도·분류 불일치')
        key=HOUSEHOLD_SIZE_ITEMS.get(r.get('ITM_ID'));value=count(r.get('DT'))
        if not key or value is None or key in values:raise ValueError('전국 가구 항목 누락·중복·값 오류')
        values[key]=value
    if set(values)!=set(HOUSEHOLD_SIZE_ITEMS.values()):raise ValueError('전국 가구 분류 누락')
    if sum(v for k,v in values.items() if k!='total')!=values['total']:raise ValueError('전국 가구 합계 불일치')
    return dict(year=year,total=values['total'],sizes={**{k:values[k] for k in ('1','2','3','4')},'5+':sum(values[k] for k in ('5','6','7+'))},evidence_url=kosis_url(HOUSE_TABLE),table_id=HOUSE_TABLE)

def national_workers(rows):
    """SGIS supplies 17 province totals and a repeated nationwide total; cross-check both."""
    if not rows:return None
    codes=[str(r.get('adm_cd','')) for r in rows]
    if len(set(codes))!=17 or len(rows)!=17 or any(len(c)!=2 for c in codes):raise ValueError('전국 산업 17개 시도 범위·중복 확인 필요')
    values=[count(r.get('tot_worker')) for r in rows];totals={count(r.get('all_worker_cnt')) for r in rows}
    if None in values or None in totals or len(totals)!=1 or sum(values)!=next(iter(totals)):raise ValueError('전국 산업 시도 합계·전국 총계 불일치')
    return sum(values)

def collect(source,fetcher,service):
    local=service.rows('area_stat');records=[]
    # Fetch only the periods actually used by current regional charts, never substitute another vintage.
    def latest(group,field):
        places=defaultdict(list)
        for r in local:
            if r.get('metric_group')==group and r.get('region')!='전국':places[(r['region'],r.get('municipality'))].append(r[field])
        return sorted({max(values) for values in places.values()})
    periods=latest('kosis_age','period');houseyears=latest('kosis_household_size','year');workyears=latest('sgis_census','year')
    key=kosis_key()
    def add(group,period,value):
        records.append(('area_benchmark',group+':'+str(period),dict(value,metric_group=group,region='전국',name='전국 '+group,base_date=today().isoformat(),definition='전국 해당 항목 수 / 전국 전체 수. 시군구 비율의 단순 평균이 아님')))
    for period in periods:
        raw=period.replace('-','');rows=kosis_rows(fetcher,key,AGE_TABLE,'M','T2+T3+T4',raw,raw,objL1='00',objL2='ALL')
        add('age',period,national_age(rows,raw))
    for year in houseyears:
        rows=kosis_rows(fetcher,key,HOUSE_TABLE,'A','+'.join(HOUSEHOLD_SIZE_ITEMS),str(year),str(year),objL1='00',objL2='00')
        add('household',year,national_household(rows,year))
    if workyears:
        token=sgis_token(fetcher);classes=sgis_data(fetcher,'stats/industrycode.json',token,class_deg=11)
        if not classes or len({r['class_code'] for r in classes})!=len(classes):raise ValueError('전국 산업분류 확인 필요')
        for year in workyears:
            total=national_workers(sgis_data(fetcher,'stats/company.json',token,year=year,low_search=0))
            if total is None:raise ValueError('전국 종사자 총계 미확보')
            industries={}
            for c in classes:
                value=national_workers(sgis_data(fetcher,'stats/company.json',token,year=year,low_search=0,class_code=c['class_code']))
                industries[c['class_code']]=dict(name=c['class_nm'],workers=value)
            if sum(r['workers'] or 0 for r in industries.values())>total:raise ValueError('전국 산업 합계 총계 초과')
            add('industry',year,dict(year=year,total=total,industry_workers=industries,class_deg=11,evidence_url=SGIS_DOC,covered_provinces=17))
    if not records:raise ValueError('비교할 지역 통계의 기준시점 미확보')
    return records,dict(age_periods=periods,household_years=houseyears,industry_years=workyears,complete_query=True)

def context(service,age,households,census):
    bykey={(r['metric_group'],str(r.get('period') or r.get('year'))):r for r in service.rows('area_benchmark')}
    periods=dict(age=(age.get('current') or {}).get('period'),household=(households[-1] if households else {}).get('year'),industry=(census[-1] if census else {}).get('year'))
    return {k:bykey.get((k,str(v))) for k,v in periods.items()}
