"""Discovery → source capture → advisory analysis. No approval/actuals writes."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from urllib.parse import urlencode, urlsplit, parse_qs
from xml.etree import ElementTree as ET
from sqlalchemy import select, Text
from .db import Revision, Audit, upsert_revision, now
from .sources import SOURCES
from .source_authority import authority
from .publication_reviews import source_ids
from .ai_collection_store import Store, BudgetExceeded
from .ai_collection_fetch import Fetcher, canonical, text_content
from .ai_collection_models import evaluate

SOURCE='ai_publication'
KIND='ai_publication_analysis'
RULE_VERSION='ai-collection-1'


def register(service, row, rid):
    url=canonical(row['evidence_url'])
    with service.sessions.begin() as db:
        # Shared review identity for URLs already discovered by a deterministic collector.
        base=url.split('?',1)[0]
        docs=db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.superseded_at.is_(None),
                                             Revision.payload.cast(Text).contains(base,autoescape=True)))
        for doc in docs:
            try: same=canonical(doc.payload.get('evidence_url',''))==url
            except ValueError: same=False
            if same: return doc.entity_id, False
        payload=dict(name=str(row.get('name') or url)[:500],evidence_url=url,source_date=row.get('source_date'),
                     document_role='PUBLICATION_DISCOVERY',authority=authority(url),facts=[],units=None,planned_units=None,
                     matched_project_ids=[],status='REVIEW',policy_candidate_only=True,proposed_policy='UNASSIGNED',
                     verification_status='DISCOVERED_REVIEW_REQUIRED',
                     content_scope='자동 탐색 후보 · 원문·사업 범위 담당자 승인 전',
                     unit_basis='자동 등록은 사업 연결·실적 확정 아님')
        doc,outcome=upsert_revision(db,'document_evidence',SOURCE,url,payload,rid)
        if outcome!='unchanged': db.add(Audit(entity_id=doc.entity_id,action='AI_PUBLICATION_DISCOVERY',before={},after=dict(run_id=rid,url=url)))
        return doc.entity_id, outcome=='new'


def search_rows(raw):
    if len(raw)>3_000_000 or b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('검색 피드 검증 실패')
    root=ET.fromstring(raw)
    if root.tag!='rss': raise ValueError('검색 피드 구조 변경')
    rows=[]
    for item in root.findall('./channel/item')[:20]:
        url=item.findtext('link') or ''
        p=urlsplit(url)
        if p.hostname and (p.hostname=='bing.com' or p.hostname.endswith('.bing.com')):
            url=(parse_qs(p.query).get('url') or [''])[0]
        try:
            url=canonical(url)
            published=parsedate_to_datetime(item.findtext('pubDate') or '')
            if not published.tzinfo: published=published.replace(tzinfo=timezone.utc)
            if not datetime.now(timezone.utc)-timedelta(days=30)<=published<=datetime.now(timezone.utc)+timedelta(days=1): continue
        except (ValueError,TypeError,OverflowError): continue
        rows.append(dict(name=item.findtext('title') or url,evidence_url=url,source_date=published.date().isoformat()))
    return rows


def discovery(service, store, run, fetcher):
    from .publication_watch import collect
    sources=[source for source in SOURCES if source.get('collection_mode')=='PUBLICATION_WATCH']
    total=len(sources)+(len(run['config']['queries']) if run['config']['search_enabled'] else 0)+len(run['config']['seed_urls'])
    done=0
    store.checkpoint(run['id'],stage='DISCOVERY',sources_total=total,sources_done=0,model=None)
    for source in sources:
        store.checkpoint(run['id'],current=source['name'])
        if not store.alive(run['id']): raise InterruptedError()
        try:
            rows,stats=collect(source,fetcher)
            for _,_,row in rows:
                did,created=register(service,row,run['id'])
                if created: store.event(run['id'],'DISCOVERED',document_id=did,title=row['name'])
            store.event(run['id'],'SOURCE',source=source['name'],found=len(rows))
        except Exception as error:
            store.event(run['id'],'SOURCE_ERROR',source=source['name'],error=type(error).__name__,
                        message='목록 수집 실패 · 기존 자료 보존, 원문 경로 확인 필요')
        done+=1;store.checkpoint(run['id'],sources_done=done)
    if run['config']['search_enabled']:
        for query in run['config']['queries']:
            store.checkpoint(run['id'],current='뉴스 검색: '+query)
            if not store.alive(run['id']): raise InterruptedError()
            try:
                url='https://www.bing.com/news/search?'+urlencode(dict(q=query,format='rss',setlang='ko-KR'))
                rows=search_rows(fetcher.get(url,'xml'))
                for row in rows:
                    did,created=register(service,row,run['id'])
                    if created: store.event(run['id'],'DISCOVERED',document_id=did,title=row['name'])
                store.event(run['id'],'SEARCH',query=query,found=len(rows))
            except Exception as error:
                store.event(run['id'],'SOURCE_ERROR',source='뉴스 검색: '+query,error=type(error).__name__,message='검색 피드 실패 · 검색어 또는 제공사 응답 확인 필요')
            done+=1;store.checkpoint(run['id'],sources_done=done)
    for url in run['config']['seed_urls']:
        store.checkpoint(run['id'],current=url)
        if not store.alive(run['id']): raise InterruptedError()
        did,created=register(service,dict(evidence_url=url,name=url),run['id'])
        if created: store.event(run['id'],'DISCOVERED',document_id=did,title=url)
        done+=1;store.checkpoint(run['id'],sources_done=done)


def annotations(service, document_ids):
    if not document_ids: return {}
    with service.sessions() as db:
        return {r.payload['document_id']:r.payload for r in db.scalars(select(Revision).where(
            Revision.kind==KIND,Revision.superseded_at.is_(None),Revision.payload['document_id'].as_string().in_(document_ids)))}


def candidates(service):
    with service.sessions() as db:
        docs=list(db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.source_id.in_(source_ids()),
                                                 Revision.superseded_at.is_(None))))
        reviews={r.payload['document_id']:dict(r.payload,review_revision_no=r.revision_no) for r in db.scalars(
            select(Revision).where(Revision.kind=='publication_review',Revision.superseded_at.is_(None)))}
    return [dict(id=r.entity_id,source_revision_no=r.revision_no,**r.payload,previous=reviews.get(r.entity_id)) for r in docs]


def save_analysis(service, doc, body, raw_meta, analysis, run):
    payload=dict(document_id=doc['id'],source_revision_no=doc['source_revision_no'],
                 review_revision_no=(doc.get('previous') or {}).get('review_revision_no',0),
                 body_text=body,body_sha256=hashlib.sha256(body.encode()).hexdigest(),raw=raw_meta,
                 run_id=run['id'],profile=run['config']['profile'],rule_version=RULE_VERSION,
                 model_config=[run['config'].get('selected_model'),run['config'].get('review_model')],
                 collected_at=now().isoformat(),actor='AI 자동 수집 · 담당자 미확인',**analysis)
    with service.sessions.begin() as db:
        current=db.scalar(select(Revision).where(Revision.entity_id==doc['id'],Revision.superseded_at.is_(None)).with_for_update())
        if not current or current.revision_no!=doc['source_revision_no']: raise ValueError('원문 판본 변경 · 다음 실행에서 재검토')
        previous=db.scalar(select(Revision).where(Revision.kind==KIND,Revision.superseded_at.is_(None),
                          Revision.payload['document_id'].as_string()==doc['id']))
        old=previous.payload if previous else {}
        if (old.get('body_sha256') and old['body_sha256']!=payload['body_sha256']) or (
            old.get('source_text_changed') and old.get('review_revision_no',0)==payload['review_revision_no']):
            payload['source_text_changed']=True
            warning='이전 자동 수집 본문과 변경됨 · 기존 담당자 판단 재확인 필요'
            payload['checks']=sorted(set(payload['checks']+[warning]))
        row,_=upsert_revision(db,KIND,SOURCE,doc['id'],payload,run['id'])
        db.add(Audit(entity_id=row.entity_id,action='AI_PUBLICATION_ANALYSIS',before={},
                     after=dict(run_id=run['id'],document_id=doc['id'],profile=payload['profile'],approved=False)))
    return payload


def process_run(service, store, run, fetcher=None, analyzer=evaluate, discover=discovery):
    fetcher=fetcher or Fetcher(service.data_dir)
    rid=run['id']; errors=0
    store.checkpoint(rid,stage='DISCOVERY',current='탐색 대상 확인',model=None)
    try:
        discover(service,store,run,fetcher)
        docs=candidates(service); old=annotations(service,[d['id'] for d in docs])
        # Rotate through unprocessed/stale material first; same completed work is not billed again.
        scans=store.scan_times()
        docs.sort(key=lambda d:(scans.get(d['id'],0),d.get('source_date') or '',d['id']))
        selected=docs[:run['config']['max_documents']]
        completed=skipped=failed=deferred=0
        store.checkpoint(rid,stage='FETCH',documents_total=len(selected),documents_done=0,completed_tokens=0)
        for doc in selected:
            finished=False
            store.checkpoint(rid,stage='FETCH',current=doc.get('name') or doc['evidence_url'],model=None)
            if not store.alive(rid): raise InterruptedError()
            store.scanned(doc['id'])
            try:
                raw=fetcher.get(doc['evidence_url']);title,body,truncated=text_content(raw)
                doc['name']=title or doc.get('name')
                before=old.get(doc['id'],{})
                digest=hashlib.sha256(body.encode()).hexdigest()
                same_context=(before.get('body_sha256')==digest and before.get('profile')==run['config']['profile'] and
                    before.get('source_revision_no')==doc['source_revision_no'] and before.get('rule_version')==RULE_VERSION and
                    before.get('model_config',[None,None])==[run['config'].get('selected_model'),run['config'].get('review_model')] and
                    before.get('review_revision_no')==(doc.get('previous') or {}).get('review_revision_no',0) and not before.get('failure'))
                if same_context and not before.get('escalation_pending'):
                    store.event(rid,'UNCHANGED',document_id=doc['id'],title=doc['name'])
                    skipped+=1;finished=True
                    continue
                if same_context: doc['_prior_analysis']=before
                try:
                    store.checkpoint(rid,stage='ANALYZE',current=doc['name'],model=None)
                    analysis=analyzer(store,run,doc,body,doc.get('previous'))
                except BudgetExceeded:
                    save_analysis(service,doc,body,fetcher.last,dict(result=None,passes=[],
                        checks=['비용·토큰 한도 도달 · 수집 원문 보존, AI 분석은 다음 실행에서 재시도'],
                        failure=True,approved=False,actual_units_added=0),run)
                    raise
                except InterruptedError: raise
                except Exception:
                    analysis=dict(result=None,passes=[],checks=['AI 분석 실패 · 원문 직접 검토 가능'],
                                  failure=True,approved=False,actual_units_added=0)
                    errors+=1
                if analysis.get('escalation_pending'): errors+=1;deferred+=1
                if truncated: analysis['checks'].append('본문 24,000자까지만 분석 · 전체 원문 확인 필요')
                if before.get('body_sha256') and before['body_sha256']!=digest:
                    analysis['checks'].append('이전 자동 수집 본문과 변경됨 · 기존 담당자 판단 재확인 필요')
                    analysis['source_text_changed']=True
                if not store.alive(rid,allow_finish=True): raise InterruptedError()
                store.checkpoint(rid,stage='SAVE',model=None)
                saved=save_analysis(service,doc,body,fetcher.last,analysis,run)
                store.event(rid,'ANALYZED' if not saved.get('failure') else 'ANALYSIS_ERROR',document_id=doc['id'],title=doc['name'],
                            models=[p['model'] for p in saved['passes']],checks=saved['checks'])
                finished=True
                if saved.get('failure'): failed+=1
            except (BudgetExceeded,InterruptedError): raise
            except Exception as error:
                errors+=1;failed+=1;finished=True
                store.event(rid,'DOCUMENT_ERROR',document_id=doc['id'],title=doc.get('name'),error=type(error).__name__,
                            message='원문 접근·본문 추출 실패 · 검토함의 원문 링크에서 확인하세요')
            finally:
                if finished:
                    completed+=1
                    store.checkpoint(rid,documents_done=completed,documents_skipped=skipped,documents_failed=failed,
                        documents_deferred=deferred,completed_tokens=store.confirmed_tokens(rid))
        # Source failures must not be reported as a complete search.
        with store.db() as db:
            source_errors=db.execute("SELECT COUNT(*) FROM events WHERE run_id=? AND kind='SOURCE_ERROR'",(rid,)).fetchone()[0]
        store.finish(rid,'PARTIAL' if errors or source_errors else 'COMPLETED')
    except BudgetExceeded as error: store.finish(rid,'BUDGET_PAUSED',str(error))
    except InterruptedError: store.finish(rid,'CANCELLED','중지 요청 · 완료 자료와 사용량 보존')
    except Exception as error: store.finish(rid,'FAILED','실행 실패: '+type(error).__name__)
