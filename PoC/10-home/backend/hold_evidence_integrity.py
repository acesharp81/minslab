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
          'notice_no','source_notice_round','source_name','source_entity_id','source_revision_no','base_date',
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
    return dict(requested_ref=ref,status='PINNED_REVISION_MATCHED' if verified else 'HASH_MISMATCH' if pinned else 'REVISION_MISSING',
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
                                     body_sha256=sha(candidate),quote_checks=[quote_check(candidate,q) for q in row.get('evidence',[]) if isinstance(q,str) and q.strip()]))
    for entry in entries:
        if entry['body'] and entry['body']!=body:
            alternatives.append(dict(role='SAVED_'+entry['requested_ref']['kind'],source_revision_no=entry['requested_ref'].get('revision_no'),
                body_sha256=entry['exported_body_sha256'],quote_checks=[quote_check(entry['body'],q) for q in row.get('evidence',[]) if isinstance(q,str) and q.strip()]))
    for check in checks:
        check['other_agent_body_matches']=[dict(role=a['role'],source_revision_no=a['source_revision_no'],body_sha256=a['body_sha256']) for a in alternatives
            if any(c['quote']==check['quote'] and c['anchor'] for c in a['quote_checks'])]
    old=(row.get('cross_review') or {}).get('refs',[])
    current_refs={(e['current_ref']['kind'],e['current_ref']['id']):e['current_ref'] for e in entries if e['current_ref']}
    transitions=[dict(previous_ref=r,current_ref=current_refs.get((r['kind'],r['id'])),changed=r.get('hash')!=current_refs[(r['kind'],r['id'])]['hash'])
        for r in old if (r['kind'],r['id']) in current_refs]
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
        can_apply_note='can_apply는 형식상 수동 검토 가능 여부이며 승인 아님. auto_eligible·동일성·원문·담당자 보류·선후관계는 별도 검사.',
        unverifiable_reason=None if body else '저장 원문 본문 미확보 · 원인과 재수집 결과는 교차검토 기록 참조',
        note='저장 판본/인용의 기계적 재검증 · 외부 원문 재조회·사업 동일성·실적 승인을 뜻하지 않음')
    return value
