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
    '수동수집상태', '수동수집본문', '수동수집확인내용', '수동수집첨부_JSON',
)


def cell(value):
    """Quote spreadsheet formulas without losing commas/newlines or Korean."""
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@')) or text.startswith(('\t', '\r', '\n')) else text


def export_csv(service, status='ALL', priority=None, search=''):
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
                documents[r.entity_id] = (r.payload, r.payload_hash)
            review_ids = [r['id'] for r in items]
            for r in db.scalars(select(Revision).where(
                    Revision.kind == KIND, Revision.payload['document_id'].as_string().in_(review_ids))
                    .order_by(Revision.revision_no.desc())):
                doc_id = r.payload['document_id']
                if r.revision_no <= decisions[doc_id]:
                    histories[doc_id].append(dict(r.payload, revision_no=r.revision_no, recorded_at=r.recorded_at.isoformat()))
    from .publication_supplements import load as load_supplements
    supplements = load_supplements(service, [r['id'] for r in items])
    projects = {p['id']: p for p in data['projects']}
    policies = {p['id']: p['name'] for p in data['policies']}
    policies['UNASSIGNED'] = '정책 미지정'
    encoded = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    output = io.StringIO(newline=''); writer = csv.DictWriter(output, fieldnames=FIELDS)
    writer.writeheader(); exported_at = now().isoformat()
    for r in items:
        d = r['decision'] or {}; g = r['guidance'] or {}
        source, digest = documents.get(r['id'], ({}, ''))
        body = source.get('text') or source.get('full_text') or source.get('body_text') or ''
        selected = [projects.get(pid, dict(id=pid, missing=True)) for pid in d.get('project_ids', [])]
        extra = supplements.get(r['id'], {})
        extra_state = ('이전 판본 수집 · 재확인 필요' if extra['source_revision_no'] != r['source_revision_no'] else '현재 판본 원문·첨부 수집') if extra else '미수집'
        values = (
            exported_at, r['id'], r['title'], r['status'], r['status_label'], r['priority'],
            r['source_id'], r['source_name'], LABELS.get(r['authority'], '출처 확인 필요'),
            r['source_date'], r['evidence_url'], r['source_revision_no'], digest,
            source.get('content_scope', ''), '보유 · 수집본문 기준' if body else '미보유 · 원문URL에서 별도 확인 필요', body,
            '예' if r['source_changed'] else '아니오', '예' if r['link_changed'] else '아니오',
            d.get('status'), STATES.get(d.get('status'), '판단 기록 없음'), r['review_revision_no'], d.get('source_revision_no'),
            d.get('actor'), d.get('reviewed_at'), d.get('reason'),
            ('예' if d.get('source_checked') else '아니오') if d else '판단 기록 없음',
            d.get('policy_id'), policies.get(d.get('policy_id'), ''), encoded(d.get('project_names', [])),
            encoded(selected), encoded(d.get('new_project_names', [])), encoded(r['candidates']),
            r['review_topic'], g.get('decision', r['question']), g.get('basis'), encoded(g.get('checks', [])),
            g.get('next_step'), d.get('effect'), encoded(histories[r['id']]), '', '', '',
            extra_state, extra.get('body_text'), extra.get('summary'), encoded(extra.get('attachments', [])),
        )
        writer.writerow({key: cell(value) for key, value in zip(FIELDS, values, strict=True)})
    return '\ufeff' + output.getvalue()
