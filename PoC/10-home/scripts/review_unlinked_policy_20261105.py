"""Apply reviewed POLICY_REFERENCE records only; default is read-only preflight."""
import argparse,hashlib,json
from pathlib import Path
from collections import Counter
from sqlalchemy import select
from backend.db import Revision,Mapping,ProgramMapping,engine_for
from backend.service import HomeService
from backend.project_policy_relations import save_reference,validate_reference


def protected(service):
    with service.sessions() as db:
        kinds=('project','project_profile','goal','execution_schedule','policy_profile','stage_proposal','evidence_bridge','publication_review','publication_assessment')
        records=[tuple(r) for r in db.execute(select(Revision.kind,Revision.entity_id,Revision.payload_hash).where(Revision.superseded_at.is_(None),Revision.kind.in_(kinds)).order_by(Revision.kind,Revision.entity_id))]
        mappings=sorted((m.project_id,m.policy_id,m.program_id,m.status,m.revision_no,m.basis,m.evidence_url) for m in db.scalars(select(Mapping)))
        programs=sorted((m.id,m.policy_id,m.status,m.revision_no,m.basis,m.evidence_url) for m in db.scalars(select(ProgramMapping)))
    return dict(records_sha256=hashlib.sha256(json.dumps(records,ensure_ascii=False).encode()).hexdigest(),mappings=mappings,programs=programs)


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--output',required=True);ap.add_argument('--apply',action='store_true');args=ap.parse_args()
    rows=json.loads(Path(args.input).read_text());assert len(rows)==len({r['project_id'] for r in rows})==98
    assert Counter(r['category'] for r in rows)==dict(A=3,B=3,C=39,D=53)
    s=HomeService(engine_for(),'/app/data');before=protected(s)
    actual={m[0]:m for m in before['mappings']}
    for r in rows:
        validate_reference(r);assert actual[r['project_id']][1]=='UNASSIGNED'
    with s.sessions() as db:
        current={r.entity_id:r for r in db.scalars(select(Revision).where(Revision.kind=='project',Revision.superseded_at.is_(None)))}
        for r in rows:assert current[r['project_id']].payload_hash==r['project_sha256'] and actual[r['project_id']][4]==r['mapping_revision_no']
    results=[save_reference(s,r) for r in rows] if args.apply else []
    after=protected(s);assert after==before,'Concurrent protected-data change; inspect before claiming unchanged'
    result=dict(applied=args.apply,count=len(rows),categories=dict(Counter(r['category'] for r in rows)),protected_unchanged=True,protected=after,results=results)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('protected','results')},ensure_ascii=False))

if __name__=='__main__':main()
