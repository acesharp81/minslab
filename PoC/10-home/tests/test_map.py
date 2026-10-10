import json
import os
import tempfile
import unittest
from datetime import timedelta
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.app import create_app
from backend.db import Base, Mapping, upsert_revision
from backend.map_data import district_term, same_district, parse_page
from backend.service import HomeService, today
from backend.tiles import tile, _fetch


class DistrictTests(unittest.TestCase):
    def test_district_names_keep_numbered_districts_distinct(self):
        self.assertEqual(district_term({'source_id':'lh_construction','name':'남양주왕숙2 A-3BL (공공분양)'}),'남양주왕숙2')
        self.assertEqual(district_term({'source_id':'lh_rent','name':'고양창릉 A-4 (공공임대'}),'고양창릉')
        self.assertTrue(same_district('남양주왕숙2','남양주왕숙2 공공주택지구'))
        self.assertFalse(same_district('남양주왕숙','남양주왕숙2 공공주택지구'))
        self.assertFalse(same_district('구리갈매','구리갈매역세권 공공주택지구'))
        self.assertTrue(same_district('오산세교2','오산세교2지구 택지개발사업'))
        self.assertTrue(same_district('고덕국제화계획','고덕국제화계획지구'))
        self.assertIsNone(district_term({'source_id':'policy_0907','name':'사업 후보'}))

    def test_space_layer_rejects_unexpected_schema_and_missing_evidence(self):
        self.assertEqual(parse_page({'response':{'status':'NOT_FOUND'}}),([],0))
        feature={'geometry':{'type':'Polygon','coordinates':[]},'properties':{'zonename':'공식 지구'}}
        valid={'response':{'status':'OK','record':{'total':'1'},'result':{'featureCollection':{'features':[feature]}}}}
        self.assertEqual(parse_page(valid)[1],1)
        for change in ({'status':'ERROR'}, {'status':'OK'}, {'status':'OK','record':{'total':10001},'result':valid['response']['result']}):
            with self.assertRaises(ValueError):parse_page({'response':change})
        feature['geometry']['type']='Point'
        with self.assertRaises(ValueError):parse_page(valid)


class MapAPITests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.directory.name)
        with self.service.sessions.begin() as session:
            self.ids=[]
            for name,region in [('서울 사업','서울특별시'),('경기 사업','경기도'),('미연결 사업','경기도')]:
                row,_=upsert_revision(session,'project','lh_sale',name,{'name':name,'region':region,'municipality':'구',
                    'program':'공공분양','stage':'PLANNED_SUPPLY','stage_label':'공급계획','planned_units':None,
                    'base_date':today().isoformat(),'warnings':[],'evidence_url':'https://apply.lh.or.kr/'},'test')
                self.ids.append(row.entity_id)
                session.add(Mapping(project_id=row.entity_id,policy_id='POL_TEST',status='REVIEW',basis='근거',evidence_url='https://apply.lh.or.kr/'))
            upsert_revision(session,'district','vworld_district','지구',{'name':'공식 지구','project_ids':self.ids[:2],
                'longitude':127,'latitude':37.5,'geometry':{'type':'MultiPolygon','coordinates':[]},
                'base_date':today().isoformat(),'link_status':'REVIEW'},'test')
            parent,_=upsert_revision(session,'notice','cheongyak','공고',{'name':'API 관측','address':'서울특별시 주소',
                'region':'서울특별시','base_date':today().isoformat()},'test')
            for status in ('OK','NOT_FOUND'):
                upsert_revision(session,'location','vworld',status,{'name':'주소','region':'서울특별시',
                    'base_date':today().isoformat(),'parent_sample_id':parent.entity_id,'resolution_status':status,
                    'longitude':127 if status=='OK' else None,'latitude':37.5 if status=='OK' else None},'test')
        self.client=TestClient(create_app(self.engine,auto_collect=False))

    def tearDown(self):
        self.client.close();self.engine.dispose();self.directory.cleanup()

    def test_real_district_links_keep_unlocated_and_api_samples_separate(self):
        result=self.client.get('/poc/home/api/map').json()
        self.assertEqual(result['project_count'],3)
        self.assertEqual(result['located_project_count'],2)
        self.assertEqual(result['unlocated_project_ids'],[self.ids[2]])
        self.assertEqual(len(result['districts']),1)
        self.assertEqual(len(result['observations']),1)
        self.assertNotIn('planned_units',result['districts'][0])
        self.assertNotIn('policy_id',result['observations'][0])

    def test_map_filters_intersect_links_and_hide_unmapped_observations(self):
        result=self.client.get('/poc/home/api/map?region=경기도').json()
        self.assertEqual(result['project_count'],2)
        self.assertEqual(result['districts'][0]['project_ids'],[self.ids[1]])
        self.assertEqual(result['observations'],[])
        self.assertEqual(self.client.get('/poc/home/api/map?policy_id=POL_TEST').json()['observations'],[])
        result=self.client.get('/poc/home/api/map?q=미연결').json()
        self.assertEqual(result['districts'],[])
        self.assertEqual(result['unlocated_project_ids'],[self.ids[2]])

    def test_historical_map_never_uses_later_geometry(self):
        result=self.client.get('/poc/home/api/map?as_of_date='+(today()-timedelta(days=1)).isoformat()).json()
        self.assertEqual(result['districts'],[])
        self.assertEqual(result['observations'],[])

    def test_tile_response_is_png_and_generic_error_has_no_secret(self):
        png=b'\x89PNG\r\n\x1a\nexample'
        with patch('backend.app.tile',return_value=png):
            response=self.client.get('/poc/home/api/tiles/10/873/396.png')
            self.assertEqual(response.content,png)
            self.assertEqual(response.headers['content-type'],'image/png')
            self.assertEqual(response.headers['cache-control'],'public, max-age=3600')
        with patch('backend.app.tile',side_effect=ValueError('private-key')):
            response=self.client.get('/poc/home/api/tiles/10/873/396.png')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('private-key',response.text)


class TileTests(unittest.TestCase):
    def tearDown(self):_fetch.cache_clear()

    def test_fixed_official_origin_key_only_server_side_and_cache(self):
        png=b'\x89PNG\r\n\x1a\nexample'
        calls=[]
        def respond(request):
            calls.append(request)
            self.assertEqual(request.url.host,'api.vworld.kr')
            self.assertEqual(request.url.path,'/req/wmts/1.0.0/test-private-key/Base/10/396/873.png')
            self.assertEqual(request.headers['referer'],'https://www.minslab.kr/poc/home/')
            return httpx.Response(200,content=png)
        client=httpx.Client(transport=httpx.MockTransport(respond))
        with patch.dict(os.environ,{'POC10_VWORLD_API_KEY':'test-private-key'}),patch('backend.tiles.httpx.Client',return_value=client):
            self.assertEqual(tile(10,873,396),png)
            self.assertEqual(tile(10,873,396),png)
        self.assertEqual(len(calls),1)

    def test_out_of_range_never_requests_tiles(self):
        with patch('backend.tiles._fetch') as fetch:
            for xyz in ((6,1,1),(19,1,1),(10,-1,1),(10,1,1024)):
                with self.assertRaises(ValueError):tile(*xyz)
            fetch.assert_not_called()

    def test_redirect_and_non_image_are_rejected(self):
        for response in (httpx.Response(302,headers={'location':'https://example.com/'}),httpx.Response(200,content=b'API key error')):
            client=httpx.Client(transport=httpx.MockTransport(lambda _:response))
            with patch.dict(os.environ,{'POC10_VWORLD_API_KEY':'test-private-key'}),patch('backend.tiles.httpx.Client',return_value=client):
                with self.assertRaises(ValueError) as error:tile(10,873,396)
                self.assertNotIn('test-private-key',str(error.exception))
