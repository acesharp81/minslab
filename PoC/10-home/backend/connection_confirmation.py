"""Version-checked officer review of existing policy/program/project connections."""
from sqlalchemy import select, text
from .db import Audit, Mapping, ProgramMapping, Revision, entity_id, now, upsert_revision
from .service import today
from .independent_metrics import digest


def apply_review(service, review_id, plan, actor, reason):
    if not actor.strip() or not reason.strip() or not plan.get('programs') or not plan.get('projects'):
        raise ValueError('담당자·사유·프로그램과 사업 검토안이 필요합니다.')
    real = {p['policy_id'] for p in service.mapping_policies() if p.get('monitor_kind') == 'POLICY'}
    signature = digest(dict(plan=plan, actor=actor, reason=reason))
    review_entity = entity_id('connection_review', 'officer_review', review_id)
    with service.sessions.begin() as db:
        if service.engine.dialect.name == 'postgresql':
            db.execute(text('SELECT pg_advisory_xact_lock(1019182)'))
        prior = db.scalar(select(Revision).where(Revision.entity_id == review_entity, Revision.superseded_at.is_(None)))
        if prior:
            if prior.payload['plan_digest'] != signature:
                raise ValueError('같은 검토 ID에 다른 검토안을 덮어쓸 수 없습니다.')
            return dict(prior.payload, unchanged=True)
        jobs = []
        program_ids = [r['id'] for r in plan['programs']]
        project_ids = [r['id'] for r in plan['projects']]
        if len(set(program_ids)) != len(program_ids) or len(set(project_ids)) != len(project_ids):
            raise ValueError('검토안의 ID가 중복됩니다.')
        for kind, entries, model, id_field, action in (
                ('program', plan['programs'], ProgramMapping, ProgramMapping.id, 'PROGRAM_POLICY_REVIEW'),
                ('project', plan['projects'], Mapping, Mapping.project_id, 'PROGRAM_PROJECT_REVIEW')):
            records = {getattr(r, 'id' if kind == 'program' else 'project_id'): r for r in
                       db.scalars(select(model).where(id_field.in_([e['id'] for e in entries])).with_for_update())}
            for e in entries:
                row = records.get(e['id'])
                if row is None or row.revision_no != e['revision_no']:
                    raise ValueError('연결 판본이 변경됐습니다: ' + e['id'])
                if row.status in ('RELEASED', 'REJECTED'):
                    raise ValueError('해제·거절한 연결은 재확정 대상에서 제외해야 합니다.')
                if e['policy_id'] not in real or not e.get('explanation') or not e.get('evidence_url', '').startswith('https://'):
                    raise ValueError('정책·검토 근거·공식 원문 URL을 확인하세요.')
                fields = ('policy_id', 'status', 'basis', 'evidence_url', 'revision_no')
                before = {k: getattr(row, k) for k in fields}
                after = dict(policy_id=e['policy_id'], status='CONFIRMED', revision_no=row.revision_no + 1,
                    basis='사용자 입력 · ' + actor + ' · ' + reason + ' · ' + e['explanation'], evidence_url=e['evidence_url'])
                if kind == 'project':
                    before['program_id'] = row.program_id
                    parent = next((p for p in plan['programs'] if p['id'] == e['program_id']), None)
                    if parent is None or parent['policy_id'] != e['policy_id']:
                        raise ValueError('검토안의 정책–프로그램–사업 연결이 일치하지 않습니다.')
                    after['program_id'] = e['program_id']
                jobs.append((row, e['id'], action, before, after, e))
        # All optimistic versions and graph relationships are checked before any
        # writes; the entire review is one transaction, with original history.
        stamp = now()
        outcomes = []
        for row, identity, action, before, after, evidence in jobs:
            for key, value in after.items():
                setattr(row, key, value)
            row.reviewed_at = stamp
            db.add(Audit(entity_id=identity, action=action, before=before,
                after=dict(after, actor=actor, reason=reason, changed_at=stamp.isoformat(),
                           origin='MANUAL', review_id=review_id, evidence_urls=evidence.get('evidence_urls', []),
                           confirmation_scope='정책·프로그램 관리 연결 확정; 실제 착공·분양·입주 및 호수 증빙은 별도')))
            outcomes.append(dict(id=identity, before=before, after=after))
        payload = dict(actor=actor, reason=reason, review_id=review_id, plan_digest=signature, plan=plan,
            base_date=today().isoformat(), changed_at=stamp.isoformat(), outcomes=outcomes,
            program_count=len(program_ids), project_count=len(project_ids), actual_events_created=0,
            scope='기존 관리 연결 검토; 원천 수집·실적 생성과 구분')
        record, _ = upsert_revision(db, 'connection_review', 'officer_review', review_id, payload, 'officer_connection_review')
        db.add(Audit(entity_id=record.entity_id, action='CONNECTION_REVIEW_COMPLETED', before={}, after=payload))
        return payload
