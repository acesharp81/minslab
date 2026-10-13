"""Menu read optimizations retain evidence and invalidate on officer writes."""
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.app import create_app
from backend.db import Base, Batch, upsert_revision, now
from backend.service import HomeService
from backend.sources import SOURCES

class MenuPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.service=HomeService(self.engine)
        self.client=TestClient(create_app(self.engine,auto_collect=False))
        self.addCleanup(self.client.close);self.addCleanup(self.engine.dispose)

    def test_compact_sources_keep_status_and_full_evidence_remains_available(self):
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=SOURCES[0]['id'],status='SUCCESS',finished_at=now(),
                         stats={'record_count':17,'source_base_date':'2026-10-13','large_detail':['detail']},
                         manifest=[{'url':'https://example.org/source','sha256':'abc'}]))
        full=self.client.get('/poc/home/api/sources').json()['items'][0]
        compact=self.client.get('/poc/home/api/sources?compact=true').json()['items'][0]
        for key in ['id','name','status','record_count','last_success']:
            self.assertEqual(full[key],compact[key])
        self.assertEqual(compact['snapshot_count'],1);self.assertEqual(compact['snapshots'],[])
        self.assertEqual(full['snapshots'][0]['sha256'],'abc')
        self.assertNotIn('large_detail',compact['stats'])

    def test_menu_caches_see_saved_revision_immediately(self):
        for endpoint,method,value in [('tree','tree',[]),('mappings','mappings',{'items':[]}),
                                     ('policy-monitor','policy_monitor',{'items':[]})]:
            with self.subTest(endpoint=endpoint),patch.object(HomeService,method,return_value=value) as build:
                url='/poc/home/api/'+endpoint
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'MISS')
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'HIT')
                with self.service.sessions.begin() as db:
                    upsert_revision(db,'collection_assessment','officer',endpoint,{'status':'REVIEW'},'test')
                self.assertEqual(self.client.get(url).headers['x-home-cache'],'MISS')
                self.assertEqual(build.call_count,2)

    def test_restart_scheduler_skips_recent_success_but_manual_remains_available(self):
        source=dict(id='demo_source',implemented=True,collection_mode='PUBLIC_FILE')
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='SUCCESS',finished_at=now()))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one',return_value={'status':'FAILED'}) as collect:
            result=self.service.collect_all(scheduled=True)
            self.assertEqual(result['results'],[]);collect.assert_not_called()
            self.service.collect_all(source_id=source['id'])
            collect.assert_called_once()

    def test_scheduler_collects_expired_sources_and_backs_off_failures(self):
        from datetime import timedelta
        source=dict(id='demo_source',implemented=True,collection_mode='PUBLIC_FILE')
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='SUCCESS',finished_at=now()-timedelta(days=2),started_at=now()-timedelta(days=2)))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one',return_value={'status':'FAILED'}) as collect,patch('backend.stage_evidence.refresh'),patch('backend.project_collection.refresh_links'):
            self.service.collect_all(scheduled=True)
            collect.assert_called_once()
        with self.service.sessions.begin() as db:
            db.add(Batch(source_id=source['id'],status='FAILED',finished_at=now()))
        with patch('backend.service.SOURCES',[source]),patch.object(self.service,'collect_one') as collect:
            self.service.collect_all(scheduled=True)
            collect.assert_not_called()
