"""Pinned, delegated review of eight official LH policy follow-up blocks."""
import argparse
import hashlib
import json
from collections import Counter
from sqlalchemy import select
from backend.db import engine_for, Revision, Mapping, ProgramMapping
from backend.service import HomeService
from backend.lh_policy_followup import admit_reviewed


def protected(service):
    with service.sessions() as db:
        result = {f'revision:{r.entity_id}': r.payload_hash for r in db.scalars(
            select(Revision).where(Revision.superseded_at.is_(None),
                Revision.kind.in_(['project', 'project_profile', 'execution_schedule'])))}
        for m in db.scalars(select(Mapping)):
            result['mapping:' + m.project_id] = [m.policy_id, m.program_id, m.status, m.revision_no, m.basis, m.evidence_url]
        for p in db.scalars(select(ProgramMapping)):
            result['program:' + p.id] = [p.name, p.policy_id, p.status]
    return result


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def main(apply=False):
    service = HomeService(engine_for())
    before = protected(service)
    result = admit_reviewed(service, apply=apply)
    after = protected(service)
    changed = [key for key, value in before.items() if after.get(key) != value]
    result.update(protected_existing_records=len(before), protected_before=digest(before),
                  protected_after=digest({key: after.get(key) for key in before}),
                  changed_existing_keys=changed, protected_unchanged=not changed)
    path = service.data_dir / ('policy-readmission-applied-20261019.json' if apply else 'policy-readmission-review-20261019.json')
    # Keep the initial admission audit when a repeat invocation only preserves rows.
    if path.exists() and all(p['result'] == 'existing_preserved' for p in result['projects']):
        path = service.data_dir / 'policy-readmission-idempotence-20261019.json'
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(dict(file=str(path), results=dict(Counter(p['result'] for p in result['projects'])),
                         units=sum(p['units'] for p in result['projects']), protected_unchanged=not changed), ensure_ascii=False))
    if changed:
        raise RuntimeError('기존 승인 기록 변경 확인 필요: ' + ', '.join(changed))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    main(parser.parse_args().apply)
