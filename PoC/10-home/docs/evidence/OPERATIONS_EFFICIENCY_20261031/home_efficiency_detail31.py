from sqlalchemy import text
from backend.db import engine_for
import json,time,hashlib,collections
engine=engine_for();results={}
queries={
 'batch_24h':"SELECT source_id,status,count(*) runs,sum(COALESCE((stats->>'records')::bigint,0)) records,sum(COALESCE((stats->>'new')::bigint,0)) new_records,sum(COALESCE((stats->>'changed')::bigint,0)) changed_records,sum(COALESCE((stats->>'unchanged')::bigint,0)) unchanged_records,min(started_at) first_started,max(started_at) last_started FROM home_batch WHERE started_at>=now()-interval '24 hours' GROUP BY source_id,status ORDER BY runs DESC LIMIT 35",
 'snapshot_counts':"SELECT actor,count(*) snapshots,count(*) FILTER (WHERE created_at>=now()-interval '24 hours') last_24h,min(created_at) first_created,max(created_at) last_created FROM home_metric_snapshot GROUP BY actor ORDER BY snapshots DESC",
 'revision_growth':"SELECT kind,count(*) revisions,count(*) FILTER(WHERE superseded_at IS NOT NULL) superseded FROM home_revision WHERE recorded_at>=now()-interval '24 hours' GROUP BY kind ORDER BY revisions DESC LIMIT 15",
 'audit_24h':"SELECT action,count(*) records FROM home_audit WHERE recorded_at>=now()-interval '24 hours' GROUP BY action ORDER BY records DESC LIMIT 15",
 'batch_samples':"SELECT source_id, status, json_array_length(COALESCE(manifest::json,'[]'::json)) stored_responses FROM home_batch ORDER BY started_at DESC LIMIT 1"
}
# Each query has a strict time budget and its own read-only transaction.
for name,query in queries.items():
 with engine.connect() as c:
  c.execute(text('SET TRANSACTION READ ONLY'));c.execute(text("SET LOCAL statement_timeout='15000'"));t=time.monotonic()
  try: rows=[dict(r) for r in c.execute(text(query)).mappings()];results[name]={'seconds':time.monotonic()-t,'rows':rows}
  except Exception as e: results[name]={'error':type(e).__name__}
# Compare recent immutable snapshots after removing observation time only.
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'));c.execute(text("SET LOCAL statement_timeout='15000'"))
 hashes=collections.Counter();sizes=[]
 for r in c.execute(text('SELECT context,result FROM home_metric_snapshot ORDER BY created_at DESC LIMIT 12')).mappings():
  context=dict(r['context']);result=dict(r['result']);context.pop('known_at',None);result.pop('known_at',None)
  value=json.dumps({'context':context,'result':result},ensure_ascii=False,sort_keys=True).encode();hashes[hashlib.sha256(value).hexdigest()]+=1;sizes.append(len(value))
 results['snapshot_recent12_normalized']={'rows':sum(hashes.values()),'distinct_without_known_at':len(hashes),'group_sizes':sorted(hashes.values(),reverse=True),'mean_uncompressed_bytes':sum(sizes)//max(1,len(sizes))}
print(json.dumps(results,ensure_ascii=False,default=str,indent=2))
