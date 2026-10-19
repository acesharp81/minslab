import json
from pathlib import Path
from datetime import datetime, timezone, date
from collections import Counter
from sqlalchemy import select, text
from backend.db import engine_for, Revision, Batch, Mapping
from backend.service import HomeService, latest_batches
from backend.sources import SOURCES
from backend.roadmap import source_events
from backend.schedule_period import schedule_period
s=HomeService(engine_for()); now=date(2026,10,19)
ids=['lh_sale','lh_rent','lh_incheon_sale','lh_incheon_rent','lh_construction','lh_incheon_construction','lh_department_plans','lh_completion_plan','lh_movein_history','sh_supply_plan','sh_redevelopment','sh_inventory','gh_supply_plan','ih_notice','policy_907_plan','policy_129','seoul_plan_notice_pilot','gyeonggi_plan_notice_pilot']
out={'captured_at':datetime.now(timezone.utc).isoformat(),'sources':[],'rows':[]}
with s.sessions() as db:
 db.execute(text("SET statement_timeout = '120s'"))
 for sid in ids:
  src=next((r for r in SOURCES if r['id']==sid),{'id':sid})
  rs=db.scalars(select(Revision).where(Revision.source_id==sid,Revision.superseded_at.is_(None))).all()
  rows=[dict(r.payload,id=r.entity_id,kind=r.kind,source_id=sid,recorded_at=r.recorded_at.isoformat()) for r in rs]
  # Keep full payloads for reproducible date/quantity/link audit, omit large source text/tables from row export.
  for r in rows:
   r['table_count']=len(r.get('tables',[]));r['content_length']=len(r.get('content_text',''))
   for key in ['tables','content_text']:r.pop(key,None)
  batches={}
  for status in [None,'SUCCESS']:
   bs=latest_batches(db,status,source_ids=[sid])
   if bs:
    b=bs[0];batches['latest' if status is None else 'last_success']={'status':b.status,'started_at':str(b.started_at),'finished_at':str(b.finished_at),'error':b.error,'stats':b.stats}
  out['sources'].append({'source':{k:v for k,v in src.items() if 'key' not in k},'counts':dict(Counter(r['kind'] for r in rows)),**batches})
  out['rows'].extend(rows)
  print(sid,len(rows),flush=True)
 for kind in ['execution_schedule','evidence_bridge','project_profile']:
  rs=db.scalars(select(Revision).where(Revision.kind==kind,Revision.superseded_at.is_(None))).all()
  out[kind]=[dict(r.payload,id=r.entity_id,source_id=r.source_id) for r in rs]
 out['mappings']=[{'project_id':m.project_id,'policy_id':m.policy_id,'program_id':m.program_id,'status':m.status} for m in db.scalars(select(Mapping)).all()]
Path('/app/data/plan-audit-snapshot-20261019.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
print('snapshot saved',len(out['rows']),flush=True)
