"""Reproducible review tables from saved snapshots; never writes the database."""
import csv
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from backend.lh_policy_followup import physical_key
from backend.plan_review_matching import scope_key
from backend.policy_delivery_comparison import comparison_index

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'
OUT = ROOT/'docs/analysis'
EVIDENCE = OUT/'policy_readmission_20261019'


def read(name):
    return json.loads((DATA/name).read_text())


def csv_write(name, rows):
    if not rows:
        return
    with (EVIDENCE/name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    snapshot = read('policy-readmission-snapshot-20261019.json')
    review = read('plan-links-review-20261019.json')
    sources = {r['id']: r for rs in read('policy-readmission-sources-20261019.json').values() for r in rs}
    additions = read('policy-readmission-idempotence-20261019.json')['projects']
    projects = snapshot['projects'] + [dict(id=p['id'], name=p['name'], region='인천광역시' if p['name'].startswith('인천') else '경기도',
        planned_units=p['units'], mapping=dict(policy_id='POL_2025_0907', status='CONFIRMED')) for p in additions]
    index = defaultdict(list)
    for p in projects:
        key = physical_key(p)
        if key:
            index[key].append(p)
    added_ids = {p['id'] for p in additions}
    rows = []
    for n, held in enumerate(review['held'], 1):
        key = tuple(held['key'])
        candidates = index.get(key, [])
        confirmed = [p for p in candidates if p['mapping']['status']=='CONFIRMED' and p['mapping']['policy_id']=='POL_2025_0907']
        exact = [p for p in confirmed if p.get('planned_units')==held['units']]
        if key[0] not in ('서울특별시','경기도','인천광역시'):
            category = '수도권 범위 밖'
        elif any(p['id'] in added_ids for p in confirmed):
            category = '이번 추가 블록의 별도 계획자료 · 호수·시기 대조 필요'
        elif exact:
            category = '기존 9·7 연결 사업 · 유형·시기·세부행 범위 검토'
        elif confirmed:
            category = '기존 9·7 블록 · 호수 또는 부분물량 차이'
        elif candidates:
            category = '기존 후보 · 개별 정책 귀속 근거 검토'
        else:
            category = '같은 물리 키의 사업 원장 없음'
        refs = [sources[s] for s in held['source_ids'] if s in sources]
        rows.append(dict(검토번호=n, 분류=category, 출처=held['source_id'], 시도=key[0], 지구=key[1], 블록=key[2],
            원천그룹호수=held['units'], 유형=held.get('tenure',''),
            원천명=' | '.join(dict.fromkeys(str(r.get('name','')) for r in refs)),
            원천ID=' | '.join(held['source_ids']),
            후보사업=' | '.join(f"{p['id']} / {p['name']} / {p.get('planned_units')}호 / {p['mapping']['status']}" for p in candidates),
            근거URL=' | '.join(dict.fromkeys(r.get('evidence_url','') for r in refs)),
            기존보류이유=held['reason']))
    csv_write('held_plan_groups.csv', rows)
    no_key = [dict(원천ID=r['id'], 출처=r['source_id'], 이름=r.get('name',''), 시도=r.get('region',''),
                   호수=r.get('units',r.get('planned_units')), 근거URL=r.get('evidence_url',''))
              for r in sources.values() if not scope_key(r)]
    csv_write('source_rows_without_physical_key.csv', no_key)
    csv_write('other_policy_candidates.csv', [dict(사업ID=p['id'], 사업명=p['name'], 출처=p['source_id'],
        시도=p.get('region',''), 호수=p.get('planned_units'), 정책=p['mapping']['policy_id'],
        상태=p['mapping']['status'], 기존배정근거=p['mapping'].get('basis',''), 근거URL=p.get('evidence_url',''))
        for p in snapshot['projects'] if p['mapping']['policy_id']!='POL_2025_0907'])
    csv_write('admitted_blocks.csv', [dict(사업ID=p['id'], 사업명=p['name'], 호수=p['units'], 프로그램=p['program'],
        원천ID=p['source_id'], 근거URL=p['evidence_url'], 배정근거=p['basis']) for p in additions])
    comparison = {}
    for which in ('before','after'):
        d = read(f'policy-readmission-{which}-20261019.json')
        metrics = comparison_index(dict(d['plan'], period_start='1900-01-01', portfolio=True),
            d['portfolio_cohorts'],d['settings'],[],date(2026,10,19))['policy']['metrics']
        comparison[which] = {}
        for stage, metric in metrics.items():
            # Exactly the tracking series used by policy-907.js / summaryValues.
            tracking = metric['tracking']
            actual = [p for p in tracking['actual_points'] if p['date']<='2026-10-19']
            plans = [p for p in tracking['target_points'] if p['date']<='2026-12-31']
            comparison[which][stage] = dict(actual=actual[-1]['units'] if actual else None,
                year_end=plans[-1]['units'] if plans else None)
    (DATA/'policy-readmission-comparison-20261019.json').write_text(json.dumps(comparison,ensure_ascii=False,indent=2))
    counts = dict(held_group_classification=dict(Counter(r['분류'] for r in rows)), held_groups=len(rows),
        no_physical_key_rows=len(no_key), unlinked_to_907_projects=sum(p['mapping']['policy_id']!='POL_2025_0907' for p in snapshot['projects']),
        comparison=comparison)
    (EVIDENCE/'summary.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2))
    for name in ['policy-readmission-applied-20261019.json','policy-readmission-idempotence-20261019.json',
                 'policy-readmission-program-review-20261019.json','policy-readmission-conversion-references-20261019.json',
                 'policy-readmission-comparison-20261019.json','policy-readmission-collection-20261019.json']:
        shutil.copy2(DATA/name,EVIDENCE/name)
    shutil.copy2(DATA/'policy-readmission-raw-20261019/tender-727339.pdf',EVIDENCE/'LH_20251030_tender.pdf')
    shutil.copy2(DATA/'raw/policy_129/9813bc03471c8899f346fe92415c0331115635184d6b810f5d8d33c30fbe825d.pdf',EVIDENCE/'MOLIT_20260129.pdf')
    print(json.dumps(counts,ensure_ascii=False))


if __name__=='__main__':
    main()
