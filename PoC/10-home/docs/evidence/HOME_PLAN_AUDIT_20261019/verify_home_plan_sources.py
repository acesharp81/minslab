import json
from pathlib import Path
from datetime import datetime,timezone
from backend.sources import SOURCES
from backend.collectors import Fetcher,collect_lh_plan
from backend.official_supply_files import collect_lh_completion_plan
from backend.agency_data import parse_gh_plan
from backend.db import entity_id
snapshot=json.loads(Path('/app/data/plan-audit-snapshot-20261019.json').read_text())
results=[]
for sid in ['lh_sale','lh_rent','lh_completion_plan','gh_supply_plan']:
 src=next(x for x in SOURCES if x['id']==sid);f=Fetcher(sid,Path('/app/data/plan-audit-raw-20261019'))
 item={'source_id':sid,'checked_at':datetime.now(timezone.utc).isoformat()}
 try:
  if sid in ('lh_sale','lh_rent'):records,stats=collect_lh_plan(src,f)
  elif sid=='lh_completion_plan':records,stats=collect_lh_completion_plan(src,f)
  else:records,stats=parse_gh_plan(src,f.get(src['url']))
  fields=['name','region','planned_units','supply_units','units','rows','source_supply_label','source_move_in_label','completion_plan_date','source_date','dataset_version']
  fresh={entity_id(k,sid,key):{x:p.get(x) for x in fields} for k,key,p in records}
  stored={r['id']:{x:r.get(x) for x in fields} for r in snapshot['rows'] if r['source_id']==sid}
  item.update(status='SUCCESS',stats=stats,fresh_count=len(fresh),stored_count=len(stored),new_ids=sorted(set(fresh)-set(stored)),missing_from_current_ids=sorted(set(stored)-set(fresh)),changed=[{'id':k,'fields':{x:{'stored':stored[k][x],'fresh':fresh[k][x]} for x in fields if stored[k][x]!=fresh[k][x]}} for k in fresh.keys()&stored.keys() if fresh[k]!=stored[k]],fresh=fresh)
 except Exception as e:item.update(status='ERROR',error=str(e))
 finally:f.close()
 item['manifest']=f.manifest;results.append(item)
 Path('/app/data/plan-audit-fresh-20261019.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(sid,item['status'],{k:v for k,v in item.items() if k in ('fresh_count','stored_count','new_ids','missing_from_current_ids','changed','error')},flush=True)
