"""Keep optimized reads equivalent, scoped, and fresh after persisted reviews."""
import unittest
from copy import deepcopy
from unittest.mock import patch
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.app import create_app
from backend.db import Base, upsert_revision
from backend.service import HomeService
from backend.supply_dashboard import marker_view


class MapCollectionPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.service=HomeService(self.engine)
        self.client=TestClient(create_app(self.engine,auto_collect=False))
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)

    def test_marker_payload_preserves_quantities_points_and_original_geometry(self):
        row=dict(id='area',longitude=127,latitude=37,target_units=100,
                 progress={'observed_units':None},geometry={'coordinates':[[[127,37]]]})
        data=dict(municipalities=[row],districts=[row],items=[{'planned_units':100}],summary={'units':100})
        before=deepcopy(data);compact=marker_view(data)
        self.assertEqual(data,before)
        self.assertNotIn('geometry',compact['municipalities'][0])
        self.assertEqual(compact['items'],data['items'])
        self.assertEqual(compact['summary'],data['summary'])
        self.assertEqual(compact['districts'][0],{k:v for k,v in row.items() if k!='geometry'})

    def test_cache_scope_compact_and_review_invalidation(self):
        sample=dict(municipalities=[dict(geometry={'type':'Polygon'},target_units=100)],districts=[],items=[])
        with patch.object(HomeService,'supply_dashboard',return_value=sample) as build:
            url='/poc/home/api/map/dashboard?policy_id=POL_2025_0907&compact=true'
            first=self.client.get(url);self.assertEqual(first.headers['X-Home-Cache'],'MISS')
            self.assertEqual(self.client.get(url).headers['X-Home-Cache'],'HIT')
            full=self.client.get(url.replace('compact=true','compact=false'))
            self.assertIn('geometry',full.json()['municipalities'][0])
            self.assertNotIn('geometry',first.json()['municipalities'][0])
            self.assertEqual(self.client.get(url+'&region=경기도').headers['X-Home-Cache'],'MISS')
            self.assertEqual(self.client.get(url+'&measure=COMPLETION').headers['X-Home-Cache'],'MISS')
            self.assertEqual(build.call_count,4)
        for endpoint,target in [('map','backend.service.HomeService.map_data'),
                                ('project-collection','backend.project_collection.collection_matrix')]:
            with patch(target,return_value={'items':[]}) as build:
                url='/poc/home/api/'+endpoint+'?policy_id=POL_2025_0907'
                self.assertEqual(self.client.get(url).headers['X-Home-Cache'],'MISS')
                self.assertEqual(self.client.get(url).headers['X-Home-Cache'],'HIT')
                self.assertEqual(build.call_count,1)
                with self.service.sessions.begin() as db:
                    upsert_revision(db,'collection_assessment','officer',endpoint,
                                    {'project_id':'p1','stage':'SUPPLY','status':'METHOD_UNKNOWN'},'review')
                self.assertEqual(self.client.get(url).headers['X-Home-Cache'],'MISS')
                self.assertEqual(build.call_count,2)
