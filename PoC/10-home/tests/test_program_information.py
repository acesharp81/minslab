import unittest
from datetime import date
from unittest.mock import patch
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from backend.db import Base,ProgramMapping,Mapping,Revision,Audit,upsert_revision
from backend.service import HomeService
from backend.program_profile import save,view,profiles
from backend.program_catalog import apply
from backend.policy_delivery_comparison import comparison_index,program_target_points

class ProgramInformationTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine);self.s=HomeService(self.engine)
        self.p='PRG_TEST';self.policy='POL_2025_0907'
        with self.s.sessions.begin() as db:
            db.add(ProgramMapping(id=self.p,name='자료 프로그램',seed_policy_id=self.policy,policy_id=self.policy,status='REVIEW',revision_no=1,basis='문서근거',evidence_url='https://example.org'))
            db.add(Mapping(project_id='PRO_TEST',program_id='UNASSIGNED',policy_id='UNASSIGNED',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
            upsert_revision(db,'program_source','policy_907_plan',self.p,dict(program_id=self.p,base_date='2025-09-07',fields=dict(name='자료 프로그램',target_units=100,metric='CONSTRUCTION',unit='호',period_start='2026-01-01',period_end='2030-12-31'),basis='2030년까지100호',evidence_url='https://example.org',printed_page=5,pdf_page=8),'test')
    def edit(self,changes,version=0,links=None):return save(self.s,self.p,version,changes,'담당자','검토',links,1)
    def test_manual_priority_reset_and_no_source_mutation(self):
        self.edit({'name':'입력명','annual:전체:2026':30})
        p=profiles(self.s)[self.p];self.assertEqual(p['values']['name'],'입력명');self.assertEqual(p['source']['fields']['name'],'자료 프로그램')
        self.assertTrue(self.edit({'target_units':90},0)['conflict'])
        self.edit({'name':None},1);self.assertEqual(profiles(self.s)[self.p]['values']['name'],'자료 프로그램')
        with self.s.sessions() as db:self.assertEqual(len(db.scalars(select(Audit).where(Audit.action=='PROGRAM_PROFILE_UPDATED')).all()),2)
    def test_invalid_and_conflicting_edits_are_atomic(self):
        for changes in ({'target_units':True},{'annual:전체:2026':101},{'unit':'원'},{'metric':'FAKE'},{'name':' '},{'period_end':'2020-01-01'},{'id':None}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):self.edit(changes)
        result=self.edit({'name':'충돌'},links={'PRO_TEST':dict(selected=True,revision_no=2)})
        self.assertTrue(result['conflict']);self.assertEqual(profiles(self.s)[self.p]['revision_no'],0)
    def test_project_links_saved_and_released(self):
        self.edit({},links={'PRO_TEST':dict(selected=True,revision_no=1)})
        with self.s.sessions() as db:self.assertEqual(db.scalar(select(Mapping).where(Mapping.project_id=='PRO_TEST')).program_id,self.p)
        self.edit({},1,{'PRO_TEST':dict(selected=False,revision_no=2)})
        with self.s.sessions() as db:self.assertEqual(db.scalar(select(Mapping).where(Mapping.project_id=='PRO_TEST')).program_id,'UNASSIGNED')
    def test_empty_program_target_graph_does_not_require_projects(self):
        p=profiles(self.s)[self.p]
        plan=dict(policy_id=self.policy,period_start='2026-01-01',period_end='2030-12-31',annual=[],program_profiles={self.p:dict(p,name='빈 프로그램')})
        d=comparison_index(plan,[],{},[],date(2026,10,14))['program:'+self.p]['metrics']['CONSTRUCTION']
        self.assertEqual(d['target_points'][-1]['units'],100);self.assertEqual(d['actual_points'],[])
        self.assertIsNone(next(a for a in d['annual'] if a['year']==2030)['target_units'])
        self.edit({'unit':'개소'});self.assertEqual(program_target_points(profiles(self.s)[self.p],'CONSTRUCTION'),[])
    def test_view_without_projects_and_unknown_not_zero(self):
        with patch.object(self.s,'projects',return_value=[]):
            d=view(self.s,self.p,dict(as_of_date='2026-10-14',cohorts=[]))
        self.assertEqual(d['fields']['target_units']['value'],100);self.assertIsNone(d['actual']['전체']['value'])
        self.assertEqual(d['progress']['POLICY'],100);self.assertEqual(d['programs'],[])
    def test_cumulative_stage_reach_and_added_year(self):
        self.edit({'period_end':'2031-12-31','annual:전체:2031':20})
        c=dict(name='입주 사업',program_id=self.p,parts={'BUSINESS':10,'APPROVAL':20,'CONSTRUCTION':30,'SUPPLY':15,'MOVE_IN':5,'UNKNOWN':20},events=[],region='경기도')
        with patch.object(self.s,'projects',return_value=[]):
            data=view(self.s,self.p,dict(as_of_date='2026-10-14',cohorts=[c]))
        self.assertEqual(data['progress'],dict(POLICY=100,BUSINESS=80,APPROVAL=70,CONSTRUCTION=50,SUPPLY=20,MOVE_IN=5))
        self.assertEqual(data['years'][-1],2031)
        self.assertEqual(data['fields']['annual:전체:2031']['value'],20)
        self.assertEqual(c['parts']['BUSINESS'],10)
        self.assertEqual(profiles(self.s)[self.p]['source']['fields']['period_end'],'2030-12-31')

    def test_bulk_membership_conflict_rolls_back_every_project(self):
        with self.s.sessions.begin() as db:
            db.add(Mapping(project_id='PRO_Z',program_id='UNASSIGNED',policy_id='UNASSIGNED',status='REVIEW',revision_no=1,basis='원천',evidence_url='https://example.org'))
        links={key:dict(selected=True,revision_no=1) for key in ('PRO_TEST','PRO_Z')}
        links['PRO_Z']['revision_no']=2
        self.assertTrue(self.edit({},links=links)['conflict'])
        with self.s.sessions() as db:
            self.assertTrue(all(m.program_id=='UNASSIGNED' for m in db.scalars(select(Mapping))))
        links['PRO_Z']['revision_no']=1
        self.edit({},links=links)
        with self.s.sessions() as db:
            self.assertTrue(all(m.program_id==self.p for m in db.scalars(select(Mapping))))

    def test_supplement_is_idempotent_and_records_evidence(self):
        with patch.object(self.s,'projects',return_value=[]):
            first=apply(self.s,False);second=apply(self.s,False)
        self.assertEqual(len(first['projects_added']),3);self.assertEqual(first['sources_saved'],17)
        self.assertEqual(second['projects_added'],[]);self.assertEqual(second['sources_saved'],0)
        self.assertEqual(len(self.s.rows('program_district_plan')),20)
        sites=self.s.rows('project');self.assertEqual(next(p for p in sites if p['name']=='번동2단지')['planned_units'],3048)
        self.assertTrue(all(p.get('stage')!='MOVE_IN' for p in sites))
    def test_api_requires_admin_and_versions(self):
        import os,time,hmac,hashlib
        from fastapi.testclient import TestClient
        from backend.app import create_app
        path='/poc/home/api/admin/program-information/'+self.p
        payload=dict(revision_no=0,mapping_revision_no=1,changes={'name':'관리자 수정'},actor='담당자',reason='입력')
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test'}),TestClient(create_app(self.engine,auto_collect=False)) as client:
            self.assertEqual(client.get('/poc/home/api/program-information/'+self.p).status_code,401)
            self.assertEqual(client.post(path,json=payload).status_code,401)
            stamp=str(int(time.time()));sig=hmac.new(b'test',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
            self.assertEqual(client.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code,200)
            self.assertEqual(client.post(path,json=payload,headers={'x-home-admin':stamp+':'+sig}).status_code,409)
