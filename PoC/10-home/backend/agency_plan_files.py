"""Versioned official plan files and contracts discovered in the team route audit.

These are source observations, not new projects or measured housing delivery.
"""
import hashlib
import json
import re
from collections import Counter, defaultdict
from .collectors import clean, integer
from .official_supply_files import _download, _csv_rows
from .schedule_period import schedule_period
from .lh_public_history import address_area

SPECS = {
 'lh_happy_plan_file': ('행복주택 공급계획', ('지역','유형','지구명','면적','공급호수','공급시기','입주예정')),
 'sh_national_plan_file': ('국민임대주택 공급계획', ('단지명','공급 계','소재지','공급(예정) 년도','공급(예정)월')),
 'sh_jeonse_plan_file': ('장기전세주택 공급계획', ('단지명','계','소재지','공급예정년도','공급예정월')),
 'sh_happy_plan_file': ('행복주택(리츠포함) 공급계획', ('단지명','소재지','공급(예정) 년도','공급예정물량 총계')),
 'reb_movein_plan_file': ('주택공급정보_입주예정물량정보', ('입주예정월','지역','사업유형','주소','아파트명','세대수')),
 'sh_contract_file': ('공사계약 정보', ('계약명','계약금액(원)','계약시작일','계약종료일','입찰방법','계약대상')),
}
REGIONS={'서울':'서울특별시','경기':'경기도','인천':'인천광역시'}


def parse_plan_file(content, source, version):
    sid=source['id'];rows=_csv_rows(content,SPECS[sid][1]);records=[];seen={};duplicates=0
    dimensions=defaultdict(set)
    if sid=='lh_happy_plan_file':
        for r in rows:
            dim=tuple(clean(r.get(k)) for k in ('지역','지구명','유형','면적','공급시기','입주예정','비고'))
            dimensions[dim].add(clean(r['공급호수']))
    for raw in rows:
        r={k:clean(v) for k,v in raw.items()};warnings=[];events=[];area=None;city=None
        if sid=='sh_contract_file':
            name=r['계약명'];region=None;address='';units=None;tenure='';supply=move=None
            identity=[name,r['계약대상'],r['계약시작일'],r['계약종료일'],r['계약금액(원)'],r['입찰방법']]
            warnings=['CONTRACT_NOT_CONSTRUCTION_ACTUAL','LOCATION_NOT_VERIFIED']
        elif sid=='lh_happy_plan_file':
            region=r['지역']
            if region not in REGIONS.values():continue
            name=r['지구명'];tenure=r['유형'];units=integer(r['공급호수']);area=r['면적'];address=''
            supply=r['공급시기'];move=r['입주예정'];identity=[region,name,tenure,area,supply,move,r.get('비고','')]
            if len(dimensions[tuple(identity)])>1:warnings.append('AMBIGUOUS_PLAN_DIMENSION')
            identity.append(r['공급호수'])
        elif sid=='reb_movein_plan_file':
            region=REGIONS.get(r['지역'])
            if not region:continue
            name=r['아파트명'];address=r['주소'];address_region,city=address_area(address)
            if address_region!=region:raise ValueError('입주계획 시도·주소 불일치')
            tenure=r['사업유형'];units=integer(r['세대수']);supply=None;move=r['입주예정월']
            identity=[region,name,address,tenure,move]
        else:
            region='서울특별시';name=r['단지명'];address=r['소재지'];city=address.split()[0] if address.endswith('구') else None
            tenure={'sh_national_plan_file':'국민임대','sh_jeonse_plan_file':'장기전세','sh_happy_plan_file':'행복주택'}[sid]
            if sid=='sh_national_plan_file':units=integer(r['공급 계']);year=r['공급(예정) 년도'];mo=r['공급(예정)월']
            elif sid=='sh_jeonse_plan_file':units=integer(r['계']);year=r['공급예정년도'];mo=r['공급예정월']
            else:units=integer(r['공급예정물량 총계']);year=r['공급(예정) 년도'];mo=''
            supply=year+'년'+(mo+'월' if mo else '');move=None;identity=[region,name,tenure,address,supply]
            detail=[integer(v) for k,v in r.items() if re.search('공급예정(?:물량|세대수)\\(',k)]
            if detail and all(v is not None for v in detail) and sum(detail)!=units:warnings.append('SOURCE_TOTAL_MISMATCH')
        if not name:raise ValueError('공식 계획 사업명 누락')
        if units==0:units=None;warnings.append('ZERO_UNITS_UNVERIFIED')
        for stage,value in [('SUPPLY',supply),('MOVE_IN',move)]:
            period=schedule_period(value)
            if period and 'AMBIGUOUS_PLAN_DIMENSION' not in warnings:events.append(dict(stage=stage,kind='PLAN',date=period['due_date'],units=units,
                date_label=period['original'],precision=period['precision'],date_conversion=period['conversion'],
                basis='공식 공개파일 예정 일정 · 실제 사건일 아님'))
            elif value and not period:warnings.append(stage+'_DATE_UNPARSED')
        key=hashlib.sha256(json.dumps(identity,ensure_ascii=False).encode()).hexdigest()
        digest=hashlib.sha256(json.dumps(r,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        if key in seen:
            if seen[key]!=digest:raise ValueError('공식 계획 같은 식별키의 값 충돌')
            duplicates+=1;continue
        seen[key]=digest
        kind='agency_contract' if sid=='sh_contract_file' else 'agency_plan'
        payload=dict(sample_kind=kind,name=name,region=region,municipality=city,address=address,
            tenure=tenure,area=area,units=units,planned_units=units,supply_raw=supply,move_in_raw=move,
            source_object_id=key,source_date=version,base_date=version,dataset_version=version,
            source_date_label='공개 파일명 기준일 · 계획 대상 시기와 구분',date_precision='DAY',
            facts=events,native_fields=r,source_row_sha256=digest,evidence_url=source['url'],
            warnings=warnings,policy_mapping_status='UNMAPPED',availability='PUBLIC',
            stage_label='공사 계약 참조 · 착공 증거 아님' if kind=='agency_contract' else '공식 공급·입주 예정계획',
            unit_basis='계약 참고자료 · 주택 호수 미제공' if kind=='agency_contract' else '공개본 계획 호수 · 다른 공개본·기존 사업과 중복 합산 금지')
        records.append((kind,key,payload))
    if not records:raise ValueError('수도권 공식 계획 파일 행 미확보')
    return records,dict(file_rows=len(rows),included_rows=len(records),duplicate_rows=duplicates,
        excluded_rows=len(rows)-len(records)-duplicates,complete_query=True,complete_population=False,
        dataset_version=version,region_counts=dict(Counter(p['region'] for _,_,p in records)),
        warning_counts=dict(Counter(w for _,_,p in records for w in p['warnings'])),
        scope_note='SH 공사계약 파일 전체. 사업 소재지·주택 공사 여부는 개별 연결 전 미확인' if sid=='sh_contract_file' else '공개 파일 수도권 행 전체·원천 판본 보존. 공급/입주 예정계획. 정책 귀속·실적 자동 생성 없음')


def collect_plan_file(source, fetcher):
    title=SPECS[source['id']][0]
    content,version=_download(source,fetcher,re.escape(title)+r'_(\d{8})')
    return parse_plan_file(content,source,version)
