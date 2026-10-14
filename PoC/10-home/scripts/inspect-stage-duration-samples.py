import sys,json,statistics
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend.service import HomeService
from backend.db import engine_for
from backend.project_collection import collection_matrix
from backend.project_profile import target_default,progress_default,STAGES
from backend.officer_completion import normalized
from backend.supply_dashboard import block_key
from datetime import date
s=HomeService(engine_for());m=collection_matrix(s,policy_id='POL_2025_0907');cells={p['id']:p['cells'] for p in m['items']};samples={k:[] for k in ['BUSINESS_APPROVAL','APPROVAL_CONSTRUCTION','CONSTRUCTION_COMPLETION','COMPLETION_MOVE_IN','CONSTRUCTION_SUPPLY']};seen=set()
for p in sorted(s.projects(policy_id='POL_2025_0907'),key=lambda p:p.get('base_date',''),reverse=True):
    key=block_key(p) or p['id']
    if key in seen:continue
    seen.add(key);dates={}
    for st in STAGES:
        c=cells[p['id']]['CONSTRUCTION' if st=='COMPLETION' else st];c=dict(c,sources=[r for r in c['sources'] if r.get('source_id')!='officer'],targets=[r for r in c['targets'] if r.get('source_id')!='officer'])
        dates[st]=normalized(progress_default(c,st).get('event_date') or target_default(c,st).get('due_date'))
    for a,b in [('BUSINESS','APPROVAL'),('APPROVAL','CONSTRUCTION'),('CONSTRUCTION','COMPLETION'),('COMPLETION','MOVE_IN'),('CONSTRUCTION','SUPPLY')]:
        if not dates[a] or not dates[b]:continue
        days=(date.fromisoformat(dates[b])-date.fromisoformat(dates[a])).days
        low=-730 if b=='SUPPLY' else 180 if b=='COMPLETION' else 1;high=3650 if b=='COMPLETION' else 1825
        if low<=days<=high and type(p.get('planned_units')) is int and p['planned_units']>0:samples[a+'_'+b].append(dict(id=p['id'],name=p['name'],days=days,units=p['planned_units'],from_date=dates[a],to_date=dates[b]))
print(json.dumps({k:dict(count=len(v),mean_days=round(statistics.mean(r['days'] for r in v),2) if v else None,days_per_unit=sum(r['days'] for r in v)/sum(r['units'] for r in v) if v else None) for k,v in samples.items()},ensure_ascii=False))
Path('/app/data/runtime/officer-duration-samples.json').write_text(json.dumps(samples,ensure_ascii=False,indent=2))
