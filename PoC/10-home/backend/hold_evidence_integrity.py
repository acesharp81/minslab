"""Reproducible, redacted hold exports. Integrity checks never approve business facts."""
import hashlib
import re
from collections import defaultdict
from sqlalchemy import select, tuple_
from .db import Revision
from .publication_evidence import redact, safe_value
from .publication_review_export import cell

VERSION='HOLD_EXPORT_UTF8_V2'
KINDS={'document_evidence','publication_supplement','ai_publication_analysis','publication_assessment',
       'publication_review','stage_proposal','stage_evidence','project','project_profile','evidence_bridge'}
METADATA=('name','title','project_id','document_id','address','region','municipality','district','block',
          'notice_no','project_no','developer','housing_management_no','announcement_no','source_object_id','source_notice_round','source_name','source_entity_id','source_revision_no','base_date',
          'raw_sha256','evidence_url','url','source_date','planned_units','stage','status','selected','facts','proposed')

def sha(value):return hashlib.sha256(value.encode('utf-8')).hexdigest()
def exported_text(value):return cell(redact(value))

def quote_check(body,quote):
    """Whitespace-only recovery, with offsets into the exact exported body."""
    quote=redact(quote);start=body.find(quote) if quote.strip() else -1
    status='EXACT' if start>=0 else 'MISSING_BODY' if not body else 'NOT_FOUND'
    end=start+len(quote) if start>=0 else None
    if start<0 and quote.strip() and body:
        indices=[i for i,c in enumerate(body) if not c.isspace()]
        compact=''.join(body[i] for i in indices);needle=''.join(quote.split());pos=compact.find(needle)
        if needle and pos>=0:
            start=indices[pos];end=indices[pos+len(needle)-1]+1;status='WHITESPACE_ONLY'
    if start<0 and len(quote)>2 and (quote[0],quote[-1]) in [('\"','\"'),('“','”'),('‘','’')]:
        inner=quote_check(body,quote[1:-1])
        if inner['anchor']:
            start=inner['anchor']['start'];end=inner['anchor']['end'];status='QUOTE_DELIMITERS_ONLY'
    anchor=None if start<0 else dict(start=start,end=end,offset_unit='UNICODE_CODEPOINT',end_exclusive=True,
        line=body.count('\n',0,start)+1,page=None,matched_text=body[start:end])
    return dict(quote=quote,status=status,exact=status=='EXACT',whitespace_normalized=status in ('EXACT','WHITESPACE_ONLY'),
                anchor=anchor,body_sha256=sha(body),verification_scope='EXPORTED_STORED_TEXT_ONLY',
                unverifiable_reason=None if anchor else '본문 미확보' if not body else '현재 본문에서 재현되지 않음 · 다른 판본/첨부 대조 필요')

def references(result):
    return [r for r in [result.get('source_ref'),result.get('body_ref'),*result.get('related_refs',[]),*result.get('body_refs',[])] if r and r.get('kind') in KINDS]

def load_registry(service,refs):
    ids={r['id'] for r in refs if r.get('kind') in KINDS}
    history=defaultdict(list)
    if ids:
        # Fetch current and explicitly requested versions only. Collectors can
        # retain thousands of historical records for one ID; never materialize
        # all of them just to resolve one old citation.
        with service.sessions() as db:
            rows=list(db.scalars(select(Revision).where(Revision.entity_id.in_(ids),Revision.superseded_at.is_(None))))
            present={(r.entity_id,r.revision_no) for r in rows}
            pinned={(r['id'],r['revision_no']) for r in refs if r.get('revision_no') and r.get('kind') in KINDS}-present
            if pinned:
                rows+=list(db.scalars(select(Revision).where(tuple_(Revision.entity_id,Revision.revision_no).in_(pinned))))
            unversioned={(r['id'],r['hash']) for r in refs if not r.get('revision_no') and r.get('hash') and not r.get('selection') and r.get('kind') in KINDS}
            if unversioned:
                rows+=list(db.scalars(select(Revision).where(tuple_(Revision.entity_id,Revision.payload_hash).in_(unversioned))))
            for r in {r.id:r for r in rows}.values():
                if r.kind in KINDS:history[(r.kind,r.entity_id)].append(r)
    return history

def resolve(ref,registry):
    rows=registry.get((ref['kind'],ref['id']),[])
    current=next((r for r in rows if r.superseded_at is None),None)
    def matches(r):
        if ref.get('selection'):
            from .stage_reconciliation import digest
            return digest({k:r.payload.get(k) for k in ('selected','status')})==ref.get('hash')
        return r.payload_hash==ref.get('hash')
    pinned=next((r for r in rows if r.revision_no==ref.get('revision_no')),None) if ref.get('revision_no') else next((r for r in rows if matches(r)),None)
    verified=bool(pinned and matches(pinned))
    body=(pinned.payload.get('body_text') or pinned.payload.get('text') or pinned.payload.get('full_text') or (pinned.payload.get('proof') or {}).get('body') or '') if verified else ''
    body=exported_text(body)
    raw=(pinned.payload.get('raw') or {}) if verified else {}
    artifact_sha=(pinned.payload.get('raw_sha256') or raw.get('sha256')) if verified else None
    return dict(artifact_ref=dict(sha256=artifact_sha,storage='raw/ai_publication/'+artifact_sha+'.raw' if artifact_sha and re.fullmatch('[a-f0-9]{64}',artifact_sha) else None,
        availability='NOT_CHECKED',note='보관 원본 위치. 저장 본문 해시와 구분하며 관리자 증거대장에서 파일 유무 확인'),requested_ref=ref,status='PINNED_REVISION_MATCHED' if verified else 'HASH_MISMATCH' if pinned else 'REVISION_MISSING',
        current_ref=dict(kind=current.kind,id=current.entity_id,revision_no=current.revision_no,hash=current.payload_hash) if current else None,
        current_matches=bool(current and matches(current)),selected_revision_id=pinned.id if pinned else None,
        selected_payload_sha256=pinned.payload_hash if pinned else None,
        metadata=safe_value({k:pinned.payload[k] for k in METADATA if k in pinned.payload}) if verified else {},
        body=body,exported_body_sha256=sha(body),hash_basis='body · UTF-8 · 비식별/CSV 수식보호 이후',
        unverifiable_reason=None if verified and body else '구조화 근거만 저장됨 · 원문 전체 별도 확보 필요' if verified else '지정 판본과 해시 재현 실패',
        business_identity_verified=False,metric_approved=False)

def package(row,group,registry):
    result=row.get('result') or {};raw=row.get('body_text') or '';body=exported_text(raw)
    value=dict(safe_value(result.get('evidence_package') or {}))
    refs=references(dict(result,body_ref=row.get('body_ref') or result.get('body_ref'),body_refs=row.get('body_refs',[])));entries=[resolve(r,registry) for r in refs]
    checks=[quote_check(body,q) for q in row.get('evidence',[]) if isinstance(q,str) and q.strip()]
    alternatives=[]
    for member in group:
        candidate=exported_text(member.get('body_text') or '')
        if candidate and candidate!=body:
            alternatives.append(dict(role=member.get('role'),source_revision_no=member.get('body_source_revision_no'),
                                     requested_ref=member.get('body_ref') or (member.get('result') or {}).get('body_ref'),body_sha256=sha(candidate),quote_checks=[quote_check(candidate,q) for q in row.get('evidence',[]) if isinstance(q,str) and q.strip()]))
    for entry in entries:
        if entry['body'] and entry['body']!=body:
            alternatives.append(dict(role='SAVED_'+entry['requested_ref']['kind'],source_revision_no=entry['requested_ref'].get('revision_no'),
                requested_ref=entry['requested_ref'],body_sha256=entry['exported_body_sha256'],quote_checks=[quote_check(entry['body'],q) for q in row.get('evidence',[]) if isinstance(q,str) and q.strip()]))
    for check in checks:
        check['other_agent_body_matches']=[dict(role=a['role'],source_revision_no=a['source_revision_no'],body_sha256=a['body_sha256'],
            requested_ref=a.get('requested_ref'),anchor=c['anchor'],match_status=c['status']) for a in alternatives
            for c in a['quote_checks'] if c['quote']==check['quote'] and c['anchor']]
        check['direct_evidence_verified']=check['exact']
        check['cause_classification']=('CURRENT_BODY_EXACT' if check['exact'] else 'NORMALIZATION_ONLY' if check['anchor'] else
            'OTHER_STORED_VERSION' if check['other_agent_body_matches'] else 'MISSING_BODY' if not body else 'UNRESOLVED_NOT_VERBATIM')
        check['business_fact_verified']=False
    old=(row.get('cross_review') or {}).get('refs',[])
    current_refs={(e['current_ref']['kind'],e['current_ref']['id']):e['current_ref'] for e in entries if e['current_ref']}
    transitions=[dict(previous_ref=r,current_ref=current_refs.get((r['kind'],r['id'])),changed=r.get('hash')!=current_refs[(r['kind'],r['id'])]['hash'])
        for r in old if (r['kind'],r['id']) in current_refs]
    selected=result.get('source_ref') or row.get('body_ref')
    prior=(row.get('cross_review') or {}).get('selected_source_ref')
    previous_current=next((r for r in old if selected and r['id']==selected['id'] and r['kind']==selected['kind']),None)
    compare=lambda a,b: all(a.get(k)==b.get(k) for k in ('kind','id','revision_no','hash'))
    reference_validation=dict(selected_ref=selected,previous_selected_ref=prior,previous_review_current_ref=previous_current,
        selected_comparison='UNCHANGED' if prior and selected and compare(prior,selected) else 'CHANGED' if prior and selected else 'PREVIOUS_SELECTED_REF_NOT_RECORDED',
        previous_review_current_comparison='UNCHANGED' if previous_current and compare(previous_current,selected) else 'DIFFERS' if previous_current else 'NO_PRIOR_REFERENCE',
        pinned_references_verified=bool(entries) and all(e['status']=='PINNED_REVISION_MATCHED' for e in entries),
        current_drift_refs=[e['requested_ref'] for e in entries if not e['current_matches']],
        business_revalidation_required=bool((row.get('cross_review') or {}).get('evidence_revalidation_required')),
        note='과거 검토의 당시 최신 참조와 당시 선택 참조는 다를 수 있음. 추가 증빙 필요 표시는 판본 변경 판정과 별개.')
    events=[]
    for entry in entries:
        for index,fact in enumerate(entry['metadata'].get('facts') or []):
            if fact.get('kind')!='ACTUAL' or result.get('stage') and fact.get('stage')!=result['stage']:continue
            observation=fact.get('date_basis')=='OBSERVED_BY' or fact.get('milestone')=='OBSERVED_BY'
            events.append(dict(source_ref=entry['requested_ref'],fact_index=index,stage=fact.get('stage'),
                stored_date=fact.get('date'),event_date=None if observation else fact.get('date'),
                observed_on=fact.get('date') if observation else None,event_type=fact.get('milestone') or 'UNCLASSIFIED',
                units=fact.get('units'),scope=fact.get('scope_label'),basis=fact.get('basis'),
                verification='STORED_ASSERTION_ONLY',merge_authorized=False))
    value.update(schema_version=VERSION,source_url=row.get('url'),source_revision_no=row.get('source_revision_no'),
        body_origin=row.get('body_origin','단계 제안 저장 본문' if row['subject'].startswith('STA_') else 'AI 수집'),
        body_source_revision_no=row.get('body_source_revision_no'),
        body_current=row.get('body_source_revision_no')==row.get('source_revision_no') if row.get('body_source_revision_no') else None,
        body=body,stored_body_sha256=sha(raw),redacted_body_sha256=sha(redact(raw)),exported_body_sha256=sha(body),
        hash_basis=dict(field='수집본문',encoding='UTF-8',normalization_version=VERSION,formula_escaped=cell(redact(raw))!=redact(raw),
            stages=['저장 본문','개인정보 비식별·개행 정규화','CSV 수식보호'],
            raw_artifact_sha256=next((e['metadata'].get('raw_sha256') for e in entries if e['requested_ref']['id']==(row.get('body_ref') or result.get('body_ref') or {}).get('id')),None)),
        quote_checks=checks,evidence_registry=entries,reference_transitions=transitions,
        business_status=row.get('business_status'),agent_state=row.get('state'),metric_approved=False,
        business_decision_trace=safe_value(row.get('business_decision_trace') or {}),reference_validation=reference_validation,
        structured_events=events,
        approval_gates=dict(policy_relevant=None,policy_target_included=None,policy_performance_attributed=False,
            project_identity_asserted=result.get('identity_confirmed'),project_identity_verified=None,stage_event_verified=None,
            metric_scope_verified=None,human_approved=None,auto_eligible=bool(result.get('auto_eligible')),
            evaluation_scope='EXPORT_INTEGRITY_ONLY',note='None은 이 증빙 검사에서 미판정. 기존 업무 승인과 별개이며 원천 승인 상태는 분석결과_JSON 참조.'),
        can_apply_note='can_apply는 형식상 수동 검토 가능 여부이며 승인 아님. auto_eligible·동일성·원문·담당자 보류·선후관계는 별도 검사.',
        unverifiable_reason=None if body else '저장 원문 본문 미확보 · 원인과 재수집 결과는 교차검토 기록 참조',
        note='저장 판본/인용의 기계적 재검증 · 외부 원문 재조회·사업 동일성·실적 승인을 뜻하지 않음')
    return value
