"""Describe a HOME JSON snapshot with JSON Schemas and a relationship catalog."""
import gzip
import json
from collections import Counter
from pathlib import Path

from scripts.export_json import sha256_file

DRAFT = 'https://json-schema.org/draft/2020-12/schema'


def observed_type(value):
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'boolean'
    if isinstance(value, int):
        return 'integer'
    if isinstance(value, float):
        return 'number'
    if isinstance(value, str):
        return 'string'
    if isinstance(value, list):
        return 'array'
    return 'object'


def observed_schema(fields, total, title):
    properties = {}
    for key, stats in sorted(fields.items()):
        types = sorted(stats['types'])
        properties[key] = {'type': types[0] if len(types) == 1 else types,
                           'description': f"스냅샷 {total}건 중 {stats['present']}건 존재; null {stats['null']}건"}
        if 'array' in types:
            properties[key]['items'] = {}
    return {'$schema': DRAFT, 'title': title, 'description': '현재 추출본의 관측형 스키마. 신규 원천 필드는 추가될 수 있음.',
            'type': 'object', 'required': sorted(key for key, stats in fields.items() if stats['present'] == total),
            'properties': properties, 'additionalProperties': True}


def nullable(kind):
    return {'type': [kind, 'null']}


def table_schema(title, properties):
    return {'$schema': DRAFT, 'title': title, 'type': 'object',
            'required': list(properties), 'properties': properties, 'additionalProperties': False}


def schemas(kinds):
    string = {'type': 'string'}
    number = {'type': 'integer'}
    obj = {'type': 'object'}
    dt = {'type': 'string', 'format': 'date-time'}
    ndt = {'type': ['string', 'null'], 'format': 'date-time'}
    return {
        'revision-record': table_schema('HOME revision record', {
            'id': string, 'entity_id': string, 'kind': {'enum': kinds}, 'source_id': string,
            'revision_no': number, 'previous_id': nullable('string'),
            'sample_base_date': nullable('string'), 'sample_region': nullable('string'),
            'sample_name': nullable('string'), 'sample_source_date': nullable('string'),
            'sample_event_day': nullable('string'), 'payload': obj,
            'payload_hash': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
            'batch_id': string, 'recorded_at': dt, 'superseded_at': ndt,
        }),
        'source-coverage': table_schema('HOME verified query scope', {
            'id': string, 'batch_id': string, 'source_id': string, 'endpoint': string,
            'region': nullable('string'), 'area_code': nullable('string'),
            'source_period': nullable('string'), 'expected_count': nullable('integer'),
            'fetched_count': number,
            'query_status': {'enum': ['COMPLETE_QUERY', 'PARTIAL']},
            'population_status': {'enum': ['PARTIAL_SCOPE', 'UNVERIFIED']},
            'scope_note': nullable('string'), 'recorded_at': dt,
        }),
        'collection-batch': table_schema('HOME collection batch', {
            'id': string, 'source_id': string, 'started_at': dt, 'finished_at': ndt,
            'status': string, 'stats': obj, 'error': nullable('string'),
            'manifest': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'url': string, 'sha256': string, 'bytes': number, 'file': string,
                'parser_version': string, 'credentials_removed': {'type': 'boolean'}},
                'additionalProperties': True}},
        }),
        'project-identity': table_schema('HOME candidate real-project identity', {
            'id': string, 'name': string, 'region': string, 'identity_status': string, 'created_at': dt,
        }),
        'identity-alias': table_schema('HOME source object to candidate project review link', {
            'id': string, 'project_id': string, 'source_entity_id': string, 'source_id': string,
            'relation_status': string, 'match_rule': string, 'unit_comparison': nullable('string'),
            'basis': string, 'evidence_revision_id': string, 'evidence_url': string,
            'created_at': dt, 'reviewed_at': ndt,
        }),
        'project-evidence': table_schema('HOME project supporting source revision', {
            'id': string, 'project_id': string, 'revision_id': string,
            'evidence_role': string, 'created_at': dt,
        }),
        'plan': table_schema('HOME legal plan candidate', {
            'id': string, 'name': string, 'region': string, 'plan_type': string,
            'legal_status': string, 'created_at': dt,
        }),
        'plan-event': table_schema('HOME official legal notice event', {
            'id': string, 'plan_id': string, 'event_type': string, 'notice_no': nullable('string'),
            'notice_date': nullable('string'), 'evidence_url': string,
            'evidence_sha256': nullable('string'), 'source_revision_id': nullable('string'),
            'verification_status': string, 'created_at': dt,
        }),
        'plan-project-link': table_schema('HOME plan to project review link', {
            'id': string, 'plan_id': string, 'project_id': string, 'status': string,
            'basis': string, 'evidence_url': string, 'reviewed_at': ndt,
        }),
        'project-program-link': table_schema('HOME project to programme review link', {
            'id': string, 'project_id': string, 'policy_id': string, 'program_id': nullable('string'),
            'status': {'enum': ['REVIEW', 'CONFIRMED', 'RELEASED']},
            'revision_no': number, 'basis': string, 'evidence_url': string, 'reviewed_at': ndt,
        }),
        'program-policy-link': table_schema('HOME programme to policy review link', {
            'id': string, 'name': string, 'seed_policy_id': string, 'policy_id': string,
            'status': {'enum': ['REVIEW', 'CONFIRMED', 'RELEASED']},
            'revision_no': number, 'basis': string, 'evidence_url': string,
            'reviewed_at': ndt, 'created_at': dt,
        }),
        'review-audit': table_schema('HOME review audit', {
            'id': string, 'entity_id': string, 'action': string, 'before': obj,
            'after': obj, 'recorded_at': dt,
        }),
        'current-project': table_schema('HOME current project with effective review links', {
            'id': string, 'source_id': string, 'revision_no': number, 'recorded_at': dt,
            'data': obj, 'link': {'type': 'object', 'properties': {
                'program_id': nullable('string'), 'program_name': nullable('string'),
                'policy_id': string, 'program_project_status': string,
                'policy_program_status': nullable('string'),
                'program_project_basis': nullable('string'),
                'policy_program_basis': nullable('string')}, 'additionalProperties': False},
        }),
        'source-registry': {'$schema': DRAFT, 'title': 'HOME source registry and snapshot coverage',
            'type': 'object', 'required': ['id', 'name', 'url', 'type', 'current', 'revisions'],
            'properties': {'id': string, 'name': string, 'url': string, 'type': string,
                'collection_mode': string, 'current': number, 'revisions': number,
                'first_source_date': nullable('string'), 'last_source_date': nullable('string'),
                'last_attempt': ndt, 'last_attempt_status': string, 'last_success': ndt},
            'additionalProperties': True},
    }


def relationships():
    return {
        'format': 'HOME-RELATIONSHIPS-1',
        'entities': [
            {'name': 'source_registry', 'file': 'source_registry.json', 'key': ['id'], 'meaning': '수집기 정의와 이 스냅샷의 원천별 범위'},
            {'name': 'home_batch', 'file': 'collection_batches.json.gz', 'key': ['id'], 'meaning': '수집 시도·성공/실패·원본 manifest'},
            {'name': 'home_coverage', 'file': 'source_coverage.json.gz', 'key': ['id'],
             'meaning': '배치별 endpoint·지역 조회 완결성; 서울·경기 전체 사업 전수 의미 아님'},
            {'name': 'home_revision', 'file': 'revisions/{kind}.json.gz', 'key': ['id'],
             'logical_key': ['entity_id', 'revision_no'], 'current_rule': 'superseded_at == null',
             'meaning': '원천 자료의 불변 판본; kind 별 파일로 분리'},
            {'name': 'home_project', 'file': 'project_identities.json.gz', 'key': ['id'],
             'meaning': '원천 사업 후보에서 시작한 안정 정체성; 검토 전 실사업 동일성 확정 아님'},
            {'name': 'home_identity_alias', 'file': 'identity_aliases.json.gz', 'key': ['id'],
             'unique': ['source_entity_id'], 'meaning': '원천 객체→정체성 검토 링크'},
            {'name': 'home_project_evidence', 'file': 'project_evidence.json.gz', 'key': ['id'],
             'meaning': '정체성을 뒷받침하는 원천 판본'},
            {'name': 'home_plan', 'file': 'plans.json.gz', 'key': ['id'],
             'meaning': '법적 계획 후보. 정책·사업과 별도 정체성'},
            {'name': 'home_plan_event', 'file': 'plan_events.json.gz', 'key': ['id'],
             'meaning': '공식 고시 원문과 날짜·번호·원본 해시'},
            {'name': 'home_plan_project_link', 'file': 'plan_project_links.json.gz', 'key': ['id'],
             'meaning': '계획↔실사업 검토 링크; 계획 없는 사업 허용'},
            {'name': 'home_mapping', 'file': 'project_program_links.json.gz', 'key': ['id'],
             'unique': ['project_id'], 'meaning': '사업 → 프로그램 검토 링크'},
            {'name': 'home_program_mapping', 'file': 'program_policy_links.json.gz', 'key': ['id'],
             'meaning': '프로그램 → 정책 검토 링크'},
            {'name': 'home_audit', 'file': 'review_audit.json.gz', 'key': ['id'],
             'meaning': '관리자 변경과 자동 매칭 이력'},
            {'name': 'current_projects', 'file': 'current_projects.json', 'key': ['id'],
             'meaning': '현재 사업 판본과 두 단계 유효 링크를 합친 편의 뷰'},
        ],
        'relations': [
            {'from': 'home_coverage.batch_id', 'to': 'home_batch.id', 'cardinality': 'many-to-one'},
            {'from': 'home_coverage.source_id', 'to': 'source_registry.id', 'cardinality': 'many-to-one'},
            {'from': 'home_revision.source_id', 'to': 'source_registry.id', 'cardinality': 'many-to-one'},
            {'from': 'home_batch.source_id', 'to': 'source_registry.id', 'cardinality': 'many-to-one'},
            {'from': 'home_revision.batch_id', 'to': 'home_batch.id', 'cardinality': 'many-to-one'},
            {'from': 'home_revision.previous_id', 'to': 'home_revision.id', 'cardinality': 'previous-version'},
            {'from': 'home_identity_alias.project_id', 'to': 'home_project.id', 'cardinality': 'many-to-one'},
            {'from': 'home_identity_alias.source_entity_id', 'to': 'home_revision.entity_id',
             'cardinality': 'one-to-one-source-object'},
            {'from': 'home_identity_alias.evidence_revision_id', 'to': 'home_revision.id',
             'cardinality': 'many-to-one'},
            {'from': 'home_project_evidence.project_id', 'to': 'home_project.id',
             'cardinality': 'many-to-one'},
            {'from': 'home_project_evidence.revision_id', 'to': 'home_revision.id',
             'cardinality': 'many-to-one'},
            {'from': 'home_plan_event.plan_id', 'to': 'home_plan.id', 'cardinality': 'many-to-one'},
            {'from': 'home_plan_event.source_revision_id', 'to': 'home_revision.id',
             'cardinality': 'many-to-one-optional'},
            {'from': 'home_plan_project_link.plan_id', 'to': 'home_plan.id', 'cardinality': 'many-to-one'},
            {'from': 'home_plan_project_link.project_id', 'to': 'home_project.id', 'cardinality': 'many-to-one'},
            {'from': 'home_mapping.project_id', 'to': 'home_revision.entity_id',
             'condition': 'kind == project; current row has superseded_at == null', 'cardinality': 'one-to-one-current'},
            {'from': 'home_mapping.program_id', 'to': 'home_program_mapping.id', 'cardinality': 'many-to-one'},
            {'from': 'home_program_mapping.policy_id', 'to': 'home_revision.payload.id',
             'condition': 'kind == policy; UNASSIGNED is a sentinel', 'cardinality': 'many-to-one-logical'},
            {'from': 'home_audit.entity_id', 'to': 'home_mapping.project_id OR home_program_mapping.id',
             'condition': 'resolve by audit.action', 'cardinality': 'polymorphic'},
            {'from': 'current_projects.id', 'to': 'home_revision.entity_id',
             'condition': 'kind == project AND superseded_at == null', 'cardinality': 'one-to-one'},
        ],
        'sentinels': {'UNASSIGNED': '검토 링크 미연계', 'REVIEW': '자동 또는 담당자 확인 필요',
                      'CONFIRMED': '담당자 확정', 'RELEASED': '연결 해제'},
        'effective_policy_rule': 'home_mapping.program_id -> home_program_mapping.policy_id; program_policy.status == RELEASED이면 UNASSIGNED. home_mapping.policy_id는 원래 직접 제안/과거 호환 필드이며 현재 정책 FK로 사용하지 않음.',
    }


def add_file(manifest, root, path, records=None):
    relative = str(path.relative_to(root))
    entry = {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
    if records is not None:
        entry['records'] = records
    manifest['files'][relative.removesuffix('.json')] = entry


def build(root):
    root = Path(root).resolve()
    manifest_path = root / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    kinds = sorted(manifest['kind_counts'])
    catalog = {}
    for kind in kinds:
        path = root / f'revisions/{kind}.json.gz'
        fields = {}
        count = 0
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            assert handle.readline().strip() == '['
            for line in handle:
                row = line.strip().rstrip(',')
                if not row:
                    continue
                if row == ']':
                    break
                payload = json.loads(row)['payload']
                count += 1
                for key, value in payload.items():
                    item = fields.setdefault(key, {'present': 0, 'null': 0, 'types': Counter()})
                    item['present'] += 1
                    item['null'] += int(value is None)
                    item['types'][observed_type(value)] += 1
        assert count == manifest['kind_counts'][kind]['revisions'], kind
        simple = {key: {'present': value['present'], 'missing': count - value['present'],
                         'null': value['null'], 'types': dict(value['types'])}
                  for key, value in sorted(fields.items())}
        catalog[kind] = {'records': count, 'fields': simple}
        destination = root / f'schema/payloads/{kind}.schema.json'
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(observed_schema(fields, count, f'HOME {kind} payload'),
                                          ensure_ascii=False, indent=2) + '\n')
        add_file(manifest, root, destination)
        print(f'{kind}: {len(fields)} payload fields', flush=True)
    for name, schema in schemas(kinds).items():
        destination = root / f'schema/{name}.schema.json'
        destination.write_text(json.dumps(schema, ensure_ascii=False, indent=2) + '\n')
        add_file(manifest, root, destination)
    for name, value in (('payload-field-catalog', catalog), ('relationships', relationships())):
        destination = root / f'schema/{name}.json'
        destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
        add_file(manifest, root, destination)
    manifest['schema_version'] = 'HOME-JSON-SCHEMA-1'
    manifest['payload_schema_interpretation'] = '현재 추출본에서 관측한 필드 타입과 존재율. 공식 원천의 불변 계약은 아님.'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot_dir')
    build(parser.parse_args().snapshot_dir)
