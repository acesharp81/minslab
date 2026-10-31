import json,time
from sqlalchemy import text
from backend.db import engine_for
qs={
'recent_batches':"SELECT source_id,status,count(*) runs,max(started_at) latest FROM home_batch WHERE started_at >= TIMESTAMPTZ '2026-10-31 02:42:40+00' GROUP BY source_id,status ORDER BY runs DESC",
'current_repair_jobs':"SELECT source_id,status,attempts,left(error,180) error,finished_at FROM home_collection_job WHERE status='FAILED' AND finished_at>=TIMESTAMPTZ '2026-10-31 02:42:40+00' ORDER BY finished_at DESC LIMIT 15",
'first_last_repair':"SELECT source_id,left(error,180) error FROM home_batch WHERE source_id IN ('lh_stock','lh_completion_plan','gh_files','gh_completion_evidence') AND started_at>=TIMESTAMPTZ '2026-10-31 02:42:40+00' ORDER BY started_at DESC LIMIT 10",
'snapshots_after_worker':"SELECT count(*) total FROM home_metric_snapshot WHERE created_at>=TIMESTAMPTZ '2026-10-31 02:42:40+00'"
}
e=engine_for();out={}
for name,q in qs.items():
 with e.connect() as c:
  c.execute(text('SET TRANSACTION READ ONLY'));c.execute(text("SET LOCAL statement_timeout='10000'"))
  try:out[name]=[dict(r) for r in c.execute(text(q)).mappings()]
  except Exception as err:out[name]={'error':type(err).__name__}
print(json.dumps(out,default=str,ensure_ascii=False,indent=2))
