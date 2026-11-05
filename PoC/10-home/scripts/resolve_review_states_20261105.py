"""Execute individually reviewed dispositions, independently from policy/metric approval.
Default is dry-run. A checked plan supplies source/review revisions; replay is idempotent.
"""
import argparse,json,hashlib
from pathlib import Path
from collections import Counter
from sqlalchemy import select
from backend.db import Revision,Mapping,ProgramMapping,engine_for,entity_id
from backend.service import HomeService
from backend.publication_reviews import save as review,queue
from backend.mapping_decisions import save as mapping_decision
from backend.publication_evidence import save as assess
from backend.publication_supplements import save as supplement
from backend.hold_review import save as annotate
from backend.mapping_workbench import build
from backend.publication_review_export import export_json

PROTECTED=('project','project_profile','goal','execution_schedule','policy_profile','stage_proposal','stage_evidence','policy','program_source','program_district_plan','policy_delivery_plan')

def snapshot(s):
 with s.sessions() as db:
  rows=[tuple(r) for r in db.execute(select(Revision.kind,Revision.entity_id,Revision.payload_hash).where(Revision.kind.in_(PROTECTED),Revision.superseded_at.is_(None)).order_by(Revision.kind,Revision.entity_id))]
  links=[{c.name:getattr(m,c.name) for c in Mapping.__table__.columns} for m in db.scalars(select(Mapping).order_by(Mapping.id))]
  programs=[{c.name:getattr(m,c.name) for c in ProgramMapping.__table__.columns} for m in db.scalars(select(ProgramMapping).order_by(ProgramMapping.id))]
  decisions={r.payload['document_id']:(r.id,r.payload_hash) for r in db.scalars(select(Revision).where(Revision.kind=='publication_review',Revision.superseded_at.is_(None)))}
  bridges={r.entity_id:(r.payload_hash,r.payload) for r in db.scalars(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))}
 return dict(rows=rows,mappings=links,programs=programs,decisions=decisions,bridges=bridges)


def run(folder,apply=False):
 p=Path(folder);plan=json.loads((p/'plan.json').read_text());s=HomeService(engine_for(),'/app/data');pubs=plan['publications'];projects=plan['projects'];actor=plan['actor']
 assert len(pubs)==len({r['document_id'] for r in pubs})==53 and len(projects)==len({r['project_id'] for r in projects})==53
 assert Counter(r['status'] for r in pubs)==dict(APPROVED=2,EXCLUDED=14,HOLD=37)
 live={r['id']:r for r in queue(s)['items']};view=build(s);items={r['id']:r for r in view['items']};before=snapshot(s)
 completed=lambda old,x:old.get('actor')==actor and old.get('reason')==x['reason'] and old.get('status')==x['status']
 for x in pubs:
  r=live[x['document_id']];assert r['source_hash']==x['source_hash'] and r['source_revision_no']==x['source_revision_no']
  assert completed(r.get('decision') or {},x) or (r['status']=='REVIEW' and r['review_revision_no']==x['review_revision_no'])
  if x['status']=='APPROVED':assert x['project_ids']==['PRO_1fbf5c7629634fa05be7652a'] and x['source_checked']
 for x in projects:
  r=items[x['project_id']];assert r['mapping']['policy_id']=='UNASSIGNED'
  assert r['review']['group']=='UNLINKED' or ((r.get('decision') or {}).get('actor')==actor and r['review']['group']=='EXCLUDED')
  assert any(v['category']=='D' and v['report_sha256']==x['report_sha256'] for v in r['policy_relations'])
  if r['review']['group']=='UNLINKED':assert (r.get('decision') or {}).get('revision_no',0)==x['revision_no']
 with s.sessions() as db:
  records=list(db.scalars(select(Revision).where(Revision.kind.in_(['publication_assessment','hold_cross_review']),Revision.superseded_at.is_(None))))
 old_assess={r.payload['document_id']:r.payload for r in records if r.kind=='publication_assessment'}
 notes={r.payload['subject']:dict(r.payload) for r in records if r.kind=='hold_cross_review'}
 print(json.dumps(dict(preflight=True,apply=apply,project_exclusions=53,publications=dict(Counter(r['status'] for r in pubs))),ensure_ascii=False),flush=True)
 if not apply:return
 if not (p/'before.json').exists():(p/'before.json').write_text(json.dumps(before,ensure_ascii=False,default=str))
 # Each save uses the existing audited service and optimistic revision checks.
 results=[]
 for x in projects:
  r=items[x['project_id']]
  if r['review']['group']=='EXCLUDED':continue
  result=mapping_decision(s,'project',x['project_id'],action='EXCLUDE',revision_no=x['revision_no'],actor=actor,reason=x['reason'],evidence_url=x['evidence_url']);assert not result.get('conflict');results.append(dict(project_id=x['project_id'],result=result))
 for x in pubs:
  did=x['document_id'];current=live[did];old=current.get('decision') or {}
  if not completed(old,x):
   if did in plan['supplements']:
    f=plan['supplements'][did];supplement(s,did,x['source_revision_no'],f['text'][1],'주택 공급사업 대상 여부 확인: '+x['reason'],[],actor,f['raw']['sha256'])
   args={k:x[k] for k in ('document_id','source_revision_no','review_revision_no','status','policy_id','project_ids','new_project_names','actor','reason','source_checked','expected_projects')}
   result=review(s,**args);assert not result.get('conflict');revision=result['revision_no'];results.append(dict(document_id=did,result=result))
  else:revision=current['review_revision_no']
  # Re-check original quotes and hashes at the new decision revision. No facts are added.
  if did in old_assess:
   a=dict(old_assess[did]);a['review_revision_no']=revision;a['actor']=actor;a['reason']='업무상태 처리 후 기존 인용·본문 해시 재대조. '+x['reason']
   result=assess(s,did,x['source_revision_no'],revision,a);results.append(dict(document_id=did,assessment=result))
  note=notes[did];note.pop('reviewed_at',None);note.pop('effect',None)
  note.update(actor=actor,after_state=x['status'],outcome=x['reason'],business_approval=x['status']=='APPROVED',metric_approval=False,
    workflow_resolution=dict(before_status='REVIEW',after_status=x['status'],reason=x['reason'],project_ids=x['project_ids'],actor=actor,metric_approval=False,review_revision_no=revision))
  with s.sessions() as db:
   ref_ids={did,entity_id('publication_review','publication_review',did),entity_id('publication_supplement','publication_manual',did),entity_id('publication_assessment','officer_evidence',did)} | {r['id'] for r in note['refs']}
   refs=list(db.scalars(select(Revision).where(Revision.entity_id.in_(ref_ids),Revision.superseded_at.is_(None))))
   note['refs']=[dict(kind=r.kind,id=r.entity_id,hash=r.payload_hash,revision_no=r.revision_no,revision_id=r.id) for r in refs]
  annotate(s,note)
 after=snapshot(s);assert before['rows']==after['rows'] and before['mappings']==after['mappings'] and before['programs']==after['programs']
 target_ids={x['document_id'] for x in pubs}
 assert {k:v for k,v in before['decisions'].items() if k not in target_ids}=={k:v for k,v in after['decisions'].items() if k not in target_ids}
 allowed={entity_id('evidence_bridge','cross_source',pid+':'+x['document_id']) for x in pubs for pid in x['project_ids']}
 assert {k:v for k,v in before['bridges'].items() if k not in allowed}=={k:v for k,v in after['bridges'].items() if k not in allowed}
 for key in allowed:assert after['bridges'][key][1]['facts']==[] and after['bridges'][key][1]['units'] is None
 final=queue(s);mapped=build(s);all_evidence=export_json(s,status='ALL')['items'];chosen=[r for r in all_evidence if r['document_id'] in target_ids]
 assert len(chosen)==53 and all(r['cross_review']['current'] for r in chosen)
 assert all(not r['aggregate_allowed'] for r in chosen) and sum(r['linkage_confirmed'] for r in chosen)==2
 assert not any(r['needs_revalidation'] for r in chosen)
 summary=dict(project_before={k:v['projects'] for k,v in view['counts'].items()},project_after={k:v['projects'] for k,v in mapped['counts'].items()},publication_before=dict(Counter(r['status'] for r in live.values())),publication_after=final['counts'],changed_publications=dict(Counter(r['status'] for r in pubs)),policy_actuals_unchanged=True,project_mappings_unchanged=True,new_evidence_bridges=2,new_actual_units=0,processed_cross_reviews_current=True,old_facts_revalidated=True,protected_sha256=hashlib.sha256(json.dumps(after['rows']).encode()).hexdigest())
 (p/'applied.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(p/'actions.json').write_text(json.dumps(results,ensure_ascii=False,default=str,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--apply',action='store_true');a=parser.parse_args();run(a.folder,a.apply)
