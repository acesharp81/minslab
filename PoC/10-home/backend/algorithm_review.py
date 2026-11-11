"""Human review of algorithm proposals; scoped HTML/PDF rules require validation."""
import hashlib,json,re,time,uuid
from pathlib import Path
from urllib.parse import urlsplit
from bs4 import BeautifulSoup
import soupsieve
from sqlalchemy import select
from .db import Revision
from .ai_collection_fetch import canonical,text_content,Fetcher,MAX_BYTES
from .publication_evidence import redact,text_quality

class Conflict(ValueError):pass


def init(store):
 if getattr(store,'_algorithm_review_ready',False):return
 from .ai_agents_store import init as init_agents
 init_agents(store)
 with store.db() as c:c.executescript('''
 CREATE TABLE IF NOT EXISTS algorithm_reviews(subject TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS algorithm_review_history(id TEXT PRIMARY KEY,subject TEXT NOT NULL,created REAL NOT NULL,payload TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS algorithm_review_history_subject ON algorithm_review_history(subject,created);
 CREATE TABLE IF NOT EXISTS algorithm_validations(id TEXT PRIMARY KEY,subject TEXT NOT NULL,created REAL NOT NULL,payload TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS algorithm_validations_subject ON algorithm_validations(subject,created DESC);
 CREATE TABLE IF NOT EXISTS algorithm_rules(scope_key TEXT PRIMARY KEY,version INTEGER NOT NULL,payload TEXT NOT NULL);
 ''')
 store._algorithm_review_ready=True


def load_review(c,subject):
 row=c.execute('SELECT version,payload FROM algorithm_reviews WHERE subject=?',(subject,)).fetchone()
 return dict(json.loads(row['payload']),version=row['version']) if row else dict(version=0)


def result(c,subject):
 r=c.execute("SELECT * FROM agent_results WHERE role='algorithm' AND subject=? ORDER BY created DESC LIMIT 1",(subject,)).fetchone()
 if not r:raise ValueError('알고리즘 진단 결과가 없습니다')
 return dict(r)|json.loads(r['payload'])


def source(service,subject):
 with service.sessions() as db:
  row=db.scalar(select(Revision).where(Revision.entity_id==subject,Revision.kind=='document_evidence',Revision.superseded_at.is_(None)))
 if not row:raise ValueError('문서 원문이 없는 출처 오류입니다. 재분석 또는 일시 오류 종료를 선택하세요')
 return dict(id=row.entity_id,revision_no=row.revision_no,hash=row.payload_hash,url=canonical(row.payload['evidence_url']))


def scope_key(url,scope):
 u=canonical(url);p=urlsplit(u)
 if scope not in ('URL','PATH'):raise ValueError('적용 범위를 확인하세요')
 return u if scope=='URL' else p.scheme+'://'+p.netloc+p.path


def selector_ok(selector):
 # Restrict proposals to simple CSS; no executable code, expensive relational selectors or prose.
 if not selector or len(selector)>200 or not re.fullmatch(r'[A-Za-z0-9_#.*\[\]="\x27\s,>+~|^$-]+',selector):raise ValueError('실행 가능한 CSS 선택자를 입력하세요. 설명문·코드·복잡한 의사 선택자는 지원하지 않습니다')
 if len(selector.split(','))>5:raise ValueError('선택자는 최대 5개 대안만 허용합니다')
 try:soupsieve.compile(selector)
 except Exception:raise ValueError('CSS 선택자 문법이 올바르지 않습니다') from None
 return selector.strip()


def extract(raw,selector):
 selector_ok(selector)
 soup=BeautifulSoup(raw,'html.parser')
 for node in soup.select('script,style,noscript,nav,footer,header,form'):node.decompose()
 nodes=soup.select(selector)
 if len(nodes)!=1:raise ValueError('본문 영역이 정확히 1개여야 합니다 · 현재 '+str(len(nodes))+'개')
 body=nodes[0].get_text(' ',strip=True)
 if any('.pdf' in f.get('src','').lower() for f in nodes[0].select('iframe[src]')):
  meaningful=BeautifulSoup(str(nodes[0]),'html.parser')
  for n in meaningful.select('.file,.info,.title,h1,h2,h3,iframe'):n.decompose()
  if len(meaningful.get_text(' ',strip=True))<60:raise ValueError('선택 영역은 제목·등록일·첨부 목록뿐이고 본문은 PDF iframe에 있습니다. 실제 PDF 다운로드 링크 규칙이 필요합니다')
 if len(body)<60 or len(body)>24000:raise ValueError('추출 본문은 60~24,000자여야 합니다')
 if text_quality(body)!='TEXT_AVAILABLE_UNVERIFIED':raise ValueError('안내 메뉴·본문 부족 등 품질 검증 실패')
 return body


def raw_file(store,sha):
 if not re.fullmatch('[a-f0-9]{64}',str(sha or '')):raise ValueError('검증 원문 해시 미확보')
 path=store.path.parent.parent/'raw'/'ai_publication'/(sha+'.raw')
 if not path.is_file() or path.stat().st_size>MAX_BYTES:raise ValueError('보관된 검증 원문이 없습니다')
 raw=path.read_bytes()
 if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('검증 원문이 변경됐습니다')
 return raw


def review_map(store):
 init(store)
 with store.db() as c:return {r['subject']:dict(json.loads(r['payload']),version=r['version']) for r in c.execute('SELECT * FROM algorithm_reviews')}


def detail(service,store,subject):
 init(store)
 with store.db() as c:
  r=result(c,subject);review=load_review(c,subject)
  history=[json.loads(x[0]) for x in c.execute('SELECT payload FROM algorithm_review_history WHERE subject=? ORDER BY created DESC LIMIT 20',(subject,))]
  row=c.execute('SELECT payload FROM algorithm_validations WHERE subject=? ORDER BY created DESC LIMIT 1',(subject,)).fetchone()
  validation=json.loads(row[0]) if row else None
  rules=[dict(json.loads(x['payload']),version=x['version']) for x in c.execute('SELECT * FROM algorithm_rules')]
 proposal=r.get('result') or {}
 try:src=source(service,subject)
 except ValueError:src=None
 matching=[x for x in rules if src and scope_key(src['url'],x['scope'])==x['scope_key']]
 try:selector_ok(proposal.get('selector',''));valid=True
 except ValueError:valid=False
 return dict(subject=subject,result_id=r['id'],title=r.get('title',subject),diagnosis=proposal.get('diagnosis') or r.get('reason'),
  proposal=proposal,proposal_origin=r.get('proposal_origin','AI'),original_model_proposal=r.get('original_model_proposal'),selector_valid=valid,source=src,review=review,history=history,validation=validation,rules=matching,
  baseline='기존 본문 선택자 목록 → article → main → body 순서. 활성 승인 규칙이 있으면 해당 주소 범위에서 먼저 적용.',
  boundary='본문 CSS 또는 공식 PDF 링크 규칙을 시험·승인합니다. 날짜·물량·사업 실적은 별도로 검토합니다.')


def validate(service,store,subject,result_id,selector,scope,expected_quote,fetcher=None):
 init(store);selector=selector_ok(selector);expected_quote=expected_quote.strip()
 if len(expected_quote)<10 or len(expected_quote)>500:raise ValueError('보존할 핵심 원문 문장을 10~500자로 입력하세요')
 with store.db() as c:
  r=result(c,subject)
  if r['id']!=result_id:raise Conflict('새 알고리즘 진단이 있습니다. 다시 조회하세요')
 src=source(service,subject)
 if r.get('source_revision_no')!=src['revision_no']:raise Conflict('원문 판본 변경 · 재분석을 요청하세요')
 fetcher=fetcher or Fetcher(service.data_dir);raw=fetcher.get(src['url'])
 final=canonical(fetcher.last.get('url') or src['url'])
 if final!=src['url']:raise ValueError('원문 주소가 다른 주소로 이동했습니다. 수집 주소를 먼저 확인하세요')
 sha=hashlib.sha256(raw).hexdigest()
 # Fetcher saves the raw artifact; never render source HTML in the UI.
 try:(_,before,_),_=extract_approved(store,src['url'],raw)
 except ValueError:before=''
 rule_kind=(r.get('result') or {}).get('change_type','BODY_SELECTOR')
 if rule_kind not in ('BODY_SELECTOR','PDF_ATTACHMENT'):raise ValueError('실행 가능한 추출 규칙 제안이 아닙니다')
 capture_meta=None
 if rule_kind=='PDF_ATTACHMENT':
  from .attachment_rule import extract_attachment
  (_,after,_),capture_meta=extract_attachment(raw,src['url'],selector,fetcher)
 else:after=extract(raw,selector)
 if expected_quote not in after:raise ValueError('선택한 본문에서 보존할 핵심 문장을 찾지 못했습니다')
 checks=[dict(name='대상 원문 · 단일 본문·길이·핵심 문장',passed=True)]
 cases=[]
 if scope=='PATH':
  with service.sessions() as db:
   rows=list(db.scalars(select(Revision).where(Revision.kind=='ai_publication_analysis',Revision.superseded_at.is_(None))))
  key=scope_key(src['url'],scope)
  seen=set()
  for row in rows:
   p=row.payload;url=p.get('raw',{}).get('url');old=p.get('body_text','')
   if not p.get('document_id') or p.get('document_id') in seen or p.get('document_id')==subject or not url or p.get('checks') or p.get('failure') or (p.get('result') or {}).get('issues') or len(old)<60:continue
   try:
    if scope_key(url,'PATH')!=key:continue
    seen.add(p['document_id'])
    archive=raw_file(store,p.get('raw',{}).get('landing_page',p.get('raw',{})).get('sha256'))
    if rule_kind=='PDF_ATTACHMENT':
     (_,new,_),_=extract_attachment(archive,url,selector,fetcher)
    else:new=extract(archive,selector)
    # Preserve every character of previously successful extracted bodies, ignoring whitespace.
    passed=re.sub(r'\s','',old) in re.sub(r'\s','',new)
    cases.append(dict(document_id=p['document_id'],sha256=p['raw']['sha256'],baseline_sha256=hashlib.sha256(old.encode()).hexdigest(),passed=passed))
   except ValueError:cases.append(dict(document_id=p['document_id'],passed=False))
   if len(cases)>=5:break
  checks.append(dict(name='같은 경로의 과거 정상 자료 2건 이상 원문 보존',passed=len(cases)>=2 and all(x['passed'] for x in cases)))
 if source(service,subject)!=src:raise Conflict('시험 중 원문 판본 변경')
 vid=str(uuid.uuid4());key=scope_key(src['url'],scope)
 with store.db(True) as c:
  if result(c,subject)['id']!=result_id:raise Conflict('시험 중 새 알고리즘 진단 발생')
  old=c.execute('SELECT version FROM algorithm_rules WHERE scope_key=?',(key,)).fetchone()
  payload=dict(id=vid,subject=subject,result_id=result_id,created=time.time(),source=src,selector=selector,scope=scope,scope_key=key,
   expected_quote=expected_quote,sha256=sha,rule_kind=rule_kind,capture_metadata=capture_meta,rule_version=old[0] if old else 0,before=redact(before),after=redact(after),checks=checks,cases=cases,
   passed=all(x['passed'] for x in checks),note='텍스트 추출 시험이며 사업·실적 승인이나 사실 정확도 보증은 아닙니다.')
  c.execute('INSERT INTO algorithm_validations VALUES(?,?,?,?)',(vid,subject,payload['created'],json.dumps(payload,ensure_ascii=False)))
 return payload


def decide(service,store,subject,result_id,version,action,actor,reason,validation_id='',checked=False):
 if action not in ('APPLY','IGNORE','RETRY','DISABLE'):raise ValueError('처리 방법을 선택하세요')
 if not actor.strip() or len(reason.strip())<5:raise ValueError('담당자와 5자 이상의 판단 사유가 필요합니다')
 init(store)
 # Capture the document revision outside the SQLite write lock; no network while approving.
 src=source(service,subject) if action=='APPLY' else None
 with store.db(True) as c:
  r=result(c,subject);old=load_review(c,subject)
  if r['id']!=result_id or old['version']!=version:raise Conflict('다른 검토 또는 새 진단이 있습니다. 다시 조회하세요')
  if old.get('result_id')==result_id and old.get('action') in ('APPLY','IGNORE') and action not in ('DISABLE','RETRY'):raise Conflict('이미 처리한 진단입니다')
  review=dict(subject=subject,result_id=result_id,action=action,actor=actor.strip(),reason=reason.strip(),created=time.time(),version=version+1)
  if action=='APPLY':
   if not checked:raise ValueError('시험 전후 본문과 적용 범위를 확인하세요')
   row=c.execute('SELECT payload FROM algorithm_validations WHERE id=? AND subject=?',(validation_id,subject)).fetchone()
   v=json.loads(row[0]) if row else {}
   if not v.get('passed') or v.get('result_id')!=result_id or v.get('source')!=src or time.time()-v.get('created',0)>86400:raise Conflict('유효한 검증 결과가 없습니다. 원문 시험을 다시 실행하세요')
   raw_file(store,v['sha256']);selector_ok(v['selector'])
   if v.get('rule_kind')=='PDF_ATTACHMENT':raw_file(store,(v.get('capture_metadata') or {}).get('sha256'))
   current=c.execute('SELECT * FROM algorithm_rules WHERE scope_key=?',(v['scope_key'],)).fetchone()
   if (current['version'] if current else 0)!=v['rule_version']:raise Conflict('같은 범위의 추출 규칙이 변경됐습니다. 다시 시험하세요')
   rule=dict(scope_key=v['scope_key'],scope=v['scope'],selector=v['selector'],kind=v.get('rule_kind','BODY_SELECTOR'),enabled=True,subject=subject,validation_id=validation_id,
    actor=actor,reason=reason,created=review['created'],version=v['rule_version']+1)
   c.execute('INSERT INTO algorithm_rules VALUES(?,?,?) ON CONFLICT(scope_key) DO UPDATE SET version=excluded.version,payload=excluded.payload',(rule['scope_key'],rule['version'],json.dumps(rule,ensure_ascii=False)))
   review.update(rule=rule,previous_rule=json.loads(current['payload']) if current else None,effect='승인한 주소 범위의 다음 수집부터 추출 규칙 적용 · 기존 사업·실적 변경 없음')
  elif action=='DISABLE':
   key=(old.get('rule') or {}).get('scope_key');current=c.execute('SELECT * FROM algorithm_rules WHERE scope_key=?',(key,)).fetchone()
   rule=json.loads(current['payload']) if current else {}
   if not rule.get('enabled') or rule.get('subject')!=subject or current['version']!=(old.get('rule') or {}).get('version'):raise Conflict('현재 활성 규칙이 다른 승인으로 변경됐거나 이미 해제됐습니다')
   rule.update(enabled=False,version=current['version']+1,actor=actor,reason=reason)
   c.execute('UPDATE algorithm_rules SET version=?,payload=? WHERE scope_key=?',(rule['version'],json.dumps(rule,ensure_ascii=False),key))
   review.update(rule=rule,effect='승인 규칙 해제 · 다음 수집부터 기본 추출기로 복귀')
  elif action=='IGNORE':review['effect']='이번 진단만 일시 오류로 종료 · 추출 규칙 변경 없음 · 새 수집 실패는 다시 검토'
  else:
   if old.get('rule'):review['rule']=old['rule']
   review['effect']='다음 알고리즘 실행에 이 자료 재분석 예약 · 승인·자료 연결 변경 없음'
  c.execute('INSERT INTO algorithm_reviews VALUES(?,?,?) ON CONFLICT(subject) DO UPDATE SET version=excluded.version,payload=excluded.payload',(subject,review['version'],json.dumps(review,ensure_ascii=False)))
  c.execute('INSERT INTO algorithm_review_history VALUES(?,?,?,?)',(str(uuid.uuid4()),subject,review['created'],json.dumps(review,ensure_ascii=False)))
 return review


def extract_approved(store,url,raw,fetcher=None):
 """No model calls. HTML is local; approved PDF rules use one bounded source fetch."""
 init(store);url=canonical(url);keys=[url,scope_key(url,'PATH')]
 with store.db() as c:
  rules={r['scope_key']:json.loads(r['payload']) for r in c.execute('SELECT * FROM algorithm_rules WHERE scope_key IN (?,?)',keys)}
 rule=next((rules[k] for k in keys if k in rules and rules[k].get('enabled') and scope_key(url,rules[k]['scope'])==k),None)
 if not rule:return text_content(raw),None
 landing_metadata=dict(fetcher.last) if fetcher is not None else None
 try:
  if rule.get('kind')=='PDF_ATTACHMENT':
   if fetcher is None:raise ValueError('PDF 승인 규칙에는 원문 수집기가 필요합니다')
   from .attachment_rule import extract_attachment
   value,meta=extract_attachment(raw,url,rule['selector'],fetcher)
   return value,dict(scope_key=rule['scope_key'],version=rule['version'],kind='PDF_ATTACHMENT',applied=True,source_sha256=meta['sha256'])
  body=extract(raw,rule['selector']);soup=BeautifulSoup(raw,'html.parser');title=soup.title.get_text(' ',strip=True)[:500] if soup.title else ''
  return (title,body,False),dict(scope_key=rule['scope_key'],version=rule['version'],applied=True)
 except ValueError as error:
  if fetcher is not None and landing_metadata is not None:fetcher.last=landing_metadata
  return text_content(raw),dict(scope_key=rule['scope_key'],version=rule['version'],applied=False,reason=str(error))
