import json
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.evidence_bridge import review
from scripts.review_plan_links_20261019 import protected,ACTOR
s=HomeService(engine_for());before=protected(s);applied=json.loads(Path('/app/data/plan-links-applied-20261019.json').read_text());links=s.rows('evidence_bridge');out=[]
for p in applied['proposed']:
 if p['result']!='confirmed':continue
 for old in links:
  if old['project_id']!=p['target_id'] or old['source_entity_id'] not in p['source_ids'] or old['id']==p['id'] or old['status']!='REVIEW':continue
  if not old.get('facts') or not all(f.get('kind')=='PLAN' for f in old['facts']):continue
  old_dates={(f.get('stage'),f.get('milestone'),f.get('date')) for f in old['facts']};new_dates={(f.get('stage'),f.get('milestone'),f.get('date')) for f in p['facts']}
  if not old_dates<=new_dates:continue
  result=review(s,old['id'],old['revision_no'],'RELEASED',ACTOR+' · 같은 사업·원천·계획일의 확인 연결 '+p['id']+'로 통합. 이전 검토 후보는 이력 보존·중복 표출 해제')
  if result.get('conflict'):raise ValueError('link changed')
  out.append(dict(released_review_id=old['id'],confirmed_id=p['id'],target=p['target_name']))
assert protected(s)==before
Path('/app/data/plan-links-consolidated-20261019.json').write_text(json.dumps(out,ensure_ascii=False,indent=2));print('consolidated',len(out),'protected unchanged')
