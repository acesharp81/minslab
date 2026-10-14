"""Published household income, migration and housing context; never project estimates."""
import json
from collections import defaultdict
from datetime import date
from sqlalchemy import select
from .area_stats import KOSIS, kosis_key, number, GYEONGGI
from .db import Revision

META='https://kosis.kr/openapi/statisticsData.do'
REGIONS={'서울':'서울특별시','서울특별시':'서울특별시','경기':'경기도','경기도':'경기도','인천':'인천광역시','인천광역시':'인천광역시','전국':'전국'}

def value(row):
    n=number(row.get('DT'))
    return float(n) if n is not None else None

def geography(code,name,scheme='census'):
    prefixes={'11':'서울특별시','28':'인천광역시','41':'경기도'} if scheme=='migration' else {'11':'서울특별시','23':'인천광역시','31':'경기도'}
    region=prefixes.get(code[:2])
    if not region:return None
    if len(code)==2:return region,None
    name=name.removeprefix(region+' ').strip()
    if region=='경기도':return (region,name) if name in GYEONGGI else None
    return (region,name) if len(code)==5 and ' ' not in name and name.endswith(('구','군')) else None

def fetch_table(fetcher,table,org='101',period='Y',count=1,**dims):
    key=kosis_key()
    meta=json.loads(fetcher.get(META,'json',params=dict(method='getMeta',type='PRD',apiKey=key,orgId=org,tblId=table,format='json',jsonVD='Y')))
    label={'Y':'년','M':'월','F':'5년'}[period]
    found=next((r for r in meta if r.get('PRD_SE')==label),None) if isinstance(meta,list) else None
    if not found:raise ValueError(table+' 수록시점 확인 필요')
    end=found['END_PRD_DE'].replace('.','').replace('-','');start=end
    if period=='M':
        month=int(end[:4])*12+int(end[4:])-count
        start=f'{month//12:04}{month%12+1:02}'
    params=dict(method='getList',apiKey=key,orgId=org,tblId=table,format='json',jsonVD='Y',itmId='ALL',objL1='ALL',prdSe=period,startPrdDe=start,endPrdDe=end,**{})
    params.update(dims)
    rows=json.loads(fetcher.get(KOSIS,'json',params=params))
    if not isinstance(rows,list) or not rows:raise ValueError(table+' 통계 원천 조회 실패')
    return rows

def payload(group,region,municipality,period,table,org='101',**values):
    return dict(name=municipality or region,region=region,municipality=municipality,metric_group=group,period=period,year=int(period[:4]),
                base_date=(period[:4]+'-'+period[4:]+'-01') if len(period)==6 else period+'-12-31',date_precision='MONTH' if len(period)==6 else 'YEAR',
                source_table=table,evidence_url=f'https://kosis.kr/statHtml/statHtml.do?orgId={org}&tblId={table}',**values)

def parse_income(distribution,means):
    period=max(r['PRD_DE'] for r in distribution)
    bins=[dict(label=r['C2_NM'],code=r['C2'],pct=value(r)) for r in distribution if r['C1']=='000' and r['C2']!='00' and r['PRD_DE']==period]
    values={r['ITM_ID']:value(r) for r in means if r['C1']=='000' and r['C2']=='00' and r['PRD_DE']==period}
    if len(bins)!=6 or any(b['pct'] is None for b in bins) or abs(sum(b['pct'] for b in bins)-100)>.2:raise ValueError('전국 소득 분포 합계 확인 필요')
    if not all(values.get(k) is not None and values[k]>0 for k in ('T00','T10')):raise ValueError('소득 평균·중앙값 동일 판본 확인 필요')
    return payload('income','전국',None,period,'DT_1HDAAB03',income_year=int(period)-1,bins=sorted(bins,key=lambda b:b['code']),mean_annual=values['T00'],median_annual=values['T10'],unit='만원/년',mean_source_url='https://kosis.kr/statHtml/statHtml.do?orgId=101&tblId=DT_1HDAAB01',scope_note='전국 일반가구 참고 · 시군구 소득 분포 아님')

def parse_migration(rows):
    groups=defaultdict(dict);names={}
    for r in rows:
        place=geography(r['C1'],r['C1_NM'],'migration')
        if place:
            key=(*place,r['PRD_DE']);groups[key][r['ITM_ID']]=value(r);names[key]=r['C1']
    result=[]
    for (region,municipality,period),v in groups.items():
        needed=('T10','T20','T25','T30') if municipality else ('T40','T50','T25')
        if any(v.get(k) is None for k in needed):continue
        incoming=v['T10']-v['T30'] if municipality else v['T40'];outgoing=v['T20']-v['T30'] if municipality else v['T50']
        if min(incoming,outgoing)<0 or incoming-outgoing!=v['T25']:raise ValueError('지역 경계 간 순이동 검증 실패')
        result.append(payload('migration',region,municipality,period,'DT_1B26001_A01',incoming=int(incoming),outgoing=int(outgoing),net=int(v['T25']),source_admin_code=names[(region,municipality,period)],scope_note='시군구 내 이동 제외' if municipality else '시도 내 이동 제외'))
    return result

def parse_duration(rows):
    groups=defaultdict(list)
    for r in rows:
        region=REGIONS.get(r['C1_NM'])
        if region and not r['ITM_ID'].endswith('T1'):groups[(region,r['PRD_DE'])].append(dict(label=r['ITM_NM'],pct=value(r),order=int(r['ITM_ID'].split('T')[-1])))
    result=[]
    for (region,period),bins in groups.items():
        if len(bins)!=9 or any(b['pct'] is None for b in bins) or abs(sum(b['pct'] for b in bins)-100)>.2:raise ValueError('거주기간 분포 합계 확인 필요')
        result.append(payload('duration',region,None,period,'DT_MLTM_6035','116',bins=sorted(bins,key=lambda b:b['order']),scope_note='주거실태조사 · 현재 주택 거주기간 · 시도 참고'))
    return result

def parse_housing(rows,group):
    cells=defaultdict(dict);periods={}
    for r in rows:
        place=geography(r['C1'],r['C1_NM'])
        if not place:continue
        key=(*place,r['PRD_DE']);periods[key]=r['C1']
        if group=='tenure' and r['C2']=='00':cells[key][r['ITM_ID']]=value(r)
        elif group=='housing_type' and r['ITM_ID']=='T210':cells[key][r['C2']]=value(r)
    result=[]
    for (region,municipality,period),v in cells.items():
        if group=='tenure':
            specs=[('자가',['T11']),('전세',['T12']),('월세',['T13','T14']),('사글세·무상',['T15','T16'])];total=v.get('T10');table='DT_1PE2002'
        else:
            specs=[('아파트',['102']),('단독주택',['101']),('오피스텔',['201']),('다세대·연립',['103','104']),('기타',['105','202','203','204','205'])];total=v.get('00');table='DT_1JU1502'
        bins=[dict(label=label,value=sum(v[k] for k in keys) if all(v.get(k) is not None for k in keys) else None) for label,keys in specs]
        # Exhaustive, disjoint groups permit a residual aggregate without revealing suppressed component cells.
        if group=='housing_type' and total is not None and all(b['value'] is not None for b in bins[:-1]):
            residual=total-sum(b['value'] for b in bins[:-1])
            if residual<0:raise ValueError('주거 유형 잔여 합계 확인 필요')
            if bins[-1]['value'] is None:bins[-1]['value']=residual;bins[-1]['basis']='전체 일반가구 - 앞선 네 가지 거처 유형 합계'
        # Other suppressed cells stay unknown; do not substitute zero or redistribute them.
        if total and all(b['value'] is not None for b in bins) and abs(sum(b['value'] for b in bins)-total)>1:raise ValueError('주거 구성 합계 확인 필요')
        for b in bins:b['pct']=100*b['value']/total if total and b['value'] is not None else None
        result.append(payload(group,region,municipality,period,table,total=total,bins=bins,source_admin_code=periods[(region,municipality,period)],unit='가구',scope_note='일반가구 점유형태' if group=='tenure' else '일반가구가 거주하는 주택·거처 유형 · 빈집 제외'))
    return result

PIR_URL='https://www.index.go.kr/unity/potal/eNara/sub/showStblGams3.do?freq=Y&idx_cd=F0188&period=N&stts_cd=F018801'

def parse_pir(html):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    table=soup.select_one('#t_Table_F018801')
    if table is None:raise ValueError('공식 PIR 통계표 확인 필요')
    years=[th.get_text(strip=True) for th in table.select('thead th[item-id]')]
    if not years or any(len(y)!=4 or not y.isdigit() for y in years):raise ValueError('PIR 기준연도 확인 필요')
    series={}
    for row in table.select('tbody tr'):
        labels=[th.get_text(' ',strip=True) for th in row.select('th')]
        scope=next((label for label in labels if label in ('전체','수도권')),None)
        if not scope:continue
        values=[number(td.get_text(strip=True)) for td in row.select('td')]
        if len(values)!=len(years):raise ValueError('PIR 시점·수치 열 불일치')
        series[scope]=values
    if set(series)!= {'전체','수도권'}:raise ValueError('PIR 전국·수도권 구분 확인 필요')
    records=[]
    for i,year in enumerate(years):
        if any(series[k][i] is None or series[k][i]<=0 for k in series):continue
        r=payload('pir','전국',None,year,'F018801',national=float(series['전체'][i]),capital=float(series['수도권'][i]),unit='배',scope_note='자가가구 · 주거실태조사 중위값 기준 · 수도권은 서울·인천·경기')
        r['evidence_url']=PIR_URL;records.append(r)
    if not records:raise ValueError('PIR 수치 미확보')
    return records

def collect(source,fetcher,service):
    records=[parse_income(fetch_table(fetcher,'DT_1HDAAB03',objL1='000',objL2='ALL'),fetch_table(fetcher,'DT_1HDAAB01',objL1='000',objL2='00'))]
    records+=parse_pir(fetcher.get(PIR_URL,'html'))
    records+=parse_duration(fetch_table(fetcher,'DT_MLTM_6035',org='116'))
    records+=parse_migration(fetch_table(fetcher,'DT_1B26001_A01',period='M',count=12,itmId='T10+T20+T25+T30+T40+T50'))
    records+=parse_housing(fetch_table(fetcher,'DT_1PE2002',period='F',objL2='00'),'tenure')
    records+=parse_housing(fetch_table(fetcher,'DT_1JU1502',itmId='T210',objL2='ALL'),'housing_type')
    return [('living_stat','|'.join((r['metric_group'],r['region'],r['municipality'] or '',r['period'])),r) for r in records],dict(records=len(records),groups=sorted({r['metric_group'] for r in records}),complete_query=True)

def context(service,region,municipality,year):
    with service.sessions() as session:
        rows=session.scalars(select(Revision.payload).where(Revision.kind=='living_stat',Revision.superseded_at.is_(None),Revision.sample_region.in_([region,'전국']))).all()
    rows=[r for r in rows if r['year']<=year]
    result={}
    for group in ('income','duration','tenure','housing_type','migration','pir'):
        options=[r for r in rows if r['metric_group']==group]
        exact=[r for r in options if r['region']==region and r.get('municipality')==municipality]
        regional=[r for r in options if r['region']==region and not r.get('municipality')]
        national=[r for r in options if r['region']=='전국']
        chosen=exact or regional or national
        if not chosen:result[group]=None;continue
        ordered=sorted(chosen,key=lambda r:r['period']);latest=dict(ordered[-1]);latest['fallback']=not bool(exact);latest['scope_label']=latest.get('municipality') or latest['region']
        if group=='migration':latest['history']=[{k:r[k] for k in ('period','incoming','outgoing','net')} for r in ordered[-12:]]
        result[group]=latest
    return result
