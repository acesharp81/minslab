"""Read-only production-data equivalence and cold calculation timing."""
import json,time
from datetime import date
from pathlib import Path
from backend.db import engine_for
from backend.service import HomeService
from backend.policy_delivery import build_delivery
from backend.policy_delivery_view import screen_view
from sqlalchemy import text
w=Path('data/loading-deep-20261020');s=HomeService(engine_for());day=date(2026,10,20)
t=time.monotonic();base=build_delivery(s,day,comparison_scopes=());base_seconds=time.monotonic()-t
full=json.loads((w/'before-model.json').read_text());checks={k:full[k]==base[k] for k in ['current','cohorts','portfolio_cohorts','snapshots','geometry','issues','map_reconciliation']}
geometry_checks=[]
if not checks['geometry']:
 def multipolygon(r):return dict(type='MultiPolygon',coordinates=[[ring,*r['holes'][i]] for i,ring in enumerate(r['rings'])])
 with s.engine.connect() as db:
  for a,b in zip(full['geometry']['region_shapes'],base['geometry']['region_shapes']):
   g=db.execute(text('WITH g AS (SELECT ST_MakeValid(ST_GeomFromGeoJSON(:a)) a,ST_MakeValid(ST_GeomFromGeoJSON(:b)) b) SELECT ST_Equals(a,b) exact, ST_Equals(ST_SnapToGrid(a,1e-9),ST_SnapToGrid(b,1e-9)) equal_at_grid, ST_HausdorffDistance(a,b) max_distance_degrees FROM g'),dict(a=json.dumps(multipolygon(a)),b=json.dumps(multipolygon(b)))).mappings().one()
   geometry_checks.append(dict(region=a['id'],**g,anchor_unchanged=(a['longitude'],a['latitude'])==(b['longitude'],b['latitude'])))
 checks['geometry']=all(full['geometry'][k]==base['geometry'][k] for k in full['geometry'] if k!='region_shapes') and all(r['max_distance_degrees']<.002 and r['anchor_unchanged'] for r in geometry_checks)
views=[]
for group in ['policy',*['program:'+p for p in sorted({c['program_id'] for c in base['portfolio_cohorts'] if c.get('program_id')})]]:
 t=time.monotonic();v=screen_view(base,group);seconds=time.monotonic()-t
 differences=[field+':'+key for field in ['yearly_comparisons','portfolio_comparisons'] for key,value in v[field].items() if full[field].get(key)!=value]
 views.append(dict(group=group,seconds=seconds,bytes=len(json.dumps(v,ensure_ascii=False,separators=(',',':')).encode()),yearly_scopes=len(v['yearly_comparisons']),portfolio_scopes=len(v['portfolio_comparisons']),differences=differences))
 if group=='policy':(w/'after-screen.json').write_text(json.dumps(v,ensure_ascii=False))
r=dict(base_cold_seconds=base_seconds,unchanged_fields=checks,geometry_checks=geometry_checks,views=views,all_visible_comparisons_identical=all(not v['differences'] for v in views),status='PASS' if all(checks.values()) and all(not v['differences'] for v in views) else 'FAIL')
(w/'equivalence.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));print(json.dumps(r,ensure_ascii=False));assert r['status']=='PASS'
