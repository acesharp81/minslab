"""LH public block progress: retain dated observations, never infer supplied homes."""
import json
import re
import time
from collections import Counter, defaultdict
from datetime import date
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from .api_samples import today
from .collection_period import collection_start
from .collectors import clean, date_iso, integer, GYEONGGI_CITIES
from .db import entity_id
from .supply_dashboard import block_key, SOURCE_ALIASES


def detail_data(html):
    text = html.decode('utf-8') if isinstance(html, bytes) else html
    match = re.search(r'\bvar result\s*=\s*(\{)', text)
    if not match:
        raise ValueError('LH 공사진행현황 상세 구조 변경: 기존 이력 유지')
    value = json.JSONDecoder().raw_decode(text[match.start(1):])[0]
    if not isinstance(value.get('cntCwsttDetailInfo'), dict):
        raise ValueError('LH 공정률 상세 필드 변경')
    return value


def percentage(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not re.fullmatch(r'\d+(?:\.\d+)?', str(value)):
        raise ValueError('LH 공정률 형식 변경')
    pct = float(value)
    if not 0 <= pct <= 100:
        raise ValueError('LH 공정률 범위 오류')
    return pct


def observation_date(row, allow_photo_month=False):
    """Public registration date; explicit photo month handles retrospective uploads.

    A filename month is a MONTH observation, not an invented exact report day.
    Preserve the original registration date and the filename used as evidence.
    """
    raw = str(row.get('mtiRgsDt') or '')
    if not re.fullmatch(r'20\d{6}', raw):
        raise ValueError('LH 공정률 등록일 미제공')
    registered = date.fromisoformat(f'{raw[:4]}-{raw[4:6]}-{raw[6:]}').isoformat()
    filename = clean(row.get('cmnAhflNm'))
    match = re.search(r'(?<!\d)(20\d{2})년\s*(0?[1-9]|1[0-2])월', filename)
    # Bulk historical uploads put many different observations on one registration day.
    if match and allow_photo_month:
        period = f'{match[1]}-{int(match[2]):02d}'
        if period < registered[:7]:
            return period+'-01', 'MONTH', registered, '사진 원본 파일명에 명시된 현장 기준월 · 등록일 별도'
    return registered, 'DAY', registered, 'LH 공사진행현황 공개 등록일(mtiRgsDt) · 촬영일과 다를 수 있음'


def site_meta(tr):
    region = tr.get('data-cnpnm')
    if region not in ('서울특별시', '경기도', '인천광역시'):
        return None
    district = clean(re.sub(r'\([^)]*\)', '', tr.get('data-bzdtnm') or ''))
    block = clean(tr.get('data-bnm'))
    # Public district identifiers sometimes embed the block and put "1" in the block field.
    match = re.fullmatch(r'(.+?)([A-Z]+-?\d+(?:-\d+)?)BL', district, re.I)
    if match:
        district, block = match[1], match[2]
    district = re.sub(r'[A-Z]+-?\d+$', '', district) if district.endswith(block) and re.fullmatch(r'[A-Z]+-?\d+', block) else district
    municipality = (next((city for city in GYEONGGI_CITIES if district.startswith(city)), None)
                    if region == '경기도' else region+' (구 확인 필요)')
    meta = dict(region=region, district=district.strip(), block=block,
                municipality=municipality or '시군구 확인 필요', source_id='lh_progress')
    params = {key: tr.get('data-'+attr) for key,attr in (
        ('bzdtCd','bzdtcd'),('hcBlkCd','hcblkcd'),('seBzdtNm','bzdtnm'),('cnpNm','cnpnm'),('bnm','bnm'))}
    if not all(params.values()):
        raise ValueError('LH 공정률 지구·블록 코드 미제공')
    meta.update(source_object_id=params['bzdtCd']+'|'+params['hcBlkCd'],
                name=district.strip()+' '+block, evidence_url='https://apply.lh.or.kr/lhapply/land/cwsttInfo.do?'+urlencode(dict(mi=1352,**params)))
    return meta


def collect_progress(source, fetcher, service):
    sites = {}
    total = None
    page = 1
    while True:
        params = dict(mi=1352,listCo=100,prevListCo=100,currPage=page,searchPage=page,
                      minSn=(page-1)*100,maxSn=page*100)
        soup = BeautifulSoup(fetcher.get(source['url'],params=params),'html.parser')
        form = soup.select_one('form#srchForm')
        match = re.search(r'전체\s*([\d,]+)\s*건', form.get_text(' ',strip=True) if form else '')
        if not match:
            raise ValueError('LH 공정률 전체 건수·페이지 구조 변경')
        found_total = int(match[1].replace(',',''))
        if total is None: total = found_total
        if found_total != total:
            raise ValueError('LH 공정률 수집 중 전체 건수 변경: 재수집 필요')
        rows = soup.select('tr.detailView')
        if len(rows) != min(100, total-(page-1)*100):
            raise ValueError('LH 공정률 페이지 누락: 정상 배치 유지')
        for tr in rows:
            meta = site_meta(tr)
            if not meta: continue
            if meta['source_object_id'] in sites:
                raise ValueError('LH 공정률 페이지 중복: 페이지 이동 검증 필요')
            sites[meta['source_object_id']] = meta
        if page*100 >= total: break
        page += 1
        if page > 100: raise ValueError('LH 공정률 페이지 상한 초과')
    owners = defaultdict(list)
    current = service.rows('project')
    owned={row.get('source_object_id'):row for row in current if row['source_id']=='lh_progress'}
    for row in current:
        if row['source_id'] == 'lh_progress' or 'MULTI_SITE_CONTRACT' in row.get('warnings',[]): continue
        key = block_key(dict(row,source_id=SOURCE_ALIASES.get(row['source_id'],row['source_id'])))
        if key: owners[key].append(row)
    records = []
    annual = Counter()
    linked = set()
    unknown_dates = 0
    history_blocks = 0
    empty_history_blocks = 0
    earlier_history_blocks = 0
    for identifier,meta in sites.items():
        data = detail_data(fetcher.get(meta['evidence_url']))
        info = data['cntCwsttDetailInfo']
        pct = percentage(info.get('conPrrt'))
        units = integer(info.get('hshCnt'))
        snapshots = data.get('cntCwsttDetailList',[])
        if not isinstance(snapshots,list): raise ValueError('LH 공정률 이력 목록 변경')
        candidates = owners.get(block_key(meta),[]) if block_key(meta) else []
        construction = [r for r in candidates if SOURCE_ALIASES.get(r['source_id'],r['source_id'])=='lh_construction']
        candidate = construction[0] if len(construction)==1 else candidates[0] if len(candidates)==1 else None
        project_id = candidate['id'] if candidate else owned[identifier]['id'] if identifier in owned else None
        observed = []
        registration_counts=Counter(str(row.get('mtiRgsDt') or '') for row in snapshots)
        for row in snapshots:
            if row.get('delYn')=='Y': continue
            if str(row.get('bzdtCd'))!=identifier.split('|')[0] or str(row.get('hcBlkCd'))!=identifier.split('|')[1]:
                raise ValueError('LH 공정률 상세 지구·블록 불일치')
            progress = percentage(row.get('conPrrt'))
            if progress is None: continue
            stamp,precision,registered,basis = observation_date(row,
                allow_photo_month=registration_counts[str(row.get('mtiRgsDt') or '')]>=3)
            if registered > today().isoformat() or stamp > today().isoformat(): continue
            observed.append((stamp,precision,registered,basis,row,progress))
        # Create only new active housing candidates; old completed stock is never a new policy target.
        eligible = [r for r in observed if r[0]>=collection_start().isoformat()]
        history_blocks += bool(eligible)
        empty_history_blocks += not bool(observed)
        earlier_history_blocks += bool(observed) and not bool(eligible)
        if not candidate and pct is not None and (pct<100 or identifier in owned) and units and meta['municipality']!='시군구 확인 필요' and eligible:
            project_id = entity_id('project','lh_progress',identifier)
            last = max(eligible,key=lambda r:(r[0],r[2]))
            payload = dict(meta,base_date=last[0],date_precision=last[1],progress_pct=last[5],
                progress_date=last[0],progress_date_basis=last[3],planned_units=units,supply_units=None,
                developer='LH',tenure='유형 확인 필요',stage='COMPLETED' if last[5]==100 else 'CONSTRUCTION',
                stage_label='LH 원천상 공사 완료' if last[5]==100 else 'LH 원천상 공사 진행',
                program='3기 신도시' if any(x in meta['district'] for x in ('왕숙','창릉','교산','대장')) else '공공주택 건설',
                start_plan_date=date_iso(info.get('csstDt')),completion_plan_date=date_iso(info.get('ccwDt')),
                schedule_month=(date_iso(info.get('ccwDt')) or '')[:7] or None,
                schedule_basis='LH 공개 공사기간 종료 예정 · 입주일 아님',warnings=[],
                unit_basis='LH 공사진행현황 단지 세대수 · 공급·입주 실적과 구분',availability='PUBLIC',
                policy_candidate_only=True,proposed_policy=None,mapping_basis='LH 신규 공사 발견 · 프로그램 자동 매칭 후 정책 귀속 최종 승인 필요')
            records.append(('project',identifier,payload))
        if project_id: linked.add(identifier)
        for stamp,precision,registered,basis,row,progress in eligible:
            observation_id = clean(row.get('conPgrsAdmNo'))
            if not observation_id: raise ValueError('LH 공정률 관측 식별자 미제공')
            # Current units and contract dates cannot be projected onto historic observations.
            payload = dict(meta,report_date=stamp,report_period=stamp[:7] if precision=='MONTH' else stamp,
                base_date=stamp,source_date=stamp,date_precision=precision,progress_pct=progress,
                current_project_id=project_id,planned_units=None,developer='LH',program='공공주택 건설',
                stage='COMPLETED' if progress==100 else 'CONSTRUCTION',
                stage_label='원천상 공사 완료' if progress==100 else '원천상 공사 진행',
                progress_date_basis=basis,source_registration_date=registered,
                source_filename=clean(row.get('cmnAhflNm')),construction_description=clean(row.get('conXpnDtlCts')),
                history_mode='SOURCE_REPORT',relation_status='REVIEW',warnings=['PHOTO_MONTH_BASIS'] if precision=='MONTH' else [],
                availability='PUBLIC')
            records.append(('project_report',identifier+'|'+observation_id,payload))
            annual[stamp[:4]] += 1
        if pct is not None and not observed: unknown_dates += 1
        time.sleep(.1)
    if not records: raise ValueError('LH 기간 내 실제 공정률 기록 없음')
    return records,dict(national_blocks=total,scope_blocks=len(sites),pages=page,
        linked_blocks=len(linked),history_blocks=history_blocks,empty_history_blocks=empty_history_blocks,
        earlier_history_blocks=earlier_history_blocks,observations_by_year=dict(sorted(annual.items())),
        period_start=min(r[2]['report_date'] for r in records if r[0]=='project_report'),
        period_end=max(r[2]['report_date'] for r in records if r[0]=='project_report'),
        missing_observation_date_blocks=unknown_dates,incremental=True,complete_query=True,
        provided=total,fetched=total,
        scope_note='공개 목록 전 페이지 및 서울·경기·인천 블록별 상세 이력. 공정률은 공급·입주율로 환산하지 않음; 누락 연도 보간 없음')
