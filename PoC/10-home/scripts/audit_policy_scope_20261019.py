"""Reproducible, read-only audit of frozen delivery and project snapshots."""
import json,gzip,sys,re,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from datetime import date
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.integrity_diagnostics import belongs
from backend.policy_delivery_comparison import _events,_schedule_targets
from backend.supply_dashboard import block_key
from backend.seoul_cleanup import address_key
DEST=ROOT/'docs/evidence/HOME_POLICY_SCOPE_AUDIT_20261019'
def read(p):return json.load(gzip.open(p,'rt') if str(p).endswith('.gz') else open(p))
def save(n,v):(DEST/n).write_text(json.dumps(v,ensure_ascii=False,indent=2,default=str)+'\n')
d=read(DEST/'delivery-corrected.json.gz');snap=read(DEST/'scope-corrected-snapshot.json')
pre=read(ROOT/'docs/evidence/HOME_START_LINKAGE_20261019/delivery-after.json.gz')
plan=read(ROOT/'data/remediation/start-linkage-20261019/link-plan.json')
base=read(ROOT/'backend/data/official_benchmark_20261016.json');ref=date.fromisoformat(d['as_of_date'])
projects={p['id']:p for p in snap['projects']};raw={p['id']:p for p in snap['raw_projects']}
profiles={p['project_id']:p for p in snap['profiles']}
areas=sorted({p['name'] for p in base['rows'] if p['id'].startswith('S')})
def mentions(p):return [area for area in areas if belongs(p['name'],area)]
def val(points,when):return next((p['units'] for p in reversed(points) if p['date']<=when),0)
cases=[]
for case in base['rows']:
 if not case['id'].startswith('S'):continue
 cs=[c for c in d['portfolio_cohorts'] if mentions(dict(name=c['name'])) and case['name'] in mentions(dict(name=c['name']))]
 members=[p for p in projects.values() if p['mapping']['policy_id']==d['policy_id'] and case['name'] in mentions(p)]
 stage='CONSTRUCTION' if case['stage']=='착공' else 'MOVE_IN' if case['id'] in ('S14','S15','S16') else 'SUPPLY'
 start,end=('2026-01-01',d['as_of_date']) if stage=='CONSTRUCTION' else ('2026-12-01','2026-12-31') if case['id']=='S14' else ('2027-01-01','2027-12-31') if case['id'] in ('S15','S16') else ('2026-10-01','2026-12-31')
 detail=[]
 for c in cs:
  ev=[e for e in c['events'] if e['stage']==stage and e.get('status','ACTUAL')=='ACTUAL']
  eligible=[e for e in ev if start<=e['event_date']<=end]
  schedules=_schedule_targets([c],stage,'1900-01-01')
  detail.append(dict(id=c['id'],name=c['name'],units=c['units'],block=c.get('block'),source_ids=c['source_ids'],eligible_events=eligible,other_events=[e for e in ev if e not in eligible],
   period_measurement=max((min(c['units'],e['units'] if e.get('units') is not None else c['units']) for e in eligible),default=None),
   period_plan=val(schedules,end)-val(schedules,start[:-2]+'00') if schedules else None,schedule_points=schedules))
 vals=[v['period_measurement' if stage=='CONSTRUCTION' else 'period_plan'] for v in detail]
 values=[v for v in vals if v is not None]
 cases.append(dict(official=case,stage=stage,start=start,end=end,managed_value=sum(values) if values else None,
    comparable=False,reason='공식 지구 내 세부 블록·주택유형 포함 범위 확정 전',source_record_count=len(members),cohorts=detail))
policy=[p for p in projects.values() if p['mapping']['policy_id']==d['policy_id']]
unmentioned=[p for p in policy if not mentions(p)]
# Detect duplicate aggregation identities, separately from harmless multi-source inputs.
ids=Counter(c['id'] for c in d['portfolio_cohorts']);duplicate_ids={k:v for k,v in ids.items() if v>1}
source_owners=defaultdict(list)
for c in d['portfolio_cohorts']:
 for sid in c['source_ids']:source_owners[sid].append(c['id'])
repeated_sources={k:v for k,v in source_owners.items() if len(v)>1}
blocks=defaultdict(list);addresses=defaultdict(list);names=defaultdict(list)
for c in d['portfolio_cohorts']:
 p=projects[c['id']];key=block_key(p)
 if key:blocks[key].append(c)
 address=address_key(p.get('address'))
 if address:addresses[(p['region'],address)].append(c)
 names[(p['region'],re.sub(r'\s+','',p['name']))].append(c)
repeated_blocks=[dict(key=k,cohorts=[c['id'] for c in cs],tenures=[raw[c['id']].get('tenure') for c in cs]) for k,cs in blocks.items() if len(cs)>1]
repeated_addresses=[dict(key=k,cohorts=[dict(id=c['id'],name=c['name'],units=c['units']) for c in cs]) for k,cs in addresses.items() if len(cs)>1]
repeated_names=[dict(key=k,cohorts=[c['id'] for c in cs]) for k,cs in names.items() if len(cs)>1]
withdrawn={i['project_id']:i for i in plan['items'] if i['policy_id']==d['policy_id']}
withdrawn_cohorts=[c for c in pre['portfolio_cohorts'] if c['id'] in withdrawn]
points=_events(withdrawn_cohorts,'CONSTRUCTION',ref,'1900-01-01',True)
decomp=dict(withdrawn_current_reached=val(points,d['as_of_date']),withdrawn_pre2026_reached=val(points,'2025-12-31'),
    remaining_portfolio_reached=val(d['portfolio_comparisons']['policy']['metrics']['CONSTRUCTION']['tracking']['actual_points'],d['as_of_date']),
    policy_period_reached=val(d['yearly_comparisons']['policy']['metrics']['CONSTRUCTION']['tracking']['actual_points'],d['as_of_date']))
by_region={stage:{r:val(d['yearly_comparisons']['region:'+r]['metrics'][stage]['tracking']['actual_points'],d['as_of_date']) for r in d['plan']['geography']} for stage in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
for stage,regions in by_region.items():assert sum(regions.values())==val(d['yearly_comparisons']['policy']['metrics'][stage]['tracking']['actual_points'],d['as_of_date'])
result=dict(reference=d['as_of_date'],cases=cases,decomposition=decomp,map_card_values=by_region,
 policy_records=len(policy),official_mentioned_records=len(policy)-len(unmentioned),unmentioned_records=len(unmentioned),
 unmentioned_program_counts=dict(Counter(p['program'] for p in unmentioned)),
 unmentioned=[dict(id=p['id'],name=p['name'],units=p.get('planned_units'),program=p['program'],mapping=p['mapping'],evidence_url=p['evidence_url']) for p in unmentioned],
 withdrawn=[dict(id=i['project_id'],name=i['name'],units=i['planned_units'],source_type=i['source'].get('business_type'),start_date=i['start_date'],former_program=i['program'],current_mapping=projects[i['project_id']]['mapping']) for i in withdrawn.values()],
 duplicate_checks=dict(cohorts=len(d['portfolio_cohorts']),excluded_source_records=len(d['excluded_source_ids']),duplicate_ids=duplicate_ids,repeated_source_owners=repeated_sources,repeated_blocks=repeated_blocks,repeated_addresses=repeated_addresses,repeated_names=repeated_names),
 exclusions=[dict(id=k,name=projects[k]['name'],source=projects[k]['source_id'],block_key=block_key(projects[k])) for k in d['excluded_source_ids']])
save('audit.json',result)
print(json.dumps({k:v for k,v in result.items() if k in ('decomposition','policy_records','official_mentioned_records','unmentioned_records','unmentioned_program_counts','duplicate_checks')},ensure_ascii=False))
for c in cases:print(c['official']['id'],c['official']['name'],c['official'].get('official_value'),c['managed_value'],[(p['name'],p['units'],p['period_measurement'],p['period_plan']) for p in c['cohorts']])
