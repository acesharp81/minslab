import unittest
from datetime import date
from unittest.mock import patch
from tests.test_delivery_operations import OperationsTests
from backend.execution_insights import build,confirmed_observation
from backend.delivery_operations import save,history
from backend.api_requests import save as save_request,board,draft

class InsightsTests(OperationsTests):
    def matrix(self,sources=None):
        cells={s:dict(sources=[],targets=[]) for s in ('BUSINESS','APPROVAL','CONSTRUCTION','SUPPLY','MOVE_IN')}
        cells['SUPPLY']=dict(sources=sources or [],targets=[dict(date='2026-09',units=1000,basis='공식 공급 예정')])
        return dict(items=[dict(id='new',name='사업',region='경기도',municipality='고양시',cells=cells)])
    def test_overdue_without_observation_is_verify_not_zero(self):
        d=build(self.s,self.matrix(),date(2026,10,13));r=d['items'][0]
        self.assertEqual(r['status'],'VERIFY');self.assertIsNone(r['actual_units']);self.assertIsNone(r['delay_days'])
    def test_review_partial_inference_not_confirmed_observation(self):
        for extra in [dict(review_status='REVIEW'),dict(scope_partial=True),dict(method='PREREQUISITE')]:
            cell=dict(sources=[dict(kind='ACTUAL',date='2026-08-01',units=1000,**extra)])
            self.assertIsNone(confirmed_observation(cell,'SUPPLY',date(2026,10,13),1000)['units'])
    def test_larger_supply_observation_uses_its_date(self):
        cell=dict(sources=[dict(kind='ACTUAL',date='2026-08-01',units=100),dict(kind='ACTUAL',date='2026-10-01',units=1000)])
        self.assertEqual(confirmed_observation(cell,'SUPPLY',date(2026,10,13),1000)['date'],'2026-10-01')
    def test_completion_not_start_and_progress_not_completion(self):
        cell=dict(sources=[dict(kind='ACTUAL',date='2026-09-01',pct=20),dict(kind='ACTUAL',date='2026-10-01',milestone='COMPLETION',units=1000)])
        self.assertIsNone(confirmed_observation(cell,'CONSTRUCTION',date(2026,10,13),1000)['date'])
        self.assertEqual(confirmed_observation(cell,'COMPLETION',date(2026,10,13),1000)['date'],'2026-10-01')
    def test_approved_baseline_delay_plan_and_actual(self):
        v=self.schedule();v['due_date']='2026-08-31';a=save(self.s,'schedule','new:SUPPLY',0,v)
        sources=[dict(kind='ACTUAL',date='2026-09-05',units=1000)]
        r=build(self.s,self.matrix(sources),date.today())['items'][0]
        self.assertEqual(r['status'],'DELAYED');self.assertEqual(r['delay_days'],5)
        save(self.s,'schedule','new:SUPPLY',a['revision_no'],dict(v,due_date='2026-11-01',change_reason='기반시설 일정 변경'))
        r=build(self.s,self.matrix(),date.today())['items'][0];self.assertEqual(r['status'],'PLAN_DELAY')
    def test_agency_validation_history_and_missing_actual(self):
        v=dict(project_id='new',stage='SUPPLY',units=700,due_date='2026-09-30',responsible_org='LH',cooperating_orgs=['고양시'],approving_org='국토부',status='CONFIRMED',basis='기관 배정표',evidence_url='https://www.lh.or.kr/plan',change_reason='')
        with self.assertRaisesRegex(ValueError,'HTTPS'):save(self.s,'agency','new:SUPPLY',0,dict(v,evidence_url=None))
        a=save(self.s,'agency','new:SUPPLY',0,v)
        d=build(self.s,self.matrix(),date.today());self.assertIsNone(d['assignments'][0]['gap_units'])
        with self.assertRaisesRegex(ValueError,'변경 사유'):save(self.s,'agency','new:SUPPLY',a['revision_no'],dict(v,units=800))
        b=save(self.s,'agency','new:SUPPLY',a['revision_no'],dict(v,units=800,change_reason='배정 변경 승인'))
        self.assertEqual(b['baseline']['units'],700);self.assertEqual(len(history(self.s,'agency','new:SUPPLY')),2)

class RequestTests(OperationsTests):
    def test_submission_needs_external_receipt_and_connection_needs_success(self):
        v=dict(status='SUBMITTED',responsible_org='담당부서',basis='신청 기록',receipt_no='',due_date=None)
        with self.assertRaisesRegex(ValueError,'접수번호'):save_request(self.s,'kapt_basic',0,v)
        a=save_request(self.s,'kapt_basic',0,dict(v,receipt_no='REQ-01'));self.assertEqual(a['status'],'SUBMITTED')
        with self.assertRaisesRegex(ValueError,'수집 성공'):save_request(self.s,'kapt_basic',a['revision_no'],dict(v,receipt_no='REQ-01',status='CONNECTED'))
        self.assertIn('전수',draft(self.s,'occupancy_aggregate'))
        self.assertTrue(save_request(self.s,'kapt_basic',0,dict(v,status='DRAFT'))['conflict'])
