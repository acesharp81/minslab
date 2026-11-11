#!/usr/bin/env python3
"""Bounded real-data pilot. No fabricated input or changes to official actuals.

Run in the configured HOME environment. --inputs contains immutable archived
public documents exported read-only from HOME. Model usage uses the existing
shared budget gate; a separate run ledger prevents production queue interference.
"""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from urllib.parse import urlencode

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backend


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--document-id', required=True)
    parser.add_argument('--holdout-ids', nargs='*', default=[])
    parser.add_argument('--model', default='solar-pro4')
    parser.add_argument('--code-dir', type=Path)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--reviewed-pdf-selector', default='')
    args = parser.parse_args()
    if args.code_dir: backend.__path__.insert(0, str(args.code_dir))
    from bs4 import BeautifulSoup
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from backend.db import engine_for
    from backend.service import HomeService
    from backend.ai_collection_store import Store
    from backend.ai_collection_models import invoke
    from backend.ai_agent_catalog import validate as validate_model
    from backend.ai_agent_workflows import RuleProposal, ALGORITHM
    from backend.ai_collection_fetch import Fetcher, canonical
    from backend.publication_capture import capture
    from backend.source_authority import authority
    from backend import algorithm_review as ar, ai_agents_store as agents
    from backend.evidence_chain import (ResearchPlan, Assessment, PLAN_PROMPT, ASSESS_PROMPT,
                                        document_snapshot, validate_assessment, save_case)
    from backend.attachment_rule import extract_attachment
    from backend.ai_collection import search_rows
    import sqlite3
    validate_model('algorithm', args.model)
    validate_model('officer', args.model)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    def write(name, value):
        (args.work_dir / name).write_text(json.dumps(value, ensure_ascii=False, indent=2))
    original_ledger=sqlite3.connect('file:/app/data/runtime/ai-collection.sqlite3?mode=ro',uri=True)
    production_config=json.loads(original_ledger.execute('SELECT value FROM settings WHERE id=1').fetchone()[0]);original_ledger.close()
    class BoundedPilotStore(Store):
        def reserve(self, rid, provider, model, group, tokens, cost, config):
            with self.db() as db:
                used,count=db.execute('SELECT COALESCE(SUM(COALESCE(cost_usd,reserved_usd)),0),COUNT(*) FROM calls').fetchone()
            if count >= 5:
                raise ValueError('격리 시연 전체 모델 요청 5회 상한 도달')
            if used + cost > 0.20:
                raise ValueError('격리 시연 단가 환산 예산 US$0.20 상한 도달')
            return super().reserve(rid,provider,model,group,tokens,cost,config)
    store = BoundedPilotStore(args.work_dir)
    if store.status(include_events=False)['runs'] and not args.resume:
        raise ValueError('재실행으로 새 호출하지 않도록 비어 있는 작업 폴더를 사용하세요')
    store.enqueue(actor='사용자 요청 · 실제 자료 근거 연결 검증', overrides=dict(production_config,
                  selected_model=args.model, agent_role='algorithm', max_documents=3))
    run=store.claim(); calls=json.loads((args.work_dir/'model-responses.json').read_text()) if args.resume else []
    def ask(name, schema, instructions, body, context=None):
        if len(calls)>=5:raise ValueError('시연 모델 호출 5회 상한')
        answer,cid=invoke(store,run,args.model,dict(name=name),body,context,schema=schema,instructions=instructions,output_tokens=5000)
        calls.append(dict(task=name,call_id=cid,model=args.model,response=answer.model_dump()))
        write('model-responses.json',calls)
        return answer
    def snapshot(did):
        meta=json.loads((args.inputs/(did+'.json')).read_text()); raw=(args.inputs/(did+'.raw')).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=meta['raw_sha256']:raise ValueError('실제 원문 해시 불일치')
        if raw.startswith(b'%PDF'):raise ValueError('규칙 시험에는 PDF 파일 대신 보존된 landing_page HTML이 필요합니다')
        return meta,raw
    target,raw=snapshot(args.document_id); project=json.loads((args.inputs/'project.json').read_text())
    name=project['payload']['name']
    public_project={k:project['payload'].get(k) for k in ('name','region','municipality','district','block','address','planned_units')}
    engine=engine_for(); service=HomeService(engine,data_dir=args.work_dir)
    @contextmanager
    def readonly_sessions():
        with Session(engine) as db:
            db.execute(text('SET TRANSACTION READ ONLY'));db.execute(text("SET LOCAL statement_timeout='15s'"))
            yield db
    service.sessions=readonly_sessions
    case=dict(project_id=project['id'],project_name=name,run_id=run['id'],execution_mode='ISOLATED_REAL_DATA',
              production_business_writes=0,production_rule_activations=0,model_calls=calls)
    try:
        soup=BeautifulSoup(raw,'html.parser')
        context=dict(stored_body=target['text'],original_html_sha256=target['raw_sha256'],
                     nodes=[dict(tag=n.name,id=n.get('id'),classes=n.get('class'),text=n.get_text(' ',strip=True)[:160]) for n in soup.select('article,main,section,div[id]')][:50],
                     frames=[dict(src=f.get('src')) for f in soup.select('iframe[src]')],
                     attachments=[dict(href=a.get('href'),title=a.get('title'),text=a.get_text(' ',strip=True)) for a in soup.select('a[href]') if '.pdf' in str(a).lower()][:12])
        if args.resume:
            prior=json.loads((args.work_dir/'incomplete-case.json').read_text())
            context['previous_proposal']=prior.get('algorithm_proposal')
            context['validation_error']=prior.get('error')
            if (prior.get('algorithm_proposal') or {}).get('change_type')=='BODY_SELECTOR':
                try:ar.extract(raw,prior['algorithm_proposal']['selector'])
                except ValueError as error:context['extraction_validation_error']=str(error)
        original_model_proposal=None
        if args.reviewed_pdf_selector:
            if not args.resume or not calls:raise ValueError('기존 실제 AI 진단이 필요한 검토 경로입니다')
            original_model_proposal=RuleProposal.model_validate(calls[-1]['response'])
            proposal=original_model_proposal.model_copy(update=dict(change_type='PDF_ATTACHMENT',selector=args.reviewed_pdf_selector))
            case['rule_review']=dict(origin='REVIEWED_AI_PROPOSAL',reviewer='개발 검토',
                reason='AI가 PDF 본문과 같은 호스트 다운로드 경로를 진단했으나 실행 계약은 HTML로 잘못 제안하여 코드 검사에서 차단. 원문 링크를 확인해 개발 검토자가 PDF 규칙으로 정비.',
                original_model_proposal=original_model_proposal.model_dump(),reviewed_rule=proposal.model_dump())
        else:
            proposal=ask('규칙 검증 오류 재검토' if args.resume else '실제 본문 누락의 추출 규칙 개선',RuleProposal,ALGORITHM,json.dumps(context,ensure_ascii=False))
        case['algorithm_proposal']=proposal.model_dump();write('pilot-progress.json',case)
        if proposal.change_type not in ('PDF_ATTACHMENT','BODY_SELECTOR'):
            raise ValueError('AI가 실행 가능한 규칙 변경을 제안하지 않았습니다: '+proposal.change_type)
        # All archive bytes are real. Only target was shown to the model.
        class ArchivedLandingFetcher(Fetcher):
            def get(self,url,*a,**kw):
                if canonical(url)==canonical(target['url']):
                    (self.folder/(target['raw_sha256']+'.raw')).write_bytes(raw)
                    self.last=dict(url=canonical(target['url']),sha256=target['raw_sha256'],bytes=len(raw))
                    return raw
                return super().get(url,*a,**kw)
        fetcher=ArchivedLandingFetcher(args.work_dir)
        fetcher.get(target['url'])
        if proposal.change_type=='PDF_ATTACHMENT':
            (_,body,_),captured=extract_attachment(raw,target['url'],proposal.selector,fetcher)
        else:
            body=ar.extract(raw,proposal.selector);captured=dict(fetcher.last)
        # Pin a real meaningful passage; do not manufacture a golden answer.
        quote=next((line.strip() for line in body.splitlines() if name.split()[0] in line and 10<=len(line.strip())<=500),body.strip()[:150])
        agents.record(store,'algorithm',target['id'],target['raw_sha256'],run['id'],'HOLD',title=target['title'],
                      source_revision_no=target['revision'],result=proposal.model_dump(),passes=[calls[-1]],body_text=target['text'],
                      proposal_origin='REVIEWED_AI_PROPOSAL' if original_model_proposal else 'AI',
                      original_model_proposal=original_model_proposal.model_dump() if original_model_proposal else None)
        detail=ar.detail(service,store,target['id'])
        validation=ar.validate(service,store,target['id'],detail['result_id'],proposal.selector,'URL',quote,fetcher=fetcher)
        # Separate real unseen documents, never AI-generated HTML.
        regression=[]
        for did in args.holdout_ids[:2]:
            meta,html=snapshot(did); f=Fetcher(args.work_dir)
            f.last=dict(url=canonical(meta['url']),sha256=meta['raw_sha256'],bytes=len(html))
            try:
                if proposal.change_type=='PDF_ATTACHMENT':
                    (_,after,_),m=extract_attachment(html,meta['url'],proposal.selector,f)
                else:after=ar.extract(html,proposal.selector);m=dict(f.last)
                regression.append(dict(document_id=did,title=meta['title'],raw_sha256=meta['raw_sha256'],held_out=True,
                                       after_chars=len(after),text_sha256=hashlib.sha256(after.encode()).hexdigest(),metadata=m,passed=True))
            except ValueError as error:regression.append(dict(document_id=did,held_out=True,passed=False,error=str(error)))
        write('rule-validation.json',dict(validation=validation,held_out=regression))
        if not validation['passed'] or len(regression)<2 or not all(r['passed'] for r in regression):
            raise ValueError('대상·실제 미제시 자료 회귀검사 미통과')
        approved=ar.decide(service,store,target['id'],detail['result_id'],detail['review']['version'],'APPLY',
                           '사용자 승인 범위의 격리 시연','실제 원문 및 미제시 문서 2건 검사 후 격리 원장 승인',validation_id=validation['id'],checked=True)
        # Use the actual production rule application function on a fresh capture.
        fresh=Fetcher(args.work_dir);fresh_raw=fresh.get(target['url']);landing=dict(fresh.last)
        (_,repeated_body,_),applied=ar.extract_approved(store,landing['url'],fresh_raw,fetcher=fresh)
        case['algorithm']=dict(proposal=proposal.model_dump(),rule_origin='REVIEWED_AI_PROPOSAL' if original_model_proposal else 'AI',validation_id=validation['id'],approval=approved,
                               held_out=regression,stored_before_chars=len(target['text']),after_chars=len(repeated_body),
                               fresh_landing=landing,repeat_capture=dict(fresh.last),applied=applied,
                               repeat_extraction_model_calls=0,activation_scope='ISOLATED_URL_ONLY')
        sources=[document_snapshot(target['id'],target['title'],fresh.last['url'],target['revision'],repeated_body,authority(fresh.last['url']))]
        before=dict(project_id=project['id'],project_name=name,stage='CONSTRUCTION',
                    gap='현재 공고와 같은 사업의 착공·진행 근거 및 정확한 사건일·물량을 대조')
        run['config']['agent_role']='officer'
        plan=ask('사업 단계 누락 근거 조사 계획',ResearchPlan,PLAN_PROMPT,repeated_body,dict(before,project=public_project))
        if plan.project_id!=project['id'] or plan.stage!='CONSTRUCTION':raise ValueError('조사 계획의 대상 변경')
        case['research_plan']=plan.model_dump();write('pilot-progress.json',case)
        search=[]; seen={canonical(target['url'])};captured_count=0
        for query in plan.queries:
            stats={}
            try:
                f=Fetcher(args.work_dir);rss=f.get('https://www.bing.com/search?'+urlencode(dict(q=query,format='rss',setlang='en-US',mkt='ko-KR')),'xml')
                rows=search_rows(rss,max_age_days=None,allow_undated=True,diagnostics=stats)
                attempt=dict(query=query,response=dict(f.last),stats=stats,results=[])
                for candidate in rows:
                    u=canonical(candidate['evidence_url'])
                    if u in seen or authority(u)!='OFFICIAL' or name.split()[0] not in candidate['name']:continue
                    seen.add(u)
                    if captured_count>=2:break
                    captured_count+=1
                    try:
                        data=f.get(u);(_,txt,truncated),meta=capture(data,f.last['url'],f)
                        if truncated:raise ValueError('전체 본문 미확보')
                        did='FETCH_'+hashlib.sha256(u.encode()).hexdigest()[:24]
                        sources.append(document_snapshot(did,candidate['name'],meta['url'],meta['sha256'],txt,authority(meta['url'])))
                        attempt['results'].append(dict(url=u,document_id=did,chars=len(txt),metadata=meta,status='CAPTURED'))
                    except ValueError as error:attempt['results'].append(dict(url=u,status='CAPTURE_FAILED',error=str(error)))
                attempt['status']='COMPLETED'
            except ValueError as error:attempt=dict(query=query,status='SEARCH_FAILED',error=str(error),stats=stats)
            search.append(attempt)
        case['collection']=search
        write('sources.json',sources);write('pilot-progress.json',case)
        source_text=json.dumps(sources,ensure_ascii=False)
        assessment=ask('공식 원문 대조와 부분 단계 사실 연결',Assessment,ASSESS_PROMPT,source_text,dict(project=public_project,project_id=project['id'],research_plan=plan.model_dump()))
        checked=validate_assessment(assessment,project['id'],sources)
        checked['requested_stage_present']=any(f['stage']==plan.stage for f in checked['findings'])
        if any(r['validation_errors'] for r in checked['findings']) and len(calls)<5:
            revised=ask('원문 인용·필드 오류의 1회 재검토',Assessment,ASSESS_PROMPT,source_text,dict(project_id=project['id'],previous=assessment.model_dump(),validation=checked))
            checked=validate_assessment(revised,project['id'],sources)
        case['assessment']=checked
        case['summary']=dict(linked=checked['linked'],held=checked['held'],source_documents=len(sources),
                             actuals_added=0,rule_repeat_model_calls=0,real_model_calls=len(calls))
        case['sources']=sources;case['model_calls']=calls
        case=save_case(store,case);write('case.json',case);store.finish(run['id'],'COMPLETED')
        print(json.dumps(dict(status='COMPLETED',case_id=case['id'],run_id=run['id'],summary=case['summary']),ensure_ascii=False),flush=True)
    except Exception as error:
        case['error']=type(error).__name__+': '+str(error);case['model_calls']=calls
        write('incomplete-case.json',case);store.finish(run['id'],'FAILED',str(error))
        print(json.dumps(dict(status='FAILED',error=case['error'],run_id=run['id']),ensure_ascii=False),flush=True)
        raise
    finally:
        with store.db() as db:usage=[dict(r) for r in db.execute('SELECT id,run_id,provider,model,input_tokens,output_tokens,cost_usd,status FROM calls')]
        write('usage.json',usage)


if __name__=='__main__':main()
