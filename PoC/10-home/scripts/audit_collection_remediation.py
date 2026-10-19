"""Reproduce remediation comparisons from private frozen evidence; no DB/network writes."""
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = 'HOME_COLLECTION_REMEDIATION_20261019'
EVIDENCE = ROOT / 'docs/evidence' / NAME


def main():
    before = json.loads((EVIDENCE/'before.json').read_text())
    after = json.loads((EVIDENCE/'after.json').read_text())
    official = json.loads((ROOT/'docs/evidence/HOME_COLLECTION_GAP_REVIEW_20261019/official_august_transcription.json').read_text())
    prior = json.loads((ROOT/'docs/HOME_COLLECTION_GAP_REVIEW_20261019.json').read_text())
    assert before['mappings'] == after['mappings'], 'Confirmed policy mappings changed'
    assert before['profiles'] == after['profiles'], 'Project profile editions changed'
    monthly = defaultdict(int)
    identities = set()
    ytd = {}
    for r in after['statistics']:
        p = r['payload']; region, metric, period = p['region'], p['statistic_metric'], p['statistic_period']
        if r['kind'] == 'statistic_reference':
            if p['statistic_frequency'] == 'YTD' and period == '202608':ytd[region, metric] = p['units']
            continue
        if p['statistic_frequency'] != 'MONTH':continue
        key = region, metric, period
        assert key not in identities, key
        identities.add(key)
        monthly[region, metric] += p['units']
    checks = []
    for r in official['regional_totals']:
        key = r['region'], r['metric']
        value = ytd.get(key) if r['metric'] == '인허가' else monthly.get(key)
        assert value == r['value'], (key, value, r['value'])
        checks.append(dict(r, home_value=value, difference=value-r['value'],
            method='공식 PDF 누계' if r['metric']=='인허가' else '월별 관측 8개월 합산'))
    assert len(checks) == 12
    old_sources = {r['id']:r for r in before['sources']}
    new_sources = {r['id']:r for r in after['sources']}
    scope = []
    for sid in ('building_general_permit','building_hub','building_hub_incheon','building_hub_details','building_register','building_register_recap'):
        b, a = old_sources[sid]['stats'], new_sources[sid]['stats']
        scope.append(dict(source_id=sid, name=new_sources[sid]['name'], before=b['scope_completed_dongs'],
            after=a['scope_completed_dongs'], total=a['scope_total_dongs'], remaining=a['scope_remaining_dongs']))
    candidates = after['construction_candidates']
    assert all(r['identity'] and r['has_evidence'] for r in candidates)
    with (ROOT/'docs'/f'{NAME}_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(candidates[0]));writer.writeheader();writer.writerows(candidates)
    result = dict(captured_at=after['captured_at'],statistical_checks=checks,coverage=scope,
        before_candidate_rows=prior['residential_new_build_candidates'],candidate_rows=len(candidates),
        candidate_evidence_linked=sum(r['has_evidence'] for r in candidates),
        candidate_positive_rows=sum((r['units'] or 0)>0 for r in candidates),
        candidate_raw_units=sum(r['units'] or 0 for r in candidates),candidate_units_are_verified_missing_supply=False,
        seoul_detail_rows=len(after['seoul_details']),seoul_unlinked_details=sum(r['payload'].get('discovery_candidate',False) for r in after['seoul_details']),
        confirmed_mappings_preserved=len(after['mappings']),profiles_preserved=len(after['profiles']),
        sources=len(after['sources']),source_status=dict(Counter(r['status'] for r in after['sources'])),
        raw_counts=after['raw_counts'],before_source_count=len(before['sources']))
    (ROOT/'docs'/f'{NAME}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    template=(ROOT/'docs'/f'{NAME}.template.md').read_text()
    replacements={
        '{{CAPTURED}}':after['captured_at'],
        '{{SCOPE_TABLE}}':'\n'.join(f"| {r['name']} | {r['before']:,}/{r['total']:,} | {r['after']:,}/{r['total']:,} | {r['after']-r['before']:+,} | {r['remaining']:,} |" for r in scope),
        '{{STAT_TABLE}}':'\n'.join(f"| {r['region']} | {r['metric']} | {r['value']:,} | {r['home_value']:,} | 0 | {r['method']} |" for r in checks),
        '{{CANDIDATES}}':str(len(candidates)),
        '{{POSITIVE}}':str(result['candidate_positive_rows']),
        '{{RAW_UNITS}}':str(result['candidate_raw_units']),
        '{{SOURCE_STATUS}}':' · '.join(f'{k} {v}개' for k,v in result['source_status'].items()),
    }
    for k,v in replacements.items():template=template.replace(k,v)
    (ROOT/'docs'/f'{NAME}.md').write_text(template)
    files=sorted(EVIDENCE.rglob('*'))+[ROOT/'docs'/f'{NAME}{suffix}' for suffix in ('.json','.md','.template.md','_candidates.csv')]
    files += [Path(__file__),ROOT/'scripts/snapshot_collection_remediation.py']
    manifest={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    (ROOT/'docs'/f'{NAME}.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(official_checks=len(checks),candidate_rows=len(candidates),approved_values_preserved=True),ensure_ascii=False))


if __name__=='__main__':main()
