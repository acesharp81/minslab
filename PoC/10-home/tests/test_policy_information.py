import unittest
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from backend.db import Base, Revision, ProgramMapping, Audit, upsert_revision
from backend.service import HomeService
from backend.policy_profile import save, profile, apply_profile, view, POLICY_ID
from backend.policy_delivery import build_delivery
from backend.policy_delivery_comparison import _official_targets
from tests.test_policy_delivery import FakeService

PLAN=dict(policy_id=POLICY_ID,target_units=1350000,period_start='2026-01-01',period_end='2030-12-31',annual=[dict(year=2026,units=269000,seoul_units=68000)],region_allocations={'서울특별시':334000,'경기도':None,'인천광역시':None},base_date='2025-09-07',evidence_url='https://example.org/original')

class PolicyInformationTests(unittest.TestCase):
    def setUp(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine);self.s=HomeService(engine)
        with self.s.sessions.begin() as session:
            upsert_revision(session,'policy_delivery_plan','policy_907_plan','907',PLAN,'test')
            for pid,policy in [('p1',POLICY_ID),('p2','OTHER')]:
                session.add(ProgramMapping(id=pid,name=pid,seed_policy_id=policy,policy_id=policy,status='REVIEW',basis='원천 제안',evidence_url='https://example.org',revision_no=1))
        self.build=patch('backend.policy_delivery.build_delivery',return_value={});self.build.start();self.addCleanup(self.build.stop)

    def test_priority_original_reset_history(self):
        save(self.s,0,{'name':'수정 정책명','annual:경기도:2026':120000},'홍길동 / 담당부서','담당자 목표 배분')
        stored=profile(self.s);self.assertEqual(stored['revision_no'],1)
        self.assertEqual(stored['overrides']['name']['actor'],'홍길동 / 담당부서')
        projected=apply_profile(PLAN,stored);self.assertEqual(projected['name'],'수정 정책명')
        points=_official_targets(projected,{'kind':'region','id':'경기도'},'CONSTRUCTION')
        self.assertEqual(points[0]['units'],120000);self.assertEqual(points[0]['origin'],'MANUAL')
        self.assertIsNone(self.s.rows('policy_delivery_plan')[0]['region_allocations']['경기도'])
        self.assertTrue(save(self.s,0,{'name':'덮어쓰기'},'다른사람','오래된 화면')['conflict'])
        save(self.s,1,{'name':None},'홍길동','원천값 복원')
        self.assertEqual(apply_profile(PLAN,profile(self.s))['name'],'9·7 주택공급 확대방안')
        with self.s.sessions() as session:
            self.assertEqual(len(session.scalars(select(Audit)).all()),2)
            self.assertEqual(len(session.scalars(select(Revision).where(Revision.kind=='policy_profile')).all()),2)

    def test_mapping_persistence_and_atomic_conflict(self):
        save(self.s,0,{},'담당자','프로그램 구성 변경',{'p1':dict(selected=False,revision_no=1),'p2':dict(selected=True,revision_no=1)})
        with self.s.sessions() as session:
            self.assertEqual(session.get(ProgramMapping,'p1').policy_id,'UNASSIGNED')
            self.assertEqual(session.get(ProgramMapping,'p2').policy_id,POLICY_ID)
            self.assertEqual(session.get(ProgramMapping,'p2').status,'CONFIRMED')
        self.assertTrue(save(self.s,1,{'name':'충돌 수정'},'담당자','충돌',{'p2':dict(selected=False,revision_no=1)})['conflict'])
        self.assertNotIn('name',profile(self.s)['overrides'])
        with self.s.sessions() as session:self.assertEqual(len(session.scalars(select(Audit).where(Audit.action=='PROGRAM_POLICY_REVIEW')).all()),2)
        with self.assertRaises(ValueError):save(self.s,1,{},'담당자','알수없는 프로그램',{'missing':dict(selected=True,revision_no=1)})
        self.assertEqual(profile(self.s)['revision_no'],1)

    def test_invalid_targets_dates_and_zero(self):
        bad=[{'target_units':-1},{'target_units':True},{'region:경기도':1400000},{'annual:서울특별시:2026':400000},{'annual:인천광역시:2026':269000},{'period_start':'2031-01-01'},{'period_end':'2026-02-30'},{'policy_id':'forged'},{'policy_id':None},{'annual:경기도:2031':1},{'name':' '}]
        for changes in bad:
            with self.subTest(changes=changes),self.assertRaises(ValueError):save(self.s,0,changes,'담당자','검증')
        self.assertEqual(profile(self.s)['revision_no'],0)
        save(self.s,0,{'annual:경기도:2026':0},'담당자','명시적 0 목표')
        self.assertEqual(profile(self.s)['overrides']['annual:경기도:2026']['value'],0)

    def test_invalid_ledger_rolls_back_mapping(self):
        with patch('backend.policy_delivery.build_delivery',side_effect=ValueError('목표 초과')):
            with self.assertRaises(ValueError):save(self.s,0,{'name':'실패'},'담당자','불가',{'p1':dict(selected=False,revision_no=1)})
        self.assertEqual(profile(self.s)['revision_no'],0)
        with self.s.sessions() as session:self.assertEqual(session.get(ProgramMapping,'p1').policy_id,POLICY_ID)

    def test_actual_missing_and_cumulative_progress(self):
        model=dict(plan=PLAN,as_of_date='2026-10-14',target_units=1350000,current={'totals':{'POLICY':1349000,'UNKNOWN':100,'CONSTRUCTION':700,'SUPPLY':200}},cohorts=[dict(id='c1',name='사업',region='경기도',units=1000,mapping_status='REVIEW',parts={'CONSTRUCTION':700,'SUPPLY':200,'UNKNOWN':100},evidence_url='https://example.org',events=[dict(stage='CONSTRUCTION',event_date='2026-03-01'),dict(stage='CONSTRUCTION',event_date='2026-04-01')])])
        data=view(self.s,model)
        self.assertEqual(data['actual']['경기도']['value'],1000)
        self.assertIsNone(data['actual']['서울특별시']['value']);self.assertIsNone(data['actual']['경기도']['annual']['2027'])
        self.assertEqual(data['progress'],dict(POLICY=1350000,BUSINESS=900,APPROVAL=900,CONSTRUCTION=900,SUPPLY=200,MOVE_IN=0))
        self.assertEqual([p['id'] for p in data['programs'] if p['selected']],['p1'])

    def test_added_year_persists_with_extended_period_and_source_unchanged(self):
        save(self.s,0,{'period_end':'2032-12-31','annual:전체:2032':1000,'annual:경기도:2032':500},'담당자','연도 추가')
        plan=apply_profile(PLAN,profile(self.s))
        self.assertEqual(plan['annual'][-1]['year'],2032)
        self.assertEqual(plan['annual'][-1]['units'],1000)
        self.assertEqual(self.s.rows('policy_delivery_plan')[0]['period_end'],'2030-12-31')
        self.assertEqual(_official_targets(plan,{'kind':'region','id':'경기도'},'CONSTRUCTION')[-1]['units'],500)

    def test_delivery_uses_profile(self):
        fake=FakeService();rows=fake.rows
        fake.rows=lambda kind,as_of=None: [dict(policy_id=POLICY_ID,overrides={'target_units':dict(value=1500000),'name':dict(value='사용자 정책')})] if kind=='policy_profile' else rows(kind,as_of)
        model=build_delivery(fake,date(2026,10,12))
        self.assertEqual(model['target_units'],1500000);self.assertEqual(model['plan']['name'],'사용자 정책')
        self.assertTrue(all(s['total_units']==1500000 for s in model['snapshots']))

    def test_program_selection_changes_real_delivery_membership(self):
        self.build.stop()
        db=self.s
        class MappedFake(FakeService):
            sessions=db.sessions
            def rows(self,kind,as_of=None):
                if kind=='policy_profile':return db.rows(kind,as_of)
                if kind=='policy_delivery_plan':return [PLAN]
                return super().rows(kind,as_of)
            def projects(self,**kwargs):
                with self.sessions() as session:
                    policies={p.id:p.policy_id for p in session.scalars(select(ProgramMapping))}
                first=dict(self.project_rows[0],mapping=dict(status='REVIEW',program_id='p1',policy_id=policies['p1']))
                second=dict(first,id='new2',name='고양창릉 A2',block='A2',planned_units=2000,mapping=dict(status='REVIEW',program_id='p2',policy_id=policies['p2']))
                return [r for r in (first,second) if not kwargs.get('policy_id') or r['mapping']['policy_id']==kwargs['policy_id']]
        service=MappedFake()
        self.assertEqual(build_delivery(service,date(2026,10,14))['allocated_units'],1000)
        save(service,0,{},'연결 담당자','구성 변경',{'p1':dict(selected=False,revision_no=1),'p2':dict(selected=True,revision_no=1)})
        result=build_delivery(service,date(2026,10,14))
        self.assertEqual(result['allocated_units'],2000)
        self.assertEqual([c['id'] for c in result['cohorts']],['new2'])
        self.assertEqual(view(db,result)['programs'][1]['evidence'][0]['origin'],'MANUAL')
        self.assertEqual(view(db,result)['programs'][1]['evidence'][-1]['value'],'OTHER')

class PolicyInformationAPITests(unittest.TestCase):
    def test_auth_save_and_conflict(self):
        import os,time,hmac,hashlib
        from fastapi.testclient import TestClient
        from backend.app import create_app
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
        service=HomeService(engine)
        with service.sessions.begin() as session:upsert_revision(session,'policy_delivery_plan','policy_907_plan','907',PLAN,'test')
        path='/poc/home/api/admin/policy-information';body=dict(revision_no=0,changes={'name':'새 이름'},actor='담당자',reason='명칭 변경')
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test'}),TestClient(create_app(engine,auto_collect=False)) as client:
            self.assertEqual(client.get('/poc/home/api/policy-information').status_code,401)
            self.assertEqual(client.post(path,json=body).status_code,401)
            stamp=str(int(time.time()));sig=hmac.new(b'test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest();headers={'x-home-admin':stamp+':'+sig}
            with patch('backend.policy_delivery.build_delivery',return_value={}):
                self.assertEqual(client.post(path,json=body,headers=headers).status_code,200)
                self.assertEqual(client.post(path,json=body,headers=headers).status_code,409)
                body.update(revision_no=1,changes={'target_units':-1})
                self.assertEqual(client.post(path,json=body,headers=headers).status_code,422)
