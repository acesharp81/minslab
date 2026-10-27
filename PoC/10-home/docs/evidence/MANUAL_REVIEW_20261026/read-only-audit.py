import json
from datetime import datetime,timezone
from collections import Counter
from sqlalchemy import select
from backend.db import engine_for,Revision,Batch
from backend.service import HomeService
from backend.sources import SOURCES
s=HomeService(engine_for(),'/app/data');out=dict(checked_at=datetime.now(timezone.utc).isoformat(),publications=[],ocr=[],failures=[],manual_sources=[])
watch={r['id'] for r in SOURCES if r.get('discovery_only')}
with s.sessions() as db:
 for r in db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.source_id.in_(watch),Revision.superseded_at.is_(None))):
  p=r.payload;out['publications'].append(dict(id=r.entity_id,source=r.source_id,**{k:p.get(k) for k in ('name','source_date','evidence_url','status','verification_status','facts','matched_project_ids')}))
 statuses=Counter();failed_docs=0;unique_files={};ocr_files=set()
 for r in db.scalars(select(Revision).where(Revision.kind=='document_evidence',Revision.source_id=='eum_housing_notices',Revision.superseded_at.is_(None)).execution_options(yield_per=30)):
  p=r.payload;fail=[]
  for a in p.get('attachments',[]):
   statuses[a.get('status')]+=1
   if a.get('status')=='OCR_REVIEW_REQUIRED':
    out['ocr'].append(dict(document_id=r.entity_id,name=p.get('name'),source_date=p.get('source_date'),url=p.get('evidence_url'),attachment={k:a.get(k) for k in ('name','path','original_sha256','text_scope','text_method','text_attempted_on')},text_chars=len(a.get('text','')),text_sample=a.get('text','')[:1100]));ocr_files.add(a.get('original_sha256'))
   if a.get('status')=='DOWNLOAD_FAILED':
    unique_files[a.get('path')]=a.get('error');fail.append(dict(name=a.get('name'),error=a.get('error')))
  if fail:
   failed_docs+=1
   if len(out['failures'])<8:out['failures'].append(dict(id=r.entity_id,name=p.get('name'),url=p.get('evidence_url'),attachments=fail))
 out['attachment_counts']=dict(statuses);out['download_failed_documents']=failed_docs;out['download_failed_unique_paths']=len(unique_files);out['ocr_unique_files']=len(ocr_files)
 for src in SOURCES:
  if not src.get('manual_only'):continue
  b=db.scalar(select(Batch).where(Batch.source_id==src['id']).order_by(Batch.started_at.desc()).limit(1))
  out['manual_sources'].append(dict(id=src['id'],name=src['name'],mode=src.get('collection_mode'),url=src['url'],status=b.status if b else None,error=b.error if b else None))
 print(json.dumps(out,ensure_ascii=False,indent=2))
