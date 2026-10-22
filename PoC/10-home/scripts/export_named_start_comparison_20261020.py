from pathlib import Path
from datetime import date
import json
from collections import defaultdict
from backend.db import engine_for
from backend.service import HomeService
from backend.policy_delivery import build_delivery
from scripts.build_continuation_review_20261020 import metrics
s=HomeService(engine_for());model=build_delivery(s,date(2026,10,20),include_portfolio_comparisons=False)
terms={'인천계양':['인천계양'],'남양주왕숙2':['남양주왕숙2'],'부천대장':['부천대장'],'고양창릉':['고양창릉'],'하남교산':['하남교산'],'중계본동':['중계본동'],'흑석11':['흑석11'],'신림2':['신림2']}
rows=[]
for c in model['portfolio_cohorts']:
 name=''.join(c['name'].split());group=next((k for k,words in terms.items() if any(w in name for w in words)),None)
 if not group:continue
 ev=[e for e in c.get('events',[]) if e.get('stage')=='CONSTRUCTION' and e.get('event_date','')<='2026-10-20' and e.get('status','ACTUAL')=='ACTUAL']
 cumulative=min(c['units'],max((e.get('units') if e.get('units') is not None else c['units'] for e in ev),default=0))
 annual=[e for e in ev if e.get('event_date','').startswith('2026')]
 yearly=min(c['units'],max((e.get('units') if e.get('units') is not None else c['units'] for e in annual),default=0))
 rows.append(dict(group=group,id=c['id'],name=c['name'],block=c.get('block'),capacity=c['units'],program=c.get('program'),region=c['region'],current_cumulative=cumulative,event_date_in_2026=yearly,events=ev,source_ids=c['source_ids']))
folder=s.data_dir/'three-newtown-final-20261020';folder.mkdir(exist_ok=True)
out=dict(reference='2026-10-20',metrics=metrics(model),rows=rows,group_totals=[dict(group=g,records=sum(r['group']==g for r in rows),current_cumulative=sum(r['current_cumulative'] for r in rows if r['group']==g),event_date_in_2026=sum(r['event_date_in_2026'] for r in rows if r['group']==g)) for g in terms])
(folder/'named-policy-cohorts.json').write_text(json.dumps(out,ensure_ascii=False,indent=2,default=str))
print(json.dumps(dict(metrics=out['metrics'],groups=out['group_totals']),ensure_ascii=False))
for r in rows:
 if r['group'] in ['인천계양','남양주왕숙2','부천대장']:print(json.dumps({k:r[k] for k in ['group','name','capacity','current_cumulative','event_date_in_2026','source_ids']},ensure_ascii=False))
