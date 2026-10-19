"""Read-only project comparison against the archived briefing; render offline HTML.

The benchmark supplies comparison labels only, never event quantities. Capture is
a repeatable-read transaction and does not create or amend assessment rounds.
"""
from collections import Counter, defaultdict
from datetime import date
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
NAME = 'HOME_OFFICIAL_PROJECT_COMPARISON_20261018'
CAPTURE = ROOT / 'data/remediation/project-comparison-20261018/capture.json'
DEST = ROOT / 'docs/evidence/HOME_PROJECT_COMPARISON_20261018'
POLICY = 'POL_2025_0907'


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture():
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker
    from backend.db import engine_for, now
    from backend.service import HomeService, KST
    from backend.independent_metrics import build
    if CAPTURE.exists():
        raise ValueError('기존 기준본을 덮어쓰지 않습니다. render로 재생성하세요.')
    engine = engine_for()
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with connection.begin():
            connection.execute(text('SET TRANSACTION READ ONLY'))
            known = now()
            service = HomeService(engine, ROOT / 'data', known_at=known)
            service.sessions = sessionmaker(bind=connection, expire_on_commit=False,
                                           join_transaction_mode='create_savepoint')
            projects = service.projects()
            result = dict(known_at=known.isoformat(), local_date=known.astimezone(KST).date().isoformat(),
                          projects=projects, raw_projects=service.rows('project'),
                          profiles=service.rows('project_profile'),
                          bridges=service.rows('evidence_bridge'),
                          stage_links=service.rows('stage_evidence'),
                          programs=service.program_links(projects=projects),
                          independent=build(service, known, period_start='2026-01-01',
                                            period_end=known.astimezone(KST).date().isoformat()))
    result['code_sha256'] = {name:sha(ROOT / 'backend' / name) for name in (
        'independent_metrics.py', 'evidence_bridge.py', 'subject_identity.py',
        'service.py', 'roadmap.py', 'integrity_diagnostics.py')}
    dump(CAPTURE, result)
    print(json.dumps(dict(known_at=result['known_at'], project_records=len(projects),
                          events=result['independent']['counts']), ensure_ascii=False))


def comparison_data(snapshot):
    from backend.evidence_bridge import facts, match_key
    from backend.integrity_diagnostics import belongs
    from backend.roadmap import source_events
    from backend.subject_identity import taxonomy
    benchmark = json.loads((ROOT / 'backend/data/official_benchmark_20261016.json').read_text())
    cases = [dict(r) for r in benchmark['rows'] if r['id'].startswith('S')]
    areas = sorted({r['name'] for r in cases})
    day = date.fromisoformat(snapshot['local_date'])
    raw = {p['id']:p for p in snapshot['raw_projects']}
    profiles = {p['project_id']:p for p in snapshot['profiles']}
    groups, project_groups = {}, {}
    for p in snapshot['projects']:
        r = raw[p['id']]
        physical = match_key(r)
        key = list(physical) if physical else ['SOURCE_ANCHOR', p['id']]
        gid = hashlib.sha256(json.dumps(key, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest()[:24]
        project_groups[p['id']] = gid
        group = groups.setdefault(gid, dict(id=gid, key=key, region=p['region'],
            label=' · '.join(physical[1:]) if physical else r['name'], records=[],
            official_areas=[], events=[], excluded_events=[], plans=[], conflicts=[]))
        matched = [area for area in areas if belongs(r['name'], area) or belongs(p['name'], area)]
        group['official_areas'] = sorted(set(group['official_areas']) | set(matched))
        keep = ('id', 'name', 'source_id', 'source_revision_id', 'revision_no', 'source_payload_hash',
                'base_date', 'source_date', 'recorded_at', 'source_age_days', 'evidence_url',
                'planned_units', 'supply_units', 'unit_basis', 'start_actual_date',
                'start_plan_date', 'completion_actual_date', 'completion_plan_date',
                'move_in_actual_date', 'construction_start_evidence', 'progress_pct',
                'progress_date', 'warnings', 'in_latest_source', 'tenure', 'mapping')
        record = {k:r.get(k) for k in keep}
        record.update(name=p['name'], source_name=r['name'], mapping=p['mapping'],
            managed_units=p.get('planned_units'), manual_fields=p.get('manual_fields', {}),
            managed_schedules=p.get('managed_schedules', {}),
            officer_progress=profiles.get(p['id'], {}).get('progress', {}),
            taxonomy=taxonomy(r), official_areas=matched, source_facts=facts(r, day))
        # Compact management metadata; preserve actual values, origin and provenance.
        for field in ('managed_schedules', 'officer_progress'):
            record[field] = {stage:{k:v.get(k) for k in (
                'units', 'event_date', 'due_date', 'inferred', 'actor', 'reason', 'evidence_url',
                'input_rule', 'input_basis', 'field_provenance', 'source_revision_id',
                'source_anchor', 'date_precision', 'source_date_label', 'batch_id')}
                for stage,v in record[field].items()}
        group['records'].append(record)
        for plan in source_events(r, day):
            group['plans'].append(dict(plan, project_id=p['id'], source_id=r['source_id'],
                revision_id=r['source_revision_id'], supply_mode=taxonomy(r)['supply_mode'],
                status='SOURCE', source_entity_id=p['id']))
    for bridge in snapshot['bridges']:
        gid = project_groups.get(bridge['project_id'])
        if not gid or bridge.get('status') not in ('REVIEW', 'CONFIRMED'):
            continue
        for f in bridge.get('facts', []):
            if f.get('kind') != 'PLAN' or not f.get('date'):
                continue
            # Do not use bridge.units or scope_units as the event/plan quantity.
            stage = f.get('milestone') or f['stage']
            stamp = f['date']
            groups[gid]['plans'].append(dict(stage=stage, due_date=stamp,
                month=stamp[:7], source_date_label=f.get('date_label') or stamp,
                precision='DAY' if len(stamp)==10 else 'MONTH' if len(stamp)==7 else 'YEAR',
                units=f.get('units'), basis=f.get('basis'), origin='LINKED_SOURCE',
                project_id=bridge['project_id'], source_id=bridge.get('evidence_source_id'),
                evidence_url=bridge.get('evidence_url'), revision_id=bridge['source_revision_id'],
                source_entity_id=bridge['source_entity_id'], source_revision_no=bridge.get('source_revision_no'),
                status=bridge['status'], relation_type=bridge.get('relation_type'),
                scope_partial=f.get('scope_partial', False), scope_label=f.get('scope_label'),
                supply_mode='UNKNOWN'))
    for field, target in [('selected_events', 'events'), ('exclusions', 'excluded_events')]:
        for event in snapshot['independent'][field]:
            gid = project_groups.get(event['project_id'])
            if gid:
                groups[gid][target].append(event)
    for conflict in snapshot['independent']['conflicts']:
        if conflict['physical_scope_id'] in groups:
            groups[conflict['physical_scope_id']]['conflicts'].append(conflict)
    for c in cases:
        c['kind'] = 'ACTUAL' if c['stage']=='착공' else 'PLAN'
        c['target_stage'] = 'CONSTRUCTION' if c['kind']=='ACTUAL' else 'MOVE_IN' if c['id'] in ('S14','S15','S16') else 'SUPPLY'
        c['supply_mode'] = 'RENT' if c['id']=='S13' else 'SALE' if c['target_stage']=='SUPPLY' else None
        c['start'],c['end'] = ('2026-01-01', snapshot['local_date']) if c['kind']=='ACTUAL' else ('2026-12-01','2026-12-31') if c['id']=='S14' else ('2027-01-01','2027-12-31') if c['id'] in ('S15','S16') else ('2026-10-01','2026-12-31')
        c['official_approximate'] = c['official_value'] is not None
        c['official_block_scope_verified'] = False
        c['comparable'] = False
        c['numeric_gap'] = None
    official_path = ROOT / 'docs/evidence/OFFICIAL_ACCURACY_20261016/briefing_official.txt'
    text = official_path.read_text()
    normalized_text = re.sub(r'\s+', '', text)
    assert all(area in normalized_text for area in areas if area not in ('신림2구역', '흑석11구역'))
    # The archive itself explicitly names both redevelopment districts.
    assert '흑석11구역' in text and '신림2구역' in text
    updated=[p for p in snapshot['profiles'] if p.get('batch_id')=='officer-added-20261018-v1']
    return dict(version='PROJECT-COMPARISON-2-WITH-ESTIMATES', known_at=snapshot['known_at'], local_date=snapshot['local_date'],
        default_policy=POLICY, official_date='2026-10-16', official_url=cases[0]['official_url'],
        official_archive_sha256=sha(official_path), benchmark_sha256=sha(ROOT / 'backend/data/official_benchmark_20261016.json'),
        capture_sha256=sha(CAPTURE), code_sha256=snapshot['code_sha256'],
        official_scope='보관된 공식 브리핑 속기의 사업별 16개 언급 · 12개 지구/정비구역',
        cases=cases, groups=sorted(groups.values(), key=lambda g:(g['region'],g['label'])),
        counts=dict(source_records=len(raw), active_source_records=sum(p['mapping']['status'] not in ('RELEASED','REJECTED') for p in snapshot['projects']),
                    policy_source_records=sum(p['mapping']['policy_id']==POLICY for p in snapshot['projects'])),
        event_method=snapshot['independent']['version'], all_event_counts=snapshot['independent']['counts'],
        estimate_update=dict(projects=len(updated),target_count=sum(len(p.get('managed_schedules',{})) for p in snapshot['projects'] if p['id'] in {r['project_id'] for r in updated}),
            measurement_count=sum(len(p.get('progress',{})) for p in updated),actor='김민',reason='공식 자료 확인 및 IH 추가 연결',
            source_project_ids=[p['project_id'] for p in updated]),
        rules=['공식 수치는 비교 대상이며 자체 사건 산출의 입력으로 사용하지 않는다.',
               '기본 범위는 확정된 9·7 정책의 208개 원천 사업 기록. 전체 활성 기록은 322개이며 고유 사업 수와 다르다.',
               '관리 사업 원장과 여기에 저장·연결된 원천을 대조했다. 일반 인허가 API 등의 전체 원시 행을 모두 고유 사업으로 간주한 명부는 아니다.',
               '공식 미언급은 이 속기의 12개 사업명/지구명에 대응하지 않음을 뜻한다. 전체 공식 첨부의 전수 미언급 판정은 아니다.',
               '지구가 언급되어도 보유한 모든 블록의 공식 실적 포함을 뜻하지 않는다.',
               '확인값과 담당자 추정값을 별도 열에서 비교한다. 추정값에는 산식·전후 관계·근거 원천을 보존하고 직접 실적에 합치지 않는다.',
               '값이 없으면 미확인으로 표시한다. 계획 총량·담당자 추정값·모집 물량으로 실제 착공 물량을 대체하지 않는다.',
               '차이는 나란히 놓인 수치의 단순 차이이며 모집단·기간 검증 전에는 정확도 오차나 실제 누락량이 아니다.',
               '실적은 2026년 발생 직접 사건의 부분집계. 공식 기준은 10월 둘째 주까지이며 HOME 인지 기준은 10월 18일이다.',
               '같은 블록의 서로 다른 유형·모집회차·원천 물량은 후보값을 병기하며 총 사업규모로 임의 합산하지 않는다.',
               '이 HTML은 조회 시점의 정적 기준본이다. 현재 DB 조회 화면의 실시간 값과 이후 달라질 수 있다.'])


def render():
    snapshot = json.loads(CAPTURE.read_text())
    data = comparison_data(snapshot)
    template = (ROOT / 'scripts/templates/official_project_comparison.html').read_text()
    data_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'), allow_nan=False).replace('<', '\\u003c')
    html = template.replace('__COMPARISON_DATA__', data_json)
    assert '__COMPARISON_DATA__' not in html
    dump(DEST / 'comparison.json', data)
    path = ROOT / 'docs' / (NAME + '.html')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html)
    dump(DEST / 'manifest.json', dict(known_at=data['known_at'], capture_sha256=sha(CAPTURE),
        html_sha256=sha(ROOT / 'docs' / (NAME+'.html')), data_sha256=sha(DEST/'comparison.json'),
        builder_sha256=sha(Path(__file__)), template_sha256=sha(ROOT / 'scripts/templates/official_project_comparison.html'),
        database_mutations=False, new_assessment_round=False))
    print(json.dumps(dict(output=str(ROOT / 'docs' / (NAME+'.html')), bytes=len(html.encode()), counts=data['counts']),ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('capture', 'render'))
    parser.add_argument('--capture-file', type=Path, help='새 조회 기준본 파일. 기존 기준본은 보존합니다.')
    args = parser.parse_args()
    if args.capture_file:CAPTURE=args.capture_file
    globals()[args.command]()
