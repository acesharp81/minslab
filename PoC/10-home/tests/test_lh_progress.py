import csv
import io
import json
import tempfile
import unittest
from datetime import date
from unittest.mock import patch
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from backend.app import create_app
from backend.db import Base, upsert_revision
from backend.lh_progress import collect_progress, detail_data, observation_date, percentage, site_meta
from backend.service import HomeService

SITE='<tr class="detailView" data-bzdtcd="100" data-hcblkcd="01" data-bzdtnm="고양창릉" data-cnpnm="경기도" data-bnm="A-04"></tr>'

def detail(pct=30):
    return dict(cntCwsttDetailInfo=dict(hshCnt=900,conPrrt=pct,csstDt='2024-10-31',ccwDt='2027-11-14'),
        cntCwsttDetailList=[dict(conPgrsAdmNo='history',bzdtCd='100',hcBlkCd='01',mtiRgsDt='20260629',
                              conPrrt=1.86,cmnAhflNm='2024년03월현장전경.jpg',delYn='N'),
            dict(conPgrsAdmNo='h2',bzdtCd='100',hcBlkCd='01',mtiRgsDt='20260629',conPrrt=2.65,cmnAhflNm='2024년04월현장전경.jpg'),
            dict(conPgrsAdmNo='h3',bzdtCd='100',hcBlkCd='01',mtiRgsDt='20260629',conPrrt=3.71,cmnAhflNm='2024년05월현장전경.jpg')])

class LHProgressTests(unittest.TestCase):
    def test_explicit_backfilled_photo_month_retains_registration_date(self):
        result=observation_date(detail()['cntCwsttDetailList'][0],allow_photo_month=True)
        self.assertEqual(result[:3],('2024-03-01','MONTH','2026-06-29'))
        result=observation_date(dict(mtiRgsDt='20260629',cmnAhflNm='3월.png'))
        self.assertEqual(result[:3],('2026-06-29','DAY','2026-06-29'))

    def test_percent_zero_is_known_and_no_invalid_percent_is_coerced(self):
        self.assertEqual(percentage(0),0)
        self.assertIsNone(percentage(None))
        for value in (True,101,-1,'진행','75%'):
            with self.assertRaises(ValueError):percentage(value)

    def test_block_normalization_uses_actual_region_not_headquarters(self):
        meta=site_meta(BeautifulSoup(SITE,'html.parser').tr)
        self.assertEqual((meta['district'],meta['block'],meta['municipality']),('고양창릉','A-04','고양'))
        self.assertIsNone(site_meta(BeautifulSoup(SITE.replace('경기도','인천광역시'),'html.parser').tr))
        with self.assertRaises(ValueError):detail_data('<html>정보 없음</html>')

    def collect(self,pct=30,projects=()):
        class Fetch:
            def get(self,url,**kwargs):
                if 'cwsttList' in url:return '<form id="srchForm">전체 1 건<table>'+SITE+'</table></form>'
                return 'var result = '+json.dumps(detail(pct))+';'
        class Service:
            def rows(self,kind):return projects
        with patch('backend.lh_progress.time.sleep'),patch('backend.lh_progress.today',return_value=date(2026,10,3)):
            return collect_progress(dict(url='https://apply.lh.or.kr/lhapply/land/cwsttList.do'),Fetch(),Service())

    def test_historical_progress_does_not_copy_current_capacity_and_preserves_native_pct(self):
        rows,stats=self.collect()
        reports=[r[2] for r in rows if r[0]=='project_report']
        self.assertEqual(reports[0]['progress_pct'],1.86)
        self.assertIsNone(reports[0]['planned_units'])
        self.assertEqual(reports[0]['source_registration_date'],'2026-06-29')
        self.assertEqual(stats['observations_by_year'],{'2024':3})
        self.assertTrue(stats['complete_query'])

    def test_matching_keeps_existing_master_and_completed_stock_is_not_added(self):
        owner=dict(id='current',source_id='lh_construction',region='경기도',district='고양창릉',block='A4',name='건설공사',warnings=[])
        records,_=self.collect(projects=[owner])
        self.assertEqual([r[0] for r in records],['project_report']*3)
        self.assertEqual(records[0][2]['current_project_id'],'current')
        records,_=self.collect(pct=100)
        self.assertEqual([r[0] for r in records],['project_report']*3)

    def test_page_two_uses_boundaries_and_repeated_page_is_rejected(self):
        calls=[]
        filler=SITE.replace('경기도','인천광역시')
        class Fetch:
            def get(self,url,**kwargs):
                if 'cwsttList' in url:
                    params=kwargs['params'];calls.append(params)
                    return '<form id="srchForm">전체 101 건<table>'+(filler*100 if params['minSn']==0 else SITE)+'</table></form>'
                return 'var result = '+json.dumps(detail())+';'
        class Service:
            def rows(self,kind):return []
        with patch('backend.lh_progress.time.sleep'):
            records,stats=collect_progress(dict(url='https://apply.lh.or.kr/lhapply/land/cwsttList.do'),Fetch(),Service())
        self.assertEqual((calls[1]['minSn'],calls[1]['maxSn']),(100,200))
        self.assertEqual(stats['fetched'],101)
        self.assertEqual(stats['scope_blocks'],1)

    def test_completed_existing_candidate_keeps_its_identity_and_updates_native_stage(self):
        owner=dict(id='owned',source_id='lh_progress',source_object_id='100|01',region='경기도',district='고양창릉',block='A4',name='공사',warnings=[])
        payload=detail(100)
        for row in payload['cntCwsttDetailList']:row['conPrrt']=100
        with patch('test_lh_progress.detail',return_value=payload):
            records,_=self.collect(pct=100,projects=[owner])
        project=next(r[2] for r in records if r[0]=='project')
        self.assertEqual(project['stage'],'COMPLETED')
        self.assertEqual(project['progress_pct'],100)
        self.assertIsNone(project.get('completion_actual_date'))

    def test_history_csv_uses_actual_pct_and_month_precision(self):
        engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(engine)
        with tempfile.TemporaryDirectory() as directory:
            service=HomeService(engine,directory)
            records,_=self.collect(pct=100)
            with service.sessions.begin() as session:
                for kind,key,payload in records:upsert_revision(session,kind,'lh_progress',key,payload,'test')
            with TestClient(create_app(engine,auto_collect=False)) as client:
                response=client.get('/poc/home/api/history/export.csv?history_year=2024')
                self.assertEqual(response.status_code,200)
                rows=list(csv.DictReader(io.StringIO(response.content.decode('utf-8-sig'))))
                self.assertEqual({r['progress_pct'] for r in rows},{'1.86','2.65','3.71'})
                self.assertEqual(rows[0]['date_precision'],'MONTH')
                self.assertEqual({r['report_period'] for r in rows},{'2024-03','2024-04','2024-05'})
                self.assertEqual(rows[0]['planned_units'],'')
                response=client.get('/poc/home/api/history?history_year=2024&source_id=lh_progress')
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.json()['report_total'],3)
        engine.dispose()
