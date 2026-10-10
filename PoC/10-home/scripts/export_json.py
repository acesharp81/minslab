"""Export a consistent, credential-scrubbed HOME database snapshot as JSON.

Run inside the HOME image with POC10_DATABASE_URL and a mounted output directory.
The files are JSON arrays compressed with gzip; manifest.json is plain JSON.
"""
import argparse
import gzip
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

from sqlalchemy import select, text

from backend.db import Audit, Batch, Mapping, ProgramMapping, Revision, engine_for
from backend.sources import SOURCES

SENSITIVE_KEYS = {'servicekey', 'apikey', 'api_key', 'authkey', 'access_token',
                  'accesstoken', 'consumer_key', 'consumer_secret', 'authorization',
                  'password', 'secret', 'token'}


def credential_values():
    values = set()
    for key, value in os.environ.items():
        if value and len(value) >= 8 and any(part in key.upper() for part in
                ('KEY', 'SECRET', 'TOKEN', 'PASSWORD', 'DATABASE_URL')):
            values.update({value, quote(value, safe=''), quote_plus(value)})
    return sorted(values, key=len, reverse=True)


def scrub(value, secrets):
    if isinstance(value, dict):
        return {key: ('[REDACTED]' if str(key).lower() in SENSITIVE_KEYS else scrub(item, secrets))
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [scrub(item, secrets) for item in value]
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc).isoformat()
    if not isinstance(value, str):
        return value
    for secret in secrets:
        value = value.replace(secret, '[REDACTED]')
    if value.startswith(('https://', 'http://')):
        parts = urlsplit(value)
        query = [(key, item) for key, item in parse_qsl(parts.query, keep_blank_values=True)
                 if key.lower() not in SENSITIVE_KEYS]
        value = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return value


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_array(root, name, records, secrets, on_record=None, compressed=True):
    relative = name + ('.json.gz' if compressed else '.json')
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    opener = (lambda: gzip.open(path, 'wt', encoding='utf-8', compresslevel=3)) if compressed else (
        lambda: path.open('w', encoding='utf-8'))
    count = 0
    with opener() as handle:
        handle.write('[\n')
        for record in records:
            row = dict(record._mapping) if hasattr(record, '_mapping') else dict(record)
            if on_record:
                on_record(row)
            if count:
                handle.write(',\n')
            json.dump(scrub(row, secrets), handle, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            count += 1
        handle.write('\n]\n')
    return {'path': relative, 'records': count, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}


def export(output):
    output = Path(output).resolve()
    if output.exists():
        raise SystemExit(f'출력 폴더가 이미 존재합니다: {output}')
    staging = output.with_name(output.name + '.partial')
    if staging.exists():
        raise SystemExit(f'미완료 출력 폴더가 이미 존재합니다: {staging}')
    staging.mkdir(parents=True)
    secrets = credential_values()
    engine = engine_for()
    files = {}
    source_counts = defaultdict(lambda: {'revisions': 0, 'current': 0, 'first_source_date': None,
                                         'last_source_date': None})
    kind_counts = {}
    latest_attempt, latest_success = {}, {}

    def count_revision(row):
        sid = row['source_id']
        info = source_counts[sid]
        info['revisions'] += 1
        current = row['superseded_at'] is None
        info['current'] += int(current)
        kind_counts[row['kind']]['current'] += int(current)
        day = row['sample_source_date'] or row['sample_base_date']
        if current and day:
            info['first_source_date'] = min(info['first_source_date'], day) if info['first_source_date'] else day
            info['last_source_date'] = max(info['last_source_date'], day) if info['last_source_date'] else day

    def count_batch(row):
        sid = row['source_id']
        when = row['started_at']
        if sid not in latest_attempt or when > latest_attempt[sid]['started_at']:
            latest_attempt[sid] = {'started_at': when, 'status': row['status']}
        if row['status'] == 'SUCCESS' and (sid not in latest_success or when > latest_success[sid]):
            latest_success[sid] = when

    with engine.connect() as conn:
        transaction = conn.begin()
        if engine.dialect.name == 'postgresql':
            conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        snapshot_at = conn.scalar(text('SELECT CURRENT_TIMESTAMP'))
        kinds = conn.scalars(select(Revision.kind).distinct().order_by(Revision.kind)).all()
        for kind in kinds:
            kind_counts[kind] = {'revisions': 0, 'current': 0}
            rows = conn.execution_options(stream_results=True).execute(
                select(Revision.__table__).where(Revision.kind == kind)).yield_per(1000)
            result = write_array(staging, f'revisions/{kind}', rows, secrets, count_revision)
            kind_counts[kind]['revisions'] = result['records']
            files[f'revisions/{kind}'] = result
            print(f'{kind}: {result["records"]} revisions', flush=True)
        for name, table, callback in (
                ('collection_batches', Batch.__table__, count_batch),
                ('project_program_links', Mapping.__table__, None),
                ('program_policy_links', ProgramMapping.__table__, None),
                ('review_audit', Audit.__table__, None)):
            rows = conn.execution_options(stream_results=True).execute(select(table)).yield_per(500)
            files[name] = write_array(staging, name, rows, secrets, callback)
            print(f'{name}: {files[name]["records"]} rows', flush=True)
        mapping_by_project = {row.project_id: row for row in conn.execute(select(Mapping))}
        program_by_id = {row.id: row for row in conn.execute(select(ProgramMapping))}
        def current_projects():
            rows = conn.execution_options(stream_results=True).execute(select(Revision.__table__).where(
                Revision.kind == 'project', Revision.superseded_at.is_(None))).yield_per(500)
            for record in rows:
                row = dict(record._mapping)
                link = mapping_by_project.get(row['entity_id'])
                program = program_by_id.get(link.program_id) if link else None
                effective_policy = program.policy_id if program and program.status != 'RELEASED' else 'UNASSIGNED'
                yield {'id': row['entity_id'], 'source_id': row['source_id'], 'revision_no': row['revision_no'],
                       'recorded_at': row['recorded_at'], 'data': row['payload'],
                       'link': {'program_id': link.program_id if link else None,
                                'program_name': program.name if program else None,
                                'policy_id': effective_policy,
                                'program_project_status': link.status if link else 'REVIEW',
                                'policy_program_status': program.status if program else None,
                                'program_project_basis': link.basis if link else None,
                                'policy_program_basis': program.basis if program else None}}
        files['current_projects'] = write_array(staging, 'current_projects', current_projects(), secrets, compressed=False)
        assert files['current_projects']['records'] == kind_counts['project']['current']
        transaction.commit()

    source_registry = []
    for source in SOURCES:
        sid = source['id']
        latest = latest_attempt.get(sid)
        source_registry.append({**scrub(source, secrets), **source_counts[sid],
            'last_attempt': scrub(latest['started_at'], secrets) if latest else None,
            'last_attempt_status': latest['status'] if latest else 'NOT_COLLECTED',
            'last_success': scrub(latest_success[sid], secrets) if sid in latest_success else None})
    files['source_registry'] = write_array(staging, 'source_registry', source_registry, secrets, compressed=False)
    manifest = {'format': 'HOME-JSON-EXPORT-1', 'snapshot_at': scrub(snapshot_at, secrets),
                'scope': '서울특별시·경기도 HOME 운영 DB; 행정구역·공개 원천 표본은 별도 유형 포함',
                'snapshot_consistency': 'PostgreSQL repeatable-read read-only transaction for exported tables',
                'revisions_include_history': True, 'current_rule': 'superseded_at == null',
                'raw_response_bodies_included': False,
                'kind_counts': kind_counts, 'source_counts': dict(source_counts), 'files': files}
    manifest_path = staging / 'manifest.json'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + '\n')
    output.parent.mkdir(parents=True, exist_ok=True)
    staging.rename(output)
    print(f'EXPORT_COMPLETE {output}', flush=True)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', help='New output directory, usually data/exports/home-YYYYMMDDTHHMMSSZ')
    arguments = parser.parse_args()
    export(arguments.output)
