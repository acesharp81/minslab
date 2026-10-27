import json,hashlib,os
from datetime import datetime,timezone
from pathlib import Path
from sqlalchemy import select,text
from backend.service import HomeService
from backend.db import engine_for,Revision,Batch
from backend.sources import SOURCES
s=HomeService(engine_for(),'/app/data')
out={'checked_at':datetime.now(timezone.utc).isoformat(),'collections':[]}
def fingerprint():
 result={}
 with s.sessions() as db:
  for table in ('home_mapping','home_program_mapping','home_identity_alias'):
   rows=db.execute(text('SELECT row_to_json(t)::text FROM '+table+' t')).scalars().all()
   result[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
  for kind in ('project','stage_evidence','mapping_decision','evidence_bridge'):
   rows=list(db.execute(select(Revision.entity_id,Revision.payload_hash).where(Revision.kind==kind,Revision.superseded_at.is_(None))))
   result[kind]={'count':len(rows),'sha256':hashlib.sha256(str(sorted(rows)).encode()).hexdigest()}
 return result
out['before']=fingerprint()
for source in [x for x in SOURCES if x.get('discovery_only')]:
 first=s.collect_one(source);second=s.collect_one(source)
 with s.sessions() as db:
  batch=db.scalar(select(Batch).where(Batch.source_id==source['id']).order_by(Batch.started_at.desc()).limit(1))
  docs=list(db.scalars(select(Revision).where(Revision.source_id==source['id'],Revision.superseded_at.is_(None))))
  result=dict(source_id=source['id'],first=first,second=second,stats={k:v for k,v in batch.stats.items() if k!='entity_ids'},items=[dict(id=r.entity_id,revision=r.revision_no,title=r.payload['name'],date=r.payload['source_date'],url=r.payload['evidence_url'],authority=r.payload['authority']) for r in docs])
 out['collections'].append(result)
 print(json.dumps(dict(source_id=source['id'],first=first,second=second),ensure_ascii=False),flush=True)
os.environ['POC10_EUM_DETAILS_PER_BATCH']='1';os.environ['POC10_EUM_BACKFILL_PAGES']='1'
source=next(x for x in SOURCES if x['id']=='eum_housing_notices')
out['eum_result']=s.collect_one(source)
with s.sessions() as db:
 batch=db.scalar(select(Batch).where(Batch.source_id==source['id']).order_by(Batch.started_at.desc()).limit(1))
 out['eum_stats']={k:v for k,v in batch.stats.items() if k not in ('entity_ids','detail_checked','detail_retry_after')}
 out['eum_recovered']=[dict(id=r.entity_id,attachments=[{k:a.get(k) for k in ('name','status','text_scope','error','text_attempted_on')} for a in r.payload.get('attachments',[]) if a.get('text_extractor_version')]) for r in db.scalars(select(Revision).where(Revision.source_id==source['id'],Revision.kind=='document_evidence',Revision.batch_id==batch.id))]
out['after']=fingerprint();out['preserved']=out['before']==out['after']
Path('/tmp/home-collection-verification.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps(dict(eum=out['eum_result'],stats=out['eum_stats'],preserved=out['preserved']),ensure_ascii=False),flush=True)
