import json
from datetime import datetime
from sqlalchemy import select,func,text
from backend.db import engine_for,Revision,Batch
from backend.service import HomeService
from backend.collection_schema import document_sources
from backend.source_authority import clean,authority
s=HomeService(engine_for(),'/app/data');out={'document_publishers':document_sources(s)}
with s.sessions() as db:
 db.execute(text("SET statement_timeout='60000'"))
 kinds=['notice','lh_notice','gh_notice','notice_catalogue','document_evidence']
 out['notice_inventory']=[dict(r) for r in db.execute(text('''SELECT source_id,kind,count(*) records,max(sample_source_date) latest_published,max(recorded_at) latest_saved,
 count(*) filter(where sample_source_date >= '2026-10-23') published_since,
 count(*) filter(where sample_source_date >= '2026-10-16') published_since_oct16
 FROM home_revision WHERE superseded_at is null AND kind=ANY(:kinds) GROUP BY source_id,kind'''),{'kinds':kinds}).mappings()]
 out['recent_samples']=[];out['nonofficial']=[]
 for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind.in_(kinds),Revision.sample_source_date>='2026-10-16').order_by(Revision.sample_source_date.desc())):
  p=r.payload;out['recent_samples'].append({'id':r.entity_id,'source_id':r.source_id,'kind':r.kind,'name':p.get('name'),'source_date':r.sample_source_date,'recorded_at':r.recorded_at,'revision_no':r.revision_no,'evidence_url':p.get('evidence_url'),'facts':p.get('facts'),'policy_candidate_only':p.get('policy_candidate_only'),'verification_status':p.get('verification_status')})
 for r in db.scalars(select(Revision).where(Revision.superseded_at.is_(None),Revision.kind=='document_evidence')):
  p=r.payload
  if authority(p.get('evidence_url') or p.get('source_url'),r.source_id)=='NONOFFICIAL':out['nonofficial'].append({'id':r.entity_id,'source_id':r.source_id,'name':p.get('name'),'source_date':r.sample_source_date,'recorded_at':r.recorded_at,'evidence_url':p.get('evidence_url')})
 out['recent_failures']=[{'source_id':b.source_id,'started_at':b.started_at,'finished_at':b.finished_at,'error':b.error} for b in db.scalars(select(Batch).where(Batch.status=='FAILED',Batch.started_at>=datetime.fromisoformat('2026-10-22T15:00:00+00:00')))]
 r=db.scalar(select(Revision).where(Revision.source_id=='lh_notice_detail',Revision.superseded_at.is_(None)).order_by(Revision.recorded_at.desc()).limit(1))
 if r:
  prior=db.scalar(select(Revision).where(Revision.id==r.previous_id));out['repeat_example']={'id':r.entity_id,'current_revision':r.revision_no,'previous_time':prior.recorded_at if prior else None,'current_time':r.recorded_at,'changed_fields':[k for k in set(r.payload)|set(prior.payload) if r.payload.get(k)!=prior.payload.get(k)] if prior else []}
print(json.dumps(clean(out),ensure_ascii=False,default=str))
