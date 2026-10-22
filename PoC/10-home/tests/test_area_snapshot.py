from datetime import datetime,timezone
from types import SimpleNamespace
from unittest.mock import patch
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.db import Base,upsert_revision
from backend.service import HomeService
from backend.app import create_app
from backend.area_snapshot import SnapshotStore,atomic_json,file_path,folder,refresh,stamp,REGIONS,FORMAT

@pytest.fixture
def service(tmp_path):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine);s=HomeService(engine,tmp_path)
    yield s
    engine.dispose()

def sample(year=2026):
    return dict(format=FORMAT,year=year,version='v1',generated_at=datetime.now(timezone.utc).isoformat(),
        places={'regions':{r:['중구'] for r in REGIONS}},
        contexts={r:{'':{'region':r,'value':0,'missing':None},'중구':{'region':r,'municipality':'중구','value':8}} for r in REGIONS},
        annual={r:{'rows':[{'year':year,'units':0}]} for r in REGIONS},outlooks={r:{'baseline':None} for r in REGIONS})

def test_persists_across_process_restart_and_only_swaps_complete_file(service):
    data=sample();atomic_json(file_path(service,2026),data)
    first=SnapshotStore(service);assert first.read(2026)==data
    assert SnapshotStore(service).read(2026)==data
    data['contexts']['경기도']['']['value']=123;atomic_json(file_path(service,2026),data)
    assert first.bundle('경기도',None,2026)['data']['value']==123
    assert first.bundle('서울특별시',None,2026)['data']=={'region':'서울특별시','value':0,'missing':None}
    assert first.read(2025) is None
    with pytest.raises(ValueError):first.bundle('경기도','없는시',2026)

def test_failed_or_changed_build_retains_last_completed_file(service):
    old=sample();atomic_json(file_path(service,2026),old);state={}
    with patch('backend.area_snapshot.stamp',return_value='v2'),patch('backend.area_stats.area_places',return_value=old['places']),patch('backend.area_snapshot.build_year',side_effect=RuntimeError('failed')):
        with pytest.raises(RuntimeError):refresh(service,state,years=[2026])
    assert SnapshotStore(service).read(2026)==old
    with patch('backend.area_snapshot.stamp',side_effect=['v2','v3']),patch('backend.area_stats.area_places',return_value=old['places']),patch('backend.area_snapshot.build_year',return_value=sample()):
        assert refresh(service,state,years=[2026])==[]
    assert state['last_error']=='SOURCE_CHANGED_DURING_BUILD'
    assert SnapshotStore(service).read(2026)==old

def test_unchanged_inputs_skip_and_successful_refresh_replaces(service):
    old=sample();atomic_json(file_path(service,2026),old)
    with patch('backend.area_snapshot.stamp',return_value='v1'),patch('backend.area_stats.area_places',return_value=old['places']),patch('backend.area_snapshot.build_year') as build:
        assert refresh(service,years=[2026])==[];build.assert_not_called()
    new=sample();new['contexts']['경기도']['']['value']=99
    with patch('backend.area_snapshot.stamp',return_value='v2'),patch('backend.area_stats.area_places',return_value=old['places']),patch('backend.area_snapshot.build_year',return_value=new):
        assert refresh(service,years=[2026])==[2026]
    assert SnapshotStore(service).read(2026)['version']=='v2'

def test_snapshot_version_ignores_unlinked_raw_records_but_sees_regional_corrections(service):
    before=stamp(service)
    with service.sessions.begin() as db:upsert_revision(db,'general_permit','building_general_permit','p',{'units':8},'test')
    assert stamp(service)==before
    with service.sessions.begin() as db:upsert_revision(db,'area_stat','kosis_housing','r',{'housing_units':9},'test')
    assert stamp(service)!=before
    regional=stamp(service)
    with service.sessions.begin() as db:upsert_revision(db,'living_stat','kosis_living','income',{'mean_annual':123},'test')
    assert stamp(service)!=regional

def test_api_serves_saved_content_without_recalculation_or_external_collection(service,monkeypatch):
    monkeypatch.setenv('POC10_DATA_DIR',str(service.data_dir));data=sample();atomic_json(file_path(service,2026),data)
    client=TestClient(create_app(service.engine,auto_collect=False))
    try:
        with patch('backend.area_stats.area_context',side_effect=AssertionError('must not compute')),patch('backend.area_outlook.area_outlook',side_effect=AssertionError('must not compute')):
            response=client.get('/poc/home/api/area-dashboard?region=경기도&year=2026')
            assert response.status_code==200 and response.headers['x-home-cache']=='AREA_SNAPSHOT'
            assert response.json()['data']==data['contexts']['경기도']['']
            assert client.get('/poc/home/api/area-context?region=경기도&year=2026').json()==data['contexts']['경기도']['']
            assert client.get('/poc/home/api/area-outlook?region=경기도').json()==data['outlooks']['경기도']
            assert client.get('/poc/home/api/area-dashboard?region=경기도&year=2025').status_code==503
            assert client.get('/poc/home/api/area-dashboard?region=경기도&year=2099').status_code==422
        atomic_json(folder(service)/'health.json',{'status':'RETRYING','last_error':'timeout'})
        assert client.get('/poc/home/api/area-dashboard?region=경기도&year=2026').json()['snapshot']['refresh_failed'] is True
    finally:client.close()
