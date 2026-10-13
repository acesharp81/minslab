import unittest
from backend.requirements_status import build_status, indicator, STAGES

class Service:
    def projects(self, **kw):
        return [dict(id='A',name='사업',region='서울특별시',planned_units=10,developer='SH',evidence_url='https://example.org',base_date='2026-10-13')]
    def rows(self, kind): return []

class RequirementsStatusTests(unittest.TestCase):
    def test_api_empty_scope_and_cached_response(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from backend.db import Base
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with TestClient(create_app(engine,auto_collect=False)) as client:
            response=client.get('/poc/home/api/requirements-status')
            self.assertEqual(response.status_code,200)
            self.assertIsNone(response.json()['metrics']['F-03']['percent'])
            self.assertEqual(client.get('/poc/home/api/requirements-status').headers['x-home-cache'],'HIT')
    def test_zero_denominator_is_unknown_not_complete(self):
        self.assertIsNone(indicator('기록',0,0,'')['percent'])
    def test_registered_scope_and_actual_plan_are_separate(self):
        cells={s:dict(actual_available=s=='CONSTRUCTION',dated_plan_available=s in ('CONSTRUCTION','MOVE_IN')) for s in STAGES}
        data=build_status(Service(),dict(items=[dict(id='A',cells=cells,lineage={'keys':{'coordinates':'127,37'}})],as_of_date='2026-10-13'))
        self.assertEqual(data['metrics']['F-03']['percent'],20)
        self.assertEqual(data['metrics']['F-02']['count'],1)
        self.assertEqual(data['metrics']['F-09']['percent'],100)
        self.assertEqual(data['metrics']['F-06']['percent'],0)
        self.assertIsNone(data['metrics']['F-07']['percent'])
        self.assertIsNone(data['metrics']['F-12']['percent'])
        self.assertEqual(len(data['metrics']),12)
