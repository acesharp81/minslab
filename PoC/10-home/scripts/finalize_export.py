"""Finish a HOME sharing snapshot: copy methods, hash every file, verify, and zip."""
import json
import shutil
import sys
import zipfile
from pathlib import Path

from scripts.verify_export import sha256_file, verify

ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOCS = (
    'SOURCE_REGISTRY.md', 'COLLECTION_COVERAGE.md', 'PROGRAM_HIERARCHY.md',
    'HISTORICAL_COLLECTION.md', 'AREA_CONTEXT.md', 'ANNUAL_SUPPLY.md',
    'SH_API_VERIFICATION.md', 'ADDITIONAL_API_VERIFICATION.md', 'API_KEYS.md',
)
SHARING_SCRIPTS = (
    'export_json.py', 'export_schema.py', 'export_collection_methods.py',
    'write_data_sharing_guide.py', 'finalize_export.py', 'verify_export.py',
)


def finalize(snapshot):
    snapshot = Path(snapshot).resolve()
    if not (snapshot/'manifest.json').exists() or not (snapshot/'DATA_SHARING_GUIDE.md').exists():
        raise ValueError('manifest.json과 DATA_SHARING_GUIDE.md가 필요합니다')
    refs = snapshot/'references'
    refs.mkdir(exist_ok=True)
    for name in REFERENCE_DOCS:
        shutil.copyfile(ROOT/'docs'/name, refs/name)
    code = snapshot/'reference_code'
    (code/'backend').mkdir(parents=True, exist_ok=True)
    (code/'scripts').mkdir(parents=True, exist_ok=True)
    (code/'db/migrations/versions').mkdir(parents=True, exist_ok=True)
    for path in (ROOT/'backend').glob('*.py'):
        shutil.copyfile(path, code/'backend'/path.name)
    for path in (ROOT/'db/migrations/versions').glob('*.py'):
        shutil.copyfile(path, code/'db/migrations/versions'/path.name)
    for name in SHARING_SCRIPTS:
        shutil.copyfile(ROOT/'scripts'/name, code/'scripts'/name)
    shutil.copyfile(ROOT/'requirements.txt', code/'requirements.txt')
    shutil.copyfile(ROOT/'scripts/verify_export.py', snapshot/'verify_export.py')

    manifest_path = snapshot/'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    for path in snapshot.rglob('*'):
        if not path.is_file() or path == manifest_path:
            continue
        relative = str(path.relative_to(snapshot))
        existing_key = next((k for k, v in manifest['files'].items() if v['path'] == relative), relative)
        existing = manifest['files'].get(existing_key)
        entry = {'path': relative, 'bytes': path.stat().st_size, 'sha256': sha256_file(path)}
        if existing and 'records' in existing:
            entry['records'] = existing['records']
        manifest['files'][existing_key] = entry
    manifest['package_notes'] = 'ZIP은 같은 이름의 폴더를 포함함. 압축을 풀고 해당 폴더에서 python verify_export.py . 실행.'
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    verify(snapshot)

    zip_path = snapshot.with_suffix('.zip')
    if zip_path.exists():
        raise ValueError(f'기존 ZIP을 덮어쓰지 않습니다: {zip_path}')
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for path in sorted(snapshot.rglob('*')):
            if path.is_file():
                archive.write(path, str(Path(snapshot.name)/path.relative_to(snapshot)))
    with zipfile.ZipFile(zip_path) as archive:
        broken = archive.testzip()
        if broken:
            raise ValueError(f'ZIP CRC 오류: {broken}')
    zip_path.with_suffix('.zip.sha256').write_text(f'{sha256_file(zip_path)}  {zip_path.name}\n')
    print(f'PACKAGE_COMPLETE {zip_path} ({zip_path.stat().st_size} bytes)', flush=True)
    return zip_path


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('usage: python -m scripts.finalize_export <snapshot-dir>')
    finalize(sys.argv[1])
