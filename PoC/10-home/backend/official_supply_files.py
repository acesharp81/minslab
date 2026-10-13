"""Official candidate inventories and future schedules; never infer policy achievements."""
import csv
import io
import re
from datetime import date
from html import unescape

from .collectors import clean, integer

FILE_URL = re.compile(r'"contentUrl"\s*:\s*"(https://www\.data\.go\.kr/cmm/cmm/fileDownload\.do\?[^"\s]+)"')
REGIONS = {'서울특별시', '경기도'}


def _download(source, fetcher, title_pattern):
    page = fetcher.get(source['url']).decode('utf-8', 'replace')
    match = FILE_URL.search(page)
    version = re.search(title_pattern, page)
    if not match or not version:
        raise ValueError('공식 파일 링크·기준일 확인 실패: 원천 페이지 변경')
    day = version.group(1)
    stamp = date(int(day[:4]), int(day[4:6]), int(day[6:8])).isoformat()
    return fetcher.get(unescape(match.group(1)), 'csv'), stamp


def _csv_rows(content, required):
    try:
        decoded = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        decoded = content.decode('cp949')
    reader = csv.DictReader(io.StringIO(decoded))
    if reader.fieldnames is None or not set(required).issubset(reader.fieldnames):
        raise ValueError('공식 CSV 열 구성 변경')
    rows = list(reader)
    if not rows or any(None in row for row in rows):
        raise ValueError('공식 CSV 행 누락·열 구성 오류')
    return rows


def parse_renewal_inventory(content, source, version):
    """One dated national inventory, filtered to Seoul/Gyeonggi; not a plan event."""
    columns = ('시도', '시군구', '구역명칭', '현 사업추진단계', '사업유형', '사업시행자', '공급 예정 세대수')
    rows = _csv_rows(content, columns)
    records, seen = [], set()
    regional = {region: 0 for region in REGIONS}
    unverified_zero = 0
    not_applicable = 0
    for row in rows:
        region = clean(row['시도'])
        if region not in REGIONS:
            continue
        city, name, kind = (clean(row[key]) for key in ('시군구', '구역명칭', '사업유형'))
        if not all((city, name, kind)):
            raise ValueError('정비사업 필수 지역·구역명·유형 누락')
        key = '|'.join((region, city, name, kind))
        if key in seen:
            raise ValueError('정비사업 구역 자연키 중복: 임의 병합 금지')
        seen.add(key)
        raw_units = clean(row['공급 예정 세대수'])
        if raw_units == '해당없음':
            units, value_status = None, 'NOT_APPLICABLE'
            not_applicable += 1
        else:
            units = integer(raw_units)
            if units == 0 or units is None:
                # Zero does not establish a confirmed absence of future supply.
                units, value_status = None, 'UNVERIFIED'
                unverified_zero += 1
            else:
                value_status = 'AVAILABLE'
        payload = {
            'sample_kind': 'renewal_inventory', 'name': name, 'region': region, 'municipality': city, 'address': None,
            'source_object_id': key, 'source_date': version, 'base_date': version,
            'source_date_label': '공개 파일명 기준일; 개별 사건일 아님', 'date_precision': 'DAY',
            'business_type': kind, 'stage_label': clean(row['현 사업추진단계']),
            'developer': clean(row['사업시행자']) or None,
            'units': units, 'planned_units': units, 'source_planned_units': raw_units,
            'value_status': value_status,
            'unit_basis': '정비사업 후 공급 예정 세대수; 실제 준공·입주 아님',
            'record_role': 'PROJECT_CANDIDATE', 'policy_mapping_status': 'UNMAPPED',
            'legal_effect': 'REFERENCE_ONLY', 'availability': 'PUBLIC',
            'dataset_version': version, 'evidence_url': source['url'],
            'warnings': ['ZERO_PLANNED_UNITS_UNVERIFIED'] if value_status == 'UNVERIFIED' else [],
        }
        records.append(('renewal_inventory', key, payload))
        regional[region] += 1
    if not records:
        raise ValueError('정비사업 CSV에서 서울·경기 행 미확보')
    return records, {
        'file_rows': len(rows), 'included_rows': len(records),
        'excluded_rows': len(rows) - len(records), 'region_counts': regional,
        'unverified_zero_rows': unverified_zero, 'not_applicable_rows': not_applicable,
        'dataset_version': version,
        'complete_query': True, 'complete_population': False,
        'scope_note': '공개일 기준 전국 정비구역 현황 파일 중 서울·경기 행. 고시 이력·모든 유형의 공급사업·실제 준공 전수 아님',
    }


def collect_renewal_inventory(source, fetcher):
    content, version = _download(source, fetcher, r'전국 도시정비사업 통합 데이터_(\d{8})')
    return parse_renewal_inventory(content, source, version)


def parse_lh_completion_plan(content, source, version):
    """LH block completion forecasts, never actual completion or policy delivery."""
    columns = ('사업지구명', '블록명', '위치', '공급유형', '세대수', '준공예정일')
    rows = _csv_rows(content, columns)
    records, seen = [], set()
    regional = {region: 0 for region in REGIONS}
    unknown_units = 0
    for row in rows:
        address = clean(row['위치'])
        region = next((name for name in REGIONS if address.startswith(name)), None)
        if region is None:
            continue
        district, block, tenure = (clean(row[key]) for key in ('사업지구명', '블록명', '공급유형'))
        if not all((district, block, tenure)):
            raise ValueError('LH 준공예정 지구·블록·유형 누락')
        key = '|'.join((district, block, tenure))
        if key in seen:
            raise ValueError('LH 준공예정 지구·블록·유형 중복: 계획 물량 합산 금지')
        seen.add(key)
        raw_units = clean(row['세대수'])
        units = integer(raw_units)
        if units == 0 or units is None:
            units = None
            unknown_units += 1
        planned_day = clean(row['준공예정일'])
        if planned_day:
            try:
                planned_day = date.fromisoformat(planned_day).isoformat()
            except ValueError:
                raise ValueError('LH 준공예정일 형식 변경') from None
        payload = {
            'sample_kind': 'lh_completion_plan', 'name': f'{district} {block}', 'region': region, 'municipality': address.split()[1] if len(address.split()) > 1 else None,
            'address': address, 'district': district, 'block': block, 'tenure': tenure,
            'source_object_id': key, 'source_date': version, 'base_date': version,
            'source_date_label': '공개 파일명 기준일; 실제 준공일 아님',
            'dataset_version': version, 'units': units, 'planned_units': units, 'source_planned_units': raw_units,
            'completion_plan_date': planned_day or None,
            'date_precision': 'DAY' if planned_day else 'UNKNOWN',
            'value_status': 'AVAILABLE' if units is not None else 'UNVERIFIED',
            'schedule_status': 'PLANNED' if planned_day else 'DATE_UNKNOWN',
            'unit_basis': 'LH 공공주택 블록별 준공 예정 세대수; 실제 준공·입주 아님',
            'record_role': 'BLOCK_SCHEDULE_CANDIDATE', 'policy_mapping_status': 'UNMAPPED',
            'stage_label': '준공 예정', 'availability': 'PUBLIC',
            'evidence_url': source['url'],
            'warnings': ['UNCONFIRMED_UNITS'] if units is None else [],
        }
        records.append(('lh_completion_plan', key, payload))
        regional[region] += 1
    if not records:
        raise ValueError('LH 준공예정 CSV에서 서울·경기 행 미확보')
    return records, {
        'file_rows': len(rows), 'included_rows': len(records),
        'excluded_rows': len(rows) - len(records), 'region_counts': regional,
        'unknown_units_rows': unknown_units, 'dataset_version': version,
        'complete_query': True, 'complete_population': False,
        'scope_note': '파일 기준 착공(예정) 후 공공주택 블록의 준공예정. 실제 준공·입주 및 모든 공공주택 전수 아님',
    }


def collect_lh_completion_plan(source, fetcher):
    content, version = _download(source, fetcher, r'공공주택 준공예정현황_(\d{8})')
    return parse_lh_completion_plan(content, source, version)
