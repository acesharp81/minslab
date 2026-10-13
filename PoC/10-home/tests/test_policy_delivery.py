import unittest
from datetime import date
from backend.policy_delivery import build_delivery,save_settings

class FakeService:
    def __init__(self):
        self.project_rows=[dict(id='new',name='고양창릉 A1',district='고양창릉',block='A1',region='경기도',
            source_id='lh_construction',planned_units=1000,start_actual_date='2026-03-01',
            base_date='2026-10-01',progress_pct=50,evidence_url='https://www.lh.or.kr/source',
            mapping={'status':'REVIEW','policy_id':'POL_2025_0907'}),
            dict(id='old',name='고양창릉 A2',district='고양창릉',block='A2',region='경기도',
            source_id='lh_construction',planned_units=500,start_actual_date='2025-01-01',
            base_date='2026-10-01',evidence_url='https://www.lh.or.kr/source',mapping={'status':'REVIEW'})]
        self.config=[]
    def rows(self,kind,as_of=None):
        if kind=='policy_delivery_plan':return [dict(policy_id='POL_2025_0907',target_units=1350000,
            period_start='2026-01-01',annual=[dict(year=2026,units=269000)],region_allocations={})]
        if kind=='notice':return [dict(id='N1',name='고양창릉 A1블록 분양',region='경기도',developer='한국토지주택공사',
            units=200,source_date='2026-06-01',evidence_url='https://www.lh.or.kr/notice',source_id='cheongyak')]
        if kind=='delivery_setting':return self.config
        return []
    def projects(self,**kwargs):return self.project_rows
    def supply_dashboard(self,**kwargs):return dict(municipalities=[],blocks=[],knowledge_date='2026-10-12')
    def sources(self):return []

class DeliveryTests(unittest.TestCase):
    def test_conservation_partial_supply_and_old_start_exclusion(self):
        model=build_delivery(FakeService(),date(2026,10,12))
        self.assertEqual(model['allocated_units'],1000)
        self.assertEqual(model['current']['totals']['SUPPLY'],200)
        self.assertEqual(model['current']['totals']['CONSTRUCTION'],800)
        self.assertEqual(model['current']['totals']['MOVE_IN'],0)
        self.assertEqual(model['historical'][0]['id'],'old')
        self.assertTrue(all(p['total_units']==1350000 for p in model['snapshots']))
        self.assertEqual(len(model['snapshots']),132)
    def test_compact_projection_keeps_policy_and_project_evidence(self):
        service=FakeService()
        full=build_delivery(service,date(2026,10,12))
        compact=build_delivery(service,date(2026,10,12),include_portfolio_comparisons=False)
        self.assertEqual(compact['portfolio_comparisons'],{})
        for key in ('yearly_comparisons','cohorts','portfolio_cohorts','current','snapshots'):
            self.assertEqual(compact[key],full[key])

    def test_manual_delay_is_not_an_actual_milestone(self):
        service=FakeService();service.config=[dict(policy_id='POL_2025_0907',events=[dict(project_id='new',
            stage='MOVE_IN',event_date='2026-09-01',status='DELAYED',units=None)],targets=[])]
        model=build_delivery(service,date(2026,10,12))
        self.assertEqual(model['current']['totals']['MOVE_IN'],0)
    def test_absent_notice_never_becomes_confirmed_delay(self):
        service=FakeService();service.project_rows[0]['completion_plan_date']='2026-01-01'
        model=build_delivery(service,date(2026,10,12))
        self.assertEqual(model['issues'][0]['status'],'DELAYED') # Later 50% source proves incomplete.
        service.project_rows[0]['progress_pct']=None
        model=build_delivery(service,date(2026,10,12))
        self.assertEqual(model['issues'][0]['status'],'VERIFY')
    def test_manual_cumulative_targets_must_not_decrease(self):
        targets=[dict(scope_kind='policy',scope_id='POL_2025_0907',stage='BUSINESS',due_date=d,units=u)
                 for d,u in [('2027-12-31',1000),('2028-12-31',500)]]
        with self.assertRaisesRegex(ValueError,'감소'):save_settings(FakeService(),0,targets,[])

    def test_future_business_100_pct_is_a_plan_not_a_current_actual(self):
        service=FakeService();service.config=[dict(policy_id='POL_2025_0907',events=[],targets=[dict(
            scope_kind='policy',scope_id='POL_2025_0907',stage='BUSINESS',due_date='2027-12-01',units=1350000)])]
        model=build_delivery(service,date(2026,10,12))
        self.assertEqual(model['current']['totals']['BUSINESS'],0)
        future=next(p for p in model['snapshots'] if p['date']=='2027-12-31')
        self.assertEqual(future['totals']['POLICY'],0)
        self.assertEqual(future['totals']['UNKNOWN'],0)
        self.assertEqual(future['total_units'],1350000)

if __name__=='__main__':unittest.main()

class DeliveryStorageTests(unittest.TestCase):
    def test_multiple_stages_same_year_auth_audit_and_revision_conflict(self):
        import os,time,hmac,hashlib
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine,select
        from sqlalchemy.pool import StaticPool
        from backend.db import Base,Audit
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        app=create_app(engine,auto_collect=False)
        secret='test-delivery-secret'
        target=lambda stage:dict(scope_kind='policy',scope_id='POL_2025_0907',stage=stage,
            due_date='2027-12-31',units=1000,basis='관리자 목표',origin='MANUAL',evidence_url=None)
        payload=dict(revision_no=0,targets=[target('BUSINESS'),target('APPROVAL')],events=[])
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':secret}),patch.object(app.state.service,'projects',return_value=FakeService().project_rows),TestClient(app) as client:
            path='/poc/home/api/admin/policy-delivery'
            self.assertEqual(client.post(path,json=payload).status_code,401)
            stamp=str(int(time.time()));signature=hmac.new(secret.encode(),f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
            headers={'x-home-admin':stamp+':'+signature}
            response=client.post(path,json=payload,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(len(response.json()['targets']),2)
            self.assertEqual(client.post(path,json=payload,headers=headers).status_code,409)
            self.assertEqual(len(client.get('/poc/home/api/policy-delivery/settings').json()['targets']),2)
            with app.state.service.sessions() as session:
                self.assertEqual(len(session.scalars(select(Audit).where(Audit.action=='DELIVERY_TARGETS_UPDATED')).all()),1)

class LinkedMilestoneTests(unittest.TestCase):
    def test_notice_and_approval_subtypes_reach_policy_chart(self):
        service=FakeService();original=service.rows
        def rows(kind,as_of=None):
            if kind=='notice':return []
            if kind=='evidence_bridge':return [dict(project_id='new',source_entity_id='doc',source_revision_no=1,source_name='공식 고시·모집',source_id='cross_source',evidence_source_id='official_document',status='REVIEW',evidence_url='https://www.lh.or.kr/',facts=[
                dict(stage='SUPPLY',milestone='NOTICE',kind='ACTUAL',date='2026-09-30',units=309,basis='본모집'),
                dict(stage='APPROVAL',milestone='INITIAL_APPROVAL',kind='ACTUAL',date='2022-01-06',units=1000,basis='최초승인'),
                dict(stage='APPROVAL',milestone='AMENDED_APPROVAL',kind='ACTUAL',date='2026-06-30',units=1000,basis='변경승인'),
                dict(stage='MOVE_IN',kind='PLAN',date='2029-11',units=309,basis='입주 예정')])]
            return original(kind,as_of)
        service.rows=rows;model=build_delivery(service,date(2026,10,13));c=next(p for p in model['cohorts'] if p['id']=='new')
        self.assertEqual(model['current']['totals']['SUPPLY'],309)
        self.assertEqual(len([e for e in c['events'] if e['stage']=='APPROVAL']),2)
        self.assertEqual(model['current']['totals']['MOVE_IN'],0)
        self.assertTrue(all(p['total_units']==1350000 for p in model['snapshots']))
