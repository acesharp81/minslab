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
        return {r.payload['document_id']:dict(r.payload,assessment_revision_no=r.revision_no)
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
    value=re.sub(r'(?<!\d)\d{6}[- ]?[1-4]\d{6}(?!\d)','[개인식별번호 제외]',value)
    value=re.sub(r'(?<!\d)01[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)','[개인 연락처 제외]',value)
    value=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[이메일 제외]',value)
    lines=[];roster=False
    for line in value.splitlines():
        if (re.search(r'(?:성명|당첨자명|신청자명|입주자명|생년월일)',line) and re.search(r'[|\t]',line)) or re.fullmatch(r'\s*(?:성명|당첨자명|신청자명|입주자명|생년월일)\s*',line):
            roster=True;lines.append('[개인 명단 영역 제외]');continue
        if roster:
            if not line.strip():roster=False
            elif re.search(r'(?:계약|신청|입주)\s*(?:기간|일정|방법)|^\d+[.)]\s',line):roster=False
            else:continue
        lines.append(line)
    return '\n'.join(lines)


def safe_value(value):
    if isinstance(value,str):return redact(value)
    if isinstance(value,list):return [safe_value(v) for v in value]
    if isinstance(value,dict):return {k:safe_value(v) for k,v in value.items() if k not in ('persons','applicants','winners','resident_registration_number')}
    return value


def text_quality(text, title=''):
    t=re.sub(r'\s+',' ',str(text or '')).strip()
    if not t:return 'MISSING'
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


def evidence(item, source, manual, ai, assessment):
    revision=item['source_revision_no'];candidates=[]
    for origin,data,field in [('SOURCE',source,'body_text'),('MANUAL',manual,'body_text'),('AI',ai,'body_text')]:
        body=(source.get('text') or source.get('full_text') or source.get('body_text') or '') if origin=='SOURCE' else data.get(field,'')
        rev=revision if origin=='SOURCE' else data.get('source_revision_no')
        quality=text_quality(body,item['title']);current=rev==revision
        candidates.append(dict(origin=origin,source_revision_no=rev,current=current,quality=quality,
            chars=len(body),sha256=hashlib.sha256(body.encode()).hexdigest() if body else None,
            collected_at=data.get('collected_at'),raw_sha256=data.get('raw_sha256') or data.get('body_sha256'),text=redact(body)))
    eligible=[c for c in candidates if c['current'] and c['quality'] in ('TEXT_AVAILABLE_UNVERIFIED','SUMMARY_ONLY')]
    # A targeted manual extraction beats a navigation-heavy automatic HTML body.
    chosen=next((c for quality in ('TEXT_AVAILABLE_UNVERIFIED','SUMMARY_ONLY') for origin in ('MANUAL','SOURCE','AI') for c in eligible if c['origin']==origin and c['quality']==quality),None)
    quality=chosen['quality'] if chosen else 'STALE_ONLY' if any(c['chars'] and not c['current'] for c in candidates) else 'INSUFFICIENT' if any(c['chars'] for c in candidates) else 'MISSING'
    assessment_current=bool(assessment and assessment.get('source_revision_no')==revision and assessment.get('review_revision_no')==item['review_revision_no'])
    hashes={c['origin']:c['sha256'] for c in candidates if c['current']}
    assessment_current=assessment_current and all(f.get('body_sha256')==hashes.get(f.get('source_type')) for f in assessment.get('facts',[]))
    facts=safe_value(assessment.get('facts',[])) if assessment_current else []
    stage_names=('CONSTRUCTION','SUPPLY','COMPLETION','MOVE_IN')
    result=dict(document_id=item['id'],source_revision_no=revision,review_revision_no=item['review_revision_no'],
        effective_text=chosen['text'] if chosen else '',effective_origin=chosen['origin'] if chosen else None,
        quality=quality,quality_note='문자열·판본 기준 선별이며 첨부 완전성·사실 확정은 별도 확인',
        candidates=candidates,assessment_current=assessment_current,
        external_recommendation=safe_value(assessment.get('external_recommendation',{})),
        officer_assessment=safe_value(assessment),facts=facts,
        stage_dates={stage:[f for f in facts if f.get('stage')==stage and f.get('kind')=='DATE'] for stage in stage_names},
        unknown_fields=assessment.get('unknown_fields',[]) if assessment_current else ['현재 판본의 담당자 구조화 사실 검증'],
        related_documents=safe_value(assessment.get('related_documents',[])) if assessment_current else [],
        event_group=assessment.get('event_group') if assessment_current else None,
        aggregate_allowed=False,aggregation_note='참고·모집·정정 사건. 별도 사업 실적 승인 전 합산 금지',
        linked_project_ids=(item.get('decision') or {}).get('project_ids',[]) if item['status']=='APPROVED' else [],
        linkage_confirmed=item['status']=='APPROVED' and bool((item.get('decision') or {}).get('project_ids')),
        privacy_note='개인식별번호·개인 연락처·명단 영역 제외. 첨부 명단 자동 추출 없음 · 내보내기 시 명단 제외')
    return result
