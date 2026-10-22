"""Restore individually reviewed, pre-rollback management estimates with provenance.

This is a pinned migration, not a new missing-value fill rule. Source measurements,
partial counts, mappings and schedules are never rolled back. Run preview first.
"""
import argparse
from collections import Counter
from copy import deepcopy
import csv
import hashlib
import json
from pathlib import Path
from sqlalchemy import select, text
from backend.db import Audit, Mapping, Revision, engine_for, entity_id, now, upsert_revision
from backend.service import HomeService

BATCH = 'review-restore-20261022'
ACTOR = '담당자 대행 · 사용자 채택사유 재검토·복구 지시'
REASON = '기존 개별 채택 사유·선후 일정·관리 범위 재검토: 일괄 독립사건 규칙으로 삭제된 승인 관리 추정값 복구. 수집 실적과 구분'
OUT = Path('data/remediation/review-restore-20261022')
HOLDS = {
    ('광교 A17BL 민간참여 공공주택사업', 'BUSINESS'): '원 채택 앵커가 TEST_SAMPLE 인허가 후보이며 현 사업화 날짜도 SOURCE_CONFLICT. 날짜 복구 보류, 현재 600호 보존',
    ('광교 A17BL 민간참여 공공주택사업', 'APPROVAL'): '원 채택 인허가 앵커가 TEST_SAMPLE. SOURCE_ACCEPTED 표기와 관리 추정일 근거가 혼재하여 복구 보류',
    ('수원당수2 A3', 'APPROVAL'): '검토 이력에 인허가 717호와 계획 911호 범위 불일치가 남아 있어 911호 일괄 복구 보류',
}


def digest(v):
    return hashlib.sha256(json.dumps(v, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def reviewed_values(row):
    return {f: row.get(f) for f in ('event_date', 'units')}


def protected(db):
    return dict(revisions={r.entity_id: r.payload_hash for r in db.scalars(select(Revision).where(
        Revision.superseded_at.is_(None), Revision.kind.in_(['project', 'execution_schedule'])))},
        mappings=[(m.project_id, m.policy_id, m.program_id, m.status, m.revision_no, m.basis)
                  for m in db.scalars(select(Mapping).order_by(Mapping.project_id))])


def prepare(service):
    original = {u['project_id']: u for u in json.load(open('data/remediation/measurement-targets-20261022/plan-v1.json'))['updates']}
    cases = list(csv.DictReader(open('docs/analysis/measurement_reason_review_20261022/reason_chain.csv', encoding='utf-8-sig')))
    projects = {p['id']: p for p in service.projects(policy_id='POL_2025_0907')}
    changes = {}; audit = []; stamp = now().isoformat()
    with service.sessions() as db:
        guard = protected(db)
        for case in cases:
            pid, stage = case['project_id'], case['stage']; p = projects[pid]
            old = deepcopy(original[pid]['before']['progress'][stage])
            row = db.scalar(select(Revision).where(Revision.entity_id == entity_id('project_profile','manual_project',pid), Revision.superseded_at.is_(None)))
            current = row.payload.get('progress', {}).get(stage, {})
            reason = HOLDS.get((case['name'], stage))
            if not reason and reviewed_values(old) == reviewed_values(current): reason = '이미 같은 값: 유지'
            if not reason and any(current.get(f) not in (None, '') for f in ('event_date', 'units')):
                reason = '후속 채택값 존재: 현재 값 우선 보존'
            if not reason and (p['mapping']['status'] != 'CONFIRMED' or not old.get('actor') or not old.get('reason') or not old.get('inferred')):
                reason = '확정 연결·원 채택자·사유·추정 구분 확인 필요'
            if not reason and (not old.get('event_date') or old['event_date'] > '2026-10-22' or type(old.get('units')) is not int or not 0 < old['units'] <= p['planned_units']):
                reason = '미래 날짜 또는 관리 범위 초과: 복구 보류'
            goal = p.get('managed_schedules', {}).get(stage, {})
            if not reason and goal.get('due_date', '') > '2026-10-22': reason = '현재 채택 목표 미도래: 복구 보류'
            item = dict(case, before=reviewed_values(current), original=reviewed_values(old),
                decision='HOLD' if reason else 'RESTORE_REVIEWED_ESTIMATE', decision_reason=reason or REASON,
                current_source_revision_id=p['source_revision_id'], current_profile_revision_id=row.id,
                current_goal_revision_id=goal.get('source_revision_id'), mapping_revision_no=p['mapping']['revision_no'],
                original_field_provenance=old.get('field_provenance', {}))
            audit.append(item)
            if reason: continue
            review = dict(status='RESTORED_REVIEWED_ESTIMATE', batch_id=BATCH, reviewed_at=stamp,
                reviewer=ACTOR, reason=REASON, original_revision_id=case['original_revision'],
                original_actor=old['actor'], original_reason=old['reason'], original_rule=old.get('input_rule'),
                original_basis=old.get('input_basis'), mapping_basis=p['mapping']['basis'],
                current_source_revision_id=p['source_revision_id'], goal_revision_id=goal.get('source_revision_id'),
                values=reviewed_values(old), values_digest=digest(reviewed_values(old)),
                checks=['원 채택 사유·추정 구분 확인','확정된 동일 사업·범위','기준일 이전','현 목표 미도래 아님','현 실측값 덮어쓰기 없음','명시 상충 사례 별도 보류'])
            old.update(restoration_review=review, actor=ACTOR, reason=REASON, changed_at=stamp, batch_id=BATCH, inferred=True)
            # Preserve original derivations explicitly; review is never a source fact.
            old['input_rule']='REVIEWED_MANAGEMENT_ESTIMATE'
            old['field_provenance']={f:dict(rule='REVIEWED_MANAGEMENT_ESTIMATE',value=old[f],
                original_provenance=deepcopy(old.get('field_provenance',{}).get(f,{})),
                original_revision_id=case['original_revision'],basis=REASON) for f in ('event_date','units')}
            u=changes.setdefault(pid, dict(project_id=pid, name=p['name'], expected_revision_id=row.id,
                before=deepcopy(row.payload), after=deepcopy(row.payload), stages=[]))
            u['after'].setdefault('progress', {})[stage]=old
            u['after'].get('stage_states', {}).pop(stage, None)
            u['stages'].append(stage)
        for u in changes.values():
            u['after'].setdefault('reviewed_restorations', []).append(dict(batch_id=BATCH, actor=ACTOR, reason=REASON, at=stamp, stages=u['stages']))
    return dict(batch_id=BATCH,created_at=stamp,reference_date='2026-10-22',protected=guard,protected_digest=digest(guard),
        cases=audit,updates=list(changes.values()),summary=dict(reviewed_cases=len(audit),restored_projects=len(changes),
        restored_stages=dict(Counter(c['stage'] for c in audit if c['decision']=='RESTORE_REVIEWED_ESTIMATE')),
        held_cases=sum(c['decision']=='HOLD' for c in audit)))


def apply(service, plan):
    written=[]
    with service.sessions.begin() as db:
        for lock in (9072026,9701022):
            if service.engine.dialect.name=='postgresql': db.execute(text(f'SELECT pg_advisory_xact_lock({lock})'))
        if digest(protected(db)) != plan['protected_digest']: raise ValueError('검토 후 원천·목표·연결 변경')
        for u in plan['updates']:
            row=db.scalar(select(Revision).where(Revision.entity_id==entity_id('project_profile','manual_project',u['project_id']),Revision.superseded_at.is_(None)).with_for_update())
            if not row or row.id!=u['expected_revision_id']: raise ValueError('검토 후 프로필 변경: '+u['name'])
        for u in plan['updates']:
            row,_=upsert_revision(db,'project_profile','manual_project',u['project_id'],u['after'],BATCH)
            db.add(Audit(entity_id=row.entity_id,action='REVIEWED_ESTIMATE_RESTORE',before=u['before'],
                after=dict(revision_id=row.id,actor=ACTOR,reason=REASON,stages=u['stages'],original_profile_revision_id=u['expected_revision_id'])))
            written.append(dict(project_id=u['project_id'],revision_id=row.id,stages=u['stages']))
        assert digest(protected(db)) == plan['protected_digest']
    return dict(summary=plan['summary'],written=written,raw_targets_and_mappings_unchanged=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True);p=OUT/'plan.json';s=HomeService(engine_for())
    if args.apply:
        result=apply(s,json.loads(p.read_text()));(OUT/'applied.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    else:
        if p.exists():raise ValueError('기존 검토안 보존')
        result=prepare(s);p.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result['summary'],ensure_ascii=False))
