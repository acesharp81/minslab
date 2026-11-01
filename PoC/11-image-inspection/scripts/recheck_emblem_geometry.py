"""Add an auditable local-measurement revision to an evaluation; zero API calls."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import emblem_geometry
from app.storage import now


def revise(source,evaluation,revision='geometry'):
    saved=json.loads(source.read_text());raw=(evaluation/'inputs/images'/saved['image']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=saved['image_sha256']:raise ValueError('Image hash mismatch')
    prior=saved['run'];run=copy.deepcopy(prior)
    old_work=source.parent/(Path(saved['image']).stem+'-work')
    checks=emblem_geometry.inspect(raw,run['observation'],run['reference_snapshot'],old_work)
    if not checks['checks']:raise ValueError('No eligible clear flat emblem; do not fabricate a finding')
    directory=evaluation/revision/source.parent.name;directory.mkdir(parents=True,exist_ok=True)
    target=directory/source.name
    if target.exists():raise ValueError('Existing revision; no overwrite')
    work=directory/(Path(saved['image']).stem+'-work')
    shutil.copytree(old_work/'references',work/'references')
    run.update(id=uuid.uuid4().hex,created_at=now(),finished_at=now(),phase='DONE',calls=[],reviews=[],
               selected=['H-07-b','D-02-m','D-02-o'],progress=3,total=3,elapsed_seconds=0,
               observation_reused_from={'run_id':prior['id']},analysis_reused_from={'run_id':prior['id']},
               emblem_geometry=checks,local_revision={'method':emblem_geometry.VERSION,'source_run_id':prior['id'],'api_calls':0})
    run['results']=emblem_geometry.protect(run,run['results'],run['selected'])
    for row in run['results']:
        if row.get('emblem_geometry'):row['id']=uuid.uuid4().hex
    result={**saved,'revision':revision,'source_code':'.',
            'source_hashes':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((ROOT/'app').glob('*.py'))},'run':run}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2))
    return checks


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('--evaluation-root',required=True,type=Path)
    parser.add_argument('--revision',default='geometry')
    args=parser.parse_args();checks=revise(args.source,args.evaluation_root,args.revision)
    print(json.dumps(dict(api_calls=0,checks=checks['checks']),ensure_ascii=False))
