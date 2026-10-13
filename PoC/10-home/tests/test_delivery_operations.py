import unittest
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,Revision
from backend.service import HomeService
from backend.delivery_operations import save,records,history,schedule_goals,scenario_comparison
from backend.policy_delivery import build_delivery,save_settings
from tests.test_policy_delivery import FakeService

class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.s=HomeService(self.engine)
        self.project=FakeService().project_rows[0]
        self.patch=patch.object(self.s,'projects',return_value=[self.project]);self.patch.start();self.addCleanup(self.patch.stop)
    def schedule(self,**kw):
        return dict(project_id='new',stage='SUPPLY',due_date='2027-02-28',units=1000,status='CONFIRMED',
                    origin='MANUAL',responsible_org='LH',basis='담당자 승인 목표',evidence_url=None,change_reason='',**kw)
    def test_baseline_immutable_revision_conflict_and_reason(self):
        v=self.schedule();a=save(self.s,'schedule','new:SUPPLY',0,v)
        self.assertEqual(a['baseline']['due_date'],'2027-02-28')
        b=dict(v,due_date='2028-02-29')
        with self.assertRaisesRegex(ValueError,'변경 사유'):save(self.s,'schedule','new:SUPPLY',a['revision_no'],b)
        b['change_reason']='기반시설 협의 일정 변경';b=save(self.s,'schedule','new:SUPPLY',a['revision_no'],b)
        self.assertEqual(b['baseline']['due_date'],'2027-02-28');self.assertEqual(b['shift_days'],366)
        self.assertTrue(save(self.s,'schedule','new:SUPPLY',a['revision_no'],v)['conflict'])
        self.assertEqual(len(history(self.s,'schedule','new:SUPPLY')),2)
        self.assertEqual(schedule_goals(self.s,date.today())[0]['due_date'],'2028-02-29')
    def test_capacity_unknown_and_release(self):
        v=self.schedule();v['units']=1001
        with self.assertRaisesRegex(ValueError,'계획량'):save(self.s,'schedule','new:SUPPLY',0,v)
        v['units']=None;a=save(self.s,'schedule','new:SUPPLY',0,v)
        self.assertEqual(schedule_goals(self.s,date.today()),[])
        v.update(units=1000,status='RELEASED');save(self.s,'schedule','new:SUPPLY',a['revision_no'],v)
        self.assertEqual(schedule_goals(self.s,date.today()),[])
    def test_cases_deduplicate_and_require_resolution(self):
        v=dict(project_id='new',stage='CONSTRUCTION',units=700,cause='PERMIT',status='OPEN',responsible_org='LH',cooperating_orgs=['고양시'],action='협의 회신',due_date='2025-01-01',basis='기관 확인',resolution='')
        save(self.s,'case','c1',0,v);save(self.s,'case','c2',0,dict(v,units=500,cause='FINANCE'))
        d=records(self.s)['summary'];self.assertEqual(d['affected_known_units'],700);self.assertEqual(d['overdue_cases'],2)
        with self.assertRaisesRegex(ValueError,'해결 결과'):save(self.s,'case','c3',0,dict(v,status='RESOLVED'))
    def test_scenario_zero_and_delay_preserve_baseline(self):
        cohort=dict(id='new',source_ids=['new'],units=1000,schedules=[dict(stage='SUPPLY',due_date='2027-12-01',units=1000,origin='SOURCE')])
        model=dict(as_of_date='2026-10-12',cohorts=[cohort],target_units=1350000,plan={})
        v=dict(name='비교',basis='공급 일정 12개월 이동',adjustments=[dict(project_id='new',stage='SUPPLY',months=0)])
        with patch('backend.policy_delivery.build_delivery',return_value=model):a=save(self.s,'scenario','s1',0,v)
        self.assertEqual(scenario_comparison(self.s,'s1')['stages']['SUPPLY'],[dict(year=2027,baseline=1000,scenario=1000)])
        v['adjustments'][0]['months']=12;save(self.s,'scenario','s1',a['revision_no'],v)
        result=scenario_comparison(self.s,'s1');self.assertEqual(result['baseline_fingerprint'],a['baseline']['fingerprint'])
        self.assertEqual(result['stages']['SUPPLY'],[dict(year=2027,baseline=1000,scenario=0),dict(year=2028,baseline=0,scenario=1000)])
        self.assertEqual(self.s.rows('delivery_setting'),[])
    def test_scenario_never_changes_official_ledger(self):
        s=FakeService();s.config=[dict(policy_id='POL_2025_0907',events=[],targets=[dict(scope_kind='policy',scope_id='POL_2025_0907',stage='SUPPLY',due_date='2027-12-01',units=1350000,origin='SCENARIO')])]
        m=build_delivery(s,date(2026,10,12));self.assertEqual(m['measurement_contract']['legacy_scenario_targets_excluded'],1)
        self.assertFalse(m['yearly_comparisons']['policy']['metrics']['SUPPLY']['management_points'])
        self.assertTrue(all(p['total_units']==1350000 for p in m['snapshots']))
    def test_manual_goal_capacity(self):
        with self.assertRaisesRegex(ValueError,'사업 계획물량'):save_settings(FakeService(),0,[dict(scope_kind='project',scope_id='new',stage='SUPPLY',due_date='2027-12-01',units=1001)],[])

class ApiTests(unittest.TestCase):
    def test_auth_and_malformed_values(self):
        import os,time,hmac,hashlib
        from fastapi.testclient import TestClient
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
        app=create_app(engine,auto_collect=False);path='/poc/home/api/admin/execution/schedule';payload=dict(key='x',revision_no=0,values={})
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test'}),TestClient(app) as client:
            self.assertEqual(client.post(path,json=payload).status_code,401)
            stamp=str(int(time.time()));sig=hmac.new(b'test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
            self.assertEqual(client.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code,422)
            self.assertEqual(client.get('/poc/home/api/execution').status_code,200)

class LedgerMeaningTests(unittest.TestCase):
    def test_movein_start_without_sale_notice_preserves_capacity(self):
        s=FakeService();s.config=[dict(policy_id='POL_2025_0907',targets=[],events=[dict(project_id='new',stage='MOVE_IN',event_date='2026-09-01',units=None,status='ACTUAL',evidence_url='https://www.lh.or.kr/start')])]
        m=build_delivery(s,date(2026,10,12));self.assertEqual(m['current']['totals']['MOVE_IN'],1000)
        self.assertEqual(m['current']['total_units'],1350000)
    def test_no_observation_never_becomes_zero_gap(self):
        s=FakeService();s.config=[dict(policy_id='POL_2025_0907',events=[],targets=[dict(scope_kind='policy',scope_id='POL_2025_0907',stage='BUSINESS',due_date='2026-01-01',units=1000)])]
        m=build_delivery(s,date(2026,10,12));self.assertIsNone(m['goal_comparisons'][0]['observed_units']);self.assertIsNone(m['goal_comparisons'][0]['gap_units'])
