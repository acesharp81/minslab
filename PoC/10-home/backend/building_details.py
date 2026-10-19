"""Bounded Housing HUB dong/parcel evidence linked by the native housing permit PK."""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .api_samples import key_for, response_json
from .collectors import clean, integer

BASE_URL = 'https://apis.data.go.kr/1613000/HsPmsHubService/'
ENDPOINTS = {'permit_dong': 'getHpDongOulnInfo', 'permit_parcel': 'getHpPlatPlcInfo'}
PAGE_SIZE = 100
DEFAULT_DONGS = ('1168010300', '4111710300')  # Seoul Gangnam Gaepo; Gyeonggi Suwon Yeongtong Iui.


def pilot_dongs():
    raw = os.environ.get('POC10_BUILDING_DETAIL_DONGS', ','.join(DEFAULT_DONGS))
    codes = tuple(code.strip() for code in raw.split(',') if code.strip())
    if not codes or len(codes) > 8 or len(set(codes)) != len(codes) or any(
            not re.fullmatch(r'(11|28|41)\d{8}', code) for code in codes):
        raise ValueError('건축HUB 상세 파일럿 법정동은 서울·경기·인천 10자리 코드 1~8개로 설정하세요')
    return codes


def _source_day(row):
    value = clean(row.get('crtnDay'))
    if not re.fullmatch(r'\d{8}', value):
        return None
    try:
        return date(int(value[:4]), int(value[4:6]), int(value[6:])).isoformat()
    except ValueError:
        return None


def _row_key(kind, row):
    parent = clean(row.get('mgmHsrgstPk'))
    if not parent:
        raise ValueError('건축HUB 상세행 주택인허가 관리번호 누락')
    if kind == 'permit_dong':
        child = clean(row.get('mgmDongOulnPk'))
        if not child:
            raise ValueError('건축HUB 동별개요 관리번호 누락')
        return parent + ':' + child
    parts = [parent] + [clean(row.get(field)) for field in
        ('platGbCd', 'bun', 'ji', 'reprYn', 'relJibunNm', 'dongRelGb', 'crtnDay')]
    # Some official parcel rows have no lot number; retain them for later review.
    return '|'.join(parts)


def parse_detail_rows(data, source, kind, region, sigungu, bjdong):
    response = data.get('response') or {}
    header, body = response.get('header') or {}, response.get('body') or {}
    if str(header.get('resultCode')) != '00' or 'totalCount' not in body:
        raise ValueError('건축HUB 상세 인증·응답 schema 확인 필요')
    try:
        expected = int(body['totalCount'])
    except (TypeError, ValueError):
        raise ValueError('건축HUB 상세 totalCount 오류') from None
    items = body.get('items') or {}
    rows = items.get('item', []) if isinstance(items, dict) else None
    if isinstance(rows, dict):
        rows = [rows]
    if not isinstance(rows, list) or expected < len(rows) or len(rows) > PAGE_SIZE:
        raise ValueError('건축HUB 상세 행/페이지 schema 오류')
    records = []
    for row in rows:
        if (clean(row.get('sigunguCd')) != sigungu or clean(row.get('bjdongCd')) != bjdong
                or not clean(row.get('platPlc')).startswith(region)):
            raise ValueError('건축HUB 상세 지역·법정동 응답 불일치')
        key = _row_key(kind, row)
        common = {
            'sample_kind': kind, 'name': clean(row.get('bldNm')) or clean(row.get('dongNm')) or clean(row.get('platPlc')),
            'region': region, 'address': clean(row.get('platPlc')),
            'source_object_id': key, 'parent_permit_native_id': clean(row.get('mgmHsrgstPk')),
            'sigungu_code': sigungu, 'bjdong_code': bjdong,
            'base_date': datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat(), 'source_date': _source_day(row),
            'source_date_label': '원천 레코드 생성일', 'date_precision': 'DAY' if _source_day(row) else 'UNKNOWN',
            'availability': 'PUBLIC', 'policy_mapping_status': 'UNMAPPED',
            'record_role': 'PERMIT_DETAIL_EVIDENCE', 'units': None,
            'stage_label': '주택인허가 상세 근거 · 사업/정책 연결 전',
            'evidence_url': source['url'], 'warnings': [],
        }
        if kind == 'permit_dong':
            raw_floors = row.get('grndFlrCnt')
            try:
                floors = integer(raw_floors)
            except ValueError:
                floors = None
                common['warnings'].append('FLOORS_INVALID')
            common['raw_floors'] = raw_floors
            common.update(building_dong=clean(row.get('dongNm')) or None,
                native_dong_id=clean(row.get('mgmDongOulnPk')),
                main_purpose=clean(row.get('mainPurpsCdNm')) or None,
                household_breakdown={field: integer(row.get(field)) for field in row
                    if field.startswith('hhldCnt')},
                floors=floors,
                unit_basis='동별 공공/민간 등 구성. 합산·공급실적은 사업 동일성 확인 후 판단')
        else:
            common.update(plat_gb_cd=clean(row.get('platGbCd')),
                bun=clean(row.get('bun')), ji=clean(row.get('ji')),
                representative=clean(row.get('reprYn')) == '1',
                related_lot=clean(row.get('relJibunNm')) or None,
                unit_basis='주택인허가 대지위치·필지 연결 근거. 세대수 실적 아님')
            from .parcel_identity import enrich_source
            enrich_source(common, row)
            if not common['bun'] or not common['ji']:
                common['warnings'].append('PARCEL_LOT_MISSING')
        records.append((kind, key, common))
    return records, expected


def next_detail_dongs(service):
    """Resume from the last successful batch, using the official live legal-dong list."""
    codes = list({r['source_object_id']: r for kind in ('legal_dong','policy_legal_dong') for r in service.rows(kind)}.values())
    if not codes:
        raise ValueError('공식 법정동 코드 수집이 먼저 필요합니다')
    previous = service.latest_collection_stats('building_hub_details')
    completed = dict(previous.get('district_counts') or {})
    # The first two-dong pilot predates cumulative district_counts.
    by_code = {}
    for item in previous.get('endpoint_coverage', []):
        if item.get('complete_query') and item.get('expected') == item.get('fetched'):
            by_code.setdefault(item['legal_dong_code'], set()).add(item['endpoint'])
    for code, endpoints in by_code.items():
        if endpoints == set(ENDPOINTS.values()):
            completed.setdefault(code, {'complete_query': True})
    addresses = [p.get('address') or '' for p in service.projects()]
    pending = [row for row in codes if not completed.get(row['source_object_id'], {}).get('complete_query')]
    from .parcel_identity import target_dongs
    targeted = target_dongs(service) if hasattr(service, 'sessions') else set()
    pending.sort(key=lambda row: (-1 if row['source_object_id'] in targeted else 0 if any(row['address'] in address for address in addresses if address) else 1,
                                  row['source_object_id']))
    from .building_scope import balanced_pending
    pending=balanced_pending(codes,completed,pending)
    limit = max(1, min(8, int(os.environ.get('POC10_BUILDING_DETAIL_DONGS_PER_BATCH', '8'))))
    from datetime import datetime,timedelta,timezone
    instant=datetime.now(timezone.utc)
    def overdue(row):
        try:return datetime.fromisoformat(completed[row['source_object_id']]['checked_at']).astimezone(timezone.utc)<=instant-timedelta(days=7)
        except (KeyError,TypeError,ValueError):return True
    revisit=sorted((r for r in codes if completed.get(r['source_object_id'],{}).get('complete_query') and overdue(r)),
        key=lambda r:(completed[r['source_object_id']].get('checked_at') or '',r['source_object_id']))
    reserve=min(len(revisit),max(1,limit//4)) if limit>1 or not pending or not previous.get('single_revisit_batch') else 0
    selected=pending[:limit-reserve]+revisit[:reserve]
    if len(selected)<limit:selected+=revisit[reserve:reserve+limit-len(selected)]
    service._detail_single_revisit_batch=bool(limit==1 and selected and selected[0] in revisit)
    return tuple(row['source_object_id'] for row in selected), completed, len(codes)


def _fetch_code(source, fetcher, code):
    records,coverage=[],[]
    sigungu, bjdong = code[:5], code[5:]
    region = {'11':'서울특별시','28':'인천광역시','41':'경기도'}[code[:2]]
    for kind, endpoint in ENDPOINTS.items():
        total, seen, collected, page, raw_fetched, duplicate_rows = None, {}, [], 1, 0, 0
        while True:
            params = {'serviceKey': key_for(source), 'sigunguCd': sigungu,
                      'bjdongCd': bjdong, 'pageNo': page, 'numOfRows': PAGE_SIZE, '_type': 'json'}
            data = response_json(fetcher.get(BASE_URL + endpoint, 'json', params=params))
            current, found = parse_detail_rows(data, source, kind, region, sigungu, bjdong)
            if total is None:
                total = found
                if total > 10000:
                    raise ValueError('건축HUB 상세 파일럿 페이지 상한 초과')
            if found != total or len(current) != min(PAGE_SIZE, max(0, total - raw_fetched)):
                raise ValueError('건축HUB 상세 페이지 누락·수집 중 건수 변경')
            raw_fetched += len(current)
            for item in current:
                previous = seen.get(item[1])
                if previous is not None:
                    if previous != item[2]:
                        raise ValueError('건축HUB 상세 원천키 충돌: 같은 키의 다른 내용')
                    duplicate_rows += 1
                    continue
                seen[item[1]] = item[2]
                collected.append(item)
            if raw_fetched >= total:
                break
            page += 1
        records.extend(collected)
        coverage.append({'endpoint': endpoint, 'kind': kind, 'legal_dong_code': code,
            'region': region, 'expected': total, 'fetched': raw_fetched,
            'unique_records': len(collected), 'duplicate_rows': duplicate_rows,
            'pages': page, 'complete_query': True})
    return records,coverage


def collect_building_details(source, fetcher, service=None):
    records, coverage = [], []
    selected, completed, total_dongs = (next_detail_dongs(service) if service is not None
                                        else (pilot_dongs(), {}, None))
    workers=max(1,min(4,int(os.environ.get('POC10_BUILDING_DETAIL_QUERY_WORKERS','1'))))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results=list(pool.map(lambda code:_fetch_code(source,fetcher,code),selected))
    for code,(new_records,new_coverage) in zip(selected,results):
        records.extend(new_records);coverage.extend(new_coverage)
        from .db import now
        completed[code] = {'complete_query': True,'checked_at':now().isoformat(),
                           'fetched': sum(item['fetched'] for item in coverage if item['legal_dong_code'] == code)}
    if not records and service is None:
        raise ValueError('건축HUB 상세 파일럿 근거가 없음')
    stats = {
        'pilot_dongs': list(selected), 'endpoint_coverage': coverage,
        'provided': sum(x['expected'] for x in coverage),
        'fetched': sum(x['fetched'] for x in coverage),
        'unique_records': len(records),
        'duplicate_rows': sum(x['duplicate_rows'] for x in coverage),
        'complete_query': True, 'complete_population': False,
        'scope_note': '지정된 서울·경기·인천 법정동의 동별·대지위치 전체 페이지. 다른 동과 실제 정책 공급실적은 미확보',
    }
    if stats['duplicate_rows']:
        stats['scope_note'] += f" 원천 동일 중복행 {stats['duplicate_rows']}건은 1회 저장; 다른 내용의 원천키 충돌은 배치 실패."
    if service is not None:
        done = sum(item.get('complete_query') is True for item in completed.values())
        stats.update(incremental=True, district_counts=completed,revisit_after_days=7,
                     single_revisit_batch=getattr(service,'_detail_single_revisit_batch',False),
                     scope_total_dongs=total_dongs, scope_completed_dongs=done,
                     scope_remaining_dongs=max(0, total_dongs - done), complete_scope=done == total_dongs,
                     scope_note=f'현존 서울·경기·인천 법정동 {total_dongs}개 중 {done}개 상세 2개 endpoint 전체 페이지 확인. 원천 동일 중복행 {stats["duplicate_rows"]}건은 1회 저장. 실제 정책 공급실적은 별도 검증')
    return records, stats
