import time,json
from datetime import datetime,timedelta,time as day_time
from sqlalchemy import select,func,column,Text,JSON,true
from backend.service import HomeService,today,KST
from backend.db import engine_for,Revision
s=HomeService(engine_for(),'/app/data');day=today();cutoff=datetime.combine(day+timedelta(days=1),day_time.min,KST)
t=time.perf_counter();before=s.selected_stage_links(day);print('old',time.perf_counter()-t,flush=True)
visible=select(Revision.payload).where(Revision.kind=='stage_evidence',Revision.recorded_at<cutoff,Revision.superseded_at.is_(None)).cte('visible_stage_rows').prefix_with('MATERIALIZED',dialect='postgresql')
f=func.json_to_record(visible.c.payload).table_valued(column('project_id',Text),column('stage',Text),column('status',Text),column('selected',JSON),column('base_date',Text)).render_derived(name='stage_fields',with_types=True).lateral()
q=select(f.c.project_id,f.c.stage,f.c.status,f.c.selected).select_from(visible.join(f,true())).where(f.c.base_date<=day.isoformat(),f.c.status.in_(('REVIEW','CONFIRMED')))
t=time.perf_counter()
with s.sessions() as db:after=[dict(project_id=pid,stage=stage,status=status,selected=selected) for pid,stage,status,selected in db.execute(q) if selected]
print('new',time.perf_counter()-t,'equal',sorted(before,key=lambda r:(r['project_id'],r['stage']))==sorted(after,key=lambda r:(r['project_id'],r['stage'])),'count',len(after),flush=True)
