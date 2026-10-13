"""Agency evidence. Plans become REVIEW candidates; notice lists never prove delivery."""
import hashlib
import re
from collections import defaultdict
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from .api_samples import base, today
from .schedule_period import schedule_period
from .collection_period import collection_start
from .collectors import clean, integer, urban_project


def collect_sh_inventory(source, fetcher, service):
    samples = [r for kind in ('sh_plan', 'sh_project') for r in service.rows(kind)
               if r.get('is_latest_dataset')]
    if not samples:
        raise ValueError('SH 최신 공개본 미수집: SH API 자료 수집 후 다시 실행하세요')
    groups = defaultdict(list)
    for row in samples:
        groups[(row['source_id'], row['name'], row.get('business_type', ''))].append(row)
    records = []
    for (origin, name, business), rows in sorted(groups.items()):
        row = rows[0]
        units = [r.get('units') for r in rows]
        payload = urban_project(name, row.get('municipality', ''), '서울특별시',
            sum(units) if all(u is not None for u in units) else None,
            'UNASSIGNED', row['dataset_version'], business or 'SH 분양 공급계획')
        payload.update(developer='서울주택도시공사', evidence_url=row['evidence_url'], address=row.get('address', ''),
            date_precision='DAY', source_object_id=origin+'|'+name+'|'+business,
            source_sample_ids=[r['id'] for r in rows], source_dataset=origin,
            stage_label='SH 공개본 계획 · 현재 상태 검토', warnings=list(row.get('warnings', [])),
            unit_basis='최신 공개본 계획 세대수 · 실적 아님 · 주택형만 합산, 공개본 간 합산 금지',
            mapping_basis='SH 공식 사업 목록에서 확인. 특정 공급대책 귀속은 담당자 검토 필요')
        if origin == 'sh_supply_plan':
            payload['rows'] = [dict(units=r.get('main_subscription_units'),
                supply_month=r.get('schedule_month'), supply_raw=r.get('schedule_original'), move_in_month=None,
                supply_basis='SH 본청약 예정 물량 · 사전청약 제외') for r in rows
                if r.get('main_subscription_units') not in (None, 0)]
            payload['schedule_month'] = row.get('schedule_month')
            payload['supply_units'] = None
            payload['pre_subscription_units'] = sum(r.get('pre_subscription_units') or 0 for r in rows)
            payload['main_subscription_units'] = sum(r.get('main_subscription_units') or 0 for r in rows)
        else:
            payload['source_stage'] = row.get('source_stage')
            payload['rental_units'] = row.get('rental_units')
        identifier = hashlib.sha256(payload['source_object_id'].encode()).hexdigest()
        records.append(('project', identifier, payload))
    return records, dict(complete_query=True, complete_population=False, linked_sample_rows=len(samples),
        source_versions={r['source_id']: r['dataset_version'] for r in samples},
        scope_note='수집된 SH 두 공식 데이터셋의 최신 공개본 사업만 연결. 주택형 통합, 과거 판본 미합산. 2023년 재개발 현황은 현재 상태 검토 필요')


def expanded_table(table):
    active, result = {}, []
    for tr in table.select('tbody tr'):
        cells = tr.find_all(['td','th'], recursive=False)
        if not cells:
            continue
        row, col = [], 0
        for cell in cells:
            while col in active:
                value, remaining = active[col]; row.append(value)
                if remaining == 1: del active[col]
                else: active[col] = (value, remaining-1)
                col += 1
            if cell.get('colspan', '1') != '1':
                raise ValueError('GH 공급표 열 병합 변경')
            value = clean(cell.get_text(' ', strip=True)); row.append(value)
            span = int(cell.get('rowspan', '1'))
            if span > 1: active[col] = (value, span-1)
            col += 1
        result.append(row)
    return result


def parse_gh_plan(source, html):
    soup = BeautifulSoup(html, 'html.parser'); node = soup.select_one('#cms-content')
    if not node: raise ValueError('GH 공급계획 본문 미확인')
    stamp = re.search(r'[‘’\']?(\d{2})년\s*(\d{1,2})월\s*기준', node.get_text(' ',strip=True))
    table = node.select_one('table')
    if not stamp or not table or [clean(x.get_text()) for x in table.select('thead th')][:6] != ['사업지구','분양/임대','전용면적(㎡)','공급세대','입주자모집','입주일']:
        raise ValueError('GH 공급계획 기준월·컬럼 변경')
    source_month = f'20{stamp[1]}-{int(stamp[2]):02d}'
    records, seen = [], set()
    for cells in expanded_table(table):
        if len(cells) != 7 or cells[0] in seen: raise ValueError('GH 공급계획 사업 중복·열 변경')
        seen.add(cells[0]); name, tenure, _, raw_units, supply, move_in, _ = cells
        units = re.fullmatch(r'([\d,]+)세대', raw_units)
        if not units: raise ValueError('GH 공급계획 세대수 형식 변경')
        municipality = '남양주시' if name.startswith('다산') else '광주시' if name.startswith('광주') else ''
        payload = urban_project(name, municipality, '경기도', integer(units[1]), 'UNASSIGNED', source_month+'-01', 'GH '+tenure)
        payload.update(developer='경기주택도시공사', tenure=tenure, date_precision='MONTH',
            evidence_url=source['url'], stage_label='GH 공급계획 · 실적 미확인', warnings=['AGENCY_PLAN_NOT_ACTUAL'],
            source_supply_label=supply, source_move_in_label=move_in, schedule_basis='GH 공식 공급계획 예정 일정',
            mapping_basis='GH 공급계획에서 확인한 사업. 개별 공급대책 귀속 담당자 검토 필요', rows=[])
        supply_period=schedule_period(supply);move_period=schedule_period(move_in)
        if supply_period or move_period:
            payload['rows']=[dict(units=payload['planned_units'],
                supply_month=supply_period['month'] if supply_period else None,
                move_in_month=move_period['month'] if move_period else None,
                supply_raw=supply,move_in_raw=move_in,
                supply_period=supply_period,move_in_period=move_period)]
            payload['schedule_month']=supply_period['month'] if supply_period else None
        records.append(('project', name, payload))
    if not records: raise ValueError('GH 공급계획 사업 없음: 기존 데이터 유지')
    return records, dict(complete_query=True, complete_population=False, source_base_date=source_month,
        provided=len(records), fetched=len(records), scope_note='GH 공식 분양/임대 계획 표 전체. 다른 GH 사업·과거 판본 전체를 뜻하지 않음. 분기·반기·범위 일정은 마지막 달로 집계하고 원문 보존')


def parse_gh_notices(source, html):
    soup=BeautifulSoup(html,'html.parser'); node=soup.select_one('#cms-content')
    if not node: raise ValueError('GH 주택 공고 본문 미확인')
    records, numbers=[],[]
    for tr in node.select('table tbody tr'):
        anchor=tr.select_one('td.title a[href]'); number=tr.select_one('td.number'); stamp=tr.select_one('td.date')
        if not anchor or not number or not stamp: continue
        seq=integer(clean(number.get_text()))
        match=re.fullmatch(r'(\d{2})\.(\d{2})\.(\d{2})',clean(stamp.get_text()))
        qs=parse_qs(urlparse(anchor['href']).query); identifier=qs.get('articleNo',[''])[0]
        if seq is None or not match or not identifier.isdigit(): raise ValueError('GH 공고 날짜·식별자 변경')
        numbers.append(seq)
        source_date='20'+match[1]+'-'+match[2]+'-'+match[3]
        payload=base(source,'gh_notice',clean(anchor.get_text()),'경기도','',source_date)
        payload.update(source_object_id=identifier,evidence_url=urljoin(source['url'],anchor['href']),
            source_date_label='GH 홈페이지 공고 등록일',units=None,warnings=['NOTICE_NOT_DELIVERY_ACTUAL'],
            unit_basis='공고 목록. 물량·정책 귀속은 원문 별도 검증',notice_class='RESULT' if any(word in clean(anchor.get_text()) for word in ('발표','선정결과','당첨')) else 'NOTICE')
        records.append(('gh_notice',identifier,payload))
    if not numbers: raise ValueError('GH 공고 목록 행 없음: 기존 데이터 유지')
    return records,numbers


def collect_gh_notices(source,fetcher):
    records, seen, numbers=[],set(),[]
    total=None; pages=0
    while True:
        html=fetcher.get(source['url'],params={'mode':'list','articleLimit':10,'article.offset':pages*10})
        current,seqs=parse_gh_notices(source,html)
        if total is None: total=max(seqs)
        expected=list(range(total-pages*10,max(0,total-(pages+1)*10),-1))
        if seqs!=expected: raise ValueError('GH 공고 목록 페이지 누락·수집 중 순번 변경')
        for record in current:
            if record[1] in seen: raise ValueError('GH 공고 페이지 간 중복')
            seen.add(record[1]);numbers.append(record)
            if collection_start().isoformat()<=record[2]['source_date']<=today().isoformat(): records.append(record)
        pages+=1
        if len(numbers)==total: break
        if pages>=1000: raise ValueError('GH 공고 수집 페이지 상한 초과')
    return records,dict(complete_query=True,complete_population=False,provided=total,fetched=len(numbers),pages=pages,
        collected=len(records),excluded_outside_period=len(numbers)-len(records),period_start=collection_start().isoformat(),
        period_end=today().isoformat(),scope_note='GH 주택 공고 목록 전체 페이지 중 2018년 이후 등록 자료. 추가모집·당첨결과 포함, 신규 공급실적 아님. 첨부파일 물량 미추출')
