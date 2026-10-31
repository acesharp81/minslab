import hashlib
import json
from PIL import Image
from app.storage import Store
from scripts.import_suite_history import import_history


def test_import_preserves_results_no_usage_or_global_reference_and_is_idempotent(tmp_path):
    evaluation=tmp_path/'evaluation'; data=tmp_path/'data';data.mkdir()
    images=evaluation/'inputs/images';images.mkdir(parents=True)
    image=images/'QA_01.png';Image.new('RGB',(20,20),'white').save(image)
    digest=hashlib.sha256(image.read_bytes()).hexdigest()
    (evaluation/'snapshot.json').write_text(json.dumps({'images':['QA_01.png']}))
    directory=evaluation/'final/models';directory.mkdir(parents=True)
    refs=directory/'QA_01-work/references';refs.mkdir(parents=True)
    (refs/'fixture.png').write_bytes(image.read_bytes())
    run=dict(id='run-1',created_at='2026-10-31T00:00:00Z',results=[{'rule_id':'D-02-l','status':'ERROR','reason':'budget'}],analysis=[],reviews=[],calls=[{'usage':{'input_tokens':12}}],reference_snapshot=[{'id':'fictional','image_file':'fixture.png'}])
    (directory/'QA_01.json').write_text(json.dumps(dict(image_sha256=digest,revision='final',run=run)))
    store=Store(data/'inspection.sqlite3')
    imported=import_history(evaluation,data,store); job=store.get(imported[0]['id'])
    assert job['state']=='COMPLETED_WITH_ERRORS'
    assert job['runs'][0]['calls']==run['calls']
    assert job['runs'][0]['results'][0]['reason']=='budget'
    assert job['runs'][0]['results'][0]['id']
    assert (data/job['id']/'image.png').read_bytes()==image.read_bytes()
    assert store.references()==[]
    with store.connect() as db:
        assert db.execute('select count(*) from usage_events').fetchone()[0]==0
    job['runs'][0]['reviews'].append({'reason':'user review'});store.save(job)
    assert import_history(evaluation,data,store)[0]['skipped']
    assert store.get(job['id'])['runs'][0]['reviews']==[{'reason':'user review'}]
