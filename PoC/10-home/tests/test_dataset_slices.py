"""Recipient compatibility, incremental boundaries and export safety."""
import copy
import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from backend import dataset_slices as ds


def export_fixture():
    rows = {d['name']: [] for d in ds.SPEC['slices']}
    def revision(eid, version, stamp, payload):
        return dict(entity_id=eid, kind='project', source_id='lh', revision_no=version,
                    recorded_at=stamp, payload_hash='f'*64, batch_id='batch', payload=payload)
    rows['project'] = [revision('old', 1, '2026-10-21 00:00:00+00', {'name': '이전', 'planned_units': 0}),
                       revision('new', 2, '2026-11-09 00:00:00+00', {'name': '신규', 'planned_units': None, 'actor': '김담당'})]
    rows['home_batch'] = [dict(id='old-batch', source_id='lh', status='OK', started_at='2026-10-20 00:00:00+00', finished_at='2026-10-20 01:00:00+00'),
                          dict(id='open', source_id='lh', status='RUNNING', started_at='2026-10-20 00:00:00+00', finished_at=None)]
    return dict(since=None, until='2026-11-09 01:00:00+00', rows=rows,
                current={d['name']: ds.codec.current_of(ds.codec.Slice(d), rows[d['name']]) for d in ds.SPEC['slices'] if d['mode'] != 'table'},
                removed={}, officer_terms={'names': ['김담당'], 'reasons': []})


def test_date_timezone_and_bad_inputs():
    assert ds.parse_since('delta', '2026-10-22T00:00').isoformat() == '2026-10-21T15:00:00+00:00'
    assert ds.parse_since('full', 'ignored') is None
    for mode, value in [('no', ''), ('delta', 'invalid'), ('delta', '2999-01-01')]:
        with pytest.raises(ds.ExportError): ds.parse_since(mode, value)


def test_delta_retains_global_log_digest_open_batch_and_null_zero():
    ex = export_fixture()
    before = copy.deepcopy(ex['current'])
    since = ds.parse_since('delta', '2026-10-22T00:00')
    ex['since'] = ds.codec.pg_text(since)
    assert not ds.select_delta(ex, since)
    assert [r['entity_id'] for r in ex['rows']['project']] == ['new']
    assert [r['id'] for r in ex['rows']['home_batch']] == ['open']
    assert ex['current'] == before
    assert ex['current']['home_batch']['count'] == 2


def test_privacy_change_in_unchanged_row_falls_back_to_full():
    ex = export_fixture()
    ex['rows']['project'][0]['payload']['name'] = '사업 · 김담당'
    since = ds.parse_since('delta', '2026-10-22T00:00')
    ex['since'] = ds.codec.pg_text(since)
    assert ds.select_delta(ex, since)
    assert ex['since'] is None
    assert len(ex['rows']['project']) == 2


def test_recipient_seal_apply_full_roundtrip_and_hash_rejection(tmp_path):
    ex = export_fixture()
    package, applied = tmp_path/'package', tmp_path/'applied'
    manifest = ds.codec.seal(ds.SPEC, ex, str(package))
    assert len(manifest['files']) == 31
    assert len(manifest['current']) == 27
    data = json.loads((package/'slices/project.json').read_text())
    assert '김담당' not in (package/'slices/project.json').read_text()
    assert {r['entity_id']: r['payload']['planned_units'] for r in data} == {'old': 0, 'new': None}
    result = ds.codec.apply(ds.SPEC, str(package), str(applied))
    assert result['files']['project.jsonl.gz']['rows'] == 2
    (package/'slices/project.json').write_text('[]')
    with pytest.raises(ds.codec.Stop, match='sha256'):
        ds.codec.read_package(ds.SPEC, str(package))


def test_recipient_delta_applies_and_reproduces_current_digests(tmp_path):
    ex = export_fixture()
    base = copy.deepcopy(ex)
    base['until'] = '2026-10-22 00:00:00+00'
    base['rows']['project'] = [base['rows']['project'][0]]
    base['current']['project'] = ds.codec.current_of(ds.codec.Slice(next(d for d in ds.SPEC['slices'] if d['name']=='project')),base['rows']['project'])
    ds.codec.seal(ds.SPEC,base,str(tmp_path/'base-package'))
    ds.codec.apply(ds.SPEC,str(tmp_path/'base-package'),str(tmp_path/'base'))
    since = ds.parse_since('delta','2026-10-22T00:00')
    ex['since'] = ds.codec.pg_text(since)
    assert not ds.select_delta(ex,since)
    ds.codec.seal(ds.SPEC,ex,str(tmp_path/'delta'))
    result=ds.codec.apply(ds.SPEC,str(tmp_path/'delta'),str(tmp_path/'merged'),str(tmp_path/'base'))
    assert result['files']['project.jsonl.gz']['rows']==2
    assert result['files']['home_batch.jsonl.gz']['rows']==2


def test_api_requests_deduplicated_and_all_active_programs_expanded():
    ex = export_fixture()
    calls = []
    def fetch(path, query):
        calls.append((path, query))
        if path == 'mappings':
            return {'programs': [dict(id='PRG_ab1', policy_id='POL_2025_0907', status='CONFIRMED'),
                                 dict(id='PRG_ab2', policy_id='POL_2025_0907', status='RELEASED')]}
        return {'actor':'별도담당', 'name':'자료 · 별도담당', 'value': 0, 'missing':None, 'items':[{'reason':'내부사유'}]}
    files, fetched = ds.fetch_bundle(fetch, ex, True, lambda _: None)
    assert len(calls)==len(set(calls))
    assert 'golden/S1-view-program-PRG_ab1.json' in files
    assert 'golden/S1-view-program-PRG_ab2.json' not in files
    assert len([k for k in files if k.startswith('api/')]) == 10
    assert '별도담당' not in json.dumps(files,ensure_ascii=False)
    assert files['api/policy-plan-97.json']['value']==0
    assert files['api/policy-plan-97.json']['missing'] is None
    assert len(files)==len(fetched)


def test_spooling_sanitizes_earlier_responses_with_later_names(tmp_path):
    ex=export_fixture()
    def fetch(path,query):
        return {'name':'앞 자료 · 후속담당'} if path!='mappings' else {'actor':'후속담당','programs':[]}
    files,_=ds.fetch_bundle(fetch,ex,False,lambda _:None,spool=tmp_path/'responses')
    assert len(files)==10
    assert all(isinstance(p,Path) for p in files.values())
    assert '후속담당' not in files['api/policy-plan-97.json'].read_text()
    assert files['api/policy-plan-97.json']==files['api/projects-policy-delivery-97.json']


def test_keys_stop_package_without_disclosing_value(tmp_path):
    ex=export_fixture()
    ex['rows']['project'][0]['payload']['evidence_url']='https://example.org?serviceKey=private-value'
    with pytest.raises(ds.codec.Stop) as error: ds.codec.seal(ds.SPEC,ex,str(tmp_path/'package'))
    assert 'private-value' not in str(error.value)


def test_public_document_encoding_preserves_urls_and_receiver_validation(tmp_path):
    body={'url':'https://ms.smc.seoul.kr/record/appendixDownload.do?key='+'a'*80}
    path=tmp_path/'api.json';ds.write_spooled_json(path,body)
    ds.encode_public_document_links(path)
    assert json.loads(path.read_text())==body
    assert not any(ds.codec.key_scan(path.read_text()).values())
    for url in ['https://example.org/?token='+'a'*80,
                'https://ms.smc.seoul.kr/record/appendixDownload.do?api_key=private-value',
                'https://ms.smc.seoul.kr.evil.test/record/appendixDownload.do?key='+'a'*80]:
        ds.write_spooled_json(path,{'url':url})
        with pytest.raises(ds.ExportError) as error:ds.encode_public_document_links(path)
        assert 'private-value' not in str(error.value)
    with pytest.raises(ds.ExportError):
        ds.public_json({'api_key':'private-value'}, {'names':[], 'reasons':[]})


def test_job_is_single_flight_and_get_does_not_start_new_work(tmp_path):
    jobs=ds.SliceJobs(SimpleNamespace(data_dir=tmp_path))
    gate=threading.Event()
    def build(*args):
        gate.wait(3)
        return {'filename':'home-slices-test.zip'}
    with patch.object(ds,'build',side_effect=build) as run:
        first=jobs.start(ds.TARGET,'full','',True)
        second=jobs.start(ds.TARGET,'full','',True)
        assert first['id']==second['id']
        assert jobs.get(first['id'])['status']=='RUNNING'
        with pytest.raises(ds.ExportError):jobs.start(ds.TARGET,'full','',False)
        gate.set()
        for _ in range(100):
            if jobs.get(first['id'])['status']=='COMPLETED':break
            time.sleep(.01)
        assert jobs.get(first['id'])['status']=='COMPLETED'
        assert run.call_count==1
    with pytest.raises(ds.ExportError):jobs.get('../secret')


def test_interrupted_job_is_recoverable_and_expired_job_rejected(tmp_path):
    jobs=ds.SliceJobs(SimpleNamespace(data_dir=tmp_path))
    folder=jobs.root/('a'*32);folder.mkdir(parents=True)
    jobs._save(folder,dict(id=folder.name,status='RUNNING',created_epoch=time.time()))
    assert jobs.get(folder.name)['status']=='FAILED'
    jobs._save(folder,dict(id=folder.name,status='COMPLETED',created_epoch=time.time()-ds.TTL-1))
    with pytest.raises(ds.ExportError,match='24시간'):jobs.get(folder.name)


def test_private_bundle_routes_require_admin(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine
    from sqlalchemy.pool import StaticPool
    from backend.app import create_app
    from backend.db import Base
    monkeypatch.setenv('POC10_DATA_DIR',str(tmp_path))
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    client=TestClient(create_app(engine,auto_collect=False))
    base='/poc/home/api/project-collection/slices'
    assert client.get(base).status_code==200
    for path in ['/start', '/jobs/'+('a'*32), '/jobs/'+('a'*32)+'/download']:
        assert client.get(base+path).status_code==401
    assert not (tmp_path/'runtime/dataset-slices').exists()
    engine.dispose()


def test_concurrent_database_change_never_publishes_zip(tmp_path):
    from unittest.mock import MagicMock
    service=SimpleNamespace(engine=MagicMock())
    service.engine.connect.return_value.__enter__.return_value.execute.return_value.scalar.return_value='changed'
    with patch.object(ds,'snapshot',return_value=(export_fixture(),'original')), patch.object(ds,'fetch_bundle',return_value=({},{})):
        with pytest.raises(ds.ExportError,match='DB 변경'):
            ds.build(service,tmp_path,None,False,lambda _:None)
    assert not (tmp_path/'dataset.zip').exists()


def test_legacy_adapters_keep_wire_shape_and_do_not_create_new_records():
    source=dict(id='test',name='자료',type='API',status='SUCCESS',key_configured=True,record_count=4,last_success=None,url='https://example.org')
    service=SimpleNamespace(projects=lambda **kwargs:[dict(id='p',name='사업',source_id='test',warnings=['NEEDS_CHECK'])],
                            sources=lambda **kwargs:[source], coverage_details=lambda:[],
                            data_gaps=lambda *args:{'rows':[]},rows=lambda kind:[])
    with patch('backend.coverage_audit.coverage_audit',return_value={'coverage':[]}):
        response=ds.legacy_response(service,'validation','as_of_date=2026-11-09')
    assert response['total']==1
    assert response['data_gaps']=={'rows':[]}
    assert response['items'][0]['code']=='NEEDS_CHECK'
    assert 'planned' in ds.legacy_response(service,'connections','')
    assert 'items' in ds.legacy_response(service,'api-requests','')
