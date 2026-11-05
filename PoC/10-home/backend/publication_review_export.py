"""On-demand, read-only CSV for independent review of publication decisions."""
import csv
import io
import json
from collections import defaultdict
from sqlalchemy import select, tuple_
from .db import Revision, now
from .publication_reviews import queue, STATES, KIND
from .source_authority import LABELS

OPEN_STATES = {'REVIEW', 'HOLD', 'REGISTRATION_REQUIRED'}
FIELDS = (
    '내보낸시각', '자료ID', '자료명', '현재상태코드', '현재상태', '우선순위',
    '출처ID', '출처명', '출처구분', '게시일', '원문URL', '원문판본', '원문해시',
    '수집범위', '본문보유여부', '수집본문', '원문변경_재검토필요', '연결변경_재검토필요',
    '최근저장판단코드', '최근저장판단', '검토판본', '검토당시원문판본',
    '검토담당자', '검토시각', '검토사유', '검토당시원문확인', '검토대상정책ID',
    '검토대상정책명', '검토당시선택사업명_JSON', '선택사업_현재등록정보_JSON',
    '신규등록대상사업명_JSON', '이름유사후보_동일사업미확정_JSON',
    '검토주제', '검토질문', '검토안내근거', '원문확인항목_JSON', '후속조치안내',
    '최근판단반영범위', '검토이력_JSON', '외부검증결과', '외부검증사유', '추가확인사항',
    'AI수집본문', 'AI분석_JSON',
    '수동수집상태', '수동수집본문', '수동수집확인내용', '수동수집첨부_JSON',
    '통합유효본문', '통합본문출처', '통합본문품질', '본문판본별상태_JSON',
    '외부모델권고유형', '외부모델검토의견_JSON', '담당자구조화검증_JSON',
    '구조화사실_JSON', '단계별일정_JSON', '미확인필드_JSON', '동일관련사건_JSON',
    '사건군ID', '확정자료연결여부', '실적합산허용', '개인정보처리안내',
    '원시문자열존재', '상세본문활용가능', '첨부검증완료', '통합본문_SHA256', '본문해시계약_JSON',
    '증거검증_재검토필요', '증거재검토사유_JSON', '증거집합ID', '증거대장_JSON', '업무이벤트일정_JSON',
    '사실범위_JSON', '검증단계_JSON', '외부의견교차검토_JSON', '등록대기검토_JSON', '승인추적_JSON', '독립외부검증상태',
    '첨부확보상태_JSON', '보고서원본추적_JSON', '증거집합요약_JSON', '수집점검_JSON',
)


def cell(value):
    """Quote spreadsheet formulas without losing commas/newlines or Korean."""
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def _export(service, status='ALL', priority=None, search='', structured=False):
    if status not in {*STATES, 'ALL', 'OPEN'}:
        raise ValueError('지원하지 않는 검토 상태입니다')
    if priority is not None and priority not in (1, 2, 3, 4):
        raise ValueError('우선순위는 1~4입니다')
    data = queue(service)
    term = search.lower()
    items = [r for r in data['items']
             if (status == 'ALL' or status == 'OPEN' and r['status'] in OPEN_STATES or r['status'] == status)
             and (priority is None or r['priority'] == priority)
             and (not term or term in ' '.join(str(v or '') for v in
                  (r['title'], r['source_name'], r['question'], (r['decision'] or {}).get('reason'))).lower())]
    # Pin source/decision revisions to the queue result, including when a new
    # source arrives while exporting. All histories are read in one query.
    documents = {}; histories = defaultdict(list)
    if items:
        pairs = [(r['id'], r['source_revision_no']) for r in items]
        decisions = {r['id']: r['review_revision_no'] for r in items}
        with service.sessions() as db:
            for r in db.scalars(select(Revision).where(
                    Revision.kind == 'document_evidence', tuple_(Revision.entity_id, Revision.revision_no).in_(pairs))):
                documents[r.entity_id] = (dict(r.payload,evidence_ref=dict(id=r.entity_id,revision_id=r.id,revision_no=r.revision_no,hash=r.payload_hash,recorded_at=r.recorded_at.isoformat())), r.payload_hash)
            review_ids = [r['id'] for r in items]
            for r in db.scalars(select(Revision).where(
                    Revision.kind == KIND, Revision.payload['document_id'].as_string().in_(review_ids))
                    .order_by(Revision.revision_no.desc())):
                doc_id = r.payload['document_id']
                if r.revision_no <= decisions[doc_id]:
                    histories[doc_id].append(dict(r.payload, revision_no=r.revision_no, recorded_at=r.recorded_at.isoformat()))
    from .publication_supplements import load as load_supplements
    supplements = load_supplements(service, [r['id'] for r in items])
    from .ai_collection import annotations
    ai = annotations(service, [r['id'] for r in items])
    projects = {p['id']: p for p in data['projects']}
    policies = {p['id']: p['name'] for p in data['policies']}
    policies['UNASSIGNED'] = '정책 미지정'
    from .publication_evidence import load as load_assessments, evidence, redact, safe_value
    assessments=load_assessments(service,[r['id'] for r in items])
    from .hold_review import load as load_cross_reviews
    cross_reviews=load_cross_reviews(service,[r['id'] for r in items])
    structured_items=[]
    from .review_report_artifacts import manifest
    report_manifests={rid:manifest(service.data_dir,rid) for rid in {v.get('report_id') for v in cross_reviews.values()} if rid}
    encoded = lambda value: json.dumps(safe_value(value), ensure_ascii=False, separators=(',', ':'))
    output = io.StringIO(newline=''); writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader(); exported_at = now().isoformat()
    for r in items:
        d = r['decision'] or {}; g = r['guidance'] or {}
        source, digest = documents.get(r['id'], ({}, ''))
        body = source.get('text') or source.get('full_text') or source.get('body_text') or ''
        selected = [projects.get(pid, dict(id=pid, missing=True)) for pid in d.get('project_ids', [])]
        extra = supplements.get(r['id'], {})
        extra_state = ('이전 판본 본문 기록 · 재확인 필요' if extra['source_revision_no'] != r['source_revision_no'] else '현재 판본 본문 기록 · 첨부 실물/검증은 별도 열 참조') if extra else '미수집'
        ev=evidence(dict(r,source_hash=digest,source_revision_id=source.get('evidence_ref',{}).get('revision_id')),source,extra,ai.get(r['id'],{}),assessments.get(r['id'],{}),csv_mode=not structured)
        cross=cross_reviews.get(r['id'],{})
        ev['report_provenance']=report_manifests.get(cross.get('report_id'),{})
        ev['evidence_summary']=dict(source_revision_no=r['source_revision_no'],evidence_set_id=ev['evidence_set_id'],active=len(ev['facts']),inactive=len(ev['evidence_records'])-len(ev['facts']),metric_approved=False)
        ev['collection_check']=cross.get('collection_check',{})
        ev['cross_review']=cross
        ev['registration_review']=cross.get('registration_review',{})
        for f in ev['evidence_records']:
            f.update(publisher=source.get('publisher') or r['source_name'],publisher_type='GOVERNMENT_OR_PUBLIC_AGENCY' if r['authority']=='OFFICIAL' else 'NEWS_OR_OTHER',document_kind=next((c['document_kind'] for c in ev['candidates'] if c['origin']==f.get('source_type')),'UNKNOWN'),source_format='TEXT_EXTRACT',extraction_method=f.get('source_type'))
        ev['approval_trace']=dict(approval_actor_role='RECORDED_REVIEW_ACTOR' if d else None,actor=d.get('actor'),approval_timestamp=d.get('reviewed_at'),before_state=(histories[r['id']][1].get('status') if len(histories[r['id']])>1 else None),after_state=d.get('status'),evidence_set_id=ev['evidence_set_id'],scope='DOCUMENT_REVIEW_ONLY',metric_approved=False)
        if cross.get('current') and cross.get('relations'):ev['related_documents']=cross['relations']
        ev['linkage_confirmed']=ev['linkage_confirmed'] and all(not p.get('missing') for p in selected)
        ev['verification_stages'].update(PROJECT_MATCHED=ev['linkage_confirmed'],APPROVED_FOR_LINK=ev['linkage_confirmed'])
        structured_items.append(dict(ev,title=r['title'],source_url=r['evidence_url'],source_hash=digest,
            system_status=r['status'],decision=safe_value(d),review_history=safe_value(histories[r['id']]),selected_projects=selected))
        has_text=any(c['chars'] for c in ev['candidates'])
        values = (
            exported_at, r['id'], r['title'], r['status'], r['status_label'], r['priority'],
            r['source_id'], r['source_name'], LABELS.get(r['authority'], '출처 확인 필요'),
            r['source_date'], r['evidence_url'], r['source_revision_no'], digest,
            source.get('content_scope', ''), ('상세본문 보유 · 사실 미확정' if ev['usable_detail_body'] else '요약만 보유 · 상세본문 미확보' if ev['quality']=='SUMMARY_ONLY' else '원시 문자열만 보유 · 분석용 본문 미확보') if has_text else '미보유 · 원문URL에서 별도 확인 필요', redact(body),
            '예' if r['source_changed'] or ev['needs_revalidation'] else '아니오', '예' if r['link_changed'] else '아니오',
            d.get('status'), STATES.get(d.get('status'), '판단 기록 없음'), r['review_revision_no'], d.get('source_revision_no'),
            d.get('actor'), d.get('reviewed_at'), d.get('reason'),
            ('예' if d.get('source_checked') else '아니오') if d else '판단 기록 없음',
            d.get('policy_id'), policies.get(d.get('policy_id'), ''), encoded(d.get('project_names', [])),
            encoded(selected), encoded(d.get('new_project_names', [])), encoded(r['candidates']),
            r['review_topic'], g.get('decision', r['question']), g.get('basis'), encoded(g.get('checks', [])),
            g.get('next_step'), d.get('effect'), encoded(histories[r['id']]), '', '', '',
            redact(ai.get(r['id'],{}).get('body_text','')), encoded(r.get('ai_analysis',{})),
            extra_state, redact(extra.get('body_text')), extra.get('summary'), encoded(extra.get('attachments', [])),
            ev['effective_text'], ev['effective_origin'], ev['quality'], encoded([{k:v for k,v in c.items() if k!='text'} for c in ev['candidates']]),
            ev['external_recommendation'].get('code'), encoded(ev['external_recommendation']), encoded(ev['officer_assessment']),
            encoded(ev['facts']), encoded(ev['stage_dates']), encoded(ev['unknown_fields']), encoded(ev['related_documents']),
            ev['event_group'], '예' if ev['linkage_confirmed'] else '아니오', '아니오 · 별도 실적 승인 필요', ev['privacy_note'],
            '예' if ev['raw_text_present'] else '아니오', '예' if ev['usable_detail_body'] else '아니오', '예' if ev['attachment_verified'] else '아니오',
            ev['effective_text_sha256'], encoded(dict(hash_input_field='통합유효본문',encoding='UTF-8',normalization_version=ev['normalization_version'],csv_formula_escaped=not structured,raw_hash_note='원문 바이트·저장 본문 해시는 본문판본별상태_JSON의 raw_sha256·stored_text_sha256; 내보낸 본문 해시와 구분')),
            '예' if ev['needs_revalidation'] else '아니오',encoded(ev['revalidation_reasons']),ev['evidence_set_id'],encoded(ev['evidence_records']),encoded(ev['business_event_dates']),
            encoded(ev['fact_coverage']),encoded(ev['verification_stages']),encoded(cross),encoded(ev['registration_review']),encoded(ev['approval_trace']), 'NOT_RECORDED · 업무보조 교차검토와 별개',
            encoded(dict(state=ev['attachment_inventory_state'],items=ev['attachment_inventory'],absence_confirmed=False,verified=False)),encoded(ev['report_provenance']),encoded(ev['evidence_summary']),encoded(ev['collection_check']),
        )
        writer.writerow({key: cell(redact(value) if isinstance(value,str) and not key.endswith('_JSON') else value) for key, value in zip(FIELDS, values, strict=True)})
    if structured:return dict(schema_version='publication-review-evidence-3',exported_at=exported_at,
        filters=dict(status=status,priority=priority,search=search),count=len(structured_items),items=structured_items,
        note='외부 모델 의견은 담당자 업무 보조 의견. 시스템 판단·확정 연결·사업 실적과 별도입니다.')
    return '\ufeff' + output.getvalue()

def export_csv(service,status='ALL',priority=None,search=''):
    return _export(service,status,priority,search)

def export_json(service,status='ALL',priority=None,search=''):
    return _export(service,status,priority,search,structured=True)
