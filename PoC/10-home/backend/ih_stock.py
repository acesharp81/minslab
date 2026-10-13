"""iH current rental stock is reference data, never 9.7 new-start output."""
from datetime import timedelta

from .api_samples import base, key_for, response_json, today
from .collectors import clean, integer

URL = 'https://apis.data.go.kr/B552831/ls/rntHousSplTrgtAcrs'
RESIDENTIAL = ('detachedHouse', 'purchaseRental', 'publicRental', 'permanentRental',
               'jeonseRental', 'happyHouse', 'multiUnitHouse', 'sale', 'multiFamilyHouse',
               'nationalRental', 'installmentRental', 'longTermRental', 'safeHouse')


def parse_page(data, source, requested_date):
    response = data.get('response', data)
    header = response.get('header', {})
    if str(header.get('resultCode')) not in ('00', '0', '0000', '200'):
        raise ValueError('iH API 정상 응답 미확인: 원천 접근·조회 조건 점검 필요 (0호 아님)')
    body = response.get('body', {})
    total = integer(body.get('totalCount'))
    houses = body.get('houses')
    if total is None or not isinstance(houses, list):
        raise ValueError('iH 주택 목록·전체 건수 schema 미확인 (0호 아님)')
    records = []
    for row in houses:
        municipality, name = clean(row.get('regionName')), clean(row.get('housName'))
        if not municipality or not name:
            raise ValueError('iH 주택명·지역 식별자 미확보')
        quantities = {}
        for key in ('totalHouseholds', 'contractHouseholds', 'vacantHouseholds'):
            raw = row.get(key)
            if not isinstance(raw, dict):
                raise ValueError('iH 주택 유형별 수량 schema 변경')
            quantities[key] = {k: integer(v) for k, v in raw.items()}
        # The source mixes homes, commercial units and substitution accounting.
        # Keep all raw categories, but exclude non-residential categories from sums.
        count = quantities['totalHouseholds']
        valid = [count[k] for k in RESIDENTIAL if count.get(k) is not None]
        complete = all(count.get(k) is not None for k in RESIDENTIAL)
        identifier = municipality + ':' + name
        payload = base(source, 'agency_stock', name, '인천광역시', None)
        payload.update(source_object_id=identifier, municipality=municipality,
                       units=sum(valid) if complete else None, stock_known_units=sum(valid) if valid else None,
                       stock_quantity_status='COMPLETE' if complete else 'PARTIAL',
                       unit_basis='iH 조회 기준일 주거 유형 재고 세대수 · 미확보 유형은 0으로 합산하지 않음 · 신규 착공/공급 실적 아님',
                       requested_reference_date=requested_date, source_date=None,
                       source_date_label='원천 개별 관측일 미제공 · 조회 기준일 별도',
                       raw_households=quantities, geography_basis='원천 시군구명 · 좌표 미확보',
                       stage_label='기관 재고 참조 · 9·7 신규 착공 실적 미집계',
                       policy_mapping_status='REFERENCE_ONLY', sample_mode='OFFICIAL_REFERENCE')
        records.append(('agency_stock', identifier, payload))
    return records, total


def collect_ih_stock(source, fetcher):
    requested = (today().replace(day=1) - timedelta(days=1)).isoformat()
    records, seen, expected, page = [], set(), None, 1
    while True:
        params = dict(serviceKey=key_for(source), pageNo=page, numOfRows=100,
                      crtrYmd=requested.replace('-', ''), regionName='', housName='')
        try:
            content = fetcher.get(URL, 'json', params=params)
        except RuntimeError as error:
            import re
            status = re.search(r"HTTP [0-9]{3}|ReadTimeout|ConnectTimeout|ConnectError|ReadError", str(error))
            detail = status.group(0) if status else "timeout/HTTP"
            raise ValueError(f'iH 기관 API 연결 실패({detail}). 재시도 필요 · 데이터 존재 여부 미판정 · 0호 아님') from None
        current, total = parse_page(response_json(content), source, requested)
        if expected is None:
            expected = total
        if total != expected or len(current) > 100:
            raise ValueError('iH 페이지별 전체 건수 불일치')
        for record in current:
            if record[1] in seen:
                raise ValueError('iH 지역·주택 식별자 중복: 원천 유형 분리 검토 필요')
            seen.add(record[1]);records.append(record)
        if len(records) == expected:
            break
        if not current or len(records) > expected:
            raise ValueError('iH 페이지 누락: 부분 자료를 전체 수집으로 표시하지 않음')
        page += 1
    return records, dict(complete_query=True, provided=expected, fetched=len(records), pages=page,
                         requested_reference_date=requested, policy_actual_included=False,
                         scope_note='iH 전월 말 조회조건 재고·계약·공가 참조. 개별 관측일·신규 건설 여부·정책 귀속 미확인; 9·7 실적 제외')
