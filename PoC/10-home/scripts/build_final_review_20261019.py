"""Read-only, reproducible final review tables from the frozen operating snapshot."""
import csv,json,hashlib,shutil
from pathlib import Path
from collections import defaultdict,Counter
from datetime import date
from pypdf import PdfReader
from backend.lh_spring_followup import parse_plans,review_key
from backend.policy_delivery_comparison import comparison_index

ROOT=Path(__file__).resolve().parents[1];DATA=ROOT/'data';WORK=DATA/'final-review-20261019';OUT=ROOT/'docs/analysis/final_review_20261019'
def read(p):return json.loads(p.read_text())
def write(name,rows):
 if not rows:return
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def metrics(model):
 ms=comparison_index(dict(model['plan'],period_start='1900-01-01',portfolio=True),model['portfolio_cohorts'],model['settings'],[],date(2026,10,19))['policy']['metrics']
 return {stage:{label:next((x['units'] for x in reversed(v['tracking'][field]) if x['date']<=end),None) for label,field,end in [('actual','actual_points','2026-10-19'),('year_end','target_points','2026-12-31')]} for stage,v in ms.items()}

def main():
 OUT.mkdir(exist_ok=True,parents=True);before=read(DATA/'policy-readmission-after-20261019.json');after=read(WORK/'model-final.json');projects=read(WORK/'projects-final.json');admitted=read(WORK/'admission-applied.json');benchmark=read(ROOT/'backend/data/official_benchmark_20261016.json')
 by_key=defaultdict(list);by_id={p['id']:p for p in projects}
 for c in after['portfolio_cohorts']:
  keys={review_key(by_id[s]) for s in c['source_ids'] if s in by_id}-{None}
  for k in keys:by_key[k].append(c)
 source_keys=defaultdict(list)
 for p in projects:
  k=review_key(p)
  if k:source_keys[k].append(p)
 q4=[]
 for row in read(WORK/'official-q4-plans.json'):
  k=review_key(row);matches=by_key.get(k,[]) if k else [];sources=source_keys.get(k,[]) if k else []
  manual={'고덕강일 3':'PRO_1fbf5c7629634fa05be7652a','화성병점복합타운 주복1':'PRO_e05c4608f73fa5151e560558','인천부평 A':'PRO_9a256c5d211050be9f0814ff'}
  category='정책 관리사업 키 일치' if matches else '원천 사업 키만 일치' if sources else '정확 키 연결 미확보'
  if not matches and row['name'] in manual:
   matches=[c for c in after['portfolio_cohorts'] if c['id']==manual[row['name']]]
   assert len(matches)==1 and matches[0]['units']==row['units']
   category='개별 대조 일치 · 명칭·블록·호수'
  if row['name'] in ('안산신길2 A1','안산신길2 A3'):
   matches=[c for c in after['portfolio_cohorts'] if c['id']=='PRO_6b136676d58c65ca4274e4af']
   assert len(matches)==1 and matches[0]['units']==357
   category='합본 사업과 부분 대응 · 물량 대사 필요'
  q4.append(dict(공식사업=row['name'],공급유형=row['tenure'],공식계획호수=row['units'],공식시기=row['period'],
   키대조=category,
   관리사업=' | '.join(c['id']+' / '+c['name'] for c in matches),관리사업전체호수=' | '.join(str(c['units']) for c in matches),
   보유공급계획=' | '.join(str(s.get('due_date'))+' / '+str(s.get('units')) for c in matches for s in c['schedules'] if s['stage']=='SUPPLY'),
   원천후보=' | '.join(p['id']+' / '+p['name'] for p in sources),
   주의='분기 공급계획과 사업 전체 건설호수의 차이는 곧 오류가 아님. 정확 키 미확보는 미수집 확정이 아님.',근거URL=benchmark['appendix_url']+'#page=6'))
 write('official_q4_plan_crosswalk.csv',q4)
 plans=parse_plans([p.extract_text(extraction_mode='layout') for p in PdfReader(WORK/'lh-12047.pdf').pages],[p.extract_text(extraction_mode='layout') for p in PdfReader(WORK/'lh-11981.pdf').pages]);spring=[]
 for r in plans:
  matches=by_key.get(review_key(r),[])
  spring.append(dict(사업=r['name'],호수=r['units'],원문차수='1차·4월 선정 완료' if r['policy_relationship']=='EXPLICIT_FIRST_ROUND_907' else '후속 공모·별도 정책 근거 대조',
   처리='이번 정책 연결 확정' if r['policy_relationship']=='EXPLICIT_FIRST_ROUND_907' else '원천 계획 보존·자동 정책 연결 안 함',
   기존정책사업=' | '.join(c['id']+' / '+c['name'] for c in matches),근거URL=r['evidence_url']))
 write('lh_spring_21_plans.csv',spring)
 write('admitted_six_blocks.csv',[dict(사업=r['name'],호수=r['units'],사업ID=r['id'],프로그램=r['program'],원천ID=r['source_id'],근거=r['basis'],근거URL=r['evidence_url']) for r in admitted['projects']])
 permits=read(WORK/'permit-final-check.json');write('fourteen_blocks_permit_check.csv',[dict(사업=r['name'],관리호수=r['units'],원천수=len(r['matches']),허가후보=' | '.join(m['name']+' / '+str(m.get('units')) for m in r['matches']),허가일=' | '.join(str(m.get('dates',{}).get('원천 허가일 (apprvDay)')) for m in r['matches']),실제착공일=' | '.join(str(m.get('dates',{}).get('원천 착공일 (stcnsDay)')) for m in r['matches']),원천ID=' | '.join(m['id'] for m in r['matches'])) for r in permits])
 write('official_components.csv',[dict(부문=r['name'],목표=r['target_units'],실적=r['actual_units'],기준=r['period'],주의=r['note'],근거URL=r['evidence_url']) for r in benchmark['start_components']])
 annual=[]
 for c in after['portfolio_cohorts']:
  es=[e for e in c['events'] if e['stage']=='CONSTRUCTION' and e.get('status','ACTUAL')=='ACTUAL' and e['event_date']<='2026-10-19']
  old=[e for e in es if e['event_date']<'2026-01-01'];current=[e for e in es if e['event_date']>='2026-01-01']
  units=max([min(c['units'],e['units'] if e.get('units') is not None else c['units']) for e in es]+[0])
  annual.append(dict(사업ID=c['id'],사업명=c['name'],프로그램=c['program'],관리호수=c['units'],착공사건보유량=units,구분='2026 이전 착공 보유' if old else '2026 착공 기록 보유' if current else '착공 사건 미확보',사건일=' | '.join(sorted({e['event_date'] for e in es})),확인상한일=' | '.join(sorted({e['event_date'] for e in es if e.get('date_basis')=='OBSERVED_BY'})),근거URL=' | '.join(sorted({e.get('evidence_url','') for e in es}))))
 write('construction_cohort_ledger.csv',annual)
 named=[]
 for c in after['official_alignment']['cases']:
  if c['stage']!='CONSTRUCTION':continue
  named.append(dict(공식사업=c['name'],공식개략량=c['official_units'],관리사업수=len(c['members']),관리전체량=c['managed_capacity'],구성=' | '.join(m['name']+' / '+str(m['units']) for m in c['members']),주의=c['note'],근거URL=c['evidence_url']))
 write('official_named_start_crosswalk.csv',named)
 summary=dict(as_of='2026-10-19',before=metrics(before),after=metrics(after),project_records=len(projects),confirmed_907=sum(p['mapping']['policy_id']=='POL_2025_0907' and p['mapping']['status']=='CONFIRMED' for p in projects),cohorts=len(after['portfolio_cohorts']),source_ids=len({s for c in after['portfolio_cohorts'] for s in c['source_ids']}),new_units=sum(r['units'] for r in admitted['projects']),new_blocks=len(admitted['projects']),protected_records=admitted['protected_existing_records'],protected_hash_before=admitted['protected_before'],protected_hash_after=admitted['protected_after'],changed_existing_keys=admitted['changed_existing_keys'],q4_status=dict(Counter(r['키대조'] for r in q4)),q4_sale_units=10083,q4_rent_units=4648,exact_stage_units=sum(r['착공사건보유량'] for r in annual),pre2026_units=sum(r['착공사건보유량'] for r in annual if r['구분']=='2026 이전 착공 보유'),start2026_units=sum(r['착공사건보유량'] for r in annual if r['구분']=='2026 착공 기록 보유'),programs=read(WORK/'program-summary.json'),evaluation_rows=len(benchmark['rows']),supplemental_sites=len(benchmark['supplemental_site_rows']))
 (OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
 for name in ['admission-applied.json','admission-idempotence.json','collection.json','registered-official-sources.json','official-q4-plans.json','lh-progress-check.json','lh-contract-filter-check.json']:
  shutil.copy2(WORK/name,OUT/name)
 for name in ['official-brief.pdf','lh-11981.pdf','lh-12047.pdf','lh-12075.pdf','lh-12160.pdf','lh-12158.pdf']:
  shutil.copy2(WORK/name,OUT/name)
 shutil.copy2(ROOT/'backend/data/official_benchmark_20261016.json',OUT/'official_benchmark.json')
 old=ROOT/'docs/analysis/policy_readmission_20261019'
 for name in ['held_plan_groups.csv','other_policy_candidates.csv']:
  if (old/name).exists():shutil.copy2(old/name,OUT/name)
 print(json.dumps({k:v for k,v in summary.items() if k!='programs'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
