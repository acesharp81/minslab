"""Pin the 11/04 independent review annotations; never change business decisions.
Default: validate plan/report/revision hashes only. --apply writes hold_cross_review.
"""
import argparse,hashlib,json
from pathlib import Path
from sqlalchemy import select
from backend.db import Revision,Mapping,engine_for
from backend.service import HomeService
from backend.hold_review import save,load

PROTECTED=('project','project_profile','goal','execution_schedule','policy_profile','stage_proposal','evidence_bridge','publication_review','publication_assessment')

def protected(service):
 with service.sessions() as db:
  rows=[list(x) for x in db.execute(select(Revision.kind,Revision.entity_id,Revision.payload_hash).where(Revision.kind.in_(PROTECTED),Revision.superseded_at.is_(None)).order_by(Revision.kind,Revision.entity_id))]
  mappings=[{c.name:getattr(m,c.name) for c in Mapping.__table__.columns} for m in db.scalars(select(Mapping).order_by(Mapping.id))]
 return dict(rows=rows,mappings=mappings)

def run(folder,apply=False):
 folder=Path(folder);plan=json.loads((folder/'plan.json').read_text());report_hash=hashlib.sha256((folder/'original-report.txt').read_bytes()).hexdigest()
 s=HomeService(engine_for(),'/app/data');notes=plan['reviews']
 assert len(notes)==111 and len({n['subject'] for n in notes})==111
 with s.sessions() as db:
  ids={ref['id'] for n in notes for ref in n['refs']}
  current={r.entity_id:r for r in db.scalars(select(Revision).where(Revision.entity_id.in_(ids),Revision.superseded_at.is_(None)))}
  for n in notes:
   assert n['report_sha256']==report_hash
   assert n['before_state']==n['after_state'] and not n['business_approval'] and not n['metric_approval']
   for ref in n['refs']:
    assert ref['id'] in current and current[ref['id']].payload_hash==ref['hash'],('source changed',ref['id'])
 print(json.dumps(dict(preflight=True,targets=len(notes),apply=apply)),flush=True)
 if not apply:return
 before=protected(s);(folder/'protected-before.json').write_text(json.dumps(before,ensure_ascii=False,default=str))
 outcomes=[]
 for n in notes:
  outcomes.append(dict(subject=n['subject'],result=save(s,n)))
  (folder/'progress.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2))
 after=protected(s);assert before==after,'protected business state changed'
 current_notes=load(s,[n['subject'] for n in notes]);assert len(current_notes)==111 and all(n['current'] for n in current_notes.values())
 digest=lambda v:hashlib.sha256(json.dumps(v,sort_keys=True,default=str).encode()).hexdigest()
 summary=dict(targets=111,new_annotations=sum(not x['result'].get('unchanged',False) for x in outcomes),all_current=True,existing_business_decisions_changed=0,new_projects=0,actual_units_added=0,protected_before_sha256=digest(before),protected_after_sha256=digest(after),registration_review=46,event_groups=9)
 (folder/'applied.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('--apply',action='store_true');a=p.parse_args();run(a.folder,a.apply)
