"""Reproduce the closing audit from frozen inputs; never alter business records."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from backend.collectors import parse_lh_plan
from scripts.build_final_review_20261019 import metrics

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'data/closure-review-20261019'
PREVIOUS = ROOT / 'data/final-review-20261019'
OUT = ROOT / 'docs/analysis/closure_review_20261019'


def read(path):
    return json.loads(path.read_text())


def write_csv(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    projects = read(WORK / 'projects-before.json')
    by_id = {p['id']: p for p in projects}
    model = read(WORK / 'model-after.json')
    old_model = read(PREVIOUS / 'model-final.json')
    assert metrics(model) == metrics(old_model), 'Business quantities changed'
    protected = read(WORK / 'protected-check.json')
    assert not protected['changed_keys'] and not protected['added_keys']
    cohorts = {c['id']: c for c in model['portfolio_cohorts']}
    assert len(cohorts) == 167
    source_ids = [p for c in cohorts.values() for p in c['source_ids']]
    assert len(source_ids) == len(set(source_ids)) == 210
    assert len(projects) == 443
    assert sum(p['mapping']['policy_id'] == 'POL_2025_0907' and p['mapping']['status'] == 'CONFIRMED' for p in projects) == 222

    year, total, live = parse_lh_plan((WORK / 'lh-sale.html').read_bytes())
    assert year == 2026 and len(live) == total
    # The supplier repeats total_units on each housing-type row; sum only units.
    q4 = list(csv.DictReader((ROOT / 'docs/analysis/final_review_20261019/official_q4_plan_crosswalk.csv').open(encoding='utf-8-sig')))
    comparison = []
    for row in q4:
        ids = re.findall(r'PRO_[a-f0-9]+', row['관리사업'])
        members = list(dict.fromkeys(p for i in ids for p in cohorts[i]['source_ids']))
        raw = []
        managed = []
        for pid in members:
            p = by_id[pid]
            grouped = defaultdict(int)
            for r in p.get('rows', []):
                if r.get('supply_month') and r.get('units') is not None:
                    grouped[r['supply_month']] += r['units']
            raw.extend(f"{pid}: {month} / {units}" for month, units in sorted(grouped.items()))
            s = p.get('managed_schedules', {}).get('SUPPLY')
            if s:
                managed.append(f"{pid}: {s['due_date']} / {s['units']} / {s.get('input_rule')}")
        comparison.append(dict(공식사업=row['공식사업'],공식호수=row['공식계획호수'],공식시기=row['공식시기'],
            사업대응=row['키대조'],관리사업ID=' | '.join(ids),원천공급계획=' | '.join(raw),
            승인관리일정=' | '.join(managed),원문=row['근거URL']))
    assert len(comparison) == 32
    write_csv('q4_source_vs_management.csv', comparison)
    bp = next(p for p in projects if p['name'] == '병점복합타운 주복1')
    live_bp = [r for r in live if r['name'] == bp['name']]
    assert sum(r['units'] for r in live_bp) == 780
    assert {r['supply_month'] for r in live_bp} == {'2026-11', '2026-12'}
    assert bp['managed_schedules']['SUPPLY']['due_date'] == '2031-11-16'
    gd = next(p for p in projects if p['name'] == '고덕강일 3단지')
    assert gd['planned_units'] == 1305 and gd['rows'][0]['units'] == 215
    assert '사전청약 제외' in gd['rows'][0]['supply_basis']
    assert 1305 - 500 - 590 == 215
    live_check = []
    for name in ['병점복합타운 주복1','안산신길2 A1,A3','안산신길2 A6','안산신길2 B1']:
        r = [r for r in live if r['name'] == name]
        live_check.append(dict(사업=name,원천행수=len(r),공급호수합계=sum(x['units'] for x in r),
            공급월=' | '.join(sorted({x['supply_month'] for x in r})),
            비고=' | '.join(sorted({x.get('note','') for x in r if x.get('note')}))))
    write_csv('live_lh_supply_check.csv', live_check)

    norm = lambda x: re.sub(r'([A-Z])-?0*(\d+)', lambda m:m[1]+str(int(m[2])),x)
    labels = read(WORK / 'eight-block-map-comparison.json')
    permit = read(WORK / 'permit-recheck.json')
    earlier = read(PREVIOUS / 'permit-final-check.json')
    comparable = lambda rows: {r['project_id']: [(m['id'], m.get('units'), m.get('dates')) for m in r['matches']] for r in rows}
    assert comparable(permit) == comparable(earlier), 'New permit match requires review'
    original8 = [p for p in projects if p['source_id']=='lh_policy_followup' and p['name'] not in
        {'오산오산 1','인천검단 AA31','인천영종 A57','인천영종 A63','양주회천 A4','양주회천 A23'}]
    assert len(original8) == 8 and sum(p['planned_units'] for p in original8) == 5162
    eight=[]
    for p in original8:
        r=[r for r in labels if norm(r['bnm'])==norm(p['block']) and r['bzdtNm']==p['district']]
        assert len(r)==1
        m=next(x for x in permit if x['project_id']==p['id'])['matches']
        eight.append(dict(사업=p['name'],승인계획호수=p['planned_units'],공개지도호수=r[0]['sumCnt'],
            지도공급예정연도=r[0]['supplyYear'],지도진행표기=r[0]['phaseBusinessProgress'],
            허가후보호수=' | '.join(str(x.get('units')) for x in m),
            실제착공일=' | '.join(str(x.get('dates',{}).get('원천 착공일 (stcnsDay)')) for x in m),
            판정='계획 유지 · 지도 단계/공모/감리 발주를 주택 착공 사건으로 전환하지 않음'))
    write_csv('eight_block_closure.csv',eight)
    counts = read(WORK/'record-counts-after.json')
    write_csv('current_record_counts.csv',counts)
    scope = read(WORK/'scope-current.json')
    write_csv('collection_scope.csv',[dict(원천=r['source'],최근상태=(r['latest'] or {}).get('status'),
        조회대상동수=r['last_success_stats'].get('scope_total_dongs'),완료동수=r['last_success_stats'].get('scope_completed_dongs'),
        남은동수=r['last_success_stats'].get('scope_remaining_dongs'),설명=r['last_success_stats'].get('scope_note','')) for r in scope])
    summary=dict(business_metrics=metrics(model),projects=len(projects),confirmed_907=222,cohorts=len(cohorts),
        unique_contributing_source_ids=len(set(source_ids)),q4_rows=len(comparison),
        byungjeom_source_2026_units=780,godeok_full_units=1305,godeok_advance_units=1090,godeok_remaining_units=215,
        eight_blocks=len(eight),eight_block_units=5162,protected=protected,
        record_count_note='현재 판본 전체 원장 행 수(내부 관리기록 포함). 행은 사업 수·세대 수·정책 실적과 다름',
        current_record_rows=sum(r['count'] for r in counts),distinct_source_ids=len({r['source'] for r in counts}),
        changed_business_quantities=False)
    (OUT/'validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k not in ['protected']},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
