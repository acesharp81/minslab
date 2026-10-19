"""Explicit corrections to reviewed scope decisions, with optimistic revisions.

Identity confirmation does not attest a housing cohort's quantity. Never copy a
whole permit into a smaller tenure cohort without an allocation witness.
"""
from copy import deepcopy
from sqlalchemy import select, text
from .db import Revision, Audit, upsert_revision
from .service import today
from .independent_metrics import digest

REASON = '담당자 매칭 확인 오류 수정'


def propose(projects, bridges, stages, sources):
    projects = {p['id']: p for p in projects}
    changes = []
    for old in stages:
        selected = old.get('selected') or {}
        project = projects.get(old['project_id'], {})
        source = sources.get(selected.get('source_entity_id'), {})
        target, quantity = project.get('planned_units'), selected.get('units')
        if old.get('status') != 'CONFIRMED' or old.get('stage') != 'APPROVAL':
            continue
        if (source.get('source_id') != 'building_hub' or not isinstance(target, int)
                or not isinstance(quantity, int) or quantity <= target
                or quantity != source.get('units') or selected.get('relation_type')):
            continue
        # The existing identity/date decision stays pinned. Only the erroneous
        # whole-scope quantity assertion is withdrawn; no allocation is guessed.
        new = deepcopy(old)
        new['selected'].update(units=None, source_units=quantity,
            relation_type='PART_OF_APPROVAL', scope_partial=True,
            scope_status='COHORT_ALLOCATION_UNVERIFIED', quantity_review_status='REVIEW',
            scope_label=f'관리 사업 {target}호 / 승인 원천 전체 {quantity}호 · 해당 유형 물량 미검증')
        new['selected']['basis'] += ' · 전체 승인 물량의 부분 사업 전용 오류 정정; 해당 유형 배분 근거 확보 전 물량 미확정'
        changes.append(_change('stage_evidence', old, new,
            f'관리 사업 {target}호에 전체 승인 {quantity}호를 동일 범위로 확인한 오류. 사업 연결과 원문 날짜를 유지하고 물량 귀속은 보류.'))
    for old in bridges:
        project = projects.get(old['project_id'], {})
        source = sources.get(old['source_entity_id'], {})
        target, total = project.get('planned_units'), source.get('planned_units')
        if (old.get('status') != 'CONFIRMED' or old.get('relation_type') != 'SAME_SCOPE'
                or source.get('verification_status') != 'SOURCE_CONTENT_CHECKED'
                or not isinstance(target, int) or not isinstance(total, int) or not 0 < target < total):
            continue
        facts = old.get('facts', [])
        if not facts or not any(f.get('units') == target for f in facts):
            continue
        # Retain the exact 381-unit facts, while correcting SAME_SCOPE against
        # the 577-unit source complex. No unrelated or quantityless facts move.
        if any(f.get('units') not in (None, target) for f in facts):
            continue
        new = deepcopy(old)
        new.update(relation_type='CONTAINED_SCOPE', scope_status='EXPLICIT_EVENT_COHORT',
                   scope_label=f'직접 사건 {target}호 / 원천 전체 {total}호')
        new['facts'] = [dict(f, scope_units=target, source_total_units=total,
                             scope_partial=False, scope_label=new['scope_label'])
                        if f.get('units') == target else f for f in facts]
        changes.append(_change('evidence_bridge', old, new,
            f'원천 전체 {total}호와 관리 사업 {target}호를 SAME_SCOPE로 확인한 관계 오류. 원문의 {target}호 직접 사건을 CONTAINED_SCOPE로 정정.'))
    return changes


def _change(kind, old, new, explanation):
    return dict(kind=kind, id=old['id'], expected_revision_no=old['revision_no'],
                expected_payload_hash=old.get('source_payload_hash'),
                project_id=old['project_id'], explanation=explanation, payload=new)


def apply(service, changes, actor='김민'):
    results = []
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            # Same locks as interactive bridge and stage reviews.
            db.execute(text('SELECT pg_advisory_xact_lock(1019078)'))
            db.execute(text('SELECT pg_advisory_xact_lock(1019081)'))
        for change in changes:
            old = db.scalar(select(Revision).where(Revision.entity_id == change['id'],
                Revision.kind == change['kind'], Revision.superseded_at.is_(None)).with_for_update())
            if (old is None or old.revision_no != change['expected_revision_no']
                    or change.get('expected_payload_hash') and old.payload_hash != change['expected_payload_hash']):
                raise ValueError('검토 후 판본이 변경되었습니다. 정정 대상을 다시 확인하세요')
            payload = deepcopy(old.payload)
            for field in ('selected','relation_type','scope_status','scope_label','facts'):
                if field in change['payload']:payload[field]=change['payload'][field]
            payload.update(actor=actor, reason=REASON, review_basis=REASON,
                correction_explanation=change['explanation'], corrected_from_revision_id=old.id,
                correction_round_id='HOME-INTEGRITY-R01-CONSOLIDATED-20261017', base_date=today().isoformat())
            # Transport metadata must not replace a payload's evidence source.
            if 'source_id' in old.payload:payload['source_id']=old.payload['source_id']
            else:payload.pop('source_id', None)
            key=old.payload['project_id']+':'+(old.payload['stage'] if old.kind=='stage_evidence' else old.payload['source_entity_id'])
            from .db import entity_id
            if entity_id(old.kind,old.source_id,key)!=old.entity_id:raise ValueError('정정 원천 식별자 검증 실패')
            row, outcome = upsert_revision(db, old.kind, old.source_id, key,
                                          payload, 'reviewed_matching_correction')
            action = 'STAGE_EVIDENCE_REVIEW' if old.kind == 'stage_evidence' else 'EVIDENCE_BRIDGE_REVIEW'
            db.add(Audit(entity_id=row.entity_id, action=action, before=old.payload, after=payload))
            results.append(dict(id=row.entity_id, project_id=change['project_id'], kind=old.kind,
                previous_revision_id=old.id, revision_id=row.id, revision_no=row.revision_no,
                actor=actor, reason=REASON, explanation=change['explanation'], outcome=outcome))
    return dict(items=results, count=len(results), checksum=digest(results),
                identity_reassignments=0, note='사업 동일성은 유지하고 확인된 전체/부분 범위 오류를 정정. 미확인 오매칭은 임의 변경하지 않음.')
