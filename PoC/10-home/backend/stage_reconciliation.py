"""Version-pinned stage proposals. Approval replaces a stage value, never adds twice."""
from copy import deepcopy
from datetime import date
import csv, hashlib, io, json, re
from sqlalchemy import select, text
from .db import Revision, Mapping, Audit, entity_id, upsert_revision, now
from .project_profile import STAGES
from .source_authority import authority
from .publication_reviews import normalized
from .api_samples import today

KIND='stage_proposal'
OWNER='stage_reconcile'
LIVE=('READY','HOLD')


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def current(db, kind, eid, lock=False):
    query=select(Revision).where(Revision.kind==kind,Revision.entity_id==eid,Revision.superseded_at.is_(None))
    return db.scalar(query.with_for_update() if lock else query)


def snapshot(service):
    with service.sessions() as db:
        rows=list(db.scalars(select(Revision).where(Revision.kind.in_(['project','project_profile',KIND]),Revision.superseded_at.is_(None))))
        mappings={m.project_id:dict(status=m.status,revision_no=m.revision_no,policy_id=m.policy_id) for m in db.scalars(select(Mapping))}
    return ({r.entity_id:r for r in rows if r.kind=='project'},
            {r.payload['project_id']:r for r in rows if r.kind=='project_profile'},
            [r for r in rows if r.kind==KIND],mappings)


def exact_date_in_quote(value, quote):
    try:d=date.fromisoformat(value)
    except (TypeError,ValueError):return False
    return bool(re.search(rf'(?<!\d){d.year}\s*(?:년|[-./])\s*0?{d.month}\s*(?:월|[-./])\s*0?{d.day}(?:일|\b|\D)',quote+' '))


def automatic_proof(p):
    """A model score cannot replace source identity, exact quotes or field semantics."""
    reasons=[];f=p['proposed'];stage=p['stage'];body=p.get('proof',{}).get('body','');proof=p.get('proof',{})
    if authority(p.get('url',''))!='OFFICIAL':reasons.append('공식 원문 대조 필요')
    if not p.get('identity_confirmed'):reasons.append('동일 사업 연결 확인 필요')
    if p.get('human_hold'):reasons.append('기존 담당자 보류 · 자동 덮어쓰기 금지')
    if f.get('date_basis')!='EVENT' or f.get('precision')!='DAY':reasons.append('실제 사건일 미확보 · 확인일/월/연도와 구분')
    if f.get('scope')!='WHOLE_PROJECT':reasons.append('전체·부분·재모집 범위 확인 필요')
    if proof.get('issues'):reasons.append('원문 분석의 미해결 쟁점')
    quotes=[proof.get('date_quote',''),proof.get('units_quote','')]
    if not body or any(not q or q not in body for q in quotes):reasons.append('일자·물량의 원문 인용 부족')
    name=normalized(p.get('project_name',''))
    if not name or any(name not in normalized(q) for q in quotes):reasons.append('인용 안의 동일 사업·일자·물량 결합 확인 필요')
    if not re.search(r'(?:총|전체)\s*[\d,]+\s*(?:세대|가구|호)',quotes[1]) or re.search(r'잔여|예비|재모집|추가모집|정정|부분',quotes[1]):reasons.append('전체 누적 물량 인용 확인 필요')
    if not exact_date_in_quote(f.get('event_date'),quotes[0]):reasons.append('일 단위 실제 날짜 인용 확인 필요')
    qty=str(f.get('units') or '');q=re.sub(r'[,\s]','',quotes[1])
    if not re.search(r'(?<!\d)'+re.escape(qty)+r'(?:세대|가구|호)(?!실|\d)',q):reasons.append('공급호수 단위의 인용 확인 필요')
    actual={'BUSINESS':r'지구.{0,8}지정|정비구역.{0,8}지정|사업.{0,8}확정',
            'APPROVAL':r'인가|허가|사업계획.{0,8}승인','CONSTRUCTION':r'착공',
            'COMPLETION':r'준공|사용승인|사용검사','SUPPLY':r'입주자.{0,8}모집.{0,8}공고|분양.{0,8}공고',
            'MOVE_IN':r'입주.{0,8}(?:시작|개시|완료|했다|하였다)'}
    if not re.search(actual[stage],quotes[0]) or re.search(r'예정|목표|계획|예상|착공식|기공식|미착공|취소|철회|오보|무산|하지\s*않|전망',re.sub(r'사업\s*계획\s*승인','사업승인',quotes[0])):
        reasons.append('계획·행사와 실제 단계 달성의 구분 필요')
    return reasons


def evaluate(p, project, profile, mapping):
    f=p['proposed'];hard=[];review=automatic_proof(p)
    if p.get('invalid_source'):hard.append('선택한 단계 근거의 원천 판본 변경 · 단계 연결을 재검토하세요')
    old=(profile or {}).get('progress',{}).get(p['stage']);cap=(profile or {}).get('overrides',{}).get('planned_units',{}).get('value')
    if cap is None:cap=project.get('planned_units')
    if type(f.get('units')) is not int or f['units']<=0 or type(cap) is not int or f['units']>cap:hard.append('사업 목표량 이내의 확인 물량 필요')
    try:
        d=date.fromisoformat((f.get('event_date') or ''))
        if not date(1900,1,1)<=d<=today():hard.append('미래 예정일은 실적으로 승인 불가')
    except (ValueError,TypeError):hard.append('일 단위 사건일 또는 도달 확인일 필요')
    if f.get('precision')!='DAY':hard.append('월·연도만 확인됨 · 임의의 일자 생성 금지')
    if f.get('date_basis') not in ('EVENT','OBSERVED_BY'):hard.append('실제 사건일/도달 확인일 구분 필요')
    if f.get('scope') not in ('WHOLE_PROJECT','PARTIAL'):hard.append('사업별 실적 물량의 적용 범위 확인 필요')
    if p['stage']=='CONSTRUCTION' and project.get('start_actual_date') and project['start_actual_date']!=f.get('event_date'):review.append('원천 착공일과 상충 · 담당자 확인 필요')
    if mapping.get('status')!='CONFIRMED':review.append('정책 귀속 미확정 · 담당자 확인 필요')
    if f.get('units')!=cap:review.append('부분 물량 · 누적/증분 중복 검토 필요')
    if old and not old.get('inferred'):
        if old.get('event_date')!=f.get('event_date') or old.get('units')!=f.get('units'):review.append('기존 확정 실적과 상충 · 담당자 정정 승인 필요')
    if old and type(old.get('units')) is int and type(f.get('units')) is int and f['units']<old['units']:review.append('기존 집계량 감소 · 담당자 확인 필요')
    # Supply may precede construction. Only physically ordered stages constrain one another.
    order=['BUSINESS','APPROVAL','CONSTRUCTION','COMPLETION','MOVE_IN']
    if p['stage'] in order and f.get('date_basis')=='EVENT':
        for stage,v in (profile or {}).get('progress',{}).items():
            if stage not in order or stage==p['stage'] or v.get('inferred') or v.get('date_basis','EVENT')!='EVENT' or not v.get('event_date'):continue
            if (order.index(stage)<order.index(p['stage']) and v['event_date']>(f.get('event_date') or '')) or (order.index(stage)>order.index(p['stage']) and v['event_date']<(f.get('event_date') or '')):
                hard.append('확정된 '+STAGES[stage]+' 일자와 선후관계 상충')
    identical=bool(old and not old.get('inferred') and old.get('event_date')==f.get('event_date') and old.get('units')==f.get('units') and old.get('date_basis','EVENT')==f.get('date_basis'))
    return dict(blockers=list(dict.fromkeys(hard)),review_reasons=list(dict.fromkeys(review)),can_apply=not hard,auto_eligible=not hard and not review,
                previous=old,project_cap=cap,already_reflected=identical,
                delta_units=(f['units']-(old.get('units') or 0) if old else f['units']) if type(f.get('units')) is int else None)


def propose(service, payload):
    if payload.get('stage') not in STAGES:raise ValueError('지원하지 않는 실적 단계')
    key=payload['source_ref']['id']+':'+payload['project_id']+':'+payload['stage']
    eid=entity_id(KIND,OWNER,key)
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        source=current(db,payload['source_ref']['kind'],payload['source_ref']['id'])
        if not source or source.payload_hash!=payload['source_ref']['hash']:raise ValueError('근거 판본 변경')
        project=current(db,'project',payload['project_id'])
        if not project:raise ValueError('사업 원장 미등록')
        old=current(db,KIND,eid)
        value=deepcopy(payload)
        if value.get('project_hash') and value['project_hash']!=project.payload_hash:raise ValueError('사업 식별 판본 변경')
        value['project_hash']=project.payload_hash
        if not proof_body_current(db,value):raise ValueError('원문·검토 판본 변경')
        value['fingerprint']=digest(value)
        if old and old.payload.get('fingerprint')==value['fingerprint']:return dict(id=eid,revision_no=old.revision_no,unchanged=True)
        value.update(status='HOLD',created_at=now().isoformat())
        row,_=upsert_revision(db,KIND,OWNER,key,value,'stage-reconciliation')
        db.add(Audit(entity_id=eid,action='STAGE_PROPOSED',before=old.payload if old else {},after={'source_ref':value['source_ref'],'stage':value['stage'],'project_id':value['project_id']}))
        return dict(id=eid,revision_no=row.revision_no)


def ref_matches(row, ref):
    if not row:return False
    value=digest({k:row.payload.get(k) for k in ('selected','status')}) if ref.get('selection') else row.payload_hash
    return value==ref['hash']


def proof_body_current(db,p,lock=False):
    refs=p.get('related_refs',[])+([p['body_ref']] if p.get('body_ref') else [])
    return all(ref_matches(current(db,ref['kind'],ref['id'],lock),ref) for ref in refs)


def reference(row):
    return dict(kind=row.kind,id=row.entity_id,hash=row.payload_hash,revision_no=row.revision_no)


def list_items(service):
    projects,profiles,rows,mappings=snapshot(service);result=[]
    with service.sessions() as db:
        refs={(r.payload['source_ref']['kind'],r.payload['source_ref']['id']) for r in rows}
        refs|={(ref['kind'],ref['id']) for r in rows for ref in r.payload.get('related_refs',[])+([r.payload['body_ref']] if r.payload.get('body_ref') else [])}
        versions={r.entity_id:r for r in db.scalars(select(Revision).where(Revision.entity_id.in_([i[1] for i in refs]),Revision.superseded_at.is_(None)))} if refs else {}
    for r in rows:
        p=r.payload;project=projects.get(p['project_id']);profile=profiles.get(p['project_id']);ref=p['source_ref'];src=versions.get(ref['id']);br=p.get('body_ref');body=versions.get(br['id']) if br else None
        stale=not src or src.payload_hash!=ref['hash'] or not project or project.payload_hash!=p.get('project_hash')
        stale=stale or any(not ref_matches(versions.get(x['id']),x) for x in p.get('related_refs',[])+([br] if br else []))
        check=evaluate(p,project.payload if project else {},profile.payload if profile else {},mappings.get(p['project_id'],{}))
        if stale or not project:check['blockers'].append('원문 또는 사업 판본 변경 · 재검토 필요');check['can_apply']=check['auto_eligible']=False
        value={k:v for k,v in p.items() if k!='proof'}
        value.update(id=r.entity_id,revision_no=r.revision_no,project_revision_no=project.revision_no if project else None,
            profile_revision_no=profile.revision_no if profile else 0,mapping_revision_no=mappings.get(p['project_id'],{}).get('revision_no'),
            project_name=project.payload.get('name') if project else '미등록 사업',stage_label=STAGES[p['stage']],stale=stale,
            quotes={k:v for k,v in p.get('proof',{}).items() if k!='body'},**check)
        if value['status'] in LIVE:value['status']='READY' if check['auto_eligible'] else 'HOLD'
        result.append(value)
    return sorted(result,key=lambda r:r.get('created_at',''),reverse=True)


def decide(service, pid, revision_no, project_revision_no, profile_revision_no, mapping_revision_no, action, actor, reason, checked=False, replace_confirmed=False, automatic=False):
    if not actor.strip() or len(reason.strip())<5:raise ValueError('담당자와 5자 이상의 사유가 필요합니다')
    if action not in ('APPLY','DISMISS'):raise ValueError('승인/제외 동작을 확인하세요')
    if action=='APPLY' and not checked:raise ValueError('원문·동일 사업·물량·날짜 의미를 확인하세요')
    with service.sessions.begin() as db:
        if service.engine.dialect.name=='postgresql':db.execute(text('SELECT pg_advisory_xact_lock(9072026)'))
        row=db.scalar(select(Revision).where(Revision.entity_id==pid,Revision.kind==KIND,Revision.superseded_at.is_(None)).with_for_update())
        if not row or row.revision_no!=revision_no:return dict(conflict=True)
        p=deepcopy(row.payload)
        if p['status'] in ('APPLIED','DISMISSED'):return dict(conflict=True)
        ref=p['source_ref'];source=current(db,ref['kind'],ref['id'],True)
        if not source or source.payload_hash!=ref['hash'] or not proof_body_current(db,p,True):return dict(conflict=True)
        project=current(db,'project',p['project_id'],True);profile=current(db,'project_profile',entity_id('project_profile','manual_project',p['project_id']),True)
        mapping=db.scalar(select(Mapping).where(Mapping.project_id==p['project_id']).with_for_update())
        if not project or project.revision_no!=project_revision_no or (profile.revision_no if profile else 0)!=profile_revision_no or (mapping.revision_no if mapping else None)!=mapping_revision_no:return dict(conflict=True)
        ref=p['source_ref'];source=current(db,ref['kind'],ref['id'])
        if not source or source.payload_hash!=ref['hash'] or project.payload_hash!=p.get('project_hash') or not proof_body_current(db,p):return dict(conflict=True)
        check=evaluate(p,project.payload,profile.payload if profile else {},dict(status=mapping.status) if mapping else {})
        old_profile=deepcopy(profile.payload) if profile else {};old=check['previous'];stamp=now().isoformat()
        if action=='APPLY':
            if check['blockers']:raise ValueError(' / '.join(check['blockers']))
            if automatic and not check['auto_eligible']:raise ValueError('자동 반영 조건 미충족')
            if old and not old.get('inferred') and not check['already_reflected'] and not replace_confirmed:raise ValueError('기존 확정 실적 정정 확인이 필요합니다')
            if not check['already_reflected']:
                value=deepcopy(old_profile) or dict(project_id=p['project_id'],overrides={},approvals={})
                f=p['proposed'];meta=dict(origin='MANUAL',actor=actor,reason=reason,changed_at=stamp,
                    input_rule='OFFICER_VERIFIED_SOURCE',inferred=False,source_proposal_id=pid,source_ref=ref,
                    evidence_url=p['url'],date_basis=f['date_basis'],source_event_date=f['event_date'] if f['date_basis']=='EVENT' else None,
                    observed_on=f['event_date'] if f['date_basis']=='OBSERVED_BY' else None,precision=f['precision'],scope=f['scope'])
                value.setdefault('progress',{})[p['stage']]=dict(meta,event_date=f['event_date'],units=f['units'])
                value.update(base_date=today().isoformat(),actor=actor,reason=reason)
                value['last_changes']=dict(stage_reconciliation=dict(proposal_id=pid,before=old,after=value['progress'][p['stage']]))
                saved,_=upsert_revision(db,'project_profile','manual_project',p['project_id'],value,'stage-reconciliation')
                db.add(Audit(entity_id=saved.entity_id,action='PROJECT_PROFILE_UPDATED',before=old_profile,after=value))
        p.update(status='APPLIED' if action=='APPLY' else 'DISMISSED',reviewed_at=stamp,actor=actor,review_reason=reason,automatic=automatic,
                 previous_at_review=old,effect='동일 사업·단계 누적값 대체 · 증분 가산 아님')
        key=ref['id']+':'+p['project_id']+':'+p['stage'];saved,_=upsert_revision(db,KIND,OWNER,key,p,'stage-reconciliation')
        db.add(Audit(entity_id=pid,action='STAGE_APPLIED' if action=='APPLY' else 'STAGE_DISMISSED',before=row.payload,after=p))
        return dict(id=pid,status=p['status'],revision_no=saved.revision_no,project_id=p['project_id'],already_reflected=check['already_reflected'])


def refresh(service, auto_apply=False):
    """Scheduled/on-demand only. No network, model calls or writes on dashboard reads."""
    projects,profiles,_,mappings=snapshot(service);created=0;skipped=0
    with service.sessions() as db:
        bridges=list(db.scalars(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None))))
    for row in bridges:
        b=row.payload;project=projects.get(b.get('project_id'));profile=profiles.get(b.get('project_id'))
        if not project or b.get('status') not in ('CONFIRMED','REVIEW') or b.get('relation_type')=='DOCUMENT_REFERENCE':continue
        if profile and row.recorded_at<=profile.recorded_at:continue
        # Do not manufacture a new event from a whole-district or partial-scope record.
        grouped={}
        for f in b.get('facts',[]):
            stage='COMPLETION' if f.get('milestone')=='COMPLETION' else f.get('stage')
            if f.get('kind')=='ACTUAL' and stage in STAGES and not f.get('reference_only') and not f.get('scope_partial'):grouped.setdefault(stage,[]).append(f)
        for stage,facts in grouped.items():
            # Conflicting same-stage events require choosing an event, not silently taking the last fact.
            f=max(facts,key=lambda x:x.get('date') or x.get('date_label') or '')
            stage='COMPLETION' if f.get('milestone')=='COMPLETION' else f.get('stage')
            if stage not in STAGES or f.get('kind')!='ACTUAL' or f.get('reference_only') or f.get('scope_partial'):continue
            if f.get('pct') is not None and (stage!='CONSTRUCTION' or f['pct']<=0):continue
            when=f.get('date') or f.get('date_label') or '';basis='OBSERVED_BY' if f.get('pct') is not None else f.get('date_basis','EVENT')
            quantity=f.get('units')
            if quantity is None and b.get('relation_type')=='SAME_SCOPE':quantity=b.get('units')
            p=dict(project_id=project.entity_id,stage=stage,url=b.get('evidence_url') or '',title=b.get('source_name') or b.get('name') or project.payload['name'],
                   source_ref=dict(kind='evidence_bridge',id=row.entity_id,hash=row.payload_hash,revision_no=row.revision_no),
                   identity_confirmed=b.get('status')=='CONFIRMED',human_hold=False,origin='STRUCTURED_SOURCE',
                   proposed=dict(event_date=when,units=quantity,date_basis=basis,precision='DAY' if len(when)==10 else 'MONTH' if len(when)==7 else 'UNKNOWN',scope='WHOLE_PROJECT' if b.get('relation_type')=='SAME_SCOPE' else 'UNKNOWN'),
                   proof=dict(body='',date_quote=f.get('basis',''),units_quote=b.get('basis',''),issues=['같은 단계 복수 사건 · 범위 확인 필요'] if len(facts)>1 else []),source_fact=f)
            result=propose(service,p);created+=not result.get('unchanged',False)
    created+=refresh_selected_sources(service,projects,profiles)
    # Officer-checked quotations can form proposals after a document has been linked.
    from .publication_review_export import export_json
    for item in export_json(service,status='APPROVED')['items']:
        if not item['assessment_current'] or len(item['linked_project_ids'])!=1:continue
        project=projects.get(item['linked_project_ids'][0]);a=item['officer_assessment']
        if not project:continue
        with service.sessions() as db:
            ar=current(db,'publication_assessment',entity_id('publication_assessment','officer_evidence',item['document_id']))
        if not ar:continue
        with service.sessions() as db:
            ids=[item['document_id']]+[entity_id(kind,owner,item['document_id']) for kind,owner in [('publication_review','publication_review'),('publication_supplement','publication_manual'),('ai_publication_analysis','ai_publication')]]
            related=[reference(r) for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.entity_id.in_(ids)))]
        seen=set()
        for f in item['facts']:
            if f.get('kind')!='DATE' or f.get('stage') not in STAGES or f.get('temporality')!='REPORTED_ACTUAL' or f['stage'] in seen:continue
            seen.add(f['stage'])
            qs=[q for q in item['facts'] if q.get('kind')=='QUANTITY' and q.get('temporality')=='REPORTED_ACTUAL' and q.get('unit') in ('호','세대','가구')]
            q=qs[0] if len(qs)==1 else {};body=next((c['text'] for c in item['candidates'] if c['origin']==f['source_type'] and c['current']),'')
            p=dict(project_id=project.entity_id,stage=f['stage'],url=item['source_url'],title=item['title'],document_id=item['document_id'],
                source_ref=reference(ar),related_refs=related,identity_confirmed=True,human_hold=True,origin='OFFICER_ASSESSMENT',
                proposed=dict(event_date=f.get('value',''),units=q.get('value'),date_basis='EVENT',precision=f.get('precision','UNKNOWN'),scope='WHOLE_PROJECT' if q.get('value')==project.payload.get('planned_units') else 'UNKNOWN'),
                proof=dict(body=body,date_quote=f['quote'],units_quote=q.get('quote',''),issues=[]))
            result=propose(service,p);created+=not result.get('unchanged',False)
    applied=0
    if auto_apply:
        for p in list_items(service):
            if p['status'] not in LIVE or not p['auto_eligible']:continue
            with service.sessions() as db:
                pr=current(db,'project_profile',entity_id('project_profile','manual_project',p['project_id']))
                p['profile_revision_no']=pr.revision_no if pr else 0
            result=decide(service,p['id'],p['revision_no'],p['project_revision_no'],p['profile_revision_no'],p['mapping_revision_no'],'APPLY','업무담당자 AI · 검증된 단계 실적','공식 원문·동일 사업·실제 일자·전체 물량 인용 및 기존 실적 충돌 검증 통과',True,automatic=True)
            if not result.get('conflict'):applied+=1
    return dict(proposals_changed=created,applied=applied)


def export_csv(service):
    from .publication_review_export import cell
    from .publication_evidence import safe_value
    out=io.StringIO(newline='');w=csv.writer(out);w.writerow(['검토ID','사업ID','사업명','단계','상태','기존값_JSON','새근거_JSON','변경호수_가산아님','자동반영제약','반영불가사유','원문URL','근거판본_JSON','인용_JSON'])
    for r in list_items(service):
        r=safe_value(r)
        if r['status'] not in LIVE:continue
        values=[r['id'],r['project_id'],r['project_name'],r['stage_label'],r['status'],json.dumps(r['previous'],ensure_ascii=False),json.dumps(r['proposed'],ensure_ascii=False),r['delta_units'],' / '.join(r['review_reasons']),' / '.join(r['blockers']),r['url'],json.dumps(r['source_ref'],ensure_ascii=False),json.dumps(r['quotes'],ensure_ascii=False)]
        w.writerow([cell(v) for v in values])
    return '\ufeff'+out.getvalue()


def from_ai(service, doc, project, event, body, origin, identity, human_hold):
    """Create only a proposal from current, pinned model input; never trust model IDs."""
    from .publication_reviews import KIND as RK, OWNER as RO
    with service.sessions() as db:
        source=current(db,'document_evidence',doc['id'])
        review=current(db,RK,entity_id(RK,RO,doc['id']))
        pr=current(db,'project',project['id'])
        if not source or source.revision_no!=doc['source_revision_no'] or (review.revision_no if review else 0)!=doc['review_revision_no'] or not pr or pr.revision_no!=project['revision_no']:
            raise ValueError('분석 이후 원문·사업·담당자 판단 변경 · 재검토 필요')
        refs=[reference(review)] if review else []
        if origin!='SOURCE':
            kind,owner=('publication_supplement','publication_manual') if origin=='MANUAL' else ('ai_publication_analysis','ai_publication')
            # ID lookup avoids scanning JSON bodies containing source PDF control characters.
            br=current(db,kind,entity_id(kind,owner,doc['id']))
            if not br or br.payload.get('body_text')!=body:raise ValueError('분석 본문 변경 · 재검토 필요')
            refs.append(reference(br))
        else:
            if (source.payload.get('text') or source.payload.get('full_text') or source.payload.get('body_text') or '')!=body:raise ValueError('원문 본문 변경')
        ref=reference(source);ph=pr.payload_hash
    return propose(service,dict(project_id=project['id'],project_hash=ph,project_name=project['name'],stage=event['stage'],
        document_id=doc['id'],title=doc['title'],url=doc['evidence_url'],source_ref=ref,related_refs=refs,
        identity_confirmed=identity,human_hold=human_hold,origin='AI_STAGE_REVIEW',
        proposed={k:event[k] for k in ('event_date','units','date_basis','precision','scope')},
        proof=dict(body=body,date_quote=event['date_quote'],units_quote=event['units_quote'],issues=event['issues'])))



def refresh_selected_sources(service,projects,profiles):
    """Existing business/permit matches and raw construction changes use the same inbox."""
    with service.sessions() as db:
        links=list(db.scalars(select(Revision).where(Revision.kind=='stage_evidence',Revision.superseded_at.is_(None))))
        ids={r.payload.get('selected',{}).get('source_entity_id') for r in links if r.payload.get('selected')}
        source_rows={r.entity_id:r for r in db.scalars(select(Revision).where(Revision.entity_id.in_(list(ids)),Revision.superseded_at.is_(None)))} if ids else {}
    count=0
    for link in links:
        b=link.payload;f=b.get('selected') or {};project=projects.get(b.get('project_id'));source=source_rows.get(f.get('source_entity_id'));stage=b.get('stage')
        if not project or not source or stage not in STAGES or b.get('status') not in ('CONFIRMED','REVIEW'):continue
        if not f.get('event_date') or f.get('method') in ('PREREQUISITE','STAGE_INFERENCE'):continue
        invalid_source=f.get('source_revision_no') is None or f['source_revision_no']!=source.revision_no
        profile=profiles.get(project.entity_id);old=(profile.payload if profile else {}).get('progress',{}).get(stage,{})
        if old and not old.get('inferred') and old.get('event_date')==f['event_date'] and old.get('units')==f.get('units'):continue
        if profile and max(link.recorded_at,source.recorded_at)<=profile.recorded_at:continue
        guard=dict(kind=link.kind,id=link.entity_id,hash=digest({k:b.get(k) for k in ('selected','status')}),selection=True)
        value=dict(project_id=project.entity_id,stage=stage,url=f.get('evidence_url',''),title=project.payload['name'],source_ref=reference(source),related_refs=[guard],
            identity_confirmed=b.get('status')=='CONFIRMED',human_hold=b.get('status')!='CONFIRMED',invalid_source=invalid_source,origin='SELECTED_STAGE_SOURCE',
            proposed=dict(event_date=f['event_date'],units=f.get('units'),date_basis='EVENT',precision='DAY' if len(f['event_date'])==10 else 'UNKNOWN',scope='PARTIAL' if f.get('scope_partial') else 'WHOLE_PROJECT'),
            proof=dict(body='',date_quote=f.get('basis',''),units_quote=f.get('scope_label',''),issues=[]))
        count+=not propose(service,value).get('unchanged',False)
    for project in projects.values():
        profile=profiles.get(project.entity_id);f=project.payload;when=f.get('start_actual_date')
        if not when or (profile and project.recorded_at<=profile.recorded_at):continue
        old=(profile.payload if profile else {}).get('progress',{}).get('CONSTRUCTION',{})
        if not old or old.get('event_date')==when:continue
        value=dict(project_id=project.entity_id,stage='CONSTRUCTION',url=f.get('evidence_url',''),title=f['name'],source_ref=reference(project),
            identity_confirmed=True,human_hold=False,origin='PROJECT_SOURCE',
            proposed=dict(event_date=when,units=None,date_basis='EVENT',precision='DAY' if len(when)==10 else 'UNKNOWN',scope='UNKNOWN'),
            proof=dict(body='',date_quote='원천 실제 착공일: '+when,units_quote='목표량을 실적 물량으로 전용하지 않습니다',issues=[]))
        count+=not propose(service,value).get('unchanged',False)
    return count
