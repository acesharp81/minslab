import json,traceback
from pathlib import Path
from app.config import get_settings
from app.db.connection import connect
from app.db.meeting_brief_repository import MeetingBriefRepository
from app.db.topic_structure_repository import TopicStructureRepository
from app.services.structured_narrative import has_meta_commentary
from app.ingestion.report_finalization import assess
from app.ingestion.ontology_review_worker import pending_items
out=Path('/app/data/recovery/20261107-report-audit');out.mkdir(parents=True,exist_ok=True)
s=get_settings(); results=[]
with connect(s.database_url) as c:
 items=MeetingBriefRepository(c).latest_all()
 print('TOTAL',len(items),flush=True)
 for item in items:
  bid=item['broadcast_id']; row={'id':str(bid)}
  try:
   title,life,cursor=c.execute('SELECT title,lifecycle_status,source_last_event_cursor FROM live_broadcasts WHERE id=%s',(bid,)).fetchone()
   row.update(title=title,lifecycle=life,source_cursor=cursor,report_cursor=item['source_last_event_cursor'],generated=str(item['generated_at']))
   repo=TopicStructureRepository(c);brief=repo.ready_current(item);progress=repo.progress(item)
   row.update(finalization=item['brief'].get('finalization'),progress=progress,structured=bool(brief))
   if brief:
    row.update(narrative=brief.get('narrative_coverage'),assessment=assess(brief,progress,pending_items(brief,[])),parent_review=brief.get('parent_review'),topic_count=len(brief.get('topics',[])),summary_count=len((brief.get('report_summary') or {}).get('topics',[])))
    hits=[]
    def walk(x,path=''):
     if isinstance(x,dict):
      for k,v in x.items():walk(v,path+'/'+k)
     elif isinstance(x,list):
      for i,v in enumerate(x):walk(v,path+'/'+str(i))
     elif isinstance(x,str) and has_meta_commentary(x):hits.append({'path':path,'text':x})
    walk(brief.get('report_summary',{}));row['meta']=hits
    (out/(str(bid)+'.json')).write_text(json.dumps(brief,ensure_ascii=False,default=str))
   results.append(row)
   print(json.dumps({k:v for k,v in row.items() if k not in ['finalization','parent_review','meta']},ensure_ascii=False),flush=True)
  except Exception as e: row['error']=str(e);results.append(row);traceback.print_exc()
 (out/'audit.json').write_text(json.dumps(results,ensure_ascii=False,default=str,indent=2))
 print('TOPIC_REPORT_STATUSES',c.execute('SELECT status,count(*) FROM topic_reports GROUP BY status').fetchall(),flush=True)
