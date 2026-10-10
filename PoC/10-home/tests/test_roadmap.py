import hashlib
import hmac
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.db import Audit, Base, Mapping, Revision, upsert_revision
from backend.roadmap import build_roadmap, source_events
from backend.service import HomeService, today


class RoadmapTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.directory.name)
        year=today().year
        self.payload={'name':'사업 A','region':'서울특별시','municipality':'강남구','program':'공공분양','planned_units':494,
                      'stage':'PLANNED_SUPPLY','stage_label':'공급계획','base_date':today().isoformat(),'warnings':[],
                      'proposed_policy':'POL_TEST','mapping_basis':'공식 근거','evidence_url':'https://apply.lh.or.kr/',
                      'availability':'PUBLIC','rows':[{'units':371,'supply_month':f'{year}-12','move_in_month':f'{year+1}-07'},
                                                     {'units':123,'supply_month':f'{year}-12','move_in_month':f'{year+1}-07'}]}
        with self.service.sessions.begin() as session:
            record,_=upsert_revision(session,'project','lh_sale','a',self.payload,'test')
            self.project=record.entity_id
            session.add(Mapping(project_id=self.project,policy_id='POL_TEST',status='REVIEW',basis='공식 근거',evidence_url='https://apply.lh.or.kr/'))
        self.app=create_app(self.engine,auto_collect=False)
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close();self.engine.dispose();self.directory.cleanup()

    def goal(self,year=None,units=100):
        return {'year':year or today().year+10,'stage':'SUPPLY','units':units,'basis':'담당자 추진계획','evidence_url':None}

    def auth(self,path):
        stamp=str(int(time.time()))
        signature=hmac.new(b'goal-test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
        return {'x-home-admin':stamp+':'+signature}

    def test_ten_future_years_plus_current_and_no_inferred_annual_quantities(self):
        result=self.client.get('/poc/home/api/roadmap').json()
        self.assertEqual([year['year'] for year in result['years']],list(range(today().year+1,today().year+11)))
        row=result['items'][0]
        self.assertEqual(len(row['annual']),11)
        self.assertEqual(row['annual'][0]['events'][0]['units'],494)
        self.assertEqual(row['annual'][1]['events'][0]['stage'],'MOVE_IN')
        self.assertEqual(row['annual'][1]['events'][0]['units'],494)
        self.assertEqual(row['annual'][-1]['status'],'NOT_SET')
        self.assertEqual(row['annual'][-1]['events'],[])
        self.assertEqual(self.client.get('/poc/home/api/roadmap?region=경기도').json()['total'],0)
        self.assertEqual(self.client.get('/poc/home/api/roadmap?horizon=11').status_code,422)
        self.assertEqual(self.client.get('/poc/home/api/roadmap?horizon=1').json()['horizon'],1)

    def test_unknown_units_and_contract_completion_are_not_actual_supply(self):
        unknown=dict(self.payload,id='id',source_id='lh_sale',mapping={},rows=[{'units':None,'supply_month':f'{today().year+1}-01'}])
        result=source_events(unknown,today())
        self.assertIsNone(result[0]['units'])
        construction=dict(unknown,source_id='lh_construction',rows=None,completion_plan_date=f'{today().year+2}-03-01')
        event=source_events(construction,today())[0]
        self.assertEqual(event['stage'],'COMPLETION')
        self.assertFalse(event['actual_verified'])
        self.assertIn('입주일 아님',event['basis'])

    def test_goal_save_auth_concurrency_idempotence_and_no_official_total(self):
        path='/poc/home/api/admin/targets/'+self.project
        payload={'revision_no':0,'targets':[self.goal()]}
        self.assertEqual(self.client.post(path,json=payload).status_code,401)
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'goal-test-secret'}):
            response=self.client.post(path,json=payload,headers=self.auth(path))
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['revision_no'],1)
            self.assertEqual(self.client.post(path,json=payload,headers=self.auth(path)).status_code,409)
            payload['revision_no']=1
            unchanged=self.client.post(path,json=payload,headers=self.auth(path)).json()
            self.assertEqual(unchanged['outcome'],'unchanged')
        roadmap=self.client.get('/poc/home/api/roadmap').json()
        self.assertEqual(roadmap['manual_project_count'],1)
        self.assertEqual(roadmap['items'][0]['annual'][-1]['events'][0]['origin'],'MANUAL')
        self.assertIsNone(self.client.get('/poc/home/api/overview').json()['official_total_units'])
        with self.service.sessions() as session:
            self.assertEqual(len(session.scalars(select(Audit)).all()),1)
            self.assertEqual(len(session.scalars(select(Revision).where(Revision.kind=='goal')).all()),1)

    def test_target_validation_duplicates_negative_units_and_invalid_link(self):
        path='/poc/home/api/admin/targets/'+self.project
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'goal-test-secret'}):
            for targets,status in [([self.goal(),self.goal()],400),([self.goal(today().year+11)],400),
                                   ([dict(self.goal(),units=-1)],422),([dict(self.goal(),basis=' ')],400),
                                   ([dict(self.goal(),evidence_url='http://example.org')],400)]:
                response=self.client.post(path,json={'revision_no':0,'targets':targets},headers=self.auth(path))
                self.assertEqual(response.status_code,status)
        self.assertEqual(self.service.targets(self.project)['revision_no'],0)

    def test_goal_history_and_mapping_are_reproduced_at_historical_cutoff(self):
        old=today()-timedelta(days=1)
        timestamp=datetime.combine(old,datetime.min.time(),timezone.utc)
        self.service.save_targets(self.project,0,[self.goal(units=None)])
        with self.service.sessions.begin() as session:
            for record in session.scalars(select(Revision)):
                record.recorded_at=timestamp
                record.payload=dict(record.payload,base_date=old.isoformat())
        self.service.save_targets(self.project,1,[self.goal(units=200)])
        past=self.service.targets(self.project,old)
        self.assertIsNone(past['targets'][0]['units'])
        self.assertEqual(len(past['history']),1)
        self.assertIsNone(past['history'][0]['superseded_at'])
        self.assertEqual(self.service.projects(old)[0]['mapping']['status'],'REVIEW')
        self.assertEqual(len(self.service.targets(self.project)['history']),2)
        csv=self.client.get('/poc/home/api/roadmap/export.csv').text
        self.assertIn('MANUAL',csv)
        self.assertIn('NOT_SET',csv)
        filtered=self.client.get('/poc/home/api/roadmap/export.csv?target_filter=missing').text
        self.assertNotIn('사업 A',filtered)

    def test_expanded_samples_pagination_keeps_total_and_csv_scope(self):
        with self.service.sessions.begin() as session:
            for index in range(215):
                upsert_revision(session,'notice','cheongyak',str(index),{'name':f'공고 {index}','sample_kind':'notice',
                                'region':'서울특별시','base_date':today().isoformat(),'source_object_id':str(index)},'test')
        first=self.client.get('/poc/home/api/samples?page_size=100').json()
        last=self.client.get('/poc/home/api/samples?page=3&page_size=100').json()
        self.assertEqual(first['total'],215)
        self.assertEqual(len(first['items']),100)
        self.assertEqual(len(last['items']),15)
        self.assertEqual(first['counts']['notice'],215)
        self.assertEqual(len(self.client.get('/poc/home/api/samples/export.csv').text.splitlines()),216)
