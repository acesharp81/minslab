"""Recurring official plan and notice discovery; no automatic policy quantities.

Stable source identifiers, archived originals, bounded backfill and detail retries.
Source documents remain candidates until their project and event scope are linked.
"""
import hashlib
import io
import re
import subprocess
import sys
import zipfile
from datetime import date, timedelta
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from xml.etree import ElementTree as ET

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .api_samples import today
from .collectors import clean

EUM = 'https://www.eum.go.kr/web/gs/gv/'
REGIONS = {'1100000000':'서울특별시','2800000000':'인천광역시','4100000000':'경기도'}


def hwpx_document(body):
    if len(body)>15_000_000:
        raise ValueError('HWPX 파일 크기 상한')
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        members=[i for i in z.infolist() if re.fullmatch(r'Contents/section\d+\.xml', i.filename)]
        if not members or len(members)>100 or sum(i.file_size for i in members)>40_000_000:
            raise ValueError('HWPX 본문 구조·압축 해제 크기 오류')
        paragraphs=[]; tables=[]
        for member in sorted(members,key=lambda i:int(re.search(r'\d+',i.filename)[0])):
            raw=z.read(member)
            if b'<!DOCTYPE' in raw or b'<!ENTITY' in raw:
                raise ValueError('HWPX 외부 정의 미허용')
            root=ET.fromstring(raw)
            for node in root.iter():
                if node.tag.rsplit('}',1)[-1]=='p':
                    # Nested table paragraphs are extracted separately.
                    texts=[clean(''.join(t.itertext())) for run in list(node)
                           for t in list(run) if t.tag.rsplit('}',1)[-1]=='t']
                    if any(texts):paragraphs.append(' '.join(texts))
                if node.tag.rsplit('}',1)[-1]=='tbl':
                    rows=[]
                    for tr in list(node):
                        if tr.tag.rsplit('}',1)[-1]!='tr':continue
                        rows.append([' '.join(clean(''.join(t.itertext())) for t in tc.iter()
                                              if t.tag.rsplit('}',1)[-1]=='t') for tc in list(tr)
                                     if tc.tag.rsplit('}',1)[-1]=='tc'])
                    tables.append(rows)
        text='\n'.join(paragraphs)
        if len(text.strip())<30:raise ValueError('HWPX 본문 추출 미확보')
        return text,tables


def original(fetcher, body):
    return dict(original_file='raw/'+fetcher.manifest[-1]['file'],
                original_sha256=hashlib.sha256(body).hexdigest())


def collect_lh_department_plans(source, fetcher):
    body=fetcher.get(source['url']);soup=BeautifulSoup(body,'html.parser');links={}
    for a in soup.select('a[href*="boardDownload.es"]'):
        title=clean(a.get('title') or a.get_text(' ',strip=True))
        year=re.search(r'(20\d{2})년\s*업무계획',title)
        if not year:continue
        url=urljoin(source['url'],a['href']);q=parse_qs(urlsplit(url).query)
        if urlsplit(url).hostname!='www.lh.or.kr' or q.get('list_no')!=['654637'] or not q.get('seq',[''])[0].isdigit():
            raise ValueError('LH 부서별 계획 첨부 식별자 변경')
        if int(year[1])>today().year:continue
        if int(year[1])<2025:continue
        # Title/year is part of identity: source attachment sequence may be reused.
        links[(int(year[1]),q['seq'][0],title)]=url
    if not links:raise ValueError('LH 부서별 연간 업무계획 첨부 미발견')
    records=[]
    for (year,seq,title),url in sorted(links.items()):
        body=fetcher.get(url,'hwpx');text,tables=hwpx_document(body)
        if str(year) not in text:raise ValueError('LH 계획 파일명·본문 연도 불일치')
        key=f'654637:{seq}:{year}:'+hashlib.sha256(title.encode()).hexdigest()[:12]
        records.append(('document_evidence',key,dict(name=title,source_object_id=key,
            sample_kind='document_evidence',document_role='DEPARTMENT_ANNUAL_PLAN',plan_year=year,
            region=None,source_scope='원문 전체; 수도권·전국 및 장단기 항목별 범위 별도 확인',
            evidence_url=url,listing_url=source['url'],content_text=text,tables=tables,
            planned_units=None,units=None,source_date=None,date_precision='YEAR',base_date=f'{year}-01-01',
            source_date_label='계획 대상연도; 1월 1일을 발표일·사건일로 사용하지 않음',
            facts=[],matched_project_ids=[],policy_candidate_only=True,proposed_policy='UNASSIGNED',
            verification_status='SOURCE_CONTENT_CHECKED',
            unit_basis='부서별 계획 원문·표. 권역·기간·사업명 대조 전 합계/실적 생성 없음',**original(fetcher,body))))
    return records,dict(provided=len(links),fetched=len(records),complete_query=True,complete_population=False,
        years=sorted({r[2]['plan_year'] for r in records}),actual_events_created=0,
        scope_note='LH 부서별 공개 2025년 이후 업무계획 첨부 전체 재확인. 파일별 원문·표·내용 해시 보존, 정책 호수 자동 가산 없음')


def eum_list(body, region_code):
    soup=BeautifulSoup(body,'html.parser')
    selected=soup.select_one('select[name="select2"] option[selected]')
    if not selected or selected.get('value')!=region_code:
        raise ValueError('토지이음 요청 지역 필터 미반영')
    records=[]
    for a in soup.select('a[href*="gvGosiDet.jsp?"]'):
        tr=a.find_parent('tr');cells=tr.find_all('td',recursive=False) if tr else []
        if len(cells)<4:raise ValueError('토지이음 고시 목록 열 변경')
        seq=parse_qs(urlsplit(a['href']).query).get('seq',[''])[0]
        if not seq.isdigit():raise ValueError('토지이음 고시 seq 미확보')
        stamp=clean(cells[0].get_text());date.fromisoformat(stamp)
        title=clean(a.get('title') or a.get_text(' ',strip=True))
        records.append(dict(source_object_id=seq,name=title,region=REGIONS[region_code],
            notice_date=stamp,source_date=stamp,base_date=stamp,date_precision='DAY',
            notice_no=clean(cells[1].get_text(' ',strip=True)),agency=clean(cells[3].get_text(' ',strip=True)),
            evidence_url=EUM+'gvGosiDet.jsp?'+urlencode(dict(seq=seq)),
            housing_candidate=any(w in title for w in ('주택','택지','정비구역','정비계획','도심공공','도시개발구역')),
            notice_action='CANCEL' if '취소' in title else 'AMENDMENT' if any(w in title for w in ('변경','정정')) else 'ORIGINAL'))
    if not records and not any(w in soup.get_text() for w in ('없습니다','없음','0건')):
        raise ValueError('토지이음 고시 목록 구조·응답 확인 필요')
    if len({r['source_object_id'] for r in records})!=len(records):raise ValueError('토지이음 페이지 내 고시 중복')
    return records


def eum_detail(body, row):
    soup=BeautifulSoup(body.replace(b'\0',b''),'html.parser')
    text=soup.get_text(' ',strip=True)
    if row['notice_no'] not in text or row['notice_date'] not in text:
        raise ValueError('고시 목록·상세 번호/일자 불일치')
    attachments=[]
    for a in soup.select('a[href]'):
        m=re.search(r"download\('(/web/FileDownload.do)',\s*'([^']+)'\)",a['href'])
        if m:
            attachments.append(dict(name=clean(a.get_text(' ',strip=True)),
                url='https://www.eum.go.kr'+m[1],path=m[2]))
    return dict(row,content_text=text,attachments=attachments,
        sample_kind='document_evidence',document_role='LEGAL_NOTICE_CANDIDATE',
        facts=[],matched_project_ids=[],planned_units=None,units=None,
        policy_candidate_only=True,proposed_policy='UNASSIGNED',
        verification_status='SOURCE_CONTENT_CHECKED',
        unit_basis='고시 원문 및 변경/취소 표지. 주택사업 승인·지구계획·도로공사 범위 대조 전 실적 생성 없음')


def pdf_text_bounded(body):
    # Complex official map PDFs must not monopolize the collection worker.
    # Isolate parser memory/CPU; the downloaded original survives any failure.
    code = """import io,sys,resource
resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU,(15,15))
from pypdf import PdfReader
pdf=PdfReader(io.BytesIO(sys.stdin.buffer.read()))
if len(pdf.pages)>300:raise ValueError('page limit')
parts=[];size=0
for page in pdf.pages:
 text=page.extract_text() or '';size+=len(text)
 if size>2000000:raise ValueError('text size limit')
 parts.append(text)
sys.stdout.write('\\n'.join(parts))
"""
    result=subprocess.run([sys.executable,'-c',code],input=body,capture_output=True,timeout=20)
    if result.returncode:raise ValueError('PDF extraction resource/format limit')
    return result.stdout.decode('utf-8')


def eum_attachments(payload, fetcher):
    """The legacy EUM download servlet expects a CP949 query, not UTF-8."""
    for item in payload['attachments']:
        url=item['url']+'?'+urlencode({'file':item['path']},encoding='cp949')
        suffix=item['path'].rsplit('.',1)[-1].lower()
        if suffix not in {'pdf','hwpx','hwp','png','jpg','jpeg','gif','tif','tiff','zip'}:suffix='bin'
        try:
            body=fetcher.get(url,suffix)
            is_image=body.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'GIF87a',b'GIF89a',b'II*\x00',b'MM\x00*'))
            if not (is_image or body.startswith(b'%PDF') or body.startswith(b'PK') or body.startswith(b'\xd0\xcf\x11\xe0')):
                raise ValueError('고시 첨부 다운로드 대신 오류 응답')
            item.pop('error',None)
            item.update(original(fetcher,body),download_url=url,status='ARCHIVED')
            if is_image:item['status']='IMAGE_ARCHIVED'
            elif body.startswith(b'%PDF'):
                item['text']=pdf_text_bounded(body)
                item['status']='TEXT_EXTRACTED' if item['text'].strip() else 'OCR_REQUIRED'
            elif body.startswith(b'PK'):
                item['text'],item['tables']=hwpx_document(body);item['status']='TEXT_EXTRACTED'
            else:item['status']='LEGACY_HWP_ARCHIVED'
        except Exception as exc:
            item.update(status='ARCHIVED_TEXT_PENDING' if item.get('original_file') else 'DOWNLOAD_FAILED',error=type(exc).__name__)
    payload['attachment_complete']=all(a['status'] in ('TEXT_EXTRACTED','LEGACY_HWP_ARCHIVED','OCR_REQUIRED','ARCHIVED_TEXT_PENDING','IMAGE_ARCHIVED') for a in payload['attachments'])
    payload['text_extraction_complete']=all(a['status']=='TEXT_EXTRACTED' for a in payload['attachments'])
    return payload


def select_eum_details(pending, checked, limit=15):
    """Reserve one third for recent notices while draining the old backlog."""
    recent=sorted(pending,key=lambda r:(r['notice_date'],r['source_object_id']),reverse=True)
    oldest=sorted(pending,key=lambda r:(checked.get(r['source_object_id'],''),r['notice_date'],r['source_object_id']))
    selected=recent[:max(1,limit//3)]
    seen={r['source_object_id'] for r in selected}
    for row in oldest:
        if len(selected)>=limit:break
        if row['source_object_id'] not in seen:
            selected.append(row);seen.add(row['source_object_id'])
    return selected


def collect_eum(source, fetcher, service):
    import os
    old=service.latest_collection_stats(source['id'])
    # Whole-province UI uses the two-digit prefix; a ten-digit code restricts notices.
    checkpoints=old.get('region_checkpoints',{}) if old.get('scope_version')==2 else {}
    records={};new_checkpoints={};period_start='2025-09-07';end=today().isoformat()
    for code,region in REGIONS.items():
        checkpoint=checkpoints.get(code,{})
        cursor=max(2,int(checkpoint.get('next_page',2)))
        complete=bool(checkpoint.get('complete_window'))
        revisit=max(2,int(checkpoint.get('revisit_page',2)))
        page_count=max(2,min(20,int(os.environ.get('POC10_EUM_BACKFILL_PAGES','2'))))
        pages=sorted({1,2,*range(revisit if complete else max(2,cursor-1), (revisit if complete else cursor)+page_count)})
        exhausted=False
        for page in pages:
            body=fetcher.get(EUM+'gvGosiList.jsp',params=dict(select2=code,selSggCd=code[:2],
                startdt=period_start,enddt=end,pageNo=page,listSize=50))
            current=eum_list(body,code)
            for row in current:
                if not period_start<=row['notice_date']<=end:raise ValueError('토지이음 날짜 필터 미반영')
                seq=row['source_object_id']
                # Multi-region notices share the same source identity.
                previous=records.get(seq)
                row['regions']=sorted(set((previous or {}).get('regions',[])+[region]))
                records[seq]=row
            if len(current)<50:
                exhausted=True;break
        new_checkpoints[code]=dict(next_page=cursor if complete else max(pages)+1,
            complete_window=complete or exhausted,revisit_page=2 if exhausted else revisit+page_count if complete else 2)
    # Save discovered source records even if no managed project matches.
    output=[('notice_catalogue',seq,dict(row,sample_kind='notice_catalogue',facts=[],planned_units=None,
             policy_candidate_only=True)) for seq,row in records.items()]
    known={r['source_object_id']:r for r in service.rows('notice_catalogue') if r['source_id']==source['id']}
    for seq,row in records.items():
        row['regions']=sorted(set(row.get('regions',[])+known.get(seq,{}).get('regions',[])))
    known.update(records)
    checked=dict(old.get('detail_checked',{}));failures=[]
    retry_after=dict(old.get('detail_retry_after',{}))
    pending=[r for seq,r in known.items() if r.get('housing_candidate') and
             (seq not in checked or checked[seq] <= (today()-timedelta(days=7)).isoformat())]
    # Oldest-first alone delayed newly published amendments behind the backlog.
    # Broken remote attachments remain pending, but cannot monopolize the next
    # batch. Retry them the following day while draining never-fetched notices.
    eligible=[r for r in pending if retry_after.get(r['source_object_id'],'')<=end]
    detail_limit=max(1,min(100,int(os.environ.get('POC10_EUM_DETAILS_PER_BATCH','15'))))
    selected=select_eum_details(eligible,checked,limit=detail_limit)
    def acquire(row):
        from .collectors import Fetcher
        # Each concurrent document owns its raw manifest. Sharing a Fetcher
        # would associate one attachment with another request's last file.
        local=Fetcher(source['id'],fetcher.raw_dir) if detail_workers>1 else fetcher
        if detail_workers>1:local.scheduled_bulk=getattr(fetcher,'scheduled_bulk',False)
        try:
            body=local.get(row['evidence_url']);p=eum_detail(body,row);p.update(original(local,body))
            eum_attachments(p,local)
            return row,p,None,list(local.manifest) if detail_workers>1 else []
        except Exception as exc:
            return row,None,type(exc).__name__,list(local.manifest) if detail_workers>1 else []
        finally:
            if detail_workers>1:local.close()
    detail_workers=max(1,min(2,int(os.environ.get('POC10_EUM_DETAIL_WORKERS','1'))))
    if detail_workers>1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=detail_workers) as pool:acquired=list(pool.map(acquire,selected))
    else:acquired=[acquire(row) for row in selected]
    for row,p,error,manifest in acquired:
        fetcher.manifest.extend(manifest)
        if p is not None:
            output.append(('document_evidence',row['source_object_id'],p))
            if p['attachment_complete']:
                checked[row['source_object_id']]=end;retry_after.pop(row['source_object_id'],None)
            else:
                failures.append(dict(seq=row['source_object_id'],error='ATTACHMENT_PENDING'))
                retry_after[row['source_object_id']]=(today()+timedelta(days=1)).isoformat()
        else:
            failures.append(dict(seq=row['source_object_id'],error=error))
            retry_after[row['source_object_id']]=(today()+timedelta(days=1)).isoformat()
    from .attachment_text import recover_batch
    recovery=recover_batch(service,output)
    remaining=max(0,len(pending)-len(selected))+len(failures)
    backfill_pending=not all(c['complete_window'] for c in new_checkpoints.values()) or remaining>0 or recovery.get('text_recovery_remaining',0)>0
    return output,dict(incremental=True,complete_population=False,
        complete_query=not backfill_pending,backfill_pending=backfill_pending,
        period_start=period_start,period_end=end,scope_version=2,region_checkpoints=new_checkpoints,
        discovered=len(records),housing_candidates=sum(r.get('housing_candidate',False) for r in known.values()),
        detail_checked=checked,detail_retry_after=retry_after,details_fetched=sum(p is not None for _,p,_,_ in acquired),
        details_deferred=len(pending)-len(eligible),details_per_batch=detail_limit,detail_workers=detail_workers,
        detail_remaining=remaining,failures=failures,
        **recovery,attachment_statistics_scope='CURRENT_BATCH_ONLY',
        attachments_text_pending=sum(a.get('status')!='TEXT_EXTRACTED' for kind,_,p in output if kind=='document_evidence' for a in p.get('attachments',[])),
        actual_events_created=0,scope_note=f'수도권 3개 지역 2025-09-07 이후 고시 목록: 최신 2페이지+과거 이어받기/재방문. 주택 관련 상세 최대 {detail_limit}건씩 및 첨부 다운로드·PDF/HWPX 추출. 실패 첨부는 다음날 재시도하며 미완료로 유지. 보관 첨부 배치당 4개 HWP/OCR 복구. OCR은 별도 검토 상태이며 사업별 물량 자동 생성 없음')
