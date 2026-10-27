import json
from pathlib import Path
from urllib.parse import urlencode
from sqlalchemy import select
from backend.db import engine_for,Revision
from backend.service import HomeService
from backend.collectors import Fetcher
from backend.ih_public import HOST,BOARDS,parse_list,is_housing_notice
from backend.source_authority import clean
s=HomeService(engine_for(),'/app/data');out={'ih_head_pages':[],'new_lh_first_seen':[],'new_lh_links':[]}
fetcher=Fetcher('freshness_audit','/tmp/home-freshness-raw')
try:
 for board,params in BOARDS.items():
  url=HOST+'/main/bbs/bbsMsgList.do?'+urlencode(dict(params,pgno=1))
  try:
   rows,meta=parse_list(fetcher.get(url),board,1)
   saved={r.get('source_object_id') for r in s.rows('document_evidence') if r['source_id']=='ih_notice'}
   out['ih_head_pages'].append({'board':board,'url':url,'meta':meta,'rows':[dict(r,eligible_housing=is_housing_notice(r['name']),stored=r['source_object_id'] in saved) for r in rows]})
  except Exception as e:out['ih_head_pages'].append({'board':board,'url':url,'error_type':type(e).__name__})
finally:fetcher.close()
ids=['LH__ed83eac5921e491d31e4a01d','LH__294e6ed9d86653e1bc706889','DOC_2591b4881d28e4b3cf2d3f1d','DOC_a432cbfcef42510fcfb521a2']
with s.sessions() as db:
 for eid in ids:
  first=db.scalar(select(Revision).where(Revision.entity_id==eid).order_by(Revision.revision_no).limit(1))
  current=db.scalar(select(Revision).where(Revision.entity_id==eid,Revision.superseded_at.is_(None)))
  out['new_lh_first_seen'].append({'id':eid,'first_saved':first.recorded_at,'latest_revision':current.revision_no,'name':current.payload.get('name')})
 for r in db.scalars(select(Revision).where(Revision.kind.in_(['stage_evidence','collection_link','evidence_bridge']),Revision.superseded_at.is_(None))):
  p=r.payload
  if any(eid in json.dumps(p) for eid in ids):out['new_lh_links'].append({'kind':r.kind,'id':r.entity_id,'project_id':p.get('project_id'),'status':p.get('status'),'payload':p})
print(json.dumps(clean(out),ensure_ascii=False,default=str))
