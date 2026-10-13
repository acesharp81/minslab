"""Real GH recruitment portal: complete list, scoped detail and original schedules."""
import hashlib,io,re
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .api_samples import today

URL='https://apply.gh.or.kr/sb/sr/sr7150/selectPbancRentHouseList.do'

def compact(value):return re.sub(r'\s+','',str(value or ''))

def parse_list(body,url=URL):
    soup=BeautifulSoup(body,'html.parser');text=soup.get_text(' ',strip=True)
    total=re.search(r'총게시물\s*:\s*([\d,]+)\s*페이지\s*:\s*(\d+)\s*/\s*(\d+)',text)
    if not total:raise ValueError('GH 청약공고 목록 구조 변경')
    rows=[]
    for a in soup.select('a[data-pbancno]'):
        cells=a.find_parent('tr').find_all('td',recursive=False)
        if len(cells)<4:raise ValueError('GH 청약공고 열 변경')
        match=re.search(r'20\d{2}-\d{2}-\d{2}',a.find_parent('tr').get_text(' ',strip=True))
        stamp=match[0] if match else None
        if not stamp:raise ValueError('GH 공고 게시일 미확인')
        ident=a.get('data-pbancno');title=a.get_text(' ',strip=True)
        rows.append(dict(source_object_id=ident,name=title,source_date=stamp,
            municipality=cells[3].get_text(' ',strip=True).split()[0],housing_type=cells[1].get_text(strip=True),
            evidence_url=urljoin(url,'selectPbancDetailView.do')+'?pbancNo='+ident+'&pbancKndCd='+a.get('data-pbanckndcd','01')))
    if len({r['source_object_id'] for r in rows})!=len(rows):raise ValueError('GH 목록 중복')
    return rows,dict(total=int(total[1].replace(',','')),page=int(total[2]),pages=int(total[3]))

def pdf_schedules(body):
    if not body.startswith(b'%PDF'):raise ValueError('GH 모집공고 PDF 응답 미확인')
    reader=PdfReader(io.BytesIO(body));texts=[p.extract_text() or '' for p in reader.pages];text='\n'.join(texts)
    # The exact phrase, not an unrelated application/contract date, must name the event.
    found=[]
    for m in re.finditer(r'입주\s*(?:예정\s*(?:시기|월|일)?|시기)[^\n]{0,45}?(20\d{2})\s*[.년/-]\s*(\d{1,2})\s*(?:월|[.])',text):
        month=f'{int(m[1]):04d}-{int(m[2]):02d}'
        if 1<=int(m[2])<=12:found.append(month)
    for page in texts[:8]:
        if '입주예정' not in compact(page) or not any(w in compact(page) for w in ('금회공급','총건설호수','공급대상')):continue
        # The supply table may split its heading and values into separate PDF lines.
        quoted=re.findall(r'[‘’\'](2[0-9])\.(0?[1-9]|1[0-2])(?![\d.])',page)
        if len(set(quoted))==1:
            yy,mm=quoted[0];found.append('20'+yy+'-'+str(int(mm)).zfill(2))
    months=sorted(set(found));facts=[]
    if len(months)==1:facts.append(dict(stage='MOVE_IN',kind='PLAN',date=months[0],milestone='MOVE_IN',basis='GH 모집공고 첨부 원문의 입주 예정월 · 실제 입주 아님'))
    if not months and re.search(r'입주\s*예정[^\n]{0,25}미정',text):facts.append(dict(stage='MOVE_IN',kind='PLAN',date=None,date_label='미정',schedule_status='UNDETERMINED',basis='GH 원문 입주 예정 미정 표기'))
    return facts,dict(pdf_pages=len(reader.pages),pdf_sha256=hashlib.sha256(body).hexdigest(),schedule_candidates=months)

def parse_detail(body,row,project):
    soup=BeautifulSoup(body,'html.parser');text=soup.get_text(' ',strip=True)
    if compact(project['name']) not in compact(text):raise ValueError('GH 상세 사업명 불일치')
    units=[]
    for table in soup.select('table'):
        headers=[compact(x.get_text(' ',strip=True)) for x in table.select('th[scope=col]')]
        if '금회공급세대수' not in headers:continue
        index=headers.index('금회공급세대수');values=[]
        for tr in table.select('tbody tr'):
            cells=tr.find_all(['th','td'],recursive=False)
            if len(cells)!=len(headers):continue
            value=cells[index].get_text(strip=True).replace(',','')
            if value.isdigit():values.append(int(value))
        if values:units.append(sum(values))
    if len(units)>1:raise ValueError('GH 주택형 공급표 중복')
    offered=units[0] if units else None;whole=project.get('planned_units')
    if offered is not None and whole is not None and offered>whole:raise ValueError('GH 금회 모집 호수가 사업계획을 초과 · 범위 검증 필요')
    partial=offered is None or offered!=whole or any(w in row['name'] for w in ('추가','잔여','예비','재공고'))
    fact=dict(stage='SUPPLY',kind='ACTUAL' if offered is not None else 'DOCUMENT',date=row['source_date'],units=offered,milestone='NOTICE',scope_partial=partial,
        scope_units=offered,scope_label=(f'금회 공급 {offered}호 / 사업계획 {whole}호' if offered is not None else '금회 공급호수 미확인') if partial else f'금회 공급 {offered}호',
        basis='GH 공식 모집공고 게시 · 계약·입주 실적 아님'+(' · 추가/예비 또는 부분 모집, 본모집과 중복 합산 금지' if partial else ''))
    pdfs=[a['href'] for a in soup.select('a[href]') if 'selectFileDown.do' in a['href'] and '.pdf' in a.get_text().lower() and '공고' in a.get_text() and '참고' not in a.get_text()]
    return dict(row,sample_kind='document_evidence',region=project['region'],municipality=project.get('municipality'),
        matched_project_ids=[project['id']],planned_units=whole if offered==whole else None,offered_units=offered,
        notice_round='ADDITIONAL' if partial else 'MAIN',facts=[fact],verification_status='SOURCE_CONTENT_CHECKED',
        base_date=today().isoformat(),date_precision='COLLECTION',original_sha256=hashlib.sha256(body).hexdigest(),
        unit_basis='현재 공고 금회 공급을 주택형별 합계로 대조. 예비입주자 수와 기존 재고를 합산하지 않음',
        matching_basis='GH 동일 사업 고유명·시도·주택형 공급표 대조 · 담당자 검토',pdf_urls=pdfs)

def collect(source,fetcher,service):
    rows=[];seen=set();meta=None
    for page in range(1,101):
        current,info=parse_list(fetcher.get(URL,params={'pageIndex':page}))
        if info['page']!=page:raise ValueError('GH 페이지 매개변수 미반영')
        if meta is None:meta=info
        if info['total']!=meta['total']:raise ValueError('GH 조회 중 목록 건수 변경')
        for r in current:
            if r['source_object_id'] in seen:raise ValueError('GH 페이지 반복')
            seen.add(r['source_object_id']);rows.append(r)
        if page>=info['pages']:break
    if len(rows)!=meta['total']:raise ValueError('GH 전체 공고 수 불일치')
    records=[];failures=[];cache={};projects=[p for p in service.rows('project') if p['source_id'].startswith('gh_')]
    for r in rows:
        if r['source_date']>today().isoformat():continue
        records.append(('gh_notice','portal:'+r['source_object_id'],dict(r,sample_kind='gh_notice',region='경기도',base_date=r['source_date'],units=None,notice_class='NOTICE',unit_basis='GH 공식 공고 목록 · 상세 금회 공급과 별도',source_date_label='공식 공고 게시일')))
        matching=[p for p in projects if compact(p['name']) in compact(r['name']) and len(compact(p['name']))>=4]
        for p in matching:
            try:
                if r['evidence_url'] not in cache:
                    body=fetcher.get(r['evidence_url']);cache[r['evidence_url']]=(body,'raw/'+fetcher.manifest[-1]['file'])
                body,file=cache[r['evidence_url']];payload=parse_detail(body,r,p);payload['original_file']=file
                for url in payload.pop('pdf_urls')[:1]:
                    try:
                        pdf=fetcher.get(url,'pdf');plans,pdfmeta=pdf_schedules(pdf)
                        payload.update(pdfmeta,pdf_original_file='raw/'+fetcher.manifest[-1]['file'],pdf_url=url)
                        for f in plans:
                            if payload['notice_round']!='MAIN':f=dict(f,scope_partial=True,scope_units=payload['offered_units'],scope_label='금회 추가 모집 범위')
                            payload['facts'].append(f)
                    except Exception as error:payload['pdf_error']=type(error).__name__+': 첨부 일정 추가 확인 필요'
                records.append(('document_evidence','portal:'+r['source_object_id']+':'+p['id'],payload))
            except Exception as error:failures.append(dict(project_id=p['id'],notice_id=r['source_object_id'],reason=str(error)[:200]))
    return records,dict(complete_query=True,complete_population=False,provided=len(rows),fetched=len(rows),pages=meta['pages'],documents=sum(k=='document_evidence' for k,_,_ in records),failures=failures,scope_note='공식 GH 임대주택 공고 전체 목록 대조 · 사업 고유명 일치 상세만 저장. 신규/추가/예비 모집은 범위를 구분하며 입주 예정으로 실제 입주를 만들지 않음')

def reconcile(service):
    from scripts.repair_reviewed_project_cases import explicit_link
    projects={p['id']:p for p in service.rows('project')};out={}
    for row in service.rows('document_evidence'):
        if row['source_id']!='gh_notice':continue
        for pid in row.get('matched_project_ids',[]):
            if pid in projects:
                outcome=explicit_link(service,projects[pid],row,row['facts'],row['matching_basis']);out[outcome]=out.get(outcome,0)+1
    return out
