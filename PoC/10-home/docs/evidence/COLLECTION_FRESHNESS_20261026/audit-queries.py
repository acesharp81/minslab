import json,os
from datetime import datetime,timezone
from collections import Counter
from sqlalchemy import select,func,text
from backend.db import engine_for,Batch,Revision,CollectionJob
from backend.service import HomeService
from backend.sources import SOURCES
from backend.source_summary import source_metadata
from backend.source_authority import clean,public_url
from backend.collection_jobs import FAST
service=HomeService(engine_for(),'/app/data');cutoff=datetime(2026,10,22,15,tzinfo=timezone.utc)
result={'captured_at':datetime.now(timezone.utc).isoformat(),'since':'2026-10-23T00:00:00+09:00','sources':[]}
with service.sessions() as db:
 db.execute(text("SET statement_timeout='60000'"))
 for s in SOURCES:
  sid=s['id'];r={k:s.get(k) for k in ['id','name','type','collection_mode','refresh_days','manual_only','implemented']};r.update(source_metadata(s));r['url']=public_url(s.get('url'));r['key_configured']=bool(not s.get('key_env') or any(os.environ.get(n,'').strip() for n in [s.get('key_env') or '',s.get('fallback_key_env') or '']));r['interval_seconds']=FAST.get(sid,s.get('refresh_days',1)*86400)
  batches=db.scalars(select(Batch).where(Batch.source_id==sid).order_by(Batch.started_at.desc()).limit(1)).all()
  success=db.scalar(select(Batch).where(Batch.source_id==sid,Batch.status=='SUCCESS').order_by(Batch.finished_at.desc()).limit(1))
  r['latest_batch']=[{'id':b.id,'started_at':b.started_at,'finished_at':b.finished_at,'status':b.status,'stats':clean(b.stats),'error_present':bool(b.error)} for b in batches]
  r['last_success']=success.finished_at if success else None
  r['batches_since']=dict(db.execute(select(Batch.status,func.count()).where(Batch.source_id==sid,Batch.started_at>=cutoff).group_by(Batch.status)).all())
  result['sources'].append(r)
 result['active_jobs']=[{'id':j.id,'source_id':j.source_id,'stage':j.stage,'status':j.status,'created_at':j.created_at,'run_after':j.run_after,'lease_until':j.lease_until,'attempts':j.attempts,'error':j.error} for j in db.scalars(select(CollectionJob).where(CollectionJob.status.in_(['QUEUED','RUNNING','RETRY'])))]
 result['recent_revisions']=[dict(r) for r in db.execute(text("""SELECT source_id,kind,count(*) revisions,count(distinct entity_id) entities,
 count(*) filter(where revision_no=1) first_revisions,max(recorded_at) last_recorded,
 max(sample_source_date) latest_source_date
 FROM home_revision WHERE recorded_at >= :cutoff GROUP BY source_id,kind"""),{'cutoff':cutoff}).mappings()]
 result['notice_samples']=[dict(r) for r in db.execute(text("""SELECT source_id,kind,entity_id,sample_name,sample_source_date,recorded_at,revision_no,payload
 FROM home_revision WHERE superseded_at is null AND kind in ('notice','notice_detail','news') AND sample_source_date >= '2026-10-16'
 ORDER BY sample_source_date DESC LIMIT 120""")).mappings()]
print(json.dumps(clean(result),ensure_ascii=False,default=str))
