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
        known={r['id'] for r in (previous or {}).get('runs',[])}
        runs = []
        for path in sorted(evaluation.glob('*/*/' + source.stem + '.json')):
            saved = json.loads(path.read_text())
            if saved['image_sha256'] != digest:
                raise ValueError('Evaluation image hash mismatch')
            run = copy.deepcopy(saved['run'])
            if run['id'] in known:continue
            run['cache_key'] = 'evaluation:' + run['id']
            run['evaluation_source'] = dict(dataset=evaluation.name,path=str(path.relative_to(evaluation)), revision=saved['revision'], source_code=saved.get('source_code'),source_hashes=saved.get('source_hashes'))
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
            if previous:summary.append(dict(id=jid,image=filename,runs=len(previous['runs']),added=0,skipped=True))
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
        # Re-read under the write lock: preserve reviews/reanalyses made while
        # assets were copied. Never let import overwrite an active user job.
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body FROM jobs WHERE id=?',(jid,)).fetchone()
            if row:
                existing=json.loads(row[0])
                if existing.get('evaluation_import',{}).get('image_sha256')!=digest:raise ValueError('Import ID collision')
                if existing['state'] in ('RUNNING','QUEUED'):raise RuntimeError('Active user inspection; retry import when finished')
                known={r['id'] for r in existing['runs']}
                additions=[r for r in runs if r['id'] not in known]
                existing['runs']=sorted(existing['runs']+additions,key=lambda r:r['created_at'])
                if additions and existing['runs'][-1]['id'] in {r['id'] for r in additions}:existing['state']=job['state']
                existing['evaluation_import']['last_imported_at']=now()
                job=existing
            else:additions=runs
            db.execute('INSERT INTO jobs VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',
                       (jid,job['created_at'],json.dumps(job,ensure_ascii=False)))
        store.audit('admin', 'IMPORT_EVALUATION', jid, dict(runs=len(runs), image=filename, no_new_api_calls=True))
        summary.append(dict(id=jid, image=filename, runs=len(job['runs']), added=len(additions), skipped=not bool(additions)))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', required=True)
    parser.add_argument('--evaluation-root',type=Path,default=ROOT/'data/qa-20261031')
    parser.add_argument('--report-dir',type=Path,default=ROOT/'docs/qa-suite-2026-10-31')
    args = parser.parse_args()
    settings = Settings()
    summary = import_history(args.evaluation_root, settings.data, Store(settings.data / 'inspection.sqlite3'))
    args.report_dir.mkdir(parents=True,exist_ok=True)
    (args.report_dir/'history.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(json.dumps(dict(images=len(summary), runs=sum(r['runs'] for r in summary), skipped=sum(r['skipped'] for r in summary)), ensure_ascii=False))
