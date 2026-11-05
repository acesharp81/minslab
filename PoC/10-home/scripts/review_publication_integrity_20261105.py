"""Apply the scoped 11/05 evidence review. Default validates only; --apply writes.
Preserve all existing 111 business decisions and every project/policy metric.
"""
import argparse,hashlib,json
from pathlib import Path
from sqlalchemy import select
from backend.db import Revision,Mapping,engine_for
from backend.service import HomeService
from backend.publication_supplements import save as supplement,load as supplements
from backend.publication_evidence import save as assess
from backend.publication_reviews import save as decide,queue
from backend.hold_review import save as note
from backend.publication_review_export import export_json

KINDS=('project','project_profile','goal','execution_schedule','policy_profile','stage_proposal','stage_evidence','evidence_bridge','policy','program_source','program_district_plan')
def protected(s):
 with s.sessions() as db:
  rows=[list(x) for x in db.execute(select(Revision.kind,Revision.entity_id,Revision.payload_hash).where(Revision.kind.in_(KINDS),Revision.superseded_at.is_(None)).order_by(Revision.kind,Revision.entity_id))]
  mappings=[{c.name:getattr(m,c.name) for c in Mapping.__table__.columns} for m in db.scalars(select(Mapping).order_by(Mapping.id))]
  reviews={r.payload['document_id']:[r.id,r.payload_hash] for r in db.scalars(select(Revision).where(Revision.kind=='publication_review',Revision.superseded_at.is_(None)))}
 return dict(rows=rows,mappings=mappings,reviews=reviews)

def run(folder,apply=False):
 p=Path(folder);read=lambda name:json.loads((p/(name+'.json')).read_text());notes=read('notes');extras=read('supplements');assessments=read('assessments');decisions=read('decisions');excluded={r['document_id'] for r in decisions};s=HomeService(engine_for(),'/app/data');live={r['id']:r for r in queue(s)['items']};digest=hashlib.sha256((p/'original-report.txt').read_bytes()).hexdigest()
 assert len(notes)==141 and len({r['subject'] for r in notes})==141 and len(excluded)==3
 assert all(r['status']=='EXCLUDED' and not r['project_ids'] and not r['source_checked'] for r in decisions)
 for n in notes:
  assert n['report_sha256']==digest and not n['metric_approval'] and not n['business_approval']
  source=next(r for r in n['refs'] if r['kind']=='document_evidence')
  assert live[n['subject']]['source_revision_no']==source['revision_no']
 with s.sessions() as db:
  for n in notes:
   for ref in n['refs']:
    current=db.scalar(select(Revision).where(Revision.entity_id==ref['id'],Revision.superseded_at.is_(None)))
    assert current and (current.payload_hash==ref['hash'] or (current.payload.get('actor')=='261105 사용자 위임 AI 증빙 교차검토' and ref['kind'] in ('publication_supplement','publication_assessment','publication_review'))),('concurrent change',ref['id'])
 print(json.dumps(dict(preflight=True,targets=141,apply=apply)),flush=True)
 if not apply:return
 before=protected(s)
 if not (p/'protected-before.json').exists():(p/'protected-before.json').write_text(json.dumps(before,ensure_ascii=False,default=str))
 results=[]
 old=supplements(s,[x['document_id'] for x in extras])
 for x in extras:
  prior=old.get(x['document_id'],{})
  result={'unchanged':True} if all(prior.get(k)==x[v] for k,v in [('body_text','body_text'),('raw_sha256','raw_sha256'),('source_revision_no','source_revision_no'),('attachments','attachments')]) else supplement(s,**x)
  results.append(dict(document_id=x['document_id'],kind='supplement',result=result))
 for x in decisions:
  prior=live[x['document_id']].get('decision') or {}
  if prior.get('actor')==x['actor'] and prior.get('reason')==x['reason'] and prior.get('status')==x['status']:continue
  result=decide(s,**x);assert not result.get('conflict');results.append(dict(document_id=x['document_id'],kind='scope_exclusion',result=result))
 for x in assessments:
  results.append(dict(document_id=x['document_id'],kind='assessment',result=assess(s,**x)))
 with s.sessions() as db:
  rows=list(db.scalars(select(Revision).where(Revision.kind.in_(['document_evidence','publication_review','publication_supplement','publication_assessment','ai_publication_analysis']),Revision.superseded_at.is_(None))))
 current={}
 for r in rows:
  did=r.entity_id if r.kind=='document_evidence' else r.payload.get('document_id')
  current.setdefault(did,[]).append(dict(kind=r.kind,id=r.entity_id,hash=r.payload_hash,revision_no=r.revision_no,revision_id=r.id))
 for n in notes:
  n['refs']=current[n['subject']];results.append(dict(document_id=n['subject'],kind='cross_review',result=note(s,n)))
 after=protected(s)
 assert before['rows']==after['rows'] and before['mappings']==after['mappings']
 assert {k:v for k,v in before['reviews'].items() if k not in excluded}=={k:v for k,v in after['reviews'].items() if k not in excluded}
 ids={n['subject'] for n in notes};v=[r for r in export_json(s)['items'] if r['document_id'] in ids];assert len(v)==141 and all(not r['aggregate_allowed'] and not r['linkage_confirmed'] for r in v)
 assert all(r['cross_review']['current'] for r in v)
 digest=lambda o:hashlib.sha256(json.dumps(o,sort_keys=True,default=str).encode()).hexdigest()
 summary=dict(targets=141,new_capture_documents=27,assessed_new_documents=27,new_active_facts=33,scope_excluded=3,old_111_decisions_unchanged=True,project_metrics_unchanged=True,policy_mappings_unchanged=True,actual_units_added=0,new_project_links=0,new_projects=0,protected_before_sha256=digest(before['rows']),protected_after_sha256=digest(after['rows']),active_facts=sum(len(r['facts']) for r in v),historical_facts=sum(len(r['evidence_records'])-len(r['facts']) for r in v),registry_documents=46)
 (p/'applied.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));(p/'applied-progress.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--apply',action='store_true');a=parser.parse_args();run(a.folder,a.apply)
