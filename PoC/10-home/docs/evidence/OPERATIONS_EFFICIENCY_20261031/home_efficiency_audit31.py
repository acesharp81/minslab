import json,time
from sqlalchemy import text
from backend.db import engine_for
engine=engine_for();result={}
queries={
'database':"SELECT current_database() name, current_setting('server_version') version, pg_database_size(current_database()) bytes, current_setting('autovacuum') autovacuum",
'relations':"SELECT s.relname,pg_total_relation_size(s.relid) total_bytes,pg_relation_size(s.relid) heap_bytes,s.n_live_tup,s.n_dead_tup,s.n_tup_ins,s.n_tup_upd,s.n_tup_del,s.seq_scan,s.idx_scan,s.last_autovacuum,s.last_autoanalyze FROM pg_stat_user_tables s ORDER BY pg_total_relation_size(s.relid) DESC LIMIT 15",
'columns':"SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND table_name IN ('revision','revisions','batch','batches','audit','audits','collection_jobs') ORDER BY table_name,ordinal_position",
'activity':"SELECT state,wait_event_type,count(*) connections FROM pg_stat_activity WHERE datname=current_database() GROUP BY state,wait_event_type",
}
with engine.connect() as c:
 c.execute(text('SET TRANSACTION READ ONLY'));c.execute(text("SET LOCAL statement_timeout='20000'"))
 for name,q in queries.items():
  t=time.monotonic()
  try:result[name]={'seconds':time.monotonic()-t,'rows':[dict(r) for r in c.execute(text(q)).mappings()]}
  except Exception as e:result[name]={'error':type(e).__name__};break
print(json.dumps(result,default=str,ensure_ascii=False,indent=2))
