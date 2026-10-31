"""Import completed local evaluations without inference or duplicate usage charges."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from app.config import Settings
from app.storage import Store, now


def import_history(evaluation, data, store):
    snapshot = json.loads((evaluation / 'snapshot.json').read_text())
    summary = []
    for filename in snapshot['images']:
        source = evaluation / 'inputs/images' / filename
        raw = source.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        jid = uuid.uuid5(uuid.NAMESPACE_URL, 'chekmi:qa-20261031:' + digest).hex
        previous = store.get(jid)
        if previous:
            if previous.get('evaluation_import', {}).get('image_sha256') != digest:
                raise ValueError('Import ID collision')
            summary.append(dict(id=jid, image=filename, runs=len(previous['runs']), skipped=True))
            continue  # Preserve subsequent user reviews and reanalyses.
        runs = []
        for path in sorted(evaluation.glob('*/*/' + source.stem + '.json')):
            saved = json.loads(path.read_text())
            if saved['image_sha256'] != digest:
                raise ValueError('Evaluation image hash mismatch')
            run = copy.deepcopy(saved['run'])
            run['cache_key'] = 'evaluation:' + run['id']
            run['evaluation_source'] = dict(path=str(path.relative_to(evaluation)), revision=saved['revision'], source_code=saved.get('source_code'))
            for index, result in enumerate(run['results']):
                result.setdefault('id', uuid.uuid5(uuid.NAMESPACE_URL, run['id'] + ':' + str(index)).hex)
            for ref in run['reference_snapshot']:
                name = ref.get('image_file')
                if not name:
                    continue
                if Path(name).name != name:
                    raise ValueError('Unsafe reference filename')
                asset = path.parent / (source.stem + '-work') / 'references' / name
                content = asset.read_bytes()
                target_name = 'evaluation-' + hashlib.sha256(content).hexdigest() + '.png'
                target = data / 'references' / target_name
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(content)
                ref['image_file'] = target_name
                # Snapshot only: fictional test references never enter the global registry.
            runs.append(run)
        if not runs:
            continue
        runs.sort(key=lambda r: r['created_at'])
        directory = data / jid
        directory.mkdir(exist_ok=True, mode=0o700)
        (directory / 'image.png').write_bytes(raw)
        with Image.open(source) as image:
            width, height = image.size
        latest = runs[-1]
        failed = any(r['status'] in ('ERROR', 'NOT_RUN') for r in latest['results']) or any(a.get('error') for a in latest['analysis'])
        job = dict(id=jid, created_at=now(), state='COMPLETED_WITH_ERRORS' if failed else 'COMPLETED', demo=False,
                   metadata=dict(title='자동평가 · ' + source.stem, department='', media_type='카드뉴스', release_date='',
                                 context='2026-10-31 합성 테스트 평가 기록. 정답은 모델에 제공하지 않았습니다. 미검출 및 한도 중단 결과도 보존합니다.'),
                   image=dict(width=width, height=height, original_sha256=digest, normalized_sha256=digest, orientation_normalized=True),
                   grid=dict(id='main-v1', rows=12, cols=12), runs=runs, crops=[],
                   evaluation_import=dict(dataset='qa-20261031', image_sha256=digest, imported_at=now(), no_new_api_calls=True))
        store.save(job)
        store.audit('admin', 'IMPORT_EVALUATION', jid, dict(runs=len(runs), image=filename, no_new_api_calls=True))
        summary.append(dict(id=jid, image=filename, runs=len(runs), skipped=False))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    args = parser.parse_args()
    settings = Settings()
    summary = import_history(ROOT / 'data/qa-20261031', settings.data, Store(settings.data / 'inspection.sqlite3'))
    (ROOT / 'docs/qa-suite-2026-10-31/history.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(dict(images=len(summary), runs=sum(r['runs'] for r in summary), skipped=sum(r['skipped'] for r in summary)), ensure_ascii=False))
