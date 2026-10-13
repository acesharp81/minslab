"""Verify HOME JSON snapshot file hashes, row counts, and core link integrity.

Works with Python's standard library; no HOME service or API keys are needed.
"""
import gzip
import hashlib
import json
import sys
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def json_rows(path):
    if path.suffix != '.gz':
        value = json.loads(path.read_text())
        if not isinstance(value, list):
            raise ValueError(f'JSON 배열이 아닙니다: {path}')
        yield from value
        return
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        if stream.readline().strip() != '[':
            raise ValueError(f'JSON 배열 시작이 아닙니다: {path}')
        end = False
        for line in stream:
            value = line.strip().rstrip(',')
            if not value:
                continue
            if value == ']':
                end = True
                break
            yield json.loads(value)
        if not end:
            raise ValueError(f'JSON 배열 끝이 아닙니다: {path}')


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'manifest.json').read_text())
    for name, info in manifest['files'].items():
        path = root / info['path']
        if not path.is_file() or path.stat().st_size != info['bytes'] or sha256_file(path) != info['sha256']:
            raise ValueError(f'파일 크기 또는 SHA-256 불일치: {info["path"]}')
        if 'records' in info:
            found = sum(1 for _ in json_rows(path))
            if found != info['records']:
                raise ValueError(f'레코드 건수 불일치: {name}, {found} != {info["records"]}')
        print(f'OK {info["path"]}', flush=True)
    programs = {r['id']: r for r in json_rows(root/'program_policy_links.json.gz')}
    projects = {r['id']: r for r in json_rows(root/'current_projects.json')}
    links = list(json_rows(root/'project_program_links.json.gz'))
    if len({r['project_id'] for r in links}) != len(links):
        raise ValueError('사업→프로그램 링크에 중복 사업이 있습니다')
    for link in links:
        if link['project_id'] not in projects:
            raise ValueError(f'현재 사업이 없는 링크: {link["project_id"]}')
        pid = link['program_id']
        if pid not in (None, 'UNASSIGNED') and pid not in programs:
            raise ValueError(f'프로그램이 없는 링크: {pid}')
        if projects[link['project_id']]['link']['program_id'] != pid:
            raise ValueError(f'편의 뷰와 링크 불일치: {link["project_id"]}')
    if (root/'project_identities.json.gz').is_file():
        identities = {r['id'] for r in json_rows(root/'project_identities.json.gz')}
        aliases = list(json_rows(root/'identity_aliases.json.gz'))
        if len({r['source_entity_id'] for r in aliases}) != len(aliases):
            raise ValueError('정체성 별칭의 원천 객체 키 중복')
        for alias in aliases:
            if alias['project_id'] not in identities:
                raise ValueError('정체성 별칭의 사업 ID 누락')
        for item in json_rows(root/'project_evidence.json.gz'):
            if item['project_id'] not in identities:
                raise ValueError('사업 근거의 정체성 ID 누락')
        plans = {r['id'] for r in json_rows(root/'plans.json.gz')}
        for item in json_rows(root/'plan_events.json.gz'):
            if item['plan_id'] not in plans:
                raise ValueError('고시 사건의 계획 ID 누락')
        for item in json_rows(root/'plan_project_links.json.gz'):
            if item['plan_id'] not in plans or item['project_id'] not in identities:
                raise ValueError('계획·사업 링크의 대상 ID 누락')
    print(f'VERIFIED {len(manifest["files"])} files, {len(projects)} current projects, {len(programs)} programmes', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('사용법: python verify_export.py <스냅샷 폴더>')
    verify(sys.argv[1])
