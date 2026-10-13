"""9·7 original target matrix and Incheon sources, isolated from existing map."""
import io
import re
from collections import defaultdict

from pypdf import PdfReader
from .api_samples import response_json, key_for, today
from .map_data import DATA_URL
from .additional_apis import collect_statistics
from .collectors import collect_lh_plan, collect_construction, ALLOWED_HOSTS

ALLOWED_HOSTS.add('eiec.kdi.re.kr')

PDF_URL = 'https://eiec.kdi.re.kr/policy/callDownload.do?filenum=2&num=270716'
ANNUAL = [269000, 246000, 250000, 249000, 335000]
SEOUL = [68000, 63000, 61000, 59000, 83000]
PROGRAMS = [
    ('PUBLIC_LAND', '공공택지 공급 확대·조기화', [52000,60000,60000,68000,132000]),
    ('PUBLIC_REUSE', '노후시설·유휴부지 재정비', [3000,4000,4000,12000,15000]),
    ('URBAN', '도심지 주택공급', [79000,59000,67000,70000,90000]),
    ('PRIVATE', '민간 공급여건 개선', [64000,52000,48000,28000,27000]),
    ('OTHER', '기타 주택사업', [71000,71000,71000,71000,71000]),
]

def parse_original_plan(content):
    reader=PdfReader(io.BytesIO(content))
    pages=[page.extract_text(extraction_mode='layout') or '' for page in reader.pages]
    found=next(((i,text) for i,text in enumerate(pages) if '134.9' in text and '26.9' in text and '33.5' in text),None)
    if not found: raise ValueError('9·7 원문 연도별 목표표 변경·미확보')
    index,text=found
    compact=re.sub(r'\s+',' ',text)
    if not re.search(r'134\.9\s+26\.9\s+24\.6\s+25\.0\s+24\.9\s+33\.5',compact):
        raise ValueError('9·7 연도별 착공 목표 원문 검증 실패')
    for numbers in ('33.4 6.8 6.3 6.1 5.9 8.3','37.2 5.2 6.0 6.0 6.8 13.2',
                    '3.8 0.3 0.4 0.4 1.2 1.5','36.5 7.9 5.9 6.7 7.0 9.0',
                    '21.9 6.4 5.2 4.8 2.8 2.7','35.5 7.1 7.1 7.1 7.1 7.1'):
        if not re.search(r'\s+'.join(re.escape(n) for n in numbers.split()),compact):
            raise ValueError('9·7 지역·유형별 목표 원문 변경: 담당자 재검증 필요')
    return dict(policy_id='POL_2025_0907', target_units=1350000, metric='CONSTRUCTION',
        period_start='2026-01-01', period_end='2030-12-31', announced_at='2025-09-07',
        annual=[dict(year=2026+i,units=value,seoul_units=SEOUL[i]) for i,value in enumerate(ANNUAL)],
        programs=[dict(id=key,name=name,annual=[dict(year=2026+i,units=v) for i,v in enumerate(values)],
                       target_units=sum(values)) for key,name,values in PROGRAMS],
        table_total_units=sum(ANNUAL),rounding_unallocated_units=1350000-sum(ANNUAL),
        geography=['서울특별시','경기도','인천광역시'],
        region_allocations={'서울특별시':sum(SEOUL),'경기도':None,'인천광역시':None},
        joint_region_units=sum(ANNUAL)-sum(SEOUL),
        evidence_url=PDF_URL,pdf_page=index+1,printed_page=43,origin='OFFICIAL',
        base_date='2025-09-07',date_precision='DAY',
        occupancy_outlook=extract_occupancy_outlook(pages),
        note='기타 주택사업은 원문상 과거 평균 유지 가정. 경기·인천 개별 배분 및 미특정 사업 목표는 추정하지 않음.')

def extract_occupancy_outlook(pages):
    text=next((t for t in pages if '입주물량' in t and '16.1' in t and '11.2' in t),None)
    if not text:raise ValueError('입주 전망 원문 미확보 · 수치 재검증 필요')
    for value in ('2.7','3.8','4.8','2.9','19.5','18.5','16.1','11.2'):
        if value not in text:raise ValueError('입주 전망 원문 변경')
    return dict(metric='MOVE_IN',source_role='MARKET_OUTLOOK',adoption='MANAGEMENT_TARGET',
        adoption_basis='사용자 요청에 따라 원문 입주 전망을 관리목표로 채택 · 135만 신규 착공 목표와 별도 모집단',
        unit='호',scope='수도권 아파트 전체',pdf_page=pages.index(text)+1,printed_page=2,
        evidence_url=PDF_URL,baseline_year=2025,
        annual=[dict(year=y,units=u,seoul_units=v,role='REFERENCE' if y<2025 else 'FORECAST_TARGET')
            for y,u,v in [(2023,195000,27000),(2024,185000,38000),(2025,161000,48000),(2026,112000,29000)]])

def collect_original_plan(source,fetcher):
    payload=parse_original_plan(fetcher.get(PDF_URL,'pdf'))
    return [('policy_delivery_plan','POL_2025_0907',payload)],dict(complete_query=True,provided=1,fetched=1,
        record_count=1,scope_note='9·7 원문 43쪽 수도권·서울 연도별 착공 계획 및 유형별 목표; 단계별 전체 일정은 별도')

def collect_incheon_lh(source,fetcher):
    proxy=dict(source,id='lh_rent' if source['id'].endswith('rent') else 'lh_sale',regions=['인천광역시'])
    records,stats=collect_lh_plan(proxy,fetcher)
    return records,dict(stats,scope_note='LH 인천 건설형 주택 공개 공급계획 전체; 정책 귀속 검토')

def collect_incheon_construction(source,fetcher):
    return collect_construction(dict(source,include_incheon=True),fetcher)

def collect_incheon_statistics(source,fetcher):
    return collect_statistics(dict(source,stat_regions={'인천':'인천광역시'}),fetcher)

def collect_incheon_geometry(source,fetcher,service):
    from sqlalchemy import text
    import json
    # Query all Incheon features, including islands; do not hard-code the number
    # of boroughs because the 2026 administrative reorganisation changed it.
    params=dict(key=key_for(source),service='data',request='GetFeature',version='2.0',
                data='LT_C_ADSIGG_INFO',attrFilter='sig_cd:like:28',crs='EPSG:4326',
                size=1000,page=1,format='json')
    data=response_json(fetcher.get(DATA_URL,'json',params=params,headers={'Referer':'https://www.minslab.kr/poc/home/'}))
    response=data.get('response',{})
    if response.get('status')!='OK': raise ValueError('인천 VWorld 시군구 경계 조회 확인 필요')
    features=response['result']['featureCollection']['features']
    if len(features)!=int(response['record']['total']) or not features: raise ValueError('인천 경계 페이지 누락')
    records=[]
    for f in features:
        p=f['properties'];code=str(p.get('sig_cd',''));name=p.get('sig_kor_nm','')
        if not re.fullmatch(r'28\d{3}',code):continue
        geometry=json.dumps(f['geometry'])
        with service.engine.connect() as connection:
            shape=connection.execute(text('''WITH shape AS (
              SELECT ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(:geometry),4326)) geom)
              SELECT ST_AsGeoJSON(ST_SimplifyPreserveTopology(geom,0.0001)) geometry,
                     ST_AsGeoJSON(ST_PointOnSurface(geom)) point FROM shape'''),{'geometry':geometry}).mappings().one()
        point=json.loads(shape['point'])['coordinates']
        records.append(('policy_municipality',code,dict(name=name,region='인천광역시',admin_codes=[code],
            geometry=json.loads(shape['geometry']),longitude=point[0],latitude=point[1],
            base_date=today().isoformat(),date_precision='COLLECTION',source_layer='LT_C_ADSIGG_INFO',
            evidence_url=source['url'],coordinate_basis='공식 시군구 경계 대표점')))
    if not records:raise ValueError('인천 시군구 경계 미확보')
    return records,dict(complete_query=True,provided=len(records),fetched=len(records),
        scope_note='VWorld 현재 인천 시군구 경계. 2026 행정구역 개편 반영 여부는 원천 판본 기준')
