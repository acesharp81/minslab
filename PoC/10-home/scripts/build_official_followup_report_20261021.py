"""Reproduce the follow-up report from pinned sources and before/after API captures.

No database writes or network calls. Preserve the preceding audit as history.
"""
import csv
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/analysis/official_followup_sources_20261021'
PRIOR = ROOT / 'docs/analysis/official_additional_checks_20261021'


def read(name):
    return json.loads((OUT / name).read_text())


def write_csv(name, rows):
    with (OUT / name).open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def metrics(model):
    cohorts = model['portfolio_cohorts']
    stages = ['BUSINESS', 'APPROVAL', 'CONSTRUCTION', 'SUPPLY', 'MOVE_IN']
    def units(c, selected):
        return min(c['units'], max([int(e.get('units') or 0) for e in c['events']
            if e['stage'] in selected and e.get('status', 'ACTUAL') == 'ACTUAL'
            and e.get('event_date') and e['event_date'] <= '2026-10-21'] + [0]))
    result = dict(cohorts=len(cohorts), capacity=sum(c['units'] for c in cohorts))
    for index, stage in enumerate(stages):
        result[stage + '_direct'] = sum(units(c, [stage]) for c in cohorts)
        result[stage + '_reached'] = sum(units(c, stages[index:]) for c in cohorts)
    return result


def main():
    plan, applied = read('application_plan.json'), read('applied.json')
    before, after = read('policy_before.json'), read('policy_after.json')
    now = datetime.now(ZoneInfo('Asia/Seoul')).isoformat()
    snapshot_at = datetime.fromtimestamp((OUT / 'policy_after.json').stat().st_mtime, ZoneInfo('Asia/Seoul')).isoformat()
    original_metrics, current_metrics = metrics(before), metrics(after)
    assert original_metrics == current_metrics
    changes = []
    for spec in plan['lh']:
        old = next(c for c in before['portfolio_cohorts'] if c['id'] == spec['project_id'])
        new = next(c for c in after['portfolio_cohorts'] if c['id'] == spec['project_id'])
        old_event = next(e for e in old['events'] if e['stage'] == 'SUPPLY')
        new_event = next(e for e in new['events'] if e['stage'] == 'SUPPLY')
        assert old_event['inferred'] and not new_event['inferred']
        assert new_event['input_rule'] == 'OFFICER_VERIFIED_SOURCE'
        assert old_event['units'] == new_event['units'] == spec['units']
        assert new_event['event_date'] == spec['date']
        changes.append(dict(project_id=spec['project_id'], name=spec['name'], units=spec['units'],
            old_date=old_event['event_date'], confirmed_date=spec['date'],
            before_basis=old_event['input_rule'], after_basis=new_event['input_rule'],
            review_label=new_event['review_label'], evidence_url=spec['url']))
    write_csv('applied_project_changes.csv', changes)
    verification = dict(verified_at=now, before=original_metrics, after=current_metrics,
        quantity_metrics_unchanged=True, verified_profile_changes=len(changes),
        source_confirmed_units=sum(c['units'] for c in changes), new_policy_assignments=0,
        note='Policy cumulative portfolio; not 2026 government statistical population. Direct includes registered officer estimates.')
    (OUT / 'post_verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2))

    with (PRIOR / 'A02_rental_partial.csv').open(encoding='utf-8-sig') as file:
        rows = list(csv.DictReader(file))
    baseline = [dict(agency='GH' if r['source_id'] == 'gh_notice' else 'LH',
        home_id=r['home_id'], name=r['name'], units=int(r['units']), source_publication_date=r['source_publication_date'],
        notice_no=r['notice_no'], evidence_url=r['evidence_url'],
        scope_note='기존 감사의 모집 범위; 사업 총량과 구분', policy_status='개별 기존 연결대장 참조') for r in rows]
    assert sum(r['units'] for r in baseline) == 3806
    for spec, result in zip(plan['lh'], applied['lh']):
        assert spec['project_id'] == result['project_id']
        baseline.append(dict(agency='LH', home_id=result['document_id'], name=spec['name'], units=spec['units'],
            source_publication_date=spec['date'], notice_no=spec['notice_no'], evidence_url=spec['url'],
            scope_note='최초 금회 모집. 기존 추정 공급량을 공식 확인으로 전환', policy_status='기존 9·7 CONFIRMED 유지'))
    for spec, result in zip(plan['sh'], applied['sh']):
        baseline.append(dict(agency='SH', home_id=result['document_id'], name=spec['name'], units=spec['units'],
            source_publication_date=spec['date'], notice_no='', evidence_url=spec['url'],
            scope_note=f"통합공고 신규만. 재공급·예비 포함 {spec['excluded_resupply_and_waitlist']:,}호 제외",
            policy_status='UNMAPPED: 개별 단지 정책 귀속 유보'))
    assert len(baseline) == 17 and sum(r['units'] for r in baseline) == 4260
    write_csv('rental_partial_notices.csv', baseline)
    agency_rows = [dict(agency=a, scope_count=sum(r['agency'] == a for r in baseline),
        source_backed_partial_units=sum(r['units'] for r in baseline if r['agency'] == a),
        status='PARTIAL', note='기관 전체 모집 실적 또는 9·7 귀속 확정 총계 아님') for a in ['LH', 'GH', 'SH']]
    assert [r['source_backed_partial_units'] for r in agency_rows] == [3533, 518, 209]
    agency_rows.append(dict(agency='iH', scope_count='', source_backed_partial_units='', status='UNVERIFIED',
        note='동일 기준 최초 임대 모집 부분합 미산출; 0호 아님'))
    write_csv('rental_partial_by_agency.csv', agency_rows)

    stats = read('molit_5387_seoul_2025_2026.json')
    monthly = []
    for period in sorted({r['date'] for r in stats}):
        subset = [r for r in stats if r['date'] == period]
        def value(major, middle=None, minor=None):
            hits = [r['착공실적'] for r in subset if r['대분류'] == major and
                (middle is None or r['중분류'] == middle) and (minor is None or r['소분류'] == minor)]
            assert len(hits) == 1
            return hits[0]
        row = dict(period=period, total_building_basis=value('계(다가구동수기준)'),
            apartments=value('아파트'), detached=value('단독', '단독', '단독'),
            multi_family_buildings=value('단독', '다가구', '동수'),
            multi_household=value('다세대'), row_houses=value('연립'))
        row['non_apartment'] = row['total_building_basis'] - row['apartments']
        row['alternative_total_household_basis'] = value('계(다가구가구수기준)')
        row['alternative_non_apartment_household_basis'] = row['alternative_total_household_basis'] - row['apartments']
        assert row['non_apartment'] == sum(row[k] for k in ['detached', 'multi_family_buildings', 'multi_household', 'row_houses'])
        monthly.append(row)
    write_csv('A04_seoul_monthly_types.csv', monthly)
    assert [sum(r['alternative_non_apartment_household_basis'] for r in monthly if r['period'].startswith(y))
        for y in ['2025', '2026']] == [2430, 4328]
    assert plan['statistics']['breakdown']['2025']['non_apartment'] == 2229
    assert plan['statistics']['breakdown']['2026']['non_apartment'] == 4165

    held = []
    holds = {
        'LH__eb2ed3e7eff3eb0f404ee288': '기존 공가주택 일반매각. 최초 공공분양 모집과 다른 사건',
        'LH__298c43e7b1b7c3431bb064fa': '금회 공급표에 예비자 포함. 신규 실물 주택 수와 분리 불완료',
        'LH__fb3218fbc5a9b1774d5e41b2': '기관 공급·예비자 포함. 신규 물량과 기존 재모집 구분 필요',
        'LH__491dcab0f2bf6791f5273ad7': '공식 모집공고 확인. 개별 사업의 9·7 귀속·기존 실적 중복 미확정',
        'LH__009b3d947980546b6866ed85': '주거약자 부분 모집 및 예비자 포함. 단지 최초 모집과 중복 확인 필요',
        'LH__96045db42d4f53e037f8dcc7': '주거약자 부분 모집. 기존 최초 모집의 추가 물량인지 미확정',
        'LH__9b9d23bf1a9da917491735e1': '공식 신규 모집. 9·7 사업 귀속·기존 정비 사업과 식별 연결 미확정',
        'LH__69ebe91c3aab17e3c9b6e467': '공식 신규 모집. 9·7 사업 귀속·기존 정비 사업과 식별 연결 미확정',
        'LH__08536c4bece1f34d66f6d48e': '공식 신규 모집. 9·7 사업 귀속·기존 정비 사업과 식별 연결 미확정',
        'LH__60c11d1d6159a7f3d2a541f1': '철거민 대상 국민임대 배정. 별도 신규 물량·일반 최초 모집 여부 미확정',
        'LH__3bf0a964c56f172b09c66f6c': '혼합단지 내 주거약자 부분 모집. 최초 모집 중복·9·7 귀속 미확정',
    }
    for capture in read('capture_manifest.json'):
        if capture['key'] not in holds:
            continue
        notice = capture['notice']['payload']
        held.append(dict(candidate_id=capture['key'], name=notice['name'], units='',
            source_type='OFFICIAL', source_date=notice['source_date'], evidence_url=capture['url'],
            disposition='HOLD_OR_EXCLUDE', reason=holds[capture['key']],
            needed='최초 공고 계보·개별 단지 식별·정책 산입 근거 중 미확정 항목 보완'))
    assert len(held) == 11
    for name, units in [('광진 DM7세종', 6), ('사당한누리채', 46), ('중랑 어반하임102', 3)]:
        held.append(dict(candidate_id='SH_FIRST:' + name, name=name, units=units,
            source_type='NON_OFFICIAL_REPOST_DETAIL;OFFICIAL_AGGREGATE_55', source_date='2026-05-28',
            evidence_url=plan['sh'][0]['url'], disposition='HOLD_POLICY_LINK',
            reason='신규55호의 세부 구성은 재게시 PDF에서 확인. 개별 9·7 귀속 근거 없음',
            needed='개별 사업과 정책·프로그램 연결 근거. 55호 부분합에 포함되므로 재가산 금지'))
    write_csv('held_connection_candidates.csv', held)

    results = json.loads((PRIOR / 'additional_check_results.json').read_text())
    for row in results:
        row['verified_at'] = now
        if row['check_id'] == 'A02':
            row.update(partial_home_units=4260, home_value=None, difference=None,
                home_snapshot_at=snapshot_at,
                home_method='기존3806 + LH 최초4공고245 + SH 신규2공고209 = 17개 공고/모집범위 부분합4260. SH는 정책 귀속 유보',
                home_query_or_script='scripts/build_official_followup_report_20261021.py; scripts/apply_followup_collections_20261021.py',
                difference_reason='기관별 전량 명세·공식 산입 기준 미완결. SH신규는 확인했으나 개별9·7귀속 미확정',
                home_source_ids='|'.join(r['home_id'] for r in baseline),
                evidence_urls='|'.join(sorted({r['evidence_url'] for r in baseline})))
        if row['check_id'] == 'A03':
            row.update(difference_reason='당대 월별 유형별 인허가 원호수 미수집. 검토 API의 제공기간 불일치·종료/빈 응답으로 재현 미완료; 비공개 단정 불가',
                unresolved_requirement='2025·2026년3~8월 서울 비아파트 인허가 유형별 정확 원호수와 동일 다가구 기준')
        if row['check_id'] == 'A04':
            row.update(home_value=plan['statistics']['rate'], quantity_unit='%', difference=plan['statistics']['rate'] - 87,
                difference_unit='percentage_points_before_rounding',
                home_rounded_difference=0,
                home_snapshot_at=snapshot_at,
                housing_type='일반주택=비아파트(담당자 확인); 다가구 동수 기준 총계에서 아파트 제외',
                home_method='2025.3~8 서울2229호;2026.3~8 서울4165호;(4165/2229-1)*100=86.85509196949303%;정수반올림87%',
                home_query_or_script='scripts/probe_housing_type_statistics_20261021.py --full-starts; scripts/build_official_followup_report_20261021.py',
                match_status='APPROX_COMPATIBLE', difference_reason='정수 반올림 일치. 일반주택=비아파트의 유형 대응은 비공식 기사·공식 별첨 대조로 담당자 확인',
                unresolved_requirement='정부 세부 유형코드가 공개되면 담당자 유형 대응을 공식 코드로 대체',
                home_source_ids='|'.join(r['id'] for r in applied['statistic_rows']),
                evidence_urls=plan['definition']['url']+'|https://stat.molit.go.kr/portal/api/apiList.do|'+row['official_source_url'],
                home_base_units_2025=2229, home_comparison_units_2026=4165, home_rounded_percent=87)
        if row['check_id'] == 'A07':
            row.update(difference_reason='공식 10.16 별첨과8.13 원문 검토. 총계·예시는 있으나 개별145건 명부와48건 완료 증빙 미확보; 공개 여부 전체 단정 불가')
    fields = list(dict.fromkeys(k for row in results for k in row))
    write_csv('followup_results.csv', [{k: r.get(k) for k in fields} for r in results])
    (OUT / 'followup_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    (OUT / 'source_file_hashes.json').write_text(json.dumps([
        dict(file=f.name, bytes=f.stat().st_size, sha256=hashlib.sha256(f.read_bytes()).hexdigest())
        for f in sorted(OUT.iterdir()) if f.suffix in ('.html', '.pdf')], ensure_ascii=False, indent=2))
    print(json.dumps(dict(metrics=current_metrics, rental_partial=4260, held_candidates=len(held),
        growth_percent=plan['statistics']['rate'], api_confirmation='PASS'), ensure_ascii=False))


if __name__ == '__main__':
    main()
