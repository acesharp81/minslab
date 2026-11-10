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
    # Incomplete automation is an agent outcome, not a revocation of an earlier
    # business decision. Check stored status too: queue may project REVIEW when
    # a source changes. Successful evidence-backed YES/NO still uses apply().
    protected={'APPROVED','EXCLUDED','REGISTRATION_REQUIRED'}
    if doc['status'] in protected or (doc.get('decision') or {}).get('status') in protected:return None
    if (doc.get('decision') or {}).get('reason')==reason:return None
    saved=save(service,doc['id'],doc['source_revision_no'],doc['review_revision_no'],'HOLD',
               (doc.get('decision') or {}).get('policy_id') or 'UNASSIGNED',
               (doc.get('decision') or {}).get('project_ids',[]),(doc.get('decision') or {}).get('new_project_names',[]),ACTOR,reason,False)
    if saved.get('conflict'):raise ValueError('업무 판단 동시 변경 · 보류 저장 중단')
    doc.update(review_revision_no=saved['revision_no'],status='HOLD',decision=saved)
    return saved

def search_queries(doc):
    """Short identifying phrases; do not ask RSS to interpret a long OR expression."""
    names=(doc.get('decision') or {}).get('project_names') or []
    name=doc.get('research_project') or (names[0] if names else '')
    title=re.sub(r'\[[^]]*\]|[“”‘’"·…]', ' ',doc.get('title') or '')
    words=re.findall(r'[가-힣A-Za-z0-9-]{2,}',title)
    generic={'보도자료','안내','관련','주택공급','한국토지주택공사','LH','서울시','추진','공급','모집','공고','주택','입주자'}
    words=[w for w in words if w not in generic]
    phrase=(name+' '+doc.get('research_stage','')).strip() if name else ' '.join(words[:4])
    phrase=phrase[:70]
    return [phrase+' site:'+domain for domain in ('go.kr','lh.or.kr','i-sh.co.kr')] if phrase else []


def relevant_search_result(row,doc):
    from urllib.parse import urlsplit
    from .source_authority import authority
    if authority(row['evidence_url'])!='OFFICIAL':return False
    title=row['name'];path=urlsplit(row['evidence_url']).path.lower()
    if path in ('','/','/main','/index.jsp','/main/index.jsp','/index.html') or re.search(r'^(?:임대주택검색|전세임대포털|LH청약플러스|한국토지주택공사)$',title.strip()):return False
    if '임대주택검색 <' in title or title.startswith('전세임대포털'):return False
    name=doc.get('research_project') or ''
    if name and normalized(name).replace('지구','') in normalized(title).replace('지구',''):return True
    ignored={'보도자료','주택','공급','모집','공고','입주자','한국토지주택공사','서울시','추진','안내','관련','계획'}
    words={w for w in re.findall(r'[가-힣A-Za-z0-9-]{2,}',doc.get('title','')) if w not in ignored}
    from .publication_watch import housing_title
    return bool(words) and sum(w in title for w in words)>=1 and housing_title(title)


def publisher_fallback(fetcher,run,doc,alive):
    """Read up to two known publisher lists, once per batch, not a second web crawl."""
    from .sources import SOURCES
    from .publication_watch import collect
    text=' '.join(str(doc.get(k) or '') for k in ('title','research_project','evidence_url'))
    ids=(['sh_notice_watch','seoul_press_watch'] if re.search(r'고덕강일|SH|i-sh|서울주택',text) else
         ['seoul_press_watch','sh_notice_watch'] if re.search(r'서울|면목|모아타운|모아주택|seoul.go.kr',text) else
         ['ih_press_watch','lh_press_watch'] if re.search(r'인천|ih.co.kr',text) else
         ['lh_press_watch','molit_press_watch'])
    cache=run.setdefault('_publisher_search_cache',{});found=[];attempts=[]
    for sid in ids:
        if not alive():raise InterruptedError('중지 요청')
        cached=sid in cache
        if not cached:
            source=dict(next(s for s in SOURCES if s['id']==sid))
            source['feed_urls']=(source.get('feed_urls') or [source['url']])[:1]
            try:
                records,stats=collect(source,fetcher)
                cache[sid]=([p for _,_,p in records],dict(listed=stats['provided'],raw_sha256=fetcher.last.get('sha256')))
            except Exception as error:cache[sid]=([],dict(error_type=type(error).__name__))
        rows,stats=cache[sid];accepted=[r for r in rows if relevant_search_result(r,doc)]
        attempts.append(dict(source_id=sid,method='OFFICIAL_PUBLISHER_LIST',cached=cached,**stats,
            accepted=len(accepted),outcome='SEARCH_ERROR' if stats.get('error_type') else 'CANDIDATES' if accepted else 'NO_RELEVANT_DETAIL'))
        found.extend(accepted)
        if found:break
    return found[:2],attempts


def official_search(service,store,run,doc):
    """At most three queries/two source captures, with explicit retrieval diagnostics."""
    from urllib.parse import urlencode
    from .ai_collection import search_rows,register
    from .ai_collection_fetch import Fetcher
    fetcher=Fetcher(service.data_dir);found=[];attempts=[];seen={doc['id']};successful=0
    cache=run.setdefault('_officer_search_cache',{})
    for query in search_queries(doc):
        if not store.alive(run['id']):raise InterruptedError('중지 요청')
        stats={};cached=query in cache
        try:
            if cached:rows,stats=cache[query]
            else:
                raw=fetcher.get('https://www.bing.com/search?'+urlencode(dict(q=query,format='rss',setlang='en-US',mkt='ko-KR')),'xml')
                rows=search_rows(raw,max_age_days=None,allow_undated=True,diagnostics=stats)
                stats=dict(stats,raw_sha256=fetcher.last.get('sha256'));cache[query]=(rows,stats)
            successful+=1;accepted=0
            for row in rows:
                if not relevant_search_result(row,doc):continue
                did,created=register(service,row,run['id'])
                if did in seen:continue
                seen.add(did);accepted+=1
                found.append(dict(document_id=did,created=created,url=row['evidence_url'],title=row['name'],verified=False))
                if len(found)>=2:break
            attempts.append(dict(query=query,cached=cached,**stats,accepted=accepted,outcome='CANDIDATES' if accepted else 'NO_RELEVANT_DETAIL' if rows else 'EMPTY_RESULTS'))
        except InterruptedError:raise
        except Exception as error:
            attempts.append(dict(query=query,**stats,outcome='SEARCH_ERROR',error_type=type(error).__name__))
        if found:break
    if not found:
        rows,extra=publisher_fallback(fetcher,run,doc,lambda:store.alive(run['id']))
        attempts.extend(extra);successful+=sum(a['outcome']!='SEARCH_ERROR' for a in extra)
        for row in rows:
            did,created=register(service,row,run['id'])
            if did in seen:continue
            seen.add(did)
            found.append(dict(document_id=did,created=created,url=row['evidence_url'],title=row['name'],verified=False))
    if found:
        from .publication_reviews import queue
        from .ai_officer_evidence import recover
        current={d['id']:d for d in queue(service,include_options=False)['items']}
        for item in found:
            try:
                recover(service,current[item['document_id']]);item['body_recovered']=True
            except Exception as error:item['body_recovered']=False;item['recovery_error']=type(error).__name__
    store.event(run['id'],'OFFICER_SEARCH',document_id=doc['id'],attempts=attempts,candidates=found,
                outcome='CANDIDATES' if found else 'NO_MATCH' if successful else 'SEARCH_ERROR',
                note='상세 원문 후보 확보만 · 동일 사업 및 사실은 별도 검증')
    if attempts and not successful:raise ValueError('공식 근거 검색 실패 · 응답/날짜 해석 확인 후 재시도 필요')
    return found
