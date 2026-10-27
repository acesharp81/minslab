import json
from sqlalchemy import select
from backend.db import engine_for,Revision,upsert_revision
from backend.service import HomeService
from backend.collectors import Fetcher
from backend.lh_notice_detail import parse_detail
s=HomeService(engine_for(),'/app/data');out=[]
for eid in ['DOC_2591b4881d28e4b3cf2d3f1d','DOC_a432cbfcef42510fcfb521a2']:
 with s.sessions() as db:
  old=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
  p=old.payload;n=db.scalar(select(Revision).where(Revision.entity_id==p['notice_entity_id'],Revision.superseded_at.is_(None)))
  notice=dict(n.payload,id=n.entity_id,revision_no=n.revision_no)
  fetcher=Fetcher('lh_notice_detail','/tmp/lh-repeat-check')
  try:
   body=fetcher.get(p['evidence_url']);current=parse_detail(body,notice,(p['region'],p['district'],p['block']))
   current['original_file']='raw/'+fetcher.manifest[-1]['file']
   _,outcome=upsert_revision(db,'document_evidence','lh_notice_detail',p['notice_no'],current,'read-only-verification')
   out.append(dict(id=eid,name=p['name'],revision_no=old.revision_no,outcome=outcome,changed_fields=[k for k in set(p)|set(current) if p.get(k)!=current.get(k)]))
  finally:fetcher.close();db.rollback()
print(json.dumps(out,ensure_ascii=False,indent=2))
