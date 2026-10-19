"""Reproduce the 2026-10-19 collection-gap review from frozen read-only evidence.

No network, database writes, collectors or publication. Approved values remain intact.
"""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / 'docs/evidence/HOME_COLLECTION_GAP_REVIEW_20261019'
NAME = 'HOME_COLLECTION_GAP_REVIEW_20261019'


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def main():
    db = read('database.json')
    construction = read('construction.json')
    sources = {r['id']: r for r in read('sources.json')['items']}
    official = read('official_august_transcription.json')
    assert read('period_starts.json')['periodList'] == [{'MNG_DIV_VL': '202608'}]
    totals, periods = defaultdict(int), defaultdict(set)
    seen = set()
    for r in db['statistics_2026']:
        p = r['payload']
        assert p['statistic_frequency'] == 'MONTH'
        assert '202601' <= p['statistic_period'] <= '202608'
        key = p['region'], p['statistic_metric']
        identity = (*key, p['statistic_period'])
        assert identity not in seen, identity
        seen.add(identity)
        totals[key] += p['units']
        periods[key].add(p['statistic_period'])
    checks = []
    for row in official['regional_totals']:
        key = row['region'], row['metric']
        acquired = key in totals
        checks.append(dict(row, home_value=totals.get(key), months=len(periods.get(key, set())),
            status='EXACT_MATCH' if acquired and totals[key] == row['value'] else 'NOT_ACQUIRED' if not acquired else 'DIFFERENT',
            difference=totals[key] - row['value'] if acquired else None))
    assert Counter(r['status'] for r in checks) == {'EXACT_MATCH': 9, 'NOT_ACQUIRED': 3}
    assert all(r['months'] == 8 for r in checks if r['status'] == 'EXACT_MATCH')
    metro_starts = sum(totals[region, '착공'] for region in ('서울특별시', '인천광역시', '경기도'))
    assert metro_starts == 86739
    raw = construction['raw_start_rows']
    assert len({r['entity_id'] for r in raw}) == len(raw)
    raw_summary = {}
    for kind in ('permit', 'general_permit'):
        selected = [r for r in raw if r['kind'] == kind]
        raw_summary[kind] = dict(rows=len(selected),
            positive=sum(float(r['units'] or 0) > 0 for r in selected),
            zero=sum(r['units'] == '0' for r in selected),
            bridge=sum(r['has_bridge'] for r in selected),
            identity_alias=sum(r['has_identity_alias'] for r in selected),
            regions=dict(Counter(r['sample_region'] for r in selected)))
    candidates = [r for r in raw if r['kind'] == 'general_permit' and r['construction_type'] == '신축'
                  and r['purpose'] in ('공동주택', '단독주택')]
    assert len(candidates) == 44
    assert sum(float(r['units'] or 0) > 0 for r in candidates) == 42
    assert not any(r['has_bridge'] or r['has_identity_alias'] for r in candidates)
    candidate_sum = sum(int(r['units'] or 0) for r in candidates)
    assert candidate_sum == 594
    scope_ids = ['building_general_permit', 'building_hub', 'building_hub_incheon',
                 'building_hub_details', 'building_register', 'building_register_recap']
    scope = []
    for source_id in scope_ids:
        s = sources[source_id]; st = s['stats']
        n, total = st['scope_completed_dongs'], st['scope_total_dongs']
        assert n + st['scope_remaining_dongs'] == total
        scope.append(dict(source_id=source_id, name=s['name'], completed=n, total=total,
            remaining=total-n, percent=round(100*n/total, 2), last_success=s['last_success']))
    result = dict(review_date='2026-10-19', statistical_checks=checks, metro_starts=metro_starts,
        raw_construction=raw_summary, residential_new_build_candidates=len(candidates),
        positive_residential_candidates=42, raw_candidate_household_sum=candidate_sum,
        candidate_sum_is_verified_missing_supply=False, coverage=scope,
        source_status=dict(Counter(s['status'] for s in sources.values())),
        database_mutations=False, public_publication=False,
        note='담당자 승인값은 정확한 확정값. 수집·정형화·연결·집계 범위만 점검. 원천 행 수는 고유 사업 수가 아님.')
    (ROOT / 'docs' / (NAME+'.json')).write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    candidate_path = ROOT / 'docs' / (NAME+'_construction_candidates.csv')
    with candidate_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(candidates[0]))
        writer.writeheader(); writer.writerows(candidates)
    table = '\n'.join(f"| {r['region']} | {r['metric']} | {r['value']:,} | {r['home_value']:,} | 일치 · 8개월 |" if r['home_value'] is not None else
        f"| {r['region']} | {r['metric']} | {r['value']:,} | 미수집 | 대체 수집 경로 누락 |" for r in checks)
    coverage_table = '\n'.join(f"| {r['name']} | {r['completed']:,}/{r['total']:,} | {r['percent']:.2f}% | {r['remaining']:,} |" for r in scope)
    template = (ROOT / 'docs' / (NAME+'.template.md')).read_text()
    report = template.replace('{{STATISTICAL_TABLE}}', table).replace('{{COVERAGE_TABLE}}', coverage_table)
    assert '{{' not in report
    report_path = ROOT / 'docs' / (NAME+'.md')
    report_path.write_text(report)
    files = list(EVIDENCE.glob('*')) + [Path(__file__), ROOT / 'docs' / (NAME+'.template.md'), report_path,
        ROOT / 'docs' / (NAME+'.json'), candidate_path]
    files += [ROOT/'backend'/n for n in ('additional_apis.py','sources.py','building_scope.py',
        'collection_jobs.py','general_building_permits.py','seoul_cleanup.py','lh_notice_detail.py',
        'independent_metrics.py','evidence_bridge.py')]
    manifest = dict(database_captured_at=db['capture']['captured_at'], construction_captured_at=construction['captured_at'],
        api_captures=read('capture.json'), database_mutations=False,
        files={str(p.relative_to(ROOT)):dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest())
               for p in files if p.is_file()})
    (ROOT/'docs'/(NAME+'.manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(checks=dict(Counter(r['status'] for r in checks)),
        raw_construction=raw_summary,candidates=len(candidates),report=str(report_path)),ensure_ascii=False))


if __name__ == '__main__':
    main()
