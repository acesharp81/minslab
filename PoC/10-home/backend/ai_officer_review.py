"""Officer input retrieval and audited disposition; similarity never approves identity."""
import hashlib,re
from .publication_reviews import normalized,save
from .publication_evidence import text_quality

from .ai_officer_decisions import ACTOR,block_identity

def candidate_projects(projects,body,doc):
    text=normalized(body+' '+(doc.get('title') or ''))
    compact=lambda s:normalized(s).replace('지구','').replace('블록','')
    alias_text=compact(body+' '+(doc.get('title') or ''))
    selected=set((doc.get('decision') or {}).get('project_ids',[]));ranked=[]
    for p in projects:
        name=normalized(p.get('name',''));alias=compact(p.get('name',''));score=0
        if p['id'] in selected:score=100
        if block_identity(p,body):score=max(score,85)
        if len(name)>=5 and name in text:score=max(score,80)
        if len(alias)>=5 and alias in alias_text:score=max(score,60)
        for key in ('address','project_no','project_number','block_name','block'):
            v=normalized(p.get(key,''))
            if len(v)>=5 and re.search(r'\d',v) and v in text:score=max(score,70 if key!='block' else 30)
        if score:ranked.append((score,p))
    return [p for _,p in sorted(ranked,key=lambda x:(-x[0],x[1]['id']))][:20]

def effective_analysis(doc,analysis,supplement,source):
    from .publication_supplements import usable
    from .publication_evidence import redact
    value=dict(analysis)
    if usable(supplement,doc['source_revision_no'],analysis):
        value.update(body_text=supplement['body_text'],body_origin='MANUAL',source_revision_no=doc['source_revision_no'])
    # A stale AI body must never hide a current source body.
    if value.get('source_revision_no')!=doc['source_revision_no'] or text_quality(value.get('body_text','')) in ('MISSING','INSUFFICIENT','BOILERPLATE'):
        body=source.get('text') or source.get('full_text') or source.get('body_text') or ''
        if text_quality(body)=='TEXT_AVAILABLE_UNVERIFIED':
            value.update(body_text=redact(body),body_origin='SOURCE',source_revision_no=doc['source_revision_no'])
    value['body_sha256']=hashlib.sha256(value.get('body_text','').encode()).hexdigest()
    return value

def ai_owned(doc):
    return (doc.get('decision') or {}).get('actor','')==ACTOR

def save_hold(service,doc,reason):
    # Delegation explicitly includes revisiting prior holds and registration waits.
    # A failed/new incomplete review never silently releases an existing approval.
    if doc['status'] in ('APPROVED','EXCLUDED'):return None
    if (doc.get('decision') or {}).get('reason')==reason:return None
    saved=save(service,doc['id'],doc['source_revision_no'],doc['review_revision_no'],'HOLD',
               (doc.get('decision') or {}).get('policy_id') or 'UNASSIGNED',
               (doc.get('decision') or {}).get('project_ids',[]),(doc.get('decision') or {}).get('new_project_names',[]),ACTOR,reason,False)
    if saved.get('conflict'):raise ValueError('업무 판단 동시 변경 · 보류 저장 중단')
    doc.update(review_revision_no=saved['revision_no'],status='HOLD',decision=saved)
    return saved

def official_search(service,store,run,doc):
    """One bounded search, <=2 official candidates. Snippets never become evidence."""
    from urllib.parse import urlencode
    from .ai_collection import search_rows,register
    from .ai_collection_fetch import Fetcher
    from .source_authority import authority
    from .publication_watch import housing_title
    query=re.sub(r'[^가-힣A-Za-z0-9 -]',' ',doc.get('title') or '')[:80]+' (site:go.kr OR site:lh.or.kr OR site:i-sh.co.kr)'
    fetcher=Fetcher(service.data_dir)
    rows=search_rows(fetcher.get('https://www.bing.com/search?'+urlencode(dict(q=query,format='rss',setlang='ko-KR')),'xml'),max_age_days=None,allow_undated=True)
    found=[]
    for row in rows:
        if authority(row['evidence_url'])!='OFFICIAL' or not housing_title(row['name']):continue
        did,created=register(service,row,run['id'])
        if did==doc['id']:continue
        found.append(dict(document_id=did,created=created,url=row['evidence_url'],title=row['name'],verified=False))
        if len(found)>=2:break
    if found:
        from .publication_reviews import queue
        from .ai_officer_evidence import recover
        current={d['id']:d for d in queue(service,include_options=False)['items']}
        for item in found:
            try:
                recover(service,current[item['document_id']]);item['body_recovered']=True
            except Exception as error:item['body_recovered']=False;item['recovery_error']=type(error).__name__
    store.event(run['id'],'OFFICER_SEARCH',document_id=doc['id'],query=query,candidates=found,
                note='검색 후보 등록만 수행 · 원문·동일 사업 검증 전 연결·실적 반영 없음')
    return found
