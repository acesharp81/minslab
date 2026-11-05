"""Read-only evidence projections. References point to existing immutable revisions.

Export hashes describe exported UTF-8 strings, not private pre-redaction text.
No classification here approves a project, creates a fact or adds metric units.
"""
import hashlib
import json
import re
from urllib.parse import urlsplit

NORMALIZATION='PUBLICATION_EXPORT_REDACT_V3'
BODY_FIELDS={'SOURCE':'수집본문','MANUAL':'수동수집본문','AI':'AI수집본문'}

def sha(text):return hashlib.sha256(str(text).encode('utf-8')).hexdigest()
def identifier(prefix,*parts):return prefix+'_'+sha(json.dumps(parts,ensure_ascii=False,sort_keys=True))[:24]

def body_kind(body,quality,title='',url=''):
    t=re.sub(r'\s+',' ',body).strip()
    listing=(bool(re.search(r'총\s*[\d,]+\s*건.*(?:현재페이지|전체페이지)',t)) and
             bool(re.search(r'번호.{0,20}제목.{0,30}(?:등록일|작성일|담당부서)',t)))
    if listing:return 'LIST_PAGE','MISMATCH','게시물 목록을 상세 본문으로 사용할 수 없음'
    if quality=='BOILERPLATE':return 'PORTAL_SHELL','UNVERIFIED','메뉴·게시판 껍데기'
    if quality=='SUMMARY_ONLY':return 'SUMMARY','UNVERIFIED','요약은 상세·첨부 완전성 확인과 별개'
    if quality in ('MISSING','INSUFFICIENT'):return 'UNKNOWN','UNVERIFIED','분석 가능한 본문 미확보'
    norm=lambda v:re.sub(r'[^가-힣a-z0-9]','',v.lower())
    matched=bool(title and norm(title) in norm(t))
    kind='ATTACHMENT_TEXT' if urlsplit(url).path.lower().endswith(('.pdf','.hwpx','.hwp')) else 'DETAIL_PAGE' if matched else 'TEXT_EXTRACT'
    return kind,'TITLE_MATCHED' if matched else 'UNVERIFIED','제목 문자열 대조이며 법정 사업 동일성 확정 아님'

def assessment_sync(item,assessment,source_hash=None):
    reasons=[]
    if assessment:
        if assessment.get('source_revision_no')!=item['source_revision_no']:reasons.append('SOURCE_REVISION_CHANGED')
        if assessment.get('review_revision_no')!=item['review_revision_no']:reasons.append('REVIEW_REVISION_CHANGED')
        if source_hash and assessment.get('source_hash')!=source_hash:reasons.append('SOURCE_HASH_CHANGED')
    return reasons

def export_anchor(body,quote,redacted):
    """Map an exact original quote through whole-body redaction, including cuts
    inside email/roster spans. Never export a truncated private token as a quote.
    Offsets are Python/Unicode code points, end-exclusive, in exported text.
    """
    start=body.find(quote) if quote else -1
    if start<0:return None
    end=start+len(quote)
    # Redact with full token context. A stored quote can end midway through an
    # email; redacting that fragment alone leaks a prefix and cannot be located.
    from .publication_evidence import redact
    lo,hi=start,end
    for match in re.finditer(r'[\w.+-]+@[\w.-]+|(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)|(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)',body):
        if match.start()<hi and match.end()>lo:
            lo=min(lo,match.start());hi=max(hi,match.end())
    exported=redact(body[lo:hi])
    if not exported:return None
    expected=len(redact(body[:lo]))
    pos=redacted.find(exported,max(0,expected-1))
    if pos<0:pos=redacted.find(exported)
    if pos<0:return None
    return dict(start=pos,end=pos+len(exported),quote=exported,original_start=start,original_end=end,
                redaction_context_expanded=(lo!=start or hi!=end))

def relation_projection(relations,event_group):
    mapping={'CORRECTION_OF':'REVISION_OF','FOLLOWUP_SAME_NOTICE':'FOLLOW_UP_TO',
             'SAME_RECRUITMENT':'SAME_RECRUITMENT_ROUND','SAME_EVENT':'SAME_EVENT_CANDIDATE',
             'SAME_PLANNING_EVENT':'SAME_PROJECT_EVENT_CANDIDATE','RELATED_SITE_VISIT':'RELATED_POLICY'}
    return [dict(r,relation_type=r.get('relation_type') or mapping.get(r.get('relation'),'RELATED_DOCUMENT'),
                 recruitment_group_id=event_group,document_identity_confirmed=False,
                 duplicate_publication_confirmed=False,aggregate_allowed=False,
                 relation_note='사건군·대표문서는 문서 동일성 또는 중복 실적 승인 아님') for r in relations]

def decorate_facts(item,assessment,candidates,raw_bodies,source_hash,current,redact):
    from .publication_evidence import safe_value
    result=[];by_origin={c['origin']:c for c in candidates}
    aref=assessment.get('evidence_ref',{})
    for i,original in enumerate(assessment.get('facts',[])):
        f=safe_value(original);c=by_origin.get(f.get('source_type'),{});body=raw_bodies.get(f.get('source_type'),'')
        hash_match=bool(body and original.get('body_sha256')==sha(body))
        anchor=export_anchor(body,original.get('quote',''),c.get('text','')) if hash_match else None
        status='QUOTE_MATCHED' if current and hash_match and anchor else 'NEEDS_REVALIDATION' if not current else 'QUOTE_MISMATCH'
        eid=identifier('EV',item['id'],aref.get('revision_id') or assessment.get('assessment_revision_no'),i,original.get('body_sha256'),original.get('quote'))
        f.update(evidence_id=eid,document_id=item['id'],claim_id=identifier('CLAIM',item['id'],i,{k:original.get(k) for k in ('kind','value','unit','scope','stage','temporality','quote')}),
                 source_revision_id=item.get('source_revision_id') if original.get('source_revision_no',assessment.get('source_revision_no'))==item['source_revision_no'] else None,assessment_revision_id=aref.get('revision_id'),
                 evidence_revision_id=c.get('evidence_revision_id'),artifact_id=c.get('artifact_id'),
                 stored_body_sha256=original.get('body_sha256'),body_sha256=c.get('sha256') if hash_match else None,
                 hash_input_field=c.get('hash_input_field'),normalization_version=NORMALIZATION,
                 original_quote_sha256=sha(original.get('quote','')),quote_anchor=None,
                 verification_status=status,verified_at=assessment.get('assessed_at'),verified_by_role='OFFICER_ASSISTED_REVIEW',
                 verification_method='原文 판본·저장 본문 해시·정확 인용 및 내보내기 위치 재현'.replace('原文','원문'),
                 evidence_role={'QUANTITY':'QUANTITY','DATE':'SCHEDULE','CONTEXT':'CONTEXT'}.get(f.get('kind'),'CONTEXT'),
                 linked_project_ids=(item.get('decision') or {}).get('project_ids',[]) if item['status']=='APPROVED' else [],
                 aggregate_allowed=False,metric_approval_status='NOT_APPROVED',
                 source_corroborated=False,supersedes_evidence_id=None,subset_of_claim_id=None)
        if anchor:
            f['quote']=anchor['quote'];f['quote_anchor']={k:v for k,v in anchor.items() if k!='quote'}
            f['quote_anchor'].update(offset_unit='UNICODE_CODEPOINT',end_exclusive=True,page=None,table=None)
        else:f['quote']=redact(original.get('quote',''))
        result.append(f)
    for f in result:
        if f.get('scope') in ('RENTAL_SUBSET_OF_TOTAL','EQUITY_SUBSET_OF_TOTAL'):
            parents=[p for p in result if p.get('scope') in ('PROJECT_PLANNED_TOTAL','BLOCK_PLANNED_TOTAL') and p.get('unit')==f.get('unit')]
            if len(parents)==1:f['subset_of_claim_id']=parents[0]['claim_id']
        f['quantity_role']='IDENTIFIER' if f.get('scope')=='ROOM_IDENTIFIER' else 'SUBSET' if f.get('subset_of_claim_id') else 'PLANNED_TOTAL' if 'PLANNED_TOTAL' in f.get('scope','') else 'RECRUITMENT' if f.get('scope')=='EXISTING_STOCK_RECRUITMENT' else None
    return result
