"""Durable officer worklists: bounded batches, explicit pauses, DB-verified outcomes.

A HOLD is a reviewed business outcome. An unvisited item or execution failure is
not a HOLD. Polling reads the stored summary only; verification runs in the worker.
"""
import csv,io,json,time,uuid
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from sqlalchemy import select
from .db import Revision,Mapping
from .publication_reviews import queue
from .ai_collection_store import DEFAULTS

TERMINAL={'COMPLETED','COMPLETED_WITH_HOLDS'}
REVIEWED={'YES','NO','HOLD'}


def init(store):
    if getattr(store,'_officer_campaign_ready',False):return
    with store.db(True) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS officer_campaigns (
            id TEXT PRIMARY KEY, created REAL NOT NULL, updated REAL NOT NULL,
            status TEXT NOT NULL, payload TEXT NOT NULL, summary TEXT NOT NULL)''')
        db.execute('CREATE INDEX IF NOT EXISTS officer_campaign_created ON officer_campaigns(created DESC)')
    store._officer_campaign_ready=True


def summarize(p):
    results=p['results'];counts=Counter(r['verdict'] for r in results.values())
    reviewed=sum(counts[k] for k in REVIEWED);total=len(p['document_ids'])+len(p['stage_ids'])
    effects={(e['kind'],e.get('document_id') or e.get('id') or e.get('project_id'),e.get('policy_id')):e
        for r in results.values() if r['verdict'] in ('YES','NO') for e in r.get('effects',[])
        if e['kind']!='REGISTER' or e.get('created',True)}
    return dict(id=p['id'],created=p['created'],updated=time.time(),status=p['status'],mode=p['mode'],
        total=total,documents=len(p['document_ids']),stage_candidates=len(p['stage_ids']),reviewed=reviewed,
        yes=counts['YES'],no=counts['NO'],hold=counts['HOLD'],errors=counts['ERROR'],remaining=total-reviewed,
        percent=round(100*reviewed/total,1) if total else (100 if p['status'] in TERMINAL else 0),
        active_run=p.get('active_run'),batches=len(p['runs']),reason=p.get('reason',''),
        effects=dict(Counter(e['kind'] for e in effects.values())),
        scope='시작 시점의 미결 문서·단계 후보 및 실행 중 발견한 직접 공식 대조자료. 새 탐색자료는 한 단계까지 포함.',
        verified_at=p.get('verified_at'),followup_hold=sum(d.get('status')=='HOLD' for r in results.values() for d in r.get('deferred_actions',[])),followup_errors=sum(d.get('status')=='ERROR' for r in results.values() for d in r.get('deferred_actions',[])))


def persist(db,p,allow_resume=False):
    stored=db.execute('SELECT status FROM officer_campaigns WHERE id=?',(p['id'],)).fetchone()
    if stored and stored[0]=='PAUSED_USER' and not allow_resume:
        p['status']='PAUSED_USER';p['reason']='사용자 중지 · 처리 기록 보존'
    s=summarize(p)
    db.execute('INSERT INTO officer_campaigns VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET updated=excluded.updated,status=excluded.status,payload=excluded.payload,summary=excluded.summary',
        (p['id'],p['created'],time.time(),p['status'],json.dumps(p,ensure_ascii=False),json.dumps(s,ensure_ascii=False)))
    return s


def latest(store,detail=False):
    init(store)
    with store.db() as db:
        column='payload' if detail else 'summary'
        row=db.execute('SELECT '+column+' FROM officer_campaigns ORDER BY created DESC LIMIT 1').fetchone()
    return json.loads(row[0]) if row else None


def enqueue_batch(db,p,allow_resume=False):
    stored=db.execute('SELECT status FROM officer_campaigns WHERE id=?',(p['id'],)).fetchone()
    if stored and stored[0]=='PAUSED_USER' and not allow_resume:return
    if db.execute("SELECT 1 FROM runs WHERE status IN ('QUEUED','RUNNING','STOPPING')").fetchone():return
    pending=[did for did in p['document_ids']+p['stage_ids'] if p['results'].get(did,{}).get('verdict','PENDING')=='PENDING']
    if not pending:return
    if pending[0] in p['stage_ids'] and not p.get('stage_prepared'):return
    common={**DEFAULTS,**json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])}
    size=max(1,min(100,int(common['max_documents'])));kind=p['document_ids'] if pending[0] in p['document_ids'] else p['stage_ids'];ids=[i for i in pending if i in kind][:size]
    rid=str(uuid.uuid4());config=dict(common,agent_role='officer',selected_model=p['model'],review_model='',profile=p['provider'],
        campaign_id=p['id'],target_document_ids=[i for i in ids if i in p['document_ids']],target_stage_ids=[i for i in ids if i in p['stage_ids']],force_officer_review=True,
        campaign_discovered_ids=p.get('discovered_ids',[]),max_documents=len(ids))
    schedule=p['schedule_day']+':worklist:'+str(len(p['runs'])+1) if p['mode']=='SCHEDULED' else None
    db.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?)',(rid,'QUEUED',time.time(),time.time(),json.dumps(config),'업무담당자 전체 업무 처리',schedule,None))
    p['active_run']=rid;p['runs'].append(rid);p['status']='RUNNING';p['reason']='단계 후보의 공식 원문을 재조사하고 사건·물량을 검증합니다.' if config['target_stage_ids'] else '미처리 문서의 근거를 조사하고 업무 원장 반영을 확인합니다.'
    db.execute('INSERT INTO events(run_id,created,kind,payload) VALUES(?,?,?,?)',(rid,time.time(),'OFFICER_WORKLIST',json.dumps(dict(campaign_id=p['id'],target_ids=ids,batch=len(p['runs'])))))


def start(service,store,schedule_day=None):
    init(store)
    # Resume keeps verified outcomes, so it cannot replay a completed registration.
    previous=latest(store)
    if previous and previous['status'] not in TERMINAL:
        from .ai_agents_store import settings
        from .ai_agent_catalog import validate
        cfg=settings(store)['officer'];model=validate('officer',cfg['model'])
        with store.db(True) as db:
            p=json.loads(db.execute('SELECT payload FROM officer_campaigns WHERE id=?',(previous['id'],)).fetchone()[0])
            if schedule_day or p['status']=='RUNNING':return summarize(p)
            active=db.execute("SELECT status FROM runs WHERE id=? AND status IN ('QUEUED','RUNNING','STOPPING')",(p.get('active_run'),)).fetchone()
            if active and active[0]=='QUEUED' and p['status']=='WAITING_NIGHT':
                db.execute('UPDATE runs SET schedule_day=NULL WHERE id=?',(p['active_run'],));active=None
            if active:raise ValueError('현재 작업 중지가 완료된 뒤 이어서 실행하세요')
            # A resumed campaign must use the currently selected model, not the
            # provider captured when this worklist was first created.
            p['model']=cfg['model'];p['provider']=model['provider']
            p['status']='RUNNING';p['mode']='MANUAL';p['reason']='남은 업무 이어서 처리';p['resume_requested']=bool(p.get('active_run'))
            for did,result in list(p['results'].items()):
                if result['verdict']=='ERROR' or result.get('deferred_actions') or (p.get('workflow_version',1)<2 and result['verdict']=='HOLD'):p['results'].pop(did)
            p['workflow_version']=2
            # A finished but unconsumed run is reconciled by advance before resuming.
            if not p.get('active_run'):enqueue_batch(db,p,allow_resume=True)
            return persist(db,p,allow_resume=True)
    if schedule_day:
        with store.db() as db:
            if db.execute("SELECT 1 FROM officer_campaigns WHERE json_extract(payload,'$.schedule_day')=?",(schedule_day,)).fetchone():return None
    from .ai_agents_store import settings
    from .ai_agent_catalog import validate
    from .stage_reconciliation import list_items,LIVE
    cfg=settings(store)['officer'];model=validate('officer',cfg['model'])
    from .ai_agents_store import latest as last_results
    previous_results=last_results(store,'officer')
    docs=[r for r in queue(service,include_options=False)['items'] if r['status'] not in ('EXCLUDED','APPROVED') or (r['status']=='APPROVED' and previous_results.get(r['id'],{}).get('deferred_actions'))]
    stage_ids=[r['id'] for r in list_items(service) if r['status'] in LIVE]
    p=dict(id=str(uuid.uuid4()),created=time.time(),status='RUNNING',mode='SCHEDULED' if schedule_day else 'MANUAL',
        workflow_version=2,schedule_day=schedule_day,model=cfg['model'],provider=model['provider'],document_ids=[d['id'] for d in docs],
        stage_ids=stage_ids,discovered_ids=[],runs=[],results={},active_run=None)
    with store.db(True) as db:
        # Concurrent starts must not create two separate worklists.
        row=db.execute("SELECT summary FROM officer_campaigns WHERE status NOT IN ('COMPLETED','COMPLETED_WITH_HOLDS') LIMIT 1").fetchone()
        if row:return json.loads(row[0])
        enqueue_batch(db,p);return persist(db,p)


def missing(reason,field='업무 근거',source='해당 자료의 공식 공고·첨부와 사업 원장',retry='원문·사업 식별자·단계별 일자/물량이 보완되면 재판단'):
    return dict(field=field,needed=reason,source=source,retry_when=retry)


def error_result(reason):return dict(verdict='ERROR',reason=reason,verified_at=time.time(),effects=[])


def include_document_effects(records):
    for record in list(records.values()):
        for e in record.get('effects',[]):
            if e['kind']=='DOCUMENT' and e.get('document_id'):records.setdefault(e['document_id'],record)
    return records


def verify_document(service,did,record,docs):
    doc=docs.get(did)
    if not doc:return error_result('업무 원장에 대상이 없음 · 원문/삭제 이력 확인 필요')
    if not record:
        decision=doc.get('decision') or {}
        exclusion_current=(doc['status']=='EXCLUDED' and decision.get('status')=='EXCLUDED'
            and decision.get('source_revision_no')==doc.get('source_revision_no'))
        if doc['status'] in ('APPROVED','EXCLUDED') and (decision.get('source_checked') or exclusion_current) and decision.get('actor') and decision.get('reason'):
            # A concurrent human decision is authoritative, but not an AI effect.
            proof=dict(verdict='YES' if doc['status']=='APPROVED' else 'NO',reason=decision['reason'],
                effects=[dict(kind='DOCUMENT',document_id=did,status=doc['status'],project_ids=decision.get('project_ids',[]))])
            result=verify_document(service,did,proof,docs)
            if result['verdict']!='ERROR':result.update(effects=[],origin='EXISTING_BUSINESS_DECISION')
            return result
        return error_result('이 대상의 실행 결과 없음 · 미처리이며 근거 보류가 아님')
    if record.get('stage') in ('ERROR','ANALYSIS_ERROR'):return error_result(record.get('reason') or '모델 분석 실패')
    verdict=record.get('verdict');effects=record.get('effects',[]);decision=doc.get('decision') or {}
    base=dict(reason=record.get('reason',''),business_status=doc['status'],review_revision_no=doc['review_revision_no'],
        source_revision_no=doc['source_revision_no'],verified_at=time.time(),run_id=record.get('run_id'))
    if verdict=='HOLD':
        needs=record.get('missing_evidence') or []
        if not needs or any(not all(x.get(k) for k in ('field','needed','source','retry_when')) for x in needs):return error_result('보류 사유·필요 자료·출처·재판단 조건 누락')
        # Research failures are actionable work errors, never successful final holds.
        if record.get('search_error'):return error_result(record['search_error'])
        return dict(base,verdict='HOLD',missing_evidence=needs,effects=[])
    if verdict not in ('YES','NO') or not effects:return error_result('최종 결정 또는 집행 이력 없음')
    if doc.get('source_changed') or doc.get('link_changed'):return error_result('판단 이후 원문/사업 변경 · 재검토 필요')
    if doc['status']!=('APPROVED' if verdict=='YES' else 'EXCLUDED'):return error_result('모델 결론과 실제 업무 원장 상태 불일치')
    document_effects=[e for e in effects if e['kind']=='DOCUMENT']
    if not any(e.get('document_id')==did for e in document_effects):return error_result('대상 자료의 집행 이력 누락')
    for effect in document_effects:
        target=docs.get(effect['document_id']);d=(target or {}).get('decision') or {}
        if not target or target['status']!=effect['status'] or target.get('source_changed') or target.get('link_changed') or set(d.get('project_ids',[]))!=set(effect.get('project_ids',[])):
            return error_result('자료 연결/제외의 저장 결과 불일치')
    if verdict=='YES' and not decision.get('project_ids'):return error_result('YES이나 연결된 사업 ID 없음')
    with service.sessions() as db:
        project_ids=set(decision.get('project_ids',[]))|{e['project_id'] for e in effects if e['kind'] in ('REGISTER','POLICY')}
        projects=set(db.scalars(select(Revision.entity_id).where(Revision.kind=='project',Revision.entity_id.in_(project_ids),Revision.superseded_at.is_(None)))) if project_ids else set()
        if projects!=project_ids:return error_result('등록/연결 대상 사업 원장 없음')
        for e in effects:
            if e['kind']=='POLICY':
                m=db.scalar(select(Mapping).where(Mapping.project_id==e['project_id']))
                if not m or m.status!='CONFIRMED' or m.policy_id!=e['policy_id']:return error_result('정책 귀속 원장 불일치')
            if e['kind']=='STAGE':
                r=db.scalar(select(Revision).where(Revision.kind=='stage_proposal',Revision.entity_id==e['id'],Revision.superseded_at.is_(None)))
                if not r or r.payload.get('status')!='APPLIED':return error_result('단계 실적 제안이 실제 반영되지 않음')
                if not stage_applied(db,r.payload):return error_result('단계 제안과 실제 사업 실적 원장 불일치')
    return dict(base,verdict=verdict,effects=effects,missing_evidence=record.get('missing_evidence',[]),deferred_actions=record.get('deferred_actions',[]))


def stage_applied(db,p):
    profile=db.scalar(select(Revision).where(Revision.kind=='project_profile',Revision.superseded_at.is_(None),Revision.payload['project_id'].as_string()==p['project_id']))
    v=((profile.payload if profile else {}).get('progress') or {}).get(p['stage']) or {};f=p['proposed']
    return v.get('units')==f.get('units') and (v.get('event_date')==f.get('event_date') if f.get('date_basis')=='EVENT' else v.get('observed_on')==f.get('event_date'))


def verify_stage_record(service,row,record):
    if not row:return error_result('단계 후보 없음')
    if row['status']=='DISMISSED':return dict(verdict='NO',reason='단계 제안 제외 이력 확인',effects=[],verified_at=time.time())
    effects=[dict(kind='STAGE',id=row['id'])] if row['status']=='APPLIED' else (record or {}).get('effects',[])
    for e in effects:
        if e['kind']!='STAGE':continue
        with service.sessions() as db:
            saved=db.scalar(select(Revision).where(Revision.kind=='stage_proposal',Revision.entity_id==e['id'],Revision.superseded_at.is_(None)))
            valid=bool(saved and saved.payload.get('status')=='APPLIED' and saved.payload['project_id']==row['project_id'] and saved.payload['stage']==row['stage'] and stage_applied(db,saved.payload))
        if valid:return dict(verdict='YES',reason='재조사·확정된 단계와 실제 사업 실적 원장 대조 완료',effects=[e],verified_at=time.time())
    if row['status']=='APPLIED' or (record or {}).get('verdict')=='YES':return error_result('단계 반영 원장 불일치')
    if not record or not record.get('researched'):return error_result((record or {}).get('reason') or '단계 재조사 기록 없음 · 기존 보류를 재검토 완료로 세지 않음')
    if record.get('verdict')!='HOLD':return error_result(record.get('reason') or '단계 판단 미집행')
    needs=record.get('missing_evidence') or []
    if not needs or any(not all(x.get(k) for k in ('field','needed','source','retry_when')) for x in needs):return error_result('단계 보류의 필요 근거·재판단 조건 누락')
    return dict(verdict='HOLD',reason=record['reason'],missing_evidence=needs,effects=[],researched=True,verified_at=time.time())


def verify_stages(service,p,records=None):
    from .stage_reconciliation import list_items
    rows={r['id']:r for r in list_items(service)}
    for sid in p['stage_ids']:p['results'][sid]=verify_stage_record(service,rows.get(sid),(records or {}).get(sid))


def _advance(service,store,current=None):
    """Worker-only. One batch at a time; no five-batch truncation or unchanged skip."""
    init(store);p=latest(store,True)
    if not p or p['status'] in TERMINAL or p['status'].startswith('PAUSED'):return
    from .operations_window import night_open
    current=current or datetime.now(ZoneInfo('Asia/Seoul'))
    if p['mode']=='SCHEDULED' and not night_open(current):
        p['status']='WAITING_NIGHT';p['reason']='야간 처리 시간 종료 · 다음 01~05시에 남은 대상부터 이어갑니다.'
        with store.db(True) as db:persist(db,p)
        return
    rid=p.get('active_run')
    if rid:
        with store.db() as db:
            run=dict(db.execute('SELECT * FROM runs WHERE id=?',(rid,)).fetchone())
            if run['status'] in ('QUEUED','RUNNING','STOPPING'):return
            config=json.loads(run['config']);records={r['subject']:dict(json.loads(r['payload']),run_id=rid) for r in db.execute("SELECT * FROM agent_results WHERE role='officer' AND run_id=? ORDER BY created",(rid,))}
        docs={d['id']:d for d in queue(service,include_options=False)['items']}
        records=include_document_effects(records)
        for did in config['target_document_ids']:
            if did in records:p['results'][did]=verify_document(service,did,records[did],docs)
            elif run['status'] in ('COMPLETED','PARTIAL'):p['results'][did]=verify_document(service,did,None,docs)
        if config.get('target_stage_ids'):
            from .stage_reconciliation import list_items
            stage_rows={r['id']:r for r in list_items(service)}
            for sid in config['target_stage_ids']:
                if sid in records or run['status'] in ('COMPLETED','PARTIAL'):p['results'][sid]=verify_stage_record(service,stage_rows.get(sid),records.get(sid))
        for did,record in records.items():
            # Only direct official references, never recursive unlimited discovery.
            if did in p['discovered_ids'] or did not in config['target_document_ids']:continue
            for ref in record.get('official_search',[]):
                new=ref['document_id']
                if new in docs and new not in p['document_ids']:
                    p['document_ids'].append(new);p['discovered_ids'].append(new)
                    if new in records:p['results'][new]=verify_document(service,new,records[new],docs)
        p['active_run']=None
        if run['status'] not in ('COMPLETED','PARTIAL'):
            p['status']='WAITING_NIGHT' if '야간 시간' in (run.get('error') or '') and p['mode']=='SCHEDULED' else 'PAUSED_'+('BUDGET' if run['status']=='BUDGET_PAUSED' else 'USER' if run['status']=='CANCELLED' else 'ERRORS')
            p['reason']=run.get('error') or run['status']
    if p.pop('resume_requested',False):
        p['status']='RUNNING'
        p['results']={k:v for k,v in p['results'].items() if v['verdict']!='ERROR'}
    if not p['status'].startswith('PAUSED') and p['status']!='WAITING_NIGHT' and not p.get('stage_prepared') and all(d in p['results'] for d in p['document_ids']):
        p['reason']='문서 판단 종료 · 수집 원장에서 단계 후보를 갱신한 뒤 재조사합니다.'
        with store.db(True) as db:persist(db,p)
        if latest(store)['status']=='PAUSED_USER':return
        from .stage_reconciliation import refresh,list_items,LIVE
        refresh(service,auto_apply=False)
        for row in list_items(service):
            if row['status'] in LIVE and row['id'] not in p['stage_ids']:p['stage_ids'].append(row['id'])
        p['stage_prepared']=True
    pending=[d for d in p['document_ids']+p['stage_ids'] if d not in p['results']]
    if not p['status'].startswith('PAUSED') and p['status']!='WAITING_NIGHT':
        if pending:
            with store.db(True) as db:enqueue_batch(db,p);persist(db,p)
            return
        p['reason']='문서·단계 재조사 종료 · 최종 저장 결과 대조 중'
        with store.db(True) as db:persist(db,p)
        # Recheck *all* document outcomes at the end against today's DB state.
        docs={d['id']:d for d in queue(service,include_options=False)['items']}
        with store.db() as db:
            slots=','.join('?' for _ in p['runs']) or 'NULL'
            records={r['subject']:dict(json.loads(r['payload']),run_id=r['run_id']) for r in db.execute(f"SELECT * FROM agent_results WHERE role='officer' AND run_id IN ({slots}) ORDER BY created",p['runs'])}
        records=include_document_effects(records)
        for did in p['document_ids']:p['results'][did]=verify_document(service,did,records.get(did),docs)
        if latest(store)['status']=='PAUSED_USER':return
        verify_stages(service,p,records)
        errors=any(r['verdict']=='ERROR' or any(d.get('status')=='ERROR' for d in r.get('deferred_actions',[])) for r in p['results'].values())
        p['status']='PAUSED_ERRORS' if errors else 'COMPLETED_WITH_HOLDS' if any(r['verdict']=='HOLD' or r.get('deferred_actions') for r in p['results'].values()) else 'COMPLETED'
        p['reason']='집행 결과 불일치/오류를 확인한 뒤 남은 업무 재실행 필요' if errors else '전체 대상의 최종 판단과 실제 저장 결과 대조 완료. 근거 부족 보류는 승인과 구분합니다.'
        p['verified_at']=time.time()
    if p['status']=='WAITING_NIGHT' and night_open(current):p['status']='RUNNING'
    with store.db(True) as db:persist(db,p)


def advance(service,store,current=None):
    try:return _advance(service,store,current)
    except Exception as error:
        p=latest(store,True)
        if not p or p['status'] in TERMINAL:raise
        p['status']='PAUSED_ERRORS';p['reason']='업무 원장 대조 중 오류 · '+type(error).__name__+' · 완료 처리하지 않음'
        with store.db(True) as db:persist(db,p)


def stop(store):
    p=latest(store,True)
    if not p or p['status'] in TERMINAL:return p
    with store.db(True) as db:
        p=json.loads(db.execute('SELECT payload FROM officer_campaigns WHERE id=?',(p['id'],)).fetchone()[0])
        p['status']='PAUSED_USER';p['reason']='사용자 중지 · 처리 기록을 보존하며 이어서 실행 가능'
        if p.get('active_run'):
            db.execute("UPDATE runs SET status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'STOPPING' END,updated=? WHERE id=? AND status IN ('QUEUED','RUNNING')",(time.time(),p['active_run']))
        return persist(db,p)


def export_csv(store):
    from .publication_review_export import cell
    p=latest(store,True);out=io.StringIO(newline='');w=csv.writer(out)
    w.writerow(['전체작업ID','대상ID','유형','최종결정','처리사유','실제업무상태','원장대조시각','필요근거_JSON','반영효과_JSON','후속업무_JSON'])
    if p:
        for subject in p['document_ids']+p['stage_ids']:
            r=p['results'].get(subject,{})
            stamp=datetime.fromtimestamp(r['verified_at'],ZoneInfo('Asia/Seoul')).isoformat() if r.get('verified_at') else ''
            w.writerow([cell(v) for v in [p['id'],subject,'STAGE' if subject.startswith('STA_') else 'DOCUMENT',r.get('verdict','UNPROCESSED'),r.get('reason','아직 처리하지 않음'),r.get('business_status',''),stamp,json.dumps(r.get('missing_evidence',[]),ensure_ascii=False),json.dumps(r.get('effects',[]),ensure_ascii=False),json.dumps(r.get('deferred_actions',[]),ensure_ascii=False)]])
    return '\ufeff'+out.getvalue()
