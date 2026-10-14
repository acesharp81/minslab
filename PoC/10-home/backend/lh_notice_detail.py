"""Project-scoped LH notice detail collection; counts and occupancy are separate facts."""
import hashlib
import re
from collections import Counter
from datetime import date
from urllib.parse import urlparse
from bs4 import BeautifulSoup
from .evidence_bridge import match_key
from .roadmap import month

VERSION='lh-notice-detail-v2-block-scoped'

def compact(value):
    return re.sub(r'\s+','',value or '').upper()

def title_blocks(name):
    return {a+str(int(b)) for a,b in re.findall(r'([A-Z]{1,3})[-－]?(\d+)(?:BL|블록|[^0-9]|$)',compact(name))}

def district_in(value,district):
    # 왕숙 and 왕숙2 are distinct districts; substring matching conflates their A3 blocks.
    return bool(re.search(re.escape(compact(district))+r'(?![0-9])',compact(value)))


def candidates(projects,notices):
    keys={match_key(p) for p in projects if match_key(p)}
    found=[]
    for n in notices:
        title=compact(n['name']);blocks=title_blocks(title)
        for block in sorted(blocks):
            matches=[k for k in keys if k[0]==n['region'] and district_in(title,k[1]) and k[2]==block]
            if len(matches)==1:found.append((n,matches[0]))
    return found

def supply_terms(scope):
    result=[]
    for table in scope.select('table'):
        heads=[compact(th.get_text(' ',strip=True)) for th in table.select('thead th')]
        if '전용면적(㎡)' not in heads or '평균분양가격(원)' not in heads:continue
        for tr in table.select('tbody tr'):
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)!=len(heads):continue
            row=dict(zip(heads,[c.get_text(' ',strip=True) for c in cells]))
            price=row['평균분양가격(원)'].replace(',','').strip()
            if not price.isdigit():continue
            number=lambda value:int(value.replace(',','')) if value and value.replace(',','').isdigit() else None
            result.append(dict(housing_type=row.get('주택형'),area=row['전용면적(㎡)'],
                               units=number(row.get('세대수')),offered_units=number(row.get('금회공급세대수')),
                               average_price_won=int(price),price_basis='주택형별 평균분양가격(원) · 층·동·옵션별 실제 계약가격과 다름'))
    return result


def parse_detail(body,notice,key):
    soup=BeautifulSoup(body,'html.parser');name=notice['name']
    text=soup.get_text(' ',strip=True)
    if not district_in(text,key[1]) or key[2] not in title_blocks(text):raise ValueError('상세 응답 사업명 확인 실패')
    # Select an explicitly labelled LH complex tab, never the first date/table globally.
    sections=soup.select('div[id^="wrtancSbdTab"]')
    matching=[]
    for section in sections:
        heading=section.find(['h3','h4','h5','h6'])
        label=heading.get_text(' ',strip=True) if heading else ''
        if district_in(label,key[1]) and title_blocks(label)=={key[2]}:
            matching.append(section)
    if sections and len(matching)!=1:raise ValueError('상세 단지 탭 식별 불일치 · 블록별 확인 필요')
    scope=matching[0] if matching else soup
    multi=len(sections)>1
    groups=[]
    for ul in scope.select('ul'):
        lis=[li.get_text(' ',strip=True) for li in ul.find_all('li',recursive=False)]
        units=next((re.fullmatch(r'총\s*세대수\s*:\s*([\d,]+)',x) for x in lis if re.fullmatch(r'총\s*세대수\s*:\s*([\d,]+)',x)),None)
        if not units:continue
        raw=next((x.split(':',1)[1].strip() for x in lis if re.match(r'입주예정(?:월|일)\s*:',x)),None)
        address=next((x.split(':',1)[1].strip() for x in lis if x.startswith('소재지') and ':' in x),None)
        groups.append((int(units[1].replace(',','')),raw,address))
    groups=list(dict.fromkeys(groups))
    if len(groups)!=1:raise ValueError('단일 공급정보 확인 필요: 단지별 분해 또는 첨부문서 추출 필요')
    units,raw,address=groups[0]
    stamp=None
    if raw:
        m=re.fullmatch(r'(20\d{2})[.\-/년\s]+(\d{1,2})(?:월|\s|예정|\.)*',raw)
        stamp=month(f'{m[1]}-{int(m[2]):02d}') if m else None
    # Sum the current offering column only, never all-complex household totals.
    offers=[]
    for table in scope.select('table'):
        heads=[compact(th.get_text(' ',strip=True)) for th in table.select('thead th')]
        if '금회공급세대수' not in heads:continue
        ix=heads.index('금회공급세대수');vals=[]
        for tr in table.select('tbody tr'):
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)!=len(heads):vals=[];break
            v=compact(cells[ix].get_text(' ',strip=True)).replace(',','')
            if not v.isdigit():vals=[];break
            vals.append(int(v))
        if vals:offers.append(sum(vals))
    if len(offers)>1:raise ValueError('동일 블록 금회 공급 표 중복 · 임의 합산 금지')
    offered=offers[0] if offers else None
    if offered is not None and offered>units:raise ValueError('금회 공급호수가 블록 총세대수를 초과함')
    announced=None
    for strong in soup.select('li > strong'):
        if strong.get_text(strip=True)=='공고일':
            m=re.search(r'(20\d{2})[.](\d{2})[.](\d{2})',strong.parent.get_text(' ',strip=True))
            if m:announced=date(*map(int,m.groups())).isoformat()
    original_dates=set(re.findall(r'입주자모집공고일은\s*(20\d{2})[.](\d{2})[.](\d{2})',text))
    if len(original_dates)==1:announced=date(*map(int,next(iter(original_dates)))).isoformat()
    breakdown=None
    mixed=re.finditer(r'([\d,]+)\s*세대\s*중\s*([\d,]+)\s*세대는\s*신혼희망타운\s*\(\s*공공분양\s*\).*?나머지\s*([\d,]+)\s*세대는\s*행복주택',text)
    breakdowns=set()
    for m in mixed:
        whole,sale,rent=(int(v.replace(',','')) for v in m.groups())
        if whole==units and sale+rent==whole:breakdowns.add((sale,rent))
    if len(breakdowns)>1:raise ValueError('혼합단지 유형별 물량 범위 불일치')
    if breakdowns:
        sale,rent=next(iter(breakdowns));breakdown={'공공분양':sale,'행복주택':rent}
    mixed_total=None;mixed_breakdown=None
    proof_chunks=[chunk for chunk in re.split(r'[■\n]',text) if '혼합' in chunk and district_in(chunk,key[1]) and title_blocks(chunk)=={key[2]}]
    tenure_pairs={kind:int(n.replace(',','')) for chunk in proof_chunks for kind,n in re.findall(r'(국민임대|영구임대|행복주택|공공분양|통합공공임대)(?:주택)?\s*\(\s*([\d,]+)\s*호\s*\)',chunk)}
    if len(tenure_pairs)>=2 and '혼합' in text and units in tenure_pairs.values():
        mixed_breakdown=tenure_pairs;mixed_total=sum(tenure_pairs.values())
    status='CANCELLED' if '취소' in name else 'CORRECTION' if '정정' in name else 'ORIGINAL'
    round_kind='ADDITIONAL' if any(t in name for t in ('추가','잔여','재공고')) else 'MAIN'
    facts=[]
    if announced and status!='CANCELLED':
        facts.append(dict(stage='SUPPLY',kind='ACTUAL',date=announced,milestone='NOTICE',units=offered,
            notice_round=round_kind,basis=('LH 추가·잔여 모집공고 게시 확인 · 본 모집량에 중복 합산 금지 · 금회 공급 ' if round_kind=='ADDITIONAL' else 'LH 본 모집공고 게시 확인 · 계약·입주 실적 아님 · 금회 공급 ')+(str(offered)+'호' if offered is not None else '호수 미확인')))
    if raw and status!='CANCELLED':
        facts.append(dict(stage='MOVE_IN',kind='PLAN',date=stamp,date_label=raw,milestone='MOVE_IN',
            schedule_status='DATED' if stamp else 'UNDETERMINED' if '미정' in raw else 'TEXT',
            basis='LH 모집공고 공급정보의 입주 예정월 · '+notice.get('notice_type','유형 미확인')+' '+str(units)+'호 범위 · 실제 입주 아님'))
    if breakdown:
        facts=[dict(f,scope_partial=True,scope_units=breakdown['공공분양'],
                    scope_label=f"공공분양 {breakdown['공공분양']:,}호 / 전체 {units:,}호",
                    basis=f['basis']+' · 혼합단지: 금회 공공분양 범위, 행복주택 일정 별도 확인') for f in facts]
    elif offered is not None and 0 < offered < units:
        # Additional/remaining recruitment can omit the original tenure breakdown.
        # Its notice date and move-in month never establish the whole complex scope.
        facts=[dict(f,scope_partial=True,scope_units=offered,
                    scope_label=f"금회 공급 {offered:,}호 / 전체 {units:,}호",
                    basis=f['basis']+' · 금회 공급 부분 범위; 전체 단지 일정 별도 확인') for f in facts]
    return dict(supply_terms=supply_terms(scope),scope_breakdown=breakdown,complex_scope_breakdown=mixed_breakdown,complex_total_units=mixed_total,name=(key[1]+' '+key[2]+' · '+notice.get('notice_type','')+' 모집공고' if multi else name),notice_title=name,multi_complex=multi,notice_round=round_kind,sample_kind='document_evidence',region=key[0],district=key[1],block=key[2],
        tenure=notice.get('notice_type'),planned_units=units,offered_units=offered,address=address,
        unit_basis='공급정보 총세대수 · 혼합단지 여부와 금회 공급호수를 별도 확인; 별도 합산 금지',
        move_in_month=stamp,move_in_raw=raw,source_date=notice.get('source_date'),announcement_date=announced,
        base_date=notice.get('source_date'),date_precision='DAY',notice_no=notice['notice_no'],
        notice_status=status,notice_entity_id=notice['id'],notice_revision_no=notice['revision_no'],
        parser_version=VERSION,original_sha256=hashlib.sha256(body).hexdigest(),
        evidence_url=notice['evidence_url'],facts=facts,
        verification_status='SOURCE_CONTENT_CHECKED',warnings=['PARTIAL_HOUSEHOLD_SCOPE_REVIEW'])

def collect_details(source,fetcher,service):
    notices=service.rows('lh_notice');selected=candidates(service.rows('project'),notices)
    records=[];failures=[];cache={}
    for n,key in selected:
        try:
            url=n['evidence_url'];parsed=urlparse(url)
            if parsed.scheme!='https' or parsed.hostname!='apply.lh.or.kr' or parsed.path!='/lhapply/apply/wt/wrtanc/selectWrtancInfo.do':
                raise ValueError('공식 상세 URL 확인 필요')
            if url not in cache:
                body=fetcher.get(url);cache[url]=(body,'raw/'+fetcher.manifest[-1]['file'])
            body,original_file=cache[url]
            payload=parse_detail(body,n,key)
            payload['original_file']=original_file
            record_key=n['notice_no']+':'+key[1]+':'+key[2] if payload['multi_complex'] else n['notice_no']
            records.append(('document_evidence',record_key,payload))
        except Exception as error:
            failures.append(dict(notice_id=n['id'],name=n['name'],reason=str(error) if isinstance(error,ValueError) else '상세 요청 실패 · 재수집 필요'))
    if selected and not records:raise ValueError('LH 상세 공고 전부 미확보 · 기존 정상 자료 유지')
    return records,dict(incremental=True,complete_population=False,list_records=len(notices),candidate_notices=len({n['id'] for n,k in selected}),candidate_blocks=len(selected),
        detail_acquired=len(records),failures=failures,failed_details=len(failures),
        scope_note='저장 공고 중 현재 사업의 시도·지구·블록 일치 후보. 숫자 지구 구분, 복수단지 공고는 명시된 단지 탭별 분리. 원공고·정정·추가공고 각각 보존. 제목만 연결 가능한 일부이며 전국 전수 수집 아님',
        parser_version=VERSION)
