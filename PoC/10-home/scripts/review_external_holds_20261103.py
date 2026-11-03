"""Apply the reviewed 2026-11-03 plan; default is read-only preflight.
Run inside the home API environment with plan.json and original-report.txt in
/data/raw/officer_review/20261103. Uses existing validated review services.
"""
import argparse,json,hashlib
from pathlib import Path
from sqlalchemy import select
from backend.db import Revision,Mapping,engine_for,entity_id
from backend.service import HomeService
from backend.publication_reviews import queue,save as decide
from backend.publication_supplements import save as supplement,load as supplements
from backend.hold_review import save as annotate,load as annotations
from backend.stage_reconciliation import current,reference,list_items


def run(folder,apply=False):
 service=HomeService(engine_for(),'/app/data');folder=Path(folder);plan=json.loads((folder/'plan.json').read_text());report_sha=hashlib.sha256((folder/'original-report.txt').read_bytes()).hexdigest()
 assert len(plan['reviews'])==278 and len({x['subject'] for x in plan['reviews']})==278
 q=queue(service);docs={x['id']:x for x in q['items']};projects={x['id']:x for x in q['projects']};stages={x['id']:x for x in list_items(service)}
 def protected():
  with service.sessions() as db:
   kinds=['project','project_profile','goal','stage_evidence','execution_schedule','policy_profile','program_source','program_district_plan','stage_proposal']
   rows=[(x.kind,x.entity_id,x.revision_no,x.payload_hash) for x in db.scalars(select(Revision).where(Revision.kind.in_(kinds),Revision.superseded_at.is_(None)).order_by(Revision.kind,Revision.entity_id))]
   mappings=[{c.name:getattr(m,c.name) for c in Mapping.__table__.columns} for m in db.scalars(select(Mapping).order_by(Mapping.project_id))]
   bridges=[(x.entity_id,x.payload_hash) for x in db.scalars(select(Revision).where(Revision.kind=='evidence_bridge',Revision.superseded_at.is_(None)))]
  return dict(rows=rows,mappings=mappings,bridges=sorted(bridges))
 before=protected()
 for d in plan['decisions']:
  live=docs[d['document_id']];prior=live.get('decision') or {};repeated=all(prior.get(k)==d[k] for k in ('status','actor','reason'))
  assert live['source_revision_no']==d['source_revision_no'] and (live['review_revision_no']==d['review_revision_no'] or repeated),('document changed',d['document_id'])
 for r in plan['reviews']:
  if r['kind']=='STAGE':assert stages[r['subject']]['revision_no']==r['target_revision_no'],('stage changed',r['subject'])
  else:assert docs[r['subject']]['source_revision_no']==r['source_revision_no'],('source changed',r['subject'])
 for item in plan['supplements']:
  artifact=folder/'artifacts'/(item['raw_sha256']+'.raw')
  assert artifact.is_file() and hashlib.sha256(artifact.read_bytes()).hexdigest()==item['raw_sha256']
 print(json.dumps(dict(preflight=True,supplements=len(plan['supplements']),decisions=len(plan['decisions']),annotations=len(plan['reviews']),apply=apply)),flush=True)
 if not apply:return
 if not (folder/'protected-before.json').exists():(folder/'protected-before.json').write_text(json.dumps(before,ensure_ascii=False,indent=2,default=str))
 outcomes=[]
 def checkpoint(): (folder/'progress.json').write_text(json.dumps(outcomes,ensure_ascii=False,indent=2))
 prior=supplements(service,[x['document_id'] for x in plan['supplements']])
 for d in plan['supplements']:
  old=prior.get(d['document_id'],{})
  if all(old.get(k)==d[k] for k in ('source_revision_no','raw_sha256','body_text')):result={'unchanged':True}
  else:result=supplement(service,**d)
  outcomes.append(dict(kind='supplement',subject=d['document_id'],result=result));checkpoint()
 for d in plan['decisions']:
  old=docs[d['document_id']].get('decision') or {}
  if all(old.get(k)==d[k] for k in ('status','actor','reason')):result={'unchanged':True,'status':d['status']}
  else:result=decide(service,**d,expected_projects={pid:projects[pid]['revision_no'] for pid in d['project_ids']})
  if result.get('conflict'):raise RuntimeError('Concurrent review change: '+d['document_id'])
  outcomes.append(dict(kind='decision',subject=d['document_id'],result=result));checkpoint()
 # Capture the final decision/supplement references separately from imported recommendations.
 for item in plan['reviews']:
  r=dict(item);refs=[]
  with service.sessions() as db:
   target=current(db,'stage_proposal' if r['kind']=='STAGE' else 'document_evidence',r['subject']);refs.append(reference(target))
   if r['kind']=='DOCUMENT':
    for kind,owner in [('publication_review','publication_review'),('publication_supplement','publication_manual')]:
     ref=current(db,kind,entity_id(kind,owner,r['subject']))
     if ref:refs.append(reference(ref))
   else:
    p=target.payload
    for ref in [p['source_ref']]+p.get('related_refs',[])+([p['body_ref']] if p.get('body_ref') else []):
     current_ref=current(db,ref['kind'],ref['id'])
     if current_ref:refs.append(reference(current_ref))
    body=p.get('proof',{}).get('body','');r['findings'].append('저장된 실제 원문 본문 '+str(len(body))+'자 · 인용문과 별도')
    r['findings'].append('동일 사건 후보 '+str(len(stages[r['subject']].get('duplicate_ids',[])))+'건 · 다른 값 후보 '+str(len(stages[r['subject']].get('different_value_ids',[])))+'건')
  r.update(refs=refs,report_id='OFFICER_HOLD_REVIEW_20261103',report_sha256=report_sha,actor='261103 사용자 위임 AI 교차검토')
  result=annotate(service,r);outcomes.append(dict(kind='cross_review',subject=r['subject'],result=result));checkpoint()
 after=protected();assert before['rows']==after['rows'],'business/profile/stage proposals changed';assert before['mappings']==after['mappings'],'policy mapping changed'
 assert set(before['bridges']).issubset(set(after['bridges']))
 new=set(after['bridges'])-set(before['bridges']);assert len(new)<=1
 with service.sessions() as db:
  for bid,_ in new:
   p=current(db,'evidence_bridge',bid).payload
   assert p['project_id']=='PRO_6a66b31b8f84244d491514e6' and p['relation_type']=='DOCUMENT_REFERENCE' and not p['facts'] and p['units'] is None
 notes=annotations(service,[x['subject'] for x in plan['reviews']]);assert len(notes)==278 and all(x['current'] for x in notes.values())
 summary=dict(report_targets=278,document_targets=140,stage_targets=138,supplements=len(plan['supplements']),business_reviews=len(plan['decisions']),cross_reviews=len(notes),new_document_links=len(new),actual_units_added=0,protected_before_sha256=hashlib.sha256(json.dumps(before['rows']).encode()).hexdigest(),protected_after_sha256=hashlib.sha256(json.dumps(after['rows']).encode()).hexdigest(),policy_mappings_unchanged=True)
 (folder/'applied.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2));print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('folder');parser.add_argument('--apply',action='store_true');args=parser.parse_args();run(args.folder,args.apply)
