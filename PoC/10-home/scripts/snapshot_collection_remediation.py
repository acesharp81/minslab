"""Read-only live evidence for the 2026-10-19 collection remediation.

Run in the HOME API environment; redirect stdout to a private evidence JSON.
This does not collect data, modify approvals, or publish an artifact.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import select, text
from backend.db import engine_for, Revision, Mapping, IdentityAlias, ProjectEvidence, CollectionJob
from backend.service import HomeService
from backend.construction_candidates import eligible
from backend.annual_supply import annual_supply


def main():
    service = HomeService(engine_for())
    result = dict(captured_at=datetime.now(timezone.utc).isoformat())
    result['sources'] = service.sources()
    result['annual_2026'] = [r for r in annual_supply(service)['rows']
                           if r['year'] == 2026 and r['region'] in ('서울특별시', '인천광역시', '경기도')]
    with service.sessions.begin() as db:
        db.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        result['mappings'] = [dict(project_id=r.project_id, policy_id=r.policy_id,
            program_id=r.program_id, status=r.status, revision_no=r.revision_no, basis=r.basis)
            for r in db.scalars(select(Mapping).where(Mapping.status == 'CONFIRMED').order_by(Mapping.project_id))]
        result['profiles'] = [dict(entity_id=r.entity_id, payload_hash=r.payload_hash)
            for r in db.scalars(select(Revision).where(Revision.kind == 'project_profile',
                Revision.superseded_at.is_(None)).order_by(Revision.entity_id))]
        aliases = {r.source_entity_id:r for r in db.scalars(select(IdentityAlias))}
        evidence = {(r.project_id, r.revision_id) for r in db.scalars(select(ProjectEvidence))}
        stamp = Revision.payload['dates']['실제착공일 (realStcnsDay)'].as_string()
        rows = db.scalars(select(Revision).where(Revision.kind == 'general_permit',
            Revision.superseded_at.is_(None), stamp >= '2026-01-01', stamp <= '2026-10-19')).all()
        candidates = []
        for r in rows:
            p = r.payload
            if not eligible(p, '2026-01-01', '2026-10-19'):continue
            a = aliases.get(r.entity_id)
            candidates.append(dict(entity_id=r.entity_id, name=p.get('name'), address=p.get('address'),
                units=p.get('units'), actual_start=p['dates']['실제착공일 (realStcnsDay)'],
                identity=a.project_id if a else None, status=a.relation_status if a else None,
                has_evidence=bool(a and (a.project_id, r.id) in evidence)))
        result['construction_candidates'] = sorted(candidates, key=lambda r:r['entity_id'])
        details = db.scalars(select(Revision).where(Revision.source_id == 'seoul_cleanup',
            Revision.kind == 'document_evidence', Revision.superseded_at.is_(None))).all()
        result['seoul_details'] = [dict(entity_id=r.entity_id, payload=r.payload) for r in details]
        stats = db.scalars(select(Revision).where(Revision.kind.in_(('statistic', 'statistic_reference')),
            Revision.superseded_at.is_(None), Revision.sample_region.in_(('서울특별시','인천광역시','경기도')),
            Revision.payload['statistic_period'].as_string() >= '202601',
            Revision.payload['statistic_period'].as_string() <= '202608')).all()
        result['statistics'] = [dict(entity_id=r.entity_id, kind=r.kind, source_id=r.source_id,
            payload=r.payload) for r in stats if r.payload.get('statistic_metric') in ('인허가','착공','준공','분양승인')]
        result['jobs'] = [dict(id=r.id, source_id=r.source_id, status=r.status, stage=r.stage,
            created_at=str(r.created_at), finished_at=str(r.finished_at), run_after=str(r.run_after))
            for r in db.scalars(select(CollectionJob).order_by(CollectionJob.created_at.desc()).limit(100))]
        result['raw_counts'] = dict(Counter(db.scalars(select(Revision.kind).where(
            Revision.kind.in_(('permit','general_permit','project','statistic_reference')),
            Revision.superseded_at.is_(None)))))
    result['snapshot_note'] = 'DB detail section is a read-only repeatable-read snapshot; source and annual API calculations precede it.'
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
