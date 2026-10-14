"""Persisted repair explanations and existing immutable link audit trails."""
import hashlib
import json
from datetime import datetime, time, timedelta
from sqlalchemy import select, func, text
from .db import Audit, Revision, upsert_revision, entity_id, now
from .service import today, KST

KIND = 'collection_repair'
REPAIR_TYPES = {
    'IDENTITY_LINK': '사업 식별·원천 연결 오류',
    'SCOPE_QUANTITY': '전체·유형별 물량 범위 오류',
    'COLLECTION_GAP': '수집 범위·상세자료 누락',
    'STAGE_DATE': '단계·일정 분류 오류',
    'AVAILABILITY_STATE': '미확보 상태 구분 오류',
    'COLLECTION_FAILURE': '수집 실패·복구',
    'OTHER': '기타 오류',
}
LEGACY_TYPES = {
    'a31-alias-and-documents': 'IDENTITY_LINK',
    'cross-source-bridges': 'IDENTITY_LINK',
    'geumto-a2-split-tenure': 'SCOPE_QUANTITY',
    'lh-notice-detail-gap': 'COLLECTION_GAP',
    'juam-c2-approval': 'SCOPE_QUANTITY',
    'approval-global-normalization': 'IDENTITY_LINK',
    'lh-notice-category-region-schedule': 'COLLECTION_GAP',
    'completion-stage-semantics': 'STAGE_DATE',
    'schedule-unknown-semantics': 'AVAILABILITY_STATE',
    'missing-data-classification': 'AVAILABILITY_STATE',
}


def classify_existing(service):
    known = {entity_id(KIND, 'repair_log', key): kind for key, kind in LEGACY_TYPES.items()}
    outcomes = []
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019082)'))
        rows = db.scalars(select(Revision).where(Revision.kind == KIND, Revision.superseded_at.is_(None))).all()
        for old in rows:
            if old.payload.get('repair_type'): continue
            kind = known.get(old.entity_id, 'COLLECTION_FAILURE' if old.payload.get('status') in ('OPEN','RECOVERED') else 'OTHER')
            # Preserve every existing field and append a classification-only revision.
            payload = dict(old.payload, repair_type=kind)
            old.superseded_at = now()
            db.flush()
            new = Revision(entity_id=old.entity_id, kind=KIND, source_id=old.source_id,
                revision_no=old.revision_no+1, previous_id=old.id, payload=payload,
                payload_hash=hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest(),
                batch_id='repair_type_backfill', sample_base_date=old.sample_base_date)
            db.add(new)
            outcomes.append(dict(id=old.entity_id, repair_type=kind, revision_no=new.revision_no))
    return outcomes
ACTIONS = {
    'PROGRAM_PROJECT_MERGE':'중복 프로그램 사업 연결 이관',
    'PROGRAM_POLICY_MERGE':'중복 프로그램 ID 별칭 정비',
    'PROGRAM_IDENTITY_MERGE':'프로그램 대표 ID 통합 근거',
    'PROGRAM_SOURCE_SUPPLEMENT': '정책 원문 프로그램·사업 근거 보강',
    'PROGRAM_PROFILE_UPDATED': '프로그램정보 사용자 입력',
    'PROGRAM_PROJECT_REVIEW': '프로그램–사업 연결 변경',
    'EVIDENCE_BRIDGE_AUTO': '원천 간 연결 후보 추가',
    'EVIDENCE_BRIDGE_REVIEW': '담당자 연결 검토',
    'STAGE_EVIDENCE_AUTO': '단계 근거 후보 저장',
    'STAGE_CANDIDATES_UPDATED': '단계 후보 갱신·근거 보강',
    'STAGE_EVIDENCE_REVIEW': '담당자 단계 근거 검토',
    'MAPPING_REVIEW': '정책·프로그램 귀속 검토',
    'COLLECTION_ASSESSMENT': '수집 상태 판정',
}


QUALITY_KINDS = {'VALIDITY': '데이터 유효성', 'CONSISTENCY': '원천 간 정합성', 'COVERAGE': '수집 범위', 'PROCESSING': '시스템 처리'}
QUALITY_LAYERS = {'SOURCE': '원천값 문제', 'SOURCE_LIMIT': '원천 제공 범위·형식의 한계', 'COLLECTION': '수집·정규화 문제', 'LINKAGE': '사업·필지 연결 문제', 'DISPLAY': '화면·집계 처리 문제'}
QUALITY_RESULTS = {'PASS': '확인·조치 완료', 'FAIL': '미해결', 'PARTIAL': '일부 보완·확인 필요', 'PENDING': '추가 확인 필요', 'NOT_APPLICABLE': '현재 원천으로 적용 불가'}


def validate_quality(payload):
    checks=payload.get('quality_checks', [])
    if not isinstance(checks,list):raise ValueError('품질 점검은 목록으로 입력하세요')
    identifiers=set()
    for c in checks:
        if not isinstance(c,dict) or any(not c.get(k) for k in ('id','title','kind','layer','result','rule','evidence','repair','completion_criteria','checked_at','checked_scope')):
            raise ValueError('품질 점검의 기준·근거·범위·정비 방법·완료 조건을 입력하세요')
        if c['kind'] not in QUALITY_KINDS or c['layer'] not in QUALITY_LAYERS or c['result'] not in QUALITY_RESULTS:
            raise ValueError('품질 점검 분류 값 오류')
        if c['id'] in identifiers:raise ValueError('품질 점검 식별자 중복')
        identifiers.add(c['id'])
        for m in c.get('metrics',[]):
            value,total=m.get('value'),m.get('total')
            if isinstance(value,bool) or not isinstance(value,(int,float)) or value<0 or (total is not None and (isinstance(total,bool) or not isinstance(total,(int,float)) or total<value)):
                raise ValueError('품질 점검 건수 또는 분모 값 오류')
    if not isinstance(payload.get('related_keys',[]),list):raise ValueError('연결 필드는 목록으로 입력하세요')


def patch_details(service, key, updates):
    """Append only inspected metadata, retaining an officer's current status and explanation."""
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':db.execute(text('SELECT pg_advisory_xact_lock(1019082)'))
        old=db.scalar(select(Revision).where(Revision.entity_id==entity_id(KIND,'repair_log',key),Revision.superseded_at.is_(None)))
        if old is None:raise ValueError('기록할 오류·조치 이력이 없습니다')
        payload=dict(old.payload, **updates);validate_quality(payload)
        row,outcome=upsert_revision(db,KIND,'repair_log',key,payload,'quality_details')
        return dict(id=row.entity_id,revision_no=row.revision_no,outcome=outcome)


def quality_guide(data):
    fields=('id','title','repair_type','status','base_date','recorded_at','revision_no','source_ids','project_ids','stages','related_keys','cause','action','impact','remaining','report_url','quality_checks')
    return dict(as_of_date=data['as_of_date'],project_count=data['total'],quality_kinds=QUALITY_KINDS,quality_layers=QUALITY_LAYERS,quality_results=QUALITY_RESULTS,
        repairs=[{k:r.get(k) for k in fields} for r in data['repairs']],
        note='점검 숫자는 각 기록의 점검일·점검범위 기준입니다. 조회 범위의 사업 수와 동일하지 않을 수 있습니다. 원천값 오류, 제공 범위의 한계, 수집·연결·표시 문제를 구분하고 미확보를 0으로 해석하지 않습니다.')


def save(service, key, payload):
    required = ('title', 'cause', 'action', 'remaining', 'stages', 'status', 'base_date')
    if any(not payload.get(k) for k in required):
        raise ValueError('오류명·원인·조치·남은 확인사항·단계·상태·기록 기준일이 필요합니다')
    validate_quality(payload)
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019082)'))
        old = db.scalar(select(Revision).where(Revision.entity_id == entity_id(KIND, 'repair_log', key), Revision.superseded_at.is_(None)))
        repair_type = payload.get('repair_type') or (old.payload.get('repair_type') if old else None) or LEGACY_TYPES.get(key) or ('COLLECTION_FAILURE' if key.startswith('collector:') else 'OTHER')
        if repair_type not in REPAIR_TYPES: raise ValueError('오류 유형 값 오류')
        payload = dict(payload, repair_type=repair_type)
        if old:
            for field in ('quality_checks','related_keys'):
                if field not in payload and field in old.payload:payload[field]=old.payload[field]
        for field in ('source_ids','project_ids'):
            if field not in payload:payload[field]=(old.payload.get(field) or []) if old else []
        record, outcome = upsert_revision(db, KIND, 'repair_log', key, payload, 'repair_log')
        return dict(id=record.entity_id, revision_no=record.revision_no, outcome=outcome)


def applies(repair, item):
    if repair.get('project_ids'):
        return item['id'] in repair['project_ids']
    sources = {s['source_id'] for c in item['cells'].values() for s in c['sources']}
    sources.update(item.get('lineage', {}).get('sources', {}))
    return bool(sources.intersection(repair.get('source_ids', [])))


def enrich(service, items, reference):
    repairs = service.rows(KIND, reference)
    repairs.sort(key=lambda r: (r['base_date'], r['id']), reverse=True)
    with service.sessions() as db:
        history = db.scalars(select(Revision).where(Revision.kind == KIND, Revision.entity_id.in_([r['id'] for r in repairs]), Revision.recorded_at < datetime.combine(reference + timedelta(days=1), time.min, KST)).order_by(Revision.revision_no.desc())).all()
    for repair in repairs:
        repair['history'] = [dict(revision_no=r.revision_no, recorded_at=r.recorded_at.isoformat(), **r.payload) for r in history if r.entity_id == repair['id']]
    for item in items:
        item['repair_ids'] = [r['id'] for r in repairs if applies(r, item)]
        item['link_changes'] = []
    # Read only persisted audit rows, with a bounded number per entity. Never rematch on read.
    lookup = {p['id']: p for p in items}
    entities = set(lookup)
    for kind in ('stage_evidence', 'evidence_bridge', 'collection_assessment'):
        entities.update(r['id'] for r in service.rows(kind, reference) if r.get('project_id') in lookup and r.get('id'))
    cutoff = datetime.combine(reference + timedelta(days=1), time.min, KST)
    if entities:
        ranked = select(Audit.id, func.row_number().over(partition_by=Audit.entity_id,
            order_by=(Audit.recorded_at.desc(), Audit.id.desc())).label('rn')).where(
            Audit.entity_id.in_(entities), Audit.action.in_(ACTIONS), Audit.recorded_at < cutoff).subquery()
        with service.sessions() as db:
            changes = db.scalars(select(Audit).join(ranked, Audit.id == ranked.c.id).where(ranked.c.rn <= 3)).all()
        for change in changes:
            after, before = change.after or {}, change.before or {}
            pid = after.get('project_id') or before.get('project_id') or change.entity_id
            if pid not in lookup: continue
            old, new = before.get('selected') or {}, after.get('selected') or {}
            stages = [after['stage']] if after.get('stage') else sorted({f['stage'] for f in after.get('facts', [])})
            lookup[pid]['link_changes'].append(dict(id=change.id, title=ACTIONS[change.action],
                recorded_at=change.recorded_at.isoformat(), stages=stages, status=after.get('status'),
                basis=after.get('review_basis') or after.get('upgrade_basis') or new.get('basis') or after.get('basis') or after.get('reason'),
                before=dict(status=before.get('status'), date=old.get('event_date') or ' / '.join(sorted({f['date'] for f in before.get('facts', []) if f.get('date')})) or None, method=old.get('method')),
                after=dict(status=after.get('status'), date=new.get('event_date') or ' / '.join(sorted({f['date'] for f in after.get('facts', []) if f.get('date')})) or None, method=new.get('method'))))
    for item in items:
        item['link_changes'].sort(key=lambda r: (r['recorded_at'], r['id']), reverse=True)
    relevant = {rid for p in items for rid in p['repair_ids']}
    return [r for r in repairs if r['id'] in relevant]


def record_collection(service, source, succeeded):
    """Record failure/recovery transitions, not a new explanation on every successful poll."""
    key = 'collector:' + source['id']
    from .db import entity_id
    prior = service.rows(KIND, entity_ids=[entity_id(KIND, 'repair_log', key)])
    if succeeded and (not prior or prior[0]['status'] != 'OPEN'): return
    if not succeeded and prior and prior[0]['status'] == 'OPEN': return
    from .project_collection import CATALOG
    stages = [stage for stage, ids in CATALOG.items() if source['id'] in ids]
    if not stages: stages = ['BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN']
    save(service, key, dict(title=source.get('name', source['id'])+' 수집 '+('복구' if succeeded else '실패'),
        cause='이전 수집 작업이 실패했습니다. 세부 실행 기록은 수집 배치 이력에 보존됩니다.',
        action='후속 수집 성공 확인. 원천 판본을 적재했습니다.' if succeeded else '마지막 정상 데이터를 유지하고 자동 수집의 다음 재시도 대상으로 남겼습니다.',
        remaining='자료 적재 성공과 사업 연결·내용 검증 완료는 별도입니다.' if succeeded else '원천 응답·접근 권한·파서 상태를 조사하고 정상 적재를 확인해야 합니다.',
        repair_type='COLLECTION_FAILURE', stages=stages, source_ids=[source['id']], project_ids=[], status='RECOVERED' if succeeded else 'OPEN',
        base_date=today().isoformat(), impact='이 원천을 사용하는 사업의 최신성에 영향', related_keys=['project'],
        quality_checks=[dict(id='collector-outcome',title='수집 성공·실패와 데이터 최신성',kind='COVERAGE',layer='COLLECTION',result='PARTIAL' if succeeded else 'FAIL',
            rule='수집 실패는 원천 실적 0이나 원천값 오류를 뜻하지 않습니다. 마지막 정상 자료와 최신 배치 상태를 구분합니다.',
            evidence='이전 실패 후 후속 수집 성공을 확인했습니다. 배치 이력에 성공·실패와 원문 판본이 보존됩니다.' if succeeded else '수집 배치 실패를 확인했습니다. 실패 원인은 배치 이력에서 조사하며 마지막 정상 데이터를 유지합니다.',
            repair='정상 적재 뒤 원문·페이지·사업 연결 범위의 정합성을 별도로 확인합니다.' if succeeded else '원천 응답·접근 권한·파서를 점검하고 수집을 재시도한 뒤 정상 적재와 연결 범위를 확인합니다.',
            completion_criteria='최근 배치 정상 적재와 조회 범위·원문 판본·사업 연결의 대조 결과를 함께 보존합니다.',
            checked_at=today().isoformat(),checked_scope=source.get('name',source['id'])+' 원천 수집 상태')]))
