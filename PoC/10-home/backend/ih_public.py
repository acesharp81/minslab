"""iH primary website projects and housing notices, independent of stock API.

Stable native IDs, content hashes, bounded backfill and recurring head scans.
Reserve applicants, amendments, land and shops never become net new supply.
"""
import hashlib
import io
import re
import time
import zipfile
from xml.etree import ElementTree as ET
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .collectors import clean
from .api_samples import today, collection_start
from .schedule_period import schedule_period

HOST='https://www.ih.co.kr'
BOARDS={'rental':dict(bcd='notice',cate1='general',pgdiv='general'),
        'housing':dict(bcd='sale_lease',cate1='a')}
PROJECTS=HOST+'/main/business/house.jsp'
INVENTORY=HOST+'/main/lease/leaseAptList.do'


def parse_inventory(body):
    soup=BeautifulSoup(body,'html.parser');table=soup.select_one('table.list');rows=[]
    if table is None or '입주년월' not in table.get_text():raise ValueError('iH 단지 명부 구조 변경')
    for tr in table.select('tbody tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=7:raise ValueError('iH 단지 명부 열 수 변경')
        values=[clean(c.get_text(' ',strip=True)) for c in cells];a=cells[2].select_one('a[href]')
        if not a:raise ValueError('iH 단지 고유번호 미확보')
        url=official_url(a['href']);q=parse_qs(urlsplit(url).query);identity=q.get('apt_seq',[''])[0]
        if not identity.isdigit():raise ValueError('iH 단지 고유번호 형식 변경')
        amount=re.fullmatch(r'([\d,]+)(?:\([^)]*\))?',values[4])
        program=values[2] in ('기존주택 매입임대사업','기존주택 전세임대사업')
        rows.append(dict(source_object_id=identity,name=values[2],tenure=values[0],operation_status=values[1],
            address=values[3],stock_units=int(amount[1].replace(',','')) if amount else None,
            stock_units_raw=values[4],source_supply_label=values[5],source_occupancy_label=values[6],
            record_scope='PROGRAM' if program else 'COMPLEX',sample_kind='housing_inventory',
            region='인천광역시',base_date=today().isoformat(),date_precision='COLLECTION',
            evidence_url=url,policy_candidate_only=True,proposed_policy='UNASSIGNED',
            facts=[],unit_basis='운영 임대단지 재고 명부. 당해 신규 공급·계약·실입주 사건을 생성하지 않음'))
    if not rows or len({r['source_object_id'] for r in rows})!=len(rows):raise ValueError('iH 단지 명부 누락·중복')
    return rows


def collect_inventory(source,fetcher,service):
    body=fetcher.get(INVENTORY);rows=parse_inventory(body);records=[];failures=[]
    original='raw/'+fetcher.manifest[-1]['file']
    for row in rows:
        row.update(original_file=original,original_sha256=hashlib.sha256(body).hexdigest())
        try:
            detail=fetcher.get(row['evidence_url']);soup=BeautifulSoup(detail,'html.parser')
            row['detail_original_file']='raw/'+fetcher.manifest[-1]['file']
            row['detail_original_sha256']=hashlib.sha256(detail).hexdigest()
            row['detail_tables']=[t.get_text(' ',strip=True) for t in soup.select('table.data')]
            row['verification_status']='SOURCE_CONTENT_CHECKED'
        except Exception as error:failures.append(dict(id=row['source_object_id'],reason=type(error).__name__))
        records.append(('housing_inventory',row['source_object_id'],row));time.sleep(.15)
    return records,dict(provided=len(rows),fetched=len(rows),complete_query=not failures,complete_population=False,
        complexes=sum(r['record_scope']=='COMPLEX' for r in rows),programs=sum(r['record_scope']=='PROGRAM' for r in rows),
        failures=failures,scope_note='iH 공개 건설형 임대주택 명부 전체와 상세 표. 운영 재고·광역 프로그램을 구분하며 신규 착공·계약·실입주 실적과 분리.')


def notice_fingerprint(payload):
    """Ignore view counts and presentation; include every attachment identity."""
    from .independent_metrics import digest
    return digest({k:payload.get(k) for k in ('name','source_date','content_text','notice_round','attachments')})


def scan_pages(previous):
    cursor=max(1,int(previous.get('next_page',1)))
    if previous.get('complete_window'):
        revisit=max(3,int(previous.get('revisit_next_page',3)))
        return sorted(set([1,2,revisit,revisit+1])),cursor
    # Overlap one archived page so insertions do not open a page boundary gap.
    return sorted(set([1,2]+list(range(max(1,cursor-1),cursor+6)))),cursor


def hwpx_text(content):
    """Bounded public HWPX text extraction; legacy binary HWP stays explicit."""
    if len(content)>20_000_000:raise ValueError('HWPX 압축 파일 크기 상한 초과')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        members=[i for i in archive.infolist() if re.fullmatch(r'Contents/section\d+\.xml',i.filename)]
        if not members or len(members)>200 or sum(i.file_size for i in members)>30_000_000:
            raise ValueError('HWPX 본문 구조·크기 검증 실패')
        texts=[]
        for member in sorted(members,key=lambda i:int(re.search(r'\d+',i.filename)[0])):
            body=archive.read(member)
            if b'<!DOCTYPE' in body or b'<!ENTITY' in body:raise ValueError('HWPX 외부 정의 미허용')
            root=ET.fromstring(body)
            texts.extend(' '.join(n.itertext()) for n in root.iter() if n.tag.rsplit('}',1)[-1]=='p')
        return '\n'.join(clean(t) for t in texts)


def official_url(href):
    url=urljoin(HOST,href);parts=urlsplit(url)
    if parts.scheme!='https' or parts.hostname!='www.ih.co.kr':raise ValueError('iH 원천 링크 호스트 변경')
    return url


def parse_list(body,board,page):
    soup=BeautifulSoup(body,'html.parser');text=soup.get_text(' ',strip=True)
    meta=re.search(r'전체\s*([\d,]+)건\s*,?\s*현재페이지\s*(\d+)\s*/\s*(\d+)',text)
    if not meta or int(meta[2])!=page:raise ValueError('iH 목록 건수·요청 페이지 검증 실패')
    rows=[]
    for a in soup.select('.generalList p.title a[href*="bbsMsgDetail.do"]'):
        url=official_url(a['href']);query=parse_qs(urlsplit(url).query)
        if query.get('bcd')!=[BOARDS[board]['bcd']] or not query.get('msg_seq',[''])[0].isdigit():
            raise ValueError('iH 공고 게시판·고유번호 변경')
        container=a.find_parent('li');stamp=container.select_one('[title="작성일"]')
        value=clean(stamp.get_text()) if stamp else ''
        match=re.fullmatch(r'(20\d{2})[.-](\d{2})[.-](\d{2})',value)
        if not match:raise ValueError('iH 공고 게시일 미확보')
        from datetime import date
        stamp=date(*map(int,match.groups())).isoformat()
        title=clean(a.get_text(' ',strip=True));title=re.sub(r'\s+new$','',title)
        identity=query['bcd'][0]+':'+query['msg_seq'][0]
        canonical=HOST+'/main/bbs/bbsMsgDetail.do?'+urlencode(dict(bcd=query['bcd'][0],msg_seq=query['msg_seq'][0]))
        rows.append(dict(source_object_id=identity,name=title,source_date=stamp,evidence_url=canonical,board=board))
    if not rows and int(meta[1].replace(',','')):raise ValueError('iH 공고 행 미발견 · HTML 구조 확인 필요')
    if len({r['source_object_id'] for r in rows})!=len(rows):raise ValueError('iH 한 페이지 내 공고 ID 중복')
    return rows,dict(total=int(meta[1].replace(',','')),page=int(meta[2]),pages=int(meta[3]))


def notice_round(title):
    if any(w in title for w in ('예비','사전예약','사전청약')):return 'RESERVE'
    if any(w in title for w in ('정정','변경')):return 'CORRECTION'
    if any(w in title for w in ('추가','잔여','재공고','재모집','선착순')):return 'ADDITIONAL'
    return 'MAIN'


def is_housing_notice(title):
    if any(w in title for w in ('상가','택지','토지','용지','당첨','선정','추첨','배정','서류','계약대상자')):return False
    return any(w in title for w in ('입주자','모집공고','모집 공고'))


def explicit_quantities(text):
    def one(pattern):
        values={int(v.replace(',','')) for v in re.findall(pattern,text)}
        return next(iter(values)) if len(values)==1 else None
    return dict(offered_units=one(r'금회\s*공급(?:\s*세대수|\s*호수)?\s*[:：]?\s*([\d,]+)\s*(?:세대|호)'),
                complex_total_units=one(r'(?:총\s*세대수|총\s*건설호수)\s*[:：]?\s*([\d,]+)\s*(?:세대|호)'))


def parse_notice(body,row):
    soup=BeautifulSoup(body,'html.parser');root=soup.select_one('.board_view')
    if root is None or clean(row['name']).replace(' ','') not in clean(root.get_text()).replace(' ',''):
        raise ValueError('iH 상세 공고 제목 불일치')
    detail=root.select_one('.detail')
    if detail is None:raise ValueError('iH 공고 본문 미발견')
    text=detail.get_text(' ',strip=True);round_=notice_round(row['name'])
    attachments=[]
    for a in root.select('a[href*="bbsMsgFileDown.do"]'):
        name=clean(a.get_text(' ',strip=True));url=official_url(a['href']);q=parse_qs(urlsplit(url).query)
        rq=parse_qs(urlsplit(row['evidence_url']).query)
        if q.get('bcd')!=rq.get('bcd') or q.get('msg_seq')!=rq.get('msg_seq'):raise ValueError('iH 첨부 공고 ID 불일치')
        attachments.append(dict(name=name,url=url))
    return dict(row,sample_kind='document_evidence',region='인천광역시',municipality='지역 상세 확인 필요',
        base_date=today().isoformat(),date_precision='COLLECTION',planned_units=None,units=None,offered_units=None,
        notice_round=round_,verification_status='SOURCE_CONTENT_CHECKED',original_sha256=hashlib.sha256(body).hexdigest(),
        content_text=text,attachments=attachments,unit_basis='본문·첨부의 명시적인 금회 공급만 추출 · 전체 사업·예비자·추가 모집을 구분',
        warnings=['IH_NOTICE_SCOPE_REVIEW'],facts=[dict(stage='SUPPLY',kind='DOCUMENT',date=row['source_date'],notice_round=round_,
            basis='iH 공식 주택 모집 공고 게시 · 신규 모집 물량·회차는 원문 추가 검증, 계약·실입주 아님')])


def parse_project(body,url,identity):
    soup=BeautifulSoup(body,'html.parser');root=soup.select_one('#detail_con .business_result')
    title=root.select_one('.tit') if root else None
    if not title:raise ValueError('iH 건축사업 상세 구조 변경')
    fields={}
    for li in root.select('li'):
        text=li.get_text(' ',strip=True)
        if ':' in text:
            key,value=text.split(':',1);fields[re.sub(r'\s+','',key)]=clean(value)
    if not fields.get('위치'):raise ValueError('iH 사업 위치 미확보')
    # Each explicit area group is additive. A greedy parenthesis used to swallow
    # the second group in e.g. 614세대(60㎡ 이하), 135세대(60~85㎡ 이하).
    count_text=fields.get('세대수','')
    unit_pattern=r'([\d,]+)\s*세대(?:\s*\([^()]*\))?'
    counts=list(re.finditer(unit_pattern,count_text))
    remainder=re.sub(unit_pattern,'',count_text).strip(' ,·+;/\t\n')
    units=sum(int(m[1].replace(',','')) for m in counts) if counts and not remainder else None
    name=clean(title.get_text());hits=re.findall(r'([A-Z]{1,2}\d+(?:-\d+)?)\s*BL',name,re.I)
    district='인천검단' if '검단' in name else '인천검암' if '검암' in name else None
    facts=[]
    schedule=root.select_one('.schedule_tag')
    for tag in schedule.select('span.tag-blue,span.tag-red') if schedule else []:
        label=clean(tag.get_text());next_=tag.find_next_sibling('span')
        value=clean(next_.get_text()).strip(', ') if next_ else ''
        value=re.sub(r'^(\d{2})년',r'20\1년',value)
        period=schedule_period(value)
        if period and '예정' in label:
            facts.append(dict(stage='CONSTRUCTION',kind='PLAN',date=period['month'],date_precision=period['precision'],
                              original_schedule=value,milestone='COMPLETION' if '준공' in label else 'CONSTRUCTION',
                              basis='iH 사업 페이지의 '+label+' · '+value+' · 실제 사건일 아님'))
    return dict(name=name,source_object_id='land:'+identity,region='인천광역시',municipality='지역 상세 확인 필요',
        address=fields['위치'],district=district,block=hits[0] if len(set(hits))==1 else None,
        program='iH '+fields.get('사업유형','주택건설 후보'),tenure=fields.get('사업유형','유형 확인 필요'),
        planned_units=units,stage='PLANNING',stage_label='iH 원천 사업 후보 · 실제 단계 별도 검증',
        base_date=today().isoformat(),date_precision='COLLECTION',source_date=None,source_date_label='원천 갱신일 미표기',
        source_fields=fields,evidence_url=url,original_sha256=hashlib.sha256(body).hexdigest(),
        proposed_policy='UNASSIGNED',policy_candidate_only=True,developer='인천도시공사',
        warnings=['IH_PRIMARY_PROJECT_CANDIDATE','PLAN_NOT_ACTUAL'],facts=facts,
        unit_basis='공식 사업개요에 명시된 계획 세대수 · 신규 착공·준공·실입주 실적 아님')


def collect(source,fetcher,service):
    prior=service.latest_collection_stats(source['id']);checkpoints={};records=[];failures=[];provided=0
    cutoff=collection_start().isoformat();known={};unchanged=0;extractions={}
    for r in service.rows('document_evidence'):
        if r['source_id']==source['id']:known[r['source_object_id']]=r
    for board,params in BOARDS.items():
        previous=prior.get('board_checkpoints',{}).get(board,{})
        pages,cursor=scan_pages(previous);done=bool(previous.get('complete_window'))
        seen={};meta=None;fetched_pages=[];complete=done;next_page=cursor
        for page in pages:
            if meta and page>meta['pages']:complete=True;break
            url=HOST+'/main/bbs/bbsMsgList.do?'+urlencode(dict(params,pgno=page))
            body=fetcher.get(url);current,info=parse_list(body,board,page)
            if meta is None:meta=info;provided+=info['total']
            if info['total']!=meta['total']:raise ValueError('iH 수집 중 목록 건수 변경 · 다음 배치 재시도')
            fetched_pages.append(page)
            for r in current:
                seen[r['source_object_id']]=r
            if page>=cursor:next_page=page+1
            if page==info['pages'] or all(r['source_date']<cutoff for r in current):complete=True;break
            time.sleep(.15)
        for retry in prior.get('pending_notice_rows',[]):
            if retry.get('board')==board:seen.setdefault(retry['source_object_id'],retry)
        for row in seen.values():
            if not cutoff<=row['source_date']<=today().isoformat() or not is_housing_notice(row['name']):continue
            old=known.get(row['source_object_id'])
            # Revisit head notices for corrections; old backfill details are
            # already preserved and need not be downloaded on every head scan.
            try:
                body=fetcher.get(row['evidence_url']);payload=parse_notice(body,row)
                payload['original_file']='raw/'+fetcher.manifest[-1]['file']
                fingerprint=notice_fingerprint(payload);payload['content_fingerprint']=fingerprint
                same_content=old and (old.get('content_fingerprint')==fingerprint or old.get('original_sha256')==payload['original_sha256'])
                if same_content and (not payload['attachments'] or old.get('attachment_checked_at')==today().isoformat()):
                    unchanged+=1;continue
                evidence_text=payload['content_text'];downloads=[]
                for item in payload['attachments']:
                    if len(downloads)>=2:break
                    suffix=next((ext for ext in ('pdf','hwpx','hwp','xlsx') if item['name'].lower().endswith('.'+ext)),None)
                    if not suffix or '공고' not in item['name'] or any(w in item['name'] for w in ('서류','신청서','개인정보')):continue
                    content=fetcher.get(item['url'],suffix)
                    meta_file=dict(item,sha256=hashlib.sha256(content).hexdigest(),file='raw/'+fetcher.manifest[-1]['file'])
                    if suffix=='pdf' and content.startswith(b'%PDF'):
                        try:
                            reader=PdfReader(io.BytesIO(content))
                            evidence_text+='\n'+'\n'.join(p.extract_text() or '' for p in reader.pages[:12])
                            meta_file['text_extraction']='PASS'
                            meta_file['extracted_pages']=min(12,len(reader.pages))
                            meta_file['total_pages']=len(reader.pages)
                        except Exception:meta_file['text_extraction']='REVIEW'
                    elif suffix=='hwpx':
                        try:
                            evidence_text+='\n'+hwpx_text(content);meta_file['text_extraction']='PASS'
                        except (ValueError,zipfile.BadZipFile,ET.ParseError):meta_file['text_extraction']='REVIEW'
                    else:meta_file['text_extraction']='UNSUPPORTED'
                    status=meta_file['text_extraction'];extractions[status]=extractions.get(status,0)+1
                    downloads.append(meta_file);time.sleep(.15)
                payload['downloaded_attachments']=downloads
                payload['attachment_checked_at']=today().isoformat()
                amounts=explicit_quantities(evidence_text);payload.update(amounts)
                offered=amounts['offered_units'];whole=amounts['complex_total_units'];round_=payload['notice_round']
                if offered is not None and whole is not None and offered>whole:raise ValueError('iH 금회 공급이 원문 전체 물량을 초과')
                if round_=='MAIN' and offered is not None:
                    payload['planned_units']=whole
                    payload['facts'][0].update(kind='ACTUAL',units=offered,scope_units=offered,
                        scope_partial=whole is None or offered!=whole,basis='iH 본 모집공고 금회 공급 명시 · 계약·실입주와 구분')
                records.append(('document_evidence','notice:'+row['source_object_id'],payload))
                time.sleep(.15)
            except Exception as error:
                failures.append(dict(id=row['source_object_id'],stage='NOTICE_DETAIL',reason=type(error).__name__,retry_row=row))
        revisit_next=max([v for v in fetched_pages if v>2],default=2)+1
        if revisit_next>meta['pages'] or complete and not done:revisit_next=3
        checkpoints[board]=dict(next_page=next_page,complete_window=complete,total=meta['total'],pages=meta['pages'],queried_pages=fetched_pages,revisit_next_page=revisit_next)
    index=fetcher.get(PROJECTS);soup=BeautifulSoup(index,'html.parser');links={}
    for a in soup.select('a[href*="/land/landDetail.do"]'):
        url=official_url(a['href']);q=parse_qs(urlsplit(url).query)
        if q.get('landDiv')==['1120'] and q.get('land_seq',[''])[0].isdigit() and re.search(r'주택|아파트|임대|주거',a.get_text()):links[q['land_seq'][0]]=url
    if not links:raise ValueError('iH 건축사업 목록 미확보')
    for identity,url in links.items():
        try:
            body=fetcher.get(url);payload=parse_project(body,url,identity)
            payload['original_file']='raw/'+fetcher.manifest[-1]['file']
            records.append(('project','land:'+identity,payload));time.sleep(.15)
        except Exception as error:failures.append(dict(id=identity,stage='PROJECT_DETAIL',reason=type(error).__name__))
    if not records:raise ValueError('iH 공개 자료 정형화 결과 없음 · 기존 정상 자료 유지')
    return records,dict(incremental=True,complete_query=all(c['complete_window'] for c in checkpoints.values()) and not failures,
        complete_population=False,provided=provided,fetched=len(records),board_checkpoints=checkpoints,failures=failures,
        projects=sum(k=='project' for k,_,_ in records),documents=sum(k=='document_evidence' for k,_,_ in records),
        unchanged_notices=unchanged,attachment_extraction=extractions,
        pending_notice_rows=[f['retry_row'] for f in failures if f.get('retry_row')],
        period_start=cutoff,period_end=today().isoformat(),
        scope_note='iH 공식 분양·임대 모집 공고와 건축사업. 최신 2페이지 및 과거 중첩 이어받기, 완료 후 과거 2페이지 순환 재확인. 실패 상세 재시도와 본문·첨부 식별 해시 사용. 전체 정책 모집단·실제 계약·실입주 확보와 구분.')
