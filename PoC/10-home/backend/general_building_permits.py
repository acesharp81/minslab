"""General building permits, distinct from housing project approvals.

Only native household counts are kept. Rooms/families and scheduled starts
never substitute for households or actual starts. Identity review is separate.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from .api_samples import base, day, key_for, response_json, SAMPLE_LIMIT
from .collectors import clean, integer
from .building_scope import next_districts, expansion_stats
from .parcel_identity import enrich_source
from .db import now

URL='https://apis.data.go.kr/1613000/ArchPmsHubService/getApBasisOulnInfo'
KIND='general_permit'


def parse(data,source,region,sigungu,bjdong):
    response=data.get('response') or {};body=response.get('body') or {}
    if str((response.get('header') or {}).get('resultCode'))!='00':
        raise ValueError('일반 건축인허가 인증·응답 오류: 등록된 공통 인증키의 해당 서비스 활용승인·응답 확인 필요')
    total=integer(body.get('totalCount'));items=body.get('items') or {}
    rows=items.get('item',[]) if isinstance(items,dict) else None
    if isinstance(rows,dict):rows=[rows]
    if total is None or not isinstance(rows,list) or len(rows)>min(total,SAMPLE_LIMIT):
        raise ValueError('일반 건축인허가 페이지 형식 오류')
    records=[];seen=set()
    for raw in rows:
        identifier=clean(raw.get('mgmPmsrgstPk'));address=clean(raw.get('platPlc'))
        if not identifier or identifier in seen:raise ValueError('일반 인허가 관리키 누락·중복')
        if clean(raw.get('sigunguCd'))!=sigungu or clean(raw.get('bjdongCd'))!=bjdong or not address.startswith(region):
            raise ValueError('일반 건축인허가 지역·법정동 불일치')
        seen.add(identifier)
        p=base(source,KIND,clean(raw.get('bldNm')) or address,region,address,day(raw.get('crtnDay')))
        units=integer(raw.get('hhldCnt'));actual=day(raw.get('realStcnsDay'))
        p.update(source_object_id=identifier,native_id_namespace='ArchPmsHubService.mgmPmsrgstPk',
            sigungu_code=sigungu,bjdong_code=bjdong,units=units,household_count=units,
            family_count=integer(raw.get('fmlyCnt')),unit_count=integer(raw.get('hoCnt')),
            main_purpose=clean(raw.get('mainPurpsCdNm')),main_purpose_code=clean(raw.get('mainPurpsCd')),
            construction_type=clean(raw.get('archGbCdNm')),construction_type_code=clean(raw.get('archGbCd')),
            block=clean(raw.get('block')),lot=clean(raw.get('lot')),bun=clean(raw.get('bun')),ji=clean(raw.get('ji')),
            unit_basis='일반 건축인허가 원천 hhldCnt · 주택 유형·행위·중복 검증 전',
            source_date_label='원천 레코드 생성일',facts=[],
            dates={'건축허가일 (archPmsDay)':day(raw.get('archPmsDay')),'실제착공일 (realStcnsDay)':actual,
                   '착공예정일 (stcnsSchedDay)':day(raw.get('stcnsSchedDay')),
                   '착공연기일 (stcnsDelayDay)':day(raw.get('stcnsDelayDay')),'사용승인일 (useAprDay)':day(raw.get('useAprDay'))},
            warnings=['GENERAL_PERMIT_SCOPE_REVIEW'],stage_label='일반 건축인허가 원천 · 사업·주택 범위 확인 전')
        if units==0:p['warnings'].append('ZERO_HOUSEHOLDS_UNRESOLVED')
        if units is None:p['warnings'].append('HOUSEHOLDS_MISSING')
        enrich_source(p,raw)
        records.append((KIND,identifier,p))
    return records,total


def collect(source,fetcher,service):
    key=key_for(source)  # Reuse the housing API key after this service is approved.
    districts,counts,total_dongs=next_districts(service,source['id']);records=[]
    def fetch_dong(district):
        region,sigungu,bjdong,label=district
        page=1;expected=None;seen=set();collected=[]
        while True:
            data=response_json(fetcher.get(URL,'json',params=dict(serviceKey=key,sigunguCd=sigungu,bjdongCd=bjdong,
                numOfRows=SAMPLE_LIMIT,pageNo=page,_type='json')))
            current,total=parse(data,source,region,sigungu,bjdong)
            if expected is None:expected=total
            # A legitimate dense dong (화곡동) already returns 13,571 rows.
            # This is a local resource guard, not an upstream API result cap.
            if total>100000:raise ValueError('일반 인허가 법정동 100,000행 안전 상한 초과: 조회 범위 분할 필요')
            if total!=expected or len(current)!=min(SAMPLE_LIMIT,max(0,total-len(collected))):
                raise ValueError('일반 인허가 페이지 누락·수집 중 총건수 변경')
            for item in current:
                if item[1] in seen:raise ValueError('일반 인허가 페이지 간 중복키')
                seen.add(item[1])
            collected.extend(current)
            if len(collected)==total:break
            page+=1
        return collected,sigungu+bjdong,dict(matching_records=expected,sampled=len(collected),pages=page,complete_query=True,
            legal_dong_code=sigungu+bjdong,label=label,checked_at=now().isoformat())
    workers=max(1,min(4,int(os.environ.get('POC10_GENERAL_PERMIT_QUERY_WORKERS','1'))))
    # Each dong keeps sequential, validated pages. Do not publish any scope or
    # records unless every selected dong finishes successfully.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(fetch_dong,districts))
    for collected,code,meta in results:
        records.extend(collected);counts[code]=meta
    return records,dict(expansion_stats(counts,total_dongs,len(records)),collection_mode='GENERAL_BUILDING_PERMIT',
        complete_population=False,actual_events_created=0,endpoint='getApBasisOulnInfo',
        single_revisit_batch=getattr(service,'_single_revisit_batch',False))
