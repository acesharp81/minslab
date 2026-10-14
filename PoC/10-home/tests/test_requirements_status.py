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
            empty=client.get('/poc/home/api/map/progress')
            self.assertEqual(empty.status_code,200)
            self.assertEqual(empty.json()['status'],'PLAN_NOT_COLLECTED')
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

    def test_estimates_are_separated_without_losing_source_fallback(self):
        def cell(*sources):
            return dict(sources=list(sources), actual_available=any(r['kind']=='ACTUAL' and not r.get('scope_partial') for r in sources),
                        dated_plan_available=any(r['kind']=='PLAN' and r.get('date') for r in sources))
        plan=dict(kind='PLAN',date='2026-09-01',inferred=True,origin='MANUAL')
        actual=dict(kind='ACTUAL',date='2026-09-01',inferred=True,origin='MANUAL',review_status='CONFIRMED')
        collected=dict(kind='ACTUAL',date='2026-09-01',units=0)
        approved=dict(kind='PLAN',date='2026-08-01',origin='MANUAL',input_rule='SOURCE_ACCEPTED')
        cells={stage:cell() for stage in STAGES}
        cells.update(BUSINESS=cell(plan,actual), APPROVAL=cell(approved,collected,actual),
                     CONSTRUCTION=cell(approved,dict(collected,scope_partial=True)), MOVE_IN=cell(plan))
        result=build_status(Service(),dict(items=[dict(id='A',cells=cells)]))['metrics']
        self.assertEqual(result['F-02']['with_estimates']['count'],2)
        self.assertEqual(result['F-02']['without_estimates']['count'],1)
        self.assertEqual(result['F-03']['without_estimates']['count'],1)
        self.assertEqual(result['F-09']['with_estimates']['count'],1)
        self.assertEqual(result['F-09']['without_estimates']['count'],0)
        for metric in result.values():
            self.assertEqual(metric['with_estimates']['total'],metric['without_estimates']['total'])
        self.assertTrue(plan['inferred'])

    def test_provenance_and_original_inference_survive_confirmation(self):
        from backend.requirements_status import estimated
        self.assertTrue(estimated(dict(field_provenance={'units':{'rule':'PROJECT_CAPACITY_TARGET'}},origin='MANUAL')))
        self.assertTrue(estimated(dict(method='CONFIRMED',original_method='PREREQUISITE')))
        self.assertFalse(estimated(dict(origin='MANUAL',input_rule='SOURCE_ACCEPTED',inferred=False)))
        self.assertFalse(estimated(dict(origin='MANUAL',input_rule='MEASUREMENT_TO_TARGET',inferred=False)))

    def test_estimated_field_falls_back_to_original_and_scope_denominator_stays(self):
        class EstimatedService(Service):
            def projects(self, **kw):
                return [dict(super().projects()[0],coordinate_basis='APPROXIMATE_DISTRICT',
                             planned_units=20,source_values={'planned_units':10},manual_fields={'planned_units':dict(value=20,inferred=True)})]
            def rows(self,kind):
                return [dict(project_id='A',stage='BUSINESS',baseline={'due_date':'2026-01-01'},inferred=True)] if kind=='execution_schedule' else []
        cells={s:dict(sources=[],actual_available=False,dated_plan_available=False) for s in STAGES}
        metrics=build_status(EstimatedService(),dict(items=[dict(id='A',cells=cells,lineage={'keys':{'coordinates':'127,37'}})]))['metrics']
        self.assertEqual(metrics['F-04']['without_estimates']['count'],1)
        self.assertEqual(metrics['F-01']['without_estimates']['count'],0)
        self.assertEqual(metrics['F-06']['with_estimates']['count'],1)
        self.assertEqual(metrics['F-06']['without_estimates']['count'],0)

    def test_linked_public_block_location_counts_without_estimates(self):
        cells={s:dict(sources=[],actual_available=False,dated_plan_available=False) for s in STAGES}
        locations={'blocks':[dict(id='BLOCK',project_ids=['A'],latitude=37,longitude=127,coordinate_basis='LH_PUBLIC_BLOCK_LABEL_POINT')]}
        metrics=build_status(Service(),dict(items=[dict(id='A',cells=cells)]),locations)['metrics']
        self.assertEqual(metrics['F-01']['without_estimates']['percent'],100)
        self.assertEqual(metrics['F-01']['with_estimates']['percent'],100)
