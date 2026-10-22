"""Policy-scoped candidate decisions, independent of source and membership data."""
from sqlalchemy import select
from .db import Mapping, ProgramMapping, Revision, Audit, entity_id, upsert_revision, now
from .api_samples import today

SOURCE = 'mapping_staff'
ACTIVE = 'POL_2025_0907'


def save(service, kind, target_id, *, action, revision_no, actor, reason, evidence_url='', policy_id=ACTIVE):
    actor, reason = actor.strip(), reason.strip()
    if kind not in ('project', 'program') or action not in ('EXCLUDE', 'RESTORE'):
        raise ValueError('지원하지 않는 후보 검토 작업입니다')
    if policy_id != ACTIVE:
        raise ValueError('현재 후보 검토는 9·7 정책을 대상으로 합니다')
    if not actor or not reason:
        raise ValueError('담당자와 검토 사유가 필요합니다')
    if evidence_url and not evidence_url.startswith('https://'):
        raise ValueError('출처는 HTTPS URL로 입력해 주세요')
    key = f'{kind}:{target_id}:{policy_id}'
    eid = entity_id('mapping_decision', SOURCE, key)
    with service.sessions.begin() as db:
        subject = db.scalar(select(Mapping).where(Mapping.project_id == target_id).with_for_update()) if kind == 'project' else db.scalar(select(ProgramMapping).where(ProgramMapping.id == target_id).with_for_update())
        if subject is None:
            raise KeyError(target_id)
        old = db.scalar(select(Revision).where(Revision.entity_id == eid, Revision.superseded_at.is_(None)))
        if (old.revision_no if old else 0) != revision_no:
            return dict(conflict=True, revision_no=old.revision_no if old else 0)
        if action == 'EXCLUDE':
            if kind == 'project':
                parent = db.scalar(select(ProgramMapping).where(ProgramMapping.id == subject.program_id).with_for_update()) if subject.program_id else None
                # Match the workbench's effective candidate path, including held
                # source-reference projects whose generic programme is linked.
                raw = db.scalar(select(Revision).where(Revision.entity_id == target_id, Revision.kind=='project', Revision.superseded_at.is_(None)))
                pending = raw and (raw.payload.get('source_reference_id') or raw.payload.get('policy_candidate_only')) and subject.status!='CONFIRMED' and subject.policy_id in (None,'UNASSIGNED')
                linked = bool(parent and parent.policy_id not in (None,'','UNASSIGNED') and parent.status not in ('RELEASED','REJECTED') and subject.status not in ('RELEASED','REJECTED') and not pending)
            else:
                linked = subject.policy_id not in (None,'','UNASSIGNED') and subject.status not in ('RELEASED','REJECTED')
            if linked:
                raise ValueError('현재 연결된 항목입니다. 연결을 해제한 후 후보 제외를 확인해 주세요')
        payload = dict(subject_kind=kind, subject_id=target_id, policy_id=policy_id,
                       status='EXCLUDED' if action=='EXCLUDE' else 'CANDIDATE',
                       actor=actor, reason=reason, evidence_url=evidence_url,
                       changed_at=now().isoformat(), base_date=today().isoformat())
        record, _ = upsert_revision(db, 'mapping_decision', SOURCE, key, payload, 'staff-review')
        db.add(Audit(entity_id=target_id, action='CANDIDATE_DECISION', before=old.payload if old else {}, after=payload))
        return dict(payload, revision_no=record.revision_no)


def ensure_candidate_restored(db, kind, target_id, policy_id=ACTIVE):
    eid = entity_id('mapping_decision', SOURCE, f'{kind}:{target_id}:{policy_id}')
    decision = db.scalar(select(Revision).where(Revision.entity_id==eid, Revision.superseded_at.is_(None)))
    if decision and decision.payload.get('status')=='EXCLUDED':
        raise ValueError('제외 확인된 후보입니다. 정책·프로그램·사업 연결 화면에서 후보로 복원한 후 연결해 주세요')
