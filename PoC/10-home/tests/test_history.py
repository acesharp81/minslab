import json
import os
import tempfile
import unittest
from datetime import date,datetime,timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend.api_samples import collect_notices,collect_permits,today
from backend.app import create_app
from backend.collection_period import annual_windows,collection_start
from backend.collectors import Fetcher,integer
from backend.db import Base,Mapping,upsert_revision
from backend.history_data import collect_project_reports,construction_files
from backend.service import HomeService
from backend.sources import SOURCES


class PeriodTests(unittest.TestCase):
    def test_policy_origin_overrides_recent_year_setting_and_windows_stop_at_today(self):
        with patch.dict(os.environ,{'POC10_NOTICE_START_DATE':'2024-01-01'}):
            self.assertEqual(collection_start(),date(2018,1,1))
            windows=annual_windows(date(2026,10,2))
            self.assertEqual(len(windows),9)
            self.assertEqual(windows[0],(date(2018,1,1),date(2018,12,31)))
            self.assertEqual(windows[-1],(date(2026,1,1),date(2026,10,2)))
        with patch.dict(os.environ,{'POC10_NOTICE_START_DATE':'2017-01-01'}):
            self.assertEqual(collection_start(),date(2017,1,1))
        for value in ('not-a-date','2009-01-01','2099-01-01'):
            with patch.dict(os.environ,{'POC10_NOTICE_START_DATE':value}),self.assertRaises(ValueError):collection_start()

    def test_integral_decimal_units_do_not_round_fractional_housing_counts(self):
        self.assertEqual(integer('1,424.00'),1424)
        self.assertEqual(integer('0.0'),0)
        self.assertIsNone(integer(None))
        with self.assertRaises(ValueError):integer('1,424.50')

    def test_valid_short_empty_year_json_is_not_a_blocked_response(self):
        content={'data':[],'matchCount':0}
        with tempfile.TemporaryDirectory() as directory:
            f=Fetcher('cheongyak',directory);f.client.close()
            f.client=httpx.Client(transport=httpx.MockTransport(lambda _:httpx.Response(200,json=content)))
            try:self.assertEqual(json.loads(f.get('https://api.odcloud.kr/api/test','json')),content)
            finally:f.close()

    def test_empty_years_are_marked_unverified_without_inventing_records(self):
        source=next(s for s in SOURCES if s['id']=='cheongyak')
        class Fetch:
            def get(self,*args,**kwargs):
                p=kwargs['params'];year=p['cond[RCRIT_PBLANC_DE::GTE]'][:4];region=p['cond[SUBSCRPT_AREA_CODE::EQ]']
                rows=[] if int(year)<2020 else [{'SUBSCRPT_AREA_CODE':region,'RCRIT_PBLANC_DE':year+'-01-01',
                    'HOUSE_MANAGE_NO':region+year,'PBLANC_NO':'1','HOUSE_NM':'공고','HSSPLY_ADRES':'주소'}]
                return json.dumps({'data':rows,'matchCount':len(rows)})
        with patch.dict(os.environ,{'POC10_CHEONGYAK_SERVICE_KEY':'fake','POC10_NOTICE_START_DATE':'2018-01-01'}):
            records,stats=collect_notices(source,Fetch())
        self.assertEqual(len(records),3*(today().year-2020+1))
        self.assertTrue(all(row['status']=='NO_RESULTS_UNVERIFIED' for row in stats['annual_counts'] if row['year']<2020))

    def test_permit_default_full_pages_exceeds_previous_500_limit(self):
        source=next(s for s in SOURCES if s['id']=='building_hub')
        class Fetch:
            def get(self,*args,**kwargs):
                p=kwargs['params'];first=(p['pageNo']-1)*100
                rows=[{'sigunguCd':p['sigunguCd'],'bjdongCd':p['bjdongCd'],'platPlc':'서울특별시 주소',
                    'mgmHsrgstPk':str(index),'totHhldCnt':1} for index in range(first,min(first+100,615))]
                return json.dumps({'response':{'header':{'resultCode':'00'},'body':{'totalCount':615,'items':{'item':rows}}}})
        with patch.dict(os.environ,{'POC10_BUILDING_HUB_SERVICE_KEY':'fake','POC10_PERMIT_DISTRICT_LIMIT':'0'}),\
             patch('backend.api_samples.DISTRICTS',[('서울특별시','11680','10300','개포')]):
            records,stats=collect_permits(source,Fetch())
        self.assertEqual(len(records),615)
        self.assertTrue(stats['district_counts']['개포']['complete_query'])


class HistoryAPITests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.directory=tempfile.TemporaryDirectory()
        self.service=HomeService(self.engine,self.directory.name)
        with self.service.sessions.begin() as session:
            current,_=upsert_revision(session,'project','lh_construction','site',{'name':'현재 사업','region':'경기도',
                'municipality':'고양','program':'3기 신도시','base_date':today().isoformat(),'progress_pct':80,
                'planned_units':100,'stage':'CONSTRUCTION','stage_label':'공사 진행','warnings':[]},'test')
            self.project=current.entity_id
            session.add(Mapping(project_id=self.project,policy_id='POL_TEST',status='REVIEW',basis='근거',evidence_url='https://www.lh.or.kr/'))
            upsert_revision(session,'policy_event','policy_history','origin',{'name':'기원','origin_id':'THIRD_NEW_TOWN',
                'event_date':'2018-12-19','base_date':'2018-12-19','basis':'최초 계획'},'test')
            for index in range(205):
                upsert_revision(session,'project_report','lh_history',str(index),{'name':'과거 사업','region':'경기도',
                    'report_date':'2025-01-01','base_date':'2025-01-01','current_project_id':self.project,'progress_pct':25},'test')
            upsert_revision(session,'notice','cheongyak','notice',{'name':'공고','region':'경기도','sample_kind':'notice',
                'source_date':'2020-03-01','base_date':today().isoformat()},'test')
        self.client=TestClient(create_app(self.engine,auto_collect=False))

    def tearDown(self):self.client.close();self.engine.dispose();self.directory.cleanup()

    def test_evidence_year_query_backfills_without_faking_collection_time(self):
        result=self.client.get('/poc/home/api/history?history_year=2018').json()
        self.assertEqual(result['start_year'],2018)
        self.assertEqual(len(result['events']),1)
        self.assertEqual(result['report_total'],0)
        self.assertEqual(datetime.fromisoformat(result['events'][0]['recorded_at']).astimezone(ZoneInfo('Asia/Seoul')).date(),today())
        old=self.client.get('/poc/home/api/history?as_of_date='+(today()-timedelta(days=1)).isoformat()).json()
        self.assertEqual(old['events'],[])
        self.assertEqual(old['report_total'],0)

    def test_history_pagination_and_current_state_are_independent(self):
        result=self.client.get('/poc/home/api/history?history_year=2025&page=3').json()
        self.assertEqual(result['report_total'],205)
        self.assertEqual(len(result['reports']),5)
        self.assertEqual(result['reports'][0]['progress_pct'],25)
        self.assertEqual(self.service.projects()[0]['progress_pct'],80)
        self.assertEqual(len(self.service.projects()),1)
        empty=self.client.get('/poc/home/api/history?region=서울특별시').json()
        self.assertEqual(empty['report_total'],0)

    def test_year_coverage_uses_source_date_and_does_not_join_unmapped_notices(self):
        result=self.client.get('/poc/home/api/history').json()
        by_year={row['year']:row for row in result['years']}
        self.assertEqual(by_year[2020]['notice_count'],1)
        self.assertEqual(by_year[2019]['coverage_status'],'NOT_AVAILABLE')
        result=self.client.get('/poc/home/api/history?policy_id=POL_TEST').json()
        self.assertTrue(all(row['notice_count']==0 for row in result['years']))

    def test_archives_are_dated_and_duplicate_versions_need_review(self):
        link='<a title="공사현황(20250101).docx" href="/boardDownload.es?seq=1"></a>'
        self.assertEqual(construction_files(link,'https://www.lh.or.kr/board.es')[0][0],'2025-01-01')
        with self.assertRaises(ValueError):construction_files(link+link,'https://www.lh.or.kr/board.es')
