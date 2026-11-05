"""Operator-only evidence capture; explicit PostgreSQL read-only transaction.
Run inside the existing API runtime with PYTHONPATH=/app. Raw output stays in
/tmp/official1105-capture; do not publish this unredacted capture. No ETL or writes.
The companion reconciliation script consumes a private copy in capture/db/.
"""
import json,hashlib
from pathlib import Path
from datetime import date
from sqlalchemy import select,text
from sqlalchemy.orm import sessionmaker
from backend.db import engine_for,Revision,Mapping,ProgramMapping
from backend.service import HomeService
from backend.read_scope import projection_reads
from backend.policy_delivery import build_delivery
from backend.policy_delivery_view import screen_view,trim_screen_details
out=Path('/tmp/official1105-capture');out.mkdir(exist_ok=True)
engine=engine_for()
def dump(name,value):(out/(name+'.json')).write_text(json.dumps(value,ensure_ascii=False,default=str))
with engine.connect() as conn:
 with conn.begin():
  conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
  conn.execute(text("SET LOCAL statement_timeout = '60s'"))
  mode=conn.scalar(text('SHOW transaction_read_only'));assert mode=='on'
  stamp=conn.scalar(text('SELECT CURRENT_TIMESTAMP'))
  service=HomeService(engine,'/app/data');service.sessions=sessionmaker(bind=conn,expire_on_commit=False)
  kinds=['policy','policy_profile','policy_delivery_plan','program_profile','project','project_profile','delivery_setting','execution_schedule','statistic','statistic_reference','housing_type_stat','agency_plan','lh_movein_plan','plan_notice','document_evidence']
  raw=[]
  for kind in kinds:
   values=[dict(id=r.entity_id,kind=r.kind,source_id=r.source_id,revision_no=r.revision_no,recorded_at=str(r.recorded_at),payload_hash=r.payload_hash,payload=r.payload) for r in conn.execute(select(Revision.entity_id,Revision.kind,Revision.source_id,Revision.revision_no,Revision.recorded_at,Revision.payload_hash,Revision.payload).where(Revision.kind==kind,Revision.superseded_at.is_(None)))]
   raw.extend(values);print(kind,len(values),flush=True)
  dump('raw',raw);dump('mappings',[dict(r._mapping) for r in conn.execute(select(Mapping.__table__))]);dump('programs',[dict(r._mapping) for r in conn.execute(select(ProgramMapping.__table__))])
  with projection_reads():
   projects=service.projects();dump('projects',projects)
   model=build_delivery(service,date(2026,11,5),include_portfolio_comparisons=False,comparison_scopes=(),include_snapshots=False)
   dump('model',model);dump('screen',screen_view(trim_screen_details(model),'policy','policy'))
  dump('snapshot',dict(snapshot_at=str(stamp),transaction='PostgreSQL REPEATABLE READ READ ONLY',transaction_read_only=mode,kinds=kinds,projects=len(projects),raw_rows=len(raw),business_writes=0))
print('snapshot complete',flush=True)
