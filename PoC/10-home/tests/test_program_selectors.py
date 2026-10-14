import unittest
from unittest.mock import patch
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from backend.db import Base
from backend.app import create_app
from backend.service import HomeService
from backend.program_management import scoped_model

class ProgramSelectorTests(unittest.TestCase):
    def test_policy_filter_excludes_other_unlinked_and_released_programs(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool);Base.metadata.create_all(engine)
        rows=[dict(id='A',name='A',policy_id='P1',status='REVIEW'),dict(id='B',name='B',policy_id='P2',status='CONFIRMED'),dict(id='C',name='C',policy_id='P1',status='RELEASED'),dict(id='D',name='D',policy_id='P1',status='REJECTED'),dict(id='E',name='E',policy_id='UNASSIGNED',status='REVIEW')]
        with TestClient(create_app(engine,auto_collect=False)) as client,patch.object(HomeService,'program_links',return_value=rows):
            self.assertEqual([r['id'] for r in client.get('/poc/home/api/programs?policy_id=P1').json()['items']],['A'])
            self.assertEqual([r['id'] for r in client.get('/poc/home/api/programs?policy_id=P2').json()['items']],['B'])
            self.assertEqual(client.get('/poc/home/api/programs?policy_id=EMPTY').json()['items'],[])
            self.assertEqual(len(client.get('/poc/home/api/programs').json()['items']),5)
    def test_other_policy_program_uses_own_sources_and_pinned_dates(self):
        row=dict(id='OWN',name='내 사업',region='경기도',source_id='policy_129',base_date='2026-01-29',planned_units=500,start_actual_date='2026-02-01',start_plan_month='2026-02',evidence_url='https://example.org',mapping=dict(program_id='B',policy_id='P2',status='REVIEW'))
        class Service:
            def projects(self,**kwargs):return [row,dict(row,id='OTHER',mapping=dict(program_id='A',policy_id='P1',status='REVIEW'))]
            def rows(self,*args):return []
        policy_model=dict(policy_id='P1',as_of_date='2026-10-14',portfolio_cohorts=[dict(id='FOREIGN',program_id='B',units=999999)])
        with patch('backend.stage_evidence.linked_events',return_value={}),patch('backend.evidence_bridge.by_project',return_value={}):
            model=scoped_model(Service(),dict(id='B',policy_id='P2'),policy_model)
        self.assertEqual([c['id'] for c in model['portfolio_cohorts']],['OWN'])
        self.assertEqual(model['portfolio_cohorts'][0]['units'],500)
        self.assertEqual(model['portfolio_cohorts'][0]['events'][0]['event_date'],'2026-02-01')
        self.assertEqual(policy_model['portfolio_cohorts'][0]['units'],999999)
