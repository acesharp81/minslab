from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.app import create_app
from backend.db import Base, Revision
from backend.service import HomeService
from backend.data_gaps import data_gap_audit, SERIES


def test_year_coverage_is_lightweight_and_retired_routes_are_absent():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    app = create_app(engine, auto_collect=False)
    with TestClient(app) as client, patch.object(HomeService, 'projects', side_effect=AssertionError('must not load projects')):
        response = client.get('/poc/home/api/sources/year-coverage')
        assert response.status_code == 200
        data = response.json()
        assert len(data['rows']) == len(SERIES) * 3
        assert {r['region'] for r in data['rows']} == {'서울특별시', '경기도', '인천광역시'}
        assert all(c['status'] == 'NOT_STARTED' for r in data['rows'] for c in r['cells'])
        assert '전수표는 아닙니다' in data['notice']
        for route in ['samples', 'samples/export.csv', 'samples/old', 'validation', 'connections', 'api-requests']:
            assert client.get('/poc/home/api/' + route).status_code == 404
        assert client.get('/poc/home/api/sources/lh_notice/samples').status_code == 200
        assert client.post('/poc/home/api/admin/api-requests/old', json={}).status_code == 404
    engine.dispose()


def test_incheon_missing_rows_are_not_assumed_complete():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    service = HomeService(engine)
    with service.sessions.begin() as session:
        session.add(Revision(entity_id='LH_YEAR', kind='lh_supply', source_id='lh_supply_history', revision_no=1,
            sample_region='경기도', sample_source_date='2020-05-01', payload={'year': 2020}, payload_hash='x', batch_id='test'))
    source = {'id': 'lh_supply_history', 'last_attempt': '2026-10-10', 'last_success': '2026-10-10',
        'stats': {'complete_query': True, 'period_start': '2020', 'period_end': '2025'}}
    with service.sessions() as session:
        data = data_gap_audit(session, [source], [], 2020, regions=('서울특별시', '인천광역시', '경기도'))
    rows = {r['region']: r for r in data['rows'] if r['source_id'] == 'lh_supply_history'}
    assert rows['서울특별시']['cells'][-1]['status'] == 'NO_SOURCE_RECORD'
    assert rows['인천광역시']['cells'][-1]['status'] == 'NOT_ACQUIRED'
    assert rows['경기도']['cells'][-1]['status'] == 'ACQUIRED'
    engine.dispose()
