import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

from backend.api_samples import base, collect_locations, collect_notices, parse_notices, parse_permits
from backend.app import create_app
from backend.collectors import Fetcher
from backend.db import Base, Mapping, Revision
from backend.service import HomeService, today
from backend.sources import SOURCES

SAMPLE_SOURCES = {s['id']: s for s in SOURCES if s.get('collection_mode') == 'TEST_SAMPLE'}


class SampleParserTests(unittest.TestCase):
    def notice(self):
        return {'SUBSCRPT_AREA_CODE':'100', 'RCRIT_PBLANC_DE':today().isoformat(), 'HOUSE_MANAGE_NO':2026000001,
                'PBLANC_NO':2026000002, 'HOUSE_NM':'서울 공고', 'HSSPLY_ADRES':'서울특별시 강남구 개포동 1',
                'TOT_SUPLY_HSHLDCO':62}

    def test_notices_enforce_region_date_identifiers_and_bounded_page(self):
        row = self.notice()
        start, end = f'{today().year}-01-01', today().isoformat()
        def parse(rows):
            return parse_notices({'data':rows, 'matchCount':100}, SAMPLE_SOURCES['cheongyak'], '100', start, end)
        record = parse([row])[0][2]
        self.assertEqual(record['units'],62)
        self.assertEqual(record['policy_mapping_status'],'UNMAPPED')
        self.assertEqual(record['source_date_label'],'모집공고일')
        for rows in ([dict(row,SUBSCRPT_AREA_CODE='410')], [dict(row,RCRIT_PBLANC_DE='2099-01-01')],
                     [dict(row,HOUSE_MANAGE_NO='')], [row,row], [row]*11):
            with self.assertRaises(ValueError):
                parse(rows)

    def test_permit_pk_is_lossless_and_completion_not_inferred(self):
        data = {'response':{'header':{'resultCode':'00'}, 'body':{'totalCount':1, 'items':{'item':{
            'sigunguCd':11680, 'bjdongCd':10300, 'platPlc':'서울특별시 강남구 개포동 1',
            'mgmHsrgstPk':1000000000000000190077, 'totHhldCnt':0, 'crtnDay':20240522,
            'useInsptDay':20251201, 'useInsptSchedDay':20260101}}}}}
        records, total = parse_permits(data,SAMPLE_SOURCES['building_hub'],'서울특별시','11680','10300')
        record = records[0][2]
        self.assertEqual(records[0][1],'1000000000000000190077')
        self.assertEqual(record['source_date'],'2024-05-22')
        self.assertEqual(record['units'],0)
        self.assertIn('USE_INSPECTION_FIELD_REVIEW',record['warnings'])
        self.assertIn('ZERO_UNITS_REVIEW',record['warnings'])
        self.assertNotIn('completion_actual_date',record)
        self.assertNotIn('stage',record)
        data['response']['body']['items']['item']['platPlc'] = '경기도 수원시'
        with self.assertRaises(ValueError):
            parse_permits(data,SAMPLE_SOURCES['building_hub'],'서울특별시','11680','10300')

    def test_geocoding_is_bounded_and_not_found_keeps_null_coordinates(self):
        class Service:
            def rows(self,kind):
                return [dict(base(SAMPLE_SOURCES['cheongyak'],kind,'표본',region,f'{region} 구 {kind}{i} 일원'),
                             id=region+kind+str(i),source_object_id=str(i))
                        for region in ('서울특별시','경기도') for i in range(10)]
        calls=[]
        class Fetch:
            def get(self,*args,**kwargs):
                calls.append(kwargs['params'])
                return json.dumps({'response':{'status':'NOT_FOUND'}})
        with patch.dict(os.environ,{'POC10_VWORLD_API_KEY':'fake-key'}):
            records,stats=collect_locations(SAMPLE_SOURCES['vworld'],Fetch(),Service())
        self.assertEqual(len(calls),40)
        self.assertEqual(stats['not_found'],40)
        for _,_,payload in records:
            self.assertIsNone(payload['longitude'])
            self.assertIsNone(payload['latitude'])
            self.assertIn('GEOCODE_NOT_FOUND',payload['warnings'])
            self.assertIn('ADDRESS_APPROXIMATE',payload['warnings'])

    def test_notice_expansion_collects_all_pages_and_rejects_duplicate_pages(self):
        calls=[]
        duplicate=False
        class Fetch:
            def get(inner,*args,**kwargs):
                params=kwargs['params'];calls.append(params)
                code=params['cond[SUBSCRPT_AREA_CODE::EQ]']
                year=params['cond[RCRIT_PBLANC_DE::GTE]'][:4]
                start=(params['page']-1)*100
                if duplicate:
                    start=0
                rows=[dict(self.notice(),SUBSCRPT_AREA_CODE=code,RCRIT_PBLANC_DE=year+'-01-01',HOUSE_MANAGE_NO=f'{code}-{year}-{i}',PBLANC_NO=str(i))
                      for i in range(start,min(start+100,205))]
                return json.dumps({'data':rows,'matchCount':205})
        with patch.dict(os.environ,{'POC10_CHEONGYAK_SERVICE_KEY':'fake-key','POC10_NOTICE_START_DATE':'2018-01-01'}):
            records,stats=collect_notices(SAMPLE_SOURCES['cheongyak'],Fetch())
            self.assertEqual(len(records),410*(today().year-2018+1))
            self.assertEqual(len(calls),6*(today().year-2018+1))
            self.assertEqual(stats['period_start'],'2018-01-01')
            self.assertEqual(len(stats['annual_counts']),2*(today().year-2018+1))
            self.assertTrue(stats['region_counts']['서울특별시']['complete_query'])
            duplicate=True
            with self.assertRaises(ValueError):
                collect_notices(SAMPLE_SOURCES['cheongyak'],Fetch())

    def test_credentials_removed_from_manifest_and_echoed_response(self):
        secret='sensitive+/value='
        def respond(request):
            self.assertEqual(request.url.params['serviceKey'],secret)
            return httpx.Response(200,json={'echo':secret,'encoded':quote(secret,safe=''),'padding':'x'*150})
        with tempfile.TemporaryDirectory() as directory:
            fetcher=Fetcher('cheongyak',directory)
            fetcher.client.close()
            fetcher.client=httpx.Client(transport=httpx.MockTransport(respond))
            try:
                content=fetcher.get('https://api.odcloud.kr/api/test','json',params={'serviceKey':secret,'page':1})
            finally:
                fetcher.close()
            manifest=fetcher.manifest[0]
            self.assertNotIn(secret,content.decode())
            self.assertNotIn(quote(secret,safe=''),content.decode())
            self.assertNotIn('serviceKey',manifest['url'])
            self.assertNotIn(secret,json.dumps(manifest))
            self.assertTrue(manifest['credentials_removed'])
            self.assertEqual(hashlib.sha256(content).hexdigest(),manifest['sha256'])
            self.assertEqual((Path(directory)/manifest['file']).read_bytes(),content)

    def test_authenticated_redirect_cannot_cross_host_or_downgrade(self):
        for target in ('https://api.vworld.kr/req/address','http://api.odcloud.kr/api/test'):
            calls=[]
            def respond(request):
                calls.append(request)
                return httpx.Response(302,headers={'location':target})
            with tempfile.TemporaryDirectory() as directory:
                fetcher=Fetcher('cheongyak',directory)
                fetcher.client.close()
                fetcher.client=httpx.Client(transport=httpx.MockTransport(respond))
                try:
                    with self.assertRaises(ValueError):
                        fetcher.get('https://api.odcloud.kr/api/test',params={'serviceKey':'test-value'})
                finally:
                    fetcher.close()
            self.assertEqual(len(calls),1)


class SampleStorageTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.directory.name)
        self.payload=base(SAMPLE_SOURCES['cheongyak'],'notice','=표본 공고','서울특별시','서울특별시 강남구 개포동 1',today().isoformat())
        self.payload.update(source_object_id='notice-1',units=62,unit_basis='공고 공급세대수')
        self.app=create_app(self.engine,auto_collect=False)
        self.client=TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.directory.cleanup()

    def test_additional_types_are_queryable_with_history_and_csv_without_policy_mapping(self):
        for source_id,kind in (("building_register","register"),("lh_notice","lh_notice"),("molit_statistics","statistic"),("sh_supply_plan","sh_plan"),("sh_redevelopment","sh_project")):
            payload=base(SAMPLE_SOURCES[source_id],kind,'2018년 검증 자료','서울특별시','서울 시도 전체','2018-01-31')
            payload.update(source_object_id=kind,units=12 if kind=='statistic' else None,
                           statistic_period='201801' if kind=='statistic' else None,
                           dates={'통계 대상 종료일':'2018-01-31'},warnings=['REGIONAL_TOTAL_NOT_POLICY_ACTUAL'])
            with patch('backend.service.collect_sample',return_value=([(kind,kind,payload)],{})):
                first=self.service.collect_samples(source_id)
                second=self.service.collect_samples(source_id)
            self.assertEqual(first['results'][0]['new'],1)
            self.assertEqual(second['results'][0]['unchanged'],1)
            response=self.client.get('/poc/home/api/samples?kind='+kind)
            self.assertEqual(response.status_code,200)
            row=response.json()['items'][0]
            detail=self.client.get('/poc/home/api/samples/'+row['id']).json()
            self.assertEqual(len(detail['history']),1)
            self.assertEqual(detail['source_date'],'2018-01-31')
            by_year=self.client.get('/poc/home/api/samples?kind='+kind+'&source_year=2018').json()
            self.assertEqual(by_year['total'],1)
            self.assertEqual(by_year['source_years'],[2018])
            self.assertEqual(self.client.get('/poc/home/api/samples?kind='+kind+'&source_year=2026').json()['total'],0)
            self.assertEqual(self.client.get('/poc/home/api/samples?kind='+kind+'&as_of_date='+(today()-timedelta(days=1)).isoformat()).json()['total'],0)
        csv=self.client.get('/poc/home/api/samples/export.csv?kind=statistic').text
        self.assertIn('statistic_period',csv)
        self.assertIn('201801',csv)
        self.assertIn('2018-01-31',csv)
        self.assertEqual(self.client.get('/poc/home/api/projects').json()['total'],0)

    def test_sample_collection_is_idempotent_without_project_or_mapping(self):
        records=[('notice','notice-1',self.payload)]
        with patch('backend.service.collect_sample',return_value=(records,{'collection_mode':'TEST_SAMPLE'})):
            first=self.service.collect_samples('cheongyak')
            second=self.service.collect_samples('cheongyak')
        self.assertEqual(first['results'][0]['new'],1)
        self.assertEqual(second['results'][0]['unchanged'],1)
        with self.service.sessions() as session:
            self.assertEqual(len(session.scalars(select(Revision)).all()),1)
            self.assertEqual(len(session.scalars(select(Mapping)).all()),0)
        self.assertEqual(self.client.get('/poc/home/api/overview').json()['project_count'],0)
        data=self.client.get('/poc/home/api/samples?kind=notice').json()
        self.assertEqual(data['total'],1)
        identifier=data['items'][0]['id']
        self.assertEqual(self.client.get('/poc/home/api/samples/'+identifier).json()['history'][0]['revision_no'],1)
        self.assertEqual(self.client.get('/poc/home/api/samples?region=경기도').json()['total'],0)
        self.assertEqual(self.client.get('/poc/home/api/samples?q=개포동').json()['total'],1)
        self.assertEqual(self.client.get('/poc/home/api/samples?as_of_date='+(today()-timedelta(days=1)).isoformat()).json()['total'],0)
        self.assertIn("'=표본 공고",self.client.get('/poc/home/api/samples/export.csv').text)
        self.assertNotIn('=표본 공고',self.client.get('/poc/home/api/export.csv').text)
        self.assertEqual(self.client.get('/poc/home/api/samples?kind=project').status_code,422)

    def test_scheduler_skips_manual_samples_and_admin_refresh_selects_sample_mode(self):
        with patch.object(self.service,'collect_one',return_value={'status':'SUCCESS'}) as collect:
            self.service.collect_all()
        self.assertEqual([call.args[0]['id'] for call in collect.call_args_list],
                         [s['id'] for s in SOURCES if not s.get('manual_only') and s['id'] not in {'building_hub', 'building_register', 'building_hub_details'}])
        self.assertEqual(self.client.post('/poc/home/api/admin/refresh?mode=sample').status_code,401)
        path='/poc/home/api/admin/refresh'
        stamp=str(int(time.time()))
        signature=hmac.new(b'test-secret',f'{stamp}:POST:{path}'.encode(),hashlib.sha256).hexdigest()
        with patch.dict(os.environ,{'POC10_INTERNAL_SECRET':'test-secret'}), patch('backend.app.threading.Thread') as thread:
            response=self.client.post(path+'?mode=sample',headers={'x-home-admin':stamp+':'+signature})
        self.assertEqual(response.status_code,202)
        self.assertEqual(thread.call_args.kwargs['target'],self.app.state.service.collect_samples)
        self.assertEqual(response.json()['mode'],'sample')
