"""Offline audit of a captured current project inventory; never writes production DB."""
import csv,json,collections,hashlib
from pathlib import Path
from backend.supply_type import assess,TYPES
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'docs/analysis/sector_classification_20261021'
def read(name):return json.loads((OUT/name).read_text())
def write(name,obj):(OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2))
def csvwrite(name,rows):
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def quantity(c,first=None,last='2026-10-21',tracking=False):
 events=[e for e in c.get('events',[]) if e.get('stage') in ({'CONSTRUCTION','COMPLETION','SUPPLY','MOVE_IN'} if tracking else {'CONSTRUCTION'}) and e.get('status','ACTUAL')=='ACTUAL' and e.get('event_date') and e['event_date']<=last and (not first or e['event_date']>=first) and isinstance(e.get('units'),int)]
 return min(c['units'],max((e['units'] for e in events),default=0))
def main():
 projects=read('projects.json');model=read('model.json');ps={p['id']:p for p in projects};source_rows=[]
 for p in projects:
  a=assess(p)
  source_rows.append(dict(project_id=p['id'],name=p['name'],region=p.get('region'),program=p.get('program'),source_id=p['source_id'],source_url=p.get('evidence_url'),mapping_status=p['mapping']['status'],policy_id=p['mapping']['policy_id'],supply_type=a['code'],supply_type_label=a['label'],classification_status=a['status'],candidate_type=a['candidate_code'],rule=a['rule'],basis=a['basis'],evidence_url=a['evidence_url']))
 active=[r for r in source_rows if r['mapping_status']!='RELEASED'];linked=[r for r in active if r['mapping_status']=='CONFIRMED' and r['policy_id']=='POL_2025_0907'];cohorts=[]
 for c in model['portfolio_cohorts']:
  assessments=[assess(ps[pid]) for pid in c['source_ids'] if pid in ps]
  assert assessments, c['id']
  confirmed={a['code'] for a in assessments if a['status']=='CONFIRMED'};candidates={a['candidate_code'] for a in assessments if a['candidate_code']}
  code='MIXED' if any(a['code']=='MIXED' for a in assessments) else next(iter(confirmed)) if len(confirmed)==1 and not candidates-confirmed else 'UNKNOWN'
  proofs=[a for a in assessments if a['status']=='CONFIRMED' and a['code']==code]
  basis=' | '.join(sorted({a['basis'] for a in proofs or assessments}));urls=' | '.join(sorted({a['evidence_url'] for a in proofs or assessments if a['evidence_url']}))
  cohorts.append(dict(cohort_id=c['id'],name=c['name'],region=c['region'],program=c.get('program'),supply_type=code,supply_type_label=TYPES[code],classification_status='CONFIRMED' if code not in ('UNKNOWN','MIXED') else 'UNRESOLVED',source_project_ids='|'.join(c['source_ids']),source_record_count=len(c['source_ids']),planned_units=c['units'],management_cumulative_start_units=quantity(c,tracking=True),managed_start_2026_units=quantity(c,'2026-01-01'),managed_start_to_september_units=quantity(c,'2026-01-01','2026-09-30'),managed_start_to_august_units=quantity(c,'2026-01-01','2026-08-31'),basis=basis,evidence_urls=urls))
 def summary(rows):
  return dict(total=len(rows),confirmed=sum(r['classification_status']=='CONFIRMED' for r in rows),unresolved=sum(r['classification_status']!='CONFIRMED' for r in rows),by_type={k:sum(r['supply_type']==k for r in rows) for k in TYPES})
 totals=dict(capture=read('capture.json'),all_source_records=len(source_rows),released_records=len(source_rows)-len(active),active_source_records=summary(active),policy907_source_records=summary(linked),policy907_management_cohorts=summary(cohorts),unique_contributing_source_ids=len({pid for c in model['portfolio_cohorts'] for pid in c['source_ids']}),management_start_by_type={code:dict(cohorts=sum(c['supply_type']==code for c in cohorts),current_cumulative=sum(c['management_cumulative_start_units'] for c in cohorts if c['supply_type']==code),managed_2026=sum(c['managed_start_2026_units'] for c in cohorts if c['supply_type']==code),managed_to_september=sum(c['managed_start_to_september_units'] for c in cohorts if c['supply_type']==code),managed_to_august=sum(c['managed_start_to_august_units'] for c in cohorts if c['supply_type']==code)) for code in TYPES},classification_code_sha256=hashlib.sha256((ROOT/'backend/supply_type.py').read_bytes()).hexdigest())
 assert totals['active_source_records']['confirmed']+totals['active_source_records']['unresolved']==len(active)
 assert totals['policy907_management_cohorts']['confirmed']+totals['policy907_management_cohorts']['unresolved']==len(cohorts)
 ids=[pid for c in model['portfolio_cohorts'] for pid in c['source_ids']];assert len(ids)==len(set(ids))
 csvwrite('all_source_classification.csv',source_rows);csvwrite('management_classification.csv',cohorts);csvwrite('unresolved_management.csv',[r for r in cohorts if r['classification_status']!='CONFIRMED']);csvwrite('unresolved_sources.csv',[r for r in active if r['classification_status']!='CONFIRMED']);write('result.json',totals)
 print(json.dumps(totals,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
