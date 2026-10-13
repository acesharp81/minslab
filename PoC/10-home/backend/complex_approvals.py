"""Apartment-complex use-approval reference; not a policy or occupancy total."""

import csv
import io
import re
from collections import Counter
from datetime import date

from .collectors import clean, integer
from .official_supply_files import _download

COLUMNS = {'단지고유번호', '필지고유번호', '주소', '단지명_공시가격',
           '단지명_건축물대장', '단지명_도로명주소', '단지종류', '동수', '세대수', '사용승인일', '도로명주소'}
REGIONS = ('서울특별시', '경기도')


def parse_complex_approvals(content, source, version):
    try:
        raw = content.decode('cp949')
    except UnicodeDecodeError as error:
        raise ValueError('공동주택 단지 식별정보 CSV 인코딩 변경') from error
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames or not COLUMNS.issubset(reader.fieldnames):
        raise ValueError('공동주택 단지 식별정보 CSV 열 변경')
    records, seen, region_counts = [], set(), Counter()
    all_rows = target_rows = undated = older = 0
    for row in reader:
        all_rows += 1
        if None in row:
            raise ValueError('공동주택 단지 CSV 열 수 변경')
        address = clean(row['주소'])
        region = next((name for name in REGIONS if address.startswith(name + ' ')), None)
        if not region:
            continue
        target_rows += 1
        stamp = clean(row['사용승인일'])
        if not stamp:
            undated += 1
            continue
        try:
            approval_day = date.fromisoformat(stamp)
        except ValueError as error:
            raise ValueError('공동주택 단지 사용승인일 형식 변경') from error
        if approval_day.year < 2018:
            older += 1
            continue
        complex_id, parcel_id = clean(row['단지고유번호']), clean(row['필지고유번호'])
        if not complex_id or not parcel_id or not complex_id.isdigit() or not parcel_id.isdigit():
            raise ValueError('공동주택 단지·필지 식별자 누락')
        key = complex_id + '|' + parcel_id
        if key in seen:
            raise ValueError('공동주택 단지·필지 중복: 임의 합산 금지')
        seen.add(key)
        name = next((clean(row[col]) for col in ('단지명_공시가격', '단지명_건축물대장', '단지명_도로명주소') if clean(row[col])), '')
        if not name:
            raise ValueError('공동주택 단지명 누락')
        units = integer(clean(row['세대수']))
        if units is not None and units <= 0:
            units = None
        payload = dict(sample_kind='complex_approval_reference', name=name,
            region=region, municipality=address.split()[1], address=address,
            road_address=clean(row['도로명주소']) or None, source_object_id=key,
            complex_id=complex_id, parcel_id=parcel_id,
            complex_name_register=clean(row['단지명_건축물대장']) or None,
            complex_name_road=clean(row['단지명_도로명주소']) or None,
            complex_type=clean(row['단지종류']), building_count=integer(clean(row['동수'])),
            units=units, approval_date=approval_day.isoformat(),
            source_date=version, source_date_label='CSV 공개 판본 기준일',
            base_date=approval_day.isoformat(), base_date_basis='원본 사용승인일',
            dataset_version=version, evidence_url=source['url'],
            unit_basis='공시대상 공동주택 단지·필지 세대수; 정책별 공급 또는 실제 입주 호수 아님',
            record_role='COMPLEX_APPROVAL_REFERENCE', project_link_status='REVIEW',
            actual_occupied_units=None, policy_mapping_status='UNMAPPED',
            warnings=['NOT_POLICY_DELIVERY', 'NOT_ACTUAL_OCCUPANCY', 'PROJECT_LINK_REVIEW'])
        records.append(('complex_approval_reference', key, payload))
        region_counts[region] += 1
    if all_rows < target_rows or not records or sum(region_counts.values()) != len(records):
        raise ValueError('공동주택 단지 파일에서 서울·경기 사용승인 행 미확보')
    return records, dict(file_rows=all_rows, target_region_rows=target_rows,
        included_rows=len(records), undated_target_rows=undated, before_2018_target_rows=older,
        region_counts=dict(region_counts), dataset_version=version, complete_query=True,
        complete_population=False,
        scope_note='공시대상 공동주택 단지 식별정보 공개본의 2018년 이후 사용승인 행. 단지·필지 행은 사업/정책 전수나 실제 입주 호수가 아니며 단순 합산 금지')


def collect_complex_approvals(source, fetcher):
    content, version = _download(source, fetcher, r'공동주택 단지 식별정보_기본정보_(\d{8})')
    return parse_complex_approvals(content, source, version)
