"""Revision-pinned officer findings and conservative evidence for review exports.

These records never create project, policy, quantity or achievement events.
"""
import hashlib
import re
from sqlalchemy import select
from .db import Revision, Audit, now, upsert_revision, entity_id

KIND='publication_assessment'


def load(service, ids):
    if not ids:return {}
    with service.sessions() as db:
        return {r.payload['document_id']:dict(r.payload,assessment_revision_no=r.revision_no,evidence_ref=dict(id=r.entity_id,revision_id=r.id,revision_no=r.revision_no,hash=r.payload_hash,recorded_at=r.recorded_at.isoformat()))
                for r in db.scalars(select(Revision).where(Revision.kind==KIND,
                    Revision.superseded_at.is_(None),Revision.payload['document_id'].as_string().in_(ids)))}


def save(service, document_id, source_revision_no, review_revision_no, payload):
    from .publication_reviews import KIND as REVIEW_KIND, OWNER
    with service.sessions.begin() as db:
        doc=db.scalar(select(Revision).where(Revision.kind=='document_evidence',Revision.entity_id==document_id,
            Revision.superseded_at.is_(None)).with_for_update())
        review=db.scalar(select(Revision).where(Revision.entity_id==entity_id(REVIEW_KIND,OWNER,document_id),
            Revision.superseded_at.is_(None)).with_for_update())
        if not doc or doc.revision_no!=source_revision_no or (review.revision_no if review else 0)!=review_revision_no:
            raise ValueError('원문 또는 담당자 판단 판본 변경 · 다시 대조하세요')
        if not payload.get('actor') or not payload.get('reason'):raise ValueError('확인 담당자와 사유가 필요합니다')
        if review and review.payload.get('source_revision_no') != source_revision_no:
            raise ValueError('현재 원문에 대한 담당자 판단을 먼저 저장하세요')
        from .publication_supplements import load as load_manual
        from .ai_collection import annotations
        sources={'SOURCE':doc.payload,'MANUAL':load_manual(service,[document_id]).get(document_id,{}),
                 'AI':annotations(service,[document_id]).get(document_id,{})}
        for fact in payload.get('facts',[]):
            origin=fact.get('source_type'); source=sources.get(origin,{})
            body=(source.get('text') or source.get('full_text') or source.get('body_text') or '') if origin=='SOURCE' else source.get('body_text','')
            quote=fact.get('quote','')
            if not quote or quote not in body or (origin!='SOURCE' and source.get('source_revision_no')!=source_revision_no):
                raise ValueError('현재 판본 본문과 일치하는 근거 인용이 필요합니다')
            if fact.get('body_sha256')!=hashlib.sha256(body.encode()).hexdigest():
                raise ValueError('검증 본문 해시가 변경됐습니다')
            if text_quality(body,doc.payload.get('name','')) in ('MISSING','INSUFFICIENT','BOILERPLATE'):
                raise ValueError('상세 대상 본문이 아닌 목록·부족 본문은 근거 검증에 사용할 수 없습니다')
            if text_quality(body,doc.payload.get('name',''))=='SUMMARY_ONLY' and fact.get('kind')!='CONTEXT':
                raise ValueError('요약만 있는 자료는 수량·일정의 상세 근거 검증을 먼저 수행하세요')
            if fact.get('kind') not in ('CONTEXT','QUANTITY','DATE') or fact.get('temporality') not in ('REFERENCE','PLANNED','SCHEDULED','REPORTED_ACTUAL'):
                raise ValueError('사실 유형 및 계획·예정·보도된 사실 구분이 필요합니다')
            if fact['kind']=='QUANTITY' and (not fact.get('unit') or not fact.get('scope')):
                raise ValueError('수치의 단위와 집계 범위가 필요합니다')
            if fact.get('aggregate_allowed') is not False:
                raise ValueError('검토 근거는 실적 집계에 자동 반영할 수 없습니다')
        data=dict(payload,document_id=document_id,source_revision_no=source_revision_no,
            review_revision_no=review_revision_no,source_hash=doc.payload_hash,
            assessed_at=now().isoformat(),effect='검토 근거·사건 관계 기록 · 사업·정책·물량·실적 자동 반영 없음')
        # Idempotent replay of a checked report must not append duplicate decisions.
        old=db.scalar(select(Revision).where(Revision.kind==KIND,Revision.entity_id==entity_id(KIND,'officer_evidence',document_id),
            Revision.superseded_at.is_(None)))
        if old and all(old.payload.get(k)==v for k,v in data.items() if k!='assessed_at'):
            return dict(id=old.entity_id,revision_no=old.revision_no,outcome='unchanged')
        row,outcome=upsert_revision(db,KIND,'officer_evidence',document_id,data,'officer-evidence-review')
        db.add(Audit(entity_id=row.entity_id,action='PUBLICATION_EVIDENCE_REVIEW',before=old.payload if old else {},after=data))
        return dict(id=row.entity_id,revision_no=row.revision_no,outcome=outcome)


def redact(text):
    """Suppress personal contact/identifier and roster rows in exported evidence."""
    value=str(text or '')
    # A complete SHA-256 is technical provenance, not a contact/identity number.
    # Recursive export redaction also visits digest fields and must preserve them.
    if re.fullmatch(r'[0-9a-fA-F]{64}',value):return value
    value=re.sub(r'(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)','[개인식별번호 제외]',value)
    value=re.sub(r'(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)','[개인 연락처 제외]',value)
    value=re.sub(r'[\w.+-]+@[\w.-]+','[이메일 제외]',value)
    lines=[];roster=False
    for line in value.splitlines():
        if (re.search(r'(?:성명|당첨자명|신청자명|입주자명|생년월일)',line) and re.search(r'[|\t]',line)) or re.fullmatch(r'\s*(?:성명|당첨자명|신청자명|입주자명|생년월일)\s*',line):
            roster=True;lines.append('[개인 명단 영역 제외]');continue
        if roster:
            if not line.strip():roster=False
            elif re.search(r'(?:계약|신청|입주)\s*(?:기간|일정|방법)|^\d+[.)]\s',line):roster=False
            else:continue
        lines.append(line)
    return '\n'.join(lines).rstrip('\n')


def safe_value(value):
    if isinstance(value,str):return redact(value)
    if isinstance(value,list):return [safe_value(v) for v in value]
    if isinstance(value,dict):return {k:safe_value(v) for k,v in value.items() if k not in ('persons','applicants','winners','resident_registration_number')}
    return value


def text_quality(text, title=''):
    t=re.sub(r'\s+',' ',str(text or '')).strip()
    if not t:return 'MISSING'
    if re.search(r'총\s*[\d,]+\s*건.*(?:현재페이지|전체페이지)',t) and re.search(r'번호.{0,20}제목.{0,30}(?:등록일|작성일|담당부서)',t):return 'BOILERPLATE'
    if re.match(r'^이\s*시간\s*핫\s*뉴스',t):return 'BOILERPLATE'
    if len(t)<60:return 'INSUFFICIENT'
    if '공고 및 공지는 서울주택' in t and ('본문 바로가기' in t or '우리 아파트 찾기' in t):return 'BOILERPLATE'
    if len(t)<300 and t.count(' - ')>=3 and '□' not in t:return 'SUMMARY_ONLY'
    if ('분야선택' in t and '보도자료' in t and '검색' in t and '본문 내용 바로가기' in t):return 'BOILERPLATE'
    if ('K-Artprice' in t and '프라임뉴시스' in t and not re.search(r'기자\s*=',t)):return 'BOILERPLATE'
    if '본문 내용 바로가기' in t and '청약' in t and '사이트맵' in t:return 'BOILERPLATE'
    if len(t)<240 and ('*재판매 및 DB 금지' in t or ('복사완료' in t and '입력' in t)):return 'INSUFFICIENT'
    # Common fallback responses contain only sharing controls or a board shell.
    shell=('페이스북','트위터','카카오','공유하기','URL 복사','로그인','전체메뉴')
    if len(t)<500 and sum(w in t for w in shell)>=3:return 'BOILERPLATE'
    substantive=re.sub(r'\s+','',t)
    title_norm=re.sub(r'\s+','',title or '')
    if title_norm and substantive==title_norm:return 'INSUFFICIENT'
    if ('기사본문' not in t and sum(t.count(w) for w in shell)>=8 and len(t)<1500):return 'BOILERPLATE'
    return 'TEXT_AVAILABLE_UNVERIFIED'


def evidence(item, source, manual, ai, assessment, csv_mode=False):
    from .publication_evidence_integrity import (sha, body_kind, assessment_sync, decorate_facts,
        relation_projection, NORMALIZATION, BODY_FIELDS, identifier)
    revision=item['source_revision_no'];candidates=[];raw_bodies={}
    for origin,data in [('SOURCE',source),('MANUAL',manual),('AI',ai)]:
        body=(source.get('text') or source.get('full_text') or source.get('body_text') or '') if origin=='SOURCE' else data.get('body_text','')
        raw_bodies[origin]=body
        rev=revision if origin=='SOURCE' else data.get('source_revision_no')
        quality=text_quality(body,item['title']);current=rev==revision
        kind,target,reason=body_kind(body,quality,item['title'],item.get('evidence_url',''))
        if kind=='LIST_PAGE':quality='BOILERPLATE'
        text=redact(body)
        if csv_mode:
            from .publication_review_export import cell
            text=cell(text)
        ref=data.get('evidence_ref',{})
        raw_hash=data.get('original_sha256') or data.get('raw_sha256') or (data.get('raw') or {}).get('sha256')
        candidates.append(dict(origin=origin,source_revision_no=rev,current=current,quality=quality,
            chars=len(body),exported_chars=len(text),stored_text_sha256=sha(body) if body else None,
            sha256=sha(text) if body else None,exported_text_sha256=sha(text) if body else None,
            hash_input_field=BODY_FIELDS[origin],hash_encoding='UTF-8',normalization_version=NORMALIZATION,csv_formula_escaped=csv_mode,
            hash_timestamp=data.get('collected_at') or ref.get('recorded_at'),
            evidence_revision_id=ref.get('revision_id'),evidence_ref=ref,raw_sha256=raw_hash,
            artifact_id=('SHA256:'+raw_hash) if raw_hash else None,
            collected_at=data.get('collected_at'),document_kind=kind,target_match=target,target_note=reason,
            fragment_requires_detail_resolution=bool('#' in item.get('evidence_url','') and origin=='AI' and kind in ('LIST_PAGE','PORTAL_SHELL')),
            text=text))
    eligible=[c for c in candidates if c['current'] and c['quality'] in ('TEXT_AVAILABLE_UNVERIFIED','SUMMARY_ONLY') and c['target_match']!='MISMATCH']
    chosen=next((c for quality in ('TEXT_AVAILABLE_UNVERIFIED','SUMMARY_ONLY') for origin in ('MANUAL','SOURCE','AI') for c in eligible if c['origin']==origin and c['quality']==quality),None)
    quality=chosen['quality'] if chosen else 'STALE_ONLY' if any(c['chars'] and not c['current'] for c in candidates) else 'INSUFFICIENT' if any(c['chars'] for c in candidates) else 'MISSING'
    reasons=assessment_sync(item,assessment,item.get('source_hash'))
    hashes={c['origin']:c['stored_text_sha256'] for c in candidates if c['current']}
    for f in assessment.get('facts',[]):
        if f.get('body_sha256')!=hashes.get(f.get('source_type')):reasons.append('BODY_HASH_CHANGED')
        elif not f.get('quote') or f['quote'] not in raw_bodies.get(f.get('source_type'),''):reasons.append('QUOTE_MISMATCH')
    assessment_current=bool(assessment and not reasons)
    all_facts=decorate_facts(item,assessment,candidates,raw_bodies,item.get('source_hash'),assessment_current,redact)
    if assessment_current and any(f['verification_status']!='QUOTE_MATCHED' for f in all_facts):
        reasons.append('QUOTE_EXPORT_UNAVAILABLE');assessment_current=False
    facts=all_facts if assessment_current else []
    historical=dict(safe_value(assessment),facts=all_facts,current=assessment_current,needs_revalidation=bool(reasons),revalidation_reasons=sorted(set(reasons))) if assessment else {}
    stage_names=('CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN')
    dates=[f for f in facts if f.get('kind')=='DATE']
    related=relation_projection(safe_value(assessment.get('related_documents',[])),assessment.get('event_group')) if assessment_current else []
    linkage=bool(item['status']=='APPROVED' and not item.get('source_changed') and not item.get('link_changed') and (item.get('decision') or {}).get('project_ids'))
    text=chosen['text'] if chosen else ''
    attachments=[]
    for origin,data in [('SOURCE',source),('MANUAL',manual),('AI',ai)]:
        for a in data.get('attachments') or (data.get('raw') or {}).get('attachments') or []:
            attachments.append(dict(a,origin=origin,file_state=a.get('file_state') or ('UNVERIFIED' if a.get('sha256') else 'MISSING'),verification_status='UNVERIFIED'))
    result=dict(document_id=item['id'],source_revision_no=revision,source_revision_id=item.get('source_revision_id'),review_revision_no=item['review_revision_no'],
        effective_text=text,effective_origin=chosen['origin'] if chosen else None,
        effective_text_sha256=sha(text),hash_input_field='통합유효본문',normalization_version=NORMALIZATION,
        normalized_text=text,hash_encoding='UTF-8',quality=quality,
        raw_text_present=any(c['chars'] for c in candidates),usable_detail_body=bool(chosen and chosen['quality']=='TEXT_AVAILABLE_UNVERIFIED'),
        attachment_verified=False,attachment_verification_note='첨부 실물·텍스트 추출과 내용 검증 완료는 별도',
        attachment_inventory=attachments,attachment_inventory_state='PRESENT' if attachments else 'UNVERIFIED',
        attachment_absence_confirmed=False,
        quality_note='본문 유형·문자열·판본 기준 선별이며 첨부 완전성·사실·사업 동일성 확정은 별도 확인',
        candidates=candidates,assessment_current=assessment_current,needs_revalidation=bool(reasons),revalidation_reasons=sorted(set(reasons)),
        external_recommendation=safe_value(assessment.get('external_recommendation',{})),
        officer_assessment=historical,facts=facts,evidence_records=all_facts,
        evidence_set_id=identifier('ESET',item['id'],[f['evidence_id'] for f in all_facts]),
        stage_dates={stage:[f for f in dates if f.get('stage')==stage] for stage in stage_names},
        business_event_dates=[dict(f,event_type=f.get('stage') or 'UNCLASSIFIED') for f in dates],
        fact_coverage=dict(context=sum(f.get('kind')=='CONTEXT' for f in facts),quantity=sum(f.get('kind')=='QUANTITY' for f in facts),date=len(dates)),
        unknown_fields=assessment.get('unknown_fields',[]) if assessment_current else ['현재 판본의 담당자 구조화 사실 검증'],
        related_documents=related,event_group=assessment.get('event_group') if assessment_current else None,
        aggregate_allowed=False,aggregation_note='참고·모집·정정 사건. 별도 사업 실적 승인 전 합산 금지',
        linked_project_ids=(item.get('decision') or {}).get('project_ids',[]) if linkage else [],linkage_confirmed=linkage,
        verification_stages=dict(DISCOVERED=True,CAPTURED=bool(text),PARSED=bool(facts),QUOTE_MATCHED=bool(facts) and all(f['verification_status']=='QUOTE_MATCHED' for f in facts),
            SOURCE_CORROBORATED=False,PROJECT_MATCHED=linkage,APPROVED_FOR_LINK=linkage,APPROVED_FOR_METRIC=False),
        privacy_note='개인식별번호·개인 연락처·명단 영역 제외. 본문 전체 기준으로 인용을 비식별화하고 내보낸 텍스트의 해시·오프셋 제공')
    return result
