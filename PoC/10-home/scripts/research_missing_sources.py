"""Import durable research rounds; capture primary sources and preserve officer decisions.

Search results are candidates. This importer only adds documentary facts after
an original confirms a specific project name; dates never come from snippets.
"""
import argparse,concurrent.futures,hashlib,io,json,re
from pathlib import Path
from urllib.parse import urlparse
import httpx
from bs4 import BeautifulSoup
from pypdf import PdfReader
from sqlalchemy import select
from backend.db import Audit,Revision,upsert_revision,engine_for
from backend.service import HomeService
from backend.api_samples import today
from backend.collection_repairs import save
from scripts.repair_reviewed_project_cases import explicit_link

CASE_LABELS={'PORTAL_EXCLUDED':'공식 게시판 수집 경로 누락','IDENTITY_VARIANT':'사업명·블록·대표 지번 차이',
 'MIXED_TENURE':'전체·유형별 물량 범위 차이','PDF_DETAIL':'첨부·상세 페이지의 단계 근거',
 'SOURCE_CANDIDATE':'공식 원천 후보 · 내용 검증 필요','NO_PUBLIC_MATCH':'검색에서 검증 원문 미확인'}

def primary(url):
 h=urlparse(url).hostname or ''
 return h.endswith('.go.kr') or any(h==v or h.endswith('.'+v) for v in ('lh.or.kr','gh.or.kr','ih.co.kr','i-sh.co.kr','korea.kr','krihs.re.kr'))

def compact(text):return re.sub(r'\s+|[-－·().,\[\]]','',str(text or '')).upper()

def original_text(body):
 if body.startswith(b'%PDF'):
  reader=PdfReader(io.BytesIO(body));return '\n'.join(p.extract_text() or '' for p in reader.pages),'.pdf'
 return BeautifulSoup(body,'html.parser').get_text(' ',strip=True),'.html'

def identity_matches(project,term,text):
 tokens=[project.get('district','')+(project.get('block') or ''),term]
 normalized=compact(text)
 for token in tokens:
  n=compact(token)
  if len(n)<4 or not any(c.isdigit() for c in n):continue
  if re.search(re.escape(n)+r'(?!\d)',normalized):return True
 # A district name and a zero-padded letter/number block may be separated
 # by the formal district suffix. Keep numeric boundaries and do not join
 # arbitrary intervening text or multiple block contracts.
    
 for token in [term]:
  m=re.fullmatch(r'(.+?)\s+([A-Z]{1,3})[-－]?(0*\d+)(?:BL|블록)?',str(token).upper())
  if m:
   district=compact(m[1]);number=str(int(m[3]));pattern=re.escape(district)+r'(?:공공주택지구|택지개발지구|지구)?(?:내)?'+m[2]+r'0*'+number+r'(?!\d)'
   if re.search(pattern,normalized):return True
 # Long distinctive site names may be used as a documentary reference only.
 n=compact(term)
 if any(c.isdigit() for c in n):return False
 return len(n)>=7 and n in normalized and any(w in text for w in ('주택','재개발','재건축','복합지구'))

def documentary_facts(title,text):
 t=compact(title);result=[]
 # Do not treat district-plan approvals, public hearings or applications as a
 # housing-construction approval, and never synthesize an event date.
 if any(k in t for k in ('주택건설사업계획승인','사업시행계획인가','주택건설사업계획변경승인')):
  result.append(dict(stage='APPROVAL',kind='DOCUMENT',date=None,basis='공식 승인·고시 원문 확보 · 원문의 사건일·전체/유형별 물량은 추가 대조, 수집일을 승인일로 사용하지 않음'))
 elif any(k in t for k in ('정비계획','지구지정','도심공공주택복합','사업개요','공공재개발','사업협약')):
  result.append(dict(stage='BUSINESS',kind='DOCUMENT',date=None,basis='공식 사업·계획 원문 확보 · 후보지/예정지구/확정지구 및 최초 사업화 사건일 구분 검토'))
 if any(k in t for k in ('주택건설공사','아파트건설공사','공사추진현황')):
  result.append(dict(stage='CONSTRUCTION',kind='DOCUMENT',date=None,basis='공식 공사 관련 원문 확보 · 계약·입찰·실착공·공정률은 의미와 기준일 별도 검증'))
 return result

def official_notice_facts(body,url,term,text):
    host=urlparse(url).hostname or ''
    if host not in ('www.eum.go.kr','eum.go.kr'):return None
    soup=BeautifulSoup(body,'html.parser');flat=soup.get_text(' ',strip=True)
    title_match=re.search(r'고시정보\s+(.{2,220}?)\s+-\s*고시번호',flat)
    title=title_match[1] if title_match else ''
    stamp=re.search(r'고시일\s+(20\d{2}-\d{2}-\d{2})',flat)
    number=re.search(r'고시번호\s+([^<]{2,100}?호)\s+담당기관',flat)
    if not stamp or not number or not title:return None
    from datetime import date
    when=date.fromisoformat(stamp[1])
    if when>today():return None
    name=compact(title)
    if any(w in name for w in ('신청','취소','공람','의견청취')):return None
    if re.search(r'(?:공공)?주택건설사업계획(?:변경)?승인',name):
        return [dict(stage='APPROVAL',kind='ACTUAL',date=when.isoformat(),milestone='AMENDED_APPROVAL' if '변경' in name else 'INITIAL_APPROVAL',
            event_type='주택건설사업계획 승인 고시',basis='토지이음 공식 '+number[1]+' · 고시일 확인. 고시의 승인 사건과 최초/변경을 구분하고 과거 최초 승인일을 덮어쓰지 않음')]
    return None

def load_round(root):
 rows=[]
 for file in sorted(root.glob('research-*.json')):
  if file.name=='research-normalized.json':continue
  value=json.loads(file.read_text())
  if isinstance(value,list):rows+=value
 chosen={}
 for r in rows:
  key=r['region']+'|'+r['term']+'|'+str(r.get('iteration',1))
  if key not in chosen or len(r.get('candidates',[]))>len(chosen[key].get('candidates',[])):chosen[key]=r
 for r in chosen.values():
  for c in r.get('candidates',[]):c['primary']=primary(c['url'])
 return list(chosen.values())

def fetch_sources(root,rows,projects):
 work={}
 for row in rows:
  for candidate in [c for c in row.get('candidates',[]) if c.get('primary')][:2]:
   url=candidate['url'];host=urlparse(url).hostname or ''
   # PDFs already indexed in broad reports can be very large. Capture only
   # project-relevant lead titles; unvalidated candidates remain visible.
   if not any(identity_matches(projects[pid],row['term'],candidate.get('title','')+' '+candidate.get('excerpt','')) for pid in row['project_ids'] if pid in projects):continue
   work[url]=candidate
 directory=root/'captures';directory.mkdir(exist_ok=True)
 manifest=json.loads((directory/'manifest.json').read_text()) if (directory/'manifest.json').exists() else {}
 def fetch(pair):
  url,candidate=pair;key=hashlib.sha256(url.encode()).hexdigest()
  if url in manifest and manifest[url].get('file') and (directory/manifest[url]['file']).exists():return url,manifest[url]
  try:
   response=httpx.get(url,timeout=20,follow_redirects=True,headers={'User-Agent':'HOME-PoC/1.0 source-coverage-review'});response.raise_for_status()
   if not primary(str(response.url)):raise ValueError('공식 호스트 밖 redirect')
   body=response.content
   if not 100<=len(body)<=12000000:raise ValueError('본문 크기 검증 필요')
   text,suffix=original_text(body)
   filename=key+suffix;(directory/filename).write_bytes(body);(directory/(key+'.txt')).write_text(text)
   return url,dict(file=filename,text_file=key+'.txt',sha256=hashlib.sha256(body).hexdigest(),url=str(response.url),bytes=len(body))
  except Exception as error:return url,dict(url=url,error=type(error).__name__)
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  for url,result in pool.map(fetch,work.items()):manifest[url]=result
 (directory/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 return manifest

def apply(service,root):
 rows=load_round(root);projects={p['id']:p for p in service.rows('project')};manifest=json.load(open(root/'captures'/'manifest.json')) if (root/'captures'/'manifest.json').exists() else {}
 captured=linked=0
 for r in rows:
  candidates=[];document_ids=[]
  for c in r.get('candidates',[]):
   stored=dict(c);m=manifest.get(c['url'],{})
   stored['verification_label']='원문 후보 · 내용 미검증'
   if m.get('file'):
    body=(root/'captures'/m['file']).read_bytes();text=(root/'captures'/m['text_file']).read_text()
    matched=[pid for pid in r['project_ids'] if pid in projects and identity_matches(projects[pid],r['term'],text)]
    evidence=official_notice_facts(body,m.get('url') or c['url'],r['term'],text) or documentary_facts(c.get('title',''),text)
    if matched and evidence:
     digest=hashlib.sha256(body).hexdigest();dest=service.data_dir/'raw'/'official_document'/(digest+Path(m['file']).suffix);dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
     key='research:'+hashlib.sha256((c['url']+'|'+r['region']+'|'+r['term']).encode()).hexdigest();payload=dict(sample_kind='document_evidence',name=c.get('title') or r['term'],region=r['region'],planned_units=None,
      base_date=today().isoformat(),date_precision='COLLECTION',evidence_url=m.get('url') or c['url'],original_file=str(dest.relative_to(service.data_dir)),original_sha256=digest,
      verification_status='SOURCE_CONTENT_CHECKED',facts=evidence,matched_project_ids=matched,unit_basis='자료 위치 확인 · 사건일·물량 미추출, 기존 정책 물량 유지',matching_basis='특정 사업명·블록의 원문 명시 대조 · 문서 근거 연결 후보')
     with service.sessions.begin() as db:
      doc,outcome=upsert_revision(db,'document_evidence','official_document',key,payload,'source_research')
      if outcome!='unchanged':db.add(Audit(entity_id=doc.entity_id,action='OFFICIAL_DOCUMENT_CAPTURE',before={},after=payload))
     source=dict(payload,id=doc.entity_id,revision_no=doc.revision_no,source_id='official_document');document_ids.append(doc.entity_id);captured+=1
     for pid in matched:
      scoped=[dict(f,scope_partial=True,scope_units=None,scope_label='복수 현장 계약 중 해당 고시 사업 범위',basis=f['basis']+' · 복수블록/복합계약의 전체 호수에 확대 적용 금지') for f in evidence] if 'MULTI_SITE_CONTRACT' in projects[pid].get('warnings',[]) else evidence
      from scripts.apply_research_round import refresh_review_bridge
      linked+=refresh_review_bridge(service,projects[pid],source,scoped,payload['matching_basis'])=='added'
     stored['verification_label']='원문 사업명 확인 · 문서 근거 연결 후보'
    else:stored['verification_label']='원문 확보 · 동일 사업 또는 사건 의미 추가 검증'
   elif m.get('error'):stored['verification_label']='원문 조회 실패 · 재조회 필요'
   candidates.append(stored)
  has_primary=any(c.get('primary') for c in candidates)
  case='PDF_DETAIL' if document_ids else 'SOURCE_CANDIDATE' if has_primary else 'NO_PUBLIC_MATCH'
  if r['owner']=='GH' and any('apply.gh.or.kr' in c['url'] for c in candidates):case='PORTAL_EXCLUDED'
  payload=dict(name=r['term'],term=r['term'],query=r.get('query') or r['term'],region=r['region'],project_ids=r['project_ids'],stages=r['stages'],iteration=r.get('iteration',1),
   checked_at=r.get('searched_at') or today().isoformat(),base_date=today().isoformat(),case_code=case,case_label=CASE_LABELS[case],candidates=candidates,source_document_ids=document_ids,
   status='DOCUMENT_LINKED' if document_ids else 'SOURCE_CANDIDATE' if has_primary else 'NO_PUBLIC_MATCH',status_label='문서 근거 연결 · 세부값 검토' if document_ids else '공식 후보 원문 추가 확인' if has_primary else '이번 검색에서 검증 원문 미확인',
   result_note='검색 결과와 원문 확인 결과를 구분합니다. 확인되지 않은 날짜·물량을 실적으로 생성하지 않으며 검색 실패는 자료 부재의 증거가 아닙니다.')
  key=r['region']+':'+r['term']+':round:'+str(r.get('iteration',1))
  with service.sessions.begin() as db:upsert_revision(db,'collection_research','research_case',key,payload,'source_research')
 return dict(research_records=len(rows),document_captures=captured,links_added=linked,projects=len({pid for r in rows for pid in r['project_ids']}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--fetch',action='store_true');p.add_argument('--projects',type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args()
 if a.fetch:
  projects={r['id']:r for r in json.load(open(a.projects))};m=fetch_sources(a.root,load_round(a.root),projects);print(json.dumps(dict(originals=len(m),fetched=sum(bool(r.get('file')) for r in m.values()),failed=sum(bool(r.get('error')) for r in m.values())),ensure_ascii=False))
 if a.apply:print(json.dumps(apply(HomeService(engine_for(),'/app/data'),a.root),ensure_ascii=False))
